# Config.py - הקונפיגורציה המושלמת (תוך שמירה על עקרונות ניהול סיכונים)
import os
from enum import Enum
from dotenv import load_dotenv
from COIN_MODELS.MARKETS_FETCH_DATA import BinanceConnector, BybitConnector, OKXConnector

# טעינת משתני סביבה מקובץ .env
load_dotenv()

# =====================================================
# איתותים (הבסיס לכל המערכת)
# =====================================================
class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"

# =====================================================
# קונפיגורציה ראשית
# =====================================================
class Config:
    
    # -------------------------------------------------
    # הגדרות חיבור לבורסות
    # -------------------------------------------------
    EXCHANGES = {
        "binance": BinanceConnector(),
        "bybit": BybitConnector(),
        "okx": OKXConnector()
    }
    
    # -------------------------------------------------
    # הגדרות מטבעות ולולאה ראשית
    # -------------------------------------------------
    # רשימת המטבעות למעקב
    SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    
    # מרווח (במדויק) בין כל מחזור עיבוד נתונים (בשניות)
    CYCLE_INTERVAL = 2  # מומלץ 1-2 שניות ל-4-5 מטבעות
    
    # -------------------------------------------------
    # פרמטרים של ניתוח ואסטרטגיה - מחושבים דינמית!
    # -------------------------------------------------
    
    # הגדרת אורך ההיסטוריה המבוקש (בדקות)
    HISTORY_TIME_MINUTES = 7 
    # חישוב: כמות דגימות הנדרשת כדי לכסות את הדקות הללו
    HISTORY_LIMIT = int((HISTORY_TIME_MINUTES * 60) / CYCLE_INTERVAL)  # 210 דגימות עבור 7 דקות

    # חלון זמן לחישוב מומנטום (רבע מההיסטוריה)
    MOMENTUM_WINDOW = int(HISTORY_LIMIT / 4) # 52 דגימות
    
    # חלון זמן לחישוב תנודתיות (חצי מההיסטוריה)
    VOLATILITY_WINDOW = int(HISTORY_LIMIT / 2) # 105 דגימות
    
    # סף רגישות בסיסי ללחץ קנייה/מכירה (ערך מקובל)
    BASE_THRESHOLD = 1.15  # דורש 15% יותר נפח ב-Bid/Ask
    
    # מקסימום התאמת וולטיליות (מגדיל את הסף בשווקים תנודתיים)
    MAX_VOL_ADJ = 0.5  
    
    # מינימום שינוי אחוזים במחיר מרגע האיתות כדי לאשר עסקה
    MIN_PCT_CHANGE = 0.0001 # 0.01%
    
    # מינימום איתותים עוקבים לאישור עסקה (למניעת רעש)
    MIN_CONSEC_SIGNALS = 2  
    
    # -------------------------------------------------
    # פרמטרים של ניהול סיכונים (R:R - יחס סיכון/סיכוי)
    # -------------------------------------------------
    FEE = 0.001 # עמלת מסחר (0.1%)
    
    # רווח למימוש (Take Profit) - 1%
    TAKE_profit_PCT = 0.010 
    
    # הפסד לעצירה (Stop Loss) - 0.66%
    # זה נותן יחס R:R של 1:1.5 (סיכון 0.66% לרווח 1%)
    STOP_LOSS_PCT = 0.0066 

    # -------------------------------------------------
    # הגדרות בסיס נתונים (PostgreSQL + TimescaleDB)
    # -------------------------------------------------
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "password") 
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_DATABASE = os.getenv("DB_DATABASE", "trading_data")

    def __init__(self, **kwargs):
        """
        Initialize a Config instance. 
        If kwargs are provided, they override the class defaults for this instance.
        """
        # Load defaults from class attributes
        self.SYMBOLS = Config.SYMBOLS
        self.CYCLE_INTERVAL = Config.CYCLE_INTERVAL
        self.HISTORY_TIME_MINUTES = Config.HISTORY_TIME_MINUTES
        self.BASE_THRESHOLD = Config.BASE_THRESHOLD
        self.MAX_VOL_ADJ = Config.MAX_VOL_ADJ
        self.MIN_PCT_CHANGE = Config.MIN_PCT_CHANGE
        self.MIN_CONSEC_SIGNALS = Config.MIN_CONSEC_SIGNALS
        self.FEE = Config.FEE
        self.TAKE_profit_PCT = Config.TAKE_profit_PCT
        self.STOP_LOSS_PCT = Config.STOP_LOSS_PCT
        
        # Override with provided kwargs
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        
        # Recalculate dependent parameters
        self.HISTORY_LIMIT = int((self.HISTORY_TIME_MINUTES * 60) / self.CYCLE_INTERVAL)
        self.MOMENTUM_WINDOW = int(self.HISTORY_LIMIT / 4)
        self.VOLATILITY_WINDOW = int(self.HISTORY_LIMIT / 2)

    def to_dict(self):
        return {
            "HISTORY_TIME_MINUTES": self.HISTORY_TIME_MINUTES,
            "BASE_THRESHOLD": self.BASE_THRESHOLD,
            "TAKE_profit_PCT": self.TAKE_profit_PCT,
            "STOP_LOSS_PCT": self.STOP_LOSS_PCT,
            "MIN_CONSEC_SIGNALS": self.MIN_CONSEC_SIGNALS,
            "CYCLE_INTERVAL": self.CYCLE_INTERVAL
        }