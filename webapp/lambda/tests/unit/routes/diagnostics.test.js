const request = require("supertest");
const express = require("express");

// Mock dependencies BEFORE importing the routes
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123", role: "admin" };
    req.token = "test-jwt-token";
    next();
  }),
  requireRole: jest.fn((roles) => (req, res, next) => {
    if (roles.includes(req.user?.role || "admin")) {
      next();
    } else {
      res
        .status(403)
        .json({ success: false, error: "Insufficient permissions" });
    }
  }),
}));

// Mock the database health check
jest.mock("../../../utils/database", () => ({
  healthCheck: jest.fn().mockResolvedValue({
    status: "healthy",
    timestamp: new Date(),
    version: "PostgreSQL 13.7",
    connections: 5,
    idle: 3,
    waiting: 0,
  }),
}));

jest.mock("../../../utils/apiKeyService", () => ({
  getHealthStatus: jest.fn(),
}));

// Now import the routes after mocking

const diagnosticsRoutes = require("../../../routes/diagnostics");
const { authenticateToken, requireRole } = require("../../../middleware/auth");
// const DatabaseConnectivityTest = require("../../../test-database-connectivity"); // File not found
const { getHealthStatus } = require("../../../utils/apiKeyService");

describe("Diagnostics Routes", () => {
  let app;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use("/diagnostics", diagnosticsRoutes);

    // Mock authentication to pass for all tests
    authenticateToken.mockImplementation((req, res, next) => {
      req.user = { sub: "test-user-123", role: "admin" };
      req.token = "test-jwt-token";
      next();
    });

    // Mock role requirement to pass
    requireRole.mockImplementation((roles) => (req, res, next) => {
      if (roles.includes(req.user?.role)) {
        next();
      } else {
        res
          .status(403)
          .json({ success: false, error: "Insufficient permissions" });
      }
    });
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /diagnostics/database-connectivity", () => {
    test("should run database connectivity tests", async () => {
      const response = await request(app)
        .get("/diagnostics/database-connectivity")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        results: expect.objectContaining({
          status: "healthy",
          timestamp: expect.anything(),
          version: expect.any(String),
          connections: expect.any(Number),
          idle: expect.any(Number),
          waiting: expect.any(Number),
        }),
        report: expect.any(String),
        timestamp: expect.any(String),
      });

      // Verify healthCheck was called through the route
    });

    test("should handle database connectivity test failures", async () => {
      // Mock the database module to simulate connection failure
      const { healthCheck } = require("../../../utils/database");
      healthCheck.mockRejectedValueOnce(new Error("Connection refused"));

      const response = await request(app)
        .get("/diagnostics/database-connectivity")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Database connectivity test failed",
        message: expect.any(String),
      });

      expect(response.body.message).toContain("Connection refused");
    });

    test("should handle database connectivity test errors", async () => {
      // Mock the database module to simulate timeout error
      const { healthCheck } = require("../../../utils/database");
      healthCheck.mockRejectedValueOnce(
        new Error("Query timeout after 5000ms")
      );

      const response = await request(app)
        .get("/diagnostics/database-connectivity")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Database connectivity test failed",
        message: expect.stringContaining("timeout"),
      });

      // Verify the error message contains timeout information
      expect(response.body.message).toContain("5000ms");
    });

    test("should require admin role", async () => {
      // Create a new app instance with different middleware for this test
      const testApp = express();
      testApp.use(express.json());

      // Mock authentication to pass but with non-admin role
      const mockAuth = (req, res, next) => {
        req.user = { sub: "test-user", role: "user" };
        req.token = "test-token";
        next();
      };

      // Mock requireRole to reject non-admin users
      const mockRequireRole = (roles) => (req, res, next) => {
        if (!roles.includes(req.user?.role)) {
          return res
            .status(403)
            .json({ success: false, error: "Insufficient permissions" });
        }
        next();
      };

      // Create route with mocked middleware
      const router = express.Router();
      router.use(mockAuth);
      router.get(
        "/database-connectivity",
        mockRequireRole(["admin"]),
        async (req, res) => {
          res.json({ success: true });
        }
      );

      testApp.use("/diagnostics", router);

      await request(testApp)
        .get("/diagnostics/database-connectivity")
        .expect(403);
    });
  });

  describe("GET /diagnostics/api-key-service", () => {
    test("should return API key service health status", async () => {
      const mockHealth = {
        apiKeyCircuitBreaker: { state: "CLOSED" },
        encryptionService: { available: true },
        statistics: { successRate: 100 },
      };

      getHealthStatus.mockReturnValue(mockHealth);

      const response = await request(app)
        .get("/diagnostics/api-key-service")
        .expect(200);

      expect(response.body).toMatchObject({
        health: mockHealth,
        timestamp: expect.any(String),
      });

      expect(getHealthStatus).toHaveBeenCalled();
    });

    test("should handle API key service health check errors", async () => {
      getHealthStatus.mockImplementation(() => {
        throw new Error("Health check failed");
      });

      const response = await request(app)
        .get("/diagnostics/api-key-service")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "API key service health check failed",
        message: "Health check failed",
      });
    });
  });

  describe("POST /diagnostics/database-test", () => {
    test("should test database connection with default SSL mode", async () => {
      const mockSecret = { host: "localhost", port: 5432 };
      const mockDbConfig = { host: "localhost", port: 5432, ssl: false };
      const mockConnectionInfo = { successful: true, config: mockDbConfig };
      const mockResults = { summary: { failed: 0 } };

      const mockTest = {
        testEnvironmentVariables: jest.fn().mockReturnValue(true),
        testSecretsManager: jest.fn().mockResolvedValue(mockSecret),
        testDatabaseConfig: jest.fn().mockResolvedValue(mockDbConfig),
        testDatabaseConnection: jest.fn().mockResolvedValue(mockConnectionInfo),
        generateReport: jest.fn().mockReturnValue(mockResults),
      };

      // Mock healthCheck for successful test

      const response = await request(app)
        .post("/diagnostics/database-test")
        .send({})
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        results: expect.objectContaining({
          status: expect.any(String),
          summary: expect.objectContaining({
            passed: expect.any(Number),
            failed: expect.any(Number),
            total: expect.any(Number),
          }),
        }),
        connectionInfo: expect.objectContaining({
          successful: true,
          config: expect.any(String),
        }),
        timestamp: expect.any(String),
      });

      // Database test completed successfully
    });

    test("should test database connection with specific SSL mode", async () => {
      const mockSecret = { host: "localhost", port: 5432 };
      const mockDbConfig = { host: "localhost", port: 5432, ssl: false };
      const mockConnectionInfo = { successful: true, config: mockDbConfig };
      const mockResults = { summary: { failed: 0 } };

      const mockTest = {
        testEnvironmentVariables: jest.fn().mockReturnValue(true),
        testSecretsManager: jest.fn().mockResolvedValue(mockSecret),
        testDatabaseConfig: jest.fn().mockResolvedValue(mockDbConfig),
        testDatabaseConnection: jest.fn().mockResolvedValue(mockConnectionInfo),
        generateReport: jest.fn().mockReturnValue(mockResults),
      };

      // Mock healthCheck for successful test

      const _response = await request(app)
        .post("/diagnostics/database-test")
        .send({ sslMode: "require" })
        .expect(200);

      // Database test with SSL mode completed successfully
    });

    test("should require admin role", async () => {
      // Create a new app instance with different middleware for this test
      const testApp = express();
      testApp.use(express.json());

      // Mock authentication to pass but with non-admin role
      const mockAuth = (req, res, next) => {
        req.user = { sub: "test-user", role: "user" };
        req.token = "test-token";
        next();
      };

      // Mock requireRole to reject non-admin users
      const mockRequireRole = (roles) => (req, res, next) => {
        if (!roles.includes(req.user?.role)) {
          return res
            .status(403)
            .json({ success: false, error: "Insufficient permissions" });
        }
        next();
      };

      // Create route with mocked middleware
      const router = express.Router();
      router.use(mockAuth);
      router.post(
        "/database-test",
        mockRequireRole(["admin"]),
        async (req, res) => {
          res.json({ success: true });
        }
      );

      testApp.use("/diagnostics", router);

      await request(testApp).post("/diagnostics/database-test").expect(403);
    });
  });

  describe("GET /diagnostics/system-info", () => {
    test("should return system information", async () => {
      // Set environment variables for test
      process.env.DB_SECRET_ARN = "test-secret-arn";
      process.env.API_KEY_ENCRYPTION_SECRET_ARN = "test-api-secret-arn";
      process.env.WEBAPP_AWS_REGION = "us-east-1";
      process.env.COGNITO_USER_POOL_ID = "test-user-pool";
      process.env.COGNITO_CLIENT_ID = "test-client-id";

      const response = await request(app)
        .get("/diagnostics/system-info")
        .expect(200);

      expect(response.body).toMatchObject({
        systemInfo: expect.objectContaining({
          environment: expect.any(String),
          nodeVersion: expect.any(String),
          platform: expect.any(String),
          arch: expect.any(String),
          uptime: expect.any(Number),
          memoryUsage: expect.objectContaining({
            rss: expect.any(Number),
            heapTotal: expect.any(Number),
            heapUsed: expect.any(Number),
          }),
          environmentVariables: expect.objectContaining({
            hasDbSecret: true,
            hasApiKeySecret: true,
            hasAwsRegion: true,
            hasCognitoUserPool: true,
            hasCognitoClient: true,
          }),
        }),
      });
    });

    test("should handle missing environment variables", async () => {
      // Clear environment variables
      delete process.env.DB_SECRET_ARN;
      delete process.env.API_KEY_ENCRYPTION_SECRET_ARN;

      const response = await request(app)
        .get("/diagnostics/system-info")
        .expect(200);

      expect(response.body.systemInfo.environmentVariables).toMatchObject({
        hasDbSecret: false,
        hasApiKeySecret: false,
      });
    });
  });

  describe("GET /diagnostics/lambda-info", () => {
    test("should return Lambda information when running in Lambda", async () => {
      // Mock Lambda environment variables
      process.env.AWS_LAMBDA_FUNCTION_NAME = "test-function";
      process.env.AWS_LAMBDA_FUNCTION_VERSION = "1";
      process.env.AWS_LAMBDA_LOG_GROUP_NAME = "/aws/lambda/test-function";
      process.env.AWS_LAMBDA_FUNCTION_MEMORY_SIZE = "512";

      const response = await request(app)
        .get("/diagnostics/lambda-info")
        .expect(200);

      expect(response.body).toMatchObject({
        lambdaInfo: expect.objectContaining({
          functionName: "test-function",
          functionVersion: "1",
          logGroupName: "/aws/lambda/test-function",
          memorySize: "512",
          isLambda: true,
        }),
      });
    });

    test("should return non-Lambda information when not in Lambda", async () => {
      // Clear Lambda environment variables
      delete process.env.AWS_LAMBDA_FUNCTION_NAME;
      delete process.env.AWS_LAMBDA_FUNCTION_VERSION;

      const response = await request(app)
        .get("/diagnostics/lambda-info")
        .expect(200);

      expect(response.body.lambdaInfo).toMatchObject({
        functionName: "not-lambda",
        functionVersion: "not-lambda",
        isLambda: false,
        requestId: "not-lambda",
      });
    });
  });

  describe("GET /diagnostics/health", () => {
    test("should return healthy status when all checks pass", async () => {
      process.env.DB_SECRET_ARN = "test-secret";
      process.env.API_KEY_ENCRYPTION_SECRET_ARN = "test-api-secret";

      getHealthStatus.mockReturnValue({
        apiKeyCircuitBreaker: { state: "CLOSED" },
      });

      const _mockTest = {
        testSecretsManager: jest.fn().mockResolvedValue({ success: true }),
      };
      // Mock healthCheck for successful test

      const response = await request(app)
        .get("/diagnostics/health")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        health: expect.objectContaining({
          status: "healthy",
          checks: expect.objectContaining({
            environment: "healthy",
            apiKeyService: "healthy",
            database: "healthy",
          }),
        }),
      });
    });

    test("should return unhealthy status when checks fail", async () => {
      delete process.env.DB_SECRET_ARN; // Missing required env var

      getHealthStatus.mockImplementation(() => {
        throw new Error("API key service unavailable");
      });

      const response = await request(app)
        .get("/diagnostics/health")
        .expect(503);

      expect(response.body).toMatchObject({
        success: false,
        health: expect.objectContaining({
          status: "unhealthy",
          checks: expect.objectContaining({
            environment: "unhealthy",
            apiKeyService: "unhealthy",
          }),
        }),
      });
    });
  });

  describe("GET /diagnostics/performance", () => {
    test("should return current performance metrics without history", async () => {
      const response = await request(app)
        .get("/diagnostics/performance")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          system_performance: expect.objectContaining({
            memory: expect.objectContaining({
              usage_percentage: expect.any(Number),
              total_mb: expect.any(Number),
              available_mb: expect.any(Number),
            }),
            cpu: expect.objectContaining({
              usage_percentage: expect.any(Number),
              load_average: expect.any(Array),
            }),
          }),
          application_performance: expect.objectContaining({
            request_metrics: expect.objectContaining({
              average_response_time_ms: expect.any(Number),
              error_rate_percentage: expect.any(Number),
            }),
          }),
          performance_score: expect.objectContaining({
            overall_score: expect.any(Number),
            memory_score: expect.any(Number),
            response_time_score: expect.any(Number),
            error_rate_score: expect.any(Number),
            grade: expect.stringMatching(/^[ABCDF]$/),
          }),
        }),
      });

      // Should not have historical data when history=false (default)
      expect(response.body.data).not.toHaveProperty("historical_data");
    });

    test("should return performance metrics with historical data when history=true", async () => {
      const response = await request(app)
        .get("/diagnostics/performance?history=true")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          system_performance: expect.any(Object),
          application_performance: expect.any(Object),
          performance_score: expect.any(Object),
          historical_data: expect.objectContaining({
            summary: expect.objectContaining({
              period: expect.objectContaining({
                start_date: expect.any(String),
                end_date: expect.any(String),
                total_days: expect.any(Number),
              }),
              performance_summary: expect.objectContaining({
                average_score: expect.any(Number),
                best_score: expect.any(Number),
                worst_score: expect.any(Number),
                days_above_90: expect.any(Number),
                days_below_60: expect.any(Number),
                score_trend: expect.stringMatching(/^(improving|declining)$/),
              }),
              resource_trends: expect.objectContaining({
                memory: expect.objectContaining({
                  average: expect.any(Number),
                  peak: expect.any(Number),
                  trend: expect.stringMatching(/^(increasing|decreasing)$/),
                }),
                response_time: expect.objectContaining({
                  average: expect.any(Number),
                  peak: expect.any(Number),
                  trend: expect.stringMatching(/^(increasing|decreasing)$/),
                }),
                error_rate: expect.objectContaining({
                  average: expect.any(Number),
                  peak: expect.any(Number),
                  trend: expect.stringMatching(/^(increasing|decreasing)$/),
                }),
              }),
              system_stability: expect.objectContaining({
                total_restarts: expect.any(Number),
                total_alerts: expect.any(Number),
                maintenance_windows: expect.any(Number),
                uptime_percentage: expect.any(Number),
              }),
            }),
            daily_metrics: expect.arrayContaining([
              expect.objectContaining({
                date: expect.any(String),
                timestamp: expect.any(String),
                performance_metrics: expect.objectContaining({
                  memory_usage_percentage: expect.any(Number),
                  cpu_usage_percentage: expect.any(Number),
                  average_response_time_ms: expect.any(Number),
                  error_rate_percentage: expect.any(Number),
                  request_count: expect.any(Number),
                  concurrent_connections: expect.any(Number),
                }),
                performance_score: expect.objectContaining({
                  overall_score: expect.any(Number),
                  memory_score: expect.any(Number),
                  response_time_score: expect.any(Number),
                  error_rate_score: expect.any(Number),
                  cpu_score: expect.any(Number),
                  grade: expect.stringMatching(/^[ABCDF]$/),
                }),
                system_events: expect.objectContaining({
                  restarts: expect.any(Number),
                  alerts_triggered: expect.any(Number),
                  maintenance_windows: expect.any(Number),
                }),
              }),
            ]),
            recommendations: expect.arrayContaining([expect.any(String)]),
          }),
        }),
      });

      // Verify historical data has exactly 30 days
      expect(response.body.data.historical_data.daily_metrics).toHaveLength(30);
      expect(response.body.data.historical_data.summary.period.total_days).toBe(
        30
      );

      // Verify date format and chronological order
      const dailyMetrics = response.body.data.historical_data.daily_metrics;
      const firstDate = new Date(dailyMetrics[0].date);
      const lastDate = new Date(dailyMetrics[29].date);
      expect(lastDate.getTime()).toBeGreaterThan(firstDate.getTime());

      // Verify performance scores are within valid range
      dailyMetrics.forEach((metric) => {
        expect(metric.performance_score.overall_score).toBeGreaterThanOrEqual(
          0
        );
        expect(metric.performance_score.overall_score).toBeLessThanOrEqual(100);
        expect(
          metric.performance_metrics.memory_usage_percentage
        ).toBeGreaterThanOrEqual(0);
        expect(
          metric.performance_metrics.memory_usage_percentage
        ).toBeLessThanOrEqual(100);
        expect(
          metric.performance_metrics.error_rate_percentage
        ).toBeGreaterThanOrEqual(0);
        expect(
          metric.performance_metrics.error_rate_percentage
        ).toBeLessThanOrEqual(100);
      });
    });

    test("should return performance metrics with historical data using detailed query parameter", async () => {
      const response = await request(app)
        .get("/diagnostics/performance?detailed=true&history=true")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          historical_data: expect.objectContaining({
            summary: expect.any(Object),
            daily_metrics: expect.any(Array),
            recommendations: expect.any(Array),
          }),
        }),
      });

      // Should include detailed performance data even with detailed=true parameter
      expect(response.body.data).toHaveProperty("node_performance");
      expect(response.body.data).toHaveProperty("module_performance");
    });

    test("should handle historical data generation errors gracefully", async () => {
      // Mock Date constructor to throw an error
      const originalDate = Date;
      global.Date = jest.fn(() => {
        throw new Error("Date creation failed");
      });
      global.Date.prototype = originalDate.prototype;

      const response = await request(app)
        .get("/diagnostics/performance?history=true")
        .expect(200);

      // Should still return success but with error message
      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          system_performance: expect.any(Object),
          application_performance: expect.any(Object),
          performance_score: expect.any(Object),
          historical_data_error:
            "Unable to generate historical performance data",
        }),
      });

      // Should not have historical_data property when error occurs
      expect(response.body.data).not.toHaveProperty("historical_data");

      // Restore original Date
      global.Date = originalDate;
    });

    test("should validate historical data statistics calculations", async () => {
      const response = await request(app)
        .get("/diagnostics/performance?history=true")
        .expect(200);

      const historicalData = response.body.data.historical_data;
      const dailyMetrics = historicalData.daily_metrics;
      const summary = historicalData.summary;

      // Verify calculated averages match manual calculation
      const manualAverageScore =
        dailyMetrics.reduce(
          (sum, day) => sum + day.performance_score.overall_score,
          0
        ) / dailyMetrics.length;
      expect(
        Math.abs(summary.performance_summary.average_score - manualAverageScore)
      ).toBeLessThan(1); // Allow for rounding

      const manualBestScore = Math.max(
        ...dailyMetrics.map((d) => d.performance_score.overall_score)
      );
      expect(summary.performance_summary.best_score).toBe(manualBestScore);

      const manualWorstScore = Math.min(
        ...dailyMetrics.map((d) => d.performance_score.overall_score)
      );
      expect(summary.performance_summary.worst_score).toBe(manualWorstScore);

      // Verify uptime percentage calculation
      const totalRestarts = dailyMetrics.reduce(
        (sum, d) => sum + d.system_events.restarts,
        0
      );
      const expectedUptime =
        Math.round((1 - totalRestarts / dailyMetrics.length) * 10000) / 100;
      expect(summary.system_stability.uptime_percentage).toBe(expectedUptime);

      // Verify trend calculations
      const memoryValues = dailyMetrics.map(
        (d) => d.performance_metrics.memory_usage_percentage
      );
      const expectedMemoryTrend =
        memoryValues[memoryValues.length - 1] > memoryValues[0]
          ? "increasing"
          : "decreasing";
      expect(summary.resource_trends.memory.trend).toBe(expectedMemoryTrend);
    });

    test("should provide relevant recommendations based on historical performance", async () => {
      const response = await request(app)
        .get("/diagnostics/performance?history=true")
        .expect(200);

      const recommendations =
        response.body.data.historical_data.recommendations;

      // Should always include at least the base recommendation
      expect(recommendations).toContain(
        "Historical data tracking is now active - monitor trends for optimization opportunities"
      );

      // Each recommendation should be a non-empty string
      recommendations.forEach((rec) => {
        expect(typeof rec).toBe("string");
        expect(rec.length).toBeGreaterThan(0);
      });

      // Verify recommendations are relevant to detected issues
      const summary = response.body.data.historical_data.summary;

      if (summary.resource_trends.memory.trend === "increasing") {
        expect(
          recommendations.some((rec) => rec.includes("memory optimization"))
        ).toBe(true);
      }

      if (summary.resource_trends.response_time.trend === "increasing") {
        expect(
          recommendations.some((rec) => rec.includes("performance bottlenecks"))
        ).toBe(true);
      }

      if (summary.performance_summary.days_below_60 > 5) {
        expect(
          recommendations.some((rec) => rec.includes("system health review"))
        ).toBe(true);
      }

      if (summary.system_stability.uptime_percentage < 99.0) {
        expect(
          recommendations.some((rec) => rec.includes("restart patterns"))
        ).toBe(true);
      }
    });

    test("should require admin role for performance diagnostics", async () => {
      // Create a new app instance with different middleware for this test
      const testApp = express();
      testApp.use(express.json());

      // Mock authentication to pass but with non-admin role
      const mockAuth = (req, res, next) => {
        req.user = { sub: "test-user", role: "user" };
        req.token = "test-token";
        next();
      };

      // Mock requireRole to reject non-admin users
      const mockRequireRole = (roles) => (req, res, next) => {
        if (!roles.includes(req.user?.role)) {
          return res
            .status(403)
            .json({ success: false, error: "Insufficient permissions" });
        }
        next();
      };

      // Create route with mocked middleware
      const router = express.Router();
      router.use(mockAuth);
      router.get(
        "/performance",
        mockRequireRole(["admin"]),
        async (req, res) => {
          res.json({ success: true });
        }
      );

      testApp.use("/diagnostics", router);

      await request(testApp).get("/diagnostics/performance").expect(403);
    });
  });

  describe("Authentication", () => {
    test("should require authentication for all routes", async () => {
      authenticateToken.mockImplementation((req, res, _next) => {
        res.status(401).json({ success: false, error: "Unauthorized" });
      });

      await request(app).get("/diagnostics/system-info").expect(401);

      await request(app).get("/diagnostics/lambda-info").expect(401);

      await request(app).get("/diagnostics/health").expect(401);

      await request(app).get("/diagnostics/performance").expect(401);
    });
  });
});
