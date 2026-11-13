import { frontendConfig } from "../config/env";
import type {
  BacktestSuiteReport,
  EmergencyStopResponse,
  HealthResponse,
  MarketAnalysisOutput,
  SanitizedSettingsResponse,
  StrategySignal,
  TerminalSnapshotResponse,
} from "../types/system";

export class ApiError extends Error {
  readonly statusCode: number;

  constructor(message: string, statusCode: number) {
    super(message);
    this.name = "ApiError";
    this.statusCode = statusCode;
  }
}

async function requestJson<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const baseUrl = frontendConfig.apiBaseUrl.replace(/\/+$/, "");
  const authHeaders: Record<string, string> = frontendConfig.apiAuthToken
    ? {
        Authorization: `Bearer ${frontendConfig.apiAuthToken}`,
        "X-Nexus-API-Key": frontendConfig.apiAuthToken,
      }
    : {};
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...authHeaders,
      ...init.headers,
    },
  });

  if (!response.ok) {
    let detail = `Request failed with HTTP ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string" && payload.detail.length > 0) {
        detail = payload.detail;
      }
    } catch {
      // Preserve HTTP status fallback when error body is not JSON.
    }
    throw new ApiError(detail, response.status);
  }

  return (await response.json()) as T;
}

export function buildTerminalWebSocketUrl(): string {
  const baseUrl = frontendConfig.apiBaseUrl.replace(/\/+$/, "");
  const tokenQuery = frontendConfig.apiAuthToken
    ? `?token=${encodeURIComponent(frontendConfig.apiAuthToken)}`
    : "";
  if (baseUrl.startsWith("https://")) {
    return `wss://${baseUrl.slice("https://".length)}/api/v1/ws/stream${tokenQuery}`;
  }
  if (baseUrl.startsWith("http://")) {
    return `ws://${baseUrl.slice("http://".length)}/api/v1/ws/stream${tokenQuery}`;
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${baseUrl}/api/v1/ws/stream${tokenQuery}`;
}

export async function fetchHealthStatus(signal?: AbortSignal): Promise<HealthResponse> {
  return requestJson<HealthResponse>("/api/v1/health", { method: "GET", signal });
}

export async function fetchTerminalSnapshot(
  signal?: AbortSignal,
): Promise<TerminalSnapshotResponse> {
  return requestJson<TerminalSnapshotResponse>("/api/v1/terminal/snapshot", {
    method: "GET",
    signal,
  });
}

export async function triggerEmergencyStop(params: {
  reason: string;
  flatten_positions: boolean;
}): Promise<EmergencyStopResponse> {
  return requestJson<EmergencyStopResponse>("/api/v1/terminal/emergency-stop", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function fetchCandleAnalysis(params: {
  symbol: string;
  timeframe: string;
  lookback_bars: number;
  strategy_signals?: StrategySignal[];
}): Promise<MarketAnalysisOutput> {
  return requestJson<MarketAnalysisOutput>("/api/v1/analysis/from-candles", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function runOosBacktest(params: {
  symbol: string;
  timeframe: string;
  strategy_id?: string;
  maker_fee_bps: number;
  taker_fee_bps: number;
  spread_bps: number;
  slippage_bps: number;
  lookback_bars: number;
}): Promise<BacktestSuiteReport> {
  return requestJson<BacktestSuiteReport>("/api/v1/terminal/backtest", {
    method: "POST",
    body: JSON.stringify(params),
  });
}

export async function fetchCandleSeries(params: {
  symbol: string;
  timeframe: string;
  limit?: number;
  signal?: AbortSignal;
}): Promise<import("../types/system").CandleSeriesResponse> {
  const q = new URLSearchParams({
    symbol: params.symbol,
    timeframe: params.timeframe,
    limit: String(params.limit ?? 250),
  }).toString();
  return requestJson<import("../types/system").CandleSeriesResponse>(
    `/api/v1/terminal/candles?${q}`,
    {
      method: "GET",
      signal: params.signal,
    },
  );
}

export async function fetchCandlesStatus(params: {
  symbol: string;
  timeframe: string;
  signal?: AbortSignal;
}): Promise<import("../types/system").CandlesStatusResponse> {
  const q = new URLSearchParams({
    symbol: params.symbol,
    timeframe: params.timeframe,
  }).toString();
  return requestJson<import("../types/system").CandlesStatusResponse>(
    `/api/v1/terminal/candles/status?${q}`,
    {
      method: "GET",
      signal: params.signal,
    },
  );
}

export async function syncCandles(params: {
  symbol: string;
  timeframe: string;
  lookback_bars?: number;
}): Promise<import("../types/system").SyncCandlesResponse> {
  return requestJson<import("../types/system").SyncCandlesResponse>(
    "/api/v1/terminal/candles/sync",
    {
      method: "POST",
      body: JSON.stringify({
        symbol: params.symbol,
        timeframe: params.timeframe,
        lookback_bars: params.lookback_bars ?? 250,
      }),
    },
  );
}

export async function fetchTerminalSettings(
  signal?: AbortSignal,
): Promise<SanitizedSettingsResponse> {
  return requestJson<SanitizedSettingsResponse>("/api/v1/terminal/settings", {
    method: "GET",
    signal,
  });
}

export async function fetchArbitrageScan(
  signal?: AbortSignal,
): Promise<import("../types/arbitrage").MultiMarketScanResponse> {
  return requestJson<import("../types/arbitrage").MultiMarketScanResponse>(
    "/api/v1/arbitrage/scan",
    {
      method: "GET",
      signal,
    },
  );
}

export async function executePaperArbitrageLeg(params: {
  opportunity_id: string;
  allocated_usdt: number;
}): Promise<import("../types/arbitrage").ExecutePaperArbResponse> {
  return requestJson<import("../types/arbitrage").ExecutePaperArbResponse>(
    "/api/v1/arbitrage/execute-paper-leg",
    {
      method: "POST",
      body: JSON.stringify(params),
    },
  );
}

export async function fetchAutonomousStatus(
  signal?: AbortSignal,
): Promise<import("../types/system").AutonomousEngineStatus> {
  return requestJson<import("../types/system").AutonomousEngineStatus>(
    "/api/v1/autonomous/status",
    {
      method: "GET",
      signal,
    },
  );
}

export async function triggerAutonomousCycle(): Promise<Record<string, unknown>> {
  return requestJson<Record<string, unknown>>("/api/v1/autonomous/cycle", {
    method: "POST",
  });
}

export async function toggleAutonomousEngine(): Promise<{ is_running: boolean; message: string }> {
  return requestJson<{ is_running: boolean; message: string }>("/api/v1/autonomous/toggle", {
    method: "POST",
  });
}

export async function fetchAIResearch(
  signal?: AbortSignal,
): Promise<import("../types/system").AIResearchBriefing> {
  return requestJson<import("../types/system").AIResearchBriefing>(
    "/api/v1/autonomous/ai-research",
    {
      method: "GET",
      signal,
    },
  );
}

export async function refreshAIResearch(): Promise<import("../types/system").AIResearchBriefing> {
  return requestJson<import("../types/system").AIResearchBriefing>(
    "/api/v1/autonomous/ai-research/refresh",
    {
      method: "POST",
    },
  );
}

// ---------------------------------------------------------------------------
// Crypto Futures Paper Trading Endpoints
// ---------------------------------------------------------------------------

export async function fetchFuturesSummary(
  signal?: AbortSignal,
): Promise<import("../types/futures").FuturesAccountSummary> {
  return requestJson<import("../types/futures").FuturesAccountSummary>(
    "/api/v1/futures/summary",
    {
      method: "GET",
      signal,
    },
  );
}

export async function fetchFuturesPositions(
  status: "open" | "all" = "open",
  signal?: AbortSignal,
): Promise<import("../types/futures").FuturesPosition[]> {
  return requestJson<import("../types/futures").FuturesPosition[]>(
    `/api/v1/futures/positions?status=${status}`,
    {
      method: "GET",
      signal,
    },
  );
}

export async function placeFuturesOrder(
  order: import("../types/futures").FuturesOrderRequest,
): Promise<import("../types/futures").FuturesOrderResult> {
  return requestJson<import("../types/futures").FuturesOrderResult>(
    "/api/v1/futures/orders",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(order),
    },
  );
}

export async function closeFuturesPosition(
  positionId: string,
): Promise<import("../types/futures").FuturesPosition> {
  return requestJson<import("../types/futures").FuturesPosition>(
    `/api/v1/futures/positions/${positionId}/close`,
    {
      method: "POST",
    },
  );
}

export async function fetchFuturesFundingRates(
  symbols?: string,
  signal?: AbortSignal,
): Promise<Record<string, import("../types/futures").FundingRateInfo>> {
  const query = symbols ? `?symbols=${encodeURIComponent(symbols)}` : "";
  return requestJson<Record<string, import("../types/futures").FundingRateInfo>>(
    `/api/v1/futures/funding-rates${query}`,
    {
      method: "GET",
      signal,
    },
  );
}

export async function toggleFuturesAutoTrade(
  enabled: boolean,
): Promise<{ status: string; auto_trade_enabled: boolean }> {
  return requestJson<{ status: string; auto_trade_enabled: boolean }>(
    "/api/v1/futures/toggle-auto-trade",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    },
  );
}
