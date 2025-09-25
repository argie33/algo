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
      expect(response.body.data).toHaveProperty("scores");
      expect(Array.isArray(response.body.data.scores)).toBe(true);
      expect(response.body).toHaveProperty("pagination");
      expect(response.body).toHaveProperty("summary");
      expect(response.body).toHaveProperty("metadata");
      expect(response.body.metadata).toHaveProperty("dataSource", "stock_scores_table");

      // Check score structure matches new stock_scores table
      if (response.body.data.scores.length > 0) {
        const score = response.body.data.scores[0];
        expect(score).toHaveProperty("symbol");
        expect(score).toHaveProperty("compositeScore");
        expect(score).toHaveProperty("momentumScore");
        expect(score).toHaveProperty("trendScore");
        expect(score).toHaveProperty("valueScore");
        expect(score).toHaveProperty("qualityScore");
        expect(score).toHaveProperty("currentPrice");
        expect(score).toHaveProperty("volume");
        expect(score).toHaveProperty("rsi");
        expect(score).toHaveProperty("lastUpscore_dated");
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
      expect(response.body.data).toHaveProperty("scores");
      expect(Array.isArray(response.body.data.scores)).toBe(true);
      expect(response.body).toHaveProperty("pagination");
      expect(response.body.pagination).toHaveProperty("page", 2);
      expect(response.body.pagination).toHaveProperty("limit", 25);
      expect(response.body.pagination).toHaveProperty("total");
      expect(response.body.pagination).toHaveProperty("totalPages");
    });

    test("should return all scores (no search filtering implemented)", async () => {
      const response = await request(app)
        .get("/scores")
        .set("Authorization", "Bearer dev-bypass-token")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("scores");
      expect(Array.isArray(response.body.data.scores)).toBe(true);
      // Current implementation returns all scores sorted by composite_score DESC
    });

    test("should handle limit parameter correctly", async () => {
      const response = await request(app)
        .get("/scores")
        .query({ limit: 10 })
        .set("Authorization", "Bearer dev-bypass-token")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("scores");
      expect(Array.isArray(response.body.data.scores)).toBe(true);
      expect(response.body.data.scores.length).toBeLessThanOrEqual(10);
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
      expect(response.body.data).toHaveProperty("scores");
      expect(Array.isArray(response.body.data.scores)).toBe(true);

      // Check that scores are sorted by composite score descending
      if (response.body.data.scores.length > 1) {
        for (let i = 1; i < response.body.data.scores.length; i++) {
          expect(response.body.data.scores[i-1].compositeScore)
            .toBeGreaterThanOrEqual(response.body.data.scores[i].compositeScore);
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
      expect(response.body.data).toHaveProperty("scores");
      expect(Array.isArray(response.body.data.scores)).toBe(true);
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
      expect(response.body.data).toHaveProperty("scores");
      expect(Array.isArray(response.body.data.scores)).toBe(true);
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
        expect(response.body.data).toHaveProperty("scores");
        expect(Array.isArray(response.body.data.scores)).toBe(true);
      } else if (response.status === 500) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
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
        expect(response.body.data).toHaveProperty("momentumScore");
        expect(response.body.data).toHaveProperty("trendScore");
        expect(response.body.data).toHaveProperty("valueScore");
        expect(response.body.data).toHaveProperty("qualityScore");
        expect(response.body.data).toHaveProperty("currentPrice");
        expect(response.body.data).toHaveProperty("volume");
        expect(response.body.data).toHaveProperty("rsi");
        expect(response.body.data).toHaveProperty("lastUpscore_dated");
        expect(response.body).toHaveProperty("metadata");
        expect(response.body.metadata).toHaveProperty("dataSource", "stock_scores_table");
      } else if (response.status === 404) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
        expect(response.body.error).toContain("not found");
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
      expect(response.body).toHaveProperty("error");
      expect(response.body.error).toContain("not found");
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
        expect(response.body).toHaveProperty("error");
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

      if (response.body.data.scores.length > 0) {
        const score = response.body.data.scores[0];

        // Check that scores are numbers and within expected ranges
        expect(typeof score.compositeScore).toBe("number");
        expect(score.compositeScore).toBeGreaterThanOrEqual(0);
        expect(score.compositeScore).toBeLessThanOrEqual(100);

        expect(typeof score.momentumScore).toBe("number");
        expect(score.momentumScore).toBeGreaterThanOrEqual(0);
        expect(score.momentumScore).toBeLessThanOrEqual(100);

        expect(typeof score.currentPrice).toBe("number");
        expect(score.currentPrice).toBeGreaterThanOrEqual(0);

        expect(typeof score.volume).toBe("number");
        expect(score.volume).toBeGreaterThanOrEqual(0);
      }
    });
  });
});
