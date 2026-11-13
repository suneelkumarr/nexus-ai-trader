import type { TerminalSnapshotResponse } from "../types/system";
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
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        <div className="nexus-panel rounded-lg p-3">
          <div className="font-mono text-[10px] uppercase text-slate-400">
            Virtual Balance
          </div>
          <div className="mt-1 font-mono text-base font-semibold tabular-nums text-white">
            {portfolio ? formatInr(portfolio.cash_balance_inr) : "--"}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-slate-500">
            Init: {portfolio ? formatInr(portfolio.initial_capital_inr) : "₹10,000.00"}
          </div>
        </div>

        <div className="nexus-panel rounded-lg p-3">
          <div className="font-mono text-[10px] uppercase text-slate-400">
            Realized P&L
          </div>
          <div
            className={`mt-1 font-mono text-base font-semibold tabular-nums ${
              realizedPnl > 0
                ? "text-emerald-300"
                : realizedPnl < 0
                  ? "text-rose-300"
                  : "text-white"
            }`}
          >
            {portfolio ? formatInr(realizedPnl, true) : "--"}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-slate-500">
            Settled Trades
          </div>
        </div>

        <div className="nexus-panel rounded-lg p-3">
          <div className="font-mono text-[10px] uppercase text-slate-400">
            Unrealized P&L
          </div>
          <div
            className={`mt-1 font-mono text-base font-semibold tabular-nums ${
              unrealizedPnl > 0
                ? "text-emerald-300"
                : unrealizedPnl < 0
                  ? "text-rose-300"
                  : "text-white"
            }`}
          >
            {portfolio ? formatInr(unrealizedPnl, true) : "--"}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-slate-500">
            {portfolio?.quote_status === "live" ? "Live MTM" : "At Cost Basis"}
          </div>
        </div>

        <div className="nexus-panel rounded-lg p-3">
          <div className="font-mono text-[10px] uppercase text-slate-400">
            Open Positions
          </div>
          <div className="mt-1 font-mono text-base font-semibold tabular-nums text-cyan-300">
            {risk ? `${risk.open_positions_count} / ${risk.max_concurrent_positions}` : "--"}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-slate-500">
            Spot Long Only
          </div>
        </div>

        <div className="nexus-panel rounded-lg p-3">
          <div className="font-mono text-[10px] uppercase text-slate-400">
            Daily Drawdown
          </div>
          <div
            className={`mt-1 font-mono text-base font-semibold tabular-nums ${
              (risk?.daily_loss_pct ?? 0) >= (risk?.daily_loss_limit_pct ?? 2)
                ? "text-rose-300"
                : "text-amber-300"
            }`}
          >
            {risk ? formatPct(risk.daily_loss_pct) : "--"}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-slate-500">
            Limit: {risk ? formatPct(risk.daily_loss_limit_pct) : "2.00%"}
          </div>
        </div>

        <div className="nexus-panel rounded-lg p-3">
          <div className="font-mono text-[10px] uppercase text-slate-400">
            Risk Utilization
          </div>
          <div className="mt-1 font-mono text-base font-semibold tabular-nums text-blue-300">
            {risk ? formatPct(risk.risk_utilization_pct) : "--"}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-slate-500">
            Entries: {risk ? `${risk.daily_entries_count}/${risk.max_daily_entries}` : "--"}
          </div>
        </div>

        <div className="nexus-panel rounded-lg p-3">
          <div className="font-mono text-[10px] uppercase text-slate-400">
            Engine Health
          </div>
          <div
            className={`mt-1 font-mono text-base font-semibold ${
              health?.overall_status === "ok"
                ? "text-emerald-300"
                : health
                  ? "text-amber-300"
                  : "text-slate-400"
            }`}
          >
            {health ? health.overall_status.toUpperCase() : "WAIT"}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-slate-500">
            DB {health?.database_up ? "OK" : "ERR"} · Feed {health?.market_feed_up ? "OK" : "ERR"}
          </div>
        </div>
      </div>

      {/* Bottom Tables Grid: Open Positions + Recent Trade Ledger */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {/* Open Positions Table */}
        <div className="nexus-panel overflow-hidden rounded-lg">
          <div className="flex items-center justify-between border-b border-cyan-500/15 px-4 py-2.5">
            <h3 className="font-display text-xs font-semibold uppercase tracking-wider text-white">
              Open Paper Positions
            </h3>
            <span className="font-mono text-[10px] text-cyan-300">
              {snapshot?.open_positions.length ?? 0} ACTIVE
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left font-mono text-xs">
              <thead className="border-b border-slate-800/90 bg-nexus-void/70 text-[10px] uppercase text-slate-400">
                <tr>
                  <th className="px-3 py-2">Symbol</th>
                  <th className="px-3 py-2">Qty</th>
                  <th className="px-3 py-2">Entry (USDT)</th>
                  <th className="px-3 py-2">Trailing Stop</th>
                  <th className="px-3 py-2">Cost (INR)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {!snapshot || snapshot.open_positions.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-3 py-6 text-center text-slate-500">
                      No open virtual spot positions.
                    </td>
                  </tr>
                ) : (
                  snapshot.open_positions.map((pos) => (
                    <tr key={pos.id} className="hover:bg-cyan-500/5">
                      <td className="px-3 py-2 font-semibold text-cyan-300">
                        {pos.symbol}
                      </td>
                      <td className="px-3 py-2 tabular-nums text-white">
                        {formatQty(pos.quantity)}
                      </td>
                      <td className="px-3 py-2 tabular-nums text-slate-200">
                        {formatUsdt(pos.avg_entry_price_usdt)}
                      </td>
                      <td className="px-3 py-2 tabular-nums text-amber-300">
                        {formatUsdt(pos.trailing_stop_price_usdt)}
                      </td>
                      <td className="px-3 py-2 tabular-nums text-white">
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
        <div className="nexus-panel overflow-hidden rounded-lg">
          <div className="flex items-center justify-between border-b border-cyan-500/15 px-4 py-2.5">
            <h3 className="font-display text-xs font-semibold uppercase tracking-wider text-white">
              Recent Paper Trade Ledger
            </h3>
            <span className="font-mono text-[10px] text-slate-400">
              {snapshot?.recent_trades.length ?? 0} RECORDED
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left font-mono text-xs">
              <thead className="border-b border-slate-800/90 bg-nexus-void/70 text-[10px] uppercase text-slate-400">
                <tr>
                  <th className="px-3 py-2">Symbol</th>
                  <th className="px-3 py-2">Reason</th>
                  <th className="px-3 py-2">Net P&L (INR)</th>
                  <th className="px-3 py-2">Fees</th>
                  <th className="px-3 py-2">Closed</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/70">
                {!snapshot || snapshot.recent_trades.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-3 py-6 text-center text-slate-500">
                      No settled paper trades in persistent ledger.
                    </td>
                  </tr>
                ) : (
                  snapshot.recent_trades.map((trade) => {
                    const pnl = toFiniteNumber(trade.realized_pnl_inr);
                    return (
                      <tr key={trade.id} className="hover:bg-cyan-500/5">
                        <td className="px-3 py-2 font-semibold text-white">
                          {trade.symbol}
                        </td>
                        <td className="px-3 py-2 text-slate-300">
                          {trade.exit_reason}
                        </td>
                        <td
                          className={`px-3 py-2 tabular-nums font-semibold ${
                            pnl > 0
                              ? "text-emerald-300"
                              : pnl < 0
                                ? "text-rose-300"
                                : "text-slate-300"
                          }`}
                        >
                          {formatInr(pnl, true)}
                        </td>
                        <td className="px-3 py-2 tabular-nums text-slate-400">
                          {formatInr(trade.total_fees_inr)}
                        </td>
                        <td className="px-3 py-2 text-[11px] text-slate-400">
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

