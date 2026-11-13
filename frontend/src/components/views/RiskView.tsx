import { useState } from "react";
import {
  AlertOctagon,
  ShieldCheck,
  RotateCcw,
  AlertTriangle,
  CheckCircle2,
  Lock,
  Flame,
  Activity,
  Layers,
  ShieldAlert,
} from "lucide-react";
import type {
  EmergencyStopResponse,
  ResetKillSwitchResponse,
  TerminalSnapshotResponse,
} from "../../types/system";
import { formatInr, formatPct, formatUtcTime, toFiniteNumber } from "../../utils/format";

interface RiskViewProps {
  snapshot: TerminalSnapshotResponse | null;
  emergencyPending: boolean;
  onActivateEmergencyStop: (
    reason: string,
    flattenPositions: boolean,
  ) => Promise<EmergencyStopResponse>;
  onDisarmEmergencyStop?: (reason?: string) => Promise<ResetKillSwitchResponse>;
}

function MultiZoneMeterBar({
  label,
  value,
  limit,
  unit = "%",
}: {
  label: string;
  value: number;
  limit: number;
  unit?: string;
}) {
  const ratio = limit > 0 ? Math.min(Math.max((value / limit) * 100, 0), 100) : 0;
  
  // 4-tier safety classification
  let zoneColor = "bg-cyan-400";
  let zoneTextColor = "text-cyan-300";
  let zoneBadge = "NORMAL";
  let zoneBorder = "border-cyan-500/20";

  if (ratio >= 100) {
    zoneColor = "bg-rose-600 animate-pulse";
    zoneTextColor = "text-rose-400 font-bold";
    zoneBadge = "BREAKER TRIPPED";
    zoneBorder = "border-rose-500/50 bg-rose-950/20";
  } else if (ratio >= 80) {
    zoneColor = "bg-rose-500";
    zoneTextColor = "text-rose-300 font-semibold";
    zoneBadge = "CRITICAL (80%+)";
    zoneBorder = "border-rose-500/30 bg-rose-950/10";
  } else if (ratio >= 50) {
    zoneColor = "bg-amber-400";
    zoneTextColor = "text-amber-300 font-semibold";
    zoneBadge = "WATCH (50%+)";
    zoneBorder = "border-amber-500/30 bg-amber-950/10";
  }

  return (
    <div className={`rounded-lg border ${zoneBorder} bg-nexus-void/90 p-3.5 space-y-2`}>
      <div className="flex items-center justify-between font-mono text-xs">
        <div className="flex items-center gap-2">
          <span className="text-slate-300 font-semibold">{label}</span>
          <span className={`rounded px-1.5 py-0.2 text-[9px] font-bold uppercase ${zoneTextColor} bg-slate-900 border border-slate-800`}>
            {zoneBadge}
          </span>
        </div>
        <span className={`tabular-nums ${zoneTextColor}`}>
          {value.toFixed(2)}{unit} / {limit.toFixed(2)}{unit}
        </span>
      </div>

      {/* Progress Track */}
      <div className="h-2.5 overflow-hidden rounded-full bg-slate-800/90 flex">
        <div
          className={`h-full transition-all duration-500 ${zoneColor}`}
          style={{ width: `${Math.max(ratio, 2)}%` }}
        />
      </div>

      <div className="flex justify-between font-mono text-[10px] text-slate-500">
        <span>0{unit} (Safe)</span>
        <span>Warning ({(limit * 0.5).toFixed(1)}{unit})</span>
        <span>Halt Limit ({limit.toFixed(1)}{unit})</span>
      </div>
    </div>
  );
}

export function RiskView({
  snapshot,
  emergencyPending,
  onActivateEmergencyStop,
  onDisarmEmergencyStop,
}: RiskViewProps) {
  const [reason, setReason] = useState("Manual risk circuit breaker activation from Risk panel.");
  const [flatten, setFlatten] = useState(true);
  const [actionResult, setActionResult] = useState<EmergencyStopResponse | null>(null);
  const [disarmResult, setDisarmResult] = useState<ResetKillSwitchResponse | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmDisarm, setConfirmDisarm] = useState(false);

  const risk = snapshot?.risk;
  const portfolio = snapshot?.portfolio;
  const killSwitchActive = Boolean(risk?.kill_switch_active);

  // Capital Exposure Calculations
  const initialCap = toFiniteNumber(portfolio?.initial_capital_inr || 10000);
  const totalEquity = toFiniteNumber(portfolio?.total_equity_inr || initialCap);
  const cashBalance = toFiniteNumber(portfolio?.cash_balance_inr || initialCap);
  const holdingsValue = toFiniteNumber(portfolio?.holdings_value_inr || 0);
  const capitalAtRiskPct = totalEquity > 0 ? (holdingsValue / totalEquity) * 100 : 0;
  const maxAllowedDailyLossInr = (initialCap * (risk?.daily_loss_limit_pct ?? 2)) / 100;

  async function handleEngageKillSwitch(): Promise<void> {
    setActionError(null);
    setDisarmResult(null);
    if (reason.trim().length < 3) {
      setActionError("Emergency reason must be at least 3 characters.");
      return;
    }
    try {
      const res = await onActivateEmergencyStop(reason.trim(), flatten);
      setActionResult(res);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Kill switch activation failed.");
    }
  }

  async function handleDisarmKillSwitch(): Promise<void> {
    if (!onDisarmEmergencyStop) return;
    setActionError(null);
    setActionResult(null);
    try {
      const res = await onDisarmEmergencyStop("Operator confirmed risk envelope safe. Resumed entries.");
      setDisarmResult(res);
      setConfirmDisarm(false);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Failed to disarm kill switch.");
    }
  }

  return (
    <div className="space-y-4">
      {/* 1. Executive Circuit Breaker HUD Banner */}
      <div
        className={`nexus-panel rounded-lg p-4 border transition ${
          killSwitchActive
            ? "border-rose-500/60 bg-rose-950/20 shadow-[0_0_20px_rgba(244,63,94,0.15)]"
            : (risk?.risk_utilization_pct ?? 0) >= 80
              ? "border-amber-500/50 bg-amber-950/20"
              : "border-cyan-500/25 bg-[#030712]"
        }`}
      >
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2.5">
            {killSwitchActive ? (
              <ShieldAlert className="h-5 w-5 text-rose-400 animate-pulse" />
            ) : (
              <ShieldCheck className="h-5 w-5 text-cyan-400" />
            )}
            <div>
              <h2 className="font-display text-base font-semibold text-white">
                Independent Risk Manager & Circuit Breakers
              </h2>
              <p className="text-xs text-slate-400">
                PostgreSQL-enforced hard ceiling. Automatically halts entries upon daily loss breach.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 font-mono text-xs font-bold ${
                killSwitchActive
                  ? "bg-rose-500/20 text-rose-300 border border-rose-500/60 animate-pulse"
                  : "bg-emerald-500/15 text-emerald-300 border border-emerald-500/40"
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${
                  killSwitchActive ? "bg-rose-400 animate-ping" : "bg-emerald-400"
                }`}
              />
              {killSwitchActive ? "HALTED: KILL SWITCH ENGAGED" : "SYSTEM ARMED & CLEAR"}
            </span>
          </div>
        </div>

        {/* Reason Alert if Kill Switch is Active */}
        {killSwitchActive && (
          <div className="mt-3 rounded border border-rose-500/40 bg-rose-950/40 p-3 font-mono text-xs text-rose-200 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <AlertOctagon className="h-4 w-4 text-rose-400 shrink-0" />
              <span>
                <strong>Halt Reason:</strong> {risk?.kill_switch_reason ?? "Emergency halt engaged."}
              </span>
            </div>
            <span className="text-[10px] text-slate-400">
              Triggered: {formatUtcTime(risk?.kill_switch_triggered_at)}
            </span>
          </div>
        )}

        {/* 2. Capital at Risk & Exposure Deck (4 Cards) */}
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4 font-mono text-xs">
          <div className="rounded border border-slate-800 bg-nexus-void/80 p-3">
            <div className="flex items-center gap-1 text-[10px] uppercase text-slate-400">
              <Flame className="h-3.5 w-3.5 text-amber-400" />
              <span>Capital at Risk</span>
            </div>
            <div className="mt-1 text-base font-bold text-white">
              {formatInr(holdingsValue)}
            </div>
            <div className="text-[10px] text-slate-400">
              Exposure: <span className="text-amber-300 font-semibold">{capitalAtRiskPct.toFixed(1)}%</span> of equity
            </div>
          </div>

          <div className="rounded border border-slate-800 bg-nexus-void/80 p-3">
            <div className="flex items-center gap-1 text-[10px] uppercase text-slate-400">
              <Lock className="h-3.5 w-3.5 text-cyan-400" />
              <span>Free Cash Buffer</span>
            </div>
            <div className="mt-1 text-base font-bold text-cyan-300">
              {formatInr(cashBalance)}
            </div>
            <div className="text-[10px] text-slate-400">
              Liquid: <span className="text-slate-200">{((cashBalance / Math.max(totalEquity, 1)) * 100).toFixed(1)}%</span>
            </div>
          </div>

          <div className="rounded border border-slate-800 bg-nexus-void/80 p-3">
            <div className="flex items-center gap-1 text-[10px] uppercase text-slate-400">
              <AlertTriangle className="h-3.5 w-3.5 text-rose-400" />
              <span>Max 1-Day VaR (2%)</span>
            </div>
            <div className="mt-1 text-base font-bold text-rose-300">
              {formatInr(maxAllowedDailyLossInr)}
            </div>
            <div className="text-[10px] text-slate-400">
              Daily Loss Threshold
            </div>
          </div>

          <div className="rounded border border-slate-800 bg-nexus-void/80 p-3">
            <div className="flex items-center gap-1 text-[10px] uppercase text-slate-400">
              <Activity className="h-3.5 w-3.5 text-emerald-400" />
              <span>Risk Utilization</span>
            </div>
            <div className="mt-1 text-base font-bold text-emerald-300">
              {risk ? formatPct(risk.risk_utilization_pct) : "--"}
            </div>
            <div className="text-[10px] text-slate-400">
              Enforced Multi-Factor
            </div>
          </div>
        </div>
      </div>

      {/* 3. Multi-Zone Circuit Breaker Safety Meters */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <MultiZoneMeterBar
          label="Daily Loss vs 2.00% Circuit Breaker"
          value={risk?.daily_loss_pct ?? 0}
          limit={risk?.daily_loss_limit_pct ?? 2}
        />
        <MultiZoneMeterBar
          label="Total Drawdown vs 8.00% Max Threshold"
          value={risk?.drawdown_pct ?? 0}
          limit={risk?.max_drawdown_pct ?? 8}
        />
        <MultiZoneMeterBar
          label="Concurrent Spot Positions Limit"
          value={risk?.open_positions_count ?? 0}
          limit={risk?.max_concurrent_positions ?? 2}
          unit=""
        />
        <MultiZoneMeterBar
          label="Daily Entry Orders Velocity"
          value={risk?.daily_entries_count ?? 0}
          limit={risk?.max_daily_entries ?? 5}
          unit=""
        />
      </div>

      {/* 4. Two-Way Circuit Breaker Control Hub (Halt / Disarm) */}
      <div className="nexus-panel rounded-lg p-4 space-y-4">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
          <div className="flex items-center gap-2">
            <AlertOctagon className="h-4 w-4 text-rose-400" />
            <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
              Circuit Breaker Emergency Controls
            </h3>
          </div>
          <span className="font-mono text-[10px] text-slate-400">
            TWO-WAY CONTROL PROTOCOL
          </span>
        </div>

        {killSwitchActive ? (
          /* Disarm / Reset Flow */
          <div className="rounded-lg border border-emerald-500/40 bg-emerald-950/20 p-4 space-y-3">
            <div className="flex items-start gap-3">
              <CheckCircle2 className="h-5 w-5 text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <h4 className="font-display text-sm font-semibold text-emerald-200">
                  Kill Switch Currently Engaged
                </h4>
                <p className="text-xs text-slate-300 mt-1">
                  Automated entry orders are currently blocked. Once market stability is restored and risk envelopes are validated, you can safely disarm the circuit breaker to resume normal paper trading operations.
                </p>
              </div>
            </div>

            {confirmDisarm ? (
              <div className="flex flex-wrap items-center gap-3 pt-2 border-t border-emerald-500/20">
                <span className="font-mono text-xs text-emerald-300 font-semibold">
                  Are you sure you want to disarm the kill switch and resume trading?
                </span>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={emergencyPending}
                    onClick={() => void handleDisarmKillSwitch()}
                    className="rounded border border-emerald-400 bg-emerald-600 px-4 py-1.5 font-mono text-xs font-bold text-white shadow-lg transition hover:bg-emerald-500 disabled:opacity-50"
                  >
                    {emergencyPending ? "DISARMING..." : "CONFIRM & DISARM NOW"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmDisarm(false)}
                    className="rounded border border-slate-700 bg-slate-900 px-3 py-1.5 font-mono text-xs text-slate-300 hover:text-white"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              <div className="pt-2">
                <button
                  type="button"
                  onClick={() => setConfirmDisarm(true)}
                  className="inline-flex items-center gap-2 rounded border border-emerald-500/60 bg-emerald-500/20 px-4 py-2 font-mono text-xs font-bold text-emerald-200 shadow hover:bg-emerald-500/30 transition"
                >
                  <RotateCcw className="h-4 w-4 text-emerald-400" />
                  <span>DISARM & RESET CIRCUIT BREAKER</span>
                </button>
              </div>
            )}
          </div>
        ) : (
          /* Engage Halt Flow */
          <div className="space-y-3">
            <p className="text-xs text-slate-300">
              Immediately halts all incoming autonomous and manual paper order entries, cancels all pending limit clips, and optionally submits emergency market exit orders to flatten open positions.
            </p>

            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={240}
              className="w-full rounded border border-rose-500/35 bg-[#030712] px-3 py-2 font-mono text-xs text-white placeholder-slate-500 focus:border-rose-400 focus:outline-none"
              placeholder="Audit reason for emergency stop (e.g. Extreme market flash crash or volatility spike)"
            />

            <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
              <label className="inline-flex cursor-pointer items-center gap-2 font-mono text-xs text-slate-200">
                <input
                  type="checkbox"
                  checked={flatten}
                  onChange={(e) => setFlatten(e.target.checked)}
                  className="h-3.5 w-3.5 accent-rose-500 rounded"
                />
                Submit emergency market exit orders for all open paper positions
              </label>

              <button
                type="button"
                disabled={emergencyPending}
                onClick={() => void handleEngageKillSwitch()}
                className="rounded border border-rose-400 bg-rose-600/90 px-4 py-1.5 font-mono text-xs font-semibold uppercase tracking-wider text-white shadow-lg transition hover:bg-rose-500 disabled:opacity-50"
              >
                {emergencyPending ? "EXECUTING HALT..." : "ACTIVATE EMERGENCY STOP"}
              </button>
            </div>
          </div>
        )}

        {actionError && (
          <div className="rounded border border-rose-500/50 bg-rose-950/30 p-2.5 font-mono text-xs text-rose-300 flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>{actionError}</span>
          </div>
        )}

        {actionResult && (
          <div className="rounded border border-rose-500/40 bg-rose-950/20 p-3 font-mono text-xs text-rose-200">
            ✅ Kill switch persisted in PostgreSQL at {formatUtcTime(actionResult.triggered_at)} · Flattened positions:{" "}
            <strong>{actionResult.flattened_orders_count}</strong> · Rejected: {actionResult.rejected_flatten_count}
          </div>
        )}

        {disarmResult && (
          <div className="rounded border border-emerald-500/40 bg-emerald-950/20 p-3 font-mono text-xs text-emerald-200">
            ✅ {disarmResult.message} (Disarmed at {formatUtcTime(disarmResult.reset_at)})
          </div>
        )}
      </div>

      {/* 5. Institutional Risk Ruleset Matrix */}
      <div className="nexus-panel rounded-lg p-4 space-y-3">
        <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
          <Layers className="h-4 w-4 text-cyan-400" />
          <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
            Enforced Risk Ruleset Matrix
          </h3>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left font-mono text-xs">
            <thead className="border-b border-slate-800 bg-nexus-void/80 text-[10px] uppercase text-slate-400">
              <tr>
                <th className="px-3 py-2">Guardrail</th>
                <th className="px-3 py-2">Threshold</th>
                <th className="px-3 py-2">Action on Breach</th>
                <th className="px-3 py-2">Recovery Protocol</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70 text-slate-300 text-[11px]">
              <tr>
                <td className="px-3 py-2 font-semibold text-cyan-300">Daily Loss Circuit Breaker</td>
                <td className="px-3 py-2 text-rose-300 font-bold">2.00% of Initial Capital</td>
                <td className="px-3 py-2">Blocks all new buy orders immediately</td>
                <td className="px-3 py-2 text-slate-400">Automatic reset at 00:00 UTC</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-semibold text-cyan-300">Maximum Total Drawdown</td>
                <td className="px-3 py-2 text-amber-300 font-bold">8.00% Peak-to-Trough</td>
                <td className="px-3 py-2">Hard freezes engine entries</td>
                <td className="px-3 py-2 text-slate-400">Requires manual operator disarm</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-semibold text-cyan-300">Max Concurrent Positions</td>
                <td className="px-3 py-2 text-slate-200">2 Assets Max</td>
                <td className="px-3 py-2">Rejects new signal entries</td>
                <td className="px-3 py-2 text-slate-400">Opens slot upon trailing stop exit</td>
              </tr>
              <tr>
                <td className="px-3 py-2 font-semibold text-cyan-300">Daily Order Velocity</td>
                <td className="px-3 py-2 text-slate-200">5 Entries / Day</td>
                <td className="px-3 py-2">Prevents algorithmic overtrading</td>
                <td className="px-3 py-2 text-slate-400">Resets daily at 00:00 UTC</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
