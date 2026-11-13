"""FastAPI REST endpoints for Crypto Futures Paper Trading Simulation."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from nexus.application.futures.broker import FuturesPaperBroker
from nexus.application.futures.funding_service import FuturesFundingService
from nexus.core.logging import get_logger
from nexus.core.security import require_admin_auth
from nexus.domain.futures import (
    FuturesAccountSummary,
    FuturesOrderRequest,
    FuturesOrderResult,
    FuturesPosition,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/futures", tags=["Crypto Futures Paper Trading"])


def get_futures_broker(request: Request) -> FuturesPaperBroker:
    """Dependency provider for FuturesPaperBroker."""
    broker: FuturesPaperBroker | None = getattr(request.app.state, "futures_broker", None)
    if broker is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Futures Paper Broker is initializing or unavailable.",
        )
    return broker


def get_funding_service(request: Request) -> FuturesFundingService:
    """Dependency provider for FuturesFundingService."""
    service: FuturesFundingService | None = getattr(request.app.state, "funding_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Futures Funding Service is initializing or unavailable.",
        )
    return service


class ToggleAutoTradeRequest(BaseModel):
    enabled: bool = Field(description="Enable or disable autonomous futures execution")


@router.get("/summary", response_model=FuturesAccountSummary)
async def get_futures_summary(
    broker: Annotated[FuturesPaperBroker, Depends(get_futures_broker)],
) -> FuturesAccountSummary:
    """Fetch consolidated futures account equity, margin in use, P&L, and win rate."""
    return await broker.get_account_summary()


@router.get("/positions", response_model=list[FuturesPosition])
async def get_futures_positions(
    broker: Annotated[FuturesPaperBroker, Depends(get_futures_broker)],
    status_filter: Annotated[str, Query(alias="status")] = "open",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[FuturesPosition]:
    """Fetch simulated futures positions (open or historical)."""
    if status_filter.lower() == "open":
        return await broker.get_open_positions()
    return await broker.get_all_positions(limit=limit)


@router.post("/orders", response_model=FuturesOrderResult)
async def place_futures_order(
    request: FuturesOrderRequest,
    broker: Annotated[FuturesPaperBroker, Depends(get_futures_broker)],
    _auth: Annotated[str, Depends(require_admin_auth)] = "ok",
) -> FuturesOrderResult:
    """Place a simulated futures order (OPEN_LONG, OPEN_SHORT, CLOSE_LONG, CLOSE_SHORT)."""
    return await broker.submit_order(request)


@router.post("/positions/{position_id}/close", response_model=FuturesPosition)
async def close_futures_position(
    position_id: UUID,
    broker: Annotated[FuturesPaperBroker, Depends(get_futures_broker)],
    _auth: Annotated[str, Depends(require_admin_auth)] = "ok",
) -> FuturesPosition:
    """Close an open simulated futures position at market price."""
    try:
        return await broker.close_position_by_id(position_id, reason="Manual user close via API")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/funding-rates")
async def get_funding_rates(
    funding_service: Annotated[FuturesFundingService, Depends(get_funding_service)],
    symbols: Annotated[
        str | None,
        Query(description="Comma-separated symbols, e.g. BTC/USDT,ETH/USDT"),
    ] = None,
) -> dict[str, Any]:
    """Fetch real-time Binance USDT-M perpetual funding rates and mark prices."""
    sym_list = [s.strip() for s in symbols.split(",")] if symbols else None
    rates = await funding_service.fetch_funding_rates(sym_list)
    return {
        sym: {
            "symbol": r.symbol,
            "funding_rate": str(r.funding_rate),
            "funding_rate_pct": float(r.funding_rate_pct),
            "mark_price": float(r.mark_price),
            "index_price": float(r.index_price),
            "next_funding_time": r.next_funding_time.isoformat(),
        }
        for sym, r in rates.items()
    }


@router.post("/toggle-auto-trade")
async def toggle_auto_trade(
    req: ToggleAutoTradeRequest,
    broker: Annotated[FuturesPaperBroker, Depends(get_futures_broker)],
    _auth: Annotated[str, Depends(require_admin_auth)] = "ok",
) -> dict[str, Any]:
    """Enable or disable autonomous strategy execution on futures."""
    broker.set_auto_trade(req.enabled)
    logger.info("futures_auto_trade_toggled", enabled=req.enabled)
    return {"status": "ok", "auto_trade_enabled": req.enabled}
