export type MarketSector =
  | "LAYER_1"
  | "DEFI"
  | "AI_COMPUTE"
  | "MEMES"
  | "GAMING_METAVERSE"
  | "INFRASTRUCTURE";

export interface MarketTickerItem {
  symbol: string;
  bid: number;
  ask: number;
  last: number;
  spread_bps: number;
  change_24h_pct: number;
  quote_volume_24h: number;
  sector: MarketSector;
  timestamp: string;
  is_stale: boolean;
}

export interface ArbitrageLeg {
  step: number;
  symbol: string;
  side: "BUY" | "SELL";
  from_asset: string;
  to_asset: string;
  rate: number;
  fee_bps: number;
  slippage_bps: number;
}

export interface TriangularOpportunity {
  id: string;
  path: string;
  legs: ArbitrageLeg[];
  gross_edge_bps: number;
  total_fee_bps: number;
  estimated_slippage_bps: number;
  net_edge_bps: number;
  expected_profit_usdt: number;
  status: "ACTIVE" | "EXPIRED" | "FILTERED";
  filter_reason: string | null;
  execution_window_ms: number;
  detected_at: string;
  quality_score: number;
}

export interface SyntheticDislocation {
  base_asset: string;
  quote_asset: string;
  direct_symbol: string;
  direct_price: number;
  synthetic_price: number;
  dislocation_bps: number;
  z_score: number;
  direction: "BUY_DIRECT_SELL_SYNTH" | "BUY_SYNTH_SELL_DIRECT" | "NEUTRAL";
  detected_at: string;
}

export interface ScannerTelemetry {
  load_90s: number[];
  cypher_queries_per_sec: number;
  hacks_blocked_per_sec: number;
  yaw_deg: number;
  pitch_deg: number;
  graph_r_min: number;
  graph_r_max: number;
  nodes_count: number;
  edges_count: number;
  sota_gain_pct: number;
  fps: number;
  system_buffer_verified_pct: number;
  scanner_compute_split_pct: number;
  ai_compute_split_pct: number;
  active_pods_count: number;
  total_pods_count: number;
}

export interface MultiMarketScanResponse {
  timestamp: string;
  total_markets: number;
  active_markets: number;
  avg_spread_bps: number;
  top_gainers: MarketTickerItem[];
  top_spreads: MarketTickerItem[];
  markets: MarketTickerItem[];
  triangular_opportunities: TriangularOpportunity[];
  synthetic_dislocations: SyntheticDislocation[];
  telemetry: ScannerTelemetry;
}

export interface ExecutePaperArbResponse {
  status: string;
  opportunity_id: string;
  simulated_net_profit_usdt: number;
  simulated_net_profit_inr: number;
  new_virtual_balance_inr: number;
  executed_at: string;
  message: string;
}
