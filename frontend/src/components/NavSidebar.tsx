import {
  Activity,
  BarChart3,
  Cpu,
  FlaskConical,
  LayoutDashboard,
  Radar,
  Settings,
  ShieldCheck,
  Zap,
} from "lucide-react";
import type { NavTab } from "../types/system";

interface NavSidebarProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  killSwitchActive: boolean;
  openPositionsCount: number;
  futuresEnabled: boolean;
}

const NAV_ITEMS: Array<{
  id: NavTab;
  label: string;
  sublabel: string;
  badge?: string;
  icon: typeof LayoutDashboard;
}> = [
  {
    id: "Overview",
    label: "Overview",
    sublabel: "Mission Control & 3D Core",
    icon: LayoutDashboard,
  },
  {
    id: "Futures Trading",
    label: "Futures Desk",
    sublabel: "1x-5x Shorts & Leverage",
    badge: "NEW",
    icon: Zap,
  },
  {
    id: "Scanner & Radar",
    label: "Market Radar",
    sublabel: "54 Cross-Pairs & Arbitrage",
    icon: Radar,
  },
  {
    id: "Strategies",
    label: "Strategy Engine",
    sublabel: "EMA Trend & BB Oversold",
    icon: Cpu,
  },
  {
    id: "Trades",
    label: "Trade Ledger",
    sublabel: "Realized P&L & Positions",
    icon: BarChart3,
  },
  {
    id: "Backtesting",
    label: "Backtesting",
    sublabel: "OOS Validation & Tearsheets",
    icon: FlaskConical,
  },
  {
    id: "Risk",
    label: "Risk & Circuit",
    sublabel: "Drawdown Caps & Stops",
    icon: ShieldCheck,
  },
  {
    id: "Settings",
    label: "Settings",
    sublabel: "Environment & Keys",
    icon: Settings,
  },
];

export function NavSidebar({
  activeTab,
  onSelectTab,
  killSwitchActive,
  openPositionsCount,
  futuresEnabled,
}: NavSidebarProps) {
  const visibleItems = NAV_ITEMS.filter(
    (item) => item.id !== "Futures Trading" || futuresEnabled,
  );

  return (
    <aside className="flex shrink-0 flex-row gap-1.5 overflow-x-auto border-b border-white/[0.08] bg-[#050a17]/95 p-2 sm:p-3 lg:w-60 lg:flex-col lg:border-b-0 lg:border-r lg:p-3.5 backdrop-blur-2xl shadow-2xl">
      <div className="hidden pb-3 px-2 lg:block">
        <div className="flex items-center justify-between">
          <p className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-slate-400">
            Navigation Hub
          </p>
          <span className="flex h-1.5 w-1.5 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(0,229,255,0.8)]" />
        </div>
      </div>

      <nav className="flex flex-row gap-1 lg:flex-col">
        {visibleItems.map((item) => {
          const Icon = item.icon;
          const active = activeTab === item.id;
          const isFutures = item.id === "Futures Trading";

          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelectTab(item.id)}
              className={`group relative flex shrink-0 items-center justify-between rounded-xl px-3 py-2.5 text-left transition-all duration-200 ${
                active
                  ? "border border-cyan-400/30 bg-cyan-500/10 text-white shadow-lg shadow-cyan-950/40"
                  : "border border-transparent bg-transparent text-slate-400 hover:border-white/[0.08] hover:bg-slate-800/40 hover:text-slate-200"
              }`}
            >
              {/* Active glow accent line on left */}
              {active && (
                <span className="absolute inset-y-1.5 left-0 w-1 rounded-r-full bg-cyan-400 shadow-[0_0_12px_rgba(0,229,255,0.9)]" />
              )}

              <div className="flex items-center gap-3">
                <span
                  className={`flex h-8 w-8 items-center justify-center rounded-lg border transition-all ${
                    active
                      ? "border-cyan-500/40 bg-cyan-500/20 text-cyan-300 shadow-inner"
                      : isFutures
                        ? "border-amber-500/20 bg-amber-500/10 text-amber-400 group-hover:border-amber-500/40"
                        : "border-white/5 bg-slate-900/60 text-slate-400 group-hover:border-white/10 group-hover:text-cyan-300"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                </span>

                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-display text-xs font-semibold tracking-wide sm:text-sm">
                      {item.label}
                    </span>
                    {item.badge && (
                      <span className="rounded-full bg-cyan-500/20 border border-cyan-500/40 px-1.5 py-0.2 text-[9px] font-mono font-bold text-cyan-300">
                        {item.badge}
                      </span>
                    )}
                  </div>
                  <div className="hidden font-mono text-[10px] text-slate-500 group-hover:text-slate-400 lg:block">
                    {item.sublabel}
                  </div>
                </div>
              </div>

              {/* Status Indicator Badges */}
              {item.id === "Risk" && killSwitchActive && (
                <span
                  className="ml-2 inline-block h-2 w-2 rounded-full bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.9)] animate-pulse"
                  title="Kill switch active"
                />
              )}
              {item.id === "Trades" && openPositionsCount > 0 && (
                <span className="ml-2 rounded-full border border-cyan-500/30 bg-cyan-500/15 px-2 py-0.5 font-mono text-[10px] font-bold text-cyan-300">
                  {openPositionsCount}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Safety Footer Invariant Guard */}
      <div className="mt-auto hidden rounded-xl border border-white/[0.08] bg-slate-950/60 p-3 lg:block shadow-inner">
        <div className="flex items-center justify-between font-mono text-[10px] text-cyan-300 font-bold">
          <span className="flex items-center gap-1.5">
            <Activity className="h-3.5 w-3.5 text-cyan-400" />
            SAFETY INVARIANTS
          </span>
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(16,185,129,0.8)]" />
        </div>
        <p className="mt-1.5 text-[10px] leading-relaxed text-slate-400 font-mono">
          Strict paper mode active. No live funds at risk. Isolated margin simulation.
        </p>
      </div>
    </aside>
  );
}
