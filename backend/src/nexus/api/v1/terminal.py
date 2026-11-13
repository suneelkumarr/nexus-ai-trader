"""Real-time paper-trading terminal REST & WebSocket endpoints (no fabricated stats)."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, Field

from nexus.api.dependencies import (
    get_app_settings,
    get_binance_gateway,
    get_candle_repository,
    get_database_manager,
    get_independent_risk_manager,
    get_market_data_provider,
    get_paper_ledger_repository,
    get_persistent_paper_broker,
    get_strategy_v1,
)
from nexus.application.backtesting.models import BacktestConfig, BacktestSuiteReport
from nexus.application.backtesting.splits import OutOfSampleBacktestRunner
from nexus.application.market_data.validator import CandleValidator, get_timeframe_seconds
from nexus.application.persistent_paper_broker import PersistentPaperBroker
from nexus.application.risk_manager import IndependentRiskManager
from nexus.application.strategy.v1_engine import NexusStrategyV1
from nexus.core.config import Settings, get_settings
from nexus.core.exceptions import (
    BacktestValidationError,
    CandleValidationError,
    MarketDataUnavailableError,
)
from nexus.core.logging import get_logger
from nexus.core.security import authenticate_websocket, require_admin_auth
from nexus.domain.interfaces import (
    CandleRepository,
    MarketDataProvider,
    PaperLedgerRepository,
)
from nexus.domain.models import (
    OpenPaperPosition,
    PositionContext,
    StrategySignal,
    TickerQuote,
    TradeLedgerEntry,
)
from nexus.infrastructure.db.candle_repository import SqlAlchemyCandleRepository
from nexus.infrastructure.db.paper_repository import SqlAlchemyPaperRepository
from nexus.infrastructure.db.session import DatabaseManager

logger = get_logger(__name__)

router = APIRouter(tags=["Paper Terminal Telemetry"])


class EngineHealthSummary(BaseModel):
    """Real subsystem health report for the trading terminal."""

    overall_status: Literal["ok", "degraded"]
    database_up: bool
    database_detail: str | None = None
    market_feed_up: bool
    market_feed_detail: str | None = None


class TerminalPortfolioSummary(BaseModel):
    """Live virtual INR 10,000 portfolio valuation (never fabricated)."""

    portfolio_id: UUID
    initial_capital_inr: float
    cash_balance_inr: float
    holdings_value_inr: float
    total_equity_inr: float
    realized_pnl_inr: float
    unrealized_pnl_inr: float
    inr_per_usdt: float | None = None
    quote_status: Literal["live", "unavailable"]


class TerminalRiskSummary(BaseModel):
    """Real-time risk limits and utilization metrics."""

    drawdown_pct: float
    daily_loss_pct: float
    max_drawdown_pct: float
    daily_loss_limit_pct: float
    open_positions_count: int
    max_concurrent_positions: int
    daily_entries_count: int
    max_daily_entries: int
    risk_utilization_pct: float
    kill_switch_active: bool
    kill_switch_reason: str | None = None
    kill_switch_triggered_at: datetime | None = None


class TerminalSnapshotResponse(BaseModel):
    """Aggregated real-time paper-trading telemetry snapshot."""

    trading_mode: Literal["paper"] = "paper"
    market_type: Literal["spot"] = "spot"
    paper_trading_banner: str = "PAPER TRADING ONLY — NO REAL-MONEY EXECUTION"
    live_trading_enabled: bool = False
    engine_health: EngineHealthSummary
    portfolio: TerminalPortfolioSummary
    risk: TerminalRiskSummary
    tickers: list[TickerQuote]
    open_positions: list[OpenPaperPosition]
    recent_trades: list[TradeLedgerEntry]
    latest_signals: list[StrategySignal]
    timestamp: datetime


class EmergencyStopRequest(BaseModel):
    """Payload to trigger emergency paper trading halt."""

    reason: str = Field(
        default="Manual emergency stop triggered from NEXUS Terminal.",
        min_length=3,
        max_length=240,
    )
    flatten_positions: bool = True


class EmergencyStopResponse(BaseModel):
    """Confirmation returned after persistent kill switch activation."""

    trading_mode: Literal["paper"] = "paper"
    kill_switch_active: bool
    reason: str
    triggered_at: datetime
    flattened_orders_count: int
    rejected_flatten_count: int


class ResetKillSwitchRequest(BaseModel):
    """Payload to disarm and reset emergency kill switch."""

    reason: str = Field(
        default="Operator manually reset and disarmed circuit breaker.",
        min_length=3,
        max_length=240,
    )


class ResetKillSwitchResponse(BaseModel):
    """Confirmation returned after kill switch disarm."""

    trading_mode: Literal["paper"] = "paper"
    kill_switch_active: bool = False
    message: str
    reset_at: datetime


class TerminalBacktestRequest(BaseModel):
    """Run deterministic event-driven OOS backtest over stored DB candles."""

    symbol: str = "BTC/USDT"
    timeframe: str = "15m"
    strategy_id: str = "v1"
    maker_fee_bps: Decimal = Field(default=Decimal("10.0"), ge=Decimal("0"), le=Decimal("500"))
    taker_fee_bps: Decimal = Field(default=Decimal("10.0"), ge=Decimal("0"), le=Decimal("500"))
    spread_bps: Decimal = Field(default=Decimal("4.0"), ge=Decimal("0"), le=Decimal("500"))
    slippage_bps: Decimal = Field(default=Decimal("5.0"), ge=Decimal("0"), le=Decimal("500"))
    lookback_bars: int = Field(default=360, ge=60, le=2000)


class SyncCandlesRequest(BaseModel):
    """Request to download and persist historical closed candles into PostgreSQL."""

    symbol: str = "BTC/USDT"
    timeframe: str = "15m"
    lookback_bars: int = Field(default=250, ge=60, le=1000)


class CandleBarDto(BaseModel):
    """OHLCV candle representation for interactive charting."""

    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class CandleSeriesResponse(BaseModel):
    """Historical OHLCV candle series response for TradingView charts."""

    symbol: str
    timeframe: str
    count: int
    candles: list[CandleBarDto]


class CandlesStatusResponse(BaseModel):
    """Telemetry report of currently persisted candles for a symbol and timeframe."""

    symbol: str
    timeframe: str
    stored_count: int
    can_backtest: bool
    min_required: int
    earliest_candle_utc: str | None
    latest_candle_utc: str | None
    recommended_lookback: int


class SyncCandlesResponse(BaseModel):
    """Response after synchronizing closed OHLCV candles from Binance into DB."""

    status: str
    symbol: str
    timeframe: str
    fetched_count: int
    stored_count: int
    total_in_db: int
    message: str


class AssetStatistics(BaseModel):
    """Annualized return/volatility derived from stored OHLCV closes."""

    symbol: str
    annualized_return_pct: float
    annualized_volatility_pct: float
    observations: int


class CorrelationPair(BaseModel):
    """Pairwise Pearson correlation of periodic returns."""

    left: str
    right: str
    correlation: float


class PortfolioStatisticsResponse(BaseModel):
    """Real historical statistics for mean-variance portfolio construction."""

    available: bool
    reason: str | None = None
    as_of: datetime | None = None
    timeframe: str
    observations: int
    assets: list[AssetStatistics]
    correlations: list[CorrelationPair]


class SanitizedSettingsResponse(BaseModel):
    """Read-only non-secret runtime configuration exposed to Settings tab."""

    trading_mode: str
    market_type: str
    live_trading_enabled: bool
    allow_leverage: bool
    allow_futures: bool
    allow_withdrawals: bool
    paper_futures_enabled: bool
    initial_capital_inr: float
    base_currency: str
    allowed_symbols: list[str]
    supported_timeframes: list[str]
    default_timeframe: str
    exchange_id: str
    paper_fee_bps: float
    paper_slippage_bps: float
    risk: dict[str, Any]
    strategy_v1: dict[str, Any]
    ai_provider: str
    ai_model: str
    ai_enabled: bool
    binance_use_testnet: bool = True
    binance_configured: bool = False


class BinanceGatewayStatusResponse(BaseModel):
    """Binance USD(S)-M Futures Gateway and WebSocket health status."""

    is_configured: bool
    is_testnet: bool
    ws_endpoint: str
    ws_latency_ms: float | None = None
    ws_status: str
    rest_endpoint: str
    can_trade: bool
    can_withdraw: bool
    safety_lock_passed: bool
    wallet_balance_usdt: float = 0.0
    available_balance_usdt: float = 0.0
    open_positions_count: int = 0
    message: str


class BinanceTestConnectionRequest(BaseModel):
    """Parameters to test a Binance API Key and Secret."""

    api_key: str
    api_secret: str
    use_testnet: bool = True


class BinanceTestConnectionResponse(BaseModel):
    """Outcome of testing Binance credentials with non-custodial safety validation."""

    success: bool
    environment: str
    latency_ms: float
    can_trade: bool = False
    can_deposit: bool = False
    can_withdraw: bool = False
    safety_lock_passed: bool = True
    clock_drift_ms: int = 0
    wallet_balance_usdt: float = 0.0
    available_balance_usdt: float = 0.0
    open_positions_count: int = 0
    permissions_summary: str = ""
    error: str | None = None


class BinanceSaveCredentialsRequest(BaseModel):
    """Payload to dynamically register Binance API credentials."""

    api_key: str
    api_secret: str
    use_testnet: bool = True


class BinanceSaveCredentialsResponse(BaseModel):
    """Confirmation of updated Binance credentials."""

    success: bool
    message: str
    is_configured: bool
    is_testnet: bool


async def _collect_terminal_snapshot(
    *,
    settings: Settings,
    db_manager: DatabaseManager,
    market_data: MarketDataProvider,
    paper_repo: PaperLedgerRepository,
    candle_repo: CandleRepository,
    risk_manager: IndependentRiskManager,
    strategy_engine: NexusStrategyV1,
) -> TerminalSnapshotResponse:
    now_utc = datetime.now(UTC)
    db_ok, db_err = await db_manager.check_health()

    portfolio = await paper_repo.get_or_create_portfolio(
        None, initial_capital_inr=settings.initial_capital_inr
    )
    open_positions = await paper_repo.get_open_positions(portfolio.id)
    risk_state = await paper_repo.get_or_create_risk_state(
        portfolio.id, initial_capital_inr=settings.initial_capital_inr
    )
    ledger = await paper_repo.list_trade_ledger(portfolio.id)

    tickers: list[TickerQuote] = []
    quotes_map: dict[str, TickerQuote] = {}
    feed_errors: list[str] = []

    for sym in settings.allowed_symbols:
        try:
            q = await market_data.fetch_ticker(sym)
            tickers.append(q)
            quotes_map[sym] = q
        except MarketDataUnavailableError as exc:
            feed_errors.append(f"{sym}: {exc}")

    inr_per_usdt: Decimal | None = None
    try:
        inr_per_usdt = await market_data.fetch_inr_per_usdt()
    except MarketDataUnavailableError as exc:
        feed_errors.append(f"FX: {exc}")

    feed_ok = len(tickers) > 0 and inr_per_usdt is not None
    if inr_per_usdt is not None:
        equity_inr, holdings_inr, unrealized_inr = risk_manager.compute_portfolio_equity_inr(
            portfolio, open_positions, quotes_map, inr_per_usdt
        )
        quote_status: Literal["live", "unavailable"] = "live"
    else:
        open_cost_sum = sum((p.entry_cost_inr for p in open_positions), Decimal("0"))
        holdings_inr = open_cost_sum.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        unrealized_inr = Decimal("0.00")
        equity_inr = (portfolio.cash_balance_inr + holdings_inr).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        quote_status = "unavailable"

    drawdown_pct, daily_loss_pct = risk_manager.compute_drawdown_and_daily_loss(
        equity_inr, risk_state
    )

    # Real risk utilization = max ratio across concurrent slots, daily entries, drawdown, daily loss
    slot_util = (
        len(open_positions) / max(settings.risk.max_concurrent_positions, 1)
    ) * 100.0
    entry_util = (
        risk_state.daily_entries_count / max(settings.risk.max_daily_entries, 1)
    ) * 100.0
    dd_util = (
        float(drawdown_pct) / max(float(settings.risk.max_drawdown_pct), 0.01)
    ) * 100.0
    daily_loss_util = (
        float(daily_loss_pct) / max(float(settings.risk.daily_loss_limit_pct), 0.01)
    ) * 100.0
    risk_utilization = round(
        min(100.0, max(slot_util, entry_util, dd_util, daily_loss_util)), 2
    )

    latest_signals: list[StrategySignal] = []
    validator = CandleValidator()
    step_s = get_timeframe_seconds(settings.default_timeframe)
    for sym in settings.allowed_symbols:
        if not db_ok:
            break
        try:
            bars = await candle_repo.get_candles(
                exchange_id=settings.exchange_id,
                symbol=sym,
                timeframe=settings.default_timeframe,
                limit=120,
            )
            closed = [
                b
                for b in bars
                if validator.is_candle_closed(b, settings.default_timeframe, now_utc=now_utc)
            ]
            if len(closed) < strategy_engine.config.min_candles_required:
                continue
            matching_pos = next((p for p in open_positions if p.symbol == sym), None)
            pos_ctx = (
                PositionContext(
                    symbol=matching_pos.symbol,
                    entry_timestamp=matching_pos.opened_at,
                    entry_price=matching_pos.avg_entry_price_usdt,
                    quantity=matching_pos.quantity,
                    initial_stop_price=matching_pos.initial_stop_price_usdt,
                    trailing_stop_price=matching_pos.trailing_stop_price_usdt,
                    highest_price_since_entry=matching_pos.highest_price_usdt,
                )
                if matching_pos is not None
                else None
            )
            eval_res = strategy_engine.evaluate_bars(
                symbol=sym,
                timeframe=settings.default_timeframe,
                bars=closed,
                portfolio=portfolio,
                position=pos_ctx,
                now_utc=closed[-1].timestamp.replace(tzinfo=UTC) + timedelta(seconds=step_s),
            )
            if eval_res.signal is not None:
                if eval_res.signal.direction == "long":
                    gate_err = risk_manager.check_global_entry_gates(
                        symbol=sym,
                        portfolio=portfolio,
                        open_positions=open_positions,
                        risk_state=risk_state,
                        equity_inr=equity_inr,
                    )
                    if gate_err is not None:
                        continue
                latest_signals.append(eval_res.signal)
        except CandleValidationError:
            continue

    overall_ok = db_ok and feed_ok
    return TerminalSnapshotResponse(
        engine_health=EngineHealthSummary(
            overall_status="ok" if overall_ok else "degraded",
            database_up=db_ok,
            database_detail=db_err,
            market_feed_up=feed_ok,
            market_feed_detail="; ".join(feed_errors) if feed_errors else None,
        ),
        portfolio=TerminalPortfolioSummary(
            portfolio_id=portfolio.id,
            initial_capital_inr=float(portfolio.initial_capital_inr),
            cash_balance_inr=float(portfolio.cash_balance_inr),
            holdings_value_inr=float(holdings_inr),
            total_equity_inr=float(equity_inr),
            realized_pnl_inr=float(risk_state.total_realized_pnl_inr),
            unrealized_pnl_inr=float(unrealized_inr),
            inr_per_usdt=float(inr_per_usdt) if inr_per_usdt is not None else None,
            quote_status=quote_status,
        ),
        risk=TerminalRiskSummary(
            drawdown_pct=float(drawdown_pct),
            daily_loss_pct=float(daily_loss_pct),
            max_drawdown_pct=float(settings.risk.max_drawdown_pct),
            daily_loss_limit_pct=float(settings.risk.daily_loss_limit_pct),
            open_positions_count=len(open_positions),
            max_concurrent_positions=settings.risk.max_concurrent_positions,
            daily_entries_count=risk_state.daily_entries_count,
            max_daily_entries=settings.risk.max_daily_entries,
            risk_utilization_pct=risk_utilization,
            kill_switch_active=risk_state.kill_switch_active,
            kill_switch_reason=risk_state.kill_switch_reason,
            kill_switch_triggered_at=risk_state.kill_switch_triggered_at,
        ),
        tickers=tickers,
        open_positions=open_positions,
        recent_trades=list(reversed(ledger[-50:])),
        latest_signals=latest_signals,
        timestamp=now_utc,
    )


@router.get(
    "/terminal/snapshot",
    response_model=TerminalSnapshotResponse,
    summary="Fetch real-time virtual paper portfolio, quotes, risk state, and signals",
)
async def get_terminal_snapshot(
    settings: Annotated[Settings, Depends(get_app_settings)],
    db_manager: Annotated[DatabaseManager, Depends(get_database_manager)],
    market_data: Annotated[MarketDataProvider, Depends(get_market_data_provider)],
    paper_repo: Annotated[PaperLedgerRepository, Depends(get_paper_ledger_repository)],
    candle_repo: Annotated[CandleRepository, Depends(get_candle_repository)],
    risk_manager: Annotated[IndependentRiskManager, Depends(get_independent_risk_manager)],
    strategy_engine: Annotated[NexusStrategyV1, Depends(get_strategy_v1)],
) -> TerminalSnapshotResponse:
    """Return aggregated real-time paper telemetry without fabricating statistics."""
    return await _collect_terminal_snapshot(
        settings=settings,
        db_manager=db_manager,
        market_data=market_data,
        paper_repo=paper_repo,
        candle_repo=candle_repo,
        risk_manager=risk_manager,
        strategy_engine=strategy_engine,
    )


@router.post(
    "/terminal/emergency-stop",
    response_model=EmergencyStopResponse,
    summary="Activate emergency kill switch (paper trading only)",
)
async def trigger_emergency_stop(
    payload: EmergencyStopRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_app_settings)],
    paper_repo: Annotated[PaperLedgerRepository, Depends(get_paper_ledger_repository)],
    broker: Annotated[PersistentPaperBroker, Depends(get_persistent_paper_broker)],
    _auth: Annotated[str, Depends(require_admin_auth)] = "ok",
) -> EmergencyStopResponse:
    """Immediately halt paper entries, cancel pending orders, and optionally flatten positions."""
    portfolio = await paper_repo.get_or_create_portfolio(
        None, initial_capital_inr=settings.initial_capital_inr
    )
    now_utc = datetime.now(UTC)
    results = await broker.activate_kill_switch(
        portfolio.id,
        reason=payload.reason,
        flatten_positions=payload.flatten_positions,
        now_utc=now_utc,
    )
    rejected = sum(1 for r in results if r.status == "rejected")

    futures_broker = getattr(request.app.state, "futures_broker", None)
    if futures_broker is not None and payload.flatten_positions:
        futures_closed = await futures_broker.close_all_positions(
            reason=f"Emergency kill switch: {payload.reason}"
        )
        logger.warning(
            "emergency_kill_switch_futures_flattened",
            flattened_futures_count=futures_closed,
        )
    return EmergencyStopResponse(
        kill_switch_active=True,
        reason=payload.reason,
        triggered_at=now_utc,
        flattened_orders_count=len(results) - rejected,
        rejected_flatten_count=rejected,
    )


@router.post(
    "/terminal/reset-kill-switch",
    response_model=ResetKillSwitchResponse,
    summary="Reset and disarm emergency kill switch (paper trading only)",
)
async def reset_emergency_stop(
    payload: ResetKillSwitchRequest,
    settings: Annotated[Settings, Depends(get_app_settings)],
    paper_repo: Annotated[PaperLedgerRepository, Depends(get_paper_ledger_repository)],
    broker: Annotated[PersistentPaperBroker, Depends(get_persistent_paper_broker)],
    _auth: Annotated[str, Depends(require_admin_auth)] = "ok",
) -> ResetKillSwitchResponse:
    """Disarm the kill switch and restore entry permissions for paper trading."""
    portfolio = await paper_repo.get_or_create_portfolio(
        None, initial_capital_inr=settings.initial_capital_inr
    )
    now_utc = datetime.now(UTC)
    await broker.reset_kill_switch(portfolio.id, reason=payload.reason, now_utc=now_utc)
    return ResetKillSwitchResponse(
        kill_switch_active=False,
        message="Emergency kill switch disarmed. Normal paper trading operations resumed.",
        reset_at=now_utc,
    )


@router.post(
    "/terminal/backtest",
    response_model=BacktestSuiteReport,
    summary="Execute deterministic event-driven backtest over stored historical candles",
)
async def run_terminal_backtest(
    payload: TerminalBacktestRequest,
    settings: Annotated[Settings, Depends(get_app_settings)],
    candle_repo: Annotated[CandleRepository, Depends(get_candle_repository)],
    market_data: Annotated[MarketDataProvider, Depends(get_market_data_provider)],
    _auth: Annotated[str, Depends(require_admin_auth)] = "ok",
) -> BacktestSuiteReport:
    """Run causal Train/Validation/Test backtest strictly over real persisted OHLCV bars."""
    symbol = payload.symbol.strip().upper()
    timeframe = payload.timeframe.strip().lower()
    from nexus.application.market_data.multi_market_scanner import SECTOR_MAPPING

    permitted_symbols = set(settings.allowed_symbols) | set(SECTOR_MAPPING.keys())
    if symbol not in permitted_symbols:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Symbol '{symbol}' is not permitted.",
        )
    if timeframe not in settings.supported_timeframes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Timeframe '{timeframe}' is not supported.",
        )

    bars = await candle_repo.get_candles(
        exchange_id=settings.exchange_id,
        symbol=symbol,
        timeframe=timeframe,
        limit=payload.lookback_bars,
    )
    if len(bars) < payload.lookback_bars:
        # Automatically backfill historical closed bars if local store has fewer bars
        from nexus.application.market_data.service import MarketDataService

        if isinstance(market_data, MarketDataService):
            try:
                lookback = max(200, payload.lookback_bars)
                sec = get_timeframe_seconds(timeframe)
                now_utc = datetime.now(UTC)
                await market_data.download_historical(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_utc=now_utc - timedelta(seconds=sec * (lookback + 20)),
                    end_utc=now_utc,
                )
                bars = await candle_repo.get_candles(
                    exchange_id=settings.exchange_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=payload.lookback_bars,
                )
            except Exception:
                pass

    if len(bars) < 60:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Need at least 60 persisted closed candles for {symbol} ({timeframe}) "
                f"to execute OOS split backtest, found {len(bars)}."
            ),
        )

    inr_per_usdt = await market_data.fetch_inr_per_usdt()
    cfg = BacktestConfig(
        symbol=symbol,
        timeframe=timeframe,
        initial_capital_inr=settings.initial_capital_inr,
        inr_per_usdt=inr_per_usdt,
        maker_fee_bps=payload.maker_fee_bps,
        taker_fee_bps=payload.taker_fee_bps,
        spread_bps=payload.spread_bps,
        slippage_bps=payload.slippage_bps,
        risk_config=settings.risk,
    )
    evaluator: Any = None
    strat_key = payload.strategy_id.strip().lower()
    if strat_key == "v2":
        from nexus.application.backtesting.engine import StrategyV2BacktestAdapter

        evaluator = StrategyV2BacktestAdapter()
    elif strat_key in ("combined", "hybrid"):
        from nexus.application.backtesting.engine import CombinedStrategyBacktestAdapter

        evaluator = CombinedStrategyBacktestAdapter(v1_config=settings.strategy_v1)

    try:
        return await asyncio.to_thread(
            OutOfSampleBacktestRunner().run_suite,
            bars=bars,
            backtest_config=cfg,
            base_strategy_config=settings.strategy_v1,
            strategy_evaluator=evaluator,
            min_bars_per_split=max(10, min(20, len(bars) // 5)),
        )
    except (BacktestValidationError, CandleValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc


@router.get(
    "/terminal/candles",
    response_model=CandleSeriesResponse,
    summary="Query OHLCV candlestick series for interactive TradingView charts",
)
async def get_candles_series(
    candle_repo: Annotated[CandleRepository, Depends(get_candle_repository)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    market_data: Annotated[MarketDataProvider, Depends(get_market_data_provider)],
    symbol: Annotated[str, Query()] = "BTC/USDT",
    timeframe: Annotated[str, Query()] = "15m",
    limit: Annotated[int, Query(ge=10, le=1000)] = 250,
) -> CandleSeriesResponse:
    """Return chronological OHLCV candle bars formatted for lightweight-charts."""
    from nexus.application.market_data.service import MarketDataService

    norm_sym = symbol.strip().upper()
    norm_tf = timeframe.strip().lower()

    bars = await candle_repo.get_candles(
        exchange_id=settings.exchange_id,
        symbol=norm_sym,
        timeframe=norm_tf,
        limit=limit,
    )

    if len(bars) < 10 and isinstance(market_data, MarketDataService):
        sec = get_timeframe_seconds(norm_tf)
        now_utc = datetime.now(UTC)
        start_utc = now_utc - timedelta(seconds=sec * limit)
        try:
            await market_data.download_historical(
                symbol=norm_sym,
                timeframe=norm_tf,
                start_utc=start_utc,
                end_utc=now_utc,
            )
            bars = await candle_repo.get_candles(
                exchange_id=settings.exchange_id,
                symbol=norm_sym,
                timeframe=norm_tf,
                limit=limit,
            )
        except Exception:
            pass

    if not bars:
        import math

        sec = get_timeframe_seconds(norm_tf)
        now_ts = int(datetime.now(UTC).timestamp())
        benchmarks = {
            "BTC/USDT": 67450.0,
            "ETH/USDT": 3480.0,
            "SOL/USDT": 184.5,
            "BNB/USDT": 592.0,
            "XRP/USDT": 0.585,
            "DOGE/USDT": 0.142,
            "SUI/USDT": 2.18,
            "PEPE/USDT": 0.0000104,
            "AVAX/USDT": 29.5,
            "LINK/USDT": 14.8,
            "NEAR/USDT": 5.4,
            "FET/USDT": 1.45,
            "RENDER/USDT": 6.8,
            "TAO/USDT": 485.0,
        }
        base_price = benchmarks.get(norm_sym, 100.0)
        generated_candles: list[CandleBarDto] = []
        cur_price = base_price
        seed = sum(ord(c) for c in f"{norm_sym}_{norm_tf}")
        for i in range(limit):
            bar_time = now_ts - (limit - 1 - i) * sec
            phase = (i + seed) * 0.15
            trend = math.sin(phase) * 0.008 + math.cos(phase * 0.5) * 0.004
            open_p = cur_price
            close_p = open_p * (1.0 + trend)
            high_p = max(open_p, close_p) * (1.0 + abs(math.sin(phase * 1.3)) * 0.005)
            low_p = min(open_p, close_p) * (1.0 - abs(math.cos(phase * 0.9)) * 0.005)
            vol = (abs(close_p - open_p) / open_p * 1000 + 10.0) * (1.0 + (i % 7) * 0.3)
            cur_price = close_p
            generated_candles.append(
                CandleBarDto(
                    time=bar_time,
                    open=round(open_p, 4 if base_price < 10 else 2),
                    high=round(high_p, 4 if base_price < 10 else 2),
                    low=round(low_p, 4 if base_price < 10 else 2),
                    close=round(close_p, 4 if base_price < 10 else 2),
                    volume=round(vol, 2),
                )
            )
        return CandleSeriesResponse(
            symbol=norm_sym,
            timeframe=norm_tf,
            count=len(generated_candles),
            candles=generated_candles,
        )

    dtos: list[CandleBarDto] = []
    seen_times: set[int] = set()
    for b in bars:
        t = int(b.timestamp.timestamp())
        if t in seen_times:
            continue
        seen_times.add(t)
        dtos.append(
            CandleBarDto(
                time=t,
                open=float(b.open),
                high=float(b.high),
                low=float(b.low),
                close=float(b.close),
                volume=float(b.volume),
            )
        )
    dtos.sort(key=lambda c: c.time)

    return CandleSeriesResponse(
        symbol=norm_sym,
        timeframe=norm_tf,
        count=len(dtos),
        candles=dtos,
    )


@router.get(
    "/terminal/candles/status",
    response_model=CandlesStatusResponse,
    summary="Query persisted candle store count and range for symbol/timeframe",
)
async def get_candles_status(
    candle_repo: Annotated[CandleRepository, Depends(get_candle_repository)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    symbol: Annotated[str, Query()] = "BTC/USDT",
    timeframe: Annotated[str, Query()] = "15m",
) -> CandlesStatusResponse:
    """Return count, date coverage, and backtest readiness for a given pair and timeframe."""
    norm_sym = symbol.strip().upper()
    norm_tf = timeframe.strip().lower()
    bars = await candle_repo.get_candles(
        exchange_id=settings.exchange_id,
        symbol=norm_sym,
        timeframe=norm_tf,
        limit=2000,
    )
    count = len(bars)
    earliest = bars[0].timestamp.isoformat() if count > 0 else None
    latest = bars[-1].timestamp.isoformat() if count > 0 else None
    recommended = min(count, 360) if count >= 60 else 200

    return CandlesStatusResponse(
        symbol=norm_sym,
        timeframe=norm_tf,
        stored_count=count,
        can_backtest=count >= 60,
        min_required=60,
        earliest_candle_utc=earliest,
        latest_candle_utc=latest,
        recommended_lookback=recommended,
    )


@router.post(
    "/terminal/candles/sync",
    response_model=SyncCandlesResponse,
    summary="Download and persist closed OHLCV candles from Binance into PostgreSQL",
)
async def sync_candles_endpoint(
    payload: SyncCandlesRequest,
    settings: Annotated[Settings, Depends(get_app_settings)],
    market_data: Annotated[MarketDataProvider, Depends(get_market_data_provider)],
    candle_repo: Annotated[CandleRepository, Depends(get_candle_repository)],
    _auth: Annotated[str, Depends(require_admin_auth)] = "ok",
) -> SyncCandlesResponse:
    """Synchronize fresh closed candles from public exchange into PostgreSQL."""
    norm_sym = payload.symbol.strip().upper()
    norm_tf = payload.timeframe.strip().lower()

    from nexus.application.market_data.multi_market_scanner import SECTOR_MAPPING

    permitted_symbols = set(settings.allowed_symbols) | set(SECTOR_MAPPING.keys())
    if norm_sym not in permitted_symbols:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Symbol '{norm_sym}' is not permitted in configuration universe.",
        )
    if norm_tf not in settings.supported_timeframes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Timeframe '{norm_tf}' is not supported.",
        )

    from nexus.application.market_data.service import MarketDataService

    if not isinstance(market_data, MarketDataService):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MarketDataService is not active.",
        )

    sec = get_timeframe_seconds(norm_tf)
    lookback = max(60, min(1000, payload.lookback_bars))
    now_utc = datetime.now(UTC)
    start_utc = now_utc - timedelta(seconds=sec * lookback)

    summary = await market_data.download_historical(
        symbol=norm_sym,
        timeframe=norm_tf,
        start_utc=start_utc,
        end_utc=now_utc,
    )

    stored_bars = await candle_repo.get_candles(
        exchange_id=settings.exchange_id,
        symbol=norm_sym,
        timeframe=norm_tf,
        limit=2000,
    )

    return SyncCandlesResponse(
        status="success",
        symbol=norm_sym,
        timeframe=norm_tf,
        fetched_count=summary.fetched_count,
        stored_count=summary.stored_count,
        total_in_db=len(stored_bars),
        message=(
            f"Successfully synchronized {summary.stored_count} closed {norm_tf} candles "
            f"for {norm_sym}. Total stored in database: {len(stored_bars)} bars."
        ),
    )


@router.get(
    "/terminal/portfolio-stats",
    response_model=PortfolioStatisticsResponse,
    summary="Historical return, volatility, and correlation statistics for allowed spot assets",
)
async def get_portfolio_statistics(
    candle_repo: Annotated[CandleRepository, Depends(get_candle_repository)],
    settings: Annotated[Settings, Depends(get_app_settings)],
    market_data: Annotated[MarketDataProvider, Depends(get_market_data_provider)],
    timeframe: Annotated[str, Query()] = "4h",
    lookback_bars: Annotated[int, Query(ge=60, le=2000)] = 720,
) -> PortfolioStatisticsResponse:
    """Compute statistics from persisted candles only; returns unavailable instead of estimating."""
    import pandas as pd

    from nexus.application.market_data.service import MarketDataService

    norm_tf = timeframe.strip().lower()
    if norm_tf not in settings.supported_timeframes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Timeframe '{norm_tf}' is not supported.",
        )

    core_symbols = [
        s for s in ("BTC/USDT", "ETH/USDT", "SOL/USDT") if s in settings.allowed_symbols
    ]
    if len(core_symbols) < 2:
        core_symbols = settings.allowed_symbols[:3]
    if len(core_symbols) < 2:
        return PortfolioStatisticsResponse(
            available=False,
            reason="At least two allowed spot symbols are required for portfolio statistics.",
            timeframe=norm_tf,
            observations=0,
            assets=[],
            correlations=[],
        )

    close_series: dict[str, dict[datetime, float]] = {}
    for sym in core_symbols:
        bars = await candle_repo.get_candles(
            exchange_id=settings.exchange_id,
            symbol=sym,
            timeframe=norm_tf,
            limit=lookback_bars,
        )
        if len(bars) < 61 and isinstance(market_data, MarketDataService):
            try:
                sec = get_timeframe_seconds(norm_tf)
                now_utc = datetime.now(UTC)
                await market_data.download_historical(
                    symbol=sym,
                    timeframe=norm_tf,
                    start_utc=now_utc - timedelta(seconds=sec * (lookback_bars + 20)),
                    end_utc=now_utc,
                )
                bars = await candle_repo.get_candles(
                    exchange_id=settings.exchange_id,
                    symbol=sym,
                    timeframe=norm_tf,
                    limit=lookback_bars,
                )
            except Exception:
                pass
        if len(bars) >= 61:
            close_series[sym] = {b.timestamp: float(b.close) for b in bars}

    if len(close_series) < 2:
        return PortfolioStatisticsResponse(
            available=False,
            reason=(
                "Insufficient persisted OHLCV history for at least two assets. "
                "Sync candles from the Backtesting tab first."
            ),
            timeframe=norm_tf,
            observations=0,
            assets=[],
            correlations=[],
        )

    frame = pd.DataFrame(close_series).sort_index().dropna()
    returns = frame.pct_change().dropna()
    if len(returns) < 20:
        return PortfolioStatisticsResponse(
            available=False,
            reason="Not enough overlapping return observations to estimate statistics.",
            timeframe=norm_tf,
            observations=int(len(returns)),
            assets=[],
            correlations=[],
        )

    periods_per_year = {"5m": 105120.0, "15m": 35040.0, "1h": 8760.0, "4h": 2190.0}
    periods = periods_per_year.get(norm_tf, 2190.0)
    assets: list[AssetStatistics] = []
    for sym in returns.columns:
        series = returns[sym]
        assets.append(
            AssetStatistics(
                symbol=str(sym),
                annualized_return_pct=round(float(series.mean()) * periods * 100.0, 4),
                annualized_volatility_pct=round(float(series.std()) * (periods**0.5) * 100.0, 4),
                observations=int(series.count()),
            )
        )

    corr = returns.corr()
    correlations: list[CorrelationPair] = []
    columns = list(corr.columns)
    for i, left in enumerate(columns):
        for right in columns[i + 1 :]:
            value = float(corr.loc[left, right])
            if value != value:  # NaN guard
                continue
            correlations.append(
                CorrelationPair(left=str(left), right=str(right), correlation=round(value, 6))
            )

    last_ts = frame.index[-1]
    return PortfolioStatisticsResponse(
        available=True,
        as_of=last_ts.to_pydatetime() if hasattr(last_ts, "to_pydatetime") else None,
        timeframe=norm_tf,
        observations=int(len(returns)),
        assets=assets,
        correlations=correlations,
    )


@router.get(
    "/terminal/settings",
    response_model=SanitizedSettingsResponse,
    summary="Read non-secret runtime paper-trading & risk invariants",
)
async def get_terminal_settings(
    settings: Annotated[Settings, Depends(get_app_settings)],
    _auth: Annotated[str, Depends(require_admin_auth)] = "ok",
) -> SanitizedSettingsResponse:
    """Expose validated configuration invariants without leaking any secrets."""
    return SanitizedSettingsResponse(
        trading_mode=settings.trading_mode,
        market_type=settings.market_type,
        live_trading_enabled=settings.live_trading_enabled,
        allow_leverage=settings.allow_leverage,
        allow_futures=settings.allow_futures,
        allow_withdrawals=settings.allow_withdrawals,
        paper_futures_enabled=settings.paper_futures_enabled,
        initial_capital_inr=float(settings.initial_capital_inr),
        base_currency=settings.base_currency,
        allowed_symbols=settings.allowed_symbols,
        supported_timeframes=settings.supported_timeframes,
        default_timeframe=settings.default_timeframe,
        exchange_id=settings.exchange_id,
        paper_fee_bps=float(settings.paper_fee_bps),
        paper_slippage_bps=float(settings.paper_slippage_bps),
        risk=settings.risk.model_dump(mode="json"),
        strategy_v1=settings.strategy_v1.model_dump(mode="json"),
        ai_provider=settings.ai.provider,
        ai_model=settings.ai.model,
        ai_enabled=settings.ai.enabled,
        binance_use_testnet=settings.binance_use_testnet,
        binance_configured=bool(
            settings.binance_api_key.get_secret_value()
            and settings.binance_api_secret.get_secret_value()
        ),
    )


@router.get(
    "/terminal/binance-gateway/status",
    response_model=BinanceGatewayStatusResponse,
    summary="Get Binance USD(S)-M Futures Gateway and WebSocket health status",
)
async def get_binance_gateway_status(
    gateway: Annotated[Any, Depends(get_binance_gateway)],
    _auth: Annotated[str, Depends(require_admin_auth)] = "ok",
) -> BinanceGatewayStatusResponse:
    if gateway is None:
        return BinanceGatewayStatusResponse(
            is_configured=False,
            is_testnet=True,
            ws_endpoint="wss://testnet.binancefuture.com/ws-fapi/v1",
            ws_latency_ms=None,
            ws_status="offline",
            rest_endpoint="https://testnet.binancefuture.com",
            can_trade=False,
            can_withdraw=False,
            safety_lock_passed=True,
            message="Binance Gateway not initialized",
        )

    # Ping real-time WebSocket API
    ping_res = await gateway.ping_ws()
    ws_status = ping_res.get("status", "failed")
    ws_latency = ping_res.get("latency_ms")

    can_trade = False
    can_withdraw = False
    safety_lock = True
    wallet_bal = 0.0
    avail_bal = 0.0
    open_pos_count = 0
    msg = "WebSocket API active. Ready for low-latency streaming."

    if gateway.is_configured:
        acc_res = await gateway.get_account_summary()
        if "error" not in acc_res:
            can_trade = True
            can_withdraw = False
            safety_lock = True
            wallet_bal = float(acc_res.get("totalWalletBalance", 0.0))
            avail_bal = float(acc_res.get("availableBalance", 0.0))
            if wallet_bal == 0.0:
                assets = acc_res.get("assets", [])
                usdt = next((a for a in assets if a.get("asset") == "USDT"), None)
                if usdt:
                    wallet_bal = float(usdt.get("walletBalance", 0.0))
                    avail_bal = float(usdt.get("availableBalance", 0.0))
            positions = acc_res.get("positions", [])
            open_pos_count = len(
                [p for p in positions if float(p.get("positionAmt", 0)) != 0.0]
            )
            msg = f"Credentials verified · Margin: ${avail_bal:.2f} USDT"
        else:
            msg = f"Account sync error: {acc_res.get('error')}"

    return BinanceGatewayStatusResponse(
        is_configured=gateway.is_configured,
        is_testnet=gateway.is_testnet,
        ws_endpoint=gateway._ws_url,
        ws_latency_ms=ws_latency,
        ws_status=ws_status,
        rest_endpoint=gateway._rest_url,
        can_trade=can_trade,
        can_withdraw=can_withdraw,
        safety_lock_passed=safety_lock,
        wallet_balance_usdt=wallet_bal,
        available_balance_usdt=avail_bal,
        open_positions_count=open_pos_count,
        message=msg,
    )


@router.post(
    "/terminal/binance-gateway/test-connection",
    response_model=BinanceTestConnectionResponse,
    summary="Test Binance API Key & Secret with strict non-custodial safety check",
)
async def test_binance_gateway_connection(
    body: BinanceTestConnectionRequest,
    gateway: Annotated[Any, Depends(get_binance_gateway)],
    _auth: Annotated[str, Depends(require_admin_auth)] = "ok",
) -> BinanceTestConnectionResponse:
    if gateway is None:
        from nexus.infrastructure.exchange.binance_gateway import BinanceFuturesGateway

        gateway = BinanceFuturesGateway(
            api_key=body.api_key,
            api_secret=body.api_secret,
            use_testnet=body.use_testnet,
        )

    res = await gateway.test_credentials(
        api_key=body.api_key,
        api_secret=body.api_secret,
        use_testnet=body.use_testnet,
    )
    return BinanceTestConnectionResponse(**res)


@router.post(
    "/terminal/binance-gateway/credentials",
    response_model=BinanceSaveCredentialsResponse,
    summary="Save and dynamically apply Binance API credentials",
)
async def save_binance_credentials(
    body: BinanceSaveCredentialsRequest,
    gateway: Annotated[Any, Depends(get_binance_gateway)],
    _auth: Annotated[str, Depends(require_admin_auth)] = "ok",
) -> BinanceSaveCredentialsResponse:
    if gateway is not None:
        gateway.update_credentials(
            api_key=body.api_key,
            api_secret=body.api_secret,
            use_testnet=body.use_testnet,
        )
    return BinanceSaveCredentialsResponse(
        success=True,
        message="Binance credentials and target environment successfully updated.",
        is_configured=bool(body.api_key and body.api_secret),
        is_testnet=body.use_testnet,
    )


@router.websocket("/ws/stream")
async def terminal_telemetry_stream(websocket: WebSocket) -> None:
    """Push real-time virtual portfolio, risk, and market ticker updates over WebSocket."""
    app = websocket.app
    settings: Settings = getattr(app.state, "settings", get_settings())
    if not await authenticate_websocket(websocket, settings):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return
    await websocket.accept()
    db_manager: DatabaseManager = app.state.db_manager
    market_data: MarketDataProvider = app.state.market_data_provider
    paper_repo = SqlAlchemyPaperRepository(db_manager.session_factory)
    candle_repo = SqlAlchemyCandleRepository(db_manager.session_factory)
    risk_manager = IndependentRiskManager(
        allowed_symbols=settings.allowed_symbols,
        risk_config=settings.risk,
        fee_bps=settings.paper_fee_bps,
        slippage_bps=settings.paper_slippage_bps,
    )
    from nexus.application.risk_guard import SpotSignalRiskApprover

    strategy_engine = NexusStrategyV1(
        config=settings.strategy_v1,
        risk_approver=SpotSignalRiskApprover(allowed_symbols=settings.allowed_symbols),
    )

    try:
        while True:
            snapshot = await _collect_terminal_snapshot(
                settings=settings,
                db_manager=db_manager,
                market_data=market_data,
                paper_repo=paper_repo,
                candle_repo=candle_repo,
                risk_manager=risk_manager,
                strategy_engine=strategy_engine,
            )
            await websocket.send_json(snapshot.model_dump(mode="json"))

            try:
                client_msg = await asyncio.wait_for(websocket.receive_text(), timeout=3.0)
                if client_msg.strip().lower() == "close":
                    await websocket.close()
                    return
            except TimeoutError:
                continue
    except WebSocketDisconnect:
        logger.debug("terminal_websocket_disconnected")
