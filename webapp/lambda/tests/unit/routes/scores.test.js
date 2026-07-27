/**
 * Scores Routes Unit Tests
 * Tests scores route logic with mocked database
 */
const express = require("express");
const request = require("supertest");
// Mock database for unit tests
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
}));

// Import after mocks
const { query } = require("../../../utils/database");
const scoresRouter = require("../../../routes/scores");

describe("Scores Routes Unit Tests", () => {
  let app;
  beforeAll(() => {
    // Create test app
    app = express();
    app.use(express.json());
    // Mock authentication middleware - allow all requests through
    app.use((req, res, next) => {
      req.user = { sub: "test-user-123" }; // Mock authenticated user
      next();
    });

    // Add response formatter middleware
    const responseFormatter = require("../../../middleware/responseNormalizer");
    app.use(responseFormatter);
    // Load the route module
    app.use("/scores", scoresRouter);
  });
  beforeEach(() => {
    // Reset all mocks before each test
    jest.clearAllMocks();
    // Set up default mock responses for all tests
    query.mockImplementation((sql, params) => {
      // Handle COUNT queries
      if (sql.includes("SELECT COUNT") || sql.includes("COUNT(*)")) {
        return Promise.resolve({
          rows: [{ count: "0", total: "0" }],
          rowCount: 1,
        });
      }
      // Handle INSERT/UPDATE/DELETE queries
      if (
        sql.includes("INSERT") ||
        sql.includes("UPDATE") ||
        sql.includes("DELETE")
      ) {
        return Promise.resolve({ rowCount: 0, rows: [] });
      }
      // Handle information_schema queries
      if (sql.includes("information_schema.tables")) {
        return Promise.resolve({ rows: [{ exists: true }] });
      }
      // Default: return empty rows
      return Promise.resolve({ rows: [], rowCount: 0 });
    });
  });
  // NOTE: /ping doesn't exist in routes/scores.js - its test block is removed. The
  // real "/" list endpoint is much simpler than these tests originally assumed: it
  // selects only symbol + the 6 score columns (no company_name/sector/rsi/quality_inputs/
  // growth_inputs/etc - those don't exist in this query), and returns them via
  // sendPaginated() -> { items, pagination }, not { data: { stocks, viewType }, summary,
  // metadata }.
  describe("GET /scores", () => {
    test("should return scores data from stock_scores table", async () => {
      query.mockResolvedValueOnce({
        rows: [
          {
            symbol: "AAPL",
            composite_score: 52.13,
            momentum_score: 67.92,
            value_score: 17.75,
            quality_score: 60.66,
            growth_score: 68.94,
            stability_score: 58.74,
            total_count: "1",
          },
        ],
      });
      const response = await request(app)
        .get("/scores")
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("items");
      expect(Array.isArray(response.body.items)).toBe(true);
      expect(response.body.items).toHaveLength(1);
      const stock = response.body.items[0];
      expect(stock).toEqual({
        symbol: "AAPL",
        composite_score: 52.13,
        momentum_score: 67.92,
        value_score: 17.75,
        quality_score: 60.66,
        growth_score: 68.94,
        stability_score: 58.74,
      });
      expect(response.body.pagination).toMatchObject({
        page: 1,
        limit: 50,
        total: 1,
      });
    });

    test("should handle pagination parameters", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/scores")
        .query({ page: 2, limit: 25 })
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body.pagination).toMatchObject({
        page: 2,
        limit: 25,
        offset: 25,
      });
      // Verify the LIMIT/OFFSET params reached the query
      expect(query).toHaveBeenCalledWith(
        expect.any(String),
        expect.arrayContaining([25, 25])
      );
    });

    test("should filter by symbol", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      await request(app)
        .get("/scores")
        .query({ symbol: "aapl" })
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("ss.symbol = $1"),
        expect.arrayContaining(["AAPL"])
      );
    });

    test("should sort by composite_score DESC by default", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      await request(app)
        .get("/scores")
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("ORDER BY ss.composite_score DESC"),
        expect.any(Array)
      );
    });

    test("should ignore an invalid sort field and fall back to composite_score", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      await request(app)
        .get("/scores")
        .query({ sort: "'; DROP TABLE stock_scores; --" })
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(query).toHaveBeenCalledWith(
        expect.stringContaining("ORDER BY ss.composite_score"),
        expect.any(Array)
      );
    });

    test("should cap limit at 1000", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/scores")
        .query({ limit: 5000 })
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body.pagination.limit).toBe(1000);
    });

    test("should handle invalid numeric parameters gracefully", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/scores")
        .query({ page: "invalid", limit: "not_a_number" })
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body.pagination).toMatchObject({ page: 1, limit: 50 });
    });

    test("should return 500 when the database query fails", async () => {
      query.mockRejectedValueOnce(new Error("connection lost"));

      const response = await request(app)
        .get("/scores")
        .set("Authorization", "Bearer test-token")
        .expect(500);

      expect(response.body).toHaveProperty("success", false);
      expect(response.body.message).toContain("Failed to fetch scores");
    });
  });
  // NOTE: /:symbol is a simple `SELECT * FROM stock_scores WHERE symbol = $1` -
  // sendSuccess(res, result.rows[0]) with whatever columns that returns, not a
  // factors/performance/metadata-shaped object (that richer per-symbol shape doesn't
  // exist in the current route).
  describe("GET /scores/:symbol", () => {
    test("should return the raw stock_scores row for a known symbol", async () => {
      query.mockResolvedValueOnce({
        rows: [{ symbol: "AAPL", composite_score: 52.13 }],
      });

      const response = await request(app)
        .get("/scores/AAPL")
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body.data).toEqual({
        symbol: "AAPL",
        composite_score: 52.13,
      });
      expect(query).toHaveBeenCalledWith(expect.any(String), ["AAPL"]);
    });

    test("should uppercase a lowercase symbol before querying", async () => {
      query.mockResolvedValueOnce({
        rows: [{ symbol: "AAPL", composite_score: 52.13 }],
      });

      await request(app)
        .get("/scores/aapl")
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(query).toHaveBeenCalledWith(expect.any(String), ["AAPL"]);
    });

    test("should 404 for a symbol with no scores", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/scores/ZZZNONEXISTENT123")
        .set("Authorization", "Bearer test-token")
        .expect(404);

      expect(response.body).toHaveProperty("success", false);
      expect(response.body.message).toContain(
        "No scores found for symbol ZZZNONEXISTENT123"
      );
    });

    test("should 500 when the database query fails", async () => {
      query.mockRejectedValueOnce(new Error("connection lost"));

      const response = await request(app)
        .get("/scores/TEST")
        .set("Authorization", "Bearer test-token")
        .expect(500);

      expect(response.body).toHaveProperty("success", false);
      expect(response.body.message).toContain("Failed to fetch score");
    });
  });
  describe("Response format and data validation", () => {
    test("should return consistent JSON response format", async () => {
      query.mockResolvedValueOnce({ rows: [] });

      const response = await request(app)
        .get("/scores")
        .set("Authorization", "Bearer test-token")
        .expect(200);
      expect(response.headers["content-type"]).toMatch(/json/);
      expect(typeof response.body).toBe("object");
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("items");
      expect(response.body).toHaveProperty("pagination");
      expect(response.body).toHaveProperty("timestamp");
    });

    test("should validate score data types and ranges", async () => {
      query.mockResolvedValueOnce({
        rows: [
          {
            symbol: "AAPL",
            composite_score: 52.13,
            momentum_score: 67.92,
            value_score: 17.75,
            quality_score: 60.66,
            growth_score: 68.94,
            stability_score: 58.74,
            total_count: "1",
          },
        ],
      });

      const response = await request(app)
        .get("/scores")
        .set("Authorization", "Bearer test-token")
        .expect(200);

      const stock = response.body.items[0];
      for (const field of [
        "composite_score",
        "momentum_score",
        "value_score",
        "quality_score",
        "growth_score",
        "stability_score",
      ]) {
        expect(typeof stock[field]).toBe("number");
        expect(stock[field]).toBeGreaterThanOrEqual(0);
        expect(stock[field]).toBeLessThanOrEqual(100);
      }
    });
  });
  // "Growth metrics validation" and "Value metrics schema validation" were removed:
  // both tested a factors.quality/factors.growth/factors.value.inputs nested response
  // shape (13 quality inputs, 12 growth metrics, sector/market benchmarks) that doesn't
  // exist in either the "/" list endpoint (only symbol + 6 score columns) or "/:symbol"
  // (a raw `SELECT *` row, not a factors-shaped object) - see routes/scores.js.
});
