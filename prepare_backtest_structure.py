"""
RAGE Engine -- prepare_backtest_structure.py
=============================================
One-shot converter.

Reads the flat summary CSVs that live directly in output/:
    output/rage_router_v2_summary.csv
    output/mtf_rage_summary.csv
    output/momentum_destroyer_summary.csv
    output/volume_surge_summary.csv
    output/breakout_retest_summary.csv
    output/all_backtest_results.csv   (catch-all)

...and writes them into the subfolder structure that
build_master_performance.py expects:
    output/backtest/<strategy>_<symbol>/metrics.csv

Run once:  python prepare_backtest_structure.py
Then:      python build_master_performance.py   (or click Rebuild Master Tables)
"""

from __future__ import annotations

import sys
import io
import re
from pathlib import Path
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BASE_DIR     = Path(__file__).resolve().parent
OUTPUT_DIR   = BASE_DIR / "output"
BACKTEST_DIR = OUTPUT_DIR / "backtest"

# ------------------------------------------------------------------
# Column aliases -- maps whatever column names are in the CSVs
# to the canonical names build_master_performance.py understands
# ------------------------------------------------------------------
COL_ALIASES = {
    # strategy / symbol
    "strategy_name":     "strategy",
    "strat":             "strategy",
    "ticker":            "symbol",
    "pair":              "symbol",
    "instrument":        "symbol",
    "market":            "symbol",
    # performance
    "sharpe_ratio":      "sharpe",
    "sharpe":            "sharpe",
    "sortino_ratio":     "sortino",
    "sortino":           "sortino",
    "win_rate":          "winrate",
    "winrate":           "winrate",
    "win%":              "winrate",
    "max_drawdown":      "drawdown",
    "drawdown":          "drawdown",
    "num_trades":        "trades",
    "total_trades":      "trades",
    "trades":            "trades",
    "annualised_return": "ann_return",
    "annualized_return": "ann_return",
    "annual_return":     "ann_return",
    "ann_return":        "ann_return",
    "total_return":      "total_return",
    "return":            "total_return",
    "profit_factor":     "profit_factor",
    "avg_trade_pnl":     "avg_pnl",
    "avg_pnl":           "avg_pnl",
    "avg_r":             "avg_pnl",
    "expectancy":        "avg_pnl",
}

KEEP_COLS = ["strategy", "symbol", "sharpe", "sortino", "winrate",
             "drawdown", "trades", "ann_return", "total_return",
             "profit_factor", "avg_pnl"]


def normalise_df(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase columns, apply aliases, keep only useful cols."""
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    df = df.rename(columns={k: v for k, v in COL_ALIASES.items() if k in df.columns})
    keep = [c for c in KEEP_COLS if c in df.columns]
    return df[keep]


def strategy_from_filename(path: Path) -> str:
    """rage_router_v2_summary.csv  ->  rage_router_v2"""
    name = path.stem  # e.g. rage_router_v2_summary
    name = re.sub(r"_summary$", "", name)
    name = re.sub(r"_results$", "", name)
    return name.lower()


def write_metrics(strategy: str, symbol: str, row: pd.Series):
    folder_name = f"{strategy}_{symbol}".lower().replace(" ", "_")
    dest_dir    = BACKTEST_DIR / folder_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file   = dest_dir / "metrics.csv"

    metrics = row.to_frame(name="value")
    metrics.index.name = "metric"
    metrics = metrics[metrics.index != "strategy"]
    metrics = metrics[metrics.index != "symbol"]
    metrics.to_csv(dest_file)
    return dest_file


def process_summary_file(path: Path) -> int:
    """Returns number of metrics.csv files written."""
    print(f"  Reading {path.name} ...")
    try:
        df = pd.read_csv(path)
    except Exception as e:
        print(f"    [SKIP] Cannot read: {e}")
        return 0

    df = normalise_df(df)

    if df.empty:
        print(f"    [SKIP] No usable columns after normalisation.")
        return 0

    # Infer strategy from filename if column missing
    if "strategy" not in df.columns:
        df["strategy"] = strategy_from_filename(path)

    # Infer symbol if missing
    if "symbol" not in df.columns:
        df["symbol"] = "UNKNOWN"

    written = 0
    for _, row in df.iterrows():
        strategy = str(row.get("strategy", "unknown")).strip().lower().replace(" ", "_")
        symbol   = str(row.get("symbol",   "UNKNOWN")).strip().upper().replace(" ", "_")
        dest     = write_metrics(strategy, symbol, row)
        print(f"    -> {dest.relative_to(BASE_DIR)}")
        written += 1

    return written


def main():
    print("=" * 55)
    print("  RAGE Engine -- Prepare Backtest Structure")
    print("=" * 55)

    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)

    # Find all *_summary.csv and *_results.csv in output/
    candidates = sorted(
        list(OUTPUT_DIR.glob("*_summary.csv")) +
        list(OUTPUT_DIR.glob("*_results.csv")) +
        list(OUTPUT_DIR.glob("all_backtest_results.csv"))
    )

    if not candidates:
        print(f"\n  [ERROR] No summary/results CSVs found in {OUTPUT_DIR}")
        sys.exit(1)

    print(f"\n  Found {len(candidates)} source file(s):\n")
    total = 0
    for f in candidates:
        n = process_summary_file(f)
        total += n
        print()

    print("=" * 55)
    if total:
        print(f"  [OK] Written {total} metrics.csv file(s) into output/backtest/")
        print("  Now click  Rebuild Master Tables  in the launcher.")
    else:
        print("  [WARN] Nothing written -- check column names in your CSVs.")
    print("=" * 55 + "\n")


if __name__ == "__main__":
    main()
