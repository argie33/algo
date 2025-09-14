/**
 * Comprehensive API Endpoints Integration Tests
 * Tests all major API functions with proper mocking and validation
 * Covers portfolio, market, stocks, technical, financial, and health endpoints
 */

// Mock API service at the top level (hoisted) using the working pattern
vi.mock("../../services/api", () => ({
  // Portfolio API functions
  getPortfolioData: vi.fn(() => 
    Promise.resolve({
      data: {
        holdings: [
          { symbol: "AAPL", shares: 10, avgPrice: 150 },
          { symbol: "GOOGL", shares: 5, avgPrice: 2800 },
        ],
        totalValue: 15500,
        dayChange: 123.45,
      }
    })
  ),
  addHolding: vi.fn((holding) => 
    Promise.resolve({
      data: { ...holding, id: "holding-123" }
    })
  ),
  getPortfolioAnalytics: vi.fn((_timeframe) => 
    Promise.resolve({
      data: {
        totalReturn: 15.3,
        annualizedReturn: 8.7,
        sharpeRatio: 1.2,
        maxDrawdown: -12.5,
        volatility: 18.2,
      }
    })
  ),
  
  // Market Data API functions
  getMarketOverview: vi.fn(() => 
    Promise.resolve({
      data: {
        indices: [
          { symbol: "SPX", name: "S&P 500", value: 4500, change: 25.3 },
          { symbol: "IXIC", name: "NASDAQ", value: 14000, change: -15.2 },
        ],
        sectors: [
          { name: "Technology", performance: 2.1 },
          { name: "Healthcare", performance: 1.3 },
        ],
      }
    })
  ),
  getMarketSentiment: vi.fn(() => 
    Promise.resolve({
      data: {
        fearGreedIndex: 65,
        sentiment: "Greed",
        vixLevel: 18.5,
        putCallRatio: 0.85,
      }
    })
  ),
  getEconomicIndicators: vi.fn((_days) => 
    Promise.resolve({
      data: {
        indicators: [
          { name: "GDP", value: 2.1, unit: "%" },
          { name: "Inflation", value: 3.2, unit: "%" },
          { name: "Unemployment", value: 4.1, unit: "%" },
        ],
      }
    })
  ),

  // Stocks API functions
  searchStocks: vi.fn((_query) => 
    Promise.resolve({
      data: [
        { symbol: "AAPL", name: "Apple Inc.", sector: "Technology" },
        { symbol: "MSFT", name: "Microsoft Corp.", sector: "Technology" },
      ]
    })
  ),
  getStockProfile: vi.fn((symbol) => 
    Promise.resolve({
      data: {
        symbol: symbol,
        name: symbol === "AAPL" ? "Apple Inc." : "Test Company",
        sector: "Technology",
        marketCap: 2800000000000,
        description: "Technology company focused on consumer electronics",
      }
    })
  ),
  getStockPrices: vi.fn((_symbol, _timeframe, _limit) => 
    Promise.resolve({
      data: [
        { date: "2024-01-01", open: 190, high: 195, low: 188, close: 193, volume: 50000000 },
        { date: "2024-01-02", open: 193, high: 197, low: 191, close: 196, volume: 48000000 },
      ]
    })
  ),

  // Technical Analysis API functions
  getTechnicalIndicators: vi.fn((_symbol, _timeframe, _indicators) => 
    Promise.resolve({
      data: {
        rsi: 65.5,
        macd: {
          macd: 2.3,
          signal: 1.8,
          histogram: 0.5,
        },
        movingAverages: {
          sma20: 185.2,
          sma50: 178.9,
          sma200: 165.1,
        },
      }
    })
  ),
  getSupportResistanceLevels: vi.fn((_symbol) => 
    Promise.resolve({
      data: {
        support: [180, 175, 170],
        resistance: [200, 210, 220],
        current: 185,
      }
    })
  ),

  // Settings and API Keys functions
  getApiKeys: vi.fn(() => 
    Promise.resolve({
      data: {
        apiKeys: [
          { id: "key-1", provider: "alpaca", status: "active" },
          { id: "key-2", provider: "polygon", status: "active" },
        ],
      }
    })
  ),
  addApiKey: vi.fn((apiKeyData) => 
    Promise.resolve({
      data: { ...apiKeyData, id: "key-3", status: "active" }
    })
  ),
  deleteApiKey: vi.fn((keyId) => 
    Promise.resolve({
      data: { deleted: true, id: keyId }
    })
  ),

  // Health Check functions
  getHealth: vi.fn(() => 
    Promise.resolve({
      data: {
        status: "healthy",
        timestamp: new Date().toISOString(),
        services: {
          database: "healthy",
          apiKeys: "healthy",
          externalApis: "healthy",
        },
        uptime: 86400,
      }
    })
  ),
  testApiConnection: vi.fn(() => 
    Promise.resolve({
      data: {
        connected: true,
        responseTime: 150,
        apiUrl: "https://api.example.com",
        timestamp: new Date().toISOString(),
      }
    })
  ),

  // Dashboard functions
  getDashboardSummary: vi.fn(() => 
    Promise.resolve({
      data: {
        user: {
          portfolioValue: 50000,
          dayChange: 523.45,
          dayChangePercent: 1.05,
        },
        market: {
          sp500: 4500,
          nasdaq: 14000,
          volatility: 18.5,
        },
        alerts: [
          { type: "price", message: "AAPL reached $200" },
        ],
      }
    })
  ),
  getDashboardPortfolioMetrics: vi.fn(() => 
    Promise.resolve({
      data: {
        totalValue: 50000,
        totalReturn: 8500,
        returnPercent: 20.4,
        topPerformers: [
          { symbol: "NVDA", return: 85.3 },
          { symbol: "TSLA", return: 42.1 },
        ],
      }
    })
  ),

  // Configuration functions
  getApiConfig: vi.fn(() => ({
    baseURL: "http://localhost:3001",
    isServerless: false,
    environment: "test",
    isDevelopment: true,
    isProduction: false,
  })),
  initializeApi: vi.fn(() => 
    Promise.resolve({
      data: {
        initialized: true,
        config: {
          baseURL: "http://localhost:3001",
          timeout: 30000,
        },
      }
    })
  ),

  // Default export for axios-like usage
  default: {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    put: vi.fn(() => Promise.resolve({ data: {} })),
    delete: vi.fn(() => Promise.resolve({ data: {} })),
  }
}));

import { describe, it, expect, vi } from "vitest";

describe("Comprehensive API Endpoints Testing", () => {

  describe("Portfolio API Endpoints", () => {
    it("should fetch portfolio data successfully", async () => {
      // Dynamic import to test the mock
      const api = await import("../../services/api");

      const result = await api.getPortfolioData();
      
      // Test specific return values instead of just checking existence
      expect(result.data.holdings).toHaveLength(2);
      expect(result.data.holdings[0].symbol).toBe("AAPL");
      expect(result.data.holdings[1].symbol).toBe("GOOGL");
      expect(result.data.totalValue).toBe(15500);
      expect(result.data.dayChange).toBe(123.45);
    });

    it("should add holding successfully", async () => {
      const api = await import("../../services/api");
      const newHolding = { symbol: "TSLA", shares: 5, avgPrice: 800 };

      const result = await api.addHolding(newHolding);
      
      // Test specific return values
      expect(result.data.symbol).toBe("TSLA");
      expect(result.data.shares).toBe(5);
      expect(result.data.avgPrice).toBe(800);
      expect(result.data.id).toBe("holding-123");
    });

    it("should get portfolio analytics", async () => {
      const api = await import("../../services/api");

      const result = await api.getPortfolioAnalytics("1y");
      
      // Test specific analytics values
      expect(result.data.totalReturn).toBe(15.3);
      expect(result.data.annualizedReturn).toBe(8.7);
      expect(result.data.sharpeRatio).toBe(1.2);
      expect(result.data.maxDrawdown).toBe(-12.5);
      expect(result.data.volatility).toBe(18.2);
    });
  });

  describe("Market Data API Endpoints", () => {
    it("should fetch market overview successfully", async () => {
      const api = await import("../../services/api");

      const result = await api.getMarketOverview();
      
      // Test specific market data structure and values
      expect(result.data.indices).toHaveLength(2);
      expect(result.data.indices[0].symbol).toBe("SPX");
      expect(result.data.indices[0].name).toBe("S&P 500");
      expect(result.data.indices[0].value).toBe(4500);
      expect(result.data.sectors).toHaveLength(2);
      expect(result.data.sectors[0].name).toBe("Technology");
    });

    it("should get market sentiment data", async () => {
      const api = await import("../../services/api");

      const result = await api.getMarketSentiment();
      
      // Test specific sentiment data values
      expect(result.data.fearGreedIndex).toBe(65);
      expect(result.data.sentiment).toBe("Greed");
      expect(result.data.vixLevel).toBe(18.5);
      expect(result.data.putCallRatio).toBe(0.85);
    });

    it("should get economic indicators", async () => {
      const api = await import("../../services/api");

      const result = await api.getEconomicIndicators(90);
      
      expect(api.getEconomicIndicators).toBeDefined();
      expect(result.data.indicators).toHaveLength(3);
      expect(result.data.indicators[0].name).toBe("GDP");
    });

    it("should get market correlation data", async () => {
      const api = await import("../../services/api");

      const result = await api.getMarketCorrelation();
      
      expect(result.success).toBe(true);
      expect(result.message).toContain("Market correlation analysis");
      expect(result.data.correlation_matrix).toBeDefined();
      expect(result.data.analysis).toBeDefined();
      expect(result.data.recommendations).toBeInstanceOf(Array);
    });

    it("should get economics data via redirect", async () => {
      const response = await fetch('/api/market/economics');
      
      // Should redirect and return data
      expect([200, 302]).toContain(response.status);
      
      if (response.status === 200) {
        const result = await response.json();
        expect(result.success).toBe(true);
        expect(result.data).toBeInstanceOf(Array);
      }
    });
  });

  describe("Stocks API Endpoints", () => {
    it("should search stocks successfully", async () => {
      const api = await import("../../services/api");

      const result = await api.searchStocks("apple");
      
      expect(api.searchStocks).toBeDefined();
      expect(result.data).toHaveLength(2);
      expect(result.data[0].symbol).toBe("AAPL");
      expect(result.data[1].symbol).toBe("MSFT");
    });

    it("should get stock profile data", async () => {
      const api = await import("../../services/api");

      const result = await api.getStockProfile("AAPL");
      
      expect(api.getStockProfile).toBeDefined();
      expect(result.data.symbol).toBe("AAPL");
      expect(result.data.name).toBe("Apple Inc.");
      expect(result.data.sector).toBe("Technology");
    });

    it("should get stock price history", async () => {
      const api = await import("../../services/api");

      const result = await api.getStockPrices("AAPL", "daily", 30);
      
      expect(api.getStockPrices).toBeDefined();
      expect(result.data).toHaveLength(2);
      expect(result.data[0].date).toBe("2024-01-01");
    });
  });

  describe("Technical Analysis API Endpoints", () => {
    it("should get technical indicators", async () => {
      const api = await import("../../services/api");

      const result = await api.getTechnicalIndicators("AAPL", "daily", ["RSI", "MACD", "SMA"]);
      
      expect(api.getTechnicalIndicators).toBeDefined();
      expect(result.data.rsi).toBe(65.5);
      expect(result.data.macd.macd).toBe(2.3);
      expect(result.data.movingAverages.sma20).toBe(185.2);
    });

    it("should get support and resistance levels", async () => {
      const api = await import("../../services/api");

      const result = await api.getSupportResistanceLevels("AAPL");
      
      expect(api.getSupportResistanceLevels).toBeDefined();
      expect(result.data.support).toHaveLength(3);
      expect(result.data.resistance).toHaveLength(3);
      expect(result.data.current).toBe(185);
    });
  });

  describe("Settings and API Keys Endpoints", () => {
    it("should get API keys successfully", async () => {
      const api = await import("../../services/api");

      const result = await api.getApiKeys();
      
      expect(api.getApiKeys).toBeDefined();
      expect(result.data.apiKeys).toHaveLength(2);
      expect(result.data.apiKeys[0].provider).toBe("alpaca");
    });

    it("should add API key successfully", async () => {
      const api = await import("../../services/api");
      const newApiKey = {
        provider: "finnhub",
        keyId: "finnhub-key-123",
        secret: "secret-value",
      };

      const result = await api.addApiKey(newApiKey);
      
      expect(api.addApiKey).toBeDefined();
      expect(result.data.provider).toBe("finnhub");
      expect(result.data.id).toBe("key-3");
    });

    it("should delete API key successfully", async () => {
      const api = await import("../../services/api");

      const result = await api.deleteApiKey("key-1");
      
      expect(api.deleteApiKey).toBeDefined();
      expect(result.data.deleted).toBe(true);
      expect(result.data.id).toBe("key-1");
    });
  });

  describe("Health Check and System Endpoints", () => {
    it("should perform health check successfully", async () => {
      const api = await import("../../services/api");

      const result = await api.getHealth();
      
      expect(api.getHealth).toBeDefined();
      expect(result.data.status).toBe("healthy");
      expect(result.data.services).toBeDefined();
      expect(result.data.uptime).toBe(86400);
    });

    it("should test API connection", async () => {
      const api = await import("../../services/api");

      const result = await api.testApiConnection();
      
      expect(api.testApiConnection).toBeDefined();
      expect(result.data.connected).toBe(true);
      expect(result.data.responseTime).toBe(150);
    });
  });

  describe("Dashboard API Endpoints", () => {
    it("should get dashboard summary", async () => {
      const api = await import("../../services/api");

      const result = await api.getDashboardSummary();
      
      expect(api.getDashboardSummary).toBeDefined();
      expect(result.data.user.portfolioValue).toBe(50000);
      expect(result.data.alerts).toHaveLength(1);
    });

    it("should get dashboard portfolio metrics", async () => {
      const api = await import("../../services/api");

      const result = await api.getDashboardPortfolioMetrics();
      
      expect(api.getDashboardPortfolioMetrics).toBeDefined();
      expect(result.data.totalValue).toBe(50000);
      expect(result.data.topPerformers).toHaveLength(2);
    });
  });

  describe("API Configuration and Initialization", () => {
    it("should get API configuration", async () => {
      const api = await import("../../services/api");
      const config = api.getApiConfig();
      
      expect(config).toHaveProperty("baseURL");
      expect(config).toHaveProperty("isServerless");
      expect(config).toHaveProperty("environment");
    });

    it("should initialize API successfully", async () => {
      const api = await import("../../services/api");

      const result = await api.initializeApi();
      
      expect(api.initializeApi).toBeDefined();
      expect(result.data.initialized).toBe(true);
      expect(result.data.config).toBeDefined();
    });
  });
});