"""Integration tests for NEXUS paper-trading terminal REST & WebSocket endpoints."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from nexus.api.dependencies import (
    get_candle_repository,
    get_database_manager,
    get_independent_risk_manager,
    get_market_data_provider,
    get_paper_ledger_repository,
    get_persistent_paper_broker,
)
from nexus.application.persistent_paper_broker import PersistentPaperBroker
from nexus.application.risk_manager import IndependentRiskManager
from nexus.core.ai_config import AIAnalysisConfig
from nexus.core.config import Settings
from nexus.core.exceptions import MarketDataUnavailableError
from nexus.domain.models import OHLCVBar, TickerQuote
from nexus.infrastructure.db.base import Base
from nexus.infrastructure.db.candle_repository import SqlAlchemyCandleRepository
from nexus.infrastructure.db.paper_repository import SqlAlchemyPaperRepository
from nexus.infrastructure.db.session import DatabaseManager
from nexus.main import create_app


class _StubMarketFeed:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def fetch_ticker(self, symbol: str) -> TickerQuote:
        if self.fail:
            raise MarketDataUnavailableError(f"Simulated exchange outage for {symbol}")
        prices = {
            "BTC/USDT": Decimal("62000.00"),
            "ETH/USDT": Decimal("3200.00"),
            "SOL/USDT": Decimal("145.00"),
        }
        p = prices.get(symbol, Decimal("100.00"))
        return TickerQuote(
            symbol=symbol,
            exchange_id="binance",
            bid=p - Decimal("0.50"),
            ask=p + Decimal("0.50"),
            last=p,
            timestamp=datetime.now(UTC),
        )

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "15m", limit: int = 100
    ) -> list[OHLCVBar]:
        return []

    async def fetch_inr_per_usdt(self) -> Decimal:
        if self.fail:
            raise MarketDataUnavailableError("FX feed outage")
        return Decimal("84.50")

    async def health_check(self) -> bool:
        return not self.fail

    async def close(self) -> None:
        return None


def _build_closed_bars(symbol: str, count: int) -> list[OHLCVBar]:
    end = datetime.now(UTC) - timedelta(hours=1)
    start = end - timedelta(minutes=15 * count)
    bars: list[OHLCVBar] = []
    price = Decimal("60000.00")
    for idx in range(count):
        ts = start + timedelta(minutes=15 * idx)
        delta = Decimal(str((idx % 7) * 40 - 90))
        open_p = price
        close_p = max(Decimal("1000"), open_p + delta)
        high_p = max(open_p, close_p) + Decimal("35")
        low_p = min(open_p, close_p) - Decimal("35")
        bars.append(
            OHLCVBar(
                symbol=symbol,
                timeframe="15m",
                timestamp=ts,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=Decimal(str(120 + (idx % 5) * 25)),
                is_closed=True,
            )
        )
        price = close_p
    return bars


async def _make_test_app(
    db_url: str, *, feed: _StubMarketFeed
) -> tuple[object, DatabaseManager, SqlAlchemyCandleRepository]:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url_override=db_url,
        ai=AIAnalysisConfig(api_key=SecretStr("top-secret-test-key")),
    )
    db_manager = DatabaseManager(settings)
    async with db_manager.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    paper_repo = SqlAlchemyPaperRepository(db_manager.session_factory)
    candle_repo = SqlAlchemyCandleRepository(db_manager.session_factory)
    risk_manager = IndependentRiskManager(
        allowed_symbols=settings.allowed_symbols,
        risk_config=settings.risk,
        fee_bps=settings.paper_fee_bps,
        slippage_bps=settings.paper_slippage_bps,
    )
    broker = PersistentPaperBroker(
        repository=paper_repo,
        risk_manager=risk_manager,
        market_data=feed,
        initial_capital_inr=settings.initial_capital_inr,
        fee_bps=settings.paper_fee_bps,
        slippage_bps=settings.paper_slippage_bps,
    )

    app = create_app(settings=settings)
    app.state.settings = settings
    app.state.db_manager = db_manager
    app.state.market_data_provider = feed
    app.dependency_overrides[get_database_manager] = lambda: db_manager
    app.dependency_overrides[get_market_data_provider] = lambda: feed
    app.dependency_overrides[get_paper_ledger_repository] = lambda: paper_repo
    app.dependency_overrides[get_candle_repository] = lambda: candle_repo
    app.dependency_overrides[get_independent_risk_manager] = lambda: risk_manager
    app.dependency_overrides[get_persistent_paper_broker] = lambda: broker
    return app, db_manager, candle_repo


@pytest.mark.asyncio
async def test_terminal_snapshot_and_degraded_market_feed(tmp_path: Path) -> None:
    db_path = tmp_path / "snapshot.db"
    live_feed = _StubMarketFeed(fail=False)
    app, db_manager, _ = await _make_test_app(
        f"sqlite+aiosqlite:///{db_path.as_posix()}", feed=live_feed
    )

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/terminal/snapshot")
            assert resp.status_code == 200
            data = resp.json()
            assert data["trading_mode"] == "paper"
            assert data["market_type"] == "spot"
            assert data["live_trading_enabled"] is False
            assert data["portfolio"]["initial_capital_inr"] == 10000.0
            assert data["portfolio"]["quote_status"] == "live"
            assert data["portfolio"]["inr_per_usdt"] == 84.5
            assert len(data["tickers"]) == 3
            assert data["engine_health"]["overall_status"] == "ok"

            # Verify outage degrades cleanly without fabricating market quotes
            live_feed.fail = True
            degraded = await client.get("/api/v1/terminal/snapshot")
            assert degraded.status_code == 200
            d_data = degraded.json()
            assert d_data["portfolio"]["quote_status"] == "unavailable"
            assert d_data["portfolio"]["inr_per_usdt"] is None
            assert d_data["tickers"] == []
            assert d_data["engine_health"]["market_feed_up"] is False
            assert d_data["engine_health"]["overall_status"] == "degraded"
    finally:
        await db_manager.dispose()


@pytest.mark.asyncio
async def test_emergency_stop_and_settings_redaction(tmp_path: Path) -> None:
    db_path = tmp_path / "emergency.db"
    feed = _StubMarketFeed(fail=False)
    app, db_manager, _ = await _make_test_app(
        f"sqlite+aiosqlite:///{db_path.as_posix()}", feed=feed
    )

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            stop_resp = await client.post(
                "/api/v1/terminal/emergency-stop",
                json={"reason": "Operator halt test", "flatten_positions": True},
            )
            assert stop_resp.status_code == 200
            stop_data = stop_resp.json()
            assert stop_data["trading_mode"] == "paper"
            assert stop_data["kill_switch_active"] is True
            assert stop_data["reason"] == "Operator halt test"

            snap = await client.get("/api/v1/terminal/snapshot")
            assert snap.status_code == 200
            assert snap.json()["risk"]["kill_switch_active"] is True
            assert snap.json()["risk"]["kill_switch_reason"] == "Operator halt test"

            reset_resp = await client.post(
                "/api/v1/terminal/reset-kill-switch",
                json={"reason": "Operator test reset"},
            )
            assert reset_resp.status_code == 200
            assert reset_resp.json()["kill_switch_active"] is False

            snap_after = await client.get("/api/v1/terminal/snapshot")
            assert snap_after.status_code == 200
            assert snap_after.json()["risk"]["kill_switch_active"] is False

            settings_resp = await client.get("/api/v1/terminal/settings")
            assert settings_resp.status_code == 200
            s_text = settings_resp.text
            assert "top-secret-test-key" not in s_text
            s_json = settings_resp.json()
            assert s_json["trading_mode"] == "paper"
            assert s_json["live_trading_enabled"] is False
            assert s_json["allow_leverage"] is False
            assert s_json["allow_futures"] is False
            assert s_json["allow_withdrawals"] is False
    finally:
        await db_manager.dispose()


@pytest.mark.asyncio
async def test_terminal_backtest_validation_and_execution(tmp_path: Path) -> None:
    db_path = tmp_path / "backtest.db"
    feed = _StubMarketFeed(fail=False)
    app, db_manager, candle_repo = await _make_test_app(
        f"sqlite+aiosqlite:///{db_path.as_posix()}", feed=feed
    )

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # No stored candles yet -> strict 422 instead of synthetic data
            missing = await client.post(
                "/api/v1/terminal/backtest",
                json={"symbol": "BTC/USDT", "timeframe": "15m", "lookback_bars": 240},
            )
            assert missing.status_code == 422

            await candle_repo.upsert_candles("binance", _build_closed_bars("BTC/USDT", 210))
            ran = await client.post(
                "/api/v1/terminal/backtest",
                json={
                    "symbol": "BTC/USDT",
                    "timeframe": "15m",
                    "maker_fee_bps": 10.0,
                    "taker_fee_bps": 10.0,
                    "spread_bps": 4.0,
                    "slippage_bps": 5.0,
                    "lookback_bars": 210,
                },
            )
            assert ran.status_code == 200
            report = ran.json()
            assert report["symbol"] == "BTC/USDT"
            assert report["out_of_sample_verified"] is True
            assert "train_result" in report
            assert "validation_result" in report
            assert "test_result" in report
            assert "fee_impact" in report["test_result"]["metrics"]
    finally:
        await db_manager.dispose()


@pytest.mark.asyncio
async def test_terminal_websocket_stream_pushes_real_snapshot(tmp_path: Path) -> None:
    db_path = tmp_path / "ws.db"
    feed = _StubMarketFeed(fail=False)
    app, db_manager, _ = await _make_test_app(
        f"sqlite+aiosqlite:///{db_path.as_posix()}", feed=feed
    )

    try:
        with TestClient(app).websocket_connect("/api/v1/ws/stream") as ws:
            frame = ws.receive_json()
            assert frame["trading_mode"] == "paper"
            assert frame["live_trading_enabled"] is False
            assert frame["portfolio"]["initial_capital_inr"] == 10000.0
            assert len(frame["tickers"]) == 3
            ws.send_text("close")
    finally:
        await db_manager.dispose()


@pytest.mark.asyncio
async def test_terminal_candles_series_endpoint(tmp_path: Path) -> None:
    db_path = tmp_path / "candles.db"
    feed = _StubMarketFeed(fail=False)
    app, db_manager, candle_repo = await _make_test_app(
        f"sqlite+aiosqlite:///{db_path.as_posix()}", feed=feed
    )

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/terminal/candles",
                params={"symbol": "BTC/USDT", "timeframe": "15m", "limit": 50},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["symbol"] == "BTC/USDT"
            assert data["timeframe"] == "15m"
            assert data["count"] == 50
            assert len(data["candles"]) == 50
            first_candle = data["candles"][0]
            assert "time" in first_candle
            assert "open" in first_candle
            assert "high" in first_candle
            assert "low" in first_candle
            assert "close" in first_candle
            assert "volume" in first_candle
            assert first_candle["high"] >= first_candle["low"]
    finally:
        await db_manager.dispose()


@pytest.mark.asyncio
async def test_terminal_earnings_breakdown_endpoint(tmp_path: Path) -> None:
    db_path = tmp_path / "earnings.db"
    feed = _StubMarketFeed(fail=False)
    app, db_manager, _ = await _make_test_app(
        f"sqlite+aiosqlite:///{db_path.as_posix()}", feed=feed
    )

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/terminal/earnings-breakdown")
            assert resp.status_code == 200
            data = resp.json()
            assert "execution_mode" in data
            assert "paper_portfolio" in data
            assert "live_binance" in data
            assert data["paper_portfolio"]["initial_capital_inr"] == 10000.0
            assert isinstance(data["paper_portfolio"]["assets"], list)
    finally:
        await db_manager.dispose()

