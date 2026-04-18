from __future__ import annotations
import pandas as pd
from pathlib import Path
from utils.logger import setup_logger

log = setup_logger("scanner.data")

DEFAULT_WATCHLIST = [
    "AAPL", "MSFT", "NVDA", "TSLA", "AMZN",
    "META", "GOOGL", "SPY", "QQQ", "AMD",
    "BTC-USD", "ETH-USD", "GC=F", "CL=F", "EURUSD=X"
]

class DataLoader:
    def __init__(self, period="6mo", interval="1d", cache_dir="output/data_cache"):
        self.period = period
        self.interval = interval
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)

    def fetch(self, symbol):
        cache_path = self.cache / f"{symbol.replace('/', '_')}.csv"
        if cache_path.exists():
            try:
                df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
                df.columns = [c.lower() for c in df.columns]
                return df
            except Exception:
                pass
        try:
            import yfinance as yf
            raw = yf.download(symbol, period=self.period, interval=self.interval, progress=False, auto_adjust=True)
            if raw is None or raw.empty:
                return None
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            raw.columns = [c.lower() for c in raw.columns]
            raw = raw.dropna(subset=["open", "high", "low", "close"])
            raw.to_csv(cache_path)
            return raw
        except Exception as e:
            log.error(f"Failed to fetch {symbol}: {e}")
        return None

    def get_watchlist(self):
        wl_path = Path("config/watchlist.txt")
        if wl_path.exists():
            return [l.strip() for l in wl_path.read_text().splitlines()
                    if l.strip() and not l.startswith("#")]
        return DEFAULT_WATCHLIST

    def from_csv(self, path):
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        df.columns = [c.lower() for c in df.columns]
        return df