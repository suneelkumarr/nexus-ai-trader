"""NEXUS Strategy Engine V1: EMA Trend + RSI + ATR + Volume confirmation."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from nexus.application.market_data.validator import CandleValidator
from nexus.application.strategy.config import StrategyV1Config
from nexus.application.strategy.indicators import compute_v1_indicators
from nexus.application.strategy_engine import ohlcv_to_dataframe
from nexus.core.exceptions import CandleValidationError
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


class StrategyEvaluationResult(BaseModel):
    """Detailed outcome of evaluating a closed candle bar."""

    model_config = ConfigDict(frozen=True)

    signal: StrategySignal | None = None
    status: Literal[
        "entry_signal",
        "exit_signal",
        "no_signal",
        "duplicate_suppressed",
        "risk_rejected",
        "insufficient_history",
    ]
    evaluated_timestamp: datetime
    rejection_reason: str | None = None
    updated_position: PositionContext | None = None


class NexusStrategyV1:
    """Causal, spot-only LONG/EXIT strategy with ATR stops and duplicate protection."""

    def __init__(
        self,
        *,
        config: StrategyV1Config | None = None,
        risk_approver: SignalRiskApprover,
        validator: CandleValidator | None = None,
    ) -> None:
        self._config = config or StrategyV1Config()
        self._risk_approver = risk_approver
        self._validator = validator or CandleValidator()
        self._last_evaluated_ts: dict[tuple[str, str], datetime] = {}
        self._emitted_keys: set[tuple[str, str, datetime, SignalDirection]] = set()

    @property
    def config(self) -> StrategyV1Config:
        """Return active StrategyV1Config."""
        return self._config

    def export_checkpoints(self) -> dict[str, str]:
        """Export serialized (symbol:timeframe -> ISO-8601 UTC) checkpoints for persistence."""
        return {
            f"{sym}:{tf}": ts.isoformat()
            for (sym, tf), ts in self._last_evaluated_ts.items()
        }

    def import_checkpoints(self, checkpoints: dict[str, str]) -> None:
        """Load persisted checkpoints to prevent duplicate re-evaluations across restarts."""
        for key, raw_ts in checkpoints.items():
            if ":" in key:
                sym, tf = key.split(":", maxsplit=1)
                try:
                    self._last_evaluated_ts[(sym, tf)] = datetime.fromisoformat(raw_ts)
                except ValueError:
                    continue

    @property
    def name(self) -> str:
        """Return configured strategy identifier."""
        return self._config.strategy_name

    def _validate_closed_history(
        self,
        bars: Sequence[OHLCVBar],
        *,
        symbol: str,
        timeframe: str,
        now_utc: datetime,
    ) -> list[OHLCVBar]:
        """Reject future candles, incomplete candles, duplicates, and gaps."""
        ref_now = self._validator.ensure_utc(now_utc)
        for bar in bars:
            bar_ts = self._validator.ensure_utc(bar.timestamp)
            if bar_ts > ref_now:
                raise CandleValidationError(
                    f"Future candle access forbidden: bar {bar_ts.isoformat()} > "
                    f"now {ref_now.isoformat()}"
                )
        return self._validator.validate_for_signal_generation(
            bars,
            symbol=symbol,
            timeframe=timeframe,
            min_bars=1,
            now_utc=ref_now,
            allow_gaps=False,
        )

    def _has_open_position(
        self, symbol: str, portfolio: PortfolioState, position: PositionContext | None
    ) -> bool:
        if position is not None:
            return True
        base_asset = symbol.strip().upper().split("/", maxsplit=1)[0]
        holding = portfolio.holdings.get(base_asset)
        return holding is not None and (holding.free_qty + holding.locked_qty) > Decimal("0")

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
        """Evaluate closed bars strictly up to now_utc without look-ahead bias."""
        ref_now = self._validator.ensure_utc(now_utc) if now_utc is not None else datetime.now(UTC)
        norm_symbol = symbol.strip().upper()
        norm_tf = timeframe.strip().lower()

        closed_bars = self._validate_closed_history(
            bars, symbol=norm_symbol, timeframe=norm_tf, now_utc=ref_now
        )
        latest_bar = closed_bars[-1]
        latest_ts = latest_bar.timestamp

        # Prevent duplicate evaluation / signal emission for the same closed candle
        state_key = (norm_symbol, norm_tf)
        prev_eval_ts = self._last_evaluated_ts.get(state_key)
        if prev_eval_ts is not None and latest_ts <= prev_eval_ts:
            return StrategyEvaluationResult(
                signal=None,
                status="duplicate_suppressed",
                evaluated_timestamp=latest_ts,
                rejection_reason=(
                    f"Candle {latest_ts.isoformat()} already evaluated for "
                    f"{norm_symbol} ({norm_tf})."
                ),
                updated_position=position,
            )

        if len(closed_bars) < self._config.min_candles_required:
            return StrategyEvaluationResult(
                signal=None,
                status="insufficient_history",
                evaluated_timestamp=latest_ts,
                rejection_reason=(
                    f"Need at least {self._config.min_candles_required} closed candles, "
                    f"received {len(closed_bars)}."
                ),
                updated_position=position,
            )

        df = compute_v1_indicators(ohlcv_to_dataframe(closed_bars), self._config)
        prev_row = df.iloc[-2]
        curr_row = df.iloc[-1]

        required_fields = ("ema_fast", "ema_slow", "rsi", "atr", "volume_sma")
        if any(curr_row[field] != curr_row[field] for field in required_fields) or (
            prev_row["ema_fast"] != prev_row["ema_fast"]
            or prev_row["ema_slow"] != prev_row["ema_slow"]
        ):
            return StrategyEvaluationResult(
                signal=None,
                status="insufficient_history",
                evaluated_timestamp=latest_ts,
                rejection_reason="Indicator warmup incomplete (NaN values present).",
                updated_position=position,
            )

        self._last_evaluated_ts[state_key] = latest_ts

        prev_fast = float(prev_row["ema_fast"])
        prev_slow = float(prev_row["ema_slow"])
        curr_fast = float(curr_row["ema_fast"])
        curr_slow = float(curr_row["ema_slow"])
        curr_rsi = float(curr_row["rsi"])
        curr_atr = float(curr_row["atr"])
        curr_vol = float(curr_row["volume"])
        curr_vol_sma = float(curr_row["volume_sma"])

        indicators = {
            "ema_20": round(curr_fast, 8),
            "ema_50": round(curr_slow, 8),
            "rsi_14": round(curr_rsi, 4),
            "atr_14": round(curr_atr, 8),
            "volume_sma_20": round(curr_vol_sma, 8),
            "volume": round(curr_vol, 8),
        }

        # --- EXIT EVALUATION (when a LONG position is open) ---
        if position is not None:
            return self._evaluate_exit(
                symbol=norm_symbol,
                timeframe=norm_tf,
                latest_bar=latest_bar,
                position=position,
                prev_fast=prev_fast,
                prev_slow=prev_slow,
                curr_fast=curr_fast,
                curr_slow=curr_slow,
                curr_atr=curr_atr,
                indicators=indicators,
            )

        # --- ENTRY EVALUATION (no open position) ---
        if self._has_open_position(norm_symbol, portfolio, position):
            return StrategyEvaluationResult(
                signal=None,
                status="no_signal",
                evaluated_timestamp=latest_ts,
                rejection_reason="Spot position already open in portfolio.",
                updated_position=None,
            )

        ema_crossed_up = prev_fast <= prev_slow and curr_fast > curr_slow
        rsi_in_zone = self._config.rsi_entry_min <= curr_rsi <= self._config.rsi_entry_max
        volume_confirmed = curr_vol > curr_vol_sma

        if not (ema_crossed_up and rsi_in_zone and volume_confirmed):
            return StrategyEvaluationResult(
                signal=None,
                status="no_signal",
                evaluated_timestamp=latest_ts,
                rejection_reason="Entry conditions not satisfied on latest closed bar.",
                updated_position=None,
            )

        entry_price = latest_bar.close.quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP)
        atr_dec = Decimal(str(curr_atr))
        stop_price = (entry_price - atr_dec * self._config.stop_atr_multiplier).quantize(
            _PRICE_QUANT, rounding=ROUND_HALF_UP
        )

        if stop_price <= Decimal("0"):
            return StrategyEvaluationResult(
                signal=None,
                status="risk_rejected",
                evaluated_timestamp=latest_ts,
                rejection_reason="Computed ATR stop price is non-positive.",
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
            logger.info(
                "strategy_entry_risk_rejected",
                strategy=self.name,
                symbol=norm_symbol,
                timestamp=latest_ts.isoformat(),
                reason=risk_reason,
            )
            return StrategyEvaluationResult(
                signal=None,
                status="risk_rejected",
                evaluated_timestamp=latest_ts,
                rejection_reason=risk_reason,
                updated_position=None,
            )

        dedup_key = (norm_symbol, norm_tf, latest_ts, SignalDirection.LONG)
        if dedup_key in self._emitted_keys:
            return StrategyEvaluationResult(
                signal=None,
                status="duplicate_suppressed",
                evaluated_timestamp=latest_ts,
                rejection_reason="Duplicate LONG signal suppressed.",
                updated_position=None,
            )

        self._emitted_keys.add(dedup_key)
        signal = StrategySignal(
            symbol=norm_symbol,
            timestamp=latest_ts,
            direction=SignalDirection.LONG,
            entry_price=entry_price,
            stop_price=stop_price,
            strategy_name=self.name,
            reason=(
                "EMA20 crossed above EMA50; RSI14 within entry band; "
                "volume exceeded Volume SMA20; risk manager approved."
            ),
            indicators=indicators,
        )
        logger.info(
            "strategy_long_signal_emitted",
            strategy=self.name,
            symbol=norm_symbol,
            timestamp=latest_ts.isoformat(),
            entry_price=str(entry_price),
            stop_price=str(stop_price),
        )
        return StrategyEvaluationResult(
            signal=signal,
            status="entry_signal",
            evaluated_timestamp=latest_ts,
            updated_position=None,
        )

    def _evaluate_exit(
        self,
        *,
        symbol: str,
        timeframe: str,
        latest_bar: OHLCVBar,
        position: PositionContext,
        prev_fast: float,
        prev_slow: float,
        curr_fast: float,
        curr_slow: float,
        curr_atr: float,
        indicators: dict[str, float],
    ) -> StrategyEvaluationResult:
        """Evaluate stop-loss, causal trailing stop, and confirmed trend reversal."""
        latest_ts = latest_bar.timestamp
        exit_reason: str | None = None
        trigger_stop = max(position.initial_stop_price, position.trailing_stop_price)

        # 1. Initial stop-loss check (evaluated against prior causal stop)
        if latest_bar.low <= position.initial_stop_price:
            exit_reason = "Stop-loss triggered on closed candle."
            trigger_stop = position.initial_stop_price
        # 2. Trailing stop check (evaluated against prior bar's trailing stop before ratcheting)
        elif (
            position.trailing_stop_price > position.initial_stop_price
            and latest_bar.low <= position.trailing_stop_price
        ):
            exit_reason = "Trailing stop triggered on closed candle."
            trigger_stop = position.trailing_stop_price
        # 3. Confirmed trend reversal (EMA20 crosses below EMA50)
        elif prev_fast >= prev_slow and curr_fast < curr_slow and (
            not self._config.confirm_reversal_with_close
            or float(latest_bar.close) < curr_fast
        ):
            exit_reason = "Confirmed trend reversal: EMA20 crossed below EMA50."

        if exit_reason is not None:
            dedup_key = (symbol, timeframe, latest_ts, SignalDirection.EXIT_LONG)
            if dedup_key in self._emitted_keys:
                return StrategyEvaluationResult(
                    signal=None,
                    status="duplicate_suppressed",
                    evaluated_timestamp=latest_ts,
                    rejection_reason="Duplicate EXIT_LONG signal suppressed.",
                    updated_position=position,
                )
            self._emitted_keys.add(dedup_key)
            exit_price = latest_bar.close.quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP)
            signal = StrategySignal(
                symbol=symbol,
                timestamp=latest_ts,
                direction=SignalDirection.EXIT_LONG,
                entry_price=exit_price,
                stop_price=trigger_stop,
                strategy_name=self.name,
                reason=exit_reason,
                indicators=indicators,
            )
            logger.info(
                "strategy_exit_signal_emitted",
                strategy=self.name,
                symbol=symbol,
                timestamp=latest_ts.isoformat(),
                exit_price=str(exit_price),
                stop_price=str(trigger_stop),
                reason=exit_reason,
            )
            return StrategyEvaluationResult(
                signal=signal,
                status="exit_signal",
                evaluated_timestamp=latest_ts,
                updated_position=None,
            )

        # Ratchet trailing stop causally for the NEXT bar only after confirming no exit on bar t
        new_highest = max(position.highest_price_since_entry, latest_bar.high)
        atr_dec = Decimal(str(curr_atr))
        candidate_trail = (new_highest - atr_dec * self._config.trailing_atr_multiplier).quantize(
            _PRICE_QUANT, rounding=ROUND_HALF_UP
        )
        new_trailing = max(position.trailing_stop_price, candidate_trail)
        updated_pos = position.model_copy(
            update={
                "highest_price_since_entry": new_highest,
                "trailing_stop_price": new_trailing,
            }
        )
        return StrategyEvaluationResult(
            signal=None,
            status="no_signal",
            evaluated_timestamp=latest_ts,
            rejection_reason="Position held; no exit condition triggered.",
            updated_position=updated_pos,
        )
