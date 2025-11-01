import asyncio
import argparse
from datetime import datetime, timezone
import asyncpg
from collections import defaultdict

from CONFIG import Config
from COIN_MODELS.COIN_MAIN import Coin
import json

async def fetch_backtest_data(pool, symbol, start_time, end_time):
    """
    שולף את נתוני ספר הפקודות מה-DB עבור טווח זמן נתון,
    ומקבץ אותם לפי חותמת זמן.
    """
    async with pool.acquire() as connection:
        records = await connection.fetch("""
            SELECT time, exchange, data
            FROM order_books
            WHERE symbol = $1 AND time >= $2 AND time <= $3
            ORDER BY time ASC;
        """, symbol, start_time, end_time)

        # קיבוץ הרשומות לפי חותמת זמן
        grouped_by_time = defaultdict(dict)
        for r in records:
            # r['data'] הוא string, צריך להפוך ל-dict
            grouped_by_time[r['time']][r['exchange']] = json.loads(r['data'])

        # מיון לפי זמן כדי להבטיח סדר כרונולוגי
        sorted_timestamps = sorted(grouped_by_time.keys())
        
        return [(ts, grouped_by_time[ts]) for ts in sorted_timestamps]

async def list_available_ranges(pool, symbol):
    """
    מציג למשתמש רשימה של טווחי זמן רציפים הזמינים לבדיקה בבסיס הנתונים.
    "פער" מוגדר כהפרש זמן הגדול פי 5 מה-CYCLE_INTERVAL.
    """
    print(f"Searching for available data ranges for {symbol}...")
    gap_interval_seconds = Config.CYCLE_INTERVAL * 5

    async with pool.acquire() as connection:
        # שאילתה מורכבת למציאת "איים" של נתונים רציפים
        records = await connection.fetch(f"""
            WITH TimeGaps AS (
                SELECT
                    time,
                    LAG(time, 1) OVER (ORDER BY time) as prev_time
                FROM order_books
                WHERE symbol = $1
            ),
            IslandMarkers AS (
                SELECT
                    time,
                    CASE
                        WHEN EXTRACT(EPOCH FROM (time - prev_time)) > {gap_interval_seconds} THEN 1
                        ELSE 0
                    END as is_new_island
                FROM TimeGaps
            ),
            IslandGroups AS (
                SELECT time, SUM(is_new_island) OVER (ORDER BY time) as island_id FROM IslandMarkers
            )
            SELECT MIN(time) as start_range, MAX(time) as end_range, COUNT(*) as points
            FROM IslandGroups GROUP BY island_id ORDER BY start_range;
        """, symbol)
    
    if not records:
        print(f"No data found for symbol {symbol}.")
        return

    print("-" * 80)
    print(f"Found {len(records)} continuous data range(s) for {symbol}:")
    print(f"{'Start Time (UTC)':<28} | {'End Time (UTC)':<28} | {'Data Points'}")
    print("-" * 80)
    for i, r in enumerate(records):
        start = r['start_range'].strftime('%Y-%m-%d %H:%M:%S')
        end = r['end_range'].strftime('%Y-%m-%d %H:%M:%S')
        print(f"{start:<28} | {end:<28} | {r['points']}")
    print("-" * 80)
    print("\nTo run a backtest, copy a start/end time pair into the command.")
    print("Example:")
    print(f'docker-compose run --rm app python backtest.py {symbol} "{records[0]["start_range"].strftime("%Y-%m-%d %H:%M:%S")}" "{records[0]["end_range"].strftime("%Y-%m-%d %H:%M:%S")}"')

async def run_backtest(symbol, start_time, end_time):
    """
    הפונקציה הראשית של ה-backtester.
    מריצה את הסימולציה על הנתונים ההיסטוריים.
    """
    print("-" * 50)
    print(f"Starting Backtest for {symbol}")
    print(f"Period: {start_time.strftime('%Y-%m-%d %H:%M:%S')} -> {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 50)

    # 1. התחברות ל-DB ושליפת נתונים
    pool = await asyncpg.create_pool(
        user=Config.DB_USER, password=Config.DB_PASSWORD,
        database=Config.DB_DATABASE, host=Config.DB_HOST, port=Config.DB_PORT
    )
    historical_data = await fetch_backtest_data(pool, symbol, start_time, end_time)
    
    if not historical_data:
        print("No data found for the specified period.")
        await pool.close()
        return

    if verbose:
        print(f"Found {len(historical_data)} historical data points to process.")

    # 2. אתחול אובייקט המטבע
    coin = Coin(symbol)

    # 3. לולאת סימולציה
    for timestamp, fetched_books in historical_data:
        # הדמיית "המתנה" בין מחזורים
        # אם יש פער גדול בין נקודות המידע, נדפיס הודעה
        if coin.last_time_str:
            last_ts = datetime.strptime(coin.last_time_str, "%H:%M:%S").replace(year=timestamp.year, month=timestamp.month, day=timestamp.day, tzinfo=timezone.utc)
            if (timestamp - last_ts).total_seconds() > Config.CYCLE_INTERVAL * 2:
                 print(f"--- Data gap detected. Jumping from {last_ts.time()} to {timestamp.time()} ---")

        # עדכון הזמן הנוכחי של המטבע
        coin.last_time_str = timestamp.strftime("%H:%M:%S")

        # --- קריאה ללוגיקה המאוחדת ---
        await coin.process_coin(prefetched_books=fetched_books)

    # 4. סיכום התוצאות
    total_profit_pct = (coin.total_profit / coin.buyed_price * 100) if coin.total_buy_trades > 0 and coin.buyed_price > 0 else 0
    
    if verbose:
        print("-" * 50)
        print("Backtest Finished. Results:")
        print(f"  Total Buy Trades:  {coin.total_buy_trades}")
        print(f"  Total Sell Trades: {coin.total_sell_trades}")
        print(f"  Total Profit/Loss: {coin.total_profit:.6f} ({total_profit_pct:.2f}%)")
        print("-" * 50)

    if close_pool_at_end:
        await db_pool.close()

    return {
        "total_profit": coin.total_profit,
        "total_profit_pct": total_profit_pct,
        "buy_trades": coin.total_buy_trades,
        "sell_trades": coin.total_sell_trades
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a backtest on historical order book data.")
    parser.add_argument("symbol", type=str, nargs='?', default=None, help="The crypto symbol to backtest (e.g., BTCUSDT).")
    parser.add_argument("start", type=str, nargs='?', default=None, help="Start time in 'YYYY-MM-DD HH:MM:SS' format (UTC).")
    parser.add_argument("end", type=str, nargs='?', default=None, help="End time in 'YYYY-MM-DD HH:MM:SS' format (UTC).")
    parser.add_argument("--list-ranges", action="store_true", help="List available continuous data ranges for a symbol and exit.")

    args = parser.parse_args()

    if args.list_ranges:
        if not args.symbol:
            print("Error: You must provide a symbol to list its ranges. Example: --list-ranges BTCUSDT")
            exit(1)
        
        async def main_list():
            pool = await asyncpg.create_pool(user=Config.DB_USER, password=Config.DB_PASSWORD, database=Config.DB_DATABASE, host=Config.DB_HOST, port=Config.DB_PORT)
            await list_available_ranges(pool, args.symbol)
            await pool.close()
        
        asyncio.run(main_list())
    elif args.symbol and args.start and args.end:
        try:
            # המרת מחרוזות הזמן לאובייקטים של datetime עם timezone
            start_dt = datetime.strptime(args.start, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            end_dt = datetime.strptime(args.end, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
            asyncio.run(run_backtest(args.symbol, start_dt, end_dt))
        except ValueError:
            print("Error: Date format must be 'YYYY-MM-DD HH:MM:SS'")
            exit(1)
    else:
        parser.print_help()