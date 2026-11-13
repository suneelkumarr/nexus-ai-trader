"""Integration tests for advisory AI market analysis API endpoints."""

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from nexus.api.dependencies import get_candle_repository, get_market_analysis_service
from nexus.application.ai_analysis.features import ValidatedFeatureBuilder
from nexus.application.ai_analysis.service import MarketAnalysisService
from nexus.core.ai_config import AIAnalysisConfig
from nexus.core.config import Settings
from nexus.core.exceptions import AIProviderError
from nexus.domain.enums import MarketRegime, TrendDirection, VolatilityLevel
from nexus.domain.models import OHLCVBar
from nexus.main import create_app


class _InMemoryCandleRepo:
    def __init__(self, bars: list[OHLCVBar]) -> None:
        self._bars = bars

    async def upsert_candles(self, exchange_id: str, bars: Sequence[OHLCVBar]) -> int:
        return 0

    async def get_candles(
        self,
        exchange_id: str,
        symbol: str,
        timeframe: str,
        start_utc: datetime | None = None,
        end_utc: datetime | None = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        matching = [
            bar
            for bar in self._bars
            if bar.symbol == symbol and bar.timeframe == timeframe
        ]
        return matching[-limit:]

    async def get_latest_timestamp(
        self, exchange_id: str, symbol: str, timeframe: str
    ) -> datetime | None:
        return self._bars[-1].timestamp if self._bars else None


class _MockAIClient:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    @property
    def model_name(self) -> str:
        return "mock-ai-analyst"

    async def generate_market_analysis(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
    ) -> str:
        self.calls += 1
        if self.fail:
            raise AIProviderError("Simulated upstream outage")
        ind = user_payload["indicators"]
        hist = user_payload["historical_features"]
        return json.dumps(
            {
                "market_regime": MarketRegime.TRENDING_BULLISH.value,
                "trend_direction": TrendDirection.BULLISH.value,
                "volatility_level": VolatilityLevel.MODERATE.value,
                "risk_observations": [
                    f"Close at {ind['close_usdt']} USDT sits above EMA20 ({ind['ema_fast']})."
                ],
                "strategy_assessment": {
                    "signal_explanations": [],
                    "performance_comparison": "No strategy comparison records provided.",
                    "unusual_conditions_detected": bool(hist["anomaly_flags"]),
                    "unusual_conditions": list(hist["anomaly_flags"]),
                    "advisory_only": True,
                    "executable_signal": False,
                },
                "explanation": (
                    f"{user_payload['symbol']} closed at {ind['close_usdt']} USDT within "
                    f"{hist['range_low_usdt']} to {hist['range_high_usdt']} USDT "
                    f"with RSI {ind['rsi']}."
                ),
                "timestamp": user_payload["as_of_timestamp"],
            }
        )

    async def close(self) -> None:
        return None


def _build_bars(count: int = 65, *, close_last: bool = True) -> list[OHLCVBar]:
    base = datetime(2026, 11, 10, 0, 0, tzinfo=UTC)
    bars: list[OHLCVBar] = []
    price = 3200.0
    for idx in range(count):
        ts = base + timedelta(minutes=15 * idx)
        price += 5.0
        is_closed = True if idx < count - 1 else close_last
        bars.append(
            OHLCVBar(
                symbol="ETH/USDT",
                timeframe="15m",
                timestamp=ts,
                open=Decimal(f"{price - 3.0:.2f}"),
                high=Decimal(f"{price + 6.0:.2f}"),
                low=Decimal(f"{price - 5.0:.2f}"),
                close=Decimal(f"{price:.2f}"),
                volume=Decimal("450.0"),
                is_closed=is_closed,
            )
        )
    return bars


@pytest.mark.asyncio
async def test_analysis_api_strict_json_caching_and_from_candles(
    test_settings: Settings,
) -> None:
    bars = _build_bars(count=65, close_last=True)
    ai_client = _MockAIClient()
    analysis_service = MarketAnalysisService(
        config=AIAnalysisConfig(
            provider="openai_compatible",
            api_key=SecretStr("sk-test"),
            cache_ttl_seconds=300,
        ),
        ai_client=ai_client,
    )
    app = create_app(settings=test_settings)
    app.dependency_overrides[get_candle_repository] = lambda: _InMemoryCandleRepo(bars)
    app.dependency_overrides[get_market_analysis_service] = lambda: analysis_service

    now_utc = bars[-1].timestamp + timedelta(minutes=20)
    analysis_input = ValidatedFeatureBuilder().build(
        symbol="ETH/USDT",
        timeframe="15m",
        bars=bars,
        now_utc=now_utc,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp1 = await client.post(
            "/api/v1/analysis/market",
            json=analysis_input.model_dump(mode="json"),
        )
        assert resp1.status_code == 200
        body = resp1.json()
        assert set(body.keys()) == {
            "market_regime",
            "trend_direction",
            "volatility_level",
            "risk_observations",
            "strategy_assessment",
            "explanation",
            "timestamp",
        }
        assert body["strategy_assessment"]["advisory_only"] is True
        assert body["strategy_assessment"]["executable_signal"] is False
        assert ai_client.calls == 1

        # Repeated identical request hits cache
        resp2 = await client.post(
            "/api/v1/analysis/market",
            json=analysis_input.model_dump(mode="json"),
        )
        assert resp2.status_code == 200
        assert ai_client.calls == 1

        # From-candles endpoint builds validated features from persisted bars
        resp3 = await client.post(
            "/api/v1/analysis/from-candles",
            json={"symbol": "ETH/USDT", "timeframe": "15m", "lookback_bars": 65},
        )
        assert resp3.status_code == 200
        assert set(resp3.json().keys()) == set(body.keys())


@pytest.mark.asyncio
async def test_analysis_api_rejects_unclosed_candles_and_maps_503_when_fallback_disabled(
    test_settings: Settings,
) -> None:
    unclosed_bars = _build_bars(count=65, close_last=False)
    failing_service = MarketAnalysisService(
        config=AIAnalysisConfig(
            provider="openai_compatible",
            api_key=SecretStr("sk-test"),
            fallback_to_deterministic=False,
        ),
        ai_client=_MockAIClient(fail=True),
    )
    app = create_app(settings=test_settings)
    app.dependency_overrides[get_candle_repository] = lambda: _InMemoryCandleRepo(unclosed_bars)
    app.dependency_overrides[get_market_analysis_service] = lambda: failing_service

    closed_bars = _build_bars(count=65, close_last=True)
    valid_input = ValidatedFeatureBuilder().build(
        symbol="ETH/USDT",
        timeframe="15m",
        bars=closed_bars,
        now_utc=closed_bars[-1].timestamp + timedelta(minutes=20),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        unclosed_resp = await client.post(
            "/api/v1/analysis/from-candles",
            json={"symbol": "ETH/USDT", "timeframe": "15m", "lookback_bars": 65},
        )
        assert unclosed_resp.status_code == 422

        outage_resp = await client.post(
            "/api/v1/analysis/market",
            json=valid_input.model_dump(mode="json"),
        )
        assert outage_resp.status_code == 503
