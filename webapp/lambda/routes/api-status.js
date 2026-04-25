const express = require("express");

const { query } = require("../utils/database");
const { sendSuccess, sendError } = require("../utils/apiResponse");

const router = express.Router();

router.get("/", async (req, res) => {
  try {
    const status = {
      timestamp: new Date().toISOString(),
      database: "unknown",
      tables: {},
      apis: {}
    };

    // Test database connection
    try {
      const connTest = await query("SELECT 1 as ok", []);
      status.database = connTest?.rows?.length > 0 ? "connected" : "failed";
    } catch (e) {
      status.database = "failed: " + e.message;
      return sendError(res, "Database connection failed", 503);
    }

    // Check critical tables
    const tableStatus = await query(`
      SELECT
        tablename,
        CAST(reltuples AS INT) as estimated_rows
      FROM pg_tables
      JOIN pg_class ON relname = tablename
      WHERE schemaname = 'public' AND tablename = ANY($1)
      ORDER BY tablename
    `, [[
      'company_profile', 'key_metrics', 'earnings_estimates', 'earnings_history', 'price_daily',
      'stock_scores', 'sector_ranking', 'industry_ranking', 'institutional_positioning',
      'insider_transactions', 'technical_data_daily'
    ]]);

    if (tableStatus?.rows) {
      tableStatus.rows.forEach(row => {
        status.tables[row.tablename] = row.estimated_rows;
      });
    }

    // Check API readiness based on table data
    const apiStatusMap = {
      "Earnings": {
        required: ["earnings_estimates", "earnings_history"],
        ready: false
      },
      "Stocks": {
        required: ["company_profile", "key_metrics", "price_daily"],
        ready: false
      },
      "Technical Data": {
        required: ["technical_data_daily", "price_daily"],
        ready: false
      },
      "Sectors": {
        required: ["sector_ranking", "company_profile"],
        ready: false
      },
      "Industries": {
        required: ["industry_ranking", "company_profile"],
        ready: false
      },
      "Stock Scores": {
        required: ["stock_scores"],
        ready: false
      },
      "Institutional": {
        required: ["institutional_positioning"],
        ready: false
      },
      "Insider": {
        required: ["insider_transactions"],
        ready: false
      }
    };

    // Check each API's requirements
    for (const [apiName, apiData] of Object.entries(apiStatusMap)) {
      apiData.ready = apiData.required.every(tableName => {
        const rows = status.tables[tableName] || 0;
        return rows > 0;
      });

      apiData.details = apiData.required.map(tableName => ({
        table: tableName,
        rows: status.tables[tableName] || 0,
        ready: (status.tables[tableName] || 0) > 0
      }));

      status.apis[apiName] = apiData.ready ? "✅ READY" : "❌ MISSING DATA";
    }

    // Calculate overall health
    const readyAPIs = Object.values(apiStatusMap).filter(a => a.ready).length;
    const totalAPIs = Object.keys(apiStatusMap).length;
    status.health = {
      ready_apis: readyAPIs,
      total_apis: totalAPIs,
      percentage: Math.round((readyAPIs / totalAPIs) * 100),
      status: readyAPIs === totalAPIs ? "FULLY_OPERATIONAL" :
              readyAPIs > totalAPIs / 2 ? "PARTIALLY_OPERATIONAL" :
              "DEGRADED"
    };

    return sendSuccess(res, status);
  } catch (err) {
    console.error("API status check error:", err);
    return sendError(res, "Status check failed: " + err.message, 500);
  }
});

module.exports = router;
