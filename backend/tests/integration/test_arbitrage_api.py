"""Integration tests for Arbitrage API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from nexus.main import create_app


@pytest.mark.asyncio
async def test_arbitrage_scan_endpoint() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/arbitrage/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_markets" in data
        assert data["total_markets"] >= 50
        assert "markets" in data
        assert len(data["markets"]) >= 50
        assert "triangular_opportunities" in data
        assert "telemetry" in data
        assert data["telemetry"]["system_buffer_verified_pct"] == 99.8
        assert data["telemetry"]["fps"] == 60.0


@pytest.mark.asyncio
async def test_arbitrage_opportunities_endpoint() -> None:
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/v1/arbitrage/opportunities")
        assert resp.status_code == 200
        data = resp.json()
        assert "triangular_opportunities" in data
        assert "synthetic_dislocations" in data
        assert len(data["synthetic_dislocations"]) >= 4

