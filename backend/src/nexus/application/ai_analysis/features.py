"""Causal feature builder turning validated closed OHLCV bars into AI analysis inputs."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

import numpy as np
import pandas as pd

from nexus.application.market_data.validator import CandleValidator
from nexus.application.strategy.config import StrategyV1Config
from nexus.application.strategy.indicators import compute_v1_indicators
from nexus.application.strategy_engine import ohlcv_to_dataframe
from nexus.core.exceptions import CandleValidationError, IncompleteCandleError
from nexus.domain.models import (
    HistoricalFeatureSummary,
    MarketAnalysisInput,
    OHLCVBar,
    StrategyPerformanceSnapshot,
    StrategySignal,
    StrategySignalSummary,
    TradeLedgerEntry,
    ValidatedIndicatorSnapshot,
)

_QUANT_8 = Decimal("0.00000001")


def _dec(value: float) -> Decimal:
    return Decimal(f"{value:.8f}").quantize(_QUANT_8, rounding=ROUND_HALF_UP)


def summarize_strategy_performance(
    strategy_name: str,
    entries: Sequence[TradeLedgerEntry],
) -> StrategyPerformanceSnapshot:
    """Compute realized strategy comparison metrics from closed paper trade ledger entries."""
    if not entries:
        return StrategyPerformanceSnapshot(
            strategy_name=strategy_name,
            trades_count=0,
            win_rate_pct=0.0,
            net_pnl_inr=Decimal("0.00"),
            max_drawdown_pct=0.0,
            profit_factor=None,
            avg_return_pct=0.0,
        )

    ordered = sorted(entries, key=lambda item: item.closed_at)
    wins = sum(1 for item in ordered if item.realized_pnl_inr > Decimal("0"))
    gross_profit = sum(
        (item.realized_pnl_inr for item in ordered if item.realized_pnl_inr > Decimal("0")),
        start=Decimal("0"),
    )
    gross_loss = sum(
        (-item.realized_pnl_inr for item in ordered if item.realized_pnl_inr < Decimal("0")),
        start=Decimal("0"),
    )
    net_pnl = sum((item.realized_pnl_inr for item in ordered), start=Decimal("0"))

    cumulative = Decimal("0")
    peak = Decimal("0")
    max_dd_pct = 0.0
    for item in ordered:
        cumulative += item.realized_pnl_inr
        if cumulative > peak:
            peak = cumulative
        baseline = item.entry_cost_inr + peak
        if baseline > Decimal("0") and cumulative < peak:
            dd = float(((peak - cumulative) / baseline) * Decimal("100"))
            max_dd_pct = max(max_dd_pct, dd)

    profit_factor: float | None = None
    if gross_loss > Decimal("0"):
        profit_factor = round(float(gross_profit / gross_loss), 4)

    avg_return_pct = float(
        sum(float(item.realized_pnl_pct) for item in ordered) / len(ordered)
    )
    return StrategyPerformanceSnapshot(
        strategy_name=strategy_name,
        trades_count=len(ordered),
        win_rate_pct=round((wins / len(ordered)) * 100.0, 2),
        net_pnl_inr=net_pnl.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        max_drawdown_pct=round(max_dd_pct, 2),
        profit_factor=profit_factor,
        avg_return_pct=round(avg_return_pct, 4),
    )


class ValidatedFeatureBuilder:
    """Validates closed OHLCV candles and computes strictly causal indicator/feature inputs."""

    def __init__(
        self,
        *,
        strategy_config: StrategyV1Config | None = None,
        validator: CandleValidator | None = None,
    ) -> None:
        self._config = strategy_config or StrategyV1Config()
        self._validator = validator or CandleValidator()

    def build(
        self,
        *,
        symbol: str,
        timeframe: str,
        bars: Sequence[OHLCVBar],
        strategy_signals: Sequence[StrategySignal] = (),
        strategy_comparisons: Sequence[StrategyPerformanceSnapshot] = (),
        now_utc: datetime | None = None,
        lookback_bars: int = 50,
    ) -> MarketAnalysisInput:
        """Validate closed candles and extract causal indicators and historical features."""
        ref_now = self._validator.ensure_utc(now_utc or datetime.now(UTC))
        for bar in bars:
            bar_ts = self._validator.ensure_utc(bar.timestamp)
            if bar_ts > ref_now:
                raise CandleValidationError(
                    f"Future candle access forbidden: bar {bar_ts.isoformat()} > "
                    f"now {ref_now.isoformat()}"
                )
            if not self._validator.is_candle_closed(bar, timeframe, now_utc=ref_now):
                raise IncompleteCandleError(
                    f"Incomplete candle at {bar_ts.isoformat()} for {symbol} ({timeframe}) "
                    "rejected for market analysis."
                )

        ordered, report = self._validator.validate_and_clean(
            bars,
            symbol=symbol,
            timeframe=timeframe,
            reject_incomplete=True,
            now_utc=ref_now,
        )
        if report.duplicate_timestamps:
            raise CandleValidationError(
                f"Duplicate timestamps detected for {symbol} {timeframe}: "
                f"{[ts.isoformat() for ts in report.duplicate_timestamps]}"
            )

        required_bars = max(
            self._config.ema_slow_period,
            self._config.rsi_period + 1,
            self._config.atr_period,
            self._config.volume_sma_period,
        )
        if len(ordered) < required_bars:
            raise CandleValidationError(
                f"Insufficient closed candles for indicator computation: need {required_bars}, "
                f"got {len(ordered)}."
            )

        df = ohlcv_to_dataframe(ordered)
        ind_df = compute_v1_indicators(df, self._config)
        latest = ind_df.iloc[-1]

        required_cols = ("close", "ema_fast", "ema_slow", "rsi", "atr", "volume", "volume_sma")
        for col in required_cols:
            val = float(latest[col])
            if pd.isna(val) or not np.isfinite(val):
                raise CandleValidationError(
                    f"Indicator '{col}' is not valid/finite at latest closed candle."
                )

        close_f = float(latest["close"])
        atr_f = float(latest["atr"])
        vol_f = float(latest["volume"])
        vol_sma_f = float(latest["volume_sma"])
        rsi_f = float(latest["rsi"])

        atr_pct = (atr_f / close_f) * 100.0 if close_f > 0.0 else 0.0
        volume_ratio = (vol_f / vol_sma_f) if vol_sma_f > 0.0 else 0.0

        indicators = ValidatedIndicatorSnapshot(
            close_usdt=_dec(close_f),
            ema_fast=_dec(float(latest["ema_fast"])),
            ema_slow=_dec(float(latest["ema_slow"])),
            ema_fast_period=self._config.ema_fast_period,
            ema_slow_period=self._config.ema_slow_period,
            rsi=round(rsi_f, 4),
            rsi_period=self._config.rsi_period,
            atr=_dec(atr_f),
            atr_period=self._config.atr_period,
            atr_pct=round(atr_pct, 4),
            volume=_dec(vol_f),
            volume_sma=_dec(vol_sma_f),
            volume_sma_period=self._config.volume_sma_period,
            volume_ratio=round(volume_ratio, 4),
        )

        window = min(max(lookback_bars, 2), len(ind_df))
        recent = ind_df.iloc[-window:]
        closes = recent["close"].astype(float)
        pct_returns = closes.pct_change().dropna() * 100.0

        def _lag_return_pct(lag: int) -> float:
            idx = 0 if len(closes) <= lag else -(lag + 1)
            base = float(closes.iloc[idx])
            if base <= 0.0:
                return 0.0
            return round(((close_f - base) / base) * 100.0, 4)

        realized_vol_pct = (
            round(float(pct_returns.std(ddof=0)), 4) if len(pct_returns) > 0 else 0.0
        )

        atr_series = ind_df["atr"].dropna().astype(float)
        if len(atr_series) > 0:
            atr_percentile = round(
                float((atr_series <= atr_f).sum()) / float(len(atr_series)) * 100.0, 2
            )
        else:
            atr_percentile = 0.0

        vol_series = recent["volume"].astype(float)
        vol_std = float(vol_series.std(ddof=0))
        vol_mean = float(vol_series.mean())
        volume_zscore = round((vol_f - vol_mean) / vol_std, 4) if vol_std > 0.0 else 0.0

        range_high = _dec(float(recent["high"].astype(float).max()))
        range_low = _dec(float(recent["low"].astype(float).min()))
        gap_count = len(report.missing_timestamps)

        return_1_bar = _lag_return_pct(1)
        anomaly_flags: list[str] = []
        if volume_ratio >= 2.5 or volume_zscore >= 2.5:
            anomaly_flags.append("volume_spike")
        elif vol_sma_f > 0.0 and volume_ratio <= 0.2:
            anomaly_flags.append("volume_drought")
        if rsi_f >= 80.0:
            anomaly_flags.append("extreme_rsi_overbought")
        elif rsi_f <= 20.0:
            anomaly_flags.append("extreme_rsi_oversold")
        if atr_pct >= 4.0 or atr_percentile >= 90.0:
            anomaly_flags.append("volatility_spike")
        if abs(return_1_bar) >= 5.0:
            anomaly_flags.append("shock_move_1bar")
        if gap_count > 0:
            anomaly_flags.append("candle_history_gaps_detected")

        historical_features = HistoricalFeatureSummary(
            lookback_bars=window,
            return_1_bar_pct=return_1_bar,
            return_5_bar_pct=_lag_return_pct(5),
            return_20_bar_pct=_lag_return_pct(20),
            realized_volatility_pct=realized_vol_pct,
            atr_percentile=atr_percentile,
            volume_zscore=volume_zscore,
            range_high_usdt=range_high,
            range_low_usdt=range_low,
            gap_count=gap_count,
            anomaly_flags=anomaly_flags,
        )

        signal_summaries = [
            StrategySignalSummary(
                symbol=sig.symbol,
                timestamp=sig.timestamp,
                direction=sig.direction,
                entry_price=sig.entry_price,
                stop_price=sig.stop_price,
                strategy_name=sig.strategy_name,
                reason=sig.reason,
            )
            for sig in strategy_signals
        ]

        latest_ts = self._validator.ensure_utc(ordered[-1].timestamp)
        return MarketAnalysisInput(
            symbol=ordered[-1].symbol,
            timeframe=ordered[-1].timeframe,
            as_of_timestamp=latest_ts,
            indicators=indicators,
            historical_features=historical_features,
            strategy_signals=signal_summaries,
            strategy_comparisons=list(strategy_comparisons),
        )
