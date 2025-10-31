import httpx 
import asyncio 
from datetime import datetime

class BinanceConnector:
    # 'async def' מאפשר קריאה אסינכרונית
    async def fetch(self, symbol):
        url = "https://api.binance.com/api/v3/depth"
        params = {"symbol": symbol, "limit": 5}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # 'await' ממתין לתגובה מבלי לחסום את שאר התוכנית
                r = await client.get(url, params=params)
                r.raise_for_status()  # יזרוק שגיאה אם ה-status אינו 2xx
                data = r.json()
                return {"bids": [[float(p), float(q)] for p, q in data["bids"]],
                        "asks": [[float(p), float(q)] for p, q in data["asks"]]}
        # httpx זורק שגיאות מסוג אחר
        except httpx.RequestError as e:
            print(f"BinanceConnector (Async): Request failed: {e}")
            return {"bids": [], "asks": []} # החזרת ערך ריק בכישלון
        except Exception as e:
            # לטיפול בשגיאות JSON או אחרות
            print(f"BinanceConnector (Async): General error: {e}")
            return {"bids": [], "asks": []}

class BybitConnector:
    # 'async def'
    async def fetch(self, symbol):
        url = "https://api.bybit.com/v5/market/orderbook"
        params = {"category": "spot", "symbol": symbol, "limit": 5}
        try:
             
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(url, params=params)
                r.raise_for_status()
                data = r.json()
                return {"bids": [[float(p), float(q)] for p, q in data["result"]["b"]],
                        "asks": [[float(p), float(q)] for p, q in data["result"]["a"]]}
        except httpx.RequestError as e:
            print(f"BybitConnector (Async): Request failed: {e}")
            return {"bids": [], "asks": []}
        except Exception as e:
            print(f"BybitConnector (Async): General error: {e}")
            return {"bids": [], "asks": []}

class OKXConnector:
    async def fetch(self, symbol):
        instId = symbol.replace("USDT", "-USDT")
        url = "https://www.okx.com/api/v5/market/books"
        params = {"instId": instId, "sz": 5}
        try:
             
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(url, params=params)
                r.raise_for_status()
                data = r.json()
                return {"bids": [[float(p), float(q)] for p, q, *_ in data["data"][0]["bids"]],
                        "asks": [[float(p), float(q)] for p, q, *_ in data["data"][0]["asks"]]}
        except httpx.RequestError as e:
            print(f"OKXConnector (Async): Request failed: {e}")
            return {"bids": [], "asks": []}
        except Exception as e:
            print(f"OKXConnector (Async): General error: {e}")
            return {"bids": [], "asks": []}