# Scanner — Trader's Encyclopedia & Strategy Platform

A professional Python trading platform built from scratch.

## Structure
```
scanner/
├── main.py                  # Entry point
├── core/engine.py           # Master engine — wires everything together
├── strategies/
│   ├── registry.py          # Base class + auto-discovery
│   └── builtin.py           # Breakout, VWAP Fade, EMA Trend
├── backtester/runner.py     # Walk-forward backtester + metrics
├── allocator/engine.py      # Monte Carlo + Kelly + Correlation + Scoring
├── journal/tracker.py       # Trade journal + stats
├── data/loader.py           # yfinance + CSV data loader
├── utils/logger.py          # Logging
├── config/watchlist.txt     # Your symbols
└── output/                  # All results saved here
```

## Quick Start
```bash
pip install -r requirements.txt

# Run everything
python main.py

# Just scan for signals
python main.py --mode scan

# Backtest a specific strategy
python main.py --mode backtest --strategy breakout

# Run allocator
python main.py --mode allocate

# View journal
python main.py --mode journal
```

## Adding a New Strategy
1. Create a file in `strategies/` e.g. `strategies/my_setup.py`
2. Inherit from `BaseStrategy`
3. Implement `generate_signals(df)` — return df with a `signal` column (1=long, -1=short, 0=none)
4. It auto-registers. Run `python main.py --mode scan` and it appears.

## Output
- `output/backtest/` — trade logs and metrics per strategy/symbol
- `output/allocator/` — strategy scores, weights, Kelly sizing
- `output/journal/` — your live trade journal
- `output/logs/` — full debug log
