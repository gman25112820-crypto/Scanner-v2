"""
RAGE Engine — build_master_performance.py
==========================================
Scans output/backtest/ for all metrics.csv files,
aggregates per-strategy and per-symbol stats, then
writes the five master CSVs that app.py reads:

  output/master/master_strategy_symbol_table.csv
  output/master/strategy_rank_table.csv
  output/master/symbol_rank_table.csv
  output/master/profit_factor_matrix.csv
  output/master/avg_pnl_matrix.csv

Run standalone:   python build_master_performance.py
Called by:        launch.bat / launch_rage_public.bat
"""

from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd

# -- Paths (mirror app.py exactly) ------------------------------------
BASE_DIR     = Path(__file__).resolve().parent
OUTPUT_DIR   = BASE_DIR / "output"
BACKTEST_DIR = OUTPUT_DIR / "backtest"
MASTER_DIR   = OUTPUT_DIR / "master"

MASTER_STRATEGY_SYMBOL_CSV  = MASTER_DIR / "master_strategy_symbol_table.csv"
MASTER_STRATEGY_RANK_CSV    = MASTER_DIR / "strategy_rank_table.csv"
MASTER_SYMBOL_RANK_CSV      = MASTER_DIR / "symbol_rank_table.csv"
MASTER_PROFIT_FACTOR_MATRIX = MASTER_DIR / "profit_factor_matrix.csv"
MASTER_AVG_PNL_MATRIX       = MASTER_DIR / "avg_pnl_matrix.csv"

# -- Known strategy names (matches app.py parse_strategy_symbol) ------
KNOWN_STRATEGIES = sorted([
    "mtf_momentum_binary",
    "mtf_trend_continuation_v2",
    "mtf_trend_continuation",
    "mtf_session_sniper",
    "mtf_ny_overlap_hunter",
    "mtf_fx_london_breakout",
    "mtf_us_open_momentum",
    "mtf_volatility_coil_v2",
    "mtf_volatility_coil",
    "adx_trend",
    "macd_rsi",
    "mean_reversion",
    "orb",
    "breakout",
    "pullback_trend",
    "rsi2_adx",
    "rsi2adx",
], key=len, reverse=True)


def parse_strategy_symbol(folder_name: str) -> tuple[str, str]:
    fl = folder_name.lower()
    for s in KNOWN_STRATEGIES:
        if fl == s:
            return s, folder_name
        if fl.startswith(s + "_"):
            sym = folder_name[len(s) + 1:]
            return s, sym if sym else folder_name
    if "_" in folder_name:
        l, r = folder_name.split("_", 1)
        return l.lower(), r
    return folder_name.lower(), folder_name


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def scan_backtest_metrics() -> pd.DataFrame:
    """Walk output/backtest/ and collect every metrics.csv into a flat DataFrame."""
    if not BACKTEST_DIR.exists():
        print(f"  [WARN] Backtest folder not found: {BACKTEST_DIR}")
        return pd.DataFrame()

    records = []
    rename_map = {
        "sharpe_ratio":      "sharpe",
        "sortino_ratio":     "sortino",
        "win_rate":          "winrate",
        "max_drawdown":      "drawdown",
        "num_trades":        "trades",
        "total_trades":      "trades",
        "annualised_return": "ann_return",
        "annualized_return": "ann_return",
        "total_return":      "total_return",
        "profit_factor":     "profit_factor",
        "avg_trade_pnl":     "avg_pnl",
        "avg_r":             "avg_pnl",
        "avg_pnl":           "avg_pnl",
    }

    for metrics_file in sorted(BACKTEST_DIR.rglob("metrics.csv")):
        try:
            folder = metrics_file.parent.name
            strategy, symbol = parse_strategy_symbol(folder)
            df = normalize_columns(pd.read_csv(metrics_file))

            row: dict = {}
            # Support two common formats: key/value pairs OR single wide row
            if "metric" in df.columns and "value" in df.columns:
                for _, r in df.iterrows():
                    key = str(r["metric"]).strip().lower().replace(" ", "_")
                    try:
                        row[key] = float(r["value"])
                    except Exception:
                        row[key] = r["value"]
            elif len(df) == 1:
                row = df.iloc[0].to_dict()
            else:
                numeric = df.select_dtypes(include="number")
                if not numeric.empty:
                    row = numeric.mean().to_dict()

            # Normalise key names
            normalised: dict = {}
            for k, v in row.items():
                kk = str(k).strip().lower().replace(" ", "_")
                normalised[rename_map.get(kk, kk)] = v

            normalised["strategy"]    = strategy
            normalised["symbol"]      = symbol
            normalised["source_file"] = str(metrics_file.relative_to(BASE_DIR))
            records.append(normalised)

        except Exception as exc:
            print(f"  [WARN] Skipping {metrics_file}: {exc}")
            continue

    if not records:
        return pd.DataFrame()

    df = normalize_columns(pd.DataFrame(records))

    # Numeric coercion
    for col in ["sharpe", "sortino", "winrate", "drawdown", "trades",
                "ann_return", "total_return", "profit_factor", "avg_pnl"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Normalise winrate (some backtests emit 0-100, others 0-1)
    if "winrate" in df.columns and not df["winrate"].dropna().empty:
        if df["winrate"].dropna().max() > 1.5:
            df["winrate"] = df["winrate"] / 100.0

    # Make drawdown consistently negative
    if "drawdown" in df.columns and not df["drawdown"].dropna().empty:
        if df["drawdown"].dropna().min() > 0:
            df["drawdown"] = -df["drawdown"]

    return df


def build_strategy_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-strategy, add rank_score and status columns."""
    metric_cols = [c for c in ["sharpe", "sortino", "winrate", "drawdown",
                                "trades", "profit_factor", "ann_return", "avg_pnl"]
                   if c in df.columns]
    agg = df.groupby("strategy", as_index=False)[metric_cols].agg(
        {c: ("mean" if c != "trades" else "sum") for c in metric_cols}
    )

    # Flatten MultiIndex if agg produced one
    if isinstance(agg.columns, pd.MultiIndex):
        agg.columns = ["_".join(c).strip("_") for c in agg.columns]

    # Rename aggregated columns to match app.py expectations
    col_rename = {
        "sharpe":        "avg_sharpe_like",
        "winrate":       "avg_win_rate",
        "profit_factor": "avg_profit_factor",
        "avg_pnl":       "avg_pnl",
        "trades":        "trades",
    }
    agg = agg.rename(columns=col_rename)

    # Count unique symbols per strategy (-> "markets" column in RAGE Control Panel)
    mkt_counts = df.groupby("strategy")["symbol"].nunique().reset_index()
    mkt_counts.columns = ["strategy", "markets"]
    agg = agg.merge(mkt_counts, on="strategy", how="left")

    # Ensure required columns exist with sensible defaults
    for col, default in [("avg_sharpe_like", 0.0), ("avg_win_rate", 0.0),
                         ("drawdown", -1.0), ("avg_profit_factor", 0.0),
                         ("avg_pnl", 0.0), ("trades", 0)]:
        if col not in agg.columns:
            agg[col] = default

    # Composite rank score (0-100)
    agg["rank_score"] = (
        agg["avg_sharpe_like"].fillna(0).clip(0, 3) / 3 * 35 +
        agg["avg_win_rate"].fillna(0).clip(0, 0.7)  / 0.7 * 25 +
        (1 + agg["drawdown"].fillna(-1).clip(-1, 0)) * 20 +
        agg["avg_sharpe_like"].fillna(0).clip(0, 3) / 3 * 20   # sortino proxy
    ).round(2)

    agg = agg.sort_values("rank_score", ascending=False).reset_index(drop=True)
    agg["rank"] = agg.index + 1
    return agg


def build_symbol_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-symbol, add rank_score."""
    metric_cols = [c for c in ["sharpe", "sortino", "winrate", "drawdown",
                                "trades", "profit_factor", "avg_pnl"]
                   if c in df.columns]
    agg = df.groupby("symbol", as_index=False)[metric_cols].agg(
        {c: ("mean" if c != "trades" else "sum") for c in metric_cols}
    )
    if isinstance(agg.columns, pd.MultiIndex):
        agg.columns = ["_".join(c).strip("_") for c in agg.columns]

    col_rename = {
        "sharpe":        "avg_sharpe_like",
        "winrate":       "avg_win_rate",
        "profit_factor": "avg_profit_factor",
        "avg_pnl":       "avg_pnl",
        "trades":        "trades",
    }
    agg = agg.rename(columns=col_rename)

    strat_counts = df.groupby("symbol")["strategy"].nunique().reset_index()
    strat_counts.columns = ["symbol", "strategies"]
    agg = agg.merge(strat_counts, on="symbol", how="left")

    for col, default in [("avg_sharpe_like", 0.0), ("avg_win_rate", 0.0),
                         ("drawdown", -1.0), ("avg_profit_factor", 0.0),
                         ("avg_pnl", 0.0), ("trades", 0)]:
        if col not in agg.columns:
            agg[col] = default

    agg["rank_score"] = (
        agg["avg_sharpe_like"].fillna(0).clip(0, 3) / 3 * 35 +
        agg["avg_win_rate"].fillna(0).clip(0, 0.7)  / 0.7 * 25 +
        (1 + agg["drawdown"].fillna(-1).clip(-1, 0)) * 20 +
        agg["avg_sharpe_like"].fillna(0).clip(0, 3) / 3 * 20
    ).round(2)

    agg = agg.sort_values("rank_score", ascending=False).reset_index(drop=True)
    agg["rank"] = agg.index + 1
    return agg


def build_profit_factor_matrix(df: pd.DataFrame) -> pd.DataFrame:
    if "profit_factor" not in df.columns:
        return pd.DataFrame()
    return df.pivot_table(index="strategy", columns="symbol",
                          values="profit_factor", aggfunc="mean")


def build_avg_pnl_matrix(df: pd.DataFrame) -> pd.DataFrame:
    pnl_col = next((c for c in ["avg_pnl", "ann_return", "total_return"]
                    if c in df.columns), None)
    if not pnl_col:
        return pd.DataFrame()
    return df.pivot_table(index="strategy", columns="symbol",
                          values=pnl_col, aggfunc="mean")


def main():
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    print("=" * 50)
    print("  RAGE Engine -- Master Performance Builder")
    print("=" * 50)

    MASTER_DIR.mkdir(parents=True, exist_ok=True)

    # 1 -- Scan
    print(f"\n[1/6] Scanning {BACKTEST_DIR} ...")
    df = scan_backtest_metrics()

    if df.empty:
        print("\n  [ERROR] No metrics.csv files found.")
        print(f"  Expected location: {BACKTEST_DIR}/<strategy_symbol>/metrics.csv")
        print("\n  Nothing written. Run your backtests first.")
        sys.exit(0)

    rows   = len(df)
    strats = df["strategy"].nunique() if "strategy" in df.columns else 0
    syms   = df["symbol"].nunique()   if "symbol"   in df.columns else 0
    print(f"  Found {rows} metric records -- {strats} strategies x {syms} symbols")

    # 2 -- Full table
    print("\n[2/6] Writing master strategy x symbol table ...")
    df.to_csv(MASTER_STRATEGY_SYMBOL_CSV, index=False)
    print(f"  -> {MASTER_STRATEGY_SYMBOL_CSV}")

    # 3 -- Strategy rank
    print("\n[3/6] Building strategy rank table ...")
    strat_rank = build_strategy_rank(df)
    strat_rank.to_csv(MASTER_STRATEGY_RANK_CSV, index=False)
    print(f"  -> {MASTER_STRATEGY_RANK_CSV}  ({len(strat_rank)} strategies)")
    if not strat_rank.empty and "rank_score" in strat_rank.columns:
        for _, r in strat_rank.head(3).iterrows():
            print(f"     #{int(r['rank'])}  {r['strategy']:<35}  score={r['rank_score']:.1f}")

    # 4 -- Symbol rank
    print("\n[4/6] Building symbol rank table ...")
    sym_rank = build_symbol_rank(df)
    sym_rank.to_csv(MASTER_SYMBOL_RANK_CSV, index=False)
    print(f"  -> {MASTER_SYMBOL_RANK_CSV}  ({len(sym_rank)} symbols)")

    # 5 -- Profit factor matrix
    print("\n[5/6] Building profit factor matrix ...")
    pf_matrix = build_profit_factor_matrix(df)
    if not pf_matrix.empty:
        pf_matrix.to_csv(MASTER_PROFIT_FACTOR_MATRIX)
        print(f"  -> {MASTER_PROFIT_FACTOR_MATRIX}  ({pf_matrix.shape[0]}x{pf_matrix.shape[1]})")
    else:
        print("  [SKIP] No profit_factor column found in metrics files.")

    # 6 -- Avg PnL matrix
    print("\n[6/6] Building avg PnL matrix ...")
    pnl_matrix = build_avg_pnl_matrix(df)
    if not pnl_matrix.empty:
        pnl_matrix.to_csv(MASTER_AVG_PNL_MATRIX)
        print(f"  -> {MASTER_AVG_PNL_MATRIX}  ({pnl_matrix.shape[0]}x{pnl_matrix.shape[1]})")
    else:
        print("  [SKIP] No avg_pnl/ann_return/total_return column found.")

    print("\n" + "=" * 50)
    print("  [OK] Master performance build complete.")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()