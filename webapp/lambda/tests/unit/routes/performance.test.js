const request = require("supertest");
const express = require("express");

const performanceRoutes = require("../../../routes/performance");

// Mock authentication middleware
const { authenticateToken } = require("../../../middleware/auth");

jest.mock("../../../middleware/auth");

// Mock performance monitor
jest.mock("../../../utils/performanceMonitor", () => ({
  getMetrics: jest.fn(),
  getSummary: jest.fn(),
  getApiStats: jest.fn(),
  getDatabaseStats: jest.fn(),
  getExternalApiStats: jest.fn(),
  getAlerts: jest.fn(),
  clearMetrics: jest.fn(),
}));

const performanceMonitor = require("../../../utils/performanceMonitor");

describe("Performance Routes", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/performance", performanceRoutes);

    // Mock authentication to pass for all tests
    authenticateToken.mockImplementation((req, res, next) => {
      req.user = { sub: "test-user-123" };
      req.logger = {
        info: jest.fn(),
        error: jest.fn(),
      };
      next();
    });
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /performance/health", () => {
    test("should return health status", async () => {
      const response = await request(app)
        .get("/performance/health")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        status: "operational",
        service: "performance-analytics",
        timestamp: expect.any(String),
        message: "Performance Analytics service is running",
      });
    });
  });

  describe("GET /performance/", () => {
    test("should return API status", async () => {
      const response = await request(app).get("/performance/").expect(200);

      expect(response.body).toMatchObject({
        success: true,
        message: "Performance Analytics API - Ready",
        timestamp: expect.any(String),
        status: "operational",
      });
    });
  });

  describe("GET /performance/metrics", () => {
    test("should return current performance metrics", async () => {
      const mockMetrics = {
        requests: {
          total: 1250,
          success: 1180,
          errors: 70,
          successRate: 94.4,
        },
        responseTime: {
          average: 145,
          p95: 280,
          p99: 450,
        },
        memory: {
          used: 128,
          free: 384,
          percentage: 25,
        },
        cpu: {
          usage: 35.2,
          load: [0.8, 0.9, 1.1],
        },
        database: {
          connections: 12,
          activeQueries: 3,
          avgQueryTime: 45,
        },
      };

      performanceMonitor.getMetrics.mockReturnValue(mockMetrics);

      const response = await request(app)
        .get("/performance/metrics")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: mockMetrics,
        timestamp: expect.any(String),
      });

      expect(performanceMonitor.getMetrics).toHaveBeenCalledTimes(1);
    });

    test("should handle performance monitor errors", async () => {
      performanceMonitor.getMetrics.mockImplementation(() => {
        throw new Error("Performance monitor unavailable");
      });

      const response = await request(app)
        .get("/performance/metrics")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to retrieve performance metrics",
      });
    });
  });

  describe("GET /performance/summary", () => {
    test("should return performance summary", async () => {
      const mockSummary = {
        overall: {
          status: "healthy",
          score: 85,
          uptime: "99.8%",
        },
        alerts: [
          {
            level: "warning",
            message: "Database connections approaching limit",
            threshold: 80,
            current: 75,
          },
        ],
        recommendations: [
          "Consider scaling database connections",
          "Monitor API response times during peak hours",
        ],
      };

      performanceMonitor.getSummary.mockReturnValue(mockSummary);

      const response = await request(app)
        .get("/performance/summary")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: mockSummary,
        timestamp: expect.any(String),
      });
    });

    test("should handle summary generation errors", async () => {
      performanceMonitor.getSummary.mockImplementation(() => {
        throw new Error("Unable to generate summary");
      });

      const response = await request(app)
        .get("/performance/summary")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to retrieve performance summary",
      });
    });
  });

  describe("GET /performance/api-stats", () => {
    test("should return API statistics", async () => {
      const mockMetrics = {
        api: {
          requests: {
            "/api/portfolio": {
              count: 450,
              avgResponseTime: 120,
              errors: 5,
              minResponseTime: 80,
              maxResponseTime: 200,
              recentRequests: [],
            },
            "/api/market": {
              count: 380,
              avgResponseTime: 95,
              errors: 2,
              minResponseTime: 60,
              maxResponseTime: 150,
              recentRequests: [],
            },
          },
          responseTimeHistogram: new Map(),
        },
        system: {
          totalRequests: 1050,
          totalErrors: 15,
          errorRate: 0.014,
        },
      };

      performanceMonitor.getMetrics.mockReturnValue(mockMetrics);

      const response = await request(app)
        .get("/performance/api-stats")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          endpoints: expect.any(Array),
          totalRequests: 1050,
          totalErrors: 15,
        }),
        timestamp: expect.any(String),
      });
    });
  });

  describe("GET /performance/database-stats", () => {
    test("should return database performance statistics", async () => {
      const mockMetrics = {
        database: {
          queries: {
            SELECT_portfolio: {
              count: 450,
              avgTime: 25,
              errors: 2,
              minTime: 10,
              maxTime: 80,
              recentQueries: [],
            },
            UPDATE_positions: {
              count: 180,
              avgTime: 45,
              errors: 1,
              minTime: 20,
              maxTime: 120,
              recentQueries: [],
            },
          },
        },
      };

      performanceMonitor.getMetrics.mockReturnValue(mockMetrics);

      const response = await request(app)
        .get("/performance/database-stats")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          operations: expect.any(Array),
          slowestQueries: expect.any(Array),
        }),
        timestamp: expect.any(String),
      });
    });
  });

  describe("GET /performance/external-api-stats", () => {
    test("should return external API performance statistics", async () => {
      const mockMetrics = {
        external: {
          apis: {
            alpaca: {
              count: 125,
              avgTime: 180,
              errors: 5,
              minTime: 80,
              maxTime: 300,
              recentCalls: [],
            },
            polygon: {
              count: 89,
              avgTime: 145,
              errors: 2,
              minTime: 90,
              maxTime: 200,
              recentCalls: [],
            },
          },
        },
      };

      performanceMonitor.getMetrics.mockReturnValue(mockMetrics);

      const response = await request(app)
        .get("/performance/external-api-stats")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          services: expect.any(Array),
          mostProblematic: expect.any(Array),
        }),
        timestamp: expect.any(String),
      });
    });
  });

  describe("GET /performance/alerts", () => {
    test("should return current performance alerts", async () => {
      const mockSummary = {
        status: "degraded",
        alerts: [
          {
            type: "performance",
            severity: "warning",
            message: "Query response time above threshold",
            timestamp: "2023-12-15T14:20:00Z",
          },
          {
            type: "errors",
            severity: "info",
            message: "High request volume detected",
            timestamp: "2023-12-15T14:18:00Z",
          },
        ],
      };

      performanceMonitor.getSummary.mockReturnValue(mockSummary);

      const response = await request(app)
        .get("/performance/alerts")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          alerts: expect.any(Array),
          systemStatus: "degraded",
          alertCount: 2,
        }),
        timestamp: expect.any(String),
      });
    });

    test("should handle no alerts", async () => {
      performanceMonitor.getSummary.mockReturnValue({
        status: "healthy",
        alerts: [],
      });

      const response = await request(app)
        .get("/performance/alerts")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          alerts: [],
          systemStatus: "healthy",
          alertCount: 0,
        }),
        timestamp: expect.any(String),
      });
    });
  });

  describe("POST /performance/clear-metrics", () => {
    test("should clear performance metrics", async () => {
      // Mock admin user for this test
      authenticateToken.mockImplementation((req, res, next) => {
        req.user = { sub: "admin-user-123", role: "admin" };
        req.logger = {
          info: jest.fn(),
          error: jest.fn(),
          warn: jest.fn(),
        };
        next();
      });

      performanceMonitor.reset = jest.fn();

      const response = await request(app)
        .post("/performance/clear-metrics")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        message: "Performance metrics cleared successfully",
        timestamp: expect.any(String),
      });

      expect(performanceMonitor.reset).toHaveBeenCalledTimes(1);
    });

    test("should handle clear metrics errors", async () => {
      // Mock admin user for this test
      authenticateToken.mockImplementation((req, res, next) => {
        req.user = { sub: "admin-user-123", role: "admin" };
        req.logger = {
          info: jest.fn(),
          error: jest.fn(),
          warn: jest.fn(),
        };
        next();
      });

      performanceMonitor.reset = jest.fn(() => {
        throw new Error("Unable to clear metrics");
      });

      const response = await request(app)
        .post("/performance/clear-metrics")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to clear performance metrics",
        timestamp: expect.any(String),
      });
    });
  });
});
