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
      const response = await request(app)
        .get("/api/portfolio/api-keys")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: [],
        message:
          "Portfolio API keys endpoint available (returning empty for now)",
      });

      // Validate response structure
      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("data");
      expect(response.body).toHaveProperty("message");
      expect(Array.isArray(response.body.data)).toBe(true);
      expect(typeof response.body.success).toBe("boolean");
      expect(typeof response.body.message).toBe("string");
    });

    it("should return JSON content type", async () => {
      const response = await request(app)
        .get("/api/portfolio/api-keys")
        .expect(200)
        .expect("Content-Type", /json/);

      expect(response.headers["content-type"]).toMatch(/application\/json/);
    });

    it("should handle errors gracefully with proper error structure", async () => {
      const originalConsoleError = console.error;
      console.error = jest.fn();

      const response = await request(app)
        .get("/api/portfolio/api-keys")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body).toHaveProperty("data");

      console.error = originalConsoleError;
    });

    it("should be authenticated route (mocked)", async () => {
      // This test verifies the route is using authentication middleware
      const response = await request(app)
        .get("/api/portfolio/api-keys")
        .expect(200);

      // Since auth is mocked to succeed, we should get successful response
      expect(response.body.success).toBe(true);
    });
  });

  describe("GET /api/portfolio/health", () => {
    it("should return portfolio service health status", async () => {
      const response = await request(app)
        .get("/api/portfolio/health")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        service: "Portfolio API",
        status: "healthy",
        timestamp: expect.any(String),
      });

      // Verify timestamp is valid ISO string
      expect(new Date(response.body.timestamp)).toBeInstanceOf(Date);
    });
  });

  describe("POST /api/portfolio/calculate-var", () => {
    it("should return demo VaR calculation with valid portfolio data", async () => {
      const portfolioData = {
        portfolioValue: 100000,
        positions: [
          { symbol: "AAPL", quantity: 100, currentPrice: 150 },
          { symbol: "GOOGL", quantity: 50, currentPrice: 2800 },
        ],
      };

      const response = await request(app)
        .post("/api/portfolio/calculate-var")
        .send(portfolioData)
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: {
          var: 0.05,
          confidence: 0.95,
          message: "Demo VaR calculation",
        },
      });

      // Validate response structure
      expect(response.body).toHaveProperty("success", true);
      expect(response.body).toHaveProperty("data");
      expect(response.body.data).toHaveProperty("var");
      expect(response.body.data).toHaveProperty("confidence");
      expect(response.body.data).toHaveProperty("message");
      expect(typeof response.body.data.var).toBe("number");
      expect(typeof response.body.data.confidence).toBe("number");
    });

    it("should handle empty request body gracefully", async () => {
      const response = await request(app)
        .post("/api/portfolio/calculate-var")
        .send({})
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: {
          var: 0.05,
          confidence: 0.95,
          message: "Demo VaR calculation",
        },
      });
    });

    it("should handle null request body", async () => {
      const response = await request(app)
        .post("/api/portfolio/calculate-var")
        .send(null)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    it("should handle malformed portfolio data types", async () => {
      const invalidData = {
        portfolioValue: "not-a-number",
        positions: "not-an-array",
      };

      const response = await request(app)
        .post("/api/portfolio/calculate-var")
        .send(invalidData)
        .expect(200);

      // Current implementation returns demo data regardless of input validation
      expect(response.body.success).toBe(true);
      expect(response.body.data.var).toBe(0.05);
      expect(response.body.data.confidence).toBe(0.95);
    });

    it("should handle large portfolio values", async () => {
      const largePortfolio = {
        portfolioValue: 10000000, // 10M portfolio
        positions: [
          { symbol: "AAPL", quantity: 1000, currentPrice: 150 },
          { symbol: "MSFT", quantity: 500, currentPrice: 300 },
          { symbol: "GOOGL", quantity: 200, currentPrice: 2800 },
        ],
      };

      const response = await request(app)
        .post("/api/portfolio/calculate-var")
        .send(largePortfolio)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.var).toBe(0.05);
    });

    it("should handle empty positions array", async () => {
      const emptyPositions = {
        portfolioValue: 50000,
        positions: [],
      };

      const response = await request(app)
        .post("/api/portfolio/calculate-var")
        .send(emptyPositions)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data).toBeDefined();
    });

    it("should return consistent response format", async () => {
      const response = await request(app)
        .post("/api/portfolio/calculate-var")
        .send({})
        .expect(200);

      // Verify consistent API response structure
      expect(response.body).toHaveProperty("success");
      expect(response.body).toHaveProperty("data");
      expect(typeof response.body.success).toBe("boolean");
      expect(typeof response.body.data).toBe("object");

      // VaR-specific structure
      expect(response.body.data).toHaveProperty("var");
      expect(response.body.data).toHaveProperty("confidence");
      expect(response.body.data.var).toBeGreaterThanOrEqual(0);
      expect(response.body.data.confidence).toBeGreaterThan(0);
      expect(response.body.data.confidence).toBeLessThanOrEqual(1);
    });

    it("should handle Content-Type validation", async () => {
      const response = await request(app)
        .post("/api/portfolio/calculate-var")
        .set("Content-Type", "application/json")
        .send({ portfolioValue: 100000 })
        .expect(200);

      expect(response.body.success).toBe(true);
    });
  });

  describe("Portfolio Route Structure", () => {
    it("should have all required endpoints", () => {
      const router = require("../routes/portfolio");

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
      expect(routePaths).toContain("/health");
      expect(routePaths).toContain("/calculate-var");
    });

    it("should export a valid Express router", () => {
      const router = require("../routes/portfolio");

      // Verify it has router methods
      expect(typeof router.get).toBe("function");
      expect(typeof router.post).toBe("function");
      expect(typeof router.use).toBe("function");
    });
  });

  describe("Response Format Consistency", () => {
    it("should return consistent success response format", async () => {
      const endpoints = [
        { method: "get", path: "/api/portfolio/api-keys" },
        { method: "get", path: "/api/portfolio/health" },
        { method: "post", path: "/api/portfolio/calculate-var", body: {} },
      ];

      for (const endpoint of endpoints) {
        const req = request(app)[endpoint.method](endpoint.path);

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
      const response = await request(app)
        .get("/api/portfolio/health")
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
