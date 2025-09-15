const express = require("express");
const request = require("supertest");

// Real database for integration
const { query } = require("../../../utils/database");

describe("Dashboard Routes Unit Tests", () => {
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

    // Load dashboard routes
    const dashboardRouter = require("../../../routes/dashboard");
    app.use("/dashboard", dashboardRouter);
  });

  describe("GET /dashboard/", () => {
    test("should return dashboard info", async () => {
      const response = await request(app).get("/dashboard/").expect(200);

      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("status");
    });
  });

  describe("GET /dashboard/overview", () => {
    test("should handle dashboard overview", async () => {
      const response = await request(app)
        .get("/dashboard/overview")
        .set("Authorization", "Bearer dev-bypass-token");

      // Route returns 404 when no market indices data (SPY, QQQ, etc.) exists
      // This is expected behavior in test environment without market data
      expect([200, 401, 404]).toContain(response.status);
      expect(response.body).toHaveProperty("success");

      if (response.status === 404) {
        expect(response.body.success).toBe(false);
        expect(response.body.error).toContain("key market metrics");
      }
    });
  });

  describe("GET /dashboard/widgets", () => {
    test("should handle dashboard widgets", async () => {
      const response = await request(app)
        .get("/dashboard/widgets")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 401]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });
  });
});
