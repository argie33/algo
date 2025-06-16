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
