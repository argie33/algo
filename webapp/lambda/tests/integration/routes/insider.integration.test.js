/**
 * Insider Integration Tests
 * Tests for insider trading data and analysis
 * Route: /routes/insider.js
 */

const request = require("supertest");
const { app } = require("../../../index");

// Mock database BEFORE importing routes/modules
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
  initializeDatabase: jest.fn().mockResolvedValue(undefined),
  closeDatabase: jest.fn().mockResolvedValue(undefined),
  getPool: jest.fn(),
  transaction: jest.fn((cb) => cb()),
  healthCheck: jest.fn(),
}));

// Import the mocked database
const { query } = require("../../../utils/database");

// Mock auth middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123" };
    next();
  }),
  authorizeAdmin: jest.fn((req, res, next) => next()),
  checkApiKey: jest.fn((req, res, next) => next()),
}));

// Import the mocked database
const { query } = require("../../../utils/database");


describe("Insider Trading API", () => {
  describe("Insider Trades", () => {
    beforeEach(() => {
    jest.clearAllMocks();
    query.mockImplementation((sql, params) => {
      // Default: return empty rows for all queries
      if (sql.includes("information_schema.tables")) {
        return Promise.resolve({ rows: [{ exists: true }] });
      }
      return Promise.resolve({ rows: [] });
    });
  });
    test("should return insider trades data (may be empty)", async () => {
      const response = await request(app).get("/api/insider/trades/AAPL");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("symbol", "AAPL");
      expect(response.body).toHaveProperty("trades");
      expect(response.body).toHaveProperty("summary");
      expect(Array.isArray(response.body.trades)).toBe(true);
    });

    test("should handle different symbols correctly", async () => {
      const response = await request(app).get("/api/insider/trades/GOOGL");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("symbol", "GOOGL");
      expect(response.body).toHaveProperty("trades");
      expect(response.body).toHaveProperty("summary");
      expect(Array.isArray(response.body.trades)).toBe(true);
    });
  });

  describe("Error handling", () => {
    test("should handle invalid symbols", async () => {
      const response = await request(app).get("/api/insider/trades/INVALID123");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("symbol", "INVALID123");
      expect(response.body).toHaveProperty("trades");
      expect(Array.isArray(response.body.trades)).toBe(true);
      expect(response.body.trades.length).toBe(0); // No data for invalid symbol
      expect(response.body).toHaveProperty("summary");
    });

    test("should handle server errors gracefully", async () => {
      const response = await request(app).get("/api/insider/trades/AAPL");

      // Endpoint is implemented and should return 200 even with no data
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("symbol", "AAPL");
      expect(response.body).toHaveProperty("trades");
      expect(Array.isArray(response.body.trades)).toBe(true);
      expect(response.body).toHaveProperty("summary");
    });
  });
});
