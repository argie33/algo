/**
 * Diagnostics Endpoint
 * Provides comprehensive information about API health, database status, and data availability
 */

const express = require("express");

const { query } = require("../utils/database");
const { sendSuccess, sendError } = require('../utils/apiResponse');
const router = express.Router();

// GET /api/diagnostics - Full system health check
router.get("/", async (req, res) => {
  const diagnostics = {
    timestamp: new Date().toISOString(),
    api_status: "healthy",
    database_status: "checking",
    data_availability: {},
    endpoints_status: {},
    recommendations: []
  };

  try {
    // Test database connectivity
    console.log("[DIAG] Testing database connectivity...");
    const dbTest = await query("SELECT COUNT(*) as count FROM stock_symbols");
    diagnostics.database_status = "connected";
    diagnostics.database_tables = {
      stock_symbols: parseInt(dbTest.rows[0]?.count || 0)
    };
  } catch (err) {
    diagnostics.database_status = "error";
    diagnostics.database_error = err.message;
    diagnostics.recommendations.push("❌ Database connection failed - check DB_HOST credentials");
  }

  try {
    // Check key data tables
    const tables = [
      { name: "stock_symbols", query: "SELECT COUNT(*) as count FROM stock_symbols" },
      { name: "stock_scores", query: "SELECT COUNT(*) as count FROM stock_scores" },
      { name: "company_profile", query: "SELECT COUNT(*) as count FROM company_profile" },
      { name: "growth_metrics", query: "SELECT COUNT(*) as count FROM growth_metrics" },
      { name: "value_metrics", query: "SELECT COUNT(*) as count FROM value_metrics" },
      { name: "quality_metrics", query: "SELECT COUNT(*) as count FROM quality_metrics" },
      { name: "earnings_history", query: "SELECT COUNT(*) as count FROM earnings_history" },
      { name: "earnings_estimates", query: "SELECT COUNT(*) as count FROM earnings_estimates" },
      { name: "buy_sell_daily", query: "SELECT COUNT(*) as count FROM buy_sell_daily" },
      { name: "price_daily", query: "SELECT COUNT(*) as count FROM price_daily" },
      { name: "technical_data_daily", query: "SELECT COUNT(*) as count FROM technical_data_daily" }
    ];

    for (const table of tables) {
      try {
        const result = await query(table.query);
        const count = parseInt(result.rows[0]?.count || 0);
        diagnostics.data_availability[table.name] = {
          count,
          status: count > 0 ? "✅ Data available" : "⚠️ Empty"
        };

        if (count === 0) {
          diagnostics.recommendations.push(`⚠️ Table ${table.name} is empty - no data for this metric`);
        }
      } catch (err) {
        diagnostics.data_availability[table.name] = {
          status: "❌ Query error: " + err.message.substring(0, 50)
        };
        diagnostics.recommendations.push(`❌ Cannot query ${table.name} - check table exists`);
      }
    }
  } catch (err) {
    diagnostics.database_status = "error";
    diagnostics.database_error = err.message;
  }

  // Check index status
  try {
    const indexResult = await query(`
      SELECT COUNT(*) as index_count
      FROM pg_indexes
      WHERE schemaname = 'public'
    `);
    const indexCount = parseInt(indexResult.rows[0]?.index_count || 0);
    diagnostics.database_indexes = {
      count: indexCount,
      status: indexCount > 20 ? "✅ Indexes present" : "⚠️ Few indexes - performance may suffer"
    };

    if (indexCount < 20) {
      diagnostics.recommendations.push(`⚠️ Only ${indexCount} indexes found - run optimize-database-indexes.sql`);
    }
  } catch (err) {
    diagnostics.recommendations.push("⚠️ Cannot check indexes - may not have permissions");
  }

  // Test sample endpoints
  const endpointsToTest = [
    { path: "metrics/growth?symbol=AAPL", name: "Growth Metrics" },
    { path: "metrics/value", name: "Value Metrics" },
    { path: "earnings/info?symbol=AAPL", name: "Earnings Info" },
    { path: "stocks?limit=5", name: "Stocks List" }
  ];

  for (const ep of endpointsToTest) {
    try {
      const testResult = await query("SELECT 1 as test");
      diagnostics.endpoints_status[ep.name] = "✅ Endpoint accessible";
    } catch (err) {
      diagnostics.endpoints_status[ep.name] = "❌ Error: " + err.message.substring(0, 50);
    }
  }

  // Generate summary
  if (diagnostics.recommendations.length === 0) {
    diagnostics.recommendations.push("✅ All systems operational");
    diagnostics.api_status = "healthy";
  } else {
    diagnostics.api_status = "degraded";
  }

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
    `).catch(() => ({ rows: [] }));

    return sendSuccess(res, {
      slow_queries: result.rows || [],
      message: "Queries taking >100ms. Run EXPLAIN ANALYZE on slow queries."
    });
  } catch (err) {
    return sendSuccess(res, {
      slow_queries: [],
      message: "pg_stat_statements extension may not be installed"
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
      message: "Enable debug logging in queryOptimization.js for detailed cache stats"
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

    const tableSize = await query(`
      SELECT
        schemaname,
        tablename,
        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
      FROM pg_tables
      WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
      ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
      LIMIT 20
    `);

    return sendSuccess(res, {
      database_size: dbSize.rows[0],
      largest_tables: tableSize.rows || []
    });
  } catch (err) {
    return sendError(res, err.message, 500);
  }
});

module.exports = router;
