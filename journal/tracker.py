"""
journal/tracker.py
==================
Trade journal — log trades, tag setups, view stats.
Integrates with backtester output and supports manual trade entry.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from utils.logger import setup_logger

log = setup_logger("scanner.journal")
JOURNAL_PATH = Path("output/journal/trades.csv")

COLUMNS = [
    "date", "symbol", "setup_type", "direction",
    "entry", "exit", "stop_loss", "take_profit",
    "r_multiple", "result", "pnl_gbp", "notes", "tags"
]


class TradeJournal:
    def __init__(self):
        JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not JOURNAL_PATH.exists():
            pd.DataFrame(columns=COLUMNS).to_csv(JOURNAL_PATH, index=False)

    # ------------------------------------------------------------------
    def log_trade(self, symbol: str, setup_type: str, direction: str,
                  entry: float, exit_price: float, stop_loss: float,
                  take_profit: float = None, pnl_gbp: float = None,
                  notes: str = "", tags: str = ""):
        risk = abs(entry - stop_loss)
        r = (exit_price - entry) / risk if direction == "long" else (entry - exit_price) / risk
        result = "win" if r > 0 else "loss"
        row = {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "symbol": symbol,
            "setup_type": setup_type,
            "direction": direction,
            "entry": entry,
            "exit": exit_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "r_multiple": round(r, 3),
            "result": result,
            "pnl_gbp": pnl_gbp,
            "notes": notes,
            "tags": tags,
        }
        df = pd.read_csv(JOURNAL_PATH)
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        df.to_csv(JOURNAL_PATH, index=False)
        log.info(f"Trade logged: {symbol} {direction} R={r:.2f} ({result})")
        return row

    # ------------------------------------------------------------------
    def summary(self):
        df = self._load()
        if df.empty:
            log.info("Journal is empty.")
            return
        r = df["r_multiple"].dropna()
        wins = r[r > 0]
        losses = r[r <= 0]
        print("\n" + "="*50)
        print("  SCANNER — TRADE JOURNAL SUMMARY")
        print("="*50)
        print(f"  Total trades  : {len(df)}")
        print(f"  Win rate      : {len(wins)/len(df):.1%}")
        print(f"  Avg R         : {r.mean():.2f}")
        print(f"  Total R       : {r.sum():.2f}")
        print(f"  Best trade    : {r.max():.2f}R")
        print(f"  Worst trade   : {r.min():.2f}R")
        print(f"  Profit factor : {abs(wins.sum()/losses.sum()):.2f}" if losses.sum() != 0 else "  Profit factor : ∞")
        print("\n  By setup type:")
        for setup, grp in df.groupby("setup_type"):
            g_r = grp["r_multiple"].dropna()
            print(f"    {setup:20s}  trades={len(grp):3d}  wr={( g_r>0).mean():.0%}  avg_r={g_r.mean():.2f}")
        print("="*50 + "\n")

    # ------------------------------------------------------------------
    def get_trades(self, setup_type: str = None, symbol: str = None) -> pd.DataFrame:
        df = self._load()
        if setup_type:
            df = df[df["setup_type"] == setup_type]
        if symbol:
            df = df[df["symbol"] == symbol]
        return df

    def _load(self) -> pd.DataFrame:
        try:
            return pd.read_csv(JOURNAL_PATH)
        except Exception:
            return pd.DataFrame(columns=COLUMNS)
