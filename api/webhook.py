import os
import json
import asyncio
import psycopg
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler

# Импортируем ваши обновленные функции
from sync import sync_zenmoney
from expenses import get_all_today_expenses, get_all_month_expenses

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не указан в переменных окружения")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не указан в переменных окружения")

# Создаем Flask-приложение для Vercel
app = Flask(__name__)

# Инициализируем приложение Telegram БЕЗ запуска polling
application = Application.builder().token(TOKEN).build()

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

async def start(update: Update, context):
    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Я могу показать расходы из ZenMoney.\n\n"
        "/today — расходы сегодня\n"
        "/month — расходы за текущий месяц\n"
        "/sync — синхронизировать ZenMoney"
    )

async def today(update: Update, context):
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            sync_zenmoney(conn)
            expenses = get_all_today_expenses(conn)
            conn.commit()

        message = format_expenses("📅 РАСХОДЫ СЕГОДНЯ", expenses)
        await update.message.reply_text(message)
    except Exception as error:
        await update.message.reply_text(f"❌ Ошибка:\n{error}")

async def month(update: Update, context):
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            sync_zenmoney(conn)
            expenses = get_all_month_expenses(conn)
            conn.commit()

        message = format_expenses("📊 РАСХОДЫ ЗА ТЕКУЩИЙ МЕСЯЦ", expenses)
        await update.message.reply_text(message)
    except Exception as error:
        await update.message.reply_text(f"❌ Ошибка:\n{error}")

async def sync_command(update: Update, context):
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            sync_zenmoney(conn)
            conn.commit()
        await update.message.reply_text("✅ ZenMoney синхронизирован.")
    except Exception as error:
        await update.message.reply_text(f"❌ Ошибка синхронизации:\n{error}")

# Регистрируем обработчики команд
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("today", today))
application.add_handler(CommandHandler("month", month))
application.add_handler(CommandHandler("sync", sync_command))


async def process_update(update_dict):
    """Асинхронная обработка апдейта через python-telegram-bot"""
    # Гарантируем инициализацию внутренней инфраструктуры PTB перед обработкой апдейта
    if not application.updater:
        await application.initialize()
    
    update = Update.de_json(update_dict, application.bot)
    await application.process_update(update)


# Настраиваем роутинг, на который Telegram шлет POST-запросы
@app.route("/webhook", methods=["POST"])
def webhook_handler():
    try:
        body = request.get_json(force=True)
        
        # Создаем и устанавливаем изолированный цикл событий для текущего потока запроса
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        loop.run_until_complete(process_update(body))
        loop.close()
        
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"Ошибка при обработке вебхука: {e}")
        return jsonify({"error": str(e)}), 500

# Корневой URL для проверки доступности (GET-запрос)
@app.route("/", methods=["GET"])
def index():
    return "Бот готов к работе 🚀", 200
