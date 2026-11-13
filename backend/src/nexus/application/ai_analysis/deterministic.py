"""Deterministic rule-based market analyzer producing zero-hallucination structured JSON."""

from nexus.domain.enums import MarketRegime, SignalDirection, TrendDirection, VolatilityLevel
from nexus.domain.models import (
    MarketAnalysisInput,
    MarketAnalysisOutput,
    SignalExplanation,
    StrategyAssessment,
)

_ANOMALY_DESCRIPTIONS: dict[str, str] = {
    "volume_spike": "Unusual volume surge relative to 20-bar volume SMA (>= 2.5x or z >= 2.5).",
    "volume_drought": "Unusually thin spot liquidity relative to volume SMA (<= 0.2x).",
    "extreme_rsi_overbought": "Extreme overbought momentum reading (RSI >= 80).",
    "extreme_rsi_oversold": "Extreme oversold momentum reading (RSI <= 20).",
    "volatility_spike": "Elevated ATR volatility regime (ATR% >= 4.0% or ATR percentile >= 90%).",
    "shock_move_1bar": "Single-bar price shock exceeding 5.0% absolute move.",
    "candle_history_gaps_detected": "Historical candle sequence contains missing bar timestamps.",
}


def _classify_volatility(
    atr_pct: float, realized_vol_pct: float, atr_pct_rank: float
) -> VolatilityLevel:
    if atr_pct >= 5.0 or realized_vol_pct >= 4.0:
        return VolatilityLevel.EXTREME
    if atr_pct >= 2.5 or realized_vol_pct >= 2.0 or atr_pct_rank >= 80.0:
        return VolatilityLevel.HIGH
    if atr_pct <= 0.7 and realized_vol_pct <= 0.6 and atr_pct_rank <= 30.0:
        return VolatilityLevel.LOW
    return VolatilityLevel.MODERATE


def _classify_trend(analysis_input: MarketAnalysisInput) -> TrendDirection:
    ind = analysis_input.indicators
    hist = analysis_input.historical_features
    ema_spread_pct = (
        float((ind.ema_fast - ind.ema_slow) / ind.ema_slow) * 100.0
        if ind.ema_slow > 0
        else 0.0
    )

    if (
        ind.ema_fast > ind.ema_slow
        and float(ind.close_usdt) > float(ind.ema_fast)
        and hist.return_5_bar_pct > 0.0
    ):
        return TrendDirection.BULLISH
    if (
        ind.ema_fast < ind.ema_slow
        and float(ind.close_usdt) < float(ind.ema_fast)
        and hist.return_5_bar_pct < 0.0
    ):
        return TrendDirection.BEARISH
    if abs(ema_spread_pct) < 0.15 and abs(hist.return_5_bar_pct) < 0.5:
        return TrendDirection.NEUTRAL
    return TrendDirection.MIXED


def _classify_regime(
    trend: TrendDirection,
    volatility: VolatilityLevel,
    anomalies: list[str],
) -> MarketRegime:
    if "candle_history_gaps_detected" in anomalies and trend == TrendDirection.MIXED:
        return MarketRegime.UNCERTAIN
    if volatility == VolatilityLevel.EXTREME:
        if "volume_spike" in anomalies and trend in (
            TrendDirection.BULLISH,
            TrendDirection.BEARISH,
        ):
            return MarketRegime.VOLATILE_BREAKOUT
        return MarketRegime.HIGH_VOLATILITY_CHOP
    if volatility == VolatilityLevel.HIGH and trend == TrendDirection.MIXED:
        return MarketRegime.HIGH_VOLATILITY_CHOP
    if volatility == VolatilityLevel.LOW and trend == TrendDirection.NEUTRAL:
        return MarketRegime.LOW_VOLATILITY_COMPRESSION
    if trend == TrendDirection.BULLISH:
        return MarketRegime.TRENDING_BULLISH
    if trend == TrendDirection.BEARISH:
        return MarketRegime.TRENDING_BEARISH
    if trend == TrendDirection.NEUTRAL:
        return MarketRegime.RANGING
    return MarketRegime.UNCERTAIN


def _build_performance_comparison(analysis_input: MarketAnalysisInput) -> str:
    comps = analysis_input.strategy_comparisons
    if not comps:
        return (
            "No historical strategy comparison snapshots were provided; "
            "deterministic strategy engine remains the sole source of signals."
        )

    ranked = sorted(comps, key=lambda item: item.net_pnl_inr, reverse=True)
    parts = [
        (
            f"{item.strategy_name}: {item.trades_count} trades, "
            f"historical win rate {item.win_rate_pct:.1f}%, "
            f"net INR {item.net_pnl_inr}, max DD {item.max_drawdown_pct:.2f}%"
        )
        for item in ranked
    ]
    leader = ranked[0].strategy_name
    return (
        f"Historical paper ledger comparison (past performance does not predict future outcomes; "
        f"top realized net PnL: {leader}): " + "; ".join(parts) + "."
    )


class DeterministicMarketAnalyzer:
    """Factual rule-based analyzer providing standalone or fallback structured output."""

    def analyze(
        self,
        analysis_input: MarketAnalysisInput,
        *,
        fallback_reason: str | None = None,
    ) -> MarketAnalysisOutput:
        """Analyze validated indicators and historical features without calling any LLM."""
        ind = analysis_input.indicators
        hist = analysis_input.historical_features

        volatility = _classify_volatility(
            ind.atr_pct,
            hist.realized_volatility_pct,
            hist.atr_percentile,
        )
        trend = _classify_trend(analysis_input)
        anomalies = list(dict.fromkeys(hist.anomaly_flags))
        regime = _classify_regime(trend, volatility, anomalies)

        unusual_descriptions = [
            _ANOMALY_DESCRIPTIONS.get(flag, f"Detected anomaly flag: {flag}.")
            for flag in anomalies
        ]

        risk_observations: list[str] = []
        if fallback_reason is not None:
            risk_observations.append(
                f"Advisory fallback mode active ({fallback_reason}); "
                "output generated deterministically."
            )
        if unusual_descriptions:
            risk_observations.extend(unusual_descriptions)
        if volatility in (VolatilityLevel.HIGH, VolatilityLevel.EXTREME):
            risk_observations.append(
                f"Elevated ATR ({ind.atr} USDT, {ind.atr_pct:.2f}% of close) widens stop distances "
                "under the 0.5% portfolio risk budget."
            )
        if ind.rsi >= 70.0:
            risk_observations.append(
                f"RSI ({ind.rsi:.1f}) sits above the V1 long upper threshold (70.0), "
                "raising pullback risk."
            )
        elif ind.rsi <= 30.0:
            risk_observations.append(
                f"RSI ({ind.rsi:.1f}) sits in oversold territory; "
                "momentum reversals remain erratic."
            )
        if not risk_observations:
            risk_observations.append(
                "Indicator readings lie within normal historical dispersion; all entries "
                "still require IndependentRiskManager approval and ATR stop-loss sizing."
            )

        signal_explanations: list[SignalExplanation] = []
        for sig in analysis_input.strategy_signals:
            if sig.direction == SignalDirection.LONG and trend == TrendDirection.BULLISH:
                alignment = "aligned_with_bullish_trend"
            elif sig.direction == SignalDirection.EXIT_LONG:
                alignment = "defensive_exit_or_reversal"
            else:
                alignment = "counter_trend_or_neutral_regime"
            signal_explanations.append(
                SignalExplanation(
                    strategy_name=sig.strategy_name,
                    symbol=sig.symbol,
                    direction=sig.direction,
                    signal_timestamp=sig.timestamp,
                    rationale=(
                        f"Deterministic signal at {sig.entry_price} USDT with stop "
                        f"{sig.stop_price} USDT: {sig.reason}"
                    ),
                    regime_alignment=alignment,
                    advisory_only=True,
                )
            )

        assessment = StrategyAssessment(
            signal_explanations=signal_explanations,
            performance_comparison=_build_performance_comparison(analysis_input),
            unusual_conditions_detected=bool(unusual_descriptions),
            unusual_conditions=unusual_descriptions,
            advisory_only=True,
            executable_signal=False,
        )

        explanation = (
            f"Advisory summary for {analysis_input.symbol} ({analysis_input.timeframe}) as of "
            f"{analysis_input.as_of_timestamp.isoformat()}: latest closed spot price is "
            f"{ind.close_usdt} USDT within historical range {hist.range_low_usdt} to "
            f"{hist.range_high_usdt} USDT ({hist.lookback_bars} bars). "
            f"EMA{ind.ema_fast_period} ({ind.ema_fast}) vs "
            f"EMA{ind.ema_slow_period} ({ind.ema_slow}) indicates {trend.value} trend bias with "
            f"{volatility.value} volatility (ATR {ind.atr}, RSI {ind.rsi:.1f}, volume ratio "
            f"{ind.volume_ratio:.2f}x). Analysis is strictly informational and issues no orders."
        )

        return MarketAnalysisOutput(
            market_regime=regime,
            trend_direction=trend,
            volatility_level=volatility,
            risk_observations=risk_observations,
            strategy_assessment=assessment,
            explanation=explanation,
            timestamp=analysis_input.as_of_timestamp,
        )
