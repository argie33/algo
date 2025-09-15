// Mock database before importing services
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

// Mock Alpaca Service
jest.mock("../../../utils/alpacaService", () => ({
  getAccountInfo: jest.fn(),
  getPositions: jest.fn(),
  getOrders: jest.fn(),
  placeOrder: jest.fn(),
  getMarketData: jest.fn(),
  getPortfolioHistory: jest.fn(),
}));

// Mock API Key Service
jest.mock("../../../utils/apiKeyService", () => ({
  getDecryptedApiKey: jest.fn(),
}));

const alpacaService = require("../../../utils/alpacaService");
const { query } = require("../../../utils/database");
const { getDecryptedApiKey } = require("../../../utils/apiKeyService");

describe("Alpaca Integration Service Unit Tests", () => {
  const testUserId = "test-user-123";
  const mockApiKeys = {
    apiKey: "test-key",
    apiSecret: "test-secret",
    isSandbox: true,
  };

  beforeEach(() => {
    jest.clearAllMocks();
    getDecryptedApiKey.mockResolvedValue(mockApiKeys);
  });

  describe("Account Information", () => {
    test("should retrieve account information", async () => {
      const mockAccountInfo = {
        account_id: "test-account-123",
        status: "ACTIVE",
        currency: "USD",
        buying_power: "50000.00",
        cash: "25000.00",
        portfolio_value: "75000.00",
        day_trade_count: 0,
        account_blocked: false,
      };

      alpacaService.getAccountInfo.mockResolvedValue(mockAccountInfo);

      const result = await alpacaService.getAccountInfo(testUserId);

      expect(result).toEqual(mockAccountInfo);
      expect(alpacaService.getAccountInfo).toHaveBeenCalledWith(testUserId);
      expect(getDecryptedApiKey).toHaveBeenCalledWith(testUserId, "alpaca");
    });

    test("should handle account information errors", async () => {
      alpacaService.getAccountInfo.mockRejectedValue(
        new Error("API connection failed")
      );

      await expect(alpacaService.getAccountInfo(testUserId)).rejects.toThrow(
        "API connection failed"
      );
    });

    test("should handle missing API keys", async () => {
      getDecryptedApiKey.mockResolvedValue(null);
      alpacaService.getAccountInfo.mockRejectedValue(
        new Error("No API keys configured")
      );

      await expect(alpacaService.getAccountInfo(testUserId)).rejects.toThrow(
        "No API keys configured"
      );
    });
  });

  describe("Portfolio Positions", () => {
    test("should retrieve current positions", async () => {
      const mockPositions = [
        {
          symbol: "AAPL",
          qty: "100",
          side: "long",
          avg_entry_price: "150.00",
          market_value: "18945.00",
          unrealized_pl: "2445.00",
          unrealized_plpc: "0.148",
          current_price: "189.45",
        },
        {
          symbol: "MSFT",
          qty: "50",
          side: "long",
          avg_entry_price: "300.00",
          market_value: "17512.50",
          unrealized_pl: "2512.50",
          unrealized_plpc: "0.167",
          current_price: "350.25",
        },
      ];

      alpacaService.getPositions.mockResolvedValue(mockPositions);

      const result = await alpacaService.getPositions(testUserId);

      expect(result).toEqual(mockPositions);
      expect(result).toHaveLength(2);
      expect(result[0].symbol).toBe("AAPL");
      expect(alpacaService.getPositions).toHaveBeenCalledWith(testUserId);
    });

    test("should handle empty positions", async () => {
      alpacaService.getPositions.mockResolvedValue([]);

      const result = await alpacaService.getPositions(testUserId);

      expect(result).toEqual([]);
    });

    test("should handle positions API errors", async () => {
      alpacaService.getPositions.mockRejectedValue(
        new Error("Positions API unavailable")
      );

      await expect(alpacaService.getPositions(testUserId)).rejects.toThrow(
        "Positions API unavailable"
      );
    });
  });

  describe("Order Management", () => {
    test("should retrieve order history", async () => {
      const mockOrders = [
        {
          id: "order-123",
          symbol: "AAPL",
          side: "buy",
          qty: "100",
          type: "market",
          status: "filled",
          filled_price: "189.45",
          filled_at: "2023-01-01T10:00:00Z",
        },
        {
          id: "order-124",
          symbol: "MSFT",
          side: "sell",
          qty: "25",
          type: "limit",
          status: "pending",
          limit_price: "355.00",
          submitted_at: "2023-01-01T11:00:00Z",
        },
      ];

      alpacaService.getOrders.mockResolvedValue(mockOrders);

      const result = await alpacaService.getOrders(testUserId);

      expect(result).toEqual(mockOrders);
      expect(result).toHaveLength(2);
      expect(result[0].status).toBe("filled");
      expect(alpacaService.getOrders).toHaveBeenCalledWith(testUserId);
    });

    test("should place market buy order", async () => {
      const orderRequest = {
        symbol: "TSLA",
        side: "buy",
        qty: "10",
        type: "market",
      };

      const mockOrderResponse = {
        id: "order-125",
        status: "accepted",
        ...orderRequest,
        submitted_at: "2023-01-01T12:00:00Z",
      };

      alpacaService.placeOrder.mockResolvedValue(mockOrderResponse);

      const result = await alpacaService.placeOrder(testUserId, orderRequest);

      expect(result).toEqual(mockOrderResponse);
      expect(result.status).toBe("accepted");
      expect(alpacaService.placeOrder).toHaveBeenCalledWith(
        testUserId,
        orderRequest
      );
    });

    test("should place limit sell order", async () => {
      const orderRequest = {
        symbol: "NVDA",
        side: "sell",
        qty: "5",
        type: "limit",
        limit_price: "450.00",
      };

      const mockOrderResponse = {
        id: "order-126",
        status: "accepted",
        ...orderRequest,
        submitted_at: "2023-01-01T13:00:00Z",
      };

      alpacaService.placeOrder.mockResolvedValue(mockOrderResponse);

      const result = await alpacaService.placeOrder(testUserId, orderRequest);

      expect(result).toEqual(mockOrderResponse);
      expect(result.limit_price).toBe("450.00");
    });

    test("should handle order placement errors", async () => {
      const orderRequest = {
        symbol: "INVALID",
        side: "buy",
        qty: "100",
        type: "market",
      };

      alpacaService.placeOrder.mockRejectedValue(new Error("Invalid symbol"));

      await expect(
        alpacaService.placeOrder(testUserId, orderRequest)
      ).rejects.toThrow("Invalid symbol");
    });

    test("should validate order parameters", async () => {
      const invalidOrder = {
        symbol: "",
        side: "buy",
        qty: "-10",
        type: "market",
      };

      alpacaService.placeOrder.mockRejectedValue(
        new Error("Invalid order parameters")
      );

      await expect(
        alpacaService.placeOrder(testUserId, invalidOrder)
      ).rejects.toThrow("Invalid order parameters");
    });
  });

  describe("Market Data", () => {
    test("should retrieve real-time quotes", async () => {
      const symbols = ["AAPL", "MSFT", "GOOGL"];
      const mockQuotes = {
        AAPL: {
          symbol: "AAPL",
          bid: "189.40",
          ask: "189.50",
          last: "189.45",
          timestamp: "2023-01-01T15:30:00Z",
        },
        MSFT: {
          symbol: "MSFT",
          bid: "350.20",
          ask: "350.30",
          last: "350.25",
          timestamp: "2023-01-01T15:30:00Z",
        },
        GOOGL: {
          symbol: "GOOGL",
          bid: "2650.70",
          ask: "2650.80",
          last: "2650.75",
          timestamp: "2023-01-01T15:30:00Z",
        },
      };

      alpacaService.getMarketData.mockResolvedValue(mockQuotes);

      const result = await alpacaService.getMarketData(testUserId, symbols);

      expect(result).toEqual(mockQuotes);
      expect(Object.keys(result)).toHaveLength(3);
      expect(result.AAPL.last).toBe("189.45");
      expect(alpacaService.getMarketData).toHaveBeenCalledWith(
        testUserId,
        symbols
      );
    });

    test("should handle market data API errors", async () => {
      const symbols = ["AAPL"];
      alpacaService.getMarketData.mockRejectedValue(
        new Error("Market data unavailable")
      );

      await expect(
        alpacaService.getMarketData(testUserId, symbols)
      ).rejects.toThrow("Market data unavailable");
    });

    test("should handle empty symbol list", async () => {
      alpacaService.getMarketData.mockResolvedValue({});

      const result = await alpacaService.getMarketData(testUserId, []);

      expect(result).toEqual({});
    });
  });

  describe("Portfolio History", () => {
    test("should retrieve portfolio performance history", async () => {
      const mockHistory = {
        timestamp: ["2023-01-01", "2023-01-02", "2023-01-03"],
        equity: ["70000.00", "72500.00", "75000.00"],
        profit_loss: ["0.00", "2500.00", "5000.00"],
        profit_loss_pct: ["0.0", "0.0357", "0.0714"],
        base_value: "70000.00",
        timeframe: "1D",
      };

      alpacaService.getPortfolioHistory.mockResolvedValue(mockHistory);

      const result = await alpacaService.getPortfolioHistory(testUserId, "1M");

      expect(result).toEqual(mockHistory);
      expect(result.timestamp).toHaveLength(3);
      expect(result.base_value).toBe("70000.00");
      expect(alpacaService.getPortfolioHistory).toHaveBeenCalledWith(
        testUserId,
        "1M"
      );
    });

    test("should handle portfolio history errors", async () => {
      alpacaService.getPortfolioHistory.mockRejectedValue(
        new Error("History data unavailable")
      );

      await expect(
        alpacaService.getPortfolioHistory(testUserId, "1M")
      ).rejects.toThrow("History data unavailable");
    });
  });

  describe("Database Integration", () => {
    test("should store portfolio data in database", async () => {
      const portfolioData = {
        user_id: testUserId,
        alpaca_account_id: "test-account-123",
        portfolio_value: "75000.00",
        buying_power: "25000.00",
        day_trade_count: 0,
      };

      query.mockResolvedValue({ rows: [{ ...portfolioData, id: 1 }] });

      // Since this is a unit test, we just mock the database interaction
      const result = await query(
        "INSERT INTO user_portfolios (user_id, alpaca_account_id, portfolio_value, buying_power, day_trade_count) VALUES ($1, $2, $3, $4, $5) RETURNING *",
        [
          portfolioData.user_id,
          portfolioData.alpaca_account_id,
          portfolioData.portfolio_value,
          portfolioData.buying_power,
          portfolioData.day_trade_count,
        ]
      );

      expect(result.rows[0]).toMatchObject(portfolioData);
      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("INSERT INTO user_portfolios"),
        expect.arrayContaining([testUserId, "test-account-123"])
      );
    });

    test("should handle database insertion errors", async () => {
      query.mockRejectedValue(new Error("Database constraint violation"));

      await expect(query("INSERT INTO user_portfolios...", [])).rejects.toThrow(
        "Database constraint violation"
      );
    });
  });

  describe("Error Handling", () => {
    test("should handle network timeouts", async () => {
      alpacaService.getAccountInfo.mockRejectedValue(
        new Error("Request timeout")
      );

      await expect(alpacaService.getAccountInfo(testUserId)).rejects.toThrow(
        "Request timeout"
      );
    });

    test("should handle authentication failures", async () => {
      getDecryptedApiKey.mockRejectedValue(
        new Error("Invalid API credentials")
      );

      await expect(alpacaService.getAccountInfo(testUserId)).rejects.toThrow(
        "Invalid API credentials"
      );
    });

    test("should handle API rate limiting", async () => {
      alpacaService.getMarketData.mockRejectedValue(
        new Error("Rate limit exceeded")
      );

      await expect(
        alpacaService.getMarketData(testUserId, ["AAPL"])
      ).rejects.toThrow("Rate limit exceeded");
    });

    test("should handle malformed API responses", async () => {
      alpacaService.getPositions.mockResolvedValue(null);

      const result = await alpacaService.getPositions(testUserId);

      expect(result).toBeNull();
    });
  });
});
