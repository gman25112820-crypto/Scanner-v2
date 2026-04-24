from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
MASTER_DIR = OUTPUT_DIR / "master"

MASTER_STRATEGY_SYMBOL_CSV = MASTER_DIR / "master_strategy_symbol_table.csv"
MASTER_STRATEGY_RANK_CSV = MASTER_DIR / "strategy_rank_table.csv"
MASTER_SYMBOL_RANK_CSV = MASTER_DIR / "symbol_rank_table.csv"
MASTER_PROFIT_FACTOR_MATRIX_CSV = MASTER_DIR / "profit_factor_matrix.csv"
MASTER_AVG_PNL_MATRIX_CSV = MASTER_DIR / "avg_pnl_matrix.csv"


def _safe_read_csv(path: Path) -> pd.DataFrame:
    try:
        if path.exists():
            return pd.read_csv(path)
    except Exception:
        pass
    return pd.DataFrame()


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [str(c).strip().lower().replace(" ", "_") for c in out.columns]
    return out


def load_master_strategy_symbol() -> pd.DataFrame:
    df = _safe_read_csv(MASTER_STRATEGY_SYMBOL_CSV)
    return _normalize_columns(df) if not df.empty else pd.DataFrame()


def load_master_strategy_rank() -> pd.DataFrame:
    df = _safe_read_csv(MASTER_STRATEGY_RANK_CSV)
    return _normalize_columns(df) if not df.empty else pd.DataFrame()


def load_master_symbol_rank() -> pd.DataFrame:
    df = _safe_read_csv(MASTER_SYMBOL_RANK_CSV)
    return _normalize_columns(df) if not df.empty else pd.DataFrame()


def load_master_profit_factor_matrix() -> pd.DataFrame:
    df = _safe_read_csv(MASTER_PROFIT_FACTOR_MATRIX_CSV)
    return _normalize_columns(df) if not df.empty else pd.DataFrame()


def load_master_avg_pnl_matrix() -> pd.DataFrame:
    df = _safe_read_csv(MASTER_AVG_PNL_MATRIX_CSV)
    return _normalize_columns(df) if not df.empty else pd.DataFrame()


def classify_rage_status(row: pd.Series) -> str:
    avg_pnl = pd.to_numeric(row.get("avg_pnl"), errors="coerce")
    avg_win = pd.to_numeric(row.get("avg_win_rate"), errors="coerce")
    avg_pf = pd.to_numeric(row.get("avg_profit_factor"), errors="coerce")
    trades = pd.to_numeric(row.get("trades"), errors="coerce")

    if pd.notna(avg_pnl) and pd.notna(avg_win) and pd.notna(avg_pf) and pd.notna(trades):
        if trades >= 10 and avg_pnl > 0 and avg_pf >= 1.0 and avg_win >= 0.45:
            return "DEPLOY"
        if avg_pnl > -0.20:
            return "FIX"
        return "REJECT"
    return "UNKNOWN"


def classify_loser_reason(strategy_name: str) -> str:
    s = str(strategy_name).lower()

    if any(x in s for x in ["london", "session", "overlap", "us_open"]):
        return "Wrong timeframe: intraday/session strategy on daily-style data"
    if "volatility_coil" in s:
        return "Trigger logic too strict or too rare"
    if "trend_continuation" in s:
        return "Continuation entry logic is weak or mistimed"
    if "orb" in s:
        return "Needs true open-session intraday timing"
    if "adx_trend" in s:
        return "Regime-dependent strategy, not broad deployment ready"
    return "Needs logic review and retest"


def classify_loser_action(strategy_name: str) -> str:
    s = str(strategy_name).lower()

    if any(x in s for x in ["london", "session", "overlap", "us_open", "orb"]):
        return "PARK_FOR_INTRADAY"
    if any(x in s for x in ["trend_continuation", "volatility_coil", "adx_trend"]):
        return "FIX_AND_RETEST"
    return "REVIEW"


def _fmt_small(text: str) -> None:
    st.markdown(
        f"<div style='font-size:11px;color:#4d6880;letter-spacing:0.4px'>{text}</div>",
        unsafe_allow_html=True,
    )


def render_rage_control_panel(show_raw: bool = False) -> None:
    st.subheader("RAGE Control Panel")
    _fmt_small("Master strategy intelligence, loser diagnostics, and execution roadmap")

    master_strategy_symbol_df = load_master_strategy_symbol()
    master_strategy_rank_df = load_master_strategy_rank()
    master_symbol_rank_df = load_master_symbol_rank()
    master_pf_matrix_df = load_master_profit_factor_matrix()
    master_avg_pnl_matrix_df = load_master_avg_pnl_matrix()

    if not master_strategy_rank_df.empty:
        master_strategy_rank_df["status"] = master_strategy_rank_df.apply(classify_rage_status, axis=1)
        if "strategy" in master_strategy_rank_df.columns:
            master_strategy_rank_df["loser_reason"] = master_strategy_rank_df["strategy"].apply(classify_loser_reason)
            master_strategy_rank_df["recommended_action"] = master_strategy_rank_df["strategy"].apply(classify_loser_action)

    deploy_count = int((master_strategy_rank_df["status"] == "DEPLOY").sum()) if not master_strategy_rank_df.empty and "status" in master_strategy_rank_df.columns else 0
    fix_count = int((master_strategy_rank_df["status"] == "FIX").sum()) if not master_strategy_rank_df.empty and "status" in master_strategy_rank_df.columns else 0
    reject_count = int((master_strategy_rank_df["status"] == "REJECT").sum()) if not master_strategy_rank_df.empty and "status" in master_strategy_rank_df.columns else 0
    tracked_symbols = int(master_symbol_rank_df["symbol"].nunique()) if not master_symbol_rank_df.empty and "symbol" in master_symbol_rank_df.columns else 0

    top1, top2, top3, top4 = st.columns(4)
    top1.metric("Deploy", deploy_count)
    top2.metric("Fix", fix_count)
    top3.metric("Reject", reject_count)
    top4.metric("Tracked Symbols", tracked_symbols)

    st.markdown("### 🚀 Strategy Leaderboard")
    if not master_strategy_rank_df.empty:
        rank_cols = [
            c for c in [
                "strategy",
                "status",
                "markets",
                "trades",
                "avg_win_rate",
                "avg_pnl",
                "avg_profit_factor",
                "avg_sharpe_like",
                "rank_score",
            ] if c in master_strategy_rank_df.columns
        ]
        display_df = master_strategy_rank_df.sort_values("rank_score", ascending=False) if "rank_score" in master_strategy_rank_df.columns else master_strategy_rank_df
        st.dataframe(display_df[rank_cols], use_container_width=True, hide_index=True)
    else:
        st.warning("No master strategy ranking found. Run: python build_master_performance.py")

    st.markdown("### 📊 Symbol Intelligence")
    if not master_symbol_rank_df.empty:
        sym_cols = [
            c for c in [
                "symbol",
                "strategies",
                "trades",
                "avg_win_rate",
                "avg_pnl",
                "avg_profit_factor",
                "avg_sharpe_like",
                "rank_score",
            ] if c in master_symbol_rank_df.columns
        ]
        display_df = master_symbol_rank_df.sort_values("rank_score", ascending=False) if "rank_score" in master_symbol_rank_df.columns else master_symbol_rank_df
        st.dataframe(display_df[sym_cols], use_container_width=True, hide_index=True)
    else:
        st.info("No symbol ranking data yet.")

    st.markdown("### ⚙️ Strategy Status")
    if not master_strategy_rank_df.empty:
        status_cols = [
            c for c in [
                "strategy",
                "status",
                "avg_pnl",
                "avg_win_rate",
                "avg_profit_factor",
                "rank_score",
            ] if c in master_strategy_rank_df.columns
        ]
        display_df = master_strategy_rank_df.sort_values("rank_score", ascending=False) if "rank_score" in master_strategy_rank_df.columns else master_strategy_rank_df
        st.dataframe(display_df[status_cols], use_container_width=True, hide_index=True)

    st.markdown("### 🔥 Loser Diagnostics")
    if not master_strategy_rank_df.empty and "status" in master_strategy_rank_df.columns:
        losers = master_strategy_rank_df[master_strategy_rank_df["status"] != "DEPLOY"].copy()
        loser_cols = [
            c for c in [
                "strategy",
                "status",
                "avg_pnl",
                "avg_win_rate",
                "avg_profit_factor",
                "avg_sharpe_like",
                "loser_reason",
                "recommended_action",
            ] if c in losers.columns
        ]
        if not losers.empty:
            sort_col = "avg_pnl" if "avg_pnl" in losers.columns else None
            if sort_col:
                losers = losers.sort_values(sort_col, ascending=True)
            st.dataframe(losers[loser_cols], use_container_width=True, hide_index=True)
        else:
            st.success("No non-deploy strategies found.")
    else:
        st.info("No loser diagnostics available yet.")

    st.markdown("### 🧠 Strategy × Symbol Matrix")
    if not master_strategy_symbol_df.empty and "strategy" in master_strategy_symbol_df.columns:
        strategy_options = sorted(master_strategy_symbol_df["strategy"].dropna().astype(str).unique().tolist())
        selected_strategy = st.selectbox("Open strategy drilldown", ["All"] + strategy_options, key="rage_cp_strategy")
        display_df = master_strategy_symbol_df.copy()
        if selected_strategy != "All":
            display_df = display_df[display_df["strategy"].astype(str) == selected_strategy]
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("No master strategy-symbol table found yet.")

    st.markdown("### 📐 Matrix Views")
    left, right = st.columns(2)
    with left:
        st.markdown("#### Profit Factor Matrix")
        if not master_pf_matrix_df.empty:
            st.dataframe(master_pf_matrix_df, use_container_width=True, hide_index=True)
        else:
            st.info("No profit factor matrix found.")
    with right:
        st.markdown("#### Avg PnL Matrix")
        if not master_avg_pnl_matrix_df.empty:
            st.dataframe(master_avg_pnl_matrix_df, use_container_width=True, hide_index=True)
        else:
            st.info("No avg pnl matrix found.")

    st.markdown("### ⚡ Execution Engine v1")
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Max Attempts", "3")
    e2.metric("Risk Model", "0.50 / 1.00 / 0.75")
    e3.metric("Target Model", "1.5R / 2.0R / 2.5R")
    e4.metric("Status", "Prototype")

    st.markdown(
        """
<div style="background:rgba(0,229,255,0.02);border:1px solid rgba(0,229,255,0.08);border-radius:8px;padding:12px">
<b>Execution roadmap</b><br><br>
- Attempt 1 = starter position<br>
- Attempt 2 = better retest entry if structure holds<br>
- Attempt 3 = final reclaim / confirmation attempt<br><br>
This layer is not fully wired into backtesting yet, but it is now visible inside the app.
</div>
        """,
        unsafe_allow_html=True,
    )

    if show_raw:
        st.markdown("### Raw Master Tables")
        st.write("master_strategy_rank_df", master_strategy_rank_df)
        st.write("master_symbol_rank_df", master_symbol_rank_df)
        st.write("master_strategy_symbol_df", master_strategy_symbol_df)
        st.write("master_pf_matrix_df", master_pf_matrix_df)
        st.write("master_avg_pnl_matrix_df", master_avg_pnl_matrix_df)