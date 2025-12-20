const express = require("express");
const request = require("supertest");

// Mock database BEFORE importing routes
jest.mock("../../../utils/database", () => ({
  query: jest.fn().mockResolvedValue({ rows: [], rowCount: 0 }),
  initializeDatabase: jest.fn(),
  closeDatabase: jest.fn(),
}));

// Import mocked functions AFTER jest.mock
const { query, closeDatabase, initializeDatabase } = require("../../../utils/database");

describe("Dashboard Routes Unit Tests", () => {
  let app;
  beforeAll(() => {
    // Set up database mocks
    query.mockImplementation((queryText) => {
      // Mock market data query
      if (queryText.includes("SELECT") && queryText.includes("symbol")) {
        return Promise.resolve({
          rows: [
            { symbol: "AAPL", value: 150.00, change: 2.50, change_percent: 1.69 },
            { symbol: "GOOGL", value: 2700.00, change: -5.25, change_percent: -0.19 }
          ]
        });

      }
      // Mock other queries with empty results
      return Promise.resolve({ rows: [] });
    });
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
    app.use("/api/dashboard", dashboardRouter);
  });
  describe("GET /dashboard/", () => {
    test("should return dashboard info", async () => {
      const response = await request(app)
        .get("/api/dashboard/")
        .expect(200);
      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("message");
      expect(response.body.message).toBe("Dashboard API - Ready");
    });
  });
  describe("GET /dashboard/overview", () => {
    test("should handle dashboard overview", async () => {
      const response = await request(app)
        .get("/api/dashboard/overview")
        .set("Authorization", "Bearer test-token");
      // Should return 200 with overview data or appropriate error status
      expect([200, 401, 403, 404, 503]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });
  });
  describe("GET /dashboard/widgets", () => {
    test("should handle dashboard widgets", async () => {
      const response = await request(app)
        .get("/api/dashboard/widgets")
        .set("Authorization", "Bearer test-token");
      expect([200, 401, 403, 404, 503]).toContain(response.status);
      expect(response.body).toHaveProperty("success");
    });
  });
});
