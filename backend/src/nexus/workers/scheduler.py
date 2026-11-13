"""Automated paper-trading cycle runner and orchestrator wired to PersistentPaperBroker."""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict

from nexus.application.market_data.validator import CandleValidator
from nexus.application.persistent_paper_broker import PersistentPaperBroker
from nexus.application.risk_manager import IndependentRiskManager
from nexus.application.strategy.v1_engine import NexusStrategyV1
from nexus.application.strategy_engine import ohlcv_to_dataframe
from nexus.core.config import Settings
from nexus.core.logging import get_logger
from nexus.domain.interfaces import MarketDataProvider, PaperLedgerRepository, Strategy
from nexus.domain.models import (
    PaperOrderResult,
    PositionContext,
    StrategySignal,
    TradingSignal,
)

logger = get_logger(__name__)


class CycleExecutionSummary(BaseModel):
    """Structured report of an autonomous paper-trading cycle."""

    model_config = ConfigDict(frozen=True)

    timestamp: datetime
    evaluated_symbols: list[str]
    signals_emitted: list[StrategySignal]
    orders_executed: list[PaperOrderResult]
    kill_switch_active: bool
    rejection_notes: list[str]


class AutonomousPaperTradingOrchestrator:
    """Supervised autonomous loop orchestrating market data, strategy V1, and broker."""

    def __init__(
        self,
        *,
        settings: Settings,
        market_data: MarketDataProvider,
        strategy_v1: NexusStrategyV1,
        broker: PersistentPaperBroker,
        repository: PaperLedgerRepository,
        risk_manager: IndependentRiskManager,
    ) -> None:
        self._settings = settings
        self._market_data = market_data
        self._strategy = strategy_v1
        self._broker = broker
        self._repository = repository
        self._risk_manager = risk_manager

    async def run_cycle(self, *, now_utc: datetime | None = None) -> CycleExecutionSummary:
        """Execute one end-to-end evaluation cycle across allowed spot pairs."""
        ref_now = now_utc or datetime.now(UTC)
        portfolio = await self._repository.get_or_create_portfolio(
            None, initial_capital_inr=self._settings.initial_capital_inr
        )
        risk_state = await self._repository.get_or_create_risk_state(
            portfolio.id, initial_capital_inr=self._settings.initial_capital_inr
        )

        if risk_state.kill_switch_active:
            logger.warning(
                "cycle_aborted_kill_switch_active",
                reason=risk_state.kill_switch_reason,
            )
            return CycleExecutionSummary(
                timestamp=ref_now,
                evaluated_symbols=[],
                signals_emitted=[],
                orders_executed=[],
                kill_switch_active=True,
                rejection_notes=[f"Kill switch active: {risk_state.kill_switch_reason}"],
            )

        open_positions = await self._repository.get_open_positions(portfolio.id)
        pos_by_symbol = {
            pos.symbol: PositionContext(
                symbol=pos.symbol,
                entry_timestamp=pos.opened_at,
                entry_price=pos.avg_entry_price_usdt,
                quantity=pos.quantity,
                initial_stop_price=pos.initial_stop_price_usdt,
                trailing_stop_price=pos.trailing_stop_price_usdt,
                highest_price_since_entry=pos.highest_price_usdt,
            )
            for pos in open_positions
        }

        evaluated: list[str] = []
        emitted_signals: list[StrategySignal] = []
        executed_orders: list[PaperOrderResult] = []
        rejections: list[str] = []

        timeframe = self._settings.default_timeframe

        for symbol in self._settings.allowed_symbols:
            try:
                bars = await self._market_data.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=max(self._strategy.config.ema_slow_period + 10, 65),
                )
            except Exception as exc:
                msg = f"Failed to fetch OHLCV for {symbol}: {type(exc).__name__}"
                logger.warning("cycle_market_data_error", symbol=symbol, error=str(exc))
                rejections.append(msg)
                continue

            if not bars:
                continue

            pos_ctx = pos_by_symbol.get(symbol)
            eval_result = self._strategy.evaluate_bars(
                symbol=symbol,
                timeframe=timeframe,
                bars=bars,
                portfolio=portfolio,
                position=pos_ctx,
                now_utc=ref_now,
            )
            evaluated.append(symbol)

            if eval_result.signal is not None:
                emitted_signals.append(eval_result.signal)
                try:
                    order = await self._broker.execute_strategy_signal(
                        portfolio.id, eval_result.signal, now_utc=ref_now
                    )
                    executed_orders.append(order)
                    logger.info(
                        "cycle_order_settled",
                        symbol=symbol,
                        side=order.side.value,
                        status=order.status.value,
                        quantity=str(order.requested_qty),
                    )
                except Exception as exc:
                    rejection = f"Broker execution error for {symbol}: {exc}"
                    logger.error("cycle_execution_failed", symbol=symbol, error=str(exc))
                    rejections.append(rejection)
            elif eval_result.rejection_reason:
                rejections.append(f"{symbol}: {eval_result.rejection_reason}")

        return CycleExecutionSummary(
            timestamp=ref_now,
            evaluated_symbols=evaluated,
            signals_emitted=emitted_signals,
            orders_executed=executed_orders,
            kill_switch_active=False,
            rejection_notes=rejections,
        )


class PaperTradingCycleRunner:
    """Legacy cycle runner retained for backward-compatibility with earlier test suites."""

    def __init__(
        self,
        *,
        settings: Settings,
        market_data: MarketDataProvider,
        strategy: Strategy,
        validator: CandleValidator | None = None,
    ) -> None:
        self._settings = settings
        self._market_data = market_data
        self._strategy = strategy
        self._validator = validator or CandleValidator()

    async def run_once(self, *, now_utc: datetime | None = None) -> list[TradingSignal]:
        """Fetch real spot OHLCV data, reject incomplete candles, and emit signals."""
        signals: list[TradingSignal] = []
        ref_now = now_utc or datetime.now(UTC)

        for symbol in self._settings.allowed_symbols:
            bars = await self._market_data.fetch_ohlcv(
                symbol=symbol,
                timeframe=self._settings.default_timeframe,
                limit=100,
            )
            closed_bars, _ = self._validator.validate_and_clean(
                bars,
                symbol=symbol,
                timeframe=self._settings.default_timeframe,
                now_utc=ref_now,
                reject_incomplete=True,
                strict=False,
            )
            validated_bars = self._validator.validate_for_signal_generation(
                closed_bars,
                symbol=symbol,
                timeframe=self._settings.default_timeframe,
                min_bars=1,
                now_utc=ref_now,
                allow_gaps=False,
            )
            df = ohlcv_to_dataframe(validated_bars)
            signal = self._strategy.evaluate(symbol, df)
            signals.append(signal)
        return signals
