"""Extensive unit tests for NexusStrategyV1 signal generation, exits, and boundaries."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from nexus.application.risk_guard import SpotSignalRiskApprover
from nexus.application.strategy.config import StrategyV1Config
from nexus.application.strategy.indicators import compute_v1_indicators
from nexus.application.strategy.v1_engine import NexusStrategyV1
from nexus.application.strategy_engine import ohlcv_to_dataframe
from nexus.core.config import Settings
from nexus.core.exceptions import CandleValidationError, IncompleteCandleError
from nexus.domain.enums import SignalDirection
from nexus.domain.models import AssetHolding, OHLCVBar, PortfolioState, PositionContext


def _build_bars(
    closes: list[float],
    *,
    volumes: list[float] | None = None,
    lows: list[float] | None = None,
    highs: list[float] | None = None,
    symbol: str = "BTC/USDT",
    timeframe: str = "15m",
    start: datetime | None = None,
) -> list[OHLCVBar]:
    t0 = start or datetime(2026, 11, 12, 0, 0, tzinfo=UTC)
    bars: list[OHLCVBar] = []
    for idx, c in enumerate(closes):
        v = volumes[idx] if volumes is not None else 100.0
        h = highs[idx] if highs is not None else c + 1.0
        low_p = lows[idx] if lows is not None else c - 1.0
        o_p = c - 0.2
        bars.append(
            OHLCVBar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=t0 + timedelta(minutes=15 * idx),
                open=Decimal(str(round(o_p, 4))),
                high=Decimal(str(round(h, 4))),
                low=Decimal(str(round(low_p, 4))),
                close=Decimal(str(round(c, 4))),
                volume=Decimal(str(round(v, 4))),
            )
        )
    return bars


def _find_crossover_series(
    *, final_volume: float = 400.0, push_overbought: bool = False
) -> tuple[list[OHLCVBar], datetime]:
    """Build deterministic bars where EMA20 crosses above EMA50 on the final bar."""
    closes: list[float] = [120.0 - 0.1 * i for i in range(25)] + [
        117.5 - 0.3 * i for i in range(30)
    ]
    cfg = StrategyV1Config()
    found = False

    if push_overbought:
        # Rapid vertical rally crosses EMA20 > EMA50 while pushing RSI14 > 70
        for _step in range(30):
            closes.append(closes[-1] + 2.2)
            bars_chk = _build_bars(closes)
            ind = compute_v1_indicators(ohlcv_to_dataframe(bars_chk), cfg)
            prev_f = float(ind["ema_fast"].iloc[-2])
            prev_s = float(ind["ema_slow"].iloc[-2])
            curr_f = float(ind["ema_fast"].iloc[-1])
            curr_s = float(ind["ema_slow"].iloc[-1])
            curr_rsi = float(ind["rsi"].iloc[-1])
            if prev_f <= prev_s and curr_f > curr_s and curr_rsi > 70.0:
                found = True
                break
    else:
        # Oscillating recovery crosses EMA20 > EMA50 with RSI14 cleanly in [50, 70]
        for step in range(50):
            closes.append(closes[-1] + (0.75 if step % 3 != 2 else -0.45))
            bars_chk = _build_bars(closes)
            ind = compute_v1_indicators(ohlcv_to_dataframe(bars_chk), cfg)
            prev_f = float(ind["ema_fast"].iloc[-2])
            prev_s = float(ind["ema_slow"].iloc[-2])
            curr_f = float(ind["ema_fast"].iloc[-1])
            curr_s = float(ind["ema_slow"].iloc[-1])
            curr_rsi = float(ind["rsi"].iloc[-1])
            if prev_f <= prev_s and curr_f > curr_s and 50.0 <= curr_rsi <= 70.0:
                found = True
                break

    assert found, "Failed to construct deterministic crossover test series"
    volumes = [100.0] * (len(closes) - 1) + [final_volume]
    bars = _build_bars(closes, volumes=volumes)
    now_utc = bars[-1].timestamp + timedelta(minutes=15)
    return bars, now_utc


def _make_engine(
    *,
    config: StrategyV1Config | None = None,
    approved: bool = True,
    reject_reason: str | None = "Risk limit reached",
) -> NexusStrategyV1:
    class _StubRisk:
        def approve_entry(
            self,
            *,
            symbol: str,
            timestamp: datetime,
            entry_price: Decimal,
            stop_price: Decimal,
            portfolio: PortfolioState,
        ) -> tuple[bool, str | None]:
            return (True, None) if approved else (False, reject_reason)

    return NexusStrategyV1(config=config, risk_approver=_StubRisk())


def test_long_entry_emitted_with_all_required_fields_when_conditions_met(
    initial_portfolio: PortfolioState,
) -> None:
    bars, now_utc = _find_crossover_series(final_volume=500.0)
    engine = NexusStrategyV1(
        config=StrategyV1Config(),
        risk_approver=SpotSignalRiskApprover(allowed_symbols=["BTC/USDT", "ETH/USDT", "SOL/USDT"]),
    )

    res = engine.evaluate_bars(
        symbol="BTC/USDT",
        timeframe="15m",
        bars=bars,
        portfolio=initial_portfolio,
        now_utc=now_utc,
    )

    assert res.status == "entry_signal"
    assert res.signal is not None
    sig = res.signal
    assert sig.symbol == "BTC/USDT"
    assert sig.timestamp == bars[-1].timestamp
    assert sig.direction == SignalDirection.LONG
    assert sig.entry_price == bars[-1].close
    assert Decimal("0") < sig.stop_price < sig.entry_price
    assert sig.strategy_name == "nexus_ema_rsi_atr_vol_v1"
    assert "EMA20 crossed above EMA50" in sig.reason


def test_long_entry_blocked_when_volume_or_rsi_or_position_or_risk_fails(
    initial_portfolio: PortfolioState,
) -> None:
    # 1. Low volume (below SMA20)
    bars_low_vol, now_utc = _find_crossover_series(final_volume=50.0)
    engine_low_vol = _make_engine()
    res_vol = engine_low_vol.evaluate_bars(
        symbol="BTC/USDT",
        timeframe="15m",
        bars=bars_low_vol,
        portfolio=initial_portfolio,
        now_utc=now_utc,
    )
    assert res_vol.status == "no_signal"
    assert res_vol.signal is None

    # 2. RSI > 70 (overbought) or no crossover inside range
    bars_ob, now_ob = _find_crossover_series(final_volume=500.0, push_overbought=True)
    res_ob = _make_engine().evaluate_bars(
        symbol="BTC/USDT",
        timeframe="15m",
        bars=bars_ob,
        portfolio=initial_portfolio,
        now_utc=now_ob,
    )
    assert res_ob.signal is None

    # 3. Existing spot holding in portfolio blocks entry
    bars_ok, now_ok = _find_crossover_series(final_volume=500.0)
    portfolio_with_btc = initial_portfolio.model_copy(
        update={
            "holdings": {
                "BTC": AssetHolding(
                    asset="BTC", free_qty=Decimal("0.01"), avg_entry_price_usdt=Decimal("110")
                )
            }
        }
    )
    res_existing = _make_engine().evaluate_bars(
        symbol="BTC/USDT",
        timeframe="15m",
        bars=bars_ok,
        portfolio=portfolio_with_btc,
        now_utc=now_ok,
    )
    assert res_existing.status == "no_signal"
    assert res_existing.signal is None

    # 4. Risk manager rejection suppresses signal
    res_risk = _make_engine(approved=False, reject_reason="Daily drawdown cap").evaluate_bars(
        symbol="BTC/USDT",
        timeframe="15m",
        bars=bars_ok,
        portfolio=initial_portfolio,
        now_utc=now_ok,
    )
    assert res_risk.status == "risk_rejected"
    assert res_risk.rejection_reason == "Daily drawdown cap"
    assert res_risk.signal is None


def test_candle_boundary_incomplete_future_and_duplicate_suppression(
    initial_portfolio: PortfolioState,
) -> None:
    bars, exact_close_utc = _find_crossover_series(final_volume=500.0)
    engine = _make_engine()

    # 1 second before close -> incomplete candle must be rejected
    with pytest.raises(IncompleteCandleError):
        engine.evaluate_bars(
            symbol="BTC/USDT",
            timeframe="15m",
            bars=bars,
            portfolio=initial_portfolio,
            now_utc=exact_close_utc - timedelta(seconds=1),
        )

    # Future bar strictly after now_utc -> forbidden
    with pytest.raises(CandleValidationError):
        engine.evaluate_bars(
            symbol="BTC/USDT",
            timeframe="15m",
            bars=bars,
            portfolio=initial_portfolio,
            now_utc=bars[-1].timestamp - timedelta(minutes=1),
        )

    # Exact close boundary (ts + 15m == now_utc) -> accepted
    first = engine.evaluate_bars(
        symbol="BTC/USDT",
        timeframe="15m",
        bars=bars,
        portfolio=initial_portfolio,
        now_utc=exact_close_utc,
    )
    assert first.status == "entry_signal"
    assert first.signal is not None

    # Re-evaluating the exact same candle -> duplicate suppressed
    duplicate = engine.evaluate_bars(
        symbol="BTC/USDT",
        timeframe="15m",
        bars=bars,
        portfolio=initial_portfolio,
        now_utc=exact_close_utc + timedelta(minutes=5),
    )
    assert duplicate.status == "duplicate_suppressed"
    assert duplicate.signal is None


def test_exit_stop_loss_trailing_stop_and_trend_reversal(
    initial_portfolio: PortfolioState,
) -> None:
    bars, now_utc = _find_crossover_series(final_volume=500.0)
    entry_bar = bars[-1]

    # 1. Initial stop-loss trigger
    pos_sl = PositionContext(
        symbol="BTC/USDT",
        entry_timestamp=entry_bar.timestamp,
        entry_price=entry_bar.close,
        quantity=Decimal("0.1"),
        initial_stop_price=Decimal("108.00"),
        trailing_stop_price=Decimal("108.00"),
        highest_price_since_entry=entry_bar.high,
    )
    next_ts = entry_bar.timestamp + timedelta(minutes=15)
    drop_bar = OHLCVBar(
        symbol="BTC/USDT",
        timeframe="15m",
        timestamp=next_ts,
        open=Decimal("112.0"),
        high=Decimal("112.5"),
        low=Decimal("107.5"),  # Breaches initial stop 108.00
        close=Decimal("108.2"),
        volume=Decimal("200"),
    )
    res_sl = _make_engine().evaluate_bars(
        symbol="BTC/USDT",
        timeframe="15m",
        bars=[*bars, drop_bar],
        portfolio=initial_portfolio,
        position=pos_sl,
        now_utc=next_ts + timedelta(minutes=15),
    )
    assert res_sl.status == "exit_signal"
    assert res_sl.signal is not None
    assert res_sl.signal.direction == SignalDirection.EXIT_LONG
    assert "Stop-loss" in res_sl.signal.reason

    # 2. Trailing stop ratchets upward on rally, then triggers on pullback
    engine_trail = _make_engine()
    rally_bar = OHLCVBar(
        symbol="BTC/USDT",
        timeframe="15m",
        timestamp=next_ts,
        open=entry_bar.close,
        high=entry_bar.close + Decimal("15.0"),
        low=entry_bar.close,
        close=entry_bar.close + Decimal("14.0"),
        volume=Decimal("250"),
    )
    hold_res = engine_trail.evaluate_bars(
        symbol="BTC/USDT",
        timeframe="15m",
        bars=[*bars, rally_bar],
        portfolio=initial_portfolio,
        position=pos_sl,
        now_utc=next_ts + timedelta(minutes=15),
    )
    assert hold_res.status == "no_signal"
    assert hold_res.updated_position is not None
    ratcheted_stop = hold_res.updated_position.trailing_stop_price
    assert ratcheted_stop > pos_sl.initial_stop_price

    pullback_ts = next_ts + timedelta(minutes=15)
    pullback_bar = OHLCVBar(
        symbol="BTC/USDT",
        timeframe="15m",
        timestamp=pullback_ts,
        open=rally_bar.close,
        high=rally_bar.close,
        low=ratcheted_stop - Decimal("0.5"),
        close=ratcheted_stop - Decimal("0.2"),
        volume=Decimal("220"),
    )
    res_trail = engine_trail.evaluate_bars(
        symbol="BTC/USDT",
        timeframe="15m",
        bars=[*bars, rally_bar, pullback_bar],
        portfolio=initial_portfolio,
        position=hold_res.updated_position,
        now_utc=pullback_ts + timedelta(minutes=15),
    )
    assert res_trail.status == "exit_signal"
    assert res_trail.signal is not None
    assert "Trailing stop" in res_trail.signal.reason

    # 3. Confirmed trend reversal (EMA20 crosses below EMA50 without hitting wide stop)
    engine_rev = _make_engine()
    pos_wide = PositionContext(
        symbol="BTC/USDT",
        entry_timestamp=entry_bar.timestamp,
        entry_price=entry_bar.close,
        quantity=Decimal("0.1"),
        initial_stop_price=Decimal("50.0"),
        trailing_stop_price=Decimal("50.0"),
        highest_price_since_entry=entry_bar.high,
    )
    # Append gradual decline bars until EMA20 crosses below EMA50
    seq = list(bars)
    curr_pos = pos_wide
    reversal_res = None
    for i in range(1, 35):
        ts_i = entry_bar.timestamp + timedelta(minutes=15 * i)
        c_val = float(seq[-1].close) - 0.6
        seq.append(
            OHLCVBar(
                symbol="BTC/USDT",
                timeframe="15m",
                timestamp=ts_i,
                open=Decimal(str(round(c_val + 0.2, 4))),
                high=Decimal(str(round(c_val + 0.5, 4))),
                low=Decimal(str(round(c_val - 0.5, 4))),
                close=Decimal(str(round(c_val, 4))),
                volume=Decimal("120"),
            )
        )
        # Keep trailing stop pinned low so only trend reversal triggers
        curr_pos = curr_pos.model_copy(
            update={"trailing_stop_price": Decimal("50.0"), "initial_stop_price": Decimal("50.0")}
        )
        reversal_res = engine_rev.evaluate_bars(
            symbol="BTC/USDT",
            timeframe="15m",
            bars=seq,
            portfolio=initial_portfolio,
            position=curr_pos,
            now_utc=ts_i + timedelta(minutes=15),
        )
        if reversal_res.status == "exit_signal":
            break
    assert reversal_res is not None
    assert reversal_res.status == "exit_signal"
    assert reversal_res.signal is not None
    assert "trend reversal" in reversal_res.signal.reason.lower()


def test_strategy_v1_configurable_parameters_and_settings_validation() -> None:
    cfg = StrategyV1Config(
        ema_fast_period=12,
        ema_slow_period=26,
        rsi_period=10,
        rsi_entry_min=52.0,
        rsi_entry_max=68.0,
        atr_period=10,
        volume_sma_period=15,
        stop_atr_multiplier=Decimal("1.5"),
        trailing_atr_multiplier=Decimal("2.0"),
    )
    assert cfg.min_candles_required == 27

    with pytest.raises(ValueError):
        StrategyV1Config(ema_fast_period=50, ema_slow_period=20)

    with pytest.raises(ValueError):
        StrategyV1Config(rsi_entry_min=75.0, rsi_entry_max=60.0)

    settings = Settings(_env_file=None, strategy_v1=cfg)
    assert settings.strategy_v1.ema_fast_period == 12

