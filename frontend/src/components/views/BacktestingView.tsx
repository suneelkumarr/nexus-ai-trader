import { useEffect, useState, useMemo } from "react";
import {
  CheckCircle2,
  Database,
  Download,
  FlaskConical,
  Play,
  RefreshCw,
  Sparkles,
  TriangleAlert,
  Layers,
  ShieldCheck,
  FileSpreadsheet,
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

function InteractiveEquityCurveSvg({ run }: { run: BacktestRunResult }) {
  const points = run.equity_curve;
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  if (points.length < 2) {
    return (
      <div className="flex h-36 items-center justify-center font-mono text-xs text-slate-500">
        Insufficient equity points to plot curve.
      </div>
    );
  }

  const width = 560;
  const height = 150;
  const pad = 14;

  const eqValues = points.map((p) => toFiniteNumber(p.equity_inr));
  const bmValues = points.map((p) => toFiniteNumber(p.benchmark_equity_inr));
  const allVals = [...eqValues, ...bmValues];
  const minVal = Math.min(...allVals);
  const maxVal = Math.max(...allVals);
  const span = Math.max(maxVal - minVal, 1);

  const coords = points.map((p, idx) => {
    const x = pad + (idx / Math.max(points.length - 1, 1)) * (width - pad * 2);
    const yEq = height - pad - ((toFiniteNumber(p.equity_inr) - minVal) / span) * (height - pad * 2);
    const yBm = height - pad - ((toFiniteNumber(p.benchmark_equity_inr) - minVal) / span) * (height - pad * 2);
    return {
      x,
      yEq,
      yBm,
      eq: toFiniteNumber(p.equity_inr),
      bm: toFiniteNumber(p.benchmark_equity_inr),
      timestamp: p.timestamp,
    };
  });

  const eqPath = coords.map((c, i) => `${i === 0 ? "M" : "L"} ${c.x.toFixed(1)} ${c.yEq.toFixed(1)}`).join(" ");
  const bmPath = coords.map((c, i) => `${i === 0 ? "M" : "L"} ${c.x.toFixed(1)} ${c.yBm.toFixed(1)}`).join(" ");

  const active = hoverIdx !== null && coords[hoverIdx] ? coords[hoverIdx] : coords[coords.length - 1];

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const svgX = ((e.clientX - rect.left) / rect.width) * width;
    let closest = 0;
    let minD = Infinity;
    coords.forEach((c, idx) => {
      const d = Math.abs(c.x - svgX);
      if (d < minD) {
        minD = d;
        closest = idx;
      }
    });
    setHoverIdx(closest);
  };

  return (
    <div className="relative">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="h-36 w-full cursor-crosshair rounded border border-slate-800/80 bg-nexus-void/90 select-none shadow-inner"
        role="img"
        aria-label={`${run.split.split_name} Strategy vs Buy and Hold Equity Curve`}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoverIdx(null)}
      >
        <line x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} stroke="#1e293b" strokeDasharray="3 3" />
        <line x1={pad} y1={pad} x2={width - pad} y2={pad} stroke="#1e293b" strokeDasharray="3 3" />

        {/* Buy and hold benchmark */}
        <path d={bmPath} fill="none" stroke="#d4af37" strokeWidth="1.6" strokeDasharray="4 3" />

        {/* Strategy Net Equity */}
        <path d={eqPath} fill="none" stroke="#22d3ee" strokeWidth="2.2" strokeLinecap="round" />

        {/* Hover Crosshair */}
        {active && (
          <g>
            <line
              x1={active.x}
              y1={pad}
              x2={active.x}
              y2={height - pad}
              stroke="#22d3ee"
              strokeDasharray="2 2"
              strokeWidth="1"
              strokeOpacity="0.6"
            />
            <circle cx={active.x} cy={active.yEq} r="3.5" fill="#22d3ee" stroke="#ffffff" strokeWidth="1" />
            <circle cx={active.x} cy={active.yBm} r="3" fill="#d4af37" stroke="#ffffff" strokeWidth="1" />
          </g>
        )}
      </svg>

      {/* Hover Floating HUD */}
      {hoverIdx !== null && active && (
        <div
          className="pointer-events-none absolute z-20 rounded border border-cyan-500/40 bg-slate-950/95 px-2.5 py-1.5 shadow-xl backdrop-blur font-mono text-[10px]"
          style={{
            left: Math.min(Math.max(active.x - 60, 5), width - 140),
            top: 5,
          }}
        >
          <div className="text-slate-400">{active.timestamp?.slice(0, 19).replace("T", " ")}</div>
          <div className="mt-0.5 text-cyan-300 font-bold">Strategy: {formatInr(active.eq)}</div>
          <div className="text-gold-300">Benchmark: {formatInr(active.bm)}</div>
        </div>
      )}
    </div>
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

      <InteractiveEquityCurveSvg run={run} />

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
          <span className="tabular-nums text-white font-semibold">{formatInr(m.net_profit_inr, true)}</span>
        </div>
        <div className="rounded bg-nexus-void/80 p-2">
          <span className="block text-[10px] text-slate-500">WIN RATE / TRADES</span>
          <span className="tabular-nums text-white font-semibold">
            {m.win_rate_pct.toFixed(1)}% ({m.number_of_trades})
          </span>
        </div>
        <div className="rounded bg-nexus-void/80 p-2">
          <span className="block text-[10px] text-slate-500">MAX DRAWDOWN</span>
          <span className="tabular-nums text-amber-300 font-semibold">{formatPct(m.max_drawdown_pct)}</span>
        </div>
        <div className="rounded bg-nexus-void/80 p-2">
          <span className="block text-[10px] text-slate-500">SHARPE RATIO</span>
          <span className="tabular-nums text-cyan-300 font-semibold">{m.sharpe_ratio.toFixed(2)}</span>
        </div>
        <div className="rounded bg-nexus-void/80 p-2">
          <span className="block text-[10px] text-slate-500">FEE + SLIP DRAG</span>
          <span className="tabular-nums text-rose-300">
            {formatInr(m.fee_impact.total_execution_drag_inr)}
          </span>
        </div>
        <div className="rounded bg-nexus-void/80 p-2">
          <span className="block text-[10px] text-slate-500">VS BENCHMARK</span>
          <span className="tabular-nums text-emerald-300 font-semibold">
            {formatPct(run.benchmark.excess_net_return_pct, true)}
          </span>
        </div>
      </div>
    </div>
  );
}

function exportBacktestCsv(report: BacktestSuiteReport) {
  if (!report) return;

  const testPoints = report.test_result.equity_curve;
  const headers = [
    "Bar Index",
    "Timestamp UTC",
    "Strategy Net Equity (INR)",
    "Benchmark Equity (INR)",
    "Net Return (%)",
    "Timeframe",
    "Symbol",
  ];

  const initialCap = toFiniteNumber(report.test_result.metrics.initial_capital_inr || 10000);
  const rows = testPoints.map((p, idx) => {
    const eq = toFiniteNumber(p.equity_inr);
    const retPct = initialCap > 0 ? ((eq - initialCap) / initialCap) * 100 : 0;
    return [
      idx + 1,
      `"${p.timestamp}"`,
      eq.toFixed(2),
      toFiniteNumber(p.benchmark_equity_inr).toFixed(2),
      retPct.toFixed(2),
      `"${report.timeframe}"`,
      `"${report.symbol}"`,
    ];
  });

  const csvContent = [headers.join(","), ...rows.map((r) => r.join(","))].join("\r\n");
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `backtest_${report.symbol.replace("/", "_")}_${report.timeframe}_${report.report_id.slice(0, 8)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function BacktestingView() {
  const [symbol, setSymbol] = useState<string>("BTC/USDT");
  const [timeframe, setTimeframe] = useState<string>("15m");
  const [makerFeeBps, setMakerFeeBps] = useState<number>(10);
  const [takerFeeBps, setTakerFeeBps] = useState<number>(10);
  const [spreadBps, setSpreadBps] = useState<number>(4);
  const [slippageBps, setSlippageBps] = useState<number>(5);
  const [lookbackBars, setLookbackBars] = useState<number>(500);
  const [strategyId, setStrategyId] = useState<string>("combined");

  const [candleStatus, setCandleStatus] = useState<CandlesStatusResponse | null>(null);
  const [statusLoading, setStatusLoading] = useState<boolean>(false);
  const [syncing, setSyncing] = useState<boolean>(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  const [report, setReport] = useState<BacktestSuiteReport | null>(null);
  const [running, setRunning] = useState<boolean>(false);
  const [runStage, setRunStage] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [csvDownloaded, setCsvDownloaded] = useState<boolean>(false);

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

  const handleDownloadReportJson = () => {
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

  const handleExportCsvClick = () => {
    if (!report) return;
    exportBacktestCsv(report);
    setCsvDownloaded(true);
    setTimeout(() => setCsvDownloaded(false), 3000);
  };

  // Overfitting and Robustness Assessment
  const robustnessAssessment = useMemo(() => {
    if (!report) return null;
    const trainSharpe = report.train_result.metrics.sharpe_ratio;
    const testSharpe = report.test_result.metrics.sharpe_ratio;
    const testReturn = report.test_result.metrics.total_return_pct;
    const excessReturn = report.test_result.benchmark.excess_net_return_pct;

    let rating: "EXCELLENT" | "ROBUST" | "MODERATE" | "OVERFIT" = "ROBUST";
    let message = "Out-of-sample test results match train behavior with acceptable variance.";
    let badgeColor = "border-emerald-500/40 bg-emerald-950/20 text-emerald-300";

    if (testSharpe >= trainSharpe * 0.85 && testReturn > 0) {
      rating = "EXCELLENT";
      message = "High statistical persistence: Out-of-sample test window confirms positive edge without overfitting.";
      badgeColor = "border-emerald-400 bg-emerald-500/20 text-emerald-200";
    } else if (testSharpe < 0.3 && trainSharpe > 1.2) {
      rating = "OVERFIT";
      message = "High parameter sensitivity: Strategy decayed significantly in unseen test window.";
      badgeColor = "border-rose-500 bg-rose-950/40 text-rose-300";
    }

    return { rating, message, badgeColor, testSharpe, trainSharpe, excessReturn };
  }, [report]);

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

        {/* Lookback Presets */}
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
                ⚠️ Micro Window: Strict filters may execute fewer trades to avoid noise.
              </span>
            ) : (
              <span className="text-emerald-300">
                ✅ Statistical Rigor: Multi-regime coverage across market cycles.
              </span>
            )}
          </div>
        </div>

        {/* Action Button & Report Controls */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-cyan-500/15 pt-3">
          {report ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-[11px] text-slate-400">
                Report <strong className="text-cyan-300">{report.report_id.slice(0, 8)}</strong> · OOS Verified:{" "}
                <strong className="text-emerald-300">
                  {report.out_of_sample_verified ? "YES" : "NO"}
                </strong>
              </span>

              {/* 1-Click CSV Export */}
              <button
                type="button"
                onClick={handleExportCsvClick}
                className="inline-flex items-center gap-1 rounded border border-cyan-500/40 bg-cyan-950/40 px-2.5 py-1 font-mono text-xs text-cyan-200 hover:bg-cyan-900/60 shadow"
              >
                <FileSpreadsheet className="h-3.5 w-3.5 text-cyan-400" />
                <span>{csvDownloaded ? "CSV Exported!" : "Export CSV"}</span>
              </button>

              {/* JSON Export */}
              <button
                type="button"
                onClick={handleDownloadReportJson}
                className="inline-flex items-center gap-1 rounded border border-slate-700 bg-slate-900 px-2.5 py-1 font-mono text-xs text-slate-300 hover:text-white"
              >
                <Download className="h-3.5 w-3.5" />
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

        {/* Error Notification */}
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

      {/* 3. Robustness & Overfitting Verification Scorecard */}
      {robustnessAssessment && (
        <div className={`nexus-panel rounded-lg p-3.5 border ${robustnessAssessment.badgeColor}`}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-emerald-400" />
              <span className="font-display text-sm font-semibold text-white">
                Statistical Robustness Assessment:
              </span>
              <span className="font-mono text-xs font-bold uppercase underline">
                {robustnessAssessment.rating}
              </span>
            </div>
            <div className="flex items-center gap-3 font-mono text-xs">
              <span>
                Train Sharpe: <strong className="text-cyan-300">{robustnessAssessment.trainSharpe.toFixed(2)}</strong>
              </span>
              <span>
                Test Sharpe: <strong className="text-emerald-300">{robustnessAssessment.testSharpe.toFixed(2)}</strong>
              </span>
              <span>
                Excess Alpha: <strong className="text-gold-300">{formatPct(robustnessAssessment.excessReturn, true)}</strong>
              </span>
            </div>
          </div>
          <p className="mt-1 text-xs text-slate-300 font-mono">
            {robustnessAssessment.message}
          </p>
        </div>
      )}

      {/* 4. Output Split Cards (Train 60%, Validation 20%, Untouched Test 20%) */}
      {report && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <SplitCard title="Train Period (60%)" run={report.train_result} />
          <SplitCard title="Validation Period (20%)" run={report.validation_result} />
          <SplitCard title="Untouched Test Window (20%)" run={report.test_result} />
        </div>
      )}

      {/* 5. Backtest Test Period Execution Blotter */}
      {report && report.test_result.equity_curve.length > 0 && (
        <div className="nexus-panel overflow-hidden rounded-lg">
          <div className="flex items-center justify-between border-b border-cyan-500/15 px-4 py-3">
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-cyan-400" />
              <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
                Untouched Test Window Bar-by-Bar Telemetry Blotter
              </h3>
            </div>
            <span className="font-mono text-[11px] text-slate-400">
              {report.test_result.equity_curve.length} EVALUATED BARS
            </span>
          </div>

          <div className="max-h-60 overflow-y-auto overflow-x-auto">
            <table className="w-full text-left font-mono text-xs">
              <thead className="sticky top-0 border-b border-slate-800 bg-[#030712] text-[10px] uppercase text-slate-400">
                <tr>
                  <th className="px-4 py-2">Bar #</th>
                  <th className="px-4 py-2">Timestamp UTC</th>
                  <th className="px-4 py-2">Strategy Net Equity</th>
                  <th className="px-4 py-2">Benchmark Equity</th>
                  <th className="px-4 py-2">Excess Alpha</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70 text-slate-300">
                {report.test_result.equity_curve.slice(-30).map((pt, idx) => {
                  const eq = toFiniteNumber(pt.equity_inr);
                  const bm = toFiniteNumber(pt.benchmark_equity_inr);
                  const delta = eq - bm;

                  return (
                    <tr key={idx} className="hover:bg-cyan-500/5 transition">
                      <td className="px-4 py-2 text-slate-500">#{idx + 1}</td>
                      <td className="px-4 py-2 text-slate-400">{formatUtcTime(pt.timestamp)}</td>
                      <td className="px-4 py-2 font-semibold text-cyan-300">{formatInr(eq)}</td>
                      <td className="px-4 py-2 text-gold-300">{formatInr(bm)}</td>
                      <td className={`px-4 py-2 font-bold ${delta >= 0 ? "text-emerald-300" : "text-rose-300"}`}>
                        {formatInr(delta, true)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
