import math
import statistics

# ===================================================== data processing
# מחשבון ניתוח שוק (תנודתיות, לחץ וכו')
# =====================================================
class MARKETS_CALC:
    def __init__(self, coin):
        self.coin = coin

    def calculate_med_price(self):
        try:
            prices = []
            for ex, ob in self.coin.orderbooks.items():
                if ob is not None and ob.get("bids") and ob.get("asks"):
                    b, a = ob["bids"][0], ob["asks"][0]
                    prices.append((b[0] + a[0]) / 2)
                else:
                    # זה בסדר, במצב Fallback חלק מהבורסות יהיו ריקות
                    pass 
            if not prices:
                # זה יקרה באופן תקין במצב Fallback, אין צורך להדפיס שגיאה
                return 0.0
            return statistics.median(prices)
        except Exception as e:
            print(f"MARKETS_CALC: An unexpected error occurred in calculate_med_price for {self.coin.symbol}: {e}")
            return 0.0

    def _other_exchanges_med(self, exclude):
        prices = []
        for ex in self.coin.orderbooks.keys():
            if ex in exclude:
                continue
            
            ob = self.coin.orderbooks.get(ex)
            if ob and ob.get("bids") and ob.get("asks"):
                prices.append((ob["bids"][0][0] + ob["asks"][0][0]) / 2)
        
        if prices:
            return statistics.median(prices)
        return 0.0

    def binance_price(self):
        ob = self.coin.orderbooks.get("binance")
        if not ob or not ob.get("bids") or not ob.get("asks"):
            return self._other_exchanges_med(["binance"])
        return (ob["bids"][0][0] + ob["asks"][0][0]) / 2

    def bybit_price(self):
        ob = self.coin.orderbooks.get("bybit")
        if not ob or not ob.get("bids") or not ob.get("asks"):
            return self._other_exchanges_med(["bybit"])
        return (ob["bids"][0][0] + ob["asks"][0][0]) / 2

    def okx_price(self):
        ob = self.coin.orderbooks.get("okx")
        if not ob or not ob.get("bids") or not ob.get("asks"):
            return self._other_exchanges_med(["okx"])
        return (ob["bids"][0][0] + ob["asks"][0][0]) / 2

    def calculate_volatility(self):
        prices = [p[1] for p in list(self.coin.med_price_history)]
        if len(prices) < 2: return 0.0
        returns = [math.log(p2 / p1) for p1, p2 in zip(prices, prices[1:]) if p1 > 0 and p2 > 0]
        if not returns: return 0.0
        return statistics.stdev(returns) if len(returns) > 1 else 0.0

    def calculate_pressure_ratios(self):
        buy, sell = [], []
        for ob in self.coin.orderbooks.values():
            if not ob or not ob.get("bids") or not ob.get("asks"): continue
            bid_qty = sum(q for _, q in ob["bids"])
            ask_qty = sum(q for _, q in ob["asks"])
            if ask_qty > 0: buy.append(bid_qty / ask_qty)
            if bid_qty > 0: sell.append(ask_qty / bid_qty)
        return (statistics.mean(buy) if buy else 0.0, statistics.mean(sell) if sell else 0.0)