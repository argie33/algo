import { vi } from "vitest";

// Create a comprehensive API service mock
export const createApiServiceMock = () => {
  const mockApi = {
    get: vi.fn().mockResolvedValue({ data: { success: true, data: {} } }),
    post: vi.fn().mockResolvedValue({ data: { success: true, data: {} } }),
    put: vi.fn().mockResolvedValue({ data: { success: true, data: {} } }),
    delete: vi.fn().mockResolvedValue({ data: { success: true, data: {} } }),
    patch: vi.fn().mockResolvedValue({ data: { success: true, data: {} } }),
    request: vi.fn().mockResolvedValue({ data: { success: true, data: {} } }),
  };

  return {
    api: mockApi,
    default: mockApi,
    // Named exports
    getApiConfig: vi.fn(() => ({
      baseURL: "http://localhost:3001",
      environment: "test",
      isDevelopment: true,
    })),
    getPortfolioData: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getPortfolioHoldings: vi.fn().mockResolvedValue({ success: true, data: { holdings: [] } }),
    getPortfolioAnalytics: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getMarketOverview: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getMarketStatus: vi.fn().mockResolvedValue({ success: true, data: { status: "open" } }),
    getTradingSignalsDaily: vi.fn().mockResolvedValue({ success: true, data: [] }),
    getTradingPositions: vi.fn().mockResolvedValue({ success: true, data: { positions: [] } }),
    getTopStocks: vi.fn().mockResolvedValue({ success: true, data: { stocks: [] } }),
    getCurrentUser: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getStockNews: vi.fn().mockResolvedValue({ success: true, data: { articles: [] } }),
    healthCheck: vi.fn().mockResolvedValue({ success: true }),
    testApiConnection: vi.fn().mockResolvedValue({ success: true }),
  };
};
