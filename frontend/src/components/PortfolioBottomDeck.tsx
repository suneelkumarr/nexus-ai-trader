import type { TerminalSnapshotResponse } from "../types/system";
import {
  Activity,
  CheckCircle2,
  Coins,
  History,
  Layers,
  Percent,
  ShieldAlert,
  TrendingUp,
} from "lucide-react";
import {
  formatInr,
  formatPct,
  formatQty,
  formatUsdt,
  formatUtcTime,
  toFiniteNumber,
} from "../utils/format";

interface PortfolioBottomDeckProps {
  snapshot: TerminalSnapshotResponse | null;
}

export function PortfolioBottomDeck({ snapshot }: PortfolioBottomDeckProps) {
  const portfolio = snapshot?.portfolio;
  const risk = snapshot?.risk;
  const health = snapshot?.engine_health;

  const realizedPnl = portfolio?.realized_pnl_inr ?? 0;
  const unrealizedPnl = portfolio?.unrealized_pnl_inr ?? 0;

  return (
    <section className="space-y-4">
      {/* KPI Telemetry Strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-7">
        <div className="rounded-2xl border border-white/[0.08] bg-slate-900/60 p-3.5 backdrop-blur-xl shadow-lg transition-all hover:border-cyan-500/30">
          <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>Cash Balance</span>
            <Coins className="h-3.5 w-3.5 text-cyan-400" />
          </div>
          <div className="mt-1 font-mono text-base font-bold tabular-nums text-white">
            {portfolio ? formatInr(portfolio.cash_balance_inr) : "--"}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-slate-500">
            Init: {portfolio ? formatInr(portfolio.initial_capital_inr) : "₹10,000.00"}
          </div>
        </div>

        <div className="rounded-2xl border border-white/[0.08] bg-slate-900/60 p-3.5 backdrop-blur-xl shadow-lg transition-all hover:border-emerald-500/30">
          <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>Realized P&L</span>
            <TrendingUp className="h-3.5 w-3.5 text-emerald-400" />
          </div>
          <div
            className={`mt-1 font-mono text-base font-bold tabular-nums ${
              realizedPnl > 0
                ? "text-emerald-400"
                : realizedPnl < 0
                  ? "text-rose-400"
                  : "text-white"
            }`}
          >
            {portfolio ? formatInr(realizedPnl, true) : "--"}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-slate-500">
            Settled Spot Trades
          </div>
        </div>

        <div className="rounded-2xl border border-white/[0.08] bg-slate-900/60 p-3.5 backdrop-blur-xl shadow-lg transition-all hover:border-cyan-500/30">
          <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>Unrealized P&L</span>
            <Activity className="h-3.5 w-3.5 text-cyan-400" />
          </div>
          <div
            className={`mt-1 font-mono text-base font-bold tabular-nums ${
              unrealizedPnl > 0
                ? "text-emerald-400"
                : unrealizedPnl < 0
                  ? "text-rose-400"
                  : "text-white"
            }`}
          >
            {portfolio ? formatInr(unrealizedPnl, true) : "--"}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-slate-500">
            {portfolio?.quote_status === "live" ? "Live MTM Valuation" : "Cost Basis"}
          </div>
        </div>

        <div className="rounded-2xl border border-white/[0.08] bg-slate-900/60 p-3.5 backdrop-blur-xl shadow-lg transition-all hover:border-cyan-500/30">
          <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>Open Positions</span>
            <Layers className="h-3.5 w-3.5 text-cyan-400" />
          </div>
          <div className="mt-1 font-mono text-base font-bold tabular-nums text-cyan-300">
            {risk ? `${risk.open_positions_count} / ${risk.max_concurrent_positions}` : "--"}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-slate-500">
            Active Holdings
          </div>
        </div>

        <div className="rounded-2xl border border-white/[0.08] bg-slate-900/60 p-3.5 backdrop-blur-xl shadow-lg transition-all hover:border-amber-500/30">
          <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>Daily Drawdown</span>
            <ShieldAlert className="h-3.5 w-3.5 text-amber-400" />
          </div>
          <div
            className={`mt-1 font-mono text-base font-bold tabular-nums ${
              (risk?.daily_loss_pct ?? 0) >= (risk?.daily_loss_limit_pct ?? 2)
                ? "text-rose-400"
                : "text-amber-300"
            }`}
          >
            {risk ? formatPct(risk.daily_loss_pct) : "--"}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-slate-500">
            Cap: {risk ? formatPct(risk.daily_loss_limit_pct) : "2.00%"}
          </div>
        </div>

        <div className="rounded-2xl border border-white/[0.08] bg-slate-900/60 p-3.5 backdrop-blur-xl shadow-lg transition-all hover:border-blue-500/30">
          <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>Risk Budget</span>
            <Percent className="h-3.5 w-3.5 text-blue-400" />
          </div>
          <div className="mt-1 font-mono text-base font-bold tabular-nums text-blue-300">
            {risk ? formatPct(risk.risk_utilization_pct) : "--"}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-slate-500">
            Entries: {risk ? `${risk.daily_entries_count}/${risk.max_daily_entries}` : "--"}
          </div>
        </div>

        <div className="rounded-2xl border border-white/[0.08] bg-slate-900/60 p-3.5 backdrop-blur-xl shadow-lg transition-all hover:border-emerald-500/30">
          <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
            <span>Engine Health</span>
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          </div>
          <div
            className={`mt-1 font-mono text-base font-bold ${
              health?.overall_status === "ok"
                ? "text-emerald-400"
                : health
                  ? "text-amber-300"
                  : "text-slate-400"
            }`}
          >
            {health ? health.overall_status.toUpperCase() : "SYNCING"}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-slate-500">
            DB: {health?.database_up ? "UP" : "DOWN"} • Feed: {health?.market_feed_up ? "UP" : "DOWN"}
          </div>
        </div>
      </div>

      {/* Bottom Tables Grid: Open Positions + Recent Trade Ledger */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {/* Open Positions Table */}
        <div className="overflow-hidden rounded-2xl border border-white/[0.08] bg-slate-900/70 backdrop-blur-xl shadow-xl">
          <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3 sm:px-5">
            <h3 className="font-display text-xs font-bold uppercase tracking-wider text-white flex items-center gap-2">
              <Layers className="h-3.5 w-3.5 text-cyan-400" />
              Open Paper Spot Positions
            </h3>
            <span className="rounded-full bg-cyan-500/15 border border-cyan-500/30 px-2 py-0.5 font-mono text-[10px] font-bold text-cyan-300">
              {snapshot?.open_positions.length ?? 0} ACTIVE
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left font-mono text-xs">
              <thead className="border-b border-white/[0.06] bg-slate-950/60 text-[10px] uppercase text-slate-400">
                <tr>
                  <th className="px-4 py-2.5">Symbol</th>
                  <th className="px-4 py-2.5">Quantity</th>
                  <th className="px-4 py-2.5">Entry (USDT)</th>
                  <th className="px-4 py-2.5">Trailing Stop</th>
                  <th className="px-4 py-2.5 text-right">Cost (INR)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {!snapshot || snapshot.open_positions.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                      No open virtual spot positions.
                    </td>
                  </tr>
                ) : (
                  snapshot.open_positions.map((pos) => (
                    <tr key={pos.id} className="hover:bg-slate-800/40 transition-colors">
                      <td className="px-4 py-3 font-bold text-cyan-300">
                        {pos.symbol}
                      </td>
                      <td className="px-4 py-3 tabular-nums text-white">
                        {formatQty(pos.quantity)}
                      </td>
                      <td className="px-4 py-3 tabular-nums text-slate-200">
                        {formatUsdt(pos.avg_entry_price_usdt)}
                      </td>
                      <td className="px-4 py-3 tabular-nums text-amber-300">
                        {formatUsdt(pos.trailing_stop_price_usdt)}
                      </td>
                      <td className="px-4 py-3 tabular-nums text-right font-semibold text-white">
                        {formatInr(pos.entry_cost_inr)}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Recent Trade History Table */}
        <div className="overflow-hidden rounded-2xl border border-white/[0.08] bg-slate-900/70 backdrop-blur-xl shadow-xl">
          <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3 sm:px-5">
            <h3 className="font-display text-xs font-bold uppercase tracking-wider text-white flex items-center gap-2">
              <History className="h-3.5 w-3.5 text-emerald-400" />
              Settled Roundtrip Ledger
            </h3>
            <span className="font-mono text-[10px] text-slate-400">
              {snapshot?.recent_trades.length ?? 0} RECORDED
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left font-mono text-xs">
              <thead className="border-b border-white/[0.06] bg-slate-950/60 text-[10px] uppercase text-slate-400">
                <tr>
                  <th className="px-4 py-2.5">Symbol</th>
                  <th className="px-4 py-2.5">Exit Reason</th>
                  <th className="px-4 py-2.5">Net P&L</th>
                  <th className="px-4 py-2.5">Fees</th>
                  <th className="px-4 py-2.5 text-right">Closed At</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {!snapshot || snapshot.recent_trades.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-slate-500">
                      No settled paper trades in persistent ledger.
                    </td>
                  </tr>
                ) : (
                  snapshot.recent_trades.map((trade) => {
                    const pnl = toFiniteNumber(trade.realized_pnl_inr);
                    const isProfit = pnl >= 0;

                    return (
                      <tr key={trade.id} className="hover:bg-slate-800/40 transition-colors">
                        <td className="px-4 py-3 font-bold text-white">
                          {trade.symbol}
                        </td>
                        <td className="px-4 py-3 text-slate-300 max-w-[160px] truncate" title={trade.exit_reason}>
                          {trade.exit_reason}
                        </td>
                        <td
                          className={`px-4 py-3 tabular-nums font-bold ${
                            isProfit ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {formatInr(pnl, true)}
                        </td>
                        <td className="px-4 py-3 tabular-nums text-slate-400">
                          {formatInr(trade.total_fees_inr)}
                        </td>
                        <td className="px-4 py-3 text-[11px] text-slate-500 text-right">
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
    </section>
  );
}
