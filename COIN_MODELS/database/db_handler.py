import asyncio
import asyncpg
import json
from CONFIG import Config
from datetime import datetime, timezone

class TimescaleDBHandler:
    """
    Manages connection and operations with TimescaleDB.
    Singleton pattern to ensure a single connection pool.
    """
    _pool = None

    @classmethod
    async def get_pool(cls):
        """Returns the connection pool, creating it if it doesn't exist or if the loop changed."""
        
        # Check if pool exists but is bound to a different (closed/old) loop
        if cls._pool is not None:
            try:
                # asyncpg pool stores the loop in _loop
                current_loop = asyncio.get_running_loop()
                if cls._pool._loop is not current_loop:
                    print("TimescaleDBHandler: Detected event loop change. Resetting pool.")
                    await cls._pool.close()
                    cls._pool = None
            except Exception:
                # If checking fails, assume invalid and reset
                cls._pool = None

        if cls._pool is None:
            retries = 10
            for i in range(retries):
                try:
                    cls._pool = await asyncpg.create_pool(
                        user=Config.DB_USER,
                        password=Config.DB_PASSWORD,
                        database=Config.DB_DATABASE,
                        host=Config.DB_HOST,
                        port=Config.DB_PORT
                    )
                    print("Successfully connected to TimescaleDB.")
                    return cls._pool
                except (OSError, asyncpg.CannotConnectNowError, asyncpg.PostgresError) as e:
                    wait_time = 2 * (i + 1)
                    print(f"TimescaleDB not ready yet (Attempt {i+1}/{retries}). Retrying in {wait_time}s... Error: {e}")
                    await asyncio.sleep(wait_time)
            
            print("!!! CRITICAL: Failed to connect to TimescaleDB after multiple attempts.")
            return None
        return cls._pool

    @classmethod
    async def initialize_db(cls):
        """
        Creates the table and hypertable if they don't exist.
        Should be run once at system startup.
        """
        pool = await cls.get_pool()
        if not pool: return

        async with pool.acquire() as connection:
            # 1. Check if table exists and has the correct schema
            try:
                # Check if 'time' column exists
                check_schema = await connection.fetchval("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='order_books' AND column_name='time';
                """)
                
                if not check_schema:
                    # If table exists but 'time' is missing, it's the old schema. Drop it.
                    # Check if table exists first to avoid error on fresh start
                    table_exists = await connection.fetchval("""
                        SELECT to_regclass('public.order_books');
                    """)
                    
                    if table_exists:
                        print("TimescaleDBHandler: Detected old schema (missing 'time' column). Dropping table to recreate...")
                        await connection.execute("DROP TABLE order_books CASCADE;")
            except Exception as e:
                print(f"TimescaleDBHandler: Warning during schema check: {e}")

            # 2. Create standard table
            await connection.execute("""
                CREATE TABLE IF NOT EXISTS order_books (
                    time TIMESTAMPTZ NOT NULL,
                    symbol TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    data JSONB NOT NULL
                );
            """)
            # Create market_metrics table
            await connection.execute("""
                CREATE TABLE IF NOT EXISTS market_metrics (
                    time TIMESTAMPTZ NOT NULL,
                    symbol TEXT NOT NULL,
                    price DOUBLE PRECISION,
                    volatility DOUBLE PRECISION,
                    momentum DOUBLE PRECISION,
                    buy_pressure DOUBLE PRECISION,
                    sell_pressure DOUBLE PRECISION,
                    signal TEXT,
                    readiness DOUBLE PRECISION
                );
            """)

            # 3. Convert to Hypertable (TimescaleDB magic)
            try:
                await connection.execute("SELECT create_hypertable('order_books', 'time', if_not_exists => TRUE);")
                await connection.execute("SELECT create_hypertable('market_metrics', 'time', if_not_exists => TRUE);")
                print("Hypertable 'order_books' and 'market_metrics' ensured.")
            except asyncpg.exceptions.PostgresError as e:
                if "already a hypertable" in str(e):
                    pass 
                else:
                    print(f"Warning: Could not create hypertable: {e}")

    @classmethod
    async def save_order_book_data(cls, symbol: str, fetched_books: dict):
        """Saves fetched order book data to the database."""
        pool = await cls.get_pool()
        if not pool: return

        records_to_insert = []
        timestamp = datetime.now(timezone.utc)

        for exchange, data in fetched_books.items():
            if data and data.get("bids") and data.get("asks"):
                records_to_insert.append((timestamp, symbol, exchange, json.dumps(data)))

        if not records_to_insert:
            return

        async with pool.acquire() as connection:
            try:
                await connection.copy_records_to_table(
                    'order_books', records=records_to_insert, columns=['time', 'symbol', 'exchange', 'data']
                )
            except Exception as e:
                print(f"TimescaleDBHandler: Error saving data for {symbol}: {e}")

    @classmethod
    async def save_market_metrics(cls, symbol: str, data: dict):
        """Saves calculated market metrics to the database."""
        pool = await cls.get_pool()
        if not pool: return

        timestamp = datetime.now(timezone.utc)
        
        async with pool.acquire() as connection:
            try:
                await connection.execute("""
                    INSERT INTO market_metrics (time, symbol, price, volatility, momentum, buy_pressure, sell_pressure, signal, readiness)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """, timestamp, symbol, data['price'], data['volatility'], data['momentum'], 
                   data['buy_pressure'], data['sell_pressure'], data['signal'], data['readiness'])
            except Exception as e:
                print(f"TimescaleDBHandler: Error saving metrics for {symbol}: {e}")

    @classmethod
    async def fetch_latest_metrics(cls):
        """Fetches the latest metrics for all coins."""
        pool = await cls.get_pool()
        if not pool: return []

        async with pool.acquire() as connection:
            try:
                # Get the latest row for each symbol
                rows = await connection.fetch("""
                    SELECT DISTINCT ON (symbol) *
                    FROM market_metrics
                    ORDER BY symbol, time DESC;
                """)
                return [dict(row) for row in rows]
            except Exception as e:
                print(f"TimescaleDBHandler: Error fetching metrics: {e}")
                return []
