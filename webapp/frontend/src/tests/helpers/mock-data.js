/**
 * Mock Data Helpers for Unit Tests
 * Provides realistic mock data for testing components
 */

export const mockUser = {
  id: 'test-user-123',
  email: 'test@example.com',
  name: 'Test User',
  subscription: 'premium',
  preferences: {
    theme: 'light',
    notifications: true
  }
}

export const mockApiKeys = {
  alpaca: {
    key: 'test-alpaca-key',
    secret: 'test-alpaca-secret',
    isValid: true,
    lastValidated: '2025-07-20T10:00:00Z'
  },
  polygon: {
    key: 'test-polygon-key',
    isValid: true,
    lastValidated: '2025-07-20T10:00:00Z'
  }
}

export const mockPortfolioData = [
  {
    id: 'portfolio-1',
    name: 'Growth Portfolio',
    value: 125000.50,
    dayChange: 1250.75,
    dayChangePercent: 1.01,
    holdings: [
      {
        symbol: 'AAPL',
        shares: 100,
        avgCost: 150.25,
        currentPrice: 175.30,
        value: 17530,
        dayChange: 250,
        dayChangePercent: 1.45
      },
      {
        symbol: 'MSFT',
        shares: 50,
        avgCost: 280.50,
        currentPrice: 295.75,
        value: 14787.50,
        dayChange: 762.50,
        dayChangePercent: 5.44
      }
    ]
  }
]

export const mockStockData = {
  symbol: 'AAPL',
  price: 175.30,
  change: 2.45,
  changePercent: 1.42,
  volume: 45678900,
  marketCap: 2780000000000,
  peRatio: 28.5,
  high52Week: 198.23,
  low52Week: 124.17
}

export const mockChartData = [
  { date: '2025-01-01', price: 150.25 },
  { date: '2025-01-02', price: 152.30 },
  { date: '2025-01-03', price: 148.75 },
  { date: '2025-01-04', price: 155.40 },
  { date: '2025-01-05', price: 175.30 }
]

export const mockNewsData = [
  {
    id: 'news-1',
    title: 'Apple Reports Strong Q4 Earnings',
    summary: 'Apple exceeded expectations with strong iPhone sales and services revenue.',
    url: 'https://example.com/news/1',
    publishedAt: '2025-07-20T09:00:00Z',
    source: 'Financial News',
    sentiment: 'positive'
  },
  {
    id: 'news-2',
    title: 'Market Analysis: Tech Stocks Rally',
    summary: 'Technology stocks continue their upward trend amid positive earnings reports.',
    url: 'https://example.com/news/2',
    publishedAt: '2025-07-20T08:30:00Z',
    source: 'Market Watch',
    sentiment: 'positive'
  }
]

export const mockWatchlistData = [
  { symbol: 'AAPL', name: 'Apple Inc.', price: 175.30, change: 2.45, changePercent: 1.42 },
  { symbol: 'MSFT', name: 'Microsoft Corp.', price: 295.75, change: 15.25, changePercent: 5.44 },
  { symbol: 'GOOGL', name: 'Alphabet Inc.', price: 138.21, change: -1.15, changePercent: -0.82 },
  { symbol: 'TSLA', name: 'Tesla Inc.', price: 248.50, change: 12.30, changePercent: 5.21 }
]

export const mockTradeData = [
  {
    id: 'trade-1',
    symbol: 'AAPL',
    type: 'BUY',
    quantity: 100,
    price: 150.25,
    timestamp: '2025-07-20T14:30:00Z',
    status: 'filled'
  },
  {
    id: 'trade-2',
    symbol: 'MSFT',
    type: 'SELL',
    quantity: 25,
    price: 295.75,
    timestamp: '2025-07-20T13:45:00Z',
    status: 'pending'
  }
]

export const mockMarketData = {
  indices: {
    SPY: { price: 425.30, change: 2.15, changePercent: 0.51 },
    QQQ: { price: 368.75, change: 5.20, changePercent: 1.43 },
    IWM: { price: 198.45, change: -0.85, changePercent: -0.43 }
  },
  sectors: {
    technology: { change: 1.85, changePercent: 1.2 },
    healthcare: { change: 0.95, changePercent: 0.7 },
    financials: { change: -0.45, changePercent: -0.3 }
  }
}

// Helper functions to create mock data
export const createMockPortfolio = (overrides = {}) => ({
  ...mockPortfolioData[0],
  ...overrides
})

export const createMockStock = (symbol = 'AAPL', overrides = {}) => ({
  ...mockStockData,
  symbol,
  ...overrides
})

export const createMockUser = (overrides = {}) => ({
  ...mockUser,
  ...overrides
})

// Mock API responses
export const mockApiResponses = {
  portfolio: { data: mockPortfolioData },
  stocks: { data: mockWatchlistData },
  news: { data: mockNewsData },
  trades: { data: mockTradeData },
  market: { data: mockMarketData }
}

// Mock error responses
export const mockErrorResponses = {
  unauthorized: { error: 'Unauthorized', status: 401 },
  notFound: { error: 'Not Found', status: 404 },
  serverError: { error: 'Internal Server Error', status: 500 }
}