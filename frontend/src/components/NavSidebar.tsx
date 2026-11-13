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
}

const NAV_ITEMS: Array<{
  id: NavTab;
  label: string;
  sublabel: string;
  icon: typeof LayoutDashboard;
}> = [
  { id: "Overview", label: "Overview", sublabel: "3D Core & Live Feed", icon: LayoutDashboard },
  { id: "Futures Trading", label: "Futures Trading", sublabel: "USDT-M 1-5x Shorting", icon: Zap },
  { id: "Scanner & Radar", label: "Scanner & Radar", sublabel: "54 Markets & iPad HUD", icon: Radar },
  { id: "Strategies", label: "Strategies", sublabel: "V1 Engine & Signals", icon: Cpu },
  { id: "Trades", label: "Trades", sublabel: "Positions & Ledger", icon: BarChart3 },
  { id: "Backtesting", label: "Backtesting", sublabel: "OOS & Benchmark", icon: FlaskConical },
  { id: "Risk", label: "Risk", sublabel: "Limits & Kill Switch", icon: ShieldCheck },
  { id: "Settings", label: "Settings", sublabel: "Paper Config Guard", icon: Settings },
];

export function NavSidebar({
  activeTab,
  onSelectTab,
  killSwitchActive,
  openPositionsCount,
}: NavSidebarProps) {
  return (
    <aside className="flex shrink-0 flex-row gap-1 overflow-x-auto border-b border-cyan-500/20 bg-nexus-navy/85 p-2 lg:w-56 lg:flex-col lg:border-b-0 lg:border-r lg:p-3">
      <div className="hidden pb-2 lg:block">
        <p className="px-2 font-mono text-[10px] uppercase tracking-[0.2em] text-slate-400">
          Terminal Modules
        </p>
      </div>

      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const active = activeTab === item.id;
        return (
          <button
            key={item.id}
            type="button"
            onClick={() => onSelectTab(item.id)}
            className={`group flex shrink-0 items-center justify-between rounded-md border px-3 py-2 text-left transition ${
              active
                ? "border-cyan-400/50 bg-cyan-500/12 text-white shadow-[0_0_18px_rgba(34,211,238,0.12)]"
                : "border-transparent bg-transparent text-slate-400 hover:border-cyan-500/20 hover:bg-nexus-panel/60 hover:text-slate-200"
            }`}
          >
            <div className="flex items-center gap-2.5">
              <Icon
                className={`h-4 w-4 shrink-0 ${
                  active ? "text-cyan-400" : "text-slate-500 group-hover:text-cyan-300"
                }`}
              />
              <div>
                <div className="font-display text-xs font-medium tracking-wide sm:text-sm">
                  {item.label}
                </div>
                <div className="hidden font-mono text-[10px] text-slate-500 lg:block">
                  {item.sublabel}
                </div>
              </div>
            </div>

            {item.id === "Risk" && killSwitchActive && (
              <span
                className="ml-2 inline-block h-2 w-2 rounded-full bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.9)]"
                title="Kill switch active"
              />
            )}
            {item.id === "Trades" && openPositionsCount > 0 && (
              <span className="ml-2 rounded bg-cyan-500/20 px-1.5 py-0.5 font-mono text-[10px] text-cyan-300">
                {openPositionsCount}
              </span>
            )}
          </button>
        );
      })}

      <div className="mt-auto hidden rounded-md border border-cyan-500/15 bg-nexus-void/70 p-2.5 lg:block">
        <div className="flex items-center gap-1.5 font-mono text-[10px] text-cyan-300">
          <Activity className="h-3.5 w-3.5" />
          SPOT PAPER GUARD
        </div>
        <p className="mt-1 text-[11px] leading-relaxed text-slate-400">
          Zero leverage, zero futures, zero real exchange keys. All orders settle against local virtual INR ledger.
        </p>
      </div>
    </aside>
  );
}

