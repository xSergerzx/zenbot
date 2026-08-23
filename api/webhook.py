import os
import json
import asyncio
import psycopg
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler

# Импортируем обновленные под PostgreSQL функции
from sync import sync_zenmoney
from expenses import get_all_today_expenses, get_all_month_expenses

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# ВАЖНО: Используйте Pooling URL из панели Neon (обычно заканчивается на sslmode=require или порт 5432)
DATABASE_URL = os.getenv("DATABASE_URL")

if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN не указан в .env")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не указан в .env")

# 1. Инициализируем приложение Telegram БЕЗ запуска polling
# Создаем глобальный объект, чтобы он переиспользовался между вызовами serverless-функции
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
        # Открываем ОДНО соединение с Neon на время выполнения команды
        with psycopg.connect(DATABASE_URL) as conn:
            sync_zenmoney(conn)
            expenses = get_all_today_expenses(conn)
            conn.commit()  # Фиксируем изменения после синхронизации

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


# =====================================================================
# СЕРВЕРЛЕСС ТОЧКА ВХОДА (ХАНДЛЕР)
# =====================================================================

async def process_update(update_dict):
    """Асинхронная обработка апдейта через python-telegram-bot"""
    update = Update.de_json(update_dict, application.bot)
    # Инициализируем компоненты приложения, если это первый запуск инстанса
    if not application.updater:
        await application.initialize()
    await application.process_update(update)

def handler(request):
    """
    Основная функция, которую вызывает Serverless-платформа.
    Принимает объект запроса (зависит от вашей платформы, ниже пример для WSGI/Фреймворков)
    """
    # 1. Получаем JSON от Telegram Webhook
    try:
        if hasattr(request, "get_json"):
            body = request.get_json()
        elif hasattr(request, "body"):
            body = json.loads(request.body)
        else:
            body = json.loads(request)
    except Exception:
        return {"statusCode": 400, "body": "Invalid JSON"}

    # 2. Передаем апдейт в асинхронный цикл обработки Telegram
    try:
        asyncio.run(process_update(body))
        return {"statusCode": 200, "body": "OK"}
    except Exception as e:
        print(f"Ошибка при обработке вебхука: {e}")
        return {"statusCode": 500, "body": str(e)}
