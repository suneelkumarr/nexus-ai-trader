import { useEffect, useState } from "react";
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Clock,
  Layers,
  Percent,
  Play,
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

export function FuturesTradingView({ snapshot }: FuturesTradingViewProps) {
  const [summary, setSummary] = useState<FuturesAccountSummary | null>(null);
  const [openPositions, setOpenPositions] = useState<FuturesPosition[]>([]);
  const [allPositions, setAllPositions] = useState<FuturesPosition[]>([]);
  const [fundingRates, setFundingRates] = useState<Record<string, FundingRateInfo>>({});
  const [activeTab, setActiveTab] = useState<"open" | "history">("open");
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [orderError, setOrderError] = useState<string | null>(null);
  const [orderSuccess, setOrderSuccess] = useState<string | null>(null);

  // Order Entry State
  const [selectedSymbol, setSelectedSymbol] = useState<string>("BTC/USDT");
  const [orderSide, setOrderSide] = useState<FuturesSide>("LONG");
  const [leverage, setLeverage] = useState<number>(2);
  const [quantity, setQuantity] = useState<string>("0.002");
  const [stopLoss, setStopLoss] = useState<string>("");
  const [takeProfit, setTakeProfit] = useState<string>("");

  // Load futures data
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
      : fundingRates[selectedSymbol]?.mark_price || 60000;

  const inrRate = 85.0; // Standard USD/INR reference
  const numQty = parseFloat(quantity) || 0;
  const notionalUsd = markPrice * numQty;
  const requiredMarginInr = (notionalUsd / leverage) * inrRate;
  const estFeeInr = notionalUsd * 0.0004 * inrRate;

  // Estimated Liquidation Price Formula
  const mmr = 0.005; // 0.5% MMR
  const estLiqPrice =
    orderSide === "LONG"
      ? markPrice * (1 - 1 / leverage + mmr)
      : markPrice * (1 + 1 / leverage - mmr);

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

  return (
    <div className="space-y-6 pb-20">
      {/* View Header */}
      <div className="relative overflow-hidden rounded-2xl border border-cyan-500/20 bg-gradient-to-r from-[#0d1527]/90 via-[#0a1120]/95 to-[#0b172a]/90 p-6 shadow-2xl backdrop-blur-xl">
        <div className="absolute right-0 top-0 -mr-16 -mt-16 h-64 w-64 rounded-full bg-cyan-500/10 blur-3xl" />
        <div className="relative flex flex-col justify-between gap-4 md:flex-row md:items-center">
          <div>
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 shadow-inner">
                <Zap className="h-5 w-5" />
              </span>
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                  USDT-M Futures Paper Terminal
                  <span className="rounded-md border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-xs font-mono font-medium text-cyan-300">
                    ISOLATED 1x–5x
                  </span>
                </h1>
                <p className="text-xs text-slate-400">
                  Real-time perpetual contract simulation with live Binance funding rates, short selling, and zero capital risk.
                </p>
              </div>
            </div>
          </div>

          {/* Autonomous Futures Trader Toggle */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleToggleAutoTrade}
              disabled={actionLoading === "toggle_auto"}
              className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-xs font-mono font-semibold transition-all shadow-lg ${
                summary?.auto_trade_enabled
                  ? "border border-emerald-500/40 bg-emerald-500/20 text-emerald-300 shadow-emerald-500/10 hover:bg-emerald-500/30"
                  : "border border-slate-700 bg-slate-800/80 text-slate-300 hover:bg-slate-800"
              }`}
            >
              <Sparkles className={`h-4 w-4 ${summary?.auto_trade_enabled ? "animate-pulse text-emerald-400" : "text-slate-400"}`} />
              <span>AI Auto-Pilot:</span>
              <span className={`font-bold uppercase ${summary?.auto_trade_enabled ? "text-emerald-400" : "text-slate-400"}`}>
                {summary?.auto_trade_enabled ? "ACTIVE" : "STANDBY"}
              </span>
            </button>
            <button
              type="button"
              onClick={loadFuturesData}
              className="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-700/60 bg-slate-800/60 text-slate-400 hover:text-white transition-colors"
              title="Refresh Telemetry"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Metrics Ribbon */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <div className="rounded-xl border border-slate-800/80 bg-slate-900/60 p-4 backdrop-blur-md">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span>Available Margin</span>
            <Layers className="h-3.5 w-3.5 text-cyan-400" />
          </div>
          <div className="text-lg font-mono font-bold text-white">
            {formatInr(summary?.available_cash_inr ?? 10000)}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">Free Virtual Balance</div>
        </div>

        <div className="rounded-xl border border-slate-800/80 bg-slate-900/60 p-4 backdrop-blur-md">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span>Locked Margin</span>
            <ShieldAlert className="h-3.5 w-3.5 text-amber-400" />
          </div>
          <div className="text-lg font-mono font-bold text-amber-300">
            {formatInr(summary?.total_margin_inr ?? 0)}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">{openPositions.length} Active Positions</div>
        </div>

        <div className="rounded-xl border border-slate-800/80 bg-slate-900/60 p-4 backdrop-blur-md">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span>Unrealized P&L</span>
            <Activity className="h-3.5 w-3.5 text-cyan-400" />
          </div>
          <div
            className={`text-lg font-mono font-bold ${
              toFiniteNumber(summary?.unrealized_pnl_inr) >= 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {formatInr(summary?.unrealized_pnl_inr ?? 0, true)}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">Live Open P&L</div>
        </div>

        <div className="rounded-xl border border-slate-800/80 bg-slate-900/60 p-4 backdrop-blur-md">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span>Realized P&L</span>
            <TrendingUp className="h-3.5 w-3.5 text-emerald-400" />
          </div>
          <div
            className={`text-lg font-mono font-bold ${
              toFiniteNumber(summary?.realized_pnl_inr) >= 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {formatInr(summary?.realized_pnl_inr ?? 0, true)}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">Settled Roundtrips</div>
        </div>

        <div className="rounded-xl border border-slate-800/80 bg-slate-900/60 p-4 backdrop-blur-md">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span>Win Rate</span>
            <Percent className="h-3.5 w-3.5 text-indigo-400" />
          </div>
          <div className="text-lg font-mono font-bold text-indigo-300">
            {formatPct(summary?.win_rate_pct ?? 0)}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">
            {summary?.closed_positions_count ?? 0} Closed Trades
          </div>
        </div>

        <div className="rounded-xl border border-slate-800/80 bg-slate-900/60 p-4 backdrop-blur-md">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span>Liquidations</span>
            <AlertTriangle className="h-3.5 w-3.5 text-rose-400" />
          </div>
          <div
            className={`text-lg font-mono font-bold ${
              (summary?.liquidated_count ?? 0) === 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {summary?.liquidated_count ?? 0}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">Breached Margin</div>
        </div>
      </div>

      {/* Main Grid: Order Entry & Live Funding Telemetry */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left Column: Order Placement Console (7 cols) */}
        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6 backdrop-blur-xl lg:col-span-7 shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-800/80 pb-4 mb-5">
            <h2 className="text-base font-semibold text-white flex items-center gap-2">
              <Play className="h-4 w-4 text-cyan-400" />
              Futures Order Desk
            </h2>
            <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
              <span>Mark Price:</span>
              <span className="font-bold text-white">{formatUsdt(markPrice)}</span>
            </div>
          </div>

          <form onSubmit={handleOrderSubmit} className="space-y-5">
            {/* Symbol & Direction Selection */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-2">
                  Contract Symbol
                </label>
                <div className="grid grid-cols-3 gap-1.5">
                  {SUPPORTED_FUTURES_SYMBOLS.map((sym) => (
                    <button
                      type="button"
                      key={sym}
                      onClick={() => setSelectedSymbol(sym)}
                      className={`rounded-lg py-2 text-xs font-mono font-medium transition-all ${
                        selectedSymbol === sym
                          ? "border border-cyan-500/50 bg-cyan-500/20 text-cyan-300 shadow-sm"
                          : "border border-slate-800 bg-slate-950/40 text-slate-400 hover:bg-slate-800 hover:text-white"
                      }`}
                    >
                      {sym.replace("/USDT", "")}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-400 mb-2">
                  Leverage (Isolated)
                </label>
                <div className="grid grid-cols-4 gap-1.5">
                  {LEVERAGE_OPTIONS.map((lev) => (
                    <button
                      type="button"
                      key={lev}
                      onClick={() => setLeverage(lev)}
                      className={`rounded-lg py-2 text-xs font-mono font-bold transition-all ${
                        leverage === lev
                          ? "border border-amber-500/50 bg-amber-500/20 text-amber-300 shadow-sm"
                          : "border border-slate-800 bg-slate-950/40 text-slate-400 hover:bg-slate-800 hover:text-white"
                      }`}
                    >
                      {lev}x
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Long / Short Toggle */}
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-2">
                Order Direction
              </label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setOrderSide("LONG")}
                  className={`flex items-center justify-center gap-2 rounded-xl py-3 text-sm font-bold transition-all ${
                    orderSide === "LONG"
                      ? "border border-emerald-500 bg-emerald-500/20 text-emerald-300 shadow-lg shadow-emerald-500/10"
                      : "border border-slate-800 bg-slate-950/40 text-slate-400 hover:bg-slate-800/60"
                  }`}
                >
                  <ArrowUpRight className="h-4 w-4" />
                  OPEN LONG (BUY)
                </button>
                <button
                  type="button"
                  onClick={() => setOrderSide("SHORT")}
                  className={`flex items-center justify-center gap-2 rounded-xl py-3 text-sm font-bold transition-all ${
                    orderSide === "SHORT"
                      ? "border border-rose-500 bg-rose-500/20 text-rose-300 shadow-lg shadow-rose-500/10"
                      : "border border-slate-800 bg-slate-950/40 text-slate-400 hover:bg-slate-800/60"
                  }`}
                >
                  <ArrowDownRight className="h-4 w-4" />
                  OPEN SHORT (SELL)
                </button>
              </div>
            </div>

            {/* Quantity Input */}
            <div>
              <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
                <span>Contract Quantity ({selectedSymbol.split("/")[0]})</span>
                <span>Notional: {formatUsdt(notionalUsd)}</span>
              </div>
              <input
                type="number"
                step="any"
                min="0.000001"
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                placeholder="e.g. 0.002"
                className="w-full rounded-xl border border-slate-800 bg-slate-950/80 px-4 py-2.5 text-sm font-mono text-white placeholder-slate-600 focus:border-cyan-500 focus:outline-none focus:ring-1 focus:ring-cyan-500"
              />
            </div>

            {/* Stop-Loss & Take-Profit (Optional) */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">
                  Stop-Loss Price ($)
                </label>
                <input
                  type="number"
                  step="any"
                  value={stopLoss}
                  onChange={(e) => setStopLoss(e.target.value)}
                  placeholder={`Optional SL`}
                  className="w-full rounded-xl border border-slate-800 bg-slate-950/80 px-3 py-2 text-xs font-mono text-white placeholder-slate-600 focus:border-cyan-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-400 mb-1">
                  Take-Profit Price ($)
                </label>
                <input
                  type="number"
                  step="any"
                  value={takeProfit}
                  onChange={(e) => setTakeProfit(e.target.value)}
                  placeholder={`Optional TP`}
                  className="w-full rounded-xl border border-slate-800 bg-slate-950/80 px-3 py-2 text-xs font-mono text-white placeholder-slate-600 focus:border-cyan-500 focus:outline-none"
                />
              </div>
            </div>

            {/* Dynamic Risk & Calculation Box */}
            <div className="rounded-xl border border-slate-800/90 bg-slate-950/70 p-4 space-y-2 text-xs font-mono">
              <div className="flex justify-between text-slate-400">
                <span>Required Margin (INR):</span>
                <span className="font-bold text-white">{formatInr(requiredMarginInr)}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Est. Liquidation Price:</span>
                <span className="font-bold text-amber-300">{formatUsdt(estLiqPrice)}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Est. Taker Fee (0.04%):</span>
                <span className="text-slate-300">{formatInr(estFeeInr)}</span>
              </div>
            </div>

            {/* Error & Success Messages */}
            {orderError && (
              <div className="rounded-xl border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-300 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400" />
                <span>{orderError}</span>
              </div>
            )}
            {orderSuccess && (
              <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/10 p-3 text-xs text-emerald-300 flex items-center gap-2">
                <Sparkles className="h-4 w-4 shrink-0 text-emerald-400" />
                <span>{orderSuccess}</span>
              </div>
            )}

            {/* Submit Button */}
            <button
              type="submit"
              disabled={actionLoading === "placing_order"}
              className={`w-full rounded-xl py-3.5 text-sm font-bold transition-all shadow-lg ${
                orderSide === "LONG"
                  ? "bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-600/25"
                  : "bg-rose-600 hover:bg-rose-500 text-white shadow-rose-600/25"
              } disabled:opacity-50`}
            >
              {actionLoading === "placing_order"
                ? "Simulating Order Execution..."
                : `SUBMIT ${leverage}x ${orderSide} ORDER`}
            </button>
          </form>
        </div>

        {/* Right Column: Real-time Funding Rates & Market Dynamics (5 cols) */}
        <div className="space-y-6 lg:col-span-5">
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6 backdrop-blur-xl shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-800/80 pb-4 mb-4">
              <h2 className="text-base font-semibold text-white flex items-center gap-2">
                <Clock className="h-4 w-4 text-cyan-400" />
                Binance USDT-M Funding
              </h2>
              <span className="rounded bg-cyan-500/10 border border-cyan-500/20 px-2 py-0.5 text-[10px] font-mono text-cyan-300">
                8h Periodic
              </span>
            </div>

            <div className="space-y-2.5">
              {SUPPORTED_FUTURES_SYMBOLS.map((sym) => {
                const info = fundingRates[sym];
                const ratePct = info ? info.funding_rate_pct : 0.01;
                const isPositive = ratePct >= 0;

                return (
                  <div
                    key={sym}
                    className="flex items-center justify-between rounded-xl border border-slate-800/60 bg-slate-950/40 px-3.5 py-2.5"
                  >
                    <div>
                      <div className="text-xs font-mono font-bold text-white">{sym}</div>
                      <div className="text-[10px] text-slate-500 font-mono">
                        Mark: {formatUsdt(info?.mark_price ?? 0)}
                      </div>
                    </div>

                    <div className="text-right">
                      <div
                        className={`text-xs font-mono font-bold flex items-center justify-end gap-1 ${
                          isPositive ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {isPositive ? "+" : ""}
                        {ratePct.toFixed(4)}%
                      </div>
                      <div className="text-[10px] text-slate-500">
                        {isPositive ? "Longs pay Shorts" : "Shorts pay Longs"}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="mt-4 rounded-xl border border-slate-800/80 bg-slate-950/40 p-3 text-[11px] text-slate-400 space-y-1">
              <div className="font-semibold text-slate-300">How Funding Works:</div>
              <div>• Positive rate: Long traders pay short traders to hold the peg.</div>
              <div>• Negative rate: Short traders pay long traders.</div>
              <div>• Settled automatically inside virtual paper ledger.</div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Deck: Open Positions & Position History */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-6 backdrop-blur-xl shadow-xl">
        <div className="flex items-center justify-between border-b border-slate-800/80 pb-4 mb-4">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setActiveTab("open")}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                activeTab === "open"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Open Positions ({openPositions.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("history")}
              className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                activeTab === "history"
                  ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              Position History ({allPositions.length})
            </button>
          </div>
        </div>

        {activeTab === "open" ? (
          openPositions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <div className="h-12 w-12 rounded-full bg-slate-800/60 flex items-center justify-center text-slate-500 mb-3">
                <Layers className="h-6 w-6" />
              </div>
              <div className="text-sm font-semibold text-slate-300">No Open Futures Positions</div>
              <div className="text-xs text-slate-500 max-w-sm mt-1">
                Open a simulated Long or Short position above or toggle the AI Auto-Pilot to trade automatically.
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-400">
                    <th className="pb-3 font-medium">Symbol / Side</th>
                    <th className="pb-3 font-medium">Size</th>
                    <th className="pb-3 font-medium">Entry Price</th>
                    <th className="pb-3 font-medium">Mark Price</th>
                    <th className="pb-3 font-medium">Liq Price</th>
                    <th className="pb-3 font-medium">Margin (INR)</th>
                    <th className="pb-3 font-medium">Unrealized P&L</th>
                    <th className="pb-3 font-medium">ROE %</th>
                    <th className="pb-3 font-medium text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {openPositions.map((pos) => {
                    const isLong = pos.side === "LONG";
                    const pnlInr = toFiniteNumber(pos.unrealized_pnl_inr);
                    const isProfitable = pnlInr >= 0;

                    // Liquidation distance check
                    const currentMark = toFiniteNumber(pos.mark_price);
                    const liqPrice = toFiniteNumber(pos.liquidation_price);
                    const liqDistPct =
                      currentMark > 0
                        ? Math.abs((currentMark - liqPrice) / currentMark) * 100
                        : 100;
                    const isLiqNear = liqDistPct < 5.0;

                    return (
                      <tr key={pos.id} className="hover:bg-slate-800/30">
                        <td className="py-3.5">
                          <div className="font-bold text-white">{pos.symbol}</div>
                          <div className="flex items-center gap-1.5 mt-0.5">
                            <span
                              className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                                isLong
                                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                                  : "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                              }`}
                            >
                              {pos.side}
                            </span>
                            <span className="rounded bg-amber-500/10 border border-amber-500/30 px-1 py-0.5 text-[10px] font-bold text-amber-300">
                              {pos.leverage}x Iso
                            </span>
                          </div>
                        </td>
                        <td className="py-3.5 text-slate-300">{formatQty(pos.quantity)}</td>
                        <td className="py-3.5 text-slate-300">{formatUsdt(pos.entry_price)}</td>
                        <td className="py-3.5 font-bold text-white">{formatUsdt(pos.mark_price)}</td>
                        <td className="py-3.5">
                          <span className={isLiqNear ? "text-rose-400 font-bold flex items-center gap-1" : "text-amber-300"}>
                            {formatUsdt(pos.liquidation_price)}
                            {isLiqNear && <AlertTriangle className="h-3 w-3 inline" />}
                          </span>
                        </td>
                        <td className="py-3.5 text-slate-300">{formatInr(pos.initial_margin_inr)}</td>
                        <td className="py-3.5">
                          <div
                            className={`font-bold ${isProfitable ? "text-emerald-400" : "text-rose-400"}`}
                          >
                            {formatInr(pnlInr, true)}
                          </div>
                          <div className="text-[10px] text-slate-500">
                            {formatUsdt(pos.unrealized_pnl_usd, 2)}
                          </div>
                        </td>
                        <td className="py-3.5">
                          <span
                            className={`font-bold ${isProfitable ? "text-emerald-400" : "text-rose-400"}`}
                          >
                            {formatPct(pos.roe_pct, true)}
                          </span>
                        </td>
                        <td className="py-3.5 text-right">
                          <button
                            type="button"
                            onClick={() => handleClosePosition(pos.id)}
                            disabled={actionLoading === `closing_${pos.id}`}
                            className="rounded-lg border border-slate-700 bg-slate-800/80 px-2.5 py-1 text-[11px] font-semibold text-slate-200 hover:border-rose-500/40 hover:bg-rose-500/20 hover:text-rose-300 transition-all disabled:opacity-50"
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
                <tr className="border-b border-slate-800 text-slate-400">
                  <th className="pb-3 font-medium">Symbol / Side</th>
                  <th className="pb-3 font-medium">Size</th>
                  <th className="pb-3 font-medium">Entry Price</th>
                  <th className="pb-3 font-medium">Exit Price</th>
                  <th className="pb-3 font-medium">Realized P&L</th>
                  <th className="pb-3 font-medium">Status / Reason</th>
                  <th className="pb-3 font-medium text-right">Closed At</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {allPositions.filter((p) => p.status !== "open").length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-slate-500">
                      No closed futures trades yet.
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
                        <tr key={pos.id} className="hover:bg-slate-800/30">
                          <td className="py-3.5">
                            <span className="font-bold text-white">{pos.symbol}</span>{" "}
                            <span
                              className={`rounded px-1 text-[10px] ${
                                pos.side === "LONG"
                                  ? "bg-emerald-500/20 text-emerald-300"
                                  : "bg-rose-500/20 text-rose-300"
                              }`}
                            >
                              {pos.side} {pos.leverage}x
                            </span>
                          </td>
                          <td className="py-3.5 text-slate-300">{formatQty(pos.quantity)}</td>
                          <td className="py-3.5 text-slate-300">{formatUsdt(pos.entry_price)}</td>
                          <td className="py-3.5 text-slate-300">
                            {pos.close_price ? formatUsdt(pos.close_price) : "--"}
                          </td>
                          <td className="py-3.5 font-bold">
                            <span className={isProfit ? "text-emerald-400" : "text-rose-400"}>
                              {formatInr(pnl, true)}
                            </span>
                          </td>
                          <td className="py-3.5">
                            <span
                              className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                                isLiq
                                  ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                                  : "bg-slate-800 text-slate-300"
                              }`}
                            >
                              {pos.status.toUpperCase()}
                            </span>
                            {pos.close_reason && (
                              <span className="text-[10px] text-slate-500 block truncate max-w-[200px]">
                                {pos.close_reason}
                              </span>
                            )}
                          </td>
                          <td className="py-3.5 text-right text-slate-500">
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
  );
}
