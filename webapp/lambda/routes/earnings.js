const express = require("express");

const { query } = require("../utils/database");
const responseFormatter = require("../middleware/responseFormatter");

const router = express.Router();

// Helper function to check if a table exists
async function tableExists(tableName) {
  try {
    const tableCheckQuery = `
      SELECT EXISTS (
        SELECT FROM information_schema.tables
        WHERE table_name = $1
      );
    `;
    const result = await query(tableCheckQuery, [tableName]);
    if (!result || !result.rows || result.rows.length === 0) {
      console.warn('Query returned invalid result:', result);
      return null;
    }
    return result.rows[0].exists;
  } catch (error) {
    console.warn(`Error checking table existence for ${tableName}:`, error);
    return false;
  }
}

// Apply response formatter middleware to all routes
router.use(responseFormatter);

// Earnings data - use real earnings tables from loaders
router.get("/", async (req, res) => {
  try {
    if (process.env.NODE_ENV !== 'test') {
      console.log(`📈 Earnings data requested`);
    }

    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 50, 200);
    const offset = (page - 1) * limit;

    // Check if earnings_estimates table exists
    if (!(await tableExists("earnings_estimates"))) {
      return res.json({
        success: true,
        earnings: [],
        data: [],
        pagination: {
          page,
          limit,
          total: 0,
          hasMore: false,
        },
        message: "Earnings estimates data not yet loaded",
        timestamp: new Date().toISOString(),
      });
    }

    // Use earnings_estimates table from Python loader
    let result;
    try {
      const earningsQuery = `
        SELECT
          symbol,
          period as report_date,
          avg_estimate as eps_estimate,
          low_estimate,
          high_estimate,
          year_ago_eps,
          number_of_analysts,
          growth,
          fetched_at as last_updated
        FROM earnings_estimates
        ORDER BY period DESC, symbol
        LIMIT $1 OFFSET $2
      `;

      result = await query(earningsQuery, [limit, offset]);
    } catch (error) {
      console.error("Earnings query failed:", error.message);
      return res.status(500).json({
        success: false,
        error: "Earnings query failed",
        details: error.message,
        timestamp: new Date().toISOString(),
      });
    }

    res.json({
      success: true,
      earnings: result.rows,
      data: result.rows,
      pagination: {
        page,
        limit,
        total: result.rows.length,
        hasMore: result.rows.length === limit,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Earnings delegation error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch earnings data",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Earnings calendar endpoint
router.get("/calendar", async (req, res) => {
  try {
    const {
      startDate,
      endDate,
      period = "upcoming",
      limit = 100
    } = req.query;

    if (process.env.NODE_ENV !== 'test') {
      console.log(`📅 Earnings calendar requested for period: ${period}`);
    }

    let dateFilter = "";
    let queryParams = [parseInt(limit)];

    if (startDate && endDate) {
      dateFilter = "WHERE eh.quarter BETWEEN $2 AND $3";
      queryParams = [parseInt(limit), startDate, endDate];
    } else if (period === "upcoming") {
      dateFilter = "WHERE eh.quarter >= CURRENT_DATE";
    } else if (period === "past") {
      dateFilter = "WHERE eh.quarter < CURRENT_DATE";
    }

    try {
      // Use earnings_history table and join earnings_metrics for quality scores
      const calendarQuery = `
        SELECT
          eh.symbol,
          eh.quarter as date,
          EXTRACT(QUARTER FROM eh.quarter) as quarter,
          EXTRACT(YEAR FROM eh.quarter) as year,
          eh.eps_estimate as estimated_eps,
          eh.eps_actual as actual_eps,
          NULL as estimated_revenue,
          NULL as actual_revenue,
          NULL as company_name,
          NULL as sector,
          NULL as market_cap,
          em.earnings_quality_score,
          (eh.eps_actual IS NOT NULL) as is_reported
        FROM earnings_history eh
        LEFT JOIN earnings_metrics em ON eh.symbol = em.symbol AND eh.quarter = em.report_date
        ${dateFilter.replace('er.', 'eh.')}
        ORDER BY
          CASE
            WHEN em.earnings_quality_score IS NOT NULL THEN em.earnings_quality_score
            ELSE -1
          END DESC,
          eh.quarter ASC,
          eh.symbol
        LIMIT $1
      `;

      const result = await query(calendarQuery, queryParams);

      res.json({
        success: true,
        data: {
          calendar: result.rows.map(row => ({
            symbol: row.symbol,
            company_name: row.company_name || row.symbol,
            date: row.date,
            quarter: row.quarter,
            year: row.year,
            estimated_eps: parseFloat(row.estimated_eps || 0),
            actual_eps: row.actual_eps ? parseFloat(row.actual_eps) : null,
            estimated_revenue: parseFloat(row.estimated_revenue || 0),
            actual_revenue: row.actual_revenue ? parseFloat(row.actual_revenue) : null,
            sector: row.sector || "Unknown",
            market_cap: parseFloat(row.market_cap || 0),
            earnings_quality_score: row.earnings_quality_score ? parseFloat(row.earnings_quality_score) : null,
            is_reported: !!row.is_reported
          })),
          period,
          total: result.rows.length,
          filters: {
            startDate: startDate || null,
            endDate: endDate || null,
            period
          }
        },
        timestamp: new Date().toISOString(),
      });

    } catch (error) {
      console.error("Earnings calendar query failed:", error.message);
      return res.status(500).json({
        success: false,
        error: "Earnings calendar query failed",
        details: error.message,
        timestamp: new Date().toISOString(),
      });
    }
  } catch (error) {
    console.error("Error in earnings calendar endpoint:", error);
    return res.status(500).json({
      success: false,
      error: "Internal server error",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Fallback route removed - using main /calendar route with built-in fallback logic

// Earnings surprises endpoint
router.get("/surprises", async (req, res) => {
  try {
    const {
      symbol,
      period = "recent",
      limit = 50,
      minSurprise = 0
    } = req.query;

    if (process.env.NODE_ENV !== 'test') {
      console.log(`📊 Earnings surprises requested - Symbol: ${symbol || 'all'}, Period: ${period}`);
    }

    let symbolFilter = "";
    let surpriseFilter = "";
    let queryParams = [parseInt(limit)];

    if (symbol) {
      symbolFilter = "AND eh.symbol = $2";
      queryParams = [parseInt(limit), symbol.toUpperCase()];
    }

    if (minSurprise && parseFloat(minSurprise) > 0) {
      const surpriseIndex = queryParams.length + 1;
      surpriseFilter = `AND ABS(eh.surprise_percent) >= $${surpriseIndex}`;
      queryParams.push(parseFloat(minSurprise));
    }

    try {
      // Use earnings_history table (from loadearningshistory.py) with calculated surprises
      const surprisesQuery = `
        SELECT
          eh.symbol,
          eh.quarter as date,
          EXTRACT(QUARTER FROM eh.quarter) as quarter,
          EXTRACT(YEAR FROM eh.quarter) as year,
          eh.eps_estimate as estimated_eps,
          eh.eps_actual as actual_eps,
          NULL as estimated_revenue,
          NULL as actual_revenue,
          NULL as company_name,
          NULL as sector,
          NULL as market_cap,
          eh.surprise_percent as eps_surprise_percent,
          NULL as revenue_surprise_percent
        FROM earnings_history eh
        WHERE eh.eps_actual IS NOT NULL
        ${symbolFilter.replace('er.', 'eh.')}
        ${surpriseFilter.replace('er.eps_actual', 'eh.eps_actual').replace('er.eps_estimate', 'eh.eps_estimate')}
        ORDER BY ABS(eh.surprise_percent) DESC, eh.quarter DESC
        LIMIT $1
      `;

      const result = await query(surprisesQuery, queryParams);

      res.json({
        success: true,
        data: {
          surprises: result.rows.map(row => ({
            symbol: row.symbol,
            company_name: row.company_name || row.symbol,
            date: row.date,
            quarter: row.quarter,
            year: row.year,
            earnings: {
              estimated_eps: parseFloat(row.estimated_eps || 0),
              actual_eps: parseFloat(row.actual_eps || 0),
              eps_surprise: parseFloat(row.actual_eps || 0) - parseFloat(row.estimated_eps || 0),
              eps_surprise_percent: Math.round(parseFloat(row.eps_surprise_percent || 0) * 100) / 100
            },
            revenue: {
              estimated_revenue: parseFloat(row.estimated_revenue || 0),
              actual_revenue: parseFloat(row.actual_revenue || 0),
              revenue_surprise: parseFloat(row.actual_revenue || 0) - parseFloat(row.estimated_revenue || 0),
              revenue_surprise_percent: Math.round(parseFloat(row.revenue_surprise_percent || 0) * 100) / 100
            },
            sector: row.sector || "Unknown",
            market_cap: parseFloat(row.market_cap || 0)
          })),
          filters: {
            symbol: symbol || null,
            period,
            minSurprise: parseFloat(minSurprise || 0)
          },
          total: result.rows.length
        },
        timestamp: new Date().toISOString(),
      });

    } catch (error) {
      console.error("Earnings surprises query failed:", error.message);
      return res.status(500).json({
        success: false,
        error: "Earnings surprises query failed",
        details: error.message,
        timestamp: new Date().toISOString(),
      });
    }

  } catch (error) {
    console.error("Earnings surprises error:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch earnings surprises",
      details: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

// Get earnings details for specific symbol
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;
    if (process.env.NODE_ENV !== 'test') {
      console.log(`📈 Earnings details requested for symbol: ${symbol.toUpperCase()}`);
    }

    let result;
    try {
      const symbolQuery = `
        SELECT
          symbol,
          quarter as report_date,
          eps_actual,
          eps_estimate,
          eps_difference,
          surprise_percent,
          quarter,
          fetched_at as last_updated
        FROM earnings_history
        WHERE symbol = $1
        ORDER BY quarter DESC
        LIMIT 20
      `;

      result = await query(symbolQuery, [symbol.toUpperCase()]);
    } catch (error) {
      console.error(`Earnings query failed for ${symbol}:`, error.message);
      return res.status(500).json({
        success: false,
        error: "Earnings query failed",
        details: error.message,
        timestamp: new Date().toISOString(),
      });
    }

    if (!result.rows || result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: "No earnings data found for symbol",
        symbol: symbol.toUpperCase(),
        timestamp: new Date().toISOString(),
      });
    }

    res.json({
      success: true,
      data: result.rows,
      symbol: symbol.toUpperCase(),
      count: result.rows.length,
      timestamp: new Date().toISOString(),
    });

  } catch (error) {
    console.error(`Earnings error for symbol ${req.params.symbol}:`, error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch earnings details",
      details: error.message,
      symbol: req.params.symbol?.toUpperCase() || null,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;
