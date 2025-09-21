const express = require("express");
const { query, healthCheck } = require("../utils/database");

const router = express.Router();

// System diagnostics endpoint
router.get("/", async (req, res) => {
  try {
    const diagnostics = {
      success: true,
      timestamp: new Date().toISOString(),
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

module.exports = router;
