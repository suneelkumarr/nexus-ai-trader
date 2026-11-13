"""Typed exception hierarchy for NEXUS AI TRADER."""


class NexusError(Exception):
    """Base exception for all NEXUS AI TRADER domain and infrastructure errors."""


class ConfigurationInvariantError(NexusError):
    """Raised when configuration violates paper-only or spot-only invariants."""


class RiskViolationError(NexusError):
    """Raised when an order or action violates spot-only or portfolio risk limits."""


class InsufficientBalanceError(RiskViolationError):
    """Raised when virtual cash or spot asset balance is insufficient."""


class LiveTradingForbiddenError(RiskViolationError):
    """Raised if any component attempts live execution, leverage, futures, or withdrawals."""


class MarketDataUnavailableError(NexusError):
    """Raised when real exchange market data cannot be fetched or fails validation."""


class RateLimitError(MarketDataUnavailableError):
    """Raised when upstream exchange rate limits are exceeded after retries."""


class CandleValidationError(NexusError):
    """Raised when OHLCV candles fail integrity, gap, duplicate, or UTC checks."""


class IncompleteCandleError(CandleValidationError):
    """Raised when an unclosed/in-progress candle is supplied for signal generation."""


class DatabaseUnavailableError(NexusError):
    """Raised when PostgreSQL cannot be reached or fails health checks."""


class AIProviderError(NexusError):
    """Raised when the upstream AI analysis API fails, times out, or is unconfigured."""


class AIResponseValidationError(NexusError):
    """Raised when an AI model response fails schema, price, or safety validation."""


class BacktestValidationError(NexusError):
    """Raised when historical backtest inputs or split ratios are invalid."""


class BacktestBiasError(BacktestValidationError):
    """Raised on look-ahead, survivorship, or test-period optimization violations."""


