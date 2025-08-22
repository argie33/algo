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
  clearMetrics: jest.fn()
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
        error: jest.fn()
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
        message: "Performance Analytics service is running"
      });
    });
  });

  describe("GET /performance/", () => {
    test("should return API status", async () => {
      const response = await request(app)
        .get("/performance/")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        message: "Performance Analytics API - Ready",
        timestamp: expect.any(String),
        status: "operational"
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
          successRate: 94.4
        },
        responseTime: {
          average: 145,
          p95: 280,
          p99: 450
        },
        memory: {
          used: 128,
          free: 384,
          percentage: 25
        },
        cpu: {
          usage: 35.2,
          load: [0.8, 0.9, 1.1]
        },
        database: {
          connections: 12,
          activeQueries: 3,
          avgQueryTime: 45
        }
      };

      performanceMonitor.getMetrics.mockReturnValue(mockMetrics);

      const response = await request(app)
        .get("/performance/metrics")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: mockMetrics,
        timestamp: expect.any(String)
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
        message: "Performance monitor unavailable"
      });
    });
  });

  describe("GET /performance/summary", () => {
    test("should return performance summary", async () => {
      const mockSummary = {
        overall: {
          status: "healthy",
          score: 85,
          uptime: "99.8%"
        },
        alerts: [
          {
            level: "warning",
            message: "Database connections approaching limit",
            threshold: 80,
            current: 75
          }
        ],
        recommendations: [
          "Consider scaling database connections",
          "Monitor API response times during peak hours"
        ]
      };

      performanceMonitor.getSummary.mockReturnValue(mockSummary);

      const response = await request(app)
        .get("/performance/summary")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: mockSummary,
        timestamp: expect.any(String)
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
        message: "Unable to generate summary"
      });
    });
  });

  describe("GET /performance/api-stats", () => {
    test("should return API statistics", async () => {
      const mockApiStats = {
        endpoints: {
          "/api/portfolio": { requests: 450, avgResponseTime: 120, errors: 5 },
          "/api/market": { requests: 380, avgResponseTime: 95, errors: 2 },
          "/api/trading": { requests: 220, avgResponseTime: 180, errors: 8 }
        },
        totalRequests: 1050,
        totalErrors: 15,
        averageResponseTime: 135,
        requestsPerMinute: 25.6
      };

      performanceMonitor.getApiStats.mockReturnValue(mockApiStats);

      const response = await request(app)
        .get("/performance/api-stats")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: mockApiStats,
        timestamp: expect.any(String)
      });
    });
  });

  describe("GET /performance/database-stats", () => {
    test("should return database performance statistics", async () => {
      const mockDbStats = {
        connections: {
          active: 8,
          idle: 4,
          total: 12,
          max: 20
        },
        queries: {
          total: 2150,
          successful: 2140,
          failed: 10,
          averageTime: 42,
          slowQueries: 3
        },
        tables: {
          mostAccessed: "user_portfolio",
          largestTable: "market_data",
          recentMaintenance: "2023-12-15T08:30:00Z"
        }
      };

      performanceMonitor.getDatabaseStats.mockReturnValue(mockDbStats);

      const response = await request(app)
        .get("/performance/database-stats")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: mockDbStats,
        timestamp: expect.any(String)
      });
    });
  });

  describe("GET /performance/external-api-stats", () => {
    test("should return external API performance statistics", async () => {
      const mockExternalStats = {
        alpaca: {
          requests: 125,
          successful: 120,
          failed: 5,
          averageResponseTime: 180,
          lastSuccess: "2023-12-15T14:25:00Z"
        },
        polygon: {
          requests: 89,
          successful: 87,
          failed: 2,
          averageResponseTime: 145,
          lastSuccess: "2023-12-15T14:30:00Z"
        },
        finnhub: {
          requests: 64,
          successful: 62,
          failed: 2,
          averageResponseTime: 165,
          lastSuccess: "2023-12-15T14:28:00Z"
        }
      };

      performanceMonitor.getExternalApiStats.mockReturnValue(mockExternalStats);

      const response = await request(app)
        .get("/performance/external-api-stats")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: mockExternalStats,
        timestamp: expect.any(String)
      });
    });
  });

  describe("GET /performance/alerts", () => {
    test("should return current performance alerts", async () => {
      const mockAlerts = [
        {
          id: "alert-001",
          level: "warning",
          category: "database",
          message: "Query response time above threshold",
          threshold: 100,
          current: 125,
          timestamp: "2023-12-15T14:20:00Z",
          acknowledged: false
        },
        {
          id: "alert-002",
          level: "info",
          category: "api",
          message: "High request volume detected",
          threshold: 50,
          current: 62,
          timestamp: "2023-12-15T14:18:00Z",
          acknowledged: true
        }
      ];

      performanceMonitor.getAlerts.mockReturnValue(mockAlerts);

      const response = await request(app)
        .get("/performance/alerts")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: mockAlerts,
        count: 2,
        timestamp: expect.any(String)
      });
    });

    test("should handle no alerts", async () => {
      performanceMonitor.getAlerts.mockReturnValue([]);

      const response = await request(app)
        .get("/performance/alerts")
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: [],
        count: 0,
        timestamp: expect.any(String)
      });
    });
  });

  describe("POST /performance/clear-metrics", () => {
    test("should clear performance metrics", async () => {
      performanceMonitor.clearMetrics.mockReturnValue({
        cleared: true,
        previousDataSize: "2.5MB",
        timestamp: "2023-12-15T14:35:00Z"
      });

      const response = await request(app)
        .post("/performance/clear-metrics")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        message: "Performance metrics cleared successfully",
        data: expect.objectContaining({
          cleared: true,
          previousDataSize: "2.5MB"
        })
      });

      expect(performanceMonitor.clearMetrics).toHaveBeenCalledTimes(1);
    });

    test("should handle clear metrics errors", async () => {
      performanceMonitor.clearMetrics.mockImplementation(() => {
        throw new Error("Unable to clear metrics");
      });

      const response = await request(app)
        .post("/performance/clear-metrics")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to clear performance metrics",
        message: "Unable to clear metrics"
      });
    });
  });
});