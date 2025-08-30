const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Root endpoint - provides overview of available analyst endpoints
router.get("/", async (req, res) => {
  res.success({
    message: "Analysts API - Ready",
    timestamp: new Date().toISOString(),
    status: "operational", 
    endpoints: [
      "/upgrades - Get analyst upgrades/downgrades",
      "/recent-actions - Get recent analyst actions",
      "/:ticker/recommendations - Get analyst recommendations for ticker",
      "/:ticker/earnings-estimates - Get earnings estimates",
      "/:ticker/revenue-estimates - Get revenue estimates",
      "/:ticker/earnings-history - Get earnings history",
      "/:ticker/eps-revisions - Get EPS revisions",
      "/:ticker/eps-trend - Get EPS trend data",
      "/:ticker/growth-estimates - Get growth estimates",
      "/:ticker/overview - Get comprehensive analyst overview"
    ]
  });
});

// Get analyst upgrades/downgrades
router.get("/upgrades", async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;
    const upgradesQuery = `
      SELECT 
        asa.symbol,
        cp.company_name,
        asa.upgrades_last_30d,
        asa.downgrades_last_30d,
        asa.date,
        CASE 
          WHEN asa.upgrades_last_30d > asa.downgrades_last_30d THEN 'Upgrade'
          WHEN asa.downgrades_last_30d > asa.upgrades_last_30d THEN 'Downgrade' 
          ELSE 'Neutral'
        END as action,
        'Analyst Consensus' as firm,
        CONCAT('Recent activity: ', asa.upgrades_last_30d, ' upgrades, ', asa.downgrades_last_30d, ' downgrades') as details
      FROM analyst_sentiment_analysis asa
      LEFT JOIN company_profile cp ON asa.symbol = cp.ticker
      WHERE (asa.upgrades_last_30d > 0 OR asa.downgrades_last_30d > 0)
      ORDER BY asa.date DESC, (asa.upgrades_last_30d + asa.downgrades_last_30d) DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM analyst_sentiment_analysis
      WHERE (upgrades_last_30d > 0 OR downgrades_last_30d > 0)
    `;

    const [upgradesResult, countResult] = await Promise.all([
      query(upgradesQuery, [limit, offset]),
      query(countQuery),
    ]);

    // Add null checking for database availability - return graceful degradation instead of throwing
    if (!upgradesResult || !upgradesResult.rows || !countResult || !countResult.rows) {
      console.warn("Analyst upgrades query returned null result, database may be unavailable");
      return res.error("Database temporarily unavailable", 503, {
        message: "Analyst upgrades temporarily unavailable - database connection issue",
        data: [],
        pagination: {
          page,
          limit,
          total: 0,
          totalPages: 0,
          hasNext: false,
          hasPrev: false
        }
      });
    }

    // Map company_name to company for frontend compatibility
    const mappedRows = upgradesResult.rows.map((row) => ({
      ...row,
      company: row.company_name,
    }));

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    res.success({
      data: mappedRows,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1,
      },
    });
  } catch (error) {
    console.error("Error fetching analyst upgrades:", error);
    return res.error("Failed to fetch analyst upgrades", 500);
  }
});

// Get recommendations for specific stock
router.get("/:ticker/recommendations", async (req, res) => {
  try {
    const { ticker } = req.params;

    const recQuery = `
      SELECT 
        'current' as period,
        asa.strong_buy_count as strong_buy,
        asa.buy_count as buy,
        asa.hold_count as hold,
        asa.sell_count as sell,
        asa.strong_sell_count as strong_sell,
        asa.date as collected_date,
        asa.recommendation_mean,
        asa.total_analysts,
        asa.avg_price_target,
        asa.high_price_target,
        asa.low_price_target,
        asa.price_target_vs_current
      FROM analyst_sentiment_analysis asa
      WHERE UPPER(asa.symbol) = UPPER($1)
      ORDER BY asa.date DESC
      LIMIT 12
    `;

    const result = await query(recQuery, [ticker.toUpperCase()]);

    // Add null safety check
    if (!result || !result.rows) {
      return res.error("Database temporarily unavailable", 503, {
        message: "Analyst recommendations temporarily unavailable - database connection issue",
        ticker: ticker.toUpperCase(),
        recommendations: []
      });
    }

    res.success({
      ticker: ticker.toUpperCase(),
      recommendations: result.rows,
    });
  } catch (error) {
    console.error("Error fetching recommendations:", error);
    return res.error("Failed to fetch recommendations" , 500);
  }
});

// Get earnings estimates
router.get("/:ticker/earnings-estimates", async (req, res) => {
  try {
    const { ticker } = req.params;

    const estimatesQuery = `
      SELECT 
        CONCAT('Q', er.quarter, ' ', er.year) as period,
        er.eps_estimate as estimate,
        er.eps_reported as actual,
        (er.eps_reported - er.eps_estimate) as difference,
        er.surprise_percent,
        er.report_date as reported_date
      FROM earnings_reports er
      WHERE UPPER(er.symbol) = UPPER($1)
      ORDER BY er.report_date DESC
      LIMIT 8
    `;

    const result = await query(estimatesQuery, [ticker.toUpperCase()]);

    res.success({
      ticker: ticker.toUpperCase(),
      estimates: result.rows,
    });
  } catch (error) {
    console.error("Error fetching earnings estimates:", error);
    return res.error("Failed to fetch earnings estimates" , 500);
  }
});

// Get revenue estimates
router.get("/:ticker/revenue-estimates", async (req, res) => {
  try {
    const { ticker } = req.params;

    const revenueQuery = `
      SELECT 
        CONCAT('Q', er.quarter, ' ', er.year) as period,
        NULL as estimate,
        er.revenue as actual,
        NULL as difference,
        NULL as surprise_percent,
        er.report_date as reported_date
      FROM earnings_reports er
      WHERE UPPER(er.symbol) = UPPER($1)
      ORDER BY er.report_date DESC
      LIMIT 8
    `;

    const result = await query(revenueQuery, [ticker.toUpperCase()]);

    res.success({
      ticker: ticker.toUpperCase(),
      estimates: result.rows,
    });
  } catch (error) {
    console.error("Error fetching revenue estimates:", error);
    return res.error("Failed to fetch revenue estimates" , 500);
  }
});

// Get earnings history
router.get("/:ticker/earnings-history", async (req, res) => {
  try {
    const { ticker } = req.params;

    const historyQuery = `
      SELECT 
        CONCAT('Q', er.quarter, ' ', er.year) as quarter,
        er.eps_estimate as estimate,
        er.eps_reported as actual,
        (er.eps_reported - er.eps_estimate) as difference,
        er.surprise_percent,
        er.report_date as earnings_date
      FROM earnings_reports er
      WHERE UPPER(er.symbol) = UPPER($1)
      ORDER BY er.report_date DESC
      LIMIT 12
    `;

    const result = await query(historyQuery, [ticker.toUpperCase()]);

    res.success({
      ticker: ticker.toUpperCase(),
      history: result.rows,
    });
  } catch (error) {
    console.error("Error fetching earnings history:", error);
    return res.error("Failed to fetch earnings history" , 500);
  }
});

// Get EPS revisions for a ticker
router.get("/:ticker/eps-revisions", async (req, res) => {
  try {
    const { ticker } = req.params;

    const revisionsQuery = `
      SELECT 
        asa.symbol,
        '0q' as period,
        0 as up_last7days,
        asa.eps_revisions_up_last_30d as up_last30days,
        asa.eps_revisions_down_last_30d as down_last30days,
        0 as down_last7days,
        asa.created_at as fetched_at
      FROM analyst_sentiment_analysis asa
      WHERE UPPER(asa.symbol) = UPPER($1)
      ORDER BY asa.date DESC
      LIMIT 1
    `;

    const result = await query(revisionsQuery, [ticker]);

    res.success({ticker: ticker.toUpperCase(),
      data: result.rows,
      metadata: {
        count: result.rows.length,
        timestamp: new Date().toISOString(),
      },
    });
  } catch (error) {
    console.error("EPS revisions fetch error:", error);
    return res.error("Failed to fetch EPS revisions", 500, {
      message: error.message,
    });
  }
});

// Get EPS trend for a ticker
router.get("/:ticker/eps-trend", async (req, res) => {
  try {
    const { ticker } = req.params;

    // Return trend data based on earnings reports historical data
    const trendQuery = `
      SELECT 
        er.symbol,
        '0q' as period,
        er.eps_reported as current,
        NULL as days7ago,
        NULL as days30ago,
        NULL as days60ago,
        NULL as days90ago,
        er.report_date as fetched_at
      FROM earnings_reports er
      WHERE UPPER(er.symbol) = UPPER($1)
      ORDER BY er.report_date DESC
      LIMIT 1
    `;

    const result = await query(trendQuery, [ticker]);

    res.success({ticker: ticker.toUpperCase(),
      data: result.rows,
      metadata: {
        count: result.rows.length,
        timestamp: new Date().toISOString(),
      },
    });
  } catch (error) {
    console.error("EPS trend fetch error:", error);
    return res.error("Failed to fetch EPS trend", 500, {
      message: error.message,
    });
  }
});

// Get growth estimates for a ticker
router.get("/:ticker/growth-estimates", async (req, res) => {
  try {
    const { ticker } = req.params;

    // Return placeholder growth estimates based on available data
    const growthQuery = `
      SELECT 
        er.symbol,
        '0q' as period,
        'N/A' as stock_trend,
        'N/A' as index_trend,
        er.report_date as fetched_at
      FROM earnings_reports er
      WHERE UPPER(er.symbol) = UPPER($1)
      ORDER BY er.report_date DESC
      LIMIT 1
    `;

    const result = await query(growthQuery, [ticker]);

    res.success({ticker: ticker.toUpperCase(),
      data: result.rows,
      metadata: {
        count: result.rows.length,
        timestamp: new Date().toISOString(),
        note: "Growth estimates not available - showing placeholder data"
      },
    });
  } catch (error) {
    console.error("Growth estimates fetch error:", error);
    return res.error("Failed to fetch growth estimates", 500, {
      message: error.message,
    });
  }
});

// NOTE: Duplicate recommendations endpoint removed - using the one at line 89

// Get comprehensive analyst overview for a ticker
router.get("/:ticker/overview", async (req, res) => {
  try {
    const { ticker } = req.params;

    // Get all analyst data in parallel using existing tables
    const [
      earningsData,
      revenueData, 
      analystData
    ] = await Promise.all([
      query(
        `SELECT 
          CONCAT('Q', er.quarter, ' ', er.year) as period,
          er.eps_estimate as estimate,
          er.eps_reported as actual,
          (er.eps_reported - er.eps_estimate) as difference,
          er.surprise_percent,
          er.report_date as reported_date
        FROM earnings_reports er
        WHERE UPPER(er.symbol) = UPPER($1)
        ORDER BY er.report_date DESC
        LIMIT 8`,
        [ticker]
      ),
      query(
        `SELECT 
          CONCAT('Q', er.quarter, ' ', er.year) as period,
          NULL as estimate,
          er.revenue as actual,
          NULL as difference,
          NULL as surprise_percent,
          er.report_date as reported_date
        FROM earnings_reports er
        WHERE UPPER(er.symbol) = UPPER($1)
        ORDER BY er.report_date DESC
        LIMIT 8`,
        [ticker]
      ),
      query(
        `SELECT 
          'current' as period,
          asa.strong_buy_count as strong_buy,
          asa.buy_count as buy,
          asa.hold_count as hold,
          asa.sell_count as sell,
          asa.strong_sell_count as strong_sell,
          asa.date as collected_date,
          asa.recommendation_mean,
          asa.total_analysts,
          asa.avg_price_target,
          asa.high_price_target,
          asa.low_price_target,
          asa.price_target_vs_current,
          asa.eps_revisions_up_last_30d,
          asa.eps_revisions_down_last_30d
        FROM analyst_sentiment_analysis asa
        WHERE UPPER(asa.symbol) = UPPER($1)
        ORDER BY asa.date DESC
        LIMIT 1`,
        [ticker]
      )
    ]);

    res.success({ticker: ticker.toUpperCase(),
      data: {
        earnings_estimates: earningsData.rows,
        revenue_estimates: revenueData.rows,
        earnings_history: earningsData.rows,
        eps_revisions: analystData.rows.map(row => ({
          symbol: ticker.toUpperCase(),
          period: '0q',
          up_last7days: 0,
          up_last30days: row.eps_revisions_up_last_30d,
          down_last30days: row.eps_revisions_down_last_30d,
          down_last7days: 0,
          fetched_at: row.collected_date
        })),
        eps_trend: analystData.rows.map(row => ({
          symbol: ticker.toUpperCase(),
          period: '0q',
          current: null,
          days7ago: null,
          days30ago: null,
          days60ago: null,
          days90ago: null,
          fetched_at: row.collected_date
        })),
        growth_estimates: [{
          symbol: ticker.toUpperCase(),
          period: '0q',
          stock_trend: 'N/A',
          index_trend: 'N/A',
          fetched_at: new Date().toISOString()
        }],
        recommendations: analystData.rows,
      },
      metadata: {
        timestamp: new Date().toISOString(),
        note: "Overview data adapted from existing tables"
      },
    });
  } catch (error) {
    console.error("Analyst overview fetch error:", error);
    return res.error("Failed to fetch analyst overview", 500, {
      message: error.message,
    });
  }
});

// Get recent analyst actions (upgrades/downgrades) for the most recent day
router.get("/recent-actions", async (req, res) => {
  try {
    const limit = parseInt(req.query.limit) || 10;

    // Get the most recent date with analyst actions from sentiment analysis
    const recentDateQuery = `
      SELECT DISTINCT date 
      FROM analyst_sentiment_analysis 
      WHERE (upgrades_last_30d > 0 OR downgrades_last_30d > 0)
      ORDER BY date DESC 
      LIMIT 1
    `;

    const recentDateResult = await query(recentDateQuery);

    if (!recentDateResult.rows || recentDateResult.rows.length === 0) {
      return res.success({
        data: [],
        summary: {
          date: null,
          total_actions: 0,
          upgrades: 0,
          downgrades: 0,
        },
        message: "No analyst actions found",
      });
    }

    const mostRecentDate = recentDateResult.rows[0].date;

    // Get all actions for the most recent date from sentiment analysis
    const recentActionsQuery = `
      SELECT 
        asa.symbol,
        cp.company_name,
        NULL as from_grade,
        NULL as to_grade,
        CASE 
          WHEN asa.upgrades_last_30d > asa.downgrades_last_30d THEN 'Upgrade'
          WHEN asa.downgrades_last_30d > asa.upgrades_last_30d THEN 'Downgrade' 
          ELSE 'Neutral'
        END as action,
        'Analyst Consensus' as firm,
        asa.date,
        CONCAT('Recent activity: ', asa.upgrades_last_30d, ' upgrades, ', asa.downgrades_last_30d, ' downgrades') as details,
        CASE 
          WHEN asa.upgrades_last_30d > asa.downgrades_last_30d THEN 'upgrade'
          WHEN asa.downgrades_last_30d > asa.upgrades_last_30d THEN 'downgrade'
          ELSE 'neutral'
        END as action_type
      FROM analyst_sentiment_analysis asa
      LEFT JOIN company_profile cp ON asa.symbol = cp.ticker
      WHERE asa.date = $1
        AND (asa.upgrades_last_30d > 0 OR asa.downgrades_last_30d > 0)
      ORDER BY asa.date DESC, asa.symbol ASC
      LIMIT $2
    `;

    const actionsResult = await query(recentActionsQuery, [
      mostRecentDate,
      limit,
    ]);

    // Count action types
    const actions = actionsResult.rows || [];
    const upgrades = actions.filter(
      (action) => action.action_type === "upgrade"
    );
    const downgrades = actions.filter(
      (action) => action.action_type === "downgrade"
    );
    const neutrals = actions.filter(
      (action) => action.action_type === "neutral"
    );

    res.success({
      data: actions,
      summary: {
        date: mostRecentDate,
        total_actions: actions.length,
        upgrades: upgrades.length,
        downgrades: downgrades.length,
        neutrals: neutrals.length,
      },
      metadata: {
        timestamp: new Date().toISOString(),
      },
    });
  } catch (error) {
    console.error("Error fetching recent analyst actions:", error);
    return res.error("Failed to fetch recent analyst actions", 500);
  }
});

module.exports = router;
