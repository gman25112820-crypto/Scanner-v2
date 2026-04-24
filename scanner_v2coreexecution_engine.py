"""
core/execution_engine.py
========================
Execution Layer v1 for RAGE.

Purpose:
- Wrap strategy signals with smarter execution
- Allow up to 3 attempts per trade idea
- Re-enter on valid retests
- Adjust risk and target by attempt
- Track structure invalidation

This module is framework-agnostic enough to plug into current RAGE logic.

Typical use:
    engine = ExecutionEngineV1()
    result = engine.process_signal(...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any


# ============================================================
# Data models
# ============================================================

@dataclass
class TradeIdea:
    symbol: str
    strategy: str
    direction: str              # "long" or "short"
    signal_time: Any
    entry_price: float
    stop_price: float
    target_price: float
    structure_level: Optional[float] = None
    invalidation_level: Optional[float] = None
    pullback_level: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionState:
    symbol: str
    strategy: str
    direction: str
    active: bool = False
    attempt: int = 0
    max_attempts: int = 3

    original_entry: Optional[float] = None
    current_entry: Optional[float] = None
    current_stop: Optional[float] = None
    current_target: Optional[float] = None

    structure_level: Optional[float] = None
    invalidation_level: Optional[float] = None
    pullback_level: Optional[float] = None

    last_exit_reason: Optional[str] = None
    closed_attempts: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionDecision:
    action: str                 # "enter", "reenter", "hold", "skip", "close"
    attempt: int
    risk_fraction: float
    entry_price: Optional[float]
    stop_price: Optional[float]
    target_price: Optional[float]
    reason: str


# ============================================================
# Execution engine
# ============================================================

class ExecutionEngineV1:
    """
    v1 execution engine:
    - Attempt 1: starter size
    - Attempt 2: better pullback fill if structure holds
    - Attempt 3: final confirmation attempt
    """

    def __init__(
        self,
        max_attempts: int = 3,
        attempt_risk: Optional[dict[int, float]] = None,
        attempt_rr: Optional[dict[int, float]] = None,
        retest_tolerance_pct: float = 0.003,
        confirmation_buffer_pct: float = 0.002,
    ):
        self.max_attempts = max_attempts
        self.attempt_risk = attempt_risk or {
            1: 0.50,   # half-size probe
            2: 1.00,   # full-size best retest
            3: 0.75,   # final attempt, still meaningful but controlled
        }
        self.attempt_rr = attempt_rr or {
            1: 1.5,
            2: 2.0,
            3: 2.5,
        }
        self.retest_tolerance_pct = retest_tolerance_pct
        self.confirmation_buffer_pct = confirmation_buffer_pct

    # --------------------------------------------------------
    # Public API
    # --------------------------------------------------------

    def new_trade_idea(self, idea: TradeIdea) -> tuple[ExecutionState, ExecutionDecision]:
        state = ExecutionState(
            symbol=idea.symbol,
            strategy=idea.strategy,
            direction=idea.direction,
            active=True,
            attempt=1,
            max_attempts=self.max_attempts,
            original_entry=idea.entry_price,
            current_entry=idea.entry_price,
            current_stop=idea.stop_price,
            current_target=self._recalc_target(
                direction=idea.direction,
                entry=idea.entry_price,
                stop=idea.stop_price,
                attempt=1,
            ),
            structure_level=idea.structure_level,
            invalidation_level=idea.invalidation_level,
            pullback_level=idea.pullback_level,
            metadata=idea.metadata.copy(),
        )

        decision = ExecutionDecision(
            action="enter",
            attempt=1,
            risk_fraction=self.attempt_risk.get(1, 0.5),
            entry_price=state.current_entry,
            stop_price=state.current_stop,
            target_price=state.current_target,
            reason="initial_entry",
        )
        return state, decision

    def process_bar(
        self,
        state: ExecutionState,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
    ) -> ExecutionDecision:
        """
        Called bar by bar after a position or idea exists.
        """
        if not state.active:
            return self._maybe_reenter(state, open_price, high_price, low_price, close_price)

        # First check invalidation
        if self._structure_broken(state, high_price, low_price, close_price):
            state.active = False
            state.last_exit_reason = "structure_broken"
            return ExecutionDecision(
                action="close",
                attempt=state.attempt,
                risk_fraction=0.0,
                entry_price=None,
                stop_price=None,
                target_price=None,
                reason="structure_broken",
            )

        # Check stop/target
        if state.direction == "long":
            if low_price <= (state.current_stop or -10**9):
                state.active = False
                state.closed_attempts += 1
                state.last_exit_reason = "stop"
                return self._maybe_reenter(state, open_price, high_price, low_price, close_price, stopped=True)

            if high_price >= (state.current_target or 10**9):
                state.active = False
                state.last_exit_reason = "target"
                return ExecutionDecision(
                    action="close",
                    attempt=state.attempt,
                    risk_fraction=0.0,
                    entry_price=None,
                    stop_price=None,
                    target_price=None,
                    reason="target_hit",
                )

        else:
            if high_price >= (state.current_stop or 10**9):
                state.active = False
                state.closed_attempts += 1
                state.last_exit_reason = "stop"
                return self._maybe_reenter(state, open_price, high_price, low_price, close_price, stopped=True)

            if low_price <= (state.current_target or -10**9):
                state.active = False
                state.last_exit_reason = "target"
                return ExecutionDecision(
                    action="close",
                    attempt=state.attempt,
                    risk_fraction=0.0,
                    entry_price=None,
                    stop_price=None,
                    target_price=None,
                    reason="target_hit",
                )

        return ExecutionDecision(
            action="hold",
            attempt=state.attempt,
            risk_fraction=self.attempt_risk.get(state.attempt, 0.0),
            entry_price=state.current_entry,
            stop_price=state.current_stop,
            target_price=state.current_target,
            reason="position_active",
        )

    # --------------------------------------------------------
    # Re-entry logic
    # --------------------------------------------------------

    def _maybe_reenter(
        self,
        state: ExecutionState,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
        stopped: bool = False,
    ) -> ExecutionDecision:
        if state.closed_attempts >= state.max_attempts:
            return ExecutionDecision(
                action="skip",
                attempt=state.attempt,
                risk_fraction=0.0,
                entry_price=None,
                stop_price=None,
                target_price=None,
                reason="max_attempts_reached",
            )

        if state.invalidation_level is not None:
            if state.direction == "long" and close_price < state.invalidation_level:
                return ExecutionDecision(
                    action="skip",
                    attempt=state.attempt,
                    risk_fraction=0.0,
                    entry_price=None,
                    stop_price=None,
                    target_price=None,
                    reason="long_invalidation_hit",
                )
            if state.direction == "short" and close_price > state.invalidation_level:
                return ExecutionDecision(
                    action="skip",
                    attempt=state.attempt,
                    risk_fraction=0.0,
                    entry_price=None,
                    stop_price=None,
                    target_price=None,
                    reason="short_invalidation_hit",
                )

        if not self._valid_retest(state, high_price, low_price, close_price):
            return ExecutionDecision(
                action="skip",
                attempt=state.attempt,
                risk_fraction=0.0,
                entry_price=None,
                stop_price=None,
                target_price=None,
                reason="no_valid_retest",
            )

        if not self._confirmation_reclaim(state, close_price):
            return ExecutionDecision(
                action="skip",
                attempt=state.attempt,
                risk_fraction=0.0,
                entry_price=None,
                stop_price=None,
                target_price=None,
                reason="no_confirmation_reclaim",
            )

        next_attempt = min(state.closed_attempts + 1, state.max_attempts)

        entry = close_price
        stop = self._derive_reentry_stop(state, high_price, low_price)
        target = self._recalc_target(state.direction, entry, stop, next_attempt)

        state.active = True
        state.attempt = next_attempt
        state.current_entry = entry
        state.current_stop = stop
        state.current_target = target

        return ExecutionDecision(
            action="reenter",
            attempt=next_attempt,
            risk_fraction=self.attempt_risk.get(next_attempt, 0.0),
            entry_price=entry,
            stop_price=stop,
            target_price=target,
            reason="valid_retest_reentry" if stopped else "fresh_retest_entry",
        )

    # --------------------------------------------------------
    # Internal helpers
    # --------------------------------------------------------

    def _recalc_target(self, direction: str, entry: float, stop: float, attempt: int) -> float:
        risk = abs(entry - stop)
        rr = self.attempt_rr.get(attempt, 2.0)

        if direction == "long":
            return entry + (risk * rr)
        return entry - (risk * rr)

    def _derive_reentry_stop(self, state: ExecutionState, high_price: float, low_price: float) -> float:
        if state.direction == "long":
            if state.invalidation_level is not None:
                return state.invalidation_level
            return low_price * (1 - self.confirmation_buffer_pct)

        if state.invalidation_level is not None:
            return state.invalidation_level
        return high_price * (1 + self.confirmation_buffer_pct)

    def _structure_broken(
        self,
        state: ExecutionState,
        high_price: float,
        low_price: float,
        close_price: float,
    ) -> bool:
        if state.invalidation_level is None:
            return False

        if state.direction == "long":
            return close_price < state.invalidation_level
        return close_price > state.invalidation_level

    def _valid_retest(
        self,
        state: ExecutionState,
        high_price: float,
        low_price: float,
        close_price: float,
    ) -> bool:
        """
        Has price pulled back into a sensible retest zone without fully invalidating?
        """
        anchor = state.pullback_level or state.structure_level or state.original_entry
        if anchor is None:
            return False

        tol = anchor * self.retest_tolerance_pct

        if state.direction == "long":
            touched = low_price <= (anchor + tol)
            held = state.invalidation_level is None or low_price >= state.invalidation_level
            return touched and held

        touched = high_price >= (anchor - tol)
        held = state.invalidation_level is None or high_price <= state.invalidation_level
        return touched and held

    def _confirmation_reclaim(self, state: ExecutionState, close_price: float) -> bool:
        """
        Require price to reclaim/confirm after retest before re-entering.
        """
        anchor = state.pullback_level or state.structure_level or state.original_entry
        if anchor is None:
            return False

        buffer = anchor * self.confirmation_buffer_pct

        if state.direction == "long":
            return close_price >= (anchor + buffer)
        return close_price <= (anchor - buffer)


# ============================================================
# Convenience wrapper
# ============================================================

def build_trade_idea_from_signal(
    strategy_name: str,
    symbol: str,
    direction: str,
    signal_time: Any,
    entry_price: float,
    stop_price: float,
    target_price: float,
    structure_level: Optional[float] = None,
    invalidation_level: Optional[float] = None,
    pullback_level: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> TradeIdea:
    return TradeIdea(
        symbol=symbol,
        strategy=strategy_name,
        direction=direction,
        signal_time=signal_time,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        structure_level=structure_level,
        invalidation_level=invalidation_level,
        pullback_level=pullback_level,
        metadata=metadata or {},
    )