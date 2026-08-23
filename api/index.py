import os
import asyncio
import psycopg
import sys
import logging
from fastapi import FastAPI, Request, Response
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from telegram.helpers import escape_markdown

# Добавляем корневую директорию в путь поиска модулей, чтобы импортировать sync и expenses
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

from sync import sync_zenmoney
from expenses import get_all_today_expenses, get_all_month_expenses, format_expenses, get_all_limits, set_limit

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI()
bot_app = Application.builder().token(TOKEN).build()

def get_main_keyboard():
    """Возвращает постоянную клавиатуру главного меню."""
    keyboard = [
        ["📅 Сегодня", "📊 Месяц"],
        ["🔄 Синхронизация", "⚙️ Лимиты"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def fix_markdown(text):
    """Экранирует системные символы для MarkdownV2, исключая разметку (* и [ ] для бар)."""
    # Символы, которые PTB требует экранировать в MarkdownV2, если они не являются разметкой
    bad_chars = ['_', '-', '.', '!', '(', ')', '{', '}', '+', '#']
    for char in bad_chars:
        text = text.replace(char, f"\\{char}")
    return text

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет\! 👋\n\nЯ помогу контролировать расходы из ZenMoney\.\n\n"
        "Используй кнопки меню или команды:\n"
        "• `/today` — расходы за сегодня\n"
        "• `/month` — расходы за месяц\n"
        "• `/setlimit [Категория] [День] [Месяц]` — установить лимиты",
        reply_markup=get_main_keyboard(),
        parse_mode="MarkdownV2"
    )

async def handle_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message:
            await update.message.reply_chat_action("typing")
        
        with psycopg.connect(DATABASE_URL) as conn:
            sync_zenmoney(conn)
            expenses = get_all_today_expenses(conn)
            # Из expenses.py передаем True/False для флага is_monthly
            raw_message = format_expenses(conn, "📅 *РАСХОДЫ СЕГОДНЯ*", expenses, is_monthly=False)
            conn.commit()
            
        await update.message.reply_text(fix_markdown(raw_message), parse_mode="MarkdownV2")
    except Exception as error:
        logger.error(f"Ошибка в today: {error}")
        await update.message.reply_text(f"❌ Ошибка:\n{error}")

async def handle_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message:
            await update.message.reply_chat_action("typing")
            
        with psycopg.connect(DATABASE_URL) as conn:
            sync_zenmoney(conn)
            expenses = get_all_month_expenses(conn)
            raw_message = format_expenses(conn, "📊 *РАСХОДЫ ЗА ТЕКУЩИЙ МЕСЯЦ*", expenses, is_monthly=True)
            conn.commit()
            
        await update.message.reply_text(fix_markdown(raw_message), parse_mode="MarkdownV2")
    except Exception as error:
        logger.error(f"Ошибка в month: {error}")
        await update.message.reply_text(f"❌ Ошибка:\n{error}")

async def handle_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            sync_zenmoney(conn)
            conn.commit()
        await update.message.reply_text("✅ ZenMoney успешно синхронизирован\.", reply_markup=get_main_keyboard())
    except Exception as error:
        logger.error(f"Ошибка при синхронизации: {error}")
        await update.message.reply_text(f"❌ Ошибка синхронизации:\n{error}")

async def handle_limits_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выводит текущие лимиты и Inline-кнопки для настройки."""
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            limits = get_all_limits(conn)
        
        lines = ["⚙️ *ТЕКУЩИЕ ЛИМИТЫ*", ""]
        keyboard = []
        
        for category, data in limits.items():
            daily = f"{data['daily']:.0f} грн" if data['daily'] else "не установлен"
            monthly = f"{data['monthly']:.0f} грн" if data['monthly'] else "не установлен"
            lines.append(f"• *{category}*:\n  День: {daily} | Месяц: {monthly}")
            
            # Кнопка для изменения конкретной категории
            keyboard.append([InlineKeyboardButton(f"Изменить {category}", callback_data=f"edit_lim:{category}")])
            
        lines.append("\n💡 Чтобы изменить, нажмите кнопку ниже или введите:\n`/setlimit [Категория] [День] [Месяц]`")
        
        message_text = fix_markdown("\n".join(lines))
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode="MarkdownV2")
    except Exception as error:
        logger.error(f"Ошибка в меню лимитов: {error}")
        await update.message.reply_text(f"❌ Ошибка:\n{error}")

async def set_limit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ручная установка лимитов через команду: /setlimit Продукты 500 15000"""
    try:
        args = context.args
        if len(args) < 3:
            await update.message.reply_text(
                "⚠️ *Неверный формат команды\.*\n\n"
                "Пиши так:\n`/setlimit [Категория] [Лимит_День] [Лимит_Месяц]`\n\n"
                "Пример:\n`/setlimit Продукты 300 9000`\n"
                "_(Используй 0, если лимит не нужен)_",
                parse_mode="MarkdownV2"
            )
            return

        cat_name = args[0].capitalize()
        # Позволяем писать "продукты", "Продукты"
        valid_categories = {"Алкоголь": "Алкоголь", "Кофе": "Кофе", "Продукты": "Продукты"}
        cat_name = valid_categories.get(cat_name)

        if not cat_name:
            await update.message.reply_text("❌ Ошибка: Неизвестная категория\. Доступны: Продукты, Кофе, Алкоголь")
            return

        daily = float(args[1])
        monthly = float(args[2])
        
        # Если передан 0, превращаем его в None (удаление лимита)
        daily_val = None if daily <= 0 else daily
        monthly_val = None if monthly <= 0 else monthly

        with psycopg.connect(DATABASE_URL) as conn:
            set_limit(conn, cat_name, daily_val, monthly_val)
            conn.commit()

        await update.message.reply_text(f"✅ Лимиты для категории *{cat_name}* успешно сохранены\!", parse_mode="MarkdownV2")
    except ValueError:
        await update.message.reply_text("❌ Ошибка: Лимиты должны быть числами\.")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на кнопки под сообщениями (Inline)."""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("edit_lim:"):
        category = query.data.split(":")[1]
        await query.message.reply_text(
            f"✍️ Чтобы обновить лимиты для *{category}*, отправь команду:\n"
            f"`/setlimit {category} [День] [Месяц]`\n\n"
            f"Например:\n`/setlimit {category} 500 10000`",
            parse_mode="MarkdownV2"
        )

async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Маршрутизатор текстовых нажатий постоянной клавиатуры."""
    text = update.message.text
    if text == "📅 Сегодня":
        await handle_today(update, context)
    elif text == "📊 Месяц":
        await handle_month(update, context)
    elif text == "🔄 Синхронизация":
        await handle_sync(update, context)
    elif text == "⚙️ Лимиты":
        await handle_limits_menu(update, context)

# Регистрация обработчиков
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("today", handle_today))
bot_app.add_handler(CommandHandler("month", handle_month))
bot_app.add_handler(CommandHandler("sync", handle_sync))
bot_app.add_handler(CommandHandler("setlimit", set_limit_command))

# Обработка кликов по встроенным (Inline) кнопкам
bot_app.add_handler(CallbackQueryHandler(callback_handler))

# Перехват сообщений с Reply-кнопок
bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler))

@app.post("/")
@app.post("/api/index")
async def webhook_handler(request: Request):
    try:
        if not TOKEN:
            return Response(content="TELEGRAM_BOT_TOKEN не установлен", status_code=500)
            
        data = await request.json()
        update = Update.de_json(data, bot_app.bot)
        
        async with bot_app:
            await bot_app.process_update(update)
            
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}")
        return Response(content=str(e), status_code=500)

@app.get("/")
@app.get("/api/index")
async def root():
    return {"status": "ok", "bot": "ZenMoney Bot"}

@app.get("/health")
async def health():
    return {"status": "ok"}
