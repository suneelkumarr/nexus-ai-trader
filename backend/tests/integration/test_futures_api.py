"""Integration tests for Crypto Futures REST endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from nexus.application.futures.broker import FuturesPaperBroker
from nexus.application.futures.funding_service import FuturesFundingService
from nexus.core.config import Settings
from nexus.domain.models import OHLCVBar, TickerQuote
from nexus.infrastructure.db.base import Base
from nexus.infrastructure.db.futures_repository import SqlAlchemyFuturesRepository
from nexus.infrastructure.db.session import DatabaseManager
from nexus.main import create_app


class _MockMarketFeed:
    def __init__(self) -> None:
        self.prices: dict[str, Decimal] = {
            "BTC/USDT": Decimal("60000.00"),
            "ETH/USDT": Decimal("3000.00"),
            "SOL/USDT": Decimal("150.00"),
        }

    async def fetch_ticker(self, symbol: str) -> TickerQuote:
        p = self.prices.get(symbol, Decimal("100.00"))
        return TickerQuote(
            symbol=symbol,
            exchange_id="binance",
            bid=p - Decimal("0.50"),
            ask=p + Decimal("0.50"),
            last=p,
            timestamp=datetime.now(UTC),
        )

    async def fetch_inr_per_usdt(self) -> Decimal:
        return Decimal("85.00")

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "15m", limit: int = 100) -> list[OHLCVBar]:
        return []

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_futures_api_full_flow(tmp_path: Path) -> None:
    db_path = tmp_path / "test_futures_api.db"
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url_override=f"sqlite+aiosqlite:///{db_path.as_posix()}",
    )
    db_manager = DatabaseManager(settings)
    async with db_manager.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    feed = _MockMarketFeed()
    funding = FuturesFundingService()
    futures_repo = SqlAlchemyFuturesRepository(db_manager.session_factory)
    futures_broker = FuturesPaperBroker(
        repository=futures_repo,
        market_data=feed,
        funding_service=funding,
    )

    app = create_app(settings=settings)
    app.state.settings = settings
    app.state.db_manager = db_manager
    app.state.market_data_service = feed
    app.state.market_data_provider = feed
    app.state.futures_broker = futures_broker
    app.state.funding_service = funding

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. GET /api/v1/futures/summary
        resp = await client.get("/api/v1/futures/summary")
        assert resp.status_code == 200
        summary = resp.json()
        assert summary["open_positions_count"] == 0
        assert float(summary["available_cash_inr"]) == 10000.0

        # 2. GET /api/v1/futures/positions
        resp_pos = await client.get("/api/v1/futures/positions")
        assert resp_pos.status_code == 200
        assert resp_pos.json() == []

        # 3. POST /api/v1/futures/orders (Open simulated Long: 0.001 BTC at 2x leverage = ~$25.50 margin * 85 = ~2,168 INR)
        order_req = {
            "symbol": "BTC/USDT",
            "action": "OPEN_LONG",
            "quantity": "0.001",
            "leverage": 2,
        }
        resp_order = await client.post("/api/v1/futures/orders", json=order_req)
        assert resp_order.status_code == 200
        order_res = resp_order.json()
        assert order_res["status"] == "filled"
        pos_id = order_res["position_id"]
        assert pos_id is not None

        # 4. GET /api/v1/futures/positions again -> 1 open position
        resp_pos2 = await client.get("/api/v1/futures/positions")
        assert resp_pos2.status_code == 200
        positions = resp_pos2.json()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "BTC/USDT"
        assert positions[0]["side"] == "LONG"
        assert positions[0]["leverage"] == 2

        # 5. POST /api/v1/futures/orders (Open simulated Short: 0.01 ETH at 3x leverage = ~$10 margin * 85 = ~850 INR)
        short_order_req = {
            "symbol": "ETH/USDT",
            "action": "OPEN_SHORT",
            "quantity": "0.01",
            "leverage": 3,
        }
        resp_short = await client.post("/api/v1/futures/orders", json=short_order_req)
        assert resp_short.status_code == 200
        assert resp_short.json()["status"] == "filled"
        short_pos_id = resp_short.json()["position_id"]

        # 6. Close position via API: POST /api/v1/futures/positions/{pos_id}/close
        resp_close = await client.post(f"/api/v1/futures/positions/{pos_id}/close")
        assert resp_close.status_code == 200
        closed_data = resp_close.json()
        assert closed_data["status"] == "closed"

        # 7. GET /api/v1/futures/funding-rates
        resp_rates = await client.get("/api/v1/futures/funding-rates?symbols=BTC/USDT,ETH/USDT")
        assert resp_rates.status_code == 200
        rates_data = resp_rates.json()
        assert "BTC/USDT" in rates_data
        assert "ETH/USDT" in rates_data

        # 8. POST /api/v1/futures/toggle-auto-trade
        resp_toggle = await client.post("/api/v1/futures/toggle-auto-trade", json={"enabled": True})
        assert resp_toggle.status_code == 200
        assert resp_toggle.json()["auto_trade_enabled"] is True

    await funding.close()
    await db_manager.dispose()

