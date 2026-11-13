import { useState, useMemo } from "react";
import type { TerminalSnapshotResponse, TradeLedgerEntry } from "../../types/system";
import {
  formatInr,
  formatPct,
  formatQty,
  formatUsdt,
  formatUtcTime,
  toFiniteNumber,
} from "../../utils/format";
import {
  TrendingUp,
  TrendingDown,
  Award,
  Activity,
  ShieldCheck,
  Download,
  Search,
  Filter,
  DollarSign,
  Percent,
  Layers,
  ArrowUpDown,
  CheckCircle2,
  Clock,
  RotateCcw,
} from "lucide-react";

interface TradesViewProps {
  snapshot: TerminalSnapshotResponse | null;
}

const SYMBOL_FILTERS = [
  "ALL",
  "BTC/USDT",
  "ETH/USDT",
  "SOL/USDT",
  "BNB/BTC",
  "SOL/BTC",
  "SOL/ETH",
  "ETH/BTC",
] as const;

type OutcomeFilter = "ALL" | "WINS" | "LOSSES";
type TimeframeFilter = "ALL" | "24H" | "7D" | "30D";
type SortField = "closed_at" | "realized_pnl_inr" | "total_fees_inr" | "symbol";
type SortOrder = "asc" | "desc";

interface EquityPoint {
  index: number;
  label: string;
  symbol: string;
  equity: number;
  pnl: number;
  pnlPct: number;
  fees: number;
  exitReason?: string;
  closedAt?: string;
  x: number;
  y: number;
}

/* -------------------------------------------------------------------------- */
/*                 1. Interactive Cumulative Equity Growth Chart               */
/* -------------------------------------------------------------------------- */
function InteractiveCumulativeEquityChart({
  trades,
  initialCapital,
}: {
  trades: TradeLedgerEntry[];
  initialCapital: number;
}) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  // Sort trades chronologically ascending for the equity path
  const sorted = useMemo(() => {
    return [...trades].sort(
      (a, b) => new Date(a.closed_at).getTime() - new Date(b.closed_at).getTime()
    );
  }, [trades]);

  const { points, minEq, maxEq, baselineY, linePath, areaPath, width, height, padLeft, padRight, padTop, padBottom } = useMemo(() => {
    let currentEq = initialCapital;
    const rawPoints: Array<{
      index: number;
      label: string;
      symbol: string;
      equity: number;
      pnl: number;
      pnlPct: number;
      fees: number;
      exitReason?: string;
      closedAt?: string;
    }> = [
      {
        index: 0,
        label: "Initial Capital Baseline",
        symbol: "START",
        equity: initialCapital,
        pnl: 0,
        pnlPct: 0,
        fees: 0,
        closedAt: sorted[0]?.opened_at ?? new Date().toISOString(),
      },
    ];

    for (let i = 0; i < sorted.length; i++) {
      const t = sorted[i];
      const pnl = toFiniteNumber(t.realized_pnl_inr);
      currentEq += pnl;
      rawPoints.push({
        index: i + 1,
        label: `Trade #${i + 1} (${t.symbol})`,
        symbol: t.symbol,
        equity: currentEq,
        pnl: pnl,
        pnlPct: toFiniteNumber(t.realized_pnl_pct),
        fees: toFiniteNumber(t.total_fees_inr),
        exitReason: t.exit_reason,
        closedAt: t.closed_at,
      });
    }

    const w = 840;
    const h = 200;
    const pLeft = 68;
    const pRight = 36;
    const pTop = 24;
    const pBottom = 34;

    const eqVals = rawPoints.map((p) => p.equity);
    const min = Math.min(...eqVals, initialCapital * 0.998);
    const max = Math.max(...eqVals, initialCapital * 1.002);
    const span = Math.max(max - min, 1);

    const plotW = w - pLeft - pRight;
    const plotH = h - pTop - pBottom;

    const mappedCoords: EquityPoint[] = rawPoints.map((p, idx) => {
      const x = pLeft + (idx / Math.max(rawPoints.length - 1, 1)) * plotW;
      const y = h - pBottom - ((p.equity - min) / span) * plotH;
      return { ...p, x, y };
    });

    const lPath = mappedCoords
      .map((c, i) => `${i === 0 ? "M" : "L"} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`)
      .join(" ");
    
    const baseY = h - pBottom - ((initialCapital - min) / span) * plotH;
    const latestCoord = mappedCoords[mappedCoords.length - 1] ?? { x: pLeft, y: baseY };
    const aPath = `${lPath} L ${latestCoord.x.toFixed(1)} ${baseY.toFixed(1)} L ${pLeft} ${baseY.toFixed(1)} Z`;

    return {
      points: mappedCoords,
      minEq: min,
      maxEq: max,
      baselineY: baseY,
      linePath: lPath,
      areaPath: aPath,
      width: w,
      height: h,
      padLeft: pLeft,
      padRight: pRight,
      padTop: pTop,
      padBottom: pBottom,
    };
  }, [sorted, initialCapital]);

  const activePoint = hoveredIndex !== null && points[hoveredIndex] ? points[hoveredIndex] : points[points.length - 1];
  const isNetProfit = activePoint ? activePoint.equity >= initialCapital : true;

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const svgX = ((e.clientX - rect.left) / rect.width) * width;
    
    let closestIdx = 0;
    let minDistance = Infinity;

    points.forEach((p, idx) => {
      const dist = Math.abs(p.x - svgX);
      if (dist < minDistance) {
        minDistance = dist;
        closestIdx = idx;
      }
    });

    setHoveredIndex(closestIdx);
  };

  return (
    <div className="nexus-panel rounded-lg p-4 space-y-3">
      {/* Chart Header with Interactive Hover HUD */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-cyan-500/15 pb-3">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-cyan-400" />
          <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
            Portfolio Cumulative Equity Curve
          </h3>
          <span className="rounded bg-cyan-950/80 px-2 py-0.5 font-mono text-[10px] text-cyan-300 border border-cyan-500/30">
            LIVE AUDIT TRAIL
          </span>
        </div>

        {activePoint && (
          <div className="flex items-center gap-3 font-mono text-xs">
            <span className="text-slate-400">
              Point: <span className="text-cyan-300 font-bold">{activePoint.label}</span>
            </span>
            <span className="text-slate-400">
              Equity:{" "}
              <span className={`font-bold ${isNetProfit ? "text-emerald-300" : "text-rose-300"}`}>
                {formatInr(activePoint.equity)}
              </span>
            </span>
            {activePoint.index > 0 && (
              <span className="text-slate-400">
                Clip P&L:{" "}
                <span
                  className={`font-semibold ${
                    activePoint.pnl > 0
                      ? "text-emerald-300"
                      : activePoint.pnl < 0
                        ? "text-rose-300"
                        : "text-slate-300"
                  }`}
                >
                  {formatInr(activePoint.pnl, true)} ({formatPct(activePoint.pnlPct, true)})
                </span>
              </span>
            )}
          </div>
        )}
      </div>

      {/* SVG Canvas Area */}
      <div className="relative">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="h-48 w-full cursor-crosshair rounded border border-cyan-500/20 bg-[#030712] shadow-inner select-none"
          role="img"
          aria-label="Cumulative Paper Trading Equity Growth Curve"
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoveredIndex(null)}
        >
          <defs>
            <linearGradient id="equityGradActive" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.40" />
              <stop offset="60%" stopColor="#0891b2" stopOpacity="0.10" />
              <stop offset="100%" stopColor="#030712" stopOpacity="0.0" />
            </linearGradient>
            <linearGradient id="gridGrad" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#1e293b" stopOpacity="0.2" />
              <stop offset="50%" stopColor="#1e293b" stopOpacity="0.8" />
              <stop offset="100%" stopColor="#1e293b" stopOpacity="0.2" />
            </linearGradient>
          </defs>

          {/* Grid lines */}
          <line
            x1={padLeft}
            y1={padTop}
            x2={width - padRight}
            y2={padTop}
            stroke="#1e293b"
            strokeDasharray="3 3"
          />
          <line
            x1={padLeft}
            y1={baselineY}
            x2={width - padRight}
            y2={baselineY}
            stroke="#d4af37"
            strokeDasharray="4 3"
            strokeWidth="1.2"
          />

          {/* Y Axis Baseline Reference Label */}
          <text
            x={padLeft - 8}
            y={baselineY + 4}
            fill="#d4af37"
            fontSize="9"
            fontFamily="monospace"
            textAnchor="end"
          >
            Base ₹{initialCapital.toFixed(0)}
          </text>

          {/* Y Axis Max Label */}
          <text
            x={padLeft - 8}
            y={padTop + 4}
            fill="#22d3ee"
            fontSize="9"
            fontFamily="monospace"
            textAnchor="end"
          >
            Max ₹{maxEq.toFixed(0)}
          </text>

          {/* Y Axis Min Label */}
          <text
            x={padLeft - 8}
            y={height - padBottom + 4}
            fill="#64748b"
            fontSize="9"
            fontFamily="monospace"
            textAnchor="end"
          >
            Min ₹{minEq.toFixed(0)}
          </text>

          {/* Gradient Area Fill */}
          <path d={areaPath} fill="url(#equityGradActive)" />

          {/* Primary Trend Line */}
          <path
            d={linePath}
            fill="none"
            stroke="#22d3ee"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Hover Crosshair Vertical Line */}
          {activePoint && (
            <line
              x1={activePoint.x}
              y1={padTop}
              x2={activePoint.x}
              y2={height - padBottom}
              stroke="#22d3ee"
              strokeDasharray="2 2"
              strokeWidth="1"
              strokeOpacity="0.75"
            />
          )}

          {/* Interactive Marker Beacon */}
          {activePoint && (
            <g>
              <circle
                cx={activePoint.x}
                cy={activePoint.y}
                r="7"
                fill="#22d3ee"
                fillOpacity="0.3"
                className="animate-ping"
              />
              <circle
                cx={activePoint.x}
                cy={activePoint.y}
                r="4"
                fill="#ffffff"
                stroke="#0891b2"
                strokeWidth="2"
              />
            </g>
          )}

          {/* X Axis Time Labels */}
          <text
            x={padLeft}
            y={height - 10}
            fill="#64748b"
            fontSize="9"
            fontFamily="monospace"
          >
            Start (₹{initialCapital.toFixed(0)})
          </text>
          <text
            x={width - padRight}
            y={height - 10}
            fill="#22d3ee"
            fontSize="9"
            fontFamily="monospace"
            textAnchor="end"
          >
            {sorted.length > 0 ? `Trade #${sorted.length} (Current)` : "No trades"}
          </text>
        </svg>

        {/* Hover Floating Card */}
        {hoveredIndex !== null && activePoint && activePoint.index > 0 && (
          <div
            className="pointer-events-none absolute z-20 rounded-md border border-cyan-500/40 bg-slate-950/95 px-3 py-2 shadow-xl backdrop-blur font-mono text-[11px]"
            style={{
              left: Math.min(Math.max(activePoint.x - 70, 10), width - 180),
              top: 10,
            }}
          >
            <div className="flex items-center justify-between gap-2 border-b border-slate-800 pb-1 text-cyan-300 font-bold">
              <span>{activePoint.label}</span>
              <span className="text-[10px] text-slate-400">{activePoint.closedAt?.slice(11, 19)} UTC</span>
            </div>
            <div className="mt-1 space-y-0.5">
              <div className="flex justify-between gap-3 text-slate-300">
                <span>Equity:</span>
                <span className="font-semibold text-white">{formatInr(activePoint.equity)}</span>
              </div>
              <div className="flex justify-between gap-3 text-slate-300">
                <span>Net P&L:</span>
                <span className={activePoint.pnl >= 0 ? "text-emerald-300 font-semibold" : "text-rose-300 font-semibold"}>
                  {formatInr(activePoint.pnl, true)} ({formatPct(activePoint.pnlPct, true)})
                </span>
              </div>
              <div className="flex justify-between gap-3 text-slate-400 text-[10px]">
                <span>Exit Reason:</span>
                <span className="text-amber-300">{activePoint.exitReason ?? "N/A"}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*                  2. 1-Click CSV & Tax Summary Exporter                      */
/* -------------------------------------------------------------------------- */
function exportTradeLedgerToCsv(trades: TradeLedgerEntry[]) {
  if (!trades || trades.length === 0) return;

  const headers = [
    "Trade ID",
    "Position ID",
    "Symbol",
    "Quantity",
    "Entry Price (USDT)",
    "Exit Price (USDT)",
    "Entry Cost (INR)",
    "Exit Proceeds (INR)",
    "Total Fees (INR)",
    "Realized P&L (INR)",
    "Realized P&L (%)",
    "Exit Reason",
    "Opened At (UTC)",
    "Closed At (UTC)",
  ];

  const rows = trades.map((t) => [
    `"${t.id}"`,
    `"${t.position_id}"`,
    `"${t.symbol}"`,
    toFiniteNumber(t.quantity),
    toFiniteNumber(t.entry_price_usdt),
    toFiniteNumber(t.exit_price_usdt),
    toFiniteNumber(t.entry_cost_inr),
    toFiniteNumber(t.exit_proceeds_inr),
    toFiniteNumber(t.total_fees_inr),
    toFiniteNumber(t.realized_pnl_inr),
    toFiniteNumber(t.realized_pnl_pct),
    `"${t.exit_reason}"`,
    `"${t.opened_at}"`,
    `"${t.closed_at}"`,
  ]);

  const csvContent = [headers.join(","), ...rows.map((r) => r.join(","))].join("\r\n");
  const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const dateStr = new Date().toISOString().slice(0, 10);
  link.setAttribute("href", url);
  link.setAttribute("download", `nexus_trade_ledger_${dateStr}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/* -------------------------------------------------------------------------- */
/*                            3. Main TradesView Component                    */
/* -------------------------------------------------------------------------- */
export function TradesView({ snapshot }: TradesViewProps) {
  const [symbolFilter, setSymbolFilter] = useState<string>("ALL");
  const [outcomeFilter, setOutcomeFilter] = useState<OutcomeFilter>("ALL");
  const [timeframeFilter, setTimeframeFilter] = useState<TimeframeFilter>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [sortField, setSortField] = useState<SortField>("closed_at");
  const [sortOrder, setSortOrder] = useState<SortOrder>("desc");
  const [downloadSuccess, setDownloadSuccess] = useState<boolean>(false);

  const initialCapital = toFiniteNumber(
    snapshot?.portfolio.initial_capital_inr || 10000
  );

  const allTrades = snapshot?.recent_trades ?? [];

  // Quantitative Telemetry Calculations
  const telemetry = useMemo(() => {
    const winning = allTrades.filter((t) => toFiniteNumber(t.realized_pnl_inr) > 0);
    const losing = allTrades.filter((t) => toFiniteNumber(t.realized_pnl_inr) < 0);
    const flat = allTrades.filter((t) => toFiniteNumber(t.realized_pnl_inr) === 0);

    const grossGains = winning.reduce((acc, t) => acc + toFiniteNumber(t.realized_pnl_inr), 0);
    const grossLosses = Math.abs(losing.reduce((acc, t) => acc + toFiniteNumber(t.realized_pnl_inr), 0));
    const netPnl = grossGains - grossLosses;
    const netReturnPct = initialCapital > 0 ? (netPnl / initialCapital) * 100 : 0;

    const profitFactor = grossLosses > 0 ? grossGains / grossLosses : grossGains > 0 ? Infinity : 1.0;
    const winRate = allTrades.length > 0 ? (winning.length / allTrades.length) * 100 : 0;

    const avgWin = winning.length > 0 ? grossGains / winning.length : 0;
    const avgLoss = losing.length > 0 ? grossLosses / losing.length : 0;
    const payoffRatio = avgLoss > 0 ? avgWin / avgLoss : avgWin > 0 ? Infinity : 1.0;

    const bestTrade = allTrades.length > 0 ? Math.max(...allTrades.map((t) => toFiniteNumber(t.realized_pnl_inr))) : 0;
    const worstTrade = allTrades.length > 0 ? Math.min(...allTrades.map((t) => toFiniteNumber(t.realized_pnl_inr))) : 0;

    const totalFees = allTrades.reduce((acc, t) => acc + toFiniteNumber(t.total_fees_inr), 0);
    const feeDragPct = grossGains > 0 ? (totalFees / grossGains) * 100 : 0;

    return {
      totalCount: allTrades.length,
      winCount: winning.length,
      lossCount: losing.length,
      flatCount: flat.length,
      grossGains,
      grossLosses,
      netPnl,
      netReturnPct,
      profitFactor,
      winRate,
      avgWin,
      avgLoss,
      payoffRatio,
      bestTrade,
      worstTrade,
      totalFees,
      feeDragPct,
      currentEquity: initialCapital + netPnl,
    };
  }, [allTrades, initialCapital]);

  // Filtering Open Positions
  const openPositions = useMemo(() => {
    return (snapshot?.open_positions ?? []).filter((p) => {
      if (symbolFilter !== "ALL" && p.symbol !== symbolFilter) return false;
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        if (!p.symbol.toLowerCase().includes(query) && !p.id.toLowerCase().includes(query)) {
          return false;
        }
      }
      return true;
    });
  }, [snapshot?.open_positions, symbolFilter, searchQuery]);

  // Filtering Settled Trades
  const filteredTrades = useMemo(() => {
    const now = Date.now();
    return allTrades.filter((t) => {
      // 1. Symbol Filter
      if (symbolFilter !== "ALL" && t.symbol !== symbolFilter) return false;

      // 2. Outcome Filter
      const pnl = toFiniteNumber(t.realized_pnl_inr);
      if (outcomeFilter === "WINS" && pnl <= 0) return false;
      if (outcomeFilter === "LOSSES" && pnl >= 0) return false;

      // 3. Timeframe Filter
      if (timeframeFilter !== "ALL") {
        const closedTime = new Date(t.closed_at).getTime();
        const diffMs = now - closedTime;
        if (timeframeFilter === "24H" && diffMs > 24 * 60 * 60 * 1000) return false;
        if (timeframeFilter === "7D" && diffMs > 7 * 24 * 60 * 60 * 1000) return false;
        if (timeframeFilter === "30D" && diffMs > 30 * 24 * 60 * 60 * 1000) return false;
      }

      // 4. Text Search Query
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesSymbol = t.symbol.toLowerCase().includes(q);
        const matchesReason = t.exit_reason.toLowerCase().includes(q);
        const matchesId = t.id.toLowerCase().includes(q);
        if (!matchesSymbol && !matchesReason && !matchesId) return false;
      }

      return true;
    });
  }, [allTrades, symbolFilter, outcomeFilter, timeframeFilter, searchQuery]);

  // Sorting Settled Trades
  const sortedTrades = useMemo(() => {
    return [...filteredTrades].sort((a, b) => {
      let comparison = 0;
      if (sortField === "closed_at") {
        comparison = new Date(a.closed_at).getTime() - new Date(b.closed_at).getTime();
      } else if (sortField === "realized_pnl_inr") {
        comparison = toFiniteNumber(a.realized_pnl_inr) - toFiniteNumber(b.realized_pnl_inr);
      } else if (sortField === "total_fees_inr") {
        comparison = toFiniteNumber(a.total_fees_inr) - toFiniteNumber(b.total_fees_inr);
      } else if (sortField === "symbol") {
        comparison = a.symbol.localeCompare(b.symbol);
      }
      return sortOrder === "desc" ? -comparison : comparison;
    });
  }, [filteredTrades, sortField, sortOrder]);

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortOrder("desc");
    }
  };

  const handleExportCsv = () => {
    exportTradeLedgerToCsv(filteredTrades);
    setDownloadSuccess(true);
    setTimeout(() => setDownloadSuccess(false), 3000);
  };

  const resetFilters = () => {
    setSymbolFilter("ALL");
    setOutcomeFilter("ALL");
    setTimeframeFilter("ALL");
    setSearchQuery("");
  };

  const hasActiveFilters =
    symbolFilter !== "ALL" ||
    outcomeFilter !== "ALL" ||
    timeframeFilter !== "ALL" ||
    searchQuery.trim().length > 0;

  return (
    <div className="space-y-4">
      {/* 1. Interactive Cumulative Equity Growth Chart */}
      <InteractiveCumulativeEquityChart
        trades={allTrades}
        initialCapital={initialCapital}
      />

      {/* 2. Institutional Quant Telemetry Deck (6 Executive Metrics Cards) */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6 font-mono text-xs">
        {/* Metric 1: Net Realized P&L */}
        <div className="rounded-lg border border-slate-800 bg-[#030712] p-3 space-y-1">
          <div className="flex items-center gap-1.5 text-slate-400 text-[10px] uppercase font-bold">
            {telemetry.netPnl >= 0 ? (
              <TrendingUp className="h-3.5 w-3.5 text-emerald-400" />
            ) : (
              <TrendingDown className="h-3.5 w-3.5 text-rose-400" />
            )}
            <span>Net Realized P&L</span>
          </div>
          <div
            className={`text-base font-bold ${
              telemetry.netPnl >= 0 ? "text-emerald-300" : "text-rose-300"
            }`}
          >
            {formatInr(telemetry.netPnl, true)}
          </div>
          <div className="text-[10px] text-slate-400">
            ROI: <span className="font-semibold text-white">{formatPct(telemetry.netReturnPct, true)}</span>
          </div>
        </div>

        {/* Metric 2: Profit Factor */}
        <div className="rounded-lg border border-cyan-500/30 bg-[#040816] p-3 space-y-1">
          <div className="flex items-center gap-1.5 text-cyan-400 text-[10px] uppercase font-bold">
            <Award className="h-3.5 w-3.5" />
            <span>Profit Factor</span>
          </div>
          <div className="text-base font-bold text-cyan-300">
            {telemetry.profitFactor === Infinity
              ? "∞ (No Loss)"
              : `${telemetry.profitFactor.toFixed(2)}x`}
          </div>
          <div className="text-[10px] text-slate-400 truncate">
            Win ₹{telemetry.grossGains.toFixed(0)} / Loss ₹{telemetry.grossLosses.toFixed(0)}
          </div>
        </div>

        {/* Metric 3: Win Rate & Payoff */}
        <div className="rounded-lg border border-amber-500/30 bg-amber-950/20 p-3 space-y-1">
          <div className="flex items-center gap-1.5 text-amber-400 text-[10px] uppercase font-bold">
            <Percent className="h-3.5 w-3.5" />
            <span>Win Rate / Payoff</span>
          </div>
          <div className="text-base font-bold text-amber-300">
            {telemetry.winRate.toFixed(1)}%
          </div>
          <div className="text-[10px] text-slate-400">
            Payoff: <span className="text-amber-200">{telemetry.payoffRatio.toFixed(1)}:1</span> (Avg ₹{telemetry.avgWin.toFixed(0)})
          </div>
        </div>

        {/* Metric 4: Outlier Spectrum */}
        <div className="rounded-lg border border-purple-500/30 bg-purple-950/20 p-3 space-y-1">
          <div className="flex items-center gap-1.5 text-purple-400 text-[10px] uppercase font-bold">
            <ShieldCheck className="h-3.5 w-3.5" />
            <span>Outlier Spectrum</span>
          </div>
          <div className="text-base font-bold text-purple-300">
            +{formatInr(telemetry.bestTrade)}
          </div>
          <div className="text-[10px] text-rose-300">
            Max Draw: {formatInr(telemetry.worstTrade)}
          </div>
        </div>

        {/* Metric 5: Total Fee Friction Drag */}
        <div className="rounded-lg border border-slate-800 bg-[#030712] p-3 space-y-1">
          <div className="flex items-center gap-1.5 text-slate-400 text-[10px] uppercase font-bold">
            <DollarSign className="h-3.5 w-3.5 text-cyan-400" />
            <span>Friction & Fees</span>
          </div>
          <div className="text-base font-bold text-slate-200">
            {formatInr(telemetry.totalFees)}
          </div>
          <div className="text-[10px] text-slate-400">
            Fee Drag: <span className="text-cyan-300 font-semibold">{telemetry.feeDragPct.toFixed(1)}%</span> of gains
          </div>
        </div>

        {/* Metric 6: Sample Size */}
        <div className="rounded-lg border border-slate-800 bg-[#030712] p-3 space-y-1">
          <div className="flex items-center gap-1.5 text-slate-400 text-[10px] uppercase font-bold">
            <Layers className="h-3.5 w-3.5 text-cyan-400" />
            <span>Settled Sample</span>
          </div>
          <div className="text-base font-bold text-cyan-200">
            {telemetry.totalCount} Clips
          </div>
          <div className="text-[10px] text-slate-400">
            {telemetry.winCount}W • {telemetry.lossCount}L • {telemetry.flatCount}F
          </div>
        </div>
      </div>

      {/* 3. Visual P&L Volume Distribution Bar */}
      {telemetry.totalCount > 0 && (
        <div className="nexus-panel rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between text-xs font-mono">
            <div className="flex items-center gap-2">
              <span className="text-slate-400 uppercase text-[10px]">Capital Allocation Breakdown</span>
              <span className="text-emerald-400 font-semibold">
                Wins: {telemetry.winCount} ({telemetry.winRate.toFixed(1)}%) • ₹{telemetry.grossGains.toFixed(2)}
              </span>
            </div>
            <span className="text-rose-400 font-semibold">
              Losses: {telemetry.lossCount} ({(100 - telemetry.winRate).toFixed(1)}%) • ₹{telemetry.grossLosses.toFixed(2)}
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800 flex">
            <div
              className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 transition-all duration-500"
              style={{ width: `${Math.max(telemetry.winRate, 4)}%` }}
              title={`Winning trades: ${telemetry.winRate.toFixed(1)}%`}
            />
            <div
              className="h-full bg-gradient-to-r from-rose-500 to-rose-700 transition-all duration-500"
              style={{ width: `${Math.min(100 - telemetry.winRate, 96)}%` }}
              title={`Losing trades: ${(100 - telemetry.winRate).toFixed(1)}%`}
            />
          </div>
        </div>
      )}

      {/* 4. Multi-Dimensional Filter Bar with CSV Export */}
      <div className="nexus-panel rounded-lg p-3.5 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-cyan-400" />
            <h2 className="font-display text-sm font-semibold text-white">
              Audit Ledger Controls & Telemetry
            </h2>
            <span className="text-[11px] text-slate-400 font-mono">
              ({sortedTrades.length} of {allTrades.length} records matching)
            </span>
          </div>

          <div className="flex items-center gap-2">
            {hasActiveFilters && (
              <button
                type="button"
                onClick={resetFilters}
                className="flex items-center gap-1 rounded border border-slate-700 bg-slate-900/60 px-2.5 py-1.5 font-mono text-xs text-slate-300 hover:border-slate-500 hover:text-white transition"
              >
                <RotateCcw className="h-3.5 w-3.5 text-cyan-400" />
                <span>Reset</span>
              </button>
            )}

            {/* 1-Click CSV / Audit Ledger Export Button */}
            <button
              type="button"
              onClick={handleExportCsv}
              disabled={filteredTrades.length === 0}
              className={`flex items-center gap-1.5 rounded border px-3 py-1.5 font-mono text-xs font-semibold shadow transition ${
                downloadSuccess
                  ? "border-emerald-500 bg-emerald-500/20 text-emerald-300"
                  : filteredTrades.length === 0
                    ? "border-slate-800 bg-slate-900/40 text-slate-600 cursor-not-allowed"
                    : "border-cyan-400/50 bg-cyan-500/15 text-cyan-200 hover:bg-cyan-500/25 hover:border-cyan-400"
              }`}
            >
              {downloadSuccess ? (
                <>
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                  <span>Exported CSV!</span>
                </>
              ) : (
                <>
                  <Download className="h-3.5 w-3.5 text-cyan-400" />
                  <span>Export Ledger (CSV)</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Filter Controls Row */}
        <div className="flex flex-wrap items-center gap-3 pt-1 border-t border-slate-800">
          {/* Search Box */}
          <div className="relative min-w-[200px] flex-1">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-500" />
            <input
              type="text"
              placeholder="Search symbol, exit reason, or order ID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full rounded border border-slate-700 bg-[#030712] py-1.5 pl-8 pr-3 font-mono text-xs text-slate-200 placeholder-slate-500 focus:border-cyan-400 focus:outline-none"
            />
          </div>

          {/* Outcome Filter */}
          <div className="flex items-center gap-1 font-mono text-xs">
            <span className="text-[10px] uppercase text-slate-500 mr-1">Outcome:</span>
            {(["ALL", "WINS", "LOSSES"] as OutcomeFilter[]).map((outcome) => (
              <button
                key={outcome}
                type="button"
                onClick={() => setOutcomeFilter(outcome)}
                className={`rounded border px-2 py-1 transition ${
                  outcomeFilter === outcome
                    ? outcome === "WINS"
                      ? "border-emerald-500/60 bg-emerald-500/20 text-emerald-200 font-semibold"
                      : outcome === "LOSSES"
                        ? "border-rose-500/60 bg-rose-500/20 text-rose-200 font-semibold"
                        : "border-cyan-400 bg-cyan-500/20 text-cyan-200 font-semibold"
                    : "border-slate-800 bg-[#030712] text-slate-400 hover:border-slate-700 hover:text-white"
                }`}
              >
                {outcome === "ALL" ? "All" : outcome === "WINS" ? "🟢 Wins" : "🔴 Losses"}
              </button>
            ))}
          </div>

          {/* Timeframe Filter */}
          <div className="flex items-center gap-1 font-mono text-xs">
            <span className="text-[10px] uppercase text-slate-500 mr-1">Time:</span>
            {(["ALL", "24H", "7D", "30D"] as TimeframeFilter[]).map((tf) => (
              <button
                key={tf}
                type="button"
                onClick={() => setTimeframeFilter(tf)}
                className={`rounded border px-2 py-1 transition ${
                  timeframeFilter === tf
                    ? "border-cyan-400 bg-cyan-500/20 text-cyan-200 font-semibold"
                    : "border-slate-800 bg-[#030712] text-slate-400 hover:border-slate-700 hover:text-white"
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        {/* Symbol Quick Chips */}
        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          <span className="font-mono text-[10px] uppercase text-slate-500 mr-1">Asset:</span>
          {SYMBOL_FILTERS.map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => setSymbolFilter(opt)}
              className={`rounded border px-2 py-0.5 font-mono text-[11px] transition ${
                symbolFilter === opt
                  ? "border-cyan-400 bg-cyan-500/20 text-cyan-200 font-bold"
                  : "border-slate-800 bg-[#030712] text-slate-400 hover:border-slate-700 hover:text-white"
              }`}
            >
              {opt}
            </button>
          ))}
        </div>
      </div>

      {/* 5. Open Paper Spot Positions Table */}
      <div className="nexus-panel overflow-hidden rounded-lg">
        <div className="flex items-center justify-between border-b border-cyan-500/15 px-4 py-3">
          <div className="flex items-center gap-2">
            <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
              Open Paper Spot Positions ({openPositions.length})
            </h3>
            <span className="rounded bg-emerald-950/80 px-2 py-0.5 font-mono text-[10px] text-emerald-300 border border-emerald-500/30">
              ACTIVE RISK COVERED
            </span>
          </div>
          <span className="font-mono text-[11px] text-cyan-300">
            TRAILING STOP + ATR SYSTEM TRACKED
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left font-mono text-xs">
            <thead className="border-b border-slate-800 bg-nexus-void/80 text-[10px] uppercase text-slate-400">
              <tr>
                <th className="px-4 py-2.5">Symbol</th>
                <th className="px-4 py-2.5">Qty</th>
                <th className="px-4 py-2.5">Avg Entry</th>
                <th className="px-4 py-2.5">Initial Stop</th>
                <th className="px-4 py-2.5">Trailing Stop</th>
                <th className="px-4 py-2.5">Highest Seen</th>
                <th className="px-4 py-2.5">Cost (INR)</th>
                <th className="px-4 py-2.5">Stop Distance</th>
                <th className="px-4 py-2.5">Opened UTC</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {openPositions.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-6 text-center text-slate-500">
                    No open paper positions matching filter criteria.
                  </td>
                </tr>
              ) : (
                openPositions.map((pos) => {
                  const entryPrice = toFiniteNumber(pos.avg_entry_price_usdt);
                  const trailingStop = toFiniteNumber(pos.trailing_stop_price_usdt);
                  const stopDistancePct =
                    entryPrice > 0 && trailingStop > 0
                      ? ((trailingStop - entryPrice) / entryPrice) * 100
                      : null;

                  return (
                    <tr key={pos.id} className="hover:bg-cyan-500/5 transition">
                      <td className="px-4 py-2.5 font-semibold text-cyan-300">
                        {pos.symbol}
                      </td>
                      <td className="px-4 py-2.5 tabular-nums text-white">
                        {formatQty(pos.quantity)}
                      </td>
                      <td className="px-4 py-2.5 tabular-nums text-slate-200">
                        {formatUsdt(pos.avg_entry_price_usdt)}
                      </td>
                      <td className="px-4 py-2.5 tabular-nums text-rose-300">
                        {pos.initial_stop_price_usdt
                          ? formatUsdt(pos.initial_stop_price_usdt)
                          : "—"}
                      </td>
                      <td className="px-4 py-2.5 tabular-nums text-amber-300 font-semibold">
                        {pos.trailing_stop_price_usdt
                          ? formatUsdt(pos.trailing_stop_price_usdt)
                          : "—"}
                      </td>
                      <td className="px-4 py-2.5 tabular-nums text-emerald-300">
                        {pos.highest_price_usdt
                          ? formatUsdt(pos.highest_price_usdt)
                          : "—"}
                      </td>
                      <td className="px-4 py-2.5 tabular-nums text-white">
                        {formatInr(pos.entry_cost_inr)}
                      </td>
                      <td className="px-4 py-2.5 tabular-nums">
                        {stopDistancePct !== null ? (
                          <span
                            className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${
                              stopDistancePct >= 0
                                ? "bg-emerald-950/60 text-emerald-300 border border-emerald-500/30"
                                : "bg-rose-950/60 text-rose-300 border border-rose-500/30"
                            }`}
                          >
                            {formatPct(stopDistancePct, true)}
                          </span>
                        ) : (
                          <span className="text-slate-500">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 text-[11px] text-slate-400">
                        {formatUtcTime(pos.opened_at)}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 6. Settled Paper Trade History Table */}
      <div className="nexus-panel overflow-hidden rounded-lg">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-cyan-500/15 px-4 py-3">
          <div className="flex items-center gap-2">
            <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
              Settled Paper Trade Ledger ({sortedTrades.length})
            </h3>
            <span className="rounded bg-cyan-950/80 px-2 py-0.5 font-mono text-[10px] text-cyan-300 border border-cyan-500/30">
              AUDIT COMPLIANT
            </span>
          </div>
          <span className="font-mono text-[11px] text-slate-400">
            NET AFTER ZERO-SLIPPAGE PAPER EXECUTION & FEES
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left font-mono text-xs">
            <thead className="border-b border-slate-800 bg-nexus-void/80 text-[10px] uppercase text-slate-400 select-none">
              <tr>
                <th
                  className="px-4 py-2.5 cursor-pointer hover:text-white"
                  onClick={() => toggleSort("symbol")}
                >
                  <div className="flex items-center gap-1">
                    <span>Symbol</span>
                    <ArrowUpDown className="h-3 w-3" />
                  </div>
                </th>
                <th className="px-4 py-2.5">Qty</th>
                <th className="px-4 py-2.5">Entry (USDT)</th>
                <th className="px-4 py-2.5">Exit (USDT)</th>
                <th className="px-4 py-2.5">Exit Reason</th>
                <th
                  className="px-4 py-2.5 cursor-pointer hover:text-white"
                  onClick={() => toggleSort("total_fees_inr")}
                >
                  <div className="flex items-center gap-1">
                    <span>Fees (INR)</span>
                    <ArrowUpDown className="h-3 w-3" />
                  </div>
                </th>
                <th
                  className="px-4 py-2.5 cursor-pointer hover:text-white"
                  onClick={() => toggleSort("realized_pnl_inr")}
                >
                  <div className="flex items-center gap-1">
                    <span>Realized P&L</span>
                    <ArrowUpDown className="h-3 w-3" />
                  </div>
                </th>
                <th className="px-4 py-2.5">Return (%)</th>
                <th
                  className="px-4 py-2.5 cursor-pointer hover:text-white"
                  onClick={() => toggleSort("closed_at")}
                >
                  <div className="flex items-center gap-1">
                    <span>Closed UTC</span>
                    <ArrowUpDown className="h-3 w-3" />
                  </div>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {sortedTrades.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-8 text-center text-slate-500">
                    <p className="font-semibold text-slate-400">No settled trades match your filter criteria.</p>
                    <p className="text-[11px] text-slate-500 mt-1">Try resetting the outcome, symbol, or date filter.</p>
                  </td>
                </tr>
              ) : (
                sortedTrades.map((trade) => {
                  const pnl = toFiniteNumber(trade.realized_pnl_inr);
                  const isWin = pnl > 0;
                  const isLoss = pnl < 0;

                  // Exit reason tag styling
                  const reasonLower = trade.exit_reason.toLowerCase();
                  let reasonBadgeClass = "bg-slate-900 border-slate-700 text-slate-300";
                  if (reasonLower.includes("trailing_stop")) {
                    reasonBadgeClass = "bg-cyan-950/60 border-cyan-500/30 text-cyan-300";
                  } else if (reasonLower.includes("stop_loss")) {
                    reasonBadgeClass = "bg-rose-950/60 border-rose-500/30 text-rose-300";
                  } else if (reasonLower.includes("profit") || reasonLower.includes("target")) {
                    reasonBadgeClass = "bg-emerald-950/60 border-emerald-500/30 text-emerald-300";
                  }

                  return (
                    <tr key={trade.id} className="hover:bg-cyan-500/5 transition">
                      <td className="px-4 py-2.5 font-semibold text-white">
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              isWin ? "bg-emerald-400" : isLoss ? "bg-rose-400" : "bg-slate-400"
                            }`}
                          />
                          <span>{trade.symbol}</span>
                        </div>
                      </td>
                      <td className="px-4 py-2.5 tabular-nums text-slate-200">
                        {formatQty(trade.quantity)}
                      </td>
                      <td className="px-4 py-2.5 tabular-nums text-slate-300">
                        {formatUsdt(trade.entry_price_usdt)}
                      </td>
                      <td className="px-4 py-2.5 tabular-nums text-slate-300">
                        {formatUsdt(trade.exit_price_usdt)}
                      </td>
                      <td className="px-4 py-2.5">
                        <span
                          className={`inline-block rounded border px-2 py-0.5 text-[10px] font-semibold ${reasonBadgeClass}`}
                        >
                          {trade.exit_reason}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 tabular-nums text-slate-400">
                        {formatInr(trade.total_fees_inr)}
                      </td>
                      <td
                        className={`px-4 py-2.5 tabular-nums font-bold ${
                          isWin
                            ? "text-emerald-300"
                            : isLoss
                              ? "text-rose-300"
                              : "text-slate-300"
                        }`}
                      >
                        {formatInr(pnl, true)}
                      </td>
                      <td
                        className={`px-4 py-2.5 tabular-nums font-semibold ${
                          isWin
                            ? "text-emerald-300"
                            : isLoss
                              ? "text-rose-300"
                              : "text-slate-300"
                        }`}
                      >
                        {formatPct(trade.realized_pnl_pct, true)}
                      </td>
                      <td className="px-4 py-2.5 text-[11px] text-slate-400">
                        <div className="flex items-center gap-1">
                          <Clock className="h-3 w-3 text-slate-500" />
                          <span>{formatUtcTime(trade.closed_at)}</span>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
