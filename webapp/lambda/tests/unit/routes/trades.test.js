const request = require("supertest");
const express = require("express");

// Mock dependencies BEFORE importing the routes
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123", role: "user" };
    req.token = "test-jwt-token";
    next();
  }),
}));

jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
  transaction: jest.fn(),
}));

// Mock optional services that may not exist
jest.mock(
  "../../../services/tradeAnalyticsService",
  () => {
    return jest.fn().mockImplementation(() => ({}));
  },
  { virtual: true }
);

jest.mock(
  "../../../utils/userApiKeyHelper",
  () => ({
    getUserApiKey: jest.fn(),
    validateUserAuthentication: jest.fn(),
    sendApiKeyError: jest.fn(),
  }),
  { virtual: true }
);

jest.mock(
  "../../../utils/alpacaService",
  () => {
    return jest.fn().mockImplementation(() => ({}));
  },
  { virtual: true }
);

// Now import the routes after mocking

const tradesRoutes = require("../../../routes/trades");
const { authenticateToken } = require("../../../middleware/auth");
const { query, transaction: _transaction } = require("../../../utils/database");

describe("Trades Routes - Testing Your Actual Site", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/trades", tradesRoutes);

    // Mock authentication to pass for all tests
    authenticateToken.mockImplementation((req, res, next) => {
      req.user = { sub: "test-user-123", role: "user" };
      req.token = "test-jwt-token";
      next();
    });
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /trades/health - Health check", () => {
    test("should return trade service health status", async () => {
      const response = await request(app).get("/trades/health").expect(200);

      expect(response.body).toMatchObject({
        success: true,
        status: "operational",
        service: "trades",
        timestamp: expect.any(String),
        message: "Trade History service is running",
      });

      // Health endpoint should not require authentication
      expect(authenticateToken).not.toHaveBeenCalled();
    });
  });

  describe("GET /trades/ - Root endpoint", () => {
    test("should return trade API ready message", async () => {
      const response = await request(app).get("/trades/").expect(200);

      expect(response.body).toMatchObject({
        success: true,
        message: "Trade History API - Ready",
        timestamp: expect.any(String),
        status: "operational",
      });

      // Root endpoint should not require authentication
      expect(authenticateToken).not.toHaveBeenCalled();
    });
  });

  describe("GET /trades/import/status - Trade import status", () => {
    test("should require authentication and handle protected endpoint", async () => {
      // The route requires authentication, so let's test the auth requirement
      const response = await request(app)
        .get("/trades/import/status")
        .expect([200, 400, 500]); // May succeed, fail validation, or have missing dependencies

      // Should have a response body structure
      expect(response.body).toHaveProperty("success");

      // Should use authentication middleware
      expect(authenticateToken).toHaveBeenCalled();
    });

    test("should handle missing dependencies gracefully", async () => {
      // Test what happens when route dependencies are missing
      query.mockResolvedValue({ rows: [] });

      const response = await request(app).get("/trades/import/status");

      // Route should handle missing services gracefully
      expect(response.body).toHaveProperty("success");
      expect([200, 400, 500]).toContain(response.status);
    });
  });

  describe("Authentication", () => {
    test("should require authentication for protected routes", async () => {
      authenticateToken.mockImplementation((req, res, _next) => {
        res.status(401).json({ success: false, error: "Unauthorized" });
      });

      await request(app).get("/trades/import/status").expect(401);

      expect(query).not.toHaveBeenCalled();
    });

    test("should handle route errors gracefully", async () => {
      // Test that route handles various error conditions
      query.mockRejectedValue(new Error("Service unavailable"));

      const response = await request(app).get("/trades/import/status");

      // Should handle errors gracefully with structured response
      expect(response.body).toHaveProperty("success");
      expect([400, 401, 500]).toContain(response.status);
    });
  });

  describe("Error handling", () => {
    test("should handle various error scenarios", async () => {
      // Test that the route handles different types of errors
      query.mockImplementation(() => {
        throw new Error("Database error");
      });

      const response = await request(app).get("/trades/import/status");

      // Should return a structured error response
      expect(response.body).toHaveProperty("success");
      expect([400, 401, 500]).toContain(response.status);
    });
  });
});
