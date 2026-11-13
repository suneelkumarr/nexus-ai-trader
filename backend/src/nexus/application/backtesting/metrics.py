"""Metrics calculation and buy-and-hold benchmark simulation for NEXUS backtesting."""

import math
from collections.abc import Sequence
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import NAMESPACE_URL, UUID, uuid5

from nexus.application.backtesting.models import (
    BacktestConfig,
    BacktestTradeRecord,
    BenchmarkComparison,
    FeeImpactBreakdown,
    FillEvent,
    PerformanceMetrics,
)
from nexus.domain.enums import OrderSide
from nexus.domain.models import OHLCVBar

_INR_QUANT = Decimal("0.01")
_QTY_QUANT = Decimal("0.00000001")
_BPS_DIV = Decimal("10000")

_CRYPTO_BARS_PER_YEAR: dict[str, float] = {
    "5m": 365.0 * 24.0 * 12.0,
    "15m": 365.0 * 24.0 * 4.0,
    "1h": 365.0 * 24.0,
    "4h": 365.0 * 6.0,
}


def resolve_annualization_periods(timeframe: str, override: float | None = None) -> float:
    """Resolve 24/7 spot crypto bars per year for Sharpe ratio annualization."""
    if override is not None:
        return override
    return _CRYPTO_BARS_PER_YEAR.get(timeframe.strip().lower(), 365.0 * 24.0 * 4.0)


def compute_max_drawdown_pct(equities: Sequence[Decimal]) -> float:
    """Compute maximum percentage peak-to-trough drawdown across an equity series."""
    if not equities:
        return 0.0
    peak = equities[0]
    max_dd = 0.0
    for equity in equities:
        if equity > peak:
            peak = equity
        elif peak > Decimal("0"):
            dd_pct = float(((peak - equity) / peak) * Decimal("100"))
            if dd_pct > max_dd:
                max_dd = dd_pct
    return round(max_dd, 4)


def compute_sharpe_ratio(equities: Sequence[Decimal], *, periods_per_year: float) -> float:
    """Compute annualized Sharpe ratio (risk-free = 0) from bar equity returns."""
    if len(equities) < 2:
        return 0.0
    returns: list[float] = []
    for idx in range(1, len(equities)):
        prev = float(equities[idx - 1])
        curr = float(equities[idx])
        if prev > 0.0:
            returns.append((curr - prev) / prev)

    if len(returns) < 2:
        return 0.0
    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
    std_ret = math.sqrt(max(0.0, variance))
    if std_ret <= 1e-12:
        return 0.0
    return round((mean_ret / std_ret) * math.sqrt(periods_per_year), 4)


def compute_performance_metrics(
    *,
    initial_capital_inr: Decimal,
    final_equity_inr: Decimal,
    equity_series: Sequence[Decimal],
    trades: Sequence[BacktestTradeRecord],
    fills: Sequence[FillEvent],
    timeframe: str,
    annualization_override: float | None = None,
) -> PerformanceMetrics:
    """Compute strictly net performance metrics reconciled against gross profit and costs."""
    net_profit_inr = (final_equity_inr - initial_capital_inr).quantize(
        _INR_QUANT, rounding=ROUND_HALF_UP
    )
    total_return_pct = (
        round(float((net_profit_inr / initial_capital_inr) * Decimal("100")), 4)
        if initial_capital_inr > Decimal("0")
        else 0.0
    )

    total_fees = sum((f.fee_inr for f in fills), start=Decimal("0")).quantize(
        _INR_QUANT, rounding=ROUND_HALF_UP
    )
    total_spread = sum((f.spread_cost_inr for f in fills), start=Decimal("0")).quantize(
        _INR_QUANT, rounding=ROUND_HALF_UP
    )
    total_slippage = sum((f.slippage_cost_inr for f in fills), start=Decimal("0")).quantize(
        _INR_QUANT, rounding=ROUND_HALF_UP
    )
    total_drag = (total_fees + total_spread + total_slippage).quantize(
        _INR_QUANT, rounding=ROUND_HALF_UP
    )
    gross_profit_inr = (net_profit_inr + total_drag).quantize(
        _INR_QUANT, rounding=ROUND_HALF_UP
    )
    gross_return_pct = (
        round(float((gross_profit_inr / initial_capital_inr) * Decimal("100")), 4)
        if initial_capital_inr > Decimal("0")
        else 0.0
    )
    fee_drag_pct = (
        round(float((total_drag / initial_capital_inr) * Decimal("100")), 4)
        if initial_capital_inr > Decimal("0")
        else 0.0
    )

    num_trades = len(trades)
    wins = [t for t in trades if t.net_pnl_inr > Decimal("0")]
    losses = [t for t in trades if t.net_pnl_inr < Decimal("0")]

    win_rate_pct = round((len(wins) / num_trades) * 100.0, 2) if num_trades > 0 else 0.0
    gross_win_inr = sum((t.net_pnl_inr for t in wins), start=Decimal("0"))
    gross_loss_inr = sum((-t.net_pnl_inr for t in losses), start=Decimal("0"))

    profit_factor: float | None
    if gross_loss_inr > Decimal("0"):
        profit_factor = round(float(gross_win_inr / gross_loss_inr), 4)
    elif gross_win_inr > Decimal("0"):
        profit_factor = None
    else:
        profit_factor = 0.0

    avg_hold_s = (
        round(sum(t.holding_seconds for t in trades) / num_trades, 2)
        if num_trades > 0
        else 0.0
    )
    avg_hold_h = round(avg_hold_s / 3600.0, 4)

    periods_per_year = resolve_annualization_periods(timeframe, annualization_override)
    max_dd = compute_max_drawdown_pct(equity_series)
    sharpe = compute_sharpe_ratio(equity_series, periods_per_year=periods_per_year)

    return PerformanceMetrics(
        initial_capital_inr=initial_capital_inr,
        final_equity_inr=final_equity_inr.quantize(_INR_QUANT, rounding=ROUND_HALF_UP),
        gross_profit_inr=gross_profit_inr,
        gross_return_pct=gross_return_pct,
        total_return_pct=total_return_pct,
        net_profit_inr=net_profit_inr,
        win_rate_pct=win_rate_pct,
        profit_factor=profit_factor,
        max_drawdown_pct=max_dd,
        sharpe_ratio=sharpe,
        avg_holding_time_seconds=avg_hold_s,
        avg_holding_time_hours=avg_hold_h,
        number_of_trades=num_trades,
        fee_impact=FeeImpactBreakdown(
            total_fees_inr=total_fees,
            total_spread_cost_inr=total_spread,
            total_slippage_cost_inr=total_slippage,
            total_execution_drag_inr=total_drag,
            fee_drag_pct_of_initial_capital=fee_drag_pct,
            gross_minus_net_inr=(gross_profit_inr - net_profit_inr).quantize(
                _INR_QUANT, rounding=ROUND_HALF_UP
            ),
        ),
    )


def simulate_buy_and_hold(
    *,
    bars: Sequence[OHLCVBar],
    config: BacktestConfig,
) -> tuple[list[Decimal], PerformanceMetrics]:
    """Simulate spot buy-and-hold across scored bars with identical fees, spread, and slippage."""
    if not bars:
        raise ValueError("Cannot simulate buy-and-hold on empty bar sequence.")

    half_spread = config.spread_bps / Decimal("2") / _BPS_DIV
    slippage = config.slippage_bps / _BPS_DIV
    taker_fee_rate = config.taker_fee_bps / _BPS_DIV

    entry_ref = bars[0].open
    entry_exec = entry_ref * (Decimal("1") + half_spread + slippage)
    # Allocate full initial_capital_inr = qty * entry_exec * inr_per_usdt * (1 + taker_fee_rate)
    denom = entry_exec * config.inr_per_usdt * (Decimal("1") + taker_fee_rate)
    qty = (config.initial_capital_inr / denom).quantize(_QTY_QUANT, rounding=ROUND_HALF_UP)

    entry_gross_inr = (qty * entry_ref * config.inr_per_usdt).quantize(
        _INR_QUANT, rounding=ROUND_HALF_UP
    )
    entry_spread_inr = (qty * entry_ref * half_spread * config.inr_per_usdt).quantize(
        _INR_QUANT, rounding=ROUND_HALF_UP
    )
    entry_slippage_inr = (qty * entry_ref * slippage * config.inr_per_usdt).quantize(
        _INR_QUANT, rounding=ROUND_HALF_UP
    )
    entry_notional_inr = qty * entry_exec * config.inr_per_usdt
    entry_fee_inr = (entry_notional_inr * taker_fee_rate).quantize(
        _INR_QUANT, rounding=ROUND_HALF_UP
    )
    remaining_cash = (
        config.initial_capital_inr - entry_notional_inr - entry_fee_inr
    ).quantize(_INR_QUANT, rounding=ROUND_HALF_UP)
    if remaining_cash < Decimal("0"):
        remaining_cash = Decimal("0.00")

    equities: list[Decimal] = []
    for idx, bar in enumerate(bars):
        bid_mark = bar.close * (Decimal("1") - half_spread)
        if idx < len(bars) - 1:
            equity = (remaining_cash + qty * bid_mark * config.inr_per_usdt).quantize(
                _INR_QUANT, rounding=ROUND_HALF_UP
            )
            equities.append(equity)

    exit_ref = bars[-1].close
    exit_exec = exit_ref * (Decimal("1") - half_spread - slippage)
    exit_notional_inr = qty * exit_exec * config.inr_per_usdt
    exit_fee_inr = (exit_notional_inr * taker_fee_rate).quantize(
        _INR_QUANT, rounding=ROUND_HALF_UP
    )
    exit_spread_inr = (qty * exit_ref * half_spread * config.inr_per_usdt).quantize(
        _INR_QUANT, rounding=ROUND_HALF_UP
    )
    exit_slippage_inr = (qty * exit_ref * slippage * config.inr_per_usdt).quantize(
        _INR_QUANT, rounding=ROUND_HALF_UP
    )
    final_equity = (remaining_cash + exit_notional_inr - exit_fee_inr).quantize(
        _INR_QUANT, rounding=ROUND_HALF_UP
    )
    equities.append(final_equity)

    entry_fill = FillEvent(
        order_id=_deterministic_uuid(bars[0].timestamp, "bh-buy"),
        symbol=config.symbol.strip().upper(),
        side=OrderSide.BUY,
        liquidity_role="taker",
        reference_price_usdt=entry_ref,
        executed_price_usdt=entry_exec,
        quantity=qty,
        gross_notional_inr=entry_gross_inr,
        net_cash_delta_inr=-(entry_notional_inr + entry_fee_inr).quantize(
            _INR_QUANT, rounding=ROUND_HALF_UP
        ),
        spread_cost_inr=entry_spread_inr,
        slippage_cost_inr=entry_slippage_inr,
        fee_inr=entry_fee_inr,
        executed_at=bars[0].timestamp,
        reason="Buy-and-hold benchmark initial spot entry.",
    )
    exit_fill = FillEvent(
        order_id=_deterministic_uuid(bars[-1].timestamp, "bh-sell"),
        symbol=config.symbol.strip().upper(),
        side=OrderSide.SELL,
        liquidity_role="taker",
        reference_price_usdt=exit_ref,
        executed_price_usdt=exit_exec,
        quantity=qty,
        gross_notional_inr=(qty * exit_ref * config.inr_per_usdt).quantize(
            _INR_QUANT, rounding=ROUND_HALF_UP
        ),
        net_cash_delta_inr=(exit_notional_inr - exit_fee_inr).quantize(
            _INR_QUANT, rounding=ROUND_HALF_UP
        ),
        spread_cost_inr=exit_spread_inr,
        slippage_cost_inr=exit_slippage_inr,
        fee_inr=exit_fee_inr,
        executed_at=bars[-1].timestamp,
        reason="Buy-and-hold benchmark window-end mark liquidation.",
    )

    holding_s = max(0.0, (bars[-1].timestamp - bars[0].timestamp).total_seconds())
    net_trade_pnl = (final_equity - config.initial_capital_inr).quantize(
        _INR_QUANT, rounding=ROUND_HALF_UP
    )
    total_trade_fees = (entry_fee_inr + exit_fee_inr).quantize(_INR_QUANT, rounding=ROUND_HALF_UP)
    total_trade_spread = (entry_spread_inr + exit_spread_inr).quantize(
        _INR_QUANT, rounding=ROUND_HALF_UP
    )
    total_trade_slip = (entry_slippage_inr + exit_slippage_inr).quantize(
        _INR_QUANT, rounding=ROUND_HALF_UP
    )
    gross_trade_pnl = (
        net_trade_pnl + total_trade_fees + total_trade_spread + total_trade_slip
    ).quantize(_INR_QUANT, rounding=ROUND_HALF_UP)

    bh_trade = BacktestTradeRecord(
        trade_index=1,
        symbol=config.symbol.strip().upper(),
        quantity=qty,
        entry_signal_at=bars[0].timestamp,
        entry_filled_at=bars[0].timestamp,
        exit_filled_at=bars[-1].timestamp,
        holding_seconds=holding_s,
        entry_ref_price_usdt=entry_ref,
        entry_exec_price_usdt=entry_exec,
        exit_ref_price_usdt=exit_ref,
        exit_exec_price_usdt=exit_exec,
        entry_liquidity="taker",
        exit_liquidity="taker",
        gross_pnl_inr=gross_trade_pnl,
        net_pnl_inr=net_trade_pnl,
        net_return_pct=round(
            float((net_trade_pnl / config.initial_capital_inr) * Decimal("100")), 4
        ),
        total_fees_inr=total_trade_fees,
        total_spread_cost_inr=total_trade_spread,
        total_slippage_cost_inr=total_trade_slip,
        exit_reason="end_of_window_benchmark",
    )

    metrics = compute_performance_metrics(
        initial_capital_inr=config.initial_capital_inr,
        final_equity_inr=final_equity,
        equity_series=equities,
        trades=[bh_trade],
        fills=[entry_fill, exit_fill],
        timeframe=config.timeframe,
        annualization_override=config.annualization_periods_per_year,
    )
    return equities, metrics


def compare_to_benchmark(
    strategy_metrics: PerformanceMetrics,
    benchmark_metrics: PerformanceMetrics,
) -> BenchmarkComparison:
    """Compare net strategy performance directly against net buy-and-hold benchmark."""
    return BenchmarkComparison(
        benchmark_name="spot_buy_and_hold",
        benchmark_metrics=benchmark_metrics,
        excess_net_return_pct=round(
            strategy_metrics.total_return_pct - benchmark_metrics.total_return_pct, 4
        ),
        excess_net_profit_inr=(
            strategy_metrics.net_profit_inr - benchmark_metrics.net_profit_inr
        ).quantize(_INR_QUANT, rounding=ROUND_HALF_UP),
        drawdown_difference_pct=round(
            strategy_metrics.max_drawdown_pct - benchmark_metrics.max_drawdown_pct, 4
        ),
        sharpe_difference=round(
            strategy_metrics.sharpe_ratio - benchmark_metrics.sharpe_ratio, 4
        ),
    )


def _deterministic_uuid(ts: datetime, tag: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"nexus-backtest:{tag}:{ts.isoformat()}")
