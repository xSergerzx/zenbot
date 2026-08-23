import os
import psycopg
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from sync import sync_zenmoney
from expenses import (
    get_all_today_expenses,
    get_all_month_expenses,
    format_expenses,
)

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not TOKEN:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN не указан в .env"
    )

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL не указан в .env"
    )



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Я могу показать расходы из ZenMoney.\n\n"
        "/today — расходы сегодня\n"
        "/month — расходы за текущий месяц\n"
        "/sync — синхронизировать ZenMoney"
    )


async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            sync_zenmoney(conn)
            expenses = get_all_today_expenses(conn)
            conn.commit()

        message = format_expenses(
            "📅 РАСХОДЫ СЕГОДНЯ",
            expenses,
        )

        await update.message.reply_text(message)

    except Exception as error:
        await update.message.reply_text(
            f"❌ Ошибка:\n{error}"
        )


async def month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            sync_zenmoney(conn)
            expenses = get_all_month_expenses(conn)
            conn.commit()

        message = format_expenses(
            "📊 РАСХОДЫ ЗА ТЕКУЩИЙ МЕСЯЦ",
            expenses,
        )

        await update.message.reply_text(message)

    except Exception as error:
        await update.message.reply_text(
            f"❌ Ошибка:\n{error}"
        )


async def sync_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            sync_zenmoney(conn)
            conn.commit()

        await update.message.reply_text(
            "✅ ZenMoney синхронизирован."
        )

    except Exception as error:
        await update.message.reply_text(
            f"❌ Ошибка синхронизации:\n{error}"
        )


def main():
    application = (
        Application.builder()
        .token(TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("today", today)
    )

    application.add_handler(
        CommandHandler("month", month)
    )

    application.add_handler(
        CommandHandler("sync", sync_command)
    )

    print("Telegram-бот запущен (polling).")

    application.run_polling()


if __name__ == "__main__":
    main()