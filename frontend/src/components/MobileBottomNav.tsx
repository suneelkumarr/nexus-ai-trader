import {
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

interface MobileBottomNavProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  killSwitchActive: boolean;
  openPositionsCount: number;
}

const MOBILE_TABS: Array<{
  id: NavTab;
  label: string;
  icon: typeof LayoutDashboard;
}> = [
  { id: "Overview", label: "Overview", icon: LayoutDashboard },
  { id: "Futures Trading", label: "Futures", icon: Zap },
  { id: "Scanner & Radar", label: "Radar", icon: Radar },
  { id: "Strategies", label: "Strategy", icon: Cpu },
  { id: "Trades", label: "Ledger", icon: BarChart3 },
  { id: "Backtesting", label: "Backtest", icon: FlaskConical },
  { id: "Risk", label: "Risk", icon: ShieldCheck },
  { id: "Settings", label: "Settings", icon: Settings },
];

export function MobileBottomNav({
  activeTab,
  onSelectTab,
  killSwitchActive,
  openPositionsCount,
}: MobileBottomNavProps) {
  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-40 block lg:hidden border-t border-cyan-500/20 bg-[#070d1e]/95 backdrop-blur-xl shadow-2xl pb-safe"
      role="navigation"
      aria-label="Mobile Bottom Navigation"
    >
      <div className="flex items-center justify-around px-1 py-1.5 overflow-x-auto">
        {MOBILE_TABS.map((item) => {
          const Icon = item.icon;
          const isActive = activeTab === item.id;

          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelectTab(item.id)}
              className={`flex flex-col items-center justify-center min-w-[52px] py-1 px-1 rounded-lg transition-all ${
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
              <span className="mt-0.5 font-mono text-[9px] tracking-tight truncate max-w-[56px]">
                {item.label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
