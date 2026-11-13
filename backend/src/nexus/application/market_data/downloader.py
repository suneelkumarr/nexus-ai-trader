"""Historical OHLCV downloader with pagination, validation, and PostgreSQL persistence."""

import asyncio
from datetime import UTC, datetime, timedelta

from nexus.application.market_data.validator import CandleValidator, get_timeframe_seconds
from nexus.core.logging import get_logger
from nexus.domain.interfaces import CandleRepository, PublicExchangeClient
from nexus.domain.models import HistoricalDownloadSummary, OHLCVBar

logger = get_logger(__name__)


class HistoricalDataDownloader:
    """Downloads, validates, and stores historical UTC OHLCV candles."""

    def __init__(
        self,
        *,
        exchange_client: PublicExchangeClient,
        candle_repository: CandleRepository,
        validator: CandleValidator | None = None,
        batch_limit: int = 500,
        inter_request_delay_s: float = 0.1,
    ) -> None:
        self._exchange = exchange_client
        self._repository = candle_repository
        self._validator = validator or CandleValidator()
        self._batch_limit = batch_limit
        self._inter_request_delay_s = inter_request_delay_s

    async def download_range(
        self,
        *,
        symbol: str,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime | None = None,
    ) -> HistoricalDownloadSummary:
        """Download historical closed candles for [start_utc, end_utc] and persist to DB."""
        start_norm = self._validator.ensure_utc(start_utc)
        end_norm = (
            self._validator.ensure_utc(end_utc) if end_utc is not None else datetime.now(UTC)
        )
        step_sec = get_timeframe_seconds(timeframe)
        step_delta = timedelta(seconds=step_sec)

        cursor_ms = int(start_norm.timestamp() * 1000)
        end_ms = int(end_norm.timestamp() * 1000)
        raw_bars: list[OHLCVBar] = []

        while cursor_ms < end_ms:
            batch = await self._exchange.fetch_ohlcv(
                symbol=symbol,
                timeframe=timeframe,
                since_ms=cursor_ms,
                limit=self._batch_limit,
            )
            if not batch:
                break

            in_window = [
                b
                for b in batch
                if start_norm <= self._validator.ensure_utc(b.timestamp) <= end_norm
            ]
            raw_bars.extend(in_window)

            last_ts = self._validator.ensure_utc(batch[-1].timestamp)
            next_cursor_ms = int((last_ts + step_delta).timestamp() * 1000)
            if next_cursor_ms <= cursor_ms or len(batch) < self._batch_limit:
                break
            cursor_ms = next_cursor_ms

            if self._inter_request_delay_s > 0:
                await asyncio.sleep(self._inter_request_delay_s)

        cleaned, report = self._validator.validate_and_clean(
            raw_bars,
            symbol=symbol,
            timeframe=timeframe,
            now_utc=end_norm,
            reject_incomplete=True,
            strict=False,
        )

        if report.missing_timestamps or report.duplicate_timestamps:
            logger.warning(
                "historical_candles_validation_anomalies",
                exchange_id=self._exchange.exchange_id,
                symbol=symbol,
                timeframe=timeframe,
                duplicates=len(report.duplicate_timestamps),
                missing=len(report.missing_timestamps),
                rejected_incomplete=report.rejected_incomplete_count,
            )

        stored_count = await self._repository.upsert_candles(self._exchange.exchange_id, cleaned)

        logger.info(
            "historical_candles_synced",
            exchange_id=self._exchange.exchange_id,
            symbol=symbol,
            timeframe=timeframe,
            fetched=len(raw_bars),
            stored=stored_count,
        )

        return HistoricalDownloadSummary(
            exchange_id=self._exchange.exchange_id,
            symbol=symbol.upper().strip(),
            timeframe=timeframe.lower().strip(),
            fetched_count=len(raw_bars),
            stored_count=stored_count,
            validation=report,
        )

    async def sync_all(
        self,
        *,
        symbols: list[str],
        timeframes: list[str],
        lookback_bars: int = 200,
        end_utc: datetime | None = None,
    ) -> list[HistoricalDownloadSummary]:
        """Incrementally sync historical candles across all configured symbols and timeframes."""
        ref_end = (
            self._validator.ensure_utc(end_utc) if end_utc is not None else datetime.now(UTC)
        )
        summaries: list[HistoricalDownloadSummary] = []

        for symbol in symbols:
            for timeframe in timeframes:
                step_sec = get_timeframe_seconds(timeframe)
                latest = await self._repository.get_latest_timestamp(
                    self._exchange.exchange_id, symbol, timeframe
                )
                if latest is not None:
                    start_utc = latest
                else:
                    start_utc = ref_end - timedelta(seconds=step_sec * lookback_bars)

                summary = await self.download_range(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_utc=start_utc,
                    end_utc=ref_end,
                )
                summaries.append(summary)

        return summaries
