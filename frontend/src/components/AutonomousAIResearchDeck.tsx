import { useState } from "react";
import {
  AlertTriangle,
  Brain,
  Compass,
  Flame,
  RefreshCw,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Swords,
  Radio,
  ArrowUpRight,
  ArrowDownRight,
  Zap,
} from "lucide-react";
import type { AIResearchBriefing, AutonomousEngineStatus } from "../types/system";
import { CouncilOfQuantsDebateModal } from "./common/CouncilOfQuantsDebateModal";

interface AutonomousAIResearchDeckProps {
  briefing: AIResearchBriefing | null;
  onRefresh: () => Promise<void>;
  status?: AutonomousEngineStatus | null;
}

export function AutonomousAIResearchDeck({
  briefing,
  onRefresh,
  status,
}: AutonomousAIResearchDeckProps) {
  const [refreshing, setRefreshing] = useState(false);
  const [councilOpen, setCouncilOpen] = useState(false);

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
          color: "border-emerald-500/40 bg-emerald-500/15 text-emerald-300 shadow-sm shadow-emerald-950/40",
          text: "BULLISH EXPANSION",
        };
      case "BEARISH_LIQUIDATION":
        return {
          icon: <TrendingDown className="h-3.5 w-3.5 text-rose-400" />,
          color: "border-rose-500/40 bg-rose-500/15 text-rose-300 shadow-sm shadow-rose-950/40",
          text: "BEARISH LIQUIDATION",
        };
      case "COMPRESSION_SQUEEZE":
        return {
          icon: <Sparkles className="h-3.5 w-3.5 text-purple-400" />,
          color: "border-purple-500/40 bg-purple-500/15 text-purple-300 shadow-sm shadow-purple-950/40",
          text: "COMPRESSION SQUEEZE",
        };
      default:
        return {
          icon: <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />,
          color: "border-amber-500/40 bg-amber-500/15 text-amber-300 shadow-sm shadow-amber-950/40",
          text: "VOLATILE CHOP",
        };
    }
  })();

  return (
    <div className="relative overflow-hidden rounded-2xl border border-white/[0.08] bg-gradient-to-r from-[#0a1226]/90 via-[#070d1e]/95 to-[#091124]/90 p-5 shadow-2xl backdrop-blur-xl">
      {/* Header Strip */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.06] pb-3.5">
        <div className="flex items-center gap-2.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400 shadow-inner">
            <Brain className="h-4 w-4" />
          </div>
          <div>
            <h3 className="font-display text-xs font-bold uppercase tracking-wider text-white">
              Autonomous AI Quantitative Research Deck
            </h3>
            <span className="font-mono text-[10px] text-slate-400">
              CrowLLM • 54 Spot Pairs Ingested • Continuous Macro Telemetry
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2.5">
          <span className="font-mono text-[11px] text-slate-400">
            Updated:{" "}
            {briefing?.updated_at
              ? new Date(briefing.updated_at).toLocaleTimeString()
              : "Just now"}
          </span>
          <button
            type="button"
            onClick={() => setCouncilOpen(true)}
            className="flex items-center gap-1.5 rounded-xl border border-violet-500/30 bg-violet-500/10 px-3 py-1.5 font-mono text-xs font-semibold text-violet-300 transition-all hover:bg-violet-500/20 hover:border-violet-400 active:scale-95"
            title="Convene Multi-Agent Council of Quants Debate Arena"
          >
            <Swords className="h-3.5 w-3.5 text-violet-400" />
            COUNCIL DEBATE
          </button>
          <button
            type="button"
            disabled={refreshing}
            onClick={handleRefresh}
            className="flex items-center gap-1.5 rounded-xl border border-cyan-500/30 bg-cyan-500/10 px-3 py-1.5 font-mono text-xs font-semibold text-cyan-300 transition-all hover:bg-cyan-500/20 active:scale-95 disabled:opacity-50"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 ${refreshing ? "animate-spin text-cyan-300" : ""}`}
            />
            {refreshing ? "RESEARCHING..." : "REFRESH AI"}
          </button>
        </div>
      </div>

      {/* Main Grid: Quantitative Pulse + Executive Brief + Alpha Picks */}
      <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-12">
        {/* Left: Macro Regime & Sentiment Meter (4 cols) */}
        <div className="space-y-3.5 lg:col-span-4">
          <div className="rounded-xl border border-white/[0.06] bg-slate-950/60 p-4 shadow-inner">
            <div className="flex items-center justify-between text-xs">
              <span className="font-mono text-slate-400">Macro Regime:</span>
              <span
                className={`flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 font-mono text-[10px] font-bold ${regimeBadge.color}`}
              >
                {regimeBadge.icon}
                {regimeBadge.text}
              </span>
            </div>

            <div className="mt-3.5">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-slate-400">Quant Sentiment:</span>
                <span className="font-bold text-white tabular-nums">
                  {sentiment} / 100 ({sentimentLabel})
                </span>
              </div>
              <div className="mt-2 h-2.5 w-full overflow-hidden rounded-full bg-slate-900 border border-white/5">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-rose-500 via-amber-400 to-emerald-400 transition-all duration-500 shadow-sm"
                  style={{ width: `${Math.max(5, Math.min(sentiment, 100))}%` }}
                />
              </div>
              <div className="mt-1.5 flex justify-between font-mono text-[9px] text-slate-500">
                <span>0 FEAR</span>
                <span>50 NEUTRAL</span>
                <span>100 GREED</span>
              </div>
            </div>

            <div className="mt-3.5 flex items-center justify-between border-t border-white/[0.06] pt-2.5 text-xs font-mono">
              <span className="flex items-center gap-1.5 text-slate-400">
                <Compass className="h-3.5 w-3.5 text-cyan-400" />
                Momentum Sector:
              </span>
              <span className="font-bold text-cyan-300">
                {briefing?.top_momentum_sector ?? "Layer 1 & AI"}
              </span>
            </div>
          </div>

          {/* Risk Advisory */}
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 font-mono text-xs text-amber-200">
            <div className="flex items-center gap-1.5 font-bold uppercase text-amber-300">
              <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
              Risk Advisory
            </div>
            <p className="mt-1 leading-relaxed text-amber-200/90 text-[11px]">
              {briefing?.risk_advisory ??
                "Observe stop-loss thresholds. Risk limits cannot be bypassed by automated agents."}
            </p>
          </div>
        </div>

        {/* Center: Executive Research Commentary (5 cols) */}
        <div className="flex flex-col justify-between rounded-xl border border-white/[0.06] bg-slate-950/60 p-4 shadow-inner lg:col-span-5">
          <div>
            <div className="flex items-center gap-2 font-mono text-xs font-bold uppercase tracking-wider text-cyan-400">
              <Flame className="h-4 w-4 text-cyan-400" />
              CrowLLM Institutional Market Thesis
            </div>
            <p className="mt-2.5 text-xs leading-relaxed text-slate-200">
              {briefing?.executive_briefing ??
                "Autonomous research agent ingesting 54 Binance spot markets. Synthesizing cross-pair order flow, synthetic spreads, and volume breadth."}
            </p>
          </div>

          <div className="mt-4 border-t border-white/[0.06] pt-2.5 font-mono text-[10px] text-slate-400">
            <span className="font-semibold text-cyan-400">Quantitative Edge:</span> Speed + pattern recognition
            across 54 markets simultaneously. Zero emotional hesitation.
          </div>
        </div>

        {/* Right: Top Alpha Picks (3 cols) */}
        <div className="space-y-2 lg:col-span-3">
          <div className="font-mono text-[11px] font-bold uppercase tracking-wider text-slate-400">
            Top Alpha Candidates
          </div>

          {!briefing?.top_alpha_picks || briefing.top_alpha_picks.length === 0 ? (
            <div className="rounded-xl border border-white/[0.06] bg-slate-950/60 p-4 font-mono text-xs text-slate-500 text-center">
              Evaluating relative strength candidates...
            </div>
          ) : (
            briefing.top_alpha_picks.slice(0, 3).map((pick) => (
              <div
                key={pick.symbol}
                className="rounded-xl border border-white/[0.06] bg-slate-950/60 p-2.5 transition-all hover:border-cyan-500/40 hover:bg-slate-900/60"
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-white">
                    {pick.symbol}
                  </span>
                  <span
                    className={`rounded-full px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wider ${
                      pick.conviction === "HIGH"
                        ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                        : "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                    }`}
                  >
                    {pick.conviction}
                  </span>
                </div>
                <p className="mt-1 line-clamp-2 text-[10px] text-slate-300 leading-normal">
                  {pick.thesis}
                </p>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Binance Spot & Futures Real-Time Opportunity Radar (110+ Coins) */}
      <div className="mt-4 rounded-xl border border-white/[0.08] bg-[#020617]/90 p-4 shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/[0.06] pb-3">
          <div className="flex items-center gap-2.5">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <Radio className="h-4 w-4 animate-pulse text-cyan-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-display text-xs font-bold uppercase tracking-wider text-white">
                  Binance Spot & Futures Opportunity Radar
                </span>
                <span className="rounded bg-gradient-to-r from-cyan-950 to-blue-950 px-2 py-0.5 font-mono text-[9px] font-bold text-cyan-300 border border-cyan-500/40">
                  {status?.universe_size ?? 110}+ COINS ACTIVE
                </span>
                <span className="rounded bg-emerald-950/80 px-2 py-0.5 font-mono text-[9px] font-bold text-emerald-300 border border-emerald-500/30">
                  SPOT BUY + FUTURES LONG/SHORT
                </span>
              </div>
              <p className="font-mono text-[10px] text-slate-400 mt-0.5">
                Continuous high-throughput scanning across all liquid Binance markets with automated order placement.
              </p>
            </div>
          </div>

          {/* Currently evaluated cycle queue */}
          {status?.recently_evaluated_symbols && status.recently_evaluated_symbols.length > 0 && (
            <div className="flex items-center gap-1.5 font-mono text-[10px] text-slate-400">
              <span className="text-slate-500">Live Cycle Queue:</span>
              <div className="flex flex-wrap items-center gap-1">
                {status.recently_evaluated_symbols.slice(0, 6).map((sym) => (
                  <span
                    key={sym}
                    className="rounded bg-slate-900 px-1.5 py-0.5 text-slate-300 border border-white/5"
                  >
                    {sym.replace("/USDT", "")}
                  </span>
                ))}
                {status.recently_evaluated_symbols.length > 6 && (
                  <span className="text-slate-500">
                    +{status.recently_evaluated_symbols.length - 6} more
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Live Opportunities Cards Grid */}
        <div className="mt-3.5 grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-4">
          {(!status?.recent_opportunities || status.recent_opportunities.length === 0) ? (
            <div className="col-span-full rounded-lg border border-white/5 bg-slate-950/50 p-4 text-center font-mono text-xs text-slate-500">
              Scanning 110+ Binance Spot & Futures pairs for breakout and mean-reversion setups...
            </div>
          ) : (
            status.recent_opportunities.slice(0, 8).map((opp) => (
              <div
                key={opp.symbol}
                className="group relative overflow-hidden rounded-xl border border-white/[0.06] bg-slate-950/70 p-3 transition-all hover:border-cyan-500/40 hover:bg-slate-900/60 shadow-inner"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-xs font-bold text-white">
                      {opp.symbol}
                    </span>
                    <span className="rounded bg-slate-900 px-1.5 py-0.5 font-mono text-[8px] text-slate-400 border border-white/5 uppercase">
                      {opp.sector.replace("_", " ")}
                    </span>
                  </div>
                  <span
                    className={`rounded px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wider border ${
                      opp.type === "BREAKOUT"
                        ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
                        : opp.type === "DIP_REVERSAL"
                          ? "bg-amber-500/20 text-amber-300 border-amber-500/30"
                          : "bg-cyan-500/20 text-cyan-300 border-cyan-500/30"
                    }`}
                  >
                    {opp.type}
                  </span>
                </div>

                <div className="mt-2.5 flex items-center justify-between font-mono text-xs">
                  <div>
                    <span className="text-[10px] text-slate-500 block">Price</span>
                    <span className="font-bold text-slate-200">
                      ${opp.last_price >= 1 ? opp.last_price.toFixed(2) : opp.last_price.toFixed(4)}
                    </span>
                  </div>
                  <div className="text-right">
                    <span className="text-[10px] text-slate-500 block">24h Momentum</span>
                    <span
                      className={`inline-flex items-center gap-0.5 font-bold tabular-nums ${
                        opp.change_24h_pct >= 0 ? "text-emerald-400" : "text-rose-400"
                      }`}
                    >
                      {opp.change_24h_pct >= 0 ? (
                        <ArrowUpRight className="h-3 w-3" />
                      ) : (
                        <ArrowDownRight className="h-3 w-3" />
                      )}
                      {opp.change_24h_pct >= 0 ? "+" : ""}
                      {opp.change_24h_pct.toFixed(2)}%
                    </span>
                  </div>
                </div>

                <div className="mt-2 flex items-center justify-between border-t border-white/[0.04] pt-2 font-mono text-[9px]">
                  <span className="text-slate-400">Score: {opp.score}</span>
                  <span className="text-cyan-400/90 font-semibold">Dual Spot+Futures</span>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Live Orders Placed Blotter */}
        {status?.recent_orders_placed && status.recent_orders_placed.length > 0 && (
          <div className="mt-3.5 flex flex-wrap items-center gap-2 rounded-lg border border-emerald-500/20 bg-emerald-950/20 p-2.5 font-mono text-xs">
            <span className="text-emerald-400 text-[11px] font-bold flex items-center gap-1">
              <Zap className="h-3 w-3" />
              Recent Autonomous Executions:
            </span>
            <div className="flex flex-wrap items-center gap-1.5">
              {status.recent_orders_placed.slice(-4).map((orderDesc, idx) => (
                <span
                  key={idx}
                  className="rounded bg-slate-900/90 px-2 py-0.5 text-[10px] font-bold text-emerald-300 border border-emerald-500/30"
                >
                  ⚡ {orderDesc}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {councilOpen && (
        <CouncilOfQuantsDebateModal
          isOpen={councilOpen}
          onClose={() => setCouncilOpen(false)}
        />
      )}
    </div>
  );
}
