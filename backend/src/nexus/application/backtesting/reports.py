"""Deterministic HTML and JSON report generation for NEXUS backtest results."""

import html
import json
from decimal import Decimal
from pathlib import Path

from nexus.application.backtesting.models import (
    BacktestRunResult,
    BacktestSuiteReport,
    EquityPoint,
)


def _render_equity_svg(equity_curve: list[EquityPoint], *, title: str) -> str:
    """Render an inline SVG comparing Net Strategy Equity vs Buy-and-Hold Benchmark."""
    width = 760
    height = 220
    pad = 24
    if len(equity_curve) < 2:
        return (
            f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">'
            '<rect width="100%" height="100%" fill="#0f172a" rx="8"/>'
            '<text x="30" y="110" fill="#94a3b8" font-size="13">'
            f"Insufficient points for equity chart ({html.escape(title)})</text></svg>"
        )

    strat_vals = [float(p.equity_inr) for p in equity_curve]
    bench_vals = [float(p.benchmark_equity_inr) for p in equity_curve]
    all_vals = strat_vals + bench_vals
    min_v = min(all_vals)
    max_v = max(all_vals)
    span = max(max_v - min_v, 1.0)

    def _points(series: list[float]) -> str:
        n = len(series) - 1
        coords: list[str] = []
        for idx, val in enumerate(series):
            x = pad + (idx / max(n, 1)) * (width - 2 * pad)
            y = height - pad - ((val - min_v) / span) * (height - 2 * pad)
            coords.append(f"{x:.2f},{y:.2f}")
        return " ".join(coords)

    strat_pts = _points(strat_vals)
    bench_pts = _points(bench_vals)
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="{html.escape(title)} Equity Curve">'
        '<rect width="100%" height="100%" fill="#0f172a" rx="8"/>'
        f'<polyline fill="none" stroke="#64748b" stroke-width="1.8" '
        f'stroke-dasharray="5,4" points="{bench_pts}"/>'
        f'<polyline fill="none" stroke="#38bdf8" stroke-width="2.4" points="{strat_pts}"/>'
        f'<text x="24" y="18" fill="#e2e8f0" font-size="12" font-family="monospace">'
        f"{html.escape(title)} | Blue: Strategy Net Equity | Dashed: Buy &amp; Hold | "
        f"Range: INR {min_v:.2f}–{max_v:.2f}</text></svg>"
    )


def _format_pf(val: float | None) -> str:
    return "Infinity (0 losses)" if val is None else f"{val:.3f}"


def _render_run_section(run: BacktestRunResult, heading: str) -> str:
    m = run.metrics
    b = run.benchmark
    bm = b.benchmark_metrics
    fi = m.fee_impact
    svg_chart = _render_equity_svg(run.equity_curve, title=heading)

    trade_rows = "\n".join(
        f"<tr>"
        f"<td>{t.trade_index}</td>"
        f"<td>{html.escape(t.entry_filled_at.isoformat())}</td>"
        f"<td>{html.escape(t.exit_filled_at.isoformat())}</td>"
        f"<td>{t.quantity}</td>"
        f"<td>{t.entry_exec_price_usdt}</td>"
        f"<td>{t.exit_exec_price_usdt}</td>"
        f"<td>{html.escape(t.entry_liquidity)}/{html.escape(t.exit_liquidity)}</td>"
        f"<td>{t.gross_pnl_inr}</td>"
        f"<td>{t.total_fees_inr + t.total_spread_cost_inr + t.total_slippage_cost_inr}</td>"
        f"<td><strong>{t.net_pnl_inr}</strong></td>"
        f"<td>{t.holding_seconds / 3600.0:.2f}h</td>"
        f"<td>{html.escape(t.exit_reason)}</td>"
        f"</tr>"
        for t in run.trades
    )
    if not trade_rows:
        trade_rows = '<tr><td colspan="12">No closed trades executed in this split.</td></tr>'

    return f"""
    <section class="card">
      <h2>{html.escape(heading)} ({html.escape(run.split.split_name.upper())})</h2>
      <p class="meta">
        Window: {html.escape(run.split.start_timestamp.isoformat())} to
        {html.escape(run.split.end_timestamp.isoformat())} |
        Scored Bars: {run.split.scored_bars_count} |
        Causal Warmup Bars: {run.split.warmup_bars_count} |
        Risk-Rejected Signals: {run.rejected_signals_count}
      </p>
      <div class="kpi-grid">
        <div class="kpi">
          <span>Net Total Return</span><strong>{m.total_return_pct:.2f}%</strong>
        </div>
        <div class="kpi">
          <span>Net Profit (INR)</span><strong>{m.net_profit_inr}</strong>
        </div>
        <div class="kpi">
          <span>Gross Return / Profit</span>
          <strong>{m.gross_return_pct:.2f}% / {m.gross_profit_inr}</strong>
        </div>
        <div class="kpi">
          <span>Total Cost Drag</span>
          <strong>
            {fi.total_execution_drag_inr} INR
            ({fi.fee_drag_pct_of_initial_capital:.2f}%)
          </strong>
        </div>
        <div class="kpi"><span>Win Rate</span><strong>{m.win_rate_pct:.2f}%</strong></div>
        <div class="kpi">
          <span>Profit Factor</span><strong>{_format_pf(m.profit_factor)}</strong>
        </div>
        <div class="kpi"><span>Max Drawdown</span><strong>{m.max_drawdown_pct:.2f}%</strong></div>
        <div class="kpi"><span>Sharpe Ratio</span><strong>{m.sharpe_ratio:.3f}</strong></div>
        <div class="kpi">
          <span>Avg Holding Time</span>
          <strong>{m.avg_holding_time_hours:.2f}h ({m.avg_holding_time_seconds:.0f}s)</strong>
        </div>
        <div class="kpi"><span>Trades Count</span><strong>{m.number_of_trades}</strong></div>
      </div>

      <h3>Fee, Spread &amp; Slippage Impact (Gross &ne; Net)</h3>
      <table>
        <thead>
          <tr>
            <th>Maker/Taker Fees (INR)</th><th>Spread Cost (INR)</th>
            <th>Slippage Cost (INR)</th><th>Total Execution Drag (INR)</th>
            <th>Gross &minus; Net Delta (INR)</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>{fi.total_fees_inr}</td>
            <td>{fi.total_spread_cost_inr}</td>
            <td>{fi.total_slippage_cost_inr}</td>
            <td><strong>{fi.total_execution_drag_inr}</strong></td>
            <td>{fi.gross_minus_net_inr}</td>
          </tr>
        </tbody>
      </table>

      <h3>Strategy (Net) vs Spot Buy-and-Hold Benchmark (Net)</h3>
      <table>
        <thead>
          <tr>
            <th>Metric</th><th>NEXUS Strategy (Net)</th>
            <th>Buy &amp; Hold (Net)</th><th>Difference</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Total Return</td><td>{m.total_return_pct:.2f}%</td>
            <td>{bm.total_return_pct:.2f}%</td><td>{b.excess_net_return_pct:+.2f}%</td>
          </tr>
          <tr>
            <td>Net Profit (INR)</td><td>{m.net_profit_inr}</td>
            <td>{bm.net_profit_inr}</td><td>{b.excess_net_profit_inr:+}</td>
          </tr>
          <tr>
            <td>Max Drawdown</td><td>{m.max_drawdown_pct:.2f}%</td>
            <td>{bm.max_drawdown_pct:.2f}%</td><td>{b.drawdown_difference_pct:+.2f}%</td>
          </tr>
          <tr>
            <td>Sharpe Ratio</td><td>{m.sharpe_ratio:.3f}</td>
            <td>{bm.sharpe_ratio:.3f}</td><td>{b.sharpe_difference:+.3f}</td>
          </tr>
        </tbody>
      </table>

      <div class="chart">{svg_chart}</div>

      <h3>Executed Round-Trip Trades</h3>
      <table>
        <thead>
          <tr>
            <th>#</th><th>Entry (UTC)</th><th>Exit (UTC)</th><th>Qty</th>
            <th>Entry Price</th><th>Exit Price</th><th>Liquidity</th>
            <th>Gross PnL</th><th>Total Drag</th><th>Net PnL (INR)</th>
            <th>Held</th><th>Exit Reason</th>
          </tr>
        </thead>
        <tbody>
          {trade_rows}
        </tbody>
      </table>
    </section>
    """


class BacktestReportGenerator:
    """Generates reproducible JSON and self-contained HTML reports for backtest runs."""

    def to_json(self, report: BacktestSuiteReport | BacktestRunResult) -> str:
        """Serialize report into canonical deterministic JSON string."""
        payload = report.model_dump(mode="json")
        return json.dumps(payload, sort_keys=True, indent=2)

    def write_json(self, report: BacktestSuiteReport | BacktestRunResult, path: Path) -> Path:
        """Write deterministic JSON report to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(report), encoding="utf-8")
        return path

    def to_html(self, report: BacktestSuiteReport | BacktestRunResult) -> str:
        """Render complete self-contained HTML report with KPI cards and equity charts."""
        if isinstance(report, BacktestRunResult):
            title = f"NEXUS Backtest Report — {report.symbol} ({report.timeframe})"
            body = _render_run_section(report, f"{report.symbol} ({report.timeframe})")
            meta_line = (
                f"Spot Paper Simulation | Maker {report.backtest_config.maker_fee_bps} bps | "
                f"Taker {report.backtest_config.taker_fee_bps} bps | "
                f"Spread {report.backtest_config.spread_bps} bps | "
                f"Slippage {report.backtest_config.slippage_bps} bps"
            )
        else:
            title = f"NEXUS Out-of-Sample Suite Report — {report.symbol} ({report.timeframe})"
            meta_line = (
                f"Report ID: {html.escape(report.report_id)} | "
                f"Generated At: {html.escape(report.generated_at.isoformat())} | "
                f"Optimized Strictly On: {', '.join(report.optimized_on_splits)} | "
                f"Out-of-Sample Verified: {report.out_of_sample_verified}"
            )
            summary_rows = ""
            for label, res in (
                ("Training Split", report.train_result),
                ("Validation Split", report.validation_result),
                ("Out-of-Sample Test Split", report.test_result),
            ):
                rm = res.metrics
                summary_rows += (
                    f"<tr><td><strong>{label}</strong></td>"
                    f"<td>{res.split.scored_bars_count}</td>"
                    f"<td>{rm.number_of_trades}</td>"
                    f"<td>{rm.total_return_pct:.2f}%</td>"
                    f"<td>{rm.net_profit_inr}</td>"
                    f"<td>{res.benchmark.benchmark_metrics.total_return_pct:.2f}%</td>"
                    f"<td>{rm.max_drawdown_pct:.2f}%</td>"
                    f"<td>{rm.sharpe_ratio:.3f}</td>"
                    f"<td>{rm.fee_impact.total_execution_drag_inr}</td></tr>"
                )
            body = (
                f"""
                <section class="card">
                  <h2>Train / Validation / Out-of-Sample Test Comparison</h2>
                  <p class="meta">Parameters frozen strictly prior to final Test evaluation;
                  gross returns are never reported as net returns.</p>
                  <table>
                    <thead>
                      <tr>
                        <th>Split</th><th>Bars</th><th>Trades</th><th>Net Return</th>
                        <th>Net Profit (INR)</th><th>Buy&amp;Hold Net Return</th>
                        <th>Max Drawdown</th><th>Sharpe</th><th>Cost Drag (INR)</th>
                      </tr>
                    </thead>
                    <tbody>{summary_rows}</tbody>
                  </table>
                </section>
                """
                + _render_run_section(report.test_result, "Out-of-Sample Final Test Period")
                + _render_run_section(report.validation_result, "Validation Period")
                + _render_run_section(report.train_result, "Training Period")
            )

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           background: #020617; color: #e2e8f0; margin: 0; padding: 24px; }}
    h1 {{ margin: 0 0 8px 0; color: #38bdf8; }}
    h2 {{ margin-top: 0; color: #f8fafc; }}
    h3 {{ color: #cbd5e1; margin-top: 20px; }}
    .meta {{ color: #94a3b8; font-size: 13px; margin-bottom: 16px; }}
    .card {{ background: #0f172a; border: 1px solid #1e293b; border-radius: 10px;
             padding: 20px; margin-bottom: 24px; }}
    .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
                 gap: 12px; margin-bottom: 16px; }}
    .kpi {{ background: #1e293b; border-radius: 8px; padding: 10px 12px; }}
    .kpi span {{ display: block; font-size: 11px; color: #94a3b8; text-transform: uppercase; }}
    .kpi strong {{ font-size: 16px; color: #f8fafc; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 8px; }}
    th, td {{ border-bottom: 1px solid #1e293b; padding: 8px 10px; text-align: left; }}
    th {{ background: #1e293b; color: #cbd5e1; }}
    .chart {{ margin: 18px 0; }}
    .disclaimer {{ font-size: 12px; color: #94a3b8; border-top: 1px solid #1e293b;
                   padding-top: 12px; margin-top: 24px; }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(title)}</h1>
    <p class="meta">{meta_line}</p>
  </header>
  {body}
  <footer class="disclaimer">
    Simulated historical spot paper-trading report (INR {Decimal("10000.00")} virtual baseline).
    Past simulated results do not guarantee future profitability.
  </footer>
</body>
</html>
"""

    def write_html(self, report: BacktestSuiteReport | BacktestRunResult, path: Path) -> Path:
        """Write deterministic HTML report to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_html(report), encoding="utf-8")
        return path
