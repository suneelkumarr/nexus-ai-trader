"""Unified Market Data Service orchestrating public REST, WS, validation, and DB."""

from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd

from nexus.application.market_data.downloader import HistoricalDataDownloader
from nexus.application.market_data.validator import CandleValidator
from nexus.application.market_data.websocket_manager import MarketDataWebSocketManager
from nexus.application.strategy_engine import ohlcv_to_dataframe
from nexus.core.config import Settings
from nexus.core.exceptions import RiskViolationError
from nexus.domain.interfaces import CandleRepository, PublicExchangeClient
from nexus.domain.models import HistoricalDownloadSummary, OHLCVBar, TickerQuote


class MarketDataService:
    """High-level market data facade implementing MarketDataProvider."""

    def __init__(
        self,
        *,
        settings: Settings,
        exchange_client: PublicExchangeClient,
        candle_repository: CandleRepository,
        validator: CandleValidator | None = None,
        downloader: HistoricalDataDownloader | None = None,
        ws_manager: MarketDataWebSocketManager | None = None,
    ) -> None:
        self._settings = settings
        self._exchange = exchange_client
        self._repository = candle_repository
        self._validator = validator or CandleValidator()
        self._downloader = downloader or HistoricalDataDownloader(
            exchange_client=exchange_client,
            candle_repository=candle_repository,
            validator=self._validator,
        )
        self._ws_manager = ws_manager or MarketDataWebSocketManager(
            exchange_client=exchange_client,
            candle_repository=candle_repository,
            validator=self._validator,
            reconnect_min_delay_s=settings.ws_reconnect_min_delay_s,
            reconnect_max_delay_s=settings.ws_reconnect_max_delay_s,
        )

    @property
    def ws_manager(self) -> MarketDataWebSocketManager:
        """Expose managed WebSocket orchestrator."""
        return self._ws_manager

    def _assert_supported(
        self, symbol: str, timeframe: str | None = None
    ) -> tuple[str, str | None]:
        norm_sym = symbol.strip().upper()
        from nexus.application.market_data.multi_market_scanner import SECTOR_MAPPING

        permitted = set(self._settings.allowed_symbols) | set(SECTOR_MAPPING.keys())
        if norm_sym not in permitted:
            raise RiskViolationError(
                f"Symbol '{symbol}' is outside allowed universe {self._settings.allowed_symbols}."
            )
        norm_tf: str | None = None
        if timeframe is not None:
            norm_tf = timeframe.strip().lower()
            if norm_tf not in self._settings.supported_timeframes:
                raise RiskViolationError(
                    f"Timeframe '{timeframe}' not in supported timeframes "
                    f"{self._settings.supported_timeframes}."
                )
        return norm_sym, norm_tf

    async def fetch_ticker(self, symbol: str) -> TickerQuote:
        """Fetch latest real spot ticker quote."""
        norm_sym, _ = self._assert_supported(symbol)
        return await self._exchange.fetch_ticker(norm_sym)

    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "15m",
        limit: int = 100,
        *,
        include_incomplete: bool = False,
        now_utc: datetime | None = None,
    ) -> list[OHLCVBar]:
        """Fetch public OHLCV bars and strip incomplete candles by default."""
        norm_sym, norm_tf = self._assert_supported(symbol, timeframe)
        assert norm_tf is not None
        raw = await self._exchange.fetch_ohlcv(norm_sym, timeframe=norm_tf, limit=limit)
        cleaned, _ = self._validator.validate_and_clean(
            raw,
            symbol=norm_sym,
            timeframe=norm_tf,
            now_utc=now_utc or datetime.now(UTC),
            reject_incomplete=not include_incomplete,
            strict=False,
        )
        return cleaned

    async def get_closed_candles_for_signal(
        self,
        symbol: str,
        timeframe: str,
        *,
        min_bars: int = 25,
        limit: int = 200,
        now_utc: datetime | None = None,
    ) -> tuple[list[OHLCVBar], pd.DataFrame]:
        """Load or fetch closed UTC candles and reject incomplete or gapped data before signals."""
        norm_sym, norm_tf = self._assert_supported(symbol, timeframe)
        assert norm_tf is not None
        ref_now = now_utc or datetime.now(UTC)

        bars = await self._exchange.fetch_ohlcv(norm_sym, timeframe=norm_tf, limit=limit)
        # Filter out the active forming candle, then enforce strict validation
        closed_only, _ = self._validator.validate_and_clean(
            bars,
            symbol=norm_sym,
            timeframe=norm_tf,
            now_utc=ref_now,
            reject_incomplete=True,
            strict=False,
        )
        validated = self._validator.validate_for_signal_generation(
            closed_only,
            symbol=norm_sym,
            timeframe=norm_tf,
            min_bars=min_bars,
            now_utc=ref_now,
            allow_gaps=False,
        )
        await self._repository.upsert_candles(self._exchange.exchange_id, validated)
        return validated, ohlcv_to_dataframe(validated)

    async def download_historical(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime | None = None,
    ) -> HistoricalDownloadSummary:
        """Download historical candles for one symbol/timeframe and store in PostgreSQL."""
        norm_sym, norm_tf = self._assert_supported(symbol, timeframe)
        assert norm_tf is not None
        return await self._downloader.download_range(
            symbol=norm_sym,
            timeframe=norm_tf,
            start_utc=start_utc,
            end_utc=end_utc,
        )

    async def sync_all_historical(
        self, *, lookback_bars: int = 200, end_utc: datetime | None = None
    ) -> list[HistoricalDownloadSummary]:
        """Sync historical candles across all allowed symbols and supported timeframes."""
        return await self._downloader.sync_all(
            symbols=self._settings.allowed_symbols,
            timeframes=self._settings.supported_timeframes,
            lookback_bars=lookback_bars,
            end_utc=end_utc,
        )

    async def get_stored_candles(
        self,
        symbol: str,
        timeframe: str,
        start_utc: datetime | None = None,
        end_utc: datetime | None = None,
        limit: int = 500,
    ) -> list[OHLCVBar]:
        """Query persisted UTC candles from PostgreSQL."""
        norm_sym, norm_tf = self._assert_supported(symbol, timeframe)
        assert norm_tf is not None
        return await self._repository.get_candles(
            exchange_id=self._exchange.exchange_id,
            symbol=norm_sym,
            timeframe=norm_tf,
            start_utc=start_utc,
            end_utc=end_utc,
            limit=limit,
        )

    async def fetch_inr_per_usdt(self) -> Decimal:
        """Fetch live INR per 1 USDT conversion rate."""
        return await self._exchange.fetch_inr_per_usdt()

    async def health_check(self) -> bool:
        """Check upstream public exchange health."""
        return await self._exchange.health_check()

    async def close(self) -> None:
        """Stop WebSocket loops and close underlying exchange sessions."""
        await self._ws_manager.stop()
        await self._exchange.close()
