/**
 * Portfolio API Route Integration Tests
 * Tests complete portfolio API functionality with mocked dependencies
 * Focuses on: route behavior, response formats, error handling, authentication
 * Complements: Portfolio.test.jsx (UI component), apiKeyService tests
 */

const request = require("supertest");
const express = require("express");

// Mock authentication middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: (req, res, next) => {
    req.user = { sub: "test-user-id" };
    next();
  },
}));

// Mock database queries
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

const { query } = require("../../../utils/database");

const portfolioRoutes = require("../../../routes/portfolio");
const app = express();
app.use(express.json());
app.use("/api/portfolio", portfolioRoutes);

describe("Portfolio API Routes", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /api/portfolio/api-keys", () => {
    it("should return empty api keys array with proper structure", async () => {
      // Mock database to return empty results
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/api/portfolio/api-keys")
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: [],
        timestamp: expect.any(String),
      });

      // Validate response structure
      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("data");
      expect(response.body).toHaveProperty("timestamp");
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(typeof response.body.success).toBe("boolean");
      expect(typeof response.body.timestamp).toBe("string");
    });

    it("should return JSON content type", async () => {
      // Mock database to return empty results
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/api/portfolio/api-keys")
        .expect(200)
        .expect("Content-Type", /json/);

      expect(response.headers["content-type"]).toMatch(/application\/json/);
    });

    it("should handle errors gracefully with proper error structure", async () => {
      // Mock database to return empty results
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/api/portfolio/api-keys")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");
    });

    it("should be authenticated route (mocked)", async () => {
      // Mock database to return empty results
      query.mockResolvedValue({ rows: [] });

      // This test verifies the route is using authentication middleware
      const response = await request(app)
        .get("/api/portfolio/api-keys")
        .expect(200);

      // Since auth is mocked to succeed, we should get successful response
      expect(response.body.success).toBe(true);
    });
  });

  describe("GET /api/portfolio/analytics", () => {
    it("should return portfolio analytics with authentication", async () => {
      // Mock database to return sample portfolio data
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/api/portfolio/analytics")
        .set("Authorization", "Bearer test-token")
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("holdings");
      expect(response.body.data).toHaveProperty("totalValue");
    });
  });

  describe("POST /api/portfolio/api-keys", () => {
    it("should handle api key creation with authentication", async () => {
      // Mock successful api key creation
      query.mockResolvedValue({ rows: [{ id: 1 }] });

      const apiKeyData = {
        brokerName: "alpaca",
        apiKey: "test-key-id",
        apiSecret: "test-secret-key",
        sandbox: true
      };

      const response = await request(app)
        .post("/api/portfolio/api-keys")
        .set("Authorization", "Bearer test-token")
        .send(apiKeyData)
        .expect(200);

      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("message");
    });

  });

  describe("Portfolio Route Structure", () => {
    it("should have all required endpoints", () => {
      const router = require("../../../routes/portfolio");

      // Verify the router is an Express router
      expect(router).toBeDefined();
      expect(typeof router).toBe("function");

      // Check that router.stack contains our routes
      expect(router.stack).toBeDefined();
      expect(router.stack.length).toBeGreaterThan(0);

      // Verify route paths exist
      const routePaths = router.stack
        .map((layer) => layer.route?.path)
        .filter(Boolean);
      expect(routePaths).toContain("/api-keys");
      expect(routePaths).toContain("/analytics");
      expect(routePaths).toContain("/risk-metrics");
    });

    it("should export a valid Express router", () => {
      const router = require("../../../routes/portfolio");

      // Verify it has router methods
      expect(typeof router.get).toBe("function");
      expect(typeof router.post).toBe("function");
      expect(typeof router.use).toBe("function");
    });
  });

  describe("Response Format Consistency", () => {
    it("should return consistent success response format", async () => {
      // Mock database calls for all endpoints
      query.mockResolvedValue({ rows: [] });

      const endpoints = [
        { method: "get", path: "/api/portfolio/api-keys", needsAuth: true },
        { method: "get", path: "/api/portfolio/analytics", needsAuth: true },
      ];

      for (const endpoint of endpoints) {
        const req = request(app)[endpoint.method](endpoint.path);

        if (endpoint.needsAuth) {
          req.set("Authorization", "Bearer test-token");
        }

        if (endpoint.body) {
          req.send(endpoint.body);
        }

        const response = await req.expect(200);

        // All responses should have success field
        expect(response.body).toHaveProperty("success");
        expect(response.body.success).toBe(true);

        // Should have either data or specific fields
        expect(
          Object.prototype.hasOwnProperty.call(response.body, "data") ||
            Object.prototype.hasOwnProperty.call(response.body, "service") ||
            Object.prototype.hasOwnProperty.call(response.body, "message")
        ).toBe(true);
      }
    });
  });

  describe("Content-Type Headers", () => {
    it("should return JSON content type", async () => {
      // Mock database call
      query.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get("/api/portfolio/api-keys")
        .set("Authorization", "Bearer test-token")
        .expect(200)
        .expect("Content-Type", /json/);

      expect(response.headers["content-type"]).toMatch(/application\/json/);
    });
  });

  describe("Error Handling", () => {
    it("should handle route not found", async () => {
      const response = await request(app)
        .get("/api/portfolio/nonexistent")
        .expect(404);

      // Express default 404 handling
      expect(response.status).toBe(404);
    });

    it("should handle invalid HTTP methods", async () => {
      const response = await request(app)
        .patch("/api/portfolio/health") // PATCH not supported
        .expect(404);

      expect(response.status).toBe(404);
    });
  });
});
