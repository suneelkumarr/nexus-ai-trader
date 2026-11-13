export type FuturesSide = "LONG" | "SHORT";

export type FuturesOrderAction =
  | "OPEN_LONG"
  | "CLOSE_LONG"
  | "OPEN_SHORT"
  | "CLOSE_SHORT";

export type FuturesOrderStatus = "pending" | "filled" | "rejected" | "cancelled";

export type FuturesPositionStatus = "open" | "closed" | "liquidated";

export interface FuturesPosition {
  id: string;
  portfolio_id: string;
  symbol: string;
  side: FuturesSide;
  leverage: number;
  margin_mode: "ISOLATED";
  quantity: number | string;
  entry_price: number | string;
  mark_price: number | string;
  liquidation_price: number | string;
  stop_loss_price: number | string | null;
  take_profit_price: number | string | null;
  initial_margin_inr: number | string;
  entry_fee_inr: number | string;
  unrealized_pnl_usd: number | string;
  unrealized_pnl_inr: number | string;
  roe_pct: number | string;
  status: FuturesPositionStatus;
  close_price: number | string | null;
  close_reason: string | null;
  realized_pnl_inr: number | string;
  opened_at: string;
  closed_at: string | null;
}

export interface FuturesOrderRequest {
  symbol: string;
  action: FuturesOrderAction;
  quantity: number | string;
  leverage: number;
  limit_price?: number | string | null;
  stop_loss_price?: number | string | null;
  take_profit_price?: number | string | null;
  client_order_id?: string | null;
}

export interface FuturesOrderResult {
  order_id: string;
  portfolio_id: string;
  symbol: string;
  action: FuturesOrderAction;
  status: FuturesOrderStatus;
  quantity: number | string;
  executed_price?: number | string | null;
  fee_inr: number | string;
  position_id?: string | null;
  rejection_reason?: string | null;
  created_at: string;
}

export interface FundingRateInfo {
  symbol: string;
  funding_rate: string;
  funding_rate_pct: number;
  mark_price: number;
  index_price: number;
  next_funding_time: string;
}

export interface FuturesAccountSummary {
  total_margin_inr: number;
  available_cash_inr: number;
  unrealized_pnl_inr: number;
  realized_pnl_inr: number;
  open_positions_count: number;
  closed_positions_count: number;
  liquidated_count: number;
  total_trades_count: number;
  win_rate_pct: number;
  auto_trade_enabled: boolean;
}

