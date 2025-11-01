import asyncio
import argparse
from datetime import datetime, timezone
import asyncpg
from collections import defaultdict

from CONFIG import Config
from COIN_MODELS.COIN_MAIN import Coin

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
            grouped_by_time[r['time']][r['exchange']] = r['data']

        # מיון לפי זמן כדי להבטיח סדר כרונולוגי
        sorted_timestamps = sorted(grouped_by_time.keys())
        
        return [(ts, grouped_by_time[ts]) for ts in sorted_timestamps]

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

    print(f"Found {len(historical_data)} historical data points to process.")

    # 2. אתחול אובייקט המטבע
    coin = Coin(symbol)

    # 3. לולאת סימולציה
    for timestamp, fetched_books in historical_data:
        # הדמיית "המתנה" בין מחזורים
        # אם יש פער גדול בין נקודות המידע, נדפיס הודעה
        if coin.last_time_str:
            last_ts = datetime.strptime(coin.last_time_str, "%H:%M:%S").replace(year=timestamp.year, month=timestamp.month, day=timestamp.day)
            if (timestamp - last_ts).total_seconds() > Config.CYCLE_INTERVAL * 2:
                 print(f"--- Data gap detected. Jumping from {last_ts.time()} to {timestamp.time()} ---")

        # עדכון הזמן הנוכחי של המטבע
        coin.last_time_str = timestamp.strftime("%H:%M:%S")

        # --- ליבת הלוגיקה - זהה כמעט לחלוטין ל-process_coin ---
        # כאן אנחנו "מזריקים" את הנתונים ההיסטוריים במקום לשלוף אותם מהרשת
        
        def is_book_valid(book):
            return book and book.get("bids") and book.get("asks")

        binance_ok = is_book_valid(fetched_books.get("binance"))
        other_ok_count = sum(1 for ex, book in fetched_books.items() if ex != "binance" and is_book_valid(book))
        is_data_healthy = binance_ok and (other_ok_count >= 1)

        if is_data_healthy:
            coin.Fallback_DATA = False
            coin.orderbooks = fetched_books
            
            coin.prev_med_price = coin.med_price
            
            # הרצת ניתוח
            coin.signal_state.analyze(timestamp.timestamp())

            coin.med_price = coin.signal_state.med_price
            coin.signal = coin.signal_state.last_decision.name

            # הרצת לוגיקת מסחר
            if coin.med_price is not None and coin.med_price > 0 and coin.prev_med_price != coin.med_price:
                coin.trade_manager.check_selling_cond()
                coin.trade_manager.check_buying_cond()
        else:
            coin.Fallback_DATA = True
            coin.signal = "FALLBACK_DATA"

    # 4. סיכום התוצאות
    print("-" * 50)
    print("Backtest Finished. Results:")
    print(f"  Total Buy Trades:  {coin.total_buy_trades}")
    print(f"  Total Sell Trades: {coin.total_sell_trades}")
    print(f"  Total Profit/Loss: {coin.total_profit:.6f} ({(coin.total_profit / coin.buyed_price * 100) if coin.total_buy_trades > 0 and coin.buyed_price > 0 else 0:.2f}%)")
    print("-" * 50)

    await pool.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a backtest on historical order book data.")
    parser.add_argument("symbol", type=str, help="The crypto symbol to backtest (e.g., BTCUSDT).")
    parser.add_argument("start", type=str, help="Start time in 'YYYY-MM-DD HH:MM:SS' format (UTC).")
    parser.add_argument("end", type=str, help="End time in 'YYYY-MM-DD HH:MM:SS' format (UTC).")

    args = parser.parse_args()

    try:
        # המרת מחרוזות הזמן לאובייקטים של datetime עם timezone
        start_dt = datetime.strptime(args.start, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        end_dt = datetime.strptime(args.end, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
    except ValueError:
        print("Error: Date format must be 'YYYY-MM-DD HH:MM:SS'")
        exit(1)

    asyncio.run(run_backtest(args.symbol, start_dt, end_dt))