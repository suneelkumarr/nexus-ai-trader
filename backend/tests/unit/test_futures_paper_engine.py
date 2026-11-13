"""Unit tests for Crypto Futures Paper Trading Simulation, Risk Calculator, and Broker."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from nexus.application.futures.broker import FuturesPaperBroker
from nexus.application.futures.calculator import FuturesRiskCalculator
from nexus.application.futures.funding_service import FuturesFundingService
from nexus.core.config import Settings
from nexus.domain.futures import (
    FuturesOrderAction,
    FuturesOrderRequest,
    FuturesOrderStatus,
    FuturesPositionStatus,
    FuturesSide,
)
from nexus.domain.models import OHLCVBar, TickerQuote
from nexus.infrastructure.db.base import Base
from nexus.infrastructure.db.futures_repository import SqlAlchemyFuturesRepository
from nexus.infrastructure.db.session import DatabaseManager


class _MockMarketData:
    def __init__(self, inr_rate: Decimal = Decimal("85.00")) -> None:
        self.prices: dict[str, Decimal] = {
            "BTC/USDT": Decimal("50000.00"),
            "ETH/USDT": Decimal("3000.00"),
        }
        self.inr_rate = inr_rate

    async def fetch_ticker(self, symbol: str) -> TickerQuote:
        price = self.prices.get(symbol, Decimal("100.00"))
        return TickerQuote(
            symbol=symbol,
            exchange_id="binance",
            bid=price - Decimal("1.00"),
            ask=price + Decimal("1.00"),
            last=price,
            timestamp=datetime.now(UTC),
        )

    async def fetch_inr_per_usdt(self) -> Decimal:
        return self.inr_rate

    async def fetch_ohlcv(self, symbol: str, timeframe: str = "15m", limit: int = 100) -> list[OHLCVBar]:
        return []

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        pass


def test_futures_risk_calculator_margin() -> None:
    calc = FuturesRiskCalculator()

    # 1 BTC at $50,000 at 2x leverage -> $25,000 margin * 85 INR/USD = 2,125,000 INR
    margin = calc.compute_initial_margin(
        entry_price=Decimal("50000.00"),
        quantity=Decimal("1.0"),
        leverage=2,
        inr_rate=Decimal("85.00"),
    )
    assert margin == Decimal("2125000.00")

    # 0.01 BTC at $50,000 at 5x leverage -> $100 margin * 85 = 8,500 INR
    margin_5x = calc.compute_initial_margin(
        entry_price=Decimal("50000.00"),
        quantity=Decimal("0.01"),
        leverage=5,
        inr_rate=Decimal("85.00"),
    )
    assert margin_5x == Decimal("8500.00")

    # Invalid leverage (< 1 or > 5) raises ValueError
    with pytest.raises(ValueError, match="Leverage must be between 1 and 5"):
        calc.compute_initial_margin(
            entry_price=Decimal("50000.00"),
            quantity=Decimal("1.0"),
            leverage=10,
            inr_rate=Decimal("85.00"),
        )


def test_futures_risk_calculator_liquidation_price() -> None:
    calc = FuturesRiskCalculator()

    # Long at 2x leverage (inv_lev = 0.5, mmr = 0.005) -> Factor = 1 - 0.5 + 0.005 = 0.505
    # Liq price = 50,000 * 0.505 = 25,250
    liq_long_2x = calc.compute_liquidation_price(
        entry_price=Decimal("50000.00"),
        side=FuturesSide.LONG,
        leverage=2,
    )
    assert liq_long_2x == Decimal("25250.00000000")

    # Short at 2x leverage -> Factor = 1 + 0.5 - 0.005 = 1.495
    # Liq price = 50,000 * 1.495 = 74,750
    liq_short_2x = calc.compute_liquidation_price(
        entry_price=Decimal("50000.00"),
        side=FuturesSide.SHORT,
        leverage=2,
    )
    assert liq_short_2x == Decimal("74750.00000000")

    # Short at 5x leverage -> Factor = 1 + 0.2 - 0.005 = 1.195
    # Liq price = 50,000 * 1.195 = 59,750
    liq_short_5x = calc.compute_liquidation_price(
        entry_price=Decimal("50000.00"),
        side=FuturesSide.SHORT,
        leverage=5,
    )
    assert liq_short_5x == Decimal("59750.00000000")


def test_futures_risk_calculator_pnl_and_roe() -> None:
    calc = FuturesRiskCalculator()
    margin_inr = Decimal("850.00")
    inr_rate = Decimal("85.00")

    # Long: Entry $50,000, Mark $55,000 (+10%), Size 0.01 BTC -> +$50 USD * 85 = +4,250 INR
    usd_pnl, inr_pnl, roe = calc.compute_pnl(
        entry_price=Decimal("50000.00"),
        mark_price=Decimal("55000.00"),
        quantity=Decimal("0.01"),
        side=FuturesSide.LONG,
        initial_margin_inr=margin_inr,
        inr_rate=inr_rate,
    )
    assert usd_pnl == Decimal("50.00")
    assert inr_pnl == Decimal("4250.00")
    assert roe == Decimal("500.00")  # 5x leverage -> 10% move = 500% ROE

    # Short: Entry $50,000, Mark $45,000 (-10%), Size 0.01 BTC -> +$50 USD * 85 = +4,250 INR
    usd_pnl_s, inr_pnl_s, roe_s = calc.compute_pnl(
        entry_price=Decimal("50000.00"),
        mark_price=Decimal("45000.00"),
        quantity=Decimal("0.01"),
        side=FuturesSide.SHORT,
        initial_margin_inr=margin_inr,
        inr_rate=inr_rate,
    )
    assert usd_pnl_s == Decimal("50.00")
    assert inr_pnl_s == Decimal("4250.00")
    assert roe_s == Decimal("500.00")


@pytest.mark.asyncio
async def test_futures_broker_lifecycle(tmp_path: Path) -> None:
    db_path = tmp_path / "test_futures.db"
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url_override=f"sqlite+aiosqlite:///{db_path.as_posix()}",
    )
    db = DatabaseManager(settings)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    repo = SqlAlchemyFuturesRepository(db.session_factory)
    feed = _MockMarketData(inr_rate=Decimal("85.00"))
    funding = FuturesFundingService()
    broker = FuturesPaperBroker(repository=repo, market_data=feed, funding_service=funding)

    try:
        # 1. Check Initial Summary
        summary = await broker.get_account_summary()
        assert summary.open_positions_count == 0
        assert summary.available_cash_inr == Decimal("10000.00")

        # 2. Open Simulated Long Position (0.01 BTC at 2x leverage = $250 margin * 85 = 21,250 INR) -> rejected due to cash
        res_fail = await broker.submit_order(
            FuturesOrderRequest(
                symbol="BTC/USDT",
                action=FuturesOrderAction.OPEN_LONG,
                quantity=Decimal("0.01"),
                leverage=2,
            )
        )
        assert res_fail.status == FuturesOrderStatus.REJECTED
        assert "Insufficient balance" in (res_fail.rejection_reason or "")

        # 3. Open Small Long Position (0.002 BTC at 2x leverage = $50 margin * 85 = 4,250 INR)
        res_long = await broker.submit_order(
            FuturesOrderRequest(
                symbol="BTC/USDT",
                action=FuturesOrderAction.OPEN_LONG,
                quantity=Decimal("0.002"),
                leverage=2,
            )
        )
        assert res_long.status == FuturesOrderStatus.FILLED
        assert res_long.position_id is not None

        # Cash balance reduced
        summary_after_open = await broker.get_account_summary()
        assert summary_after_open.open_positions_count == 1
        assert summary_after_open.available_cash_inr < Decimal("10000.00")

        # 4. Check Open Positions
        open_pos = await broker.get_open_positions()
        assert len(open_pos) == 1
        assert open_pos[0].side == FuturesSide.LONG
        assert open_pos[0].symbol == "BTC/USDT"
        assert open_pos[0].leverage == 2

        # 5. Open Simulated Short Position (0.001 ETH at $3,000 at 3x leverage = $1 margin * 85 = 85 INR)
        res_short = await broker.submit_order(
            FuturesOrderRequest(
                symbol="ETH/USDT",
                action=FuturesOrderAction.OPEN_SHORT,
                quantity=Decimal("0.001"),
                leverage=3,
            )
        )
        assert res_short.status == FuturesOrderStatus.FILLED
        assert res_short.position_id is not None

        open_pos_2 = await broker.get_open_positions()
        assert len(open_pos_2) == 2

        # 6. Close Short Position
        feed.prices["ETH/USDT"] = Decimal("2900.00")  # Price dropped -> Short is in profit!
        closed = await broker.close_position_by_id(res_short.position_id, reason="Test close in profit")
        assert closed.status == FuturesPositionStatus.CLOSED
        assert closed.realized_pnl_inr > Decimal("0")

        # 7. Check Summary After Close
        summary_after_close = await broker.get_account_summary()
        assert summary_after_close.open_positions_count == 1
        assert summary_after_close.closed_positions_count == 1
        assert summary_after_close.win_rate_pct == Decimal("100.00")
    finally:
        await funding.close()
        await db.dispose()
