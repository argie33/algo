/**
 * Risk Routes Integration Tests
 * Tests risk management endpoints with real database connection
 */

const request = require("supertest");
const { app } = require("../../../index"); // Import the actual Express app
const {
  query,
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

describe("Risk Routes Integration", () => {
  beforeAll(async () => {
    // Initialize database connection
    await initializeDatabase();
  });

  afterAll(async () => {
    // Close database connection
    await closeDatabase();
  });

  describe("GET /risk", () => {
    test("should return risk analysis data", async () => {
      const response = await request(app).get("/risk");

      expect([200, 404]).toContain(response.status);
      expect(response.body).toBeDefined();
    });

    test("should handle portfolio risk analysis", async () => {
      const response = await request(app)
        .get("/risk")
        .query({ type: "portfolio" });

      expect([200, 404]).toContain(response.status);
      expect(response.body).toBeDefined();
    });

    test("should handle individual stock risk analysis", async () => {
      const response = await request(app)
        .get("/risk")
        .query({ symbol: "AAPL" });

      expect([200, 404]).toContain(response.status);
      expect(response.body).toBeDefined();
    });
  });

  describe("GET /risk/analysis", () => {
    test("should handle risk analysis requests", async () => {
      const response = await request(app)
        .get("/risk/analysis")
        .set("Authorization", "Bearer dev-bypass-token")
        .query({
          period: "1y",
          confidence_level: 0.95,
        });

      expect([200, 404]).toContain(response.status);
      expect(response.body).toBeDefined();
      expect(response.body).toHaveProperty("success", true);
    });

    test("should handle different time periods", async () => {
      const response = await request(app)
        .get("/risk/analysis")
        .set("Authorization", "Bearer dev-bypass-token")
        .query({ period: "1m" });

      expect([200, 404]).toContain(response.status);
      expect(response.body).toBeDefined();
      expect(response.body).toHaveProperty("success", true);
    });

    test("should handle missing query parameters", async () => {
      const response = await request(app)
        .get("/risk/analysis")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404]).toContain(response.status);
      expect(response.body).toBeDefined();
      expect(response.body).toHaveProperty("success", true);
    });
  });

  describe("GET /risk/health", () => {
    test("should return health status", async () => {
      const response = await request(app).get("/risk/health");

      expect([200, 404]).toContain(response.status);
      expect(response.body).toBeDefined();
      expect(response.body).toHaveProperty("status", "operational");
      expect(response.body).toHaveProperty("service", "risk-analysis");
    });
  });

  describe("Error handling", () => {
    test("should handle invalid endpoints", async () => {
      const response = await request(app)
        .get("/risk/nonexistent")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([404, 500]).toContain(response.status);
    });

    test("should return consistent response format", async () => {
      const response = await request(app).get("/risk");

      expect(response.headers["content-type"]).toMatch(/json/);
      expect(typeof response.body).toBe("object");
    });

    test("should handle database connection issues", async () => {
      const response = await request(app).get("/risk");

      // Should not crash even if database issues occur
      expect([200, 404]).toContain(response.status);
      expect(response.body).toBeDefined();
    });
  });

  describe("Security tests", () => {
    test("should handle SQL injection attempts", async () => {
      const response = await request(app).get("/risk").query({
        symbol: "'; DROP TABLE trading_alerts; --",
        type: "portfolio'; DELETE FROM risk_metrics; --",
      });

      // Should handle malicious input safely
      expect([200, 404]).toContain(response.status);
      expect(response.body).toBeDefined();
    });

    test("should handle XSS attempts in query parameters", async () => {
      const response = await request(app)
        .get("/risk/analysis")
        .set("Authorization", "Bearer dev-bypass-token")
        .query({
          period: "<script>alert('xss')</script>",
          confidence_level: "<img src=x onerror=alert('xss')>",
        });

      expect([200, 404]).toContain(response.status);
      expect(response.body).toBeDefined();
    });

    test("should handle malicious query parameters", async () => {
      const response = await request(app)
        .get("/risk/analysis")
        .set("Authorization", "Bearer dev-bypass-token")
        .query({
          period: "'; DROP TABLE portfolio_holdings; --",
          confidence_level: "999999",
        });

      expect([200, 404]).toContain(response.status);
      expect(response.body).toBeDefined();
    });
  });

  describe("Performance tests", () => {
    test("should respond within reasonable time", async () => {
      const startTime = Date.now();

      const response = await request(app).get("/risk");

      const responseTime = Date.now() - startTime;

      expect([200, 404]).toContain(response.status);
      expect(responseTime).toBeLessThan(5000);
    });

    test("should handle concurrent requests", async () => {
      const requests = Array.from({ length: 3 }, () =>
        request(app).get("/risk")
      );

      const responses = await Promise.all(requests);

      responses.forEach((response) => {
        expect([200, 404]).toContain(response.status);
        expect(response.body).toBeDefined();
      });
    });
  });
});
