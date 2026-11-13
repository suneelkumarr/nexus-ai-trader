import { useEffect, useMemo, useState } from "react";
import { X, Scale, CheckCircle2, AlertTriangle, RefreshCw } from "lucide-react";
import { fetchPortfolioStatistics } from "../../services/apiClient";
import type {
  AssetStatistics,
  PortfolioStatisticsResponse,
} from "../../types/system";

interface PortfolioOptimizerModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface FrontierPoint {
  returnPct: number;
  volatilityPct: number;
  sharpe: number;
  weights: Record<string, number>;
}

const RISK_FREE_RATE = 4.5;
const ASSET_COLORS = ["#22d3ee", "#a78bfa", "#f59e0b", "#34d399"];

function correlationBetween(
  stats: PortfolioStatisticsResponse,
  left: string,
  right: string,
): number {
  if (left === right) return 1;
  const pair = stats.correlations.find(
    (item) =>
      (item.left === left && item.right === right) ||
      (item.left === right && item.right === left),
  );
  return pair ? pair.correlation : 0;
}

function portfolioMetrics(
  stats: PortfolioStatisticsResponse,
  weights: Record<string, number>,
): { expectedReturn: number; volatility: number; sharpe: number } {
  const assets = stats.assets.slice(0, 3);
  const total = assets.reduce((acc, asset) => acc + (weights[asset.symbol] ?? 0), 0);
  if (total <= 0 || assets.length === 0) {
    return { expectedReturn: 0, volatility: 0, sharpe: 0 };
  }

  let expectedReturn = 0;
  let variance = 0;
  for (const asset of assets) {
    const w = (weights[asset.symbol] ?? 0) / total;
    expectedReturn += w * asset.annualized_return_pct;
  }
  for (const left of assets) {
    const wl = (weights[left.symbol] ?? 0) / total;
    for (const right of assets) {
      const wr = (weights[right.symbol] ?? 0) / total;
      variance +=
        wl *
        wr *
        left.annualized_volatility_pct *
        right.annualized_volatility_pct *
        correlationBetween(stats, left.symbol, right.symbol);
    }
  }
  const volatility = Math.sqrt(Math.max(variance, 0));
  const sharpe = volatility > 0 ? (expectedReturn - RISK_FREE_RATE) / volatility : 0;
  return { expectedReturn, volatility, sharpe };
}

function buildFrontier(stats: PortfolioStatisticsResponse): FrontierPoint[] {
  const assets = stats.assets.slice(0, 3);
  if (assets.length < 2) return [];
  const steps = 20;
  const points: Array<{
    expectedReturn: number;
    volatility: number;
    sharpe: number;
    weights: Record<string, number>;
  }> = [];

  const walk = (index: number, remaining: number, weights: Record<string, number>) => {
    if (index === assets.length - 1) {
      const finalWeights = { ...weights, [assets[index].symbol]: remaining };
      const metrics = portfolioMetrics(stats, finalWeights);
      points.push({ ...metrics, weights: finalWeights });
      return;
    }
    for (let step = 0; step <= remaining; step += 1) {
      walk(index + 1, remaining - step, {
        ...weights,
        [assets[index].symbol]: step,
      });
    }
  };
  walk(0, steps, {});

  const normalized: FrontierPoint[] = points.map((point) => {
    const total = Object.values(point.weights).reduce((acc, value) => acc + value, 0);
    const weights = Object.fromEntries(
      Object.entries(point.weights).map(([symbol, value]) => [
        symbol,
        total > 0 ? (value / total) * 100 : 0,
      ]),
    );
    const metrics = portfolioMetrics(stats, weights);
    return {
      returnPct: metrics.expectedReturn,
      volatilityPct: metrics.volatility,
      sharpe: metrics.sharpe,
      weights,
    };
  });

  normalized.sort((a, b) => a.volatilityPct - b.volatilityPct);
  const frontier: FrontierPoint[] = [];
  let bestReturn = Number.NEGATIVE_INFINITY;
  for (const point of normalized) {
    if (point.returnPct > bestReturn) {
      frontier.push(point);
      bestReturn = point.returnPct;
    }
  }
  return frontier;
}

export function PortfolioOptimizerModal({
  isOpen,
  onClose,
}: PortfolioOptimizerModalProps) {
  const [stats, setStats] = useState<PortfolioStatisticsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [weights, setWeights] = useState<Record<string, number>>({});
  const [adoptedMessage, setAdoptedMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetchPortfolioStatistics();
        if (cancelled) return;
        setStats(response);
        if (response.available && response.assets.length >= 2) {
          const selected = response.assets.slice(0, 3);
          const equal = 100 / selected.length;
          setWeights(
            Object.fromEntries(selected.map((asset) => [asset.symbol, equal])),
          );
        }
      } catch (err) {
        if (!cancelled) {
          setStats(null);
          setError(err instanceof Error ? err.message : "Failed to load portfolio statistics");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  const assets: AssetStatistics[] = useMemo(
    () => (stats?.available ? stats.assets.slice(0, 3) : []),
    [stats],
  );

  const frontier = useMemo(
    () => (stats?.available ? buildFrontier(stats) : []),
    [stats],
  );

  const maxSharpe = useMemo(() => {
    if (frontier.length === 0) return null;
    return frontier.reduce((best, point) =>
      point.sharpe > best.sharpe ? point : best,
    );
  }, [frontier]);

  const minVariance = useMemo(() => {
    if (frontier.length === 0) return null;
    return frontier.reduce((best, point) =>
      point.volatilityPct < best.volatilityPct ? point : best,
    );
  }, [frontier]);

  const current = useMemo(() => {
    if (!stats?.available || assets.length === 0) return null;
    const total = assets.reduce((acc, asset) => acc + (weights[asset.symbol] ?? 0), 0);
    const normalized = Object.fromEntries(
      assets.map((asset) => [
        asset.symbol,
        total > 0 ? ((weights[asset.symbol] ?? 0) / total) * 100 : 0,
      ]),
    );
    return { weights: normalized, ...portfolioMetrics(stats, weights) };
  }, [stats, assets, weights]);

  const totalWeight = assets.reduce(
    (acc, asset) => acc + (weights[asset.symbol] ?? 0),
    0,
  );

  const width = 520;
  const height = 180;
  const pad = 30;
  const plotPoints = useMemo(() => {
    const series = [...frontier];
    if (current) {
      series.push({
        returnPct: current.expectedReturn,
        volatilityPct: current.volatility,
        sharpe: current.sharpe,
        weights: current.weights,
      });
    }
    if (series.length === 0) return null;
    const vols = series.map((point) => point.volatilityPct);
    const rets = series.map((point) => point.returnPct);
    const minX = Math.min(...vols);
    const maxX = Math.max(...vols);
    const minY = Math.min(...rets);
    const maxY = Math.max(...rets);
    const spanX = maxX - minX || 1;
    const spanY = maxY - minY || 1;
    const toCoords = (vol: number, ret: number) => ({
      x: pad + ((vol - minX) / spanX) * (width - pad * 2),
      y: height - pad - ((ret - minY) / spanY) * (height - pad * 2),
    });
    return { minX, maxX, minY, maxY, toCoords };
  }, [frontier, current]);

  const frontierPath = useMemo(() => {
    if (!plotPoints) return "";
    return frontier
      .map((point, index) => {
        const { x, y } = plotPoints.toCoords(point.volatilityPct, point.returnPct);
        return `${index === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ");
  }, [frontier, plotPoints]);

  const applyPreset = (point: FrontierPoint, name: string) => {
    setWeights(point.weights);
    setAdoptedMessage(`Applied ${name} allocation.`);
    window.setTimeout(() => setAdoptedMessage(null), 3000);
  };

  const handleWeightChange = (symbol: string, value: number) => {
    setWeights((prev) => ({ ...prev, [symbol]: value }));
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-3 backdrop-blur-md overflow-y-auto">
      <div className="nexus-panel max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-xl border border-cyan-500/40 bg-[#040816] p-6 shadow-2xl space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-cyan-500/20 pb-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-500/20 border border-cyan-400 text-cyan-300">
              <Scale className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-display text-lg font-bold tracking-wider text-white">
                  MARKOWITZ EFFICIENT FRONTIER
                </h2>
                <span className="rounded bg-cyan-950 px-2 py-0.5 font-mono text-[10px] text-cyan-300 border border-cyan-500/40 uppercase font-bold">
                  MEAN-VARIANCE OPTIMIZER
                </span>
              </div>
              <p className="font-mono text-xs text-slate-400">
                Derived from stored OHLCV returns · assumption: {RISK_FREE_RATE.toFixed(1)}% annual risk-free rate
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-700 bg-slate-800 p-1.5 text-slate-400 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {loading && (
          <div className="nexus-panel flex min-h-[180px] items-center justify-center rounded-lg border border-slate-800 font-mono text-xs text-cyan-300">
            <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
            Loading verified return and correlation history...
          </div>
        )}

        {!loading && (error || !stats?.available) && (
          <div className="nexus-panel rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 font-mono text-xs text-amber-200">
            <div className="flex items-center gap-2 font-semibold">
              <AlertTriangle className="h-4 w-4" />
              Portfolio statistics unavailable
            </div>
            <p className="mt-2 text-amber-200/80">
              {error ??
                stats?.reason ??
                "Insufficient persisted candle history. Sync candles from the Backtesting tab and retry."}
            </p>
          </div>
        )}

        {!loading && stats?.available && assets.length >= 2 && current && plotPoints && (
          <>
            <div className="nexus-panel rounded-lg p-4 space-y-2 border border-slate-800 bg-[#030712]">
              <div className="flex flex-wrap items-center justify-between text-xs font-mono">
                <span className="font-semibold text-white uppercase">
                  Efficient Frontier (Risk σ vs Return E[R])
                </span>
                <span className="text-[10px] text-slate-400">
                  {stats.timeframe.toUpperCase()} · {stats.observations} return observations
                </span>
              </div>

              <svg
                viewBox={`0 0 ${width} ${height}`}
                className="h-44 w-full rounded border border-slate-800 bg-nexus-void/90 shadow-inner"
                role="img"
                aria-label="Markowitz efficient frontier derived from historical returns"
              >
                <line x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} stroke="#1e293b" />
                <line x1={pad} y1={pad} x2={pad} y2={height - pad} stroke="#1e293b" />

                {frontier.map((point, index) => {
                  const { x, y } = plotPoints.toCoords(point.volatilityPct, point.returnPct);
                  return <circle key={`grid-${index}`} cx={x} cy={y} r="1.6" fill="#0e7490" />;
                })}

                <path
                  d={frontierPath}
                  fill="none"
                  stroke="#22d3ee"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  className="drop-shadow-[0_0_8px_rgba(34,211,238,0.4)]"
                />

                {minVariance && (
                  <circle
                    cx={plotPoints.toCoords(minVariance.volatilityPct, minVariance.returnPct).x}
                    cy={plotPoints.toCoords(minVariance.volatilityPct, minVariance.returnPct).y}
                    r="4.5"
                    fill="#0891b2"
                    stroke="#ffffff"
                    strokeWidth="1.5"
                  />
                )}
                {maxSharpe && (
                  <circle
                    cx={plotPoints.toCoords(maxSharpe.volatilityPct, maxSharpe.returnPct).x}
                    cy={plotPoints.toCoords(maxSharpe.volatilityPct, maxSharpe.returnPct).y}
                    r="5.5"
                    fill="#10b981"
                    stroke="#ffffff"
                    strokeWidth="1.8"
                  />
                )}
                <circle
                  cx={plotPoints.toCoords(current.volatility, current.expectedReturn).x}
                  cy={plotPoints.toCoords(current.volatility, current.expectedReturn).y}
                  r="5.5"
                  fill="#f59e0b"
                  stroke="#ffffff"
                  strokeWidth="2"
                />

                <text x={pad} y={height - 6} fill="#64748b" fontSize="8" fontFamily="monospace">
                  Low risk ({plotPoints.minX.toFixed(1)}% σ)
                </text>
                <text x={width - pad} y={height - 6} fill="#64748b" fontSize="8" fontFamily="monospace" textAnchor="end">
                  High risk ({plotPoints.maxX.toFixed(1)}% σ)
                </text>
                <text x={pad + 4} y={pad + 4} fill="#64748b" fontSize="8" fontFamily="monospace">
                  {plotPoints.maxY.toFixed(1)}% E[R]
                </text>
              </svg>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="nexus-panel rounded-lg p-4 space-y-3">
                <span className="font-display text-sm font-semibold uppercase tracking-wider text-white">
                  Historical Asset Statistics
                </span>
                <div className="space-y-2 font-mono text-xs">
                  {assets.map((asset, index) => (
                    <div
                      key={asset.symbol}
                      className="rounded border border-slate-800 bg-[#030712] p-2.5"
                    >
                      <div className="flex items-center justify-between font-bold" style={{ color: ASSET_COLORS[index] }}>
                        <span>{asset.symbol}</span>
                        <span>{asset.observations} obs</span>
                      </div>
                      <div className="mt-1 flex justify-between text-[11px] text-slate-300">
                        <span>E[R] {asset.annualized_return_pct.toFixed(2)}%</span>
                        <span>σ {asset.annualized_volatility_pct.toFixed(2)}%</span>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="flex flex-wrap gap-2 pt-1 font-mono text-xs">
                  {maxSharpe && (
                    <button
                      type="button"
                      onClick={() => applyPreset(maxSharpe, "Max Sharpe")}
                      className="flex-1 rounded border border-emerald-500/30 bg-emerald-950/20 p-2 text-emerald-300 hover:border-emerald-500/60"
                    >
                      Max Sharpe {maxSharpe.sharpe.toFixed(2)}x
                    </button>
                  )}
                  {minVariance && (
                    <button
                      type="button"
                      onClick={() => applyPreset(minVariance, "Minimum Variance")}
                      className="flex-1 rounded border border-cyan-500/30 bg-cyan-950/20 p-2 text-cyan-300 hover:border-cyan-500/60"
                    >
                      Min Vol {minVariance.volatilityPct.toFixed(2)}% σ
                    </button>
                  )}
                </div>

                {adoptedMessage && (
                  <div className="text-[11px] font-mono text-emerald-300 flex items-center gap-1.5">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    <span>{adoptedMessage}</span>
                  </div>
                )}
              </div>

              <div className="nexus-panel rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-display text-sm font-semibold uppercase tracking-wider text-white">
                    Live Weight Tuner
                  </span>
                  <span className="font-mono text-xs text-amber-300 font-bold">
                    Sharpe: {current.sharpe.toFixed(2)}x
                  </span>
                </div>

                <div className="space-y-3 font-mono text-xs">
                  {assets.map((asset, index) => {
                    const normalized =
                      totalWeight > 0
                        ? ((weights[asset.symbol] ?? 0) / totalWeight) * 100
                        : 0;
                    return (
                      <div key={asset.symbol} className="space-y-1">
                        <div className="flex justify-between text-slate-300">
                          <span style={{ color: ASSET_COLORS[index] }}>{asset.symbol}</span>
                          <span className="font-bold text-cyan-300">{normalized.toFixed(1)}%</span>
                        </div>
                        <input
                          type="range"
                          min="0"
                          max="100"
                          value={weights[asset.symbol] ?? 0}
                          onChange={(event) =>
                            handleWeightChange(asset.symbol, Number(event.target.value))
                          }
                          className="w-full accent-cyan-400 cursor-pointer"
                        />
                      </div>
                    );
                  })}

                  <div className="rounded border border-slate-800 bg-[#030712] p-2 flex justify-between text-[11px]">
                    <span className="text-slate-400">
                      Exp. Return: <strong className="text-emerald-400">{current.expectedReturn.toFixed(2)}%</strong>
                    </span>
                    <span className="text-slate-400">
                      Volatility (σ): <strong className="text-rose-300">{current.volatility.toFixed(2)}%</strong>
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div className="nexus-panel rounded-lg p-4 space-y-2">
              <div className="flex items-center justify-between font-mono text-xs">
                <span className="font-semibold text-white uppercase">
                  Pearson Correlation Matrix
                </span>
                <span className="text-[10px] text-slate-400">DERIVED FROM PERIODIC RETURNS</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-center font-mono text-xs">
                  <thead className="border-b border-slate-800 text-[10px] uppercase text-slate-400">
                    <tr>
                      <th className="py-2 text-left">Asset</th>
                      {assets.map((asset) => (
                        <th key={asset.symbol} className="py-2">
                          {asset.symbol.split("/")[0]}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 text-slate-300">
                    {assets.map((row) => (
                      <tr key={row.symbol}>
                        <td className="py-2 text-left font-bold text-white">
                          {row.symbol.split("/")[0]}
                        </td>
                        {assets.map((column) => {
                          const value = correlationBetween(stats, row.symbol, column.symbol);
                          const positive = value >= 0.5;
                          return (
                            <td
                              key={column.symbol}
                              className={`py-2 ${
                                positive ? "text-amber-300 bg-amber-950/20" : "text-emerald-300 bg-emerald-950/20"
                              }`}
                            >
                              {value.toFixed(2)}
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
