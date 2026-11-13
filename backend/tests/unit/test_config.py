"""Unit tests for configuration invariants and secret safety."""

from decimal import Decimal

import pytest

from nexus.core.config import Settings
from nexus.core.exceptions import ConfigurationInvariantError


def test_default_settings_enforce_paper_spot_inr10000() -> None:
    settings = Settings(_env_file=None)
    assert settings.trading_mode == "paper"
    assert settings.market_type == "spot"
    assert settings.live_trading_enabled is False
    assert settings.allow_leverage is False
    assert settings.allow_futures is False
    assert settings.allow_withdrawals is False
    assert settings.base_currency == "INR"
    assert settings.initial_capital_inr == Decimal("10000.00")
    assert settings.allowed_symbols == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"trading_mode": "live"},
        {"market_type": "futures"},
        {"live_trading_enabled": True},
        {"allow_leverage": True},
        {"allow_futures": True},
        {"allow_withdrawals": True},
        {"base_currency": "USD"},
        {"initial_capital_inr": Decimal("0")},
    ],
)
def test_forbidden_configuration_raises_invariant_error(overrides: dict[str, object]) -> None:
    with pytest.raises(ConfigurationInvariantError):
        Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_symbol", ["BTC/USDT:USDT", "BTC-PERP", "BTCUSDT", ""])
def test_non_spot_symbols_rejected(bad_symbol: str) -> None:
    with pytest.raises(ConfigurationInvariantError):
        Settings(_env_file=None, allowed_symbols=[bad_symbol])


def test_database_url_uses_secret_str() -> None:
    settings = Settings(_env_file=None, postgres_password="s3cr3t@value")
    assert "s3cr3t@value" not in repr(settings)
    assert "s3cr3t%40value" in settings.async_database_url
    assert "s3cr3t%40value" in settings.sync_database_url


def test_database_url_override_normalizes_postgres_scheme_and_sslmode() -> None:
    raw_url = "postgres://avnadmin:db_secret_pass@db.example.com:19311/defaultdb?sslmode=require"
    settings = Settings(_env_file=None, database_url_override=raw_url)
    assert "db_secret_pass" not in repr(settings)
    assert (
        settings.async_database_url
        == "postgresql+asyncpg://avnadmin:db_secret_pass@db.example.com:19311/defaultdb?ssl=require"
    )
    assert (
        settings.sync_database_url
        == "postgresql+psycopg://avnadmin:db_secret_pass@db.example.com:19311/defaultdb?sslmode=require"
    )

    sqlite_settings = Settings(
        _env_file=None, database_url_override="sqlite+aiosqlite:///:memory:"
    )
    assert sqlite_settings.async_database_url == "sqlite+aiosqlite:///:memory:"
    assert sqlite_settings.sync_database_url == "sqlite:///:memory:"

