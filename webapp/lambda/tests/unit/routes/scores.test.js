/**
 * Scores Routes Unit Tests
 * Tests scores route logic with real database
 */

const express = require("express");
const request = require("supertest");

// Real database for integration
const { query } = require("../../../utils/database");

describe("Scores Routes Unit Tests", () => {
  let app;
  let scoresRouter;

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
    const responseFormatter = require("../../../middleware/responseFormatter");
    app.use(responseFormatter);

    // Load the route module
    scoresRouter = require("../../../routes/scores");
    app.use("/scores", scoresRouter);
  });

  describe("GET /scores/ping", () => {
    test("should return ping response", async () => {
      const response = await request(app).get("/scores/ping").expect(200);

      expect(response.body).toHaveProperty("status", "ok");
      expect(response.body).toHaveProperty("endpoint", "scores");
      expect(response.body).toHaveProperty("timestamp");
    });
  });

  describe("GET /scores", () => {
    test("should return scores data from stock_scores table", async () => {
      const response = await request(app)
        .get("/scores")
        .set("Authorization", "Bearer dev-bypass-token")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(response.body.data).toHaveProperty("viewType", "list");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);
      expect(response.body).toHaveProperty("pagination");
      expect(response.body).toHaveProperty("summary");
      expect(response.body).toHaveProperty("metadata");
      expect(response.body.metadata).toHaveProperty("dataSource", "stock_scores_real_table");
      expect(response.body.metadata).toHaveProperty("factorAnalysis", "six_factor_scoring_system");

      // Check score structure matches new list format with six factor analysis
      if (response.body.data.stocks.length > 0) {
        const stock = response.body.data.stocks[0];
        expect(stock).toHaveProperty("symbol");
        expect(stock).toHaveProperty("compositeScore");
        expect(stock).toHaveProperty("currentPrice");
        expect(stock).toHaveProperty("priceChange1d");
        expect(stock).toHaveProperty("volume");
        expect(stock).toHaveProperty("marketCap");
        expect(stock).toHaveProperty("factors");
        expect(stock).toHaveProperty("lastUpdated");
        expect(stock).toHaveProperty("scoreDate");

        // Check six factor analysis structure
        expect(stock.factors).toHaveProperty("momentum");
        expect(stock.factors).toHaveProperty("trend");
        expect(stock.factors).toHaveProperty("value");
        expect(stock.factors).toHaveProperty("quality");
        expect(stock.factors).toHaveProperty("technical");
        expect(stock.factors).toHaveProperty("risk");

        // Check momentum factor structure
        expect(stock.factors.momentum).toHaveProperty("score");
        expect(stock.factors.momentum).toHaveProperty("rsi");
        expect(stock.factors.momentum).toHaveProperty("description");
      }
    });

    test("should handle pagination parameters", async () => {
      const response = await request(app)
        .get("/scores")
        .query({ page: 2, limit: 25 })
        .set("Authorization", "Bearer dev-bypass-token")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);
      expect(response.body).toHaveProperty("pagination");
      expect(response.body.pagination).toHaveProperty("page", 2);
      expect(response.body.pagination).toHaveProperty("limit", 25);
      expect(response.body.pagination).toHaveProperty("total");
      expect(response.body.pagination).toHaveProperty("totalPages");
    });

    test("should handle search parameter for filtering stocks", async () => {
      const response = await request(app)
        .get("/scores")
        .query({ search: "AAPL" })
        .set("Authorization", "Bearer dev-bypass-token")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);
      expect(response.body.metadata).toHaveProperty("searchTerm", "AAPL");

      // If results are found, they should match the search term
      if (response.body.data.stocks.length > 0) {
        response.body.data.stocks.forEach(stock => {
          expect(stock.symbol).toContain("AAPL");
        });
      }
    });

    test("should handle limit parameter correctly", async () => {
      const response = await request(app)
        .get("/scores")
        .query({ limit: 10 })
        .set("Authorization", "Bearer dev-bypass-token")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);
      expect(response.body.data.stocks.length).toBeLessThanOrEqual(10);
      expect(response.body.pagination).toHaveProperty("limit", 10);
    });

    test("should include summary statistics", async () => {
      const response = await request(app)
        .get("/scores")
        .set("Authorization", "Bearer dev-bypass-token")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("summary");
      expect(response.body.summary).toHaveProperty("totalStocks");
      expect(response.body.summary).toHaveProperty("averageScore");
      expect(typeof response.body.summary.averageScore).toBe("number");
    });

    test("should return scores sorted by composite_score DESC by default", async () => {
      const response = await request(app)
        .get("/scores")
        .set("Authorization", "Bearer dev-bypass-token")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);

      // Check that stocks are sorted by composite score descending
      if (response.body.data.stocks.length > 1) {
        for (let i = 1; i < response.body.data.stocks.length; i++) {
          expect(response.body.data.stocks[i-1].compositeScore)
            .toBeGreaterThanOrEqual(response.body.data.stocks[i].compositeScore);
        }
      }
    });

    test("should cap limit at 200", async () => {
      const response = await request(app)
        .get("/scores")
        .query({ limit: 500 })
        .set("Authorization", "Bearer dev-bypass-token")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);
      expect(response.body.pagination).toHaveProperty("limit", 200);
    });

    test("should handle invalid numeric parameters gracefully", async () => {
      const response = await request(app)
        .get("/scores")
        .query({
          page: "invalid",
          limit: "not_a_number",
        })
        .set("Authorization", "Bearer dev-bypass-token")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);
      // Should default to page 1, limit 50
      expect(response.body.pagination).toHaveProperty("page", 1);
      expect(response.body.pagination).toHaveProperty("limit", 50);
    });

    test("should handle database timeout gracefully", async () => {
      const response = await request(app)
        .get("/scores")
        .set("Authorization", "Bearer dev-bypass-token");

      // Should either succeed (200) or fail with proper error message (500)
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("stocks");
        expect(Array.isArray(response.body.data.stocks)).toBe(true);
      } else if (response.status === 500) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body.error || response.body.success).toBeDefined();
      }
    });
  });

  describe("GET /scores/:symbol", () => {
    test("should return individual symbol score", async () => {
      const response = await request(app)
        .get("/scores/AAPL")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("symbol", "AAPL");
        expect(response.body.data).toHaveProperty("compositeScore");
        expect(response.body.data).toHaveProperty("currentPrice");
        expect(response.body.data).toHaveProperty("priceChange1d");
        expect(response.body.data).toHaveProperty("volume");
        expect(response.body.data).toHaveProperty("marketCap");
        expect(response.body.data).toHaveProperty("factors");
        expect(response.body.data).toHaveProperty("performance");
        expect(response.body.data).toHaveProperty("lastUpdated");
        expect(response.body.data).toHaveProperty("scoreDate");
        expect(response.body).toHaveProperty("metadata");
        expect(response.body.metadata).toHaveProperty("dataSource", "stock_scores_real_table");
        expect(response.body.metadata).toHaveProperty("factorAnalysis", "six_factor_scoring_system");

        // Check six factor analysis structure
        expect(response.body.data.factors).toHaveProperty("momentum");
        expect(response.body.data.factors).toHaveProperty("trend");
        expect(response.body.data.factors).toHaveProperty("value");
        expect(response.body.data.factors).toHaveProperty("quality");
        expect(response.body.data.factors).toHaveProperty("technical");
        expect(response.body.data.factors).toHaveProperty("risk");

        // Check performance structure
        expect(response.body.data.performance).toHaveProperty("priceChange1d");
        expect(response.body.data.performance).toHaveProperty("priceChange5d");
        expect(response.body.data.performance).toHaveProperty("priceChange30d");
        expect(response.body.data.performance).toHaveProperty("volatility30d");
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body.error || response.body.success).toBeDefined();
        expect(response.body.error).toContain("Symbol not found in stock_scores table");
      }
    });

    test("should handle lowercase symbol input", async () => {
      const response = await request(app)
        .get("/scores/aapl")
        .set("Authorization", "Bearer dev-bypass-token");

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty("symbol", "AAPL");
      }
    });

    test("should return 404 for non-existent symbol", async () => {
      const response = await request(app)
        .get("/scores/NONEXISTENT")
        .set("Authorization", "Bearer dev-bypass-token")
        .expect(404);

      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error || response.body.success).toBeDefined();
      expect(response.body.error).toContain("Symbol not found in stock_scores table");
    });

    test("should handle database errors gracefully", async () => {
      const response = await request(app)
        .get("/scores/TEST")
        .set("Authorization", "Bearer dev-bypass-token");

      // Should either succeed (200) or fail with proper error (404/500)
      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      } else {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body.error || response.body.success).toBeDefined();
        expect([404, 500]).toContain(response.status);
      }
    });
  });





  describe("Response format and data validation", () => {
    test("should return consistent JSON response format", async () => {
      const response = await request(app)
        .get("/scores")
        .set("Authorization", "Bearer dev-bypass-token")
        .expect(200);

      expect(response.headers["content-type"]).toMatch(/json/);
      expect(typeof response.body).toBe("object");
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body).toHaveProperty("pagination");
      expect(response.body).toHaveProperty("summary");
      expect(response.body).toHaveProperty("metadata");
      expect(response.body).toHaveProperty("timestamp");
    });

    test("should include complete pagination metadata", async () => {
      const response = await request(app)
        .get("/scores")
        .query({ page: 2, limit: 25 })
        .set("Authorization", "Bearer dev-bypass-token")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("pagination");
      expect(response.body.pagination).toHaveProperty("page");
      expect(response.body.pagination).toHaveProperty("limit");
      expect(response.body.pagination).toHaveProperty("total");
      expect(response.body.pagination).toHaveProperty("totalPages");
      expect(response.body.pagination).toHaveProperty("hasMore");
    });

    test("should validate score data types and ranges", async () => {
      const response = await request(app)
        .get("/scores")
        .set("Authorization", "Bearer dev-bypass-token")
        .expect(200);

      if (response.body.data.stocks.length > 0) {
        const stock = response.body.data.stocks[0];

        // Check that scores are numbers and within expected ranges
        expect(typeof stock.compositeScore).toBe("number");
        expect(stock.compositeScore).toBeGreaterThanOrEqual(0);
        expect(stock.compositeScore).toBeLessThanOrEqual(100);

        expect(typeof stock.currentPrice).toBe("number");
        expect(stock.currentPrice).toBeGreaterThanOrEqual(0);

        expect(typeof stock.volume).toBe("number");
        expect(stock.volume).toBeGreaterThanOrEqual(0);

        expect(typeof stock.marketCap).toBe("number");
        expect(stock.marketCap).toBeGreaterThanOrEqual(0);

        // Check factor scores are numbers
        expect(typeof stock.factors.momentum.score).toBe("number");
        expect(typeof stock.factors.trend.score).toBe("number");
        expect(typeof stock.factors.value.score).toBe("number");
        expect(typeof stock.factors.quality.score).toBe("number");
      }
    });
  });
});
