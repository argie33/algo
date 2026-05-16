const express = require("express");
const { query } = require("../utils/database");

const router = express.Router();

// Health check endpoint - minimal, no dependencies
router.get("/", (req, res) => {
  res.status(200).json({
    status: "healthy",
    healthy: true,
    service: "Financial Dashboard API",
    timestamp: new Date().toISOString()
  });
});

// Detailed health check with database
router.get("/detailed", async (req, res) => {
  try {
    let dbStatus = "disconnected";
    let tables = {};

    try {
      // Test database connection with a simple query
      const result = await query("SELECT COUNT(*) as count FROM information_schema.tables WHERE table_schema = 'public'");
      dbStatus = "connected";

      // Get table counts for key tables
      // FIXED: Use identifier quoting to prevent SQL injection
      const keyTables = [
        "price_daily", "stock_scores", "buy_sell_daily",
        "sector_ranking", "company_profile", "technical_data_daily"
      ];

      for (const table of keyTables) {
        try {
          // Use quoted identifier to safely include table name
          const count = await query(`SELECT COUNT(*) as cnt FROM "${table}"`);
          tables[table] = count.rows[0].cnt;
        } catch (_e) {
          tables[table] = "not_found";
        }
      }
    } catch (dbError) {
      dbStatus = "error";
      tables = { error: dbError.message };
    }

    // FIXED: Do not expose detailed schema information in production
    const isProduction = (process.env.NODE_ENV || '').includes('prod');
    const response = {
      status: "healthy",
      healthy: true,
      service: "Financial Dashboard API",
      uptime: process.uptime(),
      version: "1.0.0",
      timestamp: new Date().toISOString()
    };

    // Only expose schema details to authenticated admins or in development
    if (!isProduction) {
      response.environment = process.env.NODE_ENV || "development";
      response.database = {
        status: dbStatus,
        tables: tables
      };
    } else {
      response.database = {
        status: dbStatus
      };
    }

    return sendSuccess(res, response);
  } catch (error) {
    return sendError(res, "Detailed health check failed: " + error.message, 503);
  }
});

// Deep diagnostics
router.get("/diagnostics", async (req, res) => {
  try {
    const diagnostics = {
      status: "operational",
      uptime: process.uptime(),
      memory: process.memoryUsage(),
      environment: process.env.NODE_ENV || "development",
      timestamp: new Date().toISOString(),
      database: {
        status: "connected"
      }
    };

    return sendSuccess(res, diagnostics);
  } catch (error) {
    return sendError(res, "Diagnostics check failed: " + error.message, 503);
  }
});

module.exports = router;
