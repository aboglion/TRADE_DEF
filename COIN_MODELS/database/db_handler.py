import json
from CONFIG import Config


class TimescaleDBHandler:
    """Minimal async Timescale/Postgres handler using asyncpg.

    Provides:
    - async initialize_db(): create connection pool and ensure table exists
    - async save_order_book_data(symbol, data): persist orderbook JSON

    This implementation is intentionally small and defensive so the
    application can start during development. It uses Config from
    `CONFIG.py` for credentials.
    """

    _pool = None

    @classmethod
    async def initialize_db(cls):
        if cls._pool is not None:
            return

        dsn = {
            "user": Config.DB_USER,
            "password": Config.DB_PASSWORD,
            "database": Config.DB_DATABASE,
            "host": Config.DB_HOST,
            "port": int(Config.DB_PORT),
        }

        print(f"TimescaleDBHandler: connecting to DB {dsn['host']}:{dsn['port']}/{dsn['database']} as {dsn['user']}")

        # import asyncpg lazily so importing this module doesn't require asyncpg at import time
        import asyncpg

        cls._pool = await asyncpg.create_pool(
            user=dsn["user"],
            password=dsn["password"],
            database=dsn["database"],
            host=dsn["host"],
            port=dsn["port"],
            min_size=1,
            max_size=5,
        )

        # Ensure the table exists. Keep schema minimal and safe.
        async with cls._pool.acquire() as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS order_books (
                    id BIGSERIAL PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    data JSONB NOT NULL,
                    ts TIMESTAMPTZ NOT NULL DEFAULT now()
                );
                """
            )

        print("TimescaleDBHandler: DB initialized and table ensured.")

    @classmethod
    async def save_order_book_data(cls, symbol: str, data: dict):
        if cls._pool is None:
            await cls.initialize_db()

        payload = json.dumps(data)

        async with cls._pool.acquire() as conn:
            try:
                await conn.execute(
                    "INSERT INTO order_books (symbol, data) VALUES ($1, $2::jsonb)",
                    symbol,
                    payload,
                )
            except Exception as e:
                # Swallow the error but print for visibility; the app will continue
                print(f"TimescaleDBHandler.save_order_book_data: failed to save data for {symbol}: {e}")
