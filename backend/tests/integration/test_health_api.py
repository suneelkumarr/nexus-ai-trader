"""Integration tests for FastAPI health, liveness, and readiness endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from nexus.api.dependencies import get_database_manager, get_market_data_provider
from nexus.core.config import Settings
from nexus.main import create_app


class _HealthyDB:
    async def check_health(self) -> tuple[bool, str | None]:
        return True, None


class _DownDB:
    async def check_health(self) -> tuple[bool, str | None]:
        return False, "connection refused"


class _HealthyMarketFeed:
    async def health_check(self) -> bool:
        return True


class _DownMarketFeed:
    async def health_check(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_health_endpoints_when_dependencies_are_healthy(test_settings: Settings) -> None:
    app = create_app(settings=test_settings)
    app.dependency_overrides[get_database_manager] = lambda: _HealthyDB()
    app.dependency_overrides[get_market_data_provider] = lambda: _HealthyMarketFeed()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        live = await client.get("/api/v1/health/live")
        assert live.status_code == 200
        assert live.json()["status"] == "alive"
        assert "X-Request-ID" in live.headers

        ready = await client.get("/api/v1/health/ready")
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"

        summary = await client.get("/api/v1/health")
        assert summary.status_code == 200
        body = summary.json()
        assert body["status"] == "ok"
        assert body["trading_mode"] == "paper"
        assert body["market_type"] == "spot"
        assert body["live_trading_enabled"] is False
        assert body["initial_capital_inr"] == 10000.0
        assert body["allowed_symbols"] == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


@pytest.mark.asyncio
async def test_readiness_returns_503_when_database_is_down(test_settings: Settings) -> None:
    app = create_app(settings=test_settings)
    app.dependency_overrides[get_database_manager] = lambda: _DownDB()
    app.dependency_overrides[get_market_data_provider] = lambda: _DownMarketFeed()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ready = await client.get("/api/v1/health/ready")
        assert ready.status_code == 503
        assert ready.json()["status"] == "not_ready"

        summary = await client.get("/api/v1/health")
        assert summary.status_code == 200
        assert summary.json()["status"] == "degraded"
        assert summary.json()["checks"]["database"]["status"] == "down"
        assert summary.json()["checks"]["market_feed"]["status"] == "down"

