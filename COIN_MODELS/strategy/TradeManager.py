from CONFIG import Config, SignalType

import os

# =====================================================
# TradeManager – קנייה/מכירה
# =====================================================
class TradeManager:
    def __init__(self, coin):
        self.coin = coin
        self.trade_log = []
        self.lock=False

        self.trade_log_path= os.path.join("LOGS", f"{self.coin.symbol}_trade_log.txt")
        if not os.path.exists("LOGS"):
            os.makedirs("LOGS")

    def execute_buy(self):
        self.lock=True
        if not self.coin.is_in_bought_Position:
            self.coin.is_in_bought_Position = True
            self.coin.last_buy_time = self.coin.last_time_str
            self.coin.current_profit = 0.0
            self.coin.buyed_price = self.coin.binance_price
            if self.coin.total_buy_trades is None:
                self.coin.total_buy_trades = 0
            self.coin.total_buy_trades += 1
            print(f"[{self.coin.symbol}] Executing BUY. Total Buy Trades: {self.coin.total_buy_trades}")
            return True
        print(f"[{self.coin.symbol}] Not executing BUY: Already in position.")
        self.lock=False
        return False

    def execute_sell(self):
        self.lock=True
        self.coin.is_in_bought_Position = False
        self.coin.total_sell_trades += 1
        self.coin.total_profit += self.coin.current_profit
        self.coin.buyed_price = 0.0
        self.coin.current_profit = 0.0
        print(f"[{self.coin.symbol}] Executing SELL. Total Sell Trades: {self.coin.total_sell_trades}, Total Profit: {self.coin.total_profit:.4f}")
        self.lock=False
        return True



    def check_buying_cond(self):
        # Count how many exchanges show an increase in price
        if self.lock :
             return False
        if  self.coin.binance_price is None or self.coin.prev_binance_price is None :
            return False            
        price_increases = 0
        if (
            self.coin.okx_price is not None and
            self.coin.prev_okx_price is not None and
            self.coin.okx_price > self.coin.prev_okx_price
        ):
            price_increases += 1
        if (
            self.coin.bybit_price is not None and
            self.coin.prev_bybit_price is not None and
            self.coin.bybit_price > self.coin.prev_bybit_price
        ):
            price_increases += 1
        if (
            self.coin.binance_price is not None and
            self.coin.prev_binance_price is not None and
            self.coin.binance_price > self.coin.prev_binance_price
        ):
            price_increases += 1

        # Require at least 2 out of 3 exchanges to show an increase
        if (self.coin.signal == SignalType.BUY.name and
            not self.coin.is_in_bought_Position and
            price_increases >= 2):
                print(f"[{self.coin.symbol}] Buy conditions met: Signal={self.coin.signal}, Not in position, Price Increases={price_increases}")
                if self.execute_buy():
                    msg = f"[{self.coin.last_time_str}] BUY @ {self.coin.binance_price:.4f} | Signal: {self.coin.signal}"
                    self._log(msg)
                    return True
                else:
                    print(f"[{self.coin.symbol}] Buy execution failed.")

        # print(f"[{self.coin.symbol}] Buy conditions NOT met: Signal={self.coin.signal}, In Position={self.coin.is_in_bought_Position}, Price Increases={price_increases}")
        return False


    def check_selling_cond(self):
        if self.lock : 
            return False            
        if  self.coin.binance_price is None or self.coin.prev_binance_price is None :
            return False
        if not self.coin.is_in_bought_Position or self.coin.buyed_price <= 0:
            # print(f"[{self.coin.symbol}] Not checking sell conditions: Not in bought position or buyed price is zero.")
            return False

        reason=None
        if self.coin.current_profit >= Config.TAKE_profit_PCT:
            print(f"[{self.coin.symbol}] Take Profit condition met.")
            reason="💰 TAKE_profit"
        if self.coin.current_profit <= -Config.STOP_LOSS_PCT:
            print(f"[{self.coin.symbol}] Stop Loss condition met.")
            reason="🛑 STOP_LOSS"
        if self.coin.signal == SignalType.SELL.name and self.coin.current_profit >= 0 :
            print(f"[{self.coin.symbol}] Sell Signal condition met.")
            reason="📉 SELL_SIGNAL"

        if reason is not None and self.execute_sell :
            self.coin.current_profit = (self.coin.binance_price - self.coin.buyed_price) / self.coin.buyed_price - (Config.FEE * 2)
            msg = f"[{self.coin.last_time_str}] SELL @ {self.coin.binance_price:.4f} | Reason: {reason} | PnL: {self.coin.current_profit * 100:.4f}%"
            self._log(msg)
        return False

    def _log(self, msg):
        with open(self.trade_log_path, "a+") as f:
            f.write(msg + "\n")
        self.trade_log.append(msg)


    def reset_trades(self):
        self.coin.total_buy_trades = 0
        self.coin.total_sell_trades = 0
        self.coin.total_profit = 0.0
        self.trade_log = []
        try:
            with open(self.trade_log_path, "w") as f:
                f.write("")
        except FileNotFoundError:
            print(f"Log file {self.trade_log_path} not found. Skipping reset.")
            pass # Log file might not exist yet