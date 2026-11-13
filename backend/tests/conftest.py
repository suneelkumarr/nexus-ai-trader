"""Shared pytest fixtures for NEXUS AI TRADER."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from nexus.core.config import Settings
from nexus.domain.models import PortfolioState, TickerQuote


@pytest.fixture
def test_settings() -> Settings:
    """Return isolated test settings backed by in-memory SQLite."""
    return Settings(
        _env_file=None,
        app_env="test",
        log_format="json",
        database_url_override="sqlite+aiosqlite:///:memory:",
    )


@pytest.fixture
def initial_portfolio() -> PortfolioState:
    """Return a clean INR 10,000.00 paper portfolio."""
    return PortfolioState(
        initial_capital_inr=Decimal("10000.00"),
        cash_balance_inr=Decimal("10000.00"),
    )


@pytest.fixture
def btc_quote() -> TickerQuote:
    """Return a sample validated BTC/USDT quote."""
    return TickerQuote(
        symbol="BTC/USDT",
        exchange_id="binance",
        bid=Decimal("90000.00"),
        ask=Decimal("90010.00"),
        last=Decimal("90005.00"),
        timestamp=datetime.now(UTC),
    )

