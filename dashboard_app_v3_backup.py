from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go


# ============================================================
# Scanner v2 Dashboard
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
ALLOCATOR_DIR = OUTPUT_DIR / "allocator"
BACKTEST_DIR = OUTPUT_DIR / "backtest"
JOURNAL_DIR = OUTPUT_DIR / "journal"

STRATEGY_ALLOCATION_CSV = ALLOCATOR_DIR / "strategy_allocation.csv"
STRATEGY_ALLOCATION_JSON = ALLOCATOR_DIR / "strategy_allocation.json"


# ============================================================
# Page setup
# ============================================================

st.set_page_config(
    page_title="Scanner v2 Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .main {
            padding-top: 1rem;
        }
        .block-container {
            padding-top: 1.2rem;
            padding-bottom: 1rem;
        }
        .metric-card {
            background-color: #111827;
            padding: 14px 18px;
            border-radius: 14px;
            border: 1px solid #1f2937;
        }
        .small-muted {
            color: #9ca3af;
            font-size: 0.9rem;
        }
        .section-title {
            margin-top: 0.25rem;
            margin-bottom: 0.75rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# Helpers
# ============================================================

def safe_read_csv(path: Path) -> pd.DataFrame:
    try:
        if path.exists():
            return pd.read_csv(path)
    except Exception:
        pass
    return pd.DataFrame()


def safe_read_json(path: Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def fmt_pct(value, decimals=2):
    try:
        if pd.isna(value):
            return "N/A"
        return f"{float(value):.{decimals}f}%"
    except Exception:
        return "N/A"


def fmt_num(value, decimals=2):
    try:
        if pd.isna(value):
            return "N/A"
        return f"{float(value):.{decimals}f}"
    except Exception:
        return "N/A"


def fmt_int(value):
    try:
        if pd.isna(value):
            return "N/A"
        return f"{int(round(float(value)))}"
    except Exception:
        return "N/A"


def decision_color(decision: str) -> str:
    d = str(decision).upper()
    if d == "DEPLOY":
        return "#10b981"
    if d == "THROTTLE":
        return "#f59e0b"
    if d == "REJECT":
        return "#ef4444"
    return "#6b7280"


def discover_backtest_metrics() -> pd.DataFrame:
    """
    Walks:
        output/backtest/{strategy}_{symbol}/metrics.csv
    And builds a combined dataframe for dashboard analytics.
    """
    if not BACKTEST_DIR.exists():
        return pd.DataFrame()

    records = []

    known = [
        "adx_trend",
        "macd_rsi",
        "mean_reversion",
        "orb",
        "breakout",
        "pullback_trend",
        "rsi2_adx",
        "rsi2adx",
    ]

    def parse_strategy_symbol(folder_name: str):
        folder_lower = folder_name.lower()
        for strategy in known:
            if folder_lower == strategy:
                return strategy, folder_name
            if folder_lower.startswith(strategy + "_"):
                symbol = folder_name[len(strategy) + 1 :]
                return strategy, symbol if symbol else folder_name

        if "_" in folder_name:
            left, right = folder_name.split("_", 1)
            return left.lower(), right

        return folder_name.lower(), folder_name

    for metrics_file in BACKTEST_DIR.rglob("metrics.csv"):
        try:
            folder = metrics_file.parent.name
            strategy, symbol = parse_strategy_symbol(folder)

            df = pd.read_csv(metrics_file)
            df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

            row = {}
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
                numeric_df = df.select_dtypes(include="number")
                if not numeric_df.empty:
                    row = numeric_df.mean().to_dict()

            clean_row = {}
            for k, v in row.items():
                clean_k = str(k).strip().lower().replace(" ", "_")
                clean_row[clean_k] = v

            # Normalize common names
            rename = {
                "sharpe_ratio": "sharpe",
                "sortino_ratio": "sortino",
                "win_rate": "winrate",
                "max_drawdown": "drawdown",
                "num_trades": "trades",
                "total_trades": "trades",
                "annualised_return": "ann_return",
                "annualized_return": "ann_return",
            }

            normalized = {}
            for k, v in clean_row.items():
                normalized[rename.get(k, k)] = v

            normalized["strategy"] = strategy
            normalized["symbol"] = symbol
            normalized["source_file"] = str(metrics_file)

            records.append(normalized)

        except Exception:
            continue

    if not records:
        return pd.DataFrame()

    metrics = pd.DataFrame(records)

    for col in ["sharpe", "sortino", "winrate", "drawdown", "trades", "ann_return", "total_return", "profit_factor"]:
        if col in metrics.columns:
            metrics[col] = pd.to_numeric(metrics[col], errors="coerce")

    if "winrate" in metrics.columns and not metrics["winrate"].dropna().empty:
        if metrics["winrate"].dropna().max() > 1.5:
            metrics["winrate"] = metrics["winrate"] / 100.0

    if "drawdown" in metrics.columns and not metrics["drawdown"].dropna().empty:
        if metrics["drawdown"].dropna().min() > 0:
            metrics["drawdown"] = -metrics["drawdown"]

    return metrics


def load_journal() -> pd.DataFrame:
    """
    Tries a few possible journal file names.
    """
    candidates = [
        JOURNAL_DIR / "trades.csv",
        JOURNAL_DIR / "trade_journal.csv",
        OUTPUT_DIR / "trade_journal.csv",
        OUTPUT_DIR / "trades.csv",
    ]

    for path in candidates:
        df = safe_read_csv(path)
        if not df.empty:
            return df

    return pd.DataFrame()


def load_allocator_table() -> pd.DataFrame:
    df = safe_read_csv(STRATEGY_ALLOCATION_CSV)
    if not df.empty:
        if "decision" in df.columns:
            df["decision"] = df["decision"].astype(str).str.upper()
        for col in ["score", "weight", "risk_per_trade_pct"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    payload = safe_read_json(STRATEGY_ALLOCATION_JSON)
    strategies = payload.get("strategies", [])
    if strategies:
        df = pd.DataFrame(strategies)
        if "decision" in df.columns:
            df["decision"] = df["decision"].astype(str).str.upper()
        for col in ["score", "weight", "risk_per_trade_pct"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    return pd.DataFrame()


def build_status_counts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "decision" not in df.columns:
        return pd.DataFrame({"decision": [], "count": []})
    counts = df["decision"].value_counts().reset_index()
    counts.columns = ["decision", "count"]
    return counts


def create_sample_equity_curve(alloc_df: pd.DataFrame) -> pd.DataFrame:
    """
    Placeholder equity curve when no trade-level equity data exists yet.
    """
    if alloc_df.empty:
        dates = pd.date_range(end=datetime.today(), periods=30, freq="D")
        return pd.DataFrame({"date": dates, "equity": [10000] * len(dates)})

    dates = pd.date_range(end=datetime.today(), periods=60, freq="D")
    equity = []
    current = 10000.0

    deploy_count = int((alloc_df["decision"] == "DEPLOY").sum()) if "decision" in alloc_df.columns else 0
    throttle_count = int((alloc_df["decision"] == "THROTTLE").sum()) if "decision" in alloc_df.columns else 0

    drift = 12 + (deploy_count * 2) - throttle_count

    for i, _ in enumerate(dates):
        current += drift + ((i % 5) - 2) * 3
        equity.append(round(current, 2))

    return pd.DataFrame({"date": dates, "equity": equity})


# ============================================================
# Data loading
# ============================================================

alloc_df = load_allocator_table()
metrics_df = discover_backtest_metrics()
journal_df = load_journal()
status_df = build_status_counts(alloc_df)
equity_df = create_sample_equity_curve(alloc_df)

generated_payload = safe_read_json(STRATEGY_ALLOCATION_JSON)

generated_at = None
if isinstance(generated_payload, dict):
    generated_at = generated_payload.get("generated_at")
    if generated_at is None:
        generated_at = generated_payload.get("generated")

# ============================================================
# Sidebar
# ============================================================

st.sidebar.title("Scanner v2")
st.sidebar.caption("Trader’s Encyclopedia & Strategy Platform")

page = st.sidebar.radio(
    "Navigate",
    [
        "Overview",
        "Allocator",
        "Backtests",
        "Journal",
        "Platform Vision",
    ],
)

st.sidebar.markdown("---")
show_raw = st.sidebar.checkbox("Show raw tables", value=False)

if generated_at:
    st.sidebar.markdown(f"**Last allocation run**  \n`{generated_at}`")

st.sidebar.markdown("---")
st.sidebar.write("**Detected files**")
st.sidebar.write(f"Allocator CSV: {'[OK]' if STRATEGY_ALLOCATION_CSV.exists() else '[ERROR]'}")
st.sidebar.write(f"Allocator JSON: {'[OK]' if STRATEGY_ALLOCATION_JSON.exists() else '[ERROR]'}")
st.sidebar.write(f"Backtest folder: {'[OK]' if BACKTEST_DIR.exists() else '[ERROR]'}")
st.sidebar.write(f"Journal folder: {'[OK]' if JOURNAL_DIR.exists() else '[ERROR]'}")


# ============================================================
# Header
# ============================================================

st.title("📈 Scanner v2 Dashboard")
st.caption("Live scanner foundation, backtesting intelligence, allocator control, and trading platform vision.")


# ============================================================
# Overview page
# ============================================================

if page == "Overview":
    deploy_count = int((alloc_df["decision"] == "DEPLOY").sum()) if not alloc_df.empty and "decision" in alloc_df.columns else 0
    throttle_count = int((alloc_df["decision"] == "THROTTLE").sum()) if not alloc_df.empty and "decision" in alloc_df.columns else 0
    reject_count = int((alloc_df["decision"] == "REJECT").sum()) if not alloc_df.empty and "decision" in alloc_df.columns else 0

    total_weight = float(alloc_df["weight"].fillna(0).sum()) if not alloc_df.empty and "weight" in alloc_df.columns else 0.0
    avg_risk = float(alloc_df["risk_per_trade_pct"].fillna(0).mean()) if not alloc_df.empty and "risk_per_trade_pct" in alloc_df.columns else 0.0
    strategies_seen = int(metrics_df["strategy"].nunique()) if not metrics_df.empty and "strategy" in metrics_df.columns else 0
    symbols_seen = int(metrics_df["symbol"].nunique()) if not metrics_df.empty and "symbol" in metrics_df.columns else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("DEPLOY", deploy_count)
    c2.metric("THROTTLE", throttle_count)
    c3.metric("REJECT", reject_count)
    c4.metric("Strategy Weight", f"{total_weight:.2f}")
    c5.metric("Avg Risk/Trade", f"{avg_risk:.2f}%")

    c6, c7 = st.columns(2)
    c6.metric("Strategies Found", strategies_seen)
    c7.metric("Symbols Found", symbols_seen)

    st.markdown("### Allocation Snapshot")
    if not alloc_df.empty:
        left, right = st.columns([1.2, 1])

        with left:
            chart_df = alloc_df.copy()
            chart_df["strategy"] = chart_df["strategy"].astype(str)
            chart_df["color"] = chart_df["decision"].apply(decision_color)

            fig = px.bar(
                chart_df,
                x="strategy",
                y="weight",
                color="decision",
                text="weight",
                title="Strategy Allocation Weight",
            )
            fig.update_traces(texttemplate="%{text:.2f}", textposition="outside")
            fig.update_layout(height=420)
            st.plotly_chart(fig, use_container_width=True)

        with right:
            pie_df = alloc_df[alloc_df["weight"].fillna(0) > 0].copy()
            if pie_df.empty:
                st.info("No non-zero strategy weights yet.")
            else:
                fig2 = px.pie(
                    pie_df,
                    values="weight",
                    names="strategy",
                    title="Allocated Capital Split",
                    hole=0.45,
                )
                fig2.update_layout(height=420)
                st.plotly_chart(fig2, use_container_width=True)
    else:
        st.warning("No allocator output found yet. Run: python main.py --mode allocate")

    st.markdown("### Equity View")
    fig_eq = px.line(
        equity_df,
        x="date",
        y="equity",
        title="Portfolio Equity Curve (starter dashboard view)",
    )
    fig_eq.update_layout(height=380)
    st.plotly_chart(fig_eq, use_container_width=True)

    st.markdown("### Current Strategy Decisions")
    if not alloc_df.empty:
        display_df = alloc_df.copy()
        if "weight" in display_df.columns:
            display_df["weight"] = display_df["weight"].map(lambda x: round(float(x), 6) if pd.notna(x) else x)
        if "risk_per_trade_pct" in display_df.columns:
            display_df["risk_per_trade_pct"] = display_df["risk_per_trade_pct"].map(lambda x: round(float(x), 2) if pd.notna(x) else x)
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("No strategy allocation table available yet.")

    if show_raw:
        st.markdown("### Raw allocator table")
        st.write(alloc_df)


# ============================================================
# Allocator page
# ============================================================

elif page == "Allocator":
    st.subheader("Allocator Control Panel")

    if alloc_df.empty:
        st.warning("No allocator data found. Run the allocator first with: python main.py --mode allocate")
    else:
        top_left, top_right = st.columns([1.25, 1])

        with top_left:
            styled = alloc_df.copy()
            st.dataframe(styled, use_container_width=True, hide_index=True)

        with top_right:
            if not status_df.empty:
                fig_status = px.bar(
                    status_df,
                    x="decision",
                    y="count",
                    color="decision",
                    title="Decision Breakdown",
                    text="count",
                )
                fig_status.update_traces(textposition="outside")
                fig_status.update_layout(height=380)
                st.plotly_chart(fig_status, use_container_width=True)

        bottom_left, bottom_right = st.columns(2)

        with bottom_left:
            alloc_nonzero = alloc_df[alloc_df["weight"].fillna(0) > 0].copy()
            if not alloc_nonzero.empty:
                fig_alloc = px.bar(
                    alloc_nonzero,
                    x="strategy",
                    y="risk_per_trade_pct",
                    color="decision",
                    text="risk_per_trade_pct",
                    title="Live Risk Per Trade (%)",
                )
                fig_alloc.update_traces(texttemplate="%{text:.2f}", textposition="outside")
                fig_alloc.update_layout(height=380)
                st.plotly_chart(fig_alloc, use_container_width=True)
            else:
                st.info("No active deployment risk values available.")

        with bottom_right:
            alloc_nonzero = alloc_df[alloc_df["weight"].fillna(0) > 0].copy()
            if not alloc_nonzero.empty:
                fig_weight = px.bar(
                    alloc_nonzero,
                    x="strategy",
                    y="weight",
                    color="decision",
                    text="weight",
                    title="Normalized Strategy Weights",
                )
                fig_weight.update_traces(texttemplate="%{text:.4f}", textposition="outside")
                fig_weight.update_layout(height=380)
                st.plotly_chart(fig_weight, use_container_width=True)
            else:
                st.info("No live allocation weights available.")

        st.markdown("### Allocation Commentary")
        deploy_df = alloc_df[alloc_df["decision"] == "DEPLOY"].copy()
        reject_df = alloc_df[alloc_df["decision"] == "REJECT"].copy()

        if not deploy_df.empty:
            deploy_names = ", ".join(deploy_df["strategy"].astype(str).tolist())
            st.success(f"Deploy-ready strategies: {deploy_names}")
        else:
            st.warning("No strategies are currently marked DEPLOY.")

        if not reject_df.empty:
            reject_names = ", ".join(reject_df["strategy"].astype(str).tolist())
            st.error(f"Strategies kept off live: {reject_names}")

        st.markdown(
            """
            **Live interpretation**
            - DEPLOY = allowed for live capital
            - THROTTLE = reduced confidence / reduced live size
            - REJECT = keep off live
            - Risk-per-trade should stay hard-capped before broker execution
            """
        )

    if show_raw:
        st.markdown("### Raw status table")
        st.write(status_df)


# ============================================================
# Backtests page
# ============================================================

elif page == "Backtests":
    st.subheader("Backtest Analytics")

    if metrics_df.empty:
        st.warning("No backtest metrics found in output/backtest/")
    else:
        metrics_display = metrics_df.copy()

        strategy_filter = st.multiselect(
            "Filter strategies",
            sorted(metrics_display["strategy"].dropna().astype(str).unique().tolist()),
            default=sorted(metrics_display["strategy"].dropna().astype(str).unique().tolist()),
        )

        if strategy_filter:
            metrics_display = metrics_display[metrics_display["strategy"].astype(str).isin(strategy_filter)]

        top1, top2 = st.columns(2)

        with top1:
            if "sharpe" in metrics_display.columns:
                fig_sharpe = px.box(
                    metrics_display,
                    x="strategy",
                    y="sharpe",
                    color="strategy",
                    title="Sharpe Distribution by Strategy",
                )
                fig_sharpe.update_layout(height=400, showlegend=False)
                st.plotly_chart(fig_sharpe, use_container_width=True)

        with top2:
            if "winrate" in metrics_display.columns:
                win_df = metrics_display.copy()
                win_df["winrate_pct"] = win_df["winrate"] * 100.0
                fig_win = px.box(
                    win_df,
                    x="strategy",
                    y="winrate_pct",
                    color="strategy",
                    title="Win Rate Distribution by Strategy",
                )
                fig_win.update_layout(height=400, showlegend=False)
                st.plotly_chart(fig_win, use_container_width=True)

        mid1, mid2 = st.columns(2)

        with mid1:
            if "drawdown" in metrics_display.columns:
                dd_df = metrics_display.copy()
                dd_df["drawdown_pct"] = dd_df["drawdown"] * 100.0
                fig_dd = px.bar(
                    dd_df.groupby("strategy", as_index=False)["drawdown_pct"].mean(),
                    x="strategy",
                    y="drawdown_pct",
                    color="strategy",
                    title="Average Max Drawdown (%)",
                    text="drawdown_pct",
                )
                fig_dd.update_traces(texttemplate="%{text:.2f}", textposition="outside")
                fig_dd.update_layout(height=400, showlegend=False)
                st.plotly_chart(fig_dd, use_container_width=True)

        with mid2:
            if "trades" in metrics_display.columns:
                fig_trades = px.bar(
                    metrics_display.groupby("strategy", as_index=False)["trades"].mean(),
                    x="strategy",
                    y="trades",
                    color="strategy",
                    title="Average Trades per Strategy",
                    text="trades",
                )
                fig_trades.update_traces(texttemplate="%{text:.0f}", textposition="outside")
                fig_trades.update_layout(height=400, showlegend=False)
                st.plotly_chart(fig_trades, use_container_width=True)

        st.markdown("### Strategy Summary Table")
        summary_cols = [c for c in ["strategy", "symbol", "sharpe", "sortino", "winrate", "drawdown", "trades", "profit_factor"] if c in metrics_display.columns]
        st.dataframe(metrics_display[summary_cols], use_container_width=True, hide_index=True)

    if show_raw:
        st.markdown("### Raw backtest metrics")
        st.write(metrics_df)


# ============================================================
# Journal page
# ============================================================

elif page == "Journal":
    st.subheader("Trade Journal")

    if journal_df.empty:
        st.info(
            "No journal file found yet. Supported starter files include:\n"
            "- output/journal/trades.csv\n"
            "- output/journal/trade_journal.csv\n"
            "- output/trades.csv\n"
            "- output/trade_journal.csv"
        )
    else:
        journal = journal_df.copy()
        journal.columns = [str(c).strip().lower().replace(" ", "_") for c in journal.columns]

        st.dataframe(journal, use_container_width=True, hide_index=True)

        if "pnl" in journal.columns:
            journal["pnl"] = pd.to_numeric(journal["pnl"], errors="coerce").fillna(0.0)
            c1, c2, c3 = st.columns(3)
            c1.metric("Total P&L", fmt_num(journal["pnl"].sum()))
            c2.metric("Avg Trade P&L", fmt_num(journal["pnl"].mean()))
            c3.metric("Trades", fmt_int(len(journal)))

            fig_pnl = px.bar(
                journal.reset_index().rename(columns={"index": "trade_no"}),
                x="trade_no",
                y="pnl",
                title="Trade-by-Trade P&L",
            )
            fig_pnl.update_layout(height=420)
            st.plotly_chart(fig_pnl, use_container_width=True)

        if "strategy" in journal.columns and "pnl" in journal.columns:
            strat_pnl = journal.groupby("strategy", as_index=False)["pnl"].sum()
            fig_strat = px.bar(
                strat_pnl,
                x="strategy",
                y="pnl",
                color="strategy",
                title="P&L by Strategy",
                text="pnl",
            )
            fig_strat.update_traces(texttemplate="%{text:.2f}", textposition="outside")
            fig_strat.update_layout(height=420, showlegend=False)
            st.plotly_chart(fig_strat, use_container_width=True)

    if show_raw:
        st.markdown("### Raw journal")
        st.write(journal_df)


# ============================================================
# Platform Vision page
# ============================================================

elif page == "Platform Vision":
    st.subheader("What Scanner v2 Can Become")

    st.markdown(
        """
        ### Current state
        - Scanner/backtest/allocation engine is running
        - Allocator output is already being generated
        - Backtest metrics are available from `output/backtest/`
        - Visual dashboard is now started with this file

        ### Next visual upgrades
        - live scanner table with entry/stop/target
        - broker execution panel
        - portfolio holdings page
        - equity and drawdown analytics
        - journal review workspace
        - strategy encyclopedia pages
        """
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Core modules")
        st.markdown(
            """
            - **Scanner**
            - **Backtester**
            - **Allocator**
            - **Journal**
            - **Portfolio**
            - **Education Hub**
            """
        )

    with col2:
        st.markdown("### Best first graphics")
        st.markdown(
            """
            - KPI cards
            - allocation bar chart
            - deploy / throttle / reject tags
            - equity curve
            - drawdown chart
            - trade log table
            - strategy performance comparison
            """
        )

    mock_alloc = alloc_df.copy()
    if mock_alloc.empty:
        mock_alloc = pd.DataFrame(
            {
                "strategy": ["mean_reversion", "macd_rsi", "adx_trend", "orb"],
                "decision": ["DEPLOY", "DEPLOY", "REJECT", "REJECT"],
                "weight": [0.56, 0.44, 0.0, 0.0],
                "risk_per_trade_pct": [2.0, 1.0, 0.0, 0.0],
            }
        )

    st.markdown("### Example allocator look")
    fig_mock = px.bar(
        mock_alloc,
        x="strategy",
        y="risk_per_trade_pct",
        color="decision",
        text="risk_per_trade_pct",
        title="Broker-Facing Risk Allocation View",
    )
    fig_mock.update_traces(texttemplate="%{text:.2f}", textposition="outside")
    fig_mock.update_layout(height=420)
    st.plotly_chart(fig_mock, use_container_width=True)

    st.markdown("### Design direction")
    st.markdown(
        """
        Think of the platform as a clean professional terminal:
        - dark mode
        - strong green/amber/red decision tags
        - large headline KPIs
        - clean table layouts
        - simple charts with low clutter
        - expandable strategy pages later
        """
    )