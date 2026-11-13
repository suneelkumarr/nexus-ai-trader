"""Quantitative strategy engine powered by pandas and numpy."""

import numpy as np
import pandas as pd

from nexus.domain.enums import SignalAction
from nexus.domain.models import OHLCVBar, TradingSignal


def ohlcv_to_dataframe(bars: list[OHLCVBar]) -> pd.DataFrame:
    """Convert validated domain OHLCV bars into a sorted pandas DataFrame."""
    records = [
        {
            "timestamp": bar.timestamp,
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": float(bar.volume),
        }
        for bar in bars
    ]
    df = pd.DataFrame.from_records(records)
    if df.empty:
        return df
    return df.sort_values("timestamp").reset_index(drop=True)


class EmaCrossoverStrategy:
    """Baseline deterministic EMA crossover spot strategy using pandas/numpy."""

    def __init__(self, *, fast_span: int = 9, slow_span: int = 21) -> None:
        if fast_span >= slow_span:
            raise ValueError("fast_span must be strictly less than slow_span")
        self.fast_span = fast_span
        self.slow_span = slow_span
        self.name = f"ema_crossover_{fast_span}_{slow_span}"

    def evaluate(self, symbol: str, candles_df: pd.DataFrame) -> TradingSignal:
        """Compute fast/slow EMAs and emit BUY, SELL, or HOLD."""
        if len(candles_df) < self.slow_span + 2 or "close" not in candles_df.columns:
            return TradingSignal(
                symbol=symbol,
                action=SignalAction.HOLD,
                confidence=0.0,
                strategy_name=self.name,
                reason="Insufficient OHLCV history for EMA calculation.",
            )

        closes = candles_df["close"].astype(float)
        ema_fast = closes.ewm(span=self.fast_span, adjust=False).mean()
        ema_slow = closes.ewm(span=self.slow_span, adjust=False).mean()
        spread = (ema_fast - ema_slow) / np.where(ema_slow > 0, ema_slow, 1.0)

        prev_diff = float(spread.iloc[-2])
        curr_diff = float(spread.iloc[-1])
        confidence = float(np.clip(abs(curr_diff) * 50.0, 0.1, 1.0))

        if prev_diff <= 0.0 and curr_diff > 0.0:
            return TradingSignal(
                symbol=symbol,
                action=SignalAction.BUY,
                confidence=confidence,
                strategy_name=self.name,
                reason="Bullish fast/slow EMA crossover.",
            )
        if prev_diff >= 0.0 and curr_diff < 0.0:
            return TradingSignal(
                symbol=symbol,
                action=SignalAction.SELL,
                confidence=confidence,
                strategy_name=self.name,
                reason="Bearish fast/slow EMA crossunder.",
            )
        return TradingSignal(
            symbol=symbol,
            action=SignalAction.HOLD,
            confidence=round(confidence * 0.5, 4),
            strategy_name=self.name,
            reason="No EMA crossover trigger on latest bar.",
        )

