const express = require("express");

const { query, healthCheck } = require("../utils/database");

const router = express.Router();

// System diagnostics endpoint
router.get("/", async (req, res) => {
  try {
    const diagnostics = {
      success: true,
      message: "System diagnostics completed successfully",
      timestamp: new Date().toISOString(),
      endpoints: [
        "GET /api/diagnostics - System diagnostics overview",
        "GET /api/diagnostics/database - Database connectivity test",
        "GET /api/diagnostics/database-connectivity - Database connectivity test"
      ],
      system: {
        nodejs: process.version,
        uptime: process.uptime(),
        memory: process.memoryUsage(),
        platform: process.platform,
        arch: process.arch,
      },
      database: await healthCheck(),
      environment: {
        node_env: process.env.NODE_ENV || "development",
        has_cognito: !!(
          process.env.AWS_REGION && process.env.COGNITO_USER_POOL_ID
        ),
      },
    };

    res.json(diagnostics);
  } catch (error) {
    console.error("Diagnostics error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to get system diagnostics",
      details: error.message,
    });
  }
});

// Database connectivity test
router.get("/database", async (req, res) => {
  try {
    const dbHealth = await healthCheck();
    const testQuery = await query("SELECT 1 as test");

    res.json({
      success: true,
      database: {
        ...dbHealth,
        query_test: testQuery.rows[0].test === 1 ? "passed" : "failed",
      },
    });
  } catch (error) {
    console.error("Database diagnostics error:", error);
    res.status(500).json({
      success: false,
      error: "Database diagnostics failed",
      details: error.message,
    });
  }
});

// Database connectivity test (alternative endpoint name)
router.get("/database-connectivity", async (req, res) => {
  try {
    const dbHealth = await healthCheck();
    const testQuery = await query("SELECT 1 as test");

    res.json({
      success: true,
      results: {
        connectivity_test: testQuery.rows[0].test === 1 ? "passed" : "failed",
        endpoint: "database-connectivity",
        database: {
          ...dbHealth,
        }
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Database connectivity error:", error);
    res.status(500).json({
      success: false,
      error: "Database connectivity test failed",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;
