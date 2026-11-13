import { useState } from "react";
import {
  BarChart3,
  Cpu,
  FlaskConical,
  LayoutDashboard,
  MoreHorizontal,
  Radar,
  Settings,
  ShieldCheck,
  X,
  Zap,
} from "lucide-react";
import type { NavTab } from "../types/system";

interface MobileBottomNavProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  killSwitchActive: boolean;
  openPositionsCount: number;
  futuresEnabled: boolean;
}

const PRIMARY_TABS: Array<{
  id: NavTab;
  label: string;
  icon: typeof LayoutDashboard;
}> = [
  { id: "Overview", label: "Overview", icon: LayoutDashboard },
  { id: "Futures Trading", label: "Futures", icon: Zap },
  { id: "Scanner & Radar", label: "Radar", icon: Radar },
  { id: "Trades", label: "Ledger", icon: BarChart3 },
];

const OVERFLOW_TABS: Array<{
  id: NavTab;
  label: string;
  icon: typeof LayoutDashboard;
}> = [
  { id: "Strategies", label: "Strategy", icon: Cpu },
  { id: "Backtesting", label: "Backtest", icon: FlaskConical },
  { id: "Risk", label: "Risk", icon: ShieldCheck },
  { id: "Settings", label: "Settings", icon: Settings },
];

export function MobileBottomNav({
  activeTab,
  onSelectTab,
  killSwitchActive,
  openPositionsCount,
  futuresEnabled,
}: MobileBottomNavProps) {
  const [moreOpen, setMoreOpen] = useState(false);

  const primaryTabs = PRIMARY_TABS.filter(
    (item) => item.id !== "Futures Trading" || futuresEnabled,
  );
  const overflowActive = OVERFLOW_TABS.some((item) => item.id === activeTab);

  const renderTab = (item: (typeof PRIMARY_TABS)[number], isActive: boolean) => {
    const Icon = item.icon;
    return (
      <button
        key={item.id}
        type="button"
        onClick={() => {
          setMoreOpen(false);
          onSelectTab(item.id);
        }}
        className={`flex flex-1 flex-col items-center justify-center min-w-0 py-1 px-1 rounded-lg transition-all ${
          isActive
            ? "text-cyan-300 font-bold bg-cyan-500/15"
            : "text-slate-400 hover:text-slate-200"
        }`}
      >
        <div className="relative">
          <Icon
            className={`h-4 w-4 ${
              isActive ? "text-cyan-400 drop-shadow-[0_0_6px_rgba(34,211,238,0.8)]" : ""
            }`}
          />
          {item.id === "Trades" && openPositionsCount > 0 && (
            <span className="absolute -top-1 -right-1.5 flex h-3 w-3 items-center justify-center rounded-full bg-cyan-500 text-[8px] font-bold text-black">
              {openPositionsCount}
            </span>
          )}
          {item.id === "Risk" && killSwitchActive && (
            <span className="absolute -top-1 -right-1.5 flex h-2.5 w-2.5 rounded-full bg-rose-500 animate-ping" />
          )}
        </div>
        <span className="mt-0.5 w-full truncate text-center font-mono text-[9px] tracking-tight">
          {item.label}
        </span>
      </button>
    );
  };

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-40 block lg:hidden border-t border-cyan-500/20 bg-[#070d1e]/95 backdrop-blur-xl shadow-2xl pb-safe"
      role="navigation"
      aria-label="Mobile Bottom Navigation"
    >
      {moreOpen && (
        <div className="absolute bottom-full left-0 right-0 mb-1.5 mx-2 rounded-xl border border-cyan-500/25 bg-[#070d1e]/98 p-2 shadow-2xl backdrop-blur-xl">
          <div className="mb-1.5 flex items-center justify-between px-1">
            <span className="font-mono text-[10px] font-semibold uppercase tracking-wider text-slate-400">
              More Tools
            </span>
            <button
              type="button"
              onClick={() => setMoreOpen(false)}
              className="rounded p-0.5 text-slate-400 hover:text-white"
              aria-label="Close more menu"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="grid grid-cols-4 gap-1.5">
            {OVERFLOW_TABS.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    setMoreOpen(false);
                    onSelectTab(item.id);
                  }}
                  className={`relative flex flex-col items-center justify-center rounded-lg border px-1 py-2 transition ${
                    isActive
                      ? "border-cyan-500/40 bg-cyan-500/15 text-cyan-300"
                      : "border-white/5 bg-slate-900/60 text-slate-300 hover:border-white/10"
                  }`}
                >
                  <Icon className="h-4 w-4" />
                  <span className="mt-1 font-mono text-[9px]">{item.label}</span>
                  {item.id === "Risk" && killSwitchActive && (
                    <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-rose-500 animate-pulse" />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div className="flex items-center justify-around gap-0.5 px-1 py-1.5">
        {primaryTabs.map((item) => renderTab(item, activeTab === item.id))}
        <button
          type="button"
          onClick={() => setMoreOpen((prev) => !prev)}
          aria-expanded={moreOpen}
          className={`flex flex-1 flex-col items-center justify-center min-w-0 py-1 px-1 rounded-lg transition-all ${
            overflowActive || moreOpen
              ? "text-cyan-300 font-bold bg-cyan-500/15"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <MoreHorizontal
            className={`h-4 w-4 ${
              overflowActive || moreOpen ? "text-cyan-400" : ""
            }`}
          />
          <span className="mt-0.5 w-full truncate text-center font-mono text-[9px] tracking-tight">
            More
          </span>
        </button>
      </div>
    </nav>
  );
}
