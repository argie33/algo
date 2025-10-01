/**
 * Comprehensive API Mock for Tests
 * This mock includes all API functions and can be imported by any test
 */
import { vi } from "vitest";

// Named export mocks
export const getApiConfig = vi.fn(() => ({
  baseURL: "http://localhost:3001",
  isServerless: false,
  apiUrl: "http://localhost:3001",
  isConfigured: false,
  environment: "test",
  isDevelopment: true,
  isProduction: false,
  baseUrl: "/",
  allEnvVars: {
    VITE_API_URL: "http://localhost:3001",
    MODE: "test",
    DEV: true,
    PROD: false,
    BASE_URL: "/",
  },
}));

// Named exports for functions that are also exported individually
export const getPortfolioData = vi.fn().mockResolvedValue({
  success: true,
  data: {
    holdings: [
      {
        symbol: "AAPL",
        name: "AAPL Corp.",
        quantity: 100,
        avgPrice: 150,
        currentPrice: 191.25,
        marketValue: 19125,
        totalValue: 19125,
        totalCost: 15000,
        unrealizedPnl: 4125,
        gainLoss: 4125,
        unrealizedPnlPercent: 27.5,
        gainLossPercent: 27.5,
        dayChange: 0,
        dayChangePercent: 0,
        weight: 4.68,
        sector: "Technology",
        assetClass: "equity",
        broker: "manual",
        volume: 0,
        lastUpdated: "2025-09-04T20:31:40.570Z"
      }
    ],
    summary: {
      totalValue: 1250000,
      totalCost: 850000,
      totalPnl: 400000,
      totalPnlPercent: 47.1,
      dayPnl: 15000,
      dayPnlPercent: 1.2,
      positions: 5
    },
    performance: {
      totalReturn: 400000,
      totalReturnPercent: 47.1,
    },
  },
});

export const getApiKeys = vi.fn().mockResolvedValue({ success: true, data: {} });
export const testApiConnection = vi.fn().mockResolvedValue({ success: true });
export const importPortfolioFromBroker = vi.fn().mockResolvedValue({ success: true });
export const healthCheck = vi.fn().mockResolvedValue({ success: true });

// Service Health functions
export const getDiagnosticInfo = vi.fn().mockResolvedValue({
  success: true,
  data: {
    system: {
      uptime: 3600,
      memory: { used: 256, total: 1024 },
      cpu: { usage: 25 },
      disk: { used: 50, total: 100 }
    },
    services: {
      database: { status: 'healthy', response_time: 15 },
      cache: { status: 'healthy', response_time: 5 },
      external_api: { status: 'healthy', response_time: 100 }
    },
    version: '1.0.0',
    environment: 'test'
  }
});
export const getCurrentBaseURL = vi.fn(() => 'http://localhost:3001');
export const getCurrentUser = vi.fn().mockResolvedValue({
  success: true,
  data: { id: 1, name: 'Test User', email: 'test@example.com' }
});

export const getStockPrices = vi.fn().mockResolvedValue({
  success: true,
  data: [
    { date: "2024-01-01", close: 170.25, volume: 45000000, high: 172.0, low: 169.5, open: 170.0 },
    { date: "2024-01-02", close: 172.50, volume: 42000000, high: 173.2, low: 171.8, open: 171.5 },
    { date: "2024-01-03", close: 175.25, volume: 45678900, high: 175.8, low: 172.9, open: 173.0 }
  ]
});

export const getStockMetrics = vi.fn().mockResolvedValue({
  success: true,
  data: {
    metrics: {
      pe_ratio: 28.5,
      market_cap: 2800000000000,
      dividend_yield: 0.0052,
      book_value: 15.67,
      beta: 1.2,
      eps: 6.15
    }
  }
});

export const getPortfolioAnalytics = vi.fn().mockResolvedValue({
  success: true,
  data: {
    total_value: 1250000,
    totalCost: 85000,
    totalPnl: 15000,
    totalPnlPercent: 17.5,
    performance: {
      totalReturn: 15000,
      totalReturnPercent: 17.5,
    }
  }
});

export const getTradingSignalsDaily = vi.fn().mockResolvedValue({
  success: true,
  data: [
    {
      symbol: "AAPL",
      date: "2025-08-26T05:00:00.000Z",
      signal: "BUY",
      price: "169.36",
      stoplevel: null,
      inposition: false,
      current_price: null,
      company_name: "Apple Inc.",
      sector: "Technology",
      market_cap: "175430000000",
      trailing_pe: null,
      dividend_yield: null,
      performance_percent: "0"
    },
    {
      symbol: "TSLA",
      date: "2025-08-26T05:00:00.000Z",
      signal: "SELL",
      price: "188.85",
      stoplevel: null,
      inposition: false,
      current_price: null,
      company_name: "Tesla Inc.",
      sector: "Consumer Cyclical",
      market_cap: "800000000000",
      trailing_pe: null,
      dividend_yield: null,
      performance_percent: "0"
    }
  ],
  timeframe: "daily",
  count: 2,
  pagination: {
    page: 1,
    limit: 10,
    total: 15,
    totalPages: 2,
    hasNext: true,
    hasPrev: false
  },
  metadata: {
    signal_type: "all",
    symbol: null
  }
});

// Financial Data functions
export const getKeyMetrics = vi.fn().mockResolvedValue({
  success: true,
  data: [
    {
      symbol: 'AAPL',
      pe_ratio: 28.5,
      dividend_yield: 0.0052,
      book_value: 15.67,
      roe: 0.175,
      roa: 0.283,
      revenue_growth: 0.078,
      eps_growth: 0.092
    }
  ]
});

// Market Commentary functions
export const getMarketTrends = vi.fn().mockResolvedValue({
  success: true,
  data: {
    trends: [
      { period: 'week', direction: 'up', strength: 'moderate', description: 'Market showing upward momentum' },
      { period: 'month', direction: 'sideways', strength: 'weak', description: 'Consolidation phase' }
    ]
  }
});

export const getAnalystOpinions = vi.fn().mockResolvedValue({
  success: true,
  data: {
    opinions: [
      { analyst: 'Goldman Sachs', rating: 'Buy', target: 185.0, date: '2024-01-15' },
      { analyst: 'Morgan Stanley', rating: 'Hold', target: 175.0, date: '2024-01-14' }
    ]
  }
});

export const subscribeToCommentary = vi.fn().mockResolvedValue({
  success: true,
  data: { subscribed: true, categories: ['market', 'earnings', 'technical'] }
});

// Additional StockDetail API functions
export const getStockProfile = vi.fn().mockResolvedValue({
  success: true,
  data: [
    {
      symbol: "AAPL",
      company_name: "Apple Inc.",
      sector: "Technology",
      industry: "Consumer Electronics",
      description: "Apple Inc. designs, manufactures, and markets smartphones...",
      country: "US",
      website: "https://www.apple.com",
      employees: 154000
    }
  ]
});

export const getAnalystRecommendations = vi.fn().mockResolvedValue({
  success: true,
  data: [
    { analyst: 'Goldman Sachs', rating: 'Buy', target: 185.0, date: '2024-01-15' },
    { analyst: 'Morgan Stanley', rating: 'Hold', target: 175.0, date: '2024-01-14' }
  ]
});

export const getBalanceSheet = vi.fn().mockResolvedValue({
  success: true,
  data: [
    {
      total_assets: 352755000000,
      total_liabilities: 290437000000,
      stockholder_equity: 62318000000,
      cash_and_equivalents: 51355000000,
      total_debt: 123000000000
    }
  ]
});

export const getIncomeStatement = vi.fn().mockResolvedValue({
  success: true,
  data: [
    {
      revenue: 394328000000,
      cost_of_revenue: 223546000000,
      gross_profit: 170782000000,
      operating_expenses: 55013000000,
      operating_income: 115769000000,
      net_income: 99803000000
    }
  ]
});

export const getCashFlowStatement = vi.fn().mockResolvedValue({
  success: true,
  data: [
    {
      operating_cash_flow: 122151000000,
      investing_cash_flow: -10635000000,
      financing_cash_flow: -108488000000,
      free_cash_flow: 84726000000,
      capital_expenditures: -7309000000
    }
  ]
});

export const getAnalystOverview = vi.fn().mockResolvedValue({
  success: true,
  data: {
    consensus_rating: "Buy",
    average_target: 185.50,
    high_target: 200.0,
    low_target: 165.0,
    analyst_count: 25,
    strong_buy: 10,
    buy: 8,
    hold: 5,
    sell: 2,
    strong_sell: 0
  }
});

export const getStockPricesRecent = vi.fn().mockResolvedValue({
  success: true,
  data: [
    { date: "2024-01-01", close: 170.25, volume: 45000000, high: 172.0, low: 169.5, open: 170.0 },
    { date: "2024-01-02", close: 172.50, volume: 42000000, high: 173.2, low: 171.8, open: 171.5 },
    { date: "2024-01-03", close: 175.25, volume: 45678900, high: 175.8, low: 172.9, open: 173.0 }
  ]
});

// Technical Analysis functions
export const getTechnicalData = vi.fn().mockResolvedValue({
  success: true,
  data: {
    indicators: {
      rsi: 45.2,
      macd: { macd: 1.23, signal: 1.15, histogram: 0.08 },
      bollinger: { upper: 178.5, middle: 175.2, lower: 171.9 },
      sma_20: 174.8,
      sma_50: 172.1,
      ema_12: 175.4,
      ema_26: 173.9
    },
    signals: ['bullish_macd', 'neutral_rsi'],
    trend: 'upward',
    strength: 'moderate'
  }
});

// Stock screening and search functions
export const screenStocks = vi.fn().mockImplementation(async (params = {}) => {
  // Simulate parameter validation like real API
  if (params && typeof params !== 'object') {
    throw new Error('Invalid parameters: must be an object');
  }

  // Simulate network delay
  await new Promise(resolve => setTimeout(resolve, Math.random() * 100));

  // Simulate occasional API errors (10% chance)
  if (Math.random() < 0.1) {
    throw new Error('API service temporarily unavailable');
  }

  const page = parseInt(params.page) || 1;
  const limit = parseInt(params.limit) || 25;
  const totalCount = 150; // Simulate large dataset
  const totalPages = Math.ceil(totalCount / limit);

  return {
    success: true,
    data: {
      results: [
        {
          symbol: 'AAPL',
          companyName: 'Apple Inc.',
          price: { current: 175.25, change: 2.35, changePercent: 1.58 },
          marketCap: 2500000000000,
          peRatio: 28.5,
          dividendYield: 0.52,
          sector: 'Technology',
          volume: 45000000,
          score: 8.2,
          change: 2.35,
          changePercent: 1.58
        }
      ],
      totalCount,
      totalPages,
      currentPage: page
    }
  };
});

export const getStockPriceHistory = vi.fn().mockResolvedValue({
  success: true,
  data: [
    { date: "2024-01-01", close: 170.25, volume: 45000000 },
    { date: "2024-01-02", close: 172.50, volume: 42000000 },
    { date: "2024-01-03", close: 175.25, volume: 45678900 }
  ]
});

export const getStocks = vi.fn().mockResolvedValue({
  success: true,
  data: [
    { symbol: 'AAPL', name: 'Apple Inc.', price: 175.25, change: 2.35, changePercent: 1.58 },
    { symbol: 'GOOGL', name: 'Alphabet Inc.', price: 142.56, change: -1.20, changePercent: -0.83 }
  ]
});

export const searchStocks = vi.fn().mockResolvedValue({
  success: true,
  data: [
    { symbol: 'AAPL', name: 'Apple Inc.', exchange: 'NASDAQ' }
  ]
});

export const getTopStocks = vi.fn().mockResolvedValue({
  success: true,
  data: [
    { symbol: 'AAPL', name: 'Apple Inc.', price: 175.25, change: 2.35, changePercent: 1.58 }
  ]
});

export const getMarketOverview = vi.fn().mockResolvedValue({
  success: true,
  data: {
    indices: [
      {
        symbol: "SPY",
        name: "S&P 500",
        price: 450.25,
        change: 5.75,
        changePercent: 1.29,
      },
    ],
    sentiment_indicators: {
      fear_greed: { value: 45, value_text: "Neutral" },
    },
    market_breadth: {
      advancing: 1500,
      declining: 1200,
      total_stocks: 3000,
    },
  },
});

// Create mock functions for all API methods
// Enhanced mock function with error scenarios
const createMockApiFunction = (name) => vi.fn().mockImplementation(async (..._args) => {
  // Add random network delay
  await new Promise(resolve => setTimeout(resolve, Math.random() * 50));

  // Simulate occasional errors (5% chance)
  if (Math.random() < 0.05) {
    throw new Error(`${name} service temporarily unavailable`);
  }

  return {
    success: true,
    data: null
  };
});

// Default export mock
const mockApi = {
  // Core HTTP methods
  get: vi.fn().mockImplementation((url) => {
    // Handle signals API requests
    if (url.includes('/api/signals/')) {
      const symbol = url.split('/api/signals/')[1].split('?')[0];
      return Promise.resolve({
        data: {
          success: true,
          data: [
            {
              symbol: symbol,
              signal: ['BUY', 'SELL', 'HOLD'][Math.floor(Math.random() * 3)],
              confidence: 0.7 + Math.random() * 0.3,
              date: new Date().toISOString().split('T')[0],
              current_price: 100 + Math.random() * 100,
            }
          ]
        }
      });
    }
    // Default response for other requests
    return Promise.resolve({ data: {} });
  }),
  post: vi.fn().mockResolvedValue({ data: {} }),
  put: vi.fn().mockResolvedValue({ data: {} }),
  delete: vi.fn().mockResolvedValue({ data: {} }),

  // Core API
  healthCheck: createMockApiFunction('healthCheck'),
  getMarketOverview: vi.fn().mockResolvedValue({
    success: true,
    data: {
      indices: [
        {
          symbol: "SPY",
          name: "S&P 500",
          price: 450.25,
          change: 5.75,
          changePercent: 1.29,
        },
      ],
      sentiment_indicators: {
        fear_greed: { value: 45, value_text: "Neutral" },
      },
      market_breadth: {
        advancing: 1500,
        declining: 1200,
        total_stocks: 3000,
      },
    },
  }),

  // Portfolio functions
  getPortfolio: createMockApiFunction('getPortfolio'),
  getPortfolioData: vi.fn().mockResolvedValue({
    success: true,
    data: {
      holdings: [
        {
          symbol: "AAPL",
          name: "AAPL Corp.",
          quantity: 100,
          avgPrice: 150,
          currentPrice: 191.25,
          marketValue: 19125,
          totalValue: 19125,
          totalCost: 15000,
          unrealizedPnl: 4125,
          gainLoss: 4125,
          unrealizedPnlPercent: 27.5,
          gainLossPercent: 27.5,
          dayChange: 0,
          dayChangePercent: 0,
          weight: 4.68,
          sector: "Technology",
          assetClass: "equity",
          broker: "manual",
          volume: 0,
          lastUpdated: "2025-09-04T20:31:40.570Z"
        }
      ],
      summary: {
        totalValue: 1250000,
        totalCost: 850000,
        totalPnl: 400000,
        totalPnlPercent: 47.1,
        dayPnl: 15000,
        dayPnlPercent: 1.2,
        positions: 5
      },
      performance: {
        totalReturn: 400000,
        totalReturnPercent: 47.1,
      },
    },
  }),
  getMarketSentimentHistory: createMockApiFunction('getMarketSentimentHistory'),
  getMarketSectorPerformance: createMockApiFunction('getMarketSectorPerformance'),
  getMarketBreadth: createMockApiFunction('getMarketBreadth'),
  getEconomicIndicators: createMockApiFunction('getEconomicIndicators'),
  getMarketCorrelation: createMockApiFunction('getMarketCorrelation'),
  getSeasonalityData: createMockApiFunction('getSeasonalityData'),
  getMarketResearchIndicators: createMockApiFunction('getMarketResearchIndicators'),
  getPortfolioAnalytics: createMockApiFunction('getPortfolioAnalytics'),
  getPortfolioRiskAnalysis: createMockApiFunction('getPortfolioRiskAnalysis'),
  getPortfolioOptimization: createMockApiFunction('getPortfolioOptimization'),
  addHolding: createMockApiFunction('addHolding'),
  updateHolding: createMockApiFunction('updateHolding'),
  deleteHolding: createMockApiFunction('deleteHolding'),

  // Stock and Market functions
  getStock: createMockApiFunction('getStock'),
  getStocks: vi.fn().mockResolvedValue({
    success: true,
    data: [
      { symbol: 'AAPL', name: 'Apple Inc.', price: 175.25, change: 2.35, changePercent: 1.58 },
      { symbol: 'GOOGL', name: 'Alphabet Inc.', price: 142.56, change: -1.20, changePercent: -0.83 }
    ]
  }),
  screenStocks: vi.fn().mockResolvedValue({
    success: true,
    data: {
      results: [
        {
          symbol: 'AAPL',
          companyName: 'Apple Inc.',
          price: { current: 175.25, change: 2.35, changePercent: 1.58 },
          marketCap: 2500000000000,
          peRatio: 28.5,
          dividendYield: 0.52,
          sector: 'Technology',
          volume: 45000000,
          score: 8.2,
          change: 2.35,
          changePercent: 1.58
        }
      ],
      totalCount: 1,
      totalPages: 1,
      currentPage: 1
    }
  }),
  getStockPriceHistory: vi.fn().mockResolvedValue({
    success: true,
    data: [
      { date: "2024-01-01", close: 170.25, volume: 45000000 },
      { date: "2024-01-02", close: 172.50, volume: 42000000 },
      { date: "2024-01-03", close: 175.25, volume: 45678900 }
    ]
  }),
  searchStocks: vi.fn().mockResolvedValue({
    success: true,
    data: [
      { symbol: 'AAPL', name: 'Apple Inc.', exchange: 'NASDAQ' }
    ]
  }),
  getTopStocks: vi.fn().mockResolvedValue({
    success: true,
    data: [
      { symbol: 'AAPL', name: 'Apple Inc.', price: 175.25, change: 2.35, changePercent: 1.58 }
    ]
  }),
  getStockDetail: vi.fn().mockResolvedValue({
    success: true,
    data: {
      symbol: "AAPL",
      company_name: "Apple Inc.",
      price: 175.25,
      previous_close: 172.75,
      change: 2.5,
      changePercent: 1.45,
      volume: 45678900,
      marketCap: 2750000000000,
      market_capitalization: 2750000000000,
      pe_ratio: 28.5,
      dividend_yield: 0.0052,
      beta: 1.2,
      high52Week: 198.23,
      low52Week: 124.17,
      avgVolume: 52000000,
      eps: 6.15,
      sector: "Technology",
      industry: "Consumer Electronics",
      country: "US",
      description: "Apple Inc. designs, manufactures, and markets smartphones..."
    }
  }),
  getStockPrice: createMockApiFunction('getStockPrice'),
  getStockHistory: vi.fn().mockResolvedValue({
    success: true,
    data: [
      { date: "2024-01-01", price: 170.25, volume: 45000000 },
      { date: "2024-01-02", price: 172.50, volume: 42000000 },
      { date: "2024-01-03", price: 175.25, volume: 45678900 }
    ]
  }),
  getStockFinancials: vi.fn().mockResolvedValue({
    success: true,
    data: {
      revenue: 383285000000,
      net_income: 94680000000,  // Component expects snake_case
      gross_margin: 0.421,
      operating_margin: 0.247,
      total_debt: 123000000000,
      total_cash: 51355000000,
      free_cash_flow: 84726000000  // Component expects this
    }
  }),
  getStockPrices: vi.fn().mockResolvedValue({
    success: true,
    data: [
      { date: "2024-01-01", close: 170.25, volume: 45000000, high: 172.0, low: 169.5, open: 170.0 },
      { date: "2024-01-02", close: 172.50, volume: 42000000, high: 173.2, low: 171.8, open: 171.5 },
      { date: "2024-01-03", close: 175.25, volume: 45678900, high: 175.8, low: 172.9, open: 173.0 }
    ]
  }),
  getMarketData: createMockApiFunction('getMarketData'),

  // Watchlist functions
  getWatchlist: vi.fn().mockResolvedValue({
    success: true,
    data: [
      {
        id: 1,
        symbol: "AAPL",
        name: "Apple Inc.",
        price: 175.43,
        change: 2.15,
        changePercent: 1.24,
      }
    ]
  }),
  addToWatchlist: createMockApiFunction('addToWatchlist'),
  removeFromWatchlist: createMockApiFunction('removeFromWatchlist'),

  // News and analysis
  getNews: createMockApiFunction('getNews'),
  getNewsAnalysis: createMockApiFunction('getNewsAnalysis'),
  getSentimentAnalysis: createMockApiFunction('getSentimentAnalysis'),

  // Technical analysis
  getTechnicalAnalysis: createMockApiFunction('getTechnicalAnalysis'),
  getTechnicalIndicators: createMockApiFunction('getTechnicalIndicators'),

  // Trading
  placeOrder: createMockApiFunction('placeOrder'),
  getOrders: createMockApiFunction('getOrders'),
  cancelOrder: createMockApiFunction('cancelOrder'),
  getTradingSignalsDaily: vi.fn().mockResolvedValue({
    success: true,
    data: [
      {
        id: "1", symbol: "AAPL", signal: "BUY", strength: "Strong",
        price: 175.43, targetPrice: 185.0, stopLoss: 165.0,
        confidence: 85, timeframe: "1D", timestamp: new Date().toISOString(),
        source: "Technical Analysis", description: "Golden cross pattern",
        sector: "Technology", marketCap: 2800000000000, volume: 50000000,
        dividend_yield: 0.0052  // Component expects this
      },
      {
        id: "2", symbol: "GOOGL", signal: "HOLD", strength: "Medium",
        price: 142.56, targetPrice: 150.0, stopLoss: 135.0,
        confidence: 70, timeframe: "1D", timestamp: new Date().toISOString(),
        source: "Fundamental Analysis", description: "Consolidation phase",
        sector: "Technology", marketCap: 1800000000000, volume: 28000000,
        dividend_yield: 0.0  // GOOGL doesn't pay dividends
      }
    ]
  }),
  getTradingPerformance: vi.fn().mockResolvedValue({
    success: true,
    data: {
      totalSignals: 150,
      winRate: 0.68,
      avgReturn: 0.045,
      sharpeRatio: 1.23
    }
  }),

  // Additional analytics functions
  getStockMetrics: vi.fn().mockResolvedValue({
    success: true,
    data: {
      metrics: {
        pe_ratio: 28.5,
        market_cap: 2800000000000,
        dividend_yield: 0.0052,  // Component expects this (0.52%)
        book_value: 15.67,       // Component expects this
        beta: 1.2,
        eps: 6.15
      }
    }
  }),

  // Additional StockDetail API functions
  getStockProfile: vi.fn().mockResolvedValue({
    success: true,
    data: [
      {
        symbol: "AAPL",
        company_name: "Apple Inc.",
        sector: "Technology",
        industry: "Consumer Electronics",
        description: "Apple Inc. designs, manufactures, and markets smartphones...",
        country: "US",
        website: "https://www.apple.com",
        employees: 154000
      }
    ]
  }),

  getAnalystRecommendations: vi.fn().mockResolvedValue({
    success: true,
    data: [
      { analyst: 'Goldman Sachs', rating: 'Buy', target: 185.0, date: '2024-01-15' },
      { analyst: 'Morgan Stanley', rating: 'Hold', target: 175.0, date: '2024-01-14' }
    ]
  }),

  getBalanceSheet: vi.fn().mockResolvedValue({
    success: true,
    data: [
      {
        total_assets: 352755000000,
        total_liabilities: 290437000000,
        stockholder_equity: 62318000000,
        cash_and_equivalents: 51355000000,
        total_debt: 123000000000
      }
    ]
  }),

  getIncomeStatement: vi.fn().mockResolvedValue({
    success: true,
    data: [
      {
        revenue: 394328000000,
        cost_of_revenue: 223546000000,
        gross_profit: 170782000000,
        operating_expenses: 55013000000,
        operating_income: 115769000000,
        net_income: 99803000000
      }
    ]
  }),

  getCashFlowStatement: vi.fn().mockResolvedValue({
    success: true,
    data: [
      {
        operating_cash_flow: 122151000000,
        investing_cash_flow: -10635000000,
        financing_cash_flow: -108488000000,
        free_cash_flow: 84726000000,
        capital_expenditures: -7309000000
      }
    ]
  }),

  getAnalystOverview: vi.fn().mockResolvedValue({
    success: true,
    data: {
      consensus_rating: "Buy",
      average_target: 185.50,
      high_target: 200.0,
      low_target: 165.0,
      analyst_count: 25,
      strong_buy: 10,
      buy: 8,
      hold: 5,
      sell: 2,
      strong_sell: 0
    }
  }),

  getStockPricesRecent: vi.fn().mockResolvedValue({
    success: true,
    data: [
      { date: "2024-01-01", close: 170.25, volume: 45000000, high: 172.0, low: 169.5, open: 170.0 },
      { date: "2024-01-02", close: 172.50, volume: 42000000, high: 173.2, low: 171.8, open: 171.5 },
      { date: "2024-01-03", close: 175.25, volume: 45678900, high: 175.8, low: 172.9, open: 173.0 }
    ]
  }),

  // Technical Analysis functions
  getTechnicalData: vi.fn().mockResolvedValue({
    success: true,
    data: {
      indicators: {
        rsi: 45.2,
        macd: { macd: 1.23, signal: 1.15, histogram: 0.08 },
        bollinger: { upper: 178.5, middle: 175.2, lower: 171.9 },
        sma_20: 174.8,
        sma_50: 172.1,
        ema_12: 175.4,
        ema_26: 173.9
      },
      signals: ['bullish_macd', 'neutral_rsi'],
      trend: 'upward',
      strength: 'moderate'
    }
  }),

  // Authentication and user
  login: createMockApiFunction('login'),
  logout: createMockApiFunction('logout'),
  getProfile: createMockApiFunction('getProfile'),
  updateProfile: createMockApiFunction('updateProfile'),

  // API keys and configuration
  getApiKeys: vi.fn().mockResolvedValue({ success: true, data: {} }),
  setApiKeys: createMockApiFunction('setApiKeys'),
  testApiConnection: vi.fn().mockResolvedValue({ success: true }),

  // Broker integration
  importPortfolioFromBroker: vi.fn().mockResolvedValue({ success: true }),
  getBrokerAccounts: createMockApiFunction('getBrokerAccounts'),

  // Utilities
  apiCall: createMockApiFunction('apiCall'),
  uploadFile: createMockApiFunction('uploadFile'),

  // Financial Data functions
  getKeyMetrics: vi.fn().mockResolvedValue({
    success: true,
    data: [
      {
        symbol: 'AAPL',
        pe_ratio: 28.5,
        dividend_yield: 0.0052,
        book_value: 15.67,
        roe: 0.175,
        roa: 0.283,
        revenue_growth: 0.078,
        eps_growth: 0.092
      }
    ]
  }),

  // Market Commentary functions
  getMarketTrends: vi.fn().mockResolvedValue({
    success: true,
    data: {
      trends: [
        { period: 'week', direction: 'up', strength: 'moderate', description: 'Market showing upward momentum' },
        { period: 'month', direction: 'sideways', strength: 'weak', description: 'Consolidation phase' }
      ]
    }
  }),
  getAnalystOpinions: vi.fn().mockResolvedValue({
    success: true,
    data: {
      opinions: [
        { analyst: 'Goldman Sachs', rating: 'Buy', target: 185.0, date: '2024-01-15' },
        { analyst: 'Morgan Stanley', rating: 'Hold', target: 175.0, date: '2024-01-14' }
      ]
    }
  }),
  subscribeToCommentary: vi.fn().mockResolvedValue({
    success: true,
    data: { subscribed: true, categories: ['market', 'earnings', 'technical'] }
  }),

  // Service Health functions
  getDiagnosticInfo: vi.fn().mockResolvedValue({
    success: true,
    data: {
      system: {
        uptime: 3600,
        memory: { used: 256, total: 1024 },
        cpu: { usage: 25 },
        disk: { used: 50, total: 100 }
      },
      services: {
        database: { status: 'healthy', response_time: 15 },
        cache: { status: 'healthy', response_time: 5 },
        external_api: { status: 'healthy', response_time: 100 }
      },
      version: '1.0.0',
      environment: 'test'
    }
  }),
  getCurrentBaseURL: vi.fn(() => 'http://localhost:3001'),
  getCurrentUser: vi.fn().mockResolvedValue({
    success: true,
    data: { id: 1, name: 'Test User', email: 'test@example.com' }
  }),

  // API instance for direct HTTP calls
  api: {
    get: vi.fn().mockResolvedValue({
      data: {
        success: true,
        data: {}
      }
    }),
    post: vi.fn().mockResolvedValue({
      data: {
        success: true,
        data: {}
      }
    }),
    put: vi.fn().mockResolvedValue({
      data: {
        success: true,
        data: {}
      }
    }),
    delete: vi.fn().mockResolvedValue({
      data: {
        success: true,
        data: {}
      }
    }),
  },
};

export default mockApi;
export const api = mockApi.api;