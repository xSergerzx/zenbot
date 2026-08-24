import os
import time
import requests
import psycopg


TOKEN = os.getenv("ZENMONEY_ACCESS_TOKEN")
API_URL = "https://api.zenmoney.ru/v8/diff/"


def init_db(conn):
    """Инициализация таблиц в PostgreSQL при необходимости."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                outcome DOUBLE PRECISION DEFAULT 0,
                tag_id TEXT,
                source TEXT,
                deleted BOOLEAN DEFAULT FALSE
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                balance DOUBLE PRECISION DEFAULT 0,
                archive BOOLEAN DEFAULT FALSE,
                deleted BOOLEAN DEFAULT FALSE
            )
        """)


def get_server_timestamp(conn):
    """Получение временной метки из базы PostgreSQL."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT value
            FROM settings
            WHERE key = 'server_timestamp'
        """)
        row = cur.fetchone()
        if row is None:
            return 0
        return int(row[0])


def save_server_timestamp(conn, timestamp):
    """Сохранение временной метки."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO settings (key, value)
            VALUES ('server_timestamp', %s)
            ON CONFLICT(key)
            DO UPDATE SET value = EXCLUDED.value
        """, (str(timestamp),))


def sync_zenmoney(conn):
    """
    Основная функция синхронизации.
    Принимает активное соединение `conn` от psycopg.
    """
    if not TOKEN:
        raise RuntimeError("ZENMONEY_ACCESS_TOKEN не указан в окружении")

    init_db(conn)

    server_timestamp = get_server_timestamp(conn)
    print(f"Синхронизация. serverTimestamp = {server_timestamp}")

    payload = {
        "currentClientTimestamp": int(time.time()),
        "serverTimestamp": server_timestamp,
    }

    if server_timestamp == 0:
        payload["forceFetch"] = ["tag", "transaction", "user", "account"]
    else:
        payload["forceFetch"] = ["account"]  # Счета обновляем всегда для свежего остатка

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }

    response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
    response.raise_for_status()

    data = response.json()

    # 1. Синхронизация счетов (Accounts)
    accounts = data.get("account", [])
    print(f"Получено счетов: {len(accounts)}")

    with conn.cursor() as cur:
        for acc in accounts:
            cur.execute("""
                INSERT INTO accounts (id, title, balance, archive, deleted)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(id)
                DO UPDATE SET
                    title = EXCLUDED.title,
                    balance = EXCLUDED.balance,
                    archive = EXCLUDED.archive,
                    deleted = EXCLUDED.deleted
            """, (
                acc["id"],
                acc.get("title", "Без названия"),
                acc.get("balance") or 0,
                bool(acc.get("archive")),
                bool(acc.get("deleted"))
            ))

    # 2. Синхронизация транзакций (Transactions)
    transactions = data.get("transaction", [])
    print(f"Получено транзакций: {len(transactions)}")

    with conn.cursor() as cur:
        for transaction in transactions:
            transaction_id = transaction["id"]
            transaction_date = transaction.get("date")
            outcome = transaction.get("outcome") or 0
            deleted = bool(transaction.get("deleted"))

            tags = transaction.get("tag") or []
            tag_id = tags[0] if tags else None
            source = transaction.get("source")

            cur.execute("""
                INSERT INTO transactions (
                    id,
                    date,
                    outcome,
                    tag_id,
                    source,
                    deleted
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT(id)
                DO UPDATE SET
                    date = EXCLUDED.date,
                    outcome = EXCLUDED.outcome,
                    tag_id = EXCLUDED.tag_id,
                    source = EXCLUDED.source,
                    deleted = EXCLUDED.deleted
            """, (
                transaction_id,
                transaction_date,
                outcome,
                tag_id,
                source,
                deleted,
            ))

    new_timestamp = data.get("serverTimestamp")
    if new_timestamp:
        save_server_timestamp(conn, new_timestamp)

    print(f"Новый serverTimestamp: {new_timestamp}")
    print("Синхронизация завершена.")


# ДЛЯ ЛОКАЛЬНОГО ТЕСТИРОВАНИЯ:
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL не указан в .env")
        
    print("Локальный запуск синхронизации...")
    with psycopg.connect(db_url) as conn:
        sync_zenmoney(conn)
        conn.commit()
    print("Готово.")
