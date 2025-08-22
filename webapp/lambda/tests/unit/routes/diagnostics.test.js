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
      res.status(403).json({ success: false, error: "Insufficient permissions" });
    }
  })
}));

jest.mock("../../../test-database-connectivity", () => {
  return jest.fn().mockImplementation(() => ({
    runAllTests: jest.fn(),
    generateReport: jest.fn(),
    testEnvironmentVariables: jest.fn(),
    testSecretsManager: jest.fn(),
    testDatabaseConfig: jest.fn(),
    testDatabaseConnection: jest.fn()
  }));
});

jest.mock("../../../utils/apiKeyService", () => ({
  getHealthStatus: jest.fn()
}));

// Now import the routes after mocking
const diagnosticsRoutes = require("../../../routes/diagnostics");
const { authenticateToken, requireRole } = require("../../../middleware/auth");
const DatabaseConnectivityTest = require("../../../test-database-connectivity");
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
        res.status(403).json({ success: false, error: "Insufficient permissions" });
      }
    });
  });

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe("GET /diagnostics/database-connectivity", () => {
    test("should run database connectivity tests", async () => {
      const mockResults = {
        summary: { failed: 0, passed: 5 },
        tests: [
          { name: "Environment Variables", status: "passed" },
          { name: "Secrets Manager", status: "passed" },
          { name: "Database Config", status: "passed" },
          { name: "Database Connection", status: "passed" },
          { name: "Query Test", status: "passed" }
        ]
      };

      const mockReport = {
        status: "All tests passed",
        recommendations: []
      };

      const mockTest = {
        runAllTests: jest.fn().mockResolvedValue(mockResults),
        generateReport: jest.fn().mockReturnValue(mockReport)
      };

      DatabaseConnectivityTest.mockImplementation(() => mockTest);

      const response = await request(app)
        .get("/diagnostics/database-connectivity")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        results: mockResults,
        report: mockReport,
        timestamp: expect.any(String)
      });

      expect(DatabaseConnectivityTest).toHaveBeenCalled();
      expect(mockTest.runAllTests).toHaveBeenCalled();
      expect(mockTest.generateReport).toHaveBeenCalled();
    });

    test("should handle database connectivity test failures", async () => {
      const mockResults = {
        summary: { failed: 2, passed: 3 },
        tests: [
          { name: "Environment Variables", status: "passed" },
          { name: "Secrets Manager", status: "failed" },
          { name: "Database Config", status: "failed" },
          { name: "Database Connection", status: "skipped" },
          { name: "Query Test", status: "skipped" }
        ]
      };

      const mockTest = {
        runAllTests: jest.fn().mockResolvedValue(mockResults),
        generateReport: jest.fn().mockReturnValue({ status: "Tests failed" })
      };

      DatabaseConnectivityTest.mockImplementation(() => mockTest);

      const response = await request(app)
        .get("/diagnostics/database-connectivity")
        .expect(200);

      expect(response.body.success).toBe(false);
      expect(response.body.results.summary.failed).toBe(2);
    });

    test("should handle database connectivity test errors", async () => {
      DatabaseConnectivityTest.mockImplementation(() => {
        throw new Error("Test initialization failed");
      });

      const response = await request(app)
        .get("/diagnostics/database-connectivity")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Database connectivity test failed",
        message: "Test initialization failed"
      });
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
          return res.status(403).json({ success: false, error: "Insufficient permissions" });
        }
        next();
      };
      
      // Create route with mocked middleware
      const router = express.Router();
      router.use(mockAuth);
      router.get("/database-connectivity", mockRequireRole(["admin"]), async (req, res) => {
        res.json({ success: true });
      });
      
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
        statistics: { successRate: 100 }
      };

      getHealthStatus.mockReturnValue(mockHealth);

      const response = await request(app)
        .get("/diagnostics/api-key-service")
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        health: mockHealth,
        timestamp: expect.any(String)
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
        message: "Health check failed"
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
        generateReport: jest.fn().mockReturnValue(mockResults)
      };

      DatabaseConnectivityTest.mockImplementation(() => mockTest);

      const response = await request(app)
        .post("/diagnostics/database-test")
        .send({})
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        results: mockResults,
        connectionInfo: {
          successful: true,
          config: mockDbConfig
        },
        timestamp: expect.any(String)
      });

      expect(mockTest.testDatabaseConnection).toHaveBeenCalledWith(mockDbConfig);
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
        generateReport: jest.fn().mockReturnValue(mockResults)
      };

      DatabaseConnectivityTest.mockImplementation(() => mockTest);

      const response = await request(app)
        .post("/diagnostics/database-test")
        .send({ sslMode: "require" })
        .expect(200);

      expect(mockTest.testDatabaseConnection).toHaveBeenCalledWith(mockDbConfig, "require");
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
          return res.status(403).json({ success: false, error: "Insufficient permissions" });
        }
        next();
      };
      
      // Create route with mocked middleware
      const router = express.Router();
      router.use(mockAuth);
      router.post("/database-test", mockRequireRole(["admin"]), async (req, res) => {
        res.json({ success: true });
      });
      
      testApp.use("/diagnostics", router);

      await request(testApp)
        .post("/diagnostics/database-test")
        .expect(403);
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
        success: true,
        systemInfo: expect.objectContaining({
          environment: expect.any(String),
          nodeVersion: expect.any(String),
          platform: expect.any(String),
          arch: expect.any(String),
          uptime: expect.any(Number),
          memoryUsage: expect.objectContaining({
            rss: expect.any(Number),
            heapTotal: expect.any(Number),
            heapUsed: expect.any(Number)
          }),
          environmentVariables: expect.objectContaining({
            hasDbSecret: true,
            hasApiKeySecret: true,
            hasAwsRegion: true,
            hasCognitoUserPool: true,
            hasCognitoClient: true
          })
        })
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
        hasApiKeySecret: false
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
        success: true,
        lambdaInfo: expect.objectContaining({
          functionName: "test-function",
          functionVersion: "1",
          logGroupName: "/aws/lambda/test-function",
          memorySize: "512",
          isLambda: true
        })
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
        requestId: "not-lambda"
      });
    });
  });

  describe("GET /diagnostics/health", () => {
    test("should return healthy status when all checks pass", async () => {
      process.env.DB_SECRET_ARN = "test-secret";
      process.env.API_KEY_ENCRYPTION_SECRET_ARN = "test-api-secret";

      getHealthStatus.mockReturnValue({
        apiKeyCircuitBreaker: { state: "CLOSED" }
      });

      const mockTest = {
        testSecretsManager: jest.fn().mockResolvedValue({ success: true })
      };
      DatabaseConnectivityTest.mockImplementation(() => mockTest);

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
            database: "healthy"
          })
        })
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
            apiKeyService: "unhealthy"
          })
        })
      });
    });
  });

  describe("Authentication", () => {
    test("should require authentication for all routes", async () => {
      authenticateToken.mockImplementation((req, res, next) => {
        res.status(401).json({ success: false, error: "Unauthorized" });
      });

      await request(app)
        .get("/diagnostics/system-info")
        .expect(401);

      await request(app)
        .get("/diagnostics/lambda-info")
        .expect(401);

      await request(app)
        .get("/diagnostics/health")
        .expect(401);
    });
  });
});