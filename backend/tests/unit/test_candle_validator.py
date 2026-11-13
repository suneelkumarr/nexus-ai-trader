"""Unit tests for OHLCV CandleValidator (UTC, duplicates, gaps, incomplete-candle gating)."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from nexus.application.market_data.validator import CandleValidator
from nexus.core.exceptions import CandleValidationError, IncompleteCandleError
from nexus.domain.models import OHLCVBar


def _bar(
    ts: datetime,
    *,
    symbol: str = "BTC/USDT",
    timeframe: str = "15m",
    close: str = "90000",
    is_closed: bool = True,
) -> OHLCVBar:
    return OHLCVBar(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=ts,
        open=Decimal("89900"),
        high=Decimal("90100"),
        low=Decimal("89800"),
        close=Decimal(close),
        volume=Decimal("12.5"),
        is_closed=is_closed,
    )


def test_validator_rejects_naive_datetime_and_normalizes_utc() -> None:
    naive = _bar(datetime(2026, 11, 12, 10, 0, 0))
    with pytest.raises(CandleValidationError):
        CandleValidator.validate_and_clean(
            [naive],
            symbol="BTC/USDT",
            timeframe="15m",
            now_utc=datetime(2026, 11, 12, 12, 0, tzinfo=UTC),
        )

    ist = timezone(timedelta(hours=5, minutes=30))
    ist_bar = _bar(datetime(2026, 11, 12, 15, 30, tzinfo=ist))
    cleaned, report = CandleValidator.validate_and_clean(
        [ist_bar],
        symbol="BTC/USDT",
        timeframe="15m",
        now_utc=datetime(2026, 11, 12, 12, 0, tzinfo=UTC),
    )
    assert report.valid_closed_count == 1
    assert cleaned[0].timestamp == datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
    assert cleaned[0].timestamp.tzinfo == UTC


def test_validator_detects_duplicates_and_missing_gaps() -> None:
    t0 = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
    t1 = t0 + timedelta(minutes=15)
    # t2 (10:30) is intentionally missing!
    t3 = t0 + timedelta(minutes=45)

    bars = [
        _bar(t0, close="90000"),
        _bar(t1, close="90010"),
        _bar(t1, close="90025"),  # duplicate timestamp
        _bar(t3, close="90050"),
    ]
    cleaned, report = CandleValidator.validate_and_clean(
        bars,
        symbol="BTC/USDT",
        timeframe="15m",
        now_utc=t3 + timedelta(minutes=20),
    )
    assert len(cleaned) == 3
    assert cleaned[1].close == Decimal("90025")
    assert report.duplicate_timestamps == [t1]
    assert report.missing_timestamps == [t0 + timedelta(minutes=30)]
    assert report.is_clean is False


def test_validator_rejects_incomplete_candles_for_signal_generation() -> None:
    t0 = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    # Current time is 11:20 UTC -> 11:00 1h candle has not closed yet (closes at 12:00)
    now_utc = datetime(2026, 11, 12, 11, 20, tzinfo=UTC)

    bars = [_bar(t0, timeframe="1h"), _bar(t1, timeframe="1h")]
    with pytest.raises(IncompleteCandleError):
        CandleValidator.validate_for_signal_generation(
            bars, symbol="BTC/USDT", timeframe="1h", min_bars=1, now_utc=now_utc
        )

    cleaned, report = CandleValidator.validate_and_clean(
        bars, symbol="BTC/USDT", timeframe="1h", now_utc=now_utc, reject_incomplete=True
    )
    assert len(cleaned) == 1
    assert report.rejected_incomplete_count == 1


@pytest.mark.parametrize("timeframe", ["5m", "15m", "1h", "4h"])
def test_validator_supports_all_required_timeframes(timeframe: str) -> None:
    t0 = datetime(2026, 11, 12, 0, 0, tzinfo=UTC)
    bar = _bar(t0, timeframe=timeframe)
    validated = CandleValidator.validate_for_signal_generation(
        [bar],
        symbol="ETH/USDT",
        timeframe=timeframe,
        min_bars=1,
        now_utc=datetime(2026, 11, 12, 12, 0, tzinfo=UTC),
    )
    assert len(validated) == 1


def test_validator_rejects_invalid_ohlc_envelope() -> None:
    t0 = datetime(2026, 11, 12, 10, 0, tzinfo=UTC)
    bad = OHLCVBar(
        symbol="SOL/USDT",
        timeframe="5m",
        timestamp=t0,
        open=Decimal("150"),
        high=Decimal("140"),  # high < open is invalid
        low=Decimal("130"),
        close=Decimal("145"),
        volume=Decimal("5"),
    )
    with pytest.raises(CandleValidationError):
        CandleValidator.validate_and_clean(
            [bad], symbol="SOL/USDT", timeframe="5m", now_utc=t0 + timedelta(minutes=10)
        )
