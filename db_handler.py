import asyncpg
import json
from CONFIG import Config
from datetime import datetime

class TimescaleDBHandler:
    """
    מנהל את החיבור והפעולות מול בסיס הנתונים TimescaleDB.
    פועל כ-Singleton כדי להבטיח חיבור יחיד.
    """
    _pool = None

    @classmethod
    async def get_pool(cls):
        """מחזיר את pool החיבורים, ויוצר אותו אם הוא לא קיים."""
        if cls._pool is None:
            try:
                cls._pool = await asyncpg.create_pool(
                    user=Config.DB_USER,
                    password=Config.DB_PASSWORD,
                    database=Config.DB_DATABASE,
                    host=Config.DB_HOST,
                    port=Config.DB_PORT
                )
                print("Successfully connected to TimescaleDB.")
            except Exception as e:
                print(f"!!! CRITICAL: Failed to connect to TimescaleDB: {e}")
                return None
        return cls._pool

    @classmethod
    async def initialize_db(cls):
        """
        יוצר את הטבלה וה-hypertable אם הם לא קיימים.
        יש להריץ פעם אחת عند הפעלת המערכת.
        """
        pool = await cls.get_pool()
        if not pool: return

        async with pool.acquire() as connection:
            # יצירת טבלה רגילה
            await connection.execute("""
                CREATE TABLE IF NOT EXISTS order_books (
                    time TIMESTAMPTZ NOT NULL,
                    symbol TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    data JSONB NOT NULL
                );
            """)
            # הפיכת הטבלה ל-Hypertable (הקסם של TimescaleDB)
            # שגיאה 'already a hypertable' תתקבל בהרצות הבאות וזה תקין.
            try:
                await connection.execute("SELECT create_hypertable('order_books', 'time');")
                print("Hypertable 'order_books' created successfully.")
            except asyncpg.exceptions.PostgresError as e:
                if "already a hypertable" in str(e):
                    pass # זה מצב תקין אם הטבלה כבר קיימת
                else:
                    raise

    @classmethod
    async def save_order_book_data(cls, symbol: str, fetched_books: dict):
        """שומר את נתוני ספר הפקודות שהתקבלו מהבורסות."""
        pool = await cls.get_pool()
        if not pool: return

        records_to_insert = []
        timestamp = datetime.utcnow()

        for exchange, data in fetched_books.items():
            if data and data.get("bids") and data.get("asks"):
                records_to_insert.append((timestamp, symbol, exchange, json.dumps(data)))

        if not records_to_insert:
            return

        async with pool.acquire() as connection:
            await connection.copy_records_to_table(
                'order_books', records=records_to_insert, columns=['time', 'symbol', 'exchange', 'data']
            )