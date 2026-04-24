import os
from typing import Dict, Tuple

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

PERIOD = "2y"
INTERVAL = "1d"
OUTPUT_DIR = "output"


# ============================================================
# UTILS
# ============================================================

def ensure_output_dir() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def load_market_data(
    symbols: list[str],
    period: str = PERIOD,
    interval: str = INTERVAL,
) -> Dict[str, pd.DataFrame]:
    data_dict: Dict[str, pd.DataFrame] = {}

    for symbol in symbols:
        try:
            df = yf.download(symbol, period=period, interval=interval, auto_adjust=False, progress=False)

            if df is None or df.empty:
                print(f"{symbol}: no data")
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [col[0] for col in df.columns]

            required = {"Open", "High", "Low", "Close", "Volume"}
            if not required.issubset(df.columns):
                print(f"{symbol}: missing columns {required - set(df.columns)}")
                continue

            df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            df.dropna(inplace=True)

            if len(df) < 100:
                print(f"{symbol}: insufficient data")
                continue

            data_dict[symbol] = df

        except Exception as e:
            print(f"{symbol}: data load error - {e}")

    return data_dict


def build_summary(trades_df: pd.DataFrame, symbol: str) -> dict:
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
    wins_df = trades_df[trades_df["pnl_pct"] > 0]
    losses_df = trades_df[trades_df["pnl_pct"] < 0]

    gross_profit = float(wins_df["pnl_pct"].sum()) if not wins_df.empty else 0.0
    gross_loss = float(abs(losses_df["pnl_pct"].sum())) if not losses_df.empty else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 999.0

    return {
        "symbol": symbol,
        "trades": int(len(trades_df)),
        "wins": wins,
        "win_rate": float((wins / len(trades_df)) * 100.0),
        "total_pnl": float(trades_df["pnl_pct"].sum()),
        "avg_pnl": float(trades_df["pnl_pct"].mean()),
        "profit_factor": float(profit_factor),
    }


def print_strategy_result(strategy_name: str, symbol: str, trades_df: pd.DataFrame, summary: dict) -> None:
    print(f"\n{'=' * 70}")
    print(f"RAGE ENGINE — {strategy_name} — {symbol}")
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


def save_strategy_outputs(strategy_slug: str, summaries: list[dict], all_trades: list[pd.DataFrame]) -> None:
    ensure_output_dir()

    summary_df = pd.DataFrame(summaries)

    if not summary_df.empty:
        summary_path = os.path.join(OUTPUT_DIR, f"{strategy_slug}_summary.csv")
        summary_df.to_csv(summary_path, index=False)
        print(f"\nSaved to {summary_path}")

    if all_trades:
        trades_df = pd.concat(all_trades, ignore_index=True)
        trades_path = os.path.join(OUTPUT_DIR, f"{strategy_slug}_trades.csv")
        trades_df.to_csv(trades_path, index=False)
        print(f"Saved to {trades_path}")


# ============================================================
# STRATEGY 1 — BREAKOUT + RETEST
# ============================================================

def breakout_retest_strategy(
    df: pd.DataFrame,
    symbol: str = "UNKNOWN",
    breakout_lookback: int = 20,
    atr_period: int = 14,
    max_retest_bars: int = 8,
    level_tolerance_atr: float = 0.35,
    reclaim_buffer_atr: float = 0.10,
    stop_atr_multiplier: float = 1.0,
    target_atr_multiplier: float = 1.8,
    max_hold_bars: int = 20,
) -> Tuple[pd.DataFrame, dict]:
    df = df.copy()

    df["atr"] = calculate_atr(df, atr_period)
    df["prior_high"] = df["High"].rolling(breakout_lookback).max().shift(1)
    df["prior_low"] = df["Low"].rolling(breakout_lookback).min().shift(1)

    trades = []

    pending_setup = None
    pending_level = None
    pending_breakout_bar = None
    pending_breakout_direction = None

    in_position = False
    direction = None
    entry_price = None
    stop_price = None
    target_price = None
    entry_bar = None
    retests_used = 0

    start_idx = max(breakout_lookback, atr_period) + 5

    for i in range(start_idx, len(df)):
        row = df.iloc[i]

        if pd.isna(row["atr"]) or pd.isna(row["prior_high"]) or pd.isna(row["prior_low"]):
            continue

        atr = row["atr"]
        open_price = row["Open"]
        high_price = row["High"]
        low_price = row["Low"]
        close_price = row["Close"]

        bullish_breakout = close_price > row["prior_high"]
        bearish_breakdown = close_price < row["prior_low"]

        if not in_position and pending_setup is None:
            if bullish_breakout:
                pending_setup = "long"
                pending_level = row["prior_high"]
                pending_breakout_bar = i
                pending_breakout_direction = "long"
                continue

            if bearish_breakdown:
                pending_setup = "short"
                pending_level = row["prior_low"]
                pending_breakout_bar = i
                pending_breakout_direction = "short"
                continue

        if not in_position and pending_setup is not None:
            bars_since_breakout = i - pending_breakout_bar

            if bars_since_breakout > max_retest_bars:
                pending_setup = None
                pending_level = None
                pending_breakout_bar = None
                pending_breakout_direction = None
                continue

            tolerance = atr * level_tolerance_atr
            reclaim_buffer = atr * reclaim_buffer_atr

            if pending_setup == "long":
                touched_level = low_price <= (pending_level + tolerance)
                reclaimed = close_price >= (pending_level + reclaim_buffer)

                if touched_level and reclaimed:
                    entry_price = close_price
                    stop_price = pending_level - (atr * stop_atr_multiplier)
                    risk = entry_price - stop_price

                    if risk > 0:
                        target_price = entry_price + (risk * target_atr_multiplier)
                        entry_bar = i
                        direction = "long"
                        in_position = True
                        retests_used = 1

                    pending_setup = None
                    pending_level = None
                    pending_breakout_bar = None
                    pending_breakout_direction = None

            elif pending_setup == "short":
                touched_level = high_price >= (pending_level - tolerance)
                reclaimed = close_price <= (pending_level - reclaim_buffer)

                if touched_level and reclaimed:
                    entry_price = close_price
                    stop_price = pending_level + (atr * stop_atr_multiplier)
                    risk = stop_price - entry_price

                    if risk > 0:
                        target_price = entry_price - (risk * target_atr_multiplier)
                        entry_bar = i
                        direction = "short"
                        in_position = True
                        retests_used = 1

                    pending_setup = None
                    pending_level = None
                    pending_breakout_bar = None
                    pending_breakout_direction = None

        if in_position:
            bars_held = i - entry_bar
            exit_reason = None
            exit_price = None

            if direction == "long":
                stop_hit = low_price <= stop_price
                target_hit = high_price >= target_price

                if stop_hit and target_hit:
                    exit_price = stop_price
                    exit_reason = "stop"
                elif stop_hit:
                    exit_price = stop_price
                    exit_reason = "stop"
                elif target_hit:
                    exit_price = target_price
                    exit_reason = "target"
                elif bars_held >= max_hold_bars:
                    exit_price = close_price
                    exit_reason = "time"

            elif direction == "short":
                stop_hit = high_price >= stop_price
                target_hit = low_price <= target_price

                if stop_hit and target_hit:
                    exit_price = stop_price
                    exit_reason = "stop"
                elif stop_hit:
                    exit_price = stop_price
                    exit_reason = "stop"
                elif target_hit:
                    exit_price = target_price
                    exit_reason = "target"
                elif bars_held >= max_hold_bars:
                    exit_price = close_price
                    exit_reason = "time"

            if exit_reason is not None:
                if direction == "long":
                    pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0
                else:
                    pnl_pct = ((entry_price - exit_price) / entry_price) * 100.0

                trades.append(
                    {
                        "entry_bar": entry_bar,
                        "exit_bar": i,
                        "direction": direction,
                        "entry": float(entry_price),
                        "exit": float(exit_price),
                        "pnl_pct": float(pnl_pct),
                        "result": "WIN" if pnl_pct > 0 else "LOSS",
                        "retests": retests_used,
                        "exit_reason": exit_reason,
                    }
                )

                in_position = False
                direction = None
                entry_price = None
                stop_price = None
                target_price = None
                entry_bar = None
                retests_used = 0

    trades_df = pd.DataFrame(trades)
    summary = build_summary(trades_df, symbol)
    return trades_df, summary


# ============================================================
# STRATEGY 2 — VOLUME SURGE
# ============================================================

def volume_surge_strategy(
    df: pd.DataFrame,
    symbol: str = "UNKNOWN",
    ema_fast: int = 20,
    ema_slow: int = 50,
    volume_window: int = 20,
    breakout_lookback: int = 20,
    atr_period: int = 14,
    volume_multiplier: float = 1.8,
    range_atr_multiplier: float = 1.2,
    stop_atr_multiplier: float = 1.2,
    target_atr_multiplier: float = 2.4,
    max_hold_bars: int = 12,
    min_body_ratio: float = 0.6,
) -> Tuple[pd.DataFrame, dict]:
    df = df.copy()

    df["ema_fast"] = df["Close"].ewm(span=ema_fast, adjust=False).mean()
    df["ema_slow"] = df["Close"].ewm(span=ema_slow, adjust=False).mean()
    df["atr"] = calculate_atr(df, atr_period)

    df["vol_avg"] = df["Volume"].rolling(volume_window).mean()
    df["prior_high"] = df["High"].rolling(breakout_lookback).max().shift(1)
    df["prior_low"] = df["Low"].rolling(breakout_lookback).min().shift(1)

    df["candle_range"] = df["High"] - df["Low"]
    df["body_size"] = (df["Close"] - df["Open"]).abs()
    df["body_ratio"] = np.where(df["candle_range"] > 0, df["body_size"] / df["candle_range"], 0.0)

    trades = []
    in_position = False
    direction = None
    entry_price = None
    stop_price = None
    target_price = None
    entry_bar = None

    start_idx = max(ema_slow, volume_window, breakout_lookback, atr_period) + 2

    for i in range(start_idx, len(df)):
        row = df.iloc[i]

        if pd.isna(row["atr"]) or pd.isna(row["vol_avg"]) or pd.isna(row["prior_high"]) or pd.isna(row["prior_low"]):
            continue

        open_price = row["Open"]
        high_price = row["High"]
        low_price = row["Low"]
        close_price = row["Close"]
        volume = row["Volume"]
        atr = row["atr"]

        candle_range = row["candle_range"]
        body_ratio = row["body_ratio"]

        trend_up = row["ema_fast"] > row["ema_slow"]
        trend_down = row["ema_fast"] < row["ema_slow"]

        volume_surge = volume > (row["vol_avg"] * volume_multiplier)
        range_expansion = candle_range > (atr * range_atr_multiplier)

        bullish_breakout = close_price > row["prior_high"]
        bearish_breakdown = close_price < row["prior_low"]

        bullish_body = close_price > open_price and body_ratio >= min_body_ratio
        bearish_body = close_price < open_price and body_ratio >= min_body_ratio

        if not in_position:
            long_signal = (
                trend_up
                and volume_surge
                and range_expansion
                and bullish_breakout
                and bullish_body
            )

            short_signal = (
                trend_down
                and volume_surge
                and range_expansion
                and bearish_breakdown
                and bearish_body
            )

            if long_signal:
                in_position = True
                direction = "long"
                entry_price = close_price
                stop_price = entry_price - (atr * stop_atr_multiplier)
                target_price = entry_price + (atr * target_atr_multiplier)
                entry_bar = i

            elif short_signal:
                in_position = True
                direction = "short"
                entry_price = close_price
                stop_price = entry_price + (atr * stop_atr_multiplier)
                target_price = entry_price - (atr * target_atr_multiplier)
                entry_bar = i

        else:
            exit_reason = None
            exit_price = None
            bars_held = i - entry_bar

            if direction == "long":
                stop_hit = low_price <= stop_price
                target_hit = high_price >= target_price

                if stop_hit and target_hit:
                    exit_price = stop_price
                    exit_reason = "stop"
                elif stop_hit:
                    exit_price = stop_price
                    exit_reason = "stop"
                elif target_hit:
                    exit_price = target_price
                    exit_reason = "target"
                elif bars_held >= max_hold_bars:
                    exit_price = close_price
                    exit_reason = "time"

            elif direction == "short":
                stop_hit = high_price >= stop_price
                target_hit = low_price <= target_price

                if stop_hit and target_hit:
                    exit_price = stop_price
                    exit_reason = "stop"
                elif stop_hit:
                    exit_price = stop_price
                    exit_reason = "stop"
                elif target_hit:
                    exit_price = target_price
                    exit_reason = "target"
                elif bars_held >= max_hold_bars:
                    exit_price = close_price
                    exit_reason = "time"

            if exit_reason is not None:
                if direction == "long":
                    pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0
                else:
                    pnl_pct = ((entry_price - exit_price) / entry_price) * 100.0

                trades.append(
                    {
                        "entry_bar": entry_bar,
                        "exit_bar": i,
                        "direction": direction,
                        "entry": float(entry_price),
                        "exit": float(exit_price),
                        "pnl_pct": float(pnl_pct),
                        "result": "WIN" if pnl_pct > 0 else "LOSS",
                        "exit_reason": exit_reason,
                        "volume_multiple": float(volume / row["vol_avg"]) if row["vol_avg"] > 0 else np.nan,
                    }
                )

                in_position = False
                direction = None
                entry_price = None
                stop_price = None
                target_price = None
                entry_bar = None

    trades_df = pd.DataFrame(trades)
    summary = build_summary(trades_df, symbol)
    return trades_df, summary


# ============================================================
# STRATEGY 3 — MOMENTUM DESTROYER
# ============================================================

def momentum_destroyer_strategy(
    df: pd.DataFrame,
    symbol: str = "UNKNOWN",
    ema_fast: int = 9,
    ema_slow: int = 21,
    atr_period: int = 14,
    volume_window: int = 20,
    momentum_window: int = 5,
    lookback_breakout: int = 10,
    volume_multiplier: float = 1.5,
    range_atr_multiplier: float = 1.1,
    body_ratio_min: float = 0.65,
    follow_through_bars: int = 2,
    entry_offset_atr: float = 0.05,
    stop_atr_multiplier: float = 1.0,
    target_atr_multiplier: float = 1.8,
    break_even_trigger_atr: float = 1.0,
    trailing_atr_multiplier: float = 1.0,
    max_hold_bars: int = 8,
) -> Tuple[pd.DataFrame, dict]:
    df = df.copy()

    df["ema_fast"] = df["Close"].ewm(span=ema_fast, adjust=False).mean()
    df["ema_slow"] = df["Close"].ewm(span=ema_slow, adjust=False).mean()
    df["atr"] = calculate_atr(df, atr_period)
    df["vol_avg"] = df["Volume"].rolling(volume_window).mean()

    df["range"] = df["High"] - df["Low"]
    df["body"] = (df["Close"] - df["Open"]).abs()
    df["body_ratio"] = np.where(df["range"] > 0, df["body"] / df["range"], 0.0)

    df["recent_high"] = df["High"].rolling(lookback_breakout).max().shift(1)
    df["recent_low"] = df["Low"].rolling(lookback_breakout).min().shift(1)

    df["momentum_up"] = df["Close"] - df["Close"].shift(momentum_window)
    df["momentum_down"] = df["Close"].shift(momentum_window) - df["Close"]

    trades = []

    in_position = False
    direction = None
    entry_price = None
    entry_bar = None
    stop_price = None
    target_price = None
    highest_since_entry = None
    lowest_since_entry = None
    signal_volume_multiple = None
    signal_strength_atr = None

    pending_signal = None
    pending_signal_bar = None
    pending_entry_trigger = None
    pending_stop_reference = None
    pending_signal_volume_multiple = None
    pending_signal_strength_atr = None

    start_idx = max(ema_slow, atr_period, volume_window, lookback_breakout, momentum_window) + 5

    for i in range(start_idx, len(df)):
        row = df.iloc[i]

        if pd.isna(row["atr"]) or pd.isna(row["vol_avg"]) or pd.isna(row["recent_high"]) or pd.isna(row["recent_low"]):
            continue

        open_price = row["Open"]
        high_price = row["High"]
        low_price = row["Low"]
        close_price = row["Close"]
        volume = row["Volume"]
        atr = row["atr"]

        trend_up = row["ema_fast"] > row["ema_slow"]
        trend_down = row["ema_fast"] < row["ema_slow"]

        volume_surge = volume > (row["vol_avg"] * volume_multiplier)
        range_expansion = row["range"] > (atr * range_atr_multiplier)
        strong_body = row["body_ratio"] >= body_ratio_min

        bullish_breakout = close_price > row["recent_high"]
        bearish_breakdown = close_price < row["recent_low"]

        bullish_candle = close_price > open_price
        bearish_candle = close_price < open_price

        momentum_bullish = row["momentum_up"] > atr * 0.5
        momentum_bearish = row["momentum_down"] > atr * 0.5

        if not in_position and pending_signal is None:
            long_ignition = (
                trend_up
                and bullish_candle
                and bullish_breakout
                and strong_body
                and range_expansion
                and volume_surge
                and momentum_bullish
            )

            short_ignition = (
                trend_down
                and bearish_candle
                and bearish_breakdown
                and strong_body
                and range_expansion
                and volume_surge
                and momentum_bearish
            )

            if long_ignition:
                pending_signal = "long"
                pending_signal_bar = i
                pending_entry_trigger = high_price + (atr * entry_offset_atr)
                pending_stop_reference = low_price
                pending_signal_volume_multiple = float(volume / row["vol_avg"]) if row["vol_avg"] > 0 else np.nan
                pending_signal_strength_atr = float(row["range"] / atr) if atr > 0 else np.nan

            elif short_ignition:
                pending_signal = "short"
                pending_signal_bar = i
                pending_entry_trigger = low_price - (atr * entry_offset_atr)
                pending_stop_reference = high_price
                pending_signal_volume_multiple = float(volume / row["vol_avg"]) if row["vol_avg"] > 0 else np.nan
                pending_signal_strength_atr = float(row["range"] / atr) if atr > 0 else np.nan

        if not in_position and pending_signal is not None:
            bars_since_signal = i - pending_signal_bar

            if bars_since_signal > follow_through_bars:
                pending_signal = None
                pending_signal_bar = None
                pending_entry_trigger = None
                pending_stop_reference = None
                pending_signal_volume_multiple = None
                pending_signal_strength_atr = None

            else:
                if pending_signal == "long" and high_price >= pending_entry_trigger:
                    entry_price = max(open_price, pending_entry_trigger)
                    stop_price = pending_stop_reference - (atr * stop_atr_multiplier)
                    risk = entry_price - stop_price

                    if risk > 0:
                        target_price = entry_price + max(risk * target_atr_multiplier, atr * 1.2)
                        in_position = True
                        direction = "long"
                        entry_bar = i
                        highest_since_entry = high_price
                        lowest_since_entry = low_price
                        signal_volume_multiple = pending_signal_volume_multiple
                        signal_strength_atr = pending_signal_strength_atr

                    pending_signal = None
                    pending_signal_bar = None
                    pending_entry_trigger = None
                    pending_stop_reference = None
                    pending_signal_volume_multiple = None
                    pending_signal_strength_atr = None

                elif pending_signal == "short" and low_price <= pending_entry_trigger:
                    entry_price = min(open_price, pending_entry_trigger)
                    stop_price = pending_stop_reference + (atr * stop_atr_multiplier)
                    risk = stop_price - entry_price

                    if risk > 0:
                        target_price = entry_price - max(risk * target_atr_multiplier, atr * 1.2)
                        in_position = True
                        direction = "short"
                        entry_bar = i
                        highest_since_entry = high_price
                        lowest_since_entry = low_price
                        signal_volume_multiple = pending_signal_volume_multiple
                        signal_strength_atr = pending_signal_strength_atr

                    pending_signal = None
                    pending_signal_bar = None
                    pending_entry_trigger = None
                    pending_stop_reference = None
                    pending_signal_volume_multiple = None
                    pending_signal_strength_atr = None

        if in_position:
            highest_since_entry = max(highest_since_entry, high_price)
            lowest_since_entry = min(lowest_since_entry, low_price)

            bars_held = i - entry_bar
            exit_reason = None
            exit_price = None

            if direction == "long":
                unrealized_move = highest_since_entry - entry_price

                if unrealized_move >= (atr * break_even_trigger_atr):
                    stop_price = max(stop_price, entry_price)

                trailing_stop = highest_since_entry - (atr * trailing_atr_multiplier)
                stop_price = max(stop_price, trailing_stop)

                stop_hit = low_price <= stop_price
                target_hit = high_price >= target_price

                if stop_hit and target_hit:
                    exit_price = stop_price
                    exit_reason = "stop"
                elif stop_hit:
                    exit_price = stop_price
                    exit_reason = "stop"
                elif target_hit:
                    exit_price = target_price
                    exit_reason = "target"
                elif bars_held >= max_hold_bars:
                    exit_price = close_price
                    exit_reason = "time"

            else:
                unrealized_move = entry_price - lowest_since_entry

                if unrealized_move >= (atr * break_even_trigger_atr):
                    stop_price = min(stop_price, entry_price)

                trailing_stop = lowest_since_entry + (atr * trailing_atr_multiplier)
                stop_price = min(stop_price, trailing_stop)

                stop_hit = high_price >= stop_price
                target_hit = low_price <= target_price

                if stop_hit and target_hit:
                    exit_price = stop_price
                    exit_reason = "stop"
                elif stop_hit:
                    exit_price = stop_price
                    exit_reason = "stop"
                elif target_hit:
                    exit_price = target_price
                    exit_reason = "target"
                elif bars_held >= max_hold_bars:
                    exit_price = close_price
                    exit_reason = "time"

            if exit_reason is not None:
                if direction == "long":
                    pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0
                else:
                    pnl_pct = ((entry_price - exit_price) / entry_price) * 100.0

                trades.append(
                    {
                        "entry_bar": entry_bar,
                        "exit_bar": i,
                        "direction": direction,
                        "entry": float(entry_price),
                        "exit": float(exit_price),
                        "pnl_pct": float(pnl_pct),
                        "result": "WIN" if pnl_pct > 0 else "LOSS",
                        "exit_reason": exit_reason,
                        "bars_held": int(bars_held),
                        "signal_volume_multiple": float(signal_volume_multiple) if signal_volume_multiple is not None else np.nan,
                        "signal_strength_atr": float(signal_strength_atr) if signal_strength_atr is not None else np.nan,
                    }
                )

                in_position = False
                direction = None
                entry_price = None
                entry_bar = None
                stop_price = None
                target_price = None
                highest_since_entry = None
                lowest_since_entry = None
                signal_volume_multiple = None
                signal_strength_atr = None

    trades_df = pd.DataFrame(trades)
    summary = build_summary(trades_df, symbol)
    return trades_df, summary


# ============================================================
# RUNNERS
# ============================================================

def run_breakout_retest_backtest(data_dict: Dict[str, pd.DataFrame]) -> None:
    all_summaries = []
    all_trades = []

    for symbol, df in data_dict.items():
        try:
            trades_df, summary = breakout_retest_strategy(df, symbol=symbol)
            print_strategy_result("Breakout+Retest", symbol, trades_df, summary)

            all_summaries.append(summary)
            if not trades_df.empty:
                all_trades.append(trades_df.assign(symbol=symbol))

        except Exception as e:
            print(f"{symbol}: BREAKOUT+RETEST ERROR - {e}")

    print(f"\n{'=' * 70}")
    print("RAGE ENGINE — BREAKOUT+RETEST SUMMARY")
    print(f"{'=' * 70}")

    summary_df = pd.DataFrame(all_summaries)
    if not summary_df.empty:
        print(
            summary_df[
                ["symbol", "trades", "wins", "win_rate", "total_pnl", "avg_pnl", "profit_factor"]
            ].to_string(index=False)
        )

    save_strategy_outputs("breakout_retest", all_summaries, all_trades)


def run_volume_surge_backtest(data_dict: Dict[str, pd.DataFrame]) -> None:
    all_summaries = []
    all_trades = []

    for symbol, df in data_dict.items():
        try:
            trades_df, summary = volume_surge_strategy(df, symbol=symbol)
            print_strategy_result("Volume Surge", symbol, trades_df, summary)

            all_summaries.append(summary)
            if not trades_df.empty:
                all_trades.append(trades_df.assign(symbol=symbol))

        except Exception as e:
            print(f"{symbol}: VOLUME SURGE ERROR - {e}")

    print(f"\n{'=' * 70}")
    print("RAGE ENGINE — VOLUME SURGE SUMMARY")
    print(f"{'=' * 70}")

    summary_df = pd.DataFrame(all_summaries)
    if not summary_df.empty:
        print(
            summary_df[
                ["symbol", "trades", "wins", "win_rate", "total_pnl", "avg_pnl", "profit_factor"]
            ].to_string(index=False)
        )

    save_strategy_outputs("volume_surge", all_summaries, all_trades)


def run_momentum_destroyer_backtest(data_dict: Dict[str, pd.DataFrame]) -> None:
    all_summaries = []
    all_trades = []

    for symbol, df in data_dict.items():
        try:
            trades_df, summary = momentum_destroyer_strategy(df, symbol=symbol)
            print_strategy_result("Momentum Destroyer", symbol, trades_df, summary)

            all_summaries.append(summary)
            if not trades_df.empty:
                all_trades.append(trades_df.assign(symbol=symbol))

        except Exception as e:
            print(f"{symbol}: MOMENTUM DESTROYER ERROR - {e}")

    print(f"\n{'=' * 70}")
    print("RAGE ENGINE — MOMENTUM DESTROYER SUMMARY")
    print(f"{'=' * 70}")

    summary_df = pd.DataFrame(all_summaries)
    if not summary_df.empty:
        print(
            summary_df[
                ["symbol", "trades", "wins", "win_rate", "total_pnl", "avg_pnl", "profit_factor"]
            ].to_string(index=False)
        )

    save_strategy_outputs("momentum_destroyer", all_summaries, all_trades)


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

    print("\n" + "=" * 70)
    print("RAGE ENGINE — Loading data")
    print("=" * 70)

    data_dict = load_market_data(SYMBOLS, period=PERIOD, interval=INTERVAL)

    if not data_dict:
        print("No market data loaded. Exiting.")
        raise SystemExit(1)

    print(f"\nLoaded symbols: {', '.join(data_dict.keys())}")

    run_breakout_retest_backtest(data_dict)
    run_volume_surge_backtest(data_dict)
    run_momentum_destroyer_backtest(data_dict)