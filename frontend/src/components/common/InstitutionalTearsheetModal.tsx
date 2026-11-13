import { X, Printer } from "lucide-react";
import type { TerminalSnapshotResponse, TradeLedgerEntry } from "../../types/system";
import { formatInr, formatPct, formatUtcTime, toFiniteNumber } from "../../utils/format";

interface InstitutionalTearsheetModalProps {
  isOpen: boolean;
  onClose: () => void;
  snapshot: TerminalSnapshotResponse | null;
}

interface MonthlyReturn {
  key: string;
  label: string;
  pnlInr: number;
  returnPct: number;
}

function monthlyReturns(
  trades: TradeLedgerEntry[],
  initialCapital: number,
): MonthlyReturn[] {
  if (initialCapital <= 0) return [];
  const buckets = new Map<string, { label: string; pnl: number }>();
  for (const trade of trades) {
    const closedAt = new Date(trade.closed_at);
    if (Number.isNaN(closedAt.getTime())) continue;
    const key = `${closedAt.getUTCFullYear()}-${String(closedAt.getUTCMonth() + 1).padStart(2, "0")}`;
    const label = closedAt.toLocaleString("en-US", {
      month: "short",
      year: "2-digit",
      timeZone: "UTC",
    });
    const bucket = buckets.get(key) ?? { label, pnl: 0 };
    bucket.pnl += toFiniteNumber(trade.realized_pnl_inr);
    buckets.set(key, bucket);
  }
  return [...buckets.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([key, value]) => ({
      key,
      label: value.label,
      pnlInr: value.pnl,
      returnPct: (value.pnl / initialCapital) * 100,
    }));
}

function mean(values: number[]): number {
  return values.reduce((acc, value) => acc + value, 0) / values.length;
}

function sampleStdDev(values: number[]): number | null {
  if (values.length < 2) return null;
  const avg = mean(values);
  const variance =
    values.reduce((acc, value) => acc + (value - avg) ** 2, 0) / (values.length - 1);
  return Math.sqrt(variance);
}

function downsideDeviation(values: number[]): number | null {
  if (values.length < 2) return null;
  const downside = values.filter((value) => value < 0);
  if (downside.length === 0) return 0;
  return Math.sqrt(downside.reduce((acc, value) => acc + value ** 2, 0) / values.length);
}

function percentile(values: number[], p: number): number | null {
  if (values.length < 5) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const index = Math.min(
    sorted.length - 1,
    Math.max(0, Math.floor((p / 100) * (sorted.length - 1))),
  );
  return sorted[index];
}

export function InstitutionalTearsheetModal({
  isOpen,
  onClose,
  snapshot,
}: InstitutionalTearsheetModalProps) {
  if (!isOpen) return null;

  const initialCapital = toFiniteNumber(snapshot?.portfolio.initial_capital_inr || 0);
  const totalEquity = toFiniteNumber(snapshot?.portfolio.total_equity_inr || initialCapital);
  const netPnl = totalEquity - initialCapital;
  const netReturnPct = initialCapital > 0 ? (netPnl / initialCapital) * 100 : 0;

  const trades = snapshot?.recent_trades ?? [];
  const settled = trades.filter((t) => toFiniteNumber(t.realized_pnl_inr) !== 0);
  const wins = settled.filter((t) => toFiniteNumber(t.realized_pnl_inr) > 0);
  const losses = settled.filter((t) => toFiniteNumber(t.realized_pnl_inr) < 0);
  const winRate = settled.length > 0 ? (wins.length / settled.length) * 100 : null;

  const grossWin = wins.reduce((acc, t) => acc + toFiniteNumber(t.realized_pnl_inr), 0);
  const grossLoss = Math.abs(
    losses.reduce((acc, t) => acc + toFiniteNumber(t.realized_pnl_inr), 0),
  );
  const profitFactor =
    grossLoss > 0 ? grossWin / grossLoss : grossWin > 0 ? null : null;

  const months = monthlyReturns(trades, initialCapital);
  const monthlySeries = months.map((m) => m.returnPct);
  const monthlyVol = sampleStdDev(monthlySeries);
  const annualizedVol = monthlyVol === null ? null : monthlyVol * Math.sqrt(12);
  const annualizedReturn = monthlySeries.length >= 2 ? mean(monthlySeries) * 12 : null;
  const riskFreeRate = 4.5;
  const sharpe =
    annualizedReturn !== null && annualizedVol !== null && annualizedVol > 0
      ? (annualizedReturn - riskFreeRate) / annualizedVol
      : null;
  const downside = downsideDeviation(monthlySeries);
  const sortino =
    annualizedReturn !== null && downside !== null && downside > 0
      ? (annualizedReturn - riskFreeRate) / (downside * Math.sqrt(12))
      : null;
  const var95 = percentile(monthlySeries, 5);

  const actualDrawdown = toFiniteNumber(snapshot?.risk.drawdown_pct ?? 0);
  const calmar =
    annualizedReturn !== null && actualDrawdown > 0 ? annualizedReturn / actualDrawdown : null;
  const killSwitchActive = snapshot?.risk.kill_switch_active ?? false;

  const fmt = (value: number | null, digits = 2, suffix = ""): string =>
    value === null ? "N/A" : `${value.toFixed(digits)}${suffix}`;

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-3 backdrop-blur-md overflow-y-auto print:p-0 print:bg-white print:text-black">
      <div className="nexus-panel max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-xl border border-cyan-500/40 bg-[#040816] p-6 shadow-2xl space-y-5 print:max-h-none print:border-none print:bg-white print:p-4 print:text-black print:shadow-none">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-cyan-500/20 pb-4 print:border-black/20">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-500/20 border border-cyan-400 text-cyan-300 font-bold font-display text-lg print:border-black print:text-black">
              N
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-display text-lg font-bold tracking-wider text-white print:text-black">
                  NEXUS QUANTITATIVE TEARSHEET
                </h2>
                <span className="rounded bg-cyan-950 px-2 py-0.5 font-mono text-[10px] text-cyan-300 border border-cyan-500/40 uppercase font-bold print:border-black print:text-black">
                  INTERNAL PAPER AUDIT
                </span>
              </div>
              <p className="font-mono text-xs text-slate-400 print:text-slate-600">
                Persisted paper-ledger performance · Generated {formatUtcTime(new Date().toISOString())}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 print:hidden">
            <button
              type="button"
              onClick={handlePrint}
              className="inline-flex items-center gap-1.5 rounded-lg border border-cyan-400/60 bg-cyan-500/20 px-3 py-1.5 font-mono text-xs font-semibold text-cyan-200 hover:bg-cyan-500/30 transition shadow"
            >
              <Printer className="h-3.5 w-3.5 text-cyan-400" />
              <span>Print / Save PDF</span>
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

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 font-mono text-xs">
          <div className="rounded border border-slate-800 bg-[#030712] p-3 print:border-black/20 print:bg-slate-50">
            <span className="text-[10px] uppercase text-slate-400 print:text-slate-600">Net Return (Cumulative)</span>
            <div className={`mt-1 text-base font-bold ${netReturnPct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {formatPct(netReturnPct, true)}
            </div>
            <div className="text-[10px] text-slate-500">
              Net Gain: {formatInr(netPnl, true)}
            </div>
          </div>

          <div className="rounded border border-slate-800 bg-[#030712] p-3 print:border-black/20 print:bg-slate-50">
            <span className="text-[10px] uppercase text-slate-400 print:text-slate-600">Sharpe / Sortino</span>
            <div className="mt-1 text-base font-bold text-cyan-300 print:text-black">
              {fmt(sharpe)} / {fmt(sortino)}
            </div>
            <div className="text-[10px] text-slate-500">
              Derived from {months.length} monthly observation{months.length === 1 ? "" : "s"}
            </div>
          </div>

          <div className="rounded border border-slate-800 bg-[#030712] p-3 print:border-black/20 print:bg-slate-50">
            <span className="text-[10px] uppercase text-slate-400 print:text-slate-600">Profit Factor & Win Rate</span>
            <div className="mt-1 text-base font-bold text-amber-300 print:text-black">
              {profitFactor === null ? "N/A" : `${profitFactor.toFixed(2)}x`} (
              {winRate === null ? "N/A" : `${winRate.toFixed(1)}%`})
            </div>
            <div className="text-[10px] text-slate-500">
              {settled.length} Settled Clips
            </div>
          </div>

          <div className="rounded border border-slate-800 bg-[#030712] p-3 print:border-black/20 print:bg-slate-50">
            <span className="text-[10px] uppercase text-slate-400 print:text-slate-600">Current Drawdown</span>
            <div className="mt-1 text-base font-bold text-rose-300 print:text-black">
              -{formatPct(actualDrawdown)}
            </div>
            <div className="text-[10px] text-slate-500">
              Limit: {formatPct(toFiniteNumber(snapshot?.risk.max_drawdown_pct ?? 0))}
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-slate-800 bg-[#030712] p-4 space-y-2 print:border-black/20 print:bg-slate-50">
          <div className="flex items-center justify-between font-mono text-xs">
            <span className="font-semibold text-white print:text-black uppercase">
              Monthly Return Matrix
            </span>
            <span className="text-slate-400 text-[10px]">NET OF SIMULATED FEES & SLIPPAGE</span>
          </div>

          {months.length === 0 ? (
            <p className="font-mono text-[11px] text-slate-500">
              No closed trades yet. Monthly returns will appear once the paper ledger records
              settled positions.
            </p>
          ) : (
            <div className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-12 gap-1.5 font-mono text-xs">
              {months.map((m) => (
                <div
                  key={m.key}
                  className={`rounded border p-2 text-center transition ${
                    m.returnPct >= 0
                      ? "border-emerald-500/30 bg-emerald-950/30 text-emerald-300 print:border-emerald-700 print:text-emerald-800"
                      : "border-rose-500/30 bg-rose-950/30 text-rose-300 print:border-rose-700 print:text-rose-800"
                  }`}
                >
                  <div className="text-[10px] uppercase text-slate-400 print:text-slate-600">{m.label}</div>
                  <div className="mt-1 font-bold">
                    {m.returnPct > 0 ? "+" : ""}
                    {m.returnPct.toFixed(2)}%
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 font-mono text-xs">
          <div className="rounded-lg border border-slate-800 bg-[#030712] p-3 space-y-2 print:border-black/20 print:bg-slate-50">
            <span className="font-semibold text-white uppercase text-[11px] print:text-black">
              Risk & Volatility Ratios
            </span>
            <div className="divide-y divide-slate-800 text-[11px] print:divide-black/10">
              <div className="flex justify-between py-1.5 text-slate-400 print:text-slate-700">
                <span>Annualized Volatility (σ):</span>
                <span className="text-white print:text-black font-semibold">{fmt(annualizedVol, 2, "%")}</span>
              </div>
              <div className="flex justify-between py-1.5 text-slate-400 print:text-slate-700">
                <span>Calmar Ratio (Ann. Return / Drawdown):</span>
                <span className="text-cyan-300 print:text-black font-semibold">{fmt(calmar)}</span>
              </div>
              <div className="flex justify-between py-1.5 text-slate-400 print:text-slate-700">
                <span>Monthly VaR (95%):</span>
                <span className="text-rose-300 print:text-black font-semibold">{fmt(var95, 2, "%")}</span>
              </div>
              <div className="flex justify-between py-1.5 text-slate-400 print:text-slate-700">
                <span>Beta to Bitcoin:</span>
                <span className="text-slate-300 print:text-black font-semibold">N/A (no benchmark series)</span>
              </div>
            </div>
          </div>

          <div className="rounded-lg border border-slate-800 bg-[#030712] p-3 space-y-2 print:border-black/20 print:bg-slate-50">
            <span className="font-semibold text-white uppercase text-[11px] print:text-black">
              Execution & Safety Governance
            </span>
            <div className="divide-y divide-slate-800 text-[11px] print:divide-black/10">
              <div className="flex justify-between py-1.5 text-slate-400 print:text-slate-700">
                <span>Trading Engine Mode:</span>
                <span className="text-amber-300 font-semibold uppercase">PAPER (SIMULATED ONLY)</span>
              </div>
              <div className="flex justify-between py-1.5 text-slate-400 print:text-slate-700">
                <span>Live Key Access / Withdrawals:</span>
                <span className="text-emerald-400 font-semibold uppercase">HARD BLOCKED</span>
              </div>
              <div className="flex justify-between py-1.5 text-slate-400 print:text-slate-700">
                <span>Database Audit Trail:</span>
                <span className="text-cyan-300 font-semibold">
                  {snapshot?.engine_health.database_up ? "Connected" : "Unavailable"}
                </span>
              </div>
              <div className="flex justify-between py-1.5 text-slate-400 print:text-slate-700">
                <span>Circuit Breaker State:</span>
                <span className={`font-semibold ${killSwitchActive ? "text-rose-400" : "text-emerald-400"}`}>
                  {killSwitchActive ? "ENGAGED" : "ARMED"}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between border-t border-slate-800 pt-3 font-mono text-[10px] text-slate-500 print:border-black/20 print:text-slate-600">
          <span>NEXUS AI TRADER TERMINAL · PAPER LEDGER ONLY</span>
          <span>
            SIGNATURE: {snapshot?.portfolio.portfolio_id ?? "NO ACTIVE PORTFOLIO"}
          </span>
        </div>
      </div>
    </div>
  );
}
