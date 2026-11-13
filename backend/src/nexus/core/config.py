"""Application configuration with strict paper-only and spot-only invariants."""

from decimal import Decimal
from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, quote_plus, urlencode, urlsplit, urlunsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from nexus.core.ai_config import AIAnalysisConfig
from nexus.core.exceptions import ConfigurationInvariantError
from nexus.core.risk_config import RiskConfig
from nexus.core.strategy_config import StrategyV1Config

DEFAULT_ALLOWED_SYMBOLS: tuple[str, ...] = ("BTC/USDT", "ETH/USDT", "SOL/USDT")
DEFAULT_SUPPORTED_TIMEFRAMES: tuple[str, ...] = ("5m", "15m", "1h", "4h")


def _normalize_database_url(url: str, *, target_driver: Literal["asyncpg", "psycopg"]) -> str:
    """Normalize PostgreSQL dialects and SSL query parameters for asyncpg or psycopg."""
    stripped = url.strip()
    parsed = urlsplit(stripped)
    scheme = parsed.scheme.lower()
    base_scheme = scheme.split("+", maxsplit=1)[0]
    if base_scheme not in {"postgres", "postgresql"}:
        if target_driver == "psycopg":
            return stripped.replace("+asyncpg", "+psycopg").replace("+aiosqlite", "")
        return stripped

    target_scheme = f"postgresql+{target_driver}"

    query_items = parse_qsl(parsed.query, keep_blank_values=True)
    normalized_query: list[tuple[str, str]] = []
    for key, value in query_items:
        lowered = key.lower()
        if target_driver == "asyncpg" and lowered == "sslmode":
            normalized_query.append(("ssl", value))
        elif target_driver == "psycopg" and lowered == "ssl":
            normalized_query.append(("sslmode", value))
        else:
            normalized_query.append((key, value))

    return urlunsplit(
        (
            target_scheme,
            parsed.netloc,
            parsed.path,
            urlencode(normalized_query),
            parsed.fragment,
        )
    )


class Settings(BaseSettings):
    """Validated runtime settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_nested_delimiter="__",
        extra="ignore",
    )

    # --- Application ---
    app_name: str = "nexus-ai-trader"
    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_version: str = "0.1.0"
    api_host: str = "0.0.0.0"
    api_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        validation_alias=AliasChoices("api_port", "API_PORT", "port", "PORT"),
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"]
    )
    # Narrow by default; set to an empty string to disable regex matching entirely.
    cors_origin_regex: str = r"^https://nexus-ai-trader[a-z0-9-]*\.onrender\.com$"
    trust_proxy_headers: bool = False
    api_auth_token: SecretStr = Field(default=SecretStr(""))
    rate_limit_per_minute: int = Field(default=120, ge=10, le=10000)
    max_body_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)

    # --- Non-Negotiable Trading Invariants ---
    trading_mode: str = "paper"
    market_type: str = "spot"
    live_trading_enabled: bool = False
    allow_leverage: bool = False
    allow_futures: bool = False
    allow_withdrawals: bool = False
    # Isolated-margin futures SIMULATION is paper-only and never routes orders to
    # an exchange. Live futures remain forbidden by `allow_futures` above.
    paper_futures_enabled: bool = True

    # --- Virtual Portfolio & Asset Universe ---
    initial_capital_inr: Decimal = Field(default=Decimal("10000.00"))
    base_currency: str = "INR"
    allowed_symbols: list[str] = Field(default_factory=lambda: list(DEFAULT_ALLOWED_SYMBOLS))
    supported_timeframes: list[str] = Field(
        default_factory=lambda: list(DEFAULT_SUPPORTED_TIMEFRAMES)
    )
    default_timeframe: str = "15m"
    paper_fee_bps: Decimal = Field(default=Decimal("10.0"), ge=Decimal("0"))
    paper_slippage_bps: Decimal = Field(default=Decimal("5.0"), ge=Decimal("0"))
    risk: RiskConfig = Field(default_factory=RiskConfig)
    strategy_v1: StrategyV1Config = Field(default_factory=StrategyV1Config)
    ai: AIAnalysisConfig = Field(default_factory=AIAnalysisConfig)

    # --- Exchange (Public Spot Market Data Only — No Private API Keys) ---
    exchange_id: str = "binance"
    exchange_timeout_ms: int = Field(default=10000, ge=1000, le=60000)
    market_data_max_retries: int = Field(default=3, ge=0, le=10)
    market_data_backoff_base_s: float = Field(default=0.5, ge=0.05, le=10.0)
    ws_enabled: bool = True
    ws_reconnect_min_delay_s: float = Field(default=1.0, ge=0.1, le=30.0)
    ws_reconnect_max_delay_s: float = Field(default=30.0, ge=1.0, le=300.0)

    # --- PostgreSQL Database ---
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = "nexus_trader"
    postgres_user: str = "nexus"
    postgres_password: SecretStr = Field(default=SecretStr(""))
    database_echo: bool = False
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=10, ge=0, le=100)
    database_url_override: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "database_url_override", "DATABASE_URL_OVERRIDE", "database_url", "DATABASE_URL"
        ),
    )

    @field_validator("allowed_symbols")
    @classmethod
    def validate_spot_symbols(cls, symbols: list[str]) -> list[str]:
        """Normalize and verify all trading pairs are valid spot symbols."""
        if not symbols:
            raise ConfigurationInvariantError("allowed_symbols cannot be empty")
        normalized: list[str] = []
        for raw in symbols:
            symbol = raw.strip().upper()
            if "/" not in symbol or ":" in symbol or "PERP" in symbol:
                raise ConfigurationInvariantError(
                    f"Invalid spot symbol '{raw}'. Only spot pairs like 'BTC/USDT' are permitted."
                )
            base, quote = symbol.split("/", maxsplit=1)
            if not base or not quote:
                raise ConfigurationInvariantError(f"Malformed symbol '{raw}'")
            normalized.append(f"{base}/{quote}")
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def enforce_paper_spot_invariants(self) -> "Settings":
        """Fail fast if any configuration attempts live, leveraged, futures, or withdrawal mode."""
        if self.trading_mode.strip().lower() != "paper":
            raise ConfigurationInvariantError(
                f"TRADING_MODE must be 'paper', got '{self.trading_mode}'."
            )
        if self.market_type.strip().lower() != "spot":
            raise ConfigurationInvariantError(
                f"MARKET_TYPE must be 'spot', got '{self.market_type}'."
            )
        if self.live_trading_enabled:
            raise ConfigurationInvariantError("LIVE_TRADING_ENABLED must remain false.")
        if self.allow_leverage:
            raise ConfigurationInvariantError("ALLOW_LEVERAGE must remain false.")
        if self.allow_futures:
            raise ConfigurationInvariantError("ALLOW_FUTURES must remain false.")
        if self.allow_withdrawals:
            raise ConfigurationInvariantError("ALLOW_WITHDRAWALS must remain false.")
        if self.base_currency.strip().upper() != "INR":
            raise ConfigurationInvariantError("BASE_CURRENCY must be 'INR'.")
        if self.initial_capital_inr <= Decimal("0"):
            raise ConfigurationInvariantError("INITIAL_CAPITAL_INR must be positive.")

        allowed_tf = set(DEFAULT_SUPPORTED_TIMEFRAMES)
        normalized_tf = [tf.strip().lower() for tf in self.supported_timeframes]
        if not normalized_tf or not set(normalized_tf).issubset(allowed_tf):
            raise ConfigurationInvariantError(
                f"SUPPORTED_TIMEFRAMES must be a non-empty subset of {sorted(allowed_tf)}."
            )
        self.supported_timeframes = list(dict.fromkeys(normalized_tf))
        if self.default_timeframe.strip().lower() not in self.supported_timeframes:
            raise ConfigurationInvariantError(
                f"DEFAULT_TIMEFRAME '{self.default_timeframe}' must be in "
                f"{self.supported_timeframes}."
            )
        self.default_timeframe = self.default_timeframe.strip().lower()

        # Cloud deployment convenience: accept NVIDIA_API_KEY as alias for ai.api_key
        import os

        env_key = os.environ.get("NVIDIA_API_KEY", "").strip()
        if env_key and not self.ai.api_key.get_secret_value().strip():
            self.ai.api_key = SecretStr(env_key)

        self.trading_mode = "paper"
        self.market_type = "spot"
        self.base_currency = "INR"
        return self

    @property
    def async_database_url(self) -> str:
        """Build the async SQLAlchemy database URL without exposing secrets in repr."""
        if self.database_url_override is not None:
            return _normalize_database_url(
                self.database_url_override.get_secret_value(),
                target_driver="asyncpg",
            )
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password.get_secret_value())
        auth = f"{user}:{password}" if password else user
        return (
            f"postgresql+asyncpg://{auth}@{self.postgres_host}:"
            f"{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        """Build the synchronous SQLAlchemy URL used by Alembic migrations."""
        if self.database_url_override is not None:
            return _normalize_database_url(
                self.database_url_override.get_secret_value(),
                target_driver="psycopg",
            )
        user = quote_plus(self.postgres_user)
        password = quote_plus(self.postgres_password.get_secret_value())
        auth = f"{user}:{password}" if password else user
        return (
            f"postgresql+psycopg://{auth}@{self.postgres_host}:"
            f"{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()

