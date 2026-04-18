"""utils/logger.py — Consistent logging across all Scanner modules."""
from __future__ import annotations
import logging
from pathlib import Path

Path("output/logs").mkdir(parents=True, exist_ok=True)


def setup_logger(name: str) -> logging.Logger:
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
                            datefmt="%H:%M:%S")
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    fh = logging.FileHandler("output/logs/scanner.log")
    fh.setFormatter(fmt)
    log.addHandler(ch)
    log.addHandler(fh)
    return log
