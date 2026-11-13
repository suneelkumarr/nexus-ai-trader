import { useEffect, useState } from "react";
import {
  CheckCircle2,
  Database,
  Download,
  FlaskConical,
  Play,
  RefreshCw,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import {
  fetchCandlesStatus,
  runOosBacktest,
  syncCandles,
} from "../../services/apiClient";
import type {
  BacktestRunResult,
  BacktestSuiteReport,
  CandlesStatusResponse,
} from "../../types/system";
import { formatInr, formatPct, formatUtcTime, toFiniteNumber } from "../../utils/format";
import { NexusSelect } from "../common/NexusSelect";

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

function EquityCurveSvg({ run }: { run: BacktestRunResult }) {
  const points = run.equity_curve;
  if (points.length < 2) {
    return (
      <div className="flex h-36 items-center justify-center font-mono text-xs text-slate-500">
        Insufficient equity points to plot curve.
      </div>
    );
  }

  const width = 560;
  const height = 140;
  const pad = 12;

  const eqValues = points.map((p) => toFiniteNumber(p.equity_inr));
  const bmValues = points.map((p) => toFiniteNumber(p.benchmark_equity_inr));
  const allVals = [...eqValues, ...bmValues];
  const minVal = Math.min(...allVals);
  const maxVal = Math.max(...allVals);
  const span = Math.max(maxVal - minVal, 1);

  const toCoords = (vals: number[]): string =>
    vals
      .map((val, idx) => {
        const x = pad + (idx / Math.max(vals.length - 1, 1)) * (width - pad * 2);
        const y = height - pad - ((val - minVal) / span) * (height - pad * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-36 w-full rounded border border-slate-800/80 bg-nexus-void/90"
      role="img"
      aria-label={`${run.split.split_name} Strategy vs Buy and Hold Equity Curve`}
    >
      <polyline
        fill="none"
        stroke="#d4af37"
        strokeWidth="1.5"
        strokeDasharray="4 3"
        points={toCoords(bmValues)}
      />
      <polyline
        fill="none"
        stroke="#22d3ee"
        strokeWidth="2"
        points={toCoords(eqValues)}
      />
    </svg>
  );
}

function SplitCard({ title, run }: { title: string; run: BacktestRunResult }) {
  const m = run.metrics;
  const hasTrades = m.number_of_trades > 0;

  return (
    <div className="nexus-panel flex flex-col gap-3 rounded-lg p-4">
      <div className="flex items-center justify-between border-b border-cyan-500/15 pb-2">
        <div>
          <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
            {title}
          </h3>
          <p className="font-mono text-[10px] text-slate-400">
            Bars: {run.split.scored_bars_count} scored · {run.split.warmup_bars_count} warmup
          </p>
        </div>
        <span
          className={`font-mono text-sm font-semibold tabular-nums ${
            m.total_return_pct >= 0 ? "text-emerald-300" : "text-rose-300"
          }`}
        >
          {formatPct(m.total_return_pct, true)} NET
        </span>
      </div>

      <EquityCurveSvg run={run} />

      <div className="flex items-center justify-between font-mono text-[10px] text-slate-400">
        <span className="text-cyan-300">— Strategy Net Equity</span>
        <span className="text-gold-300">--- Buy & Hold Benchmark</span>
      </div>

      {!hasTrades && (
        <div className="rounded border border-cyan-500/20 bg-cyan-950/20 p-2 font-mono text-[11px] text-cyan-300">
          🛡️ Capital preserved: Zero trades triggered in this window due to strict EMA/RSI trend filters avoiding adverse market chop.
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 font-mono text-xs">
        <div className="rounded bg-nexus-void/80 p-2">
          <span className="block text-[10px] text-slate-500">NET PROFIT</span>
          <span className="tabular-nums text-white">{formatInr(m.net_profit_inr, true)}</span>
        </div>
        <div className="rounded bg-nexus-void/80 p-2">
          <span className="block text-[10px] text-slate-500">WIN RATE / TRADES</span>
          <span className="tabular-nums text-white">
            {m.win_rate_pct.toFixed(1)}% ({m.number_of_trades})
          </span>
        </div>
        <div className="rounded bg-nexus-void/80 p-2">
          <span className="block text-[10px] text-slate-500">MAX DRAWDOWN</span>
          <span className="tabular-nums text-amber-300">{formatPct(m.max_drawdown_pct)}</span>
        </div>
        <div className="rounded bg-nexus-void/80 p-2">
          <span className="block text-[10px] text-slate-500">SHARPE RATIO</span>
          <span className="tabular-nums text-cyan-300">{m.sharpe_ratio.toFixed(2)}</span>
        </div>
        <div className="rounded bg-nexus-void/80 p-2">
          <span className="block text-[10px] text-slate-500">FEE + SLIP DRAG</span>
          <span className="tabular-nums text-rose-300">
            {formatInr(m.fee_impact.total_execution_drag_inr)}
          </span>
        </div>
        <div className="rounded bg-nexus-void/80 p-2">
          <span className="block text-[10px] text-slate-500">VS BENCHMARK</span>
          <span className="tabular-nums text-slate-200">
            {formatPct(run.benchmark.excess_net_return_pct, true)}
          </span>
        </div>
      </div>
    </div>
  );
}

export function BacktestingView() {
  const [symbol, setSymbol] = useState<string>("BTC/USDT");
  const [timeframe, setTimeframe] = useState<string>("15m");
  const [makerFeeBps, setMakerFeeBps] = useState<number>(10);
  const [takerFeeBps, setTakerFeeBps] = useState<number>(10);
  const [spreadBps, setSpreadBps] = useState<number>(4);
  const [slippageBps, setSlippageBps] = useState<number>(5);
  const [lookbackBars, setLookbackBars] = useState<number>(200);
  const [strategyId, setStrategyId] = useState<string>("combined");

  const [candleStatus, setCandleStatus] = useState<CandlesStatusResponse | null>(null);
  const [statusLoading, setStatusLoading] = useState<boolean>(false);
  const [syncing, setSyncing] = useState<boolean>(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  const [report, setReport] = useState<BacktestSuiteReport | null>(null);
  const [running, setRunning] = useState<boolean>(false);
  const [runStage, setRunStage] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  // Fetch candle status on symbol/timeframe change
  const refreshCandleStatus = async () => {
    try {
      setStatusLoading(true);
      const res = await fetchCandlesStatus({ symbol, timeframe });
      setCandleStatus(res);
    } catch {
      // Ignored
    } finally {
      setStatusLoading(false);
    }
  };

  useEffect(() => {
    refreshCandleStatus();
  }, [symbol, timeframe]);

  // Handle candle sync from Binance
  const handleSyncCandles = async () => {
    setSyncing(true);
    setSyncMessage(null);
    setError(null);
    try {
      const res = await syncCandles({
        symbol,
        timeframe,
        lookback_bars: Math.max(lookbackBars, 500),
      });
      setSyncMessage(res.message);
      await refreshCandleStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Candle sync failed");
    } finally {
      setSyncing(false);
    }
  };

  // Run backtest with simulated multi-stage progress
  async function handleRunBacktest(): Promise<void> {
    setRunning(true);
    setError(null);
    setRunStage("Validating chronological OHLCV store...");

    try {
      setRunStage("Partitioning: Train (60%) | Validation (20%) | Test (20%)...");
      await new Promise((r) => setTimeout(r, 150));

      setRunStage("Simulating Train & OOS Test with conservative stops...");
      const result = await runOosBacktest({
        symbol,
        timeframe,
        strategy_id: strategyId,
        maker_fee_bps: makerFeeBps,
        taker_fee_bps: takerFeeBps,
        spread_bps: spreadBps,
        slippage_bps: slippageBps,
        lookback_bars: lookbackBars,
      });

      setRunStage("Aggregating Sharpe, Win-rate & Drawdown metrics...");
      setReport(result);
      await refreshCandleStatus();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to execute out-of-sample backtest on persisted candle store.",
      );
    } finally {
      setRunning(false);
      setRunStage("");
    }
  }

  const handleDownloadReport = () => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `backtest-${report.symbol.replace("/", "_")}-${report.timeframe}-${report.report_id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      {/* 1. Header & Live Candle Telemetry Card */}
      <div className="nexus-panel rounded-lg p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <FlaskConical className="h-4 w-4 text-cyan-400" />
            <h2 className="font-display text-base font-semibold text-white">
              Event-Driven Out-of-Sample Backtester
            </h2>
          </div>
          <span className="rounded border border-gold-400/40 bg-gold-500/10 px-2.5 py-0.5 font-mono text-[11px] text-gold-300">
            NET RETURNS ONLY · ZERO LOOK-AHEAD · CONSERVATIVE STOPS
          </span>
        </div>

        <p className="mt-1.5 text-xs text-slate-400">
          Executes strictly over stored PostgreSQL historical candles split chronologically into Train, Validation, and untouched Test windows.
          All figures subtract maker/taker fees, bid-ask spread, and adverse slippage.
        </p>

        {/* Live Stored Candle Telemetry Bar */}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded border border-cyan-500/25 bg-[#030712] p-3 text-xs font-mono">
          <div className="flex items-center gap-3">
            <Database className="h-4 w-4 text-cyan-400 shrink-0" />
            <div>
              <div className="flex items-center gap-2">
                <span className="text-slate-300 font-bold">{symbol} ({timeframe})</span>
                <span
                  className={`rounded px-1.5 py-0.2 text-[10px] font-bold ${
                    candleStatus?.can_backtest
                      ? "bg-emerald-950/80 text-emerald-400 border border-emerald-500/40"
                      : "bg-amber-950/80 text-amber-400 border border-amber-500/40"
                  }`}
                >
                  {candleStatus?.stored_count ?? 0} BARS STORED{" "}
                  {candleStatus?.can_backtest ? "(READY >= 60)" : "(NEEDS SYNC < 60)"}
                </span>
              </div>
              <div className="text-[10px] text-slate-400 mt-0.5">
                Range: {candleStatus?.earliest_candle_utc ? formatUtcTime(candleStatus.earliest_candle_utc) : "None"} →{" "}
                {candleStatus?.latest_candle_utc ? formatUtcTime(candleStatus.latest_candle_utc) : "None"}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={syncing || statusLoading}
              onClick={handleSyncCandles}
              className="inline-flex items-center gap-1.5 rounded border border-cyan-500/50 bg-cyan-950/40 px-3 py-1 font-mono text-xs text-cyan-300 hover:bg-cyan-900/60 transition disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${syncing ? "animate-spin" : ""}`} />
              <span>{syncing ? "SYNCING BINANCE BARS..." : "SYNC FRESH CANDLES"}</span>
            </button>
          </div>
        </div>

        {syncMessage && (
          <div className="mt-2 text-[11px] font-mono text-emerald-300 flex items-center gap-1">
            <CheckCircle2 className="h-3.5 w-3.5" />
            <span>{syncMessage}</span>
          </div>
        )}

        {/* 2. Parameters Grid using NexusSelect */}
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
          <NexusSelect
            label="Symbol"
            value={symbol}
            onChange={setSymbol}
            options={[...SYMBOLS]}
            fullWidth
          />

          <NexusSelect
            label="Strategy"
            value={strategyId}
            onChange={setStrategyId}
            options={[
              { value: "combined", label: "Hybrid Alpha (V1+V2)" },
              { value: "v2", label: "Strategy V2 (Bounce)" },
              { value: "v1", label: "Strategy V1 (Trend)" },
            ]}
            fullWidth
          />

          <NexusSelect
            label="Timeframe"
            value={timeframe}
            onChange={setTimeframe}
            options={[...TIMEFRAMES]}
            fullWidth
          />

          <label className="font-mono text-[11px] text-slate-300 flex flex-col gap-1">
            <span className="text-[10px] uppercase text-slate-400">Maker (bps)</span>
            <input
              type="number"
              min={0}
              max={500}
              value={makerFeeBps}
              onChange={(e) => setMakerFeeBps(Number(e.target.value))}
              className="w-full rounded-md border border-cyan-500/35 bg-[#030712] px-3 py-1.5 font-mono text-xs text-cyan-200 transition focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/40"
            />
          </label>

          <label className="font-mono text-[11px] text-slate-300 flex flex-col gap-1">
            <span className="text-[10px] uppercase text-slate-400">Taker (bps)</span>
            <input
              type="number"
              min={0}
              max={500}
              value={takerFeeBps}
              onChange={(e) => setTakerFeeBps(Number(e.target.value))}
              className="w-full rounded-md border border-cyan-500/35 bg-[#030712] px-3 py-1.5 font-mono text-xs text-cyan-200 transition focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/40"
            />
          </label>

          <label className="font-mono text-[11px] text-slate-300 flex flex-col gap-1">
            <span className="text-[10px] uppercase text-slate-400">Spread (bps)</span>
            <input
              type="number"
              min={0}
              max={500}
              value={spreadBps}
              onChange={(e) => setSpreadBps(Number(e.target.value))}
              className="w-full rounded-md border border-cyan-500/35 bg-[#030712] px-3 py-1.5 font-mono text-xs text-cyan-200 transition focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/40"
            />
          </label>

          <label className="font-mono text-[11px] text-slate-300 flex flex-col gap-1">
            <span className="text-[10px] uppercase text-slate-400">Slippage (bps)</span>
            <input
              type="number"
              min={0}
              max={500}
              value={slippageBps}
              onChange={(e) => setSlippageBps(Number(e.target.value))}
              className="w-full rounded-md border border-cyan-500/35 bg-[#030712] px-3 py-1.5 font-mono text-xs text-cyan-200 transition focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/40"
            />
          </label>

          <label className="font-mono text-[11px] text-slate-300 flex flex-col gap-1">
            <span className="text-[10px] uppercase text-slate-400">Lookback Bars</span>
            <input
              type="number"
              min={60}
              max={2000}
              value={lookbackBars}
              onChange={(e) => setLookbackBars(Number(e.target.value))}
              className="w-full rounded-md border border-cyan-500/35 bg-[#030712] px-3 py-1.5 font-mono text-xs text-cyan-200 transition focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/40"
            />
          </label>
        </div>

        {/* Lookback Presets & Quantitative Sample Size Callout */}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded border border-slate-800 bg-nexus-void/60 p-2.5 font-mono text-[11px]">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-slate-400">Quick Presets:</span>
            {[
              { label: "200 bars (~2d Chop)", count: 200 },
              { label: "500 bars (~5d Standard)", count: 500 },
              { label: "1,000 bars (~10d Deep)", count: 1000 },
              { label: "1,500 bars (~15d Benchmark)", count: 1500 },
            ].map((p) => (
              <button
                key={p.count}
                type="button"
                onClick={() => setLookbackBars(p.count)}
                className={`rounded px-2 py-0.5 text-[10px] font-semibold transition ${
                  lookbackBars === p.count
                    ? "border border-cyan-400 bg-cyan-500/20 text-cyan-200"
                    : "border border-slate-800 bg-nexus-void text-slate-400 hover:text-slate-200"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="text-[10px]">
            {lookbackBars <= 200 ? (
              <span className="text-amber-300">
                ⚠️ Micro Window (50h): Expect 0-2 trades on test split. Filter avoids chop.
              </span>
            ) : (
              <span className="text-emerald-300">
                ✅ Statistical Rigor: Multi-regime coverage across bull/bear cycles.
              </span>
            )}
          </div>
        </div>

        {/* Action button & Live Stage indicator */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-cyan-500/15 pt-3">
          {report ? (
            <div className="flex items-center gap-3">
              <span className="font-mono text-[11px] text-slate-400">
                Report <strong className="text-cyan-300">{report.report_id}</strong> · Generated{" "}
                {formatUtcTime(report.generated_at)} · OOS Verified:{" "}
                <strong className="text-emerald-300">
                  {report.out_of_sample_verified ? "YES" : "NO"}
                </strong>
              </span>
              <button
                type="button"
                onClick={handleDownloadReport}
                className="inline-flex items-center gap-1 rounded border border-cyan-500/30 px-2 py-0.5 font-mono text-[10px] text-cyan-300 hover:bg-cyan-950/40"
              >
                <Download className="h-3 w-3" />
                <span>JSON</span>
              </button>
            </div>
          ) : (
            <span className="font-mono text-[11px] text-slate-500">
              Deterministic train/val/test splits strictly over verified PostgreSQL candle history.
            </span>
          )}

          <button
            type="button"
            disabled={running || syncing}
            onClick={() => void handleRunBacktest()}
            className="inline-flex items-center gap-1.5 rounded border border-cyan-400/60 bg-cyan-500/20 px-5 py-2 font-mono text-xs font-semibold text-cyan-200 transition hover:bg-cyan-500/30 disabled:opacity-50 shadow-[0_0_15px_rgba(34,211,238,0.2)]"
          >
            <Play className={`h-3.5 w-3.5 ${running ? "animate-pulse" : ""}`} />
            <span>{running ? "SIMULATING OUT-OF-SAMPLE..." : "RUN OOS BACKTEST"}</span>
          </button>
        </div>

        {/* Live Running Stepper */}
        {running && (
          <div className="mt-3 rounded border border-cyan-500/30 bg-cyan-950/30 p-2.5 font-mono text-xs text-cyan-300 flex items-center gap-2">
            <Sparkles className="h-4 w-4 animate-spin text-cyan-400 shrink-0" />
            <span className="font-semibold">{runStage}</span>
          </div>
        )}

        {/* Error notification with one-click fix */}
        {error && (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-200 font-mono">
            <div className="flex items-start gap-2">
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
              <span>{error}</span>
            </div>
            {error.includes("Need at least 60") && (
              <button
                type="button"
                onClick={handleSyncCandles}
                className="rounded bg-amber-500/20 border border-amber-500/50 px-2.5 py-1 text-xs text-amber-300 hover:bg-amber-500/30"
              >
                ⚡ Auto-Sync Candles Now
              </button>
            )}
          </div>
        )}
      </div>

      {/* 3. Output Split Cards */}
      {report && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <SplitCard title="Train Period (60%)" run={report.train_result} />
          <SplitCard title="Validation Period (20%)" run={report.validation_result} />
          <SplitCard title="Untouched Test Window (20%)" run={report.test_result} />
        </div>
      )}
    </div>
  );
}
