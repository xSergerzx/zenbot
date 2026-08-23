import os
import asyncio
import psycopg
from fastapi import FastAPI, Request, Response
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import logging

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Импорт наших модулей
from sync import sync_zenmoney
from expenses import get_all_today_expenses, get_all_month_expenses, format_expenses

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI()

# Инициализация PTB Application
bot_app = Application.builder().token(TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 👋\n\nЯ могу показать расходы из ZenMoney.\n\n"
        "/today — расходы сегодня\n/month — расходы за текущий месяц\n/sync — синхронизировать ZenMoney"
    )

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logger.info("Выполнение команды /today")
        with psycopg.connect(DATABASE_URL) as conn:
            sync_zenmoney(conn)
            expenses = get_all_today_expenses(conn)
            conn.commit()
        message = format_expenses("📅 РАСХОДЫ СЕГОДНЯ", expenses)
        await update.message.reply_text(message)
    except Exception as error:
        logger.error(f"Ошибка в /today: {error}")
        await update.message.reply_text(f"❌ Ошибка:\n{error}")

async def month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logger.info("Выполнение команды /month")
        with psycopg.connect(DATABASE_URL) as conn:
            sync_zenmoney(conn)
            expenses = get_all_month_expenses(conn)
            conn.commit()
        message = format_expenses("📊 РАСХОДЫ ЗА ТЕКУЩИЙ МЕСЯЦ", expenses)
        await update.message.reply_text(message)
    except Exception as error:
        logger.error(f"Ошибка в /month: {error}")
        await update.message.reply_text(f"❌ Ошибка:\n{error}")

async def sync_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logger.info("Выполнение команды /sync")
        with psycopg.connect(DATABASE_URL) as conn:
            sync_zenmoney(conn)
            conn.commit()
        await update.message.reply_text("✅ ZenMoney синхронизирован.")
    except Exception as error:
        logger.error(f"Ошибка в /sync: {error}")
        await update.message.reply_text(f"❌ Ошибка синхронизации:\n{error}")

# Регистрация обработчиков
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("today", today))
bot_app.add_handler(CommandHandler("month", month))
bot_app.add_handler(CommandHandler("sync", sync_command))

@app.post("/")
async def webhook_handler(request: Request):
    try:
        if not TOKEN:
            return Response(content="TELEGRAM_BOT_TOKEN не установлен", status_code=500)
            
        data = await request.json()
        update = Update.de_json(data, bot_app.bot)
        
        # В serverless окружении используем асинхронный контекстный менеджер
        async with bot_app:
            await bot_app.process_update(update)
            
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}")
        return Response(content=str(e), status_code=500)

@app.get("/")
async def root():
    return {"status": "ok", "bot": "ZenMoney Bot"}

@app.get("/health")
async def health():
    return {"status": "ok"}
