import { useState } from "react";
import {
  Activity,
  AlertOctagon,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Wifi,
  WifiOff,
  X,
  FileSpreadsheet,
  Scale,
  Swords,
  Zap,
} from "lucide-react";
import { InstitutionalTearsheetModal } from "./common/InstitutionalTearsheetModal";
import { PortfolioOptimizerModal } from "./common/PortfolioOptimizerModal";
import { CouncilOfQuantsDebateModal } from "./common/CouncilOfQuantsDebateModal";
import type {
  EmergencyStopResponse,
  TerminalSnapshotResponse,
  WebSocketStatus,
} from "../types/system";
import { formatInr, formatUsdt, toFiniteNumber } from "../utils/format";

interface TopBarProps {
  snapshot: TerminalSnapshotResponse | null;
  wsStatus: WebSocketStatus;
  emergencyPending: boolean;
  lastEmergencyResponse: EmergencyStopResponse | null;
  executionMode?: "paper" | "live_binance";
  onRefresh: () => Promise<void>;
  onActivateEmergencyStop: (
    reason: string,
    flattenPositions: boolean,
  ) => Promise<EmergencyStopResponse>;
  onSetExecutionMode?: (mode: "paper" | "live_binance") => Promise<void>;
}

export function TopBar({
  snapshot,
  wsStatus,
  emergencyPending,
  lastEmergencyResponse: _lastEmergencyResponse,
  executionMode = "paper",
  onRefresh,
  onActivateEmergencyStop,
  onSetExecutionMode,
}: TopBarProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [flattenPositions, setFlattenPositions] = useState(true);
  const [stopReason, setStopReason] = useState(
    "Manual emergency stop triggered from NEXUS Terminal.",
  );
  const [stopError, setStopError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [tearsheetOpen, setTearsheetOpen] = useState(false);
  const [optimizerOpen, setOptimizerOpen] = useState(false);
  const [councilOpen, setCouncilOpen] = useState(false);

  // Execution Mode Switcher State
  const [modeConfirmOpen, setModeConfirmOpen] = useState(false);
  const [pendingTargetMode, setPendingTargetMode] = useState<"paper" | "live_binance">("paper");
  const [switchingMode, setSwitchingMode] = useState(false);
  const [modeError, setModeError] = useState<string | null>(null);

  const killSwitchActive = snapshot?.risk.kill_switch_active ?? false;
  const engineOk = snapshot?.engine_health.overall_status === "ok";
  const quoteLive = snapshot?.portfolio.quote_status === "live";

  function handleTriggerModeSwitch(target: "paper" | "live_binance") {
    if (target === executionMode) return;
    setPendingTargetMode(target);
    setModeError(null);
    setModeConfirmOpen(true);
  }

  async function handleConfirmModeSwitch(): Promise<void> {
    if (!onSetExecutionMode) return;
    setSwitchingMode(true);
    setModeError(null);
    try {
      await onSetExecutionMode(pendingTargetMode);
      setModeConfirmOpen(false);
    } catch (err) {
      setModeError(err instanceof Error ? err.message : "Failed to switch execution mode.");
    } finally {
      setSwitchingMode(false);
    }
  }

  async function handleRefresh(): Promise<void> {
    setRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setRefreshing(false);
    }
  }

  async function handleConfirmEmergencyStop(): Promise<void> {
    setStopError(null);
    const trimmed = stopReason.trim();
    if (trimmed.length < 3) {
      setStopError("Reason must be at least 3 characters.");
      return;
    }
    try {
      await onActivateEmergencyStop(trimmed, flattenPositions);
      setConfirmOpen(false);
    } catch (err) {
      setStopError(
        err instanceof Error ? err.message : "Failed to trigger emergency stop.",
      );
    }
  }

  return (
    <header className="border-b border-white/[0.08] bg-[#070d1e]/90 backdrop-blur-2xl shadow-xl shadow-black/40">
      {/* Primary Brand + Telemetry + Emergency Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 sm:px-6">
        {/* Brand Identity */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2.5">
            <span className="relative flex h-3 w-3 items-center justify-center">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400 opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-cyan-400 shadow-[0_0_10px_rgba(0,229,255,0.9)]" />
            </span>
            <div className="flex items-baseline gap-1.5">
              <span className="font-display text-base font-bold tracking-widest text-white sm:text-lg">
                NEXUS
              </span>
              <span className="rounded bg-cyan-500/15 border border-cyan-500/30 px-1.5 py-0.2 font-mono text-[10px] font-bold uppercase tracking-wider text-cyan-300">
                QUANTUM
              </span>
            </div>
          </div>

          <div className="hidden h-4 w-px bg-white/10 sm:block" />

          {/* Atomic Execution Mode Switcher Pill */}
          <div className="flex items-center rounded-xl border border-white/10 bg-slate-950/80 p-0.5 shadow-inner">
            <button
              type="button"
              onClick={() => handleTriggerModeSwitch("paper")}
              className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1 font-mono text-[11px] font-bold transition-all ${
                executionMode === "paper"
                  ? "bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
              title="Switch to Virtual Paper Trading Simulation"
            >
              <ShieldAlert className="h-3 w-3 text-amber-400" />
              <span>PAPER SIM</span>
              <span className="hidden sm:inline text-[9px] text-amber-400/70 font-normal">
                • ₹10k SANDBOX
              </span>
            </button>

            <button
              type="button"
              onClick={() => handleTriggerModeSwitch("live_binance")}
              className={`flex items-center gap-1.5 rounded-lg px-2.5 py-1 font-mono text-[11px] font-bold transition-all ${
                executionMode === "live_binance"
                  ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-[0_0_12px_rgba(16,185,129,0.4)]"
                  : "text-slate-400 hover:text-slate-200"
              }`}
              title="Switch to Real Money Trading on Binance Futures"
            >
              {executionMode === "live_binance" && (
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                </span>
              )}
              <Zap className="h-3 w-3 text-emerald-400" />
              <span>LIVE BINANCE</span>
              <span className="hidden sm:inline text-[9px] text-emerald-400/80 font-normal">
                • REAL MONEY
              </span>
            </button>
          </div>
        </div>

        {/* Global Controls & Status */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Engine Status */}
          <div
            className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 font-mono text-[11px] font-medium transition-all ${
              snapshot === null
                ? "border-slate-800 bg-slate-900/60 text-slate-400"
                : engineOk
                  ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300 shadow-sm shadow-emerald-950/30"
                  : "border-amber-500/30 bg-amber-500/10 text-amber-300"
            }`}
            title={
              snapshot
                ? `DB: ${snapshot.engine_health.database_up ? "UP" : "DOWN"} | Feed: ${snapshot.engine_health.market_feed_up ? "UP" : "DOWN"}`
                : "Awaiting engine telemetry"
            }
          >
            <Activity className="h-3.5 w-3.5 text-cyan-400" />
            <span>
              ENGINE:{" "}
              {snapshot === null ? "CONNECTING" : engineOk ? "NOMINAL" : "DEGRADED"}
            </span>
          </div>

          {/* WebSocket Status */}
          <div
            className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 font-mono text-[11px] font-medium transition-all ${
              wsStatus === "live"
                ? "border-cyan-500/30 bg-cyan-500/10 text-cyan-300"
                : wsStatus === "connecting" || wsStatus === "reconnecting"
                  ? "border-blue-500/30 bg-blue-500/10 text-blue-300"
                  : "border-rose-500/30 bg-rose-500/10 text-rose-300"
            }`}
          >
            {wsStatus === "offline" ? (
              <WifiOff className="h-3.5 w-3.5 text-rose-400" />
            ) : (
              <Wifi className="h-3.5 w-3.5 text-cyan-400" />
            )}
            <span>WS: {wsStatus.toUpperCase()}</span>
          </div>

          {/* Manual Telemetry Sync */}
          <button
            type="button"
            onClick={() => void handleRefresh()}
            disabled={refreshing}
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-slate-800/60 px-3 py-1 font-mono text-[11px] font-semibold text-slate-200 transition-all hover:border-cyan-500/40 hover:bg-cyan-500/15 hover:text-cyan-200 disabled:opacity-50"
            title="Refresh telemetry snapshot"
          >
            <RefreshCw className={`h-3 w-3 ${refreshing ? "animate-spin text-cyan-400" : ""}`} />
            <span>SYNC</span>
          </button>

          {/* Institutional Tearsheet Modal Trigger */}
          <button
            type="button"
            onClick={() => setTearsheetOpen(true)}
            className="hidden sm:inline-flex items-center gap-1.5 rounded-lg border border-cyan-500/40 bg-cyan-950/40 px-2.5 py-1 font-mono text-[11px] font-semibold text-cyan-200 transition-all hover:bg-cyan-900/60 shadow"
            title="Open Institutional Tearsheet & Executive Performance Audit"
          >
            <FileSpreadsheet className="h-3 w-3 text-cyan-400" />
            <span>TEARSHEET</span>
          </button>

          {/* Markowitz Optimizer Modal Trigger */}
          <button
            type="button"
            onClick={() => setOptimizerOpen(true)}
            className="hidden sm:inline-flex items-center gap-1.5 rounded-lg border border-gold-500/40 bg-gold-950/30 px-2.5 py-1 font-mono text-[11px] font-semibold text-gold-300 transition-all hover:bg-gold-900/40 shadow"
            title="Open Markowitz Mean-Variance Efficient Frontier & Risk-Parity Optimizer"
          >
            <Scale className="h-3 w-3 text-gold-400" />
            <span>OPTIMIZER</span>
          </button>

          {/* Council of Quants Debate Modal Trigger */}
          <button
            type="button"
            onClick={() => setCouncilOpen(true)}
            className="hidden sm:inline-flex items-center gap-1.5 rounded-lg border border-purple-500/40 bg-purple-950/30 px-2.5 py-1 font-mono text-[11px] font-semibold text-purple-300 transition-all hover:bg-purple-900/40 shadow"
            title="Open Council of Quants Multi-Agent Debate Arena (Bull vs Bear vs Arbitrator)"
          >
            <Swords className="h-3 w-3 text-purple-400" />
            <span>COUNCIL</span>
          </button>

          {/* Emergency Kill Switch Button */}
          <button
            type="button"
            onClick={() => {
              setStopError(null);
              setConfirmOpen((prev) => !prev);
            }}
            data-testid="emergency-stop-trigger"
            className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-1 font-mono text-[11px] font-bold tracking-wider transition-all shadow-md ${
              killSwitchActive
                ? "border-rose-500 bg-rose-500/25 text-rose-200 shadow-rose-500/20"
                : "border-rose-500/40 bg-rose-500/10 text-rose-300 hover:border-rose-400 hover:bg-rose-500/20"
            }`}
          >
            <AlertOctagon className="h-3.5 w-3.5 text-rose-400" />
            <span>{killSwitchActive ? "KILL SWITCH ENGAGED" : "KILL SWITCH"}</span>
          </button>
        </div>
      </div>

      {/* Live Market Price & Liquidity Ticker Marquee */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/[0.05] bg-[#040814]/80 px-4 py-1.5 font-mono text-xs sm:px-6">
        <div className="flex flex-wrap items-center gap-3 overflow-x-auto py-0.5">
          {snapshot && snapshot.tickers.length > 0 ? (
            snapshot.tickers.slice(0, 6).map((ticker) => {
              const bid = toFiniteNumber(ticker.bid);
              const ask = toFiniteNumber(ticker.ask);
              const spreadBps = bid > 0 ? (((ask - bid) / bid) * 10_000).toFixed(1) : "--";

              return (
                <div
                  key={ticker.symbol}
                  className="flex items-center gap-2 border-r border-white/10 pr-3.5 last:border-r-0"
                >
                  <span className="font-semibold text-slate-300">{ticker.symbol}</span>
                  <span className="font-bold text-white tabular-nums">
                    {formatUsdt(ticker.last, ticker.symbol.startsWith("SOL") ? 3 : 2)}
                  </span>
                  <span className="rounded bg-slate-800/60 px-1 py-0.2 text-[9px] text-slate-400">
                    {spreadBps} bps
                  </span>
                </div>
              );
            })
          ) : (
            <span className="text-[11px] text-amber-300/80">
              {snapshot?.engine_health.market_feed_detail ??
                "Exchange ticker feed active — real public quotes only."}
            </span>
          )}
        </div>

        {/* Global FX & Total Capital Readout */}
        <div className="flex flex-wrap items-center gap-4 text-[11px] text-slate-400">
          <span>
            USD/INR:{" "}
            <strong className="font-bold text-amber-300 tabular-nums">
              {quoteLive && snapshot?.portfolio.inr_per_usdt
                ? `₹${snapshot.portfolio.inr_per_usdt.toFixed(2)}`
                : "₹85.00"}
            </strong>
          </span>
          <span className="hidden sm:inline">•</span>
          <span>
            NET EQUITY:{" "}
            <strong className="font-bold text-emerald-300 tabular-nums">
              {snapshot ? formatInr(snapshot.portfolio.total_equity_inr) : "--"}
            </strong>
          </span>
        </div>
      </div>

      {/* Emergency Stop Confirmation Modal */}
      {confirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-md">
          <div className="w-full max-w-lg rounded-2xl border border-rose-500/40 bg-[#0b1329] p-6 shadow-2xl shadow-rose-950/50">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-400">
                  <AlertOctagon className="h-6 w-6" />
                </div>
                <div>
                  <h3 className="font-display text-base font-bold text-white">
                    Emergency Circuit Breaker Trigger
                  </h3>
                  <p className="font-mono text-xs text-rose-300/80">
                    Instantly halt all automated trading engines
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setConfirmOpen(false)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="mt-4 space-y-3 font-mono text-xs">
              <div>
                <label className="block text-slate-400 mb-1">Audit Log Reason:</label>
                <textarea
                  value={stopReason}
                  onChange={(e) => setStopReason(e.target.value)}
                  className="w-full rounded-xl border border-slate-700 bg-slate-900/90 p-3 text-white focus:border-rose-500 focus:outline-none"
                  rows={2}
                />
              </div>

              <label className="flex items-center gap-2 cursor-pointer text-slate-300">
                <input
                  type="checkbox"
                  checked={flattenPositions}
                  onChange={(e) => setFlattenPositions(e.target.checked)}
                  className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-rose-500"
                />
                <span>Flatten and liquidate all open paper positions immediately</span>
              </label>

              {stopError && (
                <div className="rounded-xl border border-rose-500/50 bg-rose-500/15 p-2.5 text-rose-300">
                  {stopError}
                </div>
              )}
            </div>

            <div className="mt-5 flex justify-end gap-3 font-mono text-xs">
              <button
                type="button"
                onClick={() => setConfirmOpen(false)}
                className="rounded-xl border border-slate-700 px-4 py-2 font-medium text-slate-300 hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleConfirmEmergencyStop()}
                disabled={emergencyPending}
                className="rounded-xl bg-rose-600 px-4 py-2 font-bold text-white shadow-lg shadow-rose-600/30 hover:bg-rose-500 disabled:opacity-50"
              >
                {emergencyPending ? "Triggering..." : "CONFIRM EMERGENCY STOP"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Institutional Tearsheet Modal */}
      <InstitutionalTearsheetModal
        isOpen={tearsheetOpen}
        onClose={() => setTearsheetOpen(false)}
        snapshot={snapshot}
      />

      {/* Markowitz Efficient Frontier Optimizer Modal */}
      <PortfolioOptimizerModal
        isOpen={optimizerOpen}
        onClose={() => setOptimizerOpen(false)}
      />

      {/* Council of Quants Multi-Agent Debate Modal */}
      <CouncilOfQuantsDebateModal
        isOpen={councilOpen}
        onClose={() => setCouncilOpen(false)}
        defaultSymbol="BTC/USDT"
      />

      {/* Execution Mode Atomic Switcher Modal */}
      {modeConfirmOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4 backdrop-blur-md">
          <div className="w-full max-w-lg rounded-2xl border border-white/15 bg-[#0b1329] p-6 shadow-2xl">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div
                  className={`flex h-11 w-11 items-center justify-center rounded-xl border ${
                    pendingTargetMode === "live_binance"
                      ? "border-emerald-500/40 bg-emerald-500/20 text-emerald-300"
                      : "border-amber-500/40 bg-amber-500/20 text-amber-300"
                  }`}
                >
                  {pendingTargetMode === "live_binance" ? (
                    <Zap className="h-6 w-6 text-emerald-400" />
                  ) : (
                    <ShieldAlert className="h-6 w-6 text-amber-400" />
                  )}
                </div>
                <div>
                  <h3 className="font-display text-base font-bold text-white">
                    {pendingTargetMode === "live_binance"
                      ? "Activate LIVE Real Money Trading"
                      : "Switch to Virtual Paper Simulation"}
                  </h3>
                  <p className="font-mono text-xs text-slate-400">
                    {pendingTargetMode === "live_binance"
                      ? "Binance USDⓈ-M Futures Production Mainnet"
                      : "Risk-Free Virtual INR 10,000 Sandbox"}
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setModeConfirmOpen(false)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-white"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="mt-4 space-y-3 font-mono text-xs">
              {pendingTargetMode === "live_binance" ? (
                <div className="space-y-3 rounded-xl border border-emerald-500/30 bg-emerald-950/20 p-4 text-slate-200">
                  <div className="flex items-center gap-2 text-emerald-300 font-bold">
                    <ShieldCheck className="h-4 w-4 text-emerald-400" />
                    <span>Real-Money Invariant Safety Check</span>
                  </div>
                  <ul className="space-y-1.5 text-[11px] text-slate-300 list-disc list-inside">
                    <li>
                      <strong>Automatic Paper Trading Paused:</strong> Virtual simulation order generation will stop immediately.
                    </li>
                    <li>
                      <strong>Exchange Gateway:</strong> Real orders will be routed directly to Binance USDⓈ-M Futures.
                    </li>
                    <li>
                      <strong>Verified Balance:</strong> $2.9409 USDT available margin (Production).
                    </li>
                    <li>
                      <strong>Non-Custodial Lock:</strong> API key has NO withdrawal permission. Your capital cannot leave Binance.
                    </li>
                  </ul>
                </div>
              ) : (
                <div className="space-y-3 rounded-xl border border-amber-500/30 bg-amber-950/20 p-4 text-slate-200">
                  <div className="flex items-center gap-2 text-amber-300 font-bold">
                    <ShieldAlert className="h-4 w-4 text-amber-400" />
                    <span>Return to Virtual Paper Sandbox</span>
                  </div>
                  <ul className="space-y-1.5 text-[11px] text-slate-300 list-disc list-inside">
                    <li>
                      <strong>Live Exchange Execution Halted:</strong> Zero real-money orders will be placed on Binance.
                    </li>
                    <li>
                      <strong>Paper Simulation Resumed:</strong> Strategy V1 & Arbitrage paper trades will resume in PostgreSQL ledger.
                    </li>
                    <li>
                      <strong>Risk Level:</strong> 0.00% financial exposure.
                    </li>
                  </ul>
                </div>
              )}

              {modeError && (
                <div className="rounded-xl border border-rose-500/50 bg-rose-500/15 p-2.5 text-rose-300">
                  {modeError}
                </div>
              )}
            </div>

            <div className="mt-5 flex justify-end gap-3 font-mono text-xs">
              <button
                type="button"
                onClick={() => setModeConfirmOpen(false)}
                className="rounded-xl border border-slate-700 px-4 py-2 font-medium text-slate-300 hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={switchingMode}
                onClick={() => void handleConfirmModeSwitch()}
                className={`rounded-xl px-4 py-2 font-bold text-white shadow-lg disabled:opacity-50 ${
                  pendingTargetMode === "live_binance"
                    ? "bg-emerald-600 hover:bg-emerald-500 shadow-emerald-600/30"
                    : "bg-amber-600 hover:bg-amber-500 shadow-amber-600/30"
                }`}
              >
                {switchingMode
                  ? "Switching Mode..."
                  : pendingTargetMode === "live_binance"
                    ? "ACTIVATE LIVE REAL TRADING"
                    : "SWITCH TO PAPER TRADING"}
              </button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
