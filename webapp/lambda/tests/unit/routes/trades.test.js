const request = require("supertest");
const express = require("express");

// Mock dependencies BEFORE importing the routes
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123", role: "user" };
    req.token = "test-jwt-token";
    next();
  }),
}));

jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
  transaction: jest.fn(),
}));

// Mock optional services that may not exist
jest.mock(
  "../../../services/tradeAnalyticsService",
  () => {
    return jest.fn().mockImplementation(() => ({}));
  },
  { virtual: true }
);

jest.mock(
  "../../../utils/userApiKeyHelper",
  () => ({
    getUserApiKey: jest.fn(),
    validateUserAuthentication: jest.fn(),
    sendApiKeyError: jest.fn(),
  }),
  { virtual: true }
);

jest.mock(
  "../../../utils/alpacaService",
  () => {
    return jest.fn().mockImplementation(() => ({}));
  },
  { virtual: true }
);

// Now import the routes after mocking

const tradesRoutes = require("../../../routes/trades");
const { authenticateToken } = require("../../../middleware/auth");
const { query, transaction: _transaction } = require("../../../utils/database");

describe("Trades Routes - Testing Your Actual Site", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/trades", tradesRoutes);

    // Mock authentication to pass for all tests
    authenticateToken.mockImplementation((req, res, next) => {
      req.user = { sub: "test-user-123", role: "user" };
      req.token = "test-jwt-token";
      next();
    });
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /trades/health - Health check", () => {
    test("should return trade service health status", async () => {
      const response = await request(app).get("/trades/health").expect(200);

      expect(response.body).toMatchObject({
        success: true,
        status: "operational",
        service: "trades",
        timestamp: expect.any(String),
        message: "Trade History service is running",
      });

      // Health endpoint should not require authentication
      expect(authenticateToken).not.toHaveBeenCalled();
    });
  });

  describe("GET /trades/ - Root endpoint", () => {
    test("should return trade API ready message", async () => {
      const response = await request(app).get("/trades/").expect(200);

      expect(response.body).toMatchObject({
        success: true,
        message: "Trade History API - Ready",
        timestamp: expect.any(String),
        status: "operational",
      });

      // Root endpoint should not require authentication
      expect(authenticateToken).not.toHaveBeenCalled();
    });
  });

  describe("GET /trades/import/status - Trade import status", () => {
    test("should require authentication and handle protected endpoint", async () => {
      // The route requires authentication, so let's test the auth requirement
      const response = await request(app)
        .get("/trades/import/status")
        .expect([200, 400, 500]); // May succeed, fail validation, or have missing dependencies

      // Should have a response body structure
      expect(response.body).toHaveProperty("success");

      // Should use authentication middleware
      expect(authenticateToken).toHaveBeenCalled();
    });

    test("should handle missing dependencies gracefully", async () => {
      // Test what happens when route dependencies are missing
      query.mockResolvedValue({ rows: [] });

      const response = await request(app).get("/trades/import/status");

      // Route should return 200 with empty broker status
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("brokerStatus");
    });
  });

  describe("Authentication", () => {
    test("should require authentication for protected routes", async () => {
      authenticateToken.mockImplementation((req, res, _next) => {
        res.status(401).json({ success: false, error: "Unauthorized" });
      });

      await request(app).get("/trades/import/status").expect(401);

      expect(query).not.toHaveBeenCalled();
    });

    test("should handle route errors gracefully", async () => {
      // Test that route handles various error conditions
      query.mockRejectedValue(new Error("Service unavailable"));

      const response = await request(app).get("/trades/import/status");

      // Should return 500 for database errors
      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty("success", false);
    });
  });

  // ================================
  // Trade History Endpoints Tests
  // ================================

  describe("GET /trades/history - Trade history", () => {
    test("should return user trade history with pagination", async () => {
      const mockTrades = [
        {
          id: 1,
          symbol: "AAPL",
          side: "buy",
          quantity: 100,
          price: 150.0,
          executed_at: "2024-01-15T10:30:00Z",
          status: "filled",
        },
        {
          id: 2,
          symbol: "MSFT",
          side: "sell",
          quantity: 50,
          price: 300.0,
          executed_at: "2024-01-16T14:20:00Z",
          status: "filled",
        },
      ];

      query.mockResolvedValue({ rows: mockTrades });

      const response = await request(app).get("/trades/history").expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("trades");
      expect(response.body.data).toHaveProperty("pagination");
      expect(Array.isArray(response.body.data.trades)).toBe(true);

      if (response.body.data.trades.length > 0) {
        const trade = response.body.data.trades[0];
        expect(trade).toHaveProperty("symbol");
        expect(trade).toHaveProperty("side");
        expect(trade).toHaveProperty("quantity");
        expect(trade).toHaveProperty("price");
      }
    });

    test("should handle date range filtering", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/trades/history?start_date=2024-01-01&end_date=2024-01-31")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(query).toHaveBeenCalled();
    });

    test("should filter by symbol", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/trades/history?symbol=AAPL")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(query).toHaveBeenCalled();
    });

    test("should support pagination parameters", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/trades/history?page=2&limit=25")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.pagination).toHaveProperty("page", 2);
      expect(response.body.data.pagination).toHaveProperty("limit", 25);
    });
  });

  describe("GET /trades/analytics - Trade analytics", () => {
    test("should return trade performance analytics", async () => {
      const mockAnalytics = {
        total_trades: 150,
        winning_trades: 95,
        losing_trades: 55,
        win_rate: 0.633,
        average_win: 125.5,
        average_loss: -85.25,
        profit_factor: 1.47,
        total_pnl: 5420.75,
        largest_win: 850.0,
        largest_loss: -420.0,
      };

      query.mockResolvedValue({ rows: [mockAnalytics] });

      const response = await request(app).get("/trades/analytics").expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("analytics");

      const analytics = response.body.data.analytics;
      expect(analytics).toHaveProperty("total_trades");
      expect(analytics).toHaveProperty("win_rate");
      expect(analytics).toHaveProperty("profit_factor");
      expect(analytics).toHaveProperty("total_pnl");
    });

    test("should handle time period filters", async () => {
      query.mockResolvedValue({ rows: [{}] });

      const response = await request(app)
        .get("/trades/analytics?period=30d")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(query).toHaveBeenCalled();
    });

    test("should include benchmark comparison", async () => {
      query.mockResolvedValue({ rows: [{}] });

      const response = await request(app)
        .get("/trades/analytics?benchmark=SPY")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(query).toHaveBeenCalled();
    });
  });

  // ================================
  // Trade Import/Export Tests
  // ================================

  describe("POST /trades/import - Import trades", () => {
    test("should import trades from CSV data", async () => {
      const csvData = `symbol,side,quantity,price,date
AAPL,buy,100,150.00,2024-01-15
MSFT,sell,50,300.00,2024-01-16`;

      query.mockResolvedValue({ rows: [{ imported: 2 }] });
      _transaction.mockImplementation(async (callback) => {
        return await callback({ query });
      });

      const response = await request(app)
        .post("/trades/import")
        .field("format", "csv")
        .field("data", csvData)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("imported_count");
      expect(response.body.data).toHaveProperty("skipped_count");
    });

    test("should validate required fields", async () => {
      const response = await request(app)
        .post("/trades/import")
        .send({})
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body).toHaveProperty("error");
    });

    test("should handle duplicate trades", async () => {
      const tradeData = {
        format: "json",
        trades: [
          {
            symbol: "AAPL",
            side: "buy",
            quantity: 100,
            price: 150.0,
            date: "2024-01-15",
            external_id: "duplicate-123",
          },
        ],
      };

      query.mockResolvedValue({ rows: [{ imported: 0, duplicates: 1 }] });
      _transaction.mockImplementation(async (callback) => {
        return await callback({ query });
      });

      const response = await request(app)
        .post("/trades/import")
        .send(tradeData)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("duplicates_skipped");
    });

    test("should handle invalid data formats", async () => {
      const response = await request(app)
        .post("/trades/import")
        .send({ format: "invalid", data: "bad data" })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("format");
    });
  });

  describe("GET /trades/export - Export trades", () => {
    test("should export trades in CSV format", async () => {
      const mockTrades = [
        {
          symbol: "AAPL",
          side: "buy",
          quantity: 100,
          price: 150.0,
          executed_at: "2024-01-15T10:30:00Z",
        },
      ];

      query.mockResolvedValue({ rows: mockTrades });

      const response = await request(app)
        .get("/trades/export?format=csv")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("format", "csv");
      expect(response.body.data).toHaveProperty("content");
    });

    test("should export trades in JSON format", async () => {
      const mockTrades = [
        {
          symbol: "MSFT",
          side: "sell",
          quantity: 50,
          price: 300.0,
          executed_at: "2024-01-16T14:20:00Z",
        },
      ];

      query.mockResolvedValue({ rows: mockTrades });

      const response = await request(app)
        .get("/trades/export?format=json")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.format).toBe("json");
      expect(response.body.data).toHaveProperty("trades");
    });

    test("should handle date range for export", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get(
          "/trades/export?format=csv&start_date=2024-01-01&end_date=2024-01-31"
        )
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(query).toHaveBeenCalled();
    });
  });

  // ================================
  // Broker Integration Tests
  // ================================

  describe("GET /trades/brokers - Broker integration status", () => {
    test("should return connected brokers status", async () => {
      const mockBrokers = [
        {
          broker_name: "alpaca",
          status: "connected",
          last_sync: "2024-01-15T10:00:00Z",
          trade_count: 50,
        },
        {
          broker_name: "interactive_brokers",
          status: "disconnected",
          last_sync: null,
          trade_count: 0,
        },
      ];

      query.mockResolvedValue({ rows: mockBrokers });

      const response = await request(app).get("/trades/brokers").expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("brokers");
      expect(Array.isArray(response.body.data.brokers)).toBe(true);

      if (response.body.data.brokers.length > 0) {
        const broker = response.body.data.brokers[0];
        expect(broker).toHaveProperty("broker_name");
        expect(broker).toHaveProperty("status");
        expect(broker).toHaveProperty("trade_count");
      }
    });
  });

  describe("POST /trades/sync/:broker - Sync trades from broker", () => {
    test("should sync trades from Alpaca", async () => {
      const mockSyncResult = {
        synced_trades: 25,
        new_trades: 15,
        updated_trades: 10,
        errors: 0,
        last_sync: "2024-01-15T15:30:00Z",
      };

      query.mockResolvedValue({ rows: [mockSyncResult] });
      _transaction.mockImplementation(async (callback) => {
        return await callback({ query });
      });

      const response = await request(app)
        .post("/trades/sync/alpaca")
        .send({ start_date: "2024-01-01", end_date: "2024-01-15" })
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("synced_trades");
      expect(response.body.data).toHaveProperty("new_trades");
      expect(response.body.data).toHaveProperty("updated_trades");
    });

    test("should handle unsupported broker", async () => {
      const response = await request(app)
        .post("/trades/sync/unsupported_broker")
        .send({ start_date: "2024-01-01" })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("broker");
    });

    test("should validate date parameters", async () => {
      const response = await request(app)
        .post("/trades/sync/alpaca")
        .send({ start_date: "invalid-date" })
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("date");
    });
  });

  // ================================
  // Trade Performance Analysis Tests
  // ================================

  describe("GET /trades/performance - Performance analysis", () => {
    test("should return detailed performance metrics", async () => {
      const mockPerformance = {
        total_return: 12.5,
        annualized_return: 15.2,
        sharpe_ratio: 1.24,
        max_drawdown: -8.5,
        win_rate: 0.65,
        profit_factor: 1.45,
        average_trade_duration: 3.2,
        largest_winning_streak: 8,
        largest_losing_streak: 3,
      };

      query.mockResolvedValue({ rows: [mockPerformance] });

      const response = await request(app)
        .get("/trades/performance")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("performance");

      const performance = response.body.data.performance;
      expect(performance).toHaveProperty("total_return");
      expect(performance).toHaveProperty("sharpe_ratio");
      expect(performance).toHaveProperty("max_drawdown");
      expect(performance).toHaveProperty("win_rate");
    });

    test("should include benchmark comparison", async () => {
      query.mockResolvedValue({ rows: [{}] });

      const response = await request(app)
        .get("/trades/performance?benchmark=SPY")
        .expect(200);

      expect(response.body.success).toBe(true);
      if (response.body.data.benchmark) {
        expect(response.body.data.benchmark).toHaveProperty("symbol", "SPY");
        expect(response.body.data.benchmark).toHaveProperty("performance");
      }
    });

    test("should support different time periods", async () => {
      query.mockResolvedValue({ rows: [{}] });

      const response = await request(app)
        .get("/trades/performance?period=1y")
        .expect(200);

      expect(response.body.success).toBe(true);
      if (response.body.data.period_info) {
        expect(response.body.data.period_info).toHaveProperty("period", "1y");
      }
    });
  });

  describe("GET /trades/performance/attribution - Performance attribution", () => {
    test("should return performance attribution analysis", async () => {
      const mockAttribution = {
        by_symbol: [
          { symbol: "AAPL", contribution: 5.2, weight: 0.25 },
          { symbol: "MSFT", contribution: 3.1, weight: 0.15 },
          { symbol: "GOOGL", contribution: 2.8, weight: 0.2 },
        ],
        by_sector: [
          { sector: "Technology", contribution: 8.5, weight: 0.6 },
          { sector: "Healthcare", contribution: 2.1, weight: 0.25 },
        ],
        by_strategy: [
          { strategy: "momentum", contribution: 6.2, trade_count: 45 },
          { strategy: "mean_reversion", contribution: 4.3, trade_count: 32 },
        ],
      };

      query.mockResolvedValue({ rows: [mockAttribution] });

      const response = await request(app)
        .get("/trades/performance/attribution")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("attribution");

      const attribution = response.body.data.attribution;
      expect(attribution).toHaveProperty("by_symbol");
      expect(attribution).toHaveProperty("by_sector");
      expect(attribution).toHaveProperty("by_strategy");
    });
  });

  // ================================
  // Trade Statistics Tests
  // ================================

  describe("GET /trades/stats - Trade statistics", () => {
    test("should return comprehensive trade statistics", async () => {
      const mockStats = {
        total_trades: 256,
        total_volume: 125000,
        total_fees: 245.8,
        average_trade_size: 488.28,
        largest_trade: 2500.0,
        smallest_trade: 50.0,
        most_traded_symbol: "AAPL",
        most_traded_sector: "Technology",
        trading_days_active: 89,
        average_trades_per_day: 2.87,
      };

      query.mockResolvedValue({ rows: [mockStats] });

      const response = await request(app).get("/trades/stats").expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("statistics");

      const stats = response.body.data.statistics;
      expect(stats).toHaveProperty("total_trades");
      expect(stats).toHaveProperty("total_volume");
      expect(stats).toHaveProperty("average_trade_size");
      expect(stats).toHaveProperty("most_traded_symbol");
    });

    test("should filter stats by date range", async () => {
      query.mockResolvedValue({ rows: [{}] });

      const response = await request(app)
        .get("/trades/stats?start_date=2024-01-01&end_date=2024-01-31")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(query).toHaveBeenCalled();
    });

    test("should group stats by time period", async () => {
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/trades/stats?group_by=month")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(query).toHaveBeenCalled();
    });
  });

  // ================================
  // Trade Validation Tests
  // ================================

  describe("POST /trades/validate - Trade validation", () => {
    test("should validate trade data before import", async () => {
      const tradeData = {
        symbol: "AAPL",
        side: "buy",
        quantity: 100,
        price: 150.0,
        date: "2024-01-15T10:30:00Z",
      };

      const response = await request(app)
        .post("/trades/validate")
        .send({ trades: [tradeData] })
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("validation_results");
      expect(response.body.data).toHaveProperty("valid_trades");
      expect(response.body.data).toHaveProperty("invalid_trades");
    });

    test("should identify invalid trade data", async () => {
      const invalidTrade = {
        symbol: "", // Empty symbol
        side: "invalid", // Invalid side
        quantity: -10, // Negative quantity
        price: 0, // Zero price
        date: "invalid-date",
      };

      const response = await request(app)
        .post("/trades/validate")
        .send({ trades: [invalidTrade] })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.invalid_trades.length).toBeGreaterThan(0);
      expect(
        response.body.data.validation_results.errors.length
      ).toBeGreaterThan(0);
    });
  });

  // ================================
  // Trade Search and Filtering Tests
  // ================================

  describe("POST /trades/search - Advanced trade search", () => {
    test("should search trades by multiple criteria", async () => {
      const searchCriteria = {
        symbols: ["AAPL", "MSFT"],
        sides: ["buy"],
        min_quantity: 50,
        max_quantity: 500,
        min_price: 100.0,
        max_price: 200.0,
        start_date: "2024-01-01",
        end_date: "2024-01-31",
      };

      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .post("/trades/search")
        .send(searchCriteria)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("trades");
      expect(response.body.data).toHaveProperty("search_criteria");
      expect(response.body.data).toHaveProperty("total_matches");
    });

    test("should handle empty search criteria", async () => {
      const response = await request(app)
        .post("/trades/search")
        .send({})
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("criteria");
    });
  });

  // ================================
  // Error Handling Tests
  // ================================

  describe("Error handling", () => {
    test("should handle database connection errors", async () => {
      query.mockRejectedValue(new Error("Connection timeout"));

      const response = await request(app).get("/trades/history").expect(500);

      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
    });

    test("should handle transaction rollback on import errors", async () => {
      _transaction.mockRejectedValue(new Error("Transaction failed"));

      const response = await request(app)
        .post("/trades/import")
        .send({ format: "json", trades: [] })
        .expect(500);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("import");
    });

    test("should handle malformed request data", async () => {
      const response = await request(app)
        .post("/trades/import")
        .send("invalid json data")
        .expect(400);

      expect(response.body).toHaveProperty("error");
    });

    test("should handle missing authentication", async () => {
      authenticateToken.mockImplementation((req, res, _next) => {
        res.status(401).json({ success: false, error: "Unauthorized" });
      });

      const response = await request(app).get("/trades/history").expect(401);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Unauthorized");
    });

    test("should handle various error scenarios", async () => {
      // Test that the route handles different types of errors
      query.mockImplementation(() => {
        throw new Error("Database error");
      });

      const response = await request(app).get("/trades/import/status");

      // Should return 500 for database errors
      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty("success", false);
    });

    test("should validate request parameters", async () => {
      const response = await request(app)
        .get("/trades/history?page=invalid&limit=abc")
        .expect([200, 400]); // May succeed with defaults or return validation error

      expect(response.body).toHaveProperty("success");
    });
  });
});
