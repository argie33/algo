import { EventEmitter } from 'events';

// Enums
export enum OrderSide {
  BUY = 'buy',
  SELL = 'sell'
}

export enum OrderType {
  MARKET = 'market',
  LIMIT = 'limit',
  STOP = 'stop',
  STOP_LIMIT = 'stop_limit'
}

export enum OrderStatus {
  PENDING = 'pending',
  NEW = 'new',
  PARTIALLY_FILLED = 'partially_filled',
  FILLED = 'filled',
  CANCELED = 'canceled',
  REJECTED = 'rejected',
  EXPIRED = 'expired'
}

export enum TimeInForce {
  DAY = 'day',
  GTC = 'gtc',
  IOC = 'ioc',
  FOK = 'fok'
}

export enum SignalType {
  BUY = 'buy',
  SELL = 'sell',
  HOLD = 'hold'
}

export enum SignalSource {
  TECHNICAL = 'technical',
  FUNDAMENTAL = 'fundamental',
  SENTIMENT = 'sentiment',
  NEWS = 'news',
  ARBITRAGE = 'arbitrage'
}

export enum RiskLevel {
  LOW = 'low',
  MEDIUM = 'medium',
  HIGH = 'high',
  CRITICAL = 'critical'
}

// Core data types
export interface Timestamp {
  timestamp: number; // Unix timestamp in milliseconds
  exchange_timestamp?: number;
  received_timestamp?: number;
}

export interface Symbol {
  symbol: string;
  exchange: string;
  asset_class: string;
}

// Market Data Types
export interface MarketTick extends Timestamp {
  symbol: string;
  exchange: string;
  price: number;
  size: number;
  conditions?: string[];
}

export interface Quote extends Timestamp {
  symbol: string;
  exchange: string;
  bid_price: number;
  bid_size: number;
  ask_price: number;
  ask_size: number;
  bid_exchange?: string;
  ask_exchange?: string;
}

export interface Trade extends Timestamp {
  symbol: string;
  exchange: string;
  price: number;
  size: number;
  conditions?: string[];
  tape?: string;
}

export interface Bar extends Timestamp {
  symbol: string;
  exchange: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  trade_count?: number;
  vwap?: number;
}

// Signal Types
export interface Signal extends Timestamp {
  id: string;
  symbol: string;
  type: SignalType;
  source: SignalSource;
  strength: number; // 0-1 confidence level
  target_price?: number;
  stop_loss?: number;
  take_profit?: number;
  expected_holding_period?: number; // minutes
  metadata: Record<string, any>;
}

// Order Types
export interface Order extends Timestamp {
  id: string;
  client_order_id: string;
  symbol: string;
  side: OrderSide;
  type: OrderType;
  time_in_force: TimeInForce;
  quantity: number;
  filled_quantity: number;
  remaining_quantity: number;
  price?: number;
  stop_price?: number;
  limit_price?: number;
  average_fill_price?: number;
  status: OrderStatus;
  submitted_at?: number;
  filled_at?: number;
  canceled_at?: number;
  rejected_reason?: string;
  fees?: number;
  pnl?: number; // Add PnL tracking
  createdAt?: number;
  filledAt?: number;
}

export interface OrderFill extends Timestamp {
  id: string;
  order_id: string;
  symbol: string;
  side: OrderSide;
  quantity: number;
  price: number;
  commission: number;
  exchange: string;
}

// Position Types
export interface Position {
  symbol: string;
  quantity: number;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  realized_pnl: number;
  average_entry_price: number;
  averagePrice: number; // Add alias for consistency
  last_price: number;
  updated_at: number;
}

export interface Portfolio {
  cash: number;
  portfolio_value: number;
  positions: Map<string, Position>;
  day_trade_count: number;
  pattern_day_trader: boolean;
  trading_blocked: boolean;
  account_blocked: boolean;
  transfers_blocked: boolean;
  equity: number;
  last_equity: number;
  multiplier: number;
  buying_power: number;
  initial_margin: number;
  maintenance_margin: number;
  sma: number;
  daytrade_buying_power: number;
  regt_buying_power: number;
  updated_at: number;
}

// Risk Types
export interface RiskCheck {
  approved: boolean;
  risk_level: RiskLevel;
  violations: string[];
  warnings: string[];
  max_position_size?: number;
  max_order_size?: number;
  metadata?: Record<string, any>;
}

export interface RiskMetrics {
  totalExposure: number;
  netExposure: number;
  grossLeverage: number;
  netLeverage: number;
  largestPosition: number;
  numberOfPositions: number;
  concentrationRisk: number;
  var95: number;
  var99: number;
  expectedShortfall: number;
  timestamp: number;
  portfolio_value: number;
  total_exposure: number;
  net_exposure: number;
  gross_exposure: number;
  leverage: number;
  var_1d: number;
  var_5d: number;
  max_drawdown: number;
  sharpe_ratio: number;
  beta: number;
  concentration_risk: number;
  updated_at: number;
}

// Analytics Types
export interface PerformanceMetrics {
  totalPnL: number;
  realizedPnL: number;
  unrealizedPnL: number;
  totalTrades: number;
  winningTrades: number;
  losingTrades: number;
  winRate: number;
  avgWin: number;
  avgLoss: number;
  profitFactor: number;
  sharpeRatio: number;
  maxDrawdown: number;
  maxDrawdownPercent: number;
  calmarRatio: number;
  volatility: number;
  startTime: number;
  lastUpdate: number;
  total_return: number;
  daily_return: number;
  updated_at: number;
}

export interface LatencyMetrics {
  market_data_latency: number;
  signal_generation_latency: number;
  order_processing_latency: number;
  end_to_end_latency: number;
  timestamp: number;
}

// Additional Analytics Types
export interface PnLData extends Timestamp {
  symbol?: string;
  totalPnL: number;
  realizedPnL: number;
  unrealizedPnL: number;
  dailyPnL: number;
  fees: number;
}

export interface TradeStats {
  totalTrades: number;
  totalVolume: number;
  avgTradeSize: number;
  totalPnL: number;
  avgHoldTime: number;
  successRate: number;
}

// Fundamental Data Types (from existing infrastructure)
export interface EarningsData {
  symbol: string;
  fiscal_date_ending: string;
  reported_date: string;
  reported_eps: number;
  estimated_eps: number;
  surprise: number;
  surprise_percentage: number;
}

export interface FinancialStatement {
  symbol: string;
  fiscal_date_ending: string;
  reported_currency: string;
  total_revenue: number;
  cost_of_revenue: number;
  gross_profit: number;
  operating_income: number;
  net_income: number;
  total_assets: number;
  total_liabilities: number;
  shareholders_equity: number;
  operating_cash_flow: number;
  capital_expenditures: number;
  free_cash_flow: number;
}

export interface TechnicalIndicators {
  symbol: string;
  date: string;
  sma_20: number;
  sma_50: number;
  sma_200: number;
  ema_12: number;
  ema_26: number;
  rsi_14: number;
  macd: number;
  macd_signal: number;
  macd_histogram: number;
  bb_upper: number;
  bb_middle: number;
  bb_lower: number;
  volume: number;
  price: number;
}

// Event Types
export interface SystemEvent {
  id: string;
  type: string;
  timestamp: number;
  severity: 'info' | 'warning' | 'error' | 'critical';
  message: string;
  data?: Record<string, any>;
}

export interface AlertEvent extends SystemEvent {
  alert_type: string;
  threshold_value?: number;
  current_value?: number;
  symbol?: string;
}

// Base classes
export abstract class BaseEngine extends EventEmitter {
  protected name: string;
  protected logger: any;
  protected config: any;
  protected isRunning: boolean = false;
  protected metrics: Map<string, number> = new Map();

  constructor(name: string, config: any, logger: any) {
    super();
    this.name = name;
    this.config = config;
    this.logger = logger;
  }

  abstract initialize(): Promise<void>;
  abstract start(): Promise<void>;
  abstract stop(): Promise<void>;

  getName(): string {
    return this.name;
  }

  isEngineRunning(): boolean {
    return this.isRunning;
  }

  getMetrics(): Record<string, number> {
    return Object.fromEntries(this.metrics);
  }

  protected updateMetric(key: string, value: number): void {
    this.metrics.set(key, value);
  }

  protected incrementMetric(key: string, delta: number = 1): void {
    const current = this.metrics.get(key) || 0;
    this.metrics.set(key, current + delta);
  }
}

export abstract class BaseService extends EventEmitter {
  protected name: string;
  protected logger: any;
  protected config: any;
  protected isRunning: boolean = false;

  constructor(name: string, config: any, logger: any) {
    super();
    this.name = name;
    this.config = config;
    this.logger = logger;
  }

  abstract initialize(): Promise<void>;
  abstract start(): Promise<void>;
  abstract stop(): Promise<void>;

  getName(): string {
    return this.name;
  }

  isServiceRunning(): boolean {
    return this.isRunning;
  }
}

// Utility Types
export type DeepPartial<T> = {
  [P in keyof T]?: T[P] extends object ? DeepPartial<T[P]> : T[P];
};

export interface DatabaseConnection {
  query<T>(sql: string, params?: any[]): Promise<T[]>;
  execute(sql: string, params?: any[]): Promise<void>;
  transaction<T>(callback: (connection: DatabaseConnection) => Promise<T>): Promise<T>;
  close(): Promise<void>;
}

export interface CacheConnection {
  get(key: string): Promise<string | null>;
  set(key: string, value: string, ttl?: number): Promise<void>;
  del(key: string): Promise<void>;
  exists(key: string): Promise<boolean>;
  incr(key: string): Promise<number>;
  expire(key: string, ttl: number): Promise<void>;
}

// Configuration validation
export function validateOrder(order: Partial<Order>): order is Order {
  return !!(
    order.id &&
    order.symbol &&
    order.side &&
    order.type &&
    order.quantity &&
    order.quantity > 0
  );
}

export function validateSignal(signal: Partial<Signal>): signal is Signal {
  return !!(
    signal.id &&
    signal.symbol &&
    signal.type &&
    signal.source &&
    typeof signal.strength === 'number' &&
    signal.strength >= 0 &&
    signal.strength <= 1
  );
}

// Error types
export class HFTError extends Error {
  public readonly code: string;
  public readonly timestamp: number;
  public readonly context?: Record<string, any>;
  constructor(message: string, code: string, context?: Record<string, any>) {
    super(message);
    this.name = 'HFTError';
    this.code = code;
    this.timestamp = Date.now();
    this.context = context || {};
  }
}

export class RiskViolationError extends HFTError {
  constructor(message: string, context?: Record<string, any>) {
    super(message, 'RISK_VIOLATION', context);
    this.name = 'RiskViolationError';
  }
}

export class OrderRejectionError extends HFTError {
  constructor(message: string, context?: Record<string, any>) {
    super(message, 'ORDER_REJECTION', context);
    this.name = 'OrderRejectionError';
  }
}

export class MarketDataError extends HFTError {
  constructor(message: string, context?: Record<string, any>) {
    super(message, 'MARKET_DATA_ERROR', context);
    this.name = 'MarketDataError';
  }
}

// Execution Types
export interface VenueConfig {
  name: string;
  type: 'exchange' | 'dark_pool' | 'ecn';
  enabled: boolean;
  avgLatencyMs: number;
  liquidityScore: number;
  fees: {
    maker: number;
    taker: number;
  };
  limits: {
    maxOrderSize: number;
    maxOrderValue: number;
  };
  connection: {
    url: string;
    auth: Record<string, string>;
  };
}

export interface ExecutionReport {
  orderId: string;
  venue: string;
  quantity: number;
  filledQuantity: number;
  price: number;
  averagePrice: number;
  commission: number;
  timestamp: number;
  status: OrderStatus;
}

export interface ExecutionAlgorithm {
  name: string;
  type: 'TWAP' | 'VWAP' | 'IMPLEMENTATION_SHORTFALL' | 'SMART_ROUTING' | 'DARK_POOL';
  enabled: boolean;
  parameters: Record<string, any>;
}

export interface OrderSlice {
  orderId: string;
  venue: string;
  quantity: number;
  price?: number;
  delayMs: number;
  symbol?: string;
  side?: OrderSide;
  type?: OrderType;
}

export interface ExecutionMetrics {
  totalOrders: number;
  totalVolume: number;
  averageLatency: number;
  fillRate: number;
  implementationShortfall: number;
  venueStats: Record<string, any>;
  algorithmStats: Record<string, any>;
  timestamp: number;
}
