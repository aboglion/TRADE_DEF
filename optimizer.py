import asyncio
import argparse
from datetime import datetime, timezone
import asyncpg
import itertools
from tabulate import tabulate
import questionary, os

from CONFIG import Config
from backtest import run_backtest # נייבא פונקציות מ-backtest

def generate_param_grid():
    """
    Generates a search grid automatically based on the default values in CONFIG.py.
    This creates a small range around the default values to test.
    """
    param_grid = {
        # As requested, time parameter remains the same
        'HISTORY_TIME_MINUTES': [Config.HISTORY_TIME_MINUTES],
        
        # Create a range around the default float values
        'BASE_THRESHOLD': [Config.BASE_THRESHOLD * 0.95, Config.BASE_THRESHOLD, Config.BASE_THRESHOLD * 1.05],
        'TAKE_profit_PCT': [Config.TAKE_profit_PCT * 0.9, Config.TAKE_profit_PCT, Config.TAKE_profit_PCT * 1.1],
        'STOP_LOSS_PCT': [Config.STOP_LOSS_PCT * 0.9, Config.STOP_LOSS_PCT, Config.STOP_LOSS_PCT * 1.1],

        # Create a range around the default integer values
        'MIN_CONSEC_SIGNALS': [max(1, Config.MIN_CONSEC_SIGNALS - 1), Config.MIN_CONSEC_SIGNALS, Config.MIN_CONSEC_SIGNALS + 1],
    }
    # Clean up float values to have fewer decimal places
    for key in ['BASE_THRESHOLD', 'TAKE_profit_PCT', 'STOP_LOSS_PCT']:
        param_grid[key] = [round(v, 5) for v in param_grid[key]]

    return param_grid

async def optimize_single_symbol(symbol, start_time, end_time, pool):
    """
    Runs the optimization process for a single symbol.
    """
    param_grid = generate_param_grid()

    # יצירת כל הקומבינציות האפשריות
    keys, values = zip(*param_grid.items())
    combinations = [dict(zip(keys, v)) for v in itertools.product(*values)]

    print(f"--- Starting optimization for {symbol} with {len(combinations)} combinations ---")

    results = []
    for i, params in enumerate(combinations):
        # 4. Create a specific Config instance for this iteration
        # This avoids modifying the global state and allows parallel execution
        current_config = Config(**params)

        # 5. Run backtest with the new configuration
        backtest_result = await run_backtest(symbol, start_time, end_time, pool=pool, verbose=False, config=current_config)
        
        if backtest_result and backtest_result.get('buy_trades', 0) > 0:
            results.append({**params, **backtest_result})
    
    if not results:
        print(f"--- Finished optimization for {symbol}: No profitable trades found. ---")
        return None

    # מיון התוצאות לפי הרווח (מהגבוה לנמוך)
    best_result = sorted(results, key=lambda x: x['total_profit'], reverse=True)[0]
    return {symbol: best_result}

async def main_optimizer(symbols, start_time, end_time, pool):
    """
    The main function to run optimization on all specified symbols in parallel.
    """
    print("=" * 80)
    print("Starting Hyperparameter Optimizer")
    print(f"Symbols: {', '.join(symbols)}")
    print(f"Period: {start_time.strftime('%Y-%m-%d %H:%M:%S')} -> {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Create a task for each symbol to run optimizations in parallel
    tasks = [optimize_single_symbol(symbol, start_time, end_time, pool) for symbol in symbols]
    all_results = await asyncio.gather(*tasks)

    # --- Final Report Generation ---
    report_str = "\n\n" + "=" * 80 + "\n"
    report_str += "OPTIMIZATION REPORT\n"
    report_str += "=" * 80 + "\n"

    final_report_data = [res for res in all_results if res is not None]

    if not final_report_data:
        report_str += "No profitable configurations were found for any symbol in the given period.\n"
        print(report_str)
        return report_str

    param_keys = list(generate_param_grid().keys())

    for report in final_report_data:
        symbol, best_params = list(report.items())[0]
        report_str += f"\n--- Best Configuration for: {symbol} ---\n"
        
        headers = ["Parameter", "Optimal Value"]
        table_data = []
        for key in param_keys:
            table_data.append([key, best_params.get(key, 'N/A')])
        
        report_str += tabulate(table_data, headers=headers, tablefmt="pretty") + "\n"

        report_str += "\nPerformance:\n"
        perf_headers = ["Metric", "Value"]
        perf_data = [
            ["Total Profit", f"{best_params.get('total_profit', 0):.6f}"],
            ["Total Profit %", f"{best_params.get('total_profit_pct', 0):.2f}%"],
            ["Buy Trades", best_params.get('buy_trades', 0)],
            ["Sell Trades", best_params.get('sell_trades', 0)],
        ]
        report_str += tabulate(perf_data, headers=perf_headers, tablefmt="pretty") + "\n"
        report_str += "-" * 50 + "\n"
    
    print(report_str)
    return report_str

async def get_available_ranges(pool, symbol):
    """
    Fetches and returns a list of continuous data ranges for a symbol,
    sorted by size (descending).
    """
    gap_interval_seconds = Config.CYCLE_INTERVAL * 5
    async with pool.acquire() as connection:
        records = await connection.fetch(f"""
            WITH TimeGaps AS (
                SELECT time, LAG(time, 1) OVER (ORDER BY time) as prev_time
                FROM order_books WHERE symbol = $1
            ), IslandMarkers AS (
                SELECT time, CASE WHEN EXTRACT(EPOCH FROM (time - prev_time)) > {gap_interval_seconds} THEN 1 ELSE 0 END as is_new_island
                FROM TimeGaps
            ), IslandGroups AS (
                SELECT time, SUM(is_new_island) OVER (ORDER BY time) as island_id FROM IslandMarkers
            )
            SELECT MIN(time) as start_range, MAX(time) as end_range, COUNT(*) as points
            FROM IslandGroups GROUP BY island_id ORDER BY points DESC;
        """, symbol)
    return records

async def interactive_main():
    """
    Main interactive workflow for the optimizer.
    """
    print("--- Welcome to the Strategy Optimizer ---")
    
    # הגדרת סגנון צבעוני עבור התפריטים
    custom_style = questionary.Style([
        ('qmark', 'fg:#673ab7 bold'),       # סימן השאלה
        ('question', 'bold'),                    # טקסט השאלה
        ('pointer', 'fg:#673ab7 bold'),           # הסמן (חץ)
        ('highlighted', 'fg:#673ab7 bold'),       # השורה המודגשת
        ('selected', 'fg:#cc5454'),              # פריט שנבחר (ב-checkbox)
        ('separator', 'fg:#cc5454'),             # קו מפריד
        ('answer', 'fg:#f44336 bold'),           # התשובה הסופית
    ])

    # 1. Select symbols
    symbols_to_run = await questionary.checkbox(
        "Select symbols to optimize (space to select, enter to confirm):",
        choices=Config.SYMBOLS + [questionary.Separator(), "ALL"],
        style=custom_style
    ).ask_async()

    if not symbols_to_run:
        print("No symbols selected. Exiting.")
        return

    if "ALL" in symbols_to_run:
        symbols_to_run = Config.SYMBOLS

    # 2. Connect to DB and fetch time ranges
    pool = await asyncpg.create_pool(
        user=Config.DB_USER, password=Config.DB_PASSWORD,
        database=Config.DB_DATABASE, host=Config.DB_HOST, port=Config.DB_PORT
    )
    
    print(f"\nFetching available time ranges for {symbols_to_run[0]}...")
    ranges = await get_available_ranges(pool, symbols_to_run[0])

    if not ranges:
        print(f"No data found for {symbols_to_run[0]}. Cannot proceed.")
        await pool.close()
        return

    # 3. Select time range
    range_choices = [
        f"From {r['start_range'].strftime('%Y-%m-%d %H:%M')} to {r['end_range'].strftime('%Y-%m-%d %H:%M')} ({r['points']} data points)"
        for r in ranges
    ]
    
    selected_range_str = await questionary.select(
        "Select a time range to run the optimization on (sorted by size):",
        choices=range_choices,
        style=custom_style
    ).ask_async()

    if not selected_range_str:
        print("No time range selected. Exiting.")
        await pool.close()
        return

    selected_index = range_choices.index(selected_range_str)
    selected_range = ranges[selected_index]
    start_dt = selected_range['start_range']
    end_dt = selected_range['end_range']

    # 4. Run the optimizer
    report_content = await main_optimizer(symbols_to_run, start_dt, end_dt, pool)
    await pool.close()

    # 5. Save the report to a file
    if report_content:
        reports_dir = "REPORTS"
        if not os.path.exists(reports_dir):
            os.makedirs(reports_dir)

        symbols_str = "_".join(symbols_to_run) if len(symbols_to_run) < 4 else "MULTIPLE_SYMBOLS"
        filename = os.path.join(reports_dir, f"opt_report_{symbols_str}_{start_dt.strftime('%Y%m%d_%H%M')}_to_{end_dt.strftime('%Y%m%d_%H%M')}.txt")
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(report_content)
        print(f"\n✅ Report saved successfully to: {filename}")

if __name__ == "__main__":
    try:
        asyncio.run(interactive_main())
    except KeyboardInterrupt:
        print("\nOptimizer cancelled by user. Exiting.")