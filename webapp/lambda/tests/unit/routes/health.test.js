const request = require("supertest");
const express = require("express");

// Mock dependencies BEFORE importing the routes  
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
  initializeDatabase: jest.fn(),
  getPool: jest.fn(),
  healthCheck: jest.fn()
}));

// Now import the routes after mocking
const healthRoutes = require("../../../routes/health");
const { query, initializeDatabase, getPool, healthCheck } = require("../../../utils/database");

describe("Health Routes - Testing Your Actual Site", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/health", healthRoutes);
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /health - Health check endpoint", () => {
    test("should return quick health check when quick=true", async () => {
      const response = await request(app)
        .get("/health")
        .query({ quick: "true" })
        .expect(200);

      expect(response.body).toMatchObject({
        status: "healthy",
        healthy: true,
        service: "Financial Dashboard API",
        timestamp: expect.any(String),
        environment: expect.any(String),
        memory: expect.objectContaining({
          rss: expect.any(Number),
          heapTotal: expect.any(Number),
          heapUsed: expect.any(Number)
        }),
        uptime: expect.any(Number),
        note: "Quick health check - database not tested",
        database: { status: "not_tested" },
        api: expect.objectContaining({
          version: "1.0.0",
          environment: expect.any(String)
        })
      });

      // Should not query database for quick check
      expect(query).not.toHaveBeenCalled();
      expect(initializeDatabase).not.toHaveBeenCalled();
    });

    test("should return full health check with database testing", async () => {
      const mockHealthCheck = {
        healthy: true,
        status: "connected",
        responseTime: 0,
        tables: {
          user_portfolio: true,
          user_api_keys: true,
          stock_prices: true,
          risk_alerts: true
        }
      };

      initializeDatabase.mockResolvedValue();
      healthCheck.mockResolvedValue(mockHealthCheck);

      const response = await request(app)
        .get("/health")
        .expect(200);

      expect(response.body).toMatchObject({
        status: "healthy", 
        healthy: true,
        service: "Financial Dashboard API",
        timestamp: expect.any(String),
        environment: expect.any(String),
        database: expect.objectContaining({
          status: "connected",
          responseTime: expect.any(Number),
          tables: expect.objectContaining({
            user_portfolio: expect.any(Boolean),
            user_api_keys: expect.any(Boolean),
            stock_prices: expect.any(Boolean),
            risk_alerts: expect.any(Boolean)
          })
        }),
        api: expect.objectContaining({
          version: "1.0.0"
        })
      });

      // Should include database information in full check
      expect(response.body.database).toBeDefined();
    });

    test("should handle database connection failures gracefully", async () => {
      initializeDatabase.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app)
        .get("/health")
        .expect(200); // Your site returns 200 even for database failures

      expect(response.body).toMatchObject({
        status: expect.any(String), // May be "error" or "unhealthy"
        service: "Financial Dashboard API",
        timestamp: expect.any(String)
      });
      
      // Should handle error gracefully without crashing
      expect(response.body).toHaveProperty('status');
    });

    test("should handle database query failures", async () => {
      initializeDatabase.mockResolvedValue();
      healthCheck.mockResolvedValue({ 
        healthy: false, 
        status: "error",
        error: "Query timeout" 
      });

      const response = await request(app)
        .get("/health")
        .expect(200); // Your site returns 200 even for query failures

      expect(response.body).toMatchObject({
        service: "Financial Dashboard API",
        timestamp: expect.any(String)
      });
      
      // Should handle database errors gracefully  
      expect(response.body).toHaveProperty('database');
    });
  });

  describe("Error handling", () => {
    test("should return valid response structure for all cases", async () => {
      // Test that health endpoint always returns valid JSON structure
      const response = await request(app)
        .get("/health")
        .query({ quick: "true" })
        .expect(200);

      // Your site always returns valid structured response
      expect(response.body).toHaveProperty('service');
      expect(response.body).toHaveProperty('timestamp');
      expect(response.body).toHaveProperty('status');
      expect(response.body.service).toBe("Financial Dashboard API");
    });
  });
});