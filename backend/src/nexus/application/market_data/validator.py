"""OHLCV candle validation: UTC, OHLC integrity, gap/duplicate checks, and closed-bar gating."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from nexus.core.exceptions import CandleValidationError, IncompleteCandleError
from nexus.domain.models import CandleValidationReport, OHLCVBar

TIMEFRAME_SECONDS: dict[str, int] = {
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
    "4h": 4 * 60 * 60,
}


def get_timeframe_seconds(timeframe: str) -> int:
    """Resolve timeframe string to integer duration in seconds."""
    tf = timeframe.strip().lower()
    seconds = TIMEFRAME_SECONDS.get(tf)
    if seconds is None:
        raise CandleValidationError(
            f"Unsupported timeframe '{timeframe}'. Supported: {sorted(TIMEFRAME_SECONDS)}"
        )
    return seconds


class CandleValidator:
    """Validates OHLCV bars for UTC consistency, completeness, duplicates, and gaps."""

    @staticmethod
    def ensure_utc(ts: datetime) -> datetime:
        """Require timezone-aware timestamp and normalize to UTC."""
        if ts.tzinfo is None or ts.utcoffset() is None:
            raise CandleValidationError(
                f"Naive timestamp '{ts.isoformat()}' is forbidden; UTC timezone is required."
            )
        return ts.astimezone(UTC)

    @staticmethod
    def validate_ohlc_integrity(bar: OHLCVBar) -> None:
        """Verify high/low bounds and positive prices."""
        max_oc = max(bar.open, bar.close)
        min_oc = min(bar.open, bar.close)
        if bar.high < max_oc or bar.low > min_oc or bar.low > bar.high:
            raise CandleValidationError(
                f"Invalid OHLC envelope for {bar.symbol} at {bar.timestamp.isoformat()}: "
                f"O={bar.open}, H={bar.high}, L={bar.low}, C={bar.close}"
            )

    @classmethod
    def is_candle_closed(
        cls, bar: OHLCVBar, timeframe: str, now_utc: datetime | None = None
    ) -> bool:
        """Return True iff the candle period has fully elapsed by now_utc."""
        if not bar.is_closed:
            return False
        step = timedelta(seconds=get_timeframe_seconds(timeframe))
        ts_utc = cls.ensure_utc(bar.timestamp)
        ref_now = cls.ensure_utc(now_utc) if now_utc is not None else datetime.now(UTC)
        return (ts_utc + step) <= ref_now

    @classmethod
    def validate_and_clean(
        cls,
        bars: Sequence[OHLCVBar],
        *,
        symbol: str,
        timeframe: str,
        now_utc: datetime | None = None,
        reject_incomplete: bool = True,
        strict: bool = False,
    ) -> tuple[list[OHLCVBar], CandleValidationReport]:
        """Normalize UTC, check OHLC, filter incomplete bars, and detect duplicates/gaps."""
        step_sec = get_timeframe_seconds(timeframe)
        step = timedelta(seconds=step_sec)
        ref_now = cls.ensure_utc(now_utc) if now_utc is not None else datetime.now(UTC)

        rejected_incomplete = 0
        duplicate_timestamps: list[datetime] = []
        deduped: dict[datetime, OHLCVBar] = {}

        for bar in bars:
            ts_utc = cls.ensure_utc(bar.timestamp)
            cls.validate_ohlc_integrity(bar)

            if reject_incomplete and not cls.is_candle_closed(bar, timeframe, now_utc=ref_now):
                rejected_incomplete += 1
                continue

            normalized_bar = bar.model_copy(
                update={
                    "symbol": symbol.upper().strip(),
                    "timeframe": timeframe.lower().strip(),
                    "timestamp": ts_utc,
                    "is_closed": cls.is_candle_closed(bar, timeframe, now_utc=ref_now),
                }
            )
            if ts_utc in deduped:
                duplicate_timestamps.append(ts_utc)
            deduped[ts_utc] = normalized_bar

        ordered = [deduped[ts] for ts in sorted(deduped)]
        missing_timestamps: list[datetime] = []

        for idx in range(1, len(ordered)):
            prev_ts = ordered[idx - 1].timestamp
            curr_ts = ordered[idx].timestamp
            cursor = prev_ts + step
            while cursor < curr_ts:
                missing_timestamps.append(cursor)
                cursor += step

        is_clean = not duplicate_timestamps and not missing_timestamps
        report = CandleValidationReport(
            symbol=symbol.upper().strip(),
            timeframe=timeframe.lower().strip(),
            total_input=len(bars),
            valid_closed_count=len(ordered),
            rejected_incomplete_count=rejected_incomplete,
            duplicate_timestamps=duplicate_timestamps,
            missing_timestamps=missing_timestamps,
            is_clean=is_clean,
        )

        if strict and not is_clean:
            raise CandleValidationError(
                f"Strict candle validation failed for {symbol} ({timeframe}): "
                f"duplicates={len(duplicate_timestamps)}, missing={len(missing_timestamps)}"
            )

        return ordered, report

    @classmethod
    def validate_for_signal_generation(
        cls,
        bars: Sequence[OHLCVBar],
        *,
        symbol: str,
        timeframe: str,
        min_bars: int = 1,
        now_utc: datetime | None = None,
        allow_gaps: bool = False,
    ) -> list[OHLCVBar]:
        """Strictly validate bars for strategy evaluation; rejects any incomplete candle."""
        if not bars:
            raise CandleValidationError(
                f"No OHLCV candles available for signal generation on {symbol} ({timeframe})."
            )

        ref_now = cls.ensure_utc(now_utc) if now_utc is not None else datetime.now(UTC)
        for bar in bars:
            if not cls.is_candle_closed(bar, timeframe, now_utc=ref_now):
                raise IncompleteCandleError(
                    f"Incomplete candle at {bar.timestamp.isoformat()} for {symbol} ({timeframe}) "
                    "rejected for signal generation."
                )

        cleaned, report = cls.validate_and_clean(
            bars,
            symbol=symbol,
            timeframe=timeframe,
            now_utc=ref_now,
            reject_incomplete=True,
            strict=False,
        )

        if report.duplicate_timestamps:
            raise CandleValidationError(
                f"Duplicate timestamps detected in signal input for {symbol} ({timeframe})."
            )
        if not allow_gaps and report.missing_timestamps:
            raise CandleValidationError(
                f"Missing {len(report.missing_timestamps)} candle(s) detected for "
                f"{symbol} ({timeframe})."
            )
        if len(cleaned) < min_bars:
            raise CandleValidationError(
                f"Insufficient closed candles for {symbol} ({timeframe}): "
                f"have {len(cleaned)}, need {min_bars}."
            )
        return cleaned
