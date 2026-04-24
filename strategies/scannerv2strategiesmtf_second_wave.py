"""
strategies/mtf_second_wave.py
=============================
Second-wave strategy pack for RAGE.

Adds broader 24-hour market coverage without duplicating the first pack.

Strategies:
  1. MTFFXLondonBreakout   — FX Asian range breakout + retest
  2. MTFUSOpenMomentum     — US cash-open impulse continuation
  3. MTFVolatilityCoilV2   — looser BB squeeze breakout
  4. MTFTrendContinuationV2 — improved EMA/ADX continuation logic

All strategies are:
- long + short
- BaseStrategy-compatible
- registry auto-discoverable
- daily-compatible proxies if intraday feed is not available
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from strategies.registry import BaseStrategy


# ============================================================
# Shared helpers
# ============================================================

def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = g / l.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - pc).abs(),
            (df["low"] - pc).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()


def _macd(s: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ml = _ema(s, fast) - _ema(s, slow)
    sl = _ema(ml, signal)
    hist = ml - sl
    return ml, sl, hist


def _bollinger(s: pd.Series, n: int = 20, std: float = 2.0):
    mid = s.rolling(n).mean()
    sigma = s.rolling(n).std()
    upper = mid + std * sigma
    lower = mid - std * sigma
    width = upper - lower
    return upper, mid, lower, width


def _adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h = df["high"]
    l = df["low"]
    pc = df["close"].shift(1)

    tr = pd.concat(
        [
            h - l,
            (h - pc).abs(),
            (l - pc).abs(),
        ],
        axis=1,
    ).max(axis=1)

    up = h - h.shift(1)
    dn = l.shift(1) - l

    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    ndm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)

    atr_s = tr.ewm(span=n, adjust=False).mean()
    pdi = 100 * pdm.ewm(span=n, adjust=False).mean() / atr_s.replace(0, np.nan)
    ndi = 100 * ndm.ewm(span=n, adjust=False).mean() / atr_s.replace(0, np.nan)
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)

    return dx.ewm(span=n, adjust=False).mean()


def _vwap_proxy(df: pd.DataFrame) -> pd.Series:
    tp = (df["high"] + df["low"] + df["close"]) / 3
    return (tp * df["volume"]).cumsum() / df["volume"].cumsum().replace(0, np.nan)


def _score(row: pd.Series, risk: float, reward: float) -> str:
    """
    Lightweight quality gate.
    Returns: 'full', 'half', or 'skip'
    """
    pts = 0

    vol_ratio = row.get("vol_ratio", 1.0)
    if vol_ratio >= 2.0:
        pts += 20
    elif vol_ratio >= 1.5:
        pts += 14
    elif vol_ratio >= 1.2:
        pts += 10
    else:
        pts += 4

    body_ratio = row.get("body_ratio", 0.5)
    pts += 20 if body_ratio >= 0.70 else (12 if body_ratio >= 0.55 else 5)

    rr = reward / risk if risk > 0 else 0
    pts += 15 if rr >= 3.0 else (10 if rr >= 2.0 else (5 if rr >= 1.5 else 1))

    atr_mult = row.get("atr_mult", 1.0)
    pts += 10 if atr_mult >= 1.5 else (6 if atr_mult >= 1.0 else 2)

    total = pts
    if total >= 45:
        return "full"
    elif total >= 30:
        return "half"
    return "skip"


# ============================================================
# 1. FX LONDON BREAKOUT
# ============================================================

class MTFFXLondonBreakout(BaseStrategy):
    """
    FX breakout/retest concept.
    Daily proxy version:
    - uses prior bar range as session proxy
    - break + hold + body confirmation
    Best on intraday FX feeds, but still registry-safe on daily data.
    """
    name = "mtf_fx_london_breakout"
    description = "FX Asian-range breakout/retest proxy with long + short logic"
    asset_classes = ["forex"]
    timeframes = ["15m", "1h", "1d"]

    def __init__(self, rr: float = 2.0, retest_tolerance_atr: float = 0.35):
        self.rr = rr
        self.retest_tolerance_atr = retest_tolerance_atr

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        df["atr"] = _atr(df)
        df["range"] = df["high"] - df["low"]
        df["body"] = (df["close"] - df["open"]).abs()
        df["body_ratio"] = np.where(df["range"] > 0, df["body"] / df["range"], 0.0)
        df["vol_avg"] = df["volume"].rolling(20).mean()
        df["vol_ratio"] = df["volume"] / df["vol_avg"].replace(0, np.nan)
        df["atr_mult"] = df["range"] / df["atr"].replace(0, np.nan)

        df["prior_high"] = df["high"].shift(1)
        df["prior_low"] = df["low"].shift(1)
        df["prior_range"] = df["prior_high"] - df["prior_low"]

        tol = df["atr"] * self.retest_tolerance_atr

        long_break = (
            (df["close"] > df["prior_high"])
            & (df["low"] <= (df["prior_high"] + tol))
            & (df["close"] > df["open"])
            & (df["body_ratio"] >= 0.55)
        )

        short_break = (
            (df["close"] < df["prior_low"])
            & (df["high"] >= (df["prior_low"] - tol))
            & (df["close"] < df["open"])
            & (df["body_ratio"] >= 0.55)
        )

        wl_long = (
            (df["close"] >= df["prior_high"] * 0.997)
            & ~long_break
        )
        wl_short = (
            (df["close"] <= df["prior_low"] * 1.003)
            & ~short_break
        )

        df["signal"] = 0
        df.loc[long_break, "signal"] = 1
        df.loc[short_break, "signal"] = -1
        df.loc[wl_long & (df["signal"] == 0), "signal"] = 2
        df.loc[wl_short & (df["signal"] == 0), "signal"] = -2

        for idx in df[df["signal"].isin([1, -1])].index:
            row = df.loc[idx]
            risk = max(float(row["atr"]) * 1.1, float(row["prior_range"]) if pd.notna(row["prior_range"]) else 0.0)
            reward = risk * self.rr
            if _score(row, risk, reward) == "skip":
                df.loc[idx, "signal"] = 0

        df["entry"] = df["close"]
        df.loc[df["signal"].isin([1, 2]), "stop_loss"] = df["prior_low"]
        df.loc[df["signal"].isin([-1, -2]), "stop_loss"] = df["prior_high"]
        df.loc[df["signal"] == 1, "take_profit"] = df["close"] + df["atr"] * self.rr
        df.loc[df["signal"] == -1, "take_profit"] = df["close"] - df["atr"] * self.rr
        df["r_multiple"] = self.rr
        return df


# ============================================================
# 2. US OPEN MOMENTUM
# ============================================================

class MTFUSOpenMomentum(BaseStrategy):
    """
    US cash-open style momentum proxy.
    Daily-safe version:
    - trend bias
    - expansion candle
    - strong body
    - volume surge
    - breakout through recent highs/lows
    """
    name = "mtf_us_open_momentum"
    description = "US open impulse momentum with long + short breakout logic"
    asset_classes = ["stocks", "futures", "crypto"]
    timeframes = ["5m", "15m", "1h"]

    def __init__(self, rr: float = 2.0, breakout_lookback: int = 10):
        self.rr = rr
        self.breakout_lookback = breakout_lookback

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        df["ema20"] = _ema(df["close"], 20)
        df["ema50"] = _ema(df["close"], 50)
        df["atr"] = _atr(df)
        df["vol_avg"] = df["volume"].rolling(20).mean()
        df["vol_ratio"] = df["volume"] / df["vol_avg"].replace(0, np.nan)
        df["range"] = df["high"] - df["low"]
        df["body"] = (df["close"] - df["open"]).abs()
        df["body_ratio"] = np.where(df["range"] > 0, df["body"] / df["range"], 0.0)
        df["atr_mult"] = df["range"] / df["atr"].replace(0, np.nan)
        df["recent_high"] = df["high"].rolling(self.breakout_lookback).max().shift(1)
        df["recent_low"] = df["low"].rolling(self.breakout_lookback).min().shift(1)

        trend_up = df["ema20"] > df["ema50"]
        trend_down = df["ema20"] < df["ema50"]

        long_signal = (
            trend_up
            & (df["close"] > df["recent_high"])
            & (df["close"] > df["open"])
            & (df["body_ratio"] >= 0.60)
            & (df["vol_ratio"] >= 1.4)
            & (df["atr_mult"] >= 1.0)
        )

        short_signal = (
            trend_down
            & (df["close"] < df["recent_low"])
            & (df["close"] < df["open"])
            & (df["body_ratio"] >= 0.60)
            & (df["vol_ratio"] >= 1.4)
            & (df["atr_mult"] >= 1.0)
        )

        wl_long = trend_up & (df["close"] >= df["recent_high"] * 0.995) & ~long_signal
        wl_short = trend_down & (df["close"] <= df["recent_low"] * 1.005) & ~short_signal

        df["signal"] = 0
        df.loc[long_signal, "signal"] = 1
        df.loc[short_signal, "signal"] = -1
        df.loc[wl_long & (df["signal"] == 0), "signal"] = 2
        df.loc[wl_short & (df["signal"] == 0), "signal"] = -2

        for idx in df[df["signal"].isin([1, -1])].index:
            row = df.loc[idx]
            risk = float(row["atr"]) * 1.2
            reward = risk * self.rr
            if _score(row, risk, reward) == "skip":
                df.loc[idx, "signal"] = 0

        df["entry"] = df["close"]
        df.loc[df["signal"].isin([1, 2]), "stop_loss"] = df["close"] - df["atr"] * 1.2
        df.loc[df["signal"].isin([-1, -2]), "stop_loss"] = df["close"] + df["atr"] * 1.2
        df.loc[df["signal"] == 1, "take_profit"] = df["close"] + df["atr"] * 1.2 * self.rr
        df.loc[df["signal"] == -1, "take_profit"] = df["close"] - df["atr"] * 1.2 * self.rr
        df["r_multiple"] = self.rr
        return df


# ============================================================
# 3. VOLATILITY COIL V2
# ============================================================

class MTFVolatilityCoilV2(BaseStrategy):
    """
    Looser and more realistic version of the first volatility coil.
    Designed to actually fire more often.
    """
    name = "mtf_volatility_coil_v2"
    description = "Looser BB squeeze breakout with long + short expansion logic"
    asset_classes = ["stocks", "crypto", "futures", "forex"]
    timeframes = ["1h", "4h", "1d"]

    def __init__(self, squeeze_pct: float = 0.25, adx_max: float = 28, rr: float = 2.0):
        self.squeeze_pct = squeeze_pct
        self.adx_max = adx_max
        self.rr = rr

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        bb_up, bb_mid, bb_low, bb_width = _bollinger(df["close"], 20, 2.0)
        df["bb_upper"] = bb_up
        df["bb_mid"] = bb_mid
        df["bb_lower"] = bb_low
        df["bb_width"] = bb_width
        df["bb_squeeze"] = bb_width.rolling(50).rank(pct=True)

        df["adx"] = _adx(df, 14)
        df["adx_prev"] = df["adx"].shift(1)
        df["atr"] = _atr(df)
        df["vol_avg"] = df["volume"].rolling(20).mean()
        df["vol_ratio"] = df["volume"] / df["vol_avg"].replace(0, np.nan)
        df["range"] = df["high"] - df["low"]
        df["body"] = (df["close"] - df["open"]).abs()
        df["body_ratio"] = np.where(df["range"] > 0, df["body"] / df["range"], 0.0)
        df["atr_mult"] = df["range"] / df["atr"].replace(0, np.nan)

        in_squeeze = (df["bb_squeeze"] <= self.squeeze_pct) & (df["adx"] <= self.adx_max)
        adx_rising = df["adx"] > df["adx_prev"]

        bull_expand = (
            in_squeeze
            & adx_rising
            & (df["close"] > df["open"])
            & (df["close"] > df["bb_upper"])
            & (df["body_ratio"] >= 0.55)
            & (df["vol_ratio"] >= 1.2)
            & (df["atr_mult"] >= 0.9)
        )

        bear_expand = (
            in_squeeze
            & adx_rising
            & (df["close"] < df["open"])
            & (df["close"] < df["bb_lower"])
            & (df["body_ratio"] >= 0.55)
            & (df["vol_ratio"] >= 1.2)
            & (df["atr_mult"] >= 0.9)
        )

        squeeze_watch = in_squeeze & ~(bull_expand | bear_expand)

        df["signal"] = 0
        df.loc[bull_expand, "signal"] = 1
        df.loc[bear_expand, "signal"] = -1
        df.loc[squeeze_watch & (df["signal"] == 0), "signal"] = 2

        for idx in df[df["signal"].isin([1, -1])].index:
            row = df.loc[idx]
            risk = float(row["atr"]) * 1.2
            reward = risk * self.rr
            if _score(row, risk, reward) == "skip":
                df.loc[idx, "signal"] = 0

        df["entry"] = df["close"]
        df.loc[df["signal"].isin([1, 2]), "stop_loss"] = df["bb_mid"]
        df.loc[df["signal"].isin([-1, -2]), "stop_loss"] = df["bb_mid"]
        df.loc[df["signal"] == 1, "take_profit"] = df["close"] + df["atr"] * self.rr
        df.loc[df["signal"] == -1, "take_profit"] = df["close"] - df["atr"] * self.rr
        df["r_multiple"] = self.rr
        return df


# ============================================================
# 4. TREND CONTINUATION V2
# ============================================================

class MTFTrendContinuationV2(BaseStrategy):
    """
    Cleaner version of trend continuation:
    - trend bias with EMA stack
    - ADX strong enough
    - pullback not too deep
    - reclaim bar in trend direction
    """
    name = "mtf_trend_continuation_v2"
    description = "Improved EMA/ADX continuation strategy with long + short logic"
    asset_classes = ["stocks", "crypto", "futures", "forex"]
    timeframes = ["5m", "15m", "1h"]

    def __init__(self, adx_min: float = 20, rr: float = 2.0):
        self.adx_min = adx_min
        self.rr = rr

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        df["ema9"] = _ema(df["close"], 9)
        df["ema21"] = _ema(df["close"], 21)
        df["ema50"] = _ema(df["close"], 50)
        df["adx"] = _adx(df, 14)
        df["atr"] = _atr(df)
        df["vol_avg"] = df["volume"].rolling(20).mean()
        df["vol_ratio"] = df["volume"] / df["vol_avg"].replace(0, np.nan)
        df["range"] = df["high"] - df["low"]
        df["body"] = (df["close"] - df["open"]).abs()
        df["body_ratio"] = np.where(df["range"] > 0, df["body"] / df["range"], 0.0)
        df["atr_mult"] = df["range"] / df["atr"].replace(0, np.nan)

        bull_stack = (
            (df["ema9"] > df["ema21"])
            & (df["ema21"] > df["ema50"])
            & (df["adx"] >= self.adx_min)
        )

        bear_stack = (
            (df["ema9"] < df["ema21"])
            & (df["ema21"] < df["ema50"])
            & (df["adx"] >= self.adx_min)
        )

        pullback_long = (df["low"] <= df["ema21"]) & (df["close"] > df["ema21"])
        pullback_short = (df["high"] >= df["ema21"]) & (df["close"] < df["ema21"])

        reclaim_long = (
            (df["close"] > df["open"])
            & (df["close"] > df["high"].shift(1))
            & (df["body_ratio"] >= 0.50)
            & (df["vol_ratio"] >= 1.1)
        )

        reclaim_short = (
            (df["close"] < df["open"])
            & (df["close"] < df["low"].shift(1))
            & (df["body_ratio"] >= 0.50)
            & (df["vol_ratio"] >= 1.1)
        )

        long_signal = bull_stack & pullback_long & reclaim_long
        short_signal = bear_stack & pullback_short & reclaim_short

        wl_long = bull_stack & pullback_long & ~long_signal
        wl_short = bear_stack & pullback_short & ~short_signal

        df["signal"] = 0
        df.loc[long_signal, "signal"] = 1
        df.loc[short_signal, "signal"] = -1
        df.loc[wl_long & (df["signal"] == 0), "signal"] = 2
        df.loc[wl_short & (df["signal"] == 0), "signal"] = -2

        for idx in df[df["signal"].isin([1, -1])].index:
            row = df.loc[idx]
            risk = float(row["atr"]) * 1.1
            reward = risk * self.rr
            if _score(row, risk, reward) == "skip":
                df.loc[idx, "signal"] = 0

        df["entry"] = df["close"]
        df.loc[df["signal"].isin([1, 2]), "stop_loss"] = df["ema21"] - df["atr"]
        df.loc[df["signal"].isin([-1, -2]), "stop_loss"] = df["ema21"] + df["atr"]
        df.loc[df["signal"] == 1, "take_profit"] = df["close"] + df["atr"] * self.rr
        df.loc[df["signal"] == -1, "take_profit"] = df["close"] - df["atr"] * self.rr
        df["r_multiple"] = self.rr
        return df