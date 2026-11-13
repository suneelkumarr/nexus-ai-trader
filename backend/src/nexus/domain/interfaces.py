"""Abstract interface protocols enabling Dependency Injection across layers."""

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

import pandas as pd

from nexus.domain.models import (
    OHLCVBar,
    OpenPaperPosition,
    PaperFill,
    PaperOrderRequest,
    PaperOrderResult,
    PortfolioState,
    RiskState,
    TickerQuote,
    TradeLedgerEntry,
    TradingSignal,
)


@runtime_checkable
class PublicExchangeClient(Protocol):
    """Public-endpoint-only exchange client interface (no private API keys)."""

    @property
    def exchange_id(self) -> str:
        """Return configured exchange identifier."""
        ...

    @property
    def supports_websocket(self) -> bool:
        """Return True if the exchange supports public WebSocket OHLCV/ticker streams."""
        ...

    async def fetch_ticker(self, symbol: str) -> TickerQuote:
        """Fetch latest real spot ticker quote from public REST endpoint."""
        ...

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "15m",
        since_ms: int | None = None,
        limit: int = 100,
    ) -> list[OHLCVBar]:
        """Fetch real historical spot OHLCV bars from public REST endpoint."""
        ...

    async def fetch_inr_per_usdt(self) -> Decimal:
        """Fetch live INR per 1 USDT conversion rate from real market/FX data."""
        ...

    async def watch_ticker(self, symbol: str) -> TickerQuote:
        """Await next real spot ticker update over public WebSocket."""
        ...

    async def watch_ohlcv(self, symbol: str, timeframe: str = "15m") -> list[OHLCVBar]:
        """Await next real spot OHLCV update over public WebSocket."""
        ...

    async def health_check(self) -> bool:
        """Verify upstream public exchange connectivity."""
        ...

    async def close(self) -> None:
        """Release underlying REST and WebSocket client sessions."""
        ...


@runtime_checkable
class CandleRepository(Protocol):
    """Persistence contract for historical UTC OHLCV candles."""

    async def upsert_candles(self, exchange_id: str, bars: Sequence[OHLCVBar]) -> int:
        """Idempotently store or update OHLCV bars in PostgreSQL."""
        ...

    async def get_candles(
        self,
        exchange_id: str,
        symbol: str,
        timeframe: str,
        start_utc: datetime | None = None,
        end_utc: datetime | None = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        """Load persisted UTC OHLCV bars ordered chronologically."""
        ...

    async def get_latest_timestamp(
        self, exchange_id: str, symbol: str, timeframe: str
    ) -> datetime | None:
        """Return the most recent stored UTC bar timestamp for incremental sync."""
        ...


@runtime_checkable
class MarketDataProvider(Protocol):
    """Read-only spot market data interface (real exchange feeds only)."""

    async def fetch_ticker(self, symbol: str) -> TickerQuote:
        """Fetch latest real spot ticker quote for a permitted symbol."""
        ...

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "15m", limit: int = 100
    ) -> list[OHLCVBar]:
        """Fetch real historical spot OHLCV bars."""
        ...

    async def fetch_inr_per_usdt(self) -> Decimal:
        """Fetch live INR per 1 USDT conversion rate from real market/FX data."""
        ...

    async def health_check(self) -> bool:
        """Verify upstream market feed connectivity."""
        ...

    async def close(self) -> None:
        """Release underlying HTTP/exchange client resources."""
        ...


@runtime_checkable
class RiskGuard(Protocol):
    """Validates spot-only, paper-only, and portfolio balance constraints."""

    def validate_order(
        self,
        request: PaperOrderRequest,
        portfolio: PortfolioState,
        quote: TickerQuote,
        inr_per_usdt: Decimal,
    ) -> None:
        """Raise RiskViolationError if the order violates any trading invariant."""
        ...


@runtime_checkable
class SignalRiskApprover(Protocol):
    """Approves or rejects proposed LONG entry signals before strategy emission."""

    def approve_entry(
        self,
        *,
        symbol: str,
        timestamp: datetime,
        entry_price: Decimal,
        stop_price: Decimal,
        portfolio: PortfolioState,
    ) -> tuple[bool, str | None]:
        """Return (approved, rejection_reason) for a proposed spot LONG entry."""
        ...


@runtime_checkable
class PaperExecutionEngine(Protocol):
    """Simulates spot order execution using real market quotes without live trading."""

    def execute_order(
        self,
        request: PaperOrderRequest,
        portfolio: PortfolioState,
        quote: TickerQuote,
        inr_per_usdt: Decimal,
    ) -> PaperOrderResult:
        """Execute a virtual paper trade and return the resulting fill/status."""
        ...


@runtime_checkable
class Strategy(Protocol):
    """Interface for automated quantitative spot strategies."""

    name: str

    def evaluate(self, symbol: str, candles_df: pd.DataFrame) -> TradingSignal:
        """Analyze OHLCV DataFrame and produce a trading signal."""
        ...


@runtime_checkable
class PortfolioRepository(Protocol):
    """Persistence contract for virtual paper portfolios."""

    async def get_by_id(self, portfolio_id: UUID) -> PortfolioState | None:
        """Load a portfolio and its spot holdings by ID."""
        ...

    async def get_or_create_default(self) -> PortfolioState:
        """Load the default INR 10,000 paper portfolio or create it if absent."""
        ...

    async def save(self, portfolio: PortfolioState) -> None:
        """Persist updated portfolio balances and spot holdings."""
        ...


@runtime_checkable
class PaperLedgerRepository(Protocol):
    """Persistence contract for paper orders, fills, open positions, trade ledger, and risk."""

    async def get_or_create_portfolio(
        self, portfolio_id: UUID | None = None, *, initial_capital_inr: Decimal = Decimal("10000")
    ) -> PortfolioState:
        """Load portfolio by ID (or default) and its spot holdings."""
        ...

    async def save_portfolio(self, portfolio: PortfolioState) -> None:
        """Persist portfolio cash balance and spot asset holdings."""
        ...

    async def get_or_create_risk_state(
        self, portfolio_id: UUID, *, initial_capital_inr: Decimal = Decimal("10000")
    ) -> RiskState:
        """Load persistent daily risk and kill-switch state."""
        ...

    async def save_risk_state(self, risk_state: RiskState) -> None:
        """Persist updated daily risk metrics and kill-switch status."""
        ...

    async def find_order_by_client_id(
        self, portfolio_id: UUID, client_order_id: str
    ) -> PaperOrderResult | None:
        """Check whether an order with this idempotency key already exists."""
        ...

    async def find_duplicate_signal_order(
        self, portfolio_id: UUID, symbol: str, side: str, strategy_name: str
    ) -> PaperOrderResult | None:
        """Optional lookup for recent active/filled orders."""
        ...

    async def record_order_and_fill(
        self,
        request: PaperOrderRequest,
        result: PaperOrderResult,
        fill: PaperFill | None,
    ) -> None:
        """Persist paper order and optional fill record."""
        ...

    async def cancel_pending_orders(self, portfolio_id: UUID, reason: str) -> int:
        """Cancel all pending paper orders on emergency kill switch."""
        ...

    async def get_open_positions(self, portfolio_id: UUID) -> list[OpenPaperPosition]:
        """Load all currently open virtual positions across restarts."""
        ...

    async def save_position(self, position: OpenPaperPosition) -> None:
        """Insert or update an open or closed paper position."""
        ...

    async def append_trade_ledger(self, entry: TradeLedgerEntry) -> None:
        """Append a closed round-trip trade entry to the persistent trade ledger."""
        ...

    async def commit_order_settlement(
        self,
        *,
        request: PaperOrderRequest,
        result: PaperOrderResult,
        fill: PaperFill,
        portfolio: PortfolioState,
        position: OpenPaperPosition,
        risk_state: RiskState,
        ledger_entry: TradeLedgerEntry | None = None,
    ) -> None:
        """Atomically persist order, fill, portfolio, position, ledger, and risk state."""
        ...

    async def list_trade_ledger(self, portfolio_id: UUID) -> list[TradeLedgerEntry]:
        """List closed trade ledger entries chronologically."""
        ...


@runtime_checkable
class AIAnalysisClient(Protocol):
    """Advisory LLM client contract (read-only analysis, zero order execution access)."""

    @property
    def model_name(self) -> str:
        """Return configured AI model identifier."""
        ...

    async def generate_market_analysis(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> str:
        """Submit validated feature payload and return raw strict JSON model response."""
        ...

    async def close(self) -> None:
        """Release underlying HTTP client resources."""
        ...


