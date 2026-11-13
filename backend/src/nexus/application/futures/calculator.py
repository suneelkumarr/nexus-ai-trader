"""Mathematical formulas and risk calculations for simulated USDT-M Perpetuals."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from nexus.domain.futures import FuturesSide

# Quantization constants
_INR_QUANT = Decimal("0.01")
_PRICE_QUANT = Decimal("0.00000001")
_PERCENT_QUANT = Decimal("0.01")
_DEFAULT_MMR = Decimal("0.005")  # 0.5% Maintenance Margin Ratio
_DEFAULT_FEE_RATE = Decimal("0.0004")  # 0.04% Taker fee


class FuturesRiskCalculator:
    """Pure, deterministic risk and margin calculator for futures paper trading."""

    @staticmethod
    def compute_initial_margin(
        *,
        entry_price: Decimal,
        quantity: Decimal,
        leverage: int,
        inr_rate: Decimal,
    ) -> Decimal:
        """Calculate required isolated margin in INR for a given leverage and size."""
        if leverage < 1 or leverage > 5:
            raise ValueError(f"Leverage must be between 1 and 5, got {leverage}")
        if entry_price <= Decimal("0") or quantity <= Decimal("0") or inr_rate <= Decimal("0"):
            raise ValueError("Price, quantity, and FX rate must be strictly positive.")

        notional_usd = entry_price * quantity
        margin_usd = notional_usd / Decimal(leverage)
        margin_inr = margin_usd * inr_rate
        return margin_inr.quantize(_INR_QUANT, rounding=ROUND_HALF_UP)

    @staticmethod
    def compute_liquidation_price(
        *,
        entry_price: Decimal,
        side: FuturesSide,
        leverage: int,
        mmr: Decimal = _DEFAULT_MMR,
    ) -> Decimal:
        """Calculate simulated bankruptcy/liquidation price based on isolated margin MMR."""
        if leverage < 1 or leverage > 5:
            raise ValueError(f"Leverage must be between 1 and 5, got {leverage}")
        if entry_price <= Decimal("0"):
            raise ValueError("Entry price must be strictly positive.")

        inv_leverage = Decimal("1") / Decimal(leverage)

        if side == FuturesSide.LONG:
            # Long: Entry * (1 - 1/Lev + MMR)
            factor = Decimal("1") - inv_leverage + mmr
            liq_price = entry_price * factor
            clamped = max(liq_price, Decimal("0.00000001"))
            return clamped.quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP)
        else:
            # Short: Entry * (1 + 1/Lev - MMR)
            factor = Decimal("1") + inv_leverage - mmr
            liq_price = entry_price * factor
            return liq_price.quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP)

    @staticmethod
    def compute_pnl(
        *,
        entry_price: Decimal,
        mark_price: Decimal,
        quantity: Decimal,
        side: FuturesSide,
        initial_margin_inr: Decimal,
        inr_rate: Decimal,
    ) -> tuple[Decimal, Decimal, Decimal]:
        """Compute (unrealized_pnl_usd, unrealized_pnl_inr, roe_pct)."""
        if side == FuturesSide.LONG:
            pnl_usd = (mark_price - entry_price) * quantity
        else:
            pnl_usd = (entry_price - mark_price) * quantity

        pnl_inr = (pnl_usd * inr_rate).quantize(_INR_QUANT, rounding=ROUND_HALF_UP)

        if initial_margin_inr > Decimal("0"):
            roe_pct = ((pnl_inr / initial_margin_inr) * Decimal("100")).quantize(
                _PERCENT_QUANT, rounding=ROUND_HALF_UP
            )
        else:
            roe_pct = Decimal("0")

        return pnl_usd, pnl_inr, roe_pct

    @staticmethod
    def is_liquidated(
        *,
        mark_price: Decimal,
        liquidation_price: Decimal,
        side: FuturesSide,
    ) -> bool:
        """Check if mark price has breached the isolated margin liquidation barrier."""
        if side == FuturesSide.LONG:
            return mark_price <= liquidation_price
        else:
            return mark_price >= liquidation_price

    @staticmethod
    def compute_trading_fee(
        *,
        price: Decimal,
        quantity: Decimal,
        inr_rate: Decimal,
        fee_rate: Decimal = _DEFAULT_FEE_RATE,
    ) -> Decimal:
        """Compute execution fee in INR."""
        notional_usd = price * quantity
        fee_inr = notional_usd * fee_rate * inr_rate
        return fee_inr.quantize(_INR_QUANT, rounding=ROUND_HALF_UP)
