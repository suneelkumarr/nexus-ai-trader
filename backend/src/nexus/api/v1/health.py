"""Health, liveness, and readiness endpoints."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from nexus.api.dependencies import (
    get_app_settings,
    get_database_manager,
    get_market_data_provider,
)
from nexus.core.config import Settings
from nexus.domain.interfaces import MarketDataProvider
from nexus.infrastructure.db.session import DatabaseManager

router = APIRouter(prefix="/health", tags=["Health"])


class ComponentCheck(BaseModel):
    """Health status of a downstream dependency."""

    status: Literal["up", "down"]
    detail: str | None = None


class HealthResponse(BaseModel):
    """Comprehensive system health and trading-invariant report."""

    status: Literal["ok", "degraded"]
    service: str
    version: str
    environment: str
    trading_mode: str
    market_type: str
    live_trading_enabled: bool
    allow_leverage: bool
    allow_futures: bool
    allow_withdrawals: bool
    base_currency: str
    initial_capital_inr: float
    allowed_symbols: list[str]
    checks: dict[str, ComponentCheck]
    timestamp: datetime


class LivenessResponse(BaseModel):
    """Minimal liveness probe response."""

    status: Literal["alive"]
    timestamp: datetime


class ReadinessResponse(BaseModel):
    """Readiness probe response indicating ability to serve traffic."""

    status: Literal["ready", "not_ready"]
    database: ComponentCheck
    timestamp: datetime


@router.get("", response_model=HealthResponse, summary="Service health summary")
async def health_summary(
    settings: Annotated[Settings, Depends(get_app_settings)],
    db_manager: Annotated[DatabaseManager, Depends(get_database_manager)],
    market_data: Annotated[MarketDataProvider, Depends(get_market_data_provider)],
) -> HealthResponse:
    """Report service status, active trading invariants, DB, and exchange feed checks."""
    db_ok, db_err = await db_manager.check_health()
    exchange_ok = await market_data.health_check()

    overall: Literal["ok", "degraded"] = "ok" if (db_ok and exchange_ok) else "degraded"
    return HealthResponse(
        status=overall,
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env,
        trading_mode=settings.trading_mode,
        market_type=settings.market_type,
        live_trading_enabled=settings.live_trading_enabled,
        allow_leverage=settings.allow_leverage,
        allow_futures=settings.allow_futures,
        allow_withdrawals=settings.allow_withdrawals,
        base_currency=settings.base_currency,
        initial_capital_inr=float(settings.initial_capital_inr),
        allowed_symbols=settings.allowed_symbols,
        checks={
            "database": ComponentCheck(status="up" if db_ok else "down", detail=db_err),
            "market_feed": ComponentCheck(
                status="up" if exchange_ok else "down",
                detail=None if exchange_ok else f"Exchange '{settings.exchange_id}' unreachable",
            ),
        },
        timestamp=datetime.now(UTC),
    )


@router.get("/live", response_model=LivenessResponse, summary="Kubernetes/Docker liveness probe")
async def liveness_probe() -> LivenessResponse:
    """Return 200 OK while the FastAPI event loop is responsive."""
    return LivenessResponse(status="alive", timestamp=datetime.now(UTC))


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def readiness_probe(
    response: Response,
    db_manager: Annotated[DatabaseManager, Depends(get_database_manager)],
) -> ReadinessResponse:
    """Verify PostgreSQL connectivity before marking the service ready."""
    db_ok, db_err = await db_manager.check_health()
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if db_ok else "not_ready",
        database=ComponentCheck(status="up" if db_ok else "down", detail=db_err),
        timestamp=datetime.now(UTC),
    )

