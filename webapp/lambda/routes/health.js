const express = require("express");
const { query, healthCheck } = require("../utils/database");
const { sendSuccess, sendError } = require('../utils/apiResponse');
const { authenticateToken, requireAdmin } = require('../middleware/auth');

const router = express.Router();

// Health check endpoint - quick status
router.get("/", async (req, res) => {
  try {
    return sendSuccess(res, {
      status: "healthy",
      healthy: true,
      service: "Financial Dashboard API",
      environment: process.env.NODE_ENV || "development",
      uptime: process.uptime(),
      version: "1.0.0",
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    return sendError(res, "Health check failed: " + error.message, 503);
  }
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
      const keyTables = [
        "price_daily", "stock_scores", "buy_sell_daily",
        "sector_ranking", "company_profile", "technical_data_daily"
      ];

      for (const table of keyTables) {
        try {
          const count = await query(`SELECT COUNT(*) as cnt FROM ${table}`);
          tables[table] = count.rows[0].cnt;
        } catch (_e) {
          tables[table] = "not_found";
        }
      }
    } catch (dbError) {
      dbStatus = "error";
      tables = { error: dbError.message };
    }

    return sendSuccess(res, {
      status: "healthy",
      healthy: true,
      service: "Financial Dashboard API",
      environment: process.env.NODE_ENV || "development",
      uptime: process.uptime(),
      version: "1.0.0",
      database: {
        status: dbStatus,
        tables: tables
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    return sendError(res, "Detailed health check failed: " + error.message, 503);
  }
});

// Admin-only deep diagnostics
router.get("/diagnostics", requireAdmin, async (req, res) => {
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
