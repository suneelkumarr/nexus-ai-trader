import { Lock, Settings as SettingsIcon } from "lucide-react";
import type { SanitizedSettingsResponse } from "../../types/system";
import { formatInr } from "../../utils/format";

interface SettingsViewProps {
  settings: SanitizedSettingsResponse | null;
  error: string | null;
}

export function SettingsView({ settings, error }: SettingsViewProps) {
  if (error) {
    return (
      <div className="nexus-panel rounded-lg p-4 font-mono text-xs text-amber-300">
        Unable to load backend runtime configuration: {error}
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="nexus-panel rounded-lg p-6 font-mono text-xs text-slate-400">
        Loading sanitized FastAPI settings...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="nexus-panel rounded-lg p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <SettingsIcon className="h-4 w-4 text-cyan-400" />
            <h2 className="font-display text-base font-semibold text-white">
              Sanitized System Configuration
            </h2>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded border border-emerald-500/35 bg-emerald-500/10 px-2.5 py-0.5 font-mono text-[11px] text-emerald-300">
            <Lock className="h-3.5 w-3.5" />
            SECRETS REDACTED · PAPER SAFETY LOCKED
          </span>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4 font-mono text-xs">
          <div className="rounded border border-cyan-500/15 bg-nexus-void/80 p-3">
            <div className="text-[10px] uppercase text-slate-400">Trading Mode</div>
            <div className="mt-1 font-semibold uppercase text-amber-300">
              {settings.trading_mode} ({settings.market_type})
            </div>
          </div>
          <div className="rounded border border-cyan-500/15 bg-nexus-void/80 p-3">
            <div className="text-[10px] uppercase text-slate-400">Live Trading Enabled</div>
            <div className="mt-1 font-semibold text-emerald-300">
              {settings.live_trading_enabled ? "TRUE" : "FALSE (LOCKED)"}
            </div>
          </div>
          <div className="rounded border border-cyan-500/15 bg-nexus-void/80 p-3">
            <div className="text-[10px] uppercase text-slate-400">Initial Capital</div>
            <div className="mt-1 font-semibold text-white">
              {formatInr(settings.initial_capital_inr)}
            </div>
          </div>
          <div className="rounded border border-cyan-500/15 bg-nexus-void/80 p-3">
            <div className="text-[10px] uppercase text-slate-400">Public Feed Exchange</div>
            <div className="mt-1 font-semibold uppercase text-cyan-300">
              {settings.exchange_id} (PUBLIC ONLY)
            </div>
          </div>
          <div className="rounded border border-cyan-500/15 bg-nexus-void/80 p-3">
            <div className="text-[10px] uppercase text-slate-400">Spot Constraints</div>
            <div className="mt-1 text-slate-200">
              Leverage: {String(settings.allow_leverage)} · Futures: {String(settings.allow_futures)}
            </div>
          </div>
          <div className="rounded border border-cyan-500/15 bg-nexus-void/80 p-3">
            <div className="text-[10px] uppercase text-slate-400">Withdrawals</div>
            <div className="mt-1 font-semibold text-emerald-300">
              {settings.allow_withdrawals ? "ALLOWED" : "DISABLED"}
            </div>
          </div>
          <div className="rounded border border-cyan-500/15 bg-nexus-void/80 p-3">
            <div className="text-[10px] uppercase text-slate-400">Paper Fee / Slippage</div>
            <div className="mt-1 text-white">
              {settings.paper_fee_bps} bps / {settings.paper_slippage_bps} bps
            </div>
          </div>
          <div className="rounded border border-cyan-500/15 bg-nexus-void/80 p-3">
            <div className="text-[10px] uppercase text-slate-400">AI Advisory Engine</div>
            <div className="mt-1 text-gold-300">
              {settings.ai_enabled ? `${settings.ai_provider} (${settings.ai_model})` : "Disabled"}
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="nexus-panel rounded-lg p-4">
          <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
            Risk Manager Ruleset
          </h3>
          <dl className="mt-3 divide-y divide-slate-800/80 font-mono text-xs">
            {Object.entries(settings.risk).map(([key, val]) => (
              <div key={key} className="flex items-center justify-between py-2">
                <dt className="text-slate-400">{key}</dt>
                <dd className="tabular-nums text-cyan-300">{String(val)}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="nexus-panel rounded-lg p-4">
          <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
            Market Universe & Strategy Defaults
          </h3>
          <dl className="mt-3 divide-y divide-slate-800/80 font-mono text-xs">
            <div className="flex items-center justify-between py-2">
              <dt className="text-slate-400">allowed_symbols</dt>
              <dd className="text-white">{settings.allowed_symbols.join(", ")}</dd>
            </div>
            <div className="flex items-center justify-between py-2">
              <dt className="text-slate-400">supported_timeframes</dt>
              <dd className="text-white">{settings.supported_timeframes.join(", ")}</dd>
            </div>
            <div className="flex items-center justify-between py-2">
              <dt className="text-slate-400">default_timeframe</dt>
              <dd className="text-cyan-300">{settings.default_timeframe}</dd>
            </div>
            {Object.entries(settings.strategy_v1).map(([key, val]) => (
              <div key={key} className="flex items-center justify-between py-2">
                <dt className="text-slate-400">{key}</dt>
                <dd className="tabular-nums text-gold-300">{String(val)}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </div>
  );
}

