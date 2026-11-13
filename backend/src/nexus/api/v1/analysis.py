"""Read-only advisory AI market analysis API endpoints (no order execution access)."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from nexus.api.dependencies import (
    get_app_settings,
    get_candle_repository,
    get_market_analysis_service,
)
from nexus.application.ai_analysis.service import MarketAnalysisService
from nexus.application.market_data.service import MarketDataService
from nexus.application.market_data.validator import get_timeframe_seconds
from nexus.core.config import Settings
from nexus.core.exceptions import (
    AIProviderError,
    AIResponseValidationError,
    CandleValidationError,
)
from nexus.core.security import require_admin_auth
from nexus.domain.interfaces import CandleRepository
from nexus.domain.models import (
    MarketAnalysisInput,
    MarketAnalysisOutput,
    StrategyPerformanceSnapshot,
    StrategySignal,
)

router = APIRouter(prefix="/analysis", tags=["AI Market Analysis (Advisory Only)"])


class FromCandlesAnalysisRequest(BaseModel):
    """Request payload to run advisory analysis from stored closed OHLCV candles."""

    symbol: str
    timeframe: str = "15m"
    lookback_bars: int = Field(default=120, ge=20, le=500)
    strategy_signals: list[StrategySignal] = Field(default_factory=list)
    strategy_comparisons: list[StrategyPerformanceSnapshot] = Field(default_factory=list)


@router.post(
    "/market",
    response_model=MarketAnalysisOutput,
    summary="Run advisory AI analysis on validated indicators and historical features",
)
async def analyze_market_features(
    payload: MarketAnalysisInput,
    settings: Annotated[Settings, Depends(get_app_settings)],
    analysis_service: Annotated[MarketAnalysisService, Depends(get_market_analysis_service)],
    _auth: Annotated[str, Depends(require_admin_auth)] = "ok",
) -> MarketAnalysisOutput:
    """Return strict 7-field advisory JSON; never places orders or bypasses risk."""
    if payload.symbol not in settings.allowed_symbols:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                f"Symbol '{payload.symbol}' is not in allowed spot universe "
                f"{settings.allowed_symbols}."
            ),
        )
    if payload.timeframe not in settings.supported_timeframes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Timeframe '{payload.timeframe}' is not in supported timeframes.",
        )

    try:
        return await analysis_service.analyze(payload)
    except AIProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except AIResponseValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.post(
    "/from-candles",
    response_model=MarketAnalysisOutput,
    summary="Build causal indicators from stored closed candles and run advisory analysis",
)
async def analyze_from_stored_candles(
    payload: FromCandlesAnalysisRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_app_settings)],
    candle_repo: Annotated[CandleRepository, Depends(get_candle_repository)],
    analysis_service: Annotated[MarketAnalysisService, Depends(get_market_analysis_service)],
    _auth: Annotated[str, Depends(require_admin_auth)] = "ok",
) -> MarketAnalysisOutput:
    """Load persisted UTC candles, validate closed bars, and emit advisory analysis JSON."""
    symbol = payload.symbol.strip().upper()
    timeframe = payload.timeframe.strip().lower()
    if symbol not in settings.allowed_symbols:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Symbol '{symbol}' is not in allowed spot universe {settings.allowed_symbols}.",
        )
    if timeframe not in settings.supported_timeframes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Timeframe '{timeframe}' is not supported.",
        )

    bars = await candle_repo.get_candles(
        exchange_id=settings.exchange_id,
        symbol=symbol,
        timeframe=timeframe,
        limit=payload.lookback_bars,
    )
    if len(bars) < 50:
        market_data = getattr(request.app.state, "market_data_service", None)
        if isinstance(market_data, MarketDataService):
            try:
                now_utc = datetime.now(UTC)
                sec = get_timeframe_seconds(timeframe)
                lookback = max(200, payload.lookback_bars)
                await market_data.download_historical(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_utc=now_utc - timedelta(seconds=sec * lookback),
                    end_utc=now_utc,
                )
                bars = await candle_repo.get_candles(
                    exchange_id=settings.exchange_id,
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=payload.lookback_bars,
                )
            except Exception:
                pass
    if not bars:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No historical candles stored for {symbol} ({timeframe}).",
        )

    try:
        return await analysis_service.analyze_from_candles(
            symbol=symbol,
            timeframe=timeframe,
            bars=bars,
            strategy_signals=payload.strategy_signals,
            strategy_comparisons=payload.strategy_comparisons,
            lookback_bars=payload.lookback_bars,
        )
    except CandleValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except AIProviderError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except AIResponseValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
