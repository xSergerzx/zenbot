import os
import json
import asyncio
import psycopg
from http.server import BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Импортируем ваши обновленные функции
from sync import sync_zenmoney
from expenses import get_all_today_expenses, get_all_month_expenses

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not TOKEN or not DATABASE_URL:
    raise RuntimeError("Проверьте переменные окружения TELEGRAM_BOT_TOKEN и DATABASE_URL")

# Инициализируем базовое приложение Telegram
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

# Регистрируем команды
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("today", today))
application.add_handler(CommandHandler("month", month))
application.add_handler(CommandHandler("sync", sync_command))

async def process_update(update_dict):
    if not application.updater:
        await application.initialize()
    update = Update.de_json(update_dict, application.bot)
    await application.process_update(update)

# Класс-обработчик запросов, который Vercel понимает нативно из коробки
class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Корневой URL или проверка доступности в браузере
        self.send_response(200)
        self.send_header('Content-type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write("Бот готов к работе 🚀".encode('utf-8'))
        return

    def do_POST(self):
        # Обработка вебхука Telegram
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            body = json.loads(post_data.decode('utf-8'))
            
            # Асинхронный запуск обработки
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(process_update(body))
            loop.close()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
        except Exception as e:
            print(f"Ошибка в do_POST: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
        return
