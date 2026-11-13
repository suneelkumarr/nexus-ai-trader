import { useState } from "react";
import { AlertOctagon, ShieldCheck } from "lucide-react";
import type {
  EmergencyStopResponse,
  TerminalSnapshotResponse,
} from "../../types/system";
import { formatPct, formatUtcTime } from "../../utils/format";

interface RiskViewProps {
  snapshot: TerminalSnapshotResponse | null;
  emergencyPending: boolean;
  onActivateEmergencyStop: (
    reason: string,
    flattenPositions: boolean,
  ) => Promise<EmergencyStopResponse>;
}

function MeterBar({
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
  const isHot = ratio >= 80;
  return (
    <div className="rounded border border-cyan-500/15 bg-nexus-void/80 p-3">
      <div className="flex items-center justify-between font-mono text-xs">
        <span className="text-slate-300">{label}</span>
        <span className={`tabular-nums font-semibold ${isHot ? "text-rose-300" : "text-cyan-300"}`}>
          {value.toFixed(2)}
          {unit} / {limit.toFixed(2)}
          {unit}
        </span>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-800">
        <div
          className={`h-full transition-all ${
            isHot
              ? "bg-rose-500"
              : ratio >= 50
                ? "bg-amber-400"
                : "bg-cyan-400"
          }`}
          style={{ width: `${ratio}%` }}
        />
      </div>
    </div>
  );
}

export function RiskView({
  snapshot,
  emergencyPending,
  onActivateEmergencyStop,
}: RiskViewProps) {
  const [reason, setReason] = useState("Manual risk circuit breaker activation from Risk panel.");
  const [flatten, setFlatten] = useState(true);
  const [actionResult, setActionResult] = useState<EmergencyStopResponse | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const risk = snapshot?.risk;

  async function handleEngageKillSwitch(): Promise<void> {
    setActionError(null);
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

  return (
    <div className="space-y-4">
      <div className="nexus-panel rounded-lg p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-cyan-400" />
            <h2 className="font-display text-base font-semibold text-white">
              Independent Risk Manager Telemetry
            </h2>
          </div>
          <span className="rounded border border-cyan-500/35 bg-cyan-500/10 px-2.5 py-0.5 font-mono text-[11px] text-cyan-200">
            STRICT CAPITAL PRESERVATION ENFORCED
          </span>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          <MeterBar
            label="Daily Loss vs 2.00% Circuit Breaker"
            value={risk?.daily_loss_pct ?? 0}
            limit={risk?.daily_loss_limit_pct ?? 2}
          />
          <MeterBar
            label="Total Drawdown vs 8.00% Maximum Limit"
            value={risk?.drawdown_pct ?? 0}
            limit={risk?.max_drawdown_pct ?? 8}
          />
          <MeterBar
            label="Concurrent Spot Positions"
            value={risk?.open_positions_count ?? 0}
            limit={risk?.max_concurrent_positions ?? 2}
            unit=""
          />
          <MeterBar
            label="Daily Order Entries"
            value={risk?.daily_entries_count ?? 0}
            limit={risk?.max_daily_entries ?? 5}
            unit=""
          />
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div className="rounded border border-slate-800 bg-nexus-void/70 p-3 font-mono">
            <div className="text-[10px] uppercase text-slate-400">Risk Utilization</div>
            <div className="mt-1 text-base font-semibold tabular-nums text-cyan-300">
              {risk ? formatPct(risk.risk_utilization_pct) : "--"}
            </div>
          </div>
          <div className="rounded border border-slate-800 bg-nexus-void/70 p-3 font-mono">
            <div className="text-[10px] uppercase text-slate-400">Kill Switch State</div>
            <div
              className={`mt-1 text-base font-semibold ${
                risk?.kill_switch_active ? "text-rose-300" : "text-emerald-300"
              }`}
            >
              {risk?.kill_switch_active ? "ENGAGED" : "ARMED / CLEAR"}
            </div>
          </div>
          <div className="col-span-2 rounded border border-slate-800 bg-nexus-void/70 p-3 font-mono sm:col-span-1">
            <div className="text-[10px] uppercase text-slate-400">Triggered UTC</div>
            <div className="mt-1 text-xs text-slate-200">
              {formatUtcTime(risk?.kill_switch_triggered_at)}
            </div>
          </div>
        </div>
      </div>

      {/* Emergency Stop Control Center */}
      <div className="nexus-panel rounded-lg border-rose-500/35 p-4">
        <div className="flex items-center gap-2">
          <AlertOctagon className="h-4 w-4 text-rose-400" />
          <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-rose-200">
            Emergency Stop & Kill Switch Controls
          </h3>
        </div>
        <p className="mt-1.5 text-xs text-slate-300">
          Persists the kill switch state in PostgreSQL so automated restarts never resume blocked entries until explicitly cleared by an operator.
        </p>

        <div className="mt-4 space-y-3">
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={240}
            className="w-full rounded border border-rose-500/35 bg-nexus-void px-3 py-2 font-mono text-xs text-white focus:border-rose-400 focus:outline-none"
            placeholder="Audit reason for emergency stop"
          />

          <div className="flex flex-wrap items-center justify-between gap-3">
            <label className="inline-flex cursor-pointer items-center gap-2 font-mono text-xs text-slate-200">
              <input
                type="checkbox"
                checked={flatten}
                onChange={(e) => setFlatten(e.target.checked)}
                className="h-3.5 w-3.5 accent-rose-500"
              />
              Submit emergency market exit orders for all open paper positions
            </label>

            <button
              type="button"
              disabled={emergencyPending}
              onClick={() => void handleEngageKillSwitch()}
              className="rounded border border-rose-400 bg-rose-600/90 px-4 py-1.5 font-mono text-xs font-semibold uppercase tracking-wider text-white transition hover:bg-rose-500 disabled:opacity-50"
            >
              {emergencyPending ? "EXECUTING HALT..." : "ACTIVATE EMERGENCY STOP"}
            </button>
          </div>

          {actionError && <p className="font-mono text-xs text-rose-300">{actionError}</p>}

          {actionResult && (
            <div className="rounded border border-rose-500/40 bg-rose-500/10 p-3 font-mono text-xs text-rose-200">
              Kill switch persisted at {formatUtcTime(actionResult.triggered_at)} · Flattened orders:{" "}
              {actionResult.flattened_orders_count} · Rejected flatten: {actionResult.rejected_flatten_count}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

