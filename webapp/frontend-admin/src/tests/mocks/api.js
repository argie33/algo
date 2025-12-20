import { vi } from "vitest";

// Comprehensive API mock data
const mockApiData = {
  portfolio: {
    value: 1250000,
    dailyChange: 3200,
    dailyChangePercent: 0.26,
    holdings: [
      { symbol: "AAPL", shares: 100, value: 19500, weight: 15.6 },
      { symbol: "TSLA", shares: 50, value: 35500, weight: 28.4 },
      { symbol: "NVDA", shares: 25, value: 30000, weight: 24.0 },
    ],
  },
  market: {
    indices: {
      SPY: { price: 543.21, change: 0.8, symbol: "S&P 500" },
      QQQ: { price: 378.90, change: -0.1, symbol: "NASDAQ" },
      DIA: { price: 389.00, change: 0.4, symbol: "DOW" },
    },
    status: "open",
    session: "regular",
  },
  tradingSignals: [
    {
      symbol: "AAPL",
      signal: "BUY",
      confidence: 92,
      type: "Technical",
      timestamp: "2024-01-15T10:30:00Z",
    },
    {
      symbol: "TSLA",
      signal: "SELL",
      confidence: 87,
      type: "Momentum",
      timestamp: "2024-01-15T10:25:00Z",
    },
  ],
  topStocks: [
    { symbol: "NVDA", score: 95, price: 1200.0, change: 3.5 },
    { symbol: "MSFT", score: 88, price: 420.5, change: 0.7 },
    { symbol: "GOOGL", score: 85, price: 2800.0, change: 1.2 },
  ],
  user: {
    id: "test-user",
    name: "Test User",
    email: "test@example.com",
  },
};

// Create comprehensive mock functions
export const createApiMock = () => ({
  // Config
  getApiConfig: vi.fn(() => ({
    baseURL: "http://localhost:3001",
    environment: "test",
    isDevelopment: true,
  })),

  // Portfolio functions
  getPortfolioData: vi.fn().mockResolvedValue({
    success: true,
    data: mockApiData.portfolio,
  }),
  getPortfolioHoldings: vi.fn().mockResolvedValue({
    success: true,
    data: { holdings: mockApiData.portfolio.holdings },
  }),
  getPortfolioAnalytics: vi.fn().mockResolvedValue({
    success: true,
    data: {
      totalValue: mockApiData.portfolio.value,
      dailyChange: mockApiData.portfolio.dailyChange,
      performance: { ytd: 23.7, winRate: 87.2 },
    },
  }),

  // Market functions
  getMarketOverview: vi.fn().mockResolvedValue({
    success: true,
    data: mockApiData.market,
  }),
  getMarketStatus: vi.fn().mockResolvedValue({
    success: true,
    data: { status: "open", session: "regular" },
  }),

  // Trading functions
  getTradingSignalsDaily: vi.fn().mockResolvedValue({
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
      }
    ],
    timeframe: "daily",
    count: 1,
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
  }),
  getTradingPositions: vi.fn().mockResolvedValue({
    success: true,
    data: { positions: [] },
  }),

  // Stock functions
  getTopStocks: vi.fn().mockResolvedValue({
    success: true,
    data: { stocks: mockApiData.topStocks },
  }),

  // User functions
  getCurrentUser: vi.fn().mockResolvedValue({
    success: true,
    data: mockApiData.user,
  }),

  // News functions
  getStockNews: vi.fn().mockResolvedValue({
    success: true,
    data: {
      articles: [
        {
          title: "Market Update",
          summary: "Markets showing strength",
          url: "#",
          publishedAt: "2024-01-15",
        },
      ],
    },
  }),

  // Default api object
  api: {
    get: vi.fn().mockResolvedValue({ data: { success: true, data: {} } }),
    post: vi.fn().mockResolvedValue({ data: { success: true, data: {} } }),
    put: vi.fn().mockResolvedValue({ data: { success: true, data: {} } }),
    delete: vi.fn().mockResolvedValue({ data: { success: true, data: {} } }),
  },

  // Default export
  default: {
    get: vi.fn().mockResolvedValue({ data: { success: true, data: {} } }),
    post: vi.fn().mockResolvedValue({ data: { success: true, data: {} } }),
  },
});

// Export the mock for use in tests
export const mockApi = createApiMock();