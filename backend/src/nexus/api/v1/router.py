"""Top-level v1 API router."""

from fastapi import APIRouter

from nexus.api.v1.analysis import router as analysis_router
from nexus.api.v1.arbitrage import router as arbitrage_router
from nexus.api.v1.autonomous import router as autonomous_router
from nexus.api.v1.futures import router as futures_router
from nexus.api.v1.health import router as health_router
from nexus.api.v1.terminal import router as terminal_router

v1_router = APIRouter(prefix="/api/v1")
v1_router.include_router(health_router)
v1_router.include_router(analysis_router)
v1_router.include_router(terminal_router)
v1_router.include_router(arbitrage_router)
v1_router.include_router(autonomous_router)
v1_router.include_router(futures_router)

