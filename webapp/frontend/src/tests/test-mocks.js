/**
 * Comprehensive Mock Utilities for Testing
 * Provides standardized mocks for all services to eliminate test failures
 */

import React from 'react';

// Complete API Service Mock
export const createApiServiceMock = () => ({
  default: {
    // Core API methods
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    put: vi.fn().mockResolvedValue({ data: {} }),
    delete: vi.fn().mockResolvedValue({ data: {} }),

    // Dashboard methods
    getDashboard: vi.fn().mockResolvedValue({
      success: true,
      data: {
        portfolio: { value: 10000, change: 150, changePercent: 1.5 },
        market: { sp500: 4200, nasdaq: 13000, dow: 34000 },
        activity: []
      }
    }),

    // Market data methods
    getMarketOverview: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getMarketStatus: vi.fn().mockResolvedValue({ success: true, data: { isOpen: true } }),
    getMarketSentiment: vi.fn().mockResolvedValue({ success: true, data: {} }),

    // Portfolio methods
    getPortfolioSummary: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getPortfolioAnalytics: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getPortfolioHistory: vi.fn().mockResolvedValue({ success: true, data: [] }),

    // Stock data methods
    getStockPrices: vi.fn().mockResolvedValue({ success: true, data: [] }),
    getStockMetrics: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getStockDetail: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getStockScores: vi.fn().mockResolvedValue({ success: true, data: [] }),
    getScores: vi.fn().mockResolvedValue({ success: true, data: [] }),

    // Trading methods
    getTradingSignalsDaily: vi.fn().mockResolvedValue({ success: true, data: [] }),
    getTradingSignals: vi.fn().mockResolvedValue({ success: true, data: [] }),

    // News and sentiment
    getNews: vi.fn().mockResolvedValue({ success: true, data: [] }),
    getSentimentTrends: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getSocialMediaSentiment: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getSymbolSentiment: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getSentimentIndicators: vi.fn().mockResolvedValue({ success: true, data: {} }),

    // Technical analysis
    getTechnicalIndicators: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getPatternRecognition: vi.fn().mockResolvedValue({ success: true, data: [] }),

    // Screening and analysis
    screenStocks: vi.fn().mockResolvedValue({ success: true, data: { results: [], totalCount: 0 } }),
    getAdvancedScreener: vi.fn().mockResolvedValue({ success: true, data: [] }),

    // Economic data
    getEconomicIndicators: vi.fn().mockResolvedValue({ success: true, data: [] }),
    getEarningsCalendar: vi.fn().mockResolvedValue({ success: true, data: [] }),

    // Backtest and modeling
    runBacktest: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getBacktestResults: vi.fn().mockResolvedValue({ success: true, data: {} }),

    // User and settings
    getUserSettings: vi.fn().mockResolvedValue({ success: true, data: {} }),
    updateUserSettings: vi.fn().mockResolvedValue({ success: true }),

    // Watchlist
    getWatchlist: vi.fn().mockResolvedValue({ success: true, data: [] }),
    addToWatchlist: vi.fn().mockResolvedValue({ success: true }),
    removeFromWatchlist: vi.fn().mockResolvedValue({ success: true }),
  },

  // Export individual methods for legacy compatibility
  getDashboard: vi.fn().mockResolvedValue({ success: true, data: {} }),
  getMarketOverview: vi.fn().mockResolvedValue({ success: true, data: {} }),
  getPortfolioSummary: vi.fn().mockResolvedValue({ success: true, data: {} }),
  getPortfolioAnalytics: vi.fn().mockResolvedValue({ success: true, data: {} }),
  getStockPrices: vi.fn().mockResolvedValue({ success: true, data: [] }),
  getStockMetrics: vi.fn().mockResolvedValue({ success: true, data: {} }),
  getTradingSignalsDaily: vi.fn().mockResolvedValue({ success: true, data: [] }),
  getScores: vi.fn().mockResolvedValue({ success: true, data: [] }),
  getMarketSentiment: vi.fn().mockResolvedValue({ success: true, data: {} }),
  getSentimentTrends: vi.fn().mockResolvedValue({ success: true, data: {} }),
  getSocialMediaSentiment: vi.fn().mockResolvedValue({ success: true, data: {} }),
  getSymbolSentiment: vi.fn().mockResolvedValue({ success: true, data: {} }),
  getSentimentIndicators: vi.fn().mockResolvedValue({ success: true, data: {} }),

  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    environment: "test",
  })),
});

// Complete DataCache Service Mock
export const createDataCacheMock = () => ({
  default: {
    getCachedData: vi.fn(() => null),
    setCachedData: vi.fn(),
    clearCache: vi.fn(),
    isRateLimited: vi.fn(() => false),
    canMakeApiCall: vi.fn(() => true),
    recordApiCall: vi.fn(),
    get: vi.fn().mockResolvedValue({ data: {} }),
    isMarketHours: vi.fn(() => true),
  },
  getCachedData: vi.fn(() => null),
  setCachedData: vi.fn(),
  clearCache: vi.fn(),
});

// Real-time services mock
export const createRealTimeServiceMock = () => ({
  default: {
    connect: vi.fn(),
    disconnect: vi.fn(),
    subscribe: vi.fn(() => "subscription-id"),
    unsubscribe: vi.fn(),
    isConnected: vi.fn(() => false),
    getLatestData: vi.fn(() => ({})),
    subscribeToNews: vi.fn(() => "news-subscription-id"),
    unsubscribeFromNews: vi.fn(),
    getLatestNews: vi.fn(() => []),
    fetchBreakingNews: vi.fn().mockResolvedValue([]),
    getAllLatestSentiments: vi.fn().mockResolvedValue({}),
  },
});

// Auth context mock
export const createAuthContextMock = () => ({
  useAuth: vi.fn(() => ({
    user: { username: "testuser", email: "test@example.com" },
    isAuthenticated: true,
    isLoading: false,
  })),
  AuthProvider: ({ children }) => children,
});

// Real-time sentiment score component mock
export const createRealTimeSentimentScoreMock = () => ({
  default: ({ symbol, showDetails, size }) => (
    React.createElement('div', {
      'data-testid': 'real-time-sentiment-score'
    }, [
      React.createElement('span', { key: 'symbol' }, `Real-Time Sentiment for ${symbol}`),
      showDetails && React.createElement('span', { key: 'details' }, 'Details shown'),
      React.createElement('span', { key: 'size' }, `Size: ${size}`)
    ])
  ),
});

// Common mock data
export const mockSentimentData = {
  overall: {
    score: 0.65,
    label: "Bullish",
    confidence: 0.78,
    change: 0.12,
    changePercent: 22.5,
  },
  breakdown: {
    veryBullish: 25,
    bullish: 35,
    neutral: 25,
    bearish: 12,
    veryBearish: 3,
  },
  topSymbols: [
    { symbol: "AAPL", sentiment: 0.8, volume: 1500 },
    { symbol: "GOOGL", sentiment: 0.7, volume: 1200 },
    { symbol: "MSFT", sentiment: 0.75, volume: 1100 },
  ],
};

export const mockNewsData = [
  {
    id: "news_1",
    title: "Apple reports strong quarterly earnings",
    summary: "Apple exceeded analyst expectations with record revenue growth",
    source: "Reuters",
    publishedAt: "2024-01-01T10:00:00Z",
    url: "https://reuters.com/apple-earnings",
    symbols: ["AAPL"],
    sentiment: { score: 0.8, label: "positive", confidence: 0.9 },
    impact: { score: 0.7, level: "medium" },
    isRealTime: true,
    timestamp: Date.now(),
  },
];