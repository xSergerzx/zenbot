import os
import sqlite3
import time

import requests
from dotenv import load_dotenv


load_dotenv()

TOKEN = os.getenv("ZENMONEY_ACCESS_TOKEN")

API_URL = "https://api.zenmoney.ru/v8/diff/"
DB_PATH = "bot.db"


if not TOKEN:
    raise RuntimeError(
        "ZENMONEY_ACCESS_TOKEN не указан в .env"
    )


def get_db():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_db() as db:

        db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id TEXT PRIMARY KEY,
                date TEXT NOT NULL,
                outcome REAL DEFAULT 0,
                tag_id TEXT,
                source TEXT,
                deleted INTEGER DEFAULT 0
            )
        """)

        # Если база была создана старой версией sync.py,
        # добавляем source в существующую таблицу.
        columns = db.execute(
            "PRAGMA table_info(transactions)"
        ).fetchall()

        column_names = [column[1] for column in columns]

        if "source" not in column_names:
            db.execute(
                "ALTER TABLE transactions ADD COLUMN source TEXT"
            )

        db.commit()


def get_server_timestamp():
    with get_db() as db:

        row = db.execute("""
            SELECT value
            FROM settings
            WHERE key = 'server_timestamp'
        """).fetchone()

        if row is None:
            return 0

        return int(row[0])


def save_server_timestamp(timestamp):
    with get_db() as db:

        db.execute("""
            INSERT INTO settings (key, value)
            VALUES ('server_timestamp', ?)
            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value
        """, (str(timestamp),))

        db.commit()


def sync():
    server_timestamp = get_server_timestamp()

    print(
        f"Синхронизация. "
        f"serverTimestamp = {server_timestamp}"
    )

    payload = {
        "currentClientTimestamp": int(time.time()),
        "serverTimestamp": server_timestamp,
    }

    # Первая синхронизация — получаем полную историю.
    if server_timestamp == 0:
        payload["forceFetch"] = [
            "tag",
            "transaction",
            "user",
        ]

    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        API_URL,
        headers=headers,
        json=payload,
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    transactions = data.get("transaction", [])

    print(
        f"Получено транзакций: {len(transactions)}"
    )

    with get_db() as db:

        for transaction in transactions:

            transaction_id = transaction["id"]

            transaction_date = transaction.get("date")

            outcome = transaction.get("outcome") or 0

            deleted = (
                1
                if transaction.get("deleted")
                else 0
            )

            tags = transaction.get("tag") or []

            # Для наших расчётов сохраняем категорию.
            tag_id = tags[0] if tags else None

            # Важно для split-транзакций.
            source = transaction.get("source")

            db.execute("""
                INSERT INTO transactions (
                    id,
                    date,
                    outcome,
                    tag_id,
                    source,
                    deleted
                )
                VALUES (?, ?, ?, ?, ?, ?)

                ON CONFLICT(id)
                DO UPDATE SET
                    date = excluded.date,
                    outcome = excluded.outcome,
                    tag_id = excluded.tag_id,
                    source = excluded.source,
                    deleted = excluded.deleted
            """, (
                transaction_id,
                transaction_date,
                outcome,
                tag_id,
                source,
                deleted,
            ))

        db.commit()

    new_timestamp = data.get("serverTimestamp")

    if new_timestamp:
        save_server_timestamp(new_timestamp)

    print(
        f"Новый serverTimestamp: {new_timestamp}"
    )

    print("Синхронизация завершена.")


if __name__ == "__main__":
    init_db()
    sync()