"""
╔══════════════════════════════════════════════════════════════════════════════╗
║              RAGE ENGINE V4 — broker_alpaca.py                             ║
║              Alpaca Markets Integration (Paper + Live)                      ║
║              🏴󠁧󠁢󠁷󠁬󠁳󠁥 Cymru am byth 🐉                                            ║
╚══════════════════════════════════════════════════════════════════════════════╝

SETUP:
    pip install alpaca-py

ENV VARS (add to .env or set in environment):
    ALPACA_API_KEY     — your Alpaca API key
    ALPACA_SECRET_KEY  — your Alpaca secret key
    ALPACA_PAPER       — "true" for paper trading (default), "false" for live

USAGE:
    from broker_alpaca import AlpacaBroker

    broker = AlpacaBroker()
    broker.connect()

    # Place a signal from RAGE Engine
    result = broker.place_signal(signal_dict)

    # Get account summary
    info = broker.get_account_info()

    # Check open positions
    positions = broker.get_positions()
"""

import os
import logging
import time
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)s]  %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("RAGE.Alpaca")


# ── Dependency guard ──────────────────────────────────────────────────────────
try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import (
        MarketOrderRequest,
        LimitOrderRequest,
        StopLossRequest,
        TakeProfitRequest,
        TrailingStopOrderRequest,
    )
    from alpaca.trading.enums import (
        OrderSide,
        TimeInForce,
        OrderStatus,
        AssetClass,
        PositionSide,
    )
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestQuoteRequest, StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    ALPACA_AVAILABLE = True
except ImportError:
    ALPACA_AVAILABLE = False
    log.warning(
        "alpaca-py not installed. Run:  pip install alpaca-py\n"
        "Broker will operate in STUB mode — no real orders placed."
    )


# ── Constants ─────────────────────────────────────────────────────────────────
PAPER_BASE_URL = "https://paper-api.alpaca.markets"
LIVE_BASE_URL  = "https://api.alpaca.markets"

DEFAULT_RISK_PCT      = 0.01   # 1% account risk per trade
DEFAULT_MAX_POSITION  = 0.05   # 5% of portfolio max per symbol
DEFAULT_SL_ATR_MULT   = 1.5    # Stop-loss = 1.5 × ATR
DEFAULT_TP_ATR_MULT   = 3.0    # Take-profit = 3.0 × ATR (2:1 RR)
MIN_SIGNAL_SCORE      = 50.0   # Minimum RAGE score to trade
MAX_OPEN_POSITIONS    = 10     # Portfolio concentration limit
ORDER_TIMEOUT_SECS    = 30     # Cancel unfilled limit orders after N seconds


# ── Data containers ───────────────────────────────────────────────────────────
@dataclass
class OrderResult:
    success:    bool
    order_id:   Optional[str] = None
    symbol:     Optional[str] = None
    side:       Optional[str] = None
    qty:        Optional[float] = None
    order_type: Optional[str] = None
    status:     Optional[str] = None
    filled_avg: Optional[float] = None
    message:    str = ""
    timestamp:  str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return self.__dict__


@dataclass
class AccountInfo:
    connected:       bool
    mode:            str        # "paper" or "live"
    equity:          float = 0.0
    cash:            float = 0.0
    buying_power:    float = 0.0
    portfolio_value: float = 0.0
    day_pnl:         float = 0.0
    day_pnl_pct:     float = 0.0
    open_positions:  int   = 0
    message:         str   = ""

    def to_dict(self) -> dict:
        return self.__dict__


# ══════════════════════════════════════════════════════════════════════════════
#   AlpacaBroker
# ══════════════════════════════════════════════════════════════════════════════
class AlpacaBroker:
    """
    Full-featured Alpaca broker for RAGE Engine V4.

    Handles:
      • Paper / live mode switching via env vars
      • Signal ingestion from RAGE live-signals output
      • Position sizing (risk-based or fixed-lot)
      • Market, limit, bracket orders
      • Stop-loss / take-profit attachment
      • Position & order management
      • Account monitoring
    """

    # ── Init ──────────────────────────────────────────────────────────────────
    def __init__(
        self,
        api_key:    Optional[str] = None,
        secret_key: Optional[str] = None,
        paper:      Optional[bool] = None,
    ):
        self.api_key    = api_key    or os.getenv("ALPACA_API_KEY",    "")
        self.secret_key = secret_key or os.getenv("ALPACA_SECRET_KEY", "")

        env_paper = os.getenv("ALPACA_PAPER", "true").lower()
        if paper is None:
            paper = env_paper != "false"
        self.paper = paper

        self.mode = "paper" if self.paper else "live"
        self._client:      Optional[TradingClient]            = None
        self._data_client: Optional[StockHistoricalDataClient] = None
        self._connected    = False

        # Risk / sizing config (can be overridden after init)
        self.risk_pct         = DEFAULT_RISK_PCT
        self.max_position_pct = DEFAULT_MAX_POSITION
        self.sl_atr_mult      = DEFAULT_SL_ATR_MULT
        self.tp_atr_mult      = DEFAULT_TP_ATR_MULT
        self.min_signal_score = MIN_SIGNAL_SCORE
        self.max_open_positions = MAX_OPEN_POSITIONS

        log.info(f"AlpacaBroker initialised — mode: {self.mode.upper()}")

    # ── Connection ────────────────────────────────────────────────────────────
    def connect(self) -> bool:
        """Establish connection to Alpaca. Returns True if successful."""
        if not ALPACA_AVAILABLE:
            log.warning("alpaca-py missing — stub mode active.")
            self._connected = False
            return False

        if not self.api_key or not self.secret_key:
            log.error(
                "Missing credentials. Set ALPACA_API_KEY and ALPACA_SECRET_KEY "
                "as environment variables or pass them to AlpacaBroker()."
            )
            return False

        try:
            self._client = TradingClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
                paper=self.paper,
            )
            self._data_client = StockHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.secret_key,
            )
            # Verify credentials by fetching account
            acct = self._client.get_account()
            self._connected = True
            log.info(
                f"✅ Connected to Alpaca [{self.mode.upper()}] — "
                f"Account #{acct.account_number}  "
                f"Equity: ${float(acct.equity):,.2f}"
            )
            return True

        except Exception as exc:
            log.error(f"Alpaca connection failed: {exc}")
            self._connected = False
            return False

    def disconnect(self):
        """Clean disconnect."""
        self._client      = None
        self._data_client = None
        self._connected   = False
        log.info("Alpaca broker disconnected.")

    @property
    def connected(self) -> bool:
        return self._connected and self._client is not None

    # ── Account info ──────────────────────────────────────────────────────────
    def get_account_info(self) -> AccountInfo:
        """Return structured account summary for the RAGE dashboard."""
        if not self.connected:
            return AccountInfo(connected=False, mode=self.mode,
                               message="Not connected")
        try:
            acct = self._client.get_account()
            positions = self._client.get_all_positions()

            equity   = float(acct.equity)
            prev_eq  = float(acct.last_equity)
            day_pnl  = equity - prev_eq
            day_pct  = (day_pnl / prev_eq * 100) if prev_eq else 0.0

            return AccountInfo(
                connected       = True,
                mode            = self.mode,
                equity          = equity,
                cash            = float(acct.cash),
                buying_power    = float(acct.buying_power),
                portfolio_value = float(acct.portfolio_value),
                day_pnl         = day_pnl,
                day_pnl_pct     = day_pct,
                open_positions  = len(positions),
            )
        except Exception as exc:
            log.error(f"get_account_info error: {exc}")
            return AccountInfo(connected=False, mode=self.mode, message=str(exc))

    # ── Positions ─────────────────────────────────────────────────────────────
    def get_positions(self) -> list[dict]:
        """Return all open positions as a list of dicts (DataFrame-friendly)."""
        if not self.connected:
            return []
        try:
            positions = self._client.get_all_positions()
            result = []
            for p in positions:
                result.append({
                    "symbol":       p.symbol,
                    "qty":          float(p.qty),
                    "side":         p.side.value if hasattr(p.side, "value") else str(p.side),
                    "avg_entry":    float(p.avg_entry_price),
                    "current_price":float(p.current_price),
                    "market_value": float(p.market_value),
                    "unrealised_pl":float(p.unrealized_pl),
                    "unrealised_pct":float(p.unrealized_plpc) * 100,
                    "cost_basis":   float(p.cost_basis),
                })
            return result
        except Exception as exc:
            log.error(f"get_positions error: {exc}")
            return []

    def get_position(self, symbol: str) -> Optional[dict]:
        """Return position for a single symbol, or None if flat."""
        positions = self.get_positions()
        symbol = symbol.upper()
        for p in positions:
            if p["symbol"] == symbol:
                return p
        return None

    def close_position(self, symbol: str) -> OrderResult:
        """Close (flatten) the full position for a symbol."""
        if not self.connected:
            return OrderResult(success=False, message="Not connected")
        try:
            resp = self._client.close_position(symbol.upper())
            log.info(f"Closed position: {symbol}")
            return OrderResult(
                success    = True,
                order_id   = str(resp.id),
                symbol     = symbol.upper(),
                status     = resp.status.value if hasattr(resp.status, "value") else str(resp.status),
                message    = "Position closed",
            )
        except Exception as exc:
            log.error(f"close_position error ({symbol}): {exc}")
            return OrderResult(success=False, symbol=symbol, message=str(exc))

    def close_all_positions(self) -> list[OrderResult]:
        """Flatten everything — emergency exit."""
        if not self.connected:
            return [OrderResult(success=False, message="Not connected")]
        try:
            responses = self._client.close_all_positions(cancel_orders=True)
            results = []
            for r in responses:
                results.append(OrderResult(
                    success  = True,
                    order_id = str(r.id) if hasattr(r, "id") else None,
                    message  = "Closed in bulk",
                ))
            log.warning(f"⚠️  Closed ALL positions ({len(results)} trades)")
            return results
        except Exception as exc:
            log.error(f"close_all_positions error: {exc}")
            return [OrderResult(success=False, message=str(exc))]

    # ── Orders ────────────────────────────────────────────────────────────────
    def get_orders(self, status: str = "open") -> list[dict]:
        """Return open or recent orders."""
        if not self.connected:
            return []
        try:
            from alpaca.trading.requests import GetOrdersRequest
            from alpaca.trading.enums import QueryOrderStatus
            status_map = {
                "open":   QueryOrderStatus.OPEN,
                "closed": QueryOrderStatus.CLOSED,
                "all":    QueryOrderStatus.ALL,
            }
            req = GetOrdersRequest(status=status_map.get(status, QueryOrderStatus.OPEN))
            orders = self._client.get_orders(filter=req)
            result = []
            for o in orders:
                result.append({
                    "id":          str(o.id),
                    "symbol":      o.symbol,
                    "side":        o.side.value,
                    "qty":         float(o.qty or 0),
                    "filled_qty":  float(o.filled_qty or 0),
                    "order_type":  o.order_type.value if hasattr(o.order_type, "value") else str(o.order_type),
                    "status":      o.status.value,
                    "created_at":  str(o.created_at),
                    "filled_avg":  float(o.filled_avg_price) if o.filled_avg_price else None,
                })
            return result
        except Exception as exc:
            log.error(f"get_orders error: {exc}")
            return []

    def cancel_order(self, order_id: str) -> bool:
        """Cancel a specific order by ID."""
        if not self.connected:
            return False
        try:
            self._client.cancel_order_by_id(order_id)
            log.info(f"Order cancelled: {order_id}")
            return True
        except Exception as exc:
            log.error(f"cancel_order error: {exc}")
            return False

    def cancel_all_orders(self) -> bool:
        """Cancel every open order."""
        if not self.connected:
            return False
        try:
            self._client.cancel_orders()
            log.info("All open orders cancelled.")
            return True
        except Exception as exc:
            log.error(f"cancel_all_orders error: {exc}")
            return False

    # ── Market data ───────────────────────────────────────────────────────────
    def get_latest_quote(self, symbol: str) -> Optional[dict]:
        """Fetch latest bid/ask quote for a symbol."""
        if not self.connected or self._data_client is None:
            return None
        try:
            req  = StockLatestQuoteRequest(symbol_or_symbols=symbol.upper())
            resp = self._data_client.get_stock_latest_quote(req)
            q    = resp[symbol.upper()]
            return {
                "symbol":    symbol.upper(),
                "bid":       float(q.bid_price),
                "ask":       float(q.ask_price),
                "mid":       (float(q.bid_price) + float(q.ask_price)) / 2,
                "bid_size":  float(q.bid_size),
                "ask_size":  float(q.ask_size),
                "timestamp": str(q.timestamp),
            }
        except Exception as exc:
            log.error(f"get_latest_quote error ({symbol}): {exc}")
            return None

    # ── Position sizing ───────────────────────────────────────────────────────
    def _calc_position_size(
        self,
        symbol:     str,
        entry:      float,
        stop_loss:  Optional[float] = None,
        equity:     Optional[float] = None,
    ) -> int:
        """
        Risk-based position sizing.
        Risk = risk_pct × equity
        Qty  = Risk / (entry - stop_loss)
        Capped at max_position_pct × equity / entry
        """
        if equity is None:
            acct_info = self.get_account_info()
            equity = acct_info.equity if acct_info.connected else 0.0

        if equity <= 0:
            return 1

        risk_dollars = equity * self.risk_pct
        max_dollars  = equity * self.max_position_pct

        if stop_loss and abs(entry - stop_loss) > 0:
            risk_per_share = abs(entry - stop_loss)
            qty_by_risk    = risk_dollars / risk_per_share
        else:
            # No stop defined — use 2% of entry as implicit risk
            qty_by_risk = risk_dollars / (entry * 0.02)

        qty_by_max = max_dollars / entry
        qty = int(min(qty_by_risk, qty_by_max))
        return max(qty, 1)

    # ── Core order methods ────────────────────────────────────────────────────
    def place_market_order(
        self,
        symbol:    str,
        side:      str,        # "buy" or "sell"
        qty:       int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        tif:       str = "day",
    ) -> OrderResult:
        """Place a market order, optionally with bracket SL/TP."""
        if not self.connected:
            return OrderResult(success=False, symbol=symbol,
                               message="Not connected")
        try:
            side_enum = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            tif_enum  = TimeInForce.DAY if tif.lower() == "day" else TimeInForce.GTC

            # Build order request
            if stop_loss and take_profit:
                req = MarketOrderRequest(
                    symbol       = symbol.upper(),
                    qty          = qty,
                    side         = side_enum,
                    time_in_force= tif_enum,
                    order_class  = "bracket",
                    stop_loss    = StopLossRequest(stop_price=round(stop_loss, 2)),
                    take_profit  = TakeProfitRequest(limit_price=round(take_profit, 2)),
                )
            elif stop_loss:
                req = MarketOrderRequest(
                    symbol       = symbol.upper(),
                    qty          = qty,
                    side         = side_enum,
                    time_in_force= tif_enum,
                    order_class  = "oto",
                    stop_loss    = StopLossRequest(stop_price=round(stop_loss, 2)),
                )
            else:
                req = MarketOrderRequest(
                    symbol       = symbol.upper(),
                    qty          = qty,
                    side         = side_enum,
                    time_in_force= tif_enum,
                )

            order = self._client.submit_order(req)
            log.info(
                f"📤 MARKET {side.upper()} {qty}× {symbol.upper()} "
                f"| SL={stop_loss} TP={take_profit} | ID={order.id}"
            )
            return OrderResult(
                success    = True,
                order_id   = str(order.id),
                symbol     = symbol.upper(),
                side       = side.upper(),
                qty        = qty,
                order_type = "market",
                status     = order.status.value,
                message    = "Market order submitted",
            )

        except Exception as exc:
            log.error(f"place_market_order error ({symbol}): {exc}")
            return OrderResult(success=False, symbol=symbol, message=str(exc))

    def place_limit_order(
        self,
        symbol:      str,
        side:        str,
        qty:         int,
        limit_price: float,
        stop_loss:   Optional[float] = None,
        take_profit: Optional[float] = None,
        tif:         str = "day",
    ) -> OrderResult:
        """Place a limit order with optional bracket."""
        if not self.connected:
            return OrderResult(success=False, symbol=symbol,
                               message="Not connected")
        try:
            side_enum = OrderSide.BUY if side.lower() == "buy" else OrderSide.SELL
            tif_enum  = TimeInForce.DAY if tif.lower() == "day" else TimeInForce.GTC

            if stop_loss and take_profit:
                req = LimitOrderRequest(
                    symbol       = symbol.upper(),
                    qty          = qty,
                    side         = side_enum,
                    limit_price  = round(limit_price, 2),
                    time_in_force= tif_enum,
                    order_class  = "bracket",
                    stop_loss    = StopLossRequest(stop_price=round(stop_loss, 2)),
                    take_profit  = TakeProfitRequest(limit_price=round(take_profit, 2)),
                )
            else:
                req = LimitOrderRequest(
                    symbol       = symbol.upper(),
                    qty          = qty,
                    side         = side_enum,
                    limit_price  = round(limit_price, 2),
                    time_in_force= tif_enum,
                )

            order = self._client.submit_order(req)
            log.info(
                f"📤 LIMIT {side.upper()} {qty}× {symbol.upper()} "
                f"@ ${limit_price:.2f} | SL={stop_loss} TP={take_profit}"
            )
            return OrderResult(
                success    = True,
                order_id   = str(order.id),
                symbol     = symbol.upper(),
                side       = side.upper(),
                qty        = qty,
                order_type = "limit",
                status     = order.status.value,
                message    = f"Limit order submitted @ {limit_price:.2f}",
            )

        except Exception as exc:
            log.error(f"place_limit_order error ({symbol}): {exc}")
            return OrderResult(success=False, symbol=symbol, message=str(exc))

    # ── RAGE signal ingestion ─────────────────────────────────────────────────
    def place_signal(
        self,
        signal: dict,
        order_type: str = "market",
        use_bracket: bool = True,
    ) -> OrderResult:
        """
        Primary entry point for RAGE Engine live signals.

        Expects signal dict with keys produced by RAGE live_signals:
            symbol      : str   — e.g. "AAPL"
            direction   : str   — "LONG" | "SHORT"
            score       : float — RAGE composite score (0–100)
            entry_price : float — current/suggested entry
            stop_loss   : float — (optional) pre-calculated SL
            take_profit : float — (optional) pre-calculated TP
            atr         : float — (optional) ATR for SL/TP calc
            strategy    : str   — strategy name (for logging)
            timeframe   : str   — signal timeframe

        Returns OrderResult with full detail.
        """
        if not self.connected:
            return OrderResult(success=False, message="Broker not connected")

        # ── Validate signal ────────────────────────────────────────────────
        symbol = str(signal.get("symbol", "")).upper().strip()
        if not symbol:
            return OrderResult(success=False, message="Signal missing 'symbol'")

        score = float(signal.get("score", 0.0))
        if score < self.min_signal_score:
            return OrderResult(
                success=False, symbol=symbol,
                message=f"Signal score {score:.1f} below minimum {self.min_signal_score}"
            )

        direction = str(signal.get("direction", "")).upper()
        if direction not in ("LONG", "SHORT"):
            return OrderResult(
                success=False, symbol=symbol,
                message=f"Invalid direction '{direction}' — must be LONG or SHORT"
            )

        entry = float(signal.get("entry_price", 0.0))
        if entry <= 0:
            quote = self.get_latest_quote(symbol)
            if not quote:
                return OrderResult(success=False, symbol=symbol,
                                   message="Cannot determine entry price")
            entry = quote["ask"] if direction == "LONG" else quote["bid"]

        # ── Portfolio concentration check ──────────────────────────────────
        open_count = len(self.get_positions())
        if open_count >= self.max_open_positions:
            return OrderResult(
                success=False, symbol=symbol,
                message=f"Max open positions reached ({self.max_open_positions})"
            )

        existing = self.get_position(symbol)
        if existing:
            return OrderResult(
                success=False, symbol=symbol,
                message=f"Position already open for {symbol} — skipping"
            )

        # ── Derive SL / TP ─────────────────────────────────────────────────
        stop_loss   = signal.get("stop_loss")
        take_profit = signal.get("take_profit")
        atr         = float(signal.get("atr", 0.0))

        if not stop_loss and atr > 0:
            if direction == "LONG":
                stop_loss   = entry - (atr * self.sl_atr_mult)
                take_profit = entry + (atr * self.tp_atr_mult)
            else:
                stop_loss   = entry + (atr * self.sl_atr_mult)
                take_profit = entry - (atr * self.tp_atr_mult)

        # ── Size the position ──────────────────────────────────────────────
        qty = self._calc_position_size(symbol, entry, stop_loss)

        side = "buy" if direction == "LONG" else "sell"

        strategy  = signal.get("strategy",  "unknown")
        timeframe = signal.get("timeframe", "unknown")
        log.info(
            f"🐉 RAGE Signal → {symbol} {direction} | "
            f"Score={score:.1f} | Strategy={strategy} | TF={timeframe} | "
            f"Entry={entry:.2f} SL={stop_loss} TP={take_profit} Qty={qty}"
        )

        # ── Place order ────────────────────────────────────────────────────
        if order_type == "limit":
            return self.place_limit_order(
                symbol      = symbol,
                side        = side,
                qty         = qty,
                limit_price = entry,
                stop_loss   = stop_loss if use_bracket else None,
                take_profit = take_profit if use_bracket else None,
            )
        else:
            return self.place_market_order(
                symbol      = symbol,
                side        = side,
                qty         = qty,
                stop_loss   = stop_loss if use_bracket else None,
                take_profit = take_profit if use_bracket else None,
            )

    # ── Batch signal processing ───────────────────────────────────────────────
    def process_signals(
        self,
        signals:     list[dict],
        order_type:  str  = "market",
        use_bracket: bool = True,
        max_per_run: int  = 3,
        min_score:   Optional[float] = None,
    ) -> list[OrderResult]:
        """
        Process a list of RAGE signals, sorted by score descending.
        Caps at max_per_run to avoid over-trading in a single cycle.
        """
        if min_score is not None:
            signals = [s for s in signals if float(s.get("score", 0)) >= min_score]

        # Sort by score descending
        signals = sorted(signals, key=lambda x: float(x.get("score", 0)), reverse=True)
        signals = signals[:max_per_run]

        results = []
        for sig in signals:
            result = self.place_signal(sig, order_type=order_type,
                                       use_bracket=use_bracket)
            results.append(result)
            if result.success:
                time.sleep(0.25)  # brief pause between orders

        placed = sum(1 for r in results if r.success)
        log.info(f"Batch complete — {placed}/{len(results)} orders placed.")
        return results

    # ── Utility ───────────────────────────────────────────────────────────────
    def is_market_open(self) -> bool:
        """Check if the US market is currently open."""
        if not self.connected:
            return False
        try:
            clock = self._client.get_clock()
            return clock.is_open
        except Exception as exc:
            log.error(f"is_market_open error: {exc}")
            return False

    def get_next_market_open(self) -> Optional[str]:
        """Return next market open time as ISO string."""
        if not self.connected:
            return None
        try:
            clock = self._client.get_clock()
            return str(clock.next_open)
        except Exception:
            return None

    def get_asset_info(self, symbol: str) -> Optional[dict]:
        """Return asset details — tradable, shortable, fractionable etc."""
        if not self.connected:
            return None
        try:
            asset = self._client.get_asset(symbol.upper())
            return {
                "symbol":       asset.symbol,
                "name":         asset.name,
                "tradable":     asset.tradable,
                "shortable":    asset.shortable,
                "fractionable": asset.fractionable,
                "marginable":   asset.marginable,
                "status":       asset.status.value,
            }
        except Exception as exc:
            log.error(f"get_asset_info error ({symbol}): {exc}")
            return None

    def health_check(self) -> dict:
        """Quick status report for the RAGE dashboard broker panel."""
        acct = self.get_account_info()
        return {
            "connected":      self.connected,
            "mode":           self.mode,
            "market_open":    self.is_market_open(),
            "next_open":      self.get_next_market_open(),
            "equity":         acct.equity,
            "cash":           acct.cash,
            "buying_power":   acct.buying_power,
            "open_positions": acct.open_positions,
            "day_pnl":        acct.day_pnl,
            "day_pnl_pct":    acct.day_pnl_pct,
            "timestamp":      datetime.now(timezone.utc).isoformat(),
        }

    def __repr__(self) -> str:
        status = "connected" if self.connected else "disconnected"
        return f"<AlpacaBroker mode={self.mode} status={status}>"


# ══════════════════════════════════════════════════════════════════════════════
#   Streamlit helper — drop into broker panel in app.py
# ══════════════════════════════════════════════════════════════════════════════
def render_broker_panel(broker: AlpacaBroker):
    """
    Streamlit component for the RAGE Engine broker panel.
    Import and call from the Live Signals page in app.py:

        from broker_alpaca import AlpacaBroker, render_broker_panel
        broker = AlpacaBroker()
        broker.connect()
        render_broker_panel(broker)
    """
    try:
        import streamlit as st
    except ImportError:
        return

    st.subheader("🏦 Alpaca Broker Panel")

    health = broker.health_check()

    # Connection badge
    if health["connected"]:
        mode_colour = "🟡" if health["mode"] == "paper" else "🔴"
        st.success(
            f"{mode_colour} Connected — **{health['mode'].upper()}** mode  |  "
            f"Market: {'🟢 OPEN' if health['market_open'] else '🔴 CLOSED'}"
        )
    else:
        st.error("❌ Broker not connected")
        if st.button("Connect"):
            broker.connect()
            st.rerun()
        return

    # Account metrics
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Equity",        f"${health['equity']:,.2f}")
    col2.metric("Cash",          f"${health['cash']:,.2f}")
    col3.metric("Buying Power",  f"${health['buying_power']:,.2f}")
    pnl_delta = f"{health['day_pnl_pct']:+.2f}%"
    col4.metric("Day P&L",
                f"${health['day_pnl']:+,.2f}",
                delta=pnl_delta,
                delta_color="normal")

    # Open positions table
    st.markdown("#### Open Positions")
    positions = broker.get_positions()
    if positions:
        import pandas as pd
        df = pd.DataFrame(positions)
        df.columns = [c.replace("_", " ").title() for c in df.columns]
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No open positions.")

    # Danger zone
    with st.expander("⚠️ Emergency Controls"):
        col_a, col_b = st.columns(2)
        if col_a.button("❌ Cancel All Orders", type="secondary"):
            broker.cancel_all_orders()
            st.warning("All open orders cancelled.")
        if col_b.button("🚨 Close ALL Positions", type="primary"):
            broker.close_all_positions()
            st.warning("All positions closed.")


# ══════════════════════════════════════════════════════════════════════════════
#   CLI smoke test — python broker_alpaca.py
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("\n" + "═" * 60)
    print("  RAGE ENGINE V4 — Alpaca Broker Smoke Test")
    print("  🏴󠁧󠁢󠁷󠁬󠁳󠁥 Cymru am byth 🐉")
    print("═" * 60)

    broker = AlpacaBroker()

    if not ALPACA_AVAILABLE:
        print("\n⚠️  alpaca-py not installed. Install with:")
        print("      pip install alpaca-py")
        print("\nModule structure is valid — ready to use once installed.\n")
    else:
        print(f"\nMode:  {broker.mode.upper()}")
        print(f"Key:   {'set' if broker.api_key else '*** NOT SET ***'}")
        print(f"Creds: {'set' if broker.secret_key else '*** NOT SET ***'}\n")

        connected = broker.connect()

        if connected:
            print("\n── Account ──────────────────────────────────────")
            health = broker.health_check()
            for k, v in health.items():
                print(f"  {k:<20} {v}")

            print("\n── Market quote test (AAPL) ─────────────────────")
            q = broker.get_latest_quote("AAPL")
            if q:
                print(f"  Bid: {q['bid']}  Ask: {q['ask']}  Mid: {q['mid']:.2f}")

            print("\n── Simulated signal (NOT placed) ─────────────────")
            test_signal = {
                "symbol":      "AAPL",
                "direction":   "LONG",
                "score":       72.5,
                "entry_price": 0.0,    # will auto-fetch
                "atr":         2.30,
                "strategy":    "MTF_EMA_RSI",
                "timeframe":   "1h",
            }
            qty = broker._calc_position_size("AAPL", 185.0, 185.0 - 2.30 * 1.5)
            print(f"  Signal:  {test_signal}")
            print(f"  Sizing:  {qty} shares (risk-based)")
            print("\n✅ Smoke test complete — broker ready.\n")
        else:
            print("\n❌ Connection failed. Check credentials in .env\n")
