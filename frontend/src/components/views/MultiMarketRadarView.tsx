import { useState } from "react";
import { Maximize2, RefreshCw } from "lucide-react";
import { useArbitrageRadar } from "../../hooks/useArbitrageRadar";
import { ConnectomeSphere } from "../ConnectomeSphere";
import { NexusSelect } from "../common/NexusSelect";

export function MultiMarketRadarView() {
  const {
    scanData,
    loading,
    error,
    wsConnected,
    executing,
    lastExecutionResult,
    refresh,
    triggerPaperExecution,
  } = useArbitrageRadar();

  const [activeCenterView, setActiveCenterView] = useState<"3D" | "GRID">("3D");
  const [selectedSector, setSelectedSector] = useState<string>("ALL");
  const [isFullScreen, setIsFullScreen] = useState<boolean>(false);

  const toggleFullScreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().then(() => setIsFullScreen(true));
    } else {
      document.exitFullscreen().then(() => setIsFullScreen(false));
    }
  };

  const telemetry = scanData?.telemetry || {
    load_90s: [92, 94, 91, 95, 93, 96, 92, 94, 95, 93, 91, 94],
    cypher_queries_per_sec: 266.0,
    hacks_blocked_per_sec: 4.4,
    yaw_deg: 35.3,
    pitch_deg: 47.6,
    graph_r_min: 120,
    graph_r_max: 480,
    nodes_count: 54,
    edges_count: 162,
    sota_gain_pct: 28.4,
    fps: 60.0,
    system_buffer_verified_pct: 99.8,
    scanner_compute_split_pct: 40.0,
    ai_compute_split_pct: 60.0,
    active_pods_count: 54,
    total_pods_count: 54,
  };

  const markets = scanData?.markets || [];
  const filteredMarkets =
    selectedSector === "ALL"
      ? markets
      : markets.filter((m) => m.sector === selectedSector);

  const opportunities = scanData?.triangular_opportunities || [];
  const topOpp = opportunities[0] || null;
  const dislocations = scanData?.synthetic_dislocations || [];

  return (
    <div className={`space-y-3 font-mono ${isFullScreen ? "fixed inset-0 z-50 overflow-y-auto bg-black p-4" : ""}`}>
      {/* 1. TOP HEADER: Stanford AI Lab / Discovery Architecture styling */}
      <div className="rounded-lg border border-cyan-500/30 bg-[#040816] p-3 text-slate-100 shadow-xl">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-cyan-500/20 pb-2">
          <div className="flex items-center gap-3">
            <span className="text-sm font-bold tracking-wider text-cyan-400">
              | STANFORD AI LAB / DISCOVERY ARCHITECTURE
            </span>
            <span className="text-xs font-semibold text-amber-400">
              CLAUDE OPUS 5.5 + GPT-6.1 SOL
            </span>
            <span className="text-[11px] text-slate-400">
              AGENT COGNITIVE STACK | 3 430 ITERATIONS
            </span>
          </div>

          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-1.5 text-cyan-300">
              <span className="h-2 w-2 rounded-full bg-cyan-400 animate-ping" />
              <span>GRAPH neo4j</span>
              <span className="text-slate-400">| NODES 14 284 | EDGES 68 400 | SESSIONS 100</span>
            </div>
            <div className="rounded bg-cyan-950/80 px-2 py-0.5 text-[11px] font-bold text-emerald-400">
              cypher/eval 64.6 %
            </div>
            <button
              onClick={toggleFullScreen}
              className="flex items-center gap-1 rounded border border-cyan-500/40 bg-cyan-950/40 px-2 py-1 text-[11px] text-cyan-300 hover:bg-cyan-900/60 transition"
              title="Toggle iPad / Second Screen Fullscreen"
            >
              <Maximize2 className="h-3 w-3" />
              <span>{isFullScreen ? "EXIT IPAD MODE" : "IPAD 2ND MONITOR"}</span>
            </button>
          </div>
        </div>

        {/* Cognitive stack tags row */}
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px]">
          {[
            "ast.diff",
            "sandbox.run",
            "kernel.bench",
            "assert.shape",
            "cypher.query",
            "map_elites.hop",
            "mcts.select",
            "sol.propose",
            "eval.isolate",
            "meta.distill",
            "sota.verify",
            "neo4j.graph_kv",
            "sol.sample_deck",
            "opus.search_plan",
            "sandbox.container_barrier",
            "meta.lesson_extract",
            "opus.guidance_sync",
          ].map((tag, i) => (
            <span
              key={tag}
              className={`rounded px-1.5 py-0.5 border ${
                i % 4 === 0
                  ? "border-amber-500/40 bg-amber-950/30 text-amber-300"
                  : i % 4 === 1
                  ? "border-cyan-500/40 bg-cyan-950/30 text-cyan-300"
                  : i % 4 === 2
                  ? "border-purple-500/40 bg-purple-950/30 text-purple-300"
                  : "border-emerald-500/40 bg-emerald-950/30 text-emerald-300"
              }`}
            >
              {tag}
            </span>
          ))}
        </div>

        {/* Sub-bar telemetry readout */}
        <div className="mt-2 flex flex-wrap items-center justify-between text-[11px] text-slate-400 border-t border-cyan-500/10 pt-1.5">
          <div>
            <span className="text-cyan-400 font-bold">AGENTDISCOVER</span> | OPUS 5.5 PLANNER + GPT-6.1 SOL PROPOSER | WAVE 147 DEG | HACKS BLOCKED 424 | ZERO CONTEXT BLEED
          </div>
          <div className="flex items-center gap-3 text-cyan-300">
            <span>CONNECTOME R 120-480</span>
            <span>STRANDS 23 976</span>
            <span className={wsConnected ? "text-emerald-400 font-bold" : "text-amber-400"}>
              {wsConnected ? "STREAM LIVE (1000ms)" : "STREAM RECONNECTING"}
            </span>
          </div>
        </div>

        {/* Live Real-Time Dislocation & Arbitrage Feed Ribbon */}
        <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 rounded border border-emerald-500/30 bg-emerald-950/25 px-3 py-1.5 text-[11px]">
          <div className="flex items-center gap-2">
            <span className="flex h-2 w-2 rounded-full bg-emerald-400 animate-ping" />
            <span className="font-bold text-emerald-400">⚡ LIVE DISLOCATION SNIPER STREAM:</span>
            <span className="text-slate-300">
              Autonomous loop actively monitoring 54 spot markets · 1-click execution enabled
            </span>
          </div>
          {lastExecutionResult && (
            <div className="rounded border border-emerald-400/50 bg-emerald-950/80 px-2.5 py-0.5 font-bold text-emerald-300 animate-pulse">
              {lastExecutionResult}
            </div>
          )}
        </div>
      </div>

      {/* Telemetry error alert */}
      {error && (
        <div className="rounded border border-amber-500/50 bg-amber-950/30 px-3 py-2 text-xs text-amber-300">
          ⚠️ Scanner warning: {error}
        </div>
      )}

      {/* Execution feedback alert */}
      {lastExecutionResult && (
        <div className="rounded border border-emerald-500/50 bg-emerald-950/30 px-3 py-2 text-xs text-emerald-300 flex items-center justify-between">
          <span>⚡ {lastExecutionResult}</span>
          <span className="text-[10px] text-slate-400">PAPER TRADING SIMULATION ONLY</span>
        </div>
      )}

      {/* 2. MAIN SPLIT: Center 3D/Grid & Right Telemetry Sidebar */}
      <div className="grid grid-cols-1 gap-3 xl:grid-cols-12">
        {/* CENTER STAGE (xl:col-span-8) */}
        <div className="space-y-3 xl:col-span-8">
          {/* Controls: Switch 3D Connectome vs 54-Market Grid */}
          <div className="flex items-center justify-between rounded-lg border border-cyan-500/20 bg-[#040816] px-3 py-2 text-xs">
            <div className="flex items-center gap-2">
              <span className="text-slate-400 font-bold">VIEW MODE:</span>
              <button
                onClick={() => setActiveCenterView("3D")}
                className={`rounded px-2.5 py-1 text-xs font-semibold transition ${
                  activeCenterView === "3D"
                    ? "bg-cyan-500 text-black shadow-[0_0_10px_rgba(6,182,212,0.5)]"
                    : "bg-slate-900 text-slate-300 hover:bg-slate-800"
                }`}
              >
                3D CONNECTOME CORE
              </button>
              <button
                onClick={() => setActiveCenterView("GRID")}
                className={`rounded px-2.5 py-1 text-xs font-semibold transition ${
                  activeCenterView === "GRID"
                    ? "bg-cyan-500 text-black shadow-[0_0_10px_rgba(6,182,212,0.5)]"
                    : "bg-slate-900 text-slate-300 hover:bg-slate-800"
                }`}
              >
                54-MARKET HEAT MATRIX
              </button>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-[11px] text-slate-400 font-bold hidden sm:inline">SECTOR:</span>
              <NexusSelect
                value={selectedSector}
                onChange={setSelectedSector}
                options={[
                  { value: "ALL", label: "ALL SECTORS" },
                  { value: "LAYER_1", label: "LAYER 1" },
                  { value: "DEFI", label: "DEFI" },
                  { value: "AI_COMPUTE", label: "AI & COMPUTE" },
                  { value: "MEMES", label: "MEMES" },
                  { value: "INFRASTRUCTURE", label: "INFRASTRUCTURE" },
                  { value: "GAMING_METAVERSE", label: "GAMING" },
                ]}
                ariaLabel="Filter Sector"
              />
              <button
                onClick={refresh}
                className="rounded border border-cyan-500/30 p-1.5 text-cyan-400 hover:bg-cyan-950/60"
                title="Refresh Tickers"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              </button>
            </div>
          </div>

          {/* Center Display: Either Three.js 3D Sphere or 54-Market Heat Grid */}
          {activeCenterView === "3D" ? (
            <div className="h-[460px] w-full">
              <ConnectomeSphere
                topOpportunity={topOpp}
                totalMarkets={markets.length || 54}
                yawDeg={telemetry.yaw_deg}
              />
            </div>
          ) : (
            <div className="max-h-[460px] overflow-y-auto rounded-lg border border-cyan-500/25 bg-[#030712] p-2.5 shadow-2xl">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
                {filteredMarkets.map((m) => (
                  <div
                    key={m.symbol}
                    className="rounded border border-cyan-500/20 bg-slate-950/80 p-2 text-xs transition hover:border-cyan-400/60"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-200">{m.symbol}</span>
                      <span
                        className={`text-[10px] font-semibold ${
                          m.change_24h_pct >= 0 ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {m.change_24h_pct >= 0 ? "+" : ""}
                        {m.change_24h_pct.toFixed(2)}%
                      </span>
                    </div>
                    <div className="mt-1 flex items-baseline justify-between text-[11px]">
                      <span className="text-cyan-300">${m.last.toLocaleString()}</span>
                      <span className="text-[10px] text-amber-400/80">
                        {m.spread_bps.toFixed(1)} bps
                      </span>
                    </div>
                    <div className="mt-0.5 flex items-center justify-between text-[9px] text-slate-500">
                      <span>{m.sector}</span>
                      <span>Vol: ${(m.quote_volume_24h / 1e6).toFixed(1)}M</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Triangular Opportunities & Synthetic Dislocation Scanner Deck */}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {/* Triangular Loops */}
            <div className="rounded-lg border border-cyan-500/25 bg-[#040816] p-3 text-xs shadow-lg">
              <div className="flex items-center justify-between border-b border-cyan-500/20 pb-2">
                <span className="font-bold text-cyan-300">
                  ⚡ DETECTED TRIANGULAR ARBITRAGE LOOPS
                </span>
                <span className="text-[10px] text-slate-400">
                  REAL FEES (30 bps) & SLIPPAGE (15 bps) DEDUCTED
                </span>
              </div>

              <div className="mt-2 space-y-2 max-h-[180px] overflow-y-auto">
                {opportunities.map((opp) => (
                  <div
                    key={opp.id}
                    className={`rounded border p-2 text-[11px] transition ${
                      opp.net_edge_bps > 0
                        ? "border-emerald-500/60 bg-emerald-950/20"
                        : "border-slate-800 bg-slate-950/50 text-slate-400"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-200">{opp.path}</span>
                      <span
                        className={`font-semibold ${
                          opp.net_edge_bps > 0 ? "text-emerald-400" : "text-amber-400/80"
                        }`}
                      >
                        NET: {opp.net_edge_bps > 0 ? "+" : ""}
                        {opp.net_edge_bps.toFixed(2)} bps
                      </span>
                    </div>
                    <div className="mt-1 flex items-center justify-between text-[10px]">
                      <span>
                        Gross: {opp.gross_edge_bps > 0 ? "+" : ""}
                        {opp.gross_edge_bps.toFixed(2)} bps | Fees: {opp.total_fee_bps} bps
                      </span>
                      <button
                        onClick={() => triggerPaperExecution(opp.id, 100)}
                        disabled={executing}
                        className="rounded bg-cyan-600/80 px-2 py-0.5 text-[10px] text-white hover:bg-cyan-500 transition disabled:opacity-50"
                      >
                        {executing ? "SIMULATING..." : "SIMULATE $100 CLIP"}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Synthetic Cross Dislocations */}
            <div className="rounded-lg border border-cyan-500/25 bg-[#040816] p-3 text-xs shadow-lg">
              <div className="flex items-center justify-between border-b border-cyan-500/20 pb-2">
                <span className="font-bold text-amber-300">
                  🎯 SYNTHETIC CROSS DISLOCATIONS
                </span>
                <span className="text-[10px] text-slate-400">
                  DIRECT VS SYNTHETIC CROSS
                </span>
              </div>

              <div className="mt-2 space-y-2 max-h-[180px] overflow-y-auto">
                {dislocations.map((d) => (
                  <div
                    key={d.direct_symbol}
                    className="rounded border border-slate-800 bg-slate-950/60 p-2 text-[11px] hover:border-cyan-500/40 transition"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-200">{d.direct_symbol}</span>
                      <div className="flex items-center gap-2">
                        <span
                          className={`font-bold ${
                            Math.abs(d.dislocation_bps) > 2.0
                              ? "text-emerald-400 font-mono"
                              : "text-slate-400 font-mono"
                          }`}
                        >
                          {d.dislocation_bps > 0 ? "+" : ""}
                          {d.dislocation_bps.toFixed(2)} bps
                        </span>
                        <button
                          type="button"
                          disabled={executing}
                          onClick={() => triggerPaperExecution(d.direct_symbol, 50)}
                          className="rounded border border-cyan-500/50 bg-cyan-950/70 px-1.5 py-0.5 text-[9px] font-bold text-cyan-300 hover:bg-cyan-800 hover:text-white transition disabled:opacity-50"
                          title={`Manually snipe $50 paper allocation on ${d.direct_symbol}`}
                        >
                          ⚡ SNIPE $50
                        </button>
                      </div>
                    </div>
                    <div className="mt-1 flex items-center justify-between text-[10px] text-slate-400">
                      <span>Direct: {d.direct_price.toFixed(6)}</span>
                      <span>Synth: {d.synthetic_price.toFixed(6)}</span>
                      <span className="text-cyan-300 font-semibold">{d.direction}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT TELEMETRY SIDEBAR: Exactly matches the video (xl:col-span-4) */}
        <div className="space-y-3 xl:col-span-4">
          <div className="rounded-lg border border-cyan-500/30 bg-[#040816] p-3 text-xs shadow-xl space-y-3">
            {/* 1. DISCOVERY LOAD - 90 S */}
            <div>
              <div className="flex items-center justify-between text-[11px] text-amber-400">
                <span className="font-bold">DISCOVERY LOAD - 90 S</span>
                <span className="text-amber-300 font-bold">94.7</span>
              </div>
              {/* Stepped/square load waveform */}
              <div className="mt-1 flex h-8 items-end gap-1 rounded bg-black/60 p-1 border border-amber-500/20">
                {telemetry.load_90s.map((val, i) => (
                  <div
                    key={i}
                    style={{ height: `${(val - 85) * 10}%` }}
                    className="flex-1 bg-amber-400/80 rounded-t-xs"
                  />
                ))}
              </div>
            </div>

            {/* 2. CYPHER QUERIES / S & HACKS BLOCKED / S */}
            <div className="grid grid-cols-2 gap-2 text-[11px]">
              <div className="rounded border border-red-500/30 bg-red-950/20 p-2">
                <div className="text-slate-400">CYPHER QUERIES / S</div>
                <div className="text-base font-bold text-rose-400">
                  {telemetry.cypher_queries_per_sec.toFixed(0)}
                </div>
              </div>
              <div className="rounded border border-rose-500/30 bg-rose-950/20 p-2">
                <div className="text-slate-400">HACKS BLOCKED / S</div>
                <div className="text-base font-bold text-pink-400">
                  {telemetry.hacks_blocked_per_sec.toFixed(1)}
                </div>
              </div>
            </div>

            {/* 3. IDEA DIVERSITY BY THETA | 48 BINS */}
            <div>
              <div className="text-[11px] font-bold text-cyan-400">
                IDEA DIVERSITY BY THETA | 48 BINS
              </div>
              <div className="mt-1 flex h-7 items-center gap-0.5 rounded bg-black/60 p-1 border border-cyan-500/20">
                {Array.from({ length: 48 }).map((_, i) => (
                  <div
                    key={i}
                    style={{
                      height: `${30 + Math.sin(i * 0.4) * 50}%`,
                    }}
                    className={`flex-1 rounded-xs ${
                      i === 18 ? "bg-amber-400" : "bg-cyan-500/70"
                    }`}
                  />
                ))}
              </div>
            </div>

            {/* 4. MODEL COMPUTE SPLIT | 2 HISTOGRAM */}
            <div>
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-amber-400 font-bold">OPUS 5.5: 40%</span>
                <span className="text-purple-400 font-bold">GPT-6.1 SOL: 60%</span>
              </div>
              <div className="mt-1 flex h-4 w-full overflow-hidden rounded bg-black/80">
                <div style={{ width: "40%" }} className="bg-amber-500 h-full" />
                <div style={{ width: "60%" }} className="bg-purple-600 h-full" />
              </div>
            </div>

            {/* 5. CYCLE STATE | SYNCHRONIZER */}
            <div>
              <div className="text-[11px] font-bold text-slate-300">
                CYCLE STATE | SYNCHRONIZER
              </div>
              <div className="mt-1 space-y-1 text-[10px]">
                <div className="flex items-center justify-between rounded bg-black/40 px-2 py-0.5">
                  <span className="text-amber-300">01 SOL PROPOSE</span>
                  <span className="rounded bg-amber-500/30 px-1 text-amber-300 font-bold">SWEEP</span>
                </div>
                <div className="flex items-center justify-between rounded bg-black/40 px-2 py-0.5">
                  <span className="text-slate-400">02 OPUS CYPHER</span>
                  <span className="text-slate-500">WAIT</span>
                </div>
                <div className="flex items-center justify-between rounded bg-black/40 px-2 py-0.5">
                  <span className="text-slate-400">03 ISOLATED EVAL</span>
                  <span className="text-slate-500">IDLE</span>
                </div>
                <div className="flex items-center justify-between rounded bg-black/40 px-2 py-0.5">
                  <span className="text-slate-400">04 META DISTILL</span>
                  <span className="text-slate-500">WAIT</span>
                </div>
              </div>
            </div>

            {/* 6. TELEMETRY READOUT */}
            <div>
              <div className="text-[11px] font-bold text-cyan-400">
                TELEMETRY READOUT
              </div>
              <div className="mt-1 grid grid-cols-2 gap-x-2 gap-y-1 text-[10px] text-slate-300">
                <div>YAW / PITCH: <span className="text-cyan-300">{telemetry.yaw_deg.toFixed(1)} / {telemetry.pitch_deg.toFixed(1)} DEG</span></div>
                <div>GRAPH R: <span className="text-cyan-300">120 - 480</span></div>
                <div>IDEA NODES: <span className="text-amber-300">{telemetry.nodes_count}</span></div>
                <div>CYPHER EDGES: <span className="text-amber-300">{telemetry.edges_count}</span></div>
                <div>HACKS BLOCKED: <span className="text-rose-400">424</span></div>
                <div>SESSIONS: <span className="text-emerald-400">100</span></div>
                <div>SOTA GAIN: <span className="text-emerald-400 font-bold">+{telemetry.sota_gain_pct}%</span></div>
                <div>CYCLE / FPS: <span className="text-cyan-400 font-bold">#150 | {telemetry.fps.toFixed(1)}</span></div>
              </div>
            </div>

            {/* 7. ISOLATED SANDBOX PODS | 32-54 PODS */}
            <div>
              <div className="flex items-center justify-between text-[11px]">
                <span className="text-slate-300 font-bold">ISOLATED SANDBOX PODS | 54 PODS</span>
                <span className="text-emerald-400 text-[10px]">LEAK: 0.0%</span>
              </div>
              <div className="mt-1 text-[9px] text-slate-400">ACTIVE: 54/54 | RUN: APPTAINER</div>
              {/* Pods Grid */}
              <div className="mt-1.5 grid grid-cols-9 gap-1">
                {Array.from({ length: 54 }).map((_, i) => (
                  <div
                    key={i}
                    className={`h-3 rounded-xs ${
                      i % 7 === 0
                        ? "bg-amber-400"
                        : i % 5 === 0
                        ? "bg-purple-500"
                        : i % 3 === 0
                        ? "bg-cyan-400"
                        : "bg-emerald-500"
                    }`}
                    title={`Pod #${i + 1} ACTIVE`}
                  />
                ))}
              </div>
            </div>

            {/* 8. DISPATCH QUEUE | LIVE COMMITS */}
            <div>
              <div className="text-[11px] font-bold text-slate-300">
                DISPATCH QUEUE | LIVE COMMITS
              </div>
              <div className="mt-1 space-y-0.5 rounded bg-black/60 p-2 font-mono text-[9px] text-cyan-300 border border-cyan-500/20">
                <div className="flex justify-between">
                  <span>&gt; eval.bench -&gt; score.valid</span>
                  <span className="text-emerald-400">+1.1ms</span>
                </div>
                <div className="flex justify-between">
                  <span>&gt; isolate.chk -&gt; leak.none</span>
                  <span className="text-emerald-400 font-bold">PASSED</span>
                </div>
                <div className="flex justify-between">
                  <span>&gt; meta.lesson -&gt; graph.edge</span>
                  <span className="text-slate-400">#14284</span>
                </div>
                <div className="mt-1 border-t border-cyan-500/20 pt-1 text-right text-emerald-400 font-bold">
                  SYSTEM BUFFER: {telemetry.system_buffer_verified_pct}% VERIFIED
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 3. BOTTOM PANEL: Model Token Flow Stream, Domain Merges, Benchmark Metrics & Pareto Rejections */}
      <div className="space-y-3">
        {/* Animated token flow stream ribbon */}
        <div className="rounded-lg border border-cyan-500/30 bg-[#040816] p-2 text-xs">
          <div className="flex items-center justify-between text-[11px] text-slate-300">
            <span className="font-bold text-cyan-400">
              MODEL TOKEN FLOW & COMPUTE SPEND | 30 MIN | STREAM
            </span>
            <span className="font-bold text-amber-400">3.47 B TOK / MIN</span>
          </div>
          <div className="mt-1 flex h-6 w-full items-center justify-between rounded bg-black/70 px-3 border border-cyan-500/20 text-[10px]">
            <span className="text-cyan-400 font-semibold">sol.code ~~~~~~~~~</span>
            <span className="text-amber-400 font-semibold">opus.plan ~~~~~~~~</span>
            <span className="text-emerald-400 font-semibold">eval.isolate ~~~~~~~</span>
            <span className="text-purple-400 font-semibold">graph.sync ~~~~~~~~</span>
          </div>
        </div>

        {/* 3 Sub-panels matching the bottom of the video */}
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          {/* Bottom Left: DISCOVERY MERGES BY DOMAIN */}
          <div className="rounded-lg border border-cyan-500/25 bg-[#040816] p-3 text-xs shadow-lg">
            <div className="text-[11px] font-bold text-slate-300">
              DISCOVERY MERGES BY DOMAIN
            </div>
            <div className="mt-3 flex items-center justify-center">
              <div className="relative flex h-28 w-28 items-center justify-center rounded-full border-4 border-cyan-500/40 bg-black/60 shadow-[0_0_20px_rgba(6,182,212,0.3)]">
                <div className="text-center">
                  <div className="text-sm font-bold text-amber-400">14284</div>
                  <div className="text-[9px] text-slate-400">MERGES</div>
                </div>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-4 text-center text-[10px] text-slate-400">
              <div>KERNEL</div>
              <div>SYSTEMS</div>
              <div>MATH</div>
              <div>BIO</div>
            </div>
          </div>

          {/* Bottom Center: BENCHMARK METRICS | BEFORE - AFTER */}
          <div className="rounded-lg border border-cyan-500/25 bg-[#040816] p-3 text-xs shadow-lg">
            <div className="text-[11px] font-bold text-slate-300">
              BENCHMARK METRICS | BEFORE - AFTER
            </div>
            <div className="mt-2 space-y-1.5 text-[10px]">
              {[
                { name: "ahc-heuristics", pct: "-70.4%", pos: 30 },
                { name: "kernel-builder", pct: "-59.8%", pos: 40 },
                { name: "math-extremal", pct: "-45.5%", pos: 55 },
                { name: "reward-leakage", pct: "-93.6%", pos: 10 },
                { name: "model-spend", pct: "-68.9%", pos: 32 },
                { name: "sota-winrate", pct: "+28.2%", pos: 75, positive: true },
              ].map((item) => (
                <div key={item.name} className="flex items-center justify-between gap-2">
                  <span className="w-24 truncate text-slate-400">{item.name}</span>
                  <div className="relative h-2 flex-1 rounded bg-slate-900">
                    <div
                      style={{ left: `${item.pos}%` }}
                      className={`absolute top-0 h-2 w-2 rounded-full -translate-x-1/2 ${
                        item.positive ? "bg-emerald-400" : "bg-cyan-400"
                      }`}
                    />
                  </div>
                  <span
                    className={`w-12 text-right font-bold ${
                      item.positive ? "text-emerald-400" : "text-amber-400"
                    }`}
                  >
                    {item.pct}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Bottom Right: EVALUATOR REJECTIONS | PARETO */}
          <div className="rounded-lg border border-cyan-500/25 bg-[#040816] p-3 text-xs shadow-lg">
            <div className="text-[11px] font-bold text-slate-300">
              EVALUATOR REJECTIONS | PARETO
            </div>
            <div className="mt-3 flex h-24 items-end gap-1.5 rounded bg-black/60 p-2 border border-slate-800">
              {[
                { label: "ShapeErr", height: 85, color: "bg-amber-400" },
                { label: "Timeout", height: 60, color: "bg-cyan-500" },
                { label: "MemLeak", height: 40, color: "bg-purple-500" },
                { label: "StateRewind", height: 25, color: "bg-blue-500" },
                { label: "DataLeak", height: 15, color: "bg-rose-500" },
                { label: "TypeError", height: 10, color: "bg-slate-500" },
              ].map((bar) => (
                <div key={bar.label} className="flex flex-1 flex-col items-center gap-1">
                  <div
                    style={{ height: `${bar.height}%` }}
                    className={`w-full rounded-t-xs ${bar.color}`}
                  />
                  <span className="text-[7px] text-slate-400 rotate-45 origin-left">
                    {bar.label}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
