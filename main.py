# main.py

import asyncio
import time
import traceback
from datetime import datetime

try:
    from CONFIG import Config
    from COIN_MODELS.COIN_MAIN import Coin, ALL_Coins
    from COIN_MODELS.database.db_handler import TimescaleDBHandler
except ImportError as e:
    print(f"!!! CRITICAL IMPORT ERROR !!!: {e}")
    exit(1)

# =====================================================
# פונקציית הלולאה הראשית (אסינכרונית)
# =====================================================
async def main_loop():
    """
    מנהלת את לולאת הריצה הראשית, מאתחלת את המטבעות ומריצה את העיבוד
    של כל המטבעות במקביל באמצעות asyncio.gather.
    """
    
    print("-" * 50)
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- System Initialization ---")
    
    # 0. אתחול בסיס הנתונים
    await TimescaleDBHandler.initialize_db()
    print("Database initialized.")

    # 1. אתחול אובייקטים של מטבעות
    if not Config.SYMBOLS:
        print("CRITICAL: Config.SYMBOLS is empty. Cannot start.")
        return

    for symbol in Config.SYMBOLS:
        Coin(symbol)
        
    print(f"Tracking {len(ALL_Coins.Coins)} coins: {', '.join(Config.SYMBOLS)}")
    print(f"Cycle interval: {Config.CYCLE_INTERVAL} seconds.")
    print(f"History/Volatility/Momentum windows: {Config.HISTORY_LIMIT}/{Config.VOLATILITY_WINDOW}/{Config.MOMENTUM_WINDOW}")
    print("-" * 50)

    # 2. לולאה אינסופית
    while True:
        start_time = time.time()
        now_str = datetime.now().strftime("%H:%M:%S")

        try:
            # 3. הכנת רשימת משימות (async tasks)
            # יצירת רשימה של קריאות ל-process_coin() עבור כל מטבע
            coin_tasks = [coin.process_coin() for coin in ALL_Coins.Coins]
            
            # 4. הרצת כל המשימות במקביל והמתנה לסיום כולן
            await asyncio.gather(*coin_tasks)

            end_time = time.time()
            cycle_duration = end_time - start_time
            
            # 5. הדפסת סיכום "סיבוב"
            print(f"[{now_str}] Cycle completed in {cycle_duration:.2f}s. Summary:")
            
            for coin in ALL_Coins.Coins:
                status_color = "🟢" if coin.signal in ["BUY", "SELL"] and not coin.Fallback_DATA else "🟡" if coin.Fallback_DATA else "⚫"
                
                print(f"  {status_color} {coin.symbol:<8} | Price: {coin.med_price:10.4f} | Signal: {coin.signal:<15} | Fallback: {'YES' if coin.Fallback_DATA else 'NO'}")
                
            
            # 6. המתנה (המתנה יעילה שמפצה על הזמן שכבר עבר)
            time_to_sleep = Config.CYCLE_INTERVAL - cycle_duration
            if time_to_sleep > 0:
                await asyncio.sleep(time_to_sleep)
            else:
                # אם העיבוד ארך יותר מהמרווח, נדפיס אזהרה וניגש מיד לסיבוב הבא
                print(f"!!! WARNING: Cycle took too long ({cycle_duration:.2f}s). No sleep applied.")
                

        except KeyboardInterrupt:
            print("\nShutdown signal received. Exiting main loop gracefully.")
            break
        except Exception as e:
            print(f"\n!!! CRITICAL ERROR IN MAIN LOOP !!!: {e}")
            traceback.print_exc()
            print("Restarting loop after 5 seconds...")
            await asyncio.sleep(5) 

# =====================================================
# נקודת כניסה ראשית
# =====================================================
if __name__ == "__main__":
    try:
        # הפעלת הלולאה הראשית האסינכרונית
        asyncio.run(main_loop())
    except Exception as e:
        print(f"Failed to start asyncio loop: {e}")