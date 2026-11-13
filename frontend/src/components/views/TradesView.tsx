import { useState } from "react";
import type { TerminalSnapshotResponse, TradeLedgerEntry } from "../../types/system";
import {
  formatInr,
  formatPct,
  formatQty,
  formatUsdt,
  formatUtcTime,
  toFiniteNumber,
} from "../../utils/format";
import { TrendingUp, Award, Activity, ShieldCheck } from "lucide-react";

interface TradesViewProps {
  snapshot: TerminalSnapshotResponse | null;
}

const FILTER_OPTIONS = [
  "ALL",
  "BTC/USDT",
  "ETH/USDT",
  "SOL/USDT",
  "BNB/BTC",
  "SOL/BTC",
  "SOL/ETH",
  "ETH/BTC",
] as const;

function CumulativeEquityChart({
  trades,
  initialCapital,
}: {
  trades: TradeLedgerEntry[];
  initialCapital: number;
}) {
  // Sort trades chronologically ascending
  const sorted = [...trades].sort(
    (a, b) => new Date(a.closed_at).getTime() - new Date(b.closed_at).getTime()
  );

  let currentEq = initialCapital;
  const points: { label: string; equity: number; pnl: number }[] = [
    { label: "Start", equity: initialCapital, pnl: 0 },
  ];
  for (const t of sorted) {
    const pnl = toFiniteNumber(t.realized_pnl_inr);
    currentEq += pnl;
    points.push({
      label: t.symbol,
      equity: currentEq,
      pnl: pnl,
    });
  }

  const netGain = currentEq - initialCapital;
  const netGainPct = initialCapital > 0 ? (netGain / initialCapital) * 100 : 0;
  const winCount = trades.filter((t) => toFiniteNumber(t.realized_pnl_inr) > 0).length;
  const winRate = trades.length > 0 ? (winCount / trades.length) * 100 : 100;

  const width = 840;
  const height = 180;
  const padLeft = 64;
  const padRight = 36;
  const padTop = 20;
  const padBottom = 30;

  const eqVals = points.map((p) => p.equity);
  const minEq = Math.min(...eqVals, initialCapital * 0.999);
  const maxEq = Math.max(...eqVals, initialCapital * 1.002);
  const span = Math.max(maxEq - minEq, 1);

  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;

  const coords = points.map((p, idx) => {
    const x = padLeft + (idx / Math.max(points.length - 1, 1)) * plotW;
    const y = height - padBottom - ((p.equity - minEq) / span) * plotH;
    return { x, y, ...p };
  });

  const linePath = coords.map((c, i) => `${i === 0 ? "M" : "L"} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`).join(" ");
  const baselineY = height - padBottom - ((initialCapital - minEq) / span) * plotH;
  const latestCoord = coords[coords.length - 1] ?? { x: padLeft, y: baselineY };
  const areaPath = `${linePath} L ${latestCoord.x.toFixed(1)} ${baselineY.toFixed(1)} L ${padLeft} ${baselineY.toFixed(1)} Z`;

  return (
    <div className="nexus-panel rounded-lg p-4 space-y-3">
      {/* 4 Summary Stat Badges */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 font-mono text-xs">
        <div className="rounded border border-slate-800 bg-[#030712] p-2.5">
          <div className="flex items-center gap-1.5 text-slate-400 text-[10px] uppercase">
            <ShieldCheck className="h-3.5 w-3.5 text-cyan-400" />
            <span>Initial Capital</span>
          </div>
          <div className="mt-1 text-sm font-bold text-slate-200">
            {formatInr(initialCapital)}
          </div>
        </div>

        <div className="rounded border border-cyan-500/30 bg-[#040816] p-2.5">
          <div className="flex items-center gap-1.5 text-cyan-400 text-[10px] uppercase font-bold">
            <Activity className="h-3.5 w-3.5" />
            <span>Current Equity</span>
          </div>
          <div className="mt-1 text-sm font-bold text-cyan-300">
            {formatInr(currentEq)}
          </div>
        </div>

        <div className="rounded border border-emerald-500/30 bg-emerald-950/20 p-2.5">
          <div className="flex items-center gap-1.5 text-emerald-400 text-[10px] uppercase font-bold">
            <TrendingUp className="h-3.5 w-3.5" />
            <span>Net Realized P&L</span>
          </div>
          <div className="mt-1 text-sm font-bold text-emerald-300">
            {formatInr(netGain, true)} ({formatPct(netGainPct, true)})
          </div>
        </div>

        <div className="rounded border border-amber-500/30 bg-amber-950/20 p-2.5">
          <div className="flex items-center gap-1.5 text-amber-400 text-[10px] uppercase font-bold">
            <Award className="h-3.5 w-3.5" />
            <span>Win Rate / Trades</span>
          </div>
          <div className="mt-1 text-sm font-bold text-amber-300">
            {winRate.toFixed(1)}% ({trades.length} trades)
          </div>
        </div>
      </div>

      {/* SVG Equity Chart */}
      <div className="relative">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="h-44 w-full rounded border border-cyan-500/20 bg-[#030712] shadow-inner"
          role="img"
          aria-label="Cumulative Paper Trading Equity Growth Curve"
        >
          <defs>
            <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.35" />
              <stop offset="100%" stopColor="#22d3ee" stopOpacity="0.0" />
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

          {/* Y Axis Baseline Label */}
          <text
            x={padLeft - 6}
            y={baselineY + 4}
            fill="#94a3b8"
            fontSize="9"
            fontFamily="monospace"
            textAnchor="end"
          >
            ₹{initialCapital.toFixed(0)}
          </text>

          {/* Y Axis Max Label */}
          <text
            x={padLeft - 6}
            y={padTop + 4}
            fill="#22d3ee"
            fontSize="9"
            fontFamily="monospace"
            textAnchor="end"
          >
            ₹{maxEq.toFixed(0)}
          </text>

          {/* Gradient Area */}
          <path d={areaPath} fill="url(#equityGrad)" />

          {/* Line Path */}
          <path
            d={linePath}
            fill="none"
            stroke="#22d3ee"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />

          {/* Latest point beacon */}
          <circle
            cx={latestCoord.x}
            cy={latestCoord.y}
            r="6"
            fill="#22d3ee"
            fillOpacity="0.4"
            className="animate-ping"
          />
          <circle
            cx={latestCoord.x}
            cy={latestCoord.y}
            r="3.5"
            fill="#ffffff"
            stroke="#0891b2"
            strokeWidth="1.5"
          />

          {/* X Axis Labels */}
          <text
            x={padLeft}
            y={height - 8}
            fill="#64748b"
            fontSize="9"
            fontFamily="monospace"
          >
            Trade #1 (Start)
          </text>
          <text
            x={width - padRight}
            y={height - 8}
            fill="#22d3ee"
            fontSize="9"
            fontFamily="monospace"
            textAnchor="end"
          >
            Trade #{trades.length} (Latest)
          </text>
        </svg>
      </div>
    </div>
  );
}

export function TradesView({ snapshot }: TradesViewProps) {
  const [symbolFilter, setSymbolFilter] = useState<string>("ALL");

  const initialCapital = toFiniteNumber(
    snapshot?.portfolio.initial_capital_inr || 10000
  );

  const positions = (snapshot?.open_positions ?? []).filter(
    (p) => symbolFilter === "ALL" || p.symbol === symbolFilter,
  );
  const trades = (snapshot?.recent_trades ?? []).filter(
    (t) => symbolFilter === "ALL" || t.symbol === symbolFilter,
  );

  return (
    <div className="space-y-4">
      {/* 1. Interactive Cumulative Equity Growth Curve */}
      <CumulativeEquityChart
        trades={snapshot?.recent_trades ?? []}
        initialCapital={initialCapital}
      />

      {/* 2. Filter Bar */}
      <div className="nexus-panel flex flex-wrap items-center justify-between gap-3 rounded-lg p-3">
        <div>
          <h2 className="font-display text-sm font-semibold text-white">
            Audit Ledger Filter
          </h2>
          <p className="text-[11px] text-slate-400">
            PostgreSQL-backed virtual execution audit trail. Zero private keys or exchange execution.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {FILTER_OPTIONS.map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => setSymbolFilter(opt)}
              className={`rounded border px-2.5 py-1 font-mono text-[11px] transition ${
                symbolFilter === opt
                  ? "border-cyan-400 bg-cyan-500/20 text-cyan-200"
                  : "border-slate-700 bg-nexus-void text-slate-400 hover:border-slate-500 hover:text-white"
              }`}
            >
              {opt}
            </button>
          ))}
        </div>
      </div>

      {/* 3. Open Positions */}
      <div className="nexus-panel overflow-hidden rounded-lg">
        <div className="flex items-center justify-between border-b border-cyan-500/15 px-4 py-3">
          <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
            Open Paper Spot Positions ({positions.length})
          </h3>
          <span className="font-mono text-[11px] text-cyan-300">
            TRAILING STOP + ATR TRACKED
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
                <th className="px-4 py-2.5">Opened UTC</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {positions.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-6 text-center text-slate-500">
                    No open paper positions matching filter.
                  </td>
                </tr>
              ) : (
                positions.map((pos) => (
                  <tr key={pos.id} className="hover:bg-cyan-500/5">
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
                    <td className="px-4 py-2.5 text-[11px] text-slate-400">
                      {formatUtcTime(pos.opened_at)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 4. Closed Trade Ledger */}
      <div className="nexus-panel overflow-hidden rounded-lg">
        <div className="flex items-center justify-between border-b border-cyan-500/15 px-4 py-3">
          <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
            Settled Paper Trade History ({trades.length})
          </h3>
          <span className="font-mono text-[11px] text-slate-400">
            NET AFTER FEES & SLIPPAGE
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left font-mono text-xs">
            <thead className="border-b border-slate-800 bg-nexus-void/80 text-[10px] uppercase text-slate-400">
              <tr>
                <th className="px-4 py-2.5">Symbol</th>
                <th className="px-4 py-2.5">Qty</th>
                <th className="px-4 py-2.5">Entry</th>
                <th className="px-4 py-2.5">Exit</th>
                <th className="px-4 py-2.5">Exit Reason</th>
                <th className="px-4 py-2.5">Fees (INR)</th>
                <th className="px-4 py-2.5">Realized P&L</th>
                <th className="px-4 py-2.5">Return</th>
                <th className="px-4 py-2.5">Closed UTC</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/70">
              {trades.length === 0 ? (
                <tr>
                  <td colSpan={9} className="px-4 py-6 text-center text-slate-500">
                    No settled paper trades recorded yet.
                  </td>
                </tr>
              ) : (
                trades.map((trade) => {
                  const pnl = toFiniteNumber(trade.realized_pnl_inr);
                  return (
                    <tr key={trade.id} className="hover:bg-cyan-500/5">
                      <td className="px-4 py-2.5 font-semibold text-white">
                        {trade.symbol}
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
                      <td className="px-4 py-2.5 text-slate-300">{trade.exit_reason}</td>
                      <td className="px-4 py-2.5 tabular-nums text-slate-400">
                        {formatInr(trade.total_fees_inr)}
                      </td>
                      <td
                        className={`px-4 py-2.5 tabular-nums font-semibold ${
                          pnl > 0
                            ? "text-emerald-300"
                            : pnl < 0
                              ? "text-rose-300"
                              : "text-slate-300"
                        }`}
                      >
                        {formatInr(pnl, true)}
                      </td>
                      <td
                        className={`px-4 py-2.5 tabular-nums ${
                          pnl > 0
                            ? "text-emerald-300"
                            : pnl < 0
                              ? "text-rose-300"
                              : "text-slate-300"
                        }`}
                      >
                        {formatPct(trade.realized_pnl_pct, true)}
                      </td>
                      <td className="px-4 py-2.5 text-[11px] text-slate-400">
                        {formatUtcTime(trade.closed_at)}
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
