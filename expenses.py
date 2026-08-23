import os
from datetime import date
import psycopg
from dotenv import load_dotenv

load_dotenv()

CATEGORIES = {
    "Алкоголь": os.getenv("ZENMONEY_ALCOHOL_TAG"),
    "Кофе": os.getenv("ZENMONEY_COFFEE_TAG"),
    "Продукты": os.getenv("ZENMONEY_FOOD_TAG"),
}

def generate_progress_bar(spent, limit):
    """Генерирует визуальный прогресс-бар из 5 делений."""
    if not limit or limit <= 0:
        return ""
    
    percentage = spent / limit
    filled_blocks = min(int(percentage * 5), 5)
    empty_blocks = 5 - filled_blocks
    
    # Если перерасход — красим в красный, иначе в зелёный
    color_emoji = "🟥" if percentage > 1.0 else "🟩"
    
    return f"[{color_emoji * filled_blocks}{'⬜' * empty_blocks}]"

def format_expenses(conn, title, expenses, is_monthly=False):
    """
    Форматирует словарь расходов в красивое сообщение, 
    учитывая установленные лимиты и прогресс-бары.
    """
    lines = [title, ""]
    emojis = {"Алкоголь": "🍺", "Кофе": "☕", "Продукты": "🛒"}
    total = 0

    # Получаем лимиты для всех категорий
    limits = get_all_limits(conn)
    limit_type = "monthly" if is_monthly else "daily"

    for category, amount in expenses.items():
        total += amount
        emoji = emojis.get(category, "💰")
        
        # Берем нужный лимит (дневной или месячный)
        cat_limit = limits.get(category, {}).get(limit_type)

        if cat_limit:
            progress_bar = generate_progress_bar(amount, cat_limit)
            left = cat_limit - amount
            
            if left >= 0:
                limit_info = f"из {cat_limit:.0f} (осталось {left:.2f})"
                status_emoji = ""
            else:
                limit_info = f"из {cat_limit:.0f} (🚨 ПЕРЕРАСХОД {abs(left):.2f})"
                status_emoji = " ⚠️"
                
            lines.append(f"{emoji} **{category}**: {amount:.2f} грн {limit_info}\n   {progress_bar}{status_emoji}")
        else:
            # Если лимит не задан, выводим обычную строку
            lines.append(f"{emoji} **{category}**: {amount:.2f} грн")

    lines.extend([
        "",
        "────────────────",
        f"💰 **Итого**: {total:.2f} грн",
    ])

    return "\n".join(lines)

def init_limits(conn):
    """Инициализация таблицы лимитов в PostgreSQL."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS limits (
                category TEXT PRIMARY KEY,
                daily_limit DOUBLE PRECISION,
                monthly_limit DOUBLE PRECISION,
                updated_at TIMESTAMP WITH TIME ZONE
            )
        """)

def get_limit(conn, category_name):
    """Получение лимитов для конкретной категории."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT daily_limit, monthly_limit
            FROM limits
            WHERE category = %s
        """, (category_name,))
        row = cur.fetchone()

    if row is None:
        return {"daily": None, "monthly": None}

    return {"daily": row[0], "monthly": row[1]}

def set_limit(conn, category_name, daily_limit=None, monthly_limit=None):
    """Установка лимитов."""
    if category_name not in CATEGORIES:
        raise ValueError(f"Неизвестная категория: {category_name}")

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO limits (category, daily_limit, monthly_limit, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT(category)
            DO UPDATE SET
                daily_limit = EXCLUDED.daily_limit,
                monthly_limit = EXCLUDED.monthly_limit,
                updated_at = EXCLUDED.updated_at
        """, (category_name, daily_limit, monthly_limit))

def get_all_limits(conn):
    """Получение лимитов по всем категориям."""
    result = {}
    for category in CATEGORIES:
        result[category] = get_limit(conn, category)
    return result

def get_category_expenses(conn, category_name, start_date=None, end_date=None):
    """Возвращает сумму расходов по категории за указанный период из PostgreSQL."""
    tag_id = CATEGORIES.get(category_name)
    if not tag_id:
        return 0

    query = """
        SELECT COALESCE(SUM(outcome), 0)
        FROM transactions
        WHERE tag_id = %s
          AND deleted = FALSE
          AND outcome > 0
    """
    params = [tag_id]

    if start_date:
        query += " AND date >= %s"
        params.append(start_date)

    if end_date:
        query += " AND date <= %s"
        params.append(end_date)

    with conn.cursor() as cur:
        cur.execute(query, params)
        result = cur.fetchone()

    return result[0] or 0

def get_today_expenses(conn, category_name):
    today = date.today().isoformat()
    return get_category_expenses(conn, category_name, start_date=today, end_date=today)

def get_month_expenses(conn, category_name):
    today = date.today()
    start_date = today.replace(day=1).isoformat()
    end_date = today.isoformat()
    return get_category_expenses(conn, category_name, start_date=start_date, end_date=end_date)

def get_all_today_expenses(conn):
    return {category: get_today_expenses(conn, category) for category in CATEGORIES}

def get_all_month_expenses(conn):
    return {category: get_month_expenses(conn, category) for category in CATEGORIES}
