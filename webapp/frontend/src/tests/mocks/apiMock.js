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
    holdings: [],
    summary: {
      totalValue: 100000,
      totalCost: 85000,
      totalPnl: 15000,
      totalPnlPercent: 17.5,
    },
    performance: {
      totalReturn: 15000,
      totalReturnPercent: 17.5,
    },
  },
});

export const getApiKeys = vi.fn().mockResolvedValue({ success: true, data: {} });
export const testApiConnection = vi.fn().mockResolvedValue({ success: true });
export const importPortfolioFromBroker = vi.fn().mockResolvedValue({ success: true });
export const healthCheck = vi.fn().mockResolvedValue({ success: true });
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
const createMockApiFunction = (_name) => vi.fn().mockResolvedValue({
  success: true,
  data: null
});

// Default export mock
const mockApi = {
  // Core HTTP methods
  get: vi.fn().mockResolvedValue({ data: {} }),
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
      holdings: [],
      summary: {
        totalValue: 100000,
        totalCost: 85000,
        totalPnl: 15000,
        totalPnlPercent: 17.5,
      },
      performance: {
        totalReturn: 15000,
        totalReturnPercent: 17.5,
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
  getStockPrice: createMockApiFunction('getStockPrice'),
  getStockHistory: createMockApiFunction('getStockHistory'),
  getStockPrices: createMockApiFunction('getStockPrices'),
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
};

export default mockApi;