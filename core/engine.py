"""
core/engine.py
==============
The central engine. Wires together scanner, backtester,
allocator, journal, and data modules.
"""
from __future__ import annotations
import logging
from pathlib import Path
from data.loader import DataLoader
from strategies.registry import StrategyRegistry
from backtester.runner import BacktestRunner
from allocator.engine import AllocationEngine
from journal.tracker import TradeJournal
from utils.logger import setup_logger

OUTPUT = Path("output")
OUTPUT.mkdir(exist_ok=True)

log = setup_logger("scanner.engine")


class ScannerEngine:
    def __init__(self):
        self.data = DataLoader()
        self.registry = StrategyRegistry()
        self.backtester = BacktestRunner()
        self.allocator = AllocationEngine()
        self.journal = TradeJournal()
        log.info("Scanner engine initialised")

    # ------------------------------------------------------------------
    def run_scanner(self, strategy=None, symbol=None):
        """Run live signal scan across all strategies and symbols."""
        log.info("Running scanner...")
        strategies = self.registry.get(strategy)
        symbols = [symbol] if symbol else self.data.get_watchlist()
        signals = []
        for strat in strategies:
            for sym in symbols:
                df = self.data.fetch(sym)
                if df is None or df.empty:
                    continue
                result = strat.scan(df, sym)
                if result:
                    signals.append(result)
                    log.info(f"  SIGNAL  {strat.name} | {sym} | {result['direction']} | {result['entry']:.2f}")
        log.info(f"Scanner complete. {len(signals)} signal(s) found.")
        return signals

    # ------------------------------------------------------------------
    def run_backtest(self, strategy=None, symbol=None):
        """Backtest all strategies and write results to output/."""
        log.info("Running backtests...")
        strategies = self.registry.get(strategy)
        symbols = [symbol] if symbol else self.data.get_watchlist()
        for strat in strategies:
            for sym in symbols:
                df = self.data.fetch(sym)
                if df is None or df.empty:
                    continue
                self.backtester.run(strat, df, sym)
        log.info("Backtests complete. Results in output/backtest/")

    # ------------------------------------------------------------------
    def run_allocator(self):
        """Score all backtested strategies and produce allocation weights."""
        log.info("Running allocator...")
        self.allocator.run()
        log.info("Allocation complete. Results in output/allocator/")

    # ------------------------------------------------------------------
    def run_journal(self):
        """Print trade journal summary."""
        log.info("Loading trade journal...")
        self.journal.summary()

    # ------------------------------------------------------------------
    def run_all(self):
        self.run_scanner()
        self.run_backtest()
        self.run_allocator()
        self.run_journal()
