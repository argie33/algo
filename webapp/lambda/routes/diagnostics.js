const express = require("express");
const {
  authenticateToken,
  requireRole,
} = require("../middleware/authEnhanced");
const DatabaseConnectivityTest = require("../test-database-connectivity");
const { getHealthStatus } = require("../utils/apiKeyService");

const router = express.Router();

// Apply authentication to all diagnostic routes
router.use(authenticateToken);

/**
 * Run comprehensive database connectivity test
 */
router.get(
  "/database-connectivity",
  requireRole(["admin"]),
  async (req, res) => {
    try {
      const test = new DatabaseConnectivityTest();
      const results = await test.runAllTests();
      const report = test.generateReport();

      res.json({
        success: results.summary.failed === 0,
        results: results,
        report: report,
        timestamp: new Date().toISOString(),
      });
    } catch (error) {
      console.error("Database connectivity test failed:", error);
      res.status(500).json({
        success: false,
        error: "Database connectivity test failed",
        message: error.message,
      });
    }
  }
);

/**
 * Get API key service health status
 */
router.get("/api-key-service", async (req, res) => {
  try {
    const health = getHealthStatus();

    res.json({
      success: true,
      health: health,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("API key service health check failed:", error);
    res.status(500).json({
      success: false,
      error: "API key service health check failed",
      message: error.message,
    });
  }
});

/**
 * Test specific database connection configuration
 */
router.post("/database-test", requireRole(["admin"]), async (req, res) => {
  const { sslMode = "auto" } = req.body;

  try {
    const test = new DatabaseConnectivityTest();

    // Test environment variables
    const envOk = test.testEnvironmentVariables();

    // Test AWS Secrets Manager
    const secret = await test.testSecretsManager();

    // Test database configuration
    const dbConfig = await test.testDatabaseConfig(secret);

    // Test database connection with specific SSL mode
    let connectionInfo = null;
    if (dbConfig && sslMode !== "auto") {
      connectionInfo = await test.testDatabaseConnection(dbConfig, sslMode);
    } else if (dbConfig) {
      connectionInfo = await test.testDatabaseConnection(dbConfig);
    }

    const results = test.generateReport();

    res.json({
      success: results.summary.failed === 0,
      results: results,
      connectionInfo: connectionInfo
        ? {
            successful: true,
            config: connectionInfo.config,
          }
        : null,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Database test failed:", error);
    res.status(500).json({
      success: false,
      error: "Database test failed",
      message: error.message,
    });
  }
});

/**
 * Get system information
 */
router.get("/system-info", async (req, res) => {
  try {
    const systemInfo = {
      environment: process.env.NODE_ENV || "development",
      nodeVersion: process.version,
      platform: process.platform,
      arch: process.arch,
      uptime: process.uptime(),
      memoryUsage: process.memoryUsage(),
      cpuUsage: process.cpuUsage(),
      timestamp: new Date().toISOString(),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      environmentVariables: {
        hasDbSecret: !!process.env.DB_SECRET_ARN,
        hasApiKeySecret: !!process.env.API_KEY_ENCRYPTION_SECRET_ARN,
        hasAwsRegion: !!process.env.WEBAPP_AWS_REGION,
        hasCognitoUserPool: !!process.env.COGNITO_USER_POOL_ID,
        hasCognitoClient: !!process.env.COGNITO_CLIENT_ID,
        nodeEnv: process.env.NODE_ENV || "not-set",
      },
    };

    res.json({
      success: true,
      systemInfo: systemInfo,
    });
  } catch (error) {
    console.error("System info error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to get system info",
      message: error.message,
    });
  }
});

/**
 * Test external service connectivity
 */
router.post("/external-services", async (req, res) => {
  const { testAlpaca = false, testPolygon = false } = req.body;

  try {
    const results = {
      aws: {
        secretsManager: { status: "unknown" },
        region: process.env.WEBAPP_AWS_REGION || "not-set",
      },
      database: { status: "unknown" },
      external: {},
    };

    // Test AWS Secrets Manager
    if (process.env.DB_SECRET_ARN) {
      const {
        SecretsManagerClient,
        GetSecretValueCommand,
      } = require("@aws-sdk/client-secrets-manager");
      const secretsManager = new SecretsManagerClient({
        region: process.env.WEBAPP_AWS_REGION || "us-east-1",
      });

      try {
        const command = new GetSecretValueCommand({
          SecretId: process.env.DB_SECRET_ARN,
        });
        await secretsManager.send(command);
        results.aws.secretsManager.status = "connected";
      } catch (error) {
        results.aws.secretsManager.status = "error";
        results.aws.secretsManager.error = error.message;
      }
    }

    // Test database
    if (results.aws.secretsManager.status === "connected") {
      try {
        const test = new DatabaseConnectivityTest();
        const secret = await test.testSecretsManager();
        const dbConfig = await test.testDatabaseConfig(secret);
        const connectionInfo = await test.testDatabaseConnection(dbConfig);

        results.database.status = connectionInfo ? "connected" : "error";
        if (connectionInfo) {
          results.database.config = connectionInfo.config;
        }
      } catch (error) {
        results.database.status = "error";
        results.database.error = error.message;
      }
    }

    // Test external services if requested
    if (testAlpaca && req.user) {
      try {
        const { getApiKey } = require("../utils/apiKeyService");
        const alpacaKey = await getApiKey(req.token, "alpaca");

        if (alpacaKey) {
          const AlpacaService = require("../utils/alpacaService");
          const alpacaService = new AlpacaService(
            alpacaKey.apiKey,
            alpacaKey.apiSecret,
            alpacaKey.isSandbox
          );

          const validation = await alpacaService.validateCredentials();
          results.external.alpaca = validation;
        } else {
          results.external.alpaca = { status: "no-key" };
        }
      } catch (error) {
        results.external.alpaca = { status: "error", error: error.message };
      }
    }

    const overallSuccess =
      results.aws.secretsManager.status === "connected" &&
      results.database.status === "connected";

    res.json({
      success: overallSuccess,
      results: results,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("External services test failed:", error);
    res.status(500).json({
      success: false,
      error: "External services test failed",
      message: error.message,
    });
  }
});

/**
 * Get Lambda function information
 */
router.get("/lambda-info", async (req, res) => {
  try {
    const lambdaInfo = {
      functionName: process.env.AWS_LAMBDA_FUNCTION_NAME || "not-lambda",
      functionVersion: process.env.AWS_LAMBDA_FUNCTION_VERSION || "not-lambda",
      logGroupName: process.env.AWS_LAMBDA_LOG_GROUP_NAME || "not-lambda",
      logStreamName: process.env.AWS_LAMBDA_LOG_STREAM_NAME || "not-lambda",
      memorySize: process.env.AWS_LAMBDA_FUNCTION_MEMORY_SIZE || "not-lambda",
      timeout: process.env.AWS_LAMBDA_FUNCTION_TIMEOUT || "not-lambda",
      region: process.env.AWS_REGION || "not-set",
      isLambda: !!process.env.AWS_LAMBDA_FUNCTION_NAME,
      requestId: req.context?.awsRequestId || "not-lambda",
      remainingTime: req.context?.getRemainingTimeInMillis
        ? req.context.getRemainingTimeInMillis()
        : "not-lambda",
    };

    res.json({
      success: true,
      lambdaInfo: lambdaInfo,
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Lambda info error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to get Lambda info",
      message: error.message,
    });
  }
});

/**
 * Comprehensive health check
 */
router.get("/health", async (req, res) => {
  try {
    const health = {
      status: "healthy",
      timestamp: new Date().toISOString(),
      checks: {},
    };

    // Check environment variables
    const requiredEnvVars = ["DB_SECRET_ARN", "API_KEY_ENCRYPTION_SECRET_ARN"];
    const envCheck = requiredEnvVars.every((varName) => !!process.env[varName]);
    health.checks.environment = envCheck ? "healthy" : "unhealthy";

    // Check API key service
    try {
      const apiKeyHealth = getHealthStatus();
      health.checks.apiKeyService =
        apiKeyHealth.apiKeyCircuitBreaker.state === "CLOSED"
          ? "healthy"
          : "unhealthy";
    } catch (error) {
      health.checks.apiKeyService = "unhealthy";
    }

    // Check database connectivity (quick test)
    if (process.env.DB_SECRET_ARN) {
      try {
        const test = new DatabaseConnectivityTest();
        const secret = await test.testSecretsManager();
        health.checks.database = secret ? "healthy" : "unhealthy";
      } catch (error) {
        health.checks.database = "unhealthy";
      }
    } else {
      health.checks.database = "unhealthy";
    }

    // Overall status
    const allHealthy = Object.values(health.checks).every(
      (check) => check === "healthy"
    );
    health.status = allHealthy ? "healthy" : "unhealthy";

    res.status(allHealthy ? 200 : 503).json({
      success: allHealthy,
      health: health,
    });
  } catch (error) {
    console.error("Health check failed:", error);
    res.status(500).json({
      success: false,
      error: "Health check failed",
      message: error.message,
    });
  }
});

module.exports = router;
