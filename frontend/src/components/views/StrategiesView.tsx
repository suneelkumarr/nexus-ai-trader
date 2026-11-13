import { Cpu, ShieldCheck } from "lucide-react";
import type {
  SanitizedSettingsResponse,
  TerminalSnapshotResponse,
} from "../../types/system";
import { formatUsdt, formatUtcTime } from "../../utils/format";

interface StrategiesViewProps {
  snapshot: TerminalSnapshotResponse | null;
  settings: SanitizedSettingsResponse | null;
}

export function StrategiesView({ snapshot, settings }: StrategiesViewProps) {
  const signals = snapshot?.latest_signals ?? [];
  const strategyConfig = settings?.strategy_v1 ?? {};

  return (
    <div className="space-y-4">
      <div className="nexus-panel rounded-lg p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Cpu className="h-4 w-4 text-cyan-400" />
            <h2 className="font-display text-base font-semibold text-white">
              NEXUS Strategy Engine V1
            </h2>
          </div>
          <span className="rounded border border-cyan-500/35 bg-cyan-500/10 px-2.5 py-0.5 font-mono text-[11px] text-cyan-200">
            EMA20 / EMA50 + RSI14 + ATR14 + VOLUME SMA20
          </span>
        </div>

        <p className="mt-2 text-xs leading-relaxed text-slate-300">
          Deterministic signal generator evaluated strictly on fully closed UTC candles without look-ahead access.
          Signals require Independent Risk Manager approval before virtual paper execution and make zero profitability claims.
        </p>

        {Object.keys(strategyConfig).length > 0 && (
          <div className="mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-5">
            {Object.entries(strategyConfig).map(([key, value]) => (
              <div
                key={key}
                className="rounded border border-cyan-500/15 bg-nexus-void/80 p-2.5 font-mono"
              >
                <div className="text-[10px] uppercase text-slate-400">{key}</div>
                <div className="mt-0.5 text-xs font-semibold tabular-nums text-cyan-300">
                  {String(value)}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="nexus-panel rounded-lg p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
            Latest Closed-Candle Evaluations
          </h3>
          <div className="flex items-center gap-1.5 font-mono text-[11px] text-emerald-300">
            <ShieldCheck className="h-3.5 w-3.5" />
            NO LOOK-AHEAD BIAS
          </div>
        </div>

        {signals.length === 0 ? (
          <div className="rounded border border-slate-800 bg-nexus-void/70 p-6 text-center font-mono text-xs text-slate-400">
            No strategy V1 signals available yet. Sync at least 52 closed OHLCV bars in PostgreSQL per symbol.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {signals.map((signal) => (
              <div
                key={`${signal.symbol}-${signal.timestamp}`}
                className="rounded-md border border-cyan-500/20 bg-nexus-void/85 p-3.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <span className="font-mono text-sm font-semibold text-white">
                      {signal.symbol}
                    </span>
                    <span className="ml-2 font-mono text-[11px] text-slate-400">
                      {signal.strategy_name}
                    </span>
                  </div>
                  <span
                    className={`rounded px-2 py-0.5 font-mono text-[11px] font-semibold uppercase ${
                      signal.direction === "long"
                        ? "bg-emerald-500/20 text-emerald-300"
                        : signal.direction === "exit_long"
                          ? "bg-amber-500/20 text-amber-300"
                          : "bg-slate-800 text-slate-300"
                    }`}
                  >
                    {signal.direction}
                  </span>
                </div>

                <p className="mt-2 text-xs text-slate-300">{signal.reason}</p>

                <div className="mt-3 grid grid-cols-3 gap-2 border-t border-slate-800 pt-2.5 font-mono text-[11px]">
                  <div>
                    <span className="block text-[10px] text-slate-500">ENTRY REF</span>
                    <span className="tabular-nums text-cyan-300">
                      {formatUsdt(signal.entry_price)}
                    </span>
                  </div>
                  <div>
                    <span className="block text-[10px] text-slate-500">STOP REF</span>
                    <span className="tabular-nums text-amber-300">
                      {formatUsdt(signal.stop_price)}
                    </span>
                  </div>
                  <div>
                    <span className="block text-[10px] text-slate-500">CANDLE UTC</span>
                    <span className="text-slate-300">{formatUtcTime(signal.timestamp)}</span>
                  </div>
                </div>

                {Object.keys(signal.indicators).length > 0 && (
                  <div className="mt-2.5 flex flex-wrap gap-2 border-t border-slate-800/80 pt-2 font-mono text-[10px]">
                    {Object.entries(signal.indicators).map(([indName, indValue]) => (
                      <span
                        key={indName}
                        className="rounded bg-slate-900 px-2 py-0.5 text-slate-300"
                      >
                        {indName}:{" "}
                        <strong className="tabular-nums text-cyan-300">
                          {Number.isFinite(indValue) ? indValue.toFixed(4) : String(indValue)}
                        </strong>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
