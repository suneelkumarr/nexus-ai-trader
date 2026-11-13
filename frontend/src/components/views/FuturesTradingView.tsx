import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CheckCircle2,
  Clock,
  Layers,
  Percent,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  TrendingUp,
  Zap,
} from "lucide-react";
import {
  closeFuturesPosition,
  fetchFuturesFundingRates,
  fetchFuturesPositions,
  fetchFuturesSummary,
  placeFuturesOrder,
  toggleFuturesAutoTrade,
} from "../../services/apiClient";
import type {
  FundingRateInfo,
  FuturesAccountSummary,
  FuturesOrderAction,
  FuturesPosition,
  FuturesSide,
} from "../../types/futures";
import type { TerminalSnapshotResponse } from "../../types/system";
import {
  formatInr,
  formatPct,
  formatQty,
  formatUsdt,
  formatUtcTime,
  toFiniteNumber,
} from "../../utils/format";
import { TradingViewChart } from "../trading/TradingViewChart";

interface FuturesTradingViewProps {
  snapshot: TerminalSnapshotResponse | null;
}

const SUPPORTED_FUTURES_SYMBOLS = [
  "BTC/USDT",
  "ETH/USDT",
  "SOL/USDT",
  "BNB/USDT",
  "XRP/USDT",
  "DOGE/USDT",
] as const;

const LEVERAGE_OPTIONS = [1, 2, 3, 5] as const;

function calculateFundingCountdown(): string {
  const now = new Date();
  const nextHours = [0, 8, 16, 24];
  const currentUtcHour = now.getUTCHours();
  const nextHour = nextHours.find((h) => h > currentUtcHour) ?? 24;
  const target = new Date(now);
  target.setUTCHours(nextHour, 0, 0, 0);
  const diffMs = Math.max(0, target.getTime() - now.getTime());
  const hours = Math.floor(diffMs / 3600000);
  const minutes = Math.floor((diffMs % 3600000) / 60000);
  const seconds = Math.floor((diffMs % 60000) / 1000);
  return `${String(hours).padStart(2, "0")}h ${String(minutes).padStart(2, "0")}m ${String(seconds).padStart(2, "0")}s`;
}

export function FuturesTradingView({ snapshot }: FuturesTradingViewProps) {
  const [summary, setSummary] = useState<FuturesAccountSummary | null>(null);
  const [openPositions, setOpenPositions] = useState<FuturesPosition[]>([]);
  const [allPositions, setAllPositions] = useState<FuturesPosition[]>([]);
  const [fundingRates, setFundingRates] = useState<Record<string, FundingRateInfo>>({});
  const [activeTab, setActiveTab] = useState<"open" | "history">("open");
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [orderError, setOrderError] = useState<string | null>(null);
  const [orderSuccess, setOrderSuccess] = useState<string | null>(null);
  const [fundingCountdown, setFundingCountdown] = useState<string>(calculateFundingCountdown());

  // Order Entry State
  const [selectedSymbol, setSelectedSymbol] = useState<string>("BTC/USDT");
  const [orderSide, setOrderSide] = useState<FuturesSide>("LONG");
  const [leverage, setLeverage] = useState<number>(2);
  const [quantity, setQuantity] = useState<string>("0.002");
  const [stopLoss, setStopLoss] = useState<string>("");
  const [takeProfit, setTakeProfit] = useState<string>("");

  // Countdown timer for 8h funding
  useEffect(() => {
    const timer = setInterval(() => {
      setFundingCountdown(calculateFundingCountdown());
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  // Load futures data periodically
  const loadFuturesData = async () => {
    try {
      const [sum, openPos, histPos, rates] = await Promise.all([
        fetchFuturesSummary(),
        fetchFuturesPositions("open"),
        fetchFuturesPositions("all"),
        fetchFuturesFundingRates(SUPPORTED_FUTURES_SYMBOLS.join(",")),
      ]);
      setSummary(sum);
      setOpenPositions(openPos);
      setAllPositions(histPos);
      setFundingRates(rates);
      setOrderError(null);
    } catch {
      // Quiet fail on periodic polling
    }
  };

  useEffect(() => {
    loadFuturesData();
    const interval = setInterval(loadFuturesData, 4000);
    return () => clearInterval(interval);
  }, []);

  // Compute live estimated mark price from snapshot or funding rates
  const currentTicker = snapshot?.tickers?.find((t) => t.symbol === selectedSymbol);
  const markPrice =
    currentTicker != null
      ? toFiniteNumber(currentTicker.last)
      : fundingRates[selectedSymbol]?.mark_price || 67000;

  const inrRate = 85.0; // Standard USD/INR reference
  const numQty = parseFloat(quantity) || 0;
  const notionalUsd = markPrice * numQty;
  const requiredMarginInr = (notionalUsd / leverage) * inrRate;
  const estFeeInr = notionalUsd * 0.0004 * inrRate;

  // Estimated Liquidation Price Formula (0.5% MMR)
  const mmr = 0.005;
  const estLiqPrice =
    orderSide === "LONG"
      ? markPrice * (1 - 1 / leverage + mmr)
      : markPrice * (1 + 1 / leverage - mmr);

  const liqDistancePct =
    markPrice > 0 ? (Math.abs(markPrice - estLiqPrice) / markPrice) * 100 : 0;

  // Quick percentage sizing
  const setPercentageSize = (pct: number) => {
    const availableCash = summary?.available_cash_inr ?? 10000;
    const targetMarginInr = (availableCash * pct) / 100;
    const targetMarginUsd = targetMarginInr / inrRate;
    const targetNotionalUsd = targetMarginUsd * leverage;
    if (markPrice > 0) {
      const calculatedQty = targetNotionalUsd / markPrice;
      const rounded = calculatedQty < 1 ? calculatedQty.toFixed(4) : calculatedQty.toFixed(2);
      setQuantity(rounded);
    }
  };

  // 1-Click Risk:Reward Presets
  const applyRiskRewardPreset = (slPct: number, tpPct: number) => {
    if (markPrice <= 0) return;
    if (orderSide === "LONG") {
      const sl = markPrice * (1 - slPct / 100);
      const tp = markPrice * (1 + tpPct / 100);
      setStopLoss(markPrice >= 10 ? sl.toFixed(2) : sl.toFixed(4));
      setTakeProfit(markPrice >= 10 ? tp.toFixed(2) : tp.toFixed(4));
    } else {
      const sl = markPrice * (1 + slPct / 100);
      const tp = markPrice * (1 - tpPct / 100);
      setStopLoss(markPrice >= 10 ? sl.toFixed(2) : sl.toFixed(4));
      setTakeProfit(markPrice >= 10 ? tp.toFixed(2) : tp.toFixed(4));
    }
  };

  // Pre-Trade ROI & P&L Simulation
  const preTradeRoi = useMemo(() => {
    const sl = parseFloat(stopLoss);
    const tp = parseFloat(takeProfit);
    if (!sl && !tp) return null;

    let tpUsd = 0;
    let slUsd = 0;

    if (orderSide === "LONG") {
      if (tp && tp > markPrice) tpUsd = (tp - markPrice) * numQty;
      if (sl && sl < markPrice) slUsd = (markPrice - sl) * numQty;
    } else {
      if (tp && tp < markPrice) tpUsd = (markPrice - tp) * numQty;
      if (sl && sl > markPrice) slUsd = (sl - markPrice) * numQty;
    }

    const marginUsd = notionalUsd / leverage;
    const tpRoePct = marginUsd > 0 ? (tpUsd / marginUsd) * 100 : 0;
    const slRoePct = marginUsd > 0 ? (slUsd / marginUsd) * 100 : 0;
    const rrRatio = slUsd > 0 ? tpUsd / slUsd : 0;

    return {
      tpUsd,
      tpInr: tpUsd * inrRate,
      tpRoePct,
      slUsd,
      slInr: slUsd * inrRate,
      slRoePct,
      rrRatio,
    };
  }, [stopLoss, takeProfit, orderSide, markPrice, numQty, notionalUsd, leverage, inrRate]);

  // Order Submission Handler
  const handleOrderSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setOrderError(null);
    setOrderSuccess(null);

    if (numQty <= 0) {
      setOrderError("Please specify a positive contract quantity.");
      return;
    }

    const action: FuturesOrderAction = orderSide === "LONG" ? "OPEN_LONG" : "OPEN_SHORT";

    setActionLoading("placing_order");
    try {
      const res = await placeFuturesOrder({
        symbol: selectedSymbol,
        action,
        quantity: quantity,
        leverage,
        stop_loss_price: stopLoss ? parseFloat(stopLoss) : null,
        take_profit_price: takeProfit ? parseFloat(takeProfit) : null,
      });

      if (res.status === "filled") {
        setOrderSuccess(
          `Successfully opened ${leverage}x ${orderSide} position on ${selectedSymbol} at ${formatUsdt(
            res.executed_price,
          )}!`
        );
        await loadFuturesData();
      } else {
        setOrderError(res.rejection_reason || "Order was rejected.");
      }
    } catch (err: unknown) {
      setOrderError(err instanceof Error ? err.message : "Failed to submit futures order.");
    } finally {
      setActionLoading(null);
    }
  };

  // Close Position Handler
  const handleClosePosition = async (posId: string) => {
    setActionLoading(`closing_${posId}`);
    try {
      await closeFuturesPosition(posId);
      await loadFuturesData();
    } catch (err: unknown) {
      setOrderError(err instanceof Error ? err.message : "Failed to close position.");
    } finally {
      setActionLoading(null);
    }
  };

  // Toggle Autonomous Trading
  const handleToggleAutoTrade = async () => {
    if (!summary) return;
    const nextState = !summary.auto_trade_enabled;
    setActionLoading("toggle_auto");
    try {
      await toggleFuturesAutoTrade(nextState);
      await loadFuturesData();
    } catch (err: unknown) {
      setOrderError(err instanceof Error ? err.message : "Failed to toggle autonomous trading.");
    } finally {
      setActionLoading(null);
    }
  };

  const currentFundingInfo = fundingRates[selectedSymbol];
  const ratePct = currentFundingInfo ? currentFundingInfo.funding_rate_pct : 0.01;

  return (
    <div className="space-y-4 pb-16 font-mono text-slate-100">
      {/* 1. TOP DERIVATIVES CONTRACT HUD BANNER (Bybit / Binance Pro Style) */}
      <div className="glass-card rounded-xl border border-white/[0.08] bg-[#050814]/90 p-4 backdrop-blur-2xl shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-white/[0.06] pb-3.5">
          {/* Contract Selector Pills */}
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-2 mr-2">
              <span className="flex h-2.5 w-2.5 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(0,229,255,0.8)]" />
              <span className="font-display text-sm font-bold uppercase tracking-wider text-white">
                USDT-M Perpetuals
              </span>
            </div>

            <div className="flex items-center rounded-lg border border-white/[0.08] bg-[#090e22]/80 p-0.5">
              {SUPPORTED_FUTURES_SYMBOLS.map((sym) => (
                <button
                  type="button"
                  key={sym}
                  onClick={() => setSelectedSymbol(sym)}
                  className={`rounded-md px-3 py-1 text-xs font-semibold transition ${
                    selectedSymbol === sym
                      ? "bg-cyan-500/20 text-cyan-300 shadow-[0_0_10px_rgba(0,229,255,0.4)]"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {sym.replace("/USDT", "")}
                </button>
              ))}
            </div>
          </div>

          {/* Mark Price & Funding Countdown Telemetry */}
          <div className="flex flex-wrap items-center gap-4 text-xs">
            <div>
              <span className="block text-[10px] text-slate-500 uppercase">Mark Price</span>
              <span className="font-mono text-sm font-bold text-white tabular-nums">
                ${markPrice >= 10 ? markPrice.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : markPrice.toFixed(4)}
              </span>
            </div>

            <div>
              <span className="block text-[10px] text-slate-500 uppercase">8H Funding Rate</span>
              <span
                className={`font-mono text-xs font-bold tabular-nums ${
                  ratePct >= 0 ? "text-emerald-400" : "text-rose-400"
                }`}
              >
                {ratePct >= 0 ? "+" : ""}
                {(ratePct * 100).toFixed(4)}%
              </span>
            </div>

            <div className="flex items-center gap-1.5 rounded-lg border border-white/[0.06] bg-[#080d1e]/80 px-2.5 py-1">
              <Clock className="h-3.5 w-3.5 text-cyan-400" />
              <div>
                <span className="block text-[9px] text-slate-500 uppercase">Next Settlement</span>
                <span className="font-bold text-cyan-300 tabular-nums text-xs">
                  {fundingCountdown}
                </span>
              </div>
            </div>

            {/* AI Auto-Pilot Button */}
            <button
              type="button"
              onClick={handleToggleAutoTrade}
              disabled={actionLoading === "toggle_auto"}
              className={`flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition ${
                summary?.auto_trade_enabled
                  ? "border-emerald-500/40 bg-emerald-500/20 text-emerald-300 shadow-[0_0_12px_rgba(16,185,129,0.3)] hover:bg-emerald-500/30"
                  : "border-white/[0.08] bg-slate-900/60 text-slate-400 hover:text-white"
              }`}
            >
              <Sparkles className={`h-3.5 w-3.5 ${summary?.auto_trade_enabled ? "animate-pulse text-emerald-400" : ""}`} />
              <span>AI AUTO-PILOT:</span>
              <span className="font-bold">{summary?.auto_trade_enabled ? "ACTIVE" : "STANDBY"}</span>
            </button>

            <button
              type="button"
              onClick={loadFuturesData}
              className="rounded-lg border border-white/[0.08] p-2 text-slate-400 transition hover:bg-white/[0.05] hover:text-white"
              title="Refresh Futures Telemetry"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Telemetry KPI Strip */}
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-6 text-xs">
          <div className="rounded-lg border border-white/[0.05] bg-[#080d1e]/70 p-2.5">
            <div className="flex items-center justify-between text-[10px] text-slate-400">
              <span>AVAILABLE MARGIN</span>
              <Layers className="h-3 w-3 text-cyan-400" />
            </div>
            <div className="mt-1 font-bold text-white tabular-nums">
              {formatInr(summary?.available_cash_inr ?? 10000)}
            </div>
            <div className="text-[9px] text-slate-500">Free Virtual INR</div>
          </div>

          <div className="rounded-lg border border-white/[0.05] bg-[#080d1e]/70 p-2.5">
            <div className="flex items-center justify-between text-[10px] text-slate-400">
              <span>LOCKED MARGIN</span>
              <ShieldAlert className="h-3 w-3 text-amber-400" />
            </div>
            <div className="mt-1 font-bold text-amber-300 tabular-nums">
              {formatInr(summary?.total_margin_inr ?? 0)}
            </div>
            <div className="text-[9px] text-slate-500">{openPositions.length} Positions Active</div>
          </div>

          <div className="rounded-lg border border-white/[0.05] bg-[#080d1e]/70 p-2.5">
            <div className="flex items-center justify-between text-[10px] text-slate-400">
              <span>UNREALIZED P&L</span>
              <Activity className="h-3 w-3 text-cyan-400" />
            </div>
            <div
              className={`mt-1 font-bold tabular-nums ${
                toFiniteNumber(summary?.unrealized_pnl_inr) >= 0 ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {formatInr(summary?.unrealized_pnl_inr ?? 0, true)}
            </div>
            <div className="text-[9px] text-slate-500">Live MTM P&L</div>
          </div>

          <div className="rounded-lg border border-white/[0.05] bg-[#080d1e]/70 p-2.5">
            <div className="flex items-center justify-between text-[10px] text-slate-400">
              <span>REALIZED P&L</span>
              <TrendingUp className="h-3 w-3 text-emerald-400" />
            </div>
            <div
              className={`mt-1 font-bold tabular-nums ${
                toFiniteNumber(summary?.realized_pnl_inr) >= 0 ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {formatInr(summary?.realized_pnl_inr ?? 0, true)}
            </div>
            <div className="text-[9px] text-slate-500">Settled Roundtrips</div>
          </div>

          <div className="rounded-lg border border-white/[0.05] bg-[#080d1e]/70 p-2.5">
            <div className="flex items-center justify-between text-[10px] text-slate-400">
              <span>WIN RATE</span>
              <Percent className="h-3 w-3 text-indigo-400" />
            </div>
            <div className="mt-1 font-bold text-indigo-300 tabular-nums">
              {formatPct(summary?.win_rate_pct ?? 0)}
            </div>
            <div className="text-[9px] text-slate-500">{summary?.closed_positions_count ?? 0} Closed Trades</div>
          </div>

          <div className="rounded-lg border border-white/[0.05] bg-[#080d1e]/70 p-2.5">
            <div className="flex items-center justify-between text-[10px] text-slate-400">
              <span>LIQUIDATIONS</span>
              <AlertTriangle className="h-3 w-3 text-rose-400" />
            </div>
            <div
              className={`mt-1 font-bold tabular-nums ${
                (summary?.liquidated_count ?? 0) === 0 ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {summary?.liquidated_count ?? 0}
            </div>
            <div className="text-[9px] text-slate-500">Breached Margin</div>
          </div>
        </div>
      </div>

      {/* 2. MAIN SPLIT: Pro Chart & Positions (8 Cols) vs Order Console (4 Cols) */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        {/* LEFT COLUMN: Candlestick Chart + Open Positions Table (8 Cols) */}
        <div className="space-y-4 xl:col-span-8">
          {/* Interactive TradingView Candlestick Chart */}
          <TradingViewChart snapshot={snapshot} initialSymbol={selectedSymbol} />

          {/* Bottom Deck: Open Positions & History Tabs */}
          <div className="glass-card rounded-xl border border-white/[0.08] bg-[#050814]/90 p-4 backdrop-blur-2xl shadow-xl">
            <div className="flex items-center justify-between border-b border-white/[0.06] pb-3 mb-3">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setActiveTab("open")}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                    activeTab === "open"
                      ? "border border-cyan-500/40 bg-cyan-500/20 text-cyan-300 shadow-[0_0_8px_rgba(0,229,255,0.3)]"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Open Positions ({openPositions.length})
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab("history")}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                    activeTab === "history"
                      ? "border border-cyan-500/40 bg-cyan-500/20 text-cyan-300 shadow-[0_0_8px_rgba(0,229,255,0.3)]"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  Position History ({allPositions.length})
                </button>
              </div>
            </div>

            {activeTab === "open" ? (
              openPositions.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-10 text-center text-xs text-slate-400">
                  <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-slate-800/60 text-slate-500">
                    <Layers className="h-5 w-5" />
                  </div>
                  <span className="font-semibold text-slate-300">No Open Futures Positions</span>
                  <span className="text-[11px] text-slate-500 mt-0.5">
                    Open a simulated Long or Short position on the right or turn on the AI Auto-Pilot.
                  </span>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead>
                      <tr className="border-b border-white/[0.06] text-[10px] uppercase text-slate-500">
                        <th className="pb-2">Contract</th>
                        <th className="pb-2">Size</th>
                        <th className="pb-2">Entry Price</th>
                        <th className="pb-2">Mark Price</th>
                        <th className="pb-2">Liq Price</th>
                        <th className="pb-2">Margin (INR)</th>
                        <th className="pb-2">Unrealized P&L</th>
                        <th className="pb-2">ROE %</th>
                        <th className="pb-2 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/[0.04]">
                      {openPositions.map((pos) => {
                        const isLong = pos.side === "LONG";
                        const pnlInr = toFiniteNumber(pos.unrealized_pnl_inr);
                        const isProfitable = pnlInr >= 0;

                        const currentMark = toFiniteNumber(pos.mark_price);
                        const liqPrice = toFiniteNumber(pos.liquidation_price);
                        const liqDistPct =
                          currentMark > 0 ? Math.abs((currentMark - liqPrice) / currentMark) * 100 : 100;
                        const isLiqNear = liqDistPct < 6.0;

                        return (
                          <tr key={pos.id} className="hover:bg-white/[0.02]">
                            <td className="py-2.5">
                              <div className="font-bold text-white">{pos.symbol}</div>
                              <div className="flex items-center gap-1 mt-0.5">
                                <span
                                  className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${
                                    isLong
                                      ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                      : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                                  }`}
                                >
                                  {pos.side}
                                </span>
                                <span className="rounded bg-amber-500/10 border border-amber-500/30 px-1 py-0.5 text-[9px] font-bold text-amber-300">
                                  {pos.leverage}x Iso
                                </span>
                              </div>
                            </td>
                            <td className="py-2.5 text-slate-300">{formatQty(pos.quantity)}</td>
                            <td className="py-2.5 text-slate-300">{formatUsdt(pos.entry_price)}</td>
                            <td className="py-2.5 font-bold text-white">{formatUsdt(pos.mark_price)}</td>
                            <td className="py-2.5">
                              <span className={isLiqNear ? "text-rose-400 font-bold flex items-center gap-1" : "text-amber-300"}>
                                {formatUsdt(pos.liquidation_price)}
                                {isLiqNear && <AlertTriangle className="h-3 w-3 inline text-rose-400" />}
                              </span>
                            </td>
                            <td className="py-2.5 text-slate-300">{formatInr(pos.initial_margin_inr)}</td>
                            <td className="py-2.5">
                              <div className={`font-bold tabular-nums ${isProfitable ? "text-emerald-400" : "text-rose-400"}`}>
                                {formatInr(pnlInr, true)}
                              </div>
                              <div className="text-[10px] text-slate-500 tabular-nums">
                                {formatUsdt(pos.unrealized_pnl_usd, 2)}
                              </div>
                            </td>
                            <td className="py-2.5">
                              <span className={`font-bold tabular-nums ${isProfitable ? "text-emerald-400" : "text-rose-400"}`}>
                                {formatPct(pos.roe_pct, true)}
                              </span>
                            </td>
                            <td className="py-2.5 text-right">
                              <button
                                type="button"
                                onClick={() => handleClosePosition(pos.id)}
                                disabled={actionLoading === `closing_${pos.id}`}
                                className="rounded border border-slate-700 bg-slate-800/80 px-2.5 py-1 text-[11px] font-semibold text-slate-200 hover:border-rose-500/40 hover:bg-rose-500/20 hover:text-rose-300 transition disabled:opacity-50"
                              >
                                {actionLoading === `closing_${pos.id}` ? "Closing..." : "Close Market"}
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="border-b border-white/[0.06] text-[10px] uppercase text-slate-500">
                      <th className="pb-2">Contract</th>
                      <th className="pb-2">Size</th>
                      <th className="pb-2">Entry Price</th>
                      <th className="pb-2">Exit Price</th>
                      <th className="pb-2">Realized P&L</th>
                      <th className="pb-2">Status</th>
                      <th className="pb-2 text-right">Closed At</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.04]">
                    {allPositions.filter((p) => p.status !== "open").length === 0 ? (
                      <tr>
                        <td colSpan={7} className="py-8 text-center text-slate-500">
                          No closed futures trades recorded yet.
                        </td>
                      </tr>
                    ) : (
                      allPositions
                        .filter((p) => p.status !== "open")
                        .map((pos) => {
                          const pnl = toFiniteNumber(pos.realized_pnl_inr);
                          const isProfit = pnl >= 0;
                          const isLiq = pos.status === "liquidated";
                          return (
                            <tr key={pos.id} className="hover:bg-white/[0.02]">
                              <td className="py-2.5 font-bold text-white">
                                {pos.symbol}{" "}
                                <span
                                  className={`rounded px-1 text-[9px] ${
                                    pos.side === "LONG" ? "bg-emerald-500/20 text-emerald-300" : "bg-rose-500/20 text-rose-300"
                                  }`}
                                >
                                  {pos.side} {pos.leverage}x
                                </span>
                              </td>
                              <td className="py-2.5 text-slate-300">{formatQty(pos.quantity)}</td>
                              <td className="py-2.5 text-slate-300">{formatUsdt(pos.entry_price)}</td>
                              <td className="py-2.5 text-slate-300">{pos.close_price ? formatUsdt(pos.close_price) : "--"}</td>
                              <td className={`py-2.5 font-bold tabular-nums ${isProfit ? "text-emerald-400" : "text-rose-400"}`}>
                                {formatInr(pnl, true)}
                              </td>
                              <td className="py-2.5">
                                <span
                                  className={`rounded px-1.5 py-0.5 text-[9px] font-bold ${
                                    isLiq ? "bg-rose-500/20 text-rose-300 border border-rose-500/30" : "bg-slate-800 text-slate-300"
                                  }`}
                                >
                                  {pos.status.toUpperCase()}
                                </span>
                              </td>
                              <td className="py-2.5 text-right text-slate-500">
                                {formatUtcTime(pos.closed_at)}
                              </td>
                            </tr>
                          );
                        })
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* RIGHT COLUMN: Pro Order Placement Console (4 Cols) */}
        <div className="space-y-4 xl:col-span-4">
          <div className="glass-card rounded-xl border border-white/[0.08] bg-[#050814]/90 p-4.5 backdrop-blur-2xl shadow-xl">
            <div className="flex items-center justify-between border-b border-white/[0.06] pb-3 mb-4">
              <h2 className="flex items-center gap-2 font-display text-xs font-bold uppercase tracking-wider text-white">
                <Zap className="h-4 w-4 text-cyan-400" />
                Derivatives Execution Desk
              </h2>
              <span className="rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-[9px] font-bold text-cyan-300">
                ISOLATED 1x–5x
              </span>
            </div>

            <form onSubmit={handleOrderSubmit} className="space-y-4">
              {/* Long / Short Direction Toggle */}
              <div>
                <label className="block text-[11px] font-medium text-slate-400 mb-1.5">
                  Order Direction
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setOrderSide("LONG")}
                    className={`flex items-center justify-center gap-1.5 rounded-lg py-2.5 text-xs font-bold transition shadow-lg ${
                      orderSide === "LONG"
                        ? "border border-emerald-500 bg-emerald-500/25 text-emerald-300 shadow-[0_0_12px_rgba(16,185,129,0.3)]"
                        : "border border-white/[0.06] bg-[#080d1e]/80 text-slate-400 hover:text-white"
                    }`}
                  >
                    <ArrowUpRight className="h-4 w-4" />
                    OPEN LONG (BUY)
                  </button>
                  <button
                    type="button"
                    onClick={() => setOrderSide("SHORT")}
                    className={`flex items-center justify-center gap-1.5 rounded-lg py-2.5 text-xs font-bold transition shadow-lg ${
                      orderSide === "SHORT"
                        ? "border border-rose-500 bg-rose-500/25 text-rose-300 shadow-[0_0_12px_rgba(244,63,94,0.3)]"
                        : "border border-white/[0.06] bg-[#080d1e]/80 text-slate-400 hover:text-white"
                    }`}
                  >
                    <ArrowDownRight className="h-4 w-4" />
                    OPEN SHORT (SELL)
                  </button>
                </div>
              </div>

              {/* Leverage Selector */}
              <div>
                <label className="block text-[11px] font-medium text-slate-400 mb-1.5">
                  Leverage (Isolated Zero-Debt)
                </label>
                <div className="grid grid-cols-4 gap-1.5">
                  {LEVERAGE_OPTIONS.map((lev) => (
                    <button
                      type="button"
                      key={lev}
                      onClick={() => setLeverage(lev)}
                      className={`rounded-lg py-1.5 text-xs font-bold transition ${
                        leverage === lev
                          ? "border border-amber-500/60 bg-amber-500/20 text-amber-300 shadow-[0_0_8px_rgba(245,158,11,0.3)]"
                          : "border border-white/[0.06] bg-[#080d1e]/80 text-slate-400 hover:text-white"
                      }`}
                    >
                      {lev}x
                    </button>
                  ))}
                </div>
              </div>

              {/* Quantity Input + Sizing % */}
              <div>
                <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1.5">
                  <span>Contract Size ({selectedSymbol.split("/")[0]})</span>
                  <span className="font-semibold text-cyan-300 tabular-nums">
                    Notional: {formatUsdt(notionalUsd)}
                  </span>
                </div>
                <input
                  type="number"
                  step="any"
                  min="0.000001"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  placeholder="e.g. 0.002"
                  className="w-full rounded-lg border border-white/[0.08] bg-[#090e22]/90 px-3 py-2 text-xs font-mono text-white placeholder-slate-600 focus:border-cyan-500/60 outline-none shadow-inner"
                />

                <div className="mt-1.5 grid grid-cols-4 gap-1.5">
                  {[25, 50, 75, 100].map((pct) => (
                    <button
                      key={pct}
                      type="button"
                      onClick={() => setPercentageSize(pct)}
                      className="rounded-md border border-white/[0.06] bg-[#080d1e]/80 py-1 text-[10px] font-semibold text-slate-400 hover:border-cyan-500/40 hover:text-cyan-300 transition"
                    >
                      {pct === 100 ? "MAX" : `${pct}%`}
                    </button>
                  ))}
                </div>
              </div>

              {/* 1-Click Smart Risk:Reward SL/TP Presets */}
              <div>
                <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1.5">
                  <span>Smart SL / TP Presets</span>
                  <span className="text-[10px] text-slate-500">Auto-calculated</span>
                </div>
                <div className="grid grid-cols-3 gap-1.5 text-[10px]">
                  <button
                    type="button"
                    onClick={() => applyRiskRewardPreset(1.5, 3.0)}
                    className="rounded-md border border-white/[0.06] bg-[#080d1e]/80 py-1 text-slate-300 hover:border-cyan-500/40 hover:text-cyan-300 transition"
                  >
                    R:R 1:2 (1.5%/3%)
                  </button>
                  <button
                    type="button"
                    onClick={() => applyRiskRewardPreset(1.0, 3.0)}
                    className="rounded-md border border-white/[0.06] bg-[#080d1e]/80 py-1 text-slate-300 hover:border-cyan-500/40 hover:text-cyan-300 transition"
                  >
                    R:R 1:3 (1%/3%)
                  </button>
                  <button
                    type="button"
                    onClick={() => applyRiskRewardPreset(0.8, 1.6)}
                    className="rounded-md border border-white/[0.06] bg-[#080d1e]/80 py-1 text-slate-300 hover:border-cyan-500/40 hover:text-cyan-300 transition"
                  >
                    Scalp (0.8%/1.6%)
                  </button>
                </div>
              </div>

              {/* Manual Stop-Loss & Take-Profit Inputs */}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-[10px] font-medium text-slate-400 mb-1">
                    Stop-Loss Price ($)
                  </label>
                  <input
                    type="number"
                    step="any"
                    value={stopLoss}
                    onChange={(e) => setStopLoss(e.target.value)}
                    placeholder="SL Price"
                    className="w-full rounded-lg border border-white/[0.08] bg-[#090e22]/90 px-2.5 py-1.5 text-xs text-white placeholder-slate-600 focus:border-cyan-500/60 outline-none"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-medium text-slate-400 mb-1">
                    Take-Profit Price ($)
                  </label>
                  <input
                    type="number"
                    step="any"
                    value={takeProfit}
                    onChange={(e) => setTakeProfit(e.target.value)}
                    placeholder="TP Price"
                    className="w-full rounded-lg border border-white/[0.08] bg-[#090e22]/90 px-2.5 py-1.5 text-xs text-white placeholder-slate-600 focus:border-cyan-500/60 outline-none"
                  />
                </div>
              </div>

              {/* Dynamic Liquidation Distance Visual Meter */}
              <div className="rounded-lg border border-white/[0.06] bg-[#080d1e]/80 p-3 space-y-2 text-xs">
                <div className="flex justify-between items-center text-[11px]">
                  <span className="text-slate-400">Est. Liquidation Price:</span>
                  <span className="font-bold text-amber-300 tabular-nums">
                    {formatUsdt(estLiqPrice)}
                  </span>
                </div>

                <div>
                  <div className="flex justify-between text-[10px] text-slate-500 mb-1">
                    <span>Liquidation Safety Buffer</span>
                    <span
                      className={`font-bold ${
                        liqDistancePct > 15
                          ? "text-emerald-400"
                          : liqDistancePct > 8
                            ? "text-amber-400"
                            : "text-rose-400"
                      }`}
                    >
                      {liqDistancePct.toFixed(1)}% Distance (
                      {liqDistancePct > 15 ? "SAFE 🟢" : liqDistancePct > 8 ? "MODERATE 🟡" : "HIGH RISK 🔴"}
                      )
                    </span>
                  </div>

                  {/* Buffer Progress Bar */}
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                    <div
                      style={{ width: `${Math.min(100, (liqDistancePct / 30) * 100)}%` }}
                      className={`h-full transition-all duration-300 ${
                        liqDistancePct > 15
                          ? "bg-emerald-400"
                          : liqDistancePct > 8
                            ? "bg-amber-400"
                            : "bg-rose-500"
                      }`}
                    />
                  </div>
                </div>

                <div className="flex justify-between text-slate-400 text-[11px] pt-1 border-t border-white/[0.04]">
                  <span>Required Margin (INR):</span>
                  <span className="font-bold text-white tabular-nums">{formatInr(requiredMarginInr)}</span>
                </div>
                <div className="flex justify-between text-slate-400 text-[11px]">
                  <span>Est. Taker Fee (0.04%):</span>
                  <span className="text-slate-300 tabular-nums">{formatInr(estFeeInr)}</span>
                </div>
              </div>

              {/* Pre-Trade ROI & P&L Simulation Card */}
              {preTradeRoi && (
                <div className="rounded-lg border border-cyan-500/30 bg-[#091528]/80 p-3 space-y-1.5 text-[11px]">
                  <div className="flex items-center justify-between font-bold text-cyan-300 border-b border-cyan-500/20 pb-1">
                    <span>Pre-Trade Simulation</span>
                    <span>R:R {preTradeRoi.rrRatio.toFixed(2)}x</span>
                  </div>
                  {preTradeRoi.tpUsd > 0 && (
                    <div className="flex justify-between text-emerald-400">
                      <span>Target Profit (TP):</span>
                      <span className="font-bold tabular-nums">
                        +${preTradeRoi.tpUsd.toFixed(2)} (+₹{preTradeRoi.tpInr.toFixed(0)}) · +{preTradeRoi.tpRoePct.toFixed(1)}% ROE
                      </span>
                    </div>
                  )}
                  {preTradeRoi.slUsd > 0 && (
                    <div className="flex justify-between text-rose-400">
                      <span>Max Loss (SL):</span>
                      <span className="font-bold tabular-nums">
                        -${preTradeRoi.slUsd.toFixed(2)} (-₹{preTradeRoi.slInr.toFixed(0)}) · -{preTradeRoi.slRoePct.toFixed(1)}% ROE
                      </span>
                    </div>
                  )}
                </div>
              )}

              {/* Alerts */}
              {orderError && (
                <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-2.5 text-xs text-rose-300 flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />
                  <span>{orderError}</span>
                </div>
              )}
              {orderSuccess && (
                <div className="rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-2.5 text-xs text-emerald-300 flex items-center gap-2">
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-400" />
                  <span>{orderSuccess}</span>
                </div>
              )}

              {/* Submit Button */}
              <button
                type="submit"
                disabled={actionLoading === "placing_order"}
                className={`w-full rounded-xl py-3 text-xs font-bold transition shadow-lg ${
                  orderSide === "LONG"
                    ? "bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-600/30"
                    : "bg-rose-600 hover:bg-rose-500 text-white shadow-rose-600/30"
                } disabled:opacity-50`}
              >
                {actionLoading === "placing_order"
                  ? "Simulating Order Execution..."
                  : `SUBMIT ${leverage}x ${orderSide} ORDER`}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
