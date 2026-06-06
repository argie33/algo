import { vi } from "vitest";

// Create a comprehensive API service mock
export const createApiServiceMock = () => {
  const mockApi = {
    get: vi.fn().mockResolvedValue({ data: { statusCode: 200, data: {} } }),
    post: vi.fn().mockResolvedValue({ data: { statusCode: 200, data: {} } }),
    put: vi.fn().mockResolvedValue({ data: { statusCode: 200, data: {} } }),
    delete: vi.fn().mockResolvedValue({ data: { statusCode: 200, data: {} } }),
    patch: vi.fn().mockResolvedValue({ data: { statusCode: 200, data: {} } }),
    request: vi.fn().mockResolvedValue({ data: { statusCode: 200, data: {} } }),
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
    initializeApiConfig: vi.fn(),
    setRefreshCallback: vi.fn(),
    getPortfolioData: vi.fn().mockResolvedValue({ data: { statusCode: 200, data: {} } }),
    getPortfolioHoldings: vi.fn().mockResolvedValue({ data: { statusCode: 200, items: [], total: 0 } }),
    getPortfolioAnalytics: vi.fn().mockResolvedValue({ data: { statusCode: 200, data: {} } }),
    getMarketOverview: vi.fn().mockResolvedValue({ data: { statusCode: 200, data: {} } }),
    getMarketStatus: vi.fn().mockResolvedValue({ data: { statusCode: 200, data: { status: "open" } } }),
    getTradingSignalsDaily: vi.fn().mockResolvedValue({ data: { statusCode: 200, items: [], total: 0 } }),
    getTradingPositions: vi.fn().mockResolvedValue({ data: { statusCode: 200, items: [], total: 0 } }),
    getTopStocks: vi.fn().mockResolvedValue({ data: { statusCode: 200, items: [], total: 0 } }),
    getCurrentUser: vi.fn().mockResolvedValue({ data: { statusCode: 200, data: {} } }),
    getStockNews: vi.fn().mockResolvedValue({ data: { statusCode: 200, items: [], total: 0 } }),
    healthCheck: vi.fn().mockResolvedValue({ data: { statusCode: 200 } }),
    testApiConnection: vi.fn().mockResolvedValue({ data: { statusCode: 200 } }),
  };
};
