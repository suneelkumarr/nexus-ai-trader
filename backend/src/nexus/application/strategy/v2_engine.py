"""NEXUS Strategy Engine V2: Mean-Reversion Bollinger Oversold Bounce (Bear & Chop Specialist)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field

from nexus.application.market_data.validator import CandleValidator
from nexus.application.strategy.indicators import (
    compute_atr,
    compute_bollinger_bands,
    compute_rsi,
    compute_volume_sma,
)
from nexus.application.strategy.v1_engine import StrategyEvaluationResult
from nexus.application.strategy_engine import ohlcv_to_dataframe
from nexus.core.exceptions import CandleValidationError, IncompleteCandleError
from nexus.core.logging import get_logger
from nexus.domain.enums import SignalDirection
from nexus.domain.interfaces import SignalRiskApprover
from nexus.domain.models import (
    OHLCVBar,
    PortfolioState,
    PositionContext,
    StrategySignal,
)

logger = get_logger(__name__)

_PRICE_QUANT = Decimal("0.00000001")


class StrategyV2Config(BaseModel):
    """Parameters for Mean-Reversion Bollinger + RSI Oversold Bounce Strategy."""

    model_config = ConfigDict(frozen=True)

    strategy_name: str = "nexus_oversold_bb_rsi_v2"
    bollinger_period: int = Field(default=20, ge=5, le=100)
    bollinger_std: float = Field(default=2.0, ge=1.0, le=4.0)
    rsi_period: int = Field(default=14, ge=2, le=50)
    rsi_oversold_max: float = Field(default=35.0, ge=10.0, le=45.0)
    rsi_exit_min: float = Field(default=60.0, ge=45.0, le=90.0)
    atr_period: int = Field(default=14, ge=2, le=50)
    volume_sma_period: int = Field(default=20, ge=2, le=100)
    stop_atr_multiplier: Decimal = Field(default=Decimal("1.5"), gt=Decimal("0"))
    min_candles_required: int = 35


class NexusStrategyV2:
    """Spot mean-reversion strategy designed to capture high win-rate bounces in downtrends."""

    def __init__(
        self,
        *,
        config: StrategyV2Config | None = None,
        risk_approver: SignalRiskApprover,
        validator: CandleValidator | None = None,
    ) -> None:
        self._config = config or StrategyV2Config()
        self._risk_approver = risk_approver
        self._validator = validator or CandleValidator()
        self._last_evaluated_ts: dict[tuple[str, str], datetime] = {}
        self._emitted_keys: set[tuple[str, str, datetime, SignalDirection]] = set()

    @property
    def config(self) -> StrategyV2Config:
        return self._config

    def evaluate_bars(
        self,
        *,
        symbol: str,
        timeframe: str,
        bars: Sequence[OHLCVBar],
        portfolio: PortfolioState,
        position: PositionContext | None = None,
        now_utc: datetime | None = None,
    ) -> StrategyEvaluationResult:
        """Evaluate latest closed bar against Bollinger lower-band oversold bounce criteria."""
        norm_symbol = symbol.strip().upper()
        norm_tf = timeframe.strip().lower()
        now = now_utc or datetime.now(UTC)

        try:
            validated_bars = self._validator.validate_for_signal_generation(
                bars,
                symbol=norm_symbol,
                timeframe=norm_tf,
                min_bars=self._config.min_candles_required,
                now_utc=now,
                allow_gaps=True,
            )
        except (CandleValidationError, IncompleteCandleError) as exc:
            return StrategyEvaluationResult(
                signal=None,
                status="insufficient_history",
                evaluated_timestamp=now,
                rejection_reason=f"Candle validation error: {exc}",
                updated_position=None,
            )

        if len(validated_bars) < self._config.min_candles_required:
            return StrategyEvaluationResult(
                signal=None,
                status="insufficient_history",
                evaluated_timestamp=now,
                rejection_reason=(
                    f"Need >= {self._config.min_candles_required} closed bars, "
                    f"got {len(validated_bars)}."
                ),
                updated_position=None,
            )

        latest_bar = validated_bars[-1]
        latest_ts = latest_bar.timestamp

        key = (norm_symbol, norm_tf)
        prev_ts = self._last_evaluated_ts.get(key)
        if prev_ts is not None and latest_ts <= prev_ts:
            return StrategyEvaluationResult(
                signal=None,
                status="duplicate_suppressed",
                evaluated_timestamp=latest_ts,
                rejection_reason=f"Bar at {latest_ts.isoformat()} was already evaluated.",
                updated_position=None,
            )
        self._last_evaluated_ts[key] = latest_ts

        df = ohlcv_to_dataframe(validated_bars)
        middle_bb, _, lower_bb = compute_bollinger_bands(
            df["close"], self._config.bollinger_period, self._config.bollinger_std
        )
        rsi_series = compute_rsi(df["close"], self._config.rsi_period)
        atr_series = compute_atr(
            df["high"], df["low"], df["close"], self._config.atr_period
        )
        vol_sma_series = compute_volume_sma(df["volume"], self._config.volume_sma_period)

        curr_close = float(df["close"].iloc[-1])
        curr_open = float(df["open"].iloc[-1])
        curr_lower = float(lower_bb.iloc[-1])
        curr_middle = float(middle_bb.iloc[-1])
        curr_rsi = float(rsi_series.iloc[-1])
        curr_atr = float(atr_series.iloc[-1])
        curr_vol = float(df["volume"].iloc[-1])
        curr_vol_sma = float(vol_sma_series.iloc[-1])

        # --- EXIT EVALUATION (If currently holding a position) ---
        if position is not None:
            hit_take_profit = curr_close >= curr_middle
            hit_overbought = curr_rsi >= self._config.rsi_exit_min
            active_stop = max(position.initial_stop_price, position.trailing_stop_price)
            hit_stop = latest_bar.low <= active_stop

            if hit_take_profit or hit_overbought or hit_stop:
                exit_reason = (
                    "Reached Middle Bollinger Mean"
                    if hit_take_profit
                    else "RSI Overbought Recovery"
                    if hit_overbought
                    else "Stop-Loss Breached"
                )
                sig = StrategySignal(
                    strategy_name=self._config.strategy_name,
                    symbol=norm_symbol,
                    direction=SignalDirection.EXIT_LONG,
                    timestamp=latest_ts,
                    entry_price=latest_bar.close.quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP),
                    stop_price=active_stop,
                    reason=exit_reason,
                    indicators={
                        "rsi": curr_rsi,
                        "close": curr_close,
                        "middle_bb": curr_middle,
                    },
                )
                return StrategyEvaluationResult(
                    signal=sig,
                    status="exit_signal",
                    evaluated_timestamp=latest_ts,
                    rejection_reason=None,
                    updated_position=None,
                )
            new_highest = max(position.highest_price_since_entry, latest_bar.high)
            updated_pos = position.model_copy(
                update={"highest_price_since_entry": new_highest}
            )
            return StrategyEvaluationResult(
                signal=None,
                status="no_signal",
                evaluated_timestamp=latest_ts,
                rejection_reason="Position open; hold condition active.",
                updated_position=updated_pos,
            )

        # --- ENTRY EVALUATION (No open position) ---
        is_oversold = curr_rsi <= self._config.rsi_oversold_max
        touches_lower_bb = curr_close <= (curr_lower * 1.005)
        is_green_reversal = curr_close > curr_open
        vol_adequate = curr_vol >= (curr_vol_sma * 0.70)

        if not (is_oversold and touches_lower_bb and is_green_reversal and vol_adequate):
            return StrategyEvaluationResult(
                signal=None,
                status="no_signal",
                evaluated_timestamp=latest_ts,
                rejection_reason="Oversold bounce entry criteria not met.",
                updated_position=None,
            )

        entry_price = latest_bar.close.quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP)
        atr_dec = Decimal(str(curr_atr))
        stop_price = (entry_price - (atr_dec * self._config.stop_atr_multiplier)).quantize(
            _PRICE_QUANT, rounding=ROUND_HALF_UP
        )

        if stop_price <= Decimal("0"):
            return StrategyEvaluationResult(
                signal=None,
                status="risk_rejected",
                evaluated_timestamp=latest_ts,
                rejection_reason="Stop price non-positive.",
                updated_position=None,
            )

        approved, risk_reason = self._risk_approver.approve_entry(
            symbol=norm_symbol,
            timestamp=latest_ts,
            entry_price=entry_price,
            stop_price=stop_price,
            portfolio=portfolio,
        )

        if not approved:
            return StrategyEvaluationResult(
                signal=None,
                status="risk_rejected",
                evaluated_timestamp=latest_ts,
                rejection_reason=risk_reason,
                updated_position=None,
            )

        sig = StrategySignal(
            strategy_name=self._config.strategy_name,
            symbol=norm_symbol,
            direction=SignalDirection.LONG,
            timestamp=latest_ts,
            entry_price=entry_price,
            stop_price=stop_price,
            reason=(
                f"Oversold bounce: RSI {curr_rsi:.1f} <= {self._config.rsi_oversold_max}, "
                f"Close {curr_close:.4f} <= Lower BB {curr_lower:.4f}, green candle confirmed."
            ),
            indicators={
                "rsi": curr_rsi,
                "lower_bb": curr_lower,
                "middle_bb": curr_middle,
                "atr": curr_atr,
            },
        )

        logger.info(
            "strategy_v2_oversold_bounce_signal",
            symbol=norm_symbol,
            entry=str(entry_price),
            stop=str(stop_price),
            rsi=round(curr_rsi, 2),
        )

        return StrategyEvaluationResult(
            signal=sig,
            status="entry_signal",
            evaluated_timestamp=latest_ts,
            rejection_reason=None,
            updated_position=None,
        )
