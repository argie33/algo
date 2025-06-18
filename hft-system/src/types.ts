// Core Types for HFT System

// Market data types
export interface MarketTick {
  symbol: string;
  timestamp: number;
  price?: number;
  size?: number;
  bid?: number;
  ask?: number;
  bidSize?: number;
  askSize?: number;
  exchange?: string;
  conditions?: string[];
  type: 'trade' | 'quote';
}

export interface QuoteData {
  bid: number;
  ask: number;
  bidSize: number;
  askSize: number;
  timestamp: number;
  spread: number;
}

export interface TradeData {
  price: number;
  size: number;
  timestamp: number;
  exchange: string;
}

export interface OHLCVBar {
  symbol: string;
  timestamp: number;
  timeframe: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  vwap?: number;
}

// Order types
export type OrderSide = 'buy' | 'sell';
export type OrderType = 'market' | 'limit' | 'stop' | 'stop_limit';
export type OrderStatus = 'pending' | 'filled' | 'partially_filled' | 'cancelled' | 'rejected';

export interface OrderRequest {
  symbol: string;
  side: OrderSide;
  type: OrderType;
  quantity: number;
  price?: number;
  stopPrice?: number;
  timeInForce?: 'day' | 'gtc' | 'ioc' | 'fok';
  clientOrderId?: string;
}

// Market data configuration
export interface MarketDataConfig {
  symbols: string[];
  isPaper: boolean;
  reconnectAttempts: number;
  heartbeatInterval: number;
  bufferSizes: {
    ticks: number;
    bars: number;
  };
}

// Event handler types
export type TickHandler = (tick: MarketTick) => void;
export type BarHandler = (bar: OHLCVBar) => void;

// Error types
export class MarketDataError extends Error {
  constructor(message: string, public metadata?: any) {
    super(message);
    this.name = 'MarketDataError';
  }
}

export class OrderError extends Error {
  constructor(message: string, public metadata?: any) {
    super(message);
    this.name = 'OrderError';
  }
}

export class RiskError extends Error {
  constructor(message: string, public metadata?: any) {
    super(message);
    this.name = 'RiskError';
  }
}

// Core Types for HFT System
export interface MarketData {
  symbol: string;
  price: number;
  volume: number;
  timestamp: number;
  bid: number;
  ask: number;
  bidSize: number;
  askSize: number;
}

export interface Order {
  id: string;
  symbol: string;
  side: 'buy' | 'sell';
  quantity: number;
  price?: number;
  type: 'market' | 'limit';
  status: 'pending' | 'filled' | 'cancelled';
  timestamp: number;
  filled?: number;
  avgPrice?: number;
}

export interface Position {
  symbol: string;
  quantity: number;
  avgPrice: number;
  marketValue: number;
  unrealizedPnL: number;
  realizedPnL: number;
}

export interface Signal {
  symbol: string;
  action: 'buy' | 'sell' | 'hold';
  strength: number; // 0-1
  price?: number;
  timestamp: number;
  source: string;
  metadata?: Record<string, any>;
}

export interface RiskMetrics {
  totalExposure: number;
  maxDrawdown: number;
  sharpeRatio: number;
  portfolioValue: number;
  leverage: number;
  var95: number;
  timestamp: number;
}

export interface Config {
  alpaca: {
    keyId: string;
    secretKey: string;
    baseUrl: string;
    dataUrl: string;
    paper: boolean;
  };
  database: {
    host: string;
    port: number;
    database: string;
    username: string;
    password: string;
  };
  redis: {
    host: string;
    port: number;
    password?: string;
  };
  trading: {
    symbols: string[];
    maxPositionSize: number;
    maxPortfolioValue: number;
    riskLimits: {
      maxDrawdown: number;
      maxLeverage: number;
    };
  };
  strategies: {
    momentum: {
      enabled: boolean;
      lookback: number;
      threshold: number;
    };
    meanReversion: {
      enabled: boolean;
      lookback: number;
      threshold: number;
    };
  };
}

export interface StrategyResult {
  symbol: string;
  signal: Signal;
  confidence: number;
  expectedReturn: number;
  risk: number;
}
