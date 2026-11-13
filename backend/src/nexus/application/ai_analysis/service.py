"""Advisory NEXUS AI Market Analysis service (strictly read-only, zero execution access)."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from nexus.application.ai_analysis.cache import AnalysisCache
from nexus.application.ai_analysis.deterministic import DeterministicMarketAnalyzer
from nexus.application.ai_analysis.features import ValidatedFeatureBuilder
from nexus.application.ai_analysis.validator import AIResponseValidator
from nexus.application.strategy.config import StrategyV1Config
from nexus.core.ai_config import AIAnalysisConfig
from nexus.core.exceptions import AIProviderError, AIResponseValidationError
from nexus.core.logging import get_logger
from nexus.domain.interfaces import AIAnalysisClient
from nexus.domain.models import (
    MarketAnalysisInput,
    MarketAnalysisOutput,
    OHLCVBar,
    StrategyPerformanceSnapshot,
    StrategySignal,
)

logger = get_logger(__name__)

_SYSTEM_PROMPT = """You are NEXUS AI Market Analyst (STRICTLY ADVISORY, READ-ONLY).
You must NEVER place orders, emit executable trade instructions, or bypass the Risk Manager.
The deterministic Strategy Engine V1 remains the sole source of executable trading signals.

Analyze ONLY the validated JSON market indicators, historical features, deterministic signals,
and historical strategy performance records supplied in the user payload.

STRICT RULES:
1. Output a single valid JSON object containing ONLY these exact 7 top-level keys:
   - "market_regime": trending_bullish | trending_bearish | ranging | volatile_breakout |
     high_volatility_chop | low_volatility_compression | uncertain
   - "trend_direction": bullish | bearish | neutral | mixed
   - "volatility_level": low | moderate | high | extreme
   - "risk_observations": non-empty array of concise strings noting market risks & anomalies
   - "strategy_assessment": {
       "signal_explanations": [{
         "strategy_name": str, "symbol": str, "direction": "long"|"exit_long"|"flat",
         "signal_timestamp": ISO8601_UTC, "rationale": str,
         "regime_alignment": str, "advisory_only": true
       }],
       "performance_comparison": str,
       "unusual_conditions_detected": bool,
       "unusual_conditions": [str],
       "advisory_only": true,
       "executable_signal": false
     }
   - "explanation": concise factual summary grounded strictly in supplied indicators/features
   - "timestamp": exact ISO-8601 UTC string copied from input.as_of_timestamp
2. NEVER invent, guess, extrapolate, or cite any market price or target absent from input.
3. NEVER express AI confidence as a probability of profitable trading or guarantee returns.
4. Highlight unusual market conditions (volume spikes/droughts, ATR spikes, extreme RSI,
   shock moves, candle gaps) in both unusual_conditions and risk_observations."""


class MarketAnalysisService:
    """Orchestrates validated feature input, LLM caching/validation, and safe fallback."""

    def __init__(
        self,
        *,
        config: AIAnalysisConfig | None = None,
        ai_client: AIAnalysisClient | None = None,
        cache: AnalysisCache | None = None,
        validator: AIResponseValidator | None = None,
        deterministic_analyzer: DeterministicMarketAnalyzer | None = None,
        strategy_config: StrategyV1Config | None = None,
    ) -> None:
        self._config = config or AIAnalysisConfig()
        self._ai_client = ai_client
        self._cache = cache or AnalysisCache(
            ttl_seconds=self._config.cache_ttl_seconds,
            max_entries=self._config.cache_max_entries,
        )
        self._validator = validator or AIResponseValidator(
            price_tolerance_pct=self._config.strict_price_tolerance_pct
        )
        self._deterministic = deterministic_analyzer or DeterministicMarketAnalyzer()
        self._feature_builder = ValidatedFeatureBuilder(strategy_config=strategy_config)

    @property
    def cache(self) -> AnalysisCache:
        """Expose analysis cache for inspection/metrics."""
        return self._cache

    def _effective_model_tag(self) -> str:
        if self._config.provider == "deterministic" or self._ai_client is None:
            return "deterministic-v1"
        return f"{self._config.provider}:{self._ai_client.model_name}"

    async def analyze(self, analysis_input: MarketAnalysisInput) -> MarketAnalysisOutput:
        """Produce validated strict-JSON market analysis with caching and API failure resilience."""
        if not self._config.enabled:
            raise AIProviderError("AI market analysis module is disabled in configuration.")

        model_tag = self._effective_model_tag()
        cache_key = AnalysisCache.build_key(analysis_input, model_tag=model_tag)

        cached = await self._cache.get(cache_key)
        if cached is not None:
            logger.debug(
                "ai_market_analysis_cache_hit",
                symbol=analysis_input.symbol,
                timeframe=analysis_input.timeframe,
                model_tag=model_tag,
            )
            return cached

        if self._config.provider == "deterministic" or self._ai_client is None:
            if (
                self._config.provider == "openai_compatible"
                and self._ai_client is None
                and not self._config.fallback_to_deterministic
            ):
                raise AIProviderError("AI client is unavailable and fallback is disabled.")

            fallback_note = (
                None
                if self._config.provider == "deterministic"
                else "AI client not configured"
            )
            output = self._deterministic.analyze(analysis_input, fallback_reason=fallback_note)
            self._validator.validate_no_invented_prices(output, source_input=analysis_input)
            self._validator.validate_safety_constraints(output)
            if self._config.provider == "deterministic":
                await self._cache.set(cache_key, output)
            return output

        user_payload: dict[str, Any] = analysis_input.model_dump(mode="json")
        try:
            raw_response = await self._ai_client.generate_market_analysis(
                system_prompt=_SYSTEM_PROMPT,
                user_payload=user_payload,
            )
            output = self._validator.validate(raw_response, source_input=analysis_input)
        except (AIProviderError, AIResponseValidationError) as exc:
            logger.warning(
                "ai_market_analysis_provider_or_validation_failed",
                symbol=analysis_input.symbol,
                timeframe=analysis_input.timeframe,
                error=str(exc),
                fallback_enabled=self._config.fallback_to_deterministic,
            )
            if not self._config.fallback_to_deterministic:
                raise
            # Do not cache degraded fallback responses so transient outages recover automatically.
            output = self._deterministic.analyze(
                analysis_input,
                fallback_reason=type(exc).__name__,
            )
            self._validator.validate_no_invented_prices(output, source_input=analysis_input)
            self._validator.validate_safety_constraints(output)
            return output

        await self._cache.set(cache_key, output)
        logger.info(
            "ai_market_analysis_completed",
            symbol=analysis_input.symbol,
            timeframe=analysis_input.timeframe,
            market_regime=output.market_regime.value,
            trend_direction=output.trend_direction.value,
            volatility_level=output.volatility_level.value,
            unusual_conditions=output.strategy_assessment.unusual_conditions_detected,
        )
        return output

    async def analyze_from_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        bars: Sequence[OHLCVBar],
        strategy_signals: Sequence[StrategySignal] = (),
        strategy_comparisons: Sequence[StrategyPerformanceSnapshot] = (),
        now_utc: datetime | None = None,
        lookback_bars: int = 50,
    ) -> MarketAnalysisOutput:
        """Validate closed candles, extract causal features, and execute advisory analysis."""
        analysis_input = self._feature_builder.build(
            symbol=symbol,
            timeframe=timeframe,
            bars=bars,
            strategy_signals=strategy_signals,
            strategy_comparisons=strategy_comparisons,
            now_utc=now_utc,
            lookback_bars=lookback_bars,
        )
        return await self.analyze(analysis_input)

    async def close(self) -> None:
        """Release underlying AI client resources if present."""
        if self._ai_client is not None:
            await self._ai_client.close()
