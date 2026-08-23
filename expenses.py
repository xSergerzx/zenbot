import os
from datetime import date
import psycopg
from dotenv import load_dotenv

load_dotenv()

# Категории инициализируем сразу, чтобы функции могли ссылаться на них
CATEGORIES = {
    "Алкоголь": os.getenv("ZENMONEY_ALCOHOL_TAG"),
    "Кофе": os.getenv("ZENMONEY_COFFEE_TAG"),
    "Продукты": os.getenv("ZENMONEY_FOOD_TAG"),
}


def init_limits(conn):
    """Инициализация таблицы лимитов в PostgreSQL."""
    with conn.cursor() as cur:
        # В PostgreSQL для даты и времени используем тип TIMESTAMP WITH TIME ZONE
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
        return {
            "daily": None,
            "monthly": None,
        }

    return {
        "daily": row[0],
        "monthly": row[1],
    }


def set_limit(conn, category_name, daily_limit=None, monthly_limit=None):
    """Установка лимитов."""
    if category_name not in CATEGORIES:
        raise ValueError(f"Неизвестная категория: {category_name}")

    with conn.cursor() as cur:
        # datetime('now') заменен на стандартную функцию NOW()
        cur.execute("""
            INSERT INTO limits (
                category,
                daily_limit,
                monthly_limit,
                updated_at
            )
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT(category)
            DO UPDATE SET
                daily_limit = EXCLUDED.daily_limit,
                monthly_limit = EXCLUDED.monthly_limit,
                updated_at = EXCLUDED.updated_at
        """, (
            category_name,
            daily_limit,
            monthly_limit,
        ))


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
        raise ValueError(f"Неизвестная категория: {category_name}")

    # В PostgreSQL колонка deleted имеет тип boolean, поэтому пишем `deleted = FALSE`
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
    return get_category_expenses(
        conn,
        category_name,
        start_date=today,
        end_date=today,
    )


def get_month_expenses(conn, category_name):
    today = date.today()
    start_date = today.replace(day=1).isoformat()
    end_date = today.isoformat()
    return get_category_expenses(
        conn,
        category_name,
        start_date=start_date,
        end_date=end_date,
    )


def get_all_today_expenses(conn):
    """Возвращает расходы за сегодня по всем категориям."""
    return {
        category: get_today_expenses(conn, category)
        for category in CATEGORIES
    }


def get_all_month_expenses(conn):
    """Возвращает расходы за текущий месяц по всем категориям."""
    return {
        category: get_month_expenses(conn, category)
        for category in CATEGORIES
    }


# ДЛЯ ЛОКАЛЬНОГО ТЕСТИРОВАНИЯ:
if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL не указан в .env")

    print("Подключаемся к Neon для проверки расходов...")
    with psycopg.connect(db_url) as connection:
        # Инициализируем таблицу лимитов в Postgres, если её не было
        init_limits(connection)
        
        print("=== СЕГОДНЯ ===")
        today_expenses = get_all_today_expenses(connection)
        for category, amount in today_expenses.items():
            print(f"{category}: {amount:.2f} грн")

        print("\n=== ТЕКУЩИЙ МЕСЯЦ ===")
        month_expenses = get_all_month_expenses(connection)
        for category, amount in month_expenses.items():
            print(f"{category}: {amount:.2f} грн")

        print(f"\nВсего за месяц: {sum(month_expenses.values()):.2f} грн")
        
        connection.commit()
