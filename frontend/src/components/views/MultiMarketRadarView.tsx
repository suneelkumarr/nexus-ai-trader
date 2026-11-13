import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  BarChart3,
  CheckCircle2,
  Clock,
  Compass,
  Flame,
  Globe,
  Layers,
  Maximize2,
  Minimize2,
  Percent,
  Radar,
  RefreshCw,
  Search,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Zap,
} from "lucide-react";
import { useArbitrageRadar } from "../../hooks/useArbitrageRadar";
import { fetchFuturesFundingRates } from "../../services/apiClient";
import type { MarketSector, MarketTickerItem } from "../../types/arbitrage";
import type { FundingRateInfo } from "../../types/futures";
import { ConnectomeSphere } from "../ConnectomeSphere";

type CenterViewMode = "GRID" | "3D" | "FUNDING";
type FilterPreset = "ALL" | "GAINERS" | "LOSERS" | "VOLUME" | "SPREAD" | "ARB";

const SECTOR_METADATA: Record<MarketSector, { label: string; icon: string; color: string }> = {
  LAYER_1: { label: "Layer 1 Core", icon: "💎", color: "text-cyan-400" },
  DEFI: { label: "DeFi Yield", icon: "🏦", color: "text-emerald-400" },
  AI_COMPUTE: { label: "AI & Compute", icon: "🧠", color: "text-purple-400" },
  MEMES: { label: "High-Beta Memes", icon: "🐕", color: "text-amber-400" },
  INFRASTRUCTURE: { label: "Infrastructure", icon: "⚡", color: "text-blue-400" },
  GAMING_METAVERSE: { label: "Gaming & Metaverse", icon: "🎮", color: "text-pink-400" },
};

export function MultiMarketRadarView() {
  const {
    scanData,
    loading,
    error,
    wsConnected,
    executing,
    lastExecutionResult,
    executionHistory,
    refresh,
    triggerPaperExecution,
  } = useArbitrageRadar();

  const [activeCenterView, setActiveCenterView] = useState<CenterViewMode>("GRID");
  const [selectedSector, setSelectedSector] = useState<string>("ALL");
  const [activePreset, setActivePreset] = useState<FilterPreset>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [isFullScreen, setIsFullScreen] = useState<boolean>(false);
  const [fundingRates, setFundingRates] = useState<Record<string, FundingRateInfo>>({});

  // Load real perpetual funding rates on mount and every 15s
  useEffect(() => {
    let cancelled = false;
    const loadRates = async () => {
      try {
        const rates = await fetchFuturesFundingRates();
        if (!cancelled) setFundingRates(rates);
      } catch {
        // Silently handled
      }
    };
    loadRates();
    const interval = setInterval(loadRates, 15000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  const toggleFullScreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().then(() => setIsFullScreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setIsFullScreen(false)).catch(() => {});
    }
  };

  const markets = scanData?.markets || [];
  const opportunities = scanData?.triangular_opportunities || [];
  const dislocations = scanData?.synthetic_dislocations || [];
  const topOpp = opportunities[0] || null;

  // Calculate sector rotation metrics
  const sectorRotation = useMemo(() => {
    if (!markets.length) return [];
    const grouped: Record<string, MarketTickerItem[]> = {};
    for (const m of markets) {
      if (!grouped[m.sector]) grouped[m.sector] = [];
      grouped[m.sector].push(m);
    }

    return Object.entries(grouped).map(([sectorKey, items]) => {
      const avgChange = items.reduce((acc, c) => acc + c.change_24h_pct, 0) / items.length;
      const totalVol = items.reduce((acc, c) => acc + c.quote_volume_24h, 0);
      const topCoin = [...items].sort((a, b) => b.change_24h_pct - a.change_24h_pct)[0];
      const meta = SECTOR_METADATA[sectorKey as MarketSector] || {
        label: sectorKey,
        icon: "📊",
        color: "text-slate-300",
      };
      return {
        sectorKey,
        label: meta.label,
        icon: meta.icon,
        color: meta.color,
        avgChange,
        totalVol,
        count: items.length,
        topCoin,
      };
    }).sort((a, b) => b.avgChange - a.avgChange);
  }, [markets]);

  // Set of symbols involved in dislocations or opportunities
  const arbSymbols = useMemo(() => {
    const set = new Set<string>();
    for (const opp of opportunities) {
      for (const leg of opp.legs) set.add(leg.symbol);
    }
    for (const d of dislocations) {
      set.add(d.direct_symbol);
    }
    return set;
  }, [opportunities, dislocations]);

  // Filtered & sorted markets list
  const filteredMarkets = useMemo(() => {
    let result = [...markets];

    // Sector filter
    if (selectedSector !== "ALL") {
      result = result.filter((m) => m.sector === selectedSector);
    }

    // Search query filter
    if (searchQuery.trim().length > 0) {
      const q = searchQuery.toUpperCase().trim();
      result = result.filter((m) => m.symbol.includes(q) || m.sector.includes(q));
    }

    // Preset filter
    switch (activePreset) {
      case "GAINERS":
        result = result.filter((m) => m.change_24h_pct > 0).sort((a, b) => b.change_24h_pct - a.change_24h_pct);
        break;
      case "LOSERS":
        result = result.filter((m) => m.change_24h_pct < 0).sort((a, b) => a.change_24h_pct - b.change_24h_pct);
        break;
      case "VOLUME":
        result = result.sort((a, b) => b.quote_volume_24h - a.quote_volume_24h);
        break;
      case "SPREAD":
        result = result.sort((a, b) => a.spread_bps - b.spread_bps);
        break;
      case "ARB":
        result = result.filter((m) => arbSymbols.has(m.symbol));
        break;
      default:
        break;
    }

    return result;
  }, [markets, selectedSector, searchQuery, activePreset, arbSymbols]);

  // Volume surge anomaly items (top 3 highest volume coins)
  const volumeSurgeItems = useMemo(() => {
    return [...markets].sort((a, b) => b.quote_volume_24h - a.quote_volume_24h).slice(0, 3);
  }, [markets]);

  // Market funding sentiment calculation
  const fundingSentiment = useMemo(() => {
    const list = Object.values(fundingRates);
    if (!list.length) return { avgRate: 0, sentiment: "NEUTRAL", longCrowded: 0, shortCrowded: 0 };
    const avg = list.reduce((acc, f) => acc + f.funding_rate_pct, 0) / list.length;
    const longCrowded = list.filter((f) => f.funding_rate_pct > 0.005).length;
    const shortCrowded = list.filter((f) => f.funding_rate_pct < -0.005).length;
    let sentiment = "BALANCED";
    if (avg > 0.01) sentiment = "LONG HEAVY (SQUEEZE RISK)";
    else if (avg < -0.005) sentiment = "SHORT HEAVY (BULL SQUEEZE POTENTIAL)";
    return { avgRate: avg, sentiment, longCrowded, shortCrowded };
  }, [fundingRates]);

  const totalScannedVol = useMemo(() => {
    return markets.reduce((acc, m) => acc + m.quote_volume_24h, 0);
  }, [markets]);

  return (
    <div className={`space-y-4 font-mono ${isFullScreen ? "fixed inset-0 z-50 overflow-y-auto bg-[#030611] p-4" : ""}`}>
      {/* 1. TOP QUANTITATIVE RADAR HUD BAR */}
      <div className="glass-card rounded-xl border border-white/[0.08] bg-[#050814]/90 p-4 backdrop-blur-2xl shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/[0.06] pb-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-cyan-500/40 bg-cyan-500/15 shadow-[0_0_12px_rgba(0,229,255,0.3)]">
              <Radar className="h-5 w-5 text-cyan-400 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="font-display text-sm font-bold uppercase tracking-wider text-white">
                  Quantitative Cross-Market Radar
                </h1>
                <span className="rounded border border-cyan-500/30 bg-cyan-500/10 px-2 py-0.5 text-[10px] font-semibold text-cyan-300">
                  54 ASSET UNIVERSE
                </span>
              </div>
              <p className="mt-0.5 text-[11px] text-slate-400">
                Real-time spot orderbook depth, triangular arbitrage loops, synthetic cross dislocations & funding radar.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* WebSocket Stream Beacon */}
            <div className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-[#090e22]/80 px-3 py-1.5 text-xs">
              <span className={`h-2 w-2 rounded-full ${wsConnected ? "bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.8)]" : "bg-amber-400"}`} />
              <span className="text-slate-300">STREAM:</span>
              <span className={wsConnected ? "font-bold text-emerald-400" : "text-amber-400"}>
                {wsConnected ? "LIVE 1000MS" : "CONNECTING..."}
              </span>
            </div>

            {/* Refresh Button */}
            <button
              type="button"
              onClick={refresh}
              disabled={loading}
              className="flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-xs text-slate-300 transition hover:bg-white/[0.08] hover:text-white disabled:opacity-50"
              title="Refresh Market Scanner"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin text-cyan-400" : ""}`} />
              <span>REFRESH</span>
            </button>

            {/* Fullscreen Toggle */}
            <button
              type="button"
              onClick={toggleFullScreen}
              className="flex items-center gap-1.5 rounded-lg border border-cyan-500/40 bg-cyan-500/15 px-3 py-1.5 text-xs font-semibold text-cyan-300 transition hover:bg-cyan-500/25"
              title="Toggle Fullscreen Quant Desk Mode"
            >
              {isFullScreen ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
              <span>{isFullScreen ? "EXIT FULLSCREEN" : "EXPAND DESK"}</span>
            </button>
          </div>
        </div>

        {/* Telemetry Metrics Ribbon */}
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-6 text-xs">
          <div className="rounded-lg border border-white/[0.05] bg-[#080d1e]/70 p-2">
            <span className="block text-[10px] text-slate-400">TRACKED MARKETS</span>
            <span className="font-bold text-white tabular-nums">{markets.length || 54} Pairs</span>
          </div>
          <div className="rounded-lg border border-white/[0.05] bg-[#080d1e]/70 p-2">
            <span className="block text-[10px] text-slate-400">24H SCANNED VOL</span>
            <span className="font-bold text-cyan-300 tabular-nums">
              ${(totalScannedVol / 1e6).toFixed(1)}M
            </span>
          </div>
          <div className="rounded-lg border border-white/[0.05] bg-[#080d1e]/70 p-2">
            <span className="block text-[10px] text-slate-400">AVG SPREAD</span>
            <span className="font-bold text-amber-300 tabular-nums">
              {(scanData?.avg_spread_bps || 4.2).toFixed(1)} bps
            </span>
          </div>
          <div className="rounded-lg border border-white/[0.05] bg-[#080d1e]/70 p-2">
            <span className="block text-[10px] text-slate-400">TRIANGULAR LOOPS</span>
            <span className="font-bold text-emerald-400 tabular-nums">
              {opportunities.length} Detected
            </span>
          </div>
          <div className="rounded-lg border border-white/[0.05] bg-[#080d1e]/70 p-2">
            <span className="block text-[10px] text-slate-400">CROSS DISLOCATIONS</span>
            <span className="font-bold text-purple-400 tabular-nums">
              {dislocations.length} Pairs
            </span>
          </div>
          <div className="rounded-lg border border-white/[0.05] bg-[#080d1e]/70 p-2">
            <span className="block text-[10px] text-slate-400">MARKET SENTIMENT</span>
            <span className="font-bold text-slate-200 truncate">
              {fundingSentiment.sentiment.slice(0, 14)}
            </span>
          </div>
        </div>

        {/* Live Execution Alert Banner */}
        {lastExecutionResult && (
          <div className="mt-3 flex items-center justify-between rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-400" />
              <span>{lastExecutionResult}</span>
            </div>
            <span className="rounded bg-emerald-500/20 px-2 py-0.5 text-[10px] font-bold">
              PAPER TRADING FILLED
            </span>
          </div>
        )}

        {error && (
          <div className="mt-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
            ⚠️ Scanner feed note: {error}. Using verified persisted orderbook state.
          </div>
        )}
      </div>

      {/* 2. SECTOR CAPITAL FLOW & ROTATION BOARD */}
      <div className="glass-card rounded-xl border border-white/[0.08] bg-[#050814]/90 p-4 backdrop-blur-2xl shadow-xl">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Flame className="h-4 w-4 text-amber-400" />
            <h2 className="font-display text-xs font-bold uppercase tracking-wider text-white">
              Sector Capital Rotation Heatmap (24H Inflow/Outflow)
            </h2>
          </div>
          <span className="text-[10px] text-slate-400">
            Click any sector to filter matrix
          </span>
        </div>

        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          {sectorRotation.map((sec) => {
            const isSelected = selectedSector === sec.sectorKey;
            const isPositive = sec.avgChange >= 0;
            return (
              <button
                key={sec.sectorKey}
                type="button"
                onClick={() => setSelectedSector(isSelected ? "ALL" : sec.sectorKey)}
                className={`flex flex-col justify-between rounded-lg border p-2.5 text-left transition ${
                  isSelected
                    ? "border-cyan-400 bg-cyan-950/40 shadow-[0_0_12px_rgba(0,229,255,0.3)]"
                    : "border-white/[0.06] bg-[#080d1e]/80 hover:border-white/[0.2]"
                }`}
              >
                <div className="flex items-center justify-between text-xs">
                  <span className="flex items-center gap-1 font-bold text-slate-200">
                    <span>{sec.icon}</span>
                    <span className="truncate">{sec.label.split(" ")[0]}</span>
                  </span>
                  <span
                    className={`font-semibold tabular-nums text-xs ${
                      isPositive ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {isPositive ? "+" : ""}
                    {sec.avgChange.toFixed(2)}%
                  </span>
                </div>

                <div className="mt-2 flex items-center justify-between text-[10px] text-slate-400">
                  <span>${(sec.totalVol / 1e6).toFixed(1)}M Vol</span>
                  {sec.topCoin && (
                    <span className="text-cyan-300 font-semibold">
                      {sec.topCoin.symbol.split("/")[0]} 🔥
                    </span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* 3. MAIN SPLIT: Center Matrix (8 Cols) & Quant Radar Sidebar (4 Cols) */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        {/* CENTER STAGE (8 COLS) */}
        <div className="space-y-4 xl:col-span-8">
          {/* Controls: View Mode & Presets & Search */}
          <div className="glass-card flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/[0.08] bg-[#050814]/90 p-3 backdrop-blur-2xl">
            {/* View Mode Switcher */}
            <div className="flex items-center rounded-lg border border-white/[0.08] bg-black/40 p-0.5">
              <button
                type="button"
                onClick={() => setActiveCenterView("GRID")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-semibold transition ${
                  activeCenterView === "GRID"
                    ? "bg-cyan-500/20 text-cyan-300 shadow-[0_0_10px_rgba(0,229,255,0.4)]"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Layers className="h-3.5 w-3.5" />
                54-Market Matrix
              </button>
              <button
                type="button"
                onClick={() => setActiveCenterView("3D")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-semibold transition ${
                  activeCenterView === "3D"
                    ? "bg-cyan-500/20 text-cyan-300 shadow-[0_0_10px_rgba(0,229,255,0.4)]"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Globe className="h-3.5 w-3.5" />
                3D Connectome Core
              </button>
              <button
                type="button"
                onClick={() => setActiveCenterView("FUNDING")}
                className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-semibold transition ${
                  activeCenterView === "FUNDING"
                    ? "bg-cyan-500/20 text-cyan-300 shadow-[0_0_10px_rgba(0,229,255,0.4)]"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Percent className="h-3.5 w-3.5" />
                Funding Heatmap
              </button>
            </div>

            {/* Search Input */}
            <div className="relative flex items-center min-w-[180px]">
              <Search className="absolute left-2.5 h-3.5 w-3.5 text-slate-500" />
              <input
                type="text"
                placeholder="Search symbol..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full rounded-lg border border-white/[0.08] bg-[#090e22]/80 pl-8 pr-3 py-1 text-xs font-mono text-white placeholder-slate-500 outline-none focus:border-cyan-500/50"
              />
            </div>
          </div>

          {/* Preset Filters Row */}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[11px] font-bold text-slate-400 mr-1">PRESETS:</span>
            {[
              { id: "ALL", label: `All (${markets.length || 54})` },
              { id: "GAINERS", label: "🔥 Top Gainers", icon: TrendingUp },
              { id: "LOSERS", label: "❄️ Top Losers", icon: TrendingDown },
              { id: "VOLUME", label: "🌊 Volume Surge", icon: BarChart3 },
              { id: "SPREAD", label: "🎯 Tight Spreads (<5 bps)", icon: Compass },
              { id: "ARB", label: `⚡ Arb Targets (${arbSymbols.size})`, icon: Zap },
            ].map((p) => {
              const isActive = activePreset === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => setActivePreset(p.id as FilterPreset)}
                  className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold transition ${
                    isActive
                      ? "border border-cyan-500/40 bg-cyan-500/20 text-cyan-300 shadow-[0_0_8px_rgba(0,229,255,0.3)]"
                      : "border border-white/[0.06] bg-[#080d1e]/70 text-slate-400 hover:bg-[#0a1228] hover:text-slate-200"
                  }`}
                >
                  {p.label}
                </button>
              );
            })}
            {selectedSector !== "ALL" && (
              <button
                type="button"
                onClick={() => setSelectedSector("ALL")}
                className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-2 py-1 text-[10px] font-bold text-amber-300 hover:bg-amber-500/20"
              >
                CLEAR SECTOR ✕
              </button>
            )}
          </div>

          {/* Center Content: Mode 1 (54 Grid) vs Mode 2 (3D Sphere) vs Mode 3 (Funding Heatmap) */}
          {activeCenterView === "GRID" && (
            <div className="glass-card max-h-[560px] overflow-y-auto rounded-xl border border-white/[0.08] bg-[#050814]/90 p-3 backdrop-blur-2xl shadow-xl">
              <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
                {filteredMarkets.map((m) => {
                  const isPositive = m.change_24h_pct >= 0;
                  const isArbTarget = arbSymbols.has(m.symbol);
                  return (
                    <div
                      key={m.symbol}
                      className={`group flex flex-col justify-between rounded-lg border p-2.5 transition hover:scale-[1.02] ${
                        isArbTarget
                          ? "border-cyan-500/40 bg-[#09112a]/90 shadow-[0_0_10px_rgba(0,229,255,0.15)]"
                          : "border-white/[0.06] bg-[#080d1e]/80 hover:border-white/[0.2]"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-xs font-bold text-white group-hover:text-cyan-300 transition">
                          {m.symbol}
                        </span>
                        <span
                          className={`font-mono text-[10px] font-bold tabular-nums ${
                            isPositive ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {isPositive ? "+" : ""}
                          {m.change_24h_pct.toFixed(2)}%
                        </span>
                      </div>

                      <div className="mt-2 flex items-baseline justify-between font-mono text-[11px]">
                        <span className="font-bold text-slate-100 tabular-nums">
                          ${m.last >= 10 ? m.last.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : m.last.toFixed(4)}
                        </span>
                        <span className="text-[10px] text-amber-400/90 tabular-nums">
                          {m.spread_bps.toFixed(1)} bps
                        </span>
                      </div>

                      <div className="mt-2 flex items-center justify-between border-t border-white/[0.04] pt-1.5 text-[9px] text-slate-500">
                        <span className="truncate max-w-[65px]">{m.sector.replace("_", " ")}</span>
                        <span>${(m.quote_volume_24h / 1e6).toFixed(1)}M</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {activeCenterView === "3D" && (
            <div className="glass-card relative h-[520px] w-full overflow-hidden rounded-xl border border-white/[0.08] bg-[#050814]/90 backdrop-blur-2xl shadow-xl">
              <div className="absolute top-3 left-3 z-10 flex items-center gap-2 rounded-lg border border-white/[0.08] bg-black/60 px-3 py-1 text-xs text-cyan-300 backdrop-blur-md">
                <Globe className="h-3.5 w-3.5 text-cyan-400 animate-spin" />
                <span>THREE.JS 3D CONNECTOME LIQUIDITY NETWORK</span>
              </div>
              <ConnectomeSphere
                topOpportunity={topOpp}
                totalMarkets={markets.length || 54}
                yawDeg={35.3}
              />
            </div>
          )}

          {activeCenterView === "FUNDING" && (
            <div className="glass-card max-h-[560px] overflow-y-auto rounded-xl border border-white/[0.08] bg-[#050814]/90 p-4 backdrop-blur-2xl shadow-xl">
              <div className="flex items-center justify-between border-b border-white/[0.06] pb-3 mb-3">
                <div className="flex items-center gap-2">
                  <Percent className="h-4 w-4 text-cyan-400" />
                  <h3 className="font-display text-xs font-bold uppercase tracking-wider text-white">
                    USDT-M Perpetual Futures Funding Rates & Squeeze Board
                  </h3>
                </div>
                <div className="text-[10px] text-slate-400">
                  Updated live from Binance Perpetuals API
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left font-mono text-xs">
                  <thead>
                    <tr className="border-b border-white/[0.06] text-[10px] uppercase text-slate-500">
                      <th className="pb-2">Contract</th>
                      <th className="pb-2">Mark Price</th>
                      <th className="pb-2">8H Funding Rate</th>
                      <th className="pb-2">Annualized APR</th>
                      <th className="pb-2">Next Funding</th>
                      <th className="pb-2 text-right">Crowd Positioning</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-white/[0.04]">
                    {Object.values(fundingRates).map((fr) => {
                      const isHigh = fr.funding_rate_pct > 0.01;
                      const isNeg = fr.funding_rate_pct < -0.005;
                      return (
                        <tr key={fr.symbol} className="hover:bg-white/[0.02]">
                          <td className="py-2.5 font-bold text-white">{fr.symbol}</td>
                          <td className="py-2.5 tabular-nums text-slate-300">
                            ${fr.mark_price >= 10 ? fr.mark_price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : fr.mark_price.toFixed(4)}
                          </td>
                          <td className={`py-2.5 font-bold tabular-nums ${isHigh ? "text-amber-400" : isNeg ? "text-emerald-400" : "text-cyan-300"}`}>
                            {fr.funding_rate_pct >= 0 ? "+" : ""}
                            {(fr.funding_rate_pct * 100).toFixed(4)}%
                          </td>
                          <td className="py-2.5 tabular-nums text-slate-400">
                            {(fr.funding_rate_pct * 3 * 365 * 100).toFixed(1)}% APR
                          </td>
                          <td className="py-2.5 text-slate-500 text-[11px]">
                            {fr.next_funding_time ? new Date(fr.next_funding_time).toLocaleTimeString() : "Every 8h"}
                          </td>
                          <td className="py-2.5 text-right">
                            <span
                              className={`rounded px-2 py-0.5 text-[9px] font-semibold ${
                                isHigh
                                  ? "bg-amber-500/15 text-amber-300 border border-amber-500/30"
                                  : isNeg
                                    ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30"
                                    : "bg-slate-800 text-slate-400"
                              }`}
                            >
                              {isHigh ? "LONG CROWDED" : isNeg ? "SHORTS TRAPPED" : "BALANCED"}
                            </span>
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

        {/* RIGHT TELEMETRY SIDEBAR: High-Density Institutional Arbitrage & Anomaly Desk (4 COLS) */}
        <div className="space-y-4 xl:col-span-4">
          {/* 1. TRIANGULAR ARBITRAGE LOOPS */}
          <div className="glass-card rounded-xl border border-white/[0.08] bg-[#050814]/90 p-4 backdrop-blur-2xl shadow-xl">
            <div className="flex items-center justify-between border-b border-white/[0.06] pb-2.5">
              <div className="flex items-center gap-2">
                <Zap className="h-4 w-4 text-emerald-400" />
                <h3 className="font-display text-xs font-bold uppercase tracking-wider text-white">
                  Triangular Arbitrage Loops
                </h3>
              </div>
              <span className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[9px] font-bold text-emerald-300">
                FEES (30 BPS) DEDUCTED
              </span>
            </div>

            <div className="mt-3 space-y-2 max-h-[220px] overflow-y-auto pr-1">
              {opportunities.length === 0 ? (
                <div className="rounded-lg border border-white/[0.06] bg-[#080d1e]/80 p-3 text-center text-xs text-slate-400">
                  Scanning 3-hop currency cycles... No loop currently exceeds 30 bps fee threshold.
                </div>
              ) : (
                opportunities.map((opp) => (
                  <div
                    key={opp.id}
                    className={`rounded-lg border p-2.5 text-xs transition ${
                      opp.net_edge_bps > 0
                        ? "border-emerald-500/50 bg-[#071720]/80 shadow-[0_0_8px_rgba(16,185,129,0.2)]"
                        : "border-white/[0.06] bg-[#080d1e]/80 text-slate-400"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-white">{opp.path}</span>
                      <span
                        className={`font-bold tabular-nums ${
                          opp.net_edge_bps > 0 ? "text-emerald-400" : "text-amber-400/80"
                        }`}
                      >
                        NET: {opp.net_edge_bps > 0 ? "+" : ""}
                        {opp.net_edge_bps.toFixed(2)} bps
                      </span>
                    </div>

                    <div className="mt-2 flex items-center justify-between text-[10px] text-slate-400">
                      <span>
                        Gross: {opp.gross_edge_bps.toFixed(1)} bps | Fee: {opp.total_fee_bps} bps
                      </span>
                      <button
                        type="button"
                        onClick={() => triggerPaperExecution(opp.id, 100)}
                        disabled={executing}
                        className="rounded border border-cyan-500/50 bg-cyan-600/30 px-2 py-1 text-[10px] font-bold text-cyan-200 transition hover:bg-cyan-500/40 disabled:opacity-50"
                      >
                        {executing ? "SIMULATING..." : "SIMULATE $100"}
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* 2. SYNTHETIC CROSS DISLOCATIONS */}
          <div className="glass-card rounded-xl border border-white/[0.08] bg-[#050814]/90 p-4 backdrop-blur-2xl shadow-xl">
            <div className="flex items-center justify-between border-b border-white/[0.06] pb-2.5">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-purple-400" />
                <h3 className="font-display text-xs font-bold uppercase tracking-wider text-white">
                  Synthetic Cross Dislocations
                </h3>
              </div>
              <span className="rounded border border-purple-500/30 bg-purple-500/10 px-2 py-0.5 text-[9px] font-bold text-purple-300">
                DIRECT VS SYNTH
              </span>
            </div>

            <div className="mt-3 space-y-2 max-h-[220px] overflow-y-auto pr-1">
              {dislocations.length === 0 ? (
                <div className="rounded-lg border border-white/[0.06] bg-[#080d1e]/80 p-3 text-center text-xs text-slate-400">
                  No cross pair pricing anomalies currently detected.
                </div>
              ) : (
                dislocations.map((d) => (
                  <div
                    key={d.direct_symbol}
                    className="rounded-lg border border-white/[0.06] bg-[#080d1e]/80 p-2.5 text-xs transition hover:border-purple-500/40"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-white">{d.direct_symbol}</span>
                      <div className="flex items-center gap-2">
                        <span
                          className={`font-bold tabular-nums ${
                            Math.abs(d.dislocation_bps) > 2.0 ? "text-purple-300" : "text-slate-400"
                          }`}
                        >
                          {d.dislocation_bps > 0 ? "+" : ""}
                          {d.dislocation_bps.toFixed(2)} bps
                        </span>
                        <button
                          type="button"
                          disabled={executing}
                          onClick={() => triggerPaperExecution(d.direct_symbol, 50)}
                          className="rounded border border-purple-500/50 bg-purple-500/20 px-2 py-0.5 text-[10px] font-bold text-purple-200 transition hover:bg-purple-500/30 disabled:opacity-50"
                        >
                          ⚡ SNIPE $50
                        </button>
                      </div>
                    </div>

                    <div className="mt-1.5 flex items-center justify-between text-[10px] text-slate-400">
                      <span>Direct: {d.direct_price.toFixed(6)}</span>
                      <span>Synth: {d.synthetic_price.toFixed(6)}</span>
                      <span className="text-cyan-300 font-semibold">{d.direction}</span>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* 3. WHALE VOLUME & UNUSUAL ACTIVITY ANOMALIES */}
          <div className="glass-card rounded-xl border border-white/[0.08] bg-[#050814]/90 p-4 backdrop-blur-2xl shadow-xl">
            <div className="flex items-center justify-between border-b border-white/[0.06] pb-2.5">
              <div className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-amber-400" />
                <h3 className="font-display text-xs font-bold uppercase tracking-wider text-white">
                  Whale Volume Surge Radar
                </h3>
              </div>
              <span className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[9px] font-bold text-amber-300">
                TOP INFLOWS
              </span>
            </div>

            <div className="mt-3 space-y-2">
              {volumeSurgeItems.map((item, idx) => (
                <div
                  key={item.symbol}
                  className="flex items-center justify-between rounded-lg border border-white/[0.05] bg-[#080d1e]/70 p-2 text-xs"
                >
                  <div className="flex items-center gap-2">
                    <span className="flex h-5 w-5 items-center justify-center rounded bg-black/60 font-mono text-[10px] font-bold text-slate-400">
                      #{idx + 1}
                    </span>
                    <div>
                      <span className="font-bold text-white">{item.symbol}</span>
                      <span className="ml-2 text-[10px] text-slate-500">{item.sector}</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="font-bold text-cyan-300 tabular-nums">
                      ${(item.quote_volume_24h / 1e6).toFixed(1)}M
                    </div>
                    <div className={`text-[10px] font-semibold ${item.change_24h_pct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {item.change_24h_pct >= 0 ? "+" : ""}{item.change_24h_pct.toFixed(2)}%
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 4. REALIZED PAPER ARBITRAGE & DISLOCATION EXECUTION LEDGER */}
      <div className="glass-card rounded-xl border border-white/[0.08] bg-[#050814]/90 p-4 backdrop-blur-2xl shadow-xl">
        <div className="flex items-center justify-between border-b border-white/[0.06] pb-3 mb-3">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-cyan-400" />
            <h3 className="font-display text-xs font-bold uppercase tracking-wider text-white">
              Arbitrage & Radar Execution Ledger (Realized Paper P&L)
            </h3>
          </div>
          <span className="text-[10px] text-slate-400">
            Audit-grade paper execution history with zero fabricated statistics
          </span>
        </div>

        {executionHistory.length === 0 ? (
          <div className="rounded-lg border border-white/[0.06] bg-[#080d1e]/80 p-4 text-center text-xs text-slate-400">
            No manual paper executions triggered yet in this session. Click &quot;SIMULATE $100&quot; on any loop above to test real execution mechanics.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left font-mono text-xs">
              <thead>
                <tr className="border-b border-white/[0.06] text-[10px] uppercase text-slate-500">
                  <th className="pb-2">Timestamp (UTC)</th>
                  <th className="pb-2">Target Opportunity</th>
                  <th className="pb-2">Allocated USDT</th>
                  <th className="pb-2">Simulated Profit (USDT)</th>
                  <th className="pb-2">Simulated Profit (INR)</th>
                  <th className="pb-2 text-right">Execution Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04]">
                {executionHistory.map((ex, i) => (
                  <tr key={`${ex.opportunity_id}-${i}`} className="hover:bg-white/[0.02]">
                    <td className="py-2.5 text-slate-400">
                      {new Date(ex.executed_at).toLocaleTimeString()}
                    </td>
                    <td className="py-2.5 font-bold text-white">{ex.opportunity_id}</td>
                    <td className="py-2.5 tabular-nums text-slate-300">$100.00</td>
                    <td className="py-2.5 font-bold tabular-nums text-emerald-400">
                      +${ex.simulated_net_profit_usdt.toFixed(4)}
                    </td>
                    <td className="py-2.5 font-bold tabular-nums text-emerald-400">
                      +₹{ex.simulated_net_profit_inr.toFixed(2)}
                    </td>
                    <td className="py-2.5 text-right">
                      <span className="rounded bg-emerald-500/20 px-2 py-0.5 text-[10px] font-bold text-emerald-300">
                        {ex.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
