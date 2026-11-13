"""FastAPI Dependency Injection providers."""

from typing import Any

from fastapi import Request

from nexus.application.ai_analysis.service import MarketAnalysisService
from nexus.application.market_data.service import MarketDataService
from nexus.application.paper_broker import SpotPaperBroker
from nexus.application.persistent_paper_broker import PersistentPaperBroker
from nexus.application.portfolio_service import PortfolioService
from nexus.application.risk_guard import SpotPaperRiskGuard, SpotSignalRiskApprover
from nexus.application.risk_manager import IndependentRiskManager
from nexus.application.strategy.v1_engine import NexusStrategyV1
from nexus.core.config import Settings, get_settings
from nexus.domain.interfaces import (
    CandleRepository,
    MarketDataProvider,
    PaperExecutionEngine,
    PaperLedgerRepository,
    RiskGuard,
    SignalRiskApprover,
)
from nexus.infrastructure.ai.http_client import OpenAICompatibleAIClient
from nexus.infrastructure.db.candle_repository import SqlAlchemyCandleRepository
from nexus.infrastructure.db.paper_repository import SqlAlchemyPaperRepository
from nexus.infrastructure.db.session import DatabaseManager


def get_app_settings(request: Request) -> Settings:
    """Resolve active Settings from app state or fallback cache."""
    settings: Settings | None = getattr(request.app.state, "settings", None)
    return settings if settings is not None else get_settings()


def get_database_manager(request: Request) -> DatabaseManager:
    """Resolve DatabaseManager initialized during app lifespan."""
    return request.app.state.db_manager  # type: ignore[no-any-return]


def get_market_data_service(request: Request) -> MarketDataService:
    """Resolve MarketDataService initialized during app lifespan."""
    return request.app.state.market_data_service  # type: ignore[no-any-return]


def get_market_data_provider(request: Request) -> MarketDataProvider:
    """Resolve MarketDataProvider backed by MarketDataService."""
    return request.app.state.market_data_provider  # type: ignore[no-any-return]


def get_risk_guard(request: Request) -> RiskGuard:
    """Build SpotPaperRiskGuard from active settings."""
    settings = get_app_settings(request)
    return SpotPaperRiskGuard(
        allowed_symbols=settings.allowed_symbols,
        fee_bps=settings.paper_fee_bps,
        slippage_bps=settings.paper_slippage_bps,
    )


def get_paper_broker(request: Request) -> PaperExecutionEngine:
    """Build SpotPaperBroker with injected RiskGuard."""
    settings = get_app_settings(request)
    return SpotPaperBroker(
        risk_guard=get_risk_guard(request),
        fee_bps=settings.paper_fee_bps,
        slippage_bps=settings.paper_slippage_bps,
    )


def get_signal_risk_approver(request: Request) -> SignalRiskApprover:
    """Build SpotSignalRiskApprover from active settings."""
    settings = get_app_settings(request)
    return SpotSignalRiskApprover(allowed_symbols=settings.allowed_symbols)


def get_strategy_v1(request: Request) -> NexusStrategyV1:
    """Build NexusStrategyV1 with configured parameters and injected risk approver."""
    settings = get_app_settings(request)
    return NexusStrategyV1(
        config=settings.strategy_v1,
        risk_approver=get_signal_risk_approver(request),
    )


def get_independent_risk_manager(request: Request) -> IndependentRiskManager:
    """Build IndependentRiskManager from active settings."""
    settings = get_app_settings(request)
    return IndependentRiskManager(
        allowed_symbols=settings.allowed_symbols,
        risk_config=settings.risk,
        fee_bps=settings.paper_fee_bps,
        slippage_bps=settings.paper_slippage_bps,
    )


def get_paper_ledger_repository(request: Request) -> PaperLedgerRepository:
    """Build SqlAlchemyPaperRepository backed by the DatabaseManager session factory."""
    db_manager = get_database_manager(request)
    return SqlAlchemyPaperRepository(db_manager.session_factory)


def get_persistent_paper_broker(request: Request) -> PersistentPaperBroker:
    """Build PersistentPaperBroker with independent risk manager and public market feed."""
    settings = get_app_settings(request)
    return PersistentPaperBroker(
        repository=get_paper_ledger_repository(request),
        risk_manager=get_independent_risk_manager(request),
        market_data=get_market_data_provider(request),
        initial_capital_inr=settings.initial_capital_inr,
        fee_bps=settings.paper_fee_bps,
        slippage_bps=settings.paper_slippage_bps,
        trailing_atr_multiplier=settings.strategy_v1.trailing_atr_multiplier,
    )


def get_portfolio_service(request: Request) -> PortfolioService:
    """Build PortfolioService from active settings."""
    return PortfolioService(settings=get_app_settings(request))


def get_candle_repository(request: Request) -> CandleRepository:
    """Build SqlAlchemyCandleRepository backed by DatabaseManager."""
    db_manager = get_database_manager(request)
    return SqlAlchemyCandleRepository(db_manager.session_factory)


def get_market_analysis_service(request: Request) -> MarketAnalysisService:
    """Resolve MarketAnalysisService initialized at lifespan or build read-only instance."""
    existing: MarketAnalysisService | None = getattr(
        request.app.state, "market_analysis_service", None
    )
    if existing is not None:
        return existing
    settings = get_app_settings(request)
    ai_client = (
        OpenAICompatibleAIClient(
            base_url=settings.ai.base_url,
            api_key=settings.ai.api_key,
            model=settings.ai.model,
            timeout_s=settings.ai.timeout_s,
            max_retries=settings.ai.max_retries,
            backoff_base_s=settings.ai.backoff_base_s,
        )
        if settings.ai.provider == "openai_compatible"
        else None
    )
    return MarketAnalysisService(
        config=settings.ai,
        ai_client=ai_client,
        strategy_config=settings.strategy_v1,
    )


def get_binance_gateway(request: Request) -> Any | None:
    """Resolve BinanceFuturesGateway initialized during app lifespan."""
    return getattr(request.app.state, "binance_gateway", None)


