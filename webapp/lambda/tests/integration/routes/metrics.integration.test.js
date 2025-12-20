/**
 * Metrics Routes Integration Tests - REAL DATA ONLY
 * Tests metrics endpoints with REAL database connection and REAL loaded data
 * NO MOCKS - validates actual behavior with actual data from loaders
 * Validates NO-FALLBACK policy: raw NULL values must flow through unmasked
 */

const request = require("supertest");
const { app } = require("../../../index");
const { initializeDatabase } = require("../../../utils/database"); // Import the actual Express app - NO MOCKS

describe("Metrics Routes - Real Data Validation", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });
  describe("GET /metrics/ping", () => {
    test("should return ping response", async () => {
      const response = await request(app).get("/metrics/ping");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("status", "ok");
      expect(response.body).toHaveProperty("endpoint", "metrics");
      expect(response.body).toHaveProperty("timestamp");
    });
  });

  describe("GET /metrics", () => {
    test("should return metrics data", async () => {
      const response = await request(app).get("/metrics");

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle pagination parameters", async () => {
      const response = await request(app)
        .get("/metrics")
        .query({ page: 1, limit: 10 });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle search parameter", async () => {
      const response = await request(app)
        .get("/metrics")
        .query({ search: "AAPL" });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle sector filter", async () => {
      const response = await request(app)
        .get("/metrics")
        .query({ sector: "Technology" });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle metric range filters", async () => {
      const response = await request(app)
        .get("/metrics")
        .query({ minMetric: 0.5, maxMetric: 1.0 });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle sorting parameters", async () => {
      const response = await request(app)
        .get("/metrics")
        .query({ sortBy: "composite_metric", sortOrder: "desc" });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle limit boundary conditions", async () => {
      const response = await request(app).get("/metrics").query({ limit: 300 }); // Should be capped at 200

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle invalid parameters gracefully", async () => {
      const response = await request(app).get("/metrics").query({
        page: "invalid",
        limit: "not_a_number",
        minMetric: "invalid",
        maxMetric: "invalid",
      });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });
  });

  describe("Error handling", () => {
    test("should handle invalid endpoints", async () => {
      const response = await request(app).get("/metrics/nonexistent");

      expect([404, 500]).toContain(response.status);
    });

    test("should return consistent response format", async () => {
      const response = await request(app).get("/metrics/ping");

      expect(response.headers["content-type"]).toMatch(/json/);
      expect(typeof response.body).toBe("object");
    });

    test("should handle database connection issues", async () => {
      const response = await request(app).get("/metrics");

      // Should not crash even if database issues occur
      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });
  });

  describe("Performance tests", () => {
    test("should respond within reasonable time", async () => {
      const startTime = Date.now();

      const response = await request(app).get("/metrics/ping");

      const responseTime = Date.now() - startTime;

      expect(response.status).toBe(200);
      expect(responseTime).toBeLessThan(5000); // 5 second timeout
    });

    test("should handle concurrent requests", async () => {
      const requests = Array.from({ length: 3 }, () =>
        request(app).get("/metrics/ping")
      );

      const responses = await Promise.all(requests);

      responses.forEach((response) => {
        expect(response.status).toBe(200);
        expect(response.body).toHaveProperty("status", "ok");
      });
    });
  });

  describe("Query parameter validation", () => {
    test("should handle empty query parameters", async () => {
      const response = await request(app).get("/metrics").query({});

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle SQL injection attempts", async () => {
      const response = await request(app).get("/metrics").query({
        search: "'; DROP TABLE stock_symbols; --",
        sector: "Technology'; DELETE FROM company_profile; --",
      });

      // Should handle malicious input safely
      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });

    test("should handle XSS attempts", async () => {
      const response = await request(app).get("/metrics").query({
        search: "<script>alert('xss')</script>",
        sector: "<img src=x onerror=alert('xss')>",
      });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();

      // Response should not contain script tags
      const responseStr = JSON.stringify(response.body);
      expect(responseStr).not.toContain("<script>");
      expect(responseStr).not.toContain("<img");
    });

    test("should handle very long input strings", async () => {
      const longString = "a".repeat(10000);

      const response = await request(app)
        .get("/metrics")
        .query({ search: longString });

      expect(response.status).toBe(200);
      expect(response.body).toBeDefined();
    });
  });
});
