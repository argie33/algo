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
    // BUG FIX: Validate parseInt results for NaN
    const parsedPage = parseInt(req.query.page, 10);
    const page = !isNaN(parsedPage) && parsedPage > 0 ? parsedPage : 1;

    const parsedLimit = parseInt(req.query.limit, 10);
    const limit = Math.min(!isNaN(parsedLimit) && parsedLimit > 0 ? parsedLimit : 50, 200);

    if (page < 1 || limit < 1) {
      return res.status(400).json({
        success: false,
        error: "Invalid pagination parameters: page and limit must be positive integers"
      });
    }

    const offset = (page - 1) * limit;

    // Query your actual analyst_upgrade_downgrade table from YFinance
    // Get all available analyst data (no date filter for dev purposes)
    const upgradesQuery = `
      SELECT
        a.id,
        a.symbol,
        c.short_name as company_name,
        a.firm,
        a.action,
        a.from_grade,
        a.to_grade,
        a.date,
        a.details,
        a.fetched_at
      FROM analyst_upgrade_downgrade a
      LEFT JOIN company_profile c ON a.symbol = c.ticker
      ORDER BY a.date DESC, a.fetched_at DESC
      LIMIT $1 OFFSET $2
    `;

    const result = await query(upgradesQuery, [limit, offset]);

    if (!result) {
      return res.status(500).json({
        success: false,
        error: "Database query failed"
      });
    }

    // Performance optimization: Use estimated count instead of full COUNT(*)
    // This avoids sequential scan on large tables
    const countResult = await query(`
      SELECT reltuples::bigint AS total
      FROM pg_class
      WHERE relname = 'analyst_upgrade_downgrade'
    `);
    const total = parseInt(countResult.rows[0]?.total) || 13793;

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

    // BUG FIX: Validate parseInt results for NaN
    const parsedPage = parseInt(req.query.page, 10);
    const page = !isNaN(parsedPage) && parsedPage > 0 ? parsedPage : 1;

    const parsedLimit = parseInt(req.query.limit, 10);
    const limit = Math.min(!isNaN(parsedLimit) && parsedLimit > 0 ? parsedLimit : 50, 200);

    if (page < 1 || limit < 1) {
      return res.status(400).json({
        success: false,
        error: "Invalid pagination parameters: page and limit must be positive integers"
      });
    }

    const offset = (page - 1) * limit;

    // Get real downgrade data from database
    // PERFORMANCE FIX: Add 30-day filter to avoid timeout on large table
    const downgradesQuery = `
      SELECT
        id, symbol, firm, action, from_grade, to_grade, date, details, analyst_name, fetched_at
      FROM analyst_upgrade_downgrade
      WHERE (action ILIKE '%downgrade%' OR action ILIKE '%sell%' OR action ILIKE '%reduce%')
        AND date >= CURRENT_DATE - INTERVAL '30 days'
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

    // PERFORMANCE FIX: Remove COUNT query - use hasMore pagination instead
    const hasMore = result.rows.length === limit;
    const total = null; // Not calculating total to avoid timeout

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
    let avgGrowth = 0;

    if (data.length > 1) {
      // Calculate average growth rate
      const growthRates = data.filter(row => row.growth !== null).map(row => parseFloat(row.growth) || 0);
      if (growthRates.length > 0) {
        avgGrowth = growthRates.reduce((sum, rate) => sum + rate, 0) / growthRates.length;
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

// GET /:symbol/overview - Get comprehensive analyst overview for a specific symbol
router.get("/:symbol/overview", async (req, res) => {
  try {
    const { symbol } = req.params;
    const symbolUpper = symbol.toUpperCase();

    // Get all analyst data in parallel
    const [
      earningsEstimates,
      revenueEstimates,
      epsRevisions,
      epsTrend,
      upgradesDowngrades,
      earningsHistory
    ] = await Promise.all([
      // Earnings estimates (limit to key periods)
      query(`
        SELECT symbol, period, avg_estimate, low_estimate, high_estimate,
               number_of_analysts, year_ago_eps, growth, fetched_at
        FROM earnings_estimates
        WHERE UPPER(symbol) = $1
          AND period IN ('0q', '+1q', '0y', '+1y')
        ORDER BY
          CASE period
            WHEN '0q' THEN 1
            WHEN '+1q' THEN 2
            WHEN '0y' THEN 3
            WHEN '+1y' THEN 4
          END
      `, [symbolUpper]),

      // Revenue estimates (limit to key periods)
      query(`
        SELECT symbol, period, avg_estimate, low_estimate, high_estimate,
               number_of_analysts, year_ago_revenue, growth, fetched_at
        FROM revenue_estimates
        WHERE UPPER(symbol) = $1
          AND period IN ('0q', '+1q', '0y', '+1y')
        ORDER BY
          CASE period
            WHEN '0q' THEN 1
            WHEN '+1q' THEN 2
            WHEN '0y' THEN 3
            WHEN '+1y' THEN 4
          END
      `, [symbolUpper]),

      // EPS revisions (same as earnings estimates)
      // PERFORMANCE FIX: Add LIMIT to avoid timeout
      query(`
        SELECT symbol, period, avg_estimate, low_estimate, high_estimate,
               number_of_analysts, year_ago_eps, growth, fetched_at
        FROM earnings_estimates
        WHERE UPPER(symbol) = $1
        ORDER BY period DESC
        LIMIT 20
      `, [symbolUpper]),

      // EPS trend (historical earnings estimates)
      // PERFORMANCE FIX: Add LIMIT to avoid timeout
      query(`
        SELECT symbol, period, avg_estimate, low_estimate, high_estimate,
               number_of_analysts, year_ago_eps, growth, fetched_at
        FROM earnings_estimates
        WHERE UPPER(symbol) = $1
        ORDER BY period ASC
        LIMIT 20
      `, [symbolUpper]),

      // Upgrades/downgrades
      // PERFORMANCE FIX: Add 90-day filter + LIMIT to avoid timeout on large table
      query(`
        SELECT id, symbol, firm, action, from_grade, to_grade,
               date, details, fetched_at
        FROM analyst_upgrade_downgrade
        WHERE UPPER(symbol) = $1
          AND date >= CURRENT_DATE - INTERVAL '90 days'
        ORDER BY date DESC
        LIMIT 50
      `, [symbolUpper]),

      // Earnings history
      // PERFORMANCE FIX: Add LIMIT to avoid timeout
      query(`
        SELECT id, symbol, date, eps_estimate, eps_actual,
               eps_difference, surprise_percent, fetched_at
        FROM earnings_history
        WHERE UPPER(symbol) = $1
        ORDER BY date DESC
        LIMIT 20
      `, [symbolUpper])
    ]);

    res.json({
      success: true,
      symbol: symbolUpper,
      data: {
        earnings_estimates: earningsEstimates?.rows || [],
        revenue_estimates: revenueEstimates?.rows || [],
        eps_revisions: epsRevisions?.rows || [],
        eps_trend: epsTrend?.rows || [],
        growth_estimates: [], // Placeholder - can add growth estimates table later
        recommendations: upgradesDowngrades?.rows || [],
        earnings_history: earningsHistory?.rows || []
      },
      counts: {
        earnings_estimates: earningsEstimates?.rows?.length || 0,
        revenue_estimates: revenueEstimates?.rows?.length || 0,
        eps_revisions: epsRevisions?.rows?.length || 0,
        eps_trend: epsTrend?.rows?.length || 0,
        recommendations: upgradesDowngrades?.rows?.length || 0,
        earnings_history: earningsHistory?.rows?.length || 0
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error(`Analyst overview error for symbol ${req.params.symbol}:`, error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch analyst overview for symbol",
      symbol: req.params.symbol?.toUpperCase() || null,
      details: error.message
    });
  }
});

// GET /:symbol/recommendations - Get analyst recommendations (upgrades/downgrades) for a specific symbol
router.get("/:symbol/recommendations", async (req, res) => {
  try {
    const { symbol } = req.params;
    const symbolUpper = symbol.toUpperCase();

    // Get upgrades/downgrades from YFinance
    // PERFORMANCE FIX: Add 90-day filter to avoid timeout on large table
    const upgradesResult = await query(`
      SELECT
        id, symbol, firm, action, from_grade, to_grade,
        date, details, fetched_at
      FROM analyst_upgrade_downgrade
      WHERE UPPER(symbol) = $1
        AND date >= CURRENT_DATE - INTERVAL '90 days'
      ORDER BY date DESC, fetched_at DESC
      LIMIT 50
    `, [symbolUpper]);

    res.json({
      success: true,
      symbol: symbolUpper,
      data: upgradesResult.rows || [],
      count: upgradesResult.rows?.length || 0,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error("❌ Error fetching analyst recommendations:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch analyst recommendations",
      message: error.message,
      symbol: req.params.symbol,
      timestamp: new Date().toISOString()
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
      // PERFORMANCE FIX: Add 90-day filter + LIMIT to avoid timeout on large table
      query(`
        SELECT
          id, symbol, firm, action, from_grade, to_grade,
          date, details, fetched_at
        FROM analyst_upgrade_downgrade
        WHERE UPPER(symbol) = $1
          AND date >= CURRENT_DATE - INTERVAL '90 days'
        ORDER BY date DESC, fetched_at DESC
        LIMIT 50
      `, [symbolUpper]),

      // Revenue estimates with analyst counts from YFinance (limit to key periods)
      query(`
        SELECT
          symbol, period, avg_estimate, low_estimate, high_estimate,
          number_of_analysts, year_ago_revenue, growth, fetched_at
        FROM revenue_estimates
        WHERE UPPER(symbol) = $1
          AND period IN ('0q', '+1q', '0y', '+1y')
        ORDER BY
          CASE period
            WHEN '0q' THEN 1
            WHEN '+1q' THEN 2
            WHEN '0y' THEN 3
            WHEN '+1y' THEN 4
          END
      `, [symbolUpper]),

      // EPS estimates with analyst counts from YFinance (limit to key periods)
      query(`
        SELECT
          symbol, period, avg_estimate, low_estimate, high_estimate,
          number_of_analysts, year_ago_eps, growth, fetched_at
        FROM earnings_estimates
        WHERE UPPER(symbol) = $1
          AND period IN ('0q', '+1q', '0y', '+1y')
        ORDER BY
          CASE period
            WHEN '0q' THEN 1
            WHEN '+1q' THEN 2
            WHEN '0y' THEN 3
            WHEN '+1y' THEN 4
          END
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

// ============================================
// ANALYST TREND ANALYSIS ENDPOINTS
// ============================================

// GET /:symbol/sentiment-trend - Historical sentiment data for charting
router.get("/:symbol/sentiment-trend", async (req, res) => {
  try {
    const symbol = req.params.symbol.toUpperCase();
    const daysBack = parseInt(req.query.days, 10) || 90; // Default 90 days

    const result = await query(`
      SELECT
        date,
        strong_buy_count,
        buy_count,
        hold_count,
        sell_count,
        strong_sell_count,
        total_analysts,
        recommendation_mean,
        avg_price_target,
        price_target_vs_current,
        upgrades_last_30d,
        downgrades_last_30d,
        eps_revisions_up_last_30d,
        eps_revisions_down_last_30d
      FROM analyst_sentiment_analysis
      WHERE UPPER(symbol) = $1
        AND date >= CURRENT_DATE - INTERVAL '1 day' * $2
      ORDER BY date ASC
    `, [symbol, daysBack]);

    // Handle null result or no data
    if (!result || !result.rows || result.rows.length === 0) {
      return res.json({
        success: true,
        symbol,
        days: daysBack,
        dataPoints: 0,
        chartData: [],
        trends: {
          sentimentTrend: null,
          ratingMomentum: null,
          analystCoverageTrend: null
        },
        message: "No analyst sentiment data available for this symbol",
        timestamp: new Date().toISOString()
      });
    }

    // Calculate trend metrics
    const data = result.rows;
    let sentimentTrend = null;
    let ratingMomentum = null;
    let analystCoverageTrend = null;

    if (data.length >= 2) {
      const firstDay = data[0];
      const lastDay = data[data.length - 1];

      // Sentiment trend: how recommendation_mean is changing
      const ratingChange = lastDay.recommendation_mean - firstDay.recommendation_mean;
      const ratingChangePercent = (ratingChange / firstDay.recommendation_mean) * 100;
      sentimentTrend = {
        current: parseFloat(lastDay.recommendation_mean) || null,
        previous: parseFloat(firstDay.recommendation_mean) || null,
        change: ratingChange,
        changePercent: ratingChangePercent,
        direction: ratingChange < -0.1 ? "improving" : ratingChange > 0.1 ? "deteriorating" : "stable",
        interpretation: ratingChange < -0.1 ? "More bullish ↗️" : ratingChange > 0.1 ? "More bearish ↘️" : "Stable →"
      };

      // Analyst coverage trend
      const coverageChange = lastDay.total_analysts - firstDay.total_analysts;
      const coverageChangePercent = (coverageChange / firstDay.total_analysts) * 100;
      analystCoverageTrend = {
        current: lastDay.total_analysts,
        previous: firstDay.total_analysts,
        change: coverageChange,
        changePercent: coverageChangePercent,
        interpretation: coverageChange > 0 ? `+${coverageChange} analysts (${coverageChangePercent.toFixed(1)}%)` : `${coverageChange} analysts (${coverageChangePercent.toFixed(1)}%)`
      };

      // Rating distribution trend
      const getPercentage = (count, total) => total > 0 ? (count / total) * 100 : 0;

      sentimentTrend.distributionCurrent = {
        strongBuy: getPercentage(lastDay.strong_buy_count, lastDay.total_analysts),
        buy: getPercentage(lastDay.buy_count, lastDay.total_analysts),
        hold: getPercentage(lastDay.hold_count, lastDay.total_analysts),
        sell: getPercentage(lastDay.sell_count, lastDay.total_analysts),
        strongSell: getPercentage(lastDay.strong_sell_count, lastDay.total_analysts)
      };

      sentimentTrend.distributionPrevious = {
        strongBuy: getPercentage(firstDay.strong_buy_count, firstDay.total_analysts),
        buy: getPercentage(firstDay.buy_count, firstDay.total_analysts),
        hold: getPercentage(firstDay.hold_count, firstDay.total_analysts),
        sell: getPercentage(firstDay.sell_count, firstDay.total_analysts),
        strongSell: getPercentage(firstDay.strong_sell_count, firstDay.total_analysts)
      };

      // Rating momentum: calculate slope of recommendation_mean
      const xValues = data.map((_, i) => i);
      const yValues = data.map(d => parseFloat(d.recommendation_mean) || 0);

      const meanX = xValues.reduce((a, b) => a + b, 0) / xValues.length;
      const meanY = yValues.reduce((a, b) => a + b, 0) / yValues.length;

      const numerator = xValues.reduce((sum, x, i) => sum + (x - meanX) * (yValues[i] - meanY), 0);
      const denominator = xValues.reduce((sum, x) => sum + Math.pow(x - meanX, 2), 0);
      const slope = denominator !== 0 ? numerator / denominator : 0;

      ratingMomentum = {
        slope: slope,
        velocity: slope < -0.001 ? "Improving rapidly ↗️" : slope < 0 ? "Improving →" : slope > 0.001 ? "Deteriorating rapidly ↘️" : slope > 0 ? "Deteriorating →" : "Stable →",
        momentum: Math.abs(slope) > 0.001 ? "Strong" : Math.abs(slope) > 0.0001 ? "Moderate" : "Weak"
      };
    }

    res.json({
      success: true,
      symbol,
      days: daysBack,
      dataPoints: data.length,
      chartData: data.map(d => ({
        date: d.date,
        ratingMean: parseFloat(d.recommendation_mean),
        totalAnalysts: d.total_analysts,
        strongBuy: d.strong_buy_count,
        buy: d.buy_count,
        hold: d.hold_count,
        sell: d.sell_count,
        strongSell: d.strong_sell_count,
        priceTarget: parseFloat(d.avg_price_target),
        epsUpRevisions: d.eps_revisions_up_last_30d,
        epsDownRevisions: d.eps_revisions_down_last_30d
      })),
      trends: {
        sentimentTrend,
        ratingMomentum,
        analystCoverageTrend
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error(`Sentiment trend error for ${req.params.symbol}:`, error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch sentiment trend data",
      details: error.message
    });
  }
});

// GET /:symbol/analyst-momentum - Quick momentum metrics
router.get("/:symbol/analyst-momentum", async (req, res) => {
  try {
    const symbol = req.params.symbol.toUpperCase();

    const result = await query(`
      SELECT
        date,
        strong_buy_count,
        buy_count,
        hold_count,
        sell_count,
        strong_sell_count,
        total_analysts,
        recommendation_mean,
        upgrades_last_30d,
        downgrades_last_30d,
        eps_revisions_up_last_30d,
        eps_revisions_down_last_30d
      FROM analyst_sentiment_analysis
      WHERE UPPER(symbol) = $1
        AND date >= CURRENT_DATE - INTERVAL '90 days'
      ORDER BY date ASC
    `, [symbol]);

    // Handle null result or no data
    if (!result || !result.rows || result.rows.length === 0) {
      return res.json({
        success: true,
        symbol,
        momentum: null,
        message: "No analyst data available for this symbol",
        timestamp: new Date().toISOString()
      });
    }

    const data = result.rows;
    const latest = data[data.length - 1];
    const thirtyDaysAgo = data[Math.max(0, data.length - 30)];

    // Calculate momentum scores (0-100, higher = more bullish)
    const bullishRatio = latest.total_analysts > 0
      ? ((latest.strong_buy_count + latest.buy_count) / latest.total_analysts) * 100
      : 0;

    const bearishRatio = latest.total_analysts > 0
      ? ((latest.sell_count + latest.strong_sell_count) / latest.total_analysts) * 100
      : 0;

    const sentimentScore = 50 + (bullishRatio - bearishRatio) / 2;

    // Revision momentum
    const netEpsRevisions = latest.eps_revisions_up_last_30d - latest.eps_revisions_down_last_30d;
    const revisionMomentum = latest.eps_revisions_up_last_30d + latest.eps_revisions_down_last_30d > 0
      ? (netEpsRevisions / (latest.eps_revisions_up_last_30d + latest.eps_revisions_down_last_30d)) * 100
      : 0;

    // Trend velocity - calculate only if recommendation_mean data exists
    let ratingChangeVelocity = 0;
    if (latest.recommendation_mean !== null && thirtyDaysAgo.recommendation_mean !== null) {
      ratingChangeVelocity = thirtyDaysAgo.recommendation_mean - latest.recommendation_mean;
    }

    res.json({
      success: true,
      symbol,
      momentum: {
        sentimentScore: Math.max(0, Math.min(100, sentimentScore)),
        bullishPercentage: bullishRatio.toFixed(1),
        bearishPercentage: bearishRatio.toFixed(1),
        neutralPercentage: (100 - bullishRatio - bearishRatio).toFixed(1),
        analystCount: latest.total_analysts,
        averageRating: latest.recommendation_mean !== null && !isNaN(latest.recommendation_mean) ? parseFloat(latest.recommendation_mean).toFixed(2) : "N/A",
        rating1To5Scale: {
          1: "Strong Buy",
          2: "Buy",
          3: "Hold",
          4: "Sell",
          5: "Strong Sell"
        }
      },
      revisions: {
        epsUpLast30d: latest.eps_revisions_up_last_30d,
        epsDownLast30d: latest.eps_revisions_down_last_30d,
        netMomentum: netEpsRevisions,
        momentumPercent: revisionMomentum.toFixed(1),
        interpretation: netEpsRevisions > 0 ? "Positive (more ups)" : netEpsRevisions < 0 ? "Negative (more downs)" : "Neutral"
      },
      trend: {
        ratingChangeVelocity: ratingChangeVelocity !== null ? ratingChangeVelocity.toFixed(3) : "N/A",
        direction: ratingChangeVelocity === 0 ? "Insufficient data" : ratingChangeVelocity < -0.01 ? "Improving (more bullish)" : ratingChangeVelocity > 0.01 ? "Deteriorating (more bearish)" : "Stable",
        interpretation: ratingChangeVelocity === 0 ? "Insufficient historical recommendation data" : ratingChangeVelocity < -0.05 ? "Rapidly improving ↗️" : ratingChangeVelocity < 0 ? "Slowly improving →" : ratingChangeVelocity > 0.05 ? "Rapidly deteriorating ↘️" : ratingChangeVelocity > 0 ? "Slowly deteriorating →" : "Stable"
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error(`Analyst momentum error for ${req.params.symbol}:`, error);
    res.status(500).json({
      success: false,
      error: "Failed to calculate analyst momentum",
      details: error.message
    });
  }
});

// GET /:symbol/sentiment-shift - Compare recent sentiment vs longer-term trend
router.get("/:symbol/sentiment-shift", async (req, res) => {
  try {
    const symbol = req.params.symbol.toUpperCase();

    const result = await query(`
      SELECT
        date,
        recommendation_mean,
        total_analysts,
        strong_buy_count,
        buy_count,
        hold_count,
        sell_count,
        strong_sell_count,
        upgrades_last_30d,
        downgrades_last_30d
      FROM analyst_sentiment_analysis
      WHERE UPPER(symbol) = $1
        AND date >= CURRENT_DATE - INTERVAL '180 days'
      ORDER BY date ASC
    `, [symbol]);

    if (result.rows.length === 0) {
      return res.json({
        success: true,
        symbol,
        shift: null,
        message: "No analyst data available"
      });
    }

    const data = result.rows;
    const latest = data[data.length - 1];
    const sixMonthsAgo = data[0];
    const threeMonthsAgo = data[Math.floor(data.length * 0.5)];
    const oneMonthAgo = data[Math.max(0, data.length - 30)];

    const getDistribution = (record) => ({
      strongBuy: (record.strong_buy_count / record.total_analysts * 100).toFixed(1),
      buy: (record.buy_count / record.total_analysts * 100).toFixed(1),
      hold: (record.hold_count / record.total_analysts * 100).toFixed(1),
      sell: (record.sell_count / record.total_analysts * 100).toFixed(1),
      strongSell: (record.strong_sell_count / record.total_analysts * 100).toFixed(1)
    });

    res.json({
      success: true,
      symbol,
      shift: {
        sixMonthTrend: {
          startDate: sixMonthsAgo.date,
          startRating: sixMonthsAgo.recommendation_mean.toFixed(2),
          startDistribution: getDistribution(sixMonthsAgo),
          endRating: latest.recommendation_mean.toFixed(2),
          endDistribution: getDistribution(latest),
          change: (latest.recommendation_mean - sixMonthsAgo.recommendation_mean).toFixed(3),
          interpretation: (latest.recommendation_mean - sixMonthsAgo.recommendation_mean) < -0.1 ? "Analysts becoming more bullish" : (latest.recommendation_mean - sixMonthsAgo.recommendation_mean) > 0.1 ? "Analysts becoming more bearish" : "No significant shift"
        },
        threeMonthTrend: {
          startDate: threeMonthsAgo.date,
          startRating: threeMonthsAgo.recommendation_mean.toFixed(2),
          endRating: latest.recommendation_mean.toFixed(2),
          change: (latest.recommendation_mean - threeMonthsAgo.recommendation_mean).toFixed(3),
          velocity: Math.abs(latest.recommendation_mean - threeMonthsAgo.recommendation_mean) > 0.2 ? "Fast" : "Slow"
        },
        recentActivity: {
          lastMonth: {
            upgradesCount: latest.upgrades_last_30d,
            downgradesCount: latest.downgrades_last_30d,
            netMomentum: latest.upgrades_last_30d - latest.downgrades_last_30d,
            interpretation: latest.upgrades_last_30d > latest.downgrades_last_30d ? "More upgrades than downgrades" : latest.upgrades_last_30d < latest.downgrades_last_30d ? "More downgrades than upgrades" : "Balanced activity"
          }
        }
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error(`Sentiment shift error for ${req.params.symbol}:`, error);
    res.status(500).json({
      success: false,
      error: "Failed to calculate sentiment shift",
      details: error.message
    });
  }
});

module.exports = router;