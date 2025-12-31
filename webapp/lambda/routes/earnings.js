const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");

const router = express.Router();

// Root endpoint - returns reference/documentation only
router.get("/", (req, res) => {
  res.json({
    data: {
      endpoint: "earnings",
      description: "Earnings data API - financial metrics and estimates",
      available_routes: [
        {
          path: "/calendar",
          method: "GET",
          description: "Calendar view of earnings with reported status",
          query_params: ["period", "startDate", "endDate", "symbol", "limit"]
        },
        {
          path: "/info",
          method: "GET",
          description: "Combined earnings info - estimates, history, and surprises ranked by magnitude",
          query_params: ["symbol", "limit", "minSurprise"]
        }
      ]
    },
    success: true
  });
});

// ============================================================
// Named endpoints (must come BEFORE /:symbol route)
// ============================================================

// GET /api/earnings/calendar - Earnings calendar view with filters
router.get("/calendar", async (req, res) => {
  try {
    const { period = "upcoming", startDate, endDate, symbol, limit = 100 } = req.query;

    // Determine date range based on period
    let dateCondition = "";
    const params = [];

    if (period === "past") {
      dateCondition = " AND ce.start_date <= CURRENT_DATE ";
    } else if (period === "upcoming") {
      dateCondition = " AND ce.start_date > CURRENT_DATE ";
    } else if (startDate || endDate) {
      if (startDate) {
        dateCondition += ` AND ce.start_date >= $${params.length + 1}`;
        params.push(startDate);
      }
      if (endDate) {
        dateCondition += ` AND ce.start_date <= $${params.length + 1}`;
        params.push(endDate);
      }
    }

    if (symbol) {
      dateCondition += ` AND ce.symbol = $${params.length + 1}`;
      params.push(symbol.toUpperCase());
    }

    const query_str = `
      SELECT DISTINCT ON (ce.symbol, ce.start_date)
        ce.symbol,
        ce.start_date as date,
        EXTRACT(QUARTER FROM ce.start_date) as quarter,
        EXTRACT(YEAR FROM ce.start_date) as year,
        ce.title,
        ce.fetched_at,
        cp.short_name as company_name,
        cp.sector
      FROM calendar_events ce
      LEFT JOIN company_profile cp ON ce.symbol = cp.ticker
      WHERE ce.event_type = 'earnings'
      ${dateCondition}
      ORDER BY ce.symbol ASC, ce.start_date DESC, ce.fetched_at DESC
      LIMIT $${params.length + 1}
    `;
    params.push(Math.min(parseInt(limit) || 100, 1000));

    const result = await query(query_str, params);

    const calendar = result.rows.map(row => ({
      symbol: row.symbol,
      company_name: row.company_name || row.symbol,
      sector: row.sector,
      date: row.date,
      quarter: parseInt(row.quarter),
      year: parseInt(row.year),
      title: row.title,
      fetched_at: row.fetched_at
    }));

    const limitNum = Math.min(parseInt(limit) || 100, 1000);
    const pageNum = 1;
    const totalPages = Math.ceil(calendar.length / limitNum);

    res.json({
      items: calendar,
      pagination: {
        page: pageNum,
        limit: limitNum,
        total: calendar.length,
        totalPages,
        hasNext: false,
        hasPrev: false
      },
      success: true
    });
  } catch (error) {
    console.error("Error fetching earnings calendar:", error);
    res.status(500).json({
      error: "Failed to fetch earnings calendar",
      success: false
    });
  }
});

// GET /api/earnings/info - Combined earnings info (estimates + history + surprises)
router.get("/info", async (req, res) => {
  try {
    const { symbol, limit = 50 } = req.query;

    console.log(`\n📊 /api/earnings/info request:`);
    console.log(`   symbol: "${symbol}"`);
    console.log(`   limit: ${limit}`);

    // Fetch estimates
    let estimateQuery = `
      SELECT
        ee.symbol,
        ee.period,
        ee.avg_estimate,
        ee.low_estimate,
        ee.high_estimate,
        ee.year_ago_eps,
        ee.growth,
        ee.number_of_analysts,
        cp.short_name as company_name,
        cp.sector
      FROM earnings_estimates ee
      LEFT JOIN company_profile cp ON ee.symbol = cp.ticker
      WHERE 1=1
    `;
    const estimateParams = [];

    if (symbol) {
      estimateQuery += ` AND ee.symbol = $${estimateParams.length + 1}`;
      estimateParams.push(symbol.toUpperCase());
    }

    estimateQuery += ` ORDER BY ee.symbol ASC, ee.period DESC LIMIT $${estimateParams.length + 1}`;
    estimateParams.push(Math.min(parseInt(limit) || 50, 500));

    console.log(`   Estimate Query (${estimateParams.length} params):`, estimateQuery.replace(/\n/g, ' '));
    console.log(`   Estimate Params:`, estimateParams);

    // Fetch history
    let historyQuery = `
      SELECT symbol, quarter, eps_actual, eps_estimate, eps_difference, surprise_percent, fetched_at FROM earnings_history
    `;
    const historyParams = [];

    if (symbol) {
      historyQuery += ` WHERE symbol = $${historyParams.length + 1}`;
      historyParams.push(symbol.toUpperCase());
    }

    historyQuery += ` ORDER BY quarter DESC LIMIT $${historyParams.length + 1}`;
    historyParams.push(Math.min(parseInt(limit) || 50, 500));

    console.log(`   History Query (${historyParams.length} params):`, historyQuery.replace(/\n/g, ' '));
    console.log(`   History Params:`, historyParams);

    // Fetch surprises
    let surpriseQuery = `
      SELECT
        eh.symbol,
        eh.quarter as date,
        EXTRACT(QUARTER FROM eh.quarter) as quarter,
        EXTRACT(YEAR FROM eh.quarter) as year,
        eh.eps_actual,
        eh.eps_estimate,
        eh.surprise_percent,
        cp.short_name as company_name,
        cp.sector
      FROM earnings_history eh
      LEFT JOIN company_profile cp ON eh.symbol = cp.ticker
      WHERE eh.eps_actual IS NOT NULL
        AND eh.surprise_percent IS NOT NULL
        AND ABS(eh.surprise_percent) >= $1
    `;

    const surpriseParams = [parseFloat(req.query.minSurprise || 0)];

    if (symbol) {
      surpriseQuery += ` AND eh.symbol = $${surpriseParams.length + 1}`;
      surpriseParams.push(symbol.toUpperCase());
    }

    surpriseQuery += ` ORDER BY ABS(eh.surprise_percent) DESC LIMIT $${surpriseParams.length + 1}`;
    surpriseParams.push(Math.min(parseInt(limit) || 50, 500));

    console.log(`   Surprise Query (${surpriseParams.length} params):`, surpriseQuery.replace(/\n/g, ' '));
    console.log(`   Surprise Params:`, surpriseParams);

    const [estimatesResult, historyResult, surpriseResult] = await Promise.all([
      query(estimateQuery, estimateParams),
      query(historyQuery, historyParams),
      query(surpriseQuery, surpriseParams)
    ]);

    console.log(`   Estimates returned: ${estimatesResult.rows.length}`);
    console.log(`   History returned: ${historyResult.rows.length}`);
    console.log(`   Surprises returned: ${surpriseResult.rows.length}`);

    // Format estimates
    const estimates = (estimatesResult.rows || []).map(row => ({
      symbol: row.symbol,
      company_name: row.company_name || row.symbol,
      sector: row.sector,
      period: row.period,
      eps: {
        average_estimate: row.avg_estimate ? parseFloat(row.avg_estimate) : null,
        low_estimate: row.low_estimate ? parseFloat(row.low_estimate) : null,
        high_estimate: row.high_estimate ? parseFloat(row.high_estimate) : null,
        year_ago: row.year_ago_eps ? parseFloat(row.year_ago_eps) : null,
        growth_percent: row.growth ? parseFloat(row.growth) : null
      },
      number_of_analysts: row.number_of_analysts
    }));

    // Format history
    const history = (historyResult.rows || []).map(row => ({
      symbol: row.symbol,
      quarter: row.quarter,
      eps_actual: row.eps_actual ? parseFloat(row.eps_actual) : null,
      eps_estimate: row.eps_estimate ? parseFloat(row.eps_estimate) : null,
      eps_difference: row.eps_difference ? parseFloat(row.eps_difference) : null,
      surprise_percent: row.surprise_percent ? parseFloat(row.surprise_percent) : null,
      fetched_at: row.fetched_at
    }));

    // Format surprises
    const surprises = (surpriseResult.rows || []).map(row => ({
      symbol: row.symbol,
      company_name: row.company_name || row.symbol,
      sector: row.sector,
      date: row.date,
      quarter: parseInt(row.quarter),
      year: parseInt(row.year),
      earnings: {
        actual: row.eps_actual ? parseFloat(row.eps_actual) : null,
        estimate: row.eps_estimate ? parseFloat(row.eps_estimate) : null,
        surprise_percent: row.surprise_percent ? parseFloat(row.surprise_percent) : null
      }
    }));

    res.json({
      data: {
        estimates,
        history,
        surprises
      },
      success: true
    });
  } catch (error) {
    console.error("Error fetching combined earnings data:", error);
    res.status(500).json({
      error: "Failed to fetch earnings data",
      success: false
    });
  }
});

// GET /api/earnings/sp500-trend - S&P 500 earnings trend over time
router.get("/sp500-trend", async (req, res) => {
  try {
    const { years = 10 } = req.query;

    // Fetch S&P 500 EPS data from FRED (SPASTT01USQ661S - quarterly earnings)
    const earningsQuery = `
      SELECT
        date,
        value as earnings_per_share,
        series_id
      FROM economic_data
      WHERE series_id = 'SPASTT01USQ661S'
        AND date >= CURRENT_DATE - INTERVAL '${parseInt(years)} years'
      ORDER BY date ASC
    `;

    // Fetch S&P 500 P/E ratio for context
    const peQuery = `
      SELECT
        date,
        value as pe_ratio
      FROM economic_data
      WHERE series_id = 'SP500PE'
        AND date >= CURRENT_DATE - INTERVAL '${parseInt(years)} years'
      ORDER BY date ASC
    `;

    const [earningsResult, peResult] = await Promise.all([
      query(earningsQuery),
      query(peQuery)
    ]);

    // Calculate trend metrics
    const earnings = earningsResult.rows;
    let trend = "neutral";
    let changePercent = 0;

    if (earnings.length >= 2) {
      const latest = parseFloat(earnings[earnings.length - 1].earnings_per_share);
      const yearAgo = earnings.find(row => {
        const date = new Date(row.date);
        const oneYearAgo = new Date();
        oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1);
        return Math.abs(date - oneYearAgo) < 90 * 24 * 60 * 60 * 1000; // Within 90 days
      });

      if (yearAgo) {
        const previous = parseFloat(yearAgo.earnings_per_share);
        changePercent = ((latest - previous) / previous) * 100;
        trend = changePercent > 5 ? "increasing" : changePercent < -5 ? "decreasing" : "neutral";
      }
    }

    res.json({
      data: {
        earnings: earnings.map(row => ({
          date: row.date,
          value: parseFloat(row.earnings_per_share)
        })),
        peRatio: peResult.rows.map(row => ({
          date: row.date,
          value: parseFloat(row.pe_ratio)
        })),
        summary: {
          trend,
          changePercent: changePercent.toFixed(2),
          latestEarnings: earnings.length > 0 ? parseFloat(earnings[earnings.length - 1].earnings_per_share) : null,
          latestDate: earnings.length > 0 ? earnings[earnings.length - 1].date : null
        }
      },
      success: true
    });
  } catch (error) {
    console.error("Error fetching S&P 500 earnings trend:", error);
    res.status(500).json({
      error: "Failed to fetch S&P 500 earnings trend",
      success: false
    });
  }
});

module.exports = router;
