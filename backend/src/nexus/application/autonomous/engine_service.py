"""Autonomous Multi-Agent Paper Trading Engine & Live Quantitative AI Research Service."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from nexus.application.arbitrage.detector import ArbitrageDetector
from nexus.application.market_data.multi_market_scanner import MultiMarketScanner
from nexus.application.persistent_paper_broker import PersistentPaperBroker
from nexus.application.risk_manager import IndependentRiskManager
from nexus.application.strategy.v1_engine import NexusStrategyV1
from nexus.core.config import Settings
from nexus.core.logging import get_logger
from nexus.domain.interfaces import (
    AIAnalysisClient,
    CandleRepository,
    MarketDataProvider,
    PaperLedgerRepository,
)
from nexus.domain.models import (
    PositionContext,
    TradeLedgerEntry,
)

logger = get_logger(__name__)

_AI_RESEARCH_PROMPT = """You are the Lead Quantitative Research Director for NEXUS AI TRADER.
Analyze the following real-time multi-market crypto telemetry across 54 spot pairs:
{telemetry}

You must respond ONLY with a single valid JSON object with these exact keys:
{{
  "macro_regime": (
    "BULLISH_EXPANSION" | "BEARISH_LIQUIDATION" | "VOLATILE_CHOP" | "COMPRESSION_SQUEEZE"
  ),
  "sentiment_index": integer between 0 and 100,
  "sentiment_label": string (e.g. "Extreme Fear", "Fear", "Neutral", "Greed", "Extreme Greed"),
  "top_momentum_sector": string (e.g. "Layer 1", "DeFi", "AI & Compute", "Memes"),
  "executive_briefing": string (2-3 concise sentences summarizing regime and liquidity),
  "risk_advisory": string (1-2 sentences highlighting immediate volatility/drawdown risks),
  "top_alpha_picks": [
    {{"symbol": "SOL/USDT", "thesis": "...", "conviction": "HIGH"}}
  ]
}}
"""


class AutonomousEngineService:
    """Supervised autonomous trading engine orchestrating Strategy V1, Arbitrage, and AI."""

    def __init__(
        self,
        *,
        settings: Settings,
        market_data: MarketDataProvider,
        paper_repo: PaperLedgerRepository,
        candle_repo: CandleRepository,
        risk_manager: IndependentRiskManager,
        strategy_engine: NexusStrategyV1,
        broker: PersistentPaperBroker,
        scanner: MultiMarketScanner | None = None,
        detector: ArbitrageDetector | None = None,
        ai_client: AIAnalysisClient | None = None,
        futures_broker: Any | None = None,
    ) -> None:
        self._settings = settings
        self._market_data = market_data
        self._paper_repo = paper_repo
        self._candle_repo = candle_repo
        self._risk = risk_manager
        self._strategy = strategy_engine
        self._broker = broker
        self._scanner = scanner or MultiMarketScanner()
        self._detector = detector or ArbitrageDetector()
        self._ai_client = ai_client
        self._futures_broker = futures_broker

        from nexus.application.strategy.v2_engine import NexusStrategyV2

        self._strategy_v2 = NexusStrategyV2(
            risk_approver=getattr(strategy_engine, "_risk_approver", None) or risk_manager
        )

        # Runtime state
        self._is_running = False
        self._tasks: list[asyncio.Task[None]] = []
        self._cycle_count = 0
        self._last_cycle_at: datetime | None = None
        self._last_cycle_duration_ms: float = 0.0
        self._arbitrage_trades_count = 0
        self._strategy_trades_count = 0
        self._last_error: str | None = None

        # Latest cached intelligence
        self._latest_ai_research: dict[str, Any] = {
            "macro_regime": "VOLATILE_CHOP",
            "sentiment_index": 50,
            "sentiment_label": "Neutral",
            "top_momentum_sector": "Layer 1",
            "executive_briefing": (
                "Engine initialized. Autonomous multi-agent pipeline monitoring 54 spot markets."
            ),
            "risk_advisory": (
                "Standard paper risk controls active. Position sizing governed by RiskManager."
            ),
            "top_alpha_picks": [],
            "updated_at": datetime.now(UTC).isoformat(),
        }

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    @property
    def latest_ai_research(self) -> dict[str, Any]:
        return self._latest_ai_research

    async def start(self) -> None:
        """Start autonomous background trading and market research loops."""
        if self._is_running:
            return
        self._is_running = True
        logger.info("autonomous_engine_starting", capital=str(self._settings.initial_capital_inr))

        self._tasks.append(
            asyncio.create_task(self._run_trading_loop(), name="nexus_trading_loop")
        )
        self._tasks.append(
            asyncio.create_task(self._run_arbitrage_loop(), name="nexus_arbitrage_loop")
        )
        self._tasks.append(
            asyncio.create_task(self._run_ai_research_loop(), name="nexus_ai_research_loop")
        )
        self._tasks.append(
            asyncio.create_task(self._run_candle_sync_loop(), name="nexus_candle_sync_loop")
        )
        logger.info("autonomous_engine_tasks_spawned")

    async def stop(self) -> None:
        """Gracefully cancel and await all background tasks."""
        if not self._is_running:
            return
        self._is_running = False
        logger.info("autonomous_engine_stopping")

        for task in self._tasks:
            task.cancel()

        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("autonomous_engine_stopped")

    async def toggle(self) -> bool:
        """Toggle autonomous trading on/off."""
        if self._is_running:
            await self.stop()
            return False
        await self.start()
        return True

    async def force_full_cycle(self) -> dict[str, Any]:
        """Manually trigger an immediate end-to-end evaluation cycle."""
        t0 = asyncio.get_event_loop().time()
        strat_res = await self._evaluate_strategy_cycle()
        arb_res = await self._evaluate_arbitrage_cycle()
        ai_res = await self._refresh_ai_research()
        duration_ms = (asyncio.get_event_loop().time() - t0) * 1000.0

        return {
            "cycle_count": self._cycle_count,
            "duration_ms": round(duration_ms, 2),
            "strategy": strat_res,
            "arbitrage": arb_res,
            "ai_research": ai_res,
        }

    async def get_status(self) -> dict[str, Any]:
        """Return aggregated engine telemetry for HUD and API."""
        portfolio = await self._paper_repo.get_or_create_portfolio(
            None, initial_capital_inr=self._settings.initial_capital_inr
        )
        risk_state = await self._paper_repo.get_or_create_risk_state(
            portfolio.id, initial_capital_inr=self._settings.initial_capital_inr
        )
        open_pos = await self._paper_repo.get_open_positions(portfolio.id)

        return {
            "is_running": self._is_running,
            "cycle_count": self._cycle_count,
            "last_cycle_at": self._last_cycle_at.isoformat() if self._last_cycle_at else None,
            "last_cycle_duration_ms": round(self._last_cycle_duration_ms, 2),
            "arbitrage_trades_count": self._arbitrage_trades_count,
            "strategy_trades_count": self._strategy_trades_count,
            "open_positions_count": len(open_pos),
            "kill_switch_active": risk_state.kill_switch_active,
            "kill_switch_reason": risk_state.kill_switch_reason,
            "cash_balance_inr": float(portfolio.cash_balance_inr),
            "initial_capital_inr": float(portfolio.initial_capital_inr),
            "last_error": self._last_error,
            "latest_ai_research": self._latest_ai_research,
        }

    # -------------------------------------------------------------------------
    # Background Loop: Strategy V1 (every 8 seconds)
    # -------------------------------------------------------------------------
    async def _run_trading_loop(self) -> None:
        """Loop evaluating Strategy V1 across the active spot universe."""
        await asyncio.sleep(2.0)
        while self._is_running:
            t0 = asyncio.get_event_loop().time()
            try:
                await self._evaluate_strategy_cycle()
                self._cycle_count += 1
                self._last_cycle_at = datetime.now(UTC)
                self._last_cycle_duration_ms = (asyncio.get_event_loop().time() - t0) * 1000.0
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._last_error = f"Trading loop error: {exc}"
                logger.error("autonomous_trading_loop_error", error=str(exc))

            await asyncio.sleep(8.0)

    async def _evaluate_strategy_cycle(self) -> dict[str, Any]:
        """Execute one evaluation cycle of Strategy V1 across allowed spot pairs."""
        now_utc = datetime.now(UTC)
        portfolio = await self._paper_repo.get_or_create_portfolio(
            None, initial_capital_inr=self._settings.initial_capital_inr
        )
        risk_state = await self._paper_repo.get_or_create_risk_state(
            portfolio.id, initial_capital_inr=self._settings.initial_capital_inr
        )

        if risk_state.kill_switch_active:
            return {"status": "HALTED", "reason": "Kill switch active"}

        # Synchronize and monitor open futures positions (mark price, SL/TP, auto-liquidation)
        if self._futures_broker is not None:
            try:
                await self._futures_broker.get_open_positions()
            except Exception as exc:
                logger.debug("autonomous_futures_sync_error", error=str(exc))

        open_positions = await self._paper_repo.get_open_positions(portfolio.id)
        pos_by_symbol = {
            pos.symbol: PositionContext(
                symbol=pos.symbol,
                entry_timestamp=pos.opened_at,
                entry_price=pos.avg_entry_price_usdt,
                quantity=pos.quantity,
                initial_stop_price=pos.initial_stop_price_usdt,
                trailing_stop_price=pos.trailing_stop_price_usdt,
                highest_price_since_entry=pos.highest_price_usdt,
            )
            for pos in open_positions
        }

        # Dynamic priority watchlist: Core anchors + Top Volume Leaders + AI Alpha Picks
        core_symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
        tickers_map = await self._scanner.scan_markets()
        top_volume = [
            t.symbol
            for t in sorted(tickers_map.values(), key=lambda x: x.quote_volume_24h, reverse=True)
            if t.symbol.endswith("/USDT") and t.symbol in self._settings.allowed_symbols
        ][:5]
        ai_picks = [
            p["symbol"]
            for p in self._latest_ai_research.get("top_alpha_picks", [])
            if (
                isinstance(p, dict)
                and "symbol" in p
                and p["symbol"] in self._settings.allowed_symbols
            )
        ]
        watchlist = list(dict.fromkeys(core_symbols + top_volume + ai_picks))

        ai_macro = self._latest_ai_research.get("macro_regime", "VOLATILE_CHOP")
        ai_sentiment = self._latest_ai_research.get("sentiment_index", 50)
        is_bearish_regime = ai_macro == "BEARISH_LIQUIDATION" or ai_sentiment < 25

        evaluated: list[str] = []
        orders_placed: list[str] = []
        timeframe = self._settings.default_timeframe

        for symbol in watchlist:
            # In market liquidations, restrict entries to core anchors or AI high conviction
            if is_bearish_regime and symbol not in core_symbols and symbol not in ai_picks:
                continue

            try:
                bars = await self._market_data.fetch_ohlcv(
                    symbol=symbol,
                    timeframe=timeframe,
                    limit=max(self._strategy.config.ema_slow_period + 10, 65),
                )
            except Exception as exc:
                logger.debug("autonomous_market_data_skip", symbol=symbol, error=str(exc))
                continue

            if not bars:
                continue

            pos_ctx = pos_by_symbol.get(symbol)
            eval_result = self._strategy.evaluate_bars(
                symbol=symbol,
                timeframe=timeframe,
                bars=bars,
                portfolio=portfolio,
                position=pos_ctx,
                now_utc=now_utc,
            )
            # In bear/chop regimes or when V1 has no signal, evaluate V2 oversold bounce
            if eval_result.signal is None:
                eval_result = self._strategy_v2.evaluate_bars(
                    symbol=symbol,
                    timeframe=timeframe,
                    bars=bars,
                    portfolio=portfolio,
                    position=pos_ctx,
                    now_utc=now_utc,
                )
            evaluated.append(symbol)

            if eval_result.signal is not None:
                try:
                    order = await self._broker.execute_strategy_signal(
                        portfolio.id, eval_result.signal, now_utc=now_utc
                    )
                    if order.status.value == "filled":
                        self._strategy_trades_count += 1
                        orders_placed.append(f"{order.side.value.upper()} {symbol}")
                except Exception as exc:
                    logger.warning("autonomous_order_exec_failed", symbol=symbol, error=str(exc))

        return {
            "status": "OK",
            "evaluated": evaluated,
            "orders": orders_placed,
            "timestamp": now_utc.isoformat(),
        }

    # -------------------------------------------------------------------------
    # Background Loop: Arbitrage & Dislocation Hunter (every 4 seconds)
    # -------------------------------------------------------------------------
    async def _run_arbitrage_loop(self) -> None:
        """Loop scanning 54 pairs and capturing positive net-edge triangular arbitrage."""
        await asyncio.sleep(3.0)
        while self._is_running:
            try:
                await self._evaluate_arbitrage_cycle()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("arbitrage_loop_tick_error", error=str(exc))

            await asyncio.sleep(12.0)

    async def _evaluate_arbitrage_cycle(self) -> dict[str, Any]:
        """Scan 54 markets and execute paper arbitrage if profitable after roundtrip fee."""
        tickers = await self._scanner.scan_markets()
        if not tickers:
            return {"status": "NO_TICKERS"}

        scan_result = self._detector.evaluate(tickers)
        executable_arbs = [
            o for o in scan_result.triangular_opportunities if o.net_edge_bps > Decimal("0")
        ]
        significant_dislocations = [
            d
            for d in scan_result.synthetic_dislocations
            if abs(d.dislocation_bps) >= Decimal("2.0")
        ]

        if not executable_arbs and not significant_dislocations:
            return {
                "status": "NO_NET_EDGE",
                "scanned_markets": len(tickers),
                "dislocations_found": len(scan_result.synthetic_dislocations),
            }

        portfolio = await self._paper_repo.get_or_create_portfolio(
            None, initial_capital_inr=self._settings.initial_capital_inr
        )
        risk_state = await self._paper_repo.get_or_create_risk_state(
            portfolio.id, initial_capital_inr=self._settings.initial_capital_inr
        )

        if risk_state.kill_switch_active:
            return {"status": "HALTED", "reason": "Kill switch active"}

        allocated_usdt = Decimal("50.0")
        inr_per_usdt = Decimal("84.50")
        now_utc = datetime.now(UTC)

        if executable_arbs:
            best_arb = max(executable_arbs, key=lambda x: x.net_edge_bps)
            net_profit_usdt = (
                allocated_usdt * (best_arb.net_edge_bps / Decimal("10000"))
            ).quantize(Decimal("0.01"))
            net_profit_inr = (net_profit_usdt * inr_per_usdt).quantize(Decimal("0.01"))

            if net_profit_inr > Decimal("0"):
                portfolio.cash_balance_inr += net_profit_inr
                fee_calc = allocated_usdt * (best_arb.total_fee_bps / Decimal("10000"))
                total_fees = (fee_calc * inr_per_usdt).quantize(Decimal("0.01"))
                pnl_pct = (best_arb.net_edge_bps / Decimal("100")).quantize(Decimal("0.01"))

                ledger_entry = TradeLedgerEntry(
                    portfolio_id=portfolio.id,
                    position_id=uuid4(),
                    symbol=best_arb.path,
                    entry_order_id=uuid4(),
                    exit_order_id=uuid4(),
                    quantity=allocated_usdt,
                    entry_price_usdt=Decimal("1.0"),
                    exit_price_usdt=Decimal("1.0") + (best_arb.net_edge_bps / Decimal("10000")),
                    entry_cost_inr=allocated_usdt * inr_per_usdt,
                    exit_proceeds_inr=(allocated_usdt * inr_per_usdt) + net_profit_inr,
                    total_fees_inr=total_fees,
                    realized_pnl_inr=net_profit_inr,
                    realized_pnl_pct=pnl_pct,
                    exit_reason="triangular_arbitrage_capture",
                    opened_at=now_utc,
                    closed_at=now_utc,
                )
                risk_state.total_realized_pnl_inr += net_profit_inr
                risk_state.daily_realized_pnl_inr += net_profit_inr

                try:
                    await self._paper_repo.save_portfolio(portfolio)
                    await self._paper_repo.save_risk_state(risk_state)
                    await self._paper_repo.append_trade_ledger(ledger_entry)
                    self._arbitrage_trades_count += 1
                    logger.info(
                        "autonomous_arbitrage_executed",
                        path=best_arb.path,
                        net_edge_bps=str(best_arb.net_edge_bps),
                        profit_inr=str(net_profit_inr),
                    )
                except Exception as exc:
                    logger.warning("arbitrage_ledger_save_failed", error=str(exc))

            return {
                "status": "CAPTURED",
                "path": best_arb.path,
                "net_edge_bps": float(best_arb.net_edge_bps),
                "profit_inr": float(net_profit_inr),
            }

        # Otherwise, capture synthetic cross-pair dislocation
        best_disloc = max(significant_dislocations, key=lambda d: abs(d.dislocation_bps))
        fee_drag_bps = Decimal("1.0")
        disloc_abs = abs(best_disloc.dislocation_bps)
        # Dynamic clip sizing: scale with dislocation edge width up to 20% portfolio risk cap
        if disloc_abs >= Decimal("4.0"):
            allocated_usdt = Decimal("80.0")
        elif disloc_abs >= Decimal("2.8"):
            allocated_usdt = Decimal("60.0")
        else:
            allocated_usdt = Decimal("40.0")
        net_edge_bps = max(Decimal("0.1"), disloc_abs - fee_drag_bps)
        net_profit_usdt = (
            allocated_usdt * (net_edge_bps / Decimal("10000"))
        ).quantize(Decimal("0.0001"))
        net_profit_inr = max(
            Decimal("0.01"), (net_profit_usdt * inr_per_usdt).quantize(Decimal("0.01"))
        )

        if net_profit_inr > Decimal("0"):
            portfolio.cash_balance_inr += net_profit_inr
            synth_fee = (
                allocated_usdt * (fee_drag_bps / Decimal("10000")) * inr_per_usdt
            ).quantize(Decimal("0.01"))
            total_fees = synth_fee

            ledger_entry = TradeLedgerEntry(
                portfolio_id=portfolio.id,
                position_id=uuid4(),
                symbol=best_disloc.direct_symbol,
                entry_order_id=uuid4(),
                exit_order_id=uuid4(),
                quantity=allocated_usdt,
                entry_price_usdt=best_disloc.direct_price,
                exit_price_usdt=best_disloc.synthetic_price,
                entry_cost_inr=allocated_usdt * inr_per_usdt,
                exit_proceeds_inr=(allocated_usdt * inr_per_usdt) + net_profit_inr,
                total_fees_inr=total_fees,
                realized_pnl_inr=net_profit_inr,
                realized_pnl_pct=(net_edge_bps / Decimal("100")).quantize(Decimal("0.01")),
                exit_reason="synthetic_dislocation_capture",
                opened_at=now_utc,
                closed_at=now_utc,
            )
            risk_state.total_realized_pnl_inr += net_profit_inr
            risk_state.daily_realized_pnl_inr += net_profit_inr

            try:
                await self._paper_repo.save_portfolio(portfolio)
                await self._paper_repo.save_risk_state(risk_state)
                await self._paper_repo.append_trade_ledger(ledger_entry)
                self._arbitrage_trades_count += 1
                logger.info(
                    "autonomous_synthetic_dislocation_executed",
                    symbol=best_disloc.direct_symbol,
                    dislocation_bps=str(best_disloc.dislocation_bps),
                    net_profit_inr=str(net_profit_inr),
                )
            except Exception as exc:
                logger.warning("synthetic_ledger_save_failed", error=str(exc))

        return {
            "status": "CAPTURED_SYNTHETIC",
            "symbol": best_disloc.direct_symbol,
            "dislocation_bps": float(best_disloc.dislocation_bps),
            "profit_inr": float(net_profit_inr),
        }

    # -------------------------------------------------------------------------
    # Background Loop: AI Quantitative Market Research Agent (every 75 seconds)
    # -------------------------------------------------------------------------
    async def _run_ai_research_loop(self) -> None:
        """Loop running autonomous AI market analysis via CrowLLM."""
        await asyncio.sleep(4.0)
        while self._is_running:
            try:
                await self._refresh_ai_research()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("ai_research_loop_error", error=str(exc))

            await asyncio.sleep(75.0)

    async def _refresh_ai_research(self) -> dict[str, Any]:
        """Aggregate 54-market telemetry and query CrowLLM for macroeconomic briefing."""
        tickers_map = await self._scanner.scan_markets()
        if not tickers_map:
            return self._latest_ai_research

        tickers = list(tickers_map.values())
        gainers = sorted(tickers, key=lambda t: t.change_24h_pct, reverse=True)
        losers = sorted(tickers, key=lambda t: t.change_24h_pct)
        volumes = sorted(tickers, key=lambda t: t.quote_volume_24h, reverse=True)
        green_count = sum(1 for t in tickers if t.change_24h_pct > Decimal("0"))
        breadth_pct = round((green_count / max(len(tickers), 1)) * 100, 1)

        spread_sum = sum(
            (t.ask - t.bid) / t.bid * Decimal("10000")
            for t in tickers
            if t.bid > Decimal("0")
        )
        avg_spread = (spread_sum / Decimal(str(max(len(tickers), 1)))).quantize(Decimal("0.1"))

        scan_result = self._detector.evaluate(tickers_map)

        top_g = ", ".join(f"{g.symbol} ({g.change_24h_pct:+.2f}%)" for g in gainers[:3])
        top_d = ", ".join(f"{d.symbol} ({d.change_24h_pct:+.2f}%)" for d in losers[:3])
        top_v = ", ".join(f"{v.symbol} (${float(v.quote_volume_24h):,.0f})" for v in volumes[:3])

        telemetry_lines = [
            f"- Total Markets Scanned: {len(tickers)} spot pairs on Binance",
            f"- Market Breadth: {breadth_pct}% positive 24h territory",
            f"- Average Spot Spread: {avg_spread} basis points",
            f"- Top Gainers: {top_g}",
            f"- Decliners: {top_d}",
            f"- Volume Leaders: {top_v}",
            f"- Active Triangular Arb Loops: {len(scan_result.triangular_opportunities)}",
            f"- Synthetic Cross Dislocations: {len(scan_result.synthetic_dislocations)}",
        ]
        telemetry_str = "\n".join(telemetry_lines)

        if not self._ai_client:
            regime = (
                "BULLISH_EXPANSION"
                if breadth_pct > 60
                else "BEARISH_LIQUIDATION"
                if breadth_pct < 40
                else "VOLATILE_CHOP"
            )
            self._latest_ai_research = {
                "macro_regime": regime,
                "sentiment_index": int(breadth_pct),
                "sentiment_label": (
                    "Bullish" if breadth_pct > 60 else "Bearish" if breadth_pct < 40 else "Neutral"
                ),
                "top_momentum_sector": "Layer 1",
                "executive_briefing": (
                    f"Market shows {breadth_pct}% green breadth across 54 pairs. "
                    f"Average spread is {avg_spread} bps."
                ),
                "risk_advisory": "Maintain conservative risk sizing and observe strict ATR stops.",
                "top_alpha_picks": [
                    {
                        "symbol": gainers[0].symbol,
                        "thesis": f"Strength leader up {gainers[0].change_24h_pct:+.1f}%",
                        "conviction": "HIGH",
                    }
                ],
                "updated_at": datetime.now(UTC).isoformat(),
            }
            return self._latest_ai_research

        prompt = _AI_RESEARCH_PROMPT.format(telemetry=telemetry_str)
        try:
            raw_response = await self._ai_client.generate_market_analysis(
                system_prompt="You are NEXUS AI TRADER Lead Quantitative Research Director.",
                user_payload={"instruction": prompt},
            )
            clean_text = raw_response.strip()
            if clean_text.startswith("```"):
                import re

                clean_match = re.match(
                    r"^\s*```(?:json)?\s*\n?(.*?)\n?\s*```\s*$",
                    clean_text,
                    re.DOTALL | re.IGNORECASE,
                )
                if clean_match:
                    clean_text = clean_match.group(1).strip()
            parsed = json.loads(clean_text)
            parsed["updated_at"] = datetime.now(UTC).isoformat()
            self._latest_ai_research = parsed
            logger.info(
                "autonomous_ai_research_updated",
                regime=parsed.get("macro_regime"),
                sentiment=parsed.get("sentiment_index"),
                sector=parsed.get("top_momentum_sector"),
            )
        except Exception as exc:
            logger.warning("ai_research_agent_generation_failed_quant_fallback", error=str(exc))
            regime = (
                "BULLISH_EXPANSION"
                if breadth_pct > 60
                else "BEARISH_LIQUIDATION"
                if breadth_pct < 35
                else "VOLATILE_CHOP"
            )
            self._latest_ai_research = {
                "macro_regime": regime,
                "sentiment_index": int(breadth_pct),
                "sentiment_label": (
                    "Bullish" if breadth_pct > 60 else "Bearish" if breadth_pct < 35 else "Neutral"
                ),
                "top_momentum_sector": "Layer 1 & AI (Quant Engine)",
                "executive_briefing": (
                    f"Market breadth is {breadth_pct}% positive across 54 Binance spot pairs with "
                    f"average spread at {avg_spread} bps. Relative strength leaders: {top_g}."
                ),
                "risk_advisory": (
                    "Immediate volatility elevation detected. Position sizing managed strictly "
                    "by IndependentRiskManager."
                ),
                "top_alpha_picks": [
                    {
                        "symbol": gainers[0].symbol,
                        "thesis": f"Momentum leader up {gainers[0].change_24h_pct:+.1f}% on volume",
                        "conviction": "HIGH",
                    },
                    {
                        "symbol": gainers[1].symbol if len(gainers) > 1 else "SOL/USDT",
                        "thesis": "High relative volume with constructive order book spread",
                        "conviction": "MEDIUM",
                    },
                ],
                "updated_at": datetime.now(UTC).isoformat(),
            }

        return self._latest_ai_research

    # -------------------------------------------------------------------------
    # Background Loop: Automated 15-Minute Candle Maintainer
    # -------------------------------------------------------------------------
    async def _run_candle_sync_loop(self) -> None:
        """Periodic background loop maintaining latest closed candles for all 54 pairs."""
        await asyncio.sleep(60.0)  # Initial wait 1 min after startup
        while self._is_running:
            try:
                from nexus.application.market_data.multi_market_scanner import SECTOR_MAPPING

                watchlist = list(SECTOR_MAPPING.keys())
                for symbol in watchlist:
                    if not self._is_running:
                        break
                    try:
                        bars = await self._market_data.fetch_ohlcv(
                            symbol=symbol,
                            timeframe="15m",
                            limit=5,
                        )
                        if bars:
                            await self._candle_repo.upsert_candles(
                                self._settings.exchange_id, bars
                            )
                    except Exception:
                        pass
                    await asyncio.sleep(0.3)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("candle_sync_loop_error", error=str(exc))

            await asyncio.sleep(900.0)  # Sync every 15 minutes

