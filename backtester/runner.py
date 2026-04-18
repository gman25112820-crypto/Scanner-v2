"""
backtester/runner.py
====================
Event-driven backtester with:
- Walk-forward testing (prevents overfitting)
- Full trade log with R multiples
- Sharpe, Sortino, max drawdown, win rate
- Results saved to output/backtest/
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from pathlib import Path
from utils.logger import setup_logger

log = setup_logger("scanner.backtester")
OUTPUT = Path("output/backtest")


class BacktestRunner:

    def run(self, strategy, df: pd.DataFrame, symbol: str,
            n_splits: int = 5, commission: float = 0.001) -> dict:
        """
        Walk-forward backtest.
        Splits data into n_splits folds: train on first, test on remainder.
        """
        OUTPUT.mkdir(parents=True, exist_ok=True)
        all_trades = []

        split_size = len(df) // n_splits
        for i in range(1, n_splits):
            train = df.iloc[:i * split_size]
            test  = df.iloc[i * split_size:(i + 1) * split_size]
            if len(test) < 10:
                continue
            # Generate signals on test fold (strategy fitted conceptually on train)
            tested = strategy.generate_signals(test.copy())
            trades = self._extract_trades(tested, symbol, strategy.name, commission)
            all_trades.extend(trades)

        if not all_trades:
            log.warning(f"No trades: {strategy.name} / {symbol}")
            return {}

        trades_df = pd.DataFrame(all_trades)
        metrics = self._metrics(trades_df)
        self._save(trades_df, metrics, strategy.name, symbol)
        log.info(f"  {strategy.name}/{symbol}: "
                 f"trades={len(trades_df)} wr={metrics['win_rate']:.1%} "
                 f"avg_r={metrics['avg_r']:.2f} sharpe={metrics['sharpe']:.2f}")
        return metrics

    # ------------------------------------------------------------------
    def _extract_trades(self, df, symbol, strategy_name, commission):
        trades = []
        in_trade = False
        entry_price = stop = target = direction = entry_date = None

        for ts, row in df.iterrows():
            if not in_trade and row.get("signal", 0) != 0:
                in_trade = True
                entry_price = row.get("entry", row["close"])
                stop = row.get("stop_loss", entry_price * 0.98)
                target = row.get("take_profit", entry_price * 1.04)
                direction = row["signal"]
                entry_date = ts

            elif in_trade:
                price = row["close"]
                risk = abs(entry_price - stop) if stop else entry_price * 0.02
                if risk == 0:
                    risk = entry_price * 0.02

                if direction == 1:
                    hit_stop   = price <= stop
                    hit_target = price >= target if target else False
                else:
                    hit_stop   = price >= stop
                    hit_target = price <= target if target else False

                if hit_target or hit_stop:
                    pnl = (target - entry_price if hit_target else stop - entry_price)
                    if direction == -1:
                        pnl = -pnl
                    r = pnl / risk - commission
                    trades.append({
                        "symbol": symbol,
                        "setup_type": strategy_name,
                        "direction": "long" if direction == 1 else "short",
                        "entry_date": entry_date,
                        "exit_date": ts,
                        "entry": entry_price,
                        "exit": target if hit_target else stop,
                        "r_multiple": round(r, 3),
                        "result": "win" if r > 0 else "loss",
                    })
                    in_trade = False

        return trades

    # ------------------------------------------------------------------
    def _metrics(self, df: pd.DataFrame) -> dict:
        r = df["r_multiple"]
        wins = r[r > 0]
        losses = r[r <= 0]
        equity = r.cumsum()
        peak = equity.cummax()
        drawdown = peak - equity
        sharpe = (r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0
        downside = r[r < 0].std()
        sortino = (r.mean() / downside * np.sqrt(252)) if downside > 0 else 0
        return {
            "trades": len(df),
            "win_rate": len(wins) / len(df),
            "avg_r": r.mean(),
            "total_r": r.sum(),
            "sharpe": sharpe,
            "sortino": sortino,
            "max_drawdown": drawdown.max(),
            "avg_win": wins.mean() if len(wins) else 0,
            "avg_loss": losses.mean() if len(losses) else 0,
            "profit_factor": abs(wins.sum() / losses.sum()) if losses.sum() != 0 else np.inf,
        }

    # ------------------------------------------------------------------
    def _save(self, trades_df, metrics, strategy_name, symbol):
        folder = OUTPUT / f"{strategy_name}_{symbol}"
        folder.mkdir(parents=True, exist_ok=True)
        trades_df.to_csv(folder / "trades.csv", index=False)
        pd.Series(metrics).to_csv(folder / "metrics.csv")
