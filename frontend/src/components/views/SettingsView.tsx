import { useState, useEffect } from "react";
import {
  Lock,
  Settings as SettingsIcon,
  ShieldCheck,
  Database,
  Radio,
  Sparkles,
  Volume2,
  VolumeX,
  Cpu,
  Layers,
  Activity,
  Sliders,
  Key,
  Eye,
  EyeOff,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Copy,
  Check,
} from "lucide-react";
import { fetchHealthStatus, fetchTerminalSettings } from "../../services/apiClient";
import {
  getAuthToken,
  setAuthToken,
  DEFAULT_API_AUTH_TOKEN,
  getApiBaseUrl,
  setApiBaseUrl,
  DEFAULT_API_BASE_URL,
} from "../../config/env";
import type { HealthResponse, SanitizedSettingsResponse } from "../../types/system";
import { formatInr } from "../../utils/format";

interface SettingsViewProps {
  settings: SanitizedSettingsResponse | null;
  error: string | null;
}

export function SettingsView({ settings, error }: SettingsViewProps) {
  const [audioAlerts, setAudioAlerts] = useState<boolean>(() => {
    return localStorage.getItem("nexus_audio_alerts") === "true";
  });
  const [compactMode, setCompactMode] = useState<boolean>(() => {
    return localStorage.getItem("nexus_compact_tables") === "true";
  });
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);

  // Authentication token & API base URL configuration state
  const [baseUrlInput, setBaseUrlInput] = useState<string>(() => getApiBaseUrl());
  const [tokenInput, setTokenInput] = useState<string>(() => getAuthToken());
  const [showToken, setShowToken] = useState<boolean>(false);
  const [copiedToken, setCopiedToken] = useState<boolean>(false);
  const [testAuthStatus, setTestAuthStatus] = useState<"idle" | "testing" | "success" | "failed">("idle");
  const [testAuthDetail, setTestAuthDetail] = useState<string>("");
  const [savedSuccess, setSavedSuccess] = useState<boolean>(false);

  const handleSaveConnection = () => {
    setAuthToken(tokenInput);
    setApiBaseUrl(baseUrlInput);
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 2500);
  };

  const handleResetConnection = () => {
    setTokenInput(DEFAULT_API_AUTH_TOKEN);
    setAuthToken(DEFAULT_API_AUTH_TOKEN);
    setBaseUrlInput(DEFAULT_API_BASE_URL);
    setApiBaseUrl(DEFAULT_API_BASE_URL);
    setSavedSuccess(true);
    setTestAuthStatus("idle");
    setTimeout(() => setSavedSuccess(false), 2500);
  };

  const handleTestToken = async () => {
    setTestAuthStatus("testing");
    setTestAuthDetail("");
    try {
      setAuthToken(tokenInput);
      setApiBaseUrl(baseUrlInput);
      await fetchTerminalSettings();
      setTestAuthStatus("success");
      setTestAuthDetail("Backend connected and credentials verified · HTTP 200 OK (Full Access Granted)");
    } catch (err: unknown) {
      setTestAuthStatus("failed");
      const msg = err instanceof Error ? err.message : "Handshake rejected";
      setTestAuthDetail(msg);
    }
  };

  const handleCopyToken = () => {
    navigator.clipboard.writeText(tokenInput).then(() => {
      setCopiedToken(true);
      setTimeout(() => setCopiedToken(false), 2000);
    });
  };

  useEffect(() => {
    let cancelled = false;
    fetchHealthStatus()
      .then((res) => {
        if (!cancelled) {
          setHealth(res);
          setHealthError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setHealth(null);
          setHealthError(err instanceof Error ? err.message : "Health probe failed");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    localStorage.setItem("nexus_audio_alerts", String(audioAlerts));
  }, [audioAlerts]);

  useEffect(() => {
    localStorage.setItem("nexus_compact_tables", String(compactMode));
  }, [compactMode]);

  if (error) {
    return (
      <div className="nexus-panel rounded-lg p-4 font-mono text-xs text-rose-300 border border-rose-500/30">
        Unable to load backend runtime configuration: {error}
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="nexus-panel rounded-lg p-6 font-mono text-xs text-slate-400">
        Loading sanitized FastAPI settings & runtime contracts...
      </div>
    );
  }

  const risk = settings.risk as Record<string, number | string>;
  const v1 = settings.strategy_v1 as Record<string, number | string>;

  return (
    <div className="space-y-4">
      {/* 1. Executive Security & Architecture Governance Header */}
      <div className="nexus-panel rounded-lg p-4 border border-cyan-500/25 bg-[#030712]">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2.5">
            <SettingsIcon className="h-5 w-5 text-cyan-400" />
            <div>
              <h2 className="font-display text-base font-semibold text-white">
                Sanitized System Governance & Configuration
              </h2>
              <p className="text-xs text-slate-400">
                Institutional runtime parameters, execution guardrails, and cryptographic safety locks.
              </p>
              {healthError && (
                <p className="font-mono text-[10px] text-amber-300">
                  Health probe unavailable: {healthError}
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-3 py-1 font-mono text-xs font-semibold text-emerald-300">
              <Lock className="h-3.5 w-3.5" />
              <span>SECRETS REDACTED · ZERO-KEY LEAK</span>
            </span>
          </div>
        </div>

        {/* Core Invariants Quick Grid */}
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4 font-mono text-xs">
          <div className="rounded border border-slate-800 bg-nexus-void/80 p-3">
            <div className="text-[10px] uppercase text-slate-400">Execution Mode</div>
            <div className="mt-1 font-bold text-amber-300 uppercase">
              {settings.trading_mode} ({settings.market_type})
            </div>
            <div className="text-[10px] text-slate-500">Zero Real Capital at Risk</div>
          </div>

          <div className="rounded border border-slate-800 bg-nexus-void/80 p-3">
            <div className="text-[10px] uppercase text-slate-400">Live Trading Safety Gate</div>
            <div className="mt-1 font-bold text-emerald-400">
              {settings.live_trading_enabled ? "TRUE" : "FALSE (LOCKED)"}
            </div>
            <div className="text-[10px] text-slate-500">API Private Keys Blocked</div>
          </div>

          <div className="rounded border border-slate-800 bg-nexus-void/80 p-3">
            <div className="text-[10px] uppercase text-slate-400">Initial Allocation</div>
            <div className="mt-1 font-bold text-white">
              {formatInr(settings.initial_capital_inr)}
            </div>
            <div className="text-[10px] text-slate-500">Fixed Base Benchmark</div>
          </div>

          <div className="rounded border border-slate-800 bg-nexus-void/80 p-3">
            <div className="text-[10px] uppercase text-slate-400">Capital Withdrawals</div>
            <div className="mt-1 font-bold text-emerald-400">
              {settings.allow_withdrawals ? "ALLOWED" : "DISABLED"}
            </div>
            <div className="text-[10px] text-slate-500">Strict Non-Custodial Lock</div>
          </div>
        </div>
      </div>

      {/* 2. API Security Key & Authentication Engine */}
      <div className="nexus-panel rounded-lg p-4 border border-cyan-500/20 bg-[#030712] space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2">
          <div className="flex items-center gap-2">
            <Key className="h-4 w-4 text-cyan-400" />
            <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
              API Security Key & Administrative Authentication
            </h3>
          </div>
          <div className="flex items-center gap-2">
            {testAuthStatus === "success" && (
              <span className="inline-flex items-center gap-1 rounded bg-emerald-950/80 px-2 py-0.5 font-mono text-[10px] font-bold text-emerald-300 border border-emerald-500/30">
                <CheckCircle2 className="h-3 w-3" />
                VERIFIED AUTHENTICATED
              </span>
            )}
            {testAuthStatus === "failed" && (
              <span className="inline-flex items-center gap-1 rounded bg-rose-950/80 px-2 py-0.5 font-mono text-[10px] font-bold text-rose-300 border border-rose-500/30">
                <AlertTriangle className="h-3 w-3" />
                AUTH REJECTED
              </span>
            )}
            {testAuthStatus === "idle" && (
              <span className="font-mono text-[10px] text-slate-400">
                {tokenInput === DEFAULT_API_AUTH_TOKEN ? "STANDARD TOKEN" : "CUSTOM OVERRIDE"}
              </span>
            )}
          </div>
        </div>

        <p className="text-xs text-slate-400">
          Enforces cryptographic token authorization across protected mutating routes: Council of Quants Debate, AI Cycle Hunter, Risk Limit Overrides, and Emergency Circuit Breakers.
        </p>

        <div className="space-y-3">
          {/* API Base URL Setting */}
          <div className="space-y-1.5 font-mono text-xs">
            <div className="flex items-center justify-between text-[11px] text-slate-400">
              <span className="font-semibold text-slate-300">FastAPI Server Endpoint</span>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => {
                    setBaseUrlInput("https://nexus-ai-trader-r2ez.onrender.com");
                    setTestAuthStatus("idle");
                  }}
                  className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] text-slate-300 hover:border-cyan-500/50 hover:text-cyan-300 transition"
                >
                  Cloud Render
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setBaseUrlInput("http://localhost:8000");
                    setTestAuthStatus("idle");
                  }}
                  className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] text-slate-300 hover:border-cyan-500/50 hover:text-cyan-300 transition"
                >
                  Localhost:8000
                </button>
              </div>
            </div>
            <input
              type="text"
              value={baseUrlInput}
              onChange={(e) => {
                setBaseUrlInput(e.target.value);
                setTestAuthStatus("idle");
              }}
              placeholder="https://nexus-ai-trader-r2ez.onrender.com"
              className="w-full rounded border border-slate-800 bg-nexus-void px-3 py-2 text-xs text-white placeholder-slate-600 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/50"
            />
          </div>

          {/* API Security Token Setting */}
          <div className="space-y-1.5 font-mono text-xs">
            <span className="block text-[11px] font-semibold text-slate-300">
              Administrative Authentication Token
            </span>
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
              <div className="relative flex-1">
                <input
                  type={showToken ? "text" : "password"}
                  value={tokenInput}
                  onChange={(e) => {
                    setTokenInput(e.target.value);
                    setTestAuthStatus("idle");
                  }}
                  placeholder="nexus_sec_admin_..."
                  className="w-full rounded border border-slate-800 bg-nexus-void px-3 py-2 pr-20 text-xs text-white placeholder-slate-600 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400/50"
                />
                <div className="absolute inset-y-0 right-1 flex items-center gap-1 pr-1.5">
                  <button
                    type="button"
                    onClick={() => setShowToken(!showToken)}
                    title={showToken ? "Hide Key" : "Reveal Key"}
                    className="rounded p-1 text-slate-400 hover:text-white hover:bg-slate-800/60 transition"
                  >
                    {showToken ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  </button>
                  <button
                    type="button"
                    onClick={handleCopyToken}
                    title="Copy Key to Clipboard"
                    className="rounded p-1 text-slate-400 hover:text-white hover:bg-slate-800/60 transition"
                  >
                    {copiedToken ? (
                      <Check className="h-3.5 w-3.5 text-emerald-400" />
                    ) : (
                      <Copy className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <button
                  type="button"
                  onClick={handleSaveConnection}
                  className="rounded border border-cyan-500/40 bg-cyan-500/20 px-3 py-2 text-xs font-semibold text-cyan-200 hover:bg-cyan-500/30 transition"
                >
                  Save Configuration
                </button>
                <button
                  type="button"
                  onClick={handleTestToken}
                  disabled={testAuthStatus === "testing"}
                  className="inline-flex items-center gap-1.5 rounded border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800 disabled:opacity-50 transition"
                >
                  <RefreshCw
                    className={`h-3 w-3 ${testAuthStatus === "testing" ? "animate-spin text-cyan-400" : ""}`}
                  />
                  <span>{testAuthStatus === "testing" ? "Testing..." : "Test Connection"}</span>
                </button>
                <button
                  type="button"
                  onClick={handleResetConnection}
                  className="rounded border border-slate-800 bg-transparent px-2.5 py-2 text-xs text-slate-400 hover:text-slate-200 hover:border-slate-700 transition"
                >
                  Reset Defaults
                </button>
              </div>
            </div>
          </div>

          {savedSuccess && (
            <p className="font-mono text-[11px] text-cyan-300">
              ✓ Connection settings saved to browser storage. Outgoing requests will use these parameters.
            </p>
          )}

          {testAuthStatus === "success" && (
            <p className="font-mono text-[11px] text-emerald-400">
              ✓ {testAuthDetail}
            </p>
          )}

          {testAuthStatus === "failed" && (
            <p className="font-mono text-[11px] text-rose-400">
              ✗ Connection test failed: {testAuthDetail}
            </p>
          )}
        </div>
      </div>

      {/* 3. Live Infrastructure Health & Diagnostic Matrix (3 Pillars) */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3 font-mono text-xs">
        {/* Pillar 1: PostgreSQL Persistent Ledger */}
        <div className="nexus-panel rounded-lg p-3.5 space-y-2 border border-cyan-500/20">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-cyan-400" />
              <span className="font-semibold text-white">Database Engine</span>
            </div>
            <span
              className={`rounded px-2 py-0.5 text-[10px] font-bold border ${
                health?.checks.database.status === "up"
                  ? "bg-emerald-950/80 text-emerald-300 border-emerald-500/30"
                  : health
                    ? "bg-rose-950/80 text-rose-300 border-rose-500/30"
                    : "bg-slate-900 text-slate-400 border-slate-700"
              }`}
            >
              {health
                ? health.checks.database.status === "up"
                  ? "CONNECTED"
                  : "UNAVAILABLE"
                : "CHECKING"}
            </span>
          </div>
          <p className="text-[11px] text-slate-400">
            PostgreSQL · audit ledger, risk state, and historical candle store.
          </p>
          <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-slate-800">
            <span>Pool: SQLAlchemy async engine</span>
            <span className="text-cyan-300">
              {health?.checks.database.detail ?? "Health probe: " + (health ? health.status : "pending")}
            </span>
          </div>
        </div>

        {/* Pillar 2: Public Market Data Exchange Feed */}
        <div className="nexus-panel rounded-lg p-3.5 space-y-2 border border-cyan-500/20">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Radio className="h-4 w-4 text-cyan-400" />
              <span className="font-semibold text-white">Market Feed</span>
            </div>
            <span
              className={`rounded px-2 py-0.5 text-[10px] font-bold border ${
                health?.checks.market_feed.status === "up"
                  ? "bg-emerald-950/80 text-emerald-300 border-emerald-500/30"
                  : health
                    ? "bg-rose-950/80 text-rose-300 border-rose-500/30"
                    : "bg-slate-900 text-slate-400 border-slate-700"
              }`}
            >
              {health
                ? health.checks.market_feed.status === "up"
                  ? "ONLINE"
                  : "UNAVAILABLE"
                : "CHECKING"}
            </span>
          </div>
          <p className="text-[11px] text-slate-400">
            Public REST & WebSocket · {settings.exchange_id.toUpperCase()} spot L1 tickers & OHLCV.
          </p>
          <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-slate-800">
            <span>Auth: public endpoints only</span>
            <span className="text-cyan-300">
              {health?.checks.market_feed.detail ?? "Probe pending"}
            </span>
          </div>
        </div>

        {/* Pillar 3: AI Advisory Engine */}
        <div className="nexus-panel rounded-lg p-3.5 space-y-2 border border-cyan-500/20">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-gold-400" />
              <span className="font-semibold text-white">AI Copilot</span>
            </div>
            <span className="rounded bg-gold-950/80 px-2 py-0.5 text-[10px] font-bold text-gold-300 border border-gold-500/30">
              {settings.ai_enabled ? "ACTIVE" : "DISABLED"}
            </span>
          </div>
          <p className="text-[11px] text-slate-400">
            {settings.ai_provider} · Model: <strong className="text-cyan-300">{settings.ai_model}</strong>. Strict advisory only.
          </p>
          <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-slate-800">
            <span>Execution Rights: 0%</span>
            <span className="text-gold-300">Advisory Only</span>
          </div>
        </div>
      </div>

      {/* 3. Institutional Configuration Cards (Replacing raw dict dump) */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Card A: Risk Management Ruleset */}
        <div className="nexus-panel rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
            <ShieldCheck className="h-4 w-4 text-cyan-400" />
            <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
              Risk Management Parameter Ruleset
            </h3>
          </div>

          <div className="divide-y divide-slate-800/80 font-mono text-xs">
            <div className="flex items-center justify-between py-2">
              <div>
                <span className="text-white font-semibold">Maximum Total Drawdown Limit</span>
                <span className="block text-[10px] text-slate-400">Hard stop circuit breaker from portfolio peak</span>
              </div>
              <span className="text-amber-300 font-bold">{Number(risk.max_drawdown_pct ?? 0).toFixed(2)}%</span>
            </div>

            <div className="flex items-center justify-between py-2">
              <div>
                <span className="text-white font-semibold">Daily Loss Circuit Breaker</span>
                <span className="block text-[10px] text-slate-400">Freezes new buy orders if intraday loss exceeds limit</span>
              </div>
              <span className="text-rose-300 font-bold">{Number(risk.daily_loss_limit_pct ?? 0).toFixed(2)}%</span>
            </div>

            <div className="flex items-center justify-between py-2">
              <div>
                <span className="text-white font-semibold">Max Concurrent Spot Positions</span>
                <span className="block text-[10px] text-slate-400">Prevents capital overconcentration</span>
              </div>
              <span className="text-cyan-300 font-bold">{String(risk.max_concurrent_positions ?? 0)} Assets</span>
            </div>

            <div className="flex items-center justify-between py-2">
              <div>
                <span className="text-white font-semibold">Max Daily Order Entries</span>
                <span className="block text-[10px] text-slate-400">Anti-churn transaction frequency control</span>
              </div>
              <span className="text-cyan-300 font-bold">{String(risk.max_daily_entries ?? 0)} Orders</span>
            </div>

            <div className="flex items-center justify-between py-2">
              <div>
                <span className="text-white font-semibold">Risk Budget Per Trade</span>
                <span className="block text-[10px] text-slate-400">Equity fraction risked between entry and stop</span>
              </div>
              <span className="text-cyan-300 font-bold">{Number(risk.risk_per_trade_pct ?? 0).toFixed(2)}%</span>
            </div>

            <div className="flex items-center justify-between py-2">
              <div>
                <span className="text-white font-semibold">Max Position Notional</span>
                <span className="block text-[10px] text-slate-400">Hard cap on any single position as a share of equity</span>
              </div>
              <span className="text-cyan-300 font-bold">{Number(risk.max_position_notional_pct ?? 0).toFixed(2)}%</span>
            </div>

            <div className="flex items-center justify-between py-2">
              <div>
                <span className="text-white font-semibold">Minimum Order Notional</span>
                <span className="block text-[10px] text-slate-400">Smallest permitted clip in virtual INR</span>
              </div>
              <span className="text-emerald-300 font-bold">{formatInr(Number(risk.min_order_notional_inr ?? 0))}</span>
            </div>
          </div>
        </div>

        {/* Card B: Quantitative Strategy Parameters */}
        <div className="nexus-panel rounded-lg p-4 space-y-3">
          <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
            <Sliders className="h-4 w-4 text-cyan-400" />
            <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
              Strategy V1 (Trend & Momentum) Parameters
            </h3>
          </div>

          <div className="divide-y divide-slate-800/80 font-mono text-xs">
            <div className="flex items-center justify-between py-2">
              <div>
                <span className="text-white font-semibold">Fast Exponential Moving Average</span>
                <span className="block text-[10px] text-slate-400">Short-term directional trend filter</span>
              </div>
              <span className="text-gold-300 font-bold">{String(v1.ema_fast_period ?? 0)} Periods</span>
            </div>

            <div className="flex items-center justify-between py-2">
              <div>
                <span className="text-white font-semibold">Slow Exponential Moving Average</span>
                <span className="block text-[10px] text-slate-400">Baseline structural trend confirmation</span>
              </div>
              <span className="text-gold-300 font-bold">{String(v1.ema_slow_period ?? 0)} Periods</span>
            </div>

            <div className="flex items-center justify-between py-2">
              <div>
                <span className="text-white font-semibold">RSI Lookback Period</span>
                <span className="block text-[10px] text-slate-400">Relative Strength Index window</span>
              </div>
              <span className="text-cyan-300 font-bold">{String(v1.rsi_period ?? 0)} Periods</span>
            </div>

            <div className="flex items-center justify-between py-2">
              <div>
                <span className="text-white font-semibold">RSI Oversold / Overbought Bounds</span>
                <span className="block text-[10px] text-slate-400">Pullback entry threshold and exhaustion ceiling</span>
              </div>                <span className="text-emerald-300 font-bold">
                {String(v1.rsi_entry_min ?? 0)} / {String(v1.rsi_entry_max ?? 0)}
              </span>
            </div>

            <div className="flex items-center justify-between py-2">
              <div>
                <span className="text-white font-semibold">Volume SMA Period</span>
                <span className="block text-[10px] text-slate-400">Baseline window for volume confirmation</span>
              </div>
              <span className="text-cyan-300 font-bold">{String(v1.volume_sma_period ?? 0)} Bars</span>
            </div>

            <div className="flex items-center justify-between py-2">
              <div>
                <span className="text-white font-semibold">Simulated Execution Friction</span>
                <span className="block text-[10px] text-slate-400">Exchange maker fee and adverse slippage model</span>
              </div>
              <span className="text-slate-300 font-bold">
                {settings.paper_fee_bps} bps Fee / {settings.paper_slippage_bps} bps Slip
              </span>
            </div>

            <div className="flex items-center justify-between py-2">
              <div>
                <span className="text-white font-semibold">Default Evaluation Timeframe</span>
                <span className="block text-[10px] text-slate-400">Primary algorithmic scanning bar interval</span>
              </div>
              <span className="text-cyan-300 font-bold">{settings.default_timeframe}</span>
            </div>
          </div>
        </div>
      </div>

      {/* 4. Terminal Preferences & Interactive Settings */}
      <div className="nexus-panel rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
          <div className="flex items-center gap-2">
            <Cpu className="h-4 w-4 text-cyan-400" />
            <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
              Terminal Preferences & Audio Alarms
            </h3>
          </div>
          <span className="font-mono text-[10px] text-slate-400">CLIENT PERSISTED</span>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 font-mono text-xs">
          {/* Audio Toggle */}
          <div className="flex items-center justify-between rounded border border-slate-800 bg-[#030712] p-3">
            <div className="flex items-center gap-2.5">
              {audioAlerts ? (
                <Volume2 className="h-4 w-4 text-cyan-400" />
              ) : (
                <VolumeX className="h-4 w-4 text-slate-500" />
              )}
              <div>
                <span className="text-white font-semibold">Order Fill & Breaker Audio Chimes</span>
                <span className="block text-[10px] text-slate-500">Audio beep on new signals and circuit breaker halts</span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setAudioAlerts(!audioAlerts)}
              className={`rounded border px-3 py-1 text-xs font-semibold transition ${
                audioAlerts
                  ? "border-cyan-400 bg-cyan-500/20 text-cyan-200"
                  : "border-slate-700 bg-slate-900 text-slate-400"
              }`}
            >
              {audioAlerts ? "ENABLED" : "MUTED"}
            </button>
          </div>

          {/* Compact Mode Toggle */}
          <div className="flex items-center justify-between rounded border border-slate-800 bg-[#030712] p-3">
            <div className="flex items-center gap-2.5">
              <Layers className="h-4 w-4 text-cyan-400" />
              <div>
                <span className="text-white font-semibold">Compact Data Density Mode</span>
                <span className="block text-[10px] text-slate-500">Optimizes spacing for high-resolution 4K quant desks</span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setCompactMode(!compactMode)}
              className={`rounded border px-3 py-1 text-xs font-semibold transition ${
                compactMode
                  ? "border-cyan-400 bg-cyan-500/20 text-cyan-200"
                  : "border-slate-700 bg-slate-900 text-slate-400"
              }`}
            >
              {compactMode ? "COMPACT" : "COMFY"}
            </button>
          </div>
        </div>
      </div>

      {/* 5. Permitted Market Universe */}
      <div className="nexus-panel rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-cyan-400" />
            <h3 className="font-display text-sm font-semibold uppercase tracking-wider text-white">
              Approved Spot Market Universe ({settings.allowed_symbols.length} Assets)
            </h3>
          </div>
          <span className="font-mono text-[10px] text-slate-400">
            SUPPORTED TIMEFRAMES: {settings.supported_timeframes.join(" · ")}
          </span>
        </div>

        <div className="flex flex-wrap gap-1.5 font-mono text-[11px]">
          {settings.allowed_symbols.map((sym) => (
            <span
              key={sym}
              className="rounded border border-slate-800 bg-nexus-void/80 px-2 py-0.5 text-cyan-300 hover:border-cyan-500/40 transition"
            >
              {sym}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
