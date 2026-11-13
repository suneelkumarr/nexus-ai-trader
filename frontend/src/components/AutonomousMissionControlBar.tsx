import { useState } from "react";
import { Activity, Play, Pause, RefreshCw, Zap, ShieldCheck } from "lucide-react";
import type { AutonomousEngineStatus } from "../types/system";

interface AutonomousMissionControlBarProps {
  status: AutonomousEngineStatus | null;
  onForceCycle: () => Promise<void>;
  onToggleEngine: () => Promise<void>;
}

export function AutonomousMissionControlBar({
  status,
  onForceCycle,
  onToggleEngine,
}: AutonomousMissionControlBarProps) {
  const [cycling, setCycling] = useState(false);
  const [toggling, setToggling] = useState(false);

  const isRunning = status?.is_running ?? true;

  async function handleCycle() {
    setCycling(true);
    try {
      await onForceCycle();
    } finally {
      setCycling(false);
    }
  }

  async function handleToggle() {
    setToggling(true);
    try {
      await onToggleEngine();
    } finally {
      setToggling(false);
    }
  }

  return (
    <div className="relative overflow-hidden rounded-lg border border-cyan-500/30 bg-gradient-to-r from-nexus-navy/95 via-nexus-void/90 to-nexus-navy/95 p-3 shadow-lg shadow-cyan-950/20 backdrop-blur-md">
      {/* Background scanline accent */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_left,rgba(6,182,212,0.1),transparent_60%)]" />

      <div className="relative flex flex-wrap items-center justify-between gap-3">
        {/* Left: Engine Status Badge */}
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center">
            {isRunning ? (
              <>
                <span className="absolute inline-flex h-3.5 w-3.5 animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-400" />
              </>
            ) : (
              <span className="inline-flex h-2.5 w-2.5 rounded-full bg-amber-400" />
            )}
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="font-display text-xs font-bold tracking-wider text-white">
                AUTONOMOUS MULTI-AGENT ENGINE
              </span>
              <span
                className={`rounded px-1.5 py-0.2 font-mono text-[9px] font-semibold uppercase ${
                  isRunning
                    ? "border border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
                    : "border border-amber-500/40 bg-amber-500/15 text-amber-300"
                }`}
              >
                {isRunning ? "AUTONOMOUS 24/7" : "PAUSED"}
              </span>
              <span className="rounded border border-cyan-500/30 bg-cyan-500/10 px-1.5 py-0.2 font-mono text-[9px] text-cyan-300">
                PAPER ONLY
              </span>
            </div>
            <div className="font-mono text-[10px] text-slate-400">
              Deterministic Strategy V1 + 54-Market Arbitrage Hunter + CrowLLM Research Loop
            </div>
          </div>
        </div>

        {/* Center: Live Telemetry Chips */}
        <div className="flex flex-wrap items-center gap-2 font-mono text-[11px]">
          <div className="flex items-center gap-1.5 rounded border border-slate-800 bg-nexus-void/80 px-2.5 py-1">
            <Activity className="h-3 w-3 text-cyan-400" />
            <span className="text-slate-400">Cycle:</span>
            <span className="font-semibold text-white">#{status?.cycle_count ?? "--"}</span>
          </div>

          <div className="flex items-center gap-1.5 rounded border border-slate-800 bg-nexus-void/80 px-2.5 py-1">
            <Zap className="h-3 w-3 text-amber-400" />
            <span className="text-slate-400">Loop:</span>
            <span className="font-semibold text-amber-300">8s cadence</span>
          </div>

          <div className="flex items-center gap-1.5 rounded border border-slate-800 bg-nexus-void/80 px-2.5 py-1">
            <ShieldCheck className="h-3 w-3 text-emerald-400" />
            <span className="text-slate-400">Universe:</span>
            <span className="font-semibold text-emerald-300">54 Binance Pairs</span>
          </div>

          <div className="flex items-center gap-1.5 rounded border border-slate-800 bg-nexus-void/80 px-2.5 py-1">
            <span className="text-slate-400">Arb Captures:</span>
            <span className="font-semibold text-cyan-300">
              {status?.arbitrage_trades_count ?? 0}
            </span>
          </div>

          <div className="flex items-center gap-1.5 rounded border border-slate-800 bg-nexus-void/80 px-2.5 py-1">
            <span className="text-slate-400">Strategy Fills:</span>
            <span className="font-semibold text-white">
              {status?.strategy_trades_count ?? 0}
            </span>
          </div>
        </div>

        {/* Right: Operational Controls */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={cycling}
            onClick={handleCycle}
            className="flex items-center gap-1.5 rounded border border-cyan-500/40 bg-cyan-500/15 px-3 py-1 font-mono text-[11px] font-semibold text-cyan-300 transition-all hover:bg-cyan-500/25 active:scale-95 disabled:opacity-50"
          >
            <RefreshCw className={`h-3 w-3 ${cycling ? "animate-spin text-cyan-300" : ""}`} />
            {cycling ? "EVALUATING..." : "FORCE CYCLE NOW"}
          </button>

          <button
            type="button"
            disabled={toggling}
            onClick={handleToggle}
            className={`flex items-center gap-1.5 rounded border px-3 py-1 font-mono text-[11px] font-semibold transition-all active:scale-95 disabled:opacity-50 ${
              isRunning
                ? "border-amber-500/40 bg-amber-500/15 text-amber-300 hover:bg-amber-500/25"
                : "border-emerald-500/40 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25"
            }`}
          >
            {isRunning ? (
              <>
                <Pause className="h-3 w-3" />
                PAUSE ENGINE
              </>
            ) : (
              <>
                <Play className="h-3 w-3" />
                RESUME ENGINE
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

