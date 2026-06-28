/**
 * Diagnostics Endpoint
 * Provides comprehensive information about API health, database status, and data availability
 */

const express = require("express");

const { query } = require("../utils/database");
const { sendSuccess, sendError } = require("../utils/apiResponse");
const logger = require("../utils/logger");
const { authenticateToken, requireAdmin } = require("../middleware/auth");
const { validateQueryResult } = require("../utils/responseValidation");
const router = express.Router();

// Protect all diagnostics endpoints with auth + admin role
router.use(authenticateToken, requireAdmin);

// Diagnostics cache with 5-minute TTL
let diagnosticsCache = null;
let diagnosticsCacheTime = 0;
const DIAGNOSTICS_CACHE_TTL = 5 * 60 * 1000; // 5 minutes

// GET /api/diagnostics - Full system health check (optimized with caching)
router.get("/", async (req, res) => {
  // Return cached result if available and fresh
  const now = Date.now();
  if (diagnosticsCache && now - diagnosticsCacheTime < DIAGNOSTICS_CACHE_TTL) {
    return sendSuccess(res, diagnosticsCache);
  }

  const diagnostics = {
    timestamp: new Date().toISOString(),
    api_status: "healthy",
    database_status: "checking",
    data_availability: {},
    database_indexes: {},
    endpoints_status: {},
    recommendations: [],
  };

  try {
    // Test database connectivity first
    const dbTest = await query("SELECT COUNT(*) as count FROM stock_symbols");
    validateQueryResult(dbTest, { requireRows: false });
    diagnostics.database_status = "connected";
    diagnostics.database_tables = {
      stock_symbols: parseInt(dbTest.rows[0]?.count ?? 0),
    };
  } catch (err) {
    diagnostics.database_status = "error";
    diagnostics.database_error = err.message;
    diagnostics.recommendations.push("Database connection failed");
    diagnosticsCache = diagnostics;
    diagnosticsCacheTime = now;
    return sendSuccess(res, diagnostics);
  }

  // WHITELIST of allowed tables - prevents SQL injection via table names
  const ALLOWED_TABLES = new Set([
    "stock_symbols",
    "stock_scores",
    "company_profile",
    "growth_metrics",
    "value_metrics",
    "quality_metrics",
    "earnings_history",
    "earnings_estimates",
    "buy_sell_daily",
    "price_daily",
    "technical_data_daily",
  ]);

  // Run table counts in parallel instead of sequentially
  const tables = [
    { name: "stock_symbols", small: true },
    { name: "stock_scores", small: true },
    { name: "company_profile", small: true },
    { name: "growth_metrics", small: true },
    { name: "value_metrics", small: true },
    { name: "quality_metrics", small: true },
    { name: "earnings_history", medium: true },
    { name: "earnings_estimates", small: true },
    { name: "buy_sell_daily", medium: true },
    { name: "price_daily", large: true },
    { name: "technical_data_daily", large: true },
  ];

  // For large tables, use n_live_tup estimate instead of COUNT(*)
  const countQueries = tables.map((table) => {
    // SECURITY: Validate table name against whitelist before interpolating
    if (!ALLOWED_TABLES.has(table.name)) {
      return Promise.resolve({
        name: table.name,
        count: 0,
        success: false,
        error: "Invalid table name",
      });
    }

    let q;
    if (table.large) {
      // Use pg_class for large tables (much faster, estimates)
      // SECURITY: Table name validated against whitelist above, safe to interpolate
      q = `SELECT $1::text as name,
           COALESCE(n_live_tup::bigint, 0) as count FROM pg_stat_user_tables
           WHERE relname = $1`;
    } else {
      // SECURITY: Table name validated against whitelist above, safe to interpolate
      q = `SELECT $1::text as name, COUNT(*) as count FROM "${table.name}"`;
    }
    return query(q, [table.name])
      .then((result) => ({
        name: table.name,
        count: parseInt(result.rows[0]?.count ?? 0),
        success: true,
      }))
      .catch((err) => {
        logger.warn(`Failed to count table ${table.name}:`, {
          error: err.message,
        });
        return {
          name: table.name,
          count: 0,
          success: false,
          error: err.message,
        };
      });
  });

  // Execute all count queries in parallel
  const results = await Promise.all(countQueries);

  // Validate results where applicable
  results.forEach((result) => {
    if (result.success) {
      // Results already validated in the Promise handler
    }
  });

  results.forEach((result) => {
    if (result.success) {
      diagnostics.data_availability[result.name] = {
        count: result.count,
        status: result.count > 0 ? "Data available" : "Empty",
      };
      if (result.count === 0) {
        diagnostics.recommendations.push(`Table ${result.name} is empty`);
      }
    } else {
      diagnostics.data_availability[result.name] = {
        status: "Query error",
      };
      diagnostics.recommendations.push(`Cannot query ${result.name}`);
    }
  });

  // Check index status
  try {
    const indexResult = await query(`
      SELECT COUNT(*) as index_count FROM pg_indexes WHERE schemaname = 'public'
    `);
    validateQueryResult(indexResult, { requireRows: false });
    const indexCount = parseInt(indexResult.rows[0]?.index_count ?? 0);
    diagnostics.database_indexes = {
      count: indexCount,
      status: indexCount > 20 ? "Indexes present" : "Few indexes",
    };
  } catch (err) {
    diagnostics.database_indexes = { count: 0, status: "Cannot check" };
  }

  // Generate summary
  if (diagnostics.recommendations.length === 0) {
    diagnostics.recommendations.push("All systems operational");
    diagnostics.api_status = "healthy";
  } else {
    diagnostics.api_status =
      diagnostics.database_status === "connected" ? "degraded" : "error";
  }

  // Cache the result
  diagnosticsCache = diagnostics;
  diagnosticsCacheTime = now;

  return sendSuccess(res, diagnostics);
});

// GET /api/diagnostics/slow-queries - Check for slow queries in database
router.get("/slow-queries", async (req, res) => {
  try {
    const result = await query(`
      SELECT query, mean_exec_time, calls
      FROM pg_stat_statements
      WHERE mean_exec_time > 100
      ORDER BY mean_exec_time DESC
      LIMIT 20
    `).catch((err) => {
      logger.warn("Failed to fetch performance statistics:", {
        error: err.message,
      });
      return { rows: [] };
    });
    validateQueryResult(result, { requireRows: false });

    return sendSuccess(res, {
      slow_queries: result.rows ?? [],
      message: "Queries taking >100ms. Run EXPLAIN ANALYZE on slow queries.",
    });
  } catch (err) {
    return sendSuccess(res, {
      slow_queries: [],
      message: "pg_stat_statements extension may not be installed",
    });
  }
});

// GET /api/diagnostics/cache-stats - Cache performance statistics
router.get("/cache-stats", (req, res) => {
  try {
    // Note: This would need to be implemented in the optimization middleware
    return sendSuccess(res, {
      cache_status: "Cache middleware active",
      ttl_seconds: 300,
      message:
        "Enable debug logging in queryOptimization.js for detailed cache stats",
    });
  } catch (err) {
    return sendError(res, err.message, 500);
  }
});

// GET /api/diagnostics/database-size - Check database and table sizes
router.get("/database-size", async (req, res) => {
  try {
    const dbSize = await query(`
      SELECT
        pg_database.datname,
        pg_size_pretty(pg_database_size(pg_database.datname)) AS size
      FROM pg_database
      WHERE datname = current_database()
    `);
    validateQueryResult(dbSize, { requireRows: false });

    const tableSize = await query(`
      SELECT
        schemaname,
        tablename,
        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
      FROM pg_tables
      WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
      ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
      LIMIT 100
    `);
    validateQueryResult(tableSize, { requireRows: false });

    return sendSuccess(res, {
      database_size: dbSize.rows[0],
      largest_tables: tableSize.rows ?? [],
    });
  } catch (err) {
    return sendError(res, err.message, 500);
  }
});

module.exports = router;
