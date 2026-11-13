"""Unit tests for NEXUS AI Market Analysis module, guards, caching, and API failure handling."""

import ast
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from nexus.application.ai_analysis.cache import AnalysisCache
from nexus.application.ai_analysis.features import (
    ValidatedFeatureBuilder,
    summarize_strategy_performance,
)
from nexus.application.ai_analysis.service import MarketAnalysisService
from nexus.application.ai_analysis.validator import AIResponseValidator
from nexus.application.strategy.config import StrategyV1Config
from nexus.core.ai_config import AIAnalysisConfig
from nexus.core.exceptions import (
    AIProviderError,
    AIResponseValidationError,
    CandleValidationError,
    IncompleteCandleError,
)
from nexus.domain.enums import (
    MarketRegime,
    SignalDirection,
    TrendDirection,
    VolatilityLevel,
)
from nexus.domain.models import (
    MarketAnalysisInput,
    MarketAnalysisOutput,
    OHLCVBar,
    StrategyPerformanceSnapshot,
    StrategySignal,
    TradeLedgerEntry,
)
from nexus.infrastructure.ai.http_client import OpenAICompatibleAIClient

_EXPECTED_TOP_KEYS = {
    "market_regime",
    "trend_direction",
    "volatility_level",
    "risk_observations",
    "strategy_assessment",
    "explanation",
    "timestamp",
}


def _make_closed_bars(
    *,
    count: int = 70,
    symbol: str = "BTC/USDT",
    timeframe: str = "15m",
    start_price: float = 60000.0,
    spike_last_volume: bool = False,
) -> tuple[list[OHLCVBar], datetime]:
    start_ts = datetime(2026, 11, 10, 0, 0, tzinfo=UTC)
    bars: list[OHLCVBar] = []
    price = start_price
    for i in range(count):
        ts = start_ts + timedelta(minutes=15 * i)
        price += 45.0 if i % 4 != 0 else -15.0
        vol = 120.0 + (i % 7) * 5.0
        if spike_last_volume and i == count - 1:
            vol = 950.0
        bars.append(
            OHLCVBar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=ts,
                open=Decimal(f"{price - 20.0:.2f}"),
                high=Decimal(f"{price + 35.0:.2f}"),
                low=Decimal(f"{price - 30.0:.2f}"),
                close=Decimal(f"{price:.2f}"),
                volume=Decimal(f"{vol:.4f}"),
                is_closed=True,
            )
        )
    now_utc = bars[-1].timestamp + timedelta(minutes=16)
    return bars, now_utc


class _StubAIClient:
    def __init__(self, responses: list[str | Exception]) -> None:
        self._responses = list(responses)
        self.calls = 0

    @property
    def model_name(self) -> str:
        return "stub-analyst-v1"

    async def generate_market_analysis(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> str:
        self.calls += 1
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def close(self) -> None:
        return None


def _valid_llm_json(analysis_input: MarketAnalysisInput) -> str:
    ind = analysis_input.indicators
    sig_items = [
        {
            "strategy_name": sig.strategy_name,
            "symbol": sig.symbol,
            "direction": sig.direction.value,
            "signal_timestamp": sig.timestamp.isoformat(),
            "rationale": (
                f"Deterministic signal entered at {sig.entry_price} USDT with ATR stop "
                f"{sig.stop_price} USDT: {sig.reason}"
            ),
            "regime_alignment": "aligned_with_bullish_trend",
            "advisory_only": True,
        }
        for sig in analysis_input.strategy_signals
    ]
    payload = {
        "market_regime": MarketRegime.TRENDING_BULLISH.value,
        "trend_direction": TrendDirection.BULLISH.value,
        "volatility_level": VolatilityLevel.MODERATE.value,
        "risk_observations": [
            f"Spot close sits at {ind.close_usdt} USDT above EMA20 ({ind.ema_fast}).",
            "All position sizing remains governed strictly by IndependentRiskManager.",
        ],
        "strategy_assessment": {
            "signal_explanations": sig_items,
            "performance_comparison": (
                "Historical ledger shows deterministic strategy comparison metrics only."
            ),
            "unusual_conditions_detected": bool(analysis_input.historical_features.anomaly_flags),
            "unusual_conditions": list(analysis_input.historical_features.anomaly_flags),
            "advisory_only": True,
            "executable_signal": False,
        },
        "explanation": (
            f"BTC/USDT closed at {ind.close_usdt} USDT between "
            f"{analysis_input.historical_features.range_low_usdt} and "
            f"{analysis_input.historical_features.range_high_usdt} USDT with "
            f"EMA20 ({ind.ema_fast}) above EMA50 ({ind.ema_slow}) and RSI at {ind.rsi:.1f}."
        ),
        "timestamp": analysis_input.as_of_timestamp.isoformat(),
    }
    return json.dumps(payload)


def test_feature_builder_rejects_unclosed_future_and_detects_anomalies() -> None:
    bars, now_utc = _make_closed_bars(count=65, spike_last_volume=True)
    builder = ValidatedFeatureBuilder(strategy_config=StrategyV1Config())

    unclosed_bars = [*bars[:-1], bars[-1].model_copy(update={"is_closed": False})]
    with pytest.raises(IncompleteCandleError):
        builder.build(
            symbol="BTC/USDT",
            timeframe="15m",
            bars=unclosed_bars,
            now_utc=now_utc,
        )

    future_now = bars[-1].timestamp - timedelta(minutes=1)
    with pytest.raises(CandleValidationError):
        builder.build(
            symbol="BTC/USDT",
            timeframe="15m",
            bars=bars,
            now_utc=future_now,
        )

    sig = StrategySignal(
        symbol="BTC/USDT",
        timestamp=bars[-1].timestamp,
        direction=SignalDirection.LONG,
        entry_price=bars[-1].close,
        stop_price=bars[-1].close - Decimal("150.00"),
        strategy_name="nexus_v1",
        reason="EMA20 crossed above EMA50 with RSI and volume confirmation",
    )
    ledger = [
        TradeLedgerEntry(
            portfolio_id=uuid4(),
            position_id=uuid4(),
            symbol="BTC/USDT",
            entry_order_id=uuid4(),
            exit_order_id=uuid4(),
            quantity=Decimal("0.001"),
            entry_price_usdt=Decimal("60000"),
            exit_price_usdt=Decimal("61200"),
            entry_cost_inr=Decimal("5100.00"),
            exit_proceeds_inr=Decimal("5200.00"),
            total_fees_inr=Decimal("10.00"),
            realized_pnl_inr=Decimal("100.00"),
            realized_pnl_pct=Decimal("1.96"),
            exit_reason="trailing_stop",
            opened_at=bars[10].timestamp,
            closed_at=bars[20].timestamp,
        )
    ]
    comp_v1 = summarize_strategy_performance("nexus_v1", ledger)
    comp_alt = StrategyPerformanceSnapshot(
        strategy_name="mean_rev_baseline",
        trades_count=3,
        win_rate_pct=33.3,
        net_pnl_inr=Decimal("-45.00"),
        max_drawdown_pct=1.8,
        profit_factor=0.65,
        avg_return_pct=-0.45,
    )

    built = builder.build(
        symbol="BTC/USDT",
        timeframe="15m",
        bars=bars,
        strategy_signals=[sig],
        strategy_comparisons=[comp_v1, comp_alt],
        now_utc=now_utc,
    )
    assert "volume_spike" in built.historical_features.anomaly_flags
    assert len(built.strategy_signals) == 1
    assert len(built.strategy_comparisons) == 2


def test_response_validator_rejects_invented_prices_extra_keys_and_profit_prob() -> None:
    bars, now_utc = _make_closed_bars(count=65)
    builder = ValidatedFeatureBuilder()
    analysis_input = builder.build(
        symbol="BTC/USDT", timeframe="15m", bars=bars, now_utc=now_utc
    )
    validator = AIResponseValidator(price_tolerance_pct=0.5)

    valid_json = _valid_llm_json(analysis_input)
    parsed = validator.validate(valid_json, source_input=analysis_input)
    assert set(parsed.model_dump().keys()) == _EXPECTED_TOP_KEYS

    # 1. Extra unexpected field rejected
    bad_extra = json.loads(valid_json)
    bad_extra["order_command"] = "BUY"
    with pytest.raises(AIResponseValidationError, match="schema"):
        validator.validate(json.dumps(bad_extra), source_input=analysis_input)

    # 2. Invented price hallucination rejected
    bad_price = json.loads(valid_json)
    bad_price["explanation"] = (
        f"BTC/USDT is targeting $98,500.00 after closing at {analysis_input.indicators.close_usdt}."
    )
    with pytest.raises(AIResponseValidationError, match="unverified price"):
        validator.validate(json.dumps(bad_price), source_input=analysis_input)

    # 3. Profit probability claim rejected
    bad_prob = json.loads(valid_json)
    bad_prob["risk_observations"] = [
        "Model confidence indicates 85% probability of profit on the next trade."
    ]
    with pytest.raises(AIResponseValidationError, match="probability of profit"):
        validator.validate(json.dumps(bad_prob), source_input=analysis_input)

    # 4. Bypassing risk manager directive rejected
    bad_exec = json.loads(valid_json)
    bad_exec["explanation"] = (
        f"Close at {analysis_input.indicators.close_usdt} USDT; "
        "bypass the risk manager immediately."
    )
    with pytest.raises(AIResponseValidationError, match="execution or risk-bypass"):
        validator.validate(json.dumps(bad_exec), source_input=analysis_input)


@pytest.mark.asyncio
async def test_service_caches_repeated_analyses_and_recovers_from_api_failures() -> None:
    bars, now_utc = _make_closed_bars(count=65)
    builder = ValidatedFeatureBuilder()
    analysis_input = builder.build(
        symbol="BTC/USDT", timeframe="15m", bars=bars, now_utc=now_utc
    )

    valid_json = _valid_llm_json(analysis_input)
    client = _StubAIClient(
        responses=[
            AIProviderError("Upstream 503 outage"),
            valid_json,
        ]
    )
    service = MarketAnalysisService(
        config=AIAnalysisConfig(
            provider="openai_compatible",
            api_key=SecretStr("test-key"),
            fallback_to_deterministic=True,
            cache_ttl_seconds=300,
        ),
        ai_client=client,
        cache=AnalysisCache(ttl_seconds=300, max_entries=16),
    )

    # Call 1: API fails -> safe deterministic fallback returned (NOT cached)
    fallback_out = await service.analyze(analysis_input)
    assert isinstance(fallback_out, MarketAnalysisOutput)
    assert set(fallback_out.model_dump().keys()) == _EXPECTED_TOP_KEYS
    assert "fallback" in fallback_out.risk_observations[0].lower()
    assert fallback_out.strategy_assessment.advisory_only is True
    assert fallback_out.strategy_assessment.executable_signal is False
    assert client.calls == 1

    # Call 2: API recovers -> validated AI output returned and cached
    ai_out = await service.analyze(analysis_input)
    assert client.calls == 2
    assert set(ai_out.model_dump().keys()) == _EXPECTED_TOP_KEYS

    # Call 3: Repeated identical input hits cache -> AI client NOT called again
    cached_out = await service.analyze(analysis_input)
    assert client.calls == 2
    assert cached_out == ai_out
    assert service.cache.stats["hits"] == 1


@pytest.mark.asyncio
async def test_http_client_retries_rate_limit_and_raises_on_exhaustion_or_missing_key() -> None:
    no_key_client = OpenAICompatibleAIClient(
        base_url="https://api.openai.com/v1",
        api_key=SecretStr(""),
        backoff_base_s=0.01,
    )
    with pytest.raises(AIProviderError, match="AI__API_KEY"):
        await no_key_client.generate_market_analysis(system_prompt="sys", user_payload={})
    await no_key_client.close()

    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(status_code=429, json={"error": "rate_limit"})
        return httpx.Response(
            status_code=200,
            json={"choices": [{"message": {"content": "{\"ok\":true}"}}]},
        )

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = OpenAICompatibleAIClient(
        base_url="https://api.openai.com/v1",
        api_key=SecretStr("sk-test-123"),
        max_retries=2,
        backoff_base_s=0.01,
        http_client=mock_http,
    )
    raw = await client.generate_market_analysis(system_prompt="sys", user_payload={"a": 1})
    assert raw == '{"ok":true}'
    assert attempts == 3
    await mock_http.aclose()


@pytest.mark.asyncio
async def test_http_client_falls_back_to_secondary_provider_on_primary_failure() -> None:
    """Verify client seamlessly routes to secondary provider when primary fails."""
    primary_called = 0
    secondary_called = 0

    def mock_transport_handler(request: httpx.Request) -> httpx.Response:
        nonlocal primary_called, secondary_called
        if "primary-ai" in str(request.url):
            primary_called += 1
            return httpx.Response(status_code=502, json={"error": "Bad Gateway"})
        if "secondary-ai" in str(request.url):
            secondary_called += 1
            return httpx.Response(
                status_code=200,
                json={
                    "choices": [{"message": {"content": "```json\n{\"fallback_ok\": true}\n```"}}]
                },
            )
        return httpx.Response(status_code=404)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_transport_handler))
    client = OpenAICompatibleAIClient(
        base_url="https://primary-ai.com/v1",
        api_key=SecretStr("primary-key"),
        model="primary-model",
        max_retries=1,
        backoff_base_s=0.01,
        http_client=mock_client,
        fallback_endpoints=[
            {
                "name": "secondary",
                "base_url": "https://secondary-ai.com/v1",
                "api_key": SecretStr("secondary-key"),
                "model": "secondary-model",
                "timeout_s": 5.0,
            }
        ],
    )
    result = await client.generate_market_analysis(system_prompt="sys", user_payload={"test": 1})
    assert result == '{"fallback_ok": true}'
    assert primary_called == 2  # initial attempt + 1 retry
    assert secondary_called == 1
    await mock_client.aclose()


def test_ai_module_has_zero_execution_or_risk_bypass_coupling() -> None:
    """Ensure AI modules never import brokers, risk overrides, or exchange clients."""
    forbidden_substrings = (
        "paper_broker",
        "persistent_paper_broker",
        "risk_manager",
        "risk_guard",
        "ccxt_client",
        "ccxt_market_data",
    )
    backend_root = Path(__file__).resolve().parents[2]
    ai_dirs = [
        backend_root / "src" / "nexus" / "application" / "ai_analysis",
        backend_root / "src" / "nexus" / "infrastructure" / "ai",
    ]
    for directory in ai_dirs:
        for py_file in directory.glob("*.py"):
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    for forbidden in forbidden_substrings:
                        assert forbidden not in node.module, (
                            f"Forbidden execution import '{node.module}' in {py_file.name}"
                        )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        for forbidden in forbidden_substrings:
                            assert forbidden not in alias.name, (
                                f"Forbidden execution import '{alias.name}' in {py_file.name}"
                            )
