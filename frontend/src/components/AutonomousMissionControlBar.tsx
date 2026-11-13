import { useState } from "react";
import { Activity, Play, Pause, RefreshCw, Zap, Cpu } from "lucide-react";
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
    <div className="relative overflow-hidden rounded-2xl border border-white/[0.08] bg-gradient-to-r from-[#0b1329]/95 via-[#080e1e]/90 to-[#0b1329]/95 p-4 shadow-xl backdrop-blur-xl">
      {/* Background ambient lighting */}
      <div className="pointer-events-none absolute -left-12 -top-12 h-40 w-40 rounded-full bg-cyan-500/10 blur-2xl" />
      <div className="pointer-events-none absolute -right-12 -bottom-12 h-40 w-40 rounded-full bg-emerald-500/10 blur-2xl" />

      <div className="relative flex flex-wrap items-center justify-between gap-4">
        {/* Left: Engine Identity & Live Beacon */}
        <div className="flex items-center gap-3.5">
          <div className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-slate-900/80 shadow-inner">
            {isRunning ? (
              <>
                <span className="absolute inline-flex h-4 w-4 animate-ping rounded-full bg-emerald-400 opacity-60" />
                <Cpu className="relative h-5 w-5 text-emerald-400" />
              </>
            ) : (
              <Cpu className="h-5 w-5 text-amber-400" />
            )}
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="font-display text-sm font-bold tracking-wide text-white">
                AUTONOMOUS MULTI-AGENT ENGINE
              </span>
              <span
                className={`rounded-full px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wider ${
                  isRunning
                    ? "border border-emerald-500/40 bg-emerald-500/15 text-emerald-300 shadow-sm shadow-emerald-950/40"
                    : "border border-amber-500/40 bg-amber-500/15 text-amber-300"
                }`}
              >
                {isRunning ? "ONLINE 24/7" : "STANDBY"}
              </span>
              <span className="rounded-full border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 font-mono text-[9px] font-semibold text-cyan-300">
                PAPER SECURE
              </span>
            </div>
            <div className="font-mono text-[11px] text-slate-400 mt-0.5">
              Multi-Asset Scanner · 110+ Binance Spot & Futures Markets · Spot Buy & Futures Long/Short Dual Execution
            </div>
          </div>
        </div>

        {/* Center: Real-time Telemetry Stats */}
        <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
          <div className="flex items-center gap-2 rounded-xl border border-white/5 bg-slate-950/60 px-3 py-1.5 shadow-inner">
            <Activity className="h-3.5 w-3.5 text-cyan-400" />
            <span className="text-slate-400 text-[11px]">Cycle:</span>
            <span className="font-bold text-white tabular-nums">#{status?.cycle_count ?? "--"}</span>
          </div>

          <div className="flex items-center gap-2 rounded-xl border border-white/5 bg-slate-950/60 px-3 py-1.5 shadow-inner">
            <Zap className="h-3.5 w-3.5 text-amber-400" />
            <span className="text-slate-400 text-[11px]">Interval:</span>
            <span className="font-bold text-amber-300 tabular-nums">8s</span>
          </div>

          <div className="flex items-center gap-2 rounded-xl border border-white/5 bg-slate-950/60 px-3 py-1.5 shadow-inner">
            <span className="text-slate-400 text-[11px]">Arb Captures:</span>
            <span className="font-bold text-cyan-300 tabular-nums">
              {status?.arbitrage_trades_count ?? 0}
            </span>
          </div>

          <div className="flex items-center gap-2 rounded-xl border border-white/5 bg-slate-950/60 px-3 py-1.5 shadow-inner">
            <span className="text-slate-400 text-[11px]">Strategy Fills:</span>
            <span className="font-bold text-emerald-300 tabular-nums">
              {status?.strategy_trades_count ?? 0}
            </span>
          </div>

          <div className="flex items-center gap-2 rounded-xl border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 shadow-inner">
            <span className="text-cyan-400 text-[11px]">Universe:</span>
            <span className="font-bold text-cyan-300 tabular-nums">
              {status?.universe_size ?? 110}+ Pairs
            </span>
          </div>
        </div>

        {/* Right: Operational Control Buttons */}
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            disabled={cycling}
            onClick={handleCycle}
            className="flex items-center gap-2 rounded-xl border border-cyan-500/40 bg-cyan-500/15 px-3.5 py-2 font-mono text-xs font-bold text-cyan-300 shadow-md shadow-cyan-950/30 transition-all hover:bg-cyan-500/25 active:scale-95 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${cycling ? "animate-spin text-cyan-300" : ""}`} />
            <span>{cycling ? "EVALUATING..." : "FORCE CYCLE"}</span>
          </button>

          <button
            type="button"
            disabled={toggling}
            onClick={handleToggle}
            className={`flex items-center gap-2 rounded-xl border px-3.5 py-2 font-mono text-xs font-bold transition-all shadow-md active:scale-95 disabled:opacity-50 ${
              isRunning
                ? "border-amber-500/40 bg-amber-500/15 text-amber-300 hover:bg-amber-500/25 shadow-amber-950/30"
                : "border-emerald-500/40 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25 shadow-emerald-950/30"
            }`}
          >
            {isRunning ? (
              <>
                <Pause className="h-3.5 w-3.5" />
                <span>PAUSE</span>
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5" />
                <span>RESUME</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
