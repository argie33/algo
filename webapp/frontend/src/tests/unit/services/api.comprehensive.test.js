/**
 * API Service Comprehensive Tests
 * Tests all API endpoints, error handling, authentication, and data flow
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// Mock axios - create fresh mock functions each time with all necessary properties
vi.mock("axios", () => ({
  default: {
    create: () => ({
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
      defaults: {
        baseURL: "http://localhost:3001",
        timeout: 30000,
        headers: {
          "Content-Type": "application/json",
        },
      },
      interceptors: {
        request: {
          use: vi.fn(),
        },
        response: {
          use: vi.fn(),
        },
      },
    }),
  },
}));

// Mock fetch for functions that use fetch directly
global.fetch = vi.fn();

import axios from "axios";
import apiService, {
  initializeApi,
  testApiConnection,
  getApiConfig,
} from "../../../services/api.js";

// Get the mocked axios instance - this will be created by the API service
const mockAxiosInstance = axios.create();

// Use the default export which contains all API functions
const api = apiService;

// Mock console to reduce test noise
const originalConsoleError = console.error;
beforeEach(() => {
  console.error = vi.fn();
});

afterEach(() => {
  console.error = originalConsoleError;
});

describe("API Service Comprehensive Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetch.mockClear();
    mockAxiosInstance.get.mockClear();
    mockAxiosInstance.post.mockClear();
    mockAxiosInstance.put.mockClear();
    mockAxiosInstance.delete.mockClear();
  });

  describe("API Configuration", () => {
    it("should return correct API configuration", () => {
      const config = getApiConfig();

      expect(config).toHaveProperty("apiUrl");
      expect(config).toHaveProperty("environment");
      expect(typeof config.apiUrl).toBe("string");
      expect(typeof config.environment).toBe("string");
    });

    it("should initialize API with proper configuration", async () => {
      fetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ status: "healthy" }),
      });

      await initializeApi();

      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/health"),
        expect.objectContaining({
          method: "GET",
        })
      );
    });

    it("should test API connection successfully", async () => {
      fetch.mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            status: "healthy",
            timestamp: new Date().toISOString(),
          }),
      });

      const result = await testApiConnection();

      expect(result).toEqual({
        success: true,
        data: expect.objectContaining({ status: "healthy" }),
      });
    });

    it("should handle API connection failures", async () => {
      fetch.mockRejectedValue(new Error("Network error"));

      const result = await testApiConnection();

      expect(result).toEqual({
        success: false,
        error: expect.any(String),
      });
    });
  });

  describe("Portfolio Endpoints", () => {
    beforeEach(() => {
      // Mock authorization header
      global.localStorage = {
        getItem: vi.fn(() => "mock-jwt-token"),
        setItem: vi.fn(),
        removeItem: vi.fn(),
      };
    });

    it("should fetch portfolio data", async () => {
      const mockPortfolio = {
        totalValue: 125750.5,
        todaysPnL: 2500.75,
        positions: [
          { symbol: "AAPL", quantity: 100, currentPrice: 150.25 },
          { symbol: "MSFT", quantity: 50, currentPrice: 280.1 },
        ],
      };

      mockAxiosInstance.get.mockResolvedValue({
        data: mockPortfolio,
      });

      const result = await api.getPortfolio();

      expect(mockAxiosInstance.get).toHaveBeenCalledWith(
        "/api/portfolio/holdings"
      );
      expect(result).toEqual(mockPortfolio);
    });

    it("should place trade orders", async () => {
      const mockOrderResponse = {
        orderId: "order-123",
        status: "pending",
        symbol: "AAPL",
        quantity: 10,
        side: "buy",
        type: "market",
        timestamp: expect.any(String),
      };

      mockAxiosInstance.post.mockResolvedValue({
        data: { orderId: "order-123", status: "pending" },
      });

      const orderRequest = {
        symbol: "AAPL",
        quantity: 10,
        side: "buy",
        type: "market",
      };

      const result = await api.placeOrder(orderRequest);

      expect(mockAxiosInstance.post).toHaveBeenCalledWith(
        "/api/orders",
        orderRequest
      );
      expect(result).toEqual(mockOrderResponse);
    });
  });

  describe("Market Data Endpoints", () => {
    it("should fetch market overview", async () => {
      const mockMarketData = {
        indices: {
          SP500: { price: 4125.75, change: 25.5, changePercent: 0.62 },
          NASDAQ: { price: 13250.25, change: -15.75, changePercent: -0.12 },
          DOW: { price: 34125.5, change: 185.25, changePercent: 0.55 },
        },
        topGainers: [{ symbol: "NVDA", change: 15.25, changePercent: 8.5 }],
        topLosers: [{ symbol: "META", change: -12.5, changePercent: -4.1 }],
      };

      mockAxiosInstance.get.mockResolvedValue({
        data: mockMarketData,
      });

      const result = await api.getMarketOverview();

      expect(mockAxiosInstance.get).toHaveBeenCalledWith(
        "/api/market/overview"
      );
      expect(result).toEqual(mockMarketData);
    });

    it("should fetch stock quotes", async () => {
      const mockQuoteResponse = {
        price: 175.25,
        change: 2.5,
        changePercent: 1.45,
        volume: 45230000,
      };

      const expectedResult = {
        symbol: "AAPL",
        price: 175.25,
        change: 2.5,
        changePercent: 1.45,
        volume: 45230000,
        timestamp: expect.any(String),
      };

      mockAxiosInstance.get.mockResolvedValue({
        data: mockQuoteResponse,
      });

      const result = await api.getQuote("AAPL");

      expect(mockAxiosInstance.get).toHaveBeenCalledWith(
        "/api/market/quote/AAPL"
      );
      expect(result).toEqual(expectedResult);
    });
  });

  describe("Error Handling", () => {
    it("should handle network errors", async () => {
      mockAxiosInstance.get.mockRejectedValue(new Error("Network Error"));

      await expect(api.getPortfolio()).rejects.toThrow("Network Error");
    });

    it("should handle HTTP error responses", async () => {
      const axiosError = new Error("Request failed with status code 404");
      axiosError.response = {
        status: 404,
        statusText: "Not Found",
        data: { error: "Resource not found" },
      };
      mockAxiosInstance.get.mockRejectedValue(axiosError);

      await expect(api.getQuote("INVALID")).rejects.toThrow(
        "Failed to fetch quote for INVALID"
      );
    });

    it("should handle unauthorized responses", async () => {
      const axiosError = new Error("Request failed with status code 401");
      axiosError.response = {
        status: 401,
        statusText: "Unauthorized",
        data: { error: "Invalid token" },
      };
      mockAxiosInstance.get.mockRejectedValue(axiosError);

      await expect(api.getPortfolio()).rejects.toThrow();
    });
  });
});
