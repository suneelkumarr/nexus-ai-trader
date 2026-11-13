"""Integration tests for PersistentPaperBroker, ledger, restart, and kill switch."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from nexus.application.persistent_paper_broker import PersistentPaperBroker
from nexus.application.risk_manager import IndependentRiskManager
from nexus.core.config import Settings
from nexus.core.exceptions import MarketDataUnavailableError
from nexus.domain.enums import OrderSide, OrderStatus, SignalDirection
from nexus.domain.models import OHLCVBar, PaperOrderRequest, StrategySignal, TickerQuote
from nexus.infrastructure.db.base import Base
from nexus.infrastructure.db.paper_repository import SqlAlchemyPaperRepository
from nexus.infrastructure.db.session import DatabaseManager


class _PublicOnlyQuoteFeed:
    """Strict public-only market data stub (no private trading methods exist)."""

    def __init__(self, *, fail_ticker: bool = False, sol_price: str = "100.00") -> None:
        self.fail_ticker = fail_ticker
        self.sol_price = Decimal(sol_price)

    async def fetch_ticker(self, symbol: str) -> TickerQuote:
        if self.fail_ticker:
            raise MarketDataUnavailableError("Simulated exchange API outage")
        p = self.sol_price if symbol == "SOL/USDT" else Decimal("3000.00")
        return TickerQuote(
            symbol=symbol,
            exchange_id="binance",
            bid=p - Decimal("0.10"),
            ask=p + Decimal("0.10"),
            last=p,
            timestamp=datetime.now(UTC),
        )

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "15m", limit: int = 100
    ) -> list[OHLCVBar]:
        return []

    async def fetch_inr_per_usdt(self) -> Decimal:
        if self.fail_ticker:
            raise MarketDataUnavailableError("FX feed outage")
        return Decimal("85.00")

    async def health_check(self) -> bool:
        return not self.fail_ticker

    async def close(self) -> None:
        return None


async def _setup_broker(
    db_url: str, feed: _PublicOnlyQuoteFeed
) -> tuple[DatabaseManager, SqlAlchemyPaperRepository, PersistentPaperBroker]:
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url_override=db_url,
    )
    db = DatabaseManager(settings)
    async with db.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    repo = SqlAlchemyPaperRepository(db.session_factory)
    risk = IndependentRiskManager(
        allowed_symbols=settings.allowed_symbols,
        risk_config=settings.risk,
        fee_bps=settings.paper_fee_bps,
        slippage_bps=settings.paper_slippage_bps,
    )
    broker = PersistentPaperBroker(
        repository=repo,
        risk_manager=risk,
        market_data=feed,
        initial_capital_inr=settings.initial_capital_inr,
        fee_bps=settings.paper_fee_bps,
        slippage_bps=settings.paper_slippage_bps,
    )
    return db, repo, broker


@pytest.mark.asyncio
async def test_duplicate_orders_and_api_failure_handled_cleanly() -> None:
    feed = _PublicOnlyQuoteFeed(sol_price="100.00")
    db, repo, broker = await _setup_broker("sqlite+aiosqlite:///:memory:", feed)
    portfolio = await repo.get_or_create_portfolio()

    req = PaperOrderRequest(
        portfolio_id=portfolio.id,
        symbol="SOL/USDT",
        side=OrderSide.BUY,
        quantity=Decimal("0.1"),
        stop_price_usdt=Decimal("90.00"),
        client_order_id="dup-order-001",
    )
    first = await broker.submit_order(req)
    assert first.status == OrderStatus.FILLED

    # Exact duplicate client_order_id must be rejected without touching balance
    second = await broker.submit_order(req)
    assert second.status == OrderStatus.REJECTED
    assert "duplicate" in (second.rejection_reason or "").lower()
    assert len(await repo.get_open_positions(portfolio.id)) == 1

    # Market API failure must reject cleanly and never mutate portfolio or create fake fills
    feed.fail_ticker = True
    cash_before = (await repo.get_or_create_portfolio(portfolio.id)).cash_balance_inr
    failed = await broker.submit_order(
        PaperOrderRequest(
            portfolio_id=portfolio.id,
            symbol="ETH/USDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.005"),
            client_order_id="api-fail-001",
        )
    )
    assert failed.status == OrderStatus.REJECTED
    assert "market data unavailable" in (failed.rejection_reason or "").lower()
    assert (await repo.get_or_create_portfolio(portfolio.id)).cash_balance_inr == cash_before

    await db.dispose()


@pytest.mark.asyncio
async def test_pnl_tracking_trailing_stop_and_persistent_ledger() -> None:
    feed = _PublicOnlyQuoteFeed(sol_price="100.00")
    db, repo, broker = await _setup_broker("sqlite+aiosqlite:///:memory:", feed)
    portfolio = await repo.get_or_create_portfolio()

    sig = StrategySignal(
        symbol="SOL/USDT",
        timestamp=datetime(2026, 11, 12, 10, 0, tzinfo=UTC),
        direction=SignalDirection.LONG,
        entry_price=Decimal("100.10"),
        stop_price=Decimal("95.00"),
        strategy_name="nexus_ema_rsi_atr_vol_v1",
        reason="Test entry",
    )
    entry_res = await broker.execute_strategy_signal(
        portfolio.id, sig, atr_value=Decimal("2.0")
    )
    assert entry_res.status == OrderStatus.FILLED

    # Price rallies to 112 -> unrealized P&L positive and trailing stop ratchets upward
    feed.sol_price = Decimal("112.00")
    await broker.process_stop_and_trailing_exits(
        portfolio.id, atr_by_symbol={"SOL/USDT": Decimal("2.0")}
    )
    pnl_mid = await broker.compute_pnl_summary(portfolio.id)
    assert pnl_mid.open_positions_count == 1
    assert pnl_mid.unrealized_pnl_inr > Decimal("0")

    positions = await repo.get_open_positions(portfolio.id)
    assert positions[0].trailing_stop_price_usdt > positions[0].initial_stop_price_usdt

    # Pullback hits ratcheted trailing stop -> position closes and writes trade_ledger
    feed.sol_price = positions[0].trailing_stop_price_usdt - Decimal("0.50")
    exit_results = await broker.process_stop_and_trailing_exits(portfolio.id)
    assert len(exit_results) == 1
    assert exit_results[0].status == OrderStatus.FILLED

    ledger = await repo.list_trade_ledger(portfolio.id)
    assert len(ledger) == 1
    assert ledger[0].realized_pnl_inr > Decimal("0")
    assert ledger[0].total_fees_inr > Decimal("0")

    pnl_after = await broker.compute_pnl_summary(portfolio.id)
    assert pnl_after.open_positions_count == 0
    assert pnl_after.realized_pnl_inr == ledger[0].realized_pnl_inr
    assert pnl_after.unrealized_pnl_inr == Decimal("0")

    await db.dispose()


@pytest.mark.asyncio
async def test_restart_recovery_reconciliation_and_emergency_kill_switch(
    tmp_path: Path,
) -> None:
    db_file = tmp_path / "nexus_restart.db"
    db_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"

    # --- Process Session 1: open position and persist to disk ---
    feed1 = _PublicOnlyQuoteFeed(sol_price="100.00")
    db1, repo1, broker1 = await _setup_broker(db_url, feed1)
    p1 = await repo1.get_or_create_portfolio()

    res = await broker1.submit_order(
        PaperOrderRequest(
            portfolio_id=p1.id,
            symbol="SOL/USDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.2"),
            stop_price_usdt=Decimal("90.00"),
            client_order_id="persist-pos-1",
        ),
        now_utc=datetime(2026, 11, 12, 12, 0, tzinfo=UTC),
    )
    assert res.status == OrderStatus.FILLED
    await db1.dispose()

    # --- Process Session 2 (Simulated Restart on next UTC day) ---
    feed2 = _PublicOnlyQuoteFeed(sol_price="105.00")
    db2, repo2, broker2 = await _setup_broker(db_url, feed2)

    report = await broker2.reconcile_on_startup(
        p1.id, now_utc=datetime(2026, 11, 13, 1, 0, tzinfo=UTC)
    )
    assert report.reconciled_positions == 1
    assert report.daily_rolled_over is True
    assert report.discrepancies == []

    # Verify open position survived restart
    restored_positions = await repo2.get_open_positions(p1.id)
    assert len(restored_positions) == 1
    assert restored_positions[0].quantity == Decimal("0.2")

    # Emergency kill switch flattens open positions and persists halt across restarts
    kill_results = await broker2.activate_kill_switch(
        p1.id, reason="Operator emergency shutdown", flatten_positions=True
    )
    assert len(kill_results) == 1
    assert kill_results[0].status == OrderStatus.FILLED
    assert len(await repo2.get_open_positions(p1.id)) == 0
    await db2.dispose()

    # --- Process Session 3: kill switch remains active after restart and blocks entries ---
    feed3 = _PublicOnlyQuoteFeed(sol_price="105.00")
    db3, _repo3, broker3 = await _setup_broker(db_url, feed3)
    blocked = await broker3.submit_order(
        PaperOrderRequest(
            portfolio_id=p1.id,
            symbol="ETH/USDT",
            side=OrderSide.BUY,
            quantity=Decimal("0.005"),
            stop_price_usdt=Decimal("2900"),
            client_order_id="post-kill-entry",
        )
    )
    assert blocked.status == OrderStatus.REJECTED
    assert "kill switch" in (blocked.rejection_reason or "").lower()
    await db3.dispose()
