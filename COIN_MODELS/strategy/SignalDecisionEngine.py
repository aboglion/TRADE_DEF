from collections import deque
from COIN_MODELS.MARKETS_CALC import MARKETS_CALC # Moved import to top
import time
from CONFIG import Config, SignalType  # Import SignalType from CONFIG.py

# =====================================================
# מחליט איתותים
# =====================================================
class SignalDecisionEngine:
    def __init__(self, coin):
        self.coin = coin
        self.recent_signals = deque([SignalType.NEUTRAL] * Config.MOMENTUM_WINDOW, maxlen=Config.MOMENTUM_WINDOW)
        self.current_signal = SignalType.NEUTRAL
        self.signal_price = 0.0
        self.consecutive = 0
        self.last_decision = SignalType.NEUTRAL
        self.med_price = 0.0
        self.volatility = 0.0
        self.momentum = 0.0
        self.buy_pressure = 0.0
        self.sell_pressure = 0.0
        self.binance_price = 0.0  # Main reference price
        self.bybit_price = 0.0  # Secondary reference price
        self.okx_price = 0.0  # OKX reference price

    def analyze(self, now=None):
        # -----------------------------------------------
        # (בקשה #3) הייבוא הכפול הוסר מכאן
        # -----------------------------------------------
        now = now or time.time()
        # Check for stale data from exchanges


        calc = MARKETS_CALC(self.coin)
        self.med_price = calc.calculate_med_price()
        self.binance_price = calc.binance_price()
        self.bybit_price = calc.bybit_price()
        self.okx_price = calc.okx_price()
        
        # -----------------------------------------------
        # (בקשה #4) הוספת בדיקה: אם המחיר הוא 0 (כמו במצב Fallback), 
        # עצור את הניתוח כאן כדי למנוע חישובים על נתונים ריקים.
        if self.med_price <= 0:
            print(f"[{self.coin.symbol}] SignalEngine: Average price is zero ({self.med_price}). Skipping analysis.")
            self.last_decision = SignalType.NEUTRAL
            return self.last_decision
        # -----------------------------------------------

        # Append current prices to history deques regardless of med_price value
        self.coin.med_price_history.append((now, self.med_price))
        self.coin.binance_history.append((now, self.binance_price))
        self.coin.bybit_history.append((now, self.bybit_price))
        self.coin.okx_history.append((now, self.okx_price))

        # Limit history length to Config.HISTORY_LIMIT
        history_limit = Config.HISTORY_LIMIT if Config.HISTORY_LIMIT > 0 else 60
        if len(self.coin.med_price_history) > history_limit:
            self.coin.med_price_history.pop(0)
        if len(self.coin.binance_history) > history_limit:
            self.coin.binance_history.pop(0)
        if len(self.coin.bybit_history) > history_limit:
            self.coin.bybit_history.pop(0)
        if len(self.coin.okx_history) > history_limit:
            self.coin.okx_history.pop(0)    

        # If med_price is still zero or negative after appending, return NEUTRAL
        # (בדיקה זו כעת מיותרת בגלל הבדיקה שהוספנו למעלה, אבל לא מזיקה)
        if self.med_price <= 0:
            print(f"Average price is zero or negative ({self.med_price}). Not appending to history.")
            self.last_decision = SignalType.NEUTRAL
            return self.last_decision

        if self.coin.is_in_bought_Position and self.coin.buyed_price > 0:
            self.coin.current_profit = (self.med_price - self.coin.buyed_price) / self.coin.buyed_price
        else:
            self.coin.current_profit = 0.0

        history_len = len(self.coin.med_price_history)
        # print(f"[{self.coin.symbol}] History Length: {history_len}, Required: {Config.VOLATILITY_WINDOW}")
        if history_len < Config.VOLATILITY_WINDOW:
            self.last_decision = SignalType.NEUTRAL
            return self.last_decision


        self.volatility = calc.calculate_volatility()
        self.buy_pressure, self.sell_pressure = calc.calculate_pressure_ratios()
        # print(f"[{self.coin.symbol}] Volatility: {self.volatility:.4f}, Buy Pressure: {self.buy_pressure:.4f}, Sell Pressure: {self.sell_pressure:.4f}")

        threshold = Config.BASE_THRESHOLD + min(self.volatility * 100, Config.MAX_VOL_ADJ) * (1 + self.momentum)

        raw = SignalType.NEUTRAL
        if self.buy_pressure > threshold: raw = SignalType.BUY
        elif self.sell_pressure > threshold: raw = SignalType.SELL

        self.recent_signals.append(raw)
        self.momentum = (self.recent_signals.count(SignalType.BUY) - self.recent_signals.count(SignalType.SELL)) / len(self.recent_signals)
        # print(f"[{self.coin.symbol}] Momentum: {self.momentum:.4f}")

        final = SignalType.BUY if self.momentum > 0.5 else SignalType.SELL if self.momentum < -0.5 else SignalType.NEUTRAL

        if final == self.current_signal:
            self.consecutive += 1
        else:
            self.current_signal = final
            self.consecutive = 1
            self.signal_price = self.med_price

        if self.consecutive >= Config.MIN_CONSEC_SIGNALS:
            pct_change = abs(self.med_price - self.signal_price) / self.signal_price if self.signal_price > 0 else 0.0
            self.last_decision = final if pct_change >= Config.MIN_PCT_CHANGE else SignalType.NEUTRAL
            # print(f"[{self.coin.symbol}] Final Signal (consecutive): {self.last_decision}, Pct Change: {pct_change:.6f}, Required: {Config.MIN_PCT_CHANGE}")
        else:
            self.last_decision = SignalType.NEUTRAL
            # print(f"[{self.coin.symbol}] Insufficient consecutive signals. Signal: {self.last_decision}")

        return self.last_decision