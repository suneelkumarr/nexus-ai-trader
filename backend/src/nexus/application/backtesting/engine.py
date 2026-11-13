"""Event-driven causal backtesting engine with conservative stops and execution drag."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Literal, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from nexus.application.backtesting.metrics import (
    compare_to_benchmark,
    compute_performance_metrics,
    simulate_buy_and_hold,
)
from nexus.application.backtesting.models import (
    AssetListingWindow,
    BacktestConfig,
    BacktestRunResult,
    BacktestTradeRecord,
    DatasetSplitBounds,
    EquityPoint,
    FillEvent,
    OrderEvent,
)
from nexus.application.market_data.validator import CandleValidator, get_timeframe_seconds
from nexus.application.risk_manager import IndependentRiskManager
from nexus.application.strategy.config import StrategyV1Config
from nexus.application.strategy.indicators import compute_v1_indicators
from nexus.application.strategy.v1_engine import NexusStrategyV1
from nexus.application.strategy.v2_engine import NexusStrategyV2, StrategyV2Config
from nexus.application.strategy_engine import ohlcv_to_dataframe
from nexus.core.exceptions import (
    BacktestBiasError,
    BacktestValidationError,
    CandleValidationError,
    IncompleteCandleError,
)
from nexus.domain.enums import OrderSide, OrderType, SignalDirection
from nexus.domain.interfaces import SignalRiskApprover
from nexus.domain.models import (
    AssetHolding,
    OHLCVBar,
    OpenPaperPosition,
    PortfolioState,
    PositionContext,
    RiskState,
    StrategySignal,
    TickerQuote,
)

_INR_QUANT = Decimal("0.01")
_QTY_QUANT = Decimal("0.00000001")
_PRICE_QUANT = Decimal("0.00000001")
_BPS_DIV = Decimal("10000")


class StrategyBarEvaluator(Protocol):
    """Protocol for pluggable causal bar-by-bar strategy evaluation."""

    def evaluate_closed_prefix(
        self,
        *,
        symbol: str,
        timeframe: str,
        closed_bars: Sequence[OHLCVBar],
        portfolio: PortfolioState,
        position: PositionContext | None,
        now_utc: datetime,
    ) -> StrategySignal | None:
        """Evaluate strictly closed historical prefix up to now_utc."""
        ...


class _AlwaysApproveSignalGate(SignalRiskApprover):
    """Permissive signal gate when full sizing/risk limits run at execution/risk stage."""

    def approve_entry(
        self,
        *,
        symbol: str,
        timestamp: datetime,
        entry_price: Decimal,
        stop_price: Decimal,
        portfolio: PortfolioState,
    ) -> tuple[bool, str | None]:
        return True, None


class StrategyV1BacktestAdapter:
    """Wraps NexusStrategyV1 for causal bar-by-bar event-driven evaluation."""

    def __init__(self, strategy_config: StrategyV1Config) -> None:
        self._engine = NexusStrategyV1(
            config=strategy_config,
            risk_approver=_AlwaysApproveSignalGate(),
        )

    def evaluate_closed_prefix(
        self,
        *,
        symbol: str,
        timeframe: str,
        closed_bars: Sequence[OHLCVBar],
        portfolio: PortfolioState,
        position: PositionContext | None,
        now_utc: datetime,
    ) -> StrategySignal | None:
        result = self._engine.evaluate_bars(
            symbol=symbol,
            timeframe=timeframe,
            bars=closed_bars,
            portfolio=portfolio,
            position=position,
            now_utc=now_utc,
        )
        return result.signal


class StrategyV2BacktestAdapter:
    """Wraps NexusStrategyV2 for causal bar-by-bar backtest evaluation."""

    def __init__(self, strategy_config: StrategyV2Config | None = None) -> None:
        self._engine = NexusStrategyV2(
            config=strategy_config or StrategyV2Config(),
            risk_approver=_AlwaysApproveSignalGate(),
        )

    def evaluate_closed_prefix(
        self,
        *,
        symbol: str,
        timeframe: str,
        closed_bars: Sequence[OHLCVBar],
        portfolio: PortfolioState,
        position: PositionContext | None,
        now_utc: datetime,
    ) -> StrategySignal | None:
        result = self._engine.evaluate_bars(
            symbol=symbol,
            timeframe=timeframe,
            bars=closed_bars,
            portfolio=portfolio,
            position=position,
            now_utc=now_utc,
        )
        return result.signal


class CombinedStrategyBacktestAdapter:
    """Evaluates Strategy V1 (Trend EMA) and falls back to Strategy V2 (Bollinger Bounce)."""

    def __init__(
        self,
        v1_config: StrategyV1Config | None = None,
        v2_config: StrategyV2Config | None = None,
    ) -> None:
        gate = _AlwaysApproveSignalGate()
        self._v1 = NexusStrategyV1(config=v1_config or StrategyV1Config(), risk_approver=gate)
        self._v2 = NexusStrategyV2(config=v2_config or StrategyV2Config(), risk_approver=gate)

    def evaluate_closed_prefix(
        self,
        *,
        symbol: str,
        timeframe: str,
        closed_bars: Sequence[OHLCVBar],
        portfolio: PortfolioState,
        position: PositionContext | None,
        now_utc: datetime,
    ) -> StrategySignal | None:
        v1_res = self._v1.evaluate_bars(
            symbol=symbol,
            timeframe=timeframe,
            bars=closed_bars,
            portfolio=portfolio,
            position=position,
            now_utc=now_utc,
        )
        if v1_res.signal is not None:
            return v1_res.signal
        v2_res = self._v2.evaluate_bars(
            symbol=symbol,
            timeframe=timeframe,
            bars=closed_bars,
            portfolio=portfolio,
            position=position,
            now_utc=now_utc,
        )
        return v2_res.signal


@dataclass
class _ActivePosition:
    position_id: UUID
    symbol: str
    asset: str
    quantity: Decimal
    entry_signal_at: datetime
    entry_filled_at: datetime
    entry_ref_price_usdt: Decimal
    entry_exec_price_usdt: Decimal
    entry_cost_inr: Decimal
    entry_fee_inr: Decimal
    entry_spread_inr: Decimal
    entry_slippage_inr: Decimal
    entry_liquidity: Literal["maker", "taker"]
    initial_stop_price_usdt: Decimal
    trailing_stop_price_usdt: Decimal
    highest_price_usdt: Decimal
    trailing_atr_multiplier: Decimal
    atr_at_entry: Decimal


def _det_uuid(tag: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"nexus-backtest:{tag}")


def _validate_survivorship_windows(
    *,
    symbol: str,
    start_ts: datetime,
    end_ts: datetime,
    listing_windows: Sequence[AssetListingWindow] | None,
) -> None:
    """Verify evaluated window falls strictly within asset's historical listing period."""
    if not listing_windows:
        return
    norm_symbol = symbol.strip().upper()
    matching = [w for w in listing_windows if w.symbol.strip().upper() == norm_symbol]
    if not matching:
        raise BacktestBiasError(
            f"Survivorship check failed: '{norm_symbol}' missing from point-in-time universe."
        )
    window = matching[0]
    if start_ts < window.listed_at_utc:
        raise BacktestBiasError(
            f"Survivorship/look-ahead violation: backtest start {start_ts.isoformat()} "
            f"precedes listing timestamp {window.listed_at_utc.isoformat()} for {norm_symbol}."
        )
    if window.delisted_at_utc is not None and end_ts > window.delisted_at_utc:
        raise BacktestBiasError(
            f"Survivorship violation: {norm_symbol} delisted at "
            f"{window.delisted_at_utc.isoformat()}, prior to window end {end_ts.isoformat()}."
        )


class EventDrivenBacktester:
    """Deterministic causal simulator with conservative stops and realistic execution drag."""

    def __init__(self, *, validator: CandleValidator | None = None) -> None:
        self._validator = validator or CandleValidator()

    def _validate_sequence(
        self,
        bars: Sequence[OHLCVBar],
        *,
        symbol: str,
        timeframe: str,
    ) -> list[OHLCVBar]:
        if not bars:
            raise BacktestValidationError("Cannot backtest an empty OHLCV sequence.")

        norm_symbol = symbol.strip().upper()
        norm_tf = timeframe.strip().lower()
        seen_ts: set[datetime] = set()
        ordered_in: list[OHLCVBar] = []

        for bar in bars:
            if bar.symbol.strip().upper() != norm_symbol:
                raise BacktestValidationError(
                    f"Mismatched bar symbol '{bar.symbol}', expected '{norm_symbol}'."
                )
            if bar.timeframe.strip().lower() != norm_tf:
                raise BacktestValidationError(
                    f"Mismatched bar timeframe '{bar.timeframe}', expected '{norm_tf}'."
                )
            ts = self._validator.ensure_utc(bar.timestamp)
            self._validator.validate_ohlc_integrity(bar)
            if not bar.is_closed:
                raise IncompleteCandleError(
                    f"Incomplete candle at {ts.isoformat()} forbidden in historical backtest."
                )
            if ts in seen_ts:
                raise CandleValidationError(
                    f"Duplicate candle timestamp {ts.isoformat()} detected in backtest data."
                )
            seen_ts.add(ts)
            ordered_in.append(bar.model_copy(update={"timestamp": ts}))

        return sorted(ordered_in, key=lambda b: b.timestamp)

    def _compute_execution_price_and_costs(
        self,
        *,
        ref_price_usdt: Decimal,
        side: OrderSide,
        liquidity_role: Literal["maker", "taker"],
        quantity: Decimal,
        config: BacktestConfig,
    ) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
        """Return (exec_price_usdt, gross_notional_inr, spread_inr, slippage_inr, fee_inr)."""
        half_spread = config.spread_bps / Decimal("2") / _BPS_DIV
        slippage = config.slippage_bps / _BPS_DIV if liquidity_role == "taker" else Decimal("0")
        fee_rate = (
            config.taker_fee_bps if liquidity_role == "taker" else config.maker_fee_bps
        ) / _BPS_DIV

        if side == OrderSide.BUY:
            exec_price = (ref_price_usdt * (Decimal("1") + half_spread + slippage)).quantize(
                _PRICE_QUANT, rounding=ROUND_HALF_UP
            )
        else:
            multiplier = max(Decimal("0.0001"), Decimal("1") - half_spread - slippage)
            exec_price = (ref_price_usdt * multiplier).quantize(
                _PRICE_QUANT, rounding=ROUND_HALF_UP
            )

        gross_notional_inr = (quantity * ref_price_usdt * config.inr_per_usdt).quantize(
            _INR_QUANT, rounding=ROUND_HALF_UP
        )
        spread_inr = (quantity * ref_price_usdt * half_spread * config.inr_per_usdt).quantize(
            _INR_QUANT, rounding=ROUND_HALF_UP
        )
        slippage_inr = (quantity * ref_price_usdt * slippage * config.inr_per_usdt).quantize(
            _INR_QUANT, rounding=ROUND_HALF_UP
        )
        exec_notional_inr = quantity * exec_price * config.inr_per_usdt
        fee_inr = (exec_notional_inr * fee_rate).quantize(_INR_QUANT, rounding=ROUND_HALF_UP)
        return exec_price, gross_notional_inr, spread_inr, slippage_inr, fee_inr

    def run(
        self,
        *,
        scored_bars: Sequence[OHLCVBar],
        warmup_bars: Sequence[OHLCVBar] = (),
        strategy_config: StrategyV1Config | None = None,
        backtest_config: BacktestConfig | None = None,
        split_name: Literal["train", "validation", "test", "full"] = "full",
        strategy_evaluator: StrategyBarEvaluator | None = None,
        listing_windows: Sequence[AssetListingWindow] | None = None,
    ) -> BacktestRunResult:
        """Execute deterministic event-driven backtest over scored bars with causal warmup."""
        cfg = backtest_config or BacktestConfig()
        strat_cfg = strategy_config or StrategyV1Config()
        norm_symbol = cfg.symbol.strip().upper()
        norm_tf = cfg.timeframe.strip().lower()
        base_asset = norm_symbol.split("/", maxsplit=1)[0]
        bar_step = timedelta(seconds=get_timeframe_seconds(norm_tf))

        clean_scored = self._validate_sequence(scored_bars, symbol=norm_symbol, timeframe=norm_tf)
        clean_warmup = (
            self._validate_sequence(warmup_bars, symbol=norm_symbol, timeframe=norm_tf)
            if warmup_bars
            else []
        )
        if clean_warmup and clean_warmup[-1].timestamp >= clean_scored[0].timestamp:
            raise BacktestBiasError(
                "Warmup candles must strictly precede scored_bars[0] chronologically."
            )

        _validate_survivorship_windows(
            symbol=norm_symbol,
            start_ts=clean_scored[0].timestamp,
            end_ts=clean_scored[-1].timestamp,
            listing_windows=listing_windows,
        )

        full_bars = [*clean_warmup, *clean_scored]
        start_idx = len(clean_warmup)

        # Precompute ATR lookup strictly per causal prefix only when evaluating bars,
        # OR compute causal ATR series (ewm adjust=False on close[:t+1]) where each bar t depends
        # exclusively on [0..t] (identical to slice-by-slice computation).
        full_df = compute_v1_indicators(ohlcv_to_dataframe(full_bars), strat_cfg)

        evaluator = strategy_evaluator or StrategyV1BacktestAdapter(strat_cfg)
        risk_mgr = IndependentRiskManager(
            allowed_symbols=[norm_symbol],
            risk_config=cfg.risk_config,
            fee_bps=cfg.taker_fee_bps,
            slippage_bps=cfg.slippage_bps,
        )

        portfolio_id = _det_uuid(f"portfolio:{norm_symbol}:{split_name}")
        portfolio = PortfolioState(
            id=portfolio_id,
            name=f"backtest-{norm_symbol}-{split_name}",
            initial_capital_inr=cfg.initial_capital_inr,
            cash_balance_inr=cfg.initial_capital_inr,
            created_at=clean_scored[0].timestamp,
        )
        risk_state = RiskState(
            portfolio_id=portfolio_id,
            trading_date_utc=clean_scored[0].timestamp.date(),
            daily_starting_equity_inr=cfg.initial_capital_inr,
            peak_equity_inr=cfg.initial_capital_inr,
        )

        bh_equities, bh_metrics = simulate_buy_and_hold(bars=clean_scored, config=cfg)
        half_spread = cfg.spread_bps / Decimal("2") / _BPS_DIV

        active_pos: _ActivePosition | None = None
        pending_order: OrderEvent | None = None
        fills: list[FillEvent] = []
        trades: list[BacktestTradeRecord] = []
        equity_curve: list[EquityPoint] = []
        rejected_signals = 0

        def _sync_portfolio_holding(pos: _ActivePosition | None) -> None:
            if pos is None:
                portfolio.holdings.pop(base_asset, None)
            else:
                portfolio.holdings[base_asset] = AssetHolding(
                    asset=base_asset,
                    free_qty=pos.quantity,
                    locked_qty=Decimal("0"),
                    avg_entry_price_usdt=pos.entry_exec_price_usdt,
                )

        def _close_position(
            *,
            pos: _ActivePosition,
            exit_ref_usdt: Decimal,
            liquidity: Literal["maker", "taker"],
            executed_at: datetime,
            reason: str,
        ) -> None:
            nonlocal portfolio, risk_state
            exec_p, gross_notional, spread_c, slip_c, fee_c = (
                self._compute_execution_price_and_costs(
                    ref_price_usdt=exit_ref_usdt,
                    side=OrderSide.SELL,
                    liquidity_role=liquidity,
                    quantity=pos.quantity,
                    config=cfg,
                )
            )
            proceeds_inr = (
                pos.quantity * exec_p * cfg.inr_per_usdt - fee_c
            ).quantize(_INR_QUANT, rounding=ROUND_HALF_UP)

            fill_ev = FillEvent(
                order_id=_det_uuid(f"sell:{executed_at.isoformat()}:{len(fills)}"),
                symbol=norm_symbol,
                side=OrderSide.SELL,
                liquidity_role=liquidity,
                reference_price_usdt=exit_ref_usdt,
                executed_price_usdt=exec_p,
                quantity=pos.quantity,
                gross_notional_inr=gross_notional,
                net_cash_delta_inr=proceeds_inr,
                spread_cost_inr=spread_c,
                slippage_cost_inr=slip_c,
                fee_inr=fee_c,
                executed_at=executed_at,
                reason=reason,
            )
            fills.append(fill_ev)

            portfolio.cash_balance_inr = (portfolio.cash_balance_inr + proceeds_inr).quantize(
                _INR_QUANT, rounding=ROUND_HALF_UP
            )
            _sync_portfolio_holding(None)

            net_pnl = (proceeds_inr - pos.entry_cost_inr).quantize(
                _INR_QUANT, rounding=ROUND_HALF_UP
            )
            tot_fees = (pos.entry_fee_inr + fee_c).quantize(_INR_QUANT, rounding=ROUND_HALF_UP)
            tot_spread = (pos.entry_spread_inr + spread_c).quantize(
                _INR_QUANT, rounding=ROUND_HALF_UP
            )
            tot_slip = (pos.entry_slippage_inr + slip_c).quantize(
                _INR_QUANT, rounding=ROUND_HALF_UP
            )
            gross_pnl = (net_pnl + tot_fees + tot_spread + tot_slip).quantize(
                _INR_QUANT, rounding=ROUND_HALF_UP
            )
            net_ret_pct = (
                round(float((net_pnl / pos.entry_cost_inr) * Decimal("100")), 4)
                if pos.entry_cost_inr > Decimal("0")
                else 0.0
            )
            hold_s = max(0.0, (executed_at - pos.entry_filled_at).total_seconds())

            trades.append(
                BacktestTradeRecord(
                    trade_index=len(trades) + 1,
                    symbol=norm_symbol,
                    quantity=pos.quantity,
                    entry_signal_at=pos.entry_signal_at,
                    entry_filled_at=pos.entry_filled_at,
                    exit_filled_at=executed_at,
                    holding_seconds=hold_s,
                    entry_ref_price_usdt=pos.entry_ref_price_usdt,
                    entry_exec_price_usdt=pos.entry_exec_price_usdt,
                    exit_ref_price_usdt=exit_ref_usdt,
                    exit_exec_price_usdt=exec_p,
                    entry_liquidity=pos.entry_liquidity,
                    exit_liquidity=liquidity,
                    gross_pnl_inr=gross_pnl,
                    net_pnl_inr=net_pnl,
                    net_return_pct=net_ret_pct,
                    total_fees_inr=tot_fees,
                    total_spread_cost_inr=tot_spread,
                    total_slippage_cost_inr=tot_slip,
                    exit_reason=reason,
                )
            )

            risk_state.daily_realized_pnl_inr += net_pnl
            risk_state.total_realized_pnl_inr += net_pnl

        def _compute_equity(mark_usdt: Decimal) -> Decimal:
            if active_pos is None:
                return portfolio.cash_balance_inr.quantize(_INR_QUANT, rounding=ROUND_HALF_UP)
            bid_mark = mark_usdt * (Decimal("1") - half_spread)
            hold_val = active_pos.quantity * bid_mark * cfg.inr_per_usdt
            return (portfolio.cash_balance_inr + hold_val).quantize(
                _INR_QUANT, rounding=ROUND_HALF_UP
            )

        def _roll_daily_risk_if_needed(bar_ts: datetime, mark_usdt: Decimal) -> None:
            nonlocal risk_state
            eq = _compute_equity(mark_usdt)
            if eq > risk_state.peak_equity_inr:
                risk_state.peak_equity_inr = eq
            if bar_ts.date() > risk_state.trading_date_utc:
                risk_state.trading_date_utc = bar_ts.date()
                risk_state.daily_starting_equity_inr = eq
                risk_state.daily_realized_pnl_inr = Decimal("0")
                risk_state.daily_entries_count = 0

        for idx in range(start_idx, len(full_bars)):
            bar = full_bars[idx]
            score_pos = idx - start_idx
            _roll_daily_risk_if_needed(bar.timestamp, bar.open)

            # 1. Execute any pending order from bar t-1 close at bar t open (no look-ahead)
            if pending_order is not None:
                order = pending_order
                pending_order = None

                if order.side == OrderSide.BUY and active_pos is None:
                    open_ref = bar.open
                    fee_rate_in = (
                        cfg.taker_fee_bps
                        if order.liquidity_role == "taker"
                        else cfg.maker_fee_bps
                    ) / _BPS_DIV
                    slip_in = (
                        cfg.slippage_bps / _BPS_DIV
                        if order.liquidity_role == "taker"
                        else Decimal("0")
                    )
                    est_exec_open = open_ref * (Decimal("1") + half_spread + slip_in)
                    stop_p = order.stop_price_usdt
                    if stop_p >= est_exec_open:
                        # Re-anchor stop proportionally if open gapped below prior stop
                        stop_dist = max(
                            Decimal("0.01"),
                            order.reference_signal_price_usdt - order.stop_price_usdt,
                        )
                        stop_p = max(
                            Decimal("0.0001"),
                            (est_exec_open - stop_dist).quantize(_PRICE_QUANT),
                        )

                    if cfg.use_risk_manager:
                        open_positions_list: list[OpenPaperPosition] = []
                        quote = TickerQuote(
                            symbol=norm_symbol,
                            exchange_id="backtest",
                            bid=open_ref * (Decimal("1") - half_spread),
                            ask=open_ref * (Decimal("1") + half_spread),
                            last=open_ref,
                            timestamp=bar.timestamp,
                        )
                        sizing = risk_mgr.calculate_position_size(
                            symbol=norm_symbol,
                            entry_price_usdt=est_exec_open,
                            stop_price_usdt=stop_p,
                            portfolio=portfolio,
                            open_positions=open_positions_list,
                            risk_state=risk_state,
                            quotes={norm_symbol: quote},
                            inr_per_usdt=cfg.inr_per_usdt,
                        )
                        target_qty = sizing.quantity if sizing.approved else Decimal("0")
                        if not sizing.approved:
                            rejected_signals += 1
                    else:
                        max_cash = portfolio.cash_balance_inr
                        denom = est_exec_open * cfg.inr_per_usdt * (Decimal("1") + fee_rate_in)
                        target_qty = (max_cash / denom).quantize(
                            _QTY_QUANT, rounding=ROUND_DOWN
                        )

                    if target_qty > Decimal("0"):
                        exec_p, gross_notional, spread_c, slip_c, fee_c = (
                            self._compute_execution_price_and_costs(
                                ref_price_usdt=open_ref,
                                side=OrderSide.BUY,
                                liquidity_role=order.liquidity_role,
                                quantity=target_qty,
                                config=cfg,
                            )
                        )
                        total_cost = (
                            target_qty * exec_p * cfg.inr_per_usdt + fee_c
                        ).quantize(_INR_QUANT, rounding=ROUND_HALF_UP)

                        if total_cost <= portfolio.cash_balance_inr:
                            fill_ev = FillEvent(
                                order_id=order.order_id,
                                symbol=norm_symbol,
                                side=OrderSide.BUY,
                                liquidity_role=order.liquidity_role,
                                reference_price_usdt=open_ref,
                                executed_price_usdt=exec_p,
                                quantity=target_qty,
                                gross_notional_inr=gross_notional,
                                net_cash_delta_inr=-total_cost,
                                spread_cost_inr=spread_c,
                                slippage_cost_inr=slip_c,
                                fee_inr=fee_c,
                                executed_at=bar.timestamp,
                                reason=order.reason,
                            )
                            fills.append(fill_ev)
                            portfolio.cash_balance_inr = (
                                portfolio.cash_balance_inr - total_cost
                            ).quantize(_INR_QUANT, rounding=ROUND_HALF_UP)
                            active_pos = _ActivePosition(
                                position_id=_det_uuid(f"pos:{bar.timestamp.isoformat()}"),
                                symbol=norm_symbol,
                                asset=base_asset,
                                quantity=target_qty,
                                entry_signal_at=order.signal_timestamp,
                                entry_filled_at=bar.timestamp,
                                entry_ref_price_usdt=open_ref,
                                entry_exec_price_usdt=exec_p,
                                entry_cost_inr=total_cost,
                                entry_fee_inr=fee_c,
                                entry_spread_inr=spread_c,
                                entry_slippage_inr=slip_c,
                                entry_liquidity=order.liquidity_role,
                                initial_stop_price_usdt=stop_p,
                                trailing_stop_price_usdt=stop_p,
                                highest_price_usdt=exec_p,
                                trailing_atr_multiplier=strat_cfg.trailing_atr_multiplier,
                                atr_at_entry=order.atr_at_signal,
                            )
                            _sync_portfolio_holding(active_pos)
                            risk_state.daily_entries_count += 1
                        else:
                            rejected_signals += 1

                elif order.side == OrderSide.SELL and active_pos is not None:
                    _close_position(
                        pos=active_pos,
                        exit_ref_usdt=bar.open,
                        liquidity=cfg.exit_liquidity,
                        executed_at=bar.timestamp,
                        reason=order.reason,
                    )
                    active_pos = None

            # 2. Conservative intra-bar stop-loss & trailing-stop check (stop precedes ratchet)
            if active_pos is not None:
                eff_stop = max(
                    active_pos.initial_stop_price_usdt,
                    active_pos.trailing_stop_price_usdt,
                )
                if bar.low <= eff_stop:
                    # Conservative fill: gap open below stop fills at open; else at stop price.
                    stop_ref = (
                        min(bar.open, eff_stop) if cfg.conservative_stop_model else eff_stop
                    )
                    stop_label = (
                        "trailing_stop"
                        if active_pos.trailing_stop_price_usdt
                        > active_pos.initial_stop_price_usdt
                        else "stop_loss"
                    )
                    _close_position(
                        pos=active_pos,
                        exit_ref_usdt=stop_ref,
                        liquidity="taker",
                        executed_at=bar.timestamp,
                        reason=f"Conservative {stop_label} triggered intrabar.",
                    )
                    active_pos = None

            # 3. Causal close-of-bar trailing stop ratchet (takes effect starting bar t+1)
            is_last_bar = idx == len(full_bars) - 1
            if active_pos is not None and not (is_last_bar and cfg.close_open_positions_at_end):
                pos_ctx = PositionContext(
                    symbol=norm_symbol,
                    entry_timestamp=active_pos.entry_filled_at,
                    entry_price=active_pos.entry_exec_price_usdt,
                    quantity=active_pos.quantity,
                    initial_stop_price=active_pos.initial_stop_price_usdt,
                    trailing_stop_price=active_pos.trailing_stop_price_usdt,
                    highest_price_since_entry=active_pos.highest_price_usdt,
                )
                bar_close_now = bar.timestamp + bar_step
                # Strategy evaluates ONLY causal prefix full_bars[: idx + 1]
                sig = evaluator.evaluate_closed_prefix(
                    symbol=norm_symbol,
                    timeframe=norm_tf,
                    closed_bars=full_bars[: idx + 1],
                    portfolio=portfolio,
                    position=pos_ctx,
                    now_utc=bar_close_now,
                )
                if sig is not None and sig.direction == SignalDirection.EXIT_LONG:
                    pending_order = OrderEvent(
                        order_id=_det_uuid(f"ord-sell:{bar.timestamp.isoformat()}"),
                        symbol=norm_symbol,
                        side=OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        liquidity_role=cfg.exit_liquidity,
                        direction=SignalDirection.EXIT_LONG,
                        signal_timestamp=sig.timestamp,
                        reference_signal_price_usdt=bar.close,
                        stop_price_usdt=sig.stop_price,
                        reason=sig.reason,
                    )
                else:
                    # Update causal trailing stop for next bar t+1
                    new_high = max(active_pos.highest_price_usdt, bar.high)
                    raw_atr = float(full_df.iloc[idx]["atr"])
                    atr_val = (
                        Decimal(f"{raw_atr:.8f}")
                        if raw_atr == raw_atr and raw_atr > 0.0
                        else active_pos.atr_at_entry
                    )
                    active_pos.highest_price_usdt = new_high
                    if atr_val > Decimal("0"):
                        candidate_trail = (
                            new_high - active_pos.trailing_atr_multiplier * atr_val
                        ).quantize(_PRICE_QUANT, rounding=ROUND_HALF_UP)
                        if candidate_trail > active_pos.trailing_stop_price_usdt:
                            active_pos.trailing_stop_price_usdt = candidate_trail
            elif active_pos is None and not is_last_bar:
                bar_close_now = bar.timestamp + bar_step
                sig = evaluator.evaluate_closed_prefix(
                    symbol=norm_symbol,
                    timeframe=norm_tf,
                    closed_bars=full_bars[: idx + 1],
                    portfolio=portfolio,
                    position=None,
                    now_utc=bar_close_now,
                )
                if sig is not None and sig.direction == SignalDirection.LONG:
                    raw_atr = float(full_df.iloc[idx]["atr"])
                    atr_val = (
                        Decimal(f"{raw_atr:.8f}")
                        if raw_atr == raw_atr and raw_atr > 0.0
                        else Decimal("0")
                    )
                    pending_order = OrderEvent(
                        order_id=_det_uuid(f"ord-buy:{bar.timestamp.isoformat()}"),
                        symbol=norm_symbol,
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        liquidity_role=cfg.entry_liquidity,
                        direction=SignalDirection.LONG,
                        signal_timestamp=sig.timestamp,
                        reference_signal_price_usdt=sig.entry_price,
                        stop_price_usdt=sig.stop_price,
                        atr_at_signal=atr_val,
                        reason=sig.reason,
                    )

            # 4. Close open position at window end if configured (realizes final net P&L cleanly)
            if is_last_bar and active_pos is not None and cfg.close_open_positions_at_end:
                _close_position(
                    pos=active_pos,
                    exit_ref_usdt=bar.close,
                    liquidity=cfg.exit_liquidity,
                    executed_at=bar.timestamp,
                    reason="end_of_window_liquidation",
                )
                active_pos = None

            end_equity = _compute_equity(bar.close)
            if end_equity > risk_state.peak_equity_inr:
                risk_state.peak_equity_inr = end_equity

            equity_curve.append(
                EquityPoint(
                    timestamp=bar.timestamp,
                    cash_inr=portfolio.cash_balance_inr,
                    holdings_qty=active_pos.quantity if active_pos is not None else Decimal("0"),
                    mark_close_usdt=bar.close,
                    equity_inr=end_equity,
                    benchmark_equity_inr=bh_equities[score_pos],
                )
            )

        equities_only = [pt.equity_inr for pt in equity_curve]
        final_eq = equities_only[-1] if equities_only else cfg.initial_capital_inr
        metrics = compute_performance_metrics(
            initial_capital_inr=cfg.initial_capital_inr,
            final_equity_inr=final_eq,
            equity_series=equities_only,
            trades=trades,
            fills=fills,
            timeframe=norm_tf,
            annualization_override=cfg.annualization_periods_per_year,
        )
        benchmark = compare_to_benchmark(metrics, bh_metrics)
        split_bounds = DatasetSplitBounds(
            split_name=split_name,
            start_timestamp=clean_scored[0].timestamp,
            end_timestamp=clean_scored[-1].timestamp,
            warmup_bars_count=len(clean_warmup),
            scored_bars_count=len(clean_scored),
        )
        return BacktestRunResult(
            split=split_bounds,
            symbol=norm_symbol,
            timeframe=norm_tf,
            strategy_config=strat_cfg,
            backtest_config=cfg,
            metrics=metrics,
            benchmark=benchmark,
            trades=trades,
            fills=fills,
            equity_curve=equity_curve,
            rejected_signals_count=rejected_signals,
        )
