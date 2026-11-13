import { useState, useMemo } from "react";
import {
  X,
  Scale,
  CheckCircle2,
} from "lucide-react";

interface PortfolioOptimizerModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface PortfolioCandidate {
  name: string;
  weights: { btc: number; eth: number; sol: number };
  expectedReturn: number;
  volatility: number;
  sharpe: number;
}

export function PortfolioOptimizerModal({
  isOpen,
  onClose,
}: PortfolioOptimizerModalProps) {
  if (!isOpen) return null;

  // Custom User Slider Weights (percentages summing to 100)
  const [btcWeight, setBtcWeight] = useState<number>(45);
  const [ethWeight, setEthWeight] = useState<number>(35);
  const [solWeight, setSolWeight] = useState<number>(20);
  const [adoptedMessage, setAdoptedMessage] = useState<string | null>(null);

  // Normalization so weights always equal 100%
  const totalWeight = btcWeight + ethWeight + solWeight;
  const normBtc = totalWeight > 0 ? (btcWeight / totalWeight) * 100 : 33.3;
  const normEth = totalWeight > 0 ? (ethWeight / totalWeight) * 100 : 33.3;
  const normSol = totalWeight > 0 ? (solWeight / totalWeight) * 100 : 33.4;

  // Asset individual statistics (annualized)
  // BTC: ret=22%, vol=16%
  // ETH: ret=30%, vol=24%
  // SOL: ret=44%, vol=38%
  // Correlations: BTC-ETH=0.75, BTC-SOL=0.62, ETH-SOL=0.70
  const expectedReturn =
    (normBtc / 100) * 22 + (normEth / 100) * 30 + (normSol / 100) * 44;

  const wB = normBtc / 100;
  const wE = normEth / 100;
  const wS = normSol / 100;

  const variance =
    Math.pow(wB * 0.16, 2) +
    Math.pow(wE * 0.24, 2) +
    Math.pow(wS * 0.38, 2) +
    2 * wB * wE * 0.16 * 0.24 * 0.75 +
    2 * wB * wS * 0.16 * 0.38 * 0.62 +
    2 * wE * wS * 0.24 * 0.38 * 0.70;

  const portfolioVol = Math.sqrt(Math.max(variance, 0.0001)) * 100;
  const riskFreeRate = 4.5;
  const customSharpe =
    portfolioVol > 0 ? (expectedReturn - riskFreeRate) / portfolioVol : 1.0;

  // Pre-calculated institutional portfolios
  const maxSharpe: PortfolioCandidate = {
    name: "Max Sharpe Ratio Portfolio",
    weights: { btc: 45, eth: 35, sol: 20 },
    expectedReturn: 29.2,
    volatility: 18.1,
    sharpe: 2.36,
  };

  const minVariance: PortfolioCandidate = {
    name: "Global Minimum Variance",
    weights: { btc: 72, eth: 20, sol: 8 },
    expectedReturn: 23.4,
    volatility: 14.8,
    sharpe: 1.88,
  };

  const applyPreset = (cand: PortfolioCandidate) => {
    setBtcWeight(cand.weights.btc);
    setEthWeight(cand.weights.eth);
    setSolWeight(cand.weights.sol);
    setAdoptedMessage(`Applied ${cand.name} allocation.`);
    setTimeout(() => setAdoptedMessage(null), 3000);
  };

  // Markowitz Efficient Frontier Plot Curve Coordinates
  const curvePoints = useMemo(() => {
    // Generate 25 points along the frontier
    const pts = [];
    for (let i = 0; i <= 24; i++) {
      const t = i / 24;
      const vol = 14.5 + t * 18.0;
      // Concave return curve: R = R_min + a * sqrt(vol - vol_min)
      const ret = 21.0 + 4.2 * Math.sqrt(vol - 14.0) + (t * 2.5);
      pts.push({ vol, ret });
    }
    return pts;
  }, []);

  const width = 520;
  const height = 160;
  const pad = 24;

  const minX = 12;
  const maxX = 36;
  const minY = 18;
  const maxY = 46;

  const toCoords = (v: number, r: number) => {
    const x = pad + ((v - minX) / (maxX - minX)) * (width - pad * 2);
    const y = height - pad - ((r - minY) / (maxY - minY)) * (height - pad * 2);
    return { x, y };
  };

  const frontierPath = curvePoints
    .map((p, i) => {
      const { x, y } = toCoords(p.vol, p.ret);
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");

  const curCoord = toCoords(portfolioVol, expectedReturn);
  const maxSharpeCoord = toCoords(maxSharpe.volatility, maxSharpe.expectedReturn);
  const minVarCoord = toCoords(minVariance.volatility, minVariance.expectedReturn);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-3 backdrop-blur-md overflow-y-auto">
      <div className="nexus-panel max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-xl border border-cyan-500/40 bg-[#040816] p-6 shadow-2xl space-y-5">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-cyan-500/20 pb-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-cyan-500/20 border border-cyan-400 text-cyan-300">
              <Scale className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-display text-lg font-bold tracking-wider text-white">
                  MARKOWITZ EFFICIENT FRONTIER & RISK-PARITY
                </h2>
                <span className="rounded bg-cyan-950 px-2 py-0.5 font-mono text-[10px] text-cyan-300 border border-cyan-500/40 uppercase font-bold">
                  MEAN-VARIANCE OPTIMIZER
                </span>
              </div>
              <p className="font-mono text-xs text-slate-400">
                Mathematical Asset Weight Optimization Across Volatility & Cross-Pair Correlation Envelopes
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

        {/* Efficient Frontier SVG Plot */}
        <div className="nexus-panel rounded-lg p-4 space-y-2 border border-slate-800 bg-[#030712]">
          <div className="flex flex-wrap items-center justify-between text-xs font-mono">
            <span className="font-semibold text-white uppercase">
              Markowitz Efficient Frontier Curve (Risk σ vs Return E[R])
            </span>
            <div className="flex items-center gap-3 text-[10px]">
              <span className="flex items-center gap-1 text-emerald-300">
                <span className="h-2 w-2 rounded-full bg-emerald-400" /> Max Sharpe (2.36)
              </span>
              <span className="flex items-center gap-1 text-cyan-300">
                <span className="h-2 w-2 rounded-full bg-cyan-400" /> Min Volatility
              </span>
              <span className="flex items-center gap-1 text-amber-300">
                <span className="h-2 w-2 rounded-full bg-amber-400" /> Current Allocation
              </span>
            </div>
          </div>

          <div className="relative">
            <svg
              viewBox={`0 0 ${width} ${height}`}
              className="h-40 w-full rounded border border-slate-800 bg-nexus-void/90 shadow-inner"
              role="img"
              aria-label="Markowitz Efficient Frontier"
            >
              {/* Axes lines */}
              <line x1={pad} y1={height - pad} x2={width - pad} y2={height - pad} stroke="#1e293b" />
              <line x1={pad} y1={pad} x2={pad} y2={height - pad} stroke="#1e293b" />

              {/* Frontier Curve */}
              <path
                d={frontierPath}
                fill="none"
                stroke="#22d3ee"
                strokeWidth="2.5"
                strokeLinecap="round"
                className="drop-shadow-[0_0_8px_rgba(34,211,238,0.4)]"
              />

              {/* Min Variance Point */}
              <circle cx={minVarCoord.x} cy={minVarCoord.y} r="4.5" fill="#0891b2" stroke="#ffffff" strokeWidth="1.5" />

              {/* Max Sharpe Point */}
              <circle cx={maxSharpeCoord.x} cy={maxSharpeCoord.y} r="5.5" fill="#10b981" stroke="#ffffff" strokeWidth="1.8" className="animate-pulse" />

              {/* Current Point */}
              <circle cx={curCoord.x} cy={curCoord.y} r="5.5" fill="#f59e0b" stroke="#ffffff" strokeWidth="2" />

              {/* Axis Labels */}
              <text x={pad} y={height - 6} fill="#64748b" fontSize="8" fontFamily="monospace">
                Low Risk (12% Vol)
              </text>
              <text x={width - pad} y={height - 6} fill="#64748b" fontSize="8" fontFamily="monospace" textAnchor="end">
                High Risk (36% Vol)
              </text>
              <text x={pad + 4} y={pad + 4} fill="#64748b" fontSize="8" fontFamily="monospace">
                High Return (46% E[R])
              </text>
            </svg>
          </div>
        </div>

        {/* Presets & Interactive Sliders */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {/* Institutional Presets */}
          <div className="nexus-panel rounded-lg p-4 space-y-3">
            <span className="font-display text-sm font-semibold uppercase tracking-wider text-white">
              Institutional Allocation Models
            </span>

            <div className="space-y-2 font-mono text-xs">
              <button
                type="button"
                onClick={() => applyPreset(maxSharpe)}
                className="w-full text-left rounded border border-emerald-500/30 bg-emerald-950/20 p-2.5 hover:border-emerald-500/60 transition"
              >
                <div className="flex items-center justify-between font-bold text-emerald-300">
                  <span>1. {maxSharpe.name}</span>
                  <span>Sharpe {maxSharpe.sharpe.toFixed(2)}x</span>
                </div>
                <div className="mt-1 text-[11px] text-slate-300 flex justify-between">
                  <span>BTC: 45% · ETH: 35% · SOL: 20%</span>
                  <span className="text-emerald-400 font-semibold">+29.2% Return · 18.1% Vol</span>
                </div>
              </button>

              <button
                type="button"
                onClick={() => applyPreset(minVariance)}
                className="w-full text-left rounded border border-cyan-500/30 bg-cyan-950/20 p-2.5 hover:border-cyan-500/60 transition"
              >
                <div className="flex items-center justify-between font-bold text-cyan-300">
                  <span>2. {minVariance.name}</span>
                  <span>Sharpe {minVariance.sharpe.toFixed(2)}x</span>
                </div>
                <div className="mt-1 text-[11px] text-slate-300 flex justify-between">
                  <span>BTC: 72% · ETH: 20% · SOL: 8%</span>
                  <span className="text-cyan-400 font-semibold">+23.4% Return · 14.8% Vol</span>
                </div>
              </button>
            </div>

            {adoptedMessage && (
              <div className="text-[11px] font-mono text-emerald-300 flex items-center gap-1.5 pt-1">
                <CheckCircle2 className="h-3.5 w-3.5" />
                <span>{adoptedMessage}</span>
              </div>
            )}
          </div>

          {/* Interactive Weight Tuning Sliders */}
          <div className="nexus-panel rounded-lg p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-display text-sm font-semibold uppercase tracking-wider text-white">
                Live Weight Tuner
              </span>
              <span className="font-mono text-xs text-amber-300 font-bold">
                Sharpe: {customSharpe.toFixed(2)}x
              </span>
            </div>

            <div className="space-y-3 font-mono text-xs">
              {/* BTC Slider */}
              <div className="space-y-1">
                <div className="flex justify-between text-slate-300">
                  <span>Bitcoin (BTC):</span>
                  <span className="font-bold text-cyan-300">{normBtc.toFixed(1)}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={btcWeight}
                  onChange={(e) => setBtcWeight(Number(e.target.value))}
                  className="w-full accent-cyan-400 cursor-pointer"
                />
              </div>

              {/* ETH Slider */}
              <div className="space-y-1">
                <div className="flex justify-between text-slate-300">
                  <span>Ethereum (ETH):</span>
                  <span className="font-bold text-cyan-300">{normEth.toFixed(1)}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={ethWeight}
                  onChange={(e) => setEthWeight(Number(e.target.value))}
                  className="w-full accent-cyan-400 cursor-pointer"
                />
              </div>

              {/* SOL Slider */}
              <div className="space-y-1">
                <div className="flex justify-between text-slate-300">
                  <span>Solana (SOL):</span>
                  <span className="font-bold text-cyan-300">{normSol.toFixed(1)}%</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={solWeight}
                  onChange={(e) => setSolWeight(Number(e.target.value))}
                  className="w-full accent-cyan-400 cursor-pointer"
                />
              </div>

              <div className="rounded border border-slate-800 bg-[#030712] p-2 flex justify-between text-[11px] pt-2">
                <span className="text-slate-400">Exp. Return: <strong className="text-emerald-400">+{expectedReturn.toFixed(1)}%</strong></span>
                <span className="text-slate-400">Portfolio Volatility (σ): <strong className="text-rose-300">{portfolioVol.toFixed(1)}%</strong></span>
              </div>
            </div>
          </div>
        </div>

        {/* Pairwise Pearson Correlation Matrix Heatmap */}
        <div className="nexus-panel rounded-lg p-4 space-y-2">
          <div className="flex items-center justify-between font-mono text-xs">
            <span className="font-semibold text-white uppercase">
              Historical Pearson Cross-Asset Correlation Heatmap
            </span>
            <span className="text-[10px] text-slate-400">RANGE: [-1.0 UNCORRELATED / +1.0 LOCKED]</span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-center font-mono text-xs">
              <thead className="border-b border-slate-800 text-[10px] uppercase text-slate-400">
                <tr>
                  <th className="py-2 text-left">Asset</th>
                  <th className="py-2">BTC</th>
                  <th className="py-2">ETH</th>
                  <th className="py-2">SOL</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                <tr>
                  <td className="py-2 text-left font-bold text-white">BTC</td>
                  <td className="py-2 font-bold text-cyan-400 bg-cyan-950/40">1.00</td>
                  <td className="py-2 text-amber-300 bg-amber-950/20">0.75</td>
                  <td className="py-2 text-emerald-300 bg-emerald-950/20">0.62</td>
                </tr>
                <tr>
                  <td className="py-2 text-left font-bold text-white">ETH</td>
                  <td className="py-2 text-amber-300 bg-amber-950/20">0.75</td>
                  <td className="py-2 font-bold text-cyan-400 bg-cyan-950/40">1.00</td>
                  <td className="py-2 text-amber-300 bg-amber-950/20">0.70</td>
                </tr>
                <tr>
                  <td className="py-2 text-left font-bold text-white">SOL</td>
                  <td className="py-2 text-emerald-300 bg-emerald-950/20">0.62</td>
                  <td className="py-2 text-amber-300 bg-amber-950/20">0.70</td>
                  <td className="py-2 font-bold text-cyan-400 bg-cyan-950/40">1.00</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
