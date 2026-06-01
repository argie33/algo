/**
 * Unit Tests for Signals Route
 * Tests route logic in isolation with mocks
 * Fast, isolated, focused on business logic
 */
const request = require("supertest");
const express = require("express");
// Mock database module
const mockQuery = jest.fn();
jest.mock("../../../utils/database", () => ({
  query: mockQuery
}))
// Import mocked functions
// Mock auth middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123" };
    next();
  })
}));

// Import after mocks
const { authenticateToken } = require("../../../middleware/auth");
describe("Signals Route - Unit Tests", () => {
  let app;
  let signalsRoutes;
  beforeAll(() => {
    // Create minimal test app
    app = express();
    app.use(express.json());
    // Mock response helpers
    app.use((req, res, next) => {
      res.error = (message, status = 500) =>
        res.status(status).json({
          success: false,
          error: message,
          timestamp: new Date().toISOString()
        });
      res.success = (data, status = 200) =>
        res.status(status).json({
          success: true,
          ...data,
          timestamp: new Date().toISOString()
        });
      next();
    });
    // Load signals route
    signalsRoutes = require("../../../routes/signals");
    app.use("/api/signals", signalsRoutes);
  });
  beforeEach(() => {
    jest.clearAllMocks();
  });
  describe("Frontend API Pattern Validation", () => {
    test("should reject /api/signals/daily path parameter pattern", async () => {
      const response = await request(app).get("/api/signals/daily");
      expect(response.status).toBe(400);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Invalid symbol");
      expect(response.body.details).toContain("Use ?timeframe=daily instead");
      expect(response.body.symbol).toBe("DAILY");
    });
    test("should reject /api/signals/weekly path parameter pattern", async () => {
      const response = await request(app).get("/api/signals/weekly");
      expect(response.status).toBe(400);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Invalid symbol");
      expect(response.body.details).toContain("Use ?timeframe=weekly instead");
      expect(response.body.symbol).toBe("WEEKLY");
    });
    test("should reject /api/signals/monthly path parameter pattern", async () => {
      const response = await request(app).get("/api/signals/monthly");
      expect(response.status).toBe(400);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Invalid symbol");
      expect(response.body.details).toContain("Use ?timeframe=monthly instead");
      expect(response.body.symbol).toBe("MONTHLY");
    });
    test("should validate timeframe parameter strictly", async () => {
      const response = await request(app).get("/api/signals?timeframe=invalid");
      expect(response.status).toBe(400);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Invalid timeframe. Must be daily, weekly, or monthly");
    });
  });
  describe("GET /api/signals/buy - Business Logic", () => {
    test("should return formatted buy signals with correct structure", async () => {
      // Mock schema introspection
      mockQuery.mockResolvedValueOnce({
        rows: [
          { column_name: "id" },
          { column_name: "symbol" },
          { column_name: "timeframe" },
          { column_name: "date" },
          { column_name: "open" },
          { column_name: "high" },
          { column_name: "low" },
          { column_name: "close" },
          { column_name: "volume" },
          { column_name: "signal" },
          { column_name: "buylevel" },
          { column_name: "stoplevel" },
          { column_name: "inposition" }
        ]
      });
      // Mock signals query
      mockQuery.mockResolvedValueOnce({
        rows: [{
          symbol: "AAPL",
          timeframe: "daily",
          date: "2024-01-01",
          open: 149.5,
          high: 152.0,
          low: 148.0,
          close: 150.0,
          volume: 1000000,
          signal: "BUY",
          buylevel: 148.0,
          stoplevel: 145.0,
          inposition: false
        }]
      });
      // Mock count query
      mockQuery.mockResolvedValueOnce({
        rows: [{ total: 1 }]
      });
      const response = await request(app).get("/api/signals/buy");
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0]).toMatchObject({
        symbol: "AAPL",
        signal_type: "BUY",
        signal: "BUY",
        current_price: 150.0,
        confidence: 0.75,
        buy_level: 148.0,
        stop_level: 145.0,
        timeframe: "daily"
      });
      expect(response.body.signal_type).toBe("BUY");
      expect(response.body.pagination.total).toBe(1);
    });
    test("should handle table not found error", async () => {
      mockQuery.mockRejectedValueOnce(new Error("Table buy_sell_daily does not exist"));
      const response = await request(app).get("/api/signals/buy");
      expect(response.status).toBe(404);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Signals data not available");
      expect(response.body.message).toContain("does not exist");
      expect(response.body.timeframe).toBe("daily");
    });
    test("should validate timeframe parameter", async () => {
      const response = await request(app)
        .get("/api/signals/buy?timeframe=invalid");
      expect(response.status).toBe(400);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Invalid timeframe. Must be daily, weekly, or monthly");
    });
    test("should handle different timeframes", async () => {
      // Mock schema introspection
      mockQuery.mockResolvedValueOnce({
        rows: [
          { column_name: "symbol" },
          { column_name: "timeframe" },
          { column_name: "signal" },
          { column_name: "close" }
        ]
      });
      // Mock weekly signals
      mockQuery.mockResolvedValueOnce({
        rows: [{
          symbol: "TSLA",
          timeframe: "weekly",
          signal: "BUY",
          close: 250.0,
          date: "2024-01-01"
        }]
      });
      mockQuery.mockResolvedValueOnce({
        rows: [{ total: 1 }]
      });
      const response = await request(app)
        .get("/api/signals/buy?timeframe=weekly");
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.timeframe).toBe("weekly");
      expect(response.body.signal_type).toBe("BUY");
      expect(response.body.data[0].symbol).toBe("TSLA");
    });
  });
  describe("GET /api/signals/sell - Business Logic", () => {
    test("should return formatted sell signals", async () => {
      // Mock schema introspection
      mockQuery.mockResolvedValueOnce({
        rows: [
          { column_name: "symbol" },
          { column_name: "signal" },
          { column_name: "close" }
        ]
      });
      mockQuery.mockResolvedValueOnce({
        rows: [{
          symbol: "GOOGL",
          signal: "SELL",
          close: 2800.0,
          date: "2024-01-01"
        }]
      });
      mockQuery.mockResolvedValueOnce({
        rows: [{ total: 1 }]
      });
      const response = await request(app).get("/api/signals/sell");
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0].symbol).toBe("GOOGL");
      expect(response.body.data[0].signal_type).toBe("SELL");
      expect(response.body.signal_type).toBe("sell");
    });
  });
  describe("GET /api/signals/technical - Business Logic", () => {
    test("should return technical signals with indicators", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [{ column_name: "symbol" }, { column_name: "signal" }]
      });
      mockQuery.mockResolvedValueOnce({
        rows: [{
          symbol: "NVDA",
          signal: "BUY",
          close: 450.0
        }]
      });
      mockQuery.mockResolvedValueOnce({
        rows: [{ total: 1 }]
      });
      const response = await request(app).get("/api/signals/technical");
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0]).toHaveProperty("rsi");
      expect(response.body.data[0]).toHaveProperty("macd");
      expect(response.body.signal_type).toBe("technical");
      expect(response.body.indicators).toContain("RSI");
    });
  });
  describe("GET /api/signals/momentum - Business Logic", () => {
    test("should return momentum signals with momentum indicators", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [{ column_name: "symbol" }, { column_name: "signal" }]
      });
      mockQuery.mockResolvedValueOnce({
        rows: [{
          symbol: "AMD",
          signal: "BUY",
          close: 120.0
        }]
      });
      mockQuery.mockResolvedValueOnce({
        rows: [{ total: 1 }]
      });
      const response = await request(app).get("/api/signals/momentum");
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0]).toHaveProperty("momentum_score");
      expect(response.body.data[0]).toHaveProperty("price_change");
      expect(response.body.signal_type).toBe("momentum");
    });
  });
  describe("GET /api/signals/options - Static Endpoints", () => {
    test("should return options signals structure", async () => {
      const response = await request(app).get("/api/signals/options");
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.signal_type).toBe("options");
      expect(response.body.data).toEqual([]);
    });
  });
  describe("GET /api/signals/alerts - Alert Management", () => {
    test("should return signal alerts", async () => {
      mockQuery.mockResolvedValueOnce({
        rows: [{
          alert_id: 1,
          symbol: "AAPL",
          signal_type: "BUY",
          user_id: "test-user",
          is_active: true,
          created_at: "2024-01-01"
        }]
      });
      const response = await request(app).get("/api/signals/alerts");
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveLength(1);
    });
    test("should handle alerts table not found", async () => {
      mockQuery.mockRejectedValueOnce(new Error("relation \"signal_alerts\" does not exist"));
      const response = await request(app).get("/api/signals/alerts");
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toEqual([]);
      expect(response.body.message).toContain("not available");
    });
  });
  describe("POST /api/signals/alerts - Alert Creation", () => {
    test("should create signal alert", async () => {
      // Skipped - requires auth middleware integration
      mockQuery.mockResolvedValueOnce({
        rows: [{
          id: 1,
          symbol: "AAPL",
          signal_type: "BUY",
          user_id: "default_user",
          is_active: true,
          created_at: "2024-01-01"
        }]
      });
      const response = await request(app)
        .post("/api/signals/alerts")
        .send({
          symbol: "AAPL",
          signal_type: "BUY",
          min_strength: 0.7
        });
      expect(response.status).toBe(201);
      expect(response.body.success).toBe(true);
      expect(response.body.data.symbol).toBe("AAPL");
    });
    test("should validate required fields", async () => {
      // Skipped - requires auth middleware integration
      const response = await request(app)
        .post("/api/signals/alerts")
        .send({});
      expect(response.status).toBe(400);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("symbol is required");
    });
  });
  describe("GET /api/signals/options - Business Logic", () => {
    test("should return options signals structure", async () => {
      const response = await request(app).get("/api/signals/options");
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.signal_type).toBe("options");
      expect(response.body.data).toEqual([]);
    });
  });
  describe("GET /api/signals/sentiment - Business Logic", () => {
    test("should return sentiment signals structure", async () => {
      const response = await request(app).get("/api/signals/sentiment");
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.signal_type).toBe("sentiment");
      expect(response.body.data).toEqual([]);
    });
  });
  describe("GET /api/signals/earnings - Business Logic", () => {
    test("should return earnings signals structure", async () => {
      const response = await request(app).get("/api/signals/earnings");
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.signal_type).toBe("earnings");
      expect(response.body.data).toEqual([]);
    });
  });
  describe("GET /api/signals/crypto - Business Logic", () => {
    test("should return crypto signals structure", async () => {
      const response = await request(app).get("/api/signals/crypto");
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.signal_type).toBe("crypto");
      expect(response.body.data).toEqual([]);
    });
  });
  describe("GET /api/signals/history - Business Logic", () => {
    test("should return historical signals with pagination", async () => {
      const response = await request(app).get("/api/signals/history");
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.signal_type).toBe("history");
      expect(response.body).toHaveProperty("data");
      expect(response.body).toHaveProperty("pagination");
      expect(Array.isArray(response.body.data)).toBe(true);
    });
    test("should handle pagination parameters", async () => {
      const response = await request(app).get("/api/signals/history?page=2&limit=5");
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.pagination.page).toBe(2);
      expect(response.body.pagination.limit).toBe(5);
    });
  });
  describe("GET /api/signals/sector-rotation - Business Logic", () => {
    test("should return sector rotation signals", async () => {
      const response = await request(app).get("/api/signals/sector-rotation");
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body.signal_type).toBe("sector_rotation");
      expect(response.body.data).toEqual([]);
    });
  });
  describe("GET /api/signals/list - Business Logic", () => {
    test("should return signals list with summary", async () => {
      // Mock signals query with sample data
      mockQuery.mockResolvedValueOnce({
        rows: [{
          symbol: "AAPL",
          date: new Date('2024-01-15'),
          timeframe: "daily",
          signal: "BUY",
          open: 185.50,
          high: 188.20,
          low: 184.75,
          close: 187.80,
          volume: 50000000,
          buylevel: 187.80,
          stoplevel: 178.42,
          inposition: false
        }]
      });
      const response = await request(app).get("/api/signals/list");
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body).toHaveProperty("summary");
      expect(Array.isArray(response.body.data)).toBe(true);
    });
    test("should handle timeframe parameter", async () => {
      // Mock weekly signals query with sample data
      mockQuery.mockResolvedValueOnce({
        rows: [{
          symbol: "TSLA",
          date: new Date('2024-01-15'),
          timeframe: "weekly",
          signal: "SELL",
          open: 245.80,
          high: 250.30,
          low: 242.10,
          close: 247.60,
          volume: 30000000,
          buylevel: 247.60,
          stoplevel: 235.22,
          inposition: true
        }]
      });
      const response = await request(app).get("/api/signals/list?timeframe=weekly");
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("timeframe", "weekly");
    });
  });
  describe("POST /api/signals/custom - Business Logic", () => {
    test("should create custom signal alert", async () => {
      // Skipped - requires auth middleware integration
      const customSignalData = {
        name: "Test Custom Signal",
        criteria: { rsi: { min: 30, max: 70 } },
        symbols: ["AAPL"]
      };
      const response = await request(app)
        .post("/api/signals/custom")
        .send(customSignalData);
      expect(response.status).toBe(201);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("signal_id");
    });
    test("should validate required fields for custom signals", async () => {
      // Skipped - requires auth middleware integration
      const response = await request(app)
        .post("/api/signals/custom")
        .send({});
      expect(response.status).toBe(400);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("required");
    });
  });
  describe("Error Handling", () => {
    test("should handle database connection errors", async () => {
      mockQuery.mockRejectedValueOnce(new Error("Database connection failed"));
      const response = await request(app).get("/api/signals/buy");
      expect([404, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toMatch(/Failed to fetch buy signals|Signals data not available/);
    });
    test("should validate signal type parameters", async () => {
      const response = await request(app).get("/api/signals/invalid_signal_type");
      expect(response.status).toBe(404);
      expect(response.body.success).toBe(false);
    });
  });
});
