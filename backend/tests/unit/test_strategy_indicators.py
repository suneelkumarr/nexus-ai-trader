"""Unit tests for Strategy V1 causal indicator calculations and zero look-ahead bias."""

import numpy as np
import pandas as pd
import pytest

from nexus.application.strategy.config import StrategyV1Config
from nexus.application.strategy.indicators import (
    compute_atr,
    compute_ema,
    compute_rsi,
    compute_v1_indicators,
    compute_volume_sma,
)


def test_ema_calculation_matches_recursive_formula() -> None:
    prices = pd.Series([float(10 + i) for i in range(30)])
    ema20 = compute_ema(prices, period=20)
    assert ema20.iloc[:19].isna().all()
    assert ema20.iloc[19:].notna().all()

    alpha = 2.0 / (20.0 + 1.0)
    expected = float(prices.iloc[0])
    for val in prices.iloc[1:]:
        expected = alpha * float(val) + (1.0 - alpha) * expected
    assert ema20.iloc[-1] == pytest.approx(expected, rel=1e-12)


def test_rsi_wilder_handles_uptrend_flat_and_mixed_series() -> None:
    rising = pd.Series([float(100 + i) for i in range(25)])
    rsi_up = compute_rsi(rising, period=14)
    assert rsi_up.iloc[-1] == pytest.approx(100.0)

    flat = pd.Series([100.0] * 25)
    rsi_flat = compute_rsi(flat, period=14)
    assert rsi_flat.iloc[-1] == pytest.approx(50.0)

    alternating = pd.Series([100.0 + (2.0 if i % 2 == 0 else -1.0) for i in range(40)])
    rsi_mix = compute_rsi(alternating, period=14)
    assert 40.0 < float(rsi_mix.iloc[-1]) < 80.0


def test_atr_includes_prev_close_gaps_and_volume_sma_exact() -> None:
    n = 30
    high = pd.Series([102.0] * n)
    low = pd.Series([98.0] * n)
    close = pd.Series([100.0] * n)
    # Introduce a sudden upward gap on bar 25 (prev_close=100, low=110, high=114 -> TR=14)
    high.iloc[25:] = 114.0
    low.iloc[25:] = 110.0
    close.iloc[25:] = 112.0

    atr = compute_atr(high, low, close, period=14)
    assert atr.iloc[24] == pytest.approx(4.0, rel=1e-9)
    assert atr.iloc[25] > atr.iloc[24]

    volumes = pd.Series([float(100 + i * 10) for i in range(30)])
    vol_sma = compute_volume_sma(volumes, period=20)
    assert vol_sma.iloc[:19].isna().all()
    assert vol_sma.iloc[19] == pytest.approx(float(volumes.iloc[:20].mean()), rel=1e-12)
    assert vol_sma.iloc[-1] == pytest.approx(float(volumes.iloc[10:30].mean()), rel=1e-12)


def test_indicators_have_zero_lookahead_bias() -> None:
    rng = np.random.default_rng(42)
    n = 90
    closes = 100.0 + np.cumsum(rng.normal(0.1, 1.2, size=n))
    df_full = pd.DataFrame(
        {
            "open": closes - 0.5,
            "high": closes + 1.5,
            "low": closes - 1.5,
            "close": closes,
            "volume": rng.uniform(100.0, 500.0, size=n),
        }
    )

    cutoff = 65
    df_truncated = df_full.iloc[:cutoff].copy()
    df_mutated_future = df_full.copy()
    df_mutated_future.loc[cutoff:, "close"] *= 5.0
    df_mutated_future.loc[cutoff:, "high"] *= 6.0
    df_mutated_future.loc[cutoff:, "volume"] *= 20.0

    cfg = StrategyV1Config()
    ind_trunc = compute_v1_indicators(df_truncated, cfg)
    ind_future = compute_v1_indicators(df_mutated_future, cfg)

    for col in ("ema_fast", "ema_slow", "rsi", "atr", "volume_sma"):
        pd.testing.assert_series_equal(
            ind_trunc[col],
            ind_future[col].iloc[:cutoff],
            check_exact=False,
            rtol=1e-12,
            atol=1e-12,
        )

