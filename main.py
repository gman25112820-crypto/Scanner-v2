"""
Scanner — Trader's Encyclopedia & Strategy Platform
====================================================
Entry point. Run this to launch the full Scanner system.
"""
from __future__ import annotations
import argparse
from core.engine import ScannerEngine


def main():
    parser = argparse.ArgumentParser(description="Scanner Trading Platform")
    parser.add_argument("--mode", choices=["scan", "backtest", "allocate", "journal", "all"],
                        default="all", help="Which module to run")
    parser.add_argument("--strategy", type=str, default=None, help="Run a specific strategy only")
    parser.add_argument("--symbol", type=str, default=None, help="Run on a specific symbol only")
    args = parser.parse_args()

    engine = ScannerEngine()

    if args.mode == "scan":
        engine.run_scanner(strategy=args.strategy, symbol=args.symbol)
    elif args.mode == "backtest":
        engine.run_backtest(strategy=args.strategy, symbol=args.symbol)
    elif args.mode == "allocate":
        engine.run_allocator()
    elif args.mode == "journal":
        engine.run_journal()
    else:
        engine.run_all()


if __name__ == "__main__":
    main()
