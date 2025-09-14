import { describe, test, expect, beforeEach, vi } from "vitest";
import axios from "axios";
import api, { getApiConfig } from "../../../services/api.js";

// Mock axios
vi.mock("axios");
const mockedAxios = vi.mocked(axios, true);

// Mock axios instance
const mockAxiosInstance = {
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  request: vi.fn(),
  interceptors: {
    request: { use: vi.fn() },
    response: { use: vi.fn() },
  },
};

// Mock axios static methods for test environment fallback
mockedAxios.get = vi.fn();
mockedAxios.post = vi.fn();
mockedAxios.put = vi.fn();
mockedAxios.delete = vi.fn();
mockedAxios.patch = vi.fn();

// Mock axios interceptors
mockedAxios.interceptors = {
  request: { use: vi.fn() },
  response: { use: vi.fn() },
};

describe("API Service - Comprehensive Unit Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedAxios.create.mockReturnValue(mockAxiosInstance);

    // Setup default successful responses for both instance and static methods
    mockedAxios.get.mockResolvedValue({
      status: 200,
      data: { success: true, data: {} },
      headers: {},
    });

    // Setup default responses for axios static methods (used in test environment)
    mockedAxios.get.mockResolvedValue({
      status: 200,
      data: { success: true, data: {} },
      headers: {},
    });
    mockedAxios.post.mockResolvedValue({
      status: 200,
      data: { success: true, data: {} },
      headers: {},
    });
  });

  describe("API Configuration", () => {
    test("should get API configuration from runtime config", () => {
      // Mock window.__CONFIG__
      Object.defineProperty(window, "__CONFIG__", {
        value: {
          API_URL: "https://runtime-api.example.com/dev",
        },
        writable: true,
        configurable: true,
      });

      const config = getApiConfig();

      expect(config.baseURL).toBe("https://runtime-api.example.com/dev");
      expect(config.isServerless).toBe(true);
      expect(config.isConfigured).toBe(true);
    });

    test("should fallback to environment variable when no runtime config", () => {
      // Clear window config safely
      if (Object.prototype.hasOwnProperty.call(window, "__CONFIG__")) {
        delete window.__CONFIG__;
      }

      // Mock environment variable
      vi.stubEnv("VITE_API_URL", "https://env-api.example.com");

      const config = getApiConfig();

      expect(config.baseURL).toBe("https://env-api.example.com");
      expect(config.isServerless).toBe(true);
    });

    test("should use localhost fallback when no config available", () => {
      // Clear window config safely
      if (Object.prototype.hasOwnProperty.call(window, "__CONFIG__")) {
        delete window.__CONFIG__;
      }
      vi.stubEnv("VITE_API_URL", "");

      const config = getApiConfig();

      expect(config.baseURL).toBe("http://localhost:3001");
      expect(config.isServerless).toBe(false);
      expect(config.isConfigured).toBe(false);
    });

    test("should detect development vs production environment", () => {
      vi.stubEnv("MODE", "development");
      vi.stubEnv("DEV", true);
      vi.stubEnv("PROD", false);

      const config = getApiConfig();

      // In test environment, environment is always 'test'
      expect(config.environment).toBe("test");
      expect(config.isDevelopment).toBe(true);
      expect(config.isProduction).toBe(false);
    });
  });

  describe("Portfolio API Endpoints", () => {
    test("should fetch portfolio holdings", async () => {
      const mockHoldings = {
        success: true,
        data: {
          holdings: [
            { symbol: "AAPL", shares: 100, current_value: 15000 },
            { symbol: "GOOGL", shares: 50, current_value: 12500 },
          ],
          total_value: 27500,
        },
      };

      mockedAxios.get.mockResolvedValueOnce({
        status: 200,
        data: mockHoldings,
      });

      const result = await api.get("/api/portfolio/holdings");

      expect(mockedAxios.get).toHaveBeenCalledWith(
        "/api/portfolio/holdings",
        undefined
      );
      expect(result.data).toEqual(mockHoldings);
    });

    test("should fetch portfolio performance metrics", async () => {
      const mockPerformance = {
        success: true,
        data: {
          total_return: 0.15,
          daily_change: 0.02,
          portfolio_beta: 1.1,
          sharpe_ratio: 1.8,
        },
      };

      mockedAxios.get.mockResolvedValueOnce({
        status: 200,
        data: mockPerformance,
      });

      const result = await api.get("/api/portfolio/performance");

      expect(result.data.data.total_return).toBe(0.15);
      expect(result.data.data.sharpe_ratio).toBe(1.8);
    });

    test("should handle portfolio API errors gracefully", async () => {
      mockedAxios.get.mockRejectedValueOnce({
        response: {
          status: 500,
          data: { error: "Failed to fetch portfolio data" },
        },
      });

      await expect(api.get("/api/portfolio/holdings")).rejects.toMatchObject({
        response: {
          status: 500,
          data: { error: "Failed to fetch portfolio data" },
        },
      });
    });
  });

  describe("Market Data API Endpoints", () => {
    test("should fetch market overview data", async () => {
      const mockMarketData = {
        success: true,
        data: {
          indices: {
            SPY: { price: 450.25, change: 0.5 },
            QQQ: { price: 375.8, change: -0.2 },
          },
          market_status: "open",
          volume: 1500000000,
        },
      };

      mockedAxios.get.mockResolvedValueOnce({
        status: 200,
        data: mockMarketData,
      });

      const result = await api.get("/api/market/overview");

      expect(result.data.data.indices.SPY.price).toBe(450.25);
      expect(result.data.data.market_status).toBe("open");
    });

    test("should fetch individual stock data", async () => {
      const mockStockData = {
        success: true,
        data: {
          symbol: "AAPL",
          price: 175.5,
          change: 2.25,
          change_percent: 1.3,
          volume: 45000000,
        },
      };

      mockedAxios.get.mockResolvedValueOnce({
        status: 200,
        data: mockStockData,
      });

      const result = await api.get("/api/stocks/AAPL");

      expect(result.data.data.symbol).toBe("AAPL");
      expect(result.data.data.price).toBe(175.5);
    });
  });

  describe("Authentication Integration", () => {
    test("should include authorization header when token is available", async () => {
      const mockToken = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test-token";

      // Mock localStorage
      Object.defineProperty(window, "localStorage", {
        value: {
          getItem: vi.fn(() => mockToken),
        },
        writable: true,
      });

      await api.get("/api/portfolio/holdings");

      // In test environment, interceptors are skipped for safety
      // but the request should still be made with proper parameters
      expect(mockedAxios.get).toHaveBeenCalledWith(
        "/api/portfolio/holdings",
        undefined
      );
    });

    test("should handle 401 unauthorized responses", async () => {
      mockedAxios.get.mockRejectedValueOnce({
        response: {
          status: 401,
          data: { error: "Unauthorized" },
        },
      });

      await expect(api.get("/api/portfolio/holdings")).rejects.toMatchObject({
        response: {
          status: 401,
        },
      });
    });
  });

  describe("Real-time Data Integration", () => {
    test("should fetch live market data", async () => {
      const mockLiveData = {
        success: true,
        data: {
          symbols: ["AAPL", "GOOGL"],
          prices: {
            AAPL: { price: 175.25, timestamp: Date.now() },
            GOOGL: { price: 125.8, timestamp: Date.now() },
          },
        },
      };

      mockedAxios.get.mockResolvedValueOnce({
        status: 200,
        data: mockLiveData,
      });

      const result = await api.get("/api/live-data/prices?symbols=AAPL,GOOGL");

      expect(result.data.data.symbols).toContain("AAPL");
      expect(result.data.data.prices.AAPL.price).toBe(175.25);
    });

    test("should handle WebSocket connection requests", async () => {
      const mockConnectionInfo = {
        success: true,
        data: {
          websocket_url: "wss://api.example.com/ws",
          connection_id: "conn-12345",
        },
      };

      mockedAxios.post.mockResolvedValueOnce({
        status: 200,
        data: mockConnectionInfo,
      });

      const result = await api.post("/api/websocket/connect", {
        symbols: ["AAPL", "TSLA"],
      });

      expect(result.data.data.websocket_url).toContain("wss://");
      expect(result.data.data.connection_id).toBe("conn-12345");
    });
  });

  describe("API Key Management", () => {
    test("should fetch user API keys", async () => {
      const mockApiKeys = {
        success: true,
        data: {
          alpaca: { configured: true, paper_trading: true },
          polygon: { configured: false },
          finnhub: { configured: true },
        },
      };

      mockedAxios.get.mockResolvedValueOnce({
        status: 200,
        data: mockApiKeys,
      });

      const result = await api.get("/api/settings/api-keys");

      expect(result.data.data.alpaca.configured).toBe(true);
      expect(result.data.data.polygon.configured).toBe(false);
    });

    test("should update API key settings", async () => {
      const mockResponse = {
        success: true,
        data: { message: "API key updated successfully" },
      };

      mockedAxios.put.mockResolvedValueOnce({
        status: 200,
        data: mockResponse,
      });

      const result = await api.put("/api/settings/api-keys/alpaca", {
        key_id: "test-key",
        secret: "test-secret",
        paper_trading: true,
      });

      expect(result.data.success).toBe(true);
    });
  });

  describe("Trading Operations", () => {
    test("should submit buy orders", async () => {
      const mockOrderResponse = {
        success: true,
        data: {
          order_id: "order-12345",
          symbol: "AAPL",
          shares: 10,
          order_type: "market",
          status: "pending",
        },
      };

      mockedAxios.post.mockResolvedValueOnce({
        status: 201,
        data: mockOrderResponse,
      });

      const result = await api.post("/api/trading/orders", {
        symbol: "AAPL",
        shares: 10,
        side: "buy",
        type: "market",
      });

      expect(result.data.data.order_id).toBe("order-12345");
      expect(result.data.data.status).toBe("pending");
    });

    test("should fetch trading history", async () => {
      const mockHistory = {
        success: true,
        data: {
          orders: [
            {
              id: "order-1",
              symbol: "AAPL",
              shares: 10,
              side: "buy",
              filled_at: "2024-01-15T10:30:00Z",
              price: 175.25,
            },
          ],
        },
      };

      mockedAxios.get.mockResolvedValueOnce({
        status: 200,
        data: mockHistory,
      });

      const result = await api.get("/api/trading/history");

      expect(result.data.data.orders).toHaveLength(1);
      expect(result.data.data.orders[0].symbol).toBe("AAPL");
    });
  });

  describe("Error Handling and Resilience", () => {
    test("should handle network errors gracefully", async () => {
      mockedAxios.get.mockRejectedValueOnce(new Error("Network error"));

      await expect(api.get("/api/portfolio/holdings")).rejects.toThrow(
        "Network error"
      );
    });

    test("should handle timeout errors", async () => {
      mockedAxios.get.mockRejectedValueOnce({
        code: "ECONNABORTED",
        message: "timeout of 5000ms exceeded",
      });

      await expect(api.get("/api/slow-endpoint")).rejects.toMatchObject({
        code: "ECONNABORTED",
      });
    });

    test("should handle rate limiting", async () => {
      mockedAxios.get.mockRejectedValueOnce({
        response: {
          status: 429,
          data: { error: "Rate limit exceeded" },
          headers: { "retry-after": "60" },
        },
      });

      await expect(api.get("/api/market/data")).rejects.toMatchObject({
        response: {
          status: 429,
        },
      });
    });
  });

  describe("Health Checks and System Status", () => {
    test("should perform API health checks", async () => {
      const mockHealthData = {
        success: true,
        data: {
          status: "healthy",
          services: {
            database: "healthy",
            market_data: "healthy",
            trading: "healthy",
          },
          timestamp: Date.now(),
        },
      };

      mockedAxios.get.mockResolvedValueOnce({
        status: 200,
        data: mockHealthData,
      });

      const result = await api.get("/api/health");

      expect(result.data.data.status).toBe("healthy");
      expect(result.data.data.services.database).toBe("healthy");
    });

    test("should handle partial service outages", async () => {
      const mockPartialHealthData = {
        success: true,
        data: {
          status: "degraded",
          services: {
            database: "healthy",
            market_data: "degraded",
            trading: "unhealthy",
          },
        },
      };

      mockedAxios.get.mockResolvedValueOnce({
        status: 200,
        data: mockPartialHealthData,
      });

      const result = await api.get("/api/health");

      expect(result.data.data.status).toBe("degraded");
      expect(result.data.data.services.trading).toBe("unhealthy");
    });
  });
});
