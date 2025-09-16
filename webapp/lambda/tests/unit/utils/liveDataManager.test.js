const LiveDataManager = require("../../../utils/liveDataManager");
const { query } = require("../../../utils/database");

jest.mock("../../../utils/database");

describe("Live Data Manager", () => {
  let liveDataManager;

  beforeEach(() => {
    liveDataManager = new LiveDataManager();
    jest.clearAllMocks();
  });

  describe("data provider management", () => {
    test("should initialize with default providers", () => {
      expect(liveDataManager.providers).toBeDefined();
      expect(liveDataManager.providers.length).toBeGreaterThan(0);
    });

    test("should add new data provider", () => {
      const provider = {
        name: "testProvider",
        endpoint: "https://api.test.com",
        apiKey: "test-key",
        rateLimit: 100,
      };

      const result = liveDataManager.addProvider(provider);
      expect(result.success).toBe(true);
      expect(
        liveDataManager.providers.some((p) => p.name === "testProvider")
      ).toBe(true);
    });

    test("should validate provider configuration", () => {
      const invalidProvider = {
        name: "",
        endpoint: "invalid-url",
      };

      const result = liveDataManager.validateProvider(invalidProvider);
      expect(result.valid).toBe(false);
      expect(result.errors).toBeDefined();
    });

    test("should get provider status", async () => {
      const result = await liveDataManager.getProviderStatus("alpaca");

      expect(result).toHaveProperty("status");
      expect(result).toHaveProperty("lastUpdate");
      expect(result).toHaveProperty("health");
    });
  });

  describe("real-time data streaming", () => {
    test("should start data stream for symbol", async () => {
      const mockCallback = jest.fn();

      const result = await liveDataManager.startStream("AAPL", mockCallback);

      expect(result.success).toBe(true);
      expect(result.streamId).toBeDefined();
    });

    test("should stop data stream", async () => {
      const mockCallback = jest.fn();
      const stream = await liveDataManager.startStream("AAPL", mockCallback);

      const result = await liveDataManager.stopStream(stream.streamId);

      expect(result.success).toBe(true);
    });

    test("should handle multiple symbol streams", async () => {
      const symbols = ["AAPL", "GOOGL", "TSLA"];
      const mockCallback = jest.fn();

      const results = await Promise.all(
        symbols.map((symbol) =>
          liveDataManager.startStream(symbol, mockCallback)
        )
      );

      expect(results.every((r) => r.success)).toBe(true);
      expect(new Set(results.map((r) => r.streamId)).size).toBe(3);
    });

    test("should process incoming market data", () => {
      const marketData = {
        symbol: "AAPL",
        price: 150.25,
        volume: 1000000,
        timestamp: Date.now(),
      };

      const result = liveDataManager.processMarketData(marketData);

      expect(result.success).toBe(true);
      expect(result.processed).toBeDefined();
    });
  });

  describe("data caching and storage", () => {
    test("should cache market data", () => {
      const data = {
        symbol: "AAPL",
        price: 150.25,
        timestamp: Date.now(),
      };

      liveDataManager.cacheData("AAPL", data);
      const cached = liveDataManager.getCachedData("AAPL");

      expect(cached).toMatchObject(data);
    });

    test("should handle cache expiration", () => {
      const data = {
        symbol: "AAPL",
        price: 150.25,
        timestamp: Date.now() - 600000, // 10 minutes ago
      };

      liveDataManager.cacheData("AAPL", data);
      const cached = liveDataManager.getCachedData("AAPL");

      expect(cached).toBeNull();
    });

    test("should store data to database", async () => {
      const data = {
        symbol: "AAPL",
        price: 150.25,
        volume: 1000000,
        timestamp: Date.now(),
      };

      query.mockResolvedValue({ rowCount: 1 });

      const result = await liveDataManager.storeData(data);

      expect(result.success).toBe(true);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("INSERT INTO live_data"),
        expect.arrayContaining([data.symbol, data.price, data.volume])
      );
    });
  });

  describe("rate limiting and throttling", () => {
    test("should enforce rate limits", async () => {
      liveDataManager.setRateLimit("testProvider", 2); // 2 requests per second

      const requests = Array.from({ length: 5 }, () =>
        liveDataManager.makeRequest("testProvider", "/quote/AAPL")
      );

      const results = await Promise.all(requests);
      const rateLimited = results.filter((r) => r.rateLimited);

      expect(rateLimited.length).toBeGreaterThan(0);
    });

    test("should reset rate limit counters", () => {
      liveDataManager.setRateLimit("testProvider", 1);
      liveDataManager.makeRequest("testProvider", "/test");

      liveDataManager.resetRateLimit("testProvider");
      const result = liveDataManager.makeRequest("testProvider", "/test");

      expect(result.rateLimited).toBe(false);
    });

    test("should get rate limit status", () => {
      const status = liveDataManager.getRateLimitStatus("alpaca");

      expect(status).toHaveProperty("remaining");
      expect(status).toHaveProperty("resetTime");
      expect(status).toHaveProperty("limit");
    });
  });

  describe("data quality and validation", () => {
    test("should validate market data format", () => {
      const validData = {
        symbol: "AAPL",
        price: 150.25,
        volume: 1000000,
        timestamp: Date.now(),
      };

      const result = liveDataManager.validateData(validData);
      expect(result.valid).toBe(true);
    });

    test("should reject invalid market data", () => {
      const invalidData = {
        symbol: "",
        price: "invalid",
        volume: -1000,
      };

      const result = liveDataManager.validateData(invalidData);
      expect(result.valid).toBe(false);
      expect(result.errors).toBeDefined();
    });

    test("should detect stale data", () => {
      const staleData = {
        symbol: "AAPL",
        price: 150.25,
        timestamp: Date.now() - 3600000, // 1 hour ago
      };

      const result = liveDataManager.isDataStale(staleData);
      expect(result).toBe(true);
    });

    test("should calculate data freshness", () => {
      const data = {
        timestamp: Date.now() - 60000, // 1 minute ago
      };

      const freshness = liveDataManager.calculateFreshness(data);
      expect(freshness).toBeCloseTo(60, -1); // approximately 60 seconds
    });
  });

  describe("subscription management", () => {
    test("should manage symbol subscriptions", () => {
      liveDataManager.subscribe("AAPL");
      liveDataManager.subscribe("GOOGL");

      const subscriptions = liveDataManager.getSubscriptions();
      expect(subscriptions).toContain("AAPL");
      expect(subscriptions).toContain("GOOGL");
    });

    test("should unsubscribe from symbols", () => {
      liveDataManager.subscribe("AAPL");
      liveDataManager.unsubscribe("AAPL");

      const subscriptions = liveDataManager.getSubscriptions();
      expect(subscriptions).not.toContain("AAPL");
    });

    test("should get subscription statistics", () => {
      liveDataManager.subscribe("AAPL");
      liveDataManager.subscribe("GOOGL");
      liveDataManager.subscribe("TSLA");

      const stats = liveDataManager.getSubscriptionStats();
      expect(stats.total).toBe(3);
      expect(stats.active).toBeDefined();
    });
  });

  describe("error handling and recovery", () => {
    test("should handle provider connection errors", async () => {
      const result = await liveDataManager.testConnection("invalidProvider");

      expect(result.success).toBe(false);
      expect(result.error).toBeDefined();
    });

    test("should implement retry logic for failed requests", async () => {
      const mockRetryCallback = jest
        .fn()
        .mockRejectedValueOnce(new Error("Network error"))
        .mockRejectedValueOnce(new Error("Network error"))
        .mockResolvedValue({ success: true });

      const result = await liveDataManager.retryRequest(mockRetryCallback, 3);

      expect(result.success).toBe(true);
      expect(mockRetryCallback).toHaveBeenCalledTimes(3);
    });

    test("should handle websocket disconnections", () => {
      const mockWs = { readyState: 3 }; // CLOSED

      const result = liveDataManager.handleWebSocketError(
        mockWs,
        new Error("Connection lost")
      );

      expect(result.reconnecting).toBe(true);
      expect(result.strategy).toBeDefined();
    });

    test("should implement circuit breaker pattern", async () => {
      // Simulate multiple failures to trigger circuit breaker
      for (let i = 0; i < 10; i++) {
        await liveDataManager
          .makeRequest("failingProvider", "/test")
          .catch(() => {});
      }

      const result = await liveDataManager.makeRequest(
        "failingProvider",
        "/test"
      );

      expect(result.circuitOpen).toBe(true);
      expect(result.error).toContain("Circuit breaker");
    });
  });

  describe("performance monitoring", () => {
    test("should track request latency", async () => {
      const start = Date.now();
      await liveDataManager.makeRequest("testProvider", "/quote/AAPL");

      const metrics = liveDataManager.getPerformanceMetrics();
      expect(metrics.averageLatency).toBeDefined();
      expect(metrics.requestCount).toBeGreaterThan(0);
    });

    test("should monitor data throughput", () => {
      for (let i = 0; i < 10; i++) {
        liveDataManager.processMarketData({
          symbol: "AAPL",
          price: 150 + i,
          timestamp: Date.now(),
        });
      }

      const throughput = liveDataManager.getThroughputMetrics();
      expect(throughput.messagesPerSecond).toBeGreaterThan(0);
    });

    test("should generate performance report", () => {
      const report = liveDataManager.generatePerformanceReport();

      expect(report).toHaveProperty("uptime");
      expect(report).toHaveProperty("dataPoints");
      expect(report).toHaveProperty("errorRate");
      expect(report).toHaveProperty("latencyStats");
    });
  });
});
