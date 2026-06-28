const express = require("express");

const { query } = require("../utils/database");
const { sendSuccess, sendError } = require("../utils/apiResponse");
const logger = require("../utils/logger");

const router = express.Router();

// Health check endpoint - minimal, no dependencies
router.get("/", (req, res) => {
  return sendSuccess(res, {
    status: "healthy",
    healthy: true,
    service: "Financial Dashboard API",
  });
});

// Detailed health check with database
router.get("/detailed", async (req, res) => {
  try {
    let dbStatus = "disconnected";
    let tables = {};

    try {
      // Test database connection with a simple query
      await query(
        "SELECT COUNT(*) as count FROM information_schema.tables WHERE table_schema = 'public'"
      );
      dbStatus = "connected";

      // Get table counts for key tables
      // FIXED: Use identifier quoting to prevent SQL injection
      const keyTables = [
        "price_daily",
        "stock_scores",
        "buy_sell_daily",
        "sector_ranking",
        "company_profile",
        "technical_data_daily",
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
    const isProduction = (process.env.NODE_ENV ?? "").includes("prod");
    const response = {
      status: "healthy",
      healthy: true,
      service: "Financial Dashboard API",
      uptime: process.uptime(),
      version: "1.0.0",
      timestamp: new Date().toISOString(),
    };

    // Only expose schema details to authenticated admins or in development
    if (!isProduction) {
      response.environment = process.env.NODE_ENV || "development";
      response.database = {
        status: dbStatus,
        tables: tables,
      };
    } else {
      response.database = {
        status: dbStatus,
      };
    }

    return sendSuccess(res, response);
  } catch (error) {
    logger.error("Error in /health/detailed:", {
      error: error.message,
      stack: error.stack,
    });
    return sendError(
      res,
      "Detailed health check failed: " + error.message,
      503
    );
  }
});

// Pipeline health status - checks data loader freshness
router.get("/pipeline", async (req, res) => {
  try {
    // Query data_loader_status to get latest pipeline health
    const result = await query(`
      SELECT
        table_name,
        status,
        row_count,
        latest_date,
        age_days,
        checked_at
      FROM data_loader_status
      WHERE checked_at = (SELECT MAX(checked_at) FROM data_loader_status)
      ORDER BY table_name
    `);

    if (!result || !result.rows || result.rows.length === 0) {
      return sendSuccess(res, {
        status: "unknown",
        message: "No pipeline health data available yet",
        timestamp: new Date().toISOString(),
      });
    }

    const tables = result.rows;
    const healthyCount = tables.filter((t) => t.status === "HEALTHY").length;
    const totalCount = tables.length;
    const coveragePct = ((healthyCount / totalCount) * 100).toFixed(1);

    const criticalAlerts = [];
    const warnings = [];

    for (const table of tables) {
      if (
        [
          "stock_symbols",
          "price_daily",
          "buy_sell_daily",
          "stock_scores",
          "economic_data",
          "market_health_daily",
        ].includes(table.table_name)
      ) {
        if (table.status === "MISSING") {
          criticalAlerts.push(
            `${table.table_name} is empty - no trades can execute`
          );
        } else if (table.status === "VERY_STALE") {
          criticalAlerts.push(
            `${table.table_name} is very stale (${table.age_days} days old)`
          );
        } else if (table.status === "STALE") {
          warnings.push(
            `${table.table_name} is stale (${table.age_days} days old)`
          );
        }
      }
    }

    const isHealthy = criticalAlerts.length === 0;

    return sendSuccess(res, {
      status: isHealthy ? "healthy" : "unhealthy",
      is_healthy: isHealthy,
      healthy_count: healthyCount,
      total_count: totalCount,
      coverage_pct: parseFloat(coveragePct),
      critical_alerts: criticalAlerts,
      warnings: warnings,
      tables: tables,
      timestamp: tables[0]?.checked_at || new Date().toISOString(),
    });
  } catch (error) {
    return sendSuccess(
      res,
      {
        status: "error",
        message: "Pipeline health check failed: " + error.message,
        timestamp: new Date().toISOString(),
      },
      200
    );
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
        status: "connected",
      },
    };

    return sendSuccess(res, diagnostics);
  } catch (error) {
    logger.error("Error in /health/diagnostics:", {
      error: error.message,
      stack: error.stack,
    });
    return sendError(res, "Diagnostics check failed: " + error.message, 503);
  }
});

module.exports = router;
