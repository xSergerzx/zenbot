import sqlite3
from datetime import date

from dotenv import load_dotenv
import os


load_dotenv()

DB_PATH = "bot.db"
def init_limits():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS limits (
                category TEXT PRIMARY KEY,
                daily_limit REAL,
                monthly_limit REAL,
                updated_at TEXT
            )
        """)
        db.commit()


def get_limit(category_name):
    with sqlite3.connect(DB_PATH) as db:
        row = db.execute("""
            SELECT daily_limit, monthly_limit
            FROM limits
            WHERE category = ?
        """, (category_name,)).fetchone()

    if row is None:
        return {
            "daily": None,
            "monthly": None,
        }

    return {
        "daily": row[0],
        "monthly": row[1],
    }


def set_limit(
    category_name,
    daily_limit=None,
    monthly_limit=None,
):
    if category_name not in CATEGORIES:
        raise ValueError(
            f"Неизвестная категория: {category_name}"
        )

    with sqlite3.connect(DB_PATH) as db:

        db.execute("""
            INSERT INTO limits (
                category,
                daily_limit,
                monthly_limit,
                updated_at
            )
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(category)
            DO UPDATE SET
                daily_limit = excluded.daily_limit,
                monthly_limit = excluded.monthly_limit,
                updated_at = excluded.updated_at
        """, (
            category_name,
            daily_limit,
            monthly_limit,
        ))

        db.commit()


def get_all_limits():
    result = {}

    for category in CATEGORIES:
        result[category] = get_limit(category)

    return result


# Инициализируем таблицу лимитов
init_limits()

CATEGORIES = {
    "Алкоголь": os.getenv("ZENMONEY_ALCOHOL_TAG"),
    "Кофе": os.getenv("ZENMONEY_COFFEE_TAG"),
    "Продукты": os.getenv("ZENMONEY_FOOD_TAG"),
}


def get_category_expenses(
    category_name,
    start_date=None,
    end_date=None,
):
    """
    Возвращает сумму расходов по категории
    за указанный период.
    """

    tag_id = CATEGORIES.get(category_name)

    if not tag_id:
        raise ValueError(
            f"Неизвестная категория: {category_name}"
        )

    query = """
        SELECT COALESCE(SUM(outcome), 0)
        FROM transactions
        WHERE tag_id = ?
          AND deleted = 0
          AND outcome > 0
    """

    params = [tag_id]

    if start_date:
        query += " AND date >= ?"
        params.append(start_date)

    if end_date:
        query += " AND date <= ?"
        params.append(end_date)

    with sqlite3.connect(DB_PATH) as db:
        result = db.execute(
            query,
            params
        ).fetchone()

    return result[0] or 0


def get_today_expenses(category_name):
    today = date.today().isoformat()

    return get_category_expenses(
        category_name,
        start_date=today,
        end_date=today,
    )


def get_month_expenses(category_name):
    today = date.today()

    start_date = today.replace(day=1).isoformat()
    end_date = today.isoformat()

    return get_category_expenses(
        category_name,
        start_date=start_date,
        end_date=end_date,
    )


def get_all_today_expenses():
    """
    Возвращает расходы за сегодня по всем категориям.
    """

    return {
        category: get_today_expenses(category)
        for category in CATEGORIES
    }


def get_all_month_expenses():
    """
    Возвращает расходы за текущий месяц
    по всем категориям.
    """

    return {
        category: get_month_expenses(category)
        for category in CATEGORIES
    }


if __name__ == "__main__":

    print("=== СЕГОДНЯ ===")

    today_expenses = get_all_today_expenses()

    for category, amount in today_expenses.items():
        print(f"{category}: {amount:.2f} грн")

    print("\n=== ТЕКУЩИЙ МЕСЯЦ ===")

    month_expenses = get_all_month_expenses()

    for category, amount in month_expenses.items():
        print(f"{category}: {amount:.2f} грн")

    print(
        f"\nВсего за месяц: "
        f"{sum(month_expenses.values()):.2f} грн"
    )

    