from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from datetime import datetime, date
from typing import Any

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# ── Load .env ────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── RAGE V4 module imports (graceful — won't crash if not yet installed) ─────
try:
    from broker_alpaca import AlpacaBroker, render_broker_panel
    BROKER_AVAILABLE = True
except ImportError:
    BROKER_AVAILABLE = False

try:
    from trade_journal import TradeJournal
    JOURNAL_V2_AVAILABLE = True
except ImportError:
    JOURNAL_V2_AVAILABLE = False

try:
    from performance_dashboard import render_performance_page
    PERF_DASHBOARD_AVAILABLE = True
except ImportError:
    PERF_DASHBOARD_AVAILABLE = False

try:
    from portfolio_heat import PortfolioHeat
    PORTFOLIO_HEAT_AVAILABLE = True
except ImportError:
    PORTFOLIO_HEAT_AVAILABLE = False

try:
    from monte_carlo import MonteCarlo
    MONTE_CARLO_AVAILABLE = True
except ImportError:
    MONTE_CARLO_AVAILABLE = False

try:
    from rage_signal_bridge import fix_final_score, candidate_to_rage
    BRIDGE_AVAILABLE = True
except ImportError:
    BRIDGE_AVAILABLE = False


# ============================================================
# RAGE ENGINE - Quotes & Welcome
# ============================================================
import datetime as _datetime

RAGE_QUOTES = [
    ("The stock market is a device for transferring money from the impatient to the patient.", "Warren Buffett"),
    ("In investing, what is comfortable is rarely profitable.", "Robert Arnott"),
    ("Risk comes from not knowing what you are doing.", "Warren Buffett"),
    ("The four most dangerous words in investing are: This time it is different.", "Sir John Templeton"),
    ("Wide diversification is only required when investors do not understand what they are doing.", "Warren Buffett"),
    ("The market is filled with individuals who know the price of everything, but the value of nothing.", "Philip Fisher"),
    ("It is not the strongest of the species that survives, but the most adaptable.", "Charles Darwin"),
    ("Be fearful when others are greedy, and greedy when others are fearful.", "Warren Buffett"),
    ("The goal of a successful trader is to make the best trades. Money is secondary.", "Alexander Elder"),
    ("In trading, the money you lose is tuition. The money you make is profit.", "Unknown"),
    ("Markets can remain irrational longer than you can remain solvent.", "John Maynard Keynes"),
    ("The trend is your friend until the end when it bends.", "Ed Seykota"),
    ("Cut your losses and let your profits run.", "David Ricardo"),
    ("Plan the trade and trade the plan.", "Unknown"),
    ("Success in investing does not correlate with IQ. What you need is the temperament to control urges.", "Warren Buffett"),
]


def get_daily_quote():
    idx = _datetime.date.today().toordinal() % len(RAGE_QUOTES)
    return RAGE_QUOTES[idx]


def get_welcome_message():
    hour = _datetime.datetime.now().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"
    return greeting


# ============================================================
# RAGE Engine — Dashboard V4
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

ALLOCATOR_DIR = OUTPUT_DIR / "allocator"
BACKTEST_DIR = OUTPUT_DIR / "backtest"
JOURNAL_DIR = OUTPUT_DIR / "journal"
REPORTS_DIR = OUTPUT_DIR / "reports"
UPLOADS_DIR = OUTPUT_DIR / "uploads"
PLANNER_DIR = OUTPUT_DIR / "planner"
NOTES_DIR = OUTPUT_DIR / "notes"
CALENDAR_DIR = OUTPUT_DIR / "calendar"
STRATEGIES_DIR = OUTPUT_DIR / "strategies"
SOCIAL_DIR = OUTPUT_DIR / "social"
MARKETS_DIR = OUTPUT_DIR / "markets"
INTEL_DIR = OUTPUT_DIR / "market_intel"
MASTER_DIR = OUTPUT_DIR / "master"

STRATEGY_ALLOCATION_CSV = ALLOCATOR_DIR / "strategy_allocation.csv"
STRATEGY_ALLOCATION_JSON = ALLOCATOR_DIR / "strategy_allocation.json"
TRADE_RESULTS_CSV = OUTPUT_DIR / "trade_results.csv"
SIGNALS_CSV = OUTPUT_DIR / "signals.csv"
WATCHLIST_CSV = OUTPUT_DIR / "watchlist.csv"
ALERTS_CSV = OUTPUT_DIR / "alerts.csv"
LEADERBOARD_CSV = OUTPUT_DIR / "leaderboard.csv"
MARKET_INTEL_JSON = INTEL_DIR / "report.json"

STRATEGIES_JSON = STRATEGIES_DIR / "builder_strategies.json"
NOTES_JSON = NOTES_DIR / "notes.json"
PLANNER_JSON = PLANNER_DIR / "daily_planner.json"
CALENDAR_CSV = CALENDAR_DIR / "events.csv"
SOCIAL_X_CSV = SOCIAL_DIR / "x_reports.csv"
SOCIAL_REDDIT_CSV = SOCIAL_DIR / "reddit_reports.csv"
MARKET_OVERVIEW_CSV = MARKETS_DIR / "market_overview.csv"

MASTER_STRATEGY_SYMBOL_CSV = MASTER_DIR / "master_strategy_symbol_table.csv"
MASTER_STRATEGY_RANK_CSV = MASTER_DIR / "strategy_rank_table.csv"
MASTER_SYMBOL_RANK_CSV = MASTER_DIR / "symbol_rank_table.csv"
MASTER_PROFIT_FACTOR_MATRIX = MASTER_DIR / "profit_factor_matrix.csv"
MASTER_AVG_PNL_MATRIX = MASTER_DIR / "avg_pnl_matrix.csv"

REPORT_SUBDIRS = [
    REPORTS_DIR / sub
    for sub in ["daily", "weekly", "social", "x_reports", "reddit_reports", "macro", "earnings", "strategy_reviews"]
]
UPLOAD_SUBDIRS = [UPLOADS_DIR / s for s in ["market_images", "trade_images", "annotated_charts"]]
NOTE_SUBDIRS = [NOTES_DIR / s for s in ["strategy_notes", "market_notes", "psychology_notes", "weekly_reviews"]]
PLANNER_SUBDIRS = [PLANNER_DIR / "daily"]

for p in [
    OUTPUT_DIR,
    ALLOCATOR_DIR,
    BACKTEST_DIR,
    JOURNAL_DIR,
    REPORTS_DIR,
    UPLOADS_DIR,
    PLANNER_DIR,
    NOTES_DIR,
    CALENDAR_DIR,
    STRATEGIES_DIR,
    SOCIAL_DIR,
    MARKETS_DIR,
    INTEL_DIR,
    MASTER_DIR,
]:
    p.mkdir(parents=True, exist_ok=True)

for p in REPORT_SUBDIRS + UPLOAD_SUBDIRS + NOTE_SUBDIRS + PLANNER_SUBDIRS:
    p.mkdir(parents=True, exist_ok=True)


# ============================================================
# Password protection
# ============================================================

RAGE_PASSWORD = os.getenv("RAGE_PASSWORD", "RAGE2024")

def check_password() -> bool:
    if st.session_state.get("authenticated"):
        return True
    st.markdown("""
    <div style="display:flex;justify-content:center;align-items:center;height:60vh;">
    <div style="background:#0b1628;border:1px solid rgba(0,229,255,0.15);border-radius:16px;
                padding:40px 48px;text-align:center;max-width:400px;width:100%">
        <div style="font-family:'Syne',sans-serif;font-weight:800;font-size:28px;
                    background:linear-gradient(90deg,#ff4500,#ff8c00);
                    -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                    margin-bottom:6px">RAGE ENGINE</div>
        <div style="font-size:11px;color:#4d6880;letter-spacing:2px;margin-bottom:28px">
            ROB AND GARETH ENGINE · V4</div>
    </div></div>
    """, unsafe_allow_html=True)
    pwd = st.text_input("Password", type="password", label_visibility="collapsed",
                        placeholder="Enter password")
    if st.button("Enter", use_container_width=True):
        if pwd == RAGE_PASSWORD:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password")
    return False


# ============================================================
# Page config
# ============================================================

st.set_page_config(
    page_title="RAGE Engine — V4",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

if not check_password():
    st.stop()

# ── Broker session state ──────────────────────────────────────────────────────
if "broker" not in st.session_state:
    st.session_state["broker"] = None
if "broker_connected" not in st.session_state:
    st.session_state["broker_connected"] = False

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Syne:wght@400;600;700;800&display=swap');

.stApp {
    background: radial-gradient(ellipse at top left, #0a1628 0%, #050912 60%, #030710 100%);
    color: #e5e7eb;
    font-family: 'JetBrains Mono', monospace;
}
section[data-testid="stSidebar"] {
    background: #070e1a;
    border-right: 1px solid rgba(0,229,255,0.08);
}
.block-container {
    padding-top: 0.75rem;
    padding-bottom: 1rem;
}
h1, h2, h3, h4 {
    color: #e5e7eb;
    font-family: 'Syne', sans-serif;
}
div[data-testid="stMetric"] {
    background: linear-gradient(145deg, #0b1628, #060e1c);
    border: 1px solid rgba(0,229,255,0.1);
    padding: 14px;
    border-radius: 10px;
    box-shadow: 0 0 20px rgba(0,229,255,0.04), inset 0 1px 0 rgba(255,255,255,0.03);
}
div[data-testid="stMetric"] label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: #4d6880;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-family: 'Syne', sans-serif;
    font-weight: 700;
    font-size: 22px;
    color: #e5e7eb;
}
.stDataFrame, div[data-testid="stTable"] {
    border-radius: 8px;
    overflow: hidden;
}
.stButton > button {
    background: linear-gradient(135deg, #00c8a0, #00b4d8);
    border: none;
    border-radius: 6px;
    color: #050912;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 1px;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #00e5c0, #00d0f5);
    transform: translateY(-1px);
}
.stDownloadButton > button {
    background: linear-gradient(135deg, #1d4ed8, #06b6d4);
    border: none;
    border-radius: 6px;
    color: white;
    font-family: 'JetBrains Mono', monospace;
}
div[data-baseweb="select"] > div {
    background-color: rgba(0,229,255,0.03);
    border-color: rgba(0,229,255,0.1);
}
div[data-testid="stTextInput"] input,
div[data-testid="stTextArea"] textarea,
div[data-testid="stDateInput"] input {
    background-color: rgba(0,229,255,0.03);
    border-color: rgba(0,229,255,0.1);
    color: #e5e7eb;
    font-family: 'JetBrains Mono', monospace;
}
.small-muted { color: #4d6880; font-size: 0.85rem; font-family: 'JetBrains Mono', monospace; }
.glass {
    background: rgba(0,229,255,0.02);
    border: 1px solid rgba(0,229,255,0.07);
    border-radius: 10px;
    padding: 14px;
}
.ticker-wrap {
    overflow: hidden;
    background: rgba(0,229,255,0.03);
    border: 1px solid rgba(0,229,255,0.08);
    border-radius: 8px;
    padding: 6px 0;
    margin-bottom: 12px;
}
.ticker-inner {
    display: inline-flex;
    gap: 36px;
    animation: ticker-scroll 60s linear infinite;
    white-space: nowrap;
}
.ticker-inner:hover { animation-play-state: paused; }
@keyframes ticker-scroll {
    0%   { transform: translateX(0); }
    100% { transform: translateX(-50%); }
}
.t-item { display: inline-flex; align-items: center; gap: 7px; font-size: 11px; padding: 0 4px; }
.t-label { color: #4d6880; font-size: 9px; letter-spacing: 1.2px; text-transform: uppercase; }
.t-price { color: #e5e7eb; font-weight: 600; }
.t-up   { color: #00e676; font-size: 10px; }
.t-down { color: #ff3d57; font-size: 10px; }
.t-flat { color: #4d6880; font-size: 10px; }
.badge {
    display: inline-block;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 1.5px;
    padding: 2px 8px;
    border-radius: 3px;
}
.badge-deploy   { background: rgba(0,230,118,0.15); color: #00e676; border: 1px solid #00e676; }
.badge-throttle { background: rgba(255,179,0,0.15);  color: #ffb300; border: 1px solid #ffb300; }
.badge-reject   { background: rgba(255,61,87,0.15);  color: #ff3d57; border: 1px solid #ff3d57; }
.intel-card {
    background: rgba(0,229,255,0.02);
    border: 1px solid rgba(0,229,255,0.09);
    border-radius: 8px;
    padding: 12px 14px;
    margin-bottom: 8px;
    transition: border-color 0.2s;
}
.intel-card:hover { border-color: rgba(0,229,255,0.22); }
.intel-card .sym  { font-family: 'Syne', sans-serif; font-weight: 700; font-size: 15px; color: #e5e7eb; }
.intel-card .name { font-size: 10px; color: #4d6880; margin-top: 1px; letter-spacing: 0.3px; }
.intel-price { font-size: 18px; font-weight: 600; font-family: 'Syne', sans-serif; color: #e5e7eb; }
.sector-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 4px; }
.sc { border-radius: 6px; padding: 9px 10px; text-align: center; flex: 1; min-width: 90px; }
.sc-label { font-size: 9px; letter-spacing: 0.8px; text-transform: uppercase; color: rgba(255,255,255,0.6); margin-bottom: 3px; }
.sc-pct   { font-size: 14px; font-weight: 700; font-family: 'Syne', sans-serif; }
.sc-etf   { font-size: 9px; color: rgba(255,255,255,0.35); margin-top: 2px; }
.news-item {
    display: flex; gap: 10px; align-items: flex-start;
    padding: 9px 12px;
    background: rgba(0,229,255,0.02);
    border: 1px solid rgba(0,229,255,0.07);
    border-radius: 6px;
    margin-bottom: 6px;
    transition: border-color 0.15s;
}
.news-item:hover { border-color: rgba(0,229,255,0.18); }
.news-src  { font-size: 9px; font-weight: 700; letter-spacing: 1.5px; color: #00e5ff; min-width: 56px; padding-top: 2px; }
.news-hl   { font-size: 11px; color: #c5d5e5; line-height: 1.45; }
.news-meta { font-size: 10px; color: #4d6880; margin-top: 2px; }
.pill { display:inline-block; font-size:9px; font-weight:700; padding:1px 7px; border-radius:10px; }
.pill-bull { background:rgba(0,230,118,0.12); color:#00e676; border:1px solid #00e676; }
.pill-bear { background:rgba(255,61,87,0.12);  color:#ff3d57; border:1px solid #ff3d57; }
.pill-neut { background:rgba(77,104,128,0.2);  color:#8ba8c4; border:1px solid #4d6880; }
.live-dot {
    display: inline-block;
    width: 7px; height: 7px;
    border-radius: 50%;
    background: #00e676;
    box-shadow: 0 0 8px #00e676;
    animation: blink 2s ease infinite;
    margin-right: 5px;
}
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: #030710; }
::-webkit-scrollbar-thumb { background: #1e2d3d; border-radius: 3px; }
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


def safe_read_json(path: Path, default: Any = None) -> Any:
    if default is None:
        default = {}
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def safe_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def append_row_csv(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df_new = pd.DataFrame([row])
    if path.exists():
        df_old = safe_read_csv(path)
        df = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df = df_new
    df.to_csv(path, index=False)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def fmt_num(v, decimals=2):
    try:
        if pd.isna(v):
            return "N/A"
        return f"{float(v):.{decimals}f}"
    except Exception:
        return "N/A"


def fmt_pct(v, decimals=2):
    try:
        if pd.isna(v):
            return "N/A"
        return f"{float(v):.{decimals}f}%"
    except Exception:
        return "N/A"


def fmt_int(v):
    try:
        if pd.isna(v):
            return "N/A"
        return str(int(round(float(v))))
    except Exception:
        return "N/A"


def highlight_decision(val):
    v = str(val).upper()
    if v == "DEPLOY":
        return "color:#00e676;font-weight:bold;"
    if v == "THROTTLE":
        return "color:#ffb300;font-weight:bold;"
    if v == "REJECT":
        return "color:#ff3d57;font-weight:bold;"
    return ""


def apply_dark_plot(fig):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e5e7eb", family="JetBrains Mono, monospace"),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    return fig


def parse_strategy_symbol(folder_name: str):
    known = [
        "adx_trend",
        "macd_rsi",
        "mean_reversion",
        "orb",
        "breakout",
        "pullback_trend",
        "rsi2_adx",
        "rsi2adx",
        "mtf_momentum_binary",
        "mtf_trend_continuation",
        "mtf_trend_continuation_v2",
        "mtf_session_sniper",
        "mtf_ny_overlap_hunter",
        "mtf_fx_london_breakout",
        "mtf_us_open_momentum",
        "mtf_volatility_coil",
        "mtf_volatility_coil_v2",
    ]
    fl = folder_name.lower()
    for s in sorted(known, key=len, reverse=True):
        if fl == s:
            return s, folder_name
        if fl.startswith(s + "_"):
            sym = folder_name[len(s) + 1 :]
            return s, sym if sym else folder_name
    if "_" in folder_name:
        l, r = folder_name.split("_", 1)
        return l.lower(), r
    return folder_name.lower(), folder_name


def list_files_recursive(folder: Path, extensions=None) -> list[Path]:
    if not folder.exists():
        return []
    paths = []
    for p in sorted(folder.rglob("*")):
        if p.is_file():
            if extensions is None or p.suffix.lower() in extensions:
                paths.append(p)
    return paths


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def save_uploaded_file(uploaded_file, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / uploaded_file.name
    with open(target_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return target_path


# ============================================================
# Market intel helpers
# ============================================================

def fmt_price(v):
    if v is None:
        return "—"
    try:
        f = float(v)
        if f >= 1000:
            return f"{f:,.2f}"
        return f"{f:.2f}"
    except Exception:
        return "—"


def fmt_mcap(v):
    if not v:
        return "—"
    try:
        v = float(v)
        if v >= 1e12:
            return f"${v/1e12:.2f}T"
        if v >= 1e9:
            return f"${v/1e9:.1f}B"
        if v >= 1e6:
            return f"${v/1e6:.0f}M"
        return f"${v:.0f}"
    except Exception:
        return "—"


def fmt_chg(v):
    if v is None:
        return "—"
    try:
        f = float(v)
        return f"+{f:.2f}%" if f >= 0 else f"{f:.2f}%"
    except Exception:
        return "—"


def chg_color(v):
    if v is None:
        return "#4d6880"
    try:
        return "#00e676" if float(v) >= 0 else "#ff3d57"
    except Exception:
        return "#4d6880"


@st.cache_data(ttl=300)
def load_market_intel() -> dict:
    return safe_read_json(MARKET_INTEL_JSON, default={})


def run_market_intel_fetch():
    try:
        from market_intel import get_full_market_report

        with st.spinner("Fetching live market data from Yahoo Finance..."):
            report = get_full_market_report()
        st.cache_data.clear()
        return report
    except ImportError:
        st.error("market_intel.py not found in scanner root. Drop it in and try again.")
        return {}
    except Exception as e:
        st.error(f"Market intel fetch failed: {e}")
        return {}


def render_ticker_tape(overview: dict):
    if not overview:
        return
    items_html = ""
    for label, d in overview.items():
        price = fmt_price(d.get("price"))
        pct = d.get("pct_change")
        c = "t-up" if (pct or 0) >= 0 else "t-down"
        items_html += f"""<span class="t-item">
            <span class="t-label">{label}</span>
            <span class="t-price">{price}</span>
            <span class="{c}">{fmt_chg(pct)}</span>
        </span>"""
    inner = items_html + items_html
    st.markdown(
        f"""
    <div class="ticker-wrap">
      <div class="ticker-inner">{inner}</div>
    </div>
    """,
        unsafe_allow_html=True,
    )


def render_sector_heatmap(sectors: list):
    if not sectors:
        st.info("No sector data. Click 'Fetch Live Data' to load.")
        return
    max_abs = max((abs(s.get("pct_change") or 0) for s in sectors), default=1) or 1
    html = '<div class="sector-row">'
    for s in sectors:
        pct = s.get("pct_change") or 0
        etf = s.get("etf", "")
        name = s.get("sector", "")
        intensity = abs(pct) / max_abs
        if pct > 0:
            g = int(80 + intensity * 120)
            bg = f"rgba(0,{g},80,{0.12 + intensity*0.38})"
        elif pct < 0:
            r = int(140 + intensity * 115)
            bg = f"rgba({r},30,50,{0.12 + intensity*0.38})"
        else:
            bg = "rgba(0,229,255,0.04)"
        col = "#00e676" if pct >= 0 else "#ff3d57"
        html += f"""<div class="sc" style="background:{bg}">
            <div class="sc-label">{name}</div>
            <div class="sc-pct" style="color:{col}">{fmt_chg(pct)}</div>
            <div class="sc-etf">{etf}</div>
        </div>"""
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def render_mover_row(m: dict, color: str):
    sym = m.get("symbol", "")
    price = fmt_price(m.get("price"))
    pct = fmt_chg(m.get("pct_change"))
    st.markdown(
        f"""
    <div class="intel-card" style="border-left:3px solid {color};padding:8px 12px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <span class="sym" style="font-family:'Syne',sans-serif;font-weight:700;font-size:14px;color:#e5e7eb">{sym}</span>
          <span style="font-size:11px;color:#4d6880;margin-left:8px">{price}</span>
        </div>
        <span style="font-size:14px;font-weight:700;color:{color};font-family:'Syne',sans-serif">{pct}</span>
      </div>
    </div>
    """,
        unsafe_allow_html=True,
    )


def render_symbol_detail_card(d: dict):
    if not d or d.get("error"):
        st.warning(f"Could not load detail: {d.get('error', 'unknown error')}")
        return

    pct = d.get("pct_change")
    color = chg_color(pct)

    st.markdown(
        f"""
    <div style="display:flex;justify-content:space-between;align-items:flex-start;
                margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid rgba(0,229,255,0.1)">
      <div>
        <div style="font-family:'Syne',sans-serif;font-weight:800;font-size:22px;color:#e5e7eb">{d.get('name', d.get('symbol',''))}</div>
        <div style="font-size:11px;color:#4d6880;margin-top:3px;letter-spacing:1px">
          {d.get('symbol','')} · {d.get('sector','')} · {d.get('industry','')[:40] if d.get('industry') else ''}
        </div>
      </div>
      <div style="text-align:right">
        <div style="font-family:'Syne',sans-serif;font-size:30px;font-weight:700;
                    color:#e5e7eb;letter-spacing:-1px">{fmt_price(d.get('price'))}</div>
        <div style="font-size:14px;font-weight:600;color:{color}">{fmt_chg(pct)} today</div>
      </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Market Cap", fmt_mcap(d.get("market_cap")))
    c2.metric("P/E (TTM)", fmt_num(d.get("pe_ratio"), 1) if d.get("pe_ratio") else "—")
    c3.metric("Fwd P/E", fmt_num(d.get("fwd_pe"), 1) if d.get("fwd_pe") else "—")
    c4.metric("Beta", fmt_num(d.get("beta"), 2) if d.get("beta") else "—")
    c5.metric("52W High", fmt_price(d.get("week52_high")))
    c6.metric("52W Low", fmt_price(d.get("week52_low")))

    c7, c8, c9 = st.columns(3)
    c7.metric("EPS", f"${fmt_num(d.get('eps'), 2)}" if d.get("eps") else "—")
    c8.metric("Div Yield", f"{fmt_num(d.get('dividend_yield'), 2)}%" if d.get("dividend_yield") else "—")
    c9.metric("Analyst Target", fmt_price(d.get("target_price")))

    if d.get("recommendation"):
        rec_colors = {
            "buy": "#00e676",
            "strong_buy": "#00e676",
            "hold": "#ffb300",
            "sell": "#ff3d57",
            "underperform": "#ff3d57",
        }
        rec = d["recommendation"]
        rcol = rec_colors.get(rec, "#8ba8c4")
        st.markdown(
            f"**Analyst consensus:** <span style='color:{rcol};font-weight:700;text-transform:uppercase'>{rec}</span>",
            unsafe_allow_html=True,
        )

    if d.get("description"):
        with st.expander("Business description"):
            st.markdown(
                f"<div style='font-size:12px;color:#8ba8c4;line-height:1.6'>{d['description']}</div>",
                unsafe_allow_html=True,
            )

    ohlcv = d.get("ohlcv_30d", [])
    if ohlcv:
        df_spark = pd.DataFrame(ohlcv)
        df_spark["date"] = pd.to_datetime(df_spark["date"])
        is_up = df_spark["close"].iloc[-1] >= df_spark["close"].iloc[0]
        line_color = "#00e676" if is_up else "#ff3d57"
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=df_spark["date"],
                y=df_spark["close"],
                mode="lines",
                line=dict(color=line_color, width=1.5),
                fill="tozeroy",
                fillcolor="rgba(0,230,118,0.08)" if is_up else "rgba(255,61,87,0.08)",
                name="Close",
            )
        )
        fig.update_layout(
            title="30-Day Price",
            height=200,
            margin=dict(l=0, r=0, t=30, b=0),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=False),
        )
        apply_dark_plot(fig)
        st.plotly_chart(fig, use_container_width=True)


def render_news_slots(news_items: list | None = None):
    if not news_items:
        news_items = [
            {"source": "REUTERS", "headline": "Fed signals patience on rate cuts as inflation persists above target", "time": "2h", "sentiment": "bearish"},
            {"source": "BLOOMBERG", "headline": "Tech sector leads gains as AI infrastructure spending accelerates globally", "time": "3h", "sentiment": "bullish"},
            {"source": "FT", "headline": "Oil slides on demand concerns amid global slowdown fears", "time": "5h", "sentiment": "bearish"},
            {"source": "CNBC", "headline": "S&P 500 approaches record high on strong Q2 earnings season", "time": "6h", "sentiment": "bullish"},
            {"source": "WSJ", "headline": "Dollar strengthens as safe-haven flows return to currency markets", "time": "7h", "sentiment": "neutral"},
            {"source": "BARRON'S", "headline": "Small-cap rotation signals shift in institutional risk appetite", "time": "9h", "sentiment": "neutral"},
        ]
    pill_map = {"bullish": "pill-bull", "bearish": "pill-bear", "neutral": "pill-neut"}
    html = ""
    for n in news_items:
        pill = pill_map.get(n.get("sentiment", "neutral"), "pill-neut")
        html += f"""<div class="news-item">
          <span class="news-src">{n['source']}</span>
          <div>
            <div class="news-hl">{n['headline']}</div>
            <div class="news-meta">{n.get('time','')} ago</div>
          </div>
          <span class="pill {pill}">{n.get('sentiment','neutral').upper()}</span>
        </div>"""
    st.markdown(html, unsafe_allow_html=True)


def render_enriched_watchlist_table(wl_data: list):
    if not wl_data:
        return
    rows = []
    for s in wl_data:
        if s.get("error"):
            rows.append(
                {"Symbol": s["symbol"], "Name": "—", "Price": "—", "Chg%": "—", "MCap": "—", "P/E": "—", "Beta": "—", "52W%": "—", "Sector": "—"}
            )
            continue
        hi = s.get("week52_high") or 1
        lo = s.get("week52_low") or 0
        rng = hi - lo
        price = s.get("price") or lo
        pos = round((price - lo) / rng * 100, 0) if rng > 0 else 50
        rows.append(
            {
                "Symbol": s.get("symbol", ""),
                "Name": (s.get("name", "") or "")[:22],
                "Price": fmt_price(s.get("price")),
                "Chg%": fmt_chg(s.get("pct_change")),
                "MCap": fmt_mcap(s.get("market_cap")),
                "P/E": fmt_num(s.get("pe_ratio"), 1) if s.get("pe_ratio") else "—",
                "Beta": fmt_num(s.get("beta"), 2) if s.get("beta") else "—",
                "52W%": f"{int(pos)}%",
                "Sector": (s.get("sector", "") or "")[:14],
            }
        )
    df = pd.DataFrame(rows)

    def color_chg(val):
        if "+" in str(val):
            return "color:#00e676;font-weight:600"
        if "-" in str(val) and val != "—":
            return "color:#ff3d57;font-weight:600"
        return ""

    styled = df.style.map(color_chg, subset=["Chg%"])
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ============================================================
# Data loaders
# ============================================================

def load_allocator_table() -> pd.DataFrame:
    df = safe_read_csv(STRATEGY_ALLOCATION_CSV)
    if not df.empty:
        df = normalize_columns(df)
        if "decision" in df.columns:
            df["decision"] = df["decision"].astype(str).str.upper()
        for col in ["score", "weight", "risk_per_trade_pct", "kelly_fraction", "sharpe", "sortino", "win_rate", "winrate", "avg_r"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        return df

    payload = safe_read_json(STRATEGY_ALLOCATION_JSON, default={})
    strategies = payload.get("strategies", []) if isinstance(payload, dict) else (payload if isinstance(payload, list) else [])
    if strategies:
        df = normalize_columns(pd.DataFrame(strategies))
        if "decision" in df.columns:
            df["decision"] = df["decision"].astype(str).str.upper()
        return df
    return pd.DataFrame()


def load_generated_at():
    payload = safe_read_json(STRATEGY_ALLOCATION_JSON, default={})
    if isinstance(payload, dict):
        return payload.get("generated_at") or payload.get("generated")
    return None


def discover_backtest_metrics() -> pd.DataFrame:
    if not BACKTEST_DIR.exists():
        return pd.DataFrame()

    records = []
    for metrics_file in BACKTEST_DIR.rglob("metrics.csv"):
        try:
            folder = metrics_file.parent.name
            strategy, symbol = parse_strategy_symbol(folder)
            df = normalize_columns(pd.read_csv(metrics_file))
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
            for k, v in row.items():
                kk = str(k).strip().lower().replace(" ", "_")
                normalized[rename.get(kk, kk)] = v

            normalized["strategy"] = strategy
            normalized["symbol"] = symbol
            normalized["source_file"] = str(metrics_file)
            records.append(normalized)
        except Exception:
            continue

    if not records:
        return pd.DataFrame()

    metrics = normalize_columns(pd.DataFrame(records))
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


def load_signals() -> pd.DataFrame:
    for path in [SIGNALS_CSV, WATCHLIST_CSV]:
        df = safe_read_csv(path)
        if not df.empty:
            return normalize_columns(df)
    return pd.DataFrame()


def load_watchlist() -> pd.DataFrame:
    df = safe_read_csv(WATCHLIST_CSV)
    return normalize_columns(df) if not df.empty else pd.DataFrame()


def load_alerts() -> pd.DataFrame:
    df = safe_read_csv(ALERTS_CSV)
    return normalize_columns(df) if not df.empty else pd.DataFrame()


def load_leaderboard() -> pd.DataFrame:
    df = safe_read_csv(LEADERBOARD_CSV)
    return normalize_columns(df) if not df.empty else pd.DataFrame()


def load_journal() -> pd.DataFrame:
    candidates = [
        JOURNAL_DIR / "trades.csv",
        JOURNAL_DIR / "trade_journal.csv",
        OUTPUT_DIR / "trade_journal.csv",
        OUTPUT_DIR / "trades.csv",
        TRADE_RESULTS_CSV,
    ]
    for path in candidates:
        df = safe_read_csv(path)
        if not df.empty:
            return normalize_columns(df)
    return pd.DataFrame()


def build_trade_results_df() -> pd.DataFrame:
    df = safe_read_csv(TRADE_RESULTS_CSV)
    if df.empty:
        return pd.DataFrame()
    df = normalize_columns(df)
    date_cols = [c for c in ["date", "close_date", "exit_date", "timestamp", "time"] if c in df.columns]
    df["plot_date"] = pd.to_datetime(df[date_cols[0]], errors="coerce") if date_cols else pd.NaT
    pnl_col = next((c for c in ["pnl", "profit", "net_pnl", "realized_pnl"] if c in df.columns), None)
    if pnl_col is None:
        return pd.DataFrame()

    df["pnl"] = pd.to_numeric(df[pnl_col], errors="coerce").fillna(0.0)
    df = df.sort_values("plot_date", kind="stable").reset_index(drop=True)
    df["cum_pnl"] = df["pnl"].cumsum()
    df["equity"] = 10000.0 + df["cum_pnl"]
    df["equity_peak"] = df["equity"].cummax()
    df["drawdown"] = df["equity"] - df["equity_peak"]
    df["drawdown_pct"] = (df["equity"] / df["equity_peak"] - 1.0) * 100.0
    return df


def create_sample_equity_curve(alloc_df: pd.DataFrame) -> pd.DataFrame:
    dates = pd.date_range(end=datetime.today(), periods=60, freq="D")
    current = 10000.0
    equity = []
    deploy_count = int((alloc_df["decision"] == "DEPLOY").sum()) if not alloc_df.empty and "decision" in alloc_df.columns else 0
    throttle_count = int((alloc_df["decision"] == "THROTTLE").sum()) if not alloc_df.empty and "decision" in alloc_df.columns else 0
    drift = 12 + (deploy_count * 2) - throttle_count
    for i, _ in enumerate(dates):
        current += drift + ((i % 5) - 2) * 3
        equity.append(round(current, 2))
    return pd.DataFrame({"date": dates, "equity": equity})


def build_status_counts(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "decision" not in df.columns:
        return pd.DataFrame({"decision": [], "count": []})
    counts = df["decision"].value_counts().reset_index()
    counts.columns = ["decision", "count"]
    return counts


def build_strategy_leaderboard(metrics_df: pd.DataFrame) -> pd.DataFrame:
    if metrics_df.empty or "strategy" not in metrics_df.columns:
        return pd.DataFrame()

    metric_cols = [c for c in ["sharpe", "sortino", "winrate", "drawdown", "trades", "profit_factor"] if c in metrics_df.columns]
    if not metric_cols:
        return pd.DataFrame()

    agg = metrics_df.groupby("strategy", as_index=False)[metric_cols].mean()

    for col, default in [("sharpe", 0.0), ("winrate", 0.0), ("drawdown", -1.0), ("sortino", 0.0)]:
        if col not in agg.columns:
            agg[col] = default

    agg["score"] = (
        agg["sharpe"].fillna(0).clip(0, 3) / 3 * 35
        + agg["winrate"].fillna(0).clip(0, 0.7) / 0.7 * 25
        + (1 + agg["drawdown"].fillna(-1).clip(-1, 0)) * 20
        + agg["sortino"].fillna(0).clip(0, 3) / 3 * 20
    ).round(1)

    if "winrate" in agg.columns:
        agg["winrate_pct"] = (agg["winrate"] * 100).round(2)
    if "drawdown" in agg.columns:
        agg["drawdown_pct"] = (agg["drawdown"] * 100).round(2)

    return agg.sort_values(["score", "sharpe"], ascending=[False, False]).reset_index(drop=True)


def load_master_strategy_symbol() -> pd.DataFrame:
    df = safe_read_csv(MASTER_STRATEGY_SYMBOL_CSV)
    return normalize_columns(df) if not df.empty else pd.DataFrame()


def load_master_strategy_rank() -> pd.DataFrame:
    df = safe_read_csv(MASTER_STRATEGY_RANK_CSV)
    return normalize_columns(df) if not df.empty else pd.DataFrame()


def load_master_symbol_rank() -> pd.DataFrame:
    df = safe_read_csv(MASTER_SYMBOL_RANK_CSV)
    return normalize_columns(df) if not df.empty else pd.DataFrame()


def load_master_profit_factor_matrix() -> pd.DataFrame:
    df = safe_read_csv(MASTER_PROFIT_FACTOR_MATRIX)
    return normalize_columns(df) if not df.empty else pd.DataFrame()


def load_master_avg_pnl_matrix() -> pd.DataFrame:
    df = safe_read_csv(MASTER_AVG_PNL_MATRIX)
    return normalize_columns(df) if not df.empty else pd.DataFrame()


def classify_rage_status(row: pd.Series) -> str:
    avg_pnl = pd.to_numeric(row.get("avg_pnl"), errors="coerce")
    avg_win = pd.to_numeric(row.get("avg_win_rate"), errors="coerce")
    avg_pf = pd.to_numeric(row.get("avg_profit_factor"), errors="coerce")
    trades = pd.to_numeric(row.get("trades"), errors="coerce")

    if pd.notna(avg_pnl) and pd.notna(avg_win) and pd.notna(avg_pf) and pd.notna(trades):
        if trades >= 10 and avg_pnl > 0 and avg_pf >= 1.0 and avg_win >= 0.45:
            return "DEPLOY"
        elif avg_pnl > -0.20:
            return "FIX"
        else:
            return "REJECT"
    return "UNKNOWN"


def classify_loser_reason(strategy_name: str) -> str:
    s = str(strategy_name).lower()

    if any(x in s for x in ["london", "session", "overlap", "us_open"]):
        return "Likely intraday/session strategy on the wrong data granularity"
    if "volatility_coil" in s:
        return "Trigger logic too strict or too rare on current feed"
    if "trend_continuation" in s:
        return "Continuation entry likely too permissive or late"
    if "orb" in s:
        return "Open-range logic likely needs true intraday timing"
    if "adx_trend" in s:
        return "Works only in selected regimes; broad deployment is weak"
    return "Needs logic review and targeted retest"


def classify_loser_action(strategy_name: str) -> str:
    s = str(strategy_name).lower()

    if any(x in s for x in ["london", "session", "overlap", "us_open", "orb"]):
        return "PARK_FOR_INTRADAY"
    if any(x in s for x in ["trend_continuation", "volatility_coil", "adx_trend"]):
        return "FIX_AND_RETEST"
    return "REVIEW"


def load_strategies_store() -> list:
    d = safe_read_json(STRATEGIES_JSON, default=[])
    return d if isinstance(d, list) else []


def load_notes_store() -> list:
    d = safe_read_json(NOTES_JSON, default=[])
    return d if isinstance(d, list) else []


def load_planner_store() -> list:
    d = safe_read_json(PLANNER_JSON, default=[])
    return d if isinstance(d, list) else []


def load_calendar_store() -> pd.DataFrame:
    df = safe_read_csv(CALENDAR_CSV)
    return normalize_columns(df) if not df.empty else pd.DataFrame(columns=["event_date", "title", "category", "asset", "notes"])


def load_social_x() -> pd.DataFrame:
    df = safe_read_csv(SOCIAL_X_CSV)
    return normalize_columns(df) if not df.empty else pd.DataFrame()


def load_social_reddit() -> pd.DataFrame:
    df = safe_read_csv(SOCIAL_REDDIT_CSV)
    return normalize_columns(df) if not df.empty else pd.DataFrame()


def load_market_overview_csv() -> pd.DataFrame:
    df = safe_read_csv(MARKET_OVERVIEW_CSV)
    return normalize_columns(df) if not df.empty else pd.DataFrame()


# ============================================================
# Load all data
# ============================================================

alloc_df = load_allocator_table()
metrics_df = discover_backtest_metrics()
signals_df = load_signals()
watchlist_df = load_watchlist()
alerts_df = load_alerts()
leaderboard_csv_df = load_leaderboard()
journal_df = load_journal()
trade_results_df = build_trade_results_df()
status_df = build_status_counts(alloc_df)
generated_at = load_generated_at()
strategy_leaderboard_df = build_strategy_leaderboard(metrics_df)

master_strategy_symbol_df = load_master_strategy_symbol()
master_strategy_rank_df = load_master_strategy_rank()
master_symbol_rank_df = load_master_symbol_rank()
master_pf_matrix_df = load_master_profit_factor_matrix()
master_avg_pnl_matrix_df = load_master_avg_pnl_matrix()

if not master_strategy_rank_df.empty and "strategy" in master_strategy_rank_df.columns:
    master_strategy_rank_df["status"] = master_strategy_rank_df.apply(classify_rage_status, axis=1)
    master_strategy_rank_df["loser_reason"] = master_strategy_rank_df["strategy"].apply(classify_loser_reason)
    master_strategy_rank_df["recommended_action"] = master_strategy_rank_df["strategy"].apply(classify_loser_action)

strategies_store = load_strategies_store()
notes_store = load_notes_store()
planner_store = load_planner_store()
calendar_df = load_calendar_store()
social_x_df = load_social_x()
social_reddit_df = load_social_reddit()
market_overview_csv = load_market_overview_csv()

intel = load_market_intel()
intel_overview = intel.get("market_overview", {})
intel_sectors = intel.get("sector_performance", [])
intel_movers = intel.get("top_movers", {})
intel_watchlist = intel.get("watchlist", [])
intel_generated_at = intel.get("generated_at", None)

if trade_results_df.empty:
    equity_df = create_sample_equity_curve(alloc_df)
    equity_is_real = False
else:
    equity_df = trade_results_df.copy()
    equity_is_real = True


# ============================================================
# Sidebar
# ============================================================

st.sidebar.markdown(
    """
<div style="font-family:'Syne',sans-serif;font-weight:800;font-size:18px;
            color:#e5e7eb;padding:8px 0 4px">
  RAGE <span style="background: linear-gradient(90deg, #ff4500, #ff8c00, #ffcc00); -webkit-background-clip: text; -webkit-text-fill-color: transparent; text-shadow: 0 0 20px rgba(255,69,0,0.5); letter-spacing: 2px;">ENGINE</span>
</div>
<div style="font-size:10px;color:#4d6880;letter-spacing:1.5px;margin-bottom:12px">
  ROB AND GARETH ENGINE</div>
    <div style="margin-top:8px; padding:8px; border-left:3px solid #ff4500; background:rgba(255,69,0,0.05);">
    <div style="font-size:10px; color:#888; font-style:italic; line-height:1.4;" id="rage-quote">
    Built by Rob &amp; Gareth. Father and son.<br>
    <span style="color:#ff8c00;">&#x26A1; RAGE Engine</span> — Trading Intelligence Platform
    </div></div>
""",
    unsafe_allow_html=True,
)

page = st.sidebar.radio(
    "Navigate",
    [
        "Overview",
        "Allocator",
        "RAGE Control Panel",
        "Live Signals",
        "Markets",
        "Charts",
        "Reports",
        "Social Sentiment",
        "Backtests",
        "Journal",
        "Trade Journal",
        "Performance",
        "Portfolio Heat",
        "Monte Carlo",
        "Uploads",
        "Strategy Builder",
        "Governance Notes",
        "Daily Planner",
        "Calendar",
        "Platform Vision",
    ],
)

st.sidebar.markdown("---")
show_raw = st.sidebar.checkbox("Show raw tables", value=False)

if generated_at:
    st.sidebar.markdown(f"<div class='small-muted'>Allocator run:<br><code>{generated_at}</code></div>", unsafe_allow_html=True)

st.sidebar.markdown("---")
intel_status = "✅ Loaded" if intel else "⚠️ Not generated"
st.sidebar.markdown(
    f"""
<div style="font-size:10px;color:#4d6880;letter-spacing:1px;margin-bottom:6px">FILE STATUS</div>
<div style="font-size:11px;line-height:1.8">
  {'✅' if STRATEGY_ALLOCATION_CSV.exists() else '❌'} Allocator CSV<br>
  {'✅' if TRADE_RESULTS_CSV.exists() else '❌'} Trade results<br>
  {'✅' if SIGNALS_CSV.exists() else '❌'} Signals<br>
  {'✅' if REPORTS_DIR.exists() else '❌'} Reports folder<br>
  <span style="color:{'#00e676' if intel else '#ffb300'}">{intel_status}</span> Market Intel<br>
  {'✅' if MASTER_STRATEGY_RANK_CSV.exists() else '❌'} Master Strategy Rank<br>
  {'✅' if MASTER_SYMBOL_RANK_CSV.exists() else '❌'} Master Symbol Rank
</div>
""",
    unsafe_allow_html=True,
)

if intel_generated_at:
    st.sidebar.markdown(f"<div class='small-muted' style='margin-top:6px'>Intel: {intel_generated_at[:16]}</div>", unsafe_allow_html=True)


# ============================================================
# Header
# ============================================================

st.markdown(
    """
<div style="display:flex;align-items:center;justify-content:space-between;
            margin-bottom:6px;padding-bottom:10px;border-bottom:1px solid rgba(0,229,255,0.08)">
  <div>
    <span style="font-family:'Syne',sans-serif;font-weight:800;font-size:22px;color:#e5e7eb">
      RAGE Engine
    </span>
    <span style="font-family:'JetBrains Mono',monospace;font-size:11px;
                 color:#00e5ff;margin-left:10px;letter-spacing:1.5px">V4</span>
    <div style="font-size:11px;color:#4d6880;letter-spacing:0.5px;margin-top:2px">
      Live Market Intel · Multi-Strategy · Backtester · Journal · Intelligence Hub
    </div>
  </div>
  <div style="text-align:right;font-size:11px;color:#4d6880">
    <span class="live-dot"></span>
    <span style="color:#e5e7eb">{}</span>
  </div>
</div>
""".format(datetime.now().strftime("%a %d %b %Y · %H:%M")),
    unsafe_allow_html=True,
)

if intel_overview:
    render_ticker_tape(intel_overview)


# ============================================================
# PAGE: Overview
# ============================================================

if page == "Overview":
    quote_text, quote_author = get_daily_quote()
    greeting = get_welcome_message()
    st.markdown(
        f"""
    <div style="background: linear-gradient(135deg, rgba(255,69,0,0.15), rgba(0,0,0,0.3)); 
                border: 1px solid rgba(255,69,0,0.3); border-radius:12px; 
                padding:20px; margin-bottom:20px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
                <div style="font-size:22px; font-weight:700; color:#fff;">
                    ⚡ {greeting}, welcome to <span style="background: linear-gradient(90deg, #ff4500, #ff8c00); 
                    -webkit-background-clip:text; -webkit-text-fill-color:transparent;">RAGE Engine</span>
                </div>
                <div style="font-size:12px; color:#888; margin-top:4px;">
                    Rob And Gareth Engine &nbsp;|&nbsp; {_datetime.datetime.now().strftime('%A, %d %B %Y')}
                </div>
            </div>
        </div>
        <div style="margin-top:16px; padding-top:16px; border-top:1px solid rgba(255,255,255,0.1);">
            <div style="font-size:13px; color:#ccc; font-style:italic;">
                &ldquo;{quote_text}&rdquo;
            </div>
            <div style="font-size:11px; color:#ff8c00; margin-top:6px;">— {quote_author}</div>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    deploy_count = int((alloc_df["decision"] == "DEPLOY").sum()) if not alloc_df.empty and "decision" in alloc_df.columns else 0
    throttle_count = int((alloc_df["decision"] == "THROTTLE").sum()) if not alloc_df.empty and "decision" in alloc_df.columns else 0
    reject_count = int((alloc_df["decision"] == "REJECT").sum()) if not alloc_df.empty and "decision" in alloc_df.columns else 0
    total_weight = float(alloc_df["weight"].fillna(0).sum()) if not alloc_df.empty and "weight" in alloc_df.columns else 0.0
    avg_risk = float(alloc_df["risk_per_trade_pct"].fillna(0).mean()) if not alloc_df.empty and "risk_per_trade_pct" in alloc_df.columns else 0.0
    strategies_found = int(metrics_df["strategy"].nunique()) if not metrics_df.empty and "strategy" in metrics_df.columns else 0
    symbols_found = int(metrics_df["symbol"].nunique()) if not metrics_df.empty and "symbol" in metrics_df.columns else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("DEPLOY", deploy_count)
    c2.metric("THROTTLE", throttle_count)
    c3.metric("REJECT", reject_count)
    c4.metric("Strategy Weight", f"{total_weight:.2f}")
    c5.metric("Avg Risk/Trade", f"{avg_risk:.2f}%")

    c6, c7, c8, c9 = st.columns(4)
    c6.metric("Strategies", strategies_found)
    c7.metric("Symbols", symbols_found)
    c8.metric("Signals", len(signals_df) if not signals_df.empty else 0)
    c9.metric("Reports", sum(len(list_files_recursive(d)) for d in REPORT_SUBDIRS))

    if intel_sectors:
        st.markdown("### ▦ Sector Performance")
        render_sector_heatmap(intel_sectors)

    left, right = st.columns([1.2, 1])
    with left:
        st.markdown("### 📊 Allocation Snapshot")
        if not alloc_df.empty and "strategy" in alloc_df.columns and "weight" in alloc_df.columns:
            fig = px.bar(
                alloc_df,
                x="strategy",
                y="weight",
                color="decision" if "decision" in alloc_df.columns else None,
                text="weight",
                title="Strategy Allocation Weight",
            )
            fig.update_traces(texttemplate="%{text:.2f}", textposition="outside")
            apply_dark_plot(fig)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No allocator weights found yet.")

    with right:
        st.markdown("### 🧠 Capital Split")
        if not alloc_df.empty and "weight" in alloc_df.columns and "strategy" in alloc_df.columns:
            pie_df = alloc_df[alloc_df["weight"].fillna(0) > 0].copy()
            if not pie_df.empty:
                fig2 = px.pie(pie_df, values="weight", names="strategy", title="Allocated Capital Split", hole=0.45)
                apply_dark_plot(fig2)
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("No non-zero allocation weights found.")
        else:
            st.info("No capital split available.")

    left, right = st.columns(2)
    with left:
        st.markdown("### 📈 Equity")
        if equity_is_real:
            fig_eq = px.line(equity_df, x="plot_date", y="equity", title="Portfolio Equity Curve")
        else:
            fig_eq = px.line(equity_df, x="date", y="equity", title="Portfolio Equity Curve (placeholder)")
        apply_dark_plot(fig_eq)
        st.plotly_chart(fig_eq, use_container_width=True)

    with right:
        st.markdown("### ⚠️ Drawdown")
        if equity_is_real:
            fig_dd = px.area(equity_df, x="plot_date", y="drawdown_pct", title="Drawdown (%)")
            apply_dark_plot(fig_dd)
            st.plotly_chart(fig_dd, use_container_width=True)
        else:
            st.info("No trade_results.csv found — drawdown not available.")

    st.markdown("### 📋 Current Strategy Decisions")
    if not alloc_df.empty:
        display_df = alloc_df.copy()
        if "risk_per_trade_pct" in display_df.columns:
            display_df["risk_%"] = pd.to_numeric(display_df["risk_per_trade_pct"], errors="coerce").round(2)
        preferred = ["strategy", "decision", "score", "risk_%", "weight", "kelly_fraction", "avg_r", "win_rate", "winrate", "sharpe", "sortino"]
        present = [c for c in preferred if c in display_df.columns] or display_df.columns.tolist()
        styled = display_df[present].style.map(highlight_decision, subset=["decision"] if "decision" in present else [])
        st.dataframe(styled, use_container_width=True, hide_index=True)

    if show_raw:
        st.write(alloc_df)


# ============================================================
# PAGE: Allocator
# ============================================================

elif page == "Allocator":
    st.subheader("Allocator Control Panel")
    if alloc_df.empty:
        st.warning("No allocator data found. Run: `python main.py --mode allocate`")
    else:
        top_left, top_right = st.columns([1.2, 1])

        with top_left:
            display_df = alloc_df.copy()
            if "risk_per_trade_pct" in display_df.columns:
                display_df["risk_%"] = display_df["risk_per_trade_pct"].round(2)
            ordered = ["strategy", "decision", "score", "risk_%", "weight", "kelly_fraction", "avg_r", "win_rate", "winrate", "sharpe", "sortino"]
            ordered = [c for c in ordered if c in display_df.columns] or display_df.columns.tolist()
            st.dataframe(
                display_df[ordered].style.map(highlight_decision, subset=["decision"] if "decision" in ordered else []),
                use_container_width=True,
                hide_index=True,
            )

        with top_right:
            if not status_df.empty:
                fig = px.bar(status_df, x="decision", y="count", color="decision", text="count", title="Decision Breakdown")
                fig.update_traces(textposition="outside")
                apply_dark_plot(fig)
                st.plotly_chart(fig, use_container_width=True)

        left, right = st.columns(2)
        with left:
            if "risk_per_trade_pct" in alloc_df.columns:
                nn = alloc_df[alloc_df["risk_per_trade_pct"].fillna(0) > 0].copy()
                if not nn.empty:
                    fig = px.bar(
                        nn,
                        x="strategy",
                        y="risk_per_trade_pct",
                        color="decision" if "decision" in nn.columns else None,
                        text="risk_per_trade_pct",
                        title="Live Risk Per Trade (%)",
                    )
                    fig.update_traces(texttemplate="%{text:.2f}", textposition="outside")
                    apply_dark_plot(fig)
                    st.plotly_chart(fig, use_container_width=True)

        with right:
            if "weight" in alloc_df.columns:
                nn = alloc_df[alloc_df["weight"].fillna(0) > 0].copy()
                if not nn.empty:
                    fig = px.bar(
                        nn,
                        x="strategy",
                        y="weight",
                        color="decision" if "decision" in nn.columns else None,
                        text="weight",
                        title="Normalized Strategy Weights",
                    )
                    fig.update_traces(texttemplate="%{text:.4f}", textposition="outside")
                    apply_dark_plot(fig)
                    st.plotly_chart(fig, use_container_width=True)

        deploy_df = alloc_df[alloc_df["decision"] == "DEPLOY"].copy() if "decision" in alloc_df.columns else pd.DataFrame()
        reject_df = alloc_df[alloc_df["decision"] == "REJECT"].copy() if "decision" in alloc_df.columns else pd.DataFrame()

        if not deploy_df.empty:
            st.success("Deploy-ready: " + ", ".join(deploy_df["strategy"].astype(str).tolist()))
        if not reject_df.empty:
            st.error("Keep off live: " + ", ".join(reject_df["strategy"].astype(str).tolist()))


# ============================================================
# PAGE: RAGE Control Panel
# ============================================================

elif page == "RAGE Control Panel":
    st.subheader("RAGE Control Panel")
    st.markdown("<div class='small-muted'>Master strategy intelligence, loser diagnostics, and execution roadmap</div>", unsafe_allow_html=True)

    top1, top2, top3, top4 = st.columns(4)

    deploy_count = int((master_strategy_rank_df["status"] == "DEPLOY").sum()) if not master_strategy_rank_df.empty and "status" in master_strategy_rank_df.columns else 0
    fix_count = int((master_strategy_rank_df["status"] == "FIX").sum()) if not master_strategy_rank_df.empty and "status" in master_strategy_rank_df.columns else 0
    reject_count = int((master_strategy_rank_df["status"] == "REJECT").sum()) if not master_strategy_rank_df.empty and "status" in master_strategy_rank_df.columns else 0
    tracked_syms = int(master_symbol_rank_df["symbol"].nunique()) if not master_symbol_rank_df.empty and "symbol" in master_symbol_rank_df.columns else 0

    top1.metric("Deploy", deploy_count)
    top2.metric("Fix", fix_count)
    top3.metric("Reject", reject_count)
    top4.metric("Tracked Symbols", tracked_syms)

    st.markdown("### 🚀 Strategy Leaderboard")
    if not master_strategy_rank_df.empty:
        show_cols = [
            c
            for c in [
                "strategy",
                "status",
                "markets",
                "trades",
                "avg_win_rate",
                "avg_pnl",
                "avg_profit_factor",
                "avg_sharpe_like",
                "rank_score",
            ]
            if c in master_strategy_rank_df.columns
        ]
        display_df = master_strategy_rank_df.sort_values("rank_score", ascending=False) if "rank_score" in master_strategy_rank_df.columns else master_strategy_rank_df
        st.dataframe(display_df[show_cols], use_container_width=True, hide_index=True)
    else:
        st.warning("No master strategy ranking found. Run: python build_master_performance.py")

    st.markdown("### 📊 Symbol Intelligence")
    if not master_symbol_rank_df.empty:
        show_cols = [
            c
            for c in [
                "symbol",
                "strategies",
                "trades",
                "avg_win_rate",
                "avg_pnl",
                "avg_profit_factor",
                "avg_sharpe_like",
                "rank_score",
            ]
            if c in master_symbol_rank_df.columns
        ]
        display_df = master_symbol_rank_df.sort_values("rank_score", ascending=False) if "rank_score" in master_symbol_rank_df.columns else master_symbol_rank_df
        st.dataframe(display_df[show_cols], use_container_width=True, hide_index=True)
    else:
        st.info("No symbol ranking data yet.")

    st.markdown("### 🔥 Loser Diagnostics")
    if not master_strategy_rank_df.empty:
        losers = master_strategy_rank_df[master_strategy_rank_df["status"] != "DEPLOY"].copy()
        show_cols = [
            c
            for c in [
                "strategy",
                "status",
                "avg_pnl",
                "avg_win_rate",
                "avg_profit_factor",
                "avg_sharpe_like",
                "loser_reason",
                "recommended_action",
            ]
            if c in losers.columns
        ]
        if "avg_pnl" in losers.columns:
            losers = losers.sort_values("avg_pnl", ascending=True)
        st.dataframe(losers[show_cols], use_container_width=True, hide_index=True)
    else:
        st.info("No loser diagnostics available yet.")

    st.markdown("### 🧠 Strategy × Symbol Matrix")
    if not master_strategy_symbol_df.empty and "strategy" in master_strategy_symbol_df.columns:
        selected_strategy = st.selectbox(
            "Open strategy drilldown",
            ["All"] + sorted(master_strategy_symbol_df["strategy"].dropna().astype(str).unique().tolist()),
        )
        display_df = master_strategy_symbol_df.copy()
        if selected_strategy != "All":
            display_df = display_df[display_df["strategy"].astype(str) == selected_strategy]
        st.dataframe(display_df, use_container_width=True, hide_index=True)
    else:
        st.info("No master strategy-symbol table found yet.")

    st.markdown("### 📐 Profit Factor Matrix")
    if not master_pf_matrix_df.empty:
        st.dataframe(master_pf_matrix_df, use_container_width=True, hide_index=True)
    else:
        st.info("No profit factor matrix found.")

    st.markdown("### 📐 Average PnL Matrix")
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
    <div class='glass'>
    <b>Execution roadmap</b><br><br>
    - Attempt 1 = starter position<br>
    - Attempt 2 = better retest entry if structure holds<br>
    - Attempt 3 = final reclaim / confirmation attempt<br><br>
    This layer is not fully wired into backtesting yet, but it is now visible inside the app.
    </div>
    """,
        unsafe_allow_html=True,
    )


# ============================================================
# PAGE: Live Signals
# ============================================================

elif page == "Live Signals":
    st.subheader("Live Scanner Signals")
    a, b, c = st.columns(3)
    a.metric("Signals", "Loaded" if not signals_df.empty else "Missing")
    b.metric("Watchlist", "Loaded" if not watchlist_df.empty else "Missing")
    c.metric("Alerts", "Loaded" if not alerts_df.empty else "Missing")

    # ── MTF Score 0.0 Fix ────────────────────────────────────────────────────
    if not signals_df.empty and "score" in signals_df.columns:
        zero_scores = (signals_df["score"].fillna(0) == 0).sum()
        if zero_scores > 0 and BRIDGE_AVAILABLE:
            st.warning(
                f"⚠️ {zero_scores} signal(s) have score 0.0 — "
                "applying MTF score fix automatically."
            )
            for idx, row in signals_df.iterrows():
                if float(row.get("score", 0)) == 0.0:
                    from rage_signal_bridge import compute_final_score_from_dict
                    try:
                        fixed = fix_final_score(row.to_dict())
                        signals_df.at[idx, "score"] = fixed.get("score", 0)
                    except Exception:
                        pass

    if not signals_df.empty:
        st.markdown("### ⚡ Current Signals")
        preferred = ["symbol", "strategy", "signal", "direction", "entry", "stop",
                     "target", "score", "strength", "rr", "timeframe", "conviction",
                     "regime", "entry_type"]
        cols = [c for c in preferred if c in signals_df.columns] or signals_df.columns.tolist()

        # Colour-code by score
        def colour_score(val):
            try:
                v = float(val)
                if v >= 75: return "color:#00e676;font-weight:bold"
                if v >= 55: return "color:#ffb300;font-weight:bold"
                return "color:#ff3d57"
            except Exception:
                return ""

        score_cols = [c for c in ["score", "strength"] if c in cols]
        if score_cols:
            styled = signals_df[cols].style.map(colour_score, subset=score_cols)
            st.dataframe(styled, use_container_width=True, hide_index=True)
        else:
            st.dataframe(signals_df[cols], use_container_width=True, hide_index=True)
    else:
        st.info("No signals.csv or watchlist.csv found yet.")

    left, right = st.columns(2)
    with left:
        st.markdown("### 👀 Watchlist")
        if not watchlist_df.empty:
            cols = [c for c in ["symbol", "strategy", "signal", "strength", "score",
                                  "conviction", "regime"] if c in watchlist_df.columns] \
                   or watchlist_df.columns.tolist()
            st.dataframe(watchlist_df[cols], use_container_width=True, hide_index=True)
        else:
            st.info("No watchlist.csv found.")

    with right:
        st.markdown("### 🔔 Alerts")
        if not alerts_df.empty:
            cols = [c for c in ["timestamp", "date", "symbol", "strategy",
                                  "alert", "signal"] if c in alerts_df.columns] \
                   or alerts_df.columns.tolist()
            st.dataframe(alerts_df[cols], use_container_width=True, hide_index=True)
        else:
            st.info("No alerts.csv found.")

    # ── Broker Panel ─────────────────────────────────────────────────────────
    st.markdown("### 🏦 Broker Panel")

    if BROKER_AVAILABLE:
        broker_col1, broker_col2 = st.columns([1, 3])
        with broker_col1:
            if not st.session_state["broker_connected"]:
                if st.button("🔌 Connect Alpaca", use_container_width=True):
                    broker = AlpacaBroker()
                    if broker.connect():
                        st.session_state["broker"] = broker
                        st.session_state["broker_connected"] = True
                        st.rerun()
                    else:
                        st.error("Connection failed — check ALPACA_API_KEY in .env")
            else:
                if st.button("🔌 Disconnect", use_container_width=True):
                    if st.session_state["broker"]:
                        st.session_state["broker"].disconnect()
                    st.session_state["broker"] = None
                    st.session_state["broker_connected"] = False
                    st.rerun()

        if st.session_state["broker_connected"] and st.session_state["broker"]:
            render_broker_panel(st.session_state["broker"])
        elif not st.session_state["broker_connected"]:
            st.info(
                "Click **Connect Alpaca** to wire live broker data.\n\n"
                "Set `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_PAPER=true` in `.env`"
            )
    else:
        st.info(
            "broker_alpaca.py not found. "
            "Drop it into scanner_v2/ and restart the dashboard."
        )



# ============================================================
# PAGE: Markets
# ============================================================

elif page == "Markets":
    st.markdown("## ◈ Markets Intelligence")
    st.markdown("<div class='small-muted'>Two layers: Strategy signals from backtests (CSV) + Live prices from Yahoo Finance (V4)</div>", unsafe_allow_html=True)
    st.markdown("")

    col_fetch, col_status = st.columns([1, 3])
    with col_fetch:
        if st.button("⚡ Fetch Live Data", use_container_width=True):
            run_market_intel_fetch()
            st.rerun()

    with col_status:
        if intel_generated_at:
            st.markdown(f"<div class='small-muted'><span class='live-dot'></span>Live data loaded · Generated {intel_generated_at[:16]}</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='small-muted'>⚠️ No live data yet — click Fetch Live Data, or run <code>python market_intel.py report</code></div>", unsafe_allow_html=True)

    st.markdown("---")

    st.markdown("### ▦ Sector Performance")
    render_sector_heatmap(intel_sectors)

    st.markdown("---")

    if intel_movers:
        st.markdown("### ▲ Top Movers")
        mcol1, mcol2 = st.columns(2)
        with mcol1:
            st.markdown("<div style='font-size:10px;letter-spacing:1px;color:#00e676;margin-bottom:6px'>▲ GAINERS</div>", unsafe_allow_html=True)
            for m in intel_movers.get("gainers", []):
                render_mover_row(m, "#00e676")
        with mcol2:
            st.markdown("<div style='font-size:10px;letter-spacing:1px;color:#ff3d57;margin-bottom:6px'>▼ LOSERS</div>", unsafe_allow_html=True)
            for m in intel_movers.get("losers", []):
                render_mover_row(m, "#ff3d57")
        st.markdown("---")

    st.markdown("### ◎ Live Watchlist (Yahoo Finance)")
    if intel_watchlist:
        render_enriched_watchlist_table(intel_watchlist)

        live_syms = [s["symbol"] for s in intel_watchlist if not s.get("error")]
        if live_syms:
            chosen_live = st.selectbox("Open live symbol detail ↓", ["— select —"] + live_syms, key="live_sym_sel")
            if chosen_live and chosen_live != "— select —":
                detail_data = next((s for s in intel_watchlist if s["symbol"] == chosen_live), None)
                if detail_data:
                    with st.container():
                        st.markdown(f"### ◉ {chosen_live} — Live Detail")
                        render_symbol_detail_card(detail_data)
    else:
        st.info("No live watchlist data. Click 'Fetch Live Data' above to load.")
        if not intel:
            st.markdown(
                """
            <div class='glass'>
            <b>To load live data:</b><br>
            1. Drop <code>market_intel.py</code> into your scanner root<br>
            2. Run <code>python market_intel.py report</code><br>
            3. Click Fetch Live Data above — or relaunch the dashboard
            </div>
            """,
                unsafe_allow_html=True,
            )

    st.markdown("---")

    st.markdown("### ◌ Strategy Signals Layer (Backtest CSV)")
    st.markdown("<div class='small-muted'>Your scanner signals and backtest watchlist — separate from live prices above</div>", unsafe_allow_html=True)
    st.markdown("")

    market_category = st.selectbox("Asset View", ["All", "Stocks", "Indices", "Forex", "Crypto", "Futures", "ETFs", "Commodities"])
    symbol_search = st.text_input("Search symbol or market")
    source_choice = st.multiselect("Data focus", ["Signals", "Watchlist", "Market Overview", "Backtests"], default=["Signals", "Watchlist", "Backtests"])

    combined = []
    if "Signals" in source_choice and not signals_df.empty:
        tmp = signals_df.copy()
        tmp["source"] = "signals"
        combined.append(tmp)
    if "Watchlist" in source_choice and not watchlist_df.empty:
        tmp = watchlist_df.copy()
        tmp["source"] = "watchlist"
        combined.append(tmp)
    if "Market Overview" in source_choice and not market_overview_csv.empty:
        tmp = market_overview_csv.copy()
        tmp["source"] = "market_overview"
        combined.append(tmp)
    if "Backtests" in source_choice and not metrics_df.empty:
        tmp = metrics_df.copy()
        tmp["source"] = "backtests"
        combined.append(tmp)

    if combined:
        market_df = pd.concat(combined, ignore_index=True, sort=False)

        if symbol_search:
            cols = [c for c in ["symbol", "asset", "market", "ticker"] if c in market_df.columns]
            if cols:
                mask = pd.Series(False, index=market_df.index)
                for c in cols:
                    mask |= market_df[c].astype(str).str.contains(symbol_search, case=False, na=False)
                market_df = market_df[mask]

        if market_category != "All":
            cat_cols = [c for c in ["asset_class", "market_type", "category", "asset"] if c in market_df.columns]
            if cat_cols:
                cat_mask = pd.Series(False, index=market_df.index)
                for c in cat_cols:
                    cat_mask |= market_df[c].astype(str).str.contains(market_category, case=False, na=False)
                market_df = market_df[cat_mask]

        st.dataframe(market_df, use_container_width=True, hide_index=True)

        if "symbol" in market_df.columns:
            syms = sorted(market_df["symbol"].dropna().astype(str).unique().tolist())
            if syms:
                sel = st.selectbox("Open backtest symbol detail", [""] + syms, key="bt_sym_sel")
                if sel:
                    sym_df = market_df[market_df["symbol"].astype(str) == sel]
                    st.markdown(f"### 🔎 {sel} — Backtest Detail")
                    st.dataframe(sym_df, use_container_width=True, hide_index=True)
                    if not metrics_df.empty and "symbol" in metrics_df.columns:
                        bt = metrics_df[metrics_df["symbol"].astype(str) == sel]
                        if not bt.empty and "strategy" in bt.columns and "sharpe" in bt.columns:
                            fig = px.bar(bt, x="strategy", y="sharpe", color="strategy", title=f"{sel} — Strategy Sharpe")
                            apply_dark_plot(fig)
                            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No strategy signal data sources found yet.")

    st.markdown("---")

    st.markdown("### ◌ Macro & News Feed")
    st.markdown("<div class='small-muted'>Placeholder slots — wire to NewsAPI / RSS feed in market_intel.py</div>", unsafe_allow_html=True)
    st.markdown("")
    render_news_slots()


# ============================================================
# PAGE: Charts  (full replacement — drop between lines 1753-1838)
# ============================================================

elif page == "Charts":
    st.markdown("## 📊 RAGE Charts")
    st.markdown(
        "<div class='small-muted'>Strategy performance · Symbol intelligence · "
        "Equity · Drawdown · Heatmaps · Correlation</div>",
        unsafe_allow_html=True,
    )
    st.markdown("")

    chart_mode = st.selectbox(
        "Chart View",
        [
            "Strategy Rank — Leaderboard",
            "Strategy Deep Dive",
            "Symbol Rank — Top Markets",
            "Metric Comparison — All Strategies",
            "Profit Factor Heatmap",
            "Average PnL Heatmap",
            "Win Rate vs Sharpe (Scatter)",
            "Equity Curve",
            "Drawdown",
            "Trades by Strategy",
        ],
    )

    # ----------------------------------------------------------
    # 1. Strategy Rank — Leaderboard
    # ----------------------------------------------------------
    if chart_mode == "Strategy Rank — Leaderboard":
        if not master_strategy_rank_df.empty and "rank_score" in master_strategy_rank_df.columns:
            df_plot = master_strategy_rank_df.sort_values("rank_score", ascending=False).copy()
            color_col = "status" if "status" in df_plot.columns else None

            fig = px.bar(
                df_plot,
                x="strategy",
                y="rank_score",
                color=color_col,
                text="rank_score",
                title="Strategy Rank Scores — All Strategies",
                color_discrete_map={
                    "DEPLOY": "#00e676",
                    "FIX": "#ffb300",
                    "REJECT": "#ff3d57",
                    "UNKNOWN": "#4d6880",
                },
            )
            fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
            fig.update_layout(xaxis_tickangle=-35, height=480)
            apply_dark_plot(fig)
            st.plotly_chart(fig, use_container_width=True)

            # Rank score vs avg_win_rate bubble
            if "avg_win_rate" in df_plot.columns and "trades" in df_plot.columns:
                st.markdown("#### Rank Score vs Win Rate (bubble = trade count)")
                fig2 = px.scatter(
                    df_plot,
                    x="avg_win_rate",
                    y="rank_score",
                    size=df_plot["trades"].fillna(1).clip(1).astype(float),
                    color=color_col,
                    text="strategy",
                    title="Win Rate vs Rank Score",
                    color_discrete_map={
                        "DEPLOY": "#00e676",
                        "FIX": "#ffb300",
                        "REJECT": "#ff3d57",
                        "UNKNOWN": "#4d6880",
                    },
                )
                fig2.update_traces(textposition="top center", textfont_size=9)
                fig2.update_layout(height=440)
                apply_dark_plot(fig2)
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.warning("No strategy rank table found. Click Rebuild Master Tables in the launcher.")

    # ----------------------------------------------------------
    # 2. Strategy Deep Dive
    # ----------------------------------------------------------
    elif chart_mode == "Strategy Deep Dive":
        if not master_strategy_symbol_df.empty and "strategy" in master_strategy_symbol_df.columns:
            strategies_available = sorted(
                master_strategy_symbol_df["strategy"].dropna().astype(str).unique().tolist()
            )
            chosen = st.selectbox("Select strategy", strategies_available)
            df_strat = master_strategy_symbol_df[
                master_strategy_symbol_df["strategy"].astype(str) == chosen
            ].copy()

            if not df_strat.empty:
                metric_options = [
                    c for c in ["sharpe", "winrate", "profit_factor", "avg_pnl",
                                 "drawdown", "sortino", "ann_return", "trades"]
                    if c in df_strat.columns
                ]
                if metric_options:
                    selected_metric = st.selectbox("Metric to plot per symbol", metric_options)

                    df_strat[selected_metric] = pd.to_numeric(df_strat[selected_metric], errors="coerce")
                    df_sorted = df_strat.sort_values(selected_metric, ascending=False).dropna(subset=[selected_metric])

                    fig = px.bar(
                        df_sorted,
                        x="symbol",
                        y=selected_metric,
                        color=selected_metric,
                        color_continuous_scale="Teal",
                        text=selected_metric,
                        title=f"{chosen} — {selected_metric} per Symbol",
                    )
                    fig.update_traces(texttemplate="%{text:.3f}", textposition="outside")
                    fig.update_layout(xaxis_tickangle=-40, height=440)
                    apply_dark_plot(fig)
                    st.plotly_chart(fig, use_container_width=True)

                    # Multi-metric radar / grouped bar
                    radar_metrics = [c for c in ["sharpe", "winrate", "profit_factor", "avg_pnl"]
                                     if c in df_strat.columns]
                    if len(radar_metrics) >= 2:
                        st.markdown(f"#### {chosen} — Multi-Metric Comparison (top 15 symbols)")
                        top15 = df_strat.sort_values(selected_metric, ascending=False).head(15)
                        melted = top15.melt(id_vars=["symbol"], value_vars=radar_metrics,
                                            var_name="metric", value_name="value")
                        melted["value"] = pd.to_numeric(melted["value"], errors="coerce")
                        fig3 = px.bar(
                            melted,
                            x="symbol",
                            y="value",
                            color="metric",
                            barmode="group",
                            title=f"{chosen} — Multi-Metric by Symbol",
                        )
                        fig3.update_layout(xaxis_tickangle=-40, height=400)
                        apply_dark_plot(fig3)
                        st.plotly_chart(fig3, use_container_width=True)

                st.markdown(f"#### Raw data — {chosen}")
                st.dataframe(df_strat, use_container_width=True, hide_index=True)
        else:
            st.warning("No strategy-symbol table found. Run Rebuild Master Tables.")

    # ----------------------------------------------------------
    # 3. Symbol Rank — Top Markets
    # ----------------------------------------------------------
    elif chart_mode == "Symbol Rank — Top Markets":
        if not master_symbol_rank_df.empty and "rank_score" in master_symbol_rank_df.columns:
            top_n = st.slider("Show top N symbols", 10, min(50, len(master_symbol_rank_df)), 20)
            df_sym = master_symbol_rank_df.sort_values("rank_score", ascending=False).head(top_n)

            fig = px.bar(
                df_sym,
                x="symbol",
                y="rank_score",
                color="rank_score",
                color_continuous_scale="Teal",
                text="rank_score",
                title=f"Top {top_n} Symbols by Rank Score",
            )
            fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
            fig.update_layout(xaxis_tickangle=-40, height=440)
            apply_dark_plot(fig)
            st.plotly_chart(fig, use_container_width=True)

            if "avg_win_rate" in df_sym.columns and "avg_profit_factor" in df_sym.columns:
                st.markdown("#### Win Rate vs Profit Factor (bubble = rank score)")
                fig2 = px.scatter(
                    df_sym,
                    x="avg_win_rate",
                    y="avg_profit_factor",
                    size=df_sym["rank_score"].fillna(1).clip(1).astype(float),
                    color="rank_score",
                    color_continuous_scale="Teal",
                    text="symbol",
                    title="Symbol: Win Rate vs Profit Factor",
                )
                fig2.update_traces(textposition="top center", textfont_size=9)
                fig2.update_layout(height=440)
                apply_dark_plot(fig2)
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.warning("No symbol rank table found. Run Rebuild Master Tables.")

    # ----------------------------------------------------------
    # 4. Metric Comparison — All Strategies
    # ----------------------------------------------------------
    elif chart_mode == "Metric Comparison — All Strategies":
        if not master_strategy_rank_df.empty:
            metric_cols_avail = [
                c for c in ["avg_sharpe_like", "avg_win_rate", "avg_profit_factor",
                             "avg_pnl", "drawdown", "trades", "markets"]
                if c in master_strategy_rank_df.columns
            ]
            if metric_cols_avail:
                selected_metrics = st.multiselect(
                    "Metrics to compare",
                    metric_cols_avail,
                    default=metric_cols_avail[:4],
                )
                if selected_metrics:
                    df_plot = master_strategy_rank_df.copy()
                    df_plot = df_plot.sort_values(
                        selected_metrics[0], ascending=False
                    ).head(20)
                    melted = df_plot.melt(
                        id_vars=["strategy"],
                        value_vars=selected_metrics,
                        var_name="metric",
                        value_name="value",
                    )
                    melted["value"] = pd.to_numeric(melted["value"], errors="coerce")
                    fig = px.bar(
                        melted,
                        x="strategy",
                        y="value",
                        color="metric",
                        barmode="group",
                        title="Strategy Metric Comparison",
                    )
                    fig.update_layout(xaxis_tickangle=-35, height=480)
                    apply_dark_plot(fig)
                    st.plotly_chart(fig, use_container_width=True)

                # Correlation heatmap of metrics
                numeric_df = master_strategy_rank_df[metric_cols_avail].apply(
                    pd.to_numeric, errors="coerce"
                ).dropna()
                if len(numeric_df) > 2:
                    st.markdown("#### Metric Correlation Matrix")
                    corr = numeric_df.corr().round(2)
                    fig_corr = px.imshow(
                        corr,
                        text_auto=True,
                        color_continuous_scale="RdBu",
                        aspect="auto",
                        title="Strategy Metric Correlations",
                    )
                    fig_corr.update_layout(height=420)
                    apply_dark_plot(fig_corr)
                    st.plotly_chart(fig_corr, use_container_width=True)
        else:
            st.warning("No strategy rank data found.")

    # ----------------------------------------------------------
    # 5. Profit Factor Heatmap
    # ----------------------------------------------------------
    elif chart_mode == "Profit Factor Heatmap":
        if not master_pf_matrix_df.empty:
            pf_df = master_pf_matrix_df.copy()
            # First col may be strategy index
            first_col = pf_df.columns[0]
            if first_col.lower() in ["strategy", "unnamed:_0", "unnamed: 0"]:
                pf_df = pf_df.set_index(first_col)
            else:
                pf_df.index.name = "strategy"

            # Numeric coerce
            for c in pf_df.columns:
                pf_df[c] = pd.to_numeric(pf_df[c], errors="coerce")

            # Filter options
            col_filter = st.text_input("Filter symbols (comma-separated, blank = all)", "")
            if col_filter.strip():
                wanted = [s.strip().upper() for s in col_filter.split(",")]
                matched = [c for c in pf_df.columns if any(w in c.upper() for w in wanted)]
                if matched:
                    pf_df = pf_df[matched]

            fig = px.imshow(
                pf_df,
                aspect="auto",
                color_continuous_scale="RdYlGn",
                color_continuous_midpoint=1.0,
                title="Profit Factor — Strategy × Symbol",
                text_auto=".2f",
            )
            fig.update_layout(height=max(350, len(pf_df) * 28 + 100))
            apply_dark_plot(fig)
            st.plotly_chart(fig, use_container_width=True)

            # Best PF per strategy bar
            st.markdown("#### Best Profit Factor per Strategy")
            best_pf = pf_df.max(axis=1).sort_values(ascending=False).reset_index()
            best_pf.columns = ["strategy", "best_pf"]
            fig2 = px.bar(best_pf, x="strategy", y="best_pf",
                          color="best_pf", color_continuous_scale="Teal",
                          text="best_pf", title="Best PF Across All Symbols")
            fig2.update_traces(texttemplate="%{text:.2f}", textposition="outside")
            fig2.update_layout(xaxis_tickangle=-35, height=380)
            apply_dark_plot(fig2)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.warning("No profit factor matrix found. Run Rebuild Master Tables.")

    # ----------------------------------------------------------
    # 6. Average PnL Heatmap
    # ----------------------------------------------------------
    elif chart_mode == "Average PnL Heatmap":
        if not master_avg_pnl_matrix_df.empty:
            pnl_df = master_avg_pnl_matrix_df.copy()
            first_col = pnl_df.columns[0]
            if first_col.lower() in ["strategy", "unnamed:_0", "unnamed: 0"]:
                pnl_df = pnl_df.set_index(first_col)
            else:
                pnl_df.index.name = "strategy"

            for c in pnl_df.columns:
                pnl_df[c] = pd.to_numeric(pnl_df[c], errors="coerce")

            col_filter = st.text_input("Filter symbols (comma-separated, blank = all)", "", key="pnl_filter")
            if col_filter.strip():
                wanted = [s.strip().upper() for s in col_filter.split(",")]
                matched = [c for c in pnl_df.columns if any(w in c.upper() for w in wanted)]
                if matched:
                    pnl_df = pnl_df[matched]

            fig = px.imshow(
                pnl_df,
                aspect="auto",
                color_continuous_scale="RdYlGn",
                color_continuous_midpoint=0.0,
                title="Average PnL — Strategy × Symbol",
                text_auto=".3f",
            )
            fig.update_layout(height=max(350, len(pnl_df) * 28 + 100))
            apply_dark_plot(fig)
            st.plotly_chart(fig, use_container_width=True)

            # Best avg PnL per strategy
            st.markdown("#### Best Avg PnL per Strategy")
            best_pnl = pnl_df.max(axis=1).sort_values(ascending=False).reset_index()
            best_pnl.columns = ["strategy", "best_avg_pnl"]
            fig2 = px.bar(best_pnl, x="strategy", y="best_avg_pnl",
                          color="best_avg_pnl", color_continuous_scale="RdYlGn",
                          color_continuous_midpoint=0,
                          text="best_avg_pnl", title="Best Avg PnL Across All Symbols")
            fig2.update_traces(texttemplate="%{text:.3f}", textposition="outside")
            fig2.update_layout(xaxis_tickangle=-35, height=380)
            apply_dark_plot(fig2)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.warning("No average PnL matrix found. Run Rebuild Master Tables.")

    # ----------------------------------------------------------
    # 7. Win Rate vs Sharpe (Scatter)
    # ----------------------------------------------------------
    elif chart_mode == "Win Rate vs Sharpe (Scatter)":
        src_df = master_strategy_symbol_df if not master_strategy_symbol_df.empty else metrics_df
        if not src_df.empty:
            needed = [c for c in ["sharpe", "winrate"] if c in src_df.columns]
            if len(needed) == 2:
                df_plot = src_df.copy()
                df_plot["sharpe"] = pd.to_numeric(df_plot["sharpe"], errors="coerce")
                df_plot["winrate"] = pd.to_numeric(df_plot["winrate"], errors="coerce")
                df_plot = df_plot.dropna(subset=["sharpe", "winrate"])

                color_by = st.selectbox("Colour by", ["strategy", "symbol"], key="sc_color")
                size_col = next((c for c in ["trades", "profit_factor"] if c in df_plot.columns), None)

                fig = px.scatter(
                    df_plot,
                    x="winrate",
                    y="sharpe",
                    color=color_by if color_by in df_plot.columns else None,
                    size=df_plot[size_col].fillna(1).clip(1).astype(float) if size_col else None,
                    hover_data=[c for c in ["strategy", "symbol", "profit_factor", "trades"] if c in df_plot.columns],
                    title="Win Rate vs Sharpe Ratio",
                )
                # Reference lines
                fig.add_hline(y=1.0, line_dash="dash", line_color="#4d6880",
                              annotation_text="Sharpe 1.0", annotation_position="right")
                fig.add_vline(x=0.5, line_dash="dash", line_color="#4d6880",
                              annotation_text="50% WR", annotation_position="top")
                fig.update_layout(height=520)
                apply_dark_plot(fig)
                st.plotly_chart(fig, use_container_width=True)

                # Quadrant summary
                q_deploy = df_plot[(df_plot["sharpe"] >= 1.0) & (df_plot["winrate"] >= 0.5)]
                q_mixed  = df_plot[(df_plot["sharpe"] >= 1.0) & (df_plot["winrate"] < 0.5)]
                q_watch  = df_plot[(df_plot["sharpe"] < 1.0)  & (df_plot["winrate"] >= 0.5)]
                q_reject = df_plot[(df_plot["sharpe"] < 1.0)  & (df_plot["winrate"] < 0.5)]

                qa, qb, qc, qd = st.columns(4)
                qa.metric("✅ Deploy Zone",   len(q_deploy), help="Sharpe ≥1.0 & WR ≥50%")
                qb.metric("⚠️ High Sharpe",   len(q_mixed),  help="Sharpe ≥1.0 but WR <50%")
                qc.metric("🔶 High WR",       len(q_watch),  help="WR ≥50% but Sharpe <1.0")
                qd.metric("❌ Reject Zone",   len(q_reject), help="Sharpe <1.0 & WR <50%")
            else:
                st.info("Need both 'sharpe' and 'winrate' columns in the master table.")
        else:
            st.warning("No data available for scatter chart.")

    # ----------------------------------------------------------
    # 8. Equity Curve
    # ----------------------------------------------------------
    elif chart_mode == "Equity Curve":
        if equity_is_real:
            st.success("Showing real equity curve from trade_results.csv")
            fig = px.line(
                trade_results_df,
                x="plot_date",
                y="equity",
                title="Real Portfolio Equity Curve",
            )
            fig.update_traces(line_color="#00e676", line_width=1.8)
            fig.add_hline(y=trade_results_df["equity"].iloc[0],
                          line_dash="dot", line_color="#4d6880",
                          annotation_text="Start")
            apply_dark_plot(fig)
            st.plotly_chart(fig, use_container_width=True)

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Start Equity",   f"${trade_results_df['equity'].iloc[0]:,.0f}")
            c2.metric("End Equity",     f"${trade_results_df['equity'].iloc[-1]:,.0f}")
            net = trade_results_df["equity"].iloc[-1] - trade_results_df["equity"].iloc[0]
            c3.metric("Net P&L",        f"${net:+,.0f}")
            c4.metric("Total Trades",   len(trade_results_df))
        else:
            st.info("No trade_results.csv yet — showing placeholder equity curve.")
            fig = px.line(equity_df, x="date", y="equity",
                          title="Sample Equity Curve (placeholder)")
            fig.update_traces(line_color="#ffb300", line_width=1.5, line_dash="dot")
            apply_dark_plot(fig)
            st.plotly_chart(fig, use_container_width=True)
            st.caption("This is a generated sample — wire trade_results.csv to see real data.")

    # ----------------------------------------------------------
    # 9. Drawdown
    # ----------------------------------------------------------
    elif chart_mode == "Drawdown":
        if equity_is_real and "drawdown_pct" in trade_results_df.columns:
            fig = px.area(
                trade_results_df,
                x="plot_date",
                y="drawdown_pct",
                title="Portfolio Drawdown (%)",
                color_discrete_sequence=["#ff3d57"],
            )
            fig.update_traces(line_color="#ff3d57", fillcolor="rgba(255,61,87,0.15)")
            fig.update_layout(height=380)
            apply_dark_plot(fig)
            st.plotly_chart(fig, use_container_width=True)

            max_dd = trade_results_df["drawdown_pct"].min()
            st.metric("Max Drawdown", f"{max_dd:.2f}%")
        else:
            st.info("No real trade data available. Connect trade_results.csv to enable drawdown chart.")

    # ----------------------------------------------------------
    # 10. Trades by Strategy
    # ----------------------------------------------------------
    elif chart_mode == "Trades by Strategy":
        if not master_strategy_rank_df.empty and "trades" in master_strategy_rank_df.columns:
            df_t = master_strategy_rank_df.copy()
            df_t["trades"] = pd.to_numeric(df_t["trades"], errors="coerce")
            df_t = df_t.sort_values("trades", ascending=False)

            color_col = "status" if "status" in df_t.columns else None
            fig = px.bar(
                df_t,
                x="strategy",
                y="trades",
                color=color_col,
                text="trades",
                title="Total Trades by Strategy",
                color_discrete_map={
                    "DEPLOY": "#00e676",
                    "FIX": "#ffb300",
                    "REJECT": "#ff3d57",
                    "UNKNOWN": "#4d6880",
                },
            )
            fig.update_traces(texttemplate="%{text:.0f}", textposition="outside")
            fig.update_layout(xaxis_tickangle=-35, height=440)
            apply_dark_plot(fig)
            st.plotly_chart(fig, use_container_width=True)

            # Trades vs Rank Score scatter
            if "rank_score" in df_t.columns:
                st.markdown("#### Trade Count vs Rank Score")
                fig2 = px.scatter(
                    df_t,
                    x="trades",
                    y="rank_score",
                    color=color_col,
                    text="strategy",
                    title="Trade Volume vs Performance Score",
                    color_discrete_map={
                        "DEPLOY": "#00e676",
                        "FIX": "#ffb300",
                        "REJECT": "#ff3d57",
                        "UNKNOWN": "#4d6880",
                    },
                )
                fig2.update_traces(textposition="top center", textfont_size=9)
                fig2.update_layout(height=420)
                apply_dark_plot(fig2)
                st.plotly_chart(fig2, use_container_width=True)
        else:
            st.warning("No trade count data found. Run Rebuild Master Tables.")


# ============================================================
# PAGE: Reports
# ============================================================

elif page == "Reports":
    st.subheader("Reports Hub")
    report_type = st.selectbox("Report Folder", ["daily", "weekly", "social", "x_reports", "reddit_reports", "macro", "earnings", "strategy_reviews"])
    target_dir = REPORTS_DIR / report_type
    uploaded_reports = st.file_uploader("Upload report files", accept_multiple_files=True, type=None, key="report_uploader")

    if uploaded_reports and st.button("Save uploaded reports"):
        for f in uploaded_reports:
            save_uploaded_file(f, target_dir)
        st.success(f"Saved {len(uploaded_reports)} file(s) to {target_dir}")

    files = list_files_recursive(target_dir)
    st.markdown(f"### 📚 {report_type.replace('_', ' ').title()} Reports")
    if files:
        selected_report = st.selectbox("Open report", [f.name for f in files])
        selected_path = next((f for f in files if f.name == selected_report), None)
        if selected_path:
            st.markdown(f"**File:** `{selected_path}`")
            if selected_path.suffix.lower() in [".txt", ".md", ".json", ".csv", ".log"]:
                if selected_path.suffix.lower() == ".csv":
                    df = safe_read_csv(selected_path)
                    if not df.empty:
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    else:
                        st.code(read_text_file(selected_path))
                else:
                    st.code(read_text_file(selected_path))
            else:
                with open(selected_path, "rb") as f:
                    st.download_button("Download file", data=f.read(), file_name=selected_path.name)
    else:
        st.info("No report files in this folder yet.")

    counts = [{"folder": d.name, "files": len(list_files_recursive(d))} for d in REPORT_SUBDIRS]
    fig = px.bar(pd.DataFrame(counts), x="folder", y="files", text="files", title="Report Library Size")
    fig.update_traces(textposition="outside")
    apply_dark_plot(fig)
    st.plotly_chart(fig, use_container_width=True)


# ============================================================
# PAGE: Social Sentiment
# ============================================================

elif page == "Social Sentiment":
    st.subheader("Social Sentiment Hub")
    left, right = st.columns(2)

    with left:
        st.markdown("### 𝕏 / X Reports")
        x_upload = st.file_uploader("Upload X report CSV", type=["csv"], key="x_csv")
        if x_upload is not None and st.button("Save X report CSV"):
            save_uploaded_file(x_upload, SOCIAL_DIR)
            saved = SOCIAL_DIR / x_upload.name
            if saved.name != SOCIAL_X_CSV.name:
                shutil.copy(saved, SOCIAL_X_CSV)
            st.success("Saved X report CSV.")
            st.rerun()

        if not social_x_df.empty:
            st.dataframe(social_x_df, use_container_width=True, hide_index=True)
        else:
            st.info("No x_reports.csv loaded yet.")

    with right:
        st.markdown("### Reddit Reports")
        reddit_upload = st.file_uploader("Upload Reddit report CSV", type=["csv"], key="reddit_csv")
        if reddit_upload is not None and st.button("Save Reddit report CSV"):
            save_uploaded_file(reddit_upload, SOCIAL_DIR)
            saved = SOCIAL_DIR / reddit_upload.name
            if saved.name != SOCIAL_REDDIT_CSV.name:
                shutil.copy(saved, SOCIAL_REDDIT_CSV)
            st.success("Saved Reddit report CSV.")
            st.rerun()

        if not social_reddit_df.empty:
            st.dataframe(social_reddit_df, use_container_width=True, hide_index=True)
        else:
            st.info("No reddit_reports.csv loaded yet.")

    combined_social = []
    if not social_x_df.empty:
        tmp = social_x_df.copy()
        tmp["source"] = "x"
        combined_social.append(tmp)
    if not social_reddit_df.empty:
        tmp = social_reddit_df.copy()
        tmp["source"] = "reddit"
        combined_social.append(tmp)

    if combined_social:
        social_df = pd.concat(combined_social, ignore_index=True, sort=False)
        st.markdown("### 💬 Combined Sentiment View")
        st.dataframe(social_df, use_container_width=True, hide_index=True)
        symbol_col = next((c for c in ["symbol", "ticker", "asset"] if c in social_df.columns), None)
        score_col = next((c for c in ["sentiment_score", "score", "mentions", "bullish_score"] if c in social_df.columns), None)
        if symbol_col and score_col:
            social_df[score_col] = pd.to_numeric(social_df[score_col], errors="coerce")
            chart_df = social_df.groupby(symbol_col, as_index=False)[score_col].sum().sort_values(score_col, ascending=False).head(15)
            fig = px.bar(chart_df, x=symbol_col, y=score_col, title="Top Social Symbols")
            apply_dark_plot(fig)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Upload X and/or Reddit report CSV files to start sentiment tracking.")


# ============================================================
# PAGE: Backtests
# ============================================================

elif page == "Backtests":
    st.subheader("Backtest Analytics")
    if metrics_df.empty:
        st.warning("No metrics.csv files found in output/backtest/")
    else:
        strategy_options = sorted(metrics_df["strategy"].dropna().astype(str).unique().tolist()) if "strategy" in metrics_df.columns else []
        selected = st.multiselect("Filter strategies", strategy_options, default=strategy_options)
        filtered = metrics_df.copy()
        if selected and "strategy" in filtered.columns:
            filtered = filtered[filtered["strategy"].astype(str).isin(selected)]

        left, right = st.columns(2)
        with left:
            if "sharpe" in filtered.columns and "strategy" in filtered.columns:
                fig = px.box(filtered, x="strategy", y="sharpe", color="strategy", title="Sharpe Distribution")
                apply_dark_plot(fig)
                st.plotly_chart(fig, use_container_width=True)
        with right:
            if "winrate" in filtered.columns and "strategy" in filtered.columns:
                tmp = filtered.copy()
                tmp["winrate_pct"] = tmp["winrate"] * 100
                fig = px.box(tmp, x="strategy", y="winrate_pct", color="strategy", title="Win Rate Distribution")
                apply_dark_plot(fig)
                st.plotly_chart(fig, use_container_width=True)

        left, right = st.columns(2)
        with left:
            if "drawdown" in filtered.columns and "strategy" in filtered.columns:
                dd = filtered.groupby("strategy", as_index=False)["drawdown"].mean()
                dd["drawdown_pct"] = dd["drawdown"] * 100
                fig = px.bar(dd, x="strategy", y="drawdown_pct", color="strategy", text="drawdown_pct", title="Avg Max Drawdown (%)")
                fig.update_traces(texttemplate="%{text:.2f}", textposition="outside")
                apply_dark_plot(fig)
                st.plotly_chart(fig, use_container_width=True)
        with right:
            if "trades" in filtered.columns and "strategy" in filtered.columns:
                tr = filtered.groupby("strategy", as_index=False)["trades"].mean()
                fig = px.bar(tr, x="strategy", y="trades", color="strategy", text="trades", title="Avg Trades by Strategy")
                fig.update_traces(texttemplate="%{text:.0f}", textposition="outside")
                apply_dark_plot(fig)
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("### 🏆 Strategy Leaderboard")
        if not strategy_leaderboard_df.empty:
            cols = [c for c in ["strategy", "score", "sharpe", "sortino", "winrate_pct", "drawdown_pct", "trades", "profit_factor"] if c in strategy_leaderboard_df.columns]
            st.dataframe(strategy_leaderboard_df[cols], use_container_width=True, hide_index=True)

        if not leaderboard_csv_df.empty:
            st.markdown("### Validation Leaderboard File")
            st.dataframe(leaderboard_csv_df, use_container_width=True, hide_index=True)


# ============================================================
# PAGE: Journal
# ============================================================

elif page == "Journal":
    st.subheader("Trade Journal & Results")
    if journal_df.empty:
        st.info("No journal file found. Supported: output/trade_results.csv, output/journal/trades.csv")
    else:
        st.dataframe(journal_df, use_container_width=True, hide_index=True)
        pnl_col = next((c for c in ["pnl", "profit", "net_pnl", "realized_pnl"] if c in journal_df.columns), None)
        if pnl_col:
            journal_df[pnl_col] = pd.to_numeric(journal_df[pnl_col], errors="coerce").fillna(0.0)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total P&L", fmt_num(journal_df[pnl_col].sum()))
            c2.metric("Avg Trade", fmt_num(journal_df[pnl_col].mean()))
            c3.metric("Trades", fmt_int(len(journal_df)))
            c4.metric("Winners", fmt_int((journal_df[pnl_col] > 0).sum()))

            chart_df = journal_df.reset_index().rename(columns={"index": "trade_no"})
            fig = px.bar(chart_df, x="trade_no", y=pnl_col, title="Trade-by-Trade P&L")
            apply_dark_plot(fig)
            st.plotly_chart(fig, use_container_width=True)

            if "strategy" in journal_df.columns:
                sp = journal_df.groupby("strategy", as_index=False)[pnl_col].sum()
                fig2 = px.bar(sp, x="strategy", y=pnl_col, color="strategy", text=pnl_col, title="P&L by Strategy")
                fig2.update_traces(texttemplate="%{text:.2f}", textposition="outside")
                apply_dark_plot(fig2)
                st.plotly_chart(fig2, use_container_width=True)

        if equity_is_real:
            left, right = st.columns(2)
            with left:
                fig = px.line(trade_results_df, x="plot_date", y="equity", title="Real Equity Curve")
                apply_dark_plot(fig)
                st.plotly_chart(fig, use_container_width=True)
            with right:
                fig = px.area(trade_results_df, x="plot_date", y="drawdown_pct", title="Real Drawdown (%)")
                apply_dark_plot(fig)
                st.plotly_chart(fig, use_container_width=True)


# ============================================================
# PAGE: Uploads
# ============================================================

elif page == "Uploads":
    st.subheader("Image Uploads & Trade Review")
    upload_type = st.selectbox("Upload category", ["market_images", "trade_images", "annotated_charts"])
    target_dir = UPLOADS_DIR / upload_type
    symbol_tag = st.text_input("Symbol tag")
    strategy_tag = st.text_input("Strategy tag")
    note_tag = st.text_area("Notes for these uploads")
    uploaded_images = st.file_uploader("Upload images", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True, key="image_uploader")

    if uploaded_images and st.button("Save images"):
        meta_path = target_dir / "metadata.csv"
        for f in uploaded_images:
            saved = save_uploaded_file(f, target_dir)
            append_row_csv(
                meta_path,
                {
                    "timestamp": datetime.now().isoformat(),
                    "filename": saved.name,
                    "path": str(saved),
                    "symbol": symbol_tag,
                    "strategy": strategy_tag,
                    "notes": note_tag,
                    "category": upload_type,
                },
            )
        st.success(f"Saved {len(uploaded_images)} image(s).")
        st.rerun()

    meta_df = safe_read_csv(target_dir / "metadata.csv")
    if not meta_df.empty:
        st.markdown("### 🖼 Upload Log")
        st.dataframe(meta_df, use_container_width=True, hide_index=True)

    files = list_files_recursive(target_dir, extensions=(".png", ".jpg", ".jpeg", ".webp"))
    if files:
        st.markdown("### Gallery")
        cols = st.columns(3)
        for i, f in enumerate(files):
            with cols[i % 3]:
                st.image(str(f), caption=f.name, use_container_width=True)
    else:
        st.info("No images uploaded yet.")


# ============================================================
# PAGE: Strategy Builder
# ============================================================

elif page == "Strategy Builder":
    st.subheader("Strategy Builder")
    with st.form("strategy_builder_form", clear_on_submit=False):
        col1, col2, col3 = st.columns(3)
        strategy_name = col1.text_input("Strategy Name")
        asset_class = col2.selectbox("Asset Class", ["Stocks", "Indices", "Forex", "Crypto", "Futures", "Options", "ETFs"])
        status = col3.selectbox("Status", ["Draft", "Backtesting", "Paper Trading", "Live", "Retired"])
        timeframe = st.text_input("Timeframe")
        market_condition = st.text_input("Market Condition")
        entry_rules = st.text_area("Entry Rules", height=120)
        exit_rules = st.text_area("Exit Rules", height=120)
        stop_rules = st.text_area("Stop Loss Rules", height=100)
        target_rules = st.text_area("Take Profit Rules", height=100)
        risk_rules = st.text_area("Risk Rules", height=100)
        notes = st.text_area("Strategy Notes", height=120)
        version = st.text_input("Version", value="1.0")
        submitted = st.form_submit_button("Save Strategy")

    if submitted and strategy_name.strip():
        strategies = load_strategies_store()
        strategies.append(
            {
                "timestamp": datetime.now().isoformat(),
                "strategy_name": strategy_name.strip(),
                "asset_class": asset_class,
                "status": status,
                "timeframe": timeframe,
                "market_condition": market_condition,
                "entry_rules": entry_rules,
                "exit_rules": exit_rules,
                "stop_rules": stop_rules,
                "target_rules": target_rules,
                "risk_rules": risk_rules,
                "notes": notes,
                "version": version,
            }
        )
        safe_write_json(STRATEGIES_JSON, strategies)
        st.success("Strategy saved.")
        st.rerun()

    strategies_store = load_strategies_store()
    if strategies_store:
        strategies_df = pd.DataFrame(strategies_store)
        st.markdown("### 🧠 Saved Strategies")
        st.dataframe(strategies_df, use_container_width=True, hide_index=True)
        names = strategies_df["strategy_name"].astype(str).tolist() if "strategy_name" in strategies_df.columns else []
        if names:
            chosen = st.selectbox("Open strategy detail", [""] + names)
            if chosen:
                st.dataframe(strategies_df[strategies_df["strategy_name"].astype(str) == chosen].T, use_container_width=True)
    else:
        st.info("No saved strategies yet.")


# ============================================================
# PAGE: Governance Notes
# ============================================================

elif page == "Governance Notes":
    st.subheader("Governance Notes")
    note_category = st.selectbox("Note Category", ["strategy_notes", "market_notes", "psychology_notes", "weekly_reviews"])
    note_title = st.text_input("Note Title")
    note_symbol = st.text_input("Symbol / Asset")
    note_body = st.text_area("Write your notes", height=220)

    if st.button("Save Note"):
        if note_title.strip() or note_body.strip():
            notes = load_notes_store()
            notes.append({"timestamp": datetime.now().isoformat(), "category": note_category, "title": note_title, "symbol": note_symbol, "body": note_body})
            safe_write_json(NOTES_JSON, notes)
            note_file = NOTES_DIR / note_category / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{note_title[:40].replace(' ', '_') or 'note'}.md"
            note_file.write_text(note_body, encoding="utf-8")
            st.success("Note saved.")
            st.rerun()

    notes_store = load_notes_store()
    if notes_store:
        notes_df = pd.DataFrame(notes_store)
        st.markdown("### 📝 Saved Governance Notes")
        st.dataframe(notes_df, use_container_width=True, hide_index=True)
        titles = notes_df["title"].fillna("").astype(str).tolist() if "title" in notes_df.columns else []
        selected = st.selectbox("Open note", [""] + titles)
        if selected:
            row = notes_df[notes_df["title"].astype(str) == selected].iloc[0]
            st.markdown(f"### {row.get('title', '')}")
            st.caption(f"{row.get('category', '')} · {row.get('symbol', '')} · {row.get('timestamp', '')}")
            st.write(row.get("body", ""))
    else:
        st.info("No governance notes saved yet.")


# ============================================================
# PAGE: Daily Planner
# ============================================================

elif page == "Daily Planner":
    st.subheader("Daily Planner")
    with st.form("daily_planner_form", clear_on_submit=False):
        planner_date = st.date_input("Planner Date", value=date.today())
        mood = st.text_input("Mood / Readiness")
        news_watch = st.text_area("News / Events To Watch", height=100)
        key_assets = st.text_area("Key Assets Today", height=80)
        setups = st.text_area("A-Grade Setups", height=100)
        daily_risk_cap = st.text_input("Daily Risk Cap")
        no_trade_conditions = st.text_area("No-Trade Conditions", height=100)
        post_review = st.text_area("Post-Market Review", height=100)
        planner_submit = st.form_submit_button("Save Daily Plan")

    if planner_submit:
        planner = load_planner_store()
        planner.append(
            {
                "timestamp": datetime.now().isoformat(),
                "planner_date": str(planner_date),
                "mood": mood,
                "news_watch": news_watch,
                "key_assets": key_assets,
                "setups": setups,
                "daily_risk_cap": daily_risk_cap,
                "no_trade_conditions": no_trade_conditions,
                "post_review": post_review,
            }
        )
        safe_write_json(PLANNER_JSON, planner)
        md_path = PLANNER_DIR / "daily" / f"{planner_date}.md"
        md_path.write_text(
            f"# Daily Planner - {planner_date}\n\n## Mood\n{mood}\n\n## News\n{news_watch}\n\n## Key Assets\n{key_assets}\n\n## Setups\n{setups}\n\n## Risk Cap\n{daily_risk_cap}\n\n## No-Trade\n{no_trade_conditions}\n\n## Review\n{post_review}\n",
            encoding="utf-8",
        )
        st.success("Daily plan saved.")
        st.rerun()

    planner_store = load_planner_store()
    if planner_store:
        st.markdown("### 📅 Saved Daily Plans")
        st.dataframe(pd.DataFrame(planner_store), use_container_width=True, hide_index=True)
    else:
        st.info("No daily plans saved yet.")


# ============================================================
# PAGE: Calendar
# ============================================================

elif page == "Calendar":
    st.subheader("Working Calendar")
    with st.form("calendar_form", clear_on_submit=False):
        event_date = st.date_input("Event Date", value=date.today(), key="calendar_date")
        title = st.text_input("Event Title")
        category = st.selectbox("Category", ["Trading Day", "Macro Event", "Earnings", "Planner", "Review", "Backtest", "Reminder", "Other"])
        asset = st.text_input("Asset / Symbol")
        notes = st.text_area("Notes", height=100)
        event_submit = st.form_submit_button("Add Calendar Event")

    if event_submit and title.strip():
        append_row_csv(
            CALENDAR_CSV,
            {
                "event_date": str(event_date),
                "title": title,
                "category": category,
                "asset": asset,
                "notes": notes,
                "created_at": datetime.now().isoformat(),
            },
        )
        st.success("Calendar event added.")
        st.rerun()

    calendar_df = load_calendar_store()
    if not calendar_df.empty:
        if "event_date" in calendar_df.columns:
            calendar_df["event_date"] = pd.to_datetime(calendar_df["event_date"], errors="coerce")
            calendar_df = calendar_df.sort_values("event_date")

        st.markdown("### 🗓 Calendar Events")
        st.dataframe(calendar_df, use_container_width=True, hide_index=True)

        if "event_date" in calendar_df.columns and "category" in calendar_df.columns:
            chart_df = calendar_df.copy()
            chart_df["count"] = 1
            grouped = chart_df.groupby([chart_df["event_date"].dt.date, "category"], as_index=False)["count"].sum()
            grouped.columns = ["event_date", "category", "count"]
            fig = px.bar(grouped, x="event_date", y="count", color="category", title="Calendar Activity")
            apply_dark_plot(fig)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No calendar events yet.")


# ============================================================
# PAGE: Platform Vision
# ============================================================

elif page == "Platform Vision":
    st.subheader("RAGE Engine — Platform Vision")
    st.markdown(
        """
### Current state
- V3 core: scanner, backtest, allocator, dashboard — all major pages working
- V4 layer: live market intel (yfinance), sector heatmap, top movers, enriched watchlist, symbol detail cards, news slots
- Ticker tape on every page when live data is loaded
- Architecture: Option B — live prices (yfinance) and strategy signals (CSVs) coexist
- Master performance tables wired into the app

### Next build targets
- Broker API connection (IBKR / Alpaca)
- Order execution panel
- Live positions monitor + account balance sync
- NewsAPI / RSS wired into news slots
- Social data pipelines (X, Reddit)
- Strategy encyclopedia pages
- Options chain viewer
- Crypto / futures cross-asset scanner
- Execution Engine v1 full backtest integration
"""
    )

    left, right = st.columns(2)
    with left:
        st.markdown(
            """
### Core modules
- **Scanner** — signal generation
- **Backtester** — walk-forward engine
- **Allocator** — Kelly / Monte Carlo
- **Journal** — P&L tracking
- **Portfolio** — multi-asset view
- **Broker Execution** — order layer
- **Education Hub** — strategy encyclopedia
- **Strategy Builder** — rules editor
- **Planner & Calendar** — daily workflow
"""
        )
    with right:
        st.markdown(
            """
### V4 live intel layer
- **Ticker tape** — macro benchmarks
- **Sector heatmap** — daily heat view
- **Top movers** — gainers / losers
- **Enriched watchlist** — MCap, P/E, Beta, 52W range
- **Symbol detail cards** — 30d sparkline, financials
- **News feed slots** — macro / sentiment
- **market_intel.py** — standalone yfinance module
- **RAGE Control Panel** — winners + losers + execution roadmap
"""
        )

    mock_df = alloc_df.copy()
    if mock_df.empty:
        mock_df = pd.DataFrame(
            {
                "strategy": ["mean_reversion", "macd_rsi", "adx_trend", "orb"],
                "decision": ["DEPLOY", "DEPLOY", "REJECT", "REJECT"],
                "risk_per_trade_pct": [2.0, 1.0, 0.0, 0.0],
            }
        )
    if "risk_per_trade_pct" in mock_df.columns:
        fig = px.bar(
            mock_df,
            x="strategy",
            y="risk_per_trade_pct",
            color="decision" if "decision" in mock_df.columns else None,
            text="risk_per_trade_pct",
            title="Broker-Facing Risk Allocation View",
        )
        fig.update_traces(texttemplate="%{text:.2f}", textposition="outside")
        apply_dark_plot(fig)
        st.plotly_chart(fig, use_container_width=True)


# ============================================================
# PAGE: Trade Journal (V2 — AI-powered)
# ============================================================

elif page == "Trade Journal":
    if JOURNAL_V2_AVAILABLE:
        journal_v2 = TradeJournal()
        journal_v2.render_page()
    else:
        st.subheader("📓 Trade Journal")
        st.info(
            "trade_journal.py not found. "
            "Drop it into scanner_v2/ and restart the dashboard."
        )


# ============================================================
# PAGE: Performance Dashboard
# ============================================================

elif page == "Performance":
    if PERF_DASHBOARD_AVAILABLE:
        render_performance_page()
    else:
        st.subheader("📈 Performance")
        st.info(
            "performance_dashboard.py not found. "
            "Drop it into scanner_v2/ and restart the dashboard."
        )


# ============================================================
# PAGE: Portfolio Heat Map
# ============================================================

elif page == "Portfolio Heat":
    st.subheader("🌡️ Portfolio Heat Map")
    if PORTFOLIO_HEAT_AVAILABLE:
        equity = 100_000.0
        positions = []

        # Try to get live positions from broker
        if st.session_state.get("broker_connected") and st.session_state.get("broker"):
            try:
                positions = st.session_state["broker"].get_positions()
                acct = st.session_state["broker"].get_account_info()
                equity = acct.equity if acct.connected else equity
            except Exception:
                pass

        ph = PortfolioHeat(equity=equity)
        ph.update(positions, equity)
        ph.render()

        if not positions:
            st.info(
                "Connect Alpaca broker on the Live Signals page "
                "to see real-time portfolio heat."
            )
    else:
        st.info(
            "portfolio_heat.py not found. "
            "Drop it into scanner_v2/ and restart the dashboard."
        )


# ============================================================
# PAGE: Monte Carlo
# ============================================================

elif page == "Monte Carlo":
    st.subheader("🎲 Monte Carlo Simulation")
    if MONTE_CARLO_AVAILABLE:
        mc = MonteCarlo(runs=1_000)

        # Try to load R-multiples from trade log
        r_multiples = []
        trade_log_paths = [
            OUTPUT_DIR / "trades" / "closed_trades.csv",
            OUTPUT_DIR / "journal" / "trades.csv",
            TRADE_RESULTS_CSV,
        ]
        for path in trade_log_paths:
            if path.exists():
                try:
                    df_mc = pd.read_csv(path)
                    r_col = next((c for c in ["r_multiple", "r_mult", "r"]
                                  if c in df_mc.columns), None)
                    if r_col:
                        r_multiples = df_mc[r_col].dropna().tolist()
                        st.success(f"Loaded {len(r_multiples)} trades from {path.name}")
                        break
                except Exception:
                    pass

        if not r_multiples:
            st.info(
                "No closed trade R-multiples found yet. "
                "Using demo data (50 trades, 55% WR, avg R=0.4)."
            )
            import numpy as np
            rng = np.random.default_rng(42)
            r_multiples = list(
                rng.choice([1.5, 2.0, -1.0, 0.5, -0.8, 2.5, -1.0, 1.0],
                           size=50, p=[0.15,0.10,0.25,0.10,0.15,0.05,0.10,0.10])
            )

        col1, col2 = st.columns(2)
        runs = col1.slider("Simulation runs", 500, 5_000, 1_000, 500)
        risk_pct = col2.slider("Risk per trade (%)", 0.25, 3.0, 1.0, 0.25) / 100

        if st.button("▶ Run Simulation", type="primary"):
            with st.spinner("Running Monte Carlo..."):
                result = mc.run(
                    r_multiples,
                    starting_equity=100_000,
                    risk_pct=risk_pct,
                    runs=runs,
                    store_paths=True,
                )
            mc.render(result)
            st.code(result.summary())
    else:
        st.info(
            "monte_carlo.py not found. "
            "Drop it into scanner_v2/ and restart the dashboard."
        )


# ============================================================
# Raw debug
# ============================================================

if show_raw:
    st.markdown("---")
    st.markdown("### Raw Data Debug")
    st.write("Allocator", alloc_df)
    st.write("Metrics", metrics_df)
    st.write("Signals", signals_df)
    st.write("Watchlist", watchlist_df)
    st.write("Alerts", alerts_df)
    st.write("Journal", journal_df)
    st.write("Trade Results", trade_results_df)
    st.write("Strategies Store", strategies_store)
    st.write("Notes Store", notes_store)
    st.write("Planner Store", planner_store)
    st.write("Calendar", calendar_df)
    st.write("Social X", social_x_df)
    st.write("Social Reddit", social_reddit_df)
    st.write("Market Overview", market_overview_csv)
    st.write("Market Intel", intel)
    st.write("Master Strategy Symbol", master_strategy_symbol_df)
    st.write("Master Strategy Rank", master_strategy_rank_df)
    st.write("Master Symbol Rank", master_symbol_rank_df)
    st.write("Master Profit Factor Matrix", master_pf_matrix_df)
    st.write("Master Avg PnL Matrix", master_avg_pnl_matrix_df)