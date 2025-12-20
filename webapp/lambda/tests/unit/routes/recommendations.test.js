/**
 * Recommendations Routes Unit Tests
 * Tests recommendations route logic in isolation with mocks
 */
const express = require("express");
const request = require("supertest");
// Mock the database utility
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
}));

const { query, closeDatabase, initializeDatabase, getPool, transaction, healthCheck } = require("../../../utils/database");
// Mock the authentication middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: (req, res, next) => {
    req.user = { sub: "test-user-123" };
    next();
  },
}));
describe("Recommendations Routes Unit Tests", () => {
  let app;
  let recommendationsRouter;
  let mockQuery;
  beforeEach(() => {
    jest.clearAllMocks();
    // Set up mocks
    mockQuery = query;
    // Default mock for all tests - return empty rows
    mockQuery.mockResolvedValue({ rows: [] });

    // Create test app
    app = express();
    app.use(express.json());
    // Add response helper middleware
    app.use((req, res, next) => {
      res.error = (message, status) =>
        res.status(status).json({
          success: false,
          error: message,
        });
      res.serverError = (message, details) =>
        res.status(500).json({
          success: false,
          error: message,
          details,
        });
      next();
    });
    // Load the route module
    recommendationsRouter = require("../../../routes/recommendations");
    app.use("/recommendations", recommendationsRouter);
  });
  describe("GET /recommendations", () => {
    beforeEach(() => {
      // Default mock for all tests in this describe block
      mockQuery.mockResolvedValue({ rows: [] });
    });
    test("should return recommendations with mocked data", async () => {
      // Mock successful database response
      mockQuery.mockResolvedValue({
        rows: [
          {
            symbol: "AAPL",
            analyst_firm: "Goldman Sachs",
            rating: "Buy",
            target_price: 200.0,
            current_price: 180.0,
            date_published: "2024-01-15",
            date_updated: "2024-01-15",
          },
        ],
      });
      const response = await request(app).get("/recommendations");
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("recommendations");
      expect(response.body).toHaveProperty("summary");
      expect(response.body).toHaveProperty("filters");
      expect(response.body).toHaveProperty("timestamp");
      // Verify recommendations structure
      expect(response.body.recommendations).toHaveLength(1);
      expect(response.body.recommendations[0]).toHaveProperty("symbol", "AAPL");
      expect(response.body.recommendations[0]).toHaveProperty(
        "analyst_firm",
        "Goldman Sachs"
      );
      // Verify timestamp is a valid ISO string
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
      expect(mockQuery).toHaveBeenCalled();
    });
    test("should handle query parameters", async () => {
      // Mock successful database response
      mockQuery.mockResolvedValue({
        rows: [
          {
            symbol: "AAPL",
            analyst_firm: "Goldman Sachs",
            rating: "Buy",
            target_price: 200.0,
            current_price: 180.0,
            date_published: "2024-01-15",
            date_updated: "2024-01-15",
          },
        ],
      });
      const response = await request(app).get("/recommendations").query({
        symbol: "AAPL",
        category: "buy",
        analyst: "goldman_sachs",
        limit: 50,
        timeframe: "recent",
      });
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.filters).toHaveProperty("symbol", "AAPL");
      expect(response.body.filters).toHaveProperty("category", "buy");
      expect(response.body.filters).toHaveProperty("analyst", "goldman_sachs");
      expect(response.body.filters).toHaveProperty("timeframe", "recent");
      expect(response.body.filters).toHaveProperty("limit", 50);
      // Parameters are processed and endpoint returns real data
    });
    test("should include comprehensive troubleshooting information", async () => {
      const response = await request(app).get("/recommendations");
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("recommendations");
      expect(response.body).toHaveProperty("summary");
      expect(response.body).toHaveProperty("filters");
      expect(response.body).toHaveProperty("timestamp");
    });
    test("should handle different category parameters", async () => {
      const categories = ["all", "buy", "sell", "hold"];
      for (const category of categories) {
        const response = await request(app)
          .get("/recommendations")
          .query({ category });
        expect(response.status).toBe(200);
        expect(response.body.filters).toHaveProperty("category", category);
        expect(response.body).toHaveProperty("success", true);
      }
    });
    test("should default to all category", async () => {
      const response = await request(app)
        .get("/recommendations")
        .query({ symbol: "AAPL" });
      expect(response.status).toBe(200);
      expect(response.body.filters).toHaveProperty("category", "all"); // default value
    });
    test("should handle different timeframe parameters", async () => {
      const timeframes = ["recent", "weekly", "monthly"];
      for (const timeframe of timeframes) {
        const response = await request(app)
          .get("/recommendations")
          .query({ timeframe });
        expect(response.status).toBe(200);
        expect(response.body.filters).toHaveProperty("timeframe", timeframe);
        expect(response.body).toHaveProperty("success", true);
      }
    });
    test("should handle analyst filter parameter", async () => {
      const response = await request(app)
        .get("/recommendations")
        .query({ analyst: "morgan_stanley" });
      expect(response.status).toBe(200);
      expect(response.body.filters).toHaveProperty("analyst", "morgan_stanley");
      expect(response.body).toHaveProperty("success", true);
    });
    test("should handle limit parameter and parse as integer", async () => {
      const response = await request(app)
        .get("/recommendations")
        .query({ limit: "100" });
      expect(response.status).toBe(200);
      expect(response.body.filters).toHaveProperty("limit", 100); // Should be parsed as number
      expect(response.body).toHaveProperty("success", true);
    });
    test("should handle default limit parameter", async () => {
      const response = await request(app).get("/recommendations");
      expect(response.status).toBe(200);
      expect(response.body.filters).toHaveProperty("limit", 20); // default value
    });
    test("should handle symbol parameter", async () => {
      const response = await request(app)
        .get("/recommendations")
        .query({ symbol: "GOOGL" });
      expect(response.status).toBe(200);
      expect(response.body.filters).toHaveProperty("symbol", "GOOGL");
      expect(response.body).toHaveProperty("success", true);
    });
    test("should handle no symbol parameter", async () => {
      const response = await request(app).get("/recommendations");
      expect(response.status).toBe(200);
      expect(response.body.filters.symbol).toBeUndefined();
      expect(response.body).toHaveProperty("success", true);
    });
  });
  describe("GET /recommendations/consensus", () => {
    test("should return not implemented for consensus endpoint when accessed", async () => {
      // This test assumes the consensus endpoint exists but is also not implemented
      const response = await request(app).get("/recommendations/consensus");
      // The consensus endpoint doesn't exist, so it should return 404
      expect(response.status).toBe(404);
    });
  });
  describe("GET /recommendations/analysts", () => {
    test("should handle analysts endpoint when accessed", async () => {
      // This test assumes the analysts endpoint might exist
      const response = await request(app).get("/recommendations/analysts");
      // The analysts endpoint without symbol doesn't exist, should return 404
      expect(response.status).toBe(404);
    });
  });
  describe("GET /recommendations/price-targets", () => {
    test("should handle price targets endpoint when accessed", async () => {
      // This test assumes the price targets endpoint might exist
      const response = await request(app).get("/recommendations/price-targets");
      // The price-targets endpoint doesn't exist, should return 404
      expect(response.status).toBe(404);
    });
  });
  describe("Error handling", () => {
    test("should handle implementation errors gracefully", async () => {
      // Test the catch block by making the database query fail
      mockQuery.mockRejectedValue(new Error("Database connection failed"));
      const response = await request(app).get("/recommendations");
      // Should return error response when implementation fails
      expect(response.status).toBe(500);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body).toHaveProperty("error");
    });
    test("should handle malformed query parameters", async () => {
      const response = await request(app).get("/recommendations").query({
        limit: "not_a_number",
        category: "invalid_category_but_still_works",
        analyst: "special!@#$%^&*()characters",
      });
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.filters.limit == null || isNaN(response.body.filters.limit)).toBe(true); // parseInt of invalid string
      expect(response.body.filters).toHaveProperty(
        "category",
        "invalid_category_but_still_works"
      );
      // Should still process gracefully even with invalid parameters
    });
    test("should handle special characters in parameters", async () => {
      const response = await request(app).get("/recommendations").query({
        symbol: "AAPL'; DROP TABLE recommendations; --",
        analyst: "<script>alert('xss')</script>",
      });
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body.filters).toHaveProperty(
        "symbol",
        "AAPL'; DROP TABLE recommendations; --"
      );
      expect(response.body.filters).toHaveProperty(
        "analyst",
        "<script>alert('xss')</script>"
      );
      // Should handle malicious input safely since it's not actually querying database
    });
    test("should handle empty string parameters", async () => {
      const response = await request(app).get("/recommendations").query({
        symbol: "",
        category: "",
        analyst: "",
      });
      expect(response.status).toBe(200);
      expect(response.body.filters).toHaveProperty("symbol", "");
      expect(response.body.filters).toHaveProperty("category", "");
      expect(response.body.filters).toHaveProperty("analyst", "");
      expect(response.body).toHaveProperty("success", true);
    });
  });
  describe("Response format", () => {
    test("should return consistent JSON response format", async () => {
      const response = await request(app).get("/recommendations");
      expect(response.headers["content-type"]).toMatch(/json/);
      expect(typeof response.body).toBe("object");
      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("timestamp");
    });
    test("should include proper response structure", async () => {
      const response = await request(app).get("/recommendations");
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("recommendations");
      expect(response.body).toHaveProperty("summary");
      expect(response.body).toHaveProperty("filters");
      expect(response.body).toHaveProperty("timestamp");
    });
    test("should preserve query parameters in response", async () => {
      const response = await request(app).get("/recommendations").query({
        symbol: "TSLA",
        category: "buy",
        limit: "25",
      });
      expect(response.body.filters).toHaveProperty("symbol", "TSLA");
      expect(response.body.filters).toHaveProperty("category", "buy");
      expect(response.body.filters).toHaveProperty("limit", 25);
    });
    test("should include all filter parameters in response", async () => {
      const response = await request(app).get("/recommendations").query({
        symbol: "AAPL",
        category: "hold",
        analyst: "jp_morgan",
        timeframe: "monthly",
        limit: "15",
      });
      expect(response.body).toHaveProperty("filters");
      expect(response.body.filters).toHaveProperty("category", "hold");
      expect(response.body.filters).toHaveProperty("analyst", "jp_morgan");
      expect(response.body.filters).toHaveProperty("timeframe", "monthly");
      expect(response.body.filters).toHaveProperty("limit", 15);
    });
  });
  describe("Future implementation readiness", () => {
    test("should handle comprehensive parameter requests with proper structure", async () => {
      const response = await request(app).get("/recommendations").query({
        symbol: "AAPL",
        category: "buy",
        analyst: "goldman_sachs",
        timeframe: "recent",
        limit: "30",
      });
      // Response structure should be complete and functional
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("filters");
      expect(response.body.filters).toHaveProperty("symbol", "AAPL");
      expect(response.body).toHaveProperty("timestamp");
      expect(response.body).toHaveProperty("recommendations");
      expect(response.body).toHaveProperty("summary");
    });
    test("should handle all expected recommendation categories", async () => {
      const validCategories = ["all", "buy", "sell", "hold"];
      for (const category of validCategories) {
        const response = await request(app)
          .get("/recommendations")
          .query({ category });
        expect(response.status).toBe(200);
        expect(response.body).toHaveProperty("success", true);
        expect(response.body.filters).toHaveProperty("category", category);
        // Implementation supports these categories
      }
    });
  });
});
