"""PostgreSQL / SQLAlchemy repository for paper portfolio, orders, positions, and ledger."""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from nexus.domain.enums import MarketType, OrderSide, OrderStatus, OrderType, TradingMode
from nexus.domain.models import (
    AssetHolding,
    OpenPaperPosition,
    PaperFill,
    PaperOrderRequest,
    PaperOrderResult,
    PortfolioState,
    RiskState,
    TradeLedgerEntry,
)
from nexus.infrastructure.db.models import (
    PaperFillORM,
    PaperOrderORM,
    PaperPositionORM,
    PortfolioBalanceORM,
    PortfolioORM,
    RiskStateORM,
    TradeLedgerORM,
)


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def _opt_utc(dt: datetime | None) -> datetime | None:
    return _utc(dt) if dt is not None else None


class SqlAlchemyPaperRepository:
    """Async SQLAlchemy persistence for paper broker, risk state, and trade ledger."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def get_or_create_portfolio(
        self,
        portfolio_id: UUID | None = None,
        *,
        initial_capital_inr: Decimal = Decimal("10000.00"),
    ) -> PortfolioState:
        """Load portfolio and spot balances or initialize default INR 10,000 portfolio."""
        async with self._session_factory() as session:
            if portfolio_id is not None:
                stmt = (
                    select(PortfolioORM)
                    .options(selectinload(PortfolioORM.balances))
                    .where(PortfolioORM.id == portfolio_id)
                )
            else:
                stmt = (
                    select(PortfolioORM)
                    .options(selectinload(PortfolioORM.balances))
                    .where(PortfolioORM.name == "nexus-default-paper")
                )
            row = (await session.execute(stmt)).scalar_one_or_none()

            if row is None:
                row = PortfolioORM(
                    id=portfolio_id if portfolio_id is not None else None,
                    name=(
                        f"nexus-paper-{portfolio_id}"
                        if portfolio_id is not None
                        else "nexus-default-paper"
                    ),
                    trading_mode="paper",
                    market_type="spot",
                    base_currency="INR",
                    initial_capital_inr=initial_capital_inr,
                    cash_balance_inr=initial_capital_inr,
                )
                session.add(row)
                await session.commit()
                await session.refresh(row, attribute_names=["balances"])

            holdings = {
                b.asset: AssetHolding(
                    asset=b.asset,
                    free_qty=b.free_qty,
                    locked_qty=b.locked_qty,
                    avg_entry_price_usdt=b.avg_entry_price_usdt,
                )
                for b in row.balances
            }
            return PortfolioState(
                id=row.id,
                name=row.name,
                trading_mode=TradingMode(row.trading_mode),
                market_type=MarketType(row.market_type),
                base_currency=row.base_currency,
                initial_capital_inr=row.initial_capital_inr,
                cash_balance_inr=row.cash_balance_inr,
                holdings=holdings,
                created_at=_utc(row.created_at),
            )

    async def save_portfolio(self, portfolio: PortfolioState) -> None:
        """Persist updated portfolio cash balance and per-asset spot holdings."""
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(PortfolioORM)
                    .options(selectinload(PortfolioORM.balances))
                    .where(PortfolioORM.id == portfolio.id)
                )
            ).scalar_one()
            row.cash_balance_inr = portfolio.cash_balance_inr

            existing_by_asset = {b.asset: b for b in row.balances}
            for asset, holding in portfolio.holdings.items():
                bal = existing_by_asset.get(asset)
                if bal is None:
                    session.add(
                        PortfolioBalanceORM(
                            portfolio_id=portfolio.id,
                            asset=asset,
                            free_qty=holding.free_qty,
                            locked_qty=holding.locked_qty,
                            avg_entry_price_usdt=holding.avg_entry_price_usdt,
                        )
                    )
                else:
                    bal.free_qty = holding.free_qty
                    bal.locked_qty = holding.locked_qty
                    bal.avg_entry_price_usdt = holding.avg_entry_price_usdt
            await session.commit()

    async def get_or_create_risk_state(
        self,
        portfolio_id: UUID,
        *,
        initial_capital_inr: Decimal = Decimal("10000.00"),
    ) -> RiskState:
        """Load persisted risk metrics and kill-switch state or create initial row."""
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(RiskStateORM).where(RiskStateORM.portfolio_id == portfolio_id)
                )
            ).scalar_one_or_none()
            if row is None:
                row = RiskStateORM(
                    portfolio_id=portfolio_id,
                    trading_date_utc=datetime.now(UTC).date(),
                    daily_starting_equity_inr=initial_capital_inr,
                    peak_equity_inr=initial_capital_inr,
                    daily_entries_count=0,
                    daily_realized_pnl_inr=Decimal("0"),
                    total_realized_pnl_inr=Decimal("0"),
                    kill_switch_active=False,
                )
                session.add(row)
                await session.commit()

            return RiskState(
                portfolio_id=row.portfolio_id,
                trading_date_utc=row.trading_date_utc,
                daily_starting_equity_inr=row.daily_starting_equity_inr,
                peak_equity_inr=row.peak_equity_inr,
                daily_entries_count=row.daily_entries_count,
                daily_realized_pnl_inr=row.daily_realized_pnl_inr,
                total_realized_pnl_inr=row.total_realized_pnl_inr,
                kill_switch_active=row.kill_switch_active,
                kill_switch_reason=row.kill_switch_reason,
                kill_switch_triggered_at=_opt_utc(row.kill_switch_triggered_at),
            )

    async def save_risk_state(self, risk_state: RiskState) -> None:
        """Persist updated daily risk counters, peak equity, and kill-switch state."""
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(RiskStateORM).where(
                        RiskStateORM.portfolio_id == risk_state.portfolio_id
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                row = RiskStateORM(portfolio_id=risk_state.portfolio_id)
                session.add(row)

            row.trading_date_utc = risk_state.trading_date_utc
            row.daily_starting_equity_inr = risk_state.daily_starting_equity_inr
            row.peak_equity_inr = risk_state.peak_equity_inr
            row.daily_entries_count = risk_state.daily_entries_count
            row.daily_realized_pnl_inr = risk_state.daily_realized_pnl_inr
            row.total_realized_pnl_inr = risk_state.total_realized_pnl_inr
            row.kill_switch_active = risk_state.kill_switch_active
            row.kill_switch_reason = risk_state.kill_switch_reason
            row.kill_switch_triggered_at = risk_state.kill_switch_triggered_at
            await session.commit()

    async def find_order_by_client_id(
        self, portfolio_id: UUID, client_order_id: str
    ) -> PaperOrderResult | None:
        """Return prior order result if client_order_id was already recorded."""
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(PaperOrderORM)
                    .options(selectinload(PaperOrderORM.fills))
                    .where(
                        PaperOrderORM.portfolio_id == portfolio_id,
                        PaperOrderORM.client_order_id == client_order_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                return None

            fill_obj: PaperFill | None = None
            if row.fills:
                f = row.fills[0]
                fill_obj = PaperFill(
                    id=f.id,
                    order_id=f.order_id,
                    symbol=f.symbol,
                    side=OrderSide(f.side),
                    executed_qty=f.executed_qty,
                    executed_price_usdt=f.executed_price_usdt,
                    fee_usdt=f.fee_usdt,
                    inr_per_usdt_rate=f.inr_per_usdt_rate,
                    total_inr=f.total_inr,
                    slippage_bps=f.slippage_bps,
                    executed_at=_utc(f.executed_at),
                )
            return PaperOrderResult(
                order_id=row.id,
                portfolio_id=row.portfolio_id,
                symbol=row.symbol,
                side=OrderSide(row.side),
                order_type=OrderType(row.order_type),
                status=OrderStatus(row.status),
                requested_qty=row.quantity,
                fill=fill_obj,
                rejection_reason=row.rejection_reason,
                created_at=_utc(row.created_at),
            )

    async def find_duplicate_signal_order(
        self, portfolio_id: UUID, symbol: str, side: str, strategy_name: str
    ) -> PaperOrderResult | None:
        """Lookup most recent filled/pending order matching symbol/side/strategy."""
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(PaperOrderORM)
                    .options(selectinload(PaperOrderORM.fills))
                    .where(
                        PaperOrderORM.portfolio_id == portfolio_id,
                        PaperOrderORM.symbol == symbol.strip().upper(),
                        PaperOrderORM.side == side.strip().lower(),
                        PaperOrderORM.strategy_name == strategy_name,
                        PaperOrderORM.status.in_(
                            [OrderStatus.PENDING.value, OrderStatus.FILLED.value]
                        ),
                    )
                    .order_by(PaperOrderORM.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if row is None:
                return None

            fill_obj: PaperFill | None = None
            if row.fills:
                f = row.fills[0]
                fill_obj = PaperFill(
                    id=f.id,
                    order_id=f.order_id,
                    symbol=f.symbol,
                    side=OrderSide(f.side),
                    executed_qty=f.executed_qty,
                    executed_price_usdt=f.executed_price_usdt,
                    fee_usdt=f.fee_usdt,
                    inr_per_usdt_rate=f.inr_per_usdt_rate,
                    total_inr=f.total_inr,
                    slippage_bps=f.slippage_bps,
                    executed_at=_utc(f.executed_at),
                )
            return PaperOrderResult(
                order_id=row.id,
                portfolio_id=row.portfolio_id,
                symbol=row.symbol,
                side=OrderSide(row.side),
                order_type=OrderType(row.order_type),
                status=OrderStatus(row.status),
                requested_qty=row.quantity,
                fill=fill_obj,
                rejection_reason=row.rejection_reason,
                created_at=_utc(row.created_at),
            )

    async def commit_order_settlement(
        self,
        *,
        request: PaperOrderRequest,
        result: PaperOrderResult,
        fill: PaperFill,
        portfolio: PortfolioState,
        position: OpenPaperPosition,
        risk_state: RiskState,
        ledger_entry: TradeLedgerEntry | None = None,
    ) -> None:
        """Atomically persist order, fill, portfolio balances, position, ledger, and risk state."""
        async with self._session_factory() as session, session.begin():
            dialect_name = session.bind.dialect.name if session.bind is not None else ""
            lock_rows = dialect_name != "sqlite"

            order_orm = PaperOrderORM(
                id=result.order_id,
                portfolio_id=result.portfolio_id,
                client_order_id=request.client_order_id,
                symbol=result.symbol,
                side=result.side.value,
                order_type=result.order_type.value,
                status=result.status.value,
                trading_mode="paper",
                market_type="spot",
                quantity=request.quantity,
                limit_price_usdt=request.limit_price_usdt,
                strategy_name=request.strategy_name,
                rejection_reason=result.rejection_reason,
            )
            session.add(order_orm)
            session.add(
                PaperFillORM(
                    id=fill.id,
                    order_id=result.order_id,
                    symbol=fill.symbol,
                    side=fill.side.value,
                    executed_qty=fill.executed_qty,
                    executed_price_usdt=fill.executed_price_usdt,
                    fee_usdt=fill.fee_usdt,
                    inr_per_usdt_rate=fill.inr_per_usdt_rate,
                    total_inr=fill.total_inr,
                    slippage_bps=fill.slippage_bps,
                    executed_at=_utc(fill.executed_at),
                )
            )

            portfolio_stmt = (
                select(PortfolioORM)
                .options(selectinload(PortfolioORM.balances))
                .where(PortfolioORM.id == portfolio.id)
            )
            if lock_rows:
                portfolio_stmt = portfolio_stmt.with_for_update()
            port_row = (await session.execute(portfolio_stmt)).scalar_one()
            port_row.cash_balance_inr = portfolio.cash_balance_inr

            existing_by_asset = {b.asset: b for b in port_row.balances}
            for asset, holding in portfolio.holdings.items():
                bal = existing_by_asset.get(asset)
                if bal is None:
                    session.add(
                        PortfolioBalanceORM(
                            portfolio_id=portfolio.id,
                            asset=asset,
                            free_qty=holding.free_qty,
                            locked_qty=holding.locked_qty,
                            avg_entry_price_usdt=holding.avg_entry_price_usdt,
                        )
                    )
                else:
                    bal.free_qty = holding.free_qty
                    bal.locked_qty = holding.locked_qty
                    bal.avg_entry_price_usdt = holding.avg_entry_price_usdt

            pos_row = (
                await session.execute(
                    select(PaperPositionORM).where(PaperPositionORM.id == position.id)
                )
            ).scalar_one_or_none()
            if pos_row is None:
                pos_row = PaperPositionORM(
                    id=position.id,
                    portfolio_id=position.portfolio_id,
                    symbol=position.symbol,
                    asset=position.asset,
                    opened_at=_utc(position.opened_at),
                )
                session.add(pos_row)

            pos_row.quantity = position.quantity
            pos_row.avg_entry_price_usdt = position.avg_entry_price_usdt
            pos_row.entry_cost_inr = position.entry_cost_inr
            pos_row.entry_fee_usdt = position.entry_fee_usdt
            pos_row.initial_stop_price_usdt = position.initial_stop_price_usdt
            pos_row.trailing_stop_price_usdt = position.trailing_stop_price_usdt
            pos_row.highest_price_usdt = position.highest_price_usdt
            pos_row.trailing_atr_multiplier = position.trailing_atr_multiplier
            pos_row.atr_at_entry = position.atr_at_entry
            pos_row.status = position.status
            pos_row.closed_at = _opt_utc(position.closed_at)

            if ledger_entry is not None:
                session.add(
                    TradeLedgerORM(
                        id=ledger_entry.id,
                        portfolio_id=ledger_entry.portfolio_id,
                        position_id=ledger_entry.position_id,
                        symbol=ledger_entry.symbol,
                        entry_order_id=ledger_entry.entry_order_id,
                        exit_order_id=ledger_entry.exit_order_id,
                        quantity=ledger_entry.quantity,
                        entry_price_usdt=ledger_entry.entry_price_usdt,
                        exit_price_usdt=ledger_entry.exit_price_usdt,
                        entry_cost_inr=ledger_entry.entry_cost_inr,
                        exit_proceeds_inr=ledger_entry.exit_proceeds_inr,
                        total_fees_inr=ledger_entry.total_fees_inr,
                        realized_pnl_inr=ledger_entry.realized_pnl_inr,
                        realized_pnl_pct=ledger_entry.realized_pnl_pct,
                        exit_reason=ledger_entry.exit_reason,
                        opened_at=_utc(ledger_entry.opened_at),
                        closed_at=_utc(ledger_entry.closed_at),
                    )
                )

            risk_stmt = select(RiskStateORM).where(
                RiskStateORM.portfolio_id == risk_state.portfolio_id
            )
            if lock_rows:
                risk_stmt = risk_stmt.with_for_update()
            risk_row = (await session.execute(risk_stmt)).scalar_one_or_none()
            if risk_row is None:
                risk_row = RiskStateORM(portfolio_id=risk_state.portfolio_id)
                session.add(risk_row)

            risk_row.trading_date_utc = risk_state.trading_date_utc
            risk_row.daily_starting_equity_inr = risk_state.daily_starting_equity_inr
            risk_row.peak_equity_inr = risk_state.peak_equity_inr
            risk_row.daily_entries_count = risk_state.daily_entries_count
            risk_row.daily_realized_pnl_inr = risk_state.daily_realized_pnl_inr
            risk_row.total_realized_pnl_inr = risk_state.total_realized_pnl_inr
            risk_row.kill_switch_active = risk_state.kill_switch_active
            risk_row.kill_switch_reason = risk_state.kill_switch_reason
            risk_row.kill_switch_triggered_at = risk_state.kill_switch_triggered_at

    async def record_order_and_fill(
        self,
        request: PaperOrderRequest,
        result: PaperOrderResult,
        fill: PaperFill | None,
    ) -> None:
        """Persist order record and optional fill inside one transaction."""
        async with self._session_factory() as session:
            # Skip persisting DB-check-violating qty <= 0; store positive min or record cleanly
            persisted_qty = (
                request.quantity if request.quantity > Decimal("0") else Decimal("0.00000001")
            )
            order_orm = PaperOrderORM(
                id=result.order_id,
                portfolio_id=result.portfolio_id,
                client_order_id=request.client_order_id,
                symbol=result.symbol,
                side=result.side.value,
                order_type=result.order_type.value,
                status=result.status.value,
                trading_mode="paper",
                market_type="spot",
                quantity=persisted_qty,
                limit_price_usdt=request.limit_price_usdt,
                strategy_name=request.strategy_name,
                rejection_reason=result.rejection_reason,
            )
            session.add(order_orm)

            if fill is not None:
                session.add(
                    PaperFillORM(
                        id=fill.id,
                        order_id=result.order_id,
                        symbol=fill.symbol,
                        side=fill.side.value,
                        executed_qty=fill.executed_qty,
                        executed_price_usdt=fill.executed_price_usdt,
                        fee_usdt=fill.fee_usdt,
                        inr_per_usdt_rate=fill.inr_per_usdt_rate,
                        total_inr=fill.total_inr,
                        slippage_bps=fill.slippage_bps,
                        executed_at=_utc(fill.executed_at),
                    )
                )
            await session.commit()

    async def cancel_pending_orders(self, portfolio_id: UUID, reason: str) -> int:
        """Mark all pending paper orders as cancelled."""
        async with self._session_factory() as session:
            res = await session.execute(
                update(PaperOrderORM)
                .where(
                    PaperOrderORM.portfolio_id == portfolio_id,
                    PaperOrderORM.status == OrderStatus.PENDING.value,
                )
                .values(status=OrderStatus.CANCELLED.value, rejection_reason=reason)
            )
            await session.commit()
            return int(res.rowcount or 0)  # type: ignore[attr-defined]

    async def get_open_positions(self, portfolio_id: UUID) -> list[OpenPaperPosition]:
        """Load all open virtual positions from DB."""
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(PaperPositionORM)
                    .where(
                        PaperPositionORM.portfolio_id == portfolio_id,
                        PaperPositionORM.status == "open",
                    )
                    .order_by(PaperPositionORM.opened_at.asc())
                )
            ).scalars().all()
            return [
                OpenPaperPosition(
                    id=r.id,
                    portfolio_id=r.portfolio_id,
                    symbol=r.symbol,
                    asset=r.asset,
                    quantity=r.quantity,
                    avg_entry_price_usdt=r.avg_entry_price_usdt,
                    entry_cost_inr=r.entry_cost_inr,
                    entry_fee_usdt=r.entry_fee_usdt,
                    initial_stop_price_usdt=r.initial_stop_price_usdt,
                    trailing_stop_price_usdt=r.trailing_stop_price_usdt,
                    highest_price_usdt=r.highest_price_usdt,
                    trailing_atr_multiplier=r.trailing_atr_multiplier,
                    atr_at_entry=r.atr_at_entry,
                    status="open",
                    opened_at=_utc(r.opened_at),
                    closed_at=_opt_utc(r.closed_at),
                )
                for r in rows
            ]

    async def save_position(self, position: OpenPaperPosition) -> None:
        """Insert or update a virtual paper position."""
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(PaperPositionORM).where(PaperPositionORM.id == position.id)
                )
            ).scalar_one_or_none()
            if row is None:
                row = PaperPositionORM(
                    id=position.id,
                    portfolio_id=position.portfolio_id,
                    symbol=position.symbol,
                    asset=position.asset,
                    opened_at=_utc(position.opened_at),
                )
                session.add(row)

            row.quantity = position.quantity
            row.avg_entry_price_usdt = position.avg_entry_price_usdt
            row.entry_cost_inr = position.entry_cost_inr
            row.entry_fee_usdt = position.entry_fee_usdt
            row.initial_stop_price_usdt = position.initial_stop_price_usdt
            row.trailing_stop_price_usdt = position.trailing_stop_price_usdt
            row.highest_price_usdt = position.highest_price_usdt
            row.trailing_atr_multiplier = position.trailing_atr_multiplier
            row.atr_at_entry = position.atr_at_entry
            row.status = position.status
            row.closed_at = _opt_utc(position.closed_at)
            await session.commit()

    async def append_trade_ledger(self, entry: TradeLedgerEntry) -> None:
        """Persist a closed round-trip trade P&L entry."""
        async with self._session_factory() as session:
            pos_exists = (
                await session.execute(
                    select(PaperPositionORM.id).where(PaperPositionORM.id == entry.position_id)
                )
            ).scalar_one_or_none()
            if pos_exists is None:
                base_asset = entry.symbol.split("/")[0] if "/" in entry.symbol else entry.symbol[:3]
                session.add(
                    PaperPositionORM(
                        id=entry.position_id,
                        portfolio_id=entry.portfolio_id,
                        symbol=entry.symbol,
                        asset=base_asset,
                        quantity=entry.quantity,
                        avg_entry_price_usdt=entry.entry_price_usdt,
                        entry_cost_inr=entry.entry_cost_inr,
                        entry_fee_usdt=Decimal("0"),
                        initial_stop_price_usdt=entry.entry_price_usdt * Decimal("0.98"),
                        trailing_stop_price_usdt=entry.entry_price_usdt * Decimal("0.98"),
                        highest_price_usdt=entry.exit_price_usdt,
                        status="closed",
                        opened_at=_utc(entry.opened_at),
                        closed_at=_utc(entry.closed_at),
                    )
                )
                await session.flush()

            session.add(
                TradeLedgerORM(
                    id=entry.id,
                    portfolio_id=entry.portfolio_id,
                    position_id=entry.position_id,
                    symbol=entry.symbol,
                    entry_order_id=entry.entry_order_id,
                    exit_order_id=entry.exit_order_id,
                    quantity=entry.quantity,
                    entry_price_usdt=entry.entry_price_usdt,
                    exit_price_usdt=entry.exit_price_usdt,
                    entry_cost_inr=entry.entry_cost_inr,
                    exit_proceeds_inr=entry.exit_proceeds_inr,
                    total_fees_inr=entry.total_fees_inr,
                    realized_pnl_inr=entry.realized_pnl_inr,
                    realized_pnl_pct=entry.realized_pnl_pct,
                    exit_reason=entry.exit_reason,
                    opened_at=_utc(entry.opened_at),
                    closed_at=_utc(entry.closed_at),
                )
            )
            await session.commit()

    async def list_trade_ledger(self, portfolio_id: UUID) -> list[TradeLedgerEntry]:
        """Return closed trade ledger entries ordered by close time ascending."""
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(TradeLedgerORM)
                    .where(TradeLedgerORM.portfolio_id == portfolio_id)
                    .order_by(TradeLedgerORM.closed_at.asc())
                )
            ).scalars().all()
            return [
                TradeLedgerEntry(
                    id=r.id,
                    portfolio_id=r.portfolio_id,
                    position_id=r.position_id,
                    symbol=r.symbol,
                    entry_order_id=r.entry_order_id,
                    exit_order_id=r.exit_order_id,
                    quantity=r.quantity,
                    entry_price_usdt=r.entry_price_usdt,
                    exit_price_usdt=r.exit_price_usdt,
                    entry_cost_inr=r.entry_cost_inr,
                    exit_proceeds_inr=r.exit_proceeds_inr,
                    total_fees_inr=r.total_fees_inr,
                    realized_pnl_inr=r.realized_pnl_inr,
                    realized_pnl_pct=r.realized_pnl_pct,
                    exit_reason=r.exit_reason,
                    opened_at=_utc(r.opened_at),
                    closed_at=_utc(r.closed_at),
                )
                for r in rows
            ]

    async def get_earnings_breakdown(
        self, portfolio_id: UUID, inr_per_usdt: Decimal = Decimal("85.00")
    ) -> dict[str, Any]:
        """Return granular asset-by-asset breakdown and portfolio totals down to the exact paisa."""
        async with self._session_factory() as session:
            stmt = (
                select(
                    TradeLedgerORM.symbol,
                    func.count().label("total_trades"),
                    func.count(case((TradeLedgerORM.realized_pnl_inr > 0, 1))).label("win_count"),
                    func.count(case((TradeLedgerORM.realized_pnl_inr < 0, 1))).label("loss_count"),
                    func.count(case((TradeLedgerORM.realized_pnl_inr == 0, 1))).label("breakeven_count"),
                    func.coalesce(
                        func.sum(
                            case(
                                (TradeLedgerORM.realized_pnl_inr > 0, TradeLedgerORM.realized_pnl_inr),
                                else_=Decimal("0"),
                            )
                        ),
                        Decimal("0"),
                    ).label("gross_profit_inr"),
                    func.coalesce(
                        func.sum(
                            case(
                                (TradeLedgerORM.realized_pnl_inr < 0, func.abs(TradeLedgerORM.realized_pnl_inr)),
                                else_=Decimal("0"),
                            )
                        ),
                        Decimal("0"),
                    ).label("gross_loss_inr"),
                    func.coalesce(func.sum(TradeLedgerORM.total_fees_inr), Decimal("0")).label("total_fees_inr"),
                    func.coalesce(func.sum(TradeLedgerORM.realized_pnl_inr), Decimal("0")).label("net_realized_pnl_inr"),
                    func.coalesce(func.sum(TradeLedgerORM.entry_cost_inr), Decimal("0")).label("total_volume_inr"),
                    func.max(TradeLedgerORM.closed_at).label("last_trade_at"),
                )
                .where(TradeLedgerORM.portfolio_id == portfolio_id)
                .group_by(TradeLedgerORM.symbol)
                .order_by(func.sum(TradeLedgerORM.realized_pnl_inr).desc())
            )
            rows = (await session.execute(stmt)).all()

            port_row = (
                await session.execute(
                    select(PortfolioORM).where(PortfolioORM.id == portfolio_id)
                )
            ).scalar_one_or_none()

            initial_cap = port_row.initial_capital_inr if port_row else Decimal("10000.00")
            cash_bal = port_row.cash_balance_inr if port_row else Decimal("10000.00")

            safe_rate = inr_per_usdt if inr_per_usdt > Decimal("0") else Decimal("85.00")

            total_trades = 0
            total_wins = 0
            total_losses = 0
            total_gross_profit = Decimal("0")
            total_gross_loss = Decimal("0")
            total_fees = Decimal("0")
            total_net_pnl = Decimal("0")
            total_volume = Decimal("0")

            assets_breakdown = []
            for r in rows:
                sym_trades = int(r.total_trades)
                sym_wins = int(r.win_count)
                sym_losses = int(r.loss_count)
                sym_gross_profit = Decimal(str(r.gross_profit_inr))
                sym_gross_loss = Decimal(str(r.gross_loss_inr))
                sym_fees = Decimal(str(r.total_fees_inr))
                sym_net_pnl = Decimal(str(r.net_realized_pnl_inr))
                sym_volume = Decimal(str(r.total_volume_inr))
                sym_win_rate = round((sym_wins / sym_trades * 100.0), 2) if sym_trades > 0 else 0.0

                total_trades += sym_trades
                total_wins += sym_wins
                total_losses += sym_losses
                total_gross_profit += sym_gross_profit
                total_gross_loss += sym_gross_loss
                total_fees += sym_fees
                total_net_pnl += sym_net_pnl
                total_volume += sym_volume

                is_arb = (
                    ("/" in r.symbol and not r.symbol.endswith("/USDT"))
                    or ("BTC" in r.symbol and "ETH" in r.symbol)
                    or ("SOL" in r.symbol and "ETH" in r.symbol)
                    or ("BNB" in r.symbol and "BTC" in r.symbol)
                )
                strategy_type = "Triangular Arbitrage" if is_arb else "Strategy Spot V1/V2"

                assets_breakdown.append({
                    "symbol": r.symbol,
                    "trade_type": strategy_type,
                    "total_trades": sym_trades,
                    "winning_trades": sym_wins,
                    "losing_trades": sym_losses,
                    "win_rate_pct": sym_win_rate,
                    "gross_profit_inr": float(sym_gross_profit),
                    "gross_loss_inr": float(sym_gross_loss),
                    "total_fees_inr": float(sym_fees),
                    "net_realized_pnl_inr": float(sym_net_pnl),
                    "net_realized_pnl_usdt": round(float(sym_net_pnl / safe_rate), 4),
                    "total_volume_inr": float(sym_volume),
                    "last_trade_at": r.last_trade_at.isoformat() if r.last_trade_at else None,
                })

            for asset in assets_breakdown:
                if total_net_pnl > Decimal("0") and asset["net_realized_pnl_inr"] > 0:
                    asset["profit_share_pct"] = round(
                        float(Decimal(str(asset["net_realized_pnl_inr"])) / total_net_pnl * Decimal("100.0")), 2
                    )
                else:
                    asset["profit_share_pct"] = 0.0

            overall_win_rate = round((total_wins / total_trades * 100.0), 2) if total_trades > 0 else 0.0
            profit_factor = (
                round(float(total_gross_profit / total_gross_loss), 2)
                if total_gross_loss > Decimal("0")
                else (999.99 if total_gross_profit > Decimal("0") else 0.0)
            )

            return {
                "portfolio_id": str(portfolio_id),
                "inr_per_usdt": float(safe_rate),
                "initial_capital_inr": float(initial_cap),
                "cash_balance_inr": float(cash_bal),
                "total_trades": total_trades,
                "winning_trades": total_wins,
                "losing_trades": total_losses,
                "win_rate_pct": overall_win_rate,
                "profit_factor": profit_factor,
                "total_gross_profit_inr": float(total_gross_profit),
                "total_gross_loss_inr": float(total_gross_loss),
                "total_fees_inr": float(total_fees),
                "net_realized_pnl_inr": float(total_net_pnl),
                "net_realized_pnl_usdt": round(float(total_net_pnl / safe_rate), 4),
                "total_volume_inr": float(total_volume),
                "assets": assets_breakdown,
            }
