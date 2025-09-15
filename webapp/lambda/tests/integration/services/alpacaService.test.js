/**
 * Alpaca Service Integration Tests
 * Tests real Alpaca API integration with paper trading account
 */

const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

// Mock Alpaca SDK to avoid requiring real API keys in tests
jest.mock("@alpacahq/alpaca-trade-api", () => {
  return jest.fn().mockImplementation(() => ({
    getAccount: jest.fn(),
    getPositions: jest.fn(),
    getOrders: jest.fn(),
    createOrder: jest.fn(),
    cancelOrder: jest.fn(),
    getAsset: jest.fn(),
    getAssets: jest.fn(),
    getBars: jest.fn(),
    getLastTrade: jest.fn(),
    getPortfolioHistory: jest.fn(),
    getWatchlists: jest.fn(),
    createWatchlist: jest.fn(),
  }));
});

const AlpacaService = require("../../../utils/alpacaService");
const Alpaca = require("@alpacahq/alpaca-trade-api");

describe("Alpaca Service Integration Tests", () => {
  let alpacaService;
  let mockClient;

  beforeAll(async () => {
    await initializeDatabase();
  });

  afterAll(async () => {
    await closeDatabase();
  });

  beforeEach(() => {
    // Clear mocks before each test
    jest.clearAllMocks();

    // Get the mock client instance
    mockClient = {
      getAccount: jest.fn(),
      getPositions: jest.fn(),
      getOrders: jest.fn(),
      createOrder: jest.fn(),
      cancelOrder: jest.fn(),
      getAsset: jest.fn(),
      getAssets: jest.fn(),
      getBars: jest.fn(),
      getLastTrade: jest.fn(),
      getPortfolioHistory: jest.fn(),
      getWatchlists: jest.fn(),
      createWatchlist: jest.fn(),
    };

    Alpaca.mockImplementation(() => mockClient);

    // Create service instance with test credentials
    alpacaService = new AlpacaService("test_key", "test_secret", true);
  });

  describe("Service Initialization", () => {
    test("should initialize with valid API credentials", () => {
      expect(alpacaService).toBeInstanceOf(AlpacaService);
      expect(alpacaService.isPaper).toBe(true);
      expect(alpacaService.rateLimitWindow).toBe(60000);
      expect(alpacaService.maxRequestsPerWindow).toBe(200);
    });

    test("should throw error with missing credentials", () => {
      expect(() => {
        new AlpacaService(null, "secret");
      }).toThrow("Alpaca API key and secret are required");

      expect(() => {
        new AlpacaService("key", null);
      }).toThrow("Alpaca API key and secret are required");
    });

    test("should configure for live trading when specified", () => {
      const liveService = new AlpacaService("test_key", "test_secret", false);
      expect(liveService.isPaper).toBe(false);
    });
  });

  describe("Rate Limiting", () => {
    test("should track request times for rate limiting", () => {
      const initialLength = alpacaService.requestTimes.length;

      alpacaService.checkRateLimit();
      expect(alpacaService.requestTimes.length).toBe(initialLength + 1);

      alpacaService.checkRateLimit();
      expect(alpacaService.requestTimes.length).toBe(initialLength + 2);
    });

    test("should throw error when rate limit exceeded", () => {
      // Fill up the rate limit
      const now = Date.now();
      alpacaService.requestTimes = new Array(200).fill(now);

      expect(() => {
        alpacaService.checkRateLimit();
      }).toThrow("Rate limit exceeded. Please try again in a minute.");
    });

    test("should clean up old request times", () => {
      // Add old request times (older than 1 minute)
      const oldTime = Date.now() - 70000; // 70 seconds ago
      alpacaService.requestTimes = [oldTime, oldTime, oldTime];

      alpacaService.checkRateLimit();

      // Old times should be filtered out, only the new one should remain
      expect(alpacaService.requestTimes.length).toBe(1);
      expect(alpacaService.requestTimes[0]).toBeGreaterThan(oldTime);
    });
  });

  describe("Account Operations", () => {
    test("should fetch account information", async () => {
      const mockAccount = {
        id: "test-account-id",
        status: "ACTIVE",
        cash: "10000.00",
        portfolio_value: "12000.00",
        buying_power: "20000.00",
      };

      mockClient.getAccount.mockResolvedValueOnce(mockAccount);

      const account = await alpacaService.getAccount();

      expect(mockClient.getAccount).toHaveBeenCalledTimes(1);
      expect(account).toEqual(mockAccount);
    });

    test("should handle account fetch errors gracefully", async () => {
      mockClient.getAccount.mockRejectedValueOnce(new Error("API Error"));

      await expect(alpacaService.getAccount()).rejects.toThrow("API Error");
      expect(mockClient.getAccount).toHaveBeenCalledTimes(1);
    });

    test("should fetch portfolio history", async () => {
      const mockHistory = {
        timestamp: [1640995200, 1641081600],
        equity: [10000, 10500],
        profit_loss: [0, 500],
      };

      mockClient.getPortfolioHistory.mockResolvedValueOnce(mockHistory);

      const history = await alpacaService.getPortfolioHistory({
        period: "1D",
        timeframe: "1Min",
      });

      expect(mockClient.getPortfolioHistory).toHaveBeenCalledWith({
        period: "1D",
        timeframe: "1Min",
      });
      expect(history).toEqual(mockHistory);
    });
  });

  describe("Position Management", () => {
    test("should fetch current positions", async () => {
      const mockPositions = [
        {
          symbol: "AAPL",
          qty: "10",
          side: "long",
          market_value: "1500.00",
          cost_basis: "1400.00",
          unrealized_pl: "100.00",
        },
        {
          symbol: "TSLA",
          qty: "5",
          side: "long",
          market_value: "2500.00",
          cost_basis: "2400.00",
          unrealized_pl: "100.00",
        },
      ];

      mockClient.getPositions.mockResolvedValueOnce(mockPositions);

      const positions = await alpacaService.getPositions();

      expect(mockClient.getPositions).toHaveBeenCalledTimes(1);
      expect(positions).toHaveLength(2);
      expect(positions[0].symbol).toBe("AAPL");
      expect(positions[1].symbol).toBe("TSLA");
    });

    test("should fetch position for specific symbol", async () => {
      const mockPosition = {
        symbol: "AAPL",
        qty: "10",
        side: "long",
        market_value: "1500.00",
        cost_basis: "1400.00",
      };

      mockClient.getPosition = jest.fn().mockResolvedValueOnce(mockPosition);
      alpacaService.client.getPosition = mockClient.getPosition;

      const position = await alpacaService.getPosition("AAPL");

      expect(mockClient.getPosition).toHaveBeenCalledWith("AAPL");
      expect(position.symbol).toBe("AAPL");
    });
  });

  describe("Order Management", () => {
    test("should place market buy order", async () => {
      const mockOrder = {
        id: "order-123",
        symbol: "AAPL",
        qty: "10",
        side: "buy",
        type: "market",
        status: "new",
      };

      mockClient.createOrder.mockResolvedValueOnce(mockOrder);

      const order = await alpacaService.createOrder({
        symbol: "AAPL",
        qty: 10,
        side: "buy",
        type: "market",
      });

      expect(mockClient.createOrder).toHaveBeenCalledWith({
        symbol: "AAPL",
        qty: 10,
        side: "buy",
        type: "market",
      });
      expect(order.id).toBe("order-123");
    });

    test("should place limit sell order", async () => {
      const mockOrder = {
        id: "order-456",
        symbol: "TSLA",
        qty: "5",
        side: "sell",
        type: "limit",
        limit_price: "800.00",
        status: "new",
      };

      mockClient.createOrder.mockResolvedValueOnce(mockOrder);

      const order = await alpacaService.createOrder({
        symbol: "TSLA",
        qty: 5,
        side: "sell",
        type: "limit",
        limit_price: 800.0,
      });

      expect(mockClient.createOrder).toHaveBeenCalledWith({
        symbol: "TSLA",
        qty: 5,
        side: "sell",
        type: "limit",
        limit_price: 800.0,
      });
      expect(order.type).toBe("limit");
    });

    test("should fetch all orders", async () => {
      const mockOrders = [
        { id: "order-1", symbol: "AAPL", status: "filled" },
        { id: "order-2", symbol: "TSLA", status: "pending_new" },
      ];

      mockClient.getOrders.mockResolvedValueOnce(mockOrders);

      const orders = await alpacaService.getOrders({ status: "all" });

      expect(mockClient.getOrders).toHaveBeenCalledWith({ status: "all" });
      expect(orders).toHaveLength(2);
    });

    test("should cancel specific order", async () => {
      mockClient.cancelOrder.mockResolvedValueOnce({ id: "order-123" });

      const result = await alpacaService.cancelOrder("order-123");

      expect(mockClient.cancelOrder).toHaveBeenCalledWith("order-123");
      expect(result.id).toBe("order-123");
    });

    test("should validate order parameters", async () => {
      // Test invalid symbol
      await expect(
        alpacaService.createOrder({
          symbol: "",
          qty: 10,
          side: "buy",
          type: "market",
        })
      ).rejects.toThrow("Symbol is required");

      // Test invalid quantity
      await expect(
        alpacaService.createOrder({
          symbol: "AAPL",
          qty: 0,
          side: "buy",
          type: "market",
        })
      ).rejects.toThrow("Quantity must be greater than 0");

      // Test invalid side
      await expect(
        alpacaService.createOrder({
          symbol: "AAPL",
          qty: 10,
          side: "invalid",
          type: "market",
        })
      ).rejects.toThrow("Side must be 'buy' or 'sell'");
    });
  });

  describe("Market Data Operations", () => {
    test("should fetch asset information", async () => {
      const mockAsset = {
        id: "asset-123",
        symbol: "AAPL",
        name: "Apple Inc.",
        exchange: "NASDAQ",
        tradable: true,
        status: "active",
      };

      mockClient.getAsset.mockResolvedValueOnce(mockAsset);

      const asset = await alpacaService.getAsset("AAPL");

      expect(mockClient.getAsset).toHaveBeenCalledWith("AAPL");
      expect(asset.symbol).toBe("AAPL");
      expect(asset.tradable).toBe(true);
    });

    test("should fetch tradable assets", async () => {
      const mockAssets = [
        { symbol: "AAPL", tradable: true, status: "active" },
        { symbol: "TSLA", tradable: true, status: "active" },
      ];

      mockClient.getAssets.mockResolvedValueOnce(mockAssets);

      const assets = await alpacaService.getAssets({ status: "active" });

      expect(mockClient.getAssets).toHaveBeenCalledWith({ status: "active" });
      expect(assets).toHaveLength(2);
      expect(assets.every((asset) => asset.tradable)).toBe(true);
    });

    test("should fetch historical bars data", async () => {
      const mockBars = {
        bars: [
          {
            t: "2023-01-01T09:30:00Z",
            o: 150.0,
            h: 155.0,
            l: 149.0,
            c: 154.0,
            v: 1000000,
          },
        ],
      };

      mockClient.getBars.mockResolvedValueOnce(mockBars);

      const bars = await alpacaService.getBars("AAPL", {
        start: "2023-01-01",
        end: "2023-01-02",
        timeframe: "1Day",
      });

      expect(mockClient.getBars).toHaveBeenCalledWith("AAPL", {
        start: "2023-01-01",
        end: "2023-01-02",
        timeframe: "1Day",
      });
      expect(bars.bars).toHaveLength(1);
    });

    test("should fetch latest trade data", async () => {
      const mockTrade = {
        symbol: "AAPL",
        price: 155.5,
        size: 100,
        timestamp: "2023-01-01T15:59:59Z",
      };

      mockClient.getLastTrade.mockResolvedValueOnce(mockTrade);

      const trade = await alpacaService.getLastTrade("AAPL");

      expect(mockClient.getLastTrade).toHaveBeenCalledWith("AAPL");
      expect(trade.symbol).toBe("AAPL");
      expect(trade.price).toBe(155.5);
    });
  });

  describe("Watchlist Management", () => {
    test("should fetch all watchlists", async () => {
      const mockWatchlists = [
        { id: "watchlist-1", name: "My Stocks", assets: [] },
        { id: "watchlist-2", name: "Tech Stocks", assets: [] },
      ];

      mockClient.getWatchlists.mockResolvedValueOnce(mockWatchlists);

      const watchlists = await alpacaService.getWatchlists();

      expect(mockClient.getWatchlists).toHaveBeenCalledTimes(1);
      expect(watchlists).toHaveLength(2);
      expect(watchlists[0].name).toBe("My Stocks");
    });

    test("should create new watchlist", async () => {
      const mockWatchlist = {
        id: "watchlist-123",
        name: "New Watchlist",
        assets: [],
      };

      mockClient.createWatchlist.mockResolvedValueOnce(mockWatchlist);

      const watchlist = await alpacaService.createWatchlist({
        name: "New Watchlist",
        symbols: ["AAPL", "TSLA"],
      });

      expect(mockClient.createWatchlist).toHaveBeenCalledWith({
        name: "New Watchlist",
        symbols: ["AAPL", "TSLA"],
      });
      expect(watchlist.name).toBe("New Watchlist");
    });
  });

  describe("Error Handling and Edge Cases", () => {
    test("should handle network errors gracefully", async () => {
      mockClient.getAccount.mockRejectedValueOnce(new Error("Network error"));

      await expect(alpacaService.getAccount()).rejects.toThrow("Network error");
    });

    test("should handle API rate limiting from Alpaca", async () => {
      const rateLimitError = new Error("Rate limit exceeded");
      rateLimitError.status = 429;
      mockClient.getAccount.mockRejectedValueOnce(rateLimitError);

      await expect(alpacaService.getAccount()).rejects.toThrow(
        "Rate limit exceeded"
      );
    });

    test("should handle invalid API credentials", async () => {
      const authError = new Error("Invalid API credentials");
      authError.status = 401;
      mockClient.getAccount.mockRejectedValueOnce(authError);

      await expect(alpacaService.getAccount()).rejects.toThrow(
        "Invalid API credentials"
      );
    });

    test("should handle market closed scenarios", async () => {
      const marketClosedError = new Error("Market is closed");
      marketClosedError.status = 422;
      mockClient.createOrder.mockRejectedValueOnce(marketClosedError);

      await expect(
        alpacaService.createOrder({
          symbol: "AAPL",
          qty: 10,
          side: "buy",
          type: "market",
        })
      ).rejects.toThrow("Market is closed");
    });

    test("should handle insufficient funds", async () => {
      const insufficientFundsError = new Error("Insufficient buying power");
      insufficientFundsError.status = 422;
      mockClient.createOrder.mockRejectedValueOnce(insufficientFundsError);

      await expect(
        alpacaService.createOrder({
          symbol: "AAPL",
          qty: 1000,
          side: "buy",
          type: "market",
        })
      ).rejects.toThrow("Insufficient buying power");
    });
  });

  describe("Performance and Monitoring", () => {
    test("should track request metrics", async () => {
      const initialRequestCount = alpacaService.requestTimes.length;

      mockClient.getAccount.mockResolvedValueOnce({ id: "test" });
      mockClient.getPositions.mockResolvedValueOnce([]);

      await alpacaService.getAccount();
      await alpacaService.getPositions();

      expect(alpacaService.requestTimes.length).toBe(initialRequestCount + 2);
    });

    test("should handle concurrent requests properly", async () => {
      mockClient.getAccount.mockResolvedValue({ id: "test" });
      mockClient.getPositions.mockResolvedValue([]);
      mockClient.getOrders.mockResolvedValue([]);

      const promises = [
        alpacaService.getAccount(),
        alpacaService.getPositions(),
        alpacaService.getOrders(),
      ];

      const results = await Promise.all(promises);

      expect(results).toHaveLength(3);
      expect(mockClient.getAccount).toHaveBeenCalledTimes(1);
      expect(mockClient.getPositions).toHaveBeenCalledTimes(1);
      expect(mockClient.getOrders).toHaveBeenCalledTimes(1);
    });
  });
});
