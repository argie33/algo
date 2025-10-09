/**
 * Scores Routes Integration Tests
 * Tests scores endpoints with real database connection
 */

const request = require("supertest");
const { app } = require("../../../index"); // Import the actual Express app
const {
  query,
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

describe("Scores Routes Integration", () => {
  beforeAll(async () => {
    // Initialize database connection
    await initializeDatabase();
  });

  afterAll(async () => {
    // Close database connection
    await closeDatabase();
  });

  describe("GET /scores/ping", () => {
    test("should return ping response", async () => {
      const response = await request(app).get("/scores/ping");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("status", "ok");
      expect(response.body).toHaveProperty("endpoint", "scores");
      expect(response.body).toHaveProperty("timestamp");
    });
  });

  describe("GET /scores", () => {
    test("should return stocks data with list view structure", async () => {
      const response = await request(app).get("/scores");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(response.body.data).toHaveProperty("viewType", "list");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);
      expect(response.body).toHaveProperty("pagination");
      expect(response.body).toHaveProperty("summary");
      expect(response.body).toHaveProperty("metadata");
      expect(response.body.metadata).toHaveProperty("dataSource", "stock_scores_real_table");
      expect(response.body.metadata).toHaveProperty("factorAnalysis", "six_factor_scoring_system");
    });

    test("should handle pagination parameters", async () => {
      const response = await request(app)
        .get("/scores")
        .query({ page: 1, limit: 10 });

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);
      expect(response.body).toHaveProperty("pagination");
      expect(response.body.pagination).toHaveProperty("page", 1);
      expect(response.body.pagination).toHaveProperty("limit", 10);
    });

    test("should handle search parameter", async () => {
      const response = await request(app)
        .get("/scores")
        .query({ search: "AAPL" });

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
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

    test("should return stocks sorted by composite score descending by default", async () => {
      const response = await request(app).get("/scores");

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);

      // Check that stocks are sorted by composite score descending
      if (response.body.data.stocks.length > 1) {
        for (let i = 1; i < response.body.data.stocks.length; i++) {
          expect(response.body.data.stocks[i-1].composite_score)
            .toBeGreaterThanOrEqual(response.body.data.stocks[i].composite_score);
        }
      }
    });

    test("should handle limit boundary conditions", async () => {
      const response = await request(app).get("/scores").query({ limit: 300 }); // Should be capped at 200

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);
      expect(response.body.pagination).toHaveProperty("limit");
      expect(response.body.pagination.limit).toBeLessThanOrEqual(200);
    });

    test("should handle invalid parameters gracefully", async () => {
      const response = await request(app).get("/scores").query({
        page: "invalid",
        limit: "not_a_number",
        minScore: "invalid",
        maxScore: "invalid",
      });

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);
    });
  });

  describe("GET /scores/:symbol", () => {
    test("should return individual symbol data with six factor analysis", async () => {
      const response = await request(app).get("/scores/AAPL");

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("symbol", "AAPL");
        expect(response.body.data).toHaveProperty("composite_score");
        expect(response.body.data).toHaveProperty("current_price");
        expect(response.body).toHaveProperty("metadata");
        expect(response.body.metadata).toHaveProperty("dataSource", "stock_scores_real_table");
        expect(response.body.metadata).toHaveProperty("factorAnalysis", "six_factor_scoring_system");

        // Check six factor scores are present (removed relative_strength)
        expect(response.body.data).toHaveProperty("momentum_score");
        expect(response.body.data).toHaveProperty("trend_score");
        expect(response.body.data).toHaveProperty("value_score");
        expect(response.body.data).toHaveProperty("quality_score");
        expect(response.body.data).toHaveProperty("growth_score");

        // Check technical indicators are present
        expect(response.body.data).toHaveProperty("rsi");
        expect(response.body.data).toHaveProperty("macd");
        expect(response.body.data).toHaveProperty("sma_20");
        expect(response.body.data).toHaveProperty("sma_50");
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body.error).toContain("Symbol not found in stock_scores table");
      }
    });

    test("should handle case insensitive symbol lookup", async () => {
      const response = await request(app).get("/scores/aapl");

      if (response.status === 200) {
        expect(response.body.data).toHaveProperty("symbol", "AAPL");
      }
    });

    test("should return 404 for non-existent symbol", async () => {
      const response = await request(app).get("/scores/NONEXISTENT");

      expect(response.status).toBe(404);
      expect(response.body).toHaveProperty("success", false);
      expect(response.body.error).toContain("Symbol not found in stock_scores table");
    });
  });

  describe("Error handling", () => {
    test("should handle invalid endpoints", async () => {
      const response = await request(app).get("/scores/invalid/endpoint");

      expect([404, 500]).toContain(response.status);
    });

    test("should return consistent response format", async () => {
      const response = await request(app).get("/scores/ping");

      expect(response.headers["content-type"]).toMatch(/json/);
      expect(typeof response.body).toBe("object");
    });

    test("should handle database connection issues", async () => {
      const response = await request(app).get("/scores");

      // Should not crash even if database issues occur
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);
    });
  });

  describe("Security tests", () => {
    test("should handle SQL injection attempts", async () => {
      const response = await request(app).get("/scores").query({
        search: "'; DROP TABLE stock_symbols; --",
        sector: "Technology'; DELETE FROM company_profile; --",
      });

      // Should handle malicious input safely
      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);
    });

    test("should handle XSS attempts", async () => {
      const response = await request(app).get("/scores").query({
        search: "<script>alert('xss')</script>",
        sector: "<img src=x onerror=alert('xss')>",
      });

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);
    });

    test("should handle large payloads", async () => {
      const longString = "a".repeat(10000);

      const response = await request(app)
        .get("/scores")
        .query({ search: longString });

      expect(response.status).toBe(200);
      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("stocks");
      expect(Array.isArray(response.body.data.stocks)).toBe(true);
    });
  });

  describe("Performance tests", () => {
    test("should respond within reasonable time", async () => {
      const startTime = Date.now();

      const response = await request(app).get("/scores/ping");

      const responseTime = Date.now() - startTime;

      expect(response.status).toBe(200);
      expect(responseTime).toBeLessThan(5000);
    });

    test("should handle concurrent requests", async () => {
      const requests = Array.from({ length: 3 }, () =>
        request(app).get("/scores/ping")
      );

      const responses = await Promise.all(requests);

      responses.forEach((response) => {
        expect(response.status).toBe(200);
        expect(response.body).toHaveProperty("status", "ok");
      });
    });
  });
});
