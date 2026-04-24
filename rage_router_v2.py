import os
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf


# ============================================================
# CONFIG
# ============================================================

SYMBOLS = [
    "AAPL",
    "TSLA",
    "NVDA",
    "MSFT",
    "AMZN",
    "BTC-USD",
    "ETH-USD",
    "GBPUSD=X",
    "EURUSD=X",
    "GC=F",
    "CL=F",
]

FX_SYMBOLS = {"GBPUSD=X", "EURUSD=X"}

OUTPUT_DIR = "output"

# MTF engine intervals
BIAS_INTERVAL = "60m"
SETUP_INTERVAL = "15m"
TRIGGER_INTERVAL = "5m"

BIAS_PERIOD = "60d"
SETUP_PERIOD = "60d"
TRIGGER_PERIOD = "30d"

# FX engine interval
FX_INTERVAL = "15m"
FX_PERIOD = "60d"

# General
MIN_BARS_REQUIRED = 120


# ============================================================
# UTILS
# ============================================================

def ensure_output_dir() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]
    return df


def safe_download(symbol: str, period: str, interval: str) -> pd.DataFrame:
    df = yf.download(
        symbol,
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False,
        prepost=False,
    )

    if df is None or df.empty:
        return pd.DataFrame()

    df = flatten_columns(df)

    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(df.columns):
        return pd.DataFrame()

    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.dropna(inplace=True)
    df.sort_index(inplace=True)
    return df


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    prev_close = df["Close"].shift(1)
    tr1 = df["High"] - df["Low"]
    tr2 = (df["High"] - prev_close).abs()
    tr3 = (df["Low"] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def compute_profit_factor(trades_df: pd.DataFrame) -> float:
    if trades_df.empty:
        return 0.0

    wins_df = trades_df[trades_df["pnl_pct"] > 0]
    losses_df = trades_df[trades_df["pnl_pct"] < 0]

    gross_profit = float(wins_df["pnl_pct"].sum()) if not wins_df.empty else 0.0
    gross_loss = float(abs(losses_df["pnl_pct"].sum())) if not losses_df.empty else 0.0

    if gross_loss == 0:
        return 999.0 if gross_profit > 0 else 0.0

    return gross_profit / gross_loss


def build_summary(symbol: str, trades_df: pd.DataFrame) -> dict:
    if trades_df.empty:
        return {
            "symbol": symbol,
            "trades": 0,
            "wins": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "avg_pnl": 0.0,
            "profit_factor": 0.0,
        }

    wins = int((trades_df["pnl_pct"] > 0).sum())

    return {
        "symbol": symbol,
        "trades": int(len(trades_df)),
        "wins": wins,
        "win_rate": float((wins / len(trades_df)) * 100.0),
        "total_pnl": float(trades_df["pnl_pct"].sum()),
        "avg_pnl": float(trades_df["pnl_pct"].mean()),
        "profit_factor": float(compute_profit_factor(trades_df)),
    }


def print_symbol_result(engine_name: str, symbol: str, trades_df: pd.DataFrame, summary: dict) -> None:
    print(f"\n{'=' * 70}")
    print(f"RAGE ENGINE — {engine_name} — {symbol}")
    print(f"{'=' * 70}")

    if trades_df.empty:
        print("No trades generated")
        return

    print(f"Total Trades:  {summary['trades']}")
    print(f"Win Rate:      {summary['win_rate']:.1f}%")
    print(f"Total P&L:     {summary['total_pnl']:.2f}%")
    print(f"Avg P&L:       {summary['avg_pnl']:.2f}%")
    print(f"Profit Factor: {summary['profit_factor']:.2f}")
    print("\n--- ALL TRADES ---")
    print(trades_df.to_string(index=False))


def align_last_row_before(ts: pd.Timestamp, df: pd.DataFrame) -> Optional[pd.Series]:
    eligible = df[df.index <= ts]
    if eligible.empty:
        return None
    return eligible.iloc[-1]


def score_trade(
    volume_multiple: float,
    signal_strength_atr: float,
    trend_distance_atr: float,
    retest_quality: float,
) -> float:
    vm = 0.0 if pd.isna(volume_multiple) else min(volume_multiple, 4.0)
    ss = 0.0 if pd.isna(signal_strength_atr) else min(signal_strength_atr, 4.0)
    td = 0.0 if pd.isna(trend_distance_atr) else min(trend_distance_atr, 4.0)
    rq = 0.0 if pd.isna(retest_quality) else min(max(retest_quality, 0.0), 1.0)

    score = (
        vm * 25.0 +
        ss * 20.0 +
        td * 15.0 +
        rq * 20.0
    )
    return float(score)


# ============================================================
# DATA LOADING
# ============================================================

def load_non_fx_symbol_data(symbol: str) -> Optional[Dict[str, pd.DataFrame]]:
    df_1h = safe_download(symbol, BIAS_PERIOD, BIAS_INTERVAL)
    df_15m = safe_download(symbol, SETUP_PERIOD, SETUP_INTERVAL)
    df_5m = safe_download(symbol, TRIGGER_PERIOD, TRIGGER_INTERVAL)

    if df_1h.empty or df_15m.empty or df_5m.empty:
        return None

    if len(df_1h) < MIN_BARS_REQUIRED or len(df_15m) < MIN_BARS_REQUIRED or len(df_5m) < MIN_BARS_REQUIRED:
        return None

    return {"1h": df_1h, "15m": df_15m, "5m": df_5m}


def load_fx_symbol_data(symbol: str) -> Optional[pd.DataFrame]:
    df = safe_download(symbol, FX_PERIOD, FX_INTERVAL)
    if df.empty or len(df) < MIN_BARS_REQUIRED:
        return None
    return df


# ============================================================
# MTF V2 FEATURE BUILDERS
# ============================================================

def prepare_bias_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = out["Close"].ewm(span=20, adjust=False).mean()
    out["ema_slow"] = out["Close"].ewm(span=50, adjust=False).mean()
    out["atr"] = calculate_atr(out, 14)
    out["trend_distance_atr"] = np.where(
        out["atr"] > 0,
        (out["ema_fast"] - out["ema_slow"]).abs() / out["atr"],
        np.nan,
    )
    return out


def prepare_setup_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = out["Close"].ewm(span=20, adjust=False).mean()
    out["ema_slow"] = out["Close"].ewm(span=50, adjust=False).mean()
    out["atr"] = calculate_atr(out, 14)
    out["vol_avg"] = out["Volume"].rolling(20).mean()
    out["prior_high"] = out["High"].rolling(20).max().shift(1)
    out["prior_low"] = out["Low"].rolling(20).min().shift(1)
    out["range"] = out["High"] - out["Low"]
    out["body"] = (out["Close"] - out["Open"]).abs()
    out["body_ratio"] = np.where(out["range"] > 0, out["body"] / out["range"], 0.0)
    return out


def prepare_trigger_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["ema_fast"] = out["Close"].ewm(span=9, adjust=False).mean()
    out["ema_slow"] = out["Close"].ewm(span=21, adjust=False).mean()
    out["atr"] = calculate_atr(out, 14)
    out["vol_avg"] = out["Volume"].rolling(20).mean()
    out["recent_high"] = out["High"].rolling(12).max().shift(1)
    out["recent_low"] = out["Low"].rolling(12).min().shift(1)
    out["range"] = out["High"] - out["Low"]
    out["body"] = (out["Close"] - out["Open"]).abs()
    out["body_ratio"] = np.where(out["range"] > 0, out["body"] / out["range"], 0.0)
    out["momentum_up"] = out["Close"] - out["Close"].shift(5)
    out["momentum_down"] = out["Close"].shift(5) - out["Close"]
    return out


# ============================================================
# MTF V2 ENGINE
# ============================================================

def get_hour_bias(row_1h: pd.Series) -> Tuple[str, float]:
    if row_1h is None:
        return "neutral", np.nan

    needed = ["ema_fast", "ema_slow", "atr", "Close", "trend_distance_atr"]
    if any(pd.isna(row_1h[col]) for col in needed):
        return "neutral", np.nan

    bullish = row_1h["ema_fast"] > row_1h["ema_slow"] and row_1h["Close"] > row_1h["ema_fast"]
    bearish = row_1h["ema_fast"] < row_1h["ema_slow"] and row_1h["Close"] < row_1h["ema_fast"]

    if bullish:
        return "long", float(row_1h["trend_distance_atr"])
    if bearish:
        return "short", float(row_1h["trend_distance_atr"])
    return "neutral", float(row_1h["trend_distance_atr"])


def detect_15m_breakout_setup(row_15m: pd.Series, bias: str) -> Optional[dict]:
    if row_15m is None:
        return None

    needed = ["atr", "vol_avg", "prior_high", "prior_low", "body_ratio", "range", "Close", "Open"]
    if any(pd.isna(row_15m[col]) for col in needed):
        return None

    atr = float(row_15m["atr"])
    if atr <= 0:
        return None

    volume_multiple = float(row_15m["Volume"] / row_15m["vol_avg"]) if row_15m["vol_avg"] > 0 else np.nan
    volume_ok = volume_multiple > 1.3
    range_ok = row_15m["range"] > (atr * 0.9)
    body_ok = row_15m["body_ratio"] >= 0.55

    if bias == "long":
        breakout = row_15m["Close"] > row_15m["prior_high"] and row_15m["Close"] > row_15m["Open"]
        if breakout and volume_ok and range_ok and body_ok:
            return {
                "direction": "long",
                "breakout_level": float(row_15m["prior_high"]),
                "setup_atr": atr,
                "setup_volume_multiple": volume_multiple,
                "setup_time": row_15m.name,
            }

    if bias == "short":
        breakout = row_15m["Close"] < row_15m["prior_low"] and row_15m["Close"] < row_15m["Open"]
        if breakout and volume_ok and range_ok and body_ok:
            return {
                "direction": "short",
                "breakout_level": float(row_15m["prior_low"]),
                "setup_atr": atr,
                "setup_volume_multiple": volume_multiple,
                "setup_time": row_15m.name,
            }

    return None


def evaluate_15m_retest(current_15m: pd.Series, pending_setup: dict) -> Optional[dict]:
    if current_15m is None or pending_setup is None:
        return None

    needed = ["atr", "Close", "High", "Low", "Open"]
    if any(pd.isna(current_15m[col]) for col in needed):
        return None

    atr = float(current_15m["atr"])
    if atr <= 0:
        return None

    direction = pending_setup["direction"]
    level = pending_setup["breakout_level"]
    tolerance = atr * 0.35
    reclaim = atr * 0.08

    if direction == "long":
        touched = current_15m["Low"] <= (level + tolerance)
        held = current_15m["Low"] >= (level - atr * 0.25)
        reclaimed = current_15m["Close"] >= (level + reclaim)

        if touched and held and reclaimed:
            penetration = max(0.0, level - float(current_15m["Low"]))
            retest_quality = 1.0 - min(penetration / (atr * 0.5), 1.0)
            return {
                "direction": "long",
                "retest_level": level,
                "retest_quality": float(retest_quality),
                "retest_time": current_15m.name,
            }

    if direction == "short":
        touched = current_15m["High"] >= (level - tolerance)
        held = current_15m["High"] <= (level + atr * 0.25)
        reclaimed = current_15m["Close"] <= (level - reclaim)

        if touched and held and reclaimed:
            penetration = max(0.0, float(current_15m["High"]) - level)
            retest_quality = 1.0 - min(penetration / (atr * 0.5), 1.0)
            return {
                "direction": "short",
                "retest_level": level,
                "retest_quality": float(retest_quality),
                "retest_time": current_15m.name,
            }

    return None


def get_5m_trigger(row_5m: pd.Series, direction: str) -> Optional[dict]:
    if row_5m is None:
        return None

    needed = ["atr", "vol_avg", "recent_high", "recent_low", "body_ratio", "range", "ema_fast", "ema_slow"]
    if any(pd.isna(row_5m[col]) for col in needed):
        return None

    atr = float(row_5m["atr"])
    if atr <= 0:
        return None

    volume_multiple = float(row_5m["Volume"] / row_5m["vol_avg"]) if row_5m["vol_avg"] > 0 else np.nan
    volume_ok = volume_multiple > 1.25
    body_ok = row_5m["body_ratio"] >= 0.60
    range_ok = row_5m["range"] > (atr * 0.75)
    strength = float(row_5m["range"] / atr) if atr > 0 else np.nan

    if direction == "long":
        cond = (
            row_5m["ema_fast"] > row_5m["ema_slow"]
            and row_5m["Close"] > row_5m["Open"]
            and row_5m["Close"] > row_5m["recent_high"]
            and row_5m["momentum_up"] > (atr * 0.35)
            and volume_ok
            and body_ok
            and range_ok
        )
        if cond:
            return {
                "direction": "long",
                "trigger_atr": atr,
                "trigger_volume_multiple": volume_multiple,
                "signal_strength_atr": strength,
            }

    if direction == "short":
        cond = (
            row_5m["ema_fast"] < row_5m["ema_slow"]
            and row_5m["Close"] < row_5m["Open"]
            and row_5m["Close"] < row_5m["recent_low"]
            and row_5m["momentum_down"] > (atr * 0.35)
            and volume_ok
            and body_ok
            and range_ok
        )
        if cond:
            return {
                "direction": "short",
                "trigger_atr": atr,
                "trigger_volume_multiple": volume_multiple,
                "signal_strength_atr": strength,
            }

    return None


def classify_symbol_profile(symbol: str) -> str:
    if symbol in {"BTC-USD", "ETH-USD"}:
        return "crypto"
    if symbol in {"GC=F", "CL=F"}:
        return "commodity"
    return "stock"


def get_profile_risk_params(symbol: str) -> dict:
    profile = classify_symbol_profile(symbol)

    if profile == "crypto":
        return {
            "stop_atr": 1.5,
            "target_r": 2.0,
            "min_trade_score": 90.0,
            "max_hold_bars_5m": 48,
        }

    if profile == "commodity":
        return {
            "stop_atr": 1.4,
            "target_r": 1.9,
            "min_trade_score": 80.0,
            "max_hold_bars_5m": 42,
        }

    return {
        "stop_atr": 1.2,
        "target_r": 1.8,
        "min_trade_score": 75.0,
        "max_hold_bars_5m": 36,
    }


def mtf_rage_v2_strategy(
    symbol: str,
    df_1h: pd.DataFrame,
    df_15m: pd.DataFrame,
    df_5m: pd.DataFrame,
) -> Tuple[pd.DataFrame, dict]:
    bias_df = prepare_bias_df(df_1h)
    setup_df = prepare_setup_df(df_15m)
    trigger_df = prepare_trigger_df(df_5m)

    params = get_profile_risk_params(symbol)
    trades = []

    pending_breakout = None
    pending_retest = None

    in_position = False
    direction = None
    entry_time = None
    entry_price = None
    stop_price = None
    target_price = None
    highest_since_entry = None
    lowest_since_entry = None
    trade_score = None
    setup_volume_multiple = None
    trigger_volume_multiple = None
    signal_strength_atr = None
    trend_distance_atr = None
    retest_quality = None

    start_idx = 100

    for i in range(start_idx, len(trigger_df) - 1):
        ts = trigger_df.index[i]
        row_5m = trigger_df.iloc[i]

        row_1h = align_last_row_before(ts, bias_df)
        row_15m = align_last_row_before(ts, setup_df)

        bias, bias_strength = get_hour_bias(row_1h)
        current_setup = detect_15m_breakout_setup(row_15m, bias)

        if not in_position:
            if current_setup is not None:
                pending_breakout = current_setup
                pending_retest = None

            if pending_breakout is not None:
                same_15m_bar = row_15m.name if row_15m is not None else None
                if same_15m_bar is not None and same_15m_bar > pending_breakout["setup_time"]:
                    maybe_retest = evaluate_15m_retest(row_15m, pending_breakout)
                    if maybe_retest is not None:
                        pending_retest = maybe_retest

            if pending_retest is not None:
                trigger = get_5m_trigger(row_5m, pending_retest["direction"])
            else:
                trigger = None
        else:
            trigger = None

        if not in_position and pending_retest is not None and trigger is not None:
            setup_volume_multiple = float(pending_breakout["setup_volume_multiple"])
            trigger_volume_multiple = float(trigger["trigger_volume_multiple"])
            signal_strength_atr = float(trigger["signal_strength_atr"])
            trend_distance_atr = float(bias_strength)
            retest_quality = float(pending_retest["retest_quality"])

            trade_score = score_trade(
                volume_multiple=(setup_volume_multiple + trigger_volume_multiple) / 2.0,
                signal_strength_atr=signal_strength_atr,
                trend_distance_atr=trend_distance_atr,
                retest_quality=retest_quality,
            )

            if trade_score >= params["min_trade_score"]:
                next_row = trigger_df.iloc[i + 1]
                entry_time = trigger_df.index[i + 1]
                entry_price = float(next_row["Open"])
                direction = trigger["direction"]

                trigger_atr = float(trigger["trigger_atr"])

                if direction == "long":
                    stop_price = entry_price - (trigger_atr * params["stop_atr"])
                    risk = entry_price - stop_price
                    target_price = entry_price + (risk * params["target_r"])
                    highest_since_entry = float(next_row["High"])
                    lowest_since_entry = float(next_row["Low"])
                else:
                    stop_price = entry_price + (trigger_atr * params["stop_atr"])
                    risk = stop_price - entry_price
                    target_price = entry_price - (risk * params["target_r"])
                    highest_since_entry = float(next_row["High"])
                    lowest_since_entry = float(next_row["Low"])

                if risk > 0:
                    in_position = True

                pending_breakout = None
                pending_retest = None

        elif not in_position and pending_retest is not None and trigger is None:
            # let the retest stay alive briefly, but kill it if it gets stale
            retest_age_bars = int((ts - pending_retest["retest_time"]) / pd.Timedelta(minutes=5))
            if retest_age_bars > 12:
                pending_breakout = None
                pending_retest = None

        if in_position:
            highest_since_entry = max(highest_since_entry, float(row_5m["High"]))
            lowest_since_entry = min(lowest_since_entry, float(row_5m["Low"]))
            bars_held = int((ts - entry_time) / pd.Timedelta(minutes=5)) if entry_time is not None else 0

            if ts <= entry_time:
                continue

            atr = float(row_5m["atr"]) if not pd.isna(row_5m["atr"]) else 0.0
            if atr <= 0:
                continue

            exit_reason = None
            exit_price = None

            if direction == "long":
                # partial-profit-inspired management via break-even and trail
                if (highest_since_entry - entry_price) >= (atr * 1.0):
                    stop_price = max(stop_price, entry_price)

                trail = highest_since_entry - (atr * 1.0)
                stop_price = max(stop_price, trail)

                stop_hit = float(row_5m["Low"]) <= stop_price
                target_hit = float(row_5m["High"]) >= target_price

                if stop_hit and target_hit:
                    exit_price = stop_price
                    exit_reason = "stop"
                elif stop_hit:
                    exit_price = stop_price
                    exit_reason = "stop"
                elif target_hit:
                    exit_price = target_price
                    exit_reason = "target"
                elif bars_held >= params["max_hold_bars_5m"]:
                    exit_price = float(row_5m["Close"])
                    exit_reason = "time"

            else:
                if (entry_price - lowest_since_entry) >= (atr * 1.0):
                    stop_price = min(stop_price, entry_price)

                trail = lowest_since_entry + (atr * 1.0)
                stop_price = min(stop_price, trail)

                stop_hit = float(row_5m["High"]) >= stop_price
                target_hit = float(row_5m["Low"]) <= target_price

                if stop_hit and target_hit:
                    exit_price = stop_price
                    exit_reason = "stop"
                elif stop_hit:
                    exit_price = stop_price
                    exit_reason = "stop"
                elif target_hit:
                    exit_price = target_price
                    exit_reason = "target"
                elif bars_held >= params["max_hold_bars_5m"]:
                    exit_price = float(row_5m["Close"])
                    exit_reason = "time"

            if exit_reason is not None:
                if direction == "long":
                    pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0
                else:
                    pnl_pct = ((entry_price - exit_price) / entry_price) * 100.0

                trades.append({
                    "symbol": symbol,
                    "engine": "MTF_V2",
                    "entry_time": entry_time,
                    "exit_time": ts,
                    "direction": direction,
                    "entry": float(entry_price),
                    "exit": float(exit_price),
                    "pnl_pct": float(pnl_pct),
                    "result": "WIN" if pnl_pct > 0 else "LOSS",
                    "exit_reason": exit_reason,
                    "bars_held_5m": bars_held,
                    "trade_score": float(trade_score),
                    "setup_volume_multiple": float(setup_volume_multiple),
                    "trigger_volume_multiple": float(trigger_volume_multiple),
                    "signal_strength_atr": float(signal_strength_atr),
                    "trend_distance_atr": float(trend_distance_atr),
                    "retest_quality": float(retest_quality),
                })

                in_position = False
                direction = None
                entry_time = None
                entry_price = None
                stop_price = None
                target_price = None
                highest_since_entry = None
                lowest_since_entry = None
                trade_score = None
                setup_volume_multiple = None
                trigger_volume_multiple = None
                signal_strength_atr = None
                trend_distance_atr = None
                retest_quality = None

    trades_df = pd.DataFrame(trades)
    summary = build_summary(symbol, trades_df)
    return trades_df, summary


# ============================================================
# FX SESSION ENGINE
# ============================================================

def prepare_fx_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["atr"] = calculate_atr(out, 14)
    out["date"] = out.index.date
    out["hour"] = out.index.hour
    out["minute"] = out.index.minute
    return out


def get_day_rows(df: pd.DataFrame, trade_date) -> pd.DataFrame:
    return df[df["date"] == trade_date].copy()


def build_fx_session_windows(day_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    # Asian range: 00:00 to 05:45
    asian = day_df[(day_df["hour"] >= 0) & (day_df["hour"] < 6)].copy()
    # London active search: 06:00 to 11:45
    london = day_df[(day_df["hour"] >= 6) & (day_df["hour"] < 12)].copy()
    return asian, london


def fx_london_breakout_strategy(symbol: str, df: pd.DataFrame) -> Tuple[pd.DataFrame, dict]:
    df = prepare_fx_df(df)
    trades = []

    unique_dates = sorted(pd.Series(df["date"]).unique())

    for day in unique_dates:
        day_df = get_day_rows(df, day)
        if len(day_df) < 20:
            continue

        asian_df, london_df = build_fx_session_windows(day_df)
        if asian_df.empty or london_df.empty:
            continue

        if len(asian_df) < 8:
            continue

        asian_high = float(asian_df["High"].max())
        asian_low = float(asian_df["Low"].min())
        asian_range = asian_high - asian_low
        day_atr = float(day_df["atr"].dropna().iloc[0]) if not day_df["atr"].dropna().empty else np.nan

        if pd.isna(day_atr) or day_atr <= 0:
            continue

        # Skip dead sessions
        if asian_range < day_atr * 0.25:
            continue

        breakout_setup = None
        retest_confirmed = None
        entry_taken = False

        london_rows = london_df.reset_index()

        for i in range(len(london_rows)):
            row = london_rows.iloc[i]
            ts = row["Datetime"] if "Datetime" in london_rows.columns else row[df.index.name or "index"]
            high_price = float(row["High"])
            low_price = float(row["Low"])
            close_price = float(row["Close"])
            open_price = float(row["Open"])
            atr = float(row["atr"]) if not pd.isna(row["atr"]) else day_atr

            if breakout_setup is None:
                long_break = close_price > asian_high + (atr * 0.05)
                short_break = close_price < asian_low - (atr * 0.05)

                if long_break:
                    breakout_setup = {
                        "direction": "long",
                        "level": asian_high,
                        "break_time": ts,
                    }
                    continue

                if short_break:
                    breakout_setup = {
                        "direction": "short",
                        "level": asian_low,
                        "break_time": ts,
                    }
                    continue

            if breakout_setup is not None and retest_confirmed is None:
                direction = breakout_setup["direction"]
                level = breakout_setup["level"]
                bars_since_break = i

                if bars_since_break > 8:
                    break

                if direction == "long":
                    touched = low_price <= level + (atr * 0.10)
                    held = low_price >= level - (atr * 0.20)
                    reclaimed = close_price >= level + (atr * 0.03)

                    if touched and held and reclaimed and close_price > open_price:
                        penetration = max(0.0, level - low_price)
                        retest_quality = 1.0 - min(penetration / (atr * 0.4), 1.0)
                        retest_confirmed = {
                            "direction": "long",
                            "level": level,
                            "confirm_time": ts,
                            "retest_quality": float(retest_quality),
                        }
                        continue

                if direction == "short":
                    touched = high_price >= level - (atr * 0.10)
                    held = high_price <= level + (atr * 0.20)
                    reclaimed = close_price <= level - (atr * 0.03)

                    if touched and held and reclaimed and close_price < open_price:
                        penetration = max(0.0, high_price - level)
                        retest_quality = 1.0 - min(penetration / (atr * 0.4), 1.0)
                        retest_confirmed = {
                            "direction": "short",
                            "level": level,
                            "confirm_time": ts,
                            "retest_quality": float(retest_quality),
                        }
                        continue

            if retest_confirmed is not None and not entry_taken:
                if i + 1 >= len(london_rows):
                    break

                next_row = london_rows.iloc[i + 1]
                entry_time = next_row["Datetime"] if "Datetime" in london_rows.columns else next_row[df.index.name or "index"]
                entry_price = float(next_row["Open"])
                direction = retest_confirmed["direction"]

                if direction == "long":
                    stop_price = entry_price - (atr * 1.0)
                    risk = entry_price - stop_price
                    target_price = entry_price + (risk * 1.8)
                else:
                    stop_price = entry_price + (atr * 1.0)
                    risk = stop_price - entry_price
                    target_price = entry_price - (risk * 1.8)

                if risk <= 0:
                    break

                trade_score = score_trade(
                    volume_multiple=1.0,  # FX volume is not reliable
                    signal_strength_atr=min(asian_range / atr, 4.0),
                    trend_distance_atr=1.0,
                    retest_quality=retest_confirmed["retest_quality"],
                )

                highest_since_entry = float(next_row["High"])
                lowest_since_entry = float(next_row["Low"])
                exit_reason = None
                exit_price = None
                exit_time = None

                # manage inside remaining London session only
                for j in range(i + 2, len(london_rows)):
                    mgr = london_rows.iloc[j]
                    mgr_ts = mgr["Datetime"] if "Datetime" in london_rows.columns else mgr[df.index.name or "index"]
                    mgr_high = float(mgr["High"])
                    mgr_low = float(mgr["Low"])
                    mgr_close = float(mgr["Close"])
                    mgr_atr = float(mgr["atr"]) if not pd.isna(mgr["atr"]) else atr

                    highest_since_entry = max(highest_since_entry, mgr_high)
                    lowest_since_entry = min(lowest_since_entry, mgr_low)
                    bars_held = j - (i + 1)

                    if direction == "long":
                        if (highest_since_entry - entry_price) >= mgr_atr:
                            stop_price = max(stop_price, entry_price)

                        trail = highest_since_entry - mgr_atr
                        stop_price = max(stop_price, trail)

                        stop_hit = mgr_low <= stop_price
                        target_hit = mgr_high >= target_price

                        if stop_hit and target_hit:
                            exit_price = stop_price
                            exit_reason = "stop"
                            exit_time = mgr_ts
                            break
                        elif stop_hit:
                            exit_price = stop_price
                            exit_reason = "stop"
                            exit_time = mgr_ts
                            break
                        elif target_hit:
                            exit_price = target_price
                            exit_reason = "target"
                            exit_time = mgr_ts
                            break
                        elif bars_held >= 12:
                            exit_price = mgr_close
                            exit_reason = "time"
                            exit_time = mgr_ts
                            break

                    else:
                        if (entry_price - lowest_since_entry) >= mgr_atr:
                            stop_price = min(stop_price, entry_price)

                        trail = lowest_since_entry + mgr_atr
                        stop_price = min(stop_price, trail)

                        stop_hit = mgr_high >= stop_price
                        target_hit = mgr_low <= target_price

                        if stop_hit and target_hit:
                            exit_price = stop_price
                            exit_reason = "stop"
                            exit_time = mgr_ts
                            break
                        elif stop_hit:
                            exit_price = stop_price
                            exit_reason = "stop"
                            exit_time = mgr_ts
                            break
                        elif target_hit:
                            exit_price = target_price
                            exit_reason = "target"
                            exit_time = mgr_ts
                            break
                        elif bars_held >= 12:
                            exit_price = mgr_close
                            exit_reason = "time"
                            exit_time = mgr_ts
                            break

                if exit_reason is None:
                    last_mgr = london_rows.iloc[-1]
                    exit_time = last_mgr["Datetime"] if "Datetime" in london_rows.columns else last_mgr[df.index.name or "index"]
                    exit_price = float(last_mgr["Close"])
                    exit_reason = "session_close"

                if direction == "long":
                    pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0
                else:
                    pnl_pct = ((entry_price - exit_price) / entry_price) * 100.0

                trades.append({
                    "symbol": symbol,
                    "engine": "FX_LONDON_BREAKOUT",
                    "entry_time": entry_time,
                    "exit_time": exit_time,
                    "direction": direction,
                    "entry": float(entry_price),
                    "exit": float(exit_price),
                    "pnl_pct": float(pnl_pct),
                    "result": "WIN" if pnl_pct > 0 else "LOSS",
                    "exit_reason": exit_reason,
                    "asian_high": float(asian_high),
                    "asian_low": float(asian_low),
                    "asian_range": float(asian_range),
                    "trade_score": float(trade_score),
                    "retest_quality": float(retest_confirmed["retest_quality"]),
                })

                entry_taken = True
                break

    trades_df = pd.DataFrame(trades)
    summary = build_summary(symbol, trades_df)
    return trades_df, summary


# ============================================================
# ROUTER
# ============================================================

def run_rage_router_v2(symbols: List[str]) -> None:
    all_summaries = []
    all_trades = []

    print("\n" + "=" * 70)
    print("RAGE ENGINE — ROUTER V2")
    print("=" * 70)

    for symbol in symbols:
        try:
            if symbol in FX_SYMBOLS:
                fx_df = load_fx_symbol_data(symbol)
                if fx_df is None:
                    print(f"{symbol}: insufficient FX data")
                    summary = build_summary(symbol, pd.DataFrame())
                    all_summaries.append(summary)
                    continue

                trades_df, summary = fx_london_breakout_strategy(symbol, fx_df)
                print_symbol_result("FX London Breakout", symbol, trades_df, summary)

            else:
                non_fx_data = load_non_fx_symbol_data(symbol)
                if non_fx_data is None:
                    print(f"{symbol}: insufficient MTF data")
                    summary = build_summary(symbol, pd.DataFrame())
                    all_summaries.append(summary)
                    continue

                trades_df, summary = mtf_rage_v2_strategy(
                    symbol=symbol,
                    df_1h=non_fx_data["1h"],
                    df_15m=non_fx_data["15m"],
                    df_5m=non_fx_data["5m"],
                )
                print_symbol_result("MTF V2", symbol, trades_df, summary)

            all_summaries.append(summary)
            if not trades_df.empty:
                all_trades.append(trades_df)

        except Exception as e:
            print(f"{symbol}: ERROR - {e}")
            all_summaries.append(build_summary(symbol, pd.DataFrame()))

    summary_df = pd.DataFrame(all_summaries)

    print(f"\n{'=' * 70}")
    print("RAGE ENGINE — ROUTER V2 SUMMARY")
    print(f"{'=' * 70}")

    if not summary_df.empty:
        print(
            summary_df[
                ["symbol", "trades", "wins", "win_rate", "total_pnl", "avg_pnl", "profit_factor"]
            ].to_string(index=False)
        )

    ensure_output_dir()

    summary_path = os.path.join(OUTPUT_DIR, "rage_router_v2_summary.csv")
    summary_df.to_csv(summary_path, index=False)
    print(f"\nSaved to {summary_path}")

    if all_trades:
        trades_df = pd.concat(all_trades, ignore_index=True)
        trades_path = os.path.join(OUTPUT_DIR, "rage_router_v2_trades.csv")
        trades_df.to_csv(trades_path, index=False)
        print(f"Saved to {trades_path}")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    # -- Windows UTF-8 fix (auto-added by fix_unicode.py) --
    import io as _io
    if hasattr(sys.stdout, "buffer"):
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
    sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

    ensure_output_dir()
    run_rage_router_v2(SYMBOLS)