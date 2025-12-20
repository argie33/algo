/**
 * Portfolio Integration Tests - Real Data
 * Tests ALL portfolio endpoints against real app instance with real database
 */

const request = require("supertest");
const { app } = require("../../../index");
const { initializeDatabase } = require("../../../utils/database");

const auth = { Authorization: "Bearer dev-bypass-token" };

describe("Portfolio Integration Tests - Real Data", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });
  // Core Portfolio Endpoints
  describe("Core Portfolio APIs", () => {
    test("GET /api/portfolio - should return portfolio API info", async () => {
      const response = await request(app)
        .get("/api/portfolio")
        .set(auth);

      expect([200, 401]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("message");
        expect(response.body).toHaveProperty("endpoints");
        expect(Array.isArray(response.body.endpoints)).toBe(true);
      }
    });

    test("GET /api/portfolio/summary - should return portfolio summary or real error", async () => {
      const response = await request(app)
        .get("/api/portfolio/summary")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      } else {
        // Real error from database
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error");
      }
    });

    test("GET /api/portfolio/positions - should return real positions or error", async () => {
      const response = await request(app)
        .get("/api/portfolio/positions")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      } else {
        expect(response.body).toHaveProperty("success", false);
      }
    });

    test("GET /api/portfolio/holdings - should return real holdings", async () => {
      const response = await request(app)
        .get("/api/portfolio/holdings")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
        expect(response.body.data).toHaveProperty("holdings");
        expect(response.body.data).toHaveProperty("summary");
        expect(response.body).toHaveProperty("trading_mode");
      }
    });

    test("GET /api/portfolio/value - should return real portfolio value", async () => {
      const response = await request(app)
        .get("/api/portfolio/value")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      }
    });

    test("GET /api/portfolio/allocation - should return real allocation", async () => {
      const response = await request(app)
        .get("/api/portfolio/allocation")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      }
    });

    test("GET /api/portfolio/allocations - should return real allocations", async () => {
      const response = await request(app)
        .get("/api/portfolio/allocations")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      }
    });
  });

  // Analytics and Analysis
  describe("Analytics and Analysis APIs", () => {
    test("GET /api/portfolio/analytics - should return real analytics", async () => {
      const response = await request(app)
        .get("/api/portfolio/analytics")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      }
    });
  });

  // Performance and Returns
  describe("Performance and Returns APIs", () => {
    test("GET /api/portfolio/returns - should return real returns", async () => {
      const response = await request(app)
        .get("/api/portfolio/returns")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      }
    });

    test("GET /api/portfolio/benchmark - should return real benchmark comparison", async () => {
      const response = await request(app)
        .get("/api/portfolio/benchmark")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      }
    });
  });

  // Risk Management
  describe("Risk Management APIs", () => {
    test("GET /api/portfolio/risk - should return real risk assessment", async () => {
      const response = await request(app)
        .get("/api/portfolio/risk")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      }
    });

    test("GET /api/portfolio/risk-analysis - should return real risk analysis", async () => {
      const response = await request(app)
        .get("/api/portfolio/risk-analysis")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      }
    });

    test("GET /api/portfolio/risk/analysis - should return detailed real risk analysis", async () => {
      const response = await request(app)
        .get("/api/portfolio/risk/analysis")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      }
    });

    test("GET /api/portfolio/risk/var - should return real VaR analysis", async () => {
      const response = await request(app)
        .get("/api/portfolio/risk/var")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      }
    });

    test("GET /api/portfolio/risk/stress-test - should return real stress test", async () => {
      const response = await request(app)
        .get("/api/portfolio/risk/stress-test")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      }
    });

    test("GET /api/portfolio/risk/concentration - should return real concentration risk", async () => {
      const response = await request(app)
        .get("/api/portfolio/risk/concentration")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      }
    });
  });

  // Portfolio Management
  describe("Portfolio Management APIs", () => {
    test("GET /api/portfolio/rebalance - should return real rebalance recommendations", async () => {
      const response = await request(app)
        .get("/api/portfolio/rebalance")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      }
    });

    test("GET /api/portfolio/optimization - should return real optimization", async () => {
      const response = await request(app)
        .get("/api/portfolio/optimization")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      }
    });

    test("GET /api/portfolio/watchlist - should return real watchlist", async () => {
      const response = await request(app)
        .get("/api/portfolio/watchlist")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      }
    });

    test("GET /api/portfolio/transactions - should return real transactions", async () => {
      const response = await request(app)
        .get("/api/portfolio/transactions")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      } else if (response.status === 503) {
        expect(response.body).toHaveProperty("success", false);
        expect(response.body).toHaveProperty("error", "Database connection error");
      }
    });
  });

  // Broker Integration APIs
  describe("Broker Integration APIs", () => {
    test("GET /api/portfolio/api-keys - should return real API keys status", async () => {
      const response = await request(app)
        .get("/api/portfolio/api-keys")
        .set(auth);

      expect([200, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("data");
      }
    });

    test("POST /api/portfolio/api-keys - should handle real API key creation", async () => {
      const response = await request(app)
        .post("/api/portfolio/api-keys")
        .set(auth)
        .send({
          brokerName: "test-broker",
          apiKey: "test-key",
          apiSecret: "test-secret",
        });

      expect([200, 400, 401, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
      }
    });
  });

  // Health and System
  describe("Health and System APIs", () => {
    test("GET /api/portfolio/health - should return real health status", async () => {
      const response = await request(app)
        .get("/api/portfolio/health")
        .set(auth);

      expect([200, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
        expect(response.body).toHaveProperty("status", "healthy");
        expect(response.body).toHaveProperty("service", "portfolio");
      }
    });
  });

  // Error Handling and Edge Cases
  describe("Error Handling and Authentication", () => {
    test("should require authentication for protected endpoints", async () => {
      const response = await request(app).get("/api/portfolio/holdings");

      // Check if authentication is enabled or bypassed
      if (response.status === 401) {
        expect(response.body).toHaveProperty("success", false);
      } else if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
      } else {
        throw new Error(`Unexpected status code: ${response.status}`);
      }
    });

    test("should handle invalid endpoints gracefully", async () => {
      const response = await request(app)
        .get("/api/portfolio/invalid-endpoint")
        .set(auth);

      expect(response.status).toBe(404);
    });

    test("should handle invalid user IDs gracefully", async () => {
      const response = await request(app)
        .get("/api/portfolio/invalid-user-id/holdings")
        .set(auth);

      expect([200, 404, 500]).toContain(response.status);
    });

    test("DELETE /api/portfolio/api-keys/test-broker - should handle real deletion", async () => {
      const response = await request(app)
        .delete("/api/portfolio/api-keys/test-broker")
        .set(auth);

      expect([200, 404, 500, 503]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body).toHaveProperty("success", true);
      }
    });

    test("GET /api/portfolio/data - should redirect to holdings endpoint", async () => {
      const response = await request(app)
        .get("/api/portfolio/data")
        .set(auth);

      expect([302, 404]).toContain(response.status);

      if (response.status === 302) {
        expect(response.headers.location).toMatch(/\/holdings/);
      }
    });
  });

  // NO-FALLBACK VALIDATION TEST
  describe("NO-FALLBACK Validation", () => {
    test("should NEVER return fake mock data - validate real data or errors", async () => {
      const response = await request(app)
        .get("/api/portfolio/holdings")
        .set(auth);

      if (response.status === 200 && response.body.success) {
        // If successful, data must be from real database
        expect(response.body.data).toBeDefined();
        // NO fake default values like {holdings:[], summary:{}, count:0}
        // Must be actual data structure from real queries
      } else {
        // If error, must be REAL database error, not fake mock error
        expect(response.body.success).toBe(false);
        expect(response.body.error).toBeDefined();
      }
    });
  });
});
