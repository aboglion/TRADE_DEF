import time
from datetime import datetime
from CONFIG import Config
from COIN_MODELS.strategy.SignalDecisionEngine import SignalDecisionEngine
from COIN_MODELS.strategy.TradeManager import TradeManager
import traceback
from COIN_MODELS.database.db_handler import TimescaleDBHandler
import asyncio  # <--- נוסף עבור asyncio

# =====================================================
# Coin אובייקט
# =====================================================
class Coin:
    def __init__(self, symbol):
        self.symbol = symbol

        # Use Config from CONFIG.py
        # Initialize SignalDecisionEngine and TradeManager with correct imports
        self.orderbooks = {ex: {"bids": [], "asks": []} for ex in ["binance", "bybit", "okx"]}
        self.signal_state = SignalDecisionEngine(self)
        self.trade_manager = TradeManager(self)
        self.is_in_bought_Position = False
        self.buyed_price = 0.0
        self.med_price_history = []
        self.binance_history = []
        self.bybit_history = []
        self.okx_history = []
        self.current_profit = 0.0
        self.last_buy_time = ""

        self.total_buy_trades = 0
        self.total_sell_trades = 0
        self.total_profit = 0.0
        self.med_price = None
        self.binance_price = None
        self.bybit_price = None
        self.okx_price = None
        self.prev_med_price = None
        self.prev_binance_price = None
        self.prev_bybit_price = None
        self.prev_okx_price = None
        self.signal = "UNKNOWN"
        self.last_time_str = ""
        
        # -----------------------------------------------
        # (בקשה #4) דגל חדש למצב Fallback
        self.Fallback_DATA = False 
        # -----------------------------------------------
        
        ALL_Coins.Coins.append(self)  # Add this coin to the static list


    # ... (הפונקציה reset_coin נשארת זהה) ...


    #####################################################################
    # Process data for the coin, fetch from Config.EXCHANGES, analyze signals, and manage trades
    #####################################################################
    
    # -----------------------------------------------
    # (בקשה #1) הפונקציה הראשית הופכת לאסינכרונית
    async def process_coin(self):
    # -----------------------------------------------
        
        try:
            now = time.time()
            self.last_time_str = datetime.fromtimestamp(now).strftime("%H:%M:%S")

            # -----------------------------------------------
            # (בקשה #1) לוגיקת שליפה אסינכרונית חדשה
            # -----------------------------------------------
            
            # 1. הכנת כל המשימות (הן לא רצות עדיין)
            tasks = []
            exchanges_order = [] # לשמור על הסדר כדי לדעת מי זו מי
            
            for ex, connector in Config.EXCHANGES.items():
                tasks.append(connector.fetch(self.symbol))
                exchanges_order.append(ex)

            # 2. הרצת כל המשימות במקביל והמתנה לתוצאות
            # return_exceptions=True -> חשוב! כדי שכשלון באחת לא יעצור את כולן
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 3. איסוף התוצאות למילון זמני
            fetched_books = {}
            for i, result in enumerate(results):
                ex = exchanges_order[i] # מציאת שם הבורסה לפי הסדר
                
                if isinstance(result, Exception):
                    # אם התוצאה היא שגיאה, נרשום אותה ונמשיך
                    print(f"Coin.process_coin (Async): Error fetching data from {ex} for {self.symbol}: {result}")
                    fetched_books[ex] = {"bids": [], "asks": []} # שמירת ערך ריק
                else:
                    # אם התוצאה תקינה
                    fetched_books[ex] = result
            
            # -----------------------------------------------
            # שלב חדש: שמירת הנתונים בבסיס הנתונים
            await TimescaleDBHandler.save_order_book_data(self.symbol, fetched_books)
            # -----------------------------------------------

            # -----------------------------------------------
            # (בקשה #4) לוגיקת בדיקת תקינות נתונים ו-Fallback
            # -----------------------------------------------

            # פונקציית עזר קטנה לבדיקת נתונים תקינים
            def is_book_valid(book):
                return book and book.get("bids") and book.get("asks")

            # בדיקת תנאי החובה: נתוני בינאנס + לפחות עוד בורסה 1
            binance_ok = is_book_valid(fetched_books.get("binance"))
            other_ok_count = sum(1 for ex, book in fetched_books.items() 
                                 if ex != "binance" and is_book_valid(book))
            
            is_data_healthy = binance_ok and (other_ok_count >= 1)

            if is_data_healthy:
                # --- מצב תקין: המשך עיבוד ---
                if self.Fallback_DATA:
                    print(f"[{self.symbol}] Data recovered. Exiting fallback mode.")
                
                self.Fallback_DATA = False
                self.orderbooks = fetched_books # עדכון הנתונים הרשמי
                
                # שמירת מחירים קודמים
                self.prev_med_price = self.med_price
                self.prev_binance_price = self.binance_price
                self.prev_bybit_price = self.bybit_price
                self.prev_okx_price = self.okx_price
                
                # הרצת ניתוח וחישוב מחירים
                self.signal_state.analyze(now)

                self.binance_price = self.signal_state.binance_price
                self.bybit_price = self.signal_state.bybit_price
                self.okx_price = self.signal_state.okx_price
                self.med_price = self.signal_state.med_price
                self.signal = self.signal_state.last_decision.name if self.signal_state.last_decision else "UNKNOWN"

                # הרצת לוגיקת מסחר (רק אם המחיר תקין)
                if self.med_price is not None and self.med_price > 0 and self.prev_med_price != self.med_price:
                    self.trade_manager.check_selling_cond()
                    self.trade_manager.check_buying_cond()

            else:
                # --- מצב כשלון/Fallback: דלג על עיבוד ---
                if not self.Fallback_DATA:
                    print(f"[{self.symbol}] Entering FALLBACK_DATA mode. Binance OK: {binance_ok}, Others OK: {other_ok_count}. Waiting for data recovery.")
                
                
                
                # איפוס מחירים כדי לשקף מצב לא תקין
                self.med_price = None
                self.binance_price = None
                self.bybit_price = None
                self.okx_price = None
                self.prev_med_price = None
                self.prev_binance_price = None
                self.prev_bybit_price = None
                self.prev_okx_price = None
                self.Fallback_DATA = True
                self.signal = "FALLBACK_DATA"
                # אין לקרוא ל-analyze או trade_manager
            

        except Exception as e:
            # לוג שגיאה כללי
            print(f"Coin.process_coin: Critical Error processing coin {self.symbol}: {e}")
            traceback.print_exc()  # הדפסת ה-traceback המלא לדיבוג

            self.med_price = None
            self.binance_price = None
            self.bybit_price = None
            self.okx_price = None
            self.prev_med_price = None
            self.prev_binance_price = None
            self.prev_bybit_price = None
            self.prev_okx_price = None
            self.Fallback_DATA = True
            self.signal = "ERROR"
            self.Fallback_DATA = True # כניסה למצב הגנה גם בשגיאה


# ... (שאר הקובץ, כולל קלאס ALL_Coins, נשאר זהה) ...
class ALL_Coins:
    """
    Static class to manage all Coin instances.
    """
    Coins = []
    @staticmethod
    def print_all_coins():
        return f"\tALL_Coins:->  [{'| '.join(coin.symbol for coin in ALL_Coins.Coins)} ]"