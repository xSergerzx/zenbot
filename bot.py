import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from sync import sync
from expenses import (
    get_all_today_expenses,
    get_all_month_expenses,
)


load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "TELEGRAM_BOT_TOKEN не указан в .env"
    )


def format_expenses(title, expenses):
    lines = [title, ""]

    emojis = {
        "Алкоголь": "🍺",
        "Кофе": "☕",
        "Продукты": "🛒",
    }

    total = 0

    for category, amount in expenses.items():
        total += amount

        emoji = emojis.get(category, "💰")

        lines.append(
            f"{emoji} {category}: {amount:.2f} грн"
        )

    lines.extend([
        "",
        "────────────────",
        f"💰 Итого: {total:.2f} грн",
    ])

    return "\n".join(lines)


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
        sync()

        expenses = get_all_today_expenses()

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
        sync()

        expenses = get_all_month_expenses()

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
        sync()

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

    print("Telegram-бот запущен.")

    application.run_polling()


if __name__ == "__main__":
    main()