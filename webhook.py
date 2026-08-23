import os
import json
import asyncio
import psycopg
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Импортируем ваши обновленные функции
from sync import sync_zenmoney
from expenses import get_all_today_expenses, get_all_month_expenses

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not TOKEN or not DATABASE_URL:
    raise RuntimeError("Проверьте переменные окружения TELEGRAM_BOT_TOKEN и DATABASE_URL")

# Инициализируем приложение Telegram
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

# Регистрируем команды
bot_app.add_handler(CommandHandler("start", start))
bot_app.add_handler(CommandHandler("today", today))
bot_app.add_handler(CommandHandler("month", month))
bot_app.add_handler(CommandHandler("sync", sync_command))

async def process_update(update_dict):
    # Инициализация и обработка внутри изолированного потока вызова
    if not bot_app.updater:
        await bot_app.initialize()
    
    update = Update.de_json(update_dict, bot_app.bot)
    await bot_app.process_update(update)

# Стандартный WSGI-интерфейс, который Vercel подхватывает автоматически
def application(environ, start_response):
    request_method = environ.get('REQUEST_METHOD', 'GET')
    
    if request_method == 'GET':
        start_response('200 OK', [('Content-type', 'text/plain; charset=utf-8')])
        return ["Бот готов к работе 🚀".encode('utf-8')]
        
    elif request_method == 'POST':
        try:
            try:
                request_body_size = int(environ.get('CONTENT_LENGTH', 0))
            except ValueError:
                request_body_size = 0
                
            request_body = environ['wsgi.input'].read(request_body_size)
            body = json.loads(request_body.decode('utf-8'))
            
            # Нативная изоляция асинхронного Event Loop под Serverless рантайм
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(process_update(body))
            finally:
                loop.close()
            
            start_response('200 OK', [('Content-type', 'application/json')])
            return [json.dumps({"status": "ok"}).encode('utf-8')]
            
        except Exception as e:
            start_response('500 Internal Server Error', [('Content-type', 'application/json')])
            return [json.dumps({"error": str(e)}).encode('utf-8')]
            
    start_response('405 Method Not Allowed', [('Content-type', 'text/plain')])
    return [b"Method Not Allowed"]
