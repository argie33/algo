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
      "/eps-revisions - Get EPS estimates with analyst counts",
      "/:symbol - Get all analyst data for a specific symbol",
      "/:symbol/eps-revisions - Get EPS estimates for a specific symbol",
      "/:symbol/eps-trend - Get EPS trend analysis for a specific symbol"
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

// GET /downgrades - Legacy endpoint for downgrades specifically (redirect to upgrades with filter)
router.get("/downgrades", async (req, res) => {
  try {
    console.log("📉 Analyst downgrades endpoint called - real database data only");

    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 50, 200);
    const offset = (page - 1) * limit;

    // Get real downgrade data from database
    const downgradesQuery = `
      SELECT
        id, symbol, firm, action, from_grade, to_grade, date, details, analyst_name, fetched_at
      FROM analyst_upgrade_downgrade
      WHERE action ILIKE '%downgrade%' OR action ILIKE '%sell%' OR action ILIKE '%reduce%'
      ORDER BY date DESC, fetched_at DESC
      LIMIT $1 OFFSET $2
    `;

    const result = await query(downgradesQuery, [limit, offset]);

    if (!result) {
      return res.status(500).json({
        success: false,
        error: "Database query failed for downgrades"
      });
    }

    // Count total downgrade records
    const countQuery = `
      SELECT COUNT(*) as total
      FROM analyst_upgrade_downgrade
      WHERE action ILIKE '%downgrade%' OR action ILIKE '%sell%' OR action ILIKE '%reduce%'
    `;
    const countResult = await query(countQuery);
    const total = parseInt(countResult?.rows[0]?.total) || 0;

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
      filter: "downgrade actions only",
      source: "YFinance via loadanalystupgradedowngrade.py",
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("Analyst downgrades error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch analyst downgrades",
      details: error.message
    });
  }
});

// GET /eps-revisions - EPS estimates with analyst data from YFinance
router.get("/eps-revisions", async (req, res) => {
  try {
    const estimatesQuery = `
      SELECT
        symbol,
        period,
        avg_estimate,
        low_estimate,
        high_estimate,
        number_of_analysts,
        year_ago_eps,
        growth,
        fetched_at
      FROM earnings_estimates
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
      source: "YFinance via loadearningsestimate.py",
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error("EPS estimates error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch EPS estimates",
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

// GET /:symbol/eps-revisions - Get EPS estimates for a specific symbol
router.get("/:symbol/eps-revisions", async (req, res) => {
  try {
    const { symbol } = req.params;
    const symbolUpper = symbol.toUpperCase();

    const epsQuery = `
      SELECT
        symbol,
        period,
        avg_estimate,
        low_estimate,
        high_estimate,
        number_of_analysts,
        year_ago_eps,
        growth,
        fetched_at
      FROM earnings_estimates
      WHERE UPPER(symbol) = $1
      ORDER BY period DESC
    `;

    const result = await query(epsQuery, [symbolUpper]);

    if (!result) {
      return res.status(500).json({
        success: false,
        error: "Database query failed"
      });
    }

    res.json({
      success: true,
      symbol: symbolUpper,
      data: result.rows,
      count: result.rows.length,
      source: "YFinance via loadearningsestimate.py",
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error(`EPS estimates error for symbol ${req.params.symbol}:`, error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch EPS estimates for symbol",
      symbol: req.params.symbol?.toUpperCase() || null,
      details: error.message
    });
  }
});

// GET /:symbol/eps-trend - Get EPS trend analysis for a specific symbol
router.get("/:symbol/eps-trend", async (req, res) => {
  try {
    const { symbol } = req.params;
    const symbolUpper = symbol.toUpperCase();

    // Get historical EPS estimates to show trend over time
    const epsTrendQuery = `
      SELECT
        symbol,
        period,
        avg_estimate,
        low_estimate,
        high_estimate,
        number_of_analysts,
        year_ago_eps,
        growth,
        fetched_at
      FROM earnings_estimates
      WHERE UPPER(symbol) = $1
      ORDER BY period ASC
    `;

    const result = await query(epsTrendQuery, [symbolUpper]);

    if (!result) {
      return res.status(500).json({
        success: false,
        error: "Database query failed"
      });
    }

    const data = result.rows;

    // Calculate trend metrics
    let trend = "neutral";
    let trendScore = 0;
    let avgGrowth = 0;

    if (data.length > 1) {
      // Calculate average growth rate
      const growthRates = data.filter(row => row.growth !== null).map(row => parseFloat(row.growth) || 0);
      if (growthRates.length > 0) {
        avgGrowth = growthRates.reduce((sum, rate) => sum + rate, 0) / growthRates.length;

        // Determine trend based on average growth
        if (avgGrowth > 10) {
          trend = "strongly_positive";
          trendScore = Math.min(100, 50 + avgGrowth * 2);
        } else if (avgGrowth > 5) {
          trend = "positive";
          trendScore = 50 + avgGrowth * 5;
        } else if (avgGrowth > 0) {
          trend = "slightly_positive";
          trendScore = 50 + avgGrowth * 3;
        } else if (avgGrowth > -5) {
          trend = "slightly_negative";
          trendScore = 50 + avgGrowth * 3;
        } else if (avgGrowth > -10) {
          trend = "negative";
          trendScore = Math.max(0, 50 + avgGrowth * 5);
        } else {
          trend = "strongly_negative";
          trendScore = Math.max(0, 50 + avgGrowth * 2);
        }
      }
    }

    // Calculate analyst consensus strength
    const totalAnalysts = data.reduce((sum, row) => sum + (row.number_of_analysts || 0), 0);
    const avgAnalysts = totalAnalysts > 0 ? totalAnalysts / data.length : 0;

    res.json({
      success: true,
      symbol: symbolUpper,
      data: data,
      trend_analysis: {
        trend,
        trend_score: Math.round(trendScore),
        avg_growth_rate: Math.round(avgGrowth * 100) / 100,
        data_points: data.length,
        avg_analysts_per_period: Math.round(avgAnalysts),
        total_analyst_estimates: totalAnalysts
      },
      source: "YFinance via loadearningsestimate.py",
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error(`EPS trend error for symbol ${req.params.symbol}:`, error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch EPS trend for symbol",
      symbol: req.params.symbol?.toUpperCase() || null,
      details: error.message,
      hint: "Check if earnings_estimates table exists and has data for this symbol",
      debug_info: {
        symbol_provided: req.params.symbol,
        symbol_uppercase: symbolUpper,
        error_code: error.code,
        error_type: error.name
      }
    });
  }
});

// GET /:symbol - Get all real analyst data for a specific symbol
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    const symbolUpper = symbol.toUpperCase();

    // Get all REAL analyst data for this symbol from your actual YFinance tables
    const [upgradesResult, revenueEstimatesResult, epsEstimatesResult] = await Promise.all([
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
      `, [symbolUpper]),

      // EPS estimates with analyst counts from YFinance
      query(`
        SELECT
          symbol, period, avg_estimate, low_estimate, high_estimate,
          number_of_analysts, year_ago_eps, growth, fetched_at
        FROM earnings_estimates
        WHERE UPPER(symbol) = $1
        ORDER BY period DESC
      `, [symbolUpper])
    ]);

    res.json({
      success: true,
      symbol: symbolUpper,
      data: {
        upgrades_downgrades: upgradesResult?.rows || [],
        revenue_estimates: revenueEstimatesResult?.rows || [],
        eps_estimates: epsEstimatesResult?.rows || []
      },
      counts: {
        upgrades_downgrades: upgradesResult?.rows?.length || 0,
        revenue_estimates: revenueEstimatesResult?.rows?.length || 0,
        eps_estimates: epsEstimatesResult?.rows?.length || 0,
        total_analysts_covering: revenueEstimatesResult?.rows?.reduce((sum, row) =>
          sum + (row.number_of_analysts || 0), 0) || 0
      },
      sources: {
        upgrades_downgrades: "YFinance via loadanalystupgradedowngrade.py",
        revenue_estimates: "YFinance via loadrevenueestimate.py",
        eps_estimates: "YFinance via loadearningsestimate.py"
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