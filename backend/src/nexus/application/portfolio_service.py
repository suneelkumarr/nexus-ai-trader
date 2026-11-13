"""Portfolio initialization and quantitative valuation using pandas and numpy."""

from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from nexus.core.config import Settings
from nexus.domain.enums import MarketType, TradingMode
from nexus.domain.models import PortfolioState, TickerQuote


class PortfolioService:
    """Manages virtual INR 10,000 portfolio initialization and valuation metrics."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create_initial_portfolio(self, name: str = "nexus-default-paper") -> PortfolioState:
        """Create a fresh INR 10,000 spot-only paper portfolio."""
        capital = self._settings.initial_capital_inr
        return PortfolioState(
            name=name,
            trading_mode=TradingMode.PAPER,
            market_type=MarketType.SPOT,
            base_currency=self._settings.base_currency,
            initial_capital_inr=capital,
            cash_balance_inr=capital,
        )

    def valuate_portfolio(
        self,
        portfolio: PortfolioState,
        quotes: dict[str, TickerQuote],
        inr_per_usdt: Decimal,
    ) -> dict[str, Any]:
        """Compute total INR valuation, weights, and return using pandas and numpy."""
        rows: list[dict[str, float | str]] = []
        fx = float(inr_per_usdt)

        for asset, holding in portfolio.holdings.items():
            qty = float(holding.free_qty + holding.locked_qty)
            if qty <= 0.0:
                continue
            pair = f"{asset}/USDT"
            quote = quotes.get(pair)
            mark_usdt = (
                float(quote.last)
                if quote is not None
                else float(holding.avg_entry_price_usdt)
            )
            value_inr = qty * mark_usdt * fx
            cost_inr = qty * float(holding.avg_entry_price_usdt) * fx
            rows.append(
                {
                    "asset": asset,
                    "qty": qty,
                    "mark_usdt": mark_usdt,
                    "value_inr": value_inr,
                    "unrealized_pnl_inr": value_inr - cost_inr,
                }
            )

        holdings_df = pd.DataFrame(rows)
        holdings_inr = (
            float(np.sum(holdings_df["value_inr"].to_numpy()))
            if not holdings_df.empty
            else 0.0
        )
        cash_inr = float(portfolio.cash_balance_inr)
        total_equity_inr = cash_inr + holdings_inr
        initial_inr = float(portfolio.initial_capital_inr)
        total_return_pct = ((total_equity_inr - initial_inr) / initial_inr) * 100.0

        return {
            "portfolio_id": str(portfolio.id),
            "base_currency": portfolio.base_currency,
            "cash_balance_inr": round(cash_inr, 2),
            "holdings_value_inr": round(holdings_inr, 2),
            "total_equity_inr": round(total_equity_inr, 2),
            "total_return_pct": round(total_return_pct, 4),
            "positions": rows,
        }

