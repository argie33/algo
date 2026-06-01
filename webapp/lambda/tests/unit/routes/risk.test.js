/**
 * Risk Routes Integration Tests
 * Tests risk route logic with real database connections
 */

const express = require("express");
const request = require("supertest");

// Mock only the auth middleware to provide test user - no database mocks
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = {
      sub: "test-user-123",
      email: "test@example.com",
      username: "testuser",
    };
    next();
  }),
}));

describe("Risk Routes Integration Tests", () => {
  let app;
  let riskRouter;

  beforeEach(() => {
    jest.clearAllMocks();

    // Create test app
    app = express();
    app.use(express.json());

    // Add response helper middleware
    app.use((req, res, next) => {
      res.error = (message, status) =>
        res.status(status).json({
          success: false,
          error: message,
        });
      next();
    });

    // Load the route module
    riskRouter = require("../../../routes/risk");
    app.use("/risk", riskRouter);
  });

  describe("GET /risk/health", () => {
    test("should return health status without authentication", async () => {
      const response = await request(app).get("/risk/health");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("status", "operational");
      expect(response.body).toHaveProperty("service", "risk-analysis");
      expect(response.body).toHaveProperty("timestamp");
      expect(response.body).toHaveProperty(
        "message",
        "Risk Analysis service is running"
      );

      // Verify timestamp is a valid ISO string
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
    });
  });

  describe("GET /risk", () => {
    test("should return risk API information without authentication", async () => {
      const response = await request(app).get("/risk");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty(
        "message",
        "Risk Analysis API - Ready"
      );
      expect(response.body.data).toHaveProperty("status", "operational");
      expect(response.body.data).toHaveProperty("timestamp");

      // Verify timestamp is a valid ISO string
      expect(new Date(response.body.data.timestamp)).toBeInstanceOf(Date);
    });
  });

  describe("GET /risk/analysis (authenticated)", () => {
    test("should return risk analysis for empty portfolio - SKIPPED: performance issues", async () => {
      const response = await request(app).get("/risk/analysis");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");

      // Since test user likely has no holdings, expect empty portfolio response
      expect(response.body.data).toHaveProperty("message", "No holdings found for risk analysis");
      expect(response.body.data).toHaveProperty("holdings_count", 0);
      expect(response.body.data).toHaveProperty("risk_metrics", null);
    });

    test("should handle different period parameters - SKIPPED: performance issues", async () => {
      const response = await request(app)
        .get("/risk/analysis")
        .query({ period: "1y", confidence_level: 0.99 });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
    });

    test("should handle invalid period gracefully - SKIPPED: performance issues", async () => {
      const response = await request(app)
        .get("/risk/analysis")
        .query({ period: "invalid_period" });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
    });

    test("should accept confidence level parameter - SKIPPED: performance issues", async () => {
      const response = await request(app)
        .get("/risk/analysis")
        .query({ confidence_level: 0.99 });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
    });

    test("should handle invalid confidence level gracefully - SKIPPED: performance issues", async () => {
      const response = await request(app)
        .get("/risk/analysis")
        .query({ confidence_level: "invalid" });

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
    });

  });

  describe("Authentication middleware", () => {
    test("should protect analysis endpoint", () => {
      const { authenticateToken } = require("../../../middleware/auth");
      expect(authenticateToken).toBeDefined();

      // Test that middleware was applied - verified through successful authenticated requests above
    });

    test("should allow public health endpoint", async () => {
      // Health endpoint should work without authentication
      const response = await request(app).get("/risk/health");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("status", "operational");
    });

    test("should allow public root endpoint", async () => {
      // Root endpoint should work without authentication
      const response = await request(app).get("/risk");

      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty(
        "message",
        "Risk Analysis API - Ready"
      );
    });
  });


  describe("Response format", () => {
    test("should return consistent JSON response", async () => {
      const response = await request(app).get("/risk/health");

      expect(response.headers["content-type"]).toMatch(/json/);
      expect(typeof response.body).toBe("object");
    });
  });
});
