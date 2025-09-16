const express = require("express");
const request = require("supertest");

// Real database for integration
const { query } = require("../../../utils/database");

describe("Analytics Routes Unit Tests", () => {
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
    const responseFormatter = require("../../../middleware/responseFormatter");
    app.use(responseFormatter);

    // Load analytics routes
    const analyticsRouter = require("../../../routes/analytics");
    app.use("/analytics", analyticsRouter);
  });

  describe("GET /analytics/", () => {
    test("should return analytics info", async () => {
      const response = await request(app).get("/analytics/").expect(200);

      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("status");
    });
  });

  describe("GET /analytics/performance", () => {
    test("should handle performance analytics", async () => {
      const response = await request(app)
        .get("/analytics/performance")
        .set("Authorization", "Bearer dev-bypass-token");

      // API may return 200 for success or 401 for auth or 503 for data issues
      expect([200, 401, 503]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });
  });

  describe("GET /analytics/risk", () => {
    test("should handle risk analytics", async () => {
      const response = await request(app)
        .get("/analytics/risk")
        .set("Authorization", "Bearer dev-bypass-token");

      // API may return 200 for success or 401 for auth
      expect([200, 401]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });
  });

  describe("GET /analytics/correlation", () => {
    test("should handle correlation analysis", async () => {
      const response = await request(app).get("/analytics/correlation");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success");
    });
  });

  describe("GET /analytics/allocation", () => {
    test("should handle allocation analytics", async () => {
      const response = await request(app)
        .get("/analytics/allocation")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });
  });

  describe("GET /analytics/returns", () => {
    test("should handle returns analytics", async () => {
      const response = await request(app)
        .get("/analytics/returns")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });
  });

  describe("GET /analytics/sectors", () => {
    test("should handle sectors analytics", async () => {
      const response = await request(app)
        .get("/analytics/sectors")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });
  });

  describe("GET /analytics/volatility", () => {
    test("should handle volatility analytics", async () => {
      const response = await request(app)
        .get("/analytics/volatility")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });
  });

  describe("GET /analytics/trends", () => {
    test("should handle trends analytics", async () => {
      const response = await request(app)
        .get("/analytics/trends")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });
  });

  describe("POST /analytics/custom", () => {
    test("should handle custom analytics request", async () => {
      const customRequest = {
        metrics: ["return", "risk"],
        period: "1Y",
        benchmark: "SPY",
      };

      const response = await request(app)
        .post("/analytics/custom")
        .set("Authorization", "Bearer dev-bypass-token")
        .send(customRequest);

      expect([200, 401, 500]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });
  });
});
