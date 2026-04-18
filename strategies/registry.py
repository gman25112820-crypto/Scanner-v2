"""
strategies/registry.py
======================
Base class for all strategies + registry that auto-discovers them.
Add a new strategy by dropping a file into strategies/ — it registers itself.
"""
from __future__ import annotations
import importlib
import pkgutil
from abc import ABC, abstractmethod
from pathlib import Path
import pandas as pd


class BaseStrategy(ABC):
    """Every strategy inherits from this."""
    name: str = "unnamed"
    description: str = ""
    asset_classes: list[str] = ["stocks"]   # stocks | options | futures | forex | crypto
    timeframes: list[str] = ["1d"]

    # ------------------------------------------------------------------
    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Accepts OHLCV dataframe.
        Must return a dataframe with at minimum a 'signal' column:
          1  = long entry
         -1  = short entry
          0  = no signal
        Optionally add: stop_loss, take_profit, r_multiple columns.
        """
        ...

    # ------------------------------------------------------------------
    def scan(self, df: pd.DataFrame, symbol: str) -> dict | None:
        """Return the latest signal dict if there is one, else None."""
        df = self.generate_signals(df.copy())
        if df.empty:
            return None
        last = df.iloc[-1]
        if last.get("signal", 0) == 0:
            return None
        return {
            "strategy": self.name,
            "symbol": symbol,
            "direction": "long" if last["signal"] == 1 else "short",
            "entry": last.get("entry", last["close"]),
            "stop": last.get("stop_loss", None),
            "target": last.get("take_profit", None),
            "r_multiple": last.get("r_multiple", None),
            "timestamp": last.name,
        }


# ======================================================================
class StrategyRegistry:
    """Auto-discovers and holds all strategy classes."""

    def __init__(self):
        self._strategies: dict[str, BaseStrategy] = {}
        self._discover()

    def _discover(self):
        pkg_path = Path(__file__).parent
        for finder, name, _ in pkgutil.iter_modules([str(pkg_path)]):
            if name in ("registry", "__init__"):
                continue
            try:
                mod = importlib.import_module(f"strategies.{name}")
                for attr in dir(mod):
                    obj = getattr(mod, attr)
                    if (isinstance(obj, type)
                            and issubclass(obj, BaseStrategy)
                            and obj is not BaseStrategy):
                        instance = obj()
                        self._strategies[instance.name] = instance
            except Exception:
                pass

    def get(self, name: str | None = None) -> list[BaseStrategy]:
        if name:
            return [self._strategies[name]] if name in self._strategies else []
        return list(self._strategies.values())

    def list(self) -> list[str]:
        return list(self._strategies.keys())
