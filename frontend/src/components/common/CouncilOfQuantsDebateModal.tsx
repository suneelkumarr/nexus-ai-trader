import { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { X, Swords, RefreshCw } from "lucide-react";
import { fetchCouncilDebate } from "../../services/apiClient";
import type { CouncilDebateResult } from "../../types/system";
import { NexusSelect } from "./NexusSelect";

interface CouncilOfQuantsDebateModalProps {
  isOpen: boolean;
  onClose: () => void;
  defaultSymbol?: string;
}

const DEBATE_SYMBOLS = [
  "BTC/USDT",
  "ETH/USDT",
  "SOL/USDT",
  "BNB/USDT",
  "AVAX/USDT",
  "NEAR/USDT",
  "LINK/USDT",
  "FET/USDT",
  "DOGE/USDT",
  "SUI/USDT",
];

export function CouncilOfQuantsDebateModal({
  isOpen,
  onClose,
  defaultSymbol = "BTC/USDT",
}: CouncilOfQuantsDebateModalProps) {
  const [symbol, setSymbol] = useState<string>(defaultSymbol);
  const [timeframe, setTimeframe] = useState<string>("15m");
  const [debate, setDebate] = useState<CouncilDebateResult | null>(null);
  const [debating, setDebating] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const runDebate = async (targetSymbol: string) => {
    setDebating(true);
    setError(null);
    try {
      const res = await fetchCouncilDebate({
        symbol: targetSymbol,
        timeframe,
      });
      setDebate(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to run Council debate.");
    } finally {
      setDebating(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      runDebate(symbol);
      const prevOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = prevOverflow;
      };
    }
  }, [isOpen, symbol, timeframe]);

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-3 backdrop-blur-md overflow-y-auto">
      <div className="nexus-panel max-h-[94vh] w-full max-w-5xl overflow-y-auto rounded-xl border border-cyan-500/40 bg-[#040816] p-6 shadow-2xl space-y-5">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-cyan-500/20 pb-4">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-500/20 to-purple-500/20 border border-cyan-400 text-cyan-300 shadow-lg shadow-cyan-500/20">
              <Swords className="h-6 w-6 text-cyan-300 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-display text-lg font-bold tracking-wider text-white">
                  COUNCIL OF QUANTS // MULTI-AGENT DEBATE ARENA
                </h2>
                <span className="rounded bg-gradient-to-r from-cyan-950 to-purple-950 px-2 py-0.5 font-mono text-[10px] text-cyan-300 border border-cyan-500/40 uppercase font-bold">
                  PHASE 1 ARCHITECTURE
                </span>
              </div>
              <p className="font-mono text-xs text-slate-400">
                Adversarial AI Consensus Engine · Momentum Bull Agent vs Risk Skeptic Bear Agent vs Chief Arbitrator
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={debating}
              onClick={() => runDebate(symbol)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-400/60 bg-cyan-500/20 px-3 py-1.5 font-mono text-xs font-semibold text-cyan-200 hover:bg-cyan-500/30 transition shadow disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${debating ? "animate-spin text-cyan-300" : ""}`} />
              <span>{debating ? "DEBATING LIVE..." : "TRIGGER DEBATE"}</span>
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700 bg-slate-800 p-1.5 text-slate-400 hover:text-white"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Controls Bar: Asset & Timeframe Switcher */}
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-800 bg-[#030712] p-3 font-mono text-xs">
          <div className="flex flex-wrap items-center gap-3">
            <div className="w-48">
              <NexusSelect
                label="Asset to Debate"
                value={symbol}
                onChange={setSymbol}
                options={DEBATE_SYMBOLS}
                fullWidth
              />
            </div>
            <div className="w-32">
              <NexusSelect
                label="Timeframe"
                value={timeframe}
                onChange={setTimeframe}
                options={["5m", "15m", "1h", "4h"]}
                fullWidth
              />
            </div>
          </div>

          <div className="flex items-center gap-2 text-[11px] text-slate-400">
            <span>Pre-Trade Execution Gate:</span>
            <span className="rounded bg-slate-900 border border-slate-700 px-2 py-0.5 text-cyan-300 font-bold">
              MIN 72% CONVICTION REQUIRED TO ENTER
            </span>
          </div>
        </div>

        {error && (
          <div className="rounded border border-rose-500/40 bg-rose-950/20 p-3 font-mono text-xs text-rose-300">
            Debate engine notice: {error}
          </div>
        )}

        {/* Live Debate Arena: 2 Opposing Columns */}
        {debate && (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {/* AGENT 1: Momentum Bull Agent */}
            <div className="nexus-panel rounded-xl border border-emerald-500/40 bg-emerald-950/10 p-4 space-y-3.5 shadow-lg">
              <div className="flex items-center justify-between border-b border-emerald-500/20 pb-2.5">
                <div className="flex items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-300 font-bold">
                    🐂
                  </div>
                  <div>
                    <h3 className="font-display text-sm font-bold text-emerald-300">
                      MOMENTUM BULL AGENT
                    </h3>
                    <span className="font-mono text-[10px] text-emerald-400/80">
                      Upside Drivers & Alpha Expansion
                    </span>
                  </div>
                </div>

                <div className="text-right font-mono">
                  <div className="text-base font-bold text-emerald-300">
                    {debate.bull_thesis.score} / 100
                  </div>
                  <span className="rounded bg-emerald-900/60 px-2 py-0.5 text-[9px] font-bold text-emerald-200 uppercase border border-emerald-500/30">
                    {debate.bull_thesis.recommended_action}
                  </span>
                </div>
              </div>

              {/* Bull Key Drivers */}
              <div className="space-y-1.5 font-mono text-xs">
                <span className="text-[10px] uppercase font-bold text-slate-400">
                  Key Upside Catalysts:
                </span>
                <ul className="space-y-1">
                  {debate.bull_thesis.key_drivers.map((driver, idx) => (
                    <li key={idx} className="flex items-start gap-1.5 text-slate-200 text-[11px]">
                      <span className="text-emerald-400 font-bold shrink-0">✓</span>
                      <span>{driver}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Bull Supporting Arguments */}
              <div className="space-y-2 pt-2 border-t border-emerald-500/15">
                <span className="font-mono text-[10px] uppercase font-bold text-slate-400">
                  Technical Thesis Breakdown:
                </span>
                <div className="space-y-2">
                  {debate.bull_thesis.arguments.map((arg, idx) => (
                    <div
                      key={idx}
                      className="rounded border border-emerald-500/20 bg-[#030712] p-2.5 font-mono text-xs space-y-1"
                    >
                      <div className="flex items-center justify-between text-[10px]">
                        <span className="font-semibold text-emerald-300">{arg.category}</span>
                        <span className="text-slate-400">Impact: {arg.impact}</span>
                      </div>
                      <p className="text-slate-300 text-[11px] leading-relaxed">{arg.point}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* AGENT 2: Risk Skeptic Bear Agent */}
            <div className="nexus-panel rounded-xl border border-rose-500/40 bg-rose-950/10 p-4 space-y-3.5 shadow-lg">
              <div className="flex items-center justify-between border-b border-rose-500/20 pb-2.5">
                <div className="flex items-center gap-2">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-rose-500/20 text-rose-300 font-bold">
                    🐻
                  </div>
                  <div>
                    <h3 className="font-display text-sm font-bold text-rose-300">
                      RISK SKEPTIC BEAR AGENT
                    </h3>
                    <span className="font-mono text-[10px] text-rose-400/80">
                      Devil's Advocate & Trap Detection
                    </span>
                  </div>
                </div>

                <div className="text-right font-mono">
                  <div className="text-base font-bold text-rose-300">
                    {debate.bear_thesis.skepticism_score} / 100
                  </div>
                  <span
                    className={`rounded px-2 py-0.5 text-[9px] font-bold uppercase border ${
                      debate.bear_thesis.threat_level === "CRITICAL"
                        ? "bg-rose-900/80 text-rose-200 border-rose-500"
                        : debate.bear_thesis.threat_level === "ELEVATED"
                          ? "bg-amber-900/60 text-amber-200 border-amber-500/30"
                          : "bg-slate-900 text-slate-300 border-slate-700"
                    }`}
                  >
                    THREAT: {debate.bear_thesis.threat_level}
                  </span>
                </div>
              </div>

              {/* Bear Red Flags */}
              <div className="space-y-1.5 font-mono text-xs">
                <span className="text-[10px] uppercase font-bold text-slate-400">
                  Critical Vulnerabilities & Red Flags:
                </span>
                <ul className="space-y-1">
                  {debate.bear_thesis.red_flags.map((flag, idx) => (
                    <li key={idx} className="flex items-start gap-1.5 text-rose-200 text-[11px]">
                      <span className="text-rose-400 font-bold shrink-0">⚠️</span>
                      <span>{flag}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Bear Counter-Arguments */}
              <div className="space-y-2 pt-2 border-t border-rose-500/15">
                <span className="font-mono text-[10px] uppercase font-bold text-slate-400">
                  Counter-Argument Scrutiny:
                </span>
                <div className="space-y-2">
                  {debate.bear_thesis.counter_arguments.map((arg, idx) => (
                    <div
                      key={idx}
                      className="rounded border border-rose-500/20 bg-[#030712] p-2.5 font-mono text-xs space-y-1"
                    >
                      <div className="flex items-center justify-between text-[10px]">
                        <span className="font-semibold text-rose-300">{arg.category}</span>
                        <span className="text-slate-400">Impact: {arg.impact}</span>
                      </div>
                      <p className="text-slate-300 text-[11px] leading-relaxed">{arg.point}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* AGENT 3: Chief Arbitrator Consensus & Official Verdict */}
        {debate && (
          <div className="nexus-panel rounded-xl border border-cyan-500/50 bg-[#020617] p-5 space-y-4 shadow-2xl">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-cyan-500/20 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-cyan-500/20 text-cyan-300 font-bold">
                  ⚖️
                </div>
                <div>
                  <h3 className="font-display text-sm font-bold text-white uppercase tracking-wider">
                    CHIEF AI ARBITRATOR // SYNTHESIS & BINDING VERDICT
                  </h3>
                  <span className="font-mono text-[10px] text-slate-400">
                    Debate ID: #{debate.debate_id} · Mathematical Consensus Model
                  </span>
                </div>
              </div>

              {/* Verdict Badge */}
              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full px-3.5 py-1 font-mono text-xs font-bold border shadow-lg ${
                    debate.verdict === "APPROVED"
                      ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/60 shadow-emerald-500/20"
                      : debate.verdict === "CONDITIONAL"
                        ? "bg-amber-500/20 text-amber-300 border-amber-500/60 shadow-amber-500/20"
                        : "bg-rose-500/20 text-rose-300 border-rose-500/60 shadow-rose-500/20"
                  }`}
                >
                  <span
                    className={`h-2 w-2 rounded-full ${
                      debate.verdict === "APPROVED"
                        ? "bg-emerald-400 animate-ping"
                        : debate.verdict === "CONDITIONAL"
                          ? "bg-amber-400"
                          : "bg-rose-400"
                    }`}
                  />
                  <span>VERDICT: {debate.verdict}</span>
                </span>
              </div>
            </div>

            {/* Conviction Score & Action Sizing Deck */}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 font-mono text-xs">
              <div className="rounded-lg border border-slate-800 bg-[#030712] p-3 space-y-1.5">
                <span className="text-[10px] uppercase text-slate-400">Consensus Conviction</span>
                <div className="text-lg font-bold text-cyan-300">
                  {debate.consensus_conviction_pct}%
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-800">
                  <div
                    className={`h-full ${
                      debate.consensus_conviction_pct >= 72
                        ? "bg-emerald-400"
                        : debate.consensus_conviction_pct >= 58
                          ? "bg-amber-400"
                          : "bg-rose-500"
                    }`}
                    style={{ width: `${debate.consensus_conviction_pct}%` }}
                  />
                </div>
              </div>

              <div className="rounded-lg border border-slate-800 bg-[#030712] p-3 space-y-1">
                <span className="text-[10px] uppercase text-slate-400">Position Sizing Authorized</span>
                <div className="text-lg font-bold text-white">
                  {debate.suggested_sizing_multiplier.toFixed(1)}x Normal
                </div>
                <div className="text-[10px] text-slate-400">
                  {debate.suggested_sizing_multiplier === 0
                    ? "Zero trade permitted"
                    : `${(debate.suggested_sizing_multiplier * 10).toFixed(0)}% Portfolio Capital`}
                </div>
              </div>

              <div className="rounded-lg border border-slate-800 bg-[#030712] p-3 space-y-1">
                <span className="text-[10px] uppercase text-slate-400">Stop Loss Guidance</span>
                <div className="text-xs font-bold text-amber-300 truncate">
                  {debate.recommended_stop_adjustment}
                </div>
                <div className="text-[10px] text-slate-400">
                  Independent Risk Manager Enforced
                </div>
              </div>
            </div>

            {/* Official Rationale Box */}
            <div className="rounded-lg border border-cyan-500/25 bg-[#030712] p-3.5 font-mono text-xs space-y-1">
              <span className="font-semibold text-cyan-300 uppercase text-[10px]">
                Executive Synthesis & Ruling:
              </span>
              <p className="text-slate-200 leading-relaxed text-[11px]">
                {debate.verdict_rationale}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}
