"""Pure causal technical indicator calculations (no look-ahead bias)."""

import numpy as np
import pandas as pd

from nexus.application.strategy.config import StrategyV1Config


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """Compute causal Exponential Moving Average using pandas ewm(adjust=False)."""
    if period < 1:
        raise ValueError("EMA period must be >= 1")
    return series.astype(float).ewm(span=period, adjust=False, min_periods=period).mean()


def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Compute causal Wilder's Relative Strength Index (RSI)."""
    if period < 2:
        raise ValueError("RSI period must be >= 2")
    closes = series.astype(float)
    delta = closes.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()

    rsi = pd.Series(np.nan, index=closes.index, dtype=float)
    valid = avg_gain.notna() & avg_loss.notna()

    zero_loss = valid & (avg_loss == 0.0)
    both_zero = zero_loss & (avg_gain == 0.0)
    pure_gain = zero_loss & (avg_gain > 0.0)
    standard = valid & (avg_loss > 0.0)

    rsi.loc[both_zero] = 50.0
    rsi.loc[pure_gain] = 100.0
    rs = avg_gain.loc[standard] / avg_loss.loc[standard]
    rsi.loc[standard] = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def compute_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    """Compute causal Wilder's Average True Range (ATR)."""
    if period < 1:
        raise ValueError("ATR period must be >= 1")
    h = high.astype(float)
    low_s = low.astype(float)
    c = close.astype(float)
    prev_close = c.shift(1)

    tr_components = pd.concat(
        [
            (h - low_s).abs(),
            (h - prev_close).abs(),
            (low_s - prev_close).abs(),
        ],
        axis=1,
    )
    true_range = tr_components.max(axis=1)
    return true_range.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def compute_volume_sma(volume: pd.Series, period: int = 20) -> pd.Series:
    """Compute causal rolling Simple Moving Average of volume."""
    if period < 1:
        raise ValueError("Volume SMA period must be >= 1")
    return volume.astype(float).rolling(window=period, min_periods=period).mean()


def compute_bollinger_bands(
    series: pd.Series, period: int = 20, num_std: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Compute causal Bollinger Bands: (middle_sma, upper_band, lower_band)."""
    if period < 2:
        raise ValueError("Bollinger period must be >= 2")
    closes = series.astype(float)
    middle = closes.rolling(window=period, min_periods=period).mean()
    std = closes.rolling(window=period, min_periods=period).std()
    upper = middle + (std * num_std)
    lower = middle - (std * num_std)
    return middle, upper, lower


def compute_v1_indicators(candles_df: pd.DataFrame, config: StrategyV1Config) -> pd.DataFrame:
    """Attach all Strategy V1 indicators strictly causally onto a DataFrame copy."""
    required_cols = {"open", "high", "low", "close", "volume"}
    missing = required_cols - set(candles_df.columns)
    if missing:
        raise ValueError(f"Candles DataFrame missing required columns: {sorted(missing)}")

    result = candles_df.copy()
    result["ema_fast"] = compute_ema(result["close"], config.ema_fast_period)
    result["ema_slow"] = compute_ema(result["close"], config.ema_slow_period)
    result["rsi"] = compute_rsi(result["close"], config.rsi_period)
    result["atr"] = compute_atr(
        result["high"], result["low"], result["close"], config.atr_period
    )
    result["volume_sma"] = compute_volume_sma(result["volume"], config.volume_sma_period)
    return result

