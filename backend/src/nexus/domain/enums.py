"""Domain enumerations enforcing spot-only and paper-only trading semantics."""

from enum import StrEnum


class TradingMode(StrEnum):
    """Execution environment mode — strictly PAPER only."""

    PAPER = "paper"


class MarketType(StrEnum):
    """Market classification — strictly SPOT only."""

    SPOT = "spot"


class OrderSide(StrEnum):
    """Spot order direction."""

    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    """Supported spot order types."""

    MARKET = "market"
    LIMIT = "limit"


class OrderStatus(StrEnum):
    """Lifecycle states of a virtual paper order."""

    PENDING = "pending"
    FILLED = "filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class SignalAction(StrEnum):
    """Action emitted by an automated quantitative strategy."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class SignalDirection(StrEnum):
    """Directional intent of Strategy Engine signals (spot and futures)."""

    LONG = "long"
    EXIT_LONG = "exit_long"
    SHORT = "short"
    EXIT_SHORT = "exit_short"
    FLAT = "flat"


class MarketRegime(StrEnum):
    """Advisory market regime classification derived from validated indicators."""

    TRENDING_BULLISH = "trending_bullish"
    TRENDING_BEARISH = "trending_bearish"
    RANGING = "ranging"
    VOLATILE_BREAKOUT = "volatile_breakout"
    HIGH_VOLATILITY_CHOP = "high_volatility_chop"
    LOW_VOLATILITY_COMPRESSION = "low_volatility_compression"
    UNCERTAIN = "uncertain"


class TrendDirection(StrEnum):
    """Advisory directional bias observed in historical price action."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class VolatilityLevel(StrEnum):
    """Advisory volatility regime categorization."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    EXTREME = "extreme"


