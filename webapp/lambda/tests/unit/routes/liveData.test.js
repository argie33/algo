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

jest.mock("../../../utils/logger", () => ({
  info: jest.fn(),
  error: jest.fn(),
  warn: jest.fn(),
  success: jest.fn(),
}));

jest.mock("../../../utils/realTimeDataService", () => ({
  getCacheStats: jest.fn(),
  requestData: jest.fn(),
  subscribeToSymbol: jest.fn(),
  unsubscribeFromSymbol: jest.fn(),
  watchedSymbols: new Set(),
  indexSymbols: new Set(),
}));

jest.mock("../../../utils/liveDataManager", () => ({
  getDashboardStatus: jest.fn(),
  getServiceHealth: jest.fn(),
  getConnectionStats: jest.fn(),
}));

// Now import the routes after mocking
const liveDataRoutes = require("../../../routes/liveData");

// Auth middleware mocked above

const logger = require("../../../utils/logger");
const realTimeDataService = require("../../../utils/realTimeDataService");
const liveDataManager = require("../../../utils/liveDataManager");

describe("Live Data Routes - Testing Your Actual Site", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/livedata", liveDataRoutes);
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /livedata/status - Live data service status", () => {
    test("should return comprehensive live data service status", async () => {
      const mockDashboardStatus = {
        global: {
          totalConnections: 15,
          totalSymbols: 25,
          dailyCost: 12.5,
          performance: {
            avgResponseTime: 145,
            successRate: 98.5,
            errorRate: 1.5,
          },
        },
        providers: {
          alpaca: {
            status: "active",
            connections: 8,
            symbols: ["AAPL", "MSFT", "TSLA"],
          },
          polygon: {
            status: "active",
            connections: 7,
            symbols: ["NVDA", "GOOGL"],
          },
        },
      };

      const mockCacheStats = {
        totalEntries: 150,
        freshEntries: 125,
        staleEntries: 25,
        hitRate: 85.2,
        memoryUsage: 45.8,
      };

      liveDataManager.getDashboardStatus.mockReturnValue(mockDashboardStatus);
      realTimeDataService.getCacheStats.mockReturnValue(mockCacheStats);

      const response = await request(app).get("/livedata/status").expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          service: "live-data",
          status: "operational",
          timestamp: expect.any(String),
          version: "2.0.0",
          correlationId: expect.any(String),
          global: expect.objectContaining({
            totalConnections: 15,
            totalSymbols: 25,
            dailyCost: 12.5,
            performance: expect.objectContaining({
              avgResponseTime: 145,
              successRate: 98.5,
              errorRate: 1.5,
            }),
          }),
          providers: expect.objectContaining({
            alpaca: expect.objectContaining({
              status: "active",
              connections: 8,
              symbols: expect.arrayContaining(["AAPL", "MSFT", "TSLA"]),
            }),
          }),
          components: expect.objectContaining({
            liveDataManager: expect.objectContaining({
              status: "operational",
              totalConnections: 15,
              totalSymbols: 25,
              dailyCost: 12.5,
            }),
            realTimeService: expect.objectContaining({
              status: "operational",
              cacheEntries: 150,
              freshEntries: 125,
              staleEntries: 25,
            }),
          }),
        }),
        meta: expect.objectContaining({
          correlationId: expect.any(String),
          duration: expect.any(Number),
          timestamp: expect.any(String),
        }),
      });

      expect(logger.info).toHaveBeenCalledWith(
        "Processing live data status request",
        expect.objectContaining({
          correlationId: expect.any(String),
        })
      );
    });

    test("should handle service degradation gracefully", async () => {
      const mockDegradedStatus = {
        global: {
          totalConnections: 5,
          totalSymbols: 10,
          dailyCost: 3.25,
          performance: {
            avgResponseTime: 500,
            successRate: 85.0,
            errorRate: 15.0,
          },
        },
        providers: {
          alpaca: {
            status: "error",
            error: "Connection timeout",
          },
        },
      };

      liveDataManager.getDashboardStatus.mockReturnValue(mockDegradedStatus);
      realTimeDataService.getCacheStats.mockReturnValue({
        totalEntries: 50,
        freshEntries: 30,
        staleEntries: 20,
      });

      const response = await request(app).get("/livedata/status").expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          service: "live-data",
          status: "operational", // Still operational even with provider issues
          providers: expect.objectContaining({
            alpaca: expect.objectContaining({
              status: "error",
              error: "Connection timeout",
            }),
          }),
        }),
      });
    });
  });

  describe("Authentication and Error Handling", () => {
    test("should handle logger errors by returning 500", async () => {
      logger.info.mockImplementation(() => {
        throw new Error("Logger failed");
      });

      const response = await request(app).get("/livedata/status").expect(500);

      // Should return error when critical components fail
      expect(response.body).toMatchObject({
        error: expect.any(String),
        correlationId: expect.any(String),
        timestamp: expect.any(String),
      });
    });

    test("should handle service errors gracefully", async () => {
      liveDataManager.getDashboardStatus.mockImplementation(() => {
        throw new Error("Live data manager failed");
      });

      realTimeDataService.getCacheStats.mockImplementation(() => {
        throw new Error("Cache service failed");
      });

      const response = await request(app).get("/livedata/status").expect(500);

      expect(response.body).toMatchObject({
        error: expect.any(String),
      });
    });
  });
});
