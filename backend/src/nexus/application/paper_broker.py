"""Virtual spot paper broker executing orders against real market quotes."""

from decimal import ROUND_HALF_UP, Decimal

from nexus.core.exceptions import LiveTradingForbiddenError, RiskViolationError
from nexus.core.logging import get_logger
from nexus.domain.enums import OrderSide, OrderStatus, OrderType
from nexus.domain.interfaces import RiskGuard
from nexus.domain.models import (
    AssetHolding,
    PaperFill,
    PaperOrderRequest,
    PaperOrderResult,
    PortfolioState,
    TickerQuote,
)

logger = get_logger(__name__)

_INR_QUANT = Decimal("0.01")


class SpotPaperBroker:
    """Executes virtual spot trades using injected RiskGuard and real TickerQuote."""

    def __init__(
        self,
        *,
        risk_guard: RiskGuard,
        fee_bps: Decimal = Decimal("10.0"),
        slippage_bps: Decimal = Decimal("5.0"),
    ) -> None:
        self._risk_guard = risk_guard
        self._fee_bps = fee_bps
        self._slippage_bps = slippage_bps

    def execute_order(
        self,
        request: PaperOrderRequest,
        portfolio: PortfolioState,
        quote: TickerQuote,
        inr_per_usdt: Decimal,
    ) -> PaperOrderResult:
        """Validate and simulate a spot fill against real market bid/ask prices."""
        try:
            self._risk_guard.validate_order(request, portfolio, quote, inr_per_usdt)
        except LiveTradingForbiddenError:
            logger.error(
                "forbidden_trading_attempt_blocked",
                portfolio_id=str(portfolio.id),
                symbol=request.symbol,
            )
            raise
        except RiskViolationError as exc:
            logger.warning(
                "paper_order_rejected",
                portfolio_id=str(portfolio.id),
                symbol=request.symbol,
                side=request.side.value,
                reason=str(exc),
            )
            return PaperOrderResult(
                portfolio_id=portfolio.id,
                symbol=request.symbol,
                side=request.side,
                order_type=request.order_type,
                status=OrderStatus.REJECTED,
                requested_qty=request.quantity,
                rejection_reason=str(exc),
            )

        if (
            request.order_type == OrderType.LIMIT
            and request.limit_price_usdt is not None
            and (
                (request.side == OrderSide.BUY and quote.ask > request.limit_price_usdt)
                or (request.side == OrderSide.SELL and quote.bid < request.limit_price_usdt)
            )
        ):
            return PaperOrderResult(
                portfolio_id=portfolio.id,
                symbol=request.symbol,
                side=request.side,
                order_type=request.order_type,
                status=OrderStatus.PENDING,
                requested_qty=request.quantity,
                rejection_reason="Limit price not yet reached by market quote.",
            )

        slippage_ratio = self._slippage_bps / Decimal("10000")
        fee_ratio = self._fee_bps / Decimal("10000")
        base_asset = request.symbol.split("/", maxsplit=1)[0]

        if request.side == OrderSide.BUY:
            fill_price = quote.ask * (Decimal("1") + slippage_ratio)
            gross_usdt = fill_price * request.quantity
            fee_usdt = gross_usdt * fee_ratio
            total_inr = ((gross_usdt + fee_usdt) * inr_per_usdt).quantize(
                _INR_QUANT, rounding=ROUND_HALF_UP
            )

            portfolio.cash_balance_inr -= total_inr
            existing = portfolio.holdings.get(base_asset)
            if existing is None or existing.free_qty == Decimal("0"):
                portfolio.holdings[base_asset] = AssetHolding(
                    asset=base_asset,
                    free_qty=request.quantity,
                    avg_entry_price_usdt=fill_price,
                )
            else:
                new_qty = existing.free_qty + request.quantity
                weighted_cost = (
                    existing.free_qty * existing.avg_entry_price_usdt
                    + request.quantity * fill_price
                )
                existing.free_qty = new_qty
                existing.avg_entry_price_usdt = weighted_cost / new_qty
        else:
            fill_price = quote.bid * (Decimal("1") - slippage_ratio)
            gross_usdt = fill_price * request.quantity
            fee_usdt = gross_usdt * fee_ratio
            net_inr = ((gross_usdt - fee_usdt) * inr_per_usdt).quantize(
                _INR_QUANT, rounding=ROUND_HALF_UP
            )
            total_inr = net_inr

            holding = portfolio.holdings[base_asset]
            holding.free_qty -= request.quantity
            if holding.free_qty == Decimal("0"):
                holding.avg_entry_price_usdt = Decimal("0")
            portfolio.cash_balance_inr += net_inr

        result = PaperOrderResult(
            portfolio_id=portfolio.id,
            symbol=request.symbol,
            side=request.side,
            order_type=request.order_type,
            status=OrderStatus.FILLED,
            requested_qty=request.quantity,
        )
        fill = PaperFill(
            order_id=result.order_id,
            symbol=request.symbol,
            side=request.side,
            executed_qty=request.quantity,
            executed_price_usdt=fill_price,
            fee_usdt=fee_usdt,
            inr_per_usdt_rate=inr_per_usdt,
            total_inr=total_inr,
            slippage_bps=self._slippage_bps,
        )

        logger.info(
            "paper_order_filled",
            order_id=str(result.order_id),
            symbol=request.symbol,
            side=request.side.value,
            qty=str(request.quantity),
            price_usdt=str(fill_price),
            total_inr=str(total_inr),
        )
        return result.model_copy(update={"fill": fill})

