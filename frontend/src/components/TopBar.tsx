import { useState } from "react";
import {
  Activity,
  AlertOctagon,
  RefreshCw,
  ShieldAlert,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import type {
  EmergencyStopResponse,
  TerminalSnapshotResponse,
  WebSocketStatus,
} from "../types/system";
import { formatInr, formatUsdt, formatUtcTime, toFiniteNumber } from "../utils/format";

interface TopBarProps {
  snapshot: TerminalSnapshotResponse | null;
  wsStatus: WebSocketStatus;
  emergencyPending: boolean;
  lastEmergencyResponse: EmergencyStopResponse | null;
  onRefresh: () => Promise<void>;
  onActivateEmergencyStop: (
    reason: string,
    flattenPositions: boolean,
  ) => Promise<EmergencyStopResponse>;
}

export function TopBar({
  snapshot,
  wsStatus,
  emergencyPending,
  lastEmergencyResponse,
  onRefresh,
  onActivateEmergencyStop,
}: TopBarProps) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [flattenPositions, setFlattenPositions] = useState(true);
  const [stopReason, setStopReason] = useState(
    "Manual emergency stop triggered from NEXUS Terminal.",
  );
  const [stopError, setStopError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const killSwitchActive = snapshot?.risk.kill_switch_active ?? false;
  const engineOk = snapshot?.engine_health.overall_status === "ok";
  const quoteLive = snapshot?.portfolio.quote_status === "live";

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
    <header className="border-b border-cyan-500/20 bg-nexus-navy/95 backdrop-blur-md">
      {/* Primary Brand + System Status + Emergency Controls Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-cyan-400 shadow-[0_0_12px_rgba(34,211,238,0.85)]" />
            <span className="font-display text-sm font-semibold tracking-[0.2em] text-white sm:text-base">
              NEXUS <span className="text-cyan-400">AI</span> TRADER
            </span>
          </div>

          {/* Mandatory Permanent Paper Trading Banner */}
          <span
            className="inline-flex items-center gap-1.5 rounded border border-amber-400/50 bg-amber-500/10 px-2.5 py-0.5 font-mono text-[11px] font-semibold uppercase tracking-wider text-amber-300"
            data-testid="paper-trading-badge"
          >
            <ShieldAlert className="h-3.5 w-3.5 text-amber-400" />
            PAPER TRADING ONLY · INR 10,000 VIRTUAL
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Engine Health Pill */}
          <div
            className={`inline-flex items-center gap-1.5 rounded border px-2.5 py-1 font-mono text-[11px] ${
              snapshot === null
                ? "border-slate-700 bg-slate-900/70 text-slate-400"
                : engineOk
                  ? "border-cyan-500/35 bg-cyan-500/10 text-cyan-200"
                  : "border-amber-500/40 bg-amber-500/10 text-amber-200"
            }`}
            title={
              snapshot
                ? `DB: ${snapshot.engine_health.database_up ? "UP" : "DOWN"} | Feed: ${snapshot.engine_health.market_feed_up ? "UP" : "DOWN"}`
                : "Awaiting engine telemetry"
            }
          >
            <Activity className="h-3.5 w-3.5" />
            <span>
              ENGINE:{" "}
              {snapshot === null
                ? "CONNECTING"
                : engineOk
                  ? "NOMINAL"
                  : "DEGRADED"}
            </span>
          </div>

          {/* WebSocket Telemetry Pill */}
          <div
            className={`inline-flex items-center gap-1.5 rounded border px-2.5 py-1 font-mono text-[11px] ${
              wsStatus === "live"
                ? "border-emerald-500/35 bg-emerald-500/10 text-emerald-300"
                : wsStatus === "connecting" || wsStatus === "reconnecting"
                  ? "border-blue-500/35 bg-blue-500/10 text-blue-300"
                  : "border-rose-500/40 bg-rose-500/10 text-rose-300"
            }`}
          >
            {wsStatus === "offline" ? (
              <WifiOff className="h-3.5 w-3.5" />
            ) : (
              <Wifi className="h-3.5 w-3.5" />
            )}
            <span>WS: {wsStatus.toUpperCase()}</span>
          </div>

          <button
            type="button"
            onClick={() => void handleRefresh()}
            disabled={refreshing}
            className="inline-flex items-center gap-1.5 rounded border border-cyan-500/30 bg-nexus-panel px-2.5 py-1 font-mono text-[11px] text-cyan-200 transition hover:border-cyan-400/60 hover:bg-cyan-500/10 disabled:opacity-50"
            title="Refresh telemetry snapshot"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
            SYNC
          </button>

          {/* Emergency Stop Trigger */}
          <button
            type="button"
            onClick={() => {
              setStopError(null);
              setConfirmOpen((prev) => !prev);
            }}
            data-testid="emergency-stop-trigger"
            className={`inline-flex items-center gap-1.5 rounded border px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-wider transition ${
              killSwitchActive
                ? "border-rose-500 bg-rose-500/20 text-rose-200 shadow-[0_0_16px_rgba(244,63,94,0.35)]"
                : "border-rose-500/60 bg-rose-500/15 text-rose-300 hover:border-rose-400 hover:bg-rose-500/25"
            }`}
          >
            <AlertOctagon className="h-3.5 w-3.5" />
            {killSwitchActive ? "KILL SWITCH ACTIVE" : "EMERGENCY STOP"}
          </button>
        </div>
      </div>

      {/* Market Ticker Strip */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-cyan-500/10 bg-nexus-void/80 px-4 py-1.5 font-mono text-xs">
        <div className="flex flex-wrap items-center gap-4">
          {snapshot && snapshot.tickers.length > 0 ? (
            snapshot.tickers.map((ticker) => {
              const bid = toFiniteNumber(ticker.bid);
              const ask = toFiniteNumber(ticker.ask);
              const spreadBps =
                bid > 0 ? (((ask - bid) / bid) * 10_000).toFixed(1) : "--";
              return (
                <div
                  key={ticker.symbol}
                  className="flex items-center gap-2 border-r border-slate-800/80 pr-4 last:border-r-0"
                >
                  <span className="font-semibold text-cyan-300">{ticker.symbol}</span>
                  <span className="tabular-nums text-white">
                    {formatUsdt(ticker.last, ticker.symbol.startsWith("SOL") ? 3 : 2)}
                  </span>
                  <span className="text-[10px] text-slate-400">
                    SPD {spreadBps} bps
                  </span>
                </div>
              );
            })
          ) : (
            <span className="text-amber-300/90">
              {snapshot?.engine_health.market_feed_detail ??
                "Public exchange ticker feed unavailable — no fabricated quotes displayed."}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-4 text-[11px] text-slate-400">
          <span>
            FX:{" "}
            <strong className="tabular-nums text-gold-300">
              {quoteLive && snapshot?.portfolio.inr_per_usdt
                ? `${snapshot.portfolio.inr_per_usdt.toFixed(2)} INR/USDT`
                : "Unavailable"}
            </strong>
          </span>
          <span>
            EQUITY:{" "}
            <strong className="tabular-nums text-white">
              {snapshot ? formatInr(snapshot.portfolio.total_equity_inr) : "--"}
            </strong>
          </span>
          <span className="hidden md:inline">
            UTC: {formatUtcTime(snapshot?.timestamp)}
          </span>
        </div>
      </div>

      {/* Emergency Stop Confirmation Drawer */}
      {confirmOpen && (
        <div
          className="border-t border-rose-500/40 bg-rose-950/35 px-4 py-3"
          role="dialog"
          aria-label="Confirm Emergency Stop"
        >
          <div className="mx-auto flex max-w-6xl flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="flex-1 space-y-1.5">
              <div className="flex items-center justify-between">
                <p className="font-mono text-xs font-semibold uppercase tracking-wider text-rose-300">
                  Confirm Paper Trading Kill Switch Activation
                </p>
                <button
                  type="button"
                  onClick={() => setConfirmOpen(false)}
                  className="text-slate-400 hover:text-white"
                  aria-label="Close emergency confirmation"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
              <p className="text-xs text-slate-300">
                Halts all new paper entries immediately in PostgreSQL state. Real exchanges are never touched.
              </p>
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <input
                  type="text"
                  value={stopReason}
                  onChange={(e) => setStopReason(e.target.value)}
                  maxLength={240}
                  className="w-full rounded border border-rose-500/40 bg-nexus-void/90 px-2.5 py-1.5 font-mono text-xs text-white focus:border-rose-400 focus:outline-none sm:max-w-md"
                  placeholder="Emergency stop audit reason"
                />
                <label className="inline-flex cursor-pointer items-center gap-2 font-mono text-xs text-slate-200">
                  <input
                    type="checkbox"
                    checked={flattenPositions}
                    onChange={(e) => setFlattenPositions(e.target.checked)}
                    className="h-3.5 w-3.5 accent-rose-500"
                  />
                  Flatten open paper positions
                </label>
              </div>
              {stopError && <p className="font-mono text-xs text-rose-300">{stopError}</p>}
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setConfirmOpen(false)}
                className="rounded border border-slate-700 bg-slate-900 px-3 py-1.5 font-mono text-xs text-slate-300 hover:border-slate-500"
              >
                CANCEL
              </button>
              <button
                type="button"
                disabled={emergencyPending}
                onClick={() => void handleConfirmEmergencyStop()}
                data-testid="confirm-emergency-stop"
                className="rounded border border-rose-400 bg-rose-600 px-3.5 py-1.5 font-mono text-xs font-semibold text-white transition hover:bg-rose-500 disabled:opacity-50"
              >
                {emergencyPending ? "ACTIVATING..." : "ENGAGE KILL SWITCH"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Persistent Kill Switch Alert Banner */}
      {killSwitchActive && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-rose-500/40 bg-rose-500/15 px-4 py-1.5 font-mono text-xs text-rose-200">
          <span>
            KILL SWITCH ENGAGED:{" "}
            {snapshot?.risk.kill_switch_reason ??
              lastEmergencyResponse?.reason ??
              "Trading halted by risk manager"}
          </span>
          {lastEmergencyResponse && (
            <span className="text-[11px] text-rose-300">
              Flattened: {lastEmergencyResponse.flattened_orders_count} · Rejected:{" "}
              {lastEmergencyResponse.rejected_flatten_count}
            </span>
          )}
        </div>
      )}
    </header>
  );
}

