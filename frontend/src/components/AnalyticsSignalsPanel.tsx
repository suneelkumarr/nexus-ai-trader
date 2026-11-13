import { useState } from "react";
import { Brain, Cpu, Sparkles, TriangleAlert } from "lucide-react";
import { fetchCandleAnalysis } from "../services/apiClient";
import type {
  MarketAnalysisOutput,
  TerminalSnapshotResponse,
} from "../types/system";
import { formatUsdt, formatUtcTime } from "../utils/format";
import { NexusSelect } from "./common/NexusSelect";

interface AnalyticsSignalsPanelProps {
  snapshot: TerminalSnapshotResponse | null;
}

const SYMBOLS = [
  // Layer 1 & Major
  "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "ADA/USDT", "AVAX/USDT",
  "SUI/USDT", "NEAR/USDT", "APT/USDT", "DOT/USDT", "SEI/USDT", "ATOM/USDT",
  // DeFi
  "LINK/USDT", "UNI/USDT", "AAVE/USDT", "MKR/USDT", "CRV/USDT", "LDO/USDT",
  "PENDLE/USDT", "JUP/USDT", "ONDO/USDT", "INJ/USDT", "RUNE/USDT",
  // AI & Decentralized Compute
  "FET/USDT", "RENDER/USDT", "TAO/USDT", "ICP/USDT", "THETA/USDT", "FIL/USDT", "TIA/USDT",
  // High-Velocity Memes
  "DOGE/USDT", "SHIB/USDT", "PEPE/USDT", "WIF/USDT", "BONK/USDT", "FLOKI/USDT",
  // Infrastructure & Scaling
  "XRP/USDT", "LTC/USDT", "BCH/USDT", "TRX/USDT", "ARB/USDT", "OP/USDT", "STX/USDT",
  // Gaming & Cross Pairs
  "GALA/USDT", "SAND/USDT", "ETH/BTC", "SOL/BTC", "BNB/BTC", "SOL/ETH",
] as const;
const TIMEFRAMES = ["5m", "15m", "1h", "4h"] as const;

export function AnalyticsSignalsPanel({ snapshot }: AnalyticsSignalsPanelProps) {
  const [symbol, setSymbol] = useState<string>("BTC/USDT");
  const [timeframe, setTimeframe] = useState<string>("15m");
  const [analysis, setAnalysis] = useState<MarketAnalysisOutput | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  async function handleRunAnalysis(): Promise<void> {
    setAnalysisLoading(true);
    setAnalysisError(null);
    try {
      const symbolSignals =
        snapshot?.latest_signals.filter((s) => s.symbol === symbol) ?? [];
      const output = await fetchCandleAnalysis({
        symbol,
        timeframe,
        lookback_bars: 120,
        strategy_signals: symbolSignals,
      });
      setAnalysis(output);
    } catch (err) {
      setAnalysisError(
        err instanceof Error
          ? err.message
          : "Market analysis unavailable for current candle store.",
      );
    } finally {
      setAnalysisLoading(false);
    }
  }

  const signals = snapshot?.latest_signals ?? [];

  return (
    <aside className="nexus-panel flex flex-col gap-4 rounded-lg p-4">
      {/* Deterministic Strategy Signals Section */}
      <div>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cpu className="h-4 w-4 text-cyan-400" />
            <h2 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
              Strategy V1 Signals
            </h2>
          </div>
          <span className="rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 font-mono text-[10px] text-cyan-300">
            DETERMINISTIC
          </span>
        </div>
        <p className="mt-1 text-[11px] text-slate-400">
          Closed-candle EMA20/EMA50 + RSI14 + ATR14 + Volume SMA20 evaluations.
        </p>

        <div className="mt-3 space-y-2">
          {signals.length === 0 ? (
            <div className="rounded border border-slate-800 bg-nexus-void/70 p-3 font-mono text-xs text-slate-400">
              No closed-candle signals emitted yet. Strategy waits for ≥52 closed bars per symbol.
            </div>
          ) : (
            signals.map((sig) => (
              <div
                key={`${sig.symbol}-${sig.timestamp}`}
                className="rounded border border-cyan-500/20 bg-nexus-void/80 p-2.5"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-semibold text-white">
                      {sig.symbol}
                    </span>
                    <span
                      className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold uppercase ${
                        sig.direction === "long"
                          ? "bg-emerald-500/20 text-emerald-300"
                          : sig.direction === "exit_long"
                            ? "bg-amber-500/20 text-amber-300"
                            : "bg-slate-800 text-slate-400"
                      }`}
                    >
                      {sig.direction}
                    </span>
                  </div>
                  <span className="font-mono text-[11px] tabular-nums text-cyan-300">
                    {formatUsdt(sig.entry_price)}
                  </span>
                </div>

                <p className="mt-1 text-[11px] leading-snug text-slate-300">
                  {sig.reason}
                </p>

                <div className="mt-1.5 flex items-center justify-between font-mono text-[10px] text-slate-500">
                  <span>STOP: {formatUsdt(sig.stop_price)}</span>
                  <span>{formatUtcTime(sig.timestamp)}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Advisory AI Market Analysis Section */}
      <div className="border-t border-cyan-500/15 pt-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-gold-400" />
            <h2 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
              AI Regime Analytics
            </h2>
          </div>
          <span className="rounded border border-gold-400/40 bg-gold-500/10 px-2 py-0.5 font-mono text-[10px] text-gold-300">
            ADVISORY ONLY
          </span>
        </div>
        <p className="mt-1 text-[11px] text-slate-400">
          AI never places orders, bypasses risk limits, or guarantees profitability.
        </p>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <NexusSelect
            value={symbol}
            onChange={setSymbol}
            options={[...SYMBOLS]}
            ariaLabel="Analysis Symbol"
          />

          <NexusSelect
            value={timeframe}
            onChange={setTimeframe}
            options={[...TIMEFRAMES]}
            ariaLabel="Analysis Timeframe"
          />

          <button
            type="button"
            disabled={analysisLoading}
            onClick={() => void handleRunAnalysis()}
            className="ml-auto inline-flex items-center gap-1.5 rounded border border-cyan-400/50 bg-cyan-500/15 px-3 py-1 font-mono text-xs font-medium text-cyan-200 transition hover:bg-cyan-500/25 disabled:opacity-50"
          >
            <Sparkles className="h-3.5 w-3.5" />
            {analysisLoading ? "ANALYZING..." : "ANALYZE"}
          </button>
        </div>

        {analysisError && (
          <div className="mt-3 flex items-start gap-2 rounded border border-amber-500/40 bg-amber-500/10 p-2.5 text-xs text-amber-200">
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{analysisError}</span>
          </div>
        )}

        {analysis && (
          <div className="mt-3 space-y-2.5 rounded border border-cyan-500/20 bg-nexus-void/85 p-3">
            <div className="grid grid-cols-3 gap-2 font-mono text-[11px]">
              <div>
                <span className="block text-[10px] text-slate-500">REGIME</span>
                <span className="font-semibold uppercase text-cyan-300">
                  {analysis.market_regime}
                </span>
              </div>
              <div>
                <span className="block text-[10px] text-slate-500">TREND</span>
                <span className="font-semibold uppercase text-white">
                  {analysis.trend_direction}
                </span>
              </div>
              <div>
                <span className="block text-[10px] text-slate-500">VOLATILITY</span>
                <span className="font-semibold uppercase text-gold-300">
                  {analysis.volatility_level}
                </span>
              </div>
            </div>

            <p className="text-xs leading-relaxed text-slate-300">
              {analysis.explanation}
            </p>

            {analysis.risk_observations.length > 0 && (
              <ul className="space-y-1 border-t border-slate-800 pt-2 text-[11px] text-amber-200/90">
                {analysis.risk_observations.map((obs, idx) => (
                  <li key={`${idx}-${obs.slice(0, 20)}`}>• {obs}</li>
                ))}
              </ul>
            )}

            <div className="flex items-center justify-between font-mono text-[10px] text-slate-500">
              <span>EXECUTABLE: FALSE</span>
              <span>{formatUtcTime(analysis.timestamp)}</span>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
}

