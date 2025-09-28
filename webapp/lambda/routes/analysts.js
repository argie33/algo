const express = require("express");
const { query } = require("../utils/database");

const router = express.Router();

// Root endpoint - provides overview of REAL data only
router.get("/", async (req, res) => {
  res.json({
    message: "Analysts API - Real YFinance Data Only",
    timestamp: new Date().toISOString(),
    status: "operational",
    endpoints: [
      "/upgrades - Get analyst upgrades/downgrades from YFinance",
      "/revenue-estimates - Get revenue estimates with analyst counts",
      "/:symbol - Get all analyst data for a specific symbol"
    ],
    data_sources: {
      upgrades: "analyst_upgrade_downgrade table (from loadanalystupgradedowngrade.py)",
      revenue_estimates: "revenue_estimates table (from loadrevenueestimate.py)"
    }
  });
});

// GET /upgrades - Real upgrade/downgrade data from YFinance
router.get("/upgrades", async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 50, 200);
    const offset = (page - 1) * limit;

    // Query your actual analyst_upgrade_downgrade table from YFinance
    const upgradesQuery = `
      SELECT
        id,
        symbol,
        firm,
        action,
        from_grade,
        to_grade,
        date,
        details,
        fetched_at
      FROM analyst_upgrade_downgrade
      ORDER BY date DESC, fetched_at DESC
      LIMIT $1 OFFSET $2
    `;

    const result = await query(upgradesQuery, [limit, offset]);

    if (!result) {
      return res.status(500).json({
        success: false,
        error: "Database query failed"
      });
    }

    // Count total records
    const countResult = await query("SELECT COUNT(*) as total FROM analyst_upgrade_downgrade");
    const total = parseInt(countResult.rows[0]?.total) || 0;

    res.json({
      success: true,
      data: result.rows,
      pagination: {
        page,
        limit,
        total,
        totalPages: Math.ceil(total / limit),
        hasMore: page < Math.ceil(total / limit)
      },
      source: "YFinance via loadanalystupgradedowngrade.py",
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Analyst upgrades error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch analyst upgrades",
      details: error.message
    });
  }
});

// GET /revenue-estimates - Revenue estimates with analyst data from YFinance
router.get("/revenue-estimates", async (req, res) => {
  try {
    const estimatesQuery = `
      SELECT
        symbol,
        period,
        avg_estimate,
        low_estimate,
        high_estimate,
        number_of_analysts,
        year_ago_revenue,
        growth,
        fetched_at
      FROM revenue_estimates
      ORDER BY symbol, period
    `;

    const result = await query(estimatesQuery);

    if (!result) {
      return res.status(500).json({
        success: false,
        error: "Database query failed"
      });
    }

    res.json({
      success: true,
      data: result.rows,
      count: result.rows.length,
      source: "YFinance via loadrevenueestimate.py",
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Revenue estimates error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch revenue estimates",
      details: error.message
    });
  }
});

// GET /:symbol - Get all real analyst data for a specific symbol
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const symbolUpper = symbol.toUpperCase();

    // Get all REAL analyst data for this symbol from your actual YFinance tables
    const [upgradesResult, revenueEstimatesResult] = await Promise.all([
      // Upgrades/downgrades from YFinance
      query(`
        SELECT
          id, symbol, firm, action, from_grade, to_grade,
          date, details, fetched_at
        FROM analyst_upgrade_downgrade
        WHERE UPPER(symbol) = $1
        ORDER BY date DESC, fetched_at DESC
      `, [symbolUpper]),

      // Revenue estimates with analyst counts from YFinance
      query(`
        SELECT
          symbol, period, avg_estimate, low_estimate, high_estimate,
          number_of_analysts, year_ago_revenue, growth, fetched_at
        FROM revenue_estimates
        WHERE UPPER(symbol) = $1
        ORDER BY period DESC
      `, [symbolUpper])
    ]);

    res.json({
      success: true,
      symbol: symbolUpper,
      data: {
        upgrades_downgrades: upgradesResult?.rows || [],
        revenue_estimates: revenueEstimatesResult?.rows || []
      },
      counts: {
        upgrades_downgrades: upgradesResult?.rows?.length || 0,
        revenue_estimates: revenueEstimatesResult?.rows?.length || 0,
        total_analysts_covering: revenueEstimatesResult?.rows?.reduce((sum, row) =>
          sum + (row.number_of_analysts || 0), 0) || 0
      },
      sources: {
        upgrades_downgrades: "YFinance via loadanalystupgradedowngrade.py",
        revenue_estimates: "YFinance via loadrevenueestimate.py"
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error(`Analyst data error for symbol ${req.params.symbol}:`, error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch analyst data for symbol",
      symbol: req.params.symbol?.toUpperCase() || null,
      details: error.message
    });
  }
});

module.exports = router;