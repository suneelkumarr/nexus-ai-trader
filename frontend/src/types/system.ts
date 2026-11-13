export type NavTab =
  | "Overview"
  | "Futures Trading"
  | "Scanner & Radar"
  | "Strategies"
  | "Trades"
  | "Backtesting"
  | "Risk"
  | "Settings";

export type WebSocketStatus = "connecting" | "live" | "reconnecting" | "offline";

export interface ComponentCheck {
  status: "up" | "down";
  detail: string | null;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  service: string;
  version: string;
  environment: string;
  trading_mode: string;
  market_type: string;
  live_trading_enabled: boolean;
  allow_leverage: boolean;
  allow_futures: boolean;
  allow_withdrawals: boolean;
  base_currency: string;
  initial_capital_inr: number;
  allowed_symbols: string[];
  checks: Record<string, ComponentCheck>;
  timestamp: string;
}

export interface TickerQuote {
  symbol: string;
  exchange_id: string;
  bid: number | string;
  ask: number | string;
  last: number | string;
  timestamp: string;
}

export interface OpenPaperPosition {
  id: string;
  portfolio_id: string;
  symbol: string;
  asset: string;
  quantity: number | string;
  avg_entry_price_usdt: number | string;
  entry_cost_inr: number | string;
  entry_fee_usdt: number | string;
  initial_stop_price_usdt: number | string;
  trailing_stop_price_usdt: number | string;
  highest_price_usdt: number | string;
  trailing_atr_multiplier: number | string;
  atr_at_entry: number | string;
  status: "open" | "closed";
  opened_at: string;
  closed_at: string | null;
}

export interface TradeLedgerEntry {
  id: string;
  portfolio_id: string;
  position_id: string;
  symbol: string;
  entry_order_id: string;
  exit_order_id: string;
  quantity: number | string;
  entry_price_usdt: number | string;
  exit_price_usdt: number | string;
  entry_cost_inr: number | string;
  exit_proceeds_inr: number | string;
  total_fees_inr: number | string;
  realized_pnl_inr: number | string;
  realized_pnl_pct: number | string;
  exit_reason: string;
  opened_at: string;
  closed_at: string;
}

export interface StrategySignal {
  symbol: string;
  timestamp: string;
  direction: "long" | "exit_long" | "flat";
  entry_price: number | string;
  stop_price: number | string;
  strategy_name: string;
  reason: string;
  indicators: Record<string, number>;
}

export interface EngineHealthSummary {
  overall_status: "ok" | "degraded";
  database_up: boolean;
  database_detail: string | null;
  market_feed_up: boolean;
  market_feed_detail: string | null;
}

export interface TerminalPortfolioSummary {
  portfolio_id: string;
  initial_capital_inr: number;
  cash_balance_inr: number;
  holdings_value_inr: number;
  total_equity_inr: number;
  realized_pnl_inr: number;
  unrealized_pnl_inr: number;
  inr_per_usdt: number | null;
  quote_status: "live" | "unavailable";
}

export interface TerminalRiskSummary {
  drawdown_pct: number;
  daily_loss_pct: number;
  max_drawdown_pct: number;
  daily_loss_limit_pct: number;
  open_positions_count: number;
  max_concurrent_positions: number;
  daily_entries_count: number;
  max_daily_entries: number;
  risk_utilization_pct: number;
  kill_switch_active: boolean;
  kill_switch_reason: string | null;
  kill_switch_triggered_at: string | null;
}

export interface TerminalSnapshotResponse {
  trading_mode: "paper";
  market_type: "spot";
  paper_trading_banner: string;
  live_trading_enabled: boolean;
  engine_health: EngineHealthSummary;
  portfolio: TerminalPortfolioSummary;
  risk: TerminalRiskSummary;
  tickers: TickerQuote[];
  open_positions: OpenPaperPosition[];
  recent_trades: TradeLedgerEntry[];
  latest_signals: StrategySignal[];
  timestamp: string;
}

export interface EmergencyStopResponse {
  trading_mode: "paper";
  kill_switch_active: boolean;
  reason: string;
  triggered_at: string;
  flattened_orders_count: number;
  rejected_flatten_count: number;
}

export interface SignalExplanation {
  strategy_name: string;
  symbol: string;
  direction: "long" | "exit_long" | "flat";
  signal_timestamp: string;
  rationale: string;
  regime_alignment: string;
  advisory_only: true;
}

export interface MarketAnalysisOutput {
  market_regime: string;
  trend_direction: string;
  volatility_level: string;
  risk_observations: string[];
  strategy_assessment: {
    signal_explanations: SignalExplanation[];
    performance_comparison: string;
    unusual_conditions_detected: boolean;
    unusual_conditions: string[];
    advisory_only: true;
    executable_signal: false;
  };
  explanation: string;
  timestamp: string;
}

export interface FeeImpactBreakdown {
  total_fees_inr: number | string;
  total_spread_cost_inr: number | string;
  total_slippage_cost_inr: number | string;
  total_execution_drag_inr: number | string;
  fee_drag_pct_of_initial_capital: number;
  gross_minus_net_inr: number | string;
}

export interface PerformanceMetrics {
  initial_capital_inr: number | string;
  final_equity_inr: number | string;
  gross_profit_inr: number | string;
  gross_return_pct: number;
  total_return_pct: number;
  net_profit_inr: number | string;
  win_rate_pct: number;
  profit_factor: number | null;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  avg_holding_time_seconds: number;
  avg_holding_time_hours: number;
  number_of_trades: number;
  fee_impact: FeeImpactBreakdown;
}

export interface BacktestRunResult {
  split: {
    split_name: string;
    start_timestamp: string;
    end_timestamp: string;
    warmup_bars_count: number;
    scored_bars_count: number;
  };
  symbol: string;
  timeframe: string;
  metrics: PerformanceMetrics;
  benchmark: {
    benchmark_name: string;
    benchmark_metrics: PerformanceMetrics;
    excess_net_return_pct: number;
    excess_net_profit_inr: number | string;
    drawdown_difference_pct: number;
    sharpe_difference: number;
  };
  equity_curve: Array<{
    timestamp: string;
    equity_inr: number | string;
    benchmark_equity_inr: number | string;
  }>;
  rejected_signals_count: number;
}

export interface BacktestSuiteReport {
  report_id: string;
  generated_at: string;
  symbol: string;
  timeframe: string;
  optimized_on_splits: string[];
  out_of_sample_verified: boolean;
  train_result: BacktestRunResult;
  validation_result: BacktestRunResult;
  test_result: BacktestRunResult;
}

export interface SanitizedSettingsResponse {
  trading_mode: string;
  market_type: string;
  live_trading_enabled: boolean;
  allow_leverage: boolean;
  allow_futures: boolean;
  allow_withdrawals: boolean;
  initial_capital_inr: number;
  base_currency: string;
  allowed_symbols: string[];
  supported_timeframes: string[];
  default_timeframe: string;
  exchange_id: string;
  paper_fee_bps: number;
  paper_slippage_bps: number;
  risk: Record<string, unknown>;
  strategy_v1: Record<string, unknown>;
  ai_provider: string;
  ai_model: string;
  ai_enabled: boolean;
}

export interface CandlesStatusResponse {
  symbol: string;
  timeframe: string;
  stored_count: number;
  can_backtest: boolean;
  min_required: number;
  earliest_candle_utc: string | null;
  latest_candle_utc: string | null;
  recommended_lookback: number;
}

export interface SyncCandlesResponse {
  status: string;
  symbol: string;
  timeframe: string;
  fetched_count: number;
  stored_count: number;
  total_in_db: number;
  message: string;
}

export interface AlphaPick {
  symbol: string;
  thesis: string;
  conviction: "HIGH" | "MEDIUM" | string;
}

export interface AIResearchBriefing {
  macro_regime: string;
  sentiment_index: number;
  sentiment_label: string;
  top_momentum_sector: string;
  executive_briefing: string;
  risk_advisory: string;
  top_alpha_picks: AlphaPick[];
  updated_at: string;
}

export interface AutonomousEngineStatus {
  is_running: boolean;
  cycle_count: number;
  last_cycle_at: string | null;
  last_cycle_duration_ms: number;
  arbitrage_trades_count: number;
  strategy_trades_count: number;
  open_positions_count: number;
  kill_switch_active: boolean;
  kill_switch_reason: string | null;
  cash_balance_inr: number;
  initial_capital_inr: number;
  last_error: string | null;
  latest_ai_research: AIResearchBriefing;
}

export interface CandleBarDto {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CandleSeriesResponse {
  symbol: string;
  timeframe: string;
  count: number;
  candles: CandleBarDto[];
}

