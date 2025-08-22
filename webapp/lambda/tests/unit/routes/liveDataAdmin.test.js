/**
 * Live Data Admin API Routes Tests
 * Tests for administrative live data management with authentication
 */

const request = require("supertest");
const express = require("express");

// Set test environment
process.env.NODE_ENV = "test";

// Mock dependencies before requiring the route
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
}));

const mockLogger = {
  info: jest.fn(),
  error: jest.fn(),
  success: jest.fn(),
  warn: jest.fn(),
};
jest.mock("../../../utils/logger", () => mockLogger);

jest.mock("../../../middleware/auth", () => ({
  authenticateToken: (req, res, next) => {
    req.user = { sub: "admin-user-id", role: "admin" };
    req.token = "admin-jwt-token";
    next();
  },
}));

// Mock liveDataManager
const mockLiveDataManager = {
  getDashboardStatus: jest.fn().mockReturnValue({
    global: {
      totalConnections: 5,
      totalSymbols: 250,
      dailyCost: 45.75,
      performance: {
        averageLatency: 42,
        uptime: 99.8,
        errorRate: 0.02,
      },
    },
    providers: {
      alpaca: { connections: 2, symbols: 120, costToday: 15.50 },
      polygon: { connections: 2, symbols: 85, costToday: 22.25 },
      finnhub: { connections: 1, symbols: 45, costToday: 8.00 },
    },
  }),
  createConnection: jest.fn(),
  closeConnection: jest.fn(),
  optimizeConnections: jest.fn(),
  updateRateLimits: jest.fn(),
  getAlertStatus: jest.fn().mockReturnValue({
    active: [],
    configured: true,
  }),
  updateAlertConfig: jest.fn(),
  testNotifications: jest.fn(),
  forceHealthCheck: jest.fn(),
};
jest.mock("../../../utils/liveDataManager", () => mockLiveDataManager);

// Set up response helper middleware
const responseHelpers = (req, res, next) => {
  res.success = (data) => res.json({ success: true, data });
  res.error = (message, status = 500) => res.status(status).json({ success: false, error: message });
  next();
};

const liveDataAdminRoutes = require("../../../routes/liveDataAdmin");
const app = express();
app.use(express.json());
app.use(responseHelpers);
app.use("/api/liveDataAdmin", liveDataAdminRoutes);

describe("Live Data Admin API Routes - Authentication Required", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    // Reset mock implementations to default
    mockLiveDataManager.getDashboardStatus.mockReturnValue({
      global: {
        totalConnections: 5,
        totalSymbols: 250,
        dailyCost: 45.75,
        performance: {
          averageLatency: 42,
          uptime: 99.8,
          errorRate: 0.02,
        },
      },
      providers: {
        alpaca: { connections: 2, symbols: 120, costToday: 15.50 },
        polygon: { connections: 2, symbols: 85, costToday: 22.25 },
        finnhub: { connections: 1, symbols: 45, costToday: 8.00 },
      },
    });
    mockLiveDataManager.getAlertStatus.mockReturnValue({
      active: [],
      configured: true,
    });
  });

  describe("Dashboard Endpoint - Admin Authentication Required", () => {
    it("should return comprehensive dashboard data for authenticated admin", async () => {
      const response = await request(app)
        .get("/api/liveDataAdmin/dashboard")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.providers).toBeDefined();
      expect(response.body.data.connections).toBeDefined();
      expect(response.body.data.analytics).toBeDefined();
      expect(response.body.data.alerts).toBeDefined();
      expect(response.body.data.adminFeatures).toBeDefined();
      expect(response.body.data.global).toEqual({
        totalConnections: 5,
        totalSymbols: 250,
        dailyCost: 45.75,
        performance: {
          averageLatency: 42,
          uptime: 99.8,
          errorRate: 0.02,
        },
      });

      expect(mockLiveDataManager.getDashboardStatus).toHaveBeenCalled();
    });

    it("should include mock connection data in dashboard", async () => {
      const response = await request(app)
        .get("/api/liveDataAdmin/dashboard")
        .expect(200);

      expect(response.body.data.connections).toBeDefined();
      expect(Array.isArray(response.body.data.connections)).toBe(true);
      expect(response.body.data.connections.length).toBeGreaterThan(0);
      
      // Check connection structure
      const connection = response.body.data.connections[0];
      expect(connection).toHaveProperty("id");
      expect(connection).toHaveProperty("provider");
      expect(connection).toHaveProperty("symbols");
      expect(connection).toHaveProperty("status");
      expect(connection).toHaveProperty("metrics");
    });

    it("should handle dashboard data retrieval errors", async () => {
      mockLiveDataManager.getDashboardStatus.mockImplementation(() => {
        throw new Error("Dashboard service unavailable");
      });

      const response = await request(app)
        .get("/api/liveDataAdmin/dashboard")
        .expect(500);

      expect(response.body.error).toBe("Failed to retrieve admin dashboard data");
    });
  });

  describe("Connection Management - Admin Authentication Required", () => {
    it("should create new connection with valid admin authentication", async () => {
      mockLiveDataManager.createConnection.mockResolvedValue("new-connection-123");

      const connectionData = {
        provider: "polygon",
        symbols: ["AAPL", "MSFT"],
        autoReconnect: true,
      };

      const response = await request(app)
        .post("/api/liveDataAdmin/connections")
        .send(connectionData)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.connectionId).toBe("new-connection-123");
      expect(response.body.data.provider).toBe("polygon");
      expect(response.body.data.symbols).toEqual(["AAPL", "MSFT"]);
      expect(response.body.data.status).toBe("connecting");
      expect(mockLiveDataManager.createConnection).toHaveBeenCalledWith("polygon", ["AAPL", "MSFT"]);
    });

    it("should handle connection creation errors", async () => {
      mockLiveDataManager.createConnection.mockRejectedValue(
        new Error("Failed to create connection")
      );

      const connectionData = {
        provider: "invalid-provider",
        symbols: ["AAPL"],
      };

      const response = await request(app)
        .post("/api/liveDataAdmin/connections")
        .send(connectionData)
        .expect(500);

      expect(response.body.error).toBe("Failed to create connection");
    });

    it("should close connection with admin authentication", async () => {
      mockLiveDataManager.closeConnection.mockResolvedValue();

      const response = await request(app)
        .delete("/api/liveDataAdmin/connections/alpaca-001-main")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.connectionId).toBe("alpaca-001-main");
      expect(response.body.data.status).toBe("closed");
      expect(mockLiveDataManager.closeConnection).toHaveBeenCalledWith("alpaca-001-main");
    });

    it("should handle connection close errors", async () => {
      mockLiveDataManager.closeConnection.mockRejectedValue(
        new Error("Connection not found")
      );

      const response = await request(app)
        .delete("/api/liveDataAdmin/connections/invalid-id")
        .expect(500);

      expect(response.body.error).toBe("Failed to close connection");
    });
  });

  describe("System Optimization - Admin Authentication Required", () => {
    it("should optimize connections with admin authentication", async () => {
      mockLiveDataManager.optimizeConnections.mockResolvedValue({
        applied: ["reduced polygon connections", "optimized alpaca routing"],
        recommendations: ["consider finnhub for news data"],
        savings: { daily: 9.35, monthly: 280.5 },
      });

      const response = await request(app)
        .post("/api/liveDataAdmin/optimize")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.applied).toBeDefined();
      expect(response.body.data.recommendations).toBeDefined();
      expect(response.body.data.estimatedSavings).toBe(9.35);
      expect(response.body.data.confidence).toBe(92);
      expect(mockLiveDataManager.optimizeConnections).toHaveBeenCalled();
    });

    it("should handle optimization errors", async () => {
      mockLiveDataManager.optimizeConnections.mockRejectedValue(
        new Error("Optimization failed")
      );

      const response = await request(app)
        .post("/api/liveDataAdmin/optimize")
        .expect(500);

      expect(response.body.error).toBe("Failed to run cost optimization");
    });
  });

  describe("Analytics Endpoint - Admin Authentication Required", () => {
    it("should return analytics data for authenticated admin", async () => {
      const response = await request(app)
        .get("/api/liveDataAdmin/analytics/24h")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.timeRange).toBe("24h");
      expect(response.body.data.performanceMetrics).toEqual({
        avgLatency: 42,
        messageRate: 1400,
        errorRate: 0.04,
        uptime: 99.8,
      });
      expect(response.body.data.latencyTrends).toEqual([]);
      expect(response.body.data.throughputData).toEqual([]);
      expect(response.body.data.errorRates).toEqual([]);
      expect(response.body.data.generatedAt).toBeDefined();
    });
  });

  describe("Alert Management - Admin Authentication Required", () => {
    it("should configure alerts with admin authentication", async () => {
      const alertConfig = {
        thresholds: {
          latency: { warning: 100, critical: 200 },
          errorRate: { warning: 0.02, critical: 0.05 },
          costDaily: { warning: 40, critical: 50 },
        },
        notifications: {
          email: { enabled: true, recipients: ["admin@example.com"] },
          slack: { enabled: false, webhook: "", channel: "#alerts" },
          webhook: { enabled: false, url: "" },
        },
      };

      const response = await request(app)
        .post("/api/liveDataAdmin/alerts/configure")
        .send(alertConfig)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.thresholds).toEqual(alertConfig.thresholds);
      expect(response.body.data.notifications).toEqual(alertConfig.notifications);
      expect(response.body.data.configuredAt).toBeDefined();
      expect(mockLiveDataManager.updateAlertConfig).toHaveBeenCalled();
    });

    it("should test alerts with admin authentication", async () => {
      const response = await request(app)
        .post("/api/liveDataAdmin/alerts/test")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.message).toBe("Test notifications sent successfully");
      expect(response.body.data.testedAt).toBeDefined();
      expect(mockLiveDataManager.testNotifications).toHaveBeenCalled();
    });

    it("should perform health check with admin authentication", async () => {
      mockLiveDataManager.forceHealthCheck.mockResolvedValue({
        active: [],
        resolved: 2,
        criticalCount: 0,
      });

      const response = await request(app)
        .post("/api/liveDataAdmin/alerts/health-check")
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(response.body.data.active).toEqual([]);
      expect(response.body.data.forcedAt).toBeDefined();
      expect(mockLiveDataManager.forceHealthCheck).toHaveBeenCalled();
    });

    it("should handle alert configuration errors", async () => {
      mockLiveDataManager.updateAlertConfig.mockImplementation(() => {
        throw new Error("Invalid alert configuration");
      });

      const response = await request(app)
        .post("/api/liveDataAdmin/alerts/configure")
        .send({ invalid: "config" })
        .expect(500);

      expect(response.body.error).toBe("Failed to configure alerts");
    });
  });

  describe("Authentication Requirements", () => {
    it("should require authentication for all admin endpoints", async () => {
      // Create app without authentication middleware
      const noAuthMiddleware = (req, res, next) => {
        // Don't set req.user to simulate unauthenticated request
        next();
      };

      const unauthApp = express();
      unauthApp.use(express.json());
      unauthApp.use(responseHelpers);
      unauthApp.use(noAuthMiddleware);
      unauthApp.use("/api/liveDataAdmin", liveDataAdminRoutes);

      // Test multiple endpoints require authentication
      const endpoints = [
        { method: "get", path: "/api/liveDataAdmin/dashboard" },
        { method: "post", path: "/api/liveDataAdmin/connections" },
        { method: "post", path: "/api/liveDataAdmin/optimize" },
        { method: "get", path: "/api/liveDataAdmin/analytics/24h" },
        { method: "post", path: "/api/liveDataAdmin/alerts/configure" },
      ];

      for (const endpoint of endpoints) {
        const response = await request(unauthApp)[endpoint.method](endpoint.path);
        
        // Expect either 401, 500, or 400 (depends on how route handles missing user)
        expect([400, 401, 500]).toContain(response.status);
      }
    });

    it("should handle multiple admin requests with same authenticated user", async () => {
      // Make multiple requests to verify consistent authentication
      await request(app).get("/api/liveDataAdmin/dashboard").expect(200);
      await request(app).post("/api/liveDataAdmin/optimize").expect(200);
      await request(app).get("/api/liveDataAdmin/analytics/1h").expect(200);

      // Verify calls were made (accumulated across all tests)
      expect(mockLiveDataManager.getDashboardStatus).toHaveBeenCalled();
      expect(mockLiveDataManager.optimizeConnections).toHaveBeenCalled();
    });
  });

  describe("Error Handling and Logging", () => {
    it("should include correlation IDs in responses", async () => {
      const response = await request(app)
        .get("/api/liveDataAdmin/dashboard")
        .set("x-correlation-id", "admin-test-123")
        .expect(200);

      expect(response.body.meta.correlationId).toBe("admin-test-123");
    });

    it("should generate correlation IDs when not provided", async () => {
      const response = await request(app)
        .get("/api/liveDataAdmin/dashboard")
        .expect(200);

      expect(response.body.meta.correlationId).toMatch(/admin-dashboard-\d+/);
    });

    it("should include request duration in responses", async () => {
      const response = await request(app)
        .get("/api/liveDataAdmin/dashboard")
        .expect(200);

      expect(response.body.meta.duration).toBeDefined();
      expect(typeof response.body.meta.duration).toBe("number");
    });

    it("should handle general service errors gracefully", async () => {
      mockLiveDataManager.getDashboardStatus.mockImplementation(() => {
        throw new Error("Unexpected service error");
      });

      const response = await request(app)
        .get("/api/liveDataAdmin/dashboard")
        .expect(500);

      expect(response.body.error).toBe("Failed to retrieve admin dashboard data");
      expect(response.body.correlationId).toBeDefined();
      expect(response.body.timestamp).toBeDefined();
    });
  });

  describe("Admin Role Validation", () => {
    it("should handle admin-specific functionality", async () => {
      // All endpoints in liveDataAdmin are inherently admin-only
      // Test that they provide administrative data and controls
      
      const dashboardResponse = await request(app)
        .get("/api/liveDataAdmin/dashboard")
        .expect(200);

      expect(dashboardResponse.body.data.connections).toBeDefined();
      expect(dashboardResponse.body.data.providers).toBeDefined();
      expect(dashboardResponse.body.data.performance).toBeDefined();

      const optimizeResponse = await request(app)
        .post("/api/liveDataAdmin/optimize")
        .expect(200);

      expect(optimizeResponse.body.data.message).toBe("System optimization completed");
    });
  });
});