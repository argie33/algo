/**
 * API Type Definitions
 *
 * Provides TypeScript types for all API endpoints
 * Ensures type safety throughout the application
 */

/**
 * Base API Response structure
 * All endpoints follow this pattern
 */
export interface BaseAPIResponse<T = any> {
  success: boolean;
  data?: T;
  timestamp: string;
  error?: string | null;
}

/**
 * SECTORS ENDPOINTS
 */
export interface Sector {
  sector_name: string;
  current_rank: number;
  rank_1w_ago: number;
  rank_4w_ago: number;
  rank_12w_ago: number;
  current_momentum: number;
  performance_1d: number | null;
  performance_5d: number | null;
  performance_20d: number | null;
  last_updated: string;
}

export interface Industry {
  industry_name: string;
  current_rank: number;
  rank_1w_ago?: number;
  rank_4w_ago?: number;
  rank_12w_ago?: number;
  momentum_score?: number;
  performance_1d?: number | null;
  last_updated?: string;
}

export interface SectorsWithHistoryResponse extends BaseAPIResponse {
  data?: {
    sectors: Sector[];
    industries?: Industry[];
  };
}

/**
 * SIGNALS ENDPOINTS
 */
export interface TradingSignal {
  symbol: string;
  signal_type: 'Buy' | 'Sell' | 'Hold';
  signal: string;
  date: string;
  signal_date: string;
  timeframe: 'Daily' | 'Weekly' | 'Monthly';
  current_price: number;
  buy_level?: number;
  stop_level?: number;
  target_price?: number | null;
  in_position: boolean;
  risk_reward_ratio: number;
  market_stage: string;
  stage_confidence: number;
  sector: string;
  [key: string]: any; // For additional technical indicators
}

export interface SignalsSummary {
  total_signals: number;
  buy_signals: number;
  sell_signals: number;
  hold_signals: number;
}

export interface Pagination {
  page: number;
  limit: number;
  hasMore?: boolean;
  hasPrev?: boolean;
  total?: number;
}

export interface SignalsResponse extends BaseAPIResponse {
  signals: TradingSignal[];
  summary: SignalsSummary;
  pagination: Pagination;
}

/**
 * SCORES ENDPOINTS
 */
export interface StockScore {
  symbol: string;
  company_name: string;
  composite_score: number;
  momentum_score: number;
  value_score: number;
  quality_score: number;
  growth_score: number;
  positioning_score: number;
  sentiment_score: number | null;
  stability_score: number;
  current_price: number;
  price_change_1d: number;
  [key: string]: any; // For additional metrics
}

export interface ScoresResponse extends BaseAPIResponse {
  data: StockScore[];
}

/**
 * PORTFOLIO ENDPOINTS
 */
export interface PortfolioMetrics {
  beta: number;
  sharpeRatio: number;
  volatility: number;
  expectedReturn: number;
  diversificationScore: number;
  concentrationRatio: number;
}

export interface EfficientFrontierPoint {
  riskProfile: string | number;
  risk: number;
  return: number;
  sharpeRatio: number;
  allocation: Array<{
    symbol: string;
    weight: number;
    riskProfile: string | number;
  }>;
}

export interface PortfolioRecommendation {
  id: number;
  action: 'BUY' | 'SELL' | 'HOLD' | 'CONSOLIDATE' | 'REDUCE';
  symbol: string;
  reason: string;
  targetWeight: string;
  priority: 'high' | 'medium' | 'low';
  impact: string;
  [key: string]: any;
}

export interface PortfolioOptimizationResponse extends BaseAPIResponse {
  analysis: {
    portfolioMetrics: {
      current: PortfolioMetrics;
      optimized: PortfolioMetrics | null;
      improvements: any | null;
      note?: string;
    };
  };
  efficientFrontier: EfficientFrontierPoint[];
  targetAllocation: Array<{
    symbol: string;
    currentWeight: string;
    targetWeight: string;
    action: string;
    rationale: string;
  }>;
  recommendations: PortfolioRecommendation[];
}

/**
 * MARKET ENDPOINTS
 */
export interface MarketSentiment {
  date: string;
  sentiment_score: number;
  bullish_percent: number;
  bearish_percent: number;
  neutral_percent: number;
}

export interface MarketSentimentResponse extends BaseAPIResponse {
  sentiment: MarketSentiment[];
  latest?: MarketSentiment;
  average?: number;
}

/**
 * PRICE/TECHNICAL ENDPOINTS
 */
export interface PriceData {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  [key: string]: any;
}

export interface TechnicalData {
  date: string;
  rsi: number;
  macd: number;
  sma_20?: number;
  sma_50?: number;
  sma_200?: number;
  [key: string]: any;
}

export interface PriceResponse extends BaseAPIResponse {
  data: PriceData[];
  meta?: {
    symbol: string;
    dataPoints?: number;
    lastUpdated?: string;
  };
}

/**
 * ERROR RESPONSE
 */
export interface ErrorResponse {
  success: false;
  error: string;
  timestamp: string;
  statusCode?: number;
  details?: {
    type?: string;
    troubleshooting?: {
      suggestion?: string;
      steps?: string[];
    };
  };
}

/**
 * Generic Paginated Response
 */
export interface PaginatedResponse<T> extends BaseAPIResponse {
  items: T[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    totalPages: number;
    hasNext: boolean;
    hasPrev: boolean;
  };
}

/**
 * Health Check Response
 */
export interface HealthCheckResponse extends BaseAPIResponse {
  status: string;
  healthy: boolean;
  database?: {
    status: string;
    tables?: Record<string, number | string>;
  };
  api?: {
    version: string;
    environment: string;
  };
  memory?: {
    rss: number;
    heapTotal: number;
    heapUsed: number;
  };
  uptime?: number;
}

/**
 * Type guards for runtime validation
 */
export const isSector = (obj: any): obj is Sector => {
  return (
    obj &&
    typeof obj === 'object' &&
    'sector_name' in obj &&
    'current_rank' in obj
  );
};

export const isSignal = (obj: any): obj is TradingSignal => {
  return (
    obj &&
    typeof obj === 'object' &&
    'symbol' in obj &&
    'signal_type' in obj &&
    'current_price' in obj
  );
};

export const isStockScore = (obj: any): obj is StockScore => {
  return (
    obj &&
    typeof obj === 'object' &&
    'symbol' in obj &&
    'composite_score' in obj
  );
};

export const isErrorResponse = (obj: any): obj is ErrorResponse => {
  return (
    obj &&
    typeof obj === 'object' &&
    obj.success === false &&
    'error' in obj
  );
};

/**
 * API Response Type Union
 * Use this for functions that handle multiple response types
 */
export type APIResponse =
  | SectorsWithHistoryResponse
  | SignalsResponse
  | ScoresResponse
  | PortfolioOptimizationResponse
  | MarketSentimentResponse
  | PriceResponse
  | ErrorResponse;
