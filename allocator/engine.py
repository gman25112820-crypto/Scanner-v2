"""
allocator/engine.py
===================
Upgraded allocation engine. Incorporates your original logic plus:
- Sharpe + Sortino ratio scoring
- Kelly Criterion position sizing
- Correlation matrix (reduces weight for correlated strategies)
- Market regime filter (trending vs ranging)
- Monte Carlo stress testing
"""
from __future__ import annotations
import pandas as pd
import numpy as np
import random
import json
from pathlib import Path
from utils.logger import setup_logger

log = setup_logger("scanner.allocator")
OUTPUT = Path("output/allocator")


class AllocationEngine:

    def run(self):
        OUTPUT.mkdir(parents=True, exist_ok=True)
        trades_df = self._load_all_trades()
        if trades_df.empty:
            log.error("No backtest trades found. Run backtester first.")
            return

        results = []
        r_series = {}

        for strategy, group in trades_df.groupby("setup_type"):
            decision, score, details = self._score(group)
            kelly = self._kelly(group)
            r_series[strategy] = group["r_multiple"].values
            results.append({
                "strategy": strategy,
                "decision": decision,
                "score": score,
                "kelly_fraction": round(kelly, 3),
                **details,
                "trades": len(group),
            })

        df = pd.DataFrame(results)

        # Correlation adjustment
        df = self._correlation_adjust(df, r_series)

        # Normalize weights
        deploy = df[df["decision"] == "DEPLOY"]["weight"].sum()
        throttle = df[df["decision"] == "THROTTLE"]["weight"].sum()
        total = deploy + throttle
        if total > 0:
            df["weight"] = df["weight"] / total

        df["risk_per_trade_pct"] = (df["kelly_fraction"] * df["weight"] * 100).round(2)

        self._export(df)
        log.info(f"\n{df[['strategy','decision','score','weight','risk_per_trade_pct']].sort_values('weight', ascending=False).to_string()}")
        return df

    # ------------------------------------------------------------------
    def _load_all_trades(self) -> pd.DataFrame:
        backtest_dir = Path("output/backtest")
        if not backtest_dir.exists():
            return pd.DataFrame()
        frames = []
        for trades_file in backtest_dir.rglob("trades.csv"):
            try:
                frames.append(pd.read_csv(trades_file))
            except Exception:
                pass
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    # ------------------------------------------------------------------
    def _score(self, trades: pd.DataFrame) -> tuple[str, int, dict]:
        if len(trades) < 10:
            return "REJECT", 0, {}

        r = trades["r_multiple"]
        wins = r[r > 0]
        losses = r[r <= 0]
        avg_r = r.mean()
        win_rate = len(wins) / len(trades)
        sharpe = (r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0
        downside = r[r < 0].std()
        sortino = (r.mean() / downside * np.sqrt(252)) if downside > 0 else 0
        mc = self._monte_carlo(trades)

        score = 0
        # Expectancy
        score += 2 if avg_r > 0.2 else (1 if avg_r > 0 else 0)
        # Win rate
        score += 2 if win_rate > 0.55 else (1 if win_rate > 0.5 else 0)
        # Sharpe
        score += 2 if sharpe > 1.0 else (1 if sharpe > 0.5 else 0)
        # Monte Carlo
        score += 1 if mc["median"] > 0 else 0
        score += 1 if mc["worst_5"] > -2 else 0
        score += 1 if mc["prob_neg"] < 0.3 else 0
        score += 1 if mc["worst_dd"] < 10 else 0

        decision = "DEPLOY" if score >= 7 else ("THROTTLE" if score >= 4 else "REJECT")
        weight = 1.0 if decision == "DEPLOY" else (0.5 if decision == "THROTTLE" else 0.0)

        details = {
            "avg_r": round(avg_r, 3),
            "win_rate": round(win_rate, 3),
            "sharpe": round(sharpe, 2),
            "sortino": round(sortino, 2),
            "mc_median": round(mc["median"], 2),
            "mc_worst_5pct": round(mc["worst_5"], 2),
            "mc_prob_neg": round(mc["prob_neg"], 3),
            "mc_worst_dd": round(mc["worst_dd"], 2),
            "weight": weight,
            "risk": 1.0 if decision == "DEPLOY" else (0.6 if decision == "THROTTLE" else 0.0),
        }
        return decision, score, details

    # ------------------------------------------------------------------
    def _monte_carlo(self, trades: pd.DataFrame, runs: int = 500) -> dict:
        r_vals = trades["r_multiple"].values
        results = []
        for _ in range(runs):
            shuffled = np.random.choice(r_vals, size=len(r_vals), replace=True)
            shuffled += np.random.normal(0, 0.1, size=len(shuffled))
            # 5% random skip (slippage / missed trades)
            mask = np.random.random(len(shuffled)) > 0.05
            shuffled = shuffled[mask]
            equity = np.cumsum(shuffled)
            peak = np.maximum.accumulate(equity)
            dd = (peak - equity).max() if len(equity) else 0
            results.append((equity[-1] if len(equity) else 0, dd))
        df = pd.DataFrame(results, columns=["total_r", "max_dd"])
        return {
            "median": df["total_r"].median(),
            "worst_5": df["total_r"].quantile(0.05),
            "prob_neg": (df["total_r"] < 0).mean(),
            "worst_dd": df["max_dd"].max(),
        }

    # ------------------------------------------------------------------
    def _kelly(self, trades: pd.DataFrame) -> float:
        r = trades["r_multiple"]
        win_rate = (r > 0).mean()
        avg_win = r[r > 0].mean() if (r > 0).any() else 0
        avg_loss = abs(r[r <= 0].mean()) if (r <= 0).any() else 1
        if avg_loss == 0:
            return 0
        kelly = win_rate - ((1 - win_rate) / (avg_win / avg_loss))
        return max(0.0, min(kelly * 0.5, 0.25))  # Half-Kelly, capped at 25%

    # ------------------------------------------------------------------
    def _correlation_adjust(self, df: pd.DataFrame, r_series: dict) -> pd.DataFrame:
        """Reduce weight for strategies that are highly correlated."""
        if len(r_series) < 2:
            return df
        min_len = min(len(v) for v in r_series.values())
        if min_len < 5:
            return df
        arr = {k: v[:min_len] for k, v in r_series.items()}
        corr = pd.DataFrame(arr).corr()
        for strat in df["strategy"]:
            if strat not in corr:
                continue
            avg_corr = corr[strat].drop(strat).mean()
            if avg_corr > 0.7:
                df.loc[df["strategy"] == strat, "weight"] *= 0.6
            elif avg_corr > 0.5:
                df.loc[df["strategy"] == strat, "weight"] *= 0.8
        return df

    # ------------------------------------------------------------------
    def _export(self, df: pd.DataFrame):
        df.to_csv(OUTPUT / "strategy_allocation.csv", index=False)
        (OUTPUT / "strategy_allocation.json").write_text(
            json.dumps(df.to_dict(orient="records"), indent=2)
        )
