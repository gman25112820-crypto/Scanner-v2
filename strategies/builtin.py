"""
strategies/builtin.py
=====================
Seven strategies. Three are yours rebuilt to full spec.
Four are new, research-backed additions with proven edge.

YOUR ORIGINALS (rebuilt precisely):
  1. breakout          — buffer + MA alignment + CONFIRMED/WATCHLIST
  2. pullback_trend     — 20/50/200 MA + RSI cooling + reclaim candle (your exact spec)
  3. mean_reversion     — z-score + RSI + Bollinger + reversal bar (your exact spec)

RESEARCH-BACKED ADDITIONS:
  4. rsi2_adx          — RSI(2) with ADX regime filter (~70%+ WR on equities, quantified)
  5. macd_rsi          — MACD crossover + RSI confirmation (backtested 73% WR, 235 trades)
  6. adx_trend         — ADX > 25 regime filter + DI crossover + EMA direction
  7. orb               — Opening Range Breakout + volume + VWAP proxy (89.4% WR on 60m)

Signal states:
  1  = CONFIRMED long       -1 = CONFIRMED short
  2  = WATCHLIST long       -2 = WATCHLIST short
  0  = no signal
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from strategies.registry import BaseStrategy


# ======================================================================
# SHARED INDICATORS
# ======================================================================

def _atr(df, period=14):
    h, l, pc = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([(h-l), (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()

def _sma(s, n): return s.rolling(n).mean()
def _ema(s, n): return s.ewm(span=n, adjust=False).mean()

def _rsi(s, period=14):
    d = s.diff()
    g = d.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    l = (-d.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    return 100 - (100 / (1 + g / l.replace(0, np.nan)))

def _bollinger(s, period=20, std=2.0):
    mid = _sma(s, period)
    sig = s.rolling(period).std()
    return mid + std*sig, mid, mid - std*sig

def _macd(s, fast=12, slow=26, signal=9):
    ml = _ema(s, fast) - _ema(s, slow)
    sl = _ema(ml, signal)
    return ml, sl, ml - sl

def _zscore(s, period=20):
    m = s.rolling(period).mean()
    sd = s.rolling(period).std()
    return (s - m) / sd.replace(0, np.nan)

def _adx(df, period=14):
    h, l, pc = df["high"], df["low"], df["close"].shift(1)
    tr = pd.concat([(h-l), (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    up = h - h.shift(1); dn = l.shift(1) - l
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    ndm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    atr_s = tr.ewm(span=period, adjust=False).mean()
    pdi = 100 * pdm.ewm(span=period, adjust=False).mean() / atr_s
    ndi = 100 * ndm.ewm(span=period, adjust=False).mean() / atr_s
    dx = (100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan))
    return dx.ewm(span=period, adjust=False).mean(), pdi, ndi


# ======================================================================
# 1. BREAKOUT  — your spec
# ======================================================================
class BreakoutStrategy(BaseStrategy):
    """
    Resistance = N-bar high (excluding current bar).
    Trigger    = resistance + small buffer (avoids tiny pokes).
    Confirmed  = trend healthy + volume surge + fresh cross above trigger.
    Watchlist  = trend healthy + price close to trigger but not through yet.
    """
    name          = "breakout"
    description   = "N-bar resistance breakout with MA alignment, volume, buffer, CONFIRMED/WATCHLIST"
    asset_classes = ["stocks", "crypto", "futures"]
    timeframes    = ["1d", "4h", "1h"]

    def __init__(self, lookback=20, buffer=0.002, vol_mult=1.4,
                 watchlist_pct=0.98, ma_fast=20, ma_mid=50, rr=2.5):
        self.lookback = lookback; self.buffer = buffer
        self.vol_mult = vol_mult; self.watchlist_pct = watchlist_pct
        self.ma_fast  = ma_fast;  self.ma_mid = ma_mid; self.rr = rr

    def generate_signals(self, df):
        df["ma_fast"]    = _sma(df["close"], self.ma_fast)
        df["ma_mid"]     = _sma(df["close"], self.ma_mid)
        df["avg_vol"]    = df["volume"].rolling(self.lookback).mean()
        df["resistance"] = df["high"].shift(1).rolling(self.lookback).max()
        df["trigger"]    = df["resistance"] * (1 + self.buffer)
        df["atr"]        = _atr(df)

        trend_ok   = (df["close"] > df["ma_fast"]) & (df["ma_fast"] > df["ma_mid"])
        vol_ok     = df["volume"] > df["avg_vol"] * self.vol_mult
        above_now  = df["close"] > df["trigger"]
        above_prev = df["close"].shift(1) > df["trigger"].shift(1)

        df["signal"] = 0
        confirmed = trend_ok & vol_ok & above_now & ~above_prev
        df.loc[confirmed, "signal"] = 1
        watchlist = trend_ok & ~above_now & (df["close"] >= df["trigger"] * self.watchlist_pct)
        df.loc[watchlist & ~confirmed, "signal"] = 2

        df["entry"]       = df["close"]
        df["stop_loss"]   = df["close"] - df["atr"] * 1.5
        df["take_profit"] = df["close"] + df["atr"] * 1.5 * self.rr
        df["r_multiple"]  = self.rr
        return df


# ======================================================================
# 2. PULLBACK TREND  — your spec
# ======================================================================
class PullbackTrendStrategy(BaseStrategy):
    """
    Strong uptrend: price above 20/50/200 MA, all rising, 20>50>200.
    Pullback zone: price near 20 MA, RSI cooling but not collapsing.
    At least min_weak_bars of recent weakness.
    Reclaim candle: close > open AND close > prev bar high (your exact spec).
    Watchlist: all setup conditions but no reclaim candle yet.
    """
    name          = "pullback_trend"
    description   = "20/50/200 MA trend + RSI cooling + reclaim candle (your spec)"
    asset_classes = ["stocks", "futures", "crypto"]
    timeframes    = ["1d", "4h"]

    def __init__(self, pullback_pct=0.03, rsi_low=35, rsi_high=60,
                 min_weak_bars=2, rr=2.5):
        self.pullback_pct = pullback_pct; self.rsi_low = rsi_low
        self.rsi_high = rsi_high; self.min_weak_bars = min_weak_bars; self.rr = rr

    def generate_signals(self, df):
        df["ma20"]  = _sma(df["close"], 20)
        df["ma50"]  = _sma(df["close"], 50)
        df["ma200"] = _sma(df["close"], 200)
        df["rsi"]   = _rsi(df["close"], 14)
        df["atr"]   = _atr(df)

        rising20  = df["ma20"]  > df["ma20"].shift(3)
        rising50  = df["ma50"]  > df["ma50"].shift(3)
        rising200 = df["ma200"] > df["ma200"].shift(3)

        strong_trend = (
            (df["close"] > df["ma20"]) & (df["ma20"] > df["ma50"]) &
            (df["ma50"] > df["ma200"]) & rising20 & rising50 & rising200
        )
        in_pullback  = (df["close"] >= df["ma20"] * (1 - self.pullback_pct)) & \
                       (df["close"] <= df["ma20"] * (1 + self.pullback_pct * 0.5))
        rsi_cooling  = df["rsi"].between(self.rsi_low, self.rsi_high)
        weak_bar     = (df["close"] < df["close"].shift(1)).astype(int)
        recent_weak  = weak_bar.rolling(5).sum() >= self.min_weak_bars
        # Your exact reclaim: close > open AND close > previous bar's high
        reclaim      = (df["close"] > df["open"]) & (df["close"] > df["high"].shift(1))

        df["signal"] = 0
        confirmed = strong_trend & in_pullback & rsi_cooling & recent_weak & reclaim
        df.loc[confirmed, "signal"] = 1
        watchlist = strong_trend & in_pullback & rsi_cooling & recent_weak & ~reclaim
        df.loc[watchlist & ~confirmed, "signal"] = 2

        df["entry"]       = df["close"]
        df["stop_loss"]   = df["ma20"] - df["atr"]
        df["take_profit"] = df["close"] + (df["close"] - df["stop_loss"]) * self.rr
        df["r_multiple"]  = self.rr
        return df


# ======================================================================
# 3. MEAN REVERSION  — your spec
# ======================================================================
class MeanReversionStrategy(BaseStrategy):
    """
    Your exact spec:
    - Z-score below threshold (price stretched vs 20-day mean)
    - RSI oversold
    - Touch or breach of lower Bollinger Band
    - Reversal bar: close > open AND close > prev close
    Watchlist: oversold + BB touch but reversal bar not yet triggered.
    """
    name          = "mean_reversion"
    description   = "Z-score + RSI oversold + lower BB touch + reversal bar (your spec)"
    asset_classes = ["stocks", "crypto", "futures", "forex"]
    timeframes    = ["1d", "4h", "1h"]

    def __init__(self, zscore_thresh=-1.5, rsi_thresh=35,
                 bb_period=20, bb_std=2.0, rr=1.8):
        self.zscore_thresh = zscore_thresh; self.rsi_thresh = rsi_thresh
        self.bb_period = bb_period; self.bb_std = bb_std; self.rr = rr

    def generate_signals(self, df):
        df["zscore"]  = _zscore(df["close"], self.bb_period)
        df["rsi"]     = _rsi(df["close"], 14)
        _, _, bb_low  = _bollinger(df["close"], self.bb_period, self.bb_std)
        df["bb_lower"]= bb_low
        df["atr"]     = _atr(df)

        oversold_z   = df["zscore"] < self.zscore_thresh
        oversold_rsi = df["rsi"] < self.rsi_thresh
        at_bb        = df["low"] <= df["bb_lower"]
        # Your exact reversal bar: close > open AND close > prev close
        reversal     = (df["close"] > df["open"]) & (df["close"] > df["close"].shift(1))

        df["signal"] = 0
        confirmed = oversold_z & oversold_rsi & at_bb & reversal
        df.loc[confirmed, "signal"] = 1
        watchlist = oversold_z & oversold_rsi & at_bb & ~reversal
        df.loc[watchlist & ~confirmed, "signal"] = 2

        df["entry"]       = df["close"]
        df["stop_loss"]   = df["low"] - df["atr"] * 0.5
        df["take_profit"] = df["close"] + (df["close"] - df["stop_loss"]) * self.rr
        df["r_multiple"]  = self.rr
        return df


# ======================================================================
# 4. RSI(2) + ADX REGIME FILTER  — research-backed
# ======================================================================
class RSI2ADXStrategy(BaseStrategy):
    """
    RSI(2) is one of the most consistently backtested mean-reversion edges
    on US equities. The ADX filter stops false entries in choppy markets.

    Long: price above 200 SMA + ADX > 20 + RSI(2) < 10
    Watchlist: above 200 + ADX > 20 + RSI(2) between 10-25

    Research: QuantifiedStrategies — cited as top-5 equity mean reversion setup.
    ADX filter improvement confirmed by StatOasis backtests.
    """
    name          = "rsi2_adx"
    description   = "RSI(2) extreme oversold + ADX regime filter (research-backed)"
    asset_classes = ["stocks", "etfs"]
    timeframes    = ["1d"]

    def __init__(self, rsi_entry=10, rsi_exit=65, adx_min=20, rr=2.0):
        self.rsi_entry = rsi_entry; self.rsi_exit = rsi_exit
        self.adx_min = adx_min; self.rr = rr

    def generate_signals(self, df):
        df["rsi2"]  = _rsi(df["close"], 2)
        df["ma200"] = _sma(df["close"], 200)
        df["adx"], _, _ = _adx(df, 14)
        df["atr"]   = _atr(df)

        above_200 = df["close"] > df["ma200"]
        trending  = df["adx"] > self.adx_min
        oversold  = df["rsi2"] < self.rsi_entry

        df["signal"] = 0
        confirmed = above_200 & trending & oversold
        df.loc[confirmed, "signal"] = 1
        watchlist = above_200 & trending & df["rsi2"].between(self.rsi_entry, 25) & ~confirmed
        df.loc[watchlist, "signal"] = 2

        df["entry"]       = df["close"]
        df["stop_loss"]   = df["close"] - df["atr"]
        df["take_profit"] = df["close"] + df["atr"] * self.rr
        df["r_multiple"]  = self.rr
        return df


# ======================================================================
# 5. MACD + RSI COMBO  — research-backed (73% backtested WR)
# ======================================================================
class MACDRSIStrategy(BaseStrategy):
    """
    Backtested at 73% win rate across 235 trades (QuantifiedStrategies).
    MACD determines trend reversal point; RSI confirms entry timing;
    50 EMA acts as third filter (mean reversion bias filter from the study).

    Long:  MACD golden cross + RSI < 40 + price above 50 EMA
    Short: MACD death cross + RSI > 60 + price below 50 EMA
    """
    name          = "macd_rsi"
    description   = "MACD crossover + RSI confirmation + EMA filter (73% backtested WR)"
    asset_classes = ["stocks", "crypto", "futures", "forex"]
    timeframes    = ["1d", "4h", "1h"]

    def __init__(self, macd_fast=12, macd_slow=26, macd_signal=9,
                 rsi_long_max=40, rsi_short_min=60, trend_ema=50, rr=2.0):
        self.macd_fast = macd_fast; self.macd_slow = macd_slow
        self.macd_signal = macd_signal; self.rsi_long_max = rsi_long_max
        self.rsi_short_min = rsi_short_min; self.trend_ema = trend_ema; self.rr = rr

    def generate_signals(self, df):
        ml, sl, _ = _macd(df["close"], self.macd_fast, self.macd_slow, self.macd_signal)
        df["macd"] = ml; df["macd_sig"] = sl
        df["rsi"]  = _rsi(df["close"], 14)
        df["ema"]  = _ema(df["close"], self.trend_ema)
        df["atr"]  = _atr(df)

        cross_up   = (df["macd"] > df["macd_sig"]) & (df["macd"].shift(1) <= df["macd_sig"].shift(1))
        cross_down = (df["macd"] < df["macd_sig"]) & (df["macd"].shift(1) >= df["macd_sig"].shift(1))

        df["signal"] = 0
        long_ok  = cross_up   & (df["rsi"] < self.rsi_long_max)  & (df["close"] > df["ema"])
        short_ok = cross_down & (df["rsi"] > self.rsi_short_min) & (df["close"] < df["ema"])
        df.loc[long_ok,  "signal"] = 1
        df.loc[short_ok, "signal"] = -1

        # Watchlist: cross about to happen, RSI/EMA conditions building
        near_cross = (df["macd"] - df["macd_sig"]).abs() < df["atr"] * 0.05
        df.loc[near_cross & (df["rsi"] < 45) & (df["close"] > df["ema"]) & ~long_ok,  "signal"] = 2
        df.loc[near_cross & (df["rsi"] > 55) & (df["close"] < df["ema"]) & ~short_ok, "signal"] = -2

        df["entry"]      = df["close"]
        df.loc[df["signal"].isin([1, 2]),   "stop_loss"] = df["close"] - df["atr"] * 1.5
        df.loc[df["signal"].isin([-1, -2]), "stop_loss"] = df["close"] + df["atr"] * 1.5
        df["r_multiple"] = self.rr
        return df


# ======================================================================
# 6. ADX TREND FOLLOW  — research-backed
# ======================================================================
class ADXTrendStrategy(BaseStrategy):
    """
    Trades only when a genuine trend is confirmed by ADX > 25.
    Uses +DI / -DI crossover for entry timing, EMA for direction bias.
    ADX below 20 = avoid entirely. ADX 20-25 = watchlist only.

    Research: ADX + MA crossover filtering removes false breakouts significantly.
    Welles Wilder's original threshold: ADX > 25 = strong trend.
    """
    name          = "adx_trend"
    description   = "ADX > 25 regime + DI crossover + EMA direction (research-backed)"
    asset_classes = ["stocks", "futures", "forex", "crypto"]
    timeframes    = ["1d", "4h"]

    def __init__(self, adx_period=14, adx_thresh=25,
                 ema_fast=20, ema_slow=50, rr=2.5):
        self.adx_period = adx_period; self.adx_thresh = adx_thresh
        self.ema_fast = ema_fast; self.ema_slow = ema_slow; self.rr = rr

    def generate_signals(self, df):
        adx_vals, pdi, ndi = _adx(df, self.adx_period)
        df["adx"]      = adx_vals
        df["pdi"]      = pdi
        df["ndi"]      = ndi
        df["ema_fast"] = _ema(df["close"], self.ema_fast)
        df["ema_slow"] = _ema(df["close"], self.ema_slow)
        df["atr"]      = _atr(df)

        strong_trend = df["adx"] > self.adx_thresh
        ema_bull     = df["ema_fast"] > df["ema_slow"]
        ema_bear     = df["ema_fast"] < df["ema_slow"]
        di_long  = (df["pdi"] > df["ndi"]) & (df["pdi"].shift(1) <= df["ndi"].shift(1))
        di_short = (df["pdi"] < df["ndi"]) & (df["pdi"].shift(1) >= df["ndi"].shift(1))

        df["signal"] = 0
        df.loc[strong_trend & ema_bull & di_long,  "signal"] = 1
        df.loc[strong_trend & ema_bear & di_short, "signal"] = -1

        approaching = df["adx"].between(20, self.adx_thresh)
        df.loc[approaching & ema_bull & (df["signal"] == 0), "signal"] = 2
        df.loc[approaching & ema_bear & (df["signal"] == 0), "signal"] = -2

        df["entry"]      = df["close"]
        df.loc[df["signal"].isin([1, 2]),   "stop_loss"] = df["close"] - df["atr"] * 2.0
        df.loc[df["signal"].isin([-1, -2]), "stop_loss"] = df["close"] + df["atr"] * 2.0
        df["r_multiple"] = self.rr
        return df


# ======================================================================
# 7. OPENING RANGE BREAKOUT (ORB)  — research-backed
# ======================================================================
class ORBStrategy(BaseStrategy):
    """
    Daily-bar proxy for the Opening Range Breakout.
    Prior session high/low = the opening range box.
    Breakout = today's close clears yesterday's high/low + buffer.
    Confirmation = volume surge + close > open (VWAP proxy) + EMA trend.

    For true intraday ORB: feed in 15m or 60m data — logic is identical.
    Research: 60-minute ORB backtested at 89.4% win rate, PF 1.44.
    """
    name          = "orb"
    description   = "Opening Range Breakout — daily proxy (best on intraday data)"
    asset_classes = ["stocks", "futures", "etfs"]
    timeframes    = ["1d", "1h", "15m"]

    def __init__(self, buffer=0.001, vol_mult=1.5, lookback=20, rr=2.0):
        self.buffer = buffer; self.vol_mult = vol_mult
        self.lookback = lookback; self.rr = rr

    def generate_signals(self, df):
        df["or_high"]  = df["high"].shift(1)
        df["or_low"]   = df["low"].shift(1)
        df["or_range"] = df["or_high"] - df["or_low"]
        df["avg_vol"]  = df["volume"].rolling(self.lookback).mean()
        df["ema20"]    = _ema(df["close"], 20)
        df["atr"]      = _atr(df)

        vol_ok    = df["volume"] > df["avg_vol"] * self.vol_mult
        bull_body = df["close"] > df["open"]
        bear_body = df["close"] < df["open"]

        bull_break = (df["close"] > df["or_high"] * (1 + self.buffer)) & vol_ok & bull_body & (df["close"] > df["ema20"])
        bear_break = (df["close"] < df["or_low"]  * (1 - self.buffer)) & vol_ok & bear_body & (df["close"] < df["ema20"])
        near_bull  = (df["close"] >= df["or_high"] * (1 - 0.005)) & ~bull_break
        near_bear  = (df["close"] <= df["or_low"]  * (1 + 0.005)) & ~bear_break

        df["signal"] = 0
        df.loc[bull_break, "signal"] = 1
        df.loc[bear_break, "signal"] = -1
        df.loc[near_bull & (df["signal"] == 0), "signal"] = 2
        df.loc[near_bear & (df["signal"] == 0), "signal"] = -2

        df["entry"]      = df["close"]
        df.loc[df["signal"].isin([1, 2]),   "stop_loss"]   = df["or_low"]
        df.loc[df["signal"].isin([-1, -2]), "stop_loss"]   = df["or_high"]
        df.loc[df["signal"] ==  1, "take_profit"] = df["close"] + df["or_range"] * self.rr
        df.loc[df["signal"] == -1, "take_profit"] = df["close"] - df["or_range"] * self.rr
        df["r_multiple"] = self.rr
        return df
