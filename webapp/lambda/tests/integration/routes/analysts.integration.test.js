/**
 * Simplified Analyst Routes Integration Tests
 * Tests the simplified analyst routes using real database connections
 */

const request = require("supertest");
const { app } = require("../../../index");

describe("Simplified Analyst Routes Integration Tests", () => {

  describe("GET /api/analysts", () => {
    test("should return simplified analyst API overview", async () => {
      const response = await request(app)
        .get("/api/analysts")
        .expect(200);

      expect(response.body).toHaveProperty("message", "Analysts API - Real Database Data Only");
      expect(response.body).toHaveProperty("status", "operational");
      expect(response.body).toHaveProperty("endpoints");
      expect(Array.isArray(response.body.endpoints)).toBe(true);
    });
  });

  describe("GET /api/analysts/upgrades", () => {
    test("should return analyst upgrades from database", async () => {
      const response = await request(app)
        .get("/api/analysts/upgrades?limit=5")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(response.body).toHaveProperty("pagination");

      if (response.body.data.length > 0) {
        const upgrade = response.body.data[0];
        expect(upgrade).toHaveProperty("id");
        expect(upgrade).toHaveProperty("symbol");
        expect(upgrade).toHaveProperty("firm");
        expect(upgrade).toHaveProperty("action");
        expect(upgrade).toHaveProperty("from_grade");
        expect(upgrade).toHaveProperty("to_grade");
        expect(upgrade).toHaveProperty("date");
        expect(upgrade).toHaveProperty("details");
        expect(upgrade).toHaveProperty("analyst_name");
      }
    });

    test("should handle pagination", async () => {
      const response = await request(app)
        .get("/api/analysts/upgrades?page=1&limit=2")
        .expect(200);

      expect(response.body.pagination).toHaveProperty("page", 1);
      expect(response.body.pagination).toHaveProperty("limit", 2);
      expect(response.body.pagination).toHaveProperty("total");
      expect(response.body.pagination).toHaveProperty("totalPages");
    });
  });

  describe("GET /api/analysts/price-targets", () => {
    test("should return price targets from database", async () => {
      const response = await request(app)
        .get("/api/analysts/price-targets")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body).toHaveProperty("count");
      expect(Array.isArray(response.body.data)).toBe(true);

      if (response.body.data.length > 0) {
        const target = response.body.data[0];
        expect(target).toHaveProperty("symbol");
        expect(target).toHaveProperty("analyst_firm");
        expect(target).toHaveProperty("target_price");
        expect(target).toHaveProperty("target_date");
      }
    });
  });

  describe("GET /api/analysts/estimates", () => {
    test("should return estimates from database", async () => {
      const response = await request(app)
        .get("/api/analysts/estimates")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body).toHaveProperty("count");
      expect(Array.isArray(response.body.data)).toBe(true);

      if (response.body.data.length > 0) {
        const estimate = response.body.data[0];
        expect(estimate).toHaveProperty("ticker");
        expect(estimate).toHaveProperty("target_mean_price");
        expect(estimate).toHaveProperty("recommendation_key");
      }
    });
  });

  describe("GET /api/analysts/recommendations", () => {
    test("should return recommendations from database", async () => {
      const response = await request(app)
        .get("/api/analysts/recommendations")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body).toHaveProperty("count");
      expect(Array.isArray(response.body.data)).toBe(true);
    });
  });

  describe("GET /api/analysts/coverage", () => {
    test("should return coverage from database", async () => {
      const response = await request(app)
        .get("/api/analysts/coverage")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body).toHaveProperty("count");
      expect(Array.isArray(response.body.data)).toBe(true);
    });
  });

  describe("GET /api/analysts/sentiment", () => {
    test("should return sentiment analysis from database", async () => {
      const response = await request(app)
        .get("/api/analysts/sentiment")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body).toHaveProperty("count");
      expect(Array.isArray(response.body.data)).toBe(true);
    });
  });

  describe("GET /api/analysts/:symbol/data", () => {
    test("should return all analyst data for AAPL", async () => {
      const response = await request(app)
        .get("/api/analysts/AAPL/data")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("symbol", "AAPL");
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("upgrades_downgrades");
      expect(response.body.data).toHaveProperty("price_targets");
      expect(response.body.data).toHaveProperty("estimates");
      expect(response.body).toHaveProperty("counts");

      expect(Array.isArray(response.body.data.upgrades_downgrades)).toBe(true);
      expect(Array.isArray(response.body.data.price_targets)).toBe(true);
      expect(Array.isArray(response.body.data.estimates)).toBe(true);
    });

    test("should handle lowercase symbol", async () => {
      const response = await request(app)
        .get("/api/analysts/aapl/data")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("symbol", "AAPL");
    });

    test("should handle symbols with no data", async () => {
      const response = await request(app)
        .get("/api/analysts/INVALID/data")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("symbol", "INVALID");
      expect(response.body.data.upgrades_downgrades).toHaveLength(0);
      expect(response.body.data.price_targets).toHaveLength(0);
      expect(response.body.data.estimates).toHaveLength(0);
    });
  });

  describe("Error Handling", () => {
    test("should handle invalid routes gracefully", async () => {
      const response = await request(app)
        .get("/api/analysts/invalid-endpoint")
        .expect(404);
    });
  });

  describe("Data Validation", () => {
    test("should return valid timestamps", async () => {
      const response = await request(app)
        .get("/api/analysts/upgrades?limit=1")
        .expect(200);

      expect(response.body).toHaveProperty("timestamp");
      expect(new Date(response.body.timestamp).getTime()).not.toBeNaN();
    });

    test("should return consistent data structure", async () => {
      const response = await request(app)
        .get("/api/analysts/price-targets")
        .expect(200);

      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("data");
      expect(response.body).toHaveProperty("count");
      expect(response.body).toHaveProperty("timestamp");
    });
  });

  describe("Performance", () => {
    test("should respond within reasonable time", async () => {
      const startTime = Date.now();

      await request(app)
        .get("/api/analysts/upgrades?limit=10")
        .expect(200);

      const responseTime = Date.now() - startTime;
      expect(responseTime).toBeLessThan(5000); // 5 second timeout
    });
  });
});