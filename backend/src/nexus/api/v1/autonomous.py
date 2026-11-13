"""Autonomous paper-trading engine and live AI quantitative research endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from nexus.application.autonomous.engine_service import AutonomousEngineService
from nexus.core.security import require_admin_auth

router = APIRouter(prefix="/autonomous", tags=["Autonomous Multi-Agent Engine"])


class EngineStatusResponse(BaseModel):
    is_running: bool
    cycle_count: int
    last_cycle_at: str | None
    last_cycle_duration_ms: float
    arbitrage_trades_count: int
    strategy_trades_count: int
    open_positions_count: int
    kill_switch_active: bool
    kill_switch_reason: str | None
    cash_balance_inr: float
    initial_capital_inr: float
    last_error: str | None
    latest_ai_research: dict[str, Any]
    universe_size: int = 115
    recently_evaluated_symbols: list[str] = []
    recent_opportunities: list[dict[str, Any]] = []
    recent_orders_placed: list[str] = []
    execution_target: str = "paper"
    binance_configured: bool = False


class SetExecutionModeRequest(BaseModel):
    mode: str


class ExecutionModeResponse(BaseModel):
    execution_target: str
    previous_target: str | None = None
    message: str
    binance_configured: bool = False
    is_running: bool = True


def get_autonomous_engine(request: Request) -> AutonomousEngineService:
    """Retrieve autonomous engine instance from application state."""
    engine = getattr(request.app.state, "autonomous_engine", None)
    if not isinstance(engine, AutonomousEngineService):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autonomous trading engine is not active on this node.",
        )
    return engine


@router.get("/status", response_model=EngineStatusResponse)
async def get_engine_status(
    engine: Annotated[AutonomousEngineService, Depends(get_autonomous_engine)],
) -> Any:
    """Return aggregated live telemetry for the autonomous multi-agent engine."""
    return await engine.get_status()


@router.post("/cycle")
async def trigger_autonomous_cycle(
    engine: Annotated[AutonomousEngineService, Depends(get_autonomous_engine)],
    _auth: Annotated[str, Depends(require_admin_auth)] = "ok",
) -> Any:
    """Manually force an immediate cycle of Strategy V1, Arbitrage, and AI Research."""
    return await engine.force_full_cycle()


@router.post("/toggle")
async def toggle_autonomous_engine(
    engine: Annotated[AutonomousEngineService, Depends(get_autonomous_engine)],
    _auth: Annotated[str, Depends(require_admin_auth)] = "ok",
) -> Any:
    """Pause or resume the autonomous multi-agent background loops."""
    active = await engine.toggle()
    return {"is_running": active, "message": "Autonomous engine resumed" if active else "Paused"}


@router.get("/ai-research")
async def get_latest_ai_research(
    engine: Annotated[AutonomousEngineService, Depends(get_autonomous_engine)],
) -> Any:
    """Return the latest macroeconomic regime and market research briefing from CrowLLM."""
    return engine.latest_ai_research


@router.post("/ai-research/refresh")
async def refresh_ai_research(
    engine: Annotated[AutonomousEngineService, Depends(get_autonomous_engine)],
    _auth: Annotated[str, Depends(require_admin_auth)] = "ok",
) -> Any:
    """Force an immediate market research refresh across all 54 spot pairs via CrowLLM."""
    return await engine._refresh_ai_research()


@router.get("/execution-mode", response_model=ExecutionModeResponse)
async def get_execution_mode(
    engine: Annotated[AutonomousEngineService, Depends(get_autonomous_engine)],
) -> Any:
    """Return active execution mode (paper simulation vs live Binance)."""
    return {
        "execution_target": engine.execution_target,
        "previous_target": None,
        "message": (
            "Automatic paper trading active. Real money trading halted."
            if engine.execution_target == "paper"
            else "LIVE Real Money Trading active on Binance USD(S)-M Futures. Paper trading paused."
        ),
        "binance_configured": bool(
            engine._binance_gateway and getattr(engine._binance_gateway, "is_configured", False)
        ),
        "is_running": engine.is_running,
    }


@router.post("/execution-mode", response_model=ExecutionModeResponse)
async def set_execution_mode(
    request: SetExecutionModeRequest,
    engine: Annotated[AutonomousEngineService, Depends(get_autonomous_engine)],
    _auth: Annotated[str, Depends(require_admin_auth)] = "ok",
) -> Any:
    """Atomically toggle between Automatic Paper Trading and Live Binance Real Trading."""
    try:
        res = engine.set_execution_target(request.mode)
        res["binance_configured"] = bool(
            engine._binance_gateway and getattr(engine._binance_gateway, "is_configured", False)
        )
        res["is_running"] = engine.is_running
        return res
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

