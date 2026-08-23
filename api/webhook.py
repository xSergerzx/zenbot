import os
import json
import psycopg
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Импортируем ваши обновленные функции
from sync import sync_zenmoney
from expenses import get_all_today_expenses, get_all_month_expenses

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not TOKEN or not DATABASE_URL:
    raise RuntimeError("Проверьте переменные окружения TELEGRAM_BOT_TOKEN и DATABASE_URL")

# Инициализируем приложение Telegram (переименовали в bot_app, чтобы не путать с ASGI-приложением)
bot_app = Application.builder().token(TOKEN).build()

def format_expenses(title, expenses):
    lines = [title, ""]
    emojis = {"Алкоголь": "🍺", "Кофе": "☕", "Продукты": "🛒"}
    total = 0
    for category, amount in expenses.items():
        total += amount
        emoji = emojis.get(category, "💰")
        lines.append(f"{emoji} {category}: {amount:.2f} грн")
    lines.extend(["", "────────────────", f"💰 Итого: {total:.2f} грн"])
    return "\n".join(lines)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 👋\n\nЯ могу показать расходы из ZenMoney.\n\n"
        "/today — расходы сегодня\n/month — расходы за текущий месяц\n/sync — синхронизировать ZenMoney"
    )

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            sync_zenmoney(conn)
            expenses = get_all_today_expenses(conn)
            conn.commit()
        message = format_expenses("📅 РАСХОДЫ СЕГОДНЯ", expenses)
        await update.message.reply_text(message)
    except Exception as error:
        await update.message.reply_text(f"❌ Ошибка:\n{error}")

async def month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            sync_zenmoney(conn)
            expenses = get_all_month_expenses(conn)
            conn.commit()
        message = format_expenses("📊 РАСХОДЫ ЗА ТЕКУЩИЙ МЕСЯЦ", expenses)
        await update.message.reply_text(message)
    except Exception as error:
        await update.message.reply_text(f"❌ Ошибка:\n{error}")

async def sync_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            sync_zenmoney(conn)
            conn.commit()
        await update.message.reply_text("✅ ZenMoney синхронизирован.")
    except Exception as error:
        await update.message.reply_text(f"❌ Ошибка синхронизации:\n{error}")

# Регистрируем команды в боте
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("today", today))
bot_app.add_handler(CommandHandler("month", month))
bot_app.add_handler(CommandHandler("sync", sync_command))

# 🚀 Создаем легитимное ASGI-приложение, которое ищет сервер (api.webhook:application)
application = FastAPI()

@application.on_event("startup")
async def startup_event():
    # Инициализируем внутренние компоненты Telegram-бота при запуске сервера
    await bot_app.initialize()

@application.get("/")
async def root():
    # Проверка доступности в браузере (GET-запрос)
    return Response(content="Бот готов к работе 🚀", media_type="text/plain")

@application.post("/")
async def telegram_webhook(request: Request):
    # Обработка входящих вебхуков от Telegram (POST-запрос)
    try:
        body = await request.json()
        update = Update.de_json(body, bot_app.bot)
        
        # Передаем обновление в бот (работает в нативном асинхронном цикле FastAPI)
        await bot_app.process_update(update)
        
        return {"status": "ok"}
    except Exception as e:
        print(f"Ошибка в вебхуке: {e}")
        return Response(content=json.dumps({"error": str(e)}), status_code=500, media_type="application/json")
