import { useState } from "react";
import {
  Brain,
  Sparkles,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  RefreshCw,
  Compass,
  Flame,
} from "lucide-react";
import type { AIResearchBriefing } from "../types/system";

interface AutonomousAIResearchDeckProps {
  briefing: AIResearchBriefing | null;
  onRefresh: () => Promise<void>;
}

export function AutonomousAIResearchDeck({
  briefing,
  onRefresh,
}: AutonomousAIResearchDeckProps) {
  const [refreshing, setRefreshing] = useState(false);

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setRefreshing(false);
    }
  }

  const sentiment = briefing?.sentiment_index ?? 50;
  const sentimentLabel = briefing?.sentiment_label ?? "Neutral";
  const regime = briefing?.macro_regime ?? "VOLATILE_CHOP";

  // Regime style mapping
  const regimeBadge = (() => {
    switch (regime) {
      case "BULLISH_EXPANSION":
        return {
          icon: <TrendingUp className="h-3.5 w-3.5 text-emerald-400" />,
          color: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
          text: "BULLISH EXPANSION",
        };
      case "BEARISH_LIQUIDATION":
        return {
          icon: <TrendingDown className="h-3.5 w-3.5 text-rose-400" />,
          color: "border-rose-500/40 bg-rose-500/10 text-rose-300",
          text: "BEARISH LIQUIDATION",
        };
      case "COMPRESSION_SQUEEZE":
        return {
          icon: <Sparkles className="h-3.5 w-3.5 text-purple-400" />,
          color: "border-purple-500/40 bg-purple-500/10 text-purple-300",
          text: "COMPRESSION SQUEEZE",
        };
      default:
        return {
          icon: <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />,
          color: "border-amber-500/40 bg-amber-500/10 text-amber-300",
          text: "VOLATILE CHOP",
        };
    }
  })();

  return (
    <div className="relative overflow-hidden rounded-lg border border-cyan-500/20 bg-nexus-navy/90 p-4 shadow-md backdrop-blur-md">
      {/* Header Strip */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-cyan-500/15 pb-3">
        <div className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-cyan-400" />
          <h3 className="font-display text-xs font-bold uppercase tracking-wider text-white">
            Autonomous AI Market Research Agent
          </h3>
          <span className="rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 font-mono text-[9px] text-cyan-300">
            CrowLLM • 54 Markets Ingested
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] text-slate-400">
            Updated:{" "}
            {briefing?.updated_at
              ? new Date(briefing.updated_at).toLocaleTimeString()
              : "Just now"}
          </span>
          <button
            type="button"
            disabled={refreshing}
            onClick={handleRefresh}
            className="flex items-center gap-1 rounded border border-cyan-500/30 bg-cyan-500/10 px-2.5 py-1 font-mono text-[10px] text-cyan-300 transition-all hover:bg-cyan-500/20 active:scale-95 disabled:opacity-50"
          >
            <RefreshCw
              className={`h-3 w-3 ${refreshing ? "animate-spin text-cyan-300" : ""}`}
            />
            {refreshing ? "RESEARCHING..." : "REFRESH AI"}
          </button>
        </div>
      </div>

      {/* Main Grid: Quantitative Pulse + Executive Brief + Alpha Picks */}
      <div className="mt-3 grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* Left: Macro Regime & Sentiment Meter (4 cols) */}
        <div className="space-y-3 lg:col-span-4">
          <div className="rounded border border-slate-800 bg-nexus-void/80 p-3">
            <div className="flex items-center justify-between text-[11px]">
              <span className="font-mono text-slate-400">Macro Regime:</span>
              <span
                className={`flex items-center gap-1 rounded border px-2 py-0.5 font-mono text-[10px] font-semibold ${regimeBadge.color}`}
              >
                {regimeBadge.icon}
                {regimeBadge.text}
              </span>
            </div>

            <div className="mt-3">
              <div className="flex items-center justify-between text-[11px] font-mono">
                <span className="text-slate-400">Quantitative Sentiment:</span>
                <span className="font-semibold text-white">
                  {sentiment} / 100 ({sentimentLabel})
                </span>
              </div>
              <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-slate-800">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-rose-500 via-amber-400 to-emerald-400 transition-all duration-500"
                  style={{ width: `${Math.max(5, Math.min(sentiment, 100))}%` }}
                />
              </div>
              <div className="mt-1 flex justify-between font-mono text-[9px] text-slate-500">
                <span>0 FEAR</span>
                <span>50 NEUTRAL</span>
                <span>100 GREED</span>
              </div>
            </div>

            <div className="mt-3 flex items-center justify-between border-t border-slate-800/80 pt-2 text-[11px] font-mono">
              <span className="flex items-center gap-1 text-slate-400">
                <Compass className="h-3 w-3 text-cyan-400" />
                Leading Sector:
              </span>
              <span className="font-semibold text-cyan-300">
                {briefing?.top_momentum_sector ?? "Layer 1 & AI"}
              </span>
            </div>
          </div>

          {/* Risk Advisory */}
          <div className="rounded border border-amber-500/30 bg-amber-500/5 p-2.5 font-mono text-[11px] text-amber-200">
            <div className="flex items-center gap-1.5 font-semibold uppercase text-amber-300">
              <AlertTriangle className="h-3 w-3 text-amber-400" />
              Risk Advisory
            </div>
            <p className="mt-1 leading-relaxed text-amber-200/90">
              {briefing?.risk_advisory ??
                "Observe stop-loss thresholds. Risk limits cannot be bypassed by automated agents."}
            </p>
          </div>
        </div>

        {/* Center: Executive Research Commentary (5 cols) */}
        <div className="flex flex-col justify-between rounded border border-slate-800 bg-nexus-void/80 p-3 lg:col-span-5">
          <div>
            <div className="flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wider text-cyan-400">
              <Flame className="h-3.5 w-3.5 text-cyan-400" />
              CrowLLM Institutional Market Commentary
            </div>
            <p className="mt-2 text-xs leading-relaxed text-slate-200">
              {briefing?.executive_briefing ??
                "Autonomous research agent ingesting 54 Binance spot markets. Synthesizing cross-pair order flow, synthetic spreads, and volume breadth."}
            </p>
          </div>

          <div className="mt-3 border-t border-slate-800/80 pt-2 font-mono text-[10px] text-slate-400">
            <span className="text-cyan-400">Quantitative Edge:</span> Speed + pattern recognition
            across 54 markets simultaneously. Zero emotional hesitation.
          </div>
        </div>

        {/* Right: Top Alpha Picks (3 cols) */}
        <div className="space-y-2 lg:col-span-3">
          <div className="font-mono text-[11px] uppercase tracking-wider text-slate-400">
            Top Alpha Candidates
          </div>

          {(!briefing?.top_alpha_picks || briefing.top_alpha_picks.length === 0) ? (
            <div className="rounded border border-slate-800 bg-nexus-void/70 p-3 font-mono text-[10px] text-slate-500">
              Evaluating relative strength candidates...
            </div>
          ) : (
            briefing.top_alpha_picks.slice(0, 3).map((pick) => (
              <div
                key={pick.symbol}
                className="rounded border border-cyan-500/20 bg-nexus-void/90 p-2 transition-colors hover:border-cyan-500/40"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-white">
                    {pick.symbol}
                  </span>
                  <span
                    className={`rounded px-1.5 py-0.2 font-mono text-[9px] font-semibold uppercase ${
                      pick.conviction === "HIGH"
                        ? "bg-emerald-500/20 text-emerald-300"
                        : "bg-cyan-500/20 text-cyan-300"
                    }`}
                  >
                    {pick.conviction}
                  </span>
                </div>
                <p className="mt-1 line-clamp-2 text-[10px] text-slate-300">
                  {pick.thesis}
                </p>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

