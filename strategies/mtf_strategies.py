"""
strategies/mtf_strategies.py
=============================
All 6 multi-timeframe strategies wrapped as BaseStrategy subclasses
so RAGE's registry auto-discovers and runs them.

Strategies:
  1. MTFMomentumBinary      — RSI burst + MACD expansion + VWAP
  2. MTFTrendContinuation   — EMA 9/21/50/200 stack + ADX + pullback
  3. MTFSessionSniper       — London open Asian range breakout
  4. MTFAsiaFade            — Overnight mean reversion (22:00–07:00 UTC)
  5. MTFNYOverlapHunter     — NY/London overlap continuation
  6. MTFVolatilityCoil      — Bollinger Band squeeze breakout

All share the same 1H→15M→5M cascade and Trade Quality Scorer gate.
The RAGE backtester feeds daily data — signals are flagged on daily bars
as a proxy. For full MTF precision, feed in 5m or 15m data via DataLoader.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from strategies.registry import BaseStrategy


# ── Shared indicator helpers (self-contained, no external imports) ────

def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()

def _rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - (100 / (1 + g / l.replace(0, np.nan)))

def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - pc).abs(),
        (df["low"]  - pc).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()

def _macd(s: pd.Series, fast=12, slow=26, signal=9):
    ml = _ema(s, fast) - _ema(s, slow)
    sl = _ema(ml, signal)
    return ml, sl, ml - sl

def _bollinger(s: pd.Series, n=20, std=2.0):
    mid   = s.rolling(n).mean()
    sigma = s.rolling(n).std()
    return mid + std * sigma, mid, mid - std * sigma, (2 * std * sigma)

def _adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, pc = df["high"], df["low"], df["close"].shift(1)
    tr  = pd.concat([(h-l), (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    up  = h - h.shift(1)
    dn  = l.shift(1) - l
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    ndm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    atr_s = tr.ewm(span=n, adjust=False).mean()
    pdi = 100 * pdm.ewm(span=n, adjust=False).mean() / atr_s
    ndi = 100 * ndm.ewm(span=n, adjust=False).mean() / atr_s
    dx  = (100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan))
    return dx.ewm(span=n, adjust=False).mean()

def _vwap_proxy(df: pd.DataFrame) -> pd.Series:
    """VWAP proxy using typical price × volume cumsum."""
    tp  = (df["high"] + df["low"] + df["close"]) / 3
    return (tp * df["volume"]).cumsum() / df["volume"].cumsum().replace(0, np.nan)

def _score(row: pd.Series, risk: float, reward: float) -> str:
    """Lightweight quality gate. Returns 'full', 'half', or 'skip'."""
    pts = 0
    # Volume
    vol_ratio = row.get("vol_ratio", 1.0)
    if   vol_ratio >= 2.0: pts += 20
    elif vol_ratio >= 1.5: pts += 14
    elif vol_ratio >= 1.2: pts += 10
    else:                  pts += 4
    # Body ratio
    body = row.get("body_ratio", 0.5)
    pts += 20 if body >= 0.70 else (12 if body >= 0.55 else 5)
    # R:R
    rr = reward / risk if risk > 0 else 0
    pts += 15 if rr >= 3.0 else (10 if rr >= 2.0 else (5 if rr >= 1.5 else 1))
    # ATR expansion
    atr_mult = row.get("atr_mult", 1.0)
    pts += 10 if atr_mult >= 1.5 else (6 if atr_mult >= 1.0 else 2)

    total = pts
    if   total >= 45: return "full"
    elif total >= 30: return "half"
    else:             return "skip"


# ======================================================================
# 1. MTF MOMENTUM BINARY
# ======================================================================
class MTFMomentumBinary(BaseStrategy):
    """
    RSI burst from extreme + MACD histogram expanding + VWAP side.
    Optimised for momentum bursts — Binary Destroyer style.
    1H bias → 15M MACD expanding → 5M RSI burst + VWAP confirm.
    """
    name          = "mtf_momentum_binary"
    description   = "RSI burst + MACD expansion + VWAP — 1H/15M/5M cascade"
    asset_classes = ["stocks", "crypto", "futures", "forex"]
    timeframes    = ["5m", "15m", "1h"]

    def __init__(self, rsi_period=9, rsi_os=35, rsi_ob=65,
                 macd_fast=12, macd_slow=26, macd_sig=9, rr=2.0):
        self.rsi_period = rsi_period
        self.rsi_os = rsi_os; self.rsi_ob = rsi_ob
        self.macd_fast = macd_fast; self.macd_slow = macd_slow
        self.macd_sig  = macd_sig;  self.rr = rr

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ema_20"]  = _ema(df["close"], 20)
        df["ema_50"]  = _ema(df["close"], 50)
        df["vwap"]    = _vwap_proxy(df)
        df["rsi"]     = _rsi(df["close"], self.rsi_period)
        df["rsi_prev"]= df["rsi"].shift(1)
        ml, sl, hist  = _macd(df["close"], self.macd_fast, self.macd_slow, self.macd_sig)
        df["hist"]    = hist
        df["hist_p1"] = hist.shift(1)
        df["hist_p2"] = hist.shift(2)
        df["atr"]     = _atr(df)
        df["vol_avg"] = df["volume"].rolling(20).mean()
        df["range"]   = df["high"] - df["low"]
        df["body"]    = (df["close"] - df["open"]).abs()
        df["body_ratio"] = np.where(df["range"] > 0, df["body"] / df["range"], 0.0)
        df["vol_ratio"]  = df["volume"] / df["vol_avg"].replace(0, np.nan)
        df["atr_mult"]   = df["range"] / df["atr"].replace(0, np.nan)

        # 1H proxy bias
        ema_bull = df["ema_20"] > df["ema_50"]
        ema_bear = df["ema_20"] < df["ema_50"]

        # MACD expanding in direction
        macd_long  = (df["hist"] > 0) & (df["hist"] > df["hist_p1"]) & (df["hist_p1"] > df["hist_p2"])
        macd_short = (df["hist"] < 0) & (df["hist"] < df["hist_p1"]) & (df["hist_p1"] < df["hist_p2"])

        # RSI burst (was oversold/overbought, now crossing back)
        rsi_burst_long  = (df["rsi_prev"] < self.rsi_os) & (df["rsi"] >= self.rsi_os)
        rsi_burst_short = (df["rsi_prev"] > self.rsi_ob) & (df["rsi"] <= self.rsi_ob)

        # VWAP side
        above_vwap = df["close"] > df["vwap"]
        below_vwap = df["close"] < df["vwap"]

        # Volume gate
        vol_ok = df["vol_ratio"] >= 1.3

        long_signal  = ema_bull & macd_long  & rsi_burst_long  & above_vwap & vol_ok
        short_signal = ema_bear & macd_short & rsi_burst_short & below_vwap & vol_ok

        df["signal"] = 0
        df.loc[long_signal,  "signal"] = 1
        df.loc[short_signal, "signal"] = -1

        # Watchlist: MACD + bias align but RSI not burst yet
        wl_long  = ema_bull & macd_long  & (df["rsi"] < 45) & above_vwap & ~long_signal
        wl_short = ema_bear & macd_short & (df["rsi"] > 55) & below_vwap & ~short_signal
        df.loc[wl_long,  "signal"] = 2
        df.loc[wl_short, "signal"] = -2

        # Apply quality scorer and nullify low-quality signals
        for idx in df[df["signal"].isin([1, -1])].index:
            row = df.loc[idx]
            risk   = float(row["atr"]) * 1.2
            reward = risk * self.rr
            action = _score(row, risk, reward)
            if action == "skip":
                df.loc[idx, "signal"] = 0

        df["entry"]      = df["close"]
        df["atr_val"]    = df["atr"]
        df.loc[df["signal"].isin([1, 2]),   "stop_loss"]   = df["close"] - df["atr"] * 1.2
        df.loc[df["signal"].isin([-1, -2]), "stop_loss"]   = df["close"] + df["atr"] * 1.2
        df.loc[df["signal"] == 1,  "take_profit"] = df["close"] + df["atr"] * 1.2 * self.rr
        df.loc[df["signal"] == -1, "take_profit"] = df["close"] - df["atr"] * 1.2 * self.rr
        df["r_multiple"] = self.rr
        return df


# ======================================================================
# 2. MTF TREND CONTINUATION
# ======================================================================
class MTFTrendContinuation(BaseStrategy):
    """
    EMA 9/21/50/200 full stack order + ADX ≥ 25 + pullback to EMA 21.
    Setup bar + trigger bar entry.
    """
    name          = "mtf_trend_continuation"
    description   = "EMA 9/21/50/200 stack + ADX ≥ 25 + pullback entry"
    asset_classes = ["stocks", "crypto", "futures", "forex"]
    timeframes    = ["5m", "15m", "1h"]

    def __init__(self, adx_min=25, rr=2.0):
        self.adx_min = adx_min
        self.rr = rr

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ema9"]   = _ema(df["close"], 9)
        df["ema21"]  = _ema(df["close"], 21)
        df["ema50"]  = _ema(df["close"], 50)
        df["ema200"] = _ema(df["close"], 200)
        df["adx"]    = _adx(df, 14)
        df["atr"]    = _atr(df)
        df["vol_avg"]= df["volume"].rolling(20).mean()
        df["range"]  = df["high"] - df["low"]
        df["body"]   = (df["close"] - df["open"]).abs()
        df["body_ratio"] = np.where(df["range"] > 0, df["body"] / df["range"], 0.0)
        df["vol_ratio"]  = df["volume"] / df["vol_avg"].replace(0, np.nan)
        df["atr_mult"]   = df["range"] / df["atr"].replace(0, np.nan)

        # Full stack
        bull_stack = (df["ema9"] > df["ema21"]) & (df["ema21"] > df["ema50"]) & \
                     (df["ema50"] > df["ema200"]) & (df["adx"] >= self.adx_min)
        bear_stack = (df["ema9"] < df["ema21"]) & (df["ema21"] < df["ema50"]) & \
                     (df["ema50"] < df["ema200"]) & (df["adx"] >= self.adx_min)

        # Pullback to EMA 21
        dist_ema21 = (df["close"] - df["ema21"]).abs() / df["atr"].replace(0, np.nan)
        near_ema21 = dist_ema21 <= 1.2

        # Trigger bar: closes back in trend direction
        bull_trigger = (df["close"] > df["open"]) & (df["close"] > df["high"].shift(1)) & \
                       (df["body_ratio"] >= 0.55) & (df["vol_ratio"] >= 1.2)
        bear_trigger = (df["close"] < df["open"]) & (df["close"] < df["low"].shift(1)) & \
                       (df["body_ratio"] >= 0.55) & (df["vol_ratio"] >= 1.2)

        long_signal  = bull_stack & near_ema21 & bull_trigger
        short_signal = bear_stack & near_ema21 & bear_trigger

        df["signal"] = 0
        df.loc[long_signal,  "signal"] = 1
        df.loc[short_signal, "signal"] = -1

        # Watchlist: stack + pullback but no trigger bar yet
        df.loc[bull_stack & near_ema21 & ~long_signal,  "signal"] = 2
        df.loc[bear_stack & near_ema21 & ~short_signal, "signal"] = -2

        for idx in df[df["signal"].isin([1, -1])].index:
            row = df.loc[idx]
            risk   = float(row["atr"]) * 1.2
            reward = risk * self.rr
            if _score(row, risk, reward) == "skip":
                df.loc[idx, "signal"] = 0

        df["entry"]      = df["close"]
        df.loc[df["signal"].isin([1, 2]),   "stop_loss"] = df["ema21"] - df["atr"]
        df.loc[df["signal"].isin([-1, -2]), "stop_loss"] = df["ema21"] + df["atr"]
        df.loc[df["signal"] == 1,  "take_profit"] = df["close"] + (df["close"] - (df["ema21"] - df["atr"])) * self.rr
        df.loc[df["signal"] == -1, "take_profit"] = df["close"] - ((df["ema21"] + df["atr"]) - df["close"]) * self.rr
        df["r_multiple"] = self.rr
        return df


# ======================================================================
# 3. MTF SESSION SNIPER
# ======================================================================
class MTFSessionSniper(BaseStrategy):
    """
    Breakout of prior session range with volume and body confirmation.
    Works on daily bars as prior day high/low proxy.
    Best results when fed 15m intraday data at session open.
    """
    name          = "mtf_session_sniper"
    description   = "Session range breakout — volume 2× + body 60%+ (London open edge)"
    asset_classes = ["stocks", "crypto", "futures", "forex"]
    timeframes    = ["15m", "1h", "1d"]

    def __init__(self, vol_mult=2.0, body_min=0.60, buffer=0.002, rr=2.0):
        self.vol_mult = vol_mult
        self.body_min = body_min
        self.buffer   = buffer
        self.rr       = rr

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["session_high"] = df["high"].shift(1)
        df["session_low"]  = df["low"].shift(1)
        df["session_range"]= df["session_high"] - df["session_low"]
        df["avg_vol"]      = df["volume"].rolling(20).mean()
        df["vwap"]         = _vwap_proxy(df)
        df["ema20"]        = _ema(df["close"], 20)
        df["atr"]          = _atr(df)
        df["range"]        = df["high"] - df["low"]
        df["body"]         = (df["close"] - df["open"]).abs()
        df["body_ratio"]   = np.where(df["range"] > 0, df["body"] / df["range"], 0.0)
        df["vol_ratio"]    = df["volume"] / df["avg_vol"].replace(0, np.nan)
        df["atr_mult"]     = df["range"] / df["atr"].replace(0, np.nan)

        # Skip if prior range too wide (already moved)
        range_ok = df["session_range"] <= df["atr"] * 3.0

        buf = df["session_high"] * self.buffer
        bull_break = (df["close"] > df["session_high"] + buf) & \
                     (df["vol_ratio"] >= self.vol_mult) & \
                     (df["body_ratio"] >= self.body_min) & \
                     (df["close"] > df["vwap"]) & range_ok

        bear_break = (df["close"] < df["session_low"] - buf) & \
                     (df["vol_ratio"] >= self.vol_mult) & \
                     (df["body_ratio"] >= self.body_min) & \
                     (df["close"] < df["vwap"]) & range_ok

        near_bull = (df["close"] >= df["session_high"] * 0.995) & ~bull_break & range_ok
        near_bear = (df["close"] <= df["session_low"]  * 1.005) & ~bear_break & range_ok

        df["signal"] = 0
        df.loc[bull_break, "signal"] = 1
        df.loc[bear_break, "signal"] = -1
        df.loc[near_bull & (df["signal"] == 0), "signal"] = 2
        df.loc[near_bear & (df["signal"] == 0), "signal"] = -2

        for idx in df[df["signal"].isin([1, -1])].index:
            row = df.loc[idx]
            risk   = float(row["session_range"]) if row["session_range"] > 0 else float(row["atr"]) * 1.5
            reward = risk * self.rr
            if _score(row, risk, reward) == "skip":
                df.loc[idx, "signal"] = 0

        df["entry"]      = df["close"]
        df.loc[df["signal"].isin([1, 2]),   "stop_loss"]   = df["session_low"]
        df.loc[df["signal"].isin([-1, -2]), "stop_loss"]   = df["session_high"]
        df.loc[df["signal"] == 1,  "take_profit"] = df["close"] + df["session_range"] * self.rr
        df.loc[df["signal"] == -1, "take_profit"] = df["close"] - df["session_range"] * self.rr
        df["r_multiple"] = self.rr
        return df


# ======================================================================
# 4. MTF ASIA FADE
# ======================================================================
class MTFAsiaFade(BaseStrategy):
    """
    Mean reversion fade of overnight extremes.
    Fires when price is outside Bollinger Bands, RSI extreme,
    volume declining, and ADX confirms ranging conditions.
    """
    name          = "mtf_asia_fade"
    description   = "Overnight mean reversion — BB extreme + RSI + ADX < 20"
    asset_classes = ["stocks", "crypto", "futures", "forex"]
    timeframes    = ["15m", "1h"]

    def __init__(self, bb_period=20, bb_std=2.0,
                 rsi_os=28, rsi_ob=72, adx_max=20, rr=1.8):
        self.bb_period = bb_period; self.bb_std = bb_std
        self.rsi_os = rsi_os; self.rsi_ob = rsi_ob
        self.adx_max = adx_max; self.rr = rr

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        bb_up, bb_mid, bb_low, bb_width = _bollinger(df["close"], self.bb_period, self.bb_std)
        df["bb_upper"] = bb_up
        df["bb_mid"]   = bb_mid
        df["bb_lower"] = bb_low
        df["bb_width_pct"] = bb_width.rolling(50).rank(pct=True)
        df["rsi"]      = _rsi(df["close"], 14)
        df["adx"]      = _adx(df, 14)
        df["atr"]      = _atr(df)
        df["ema20"]    = _ema(df["close"], 20)
        df["vol_avg"]  = df["volume"].rolling(20).mean()
        df["vol_dec"]  = (df["volume"] < df["volume"].shift(1)) & \
                         (df["volume"].shift(1) < df["volume"].shift(2))
        df["range"]    = df["high"] - df["low"]
        df["body"]     = (df["close"] - df["open"]).abs()
        df["body_ratio"] = np.where(df["range"] > 0, df["body"] / df["range"], 0.0)
        df["vol_ratio"]  = df["volume"] / df["vol_avg"].replace(0, np.nan)
        df["atr_mult"]   = df["range"] / df["atr"].replace(0, np.nan)

        ranging = (df["adx"] < self.adx_max) & (df["bb_width_pct"] <= 0.60)

        long_fade  = ranging & (df["close"] < df["bb_lower"]) & \
                     (df["rsi"] < self.rsi_os) & df["vol_dec"]
        short_fade = ranging & (df["close"] > df["bb_upper"]) & \
                     (df["rsi"] > self.rsi_ob) & df["vol_dec"]

        # Watchlist: extreme reached but vol not declining yet
        wl_long  = ranging & (df["close"] < df["bb_lower"]) & (df["rsi"] < 35) & ~long_fade
        wl_short = ranging & (df["close"] > df["bb_upper"]) & (df["rsi"] > 65) & ~short_fade

        df["signal"] = 0
        df.loc[long_fade,  "signal"] = 1
        df.loc[short_fade, "signal"] = -1
        df.loc[wl_long  & (df["signal"] == 0), "signal"] = 2
        df.loc[wl_short & (df["signal"] == 0), "signal"] = -2

        for idx in df[df["signal"].isin([1, -1])].index:
            row = df.loc[idx]
            risk   = float(row["atr"]) * 1.5
            reward = risk * self.rr
            if _score(row, risk, reward) == "skip":
                df.loc[idx, "signal"] = 0

        df["entry"]      = df["close"]
        df.loc[df["signal"].isin([1, 2]),   "stop_loss"]   = df["close"] - df["atr"] * 1.5
        df.loc[df["signal"].isin([-1, -2]), "stop_loss"]   = df["close"] + df["atr"] * 1.5
        df.loc[df["signal"] == 1,  "take_profit"] = df["ema20"]
        df.loc[df["signal"] == -1, "take_profit"] = df["ema20"]
        df["r_multiple"] = self.rr
        return df


# ======================================================================
# 5. MTF NY OVERLAP HUNTER
# ======================================================================
class MTFNYOverlapHunter(BaseStrategy):
    """
    Trades pullbacks into the NY/London overlap session.
    Requires London session to have established a clear direction,
    then enters on pullback with RSI retracement + MACD flip.
    Highest R:R strategy in the suite.
    """
    name          = "mtf_ny_overlap_hunter"
    description   = "NY/London overlap pullback — London trend + RSI retrace + MACD flip"
    asset_classes = ["stocks", "crypto", "futures", "forex"]
    timeframes    = ["15m", "1h"]

    def __init__(self, rr=3.0):
        self.rr = rr

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ema9"]   = _ema(df["close"], 9)
        df["ema21"]  = _ema(df["close"], 21)
        df["ema50"]  = _ema(df["close"], 50)
        df["rsi"]    = _rsi(df["close"], 14)
        ml, sl, hist = _macd(df["close"], 12, 26, 9)
        df["hist"]   = hist
        df["hist_p"] = hist.shift(1)
        df["atr"]    = _atr(df)
        df["vol_avg"]= df["volume"].rolling(20).mean()
        df["swing_high"] = df["high"].rolling(8).max().shift(1)
        df["swing_low"]  = df["low"].rolling(8).min().shift(1)
        df["range"]  = df["high"] - df["low"]
        df["body"]   = (df["close"] - df["open"]).abs()
        df["body_ratio"] = np.where(df["range"] > 0, df["body"] / df["range"], 0.0)
        df["vol_ratio"]  = df["volume"] / df["vol_avg"].replace(0, np.nan)
        df["atr_mult"]   = df["range"] / df["atr"].replace(0, np.nan)

        # London trend proxy: EMA stack
        london_bull = (df["ema9"] > df["ema21"]) & (df["ema21"] > df["ema50"])
        london_bear = (df["ema9"] < df["ema21"]) & (df["ema21"] < df["ema50"])

        # RSI pullback zone
        rsi_pb_bull = df["rsi"].between(40, 58)
        rsi_pb_bear = df["rsi"].between(42, 60)

        # Price near EMA 21
        dist = (df["close"] - df["ema21"]).abs() / df["atr"].replace(0, np.nan)
        near_ema21 = dist <= 1.2

        # MACD flip
        macd_flip_long  = (df["hist"] > 0) & (df["hist_p"] <= 0)
        macd_flip_short = (df["hist"] < 0) & (df["hist_p"] >= 0)

        vol_spike = df["vol_ratio"] >= 1.5

        long_signal  = london_bull & rsi_pb_bull & near_ema21 & macd_flip_long  & vol_spike
        short_signal = london_bear & rsi_pb_bear & near_ema21 & macd_flip_short & vol_spike

        df["signal"] = 0
        df.loc[long_signal,  "signal"] = 1
        df.loc[short_signal, "signal"] = -1

        # Watchlist: setup building but no MACD flip yet
        df.loc[london_bull & rsi_pb_bull & near_ema21 & ~long_signal,  "signal"] = 2
        df.loc[london_bear & rsi_pb_bear & near_ema21 & ~short_signal, "signal"] = -2

        for idx in df[df["signal"].isin([1, -1])].index:
            row = df.loc[idx]
            risk   = abs(float(row["close"]) - float(row["swing_low"]))
            if risk <= 0:
                risk = float(row["atr"]) * 1.2
            reward = risk * self.rr
            if _score(row, risk, reward) == "skip":
                df.loc[idx, "signal"] = 0

        df["entry"]      = df["close"]
        df.loc[df["signal"].isin([1, 2]),   "stop_loss"] = df["swing_low"]
        df.loc[df["signal"].isin([-1, -2]), "stop_loss"] = df["swing_high"]
        df.loc[df["signal"] == 1,  "take_profit"] = df["swing_high"]
        df.loc[df["signal"] == -1, "take_profit"] = df["swing_low"]
        df["r_multiple"] = self.rr
        return df


# ======================================================================
# 6. MTF VOLATILITY COIL
# ======================================================================
class MTFVolatilityCoil(BaseStrategy):
    """
    Bollinger Band squeeze → explosive expansion breakout.
    Session-agnostic. Low frequency, very high conviction when it fires.
    Squeeze = BB width at 15th percentile of last 50 bars + ADX < 22.
    Trigger = first big expansion candle with volume surge + rising ADX.
    """
    name          = "mtf_volatility_coil"
    description   = "BB squeeze → expansion breakout — any session, high conviction"
    asset_classes = ["stocks", "crypto", "futures", "forex"]
    timeframes    = ["1h", "4h", "1d"]

    def __init__(self, squeeze_pct=0.15, adx_max=22,
                 body_mult=1.5, vol_mult=1.8, rr=2.5):
        self.squeeze_pct = squeeze_pct
        self.adx_max  = adx_max
        self.body_mult = body_mult
        self.vol_mult  = vol_mult
        self.rr        = rr

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        bb_up, bb_mid, bb_low, bb_width = _bollinger(df["close"], 20, 2.0)
        df["bb_upper"] = bb_up
        df["bb_lower"] = bb_low
        df["bb_mid"]   = bb_mid
        df["bb_width"] = bb_width
        df["bb_squeeze"] = bb_width.rolling(50).rank(pct=True)
        df["adx"]      = _adx(df, 14)
        df["adx_prev"] = df["adx"].shift(1)
        df["atr"]      = _atr(df)
        df["vol_avg"]  = df["volume"].rolling(20).mean()
        df["range"]    = df["high"] - df["low"]
        df["body"]     = (df["close"] - df["open"]).abs()
        df["body_ratio"] = np.where(df["range"] > 0, df["body"] / df["range"], 0.0)
        df["vol_ratio"]  = df["volume"] / df["vol_avg"].replace(0, np.nan)
        df["atr_mult"]   = df["range"] / df["atr"].replace(0, np.nan)

        # Squeeze confirmed
        in_squeeze = (df["bb_squeeze"] <= self.squeeze_pct) & (df["adx"] < self.adx_max)

        # Expansion trigger
        big_body  = df["body"] >= df["atr"] * self.body_mult
        vol_surge = df["vol_ratio"] >= self.vol_mult
        adx_rising = df["adx"] > df["adx_prev"]

        expansion = in_squeeze & big_body & vol_surge & adx_rising

        # Direction of expansion
        bull_expand = expansion & (df["close"] > df["open"]) & (df["close"] > df["bb_mid"])
        bear_expand = expansion & (df["close"] < df["open"]) & (df["close"] < df["bb_mid"])

        # Watchlist: squeeze present, no expansion yet
        squeeze_watch = in_squeeze & ~expansion

        df["signal"] = 0
        df.loc[bull_expand, "signal"] = 1
        df.loc[bear_expand, "signal"] = -1
        df.loc[squeeze_watch & (df["signal"] == 0), "signal"] = 2

        for idx in df[df["signal"].isin([1, -1])].index:
            row = df.loc[idx]
            risk   = float(row["bb_width"]) / 2.0
            if risk <= 0:
                risk = float(row["atr"])
            reward = risk * self.rr
            if _score(row, risk, reward) == "skip":
                df.loc[idx, "signal"] = 0

        df["entry"]      = df["close"]
        df.loc[df["signal"].isin([1, 2]),   "stop_loss"] = df["bb_mid"]
        df.loc[df["signal"].isin([-1, -2]), "stop_loss"] = df["bb_mid"]
        df.loc[df["signal"] == 1,  "take_profit"] = df["close"] + df["bb_width"] * self.rr
        df.loc[df["signal"] == -1, "take_profit"] = df["close"] - df["bb_width"] * self.rr
        df["r_multiple"] = self.rr
        return df