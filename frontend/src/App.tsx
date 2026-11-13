import { useEffect, useState } from "react";
import { AnalyticsSignalsPanel } from "./components/AnalyticsSignalsPanel";
import { AutonomousAIResearchDeck } from "./components/AutonomousAIResearchDeck";
import { AutonomousMissionControlBar } from "./components/AutonomousMissionControlBar";
import { NavSidebar } from "./components/NavSidebar";
import { NexusScene } from "./components/NexusScene";
import { PortfolioBottomDeck } from "./components/PortfolioBottomDeck";
import { TopBar } from "./components/TopBar";
import { BacktestingView } from "./components/views/BacktestingView";
import { MultiMarketRadarView } from "./components/views/MultiMarketRadarView";
import { RiskView } from "./components/views/RiskView";
import { SettingsView } from "./components/views/SettingsView";
import { StrategiesView } from "./components/views/StrategiesView";
import { TradesView } from "./components/views/TradesView";
import { useTerminalStream } from "./hooks/useTerminalStream";
import {
  fetchAIResearch,
  fetchAutonomousStatus,
  fetchTerminalSettings,
  refreshAIResearch,
  toggleAutonomousEngine,
  triggerAutonomousCycle,
} from "./services/apiClient";
import type {
  AIResearchBriefing,
  AutonomousEngineStatus,
  NavTab,
  SanitizedSettingsResponse,
} from "./types/system";

export function App() {
  const [activeTab, setActiveTab] = useState<NavTab>("Overview");
  const [settings, setSettings] = useState<SanitizedSettingsResponse | null>(null);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [engineStatus, setEngineStatus] = useState<AutonomousEngineStatus | null>(null);
  const [aiBriefing, setAiBriefing] = useState<AIResearchBriefing | null>(null);

  const {
    snapshot,
    wsStatus,
    loading,
    error,
    emergencyPending,
    lastEmergencyResponse,
    refresh,
    activateEmergencyStop,
  } = useTerminalStream();

  // Load settings on startup
  useEffect(() => {
    const controller = new AbortController();
    fetchTerminalSettings(controller.signal)
      .then((res) => {
        setSettings(res);
        setSettingsError(null);
      })
      .catch((err) => {
        if (!controller.signal.aborted) {
          setSettingsError(
            err instanceof Error ? err.message : "Failed to fetch settings",
          );
        }
      });

    return () => controller.abort();
  }, []);

  // Poll autonomous engine status and AI research
  useEffect(() => {
    let cancelled = false;

    async function loadAutonomousState() {
      try {
        const [eng, ai] = await Promise.all([
          fetchAutonomousStatus(),
          fetchAIResearch(),
        ]);
        if (!cancelled) {
          setEngineStatus(eng);
          setAiBriefing(ai);
        }
      } catch {
        // Silently handled
      }
    }

    loadAutonomousState();
    const interval = setInterval(loadAutonomousState, 5000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  async function handleForceCycle(): Promise<void> {
    await triggerAutonomousCycle();
    await refresh();
    const eng = await fetchAutonomousStatus();
    setEngineStatus(eng);
  }

  async function handleToggleEngine(): Promise<void> {
    await toggleAutonomousEngine();
    const eng = await fetchAutonomousStatus();
    setEngineStatus(eng);
  }

  async function handleRefreshAIResearch(): Promise<void> {
    const ai = await refreshAIResearch();
    setAiBriefing(ai);
  }

  return (
    <div className="nexus-grid-bg flex min-h-screen flex-col bg-nexus-void text-slate-100">
      <TopBar
        snapshot={snapshot}
        wsStatus={wsStatus}
        emergencyPending={emergencyPending}
        lastEmergencyResponse={lastEmergencyResponse}
        onRefresh={refresh}
        onActivateEmergencyStop={activateEmergencyStop}
      />

      <div className="flex flex-1 flex-col lg:flex-row">
        <NavSidebar
          activeTab={activeTab}
          onSelectTab={setActiveTab}
          killSwitchActive={snapshot?.risk.kill_switch_active ?? false}
          openPositionsCount={snapshot?.open_positions.length ?? 0}
        />

        <main className="flex-1 overflow-y-auto p-3 sm:p-4 lg:p-5">
          {error && (
            <div className="mb-4 rounded-md border border-amber-500/40 bg-amber-500/10 px-4 py-2.5 font-mono text-xs text-amber-200">
              Telemetry warning: {error}. Displaying only verified persisted state — never fabricated statistics.
            </div>
          )}

          {loading && !snapshot ? (
            <div className="nexus-panel flex min-h-[320px] items-center justify-center rounded-lg font-mono text-xs text-cyan-300">
              Connecting to FastAPI paper trading engine...
            </div>
          ) : (
            <>
              {activeTab === "Overview" && (
                <div className="space-y-4">
                  {/* Mission Control HUD */}
                  <AutonomousMissionControlBar
                    status={engineStatus}
                    onForceCycle={handleForceCycle}
                    onToggleEngine={handleToggleEngine}
                  />

                  {/* CrowLLM Live AI Quantitative Market Research Deck */}
                  <AutonomousAIResearchDeck
                    briefing={aiBriefing}
                    onRefresh={handleRefreshAIResearch}
                  />

                  {/* 3D Scene + Real-time Indicators & Signals Panel */}
                  <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
                    <div className="xl:col-span-8">
                      <NexusScene snapshot={snapshot} />
                    </div>
                    <div className="xl:col-span-4">
                      <AnalyticsSignalsPanel snapshot={snapshot} />
                    </div>
                  </div>

                  {/* Portfolio Balances, Open Positions, and Realized P&L Ledger */}
                  <PortfolioBottomDeck snapshot={snapshot} />
                </div>
              )}

              {activeTab === "Scanner & Radar" && <MultiMarketRadarView />}

              {activeTab === "Strategies" && (
                <StrategiesView snapshot={snapshot} settings={settings} />
              )}

              {activeTab === "Trades" && <TradesView snapshot={snapshot} />}

              {activeTab === "Backtesting" && <BacktestingView />}

              {activeTab === "Risk" && (
                <RiskView
                  snapshot={snapshot}
                  emergencyPending={emergencyPending}
                  onActivateEmergencyStop={activateEmergencyStop}
                />
              )}

              {activeTab === "Settings" && (
                <SettingsView settings={settings} error={settingsError} />
              )}
            </>
          )}
        </main>
      </div>

      <footer className="border-t border-cyan-500/15 bg-nexus-navy/90 px-4 py-2 font-mono text-[11px] text-slate-400">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span>
            NEXUS AI TRADER · {snapshot?.paper_trading_banner ?? "PAPER TRADING ONLY — NO REAL-MONEY EXECUTION"}
          </span>
          <span className="text-slate-500">
            Autonomous Multi-Agent System · Real Binance Spot Data · CrowLLM Market Intelligence
          </span>
        </div>
      </footer>
    </div>
  );
}

export default App;
