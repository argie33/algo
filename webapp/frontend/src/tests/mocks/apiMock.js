import { vi } from "vitest";

export const getApiConfig = vi.fn().mockReturnValue({
  apiUrl: "http://localhost:3001",
  environment: "test",
});

export const getPortfolioData = vi.fn().mockResolvedValue({
  success: true,
  data: {
    positions: [],
    total_value: 100000,
    daily_pnl: 500,
    total_pnl: 5000,
  },
});

export const getPortfolioAnalytics = vi.fn().mockResolvedValue({
  success: true,
  data: {
    allocation: [],
    performance: [],
  },
});

export const getTradingSignalsDaily = vi.fn().mockResolvedValue({
  success: true,
  data: [],
});

export const getStockPrices = vi.fn().mockResolvedValue({
  success: true,
  data: {},
});

export const getStockMetrics = vi.fn().mockResolvedValue({
  success: true,
  data: {},
});

export const getTopStocks = vi.fn().mockResolvedValue({
  success: true,
  data: [],
});

export const getCurrentUser = vi.fn().mockResolvedValue({
  success: true,
  data: { id: 1, name: "Test User" },
});

export const getApiKeys = vi.fn().mockResolvedValue({
  success: true,
  data: [],
});

export const testApiConnection = vi.fn().mockResolvedValue({
  success: true,
});

export const importPortfolioFromBroker = vi.fn().mockResolvedValue({
  success: true,
  data: [],
});

export const healthCheck = vi.fn().mockResolvedValue({
  success: true,
  status: "healthy",
});

export const getMarketOverview = vi.fn().mockResolvedValue({
  success: true,
  data: {
    sp500: { value: 4500, change: 0.5 },
  },
});

export default {
  getApiConfig,
  getPortfolioData,
  getPortfolioAnalytics,
  getTradingSignalsDaily,
  getStockPrices,
  getStockMetrics,
  getTopStocks,
  getCurrentUser,
  getApiKeys,
  testApiConnection,
  importPortfolioFromBroker,
  healthCheck,
  getMarketOverview,
};
