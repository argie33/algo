const realTimeDataService = require("../../utils/realTimeDataService");

// Mock dependencies
jest.mock("../../utils/alpacaService");
jest.mock("../../utils/apiKeyService");

const AlpacaService = require("../../utils/alpacaService");
const apiKeyService = require("../../utils/apiKeyService");

describe("RealTimeDataService", () => {
  let realTimeService;
  let mockAlpacaService;
  const testUserId = "test-user-123";

  beforeEach(() => {
    jest.clearAllMocks();

    mockAlpacaService = {
      getBars: jest.fn(),
      getLatestQuote: jest.fn(),
      getMarketStatus: jest.fn(),
    };

    AlpacaService.mockImplementation(() => mockAlpacaService);
    apiKeyService.getDecryptedApiKey = jest.fn();

    realTimeService = realTimeDataService;

    // Clear cache before each test
    realTimeService.clearCache();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe("constructor", () => {
    test("should initialize with default settings", () => {
      expect(realTimeService.cacheTimeout).toBe(30000);
      expect(realTimeService.rateLimitDelay).toBe(1000);
      expect(realTimeService.watchedSymbols.has("AAPL")).toBe(true);
      expect(realTimeService.indexSymbols.has("SPY")).toBe(true);
      expect(realTimeService.cache).toBeInstanceOf(Map);
    });

    test("should initialize with common symbols", () => {
      const expectedSymbols = [
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "TSLA",
        "NVDA",
        "META",
      ];
      expectedSymbols.forEach((symbol) => {
        expect(realTimeService.watchedSymbols.has(symbol)).toBe(true);
      });
    });
  });

  describe("rateLimit", () => {
    test("should not delay if enough time has passed", async () => {
      realTimeService.lastRequestTime = Date.now() - 2000; // 2 seconds ago
      
      const start = Date.now();
      await realTimeService.rateLimit();
      const end = Date.now();

      expect(end - start).toBeLessThan(100); // Should be immediate
    });

    test("should update last request time", async () => {
      const initialTime = realTimeService.lastRequestTime;
      await realTimeService.rateLimit();
      expect(realTimeService.lastRequestTime).toBeGreaterThan(initialTime);
    });
  });

  describe("getCachedOrFetch", () => {
    test("should return cached data if not expired", async () => {
      const cacheKey = "test-key";
      const cachedValue = "cached";
      const fetchFunction = jest.fn().mockResolvedValue("fresh");

      // Manually set cache entry
      realTimeService.cache.set(cacheKey, {
        data: cachedValue,
        timestamp: Date.now(),
      });

      const result = await realTimeService.getCachedOrFetch(
        cacheKey,
        fetchFunction
      );

      expect(result).toBe(cachedValue);
      expect(fetchFunction).not.toHaveBeenCalled();
    });

    test("should fetch fresh data if cache expired", async () => {
      const cacheKey = "test-key";
      const freshValue = "fresh";
      const fetchFunction = jest.fn().mockResolvedValue(freshValue);

      // Set expired cache entry
      realTimeService.cache.set(cacheKey, {
        data: "old",
        timestamp: Date.now() - 60000, // 1 minute ago
      });

      const result = await realTimeService.getCachedOrFetch(
        cacheKey,
        fetchFunction,
        30000 // 30 second TTL
      );

      expect(result).toBe(freshValue);
      expect(fetchFunction).toHaveBeenCalled();
    });

    test("should cache the fetched data", async () => {
      const cacheKey = "test-key";
      const fetchFunction = jest.fn().mockResolvedValue("fresh");

      await realTimeService.getCachedOrFetch(cacheKey, fetchFunction);

      const cachedEntry = realTimeService.cache.get(cacheKey);
      expect(cachedEntry.data).toBe("fresh");
      expect(cachedEntry.timestamp).toBeGreaterThan(Date.now() - 5000); // Allow 5 second tolerance
    });
  });

  describe("getLiveMarketData", () => {
    const mockQuoteData = {
      symbol: "AAPL",
      price: 150.0,
      change: 2.5,
      changePercent: 1.67,
    };

    test("should get live market data for symbols", async () => {
      apiKeyService.getDecryptedApiKey.mockResolvedValue({
        apiKey: "test-key",
        apiSecret: "test-secret",
        isSandbox: false,
      });
      mockAlpacaService.getLatestQuote.mockResolvedValue(mockQuoteData);

      const result = await realTimeService.getLiveMarketData(testUserId, ["AAPL"]);

      expect(result).toBeDefined();
      expect(result).toHaveProperty("data");
      expect(result).toHaveProperty("metadata");
      expect(typeof result.data).toBe("object");
    });

    test("should handle API key service errors", async () => {
      apiKeyService.getDecryptedApiKey.mockRejectedValue(new Error("No API keys"));

      await expect(
        realTimeService.getLiveMarketData(testUserId, ["AAPL"])
      ).rejects.toThrow("No API keys");
    });
  });

  describe("getMarketIndices", () => {
    test("should get market indices data", async () => {
      apiKeyService.getDecryptedApiKey.mockResolvedValue({
        apiKey: "test-key",
        apiSecret: "test-secret",
        isSandbox: false,
      });

      // Mock successful responses
      mockAlpacaService.getLatestQuote.mockResolvedValue({
        symbol: "SPY",
        price: 450.0,
        change: 2.5,
        changePercent: 0.56,
      });

      const result = await realTimeService.getMarketIndices(testUserId);

      expect(result).toBeDefined();
      expect(typeof result).toBe("object");
    });

    test("should handle missing user ID", async () => {
      await expect(realTimeService.getMarketIndices()).rejects.toThrow(
        "User ID is required"
      );
    });
  });

  describe("clearCache", () => {
    test("should clear all cached data", () => {
      realTimeService.cache.set("test", { data: "data", timestamp: Date.now() });
      expect(realTimeService.cache.size).toBeGreaterThan(0);

      realTimeService.clearCache();

      expect(realTimeService.cache.size).toBe(0);
    });
  });

  describe("getCacheStats", () => {
    test("should return cache statistics", () => {
      const stats = realTimeService.getCacheStats();

      expect(stats).toHaveProperty("totalEntries");
      expect(stats).toHaveProperty("freshEntries");
      expect(stats).toHaveProperty("staleEntries");
      expect(stats).toHaveProperty("cacheTimeout");
      expect(typeof stats.totalEntries).toBe("number");
    });
  });

  describe("calculatePriceChange", () => {
    test("should calculate price change correctly", () => {
      const result = realTimeService.calculatePriceChange(105, 100);

      expect(result).toEqual({
        change: 5,
        changePercent: 5,
      });
    });

    test("should handle negative price change", () => {
      const result = realTimeService.calculatePriceChange(95, 100);

      expect(result).toEqual({
        change: -5,
        changePercent: -5,
      });
    });

    test("should handle zero price change", () => {
      const result = realTimeService.calculatePriceChange(100, 100);

      expect(result).toEqual({
        change: 0,
        changePercent: 0,
      });
    });
  });
});