"""FastAPI application factory, lifespan wiring, and request correlation middleware."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from nexus.api.v1.health import router as health_router
from nexus.api.v1.router import v1_router
from nexus.application.ai_analysis.service import MarketAnalysisService
from nexus.application.autonomous.engine_service import AutonomousEngineService
from nexus.application.market_data.service import MarketDataService
from nexus.application.persistent_paper_broker import PersistentPaperBroker
from nexus.application.risk_manager import IndependentRiskManager
from nexus.application.strategy.v1_engine import NexusStrategyV1
from nexus.core.config import Settings, get_settings
from nexus.core.logging import configure_logging, get_logger
from nexus.core.security import SecurityRateLimitMiddleware
from nexus.infrastructure.ai.http_client import OpenAICompatibleAIClient
from nexus.infrastructure.db.candle_repository import SqlAlchemyCandleRepository
from nexus.infrastructure.db.paper_repository import SqlAlchemyPaperRepository
from nexus.infrastructure.db.session import DatabaseManager
from nexus.infrastructure.exchange.ccxt_client import CCXTPublicExchangeClient

logger = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build and configure the FastAPI application with injected infrastructure."""
    active_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging(
            log_level=active_settings.log_level,
            log_format=active_settings.log_format,
            service_name=active_settings.app_name,
            environment=active_settings.app_env,
        )

        db_manager = DatabaseManager(active_settings)
        candle_repo = SqlAlchemyCandleRepository(db_manager.session_factory)
        exchange_client = CCXTPublicExchangeClient(
            exchange_id=active_settings.exchange_id,
            allowed_symbols=active_settings.allowed_symbols,
            supported_timeframes=active_settings.supported_timeframes,
            timeout_ms=active_settings.exchange_timeout_ms,
            max_retries=active_settings.market_data_max_retries,
            backoff_base_s=active_settings.market_data_backoff_base_s,
        )
        market_data_service = MarketDataService(
            settings=active_settings,
            exchange_client=exchange_client,
            candle_repository=candle_repo,
        )
        ai_client = (
            OpenAICompatibleAIClient(
                base_url=active_settings.ai.base_url,
                api_key=active_settings.ai.api_key,
                model=active_settings.ai.model,
                timeout_s=active_settings.ai.timeout_s,
                max_retries=active_settings.ai.max_retries,
                backoff_base_s=active_settings.ai.backoff_base_s,
                fallback_endpoints=active_settings.ai.get_fallback_endpoints(),
            )
            if active_settings.ai.provider == "openai_compatible"
            else None
        )
        market_analysis_service = MarketAnalysisService(
            config=active_settings.ai,
            ai_client=ai_client,
            strategy_config=active_settings.strategy_v1,
        )

        paper_repo = SqlAlchemyPaperRepository(db_manager.session_factory)
        from nexus.application.risk_guard import SpotSignalRiskApprover

        signal_approver = SpotSignalRiskApprover(
            allowed_symbols=active_settings.allowed_symbols
        )
        strategy_engine = NexusStrategyV1(
            config=active_settings.strategy_v1,
            risk_approver=signal_approver,
        )
        risk_manager = IndependentRiskManager(
            allowed_symbols=active_settings.allowed_symbols,
            risk_config=active_settings.risk,
            fee_bps=active_settings.paper_fee_bps,
            slippage_bps=active_settings.paper_slippage_bps,
        )
        broker = PersistentPaperBroker(
            repository=paper_repo,
            risk_manager=risk_manager,
            market_data=market_data_service,
            initial_capital_inr=active_settings.initial_capital_inr,
            fee_bps=active_settings.paper_fee_bps,
            slippage_bps=active_settings.paper_slippage_bps,
            trailing_atr_multiplier=active_settings.strategy_v1.trailing_atr_multiplier,
        )
        autonomous_engine = AutonomousEngineService(
            settings=active_settings,
            market_data=market_data_service,
            paper_repo=paper_repo,
            candle_repo=candle_repo,
            risk_manager=risk_manager,
            strategy_engine=strategy_engine,
            broker=broker,
            ai_client=ai_client,
        )

        app.state.settings = active_settings
        app.state.db_manager = db_manager
        app.state.market_data_service = market_data_service
        app.state.market_data_provider = market_data_service
        app.state.market_analysis_service = market_analysis_service
        app.state.paper_repo = paper_repo
        app.state.risk_manager = risk_manager
        app.state.strategy_engine = strategy_engine
        app.state.broker = broker
        app.state.autonomous_engine = autonomous_engine

        # Start autonomous multi-agent background trading and intelligence loops
        await autonomous_engine.start()

        logger.info(
            "nexus_service_started",
            trading_mode=active_settings.trading_mode,
            market_type=active_settings.market_type,
            initial_capital_inr=str(active_settings.initial_capital_inr),
            allowed_symbols=active_settings.allowed_symbols,
            supported_timeframes=active_settings.supported_timeframes,
            autonomous_engine="active",
        )

        try:
            yield
        finally:
            await autonomous_engine.stop()
            await market_analysis_service.close()
            await market_data_service.close()
            await db_manager.dispose()
            logger.info("nexus_service_stopped")

    app = FastAPI(
        title="NEXUS AI TRADER API",
        version=active_settings.app_version,
        description=(
            "Automated cryptocurrency spot paper-trading engine (INR 10,000 virtual portfolio)."
        ),
        lifespan=lifespan,
    )
    app.state.settings = active_settings

    app.add_middleware(
        SecurityRateLimitMiddleware,
        rate_limit_per_minute=active_settings.rate_limit_per_minute,
        max_body_bytes=active_settings.max_body_bytes,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origins,
        allow_origin_regex=r"^https?://.*(?:\.pages\.dev|localhost|\.onrender\.com|\.koyeb\.app)(?::\d+)?$",
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "X-Request-ID",
            "X-Nexus-API-Key",
        ],
    )

    @app.middleware("http")
    async def request_correlation_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            structlog.contextvars.unbind_contextvars("request_id", "method", "path")

    app.include_router(v1_router)
    app.include_router(health_router)
    return app


app = create_app()

