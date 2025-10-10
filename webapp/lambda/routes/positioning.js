const express = require("express");

const { query } = require("../utils/database");
const { authenticateToken } = require("../middleware/auth");

const router = express.Router();

// Root endpoint - API info
router.get("/", async (req, res) => {
  res.json({
    message: "Position Tracking API - Ready",
    status: "operational",
    endpoints: [
      "GET /stocks - Get stock positioning data",
      "GET /summary - Get positioning summary",
    ],
    timestamp: new Date().toISOString(),
  });
});

// Get stock positioning data
router.get("/stocks", async (req, res) => {
  try {
    const { symbol, timeframe = "daily", limit = 50, page = 1 } = req.query;

    // Safely parse integers with validation to prevent NaN in database queries
    const limitNum = Math.max(1, Math.min(parseInt(limit, 10) || 50, 1000));
    const pageNum = Math.max(1, parseInt(page, 10) || 1);
    const offset = (pageNum - 1) * limitNum;
    console.log(
      `📊 Stock positioning data requested - symbol: ${symbol || "all"}, timeframe: ${timeframe}`
    );

    // Get positioning metrics (ownership, short interest, etc.)
    let metricsQuery = `
      SELECT
        pm.symbol,
        pm.date,
        pm.institutional_ownership,
        pm.institutional_float_held,
        pm.institution_count,
        pm.insider_ownership,
        pm.shares_short,
        pm.shares_short_prior_month,
        pm.short_ratio,
        pm.short_percent_of_float,
        pm.short_interest_change,
        pm.float_shares,
        pm.shares_outstanding
      FROM positioning_metrics pm
      WHERE pm.symbol IS NOT NULL
    `;

    let metricsParams = [];
    if (symbol) {
      metricsQuery += ` AND pm.symbol = $1`;
      metricsParams.push(symbol);
    }
    metricsQuery += ` ORDER BY pm.date DESC LIMIT 1`;

    // Get institutional positioning data from institutional_positioning table
    let institutionalQuery = `
      SELECT
        ip.symbol,
        ip.institution_type,
        ip.institution_name,
        ip.position_size,
        ip.position_change_percent,
        ip.market_share,
        ip.filing_date,
        ip.quarter
      FROM institutional_positioning ip
      WHERE ip.symbol IS NOT NULL
    `;

    let params = [];
    if (symbol) {
      institutionalQuery += ` AND ip.symbol = $1`;
      params.push(symbol);
    }

    institutionalQuery += ` ORDER BY ip.filing_date DESC, ip.position_size DESC LIMIT $${params.length + 1} OFFSET $${params.length + 2}`;
    params.push(limitNum, offset);

    // Get retail sentiment
    let sentimentQuery = `
      SELECT
        symbol,
        bullish_percentage,
        bearish_percentage,
        neutral_percentage,
        net_sentiment,
        sentiment_change,
        source,
        date
      FROM retail_sentiment
    `;

    let sentimentParams = [];
    if (symbol) {
      sentimentQuery += ` WHERE symbol = $1`;
      sentimentParams.push(symbol);
    }
    sentimentQuery += ` ORDER BY date DESC LIMIT 10`;

    const [metricsResult, institutionalResult, sentimentResult] = await Promise.all([
      query(metricsQuery, metricsParams),
      query(institutionalQuery, params),
      query(sentimentQuery, sentimentParams)
    ]);

    if (!metricsResult.rows.length && !institutionalResult.rows.length && !sentimentResult.rows.length) {
      return res.status(404).json({
        success: false,
        error: "No positioning data found",
        message: "No positioning data available for this symbol",
        timestamp: new Date().toISOString()
      });
    }

    // Calculate positioning score if we have metrics
    let positioningScore = null;
    const metrics = metricsResult.rows[0];

    if (metrics) {
      let score = 50; // Start neutral

      // Institutional ownership (0-30 points)
      const instOwn = parseFloat(metrics.institutional_ownership || 0);
      if (instOwn > 0.7) score += 30;
      else if (instOwn > 0.5) score += 20;
      else if (instOwn > 0.3) score += 10;
      else if (instOwn < 0.2) score -= 10;

      // Insider ownership (0-15 points)
      const insiderOwn = parseFloat(metrics.insider_ownership || 0);
      if (insiderOwn > 0.1) score += 15;
      else if (insiderOwn > 0.05) score += 10;
      else if (insiderOwn > 0.02) score += 5;

      // Short interest (-20 to +10 points)
      const shortPct = parseFloat(metrics.short_percent_of_float || 0);
      if (shortPct > 0.2) score -= 20; // Heavy short
      else if (shortPct > 0.1) score -= 10;
      else if (shortPct > 0.05) score -= 5;
      else if (shortPct < 0.02) score += 10; // Very low short

      // Short interest trend (0-15 points)
      const shortChange = parseFloat(metrics.short_interest_change || 0);
      if (shortChange < -0.1) score += 15; // Shorts covering
      else if (shortChange < -0.05) score += 10;
      else if (shortChange > 0.1) score -= 15; // Shorts increasing
      else if (shortChange > 0.05) score -= 10;

      positioningScore = Math.max(0, Math.min(100, score));
    }

    res.json({
      positioning_metrics: metricsResult.rows[0] || null,
      positioning_score: positioningScore,
      institutional_holders: institutionalResult.rows,
      retail_sentiment: sentimentResult.rows[0] || null,
      metadata: {
        symbol: symbol || "all",
        timeframe: timeframe,
        total_records: {
          institutional: institutionalResult.rows.length,
          sentiment: sentimentResult.rows.length,
        },
        last_updated: new Date().toISOString(),
      },
    });
  } catch (error) {
    console.error("Error fetching stock positioning data:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch stock positioning data",
    });
  }
});

// Get positioning summary
router.get("/summary", authenticateToken, async (req, res) => {
  try {
    // Get institutional positioning summary from positioning_metrics
    const institutionalSummary = await query(`
      SELECT
        AVG(COALESCE(pm.institutional_ownership, 0)) as avg_institutional_ownership,
        AVG(COALESCE(pm.insider_ownership, 0)) as avg_insider_ownership,
        AVG(COALESCE(pm.short_percent_of_float, 0)) as avg_short_interest,
        AVG(COALESCE(pm.short_interest_change, 0)) as avg_short_change,
        COUNT(CASE WHEN pm.institutional_ownership > 0.5 THEN 1 END) as high_institutional_count,
        COUNT(CASE WHEN pm.short_percent_of_float > 0.1 THEN 1 END) as high_short_count,
        COUNT(*) as total_positions
      FROM positioning_metrics pm
      WHERE pm.date >= CURRENT_DATE - INTERVAL '30 days'
    `);

    // Get retail sentiment summary
    const retailSummary = await query(`
      SELECT
        AVG(bullish_percentage) as avg_bullish,
        AVG(bearish_percentage) as avg_bearish,
        AVG(net_sentiment) as avg_net_sentiment,
        COUNT(*) as total_readings
      FROM retail_sentiment
      WHERE date >= CURRENT_DATE - INTERVAL '30 days'
    `);

    const institutional = institutionalSummary.rows[0];
    const retail = retailSummary.rows[0];

    // Calculate institutional flow (bullish if high ownership, bearish if high short interest)
    const inst_ownership_score = parseFloat(institutional.avg_institutional_ownership || 0) * 100;
    const short_interest_score = parseFloat(institutional.avg_short_interest || 0) * 100;
    const short_change_score = parseFloat(institutional.avg_short_change || 0) * 100;

    let institutional_flow = "NEUTRAL";
    if (inst_ownership_score > 60 && short_change_score < -5) {
      institutional_flow = "BULLISH";
    } else if (short_interest_score > 15 || short_change_score > 10) {
      institutional_flow = "BEARISH";
    } else if (inst_ownership_score > 50) {
      institutional_flow = "MODERATELY_BULLISH";
    } else if (short_interest_score > 10) {
      institutional_flow = "MODERATELY_BEARISH";
    }

    // Calculate overall positioning
    const retail_sentiment_value = parseFloat(retail.avg_net_sentiment || 0);
    let overall_positioning = "NEUTRAL";

    if (institutional_flow === "BULLISH" && retail_sentiment_value > 40) {
      overall_positioning = "BULLISH";
    } else if (
      (institutional_flow === "BULLISH" || institutional_flow === "MODERATELY_BULLISH") &&
      retail_sentiment_value > 20
    ) {
      overall_positioning = "MODERATELY_BULLISH";
    } else if (institutional_flow === "BEARISH" && retail_sentiment_value < -20) {
      overall_positioning = "BEARISH";
    } else if (
      (institutional_flow === "BEARISH" || institutional_flow === "MODERATELY_BEARISH") &&
      retail_sentiment_value < 0
    ) {
      overall_positioning = "MODERATELY_BEARISH";
    }

    res.json({
      market_overview: {
        institutional_flow: institutional_flow,
        retail_sentiment:
          retail_sentiment_value > 20
            ? "BULLISH"
            : retail_sentiment_value < -20
              ? "BEARISH"
              : "MIXED",
        overall_positioning: overall_positioning,
      },
      key_metrics: {
        avg_institutional_ownership: parseFloat(institutional.avg_institutional_ownership || 0),
        avg_insider_ownership: parseFloat(institutional.avg_insider_ownership || 0),
        avg_short_interest: parseFloat(institutional.avg_short_interest || 0),
        avg_short_change: parseFloat(institutional.avg_short_change || 0),
        retail_net_sentiment: retail_sentiment_value,
      },
      data_freshness: {
        institutional_positions: parseInt(institutional.total_positions || 0),
        retail_readings: parseInt(retail.total_readings || 0),
        high_institutional_count: parseInt(institutional.high_institutional_count || 0),
        high_short_count: parseInt(institutional.high_short_count || 0),
      },
      last_updated: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching positioning summary:", error);
    res
      .status(500)
      .json({ success: false, error: "Failed to fetch positioning summary" });
  }
});

// Positioning data - top movers by positioning changes
router.get("/data", async (req, res) => {
  try {
    const { limit = 20 } = req.query;
    const limitNum = Math.max(1, Math.min(parseInt(limit, 10) || 20, 100));

    // Get stocks with highest institutional ownership changes
    const topInstitutionalFlows = await query(`
      WITH latest_metrics AS (
        SELECT DISTINCT ON (symbol)
          symbol,
          institutional_ownership,
          insider_ownership,
          short_percent_of_float,
          short_interest_change,
          date
        FROM positioning_metrics
        ORDER BY symbol, date DESC
      )
      SELECT
        lm.symbol,
        lm.institutional_ownership,
        lm.insider_ownership,
        lm.short_percent_of_float,
        lm.short_interest_change,
        lm.date,
        cp.company_name,
        cp.sector,
        cp.industry
      FROM latest_metrics lm
      LEFT JOIN company_profile cp ON lm.symbol = cp.symbol
      WHERE lm.institutional_ownership IS NOT NULL
      ORDER BY ABS(COALESCE(lm.short_interest_change, 0)) DESC
      LIMIT $1
    `, [limitNum]);

    // Get latest retail sentiment trends
    const retailTrends = await query(`
      SELECT DISTINCT ON (symbol)
        symbol,
        bullish_percentage,
        bearish_percentage,
        net_sentiment,
        sentiment_change,
        source,
        date
      FROM retail_sentiment
      ORDER BY symbol, date DESC
      LIMIT $1
    `, [limitNum]);

    res.json({
      success: true,
      data: {
        top_institutional_flows: topInstitutionalFlows.rows,
        retail_sentiment_trends: retailTrends.rows,
      },
      metadata: {
        limit: limitNum,
        institutional_count: topInstitutionalFlows.rows.length,
        retail_count: retailTrends.rows.length,
      },
      timestamp: new Date().toISOString(),
    });
  } catch (error) {
    console.error("Error fetching positioning data:", error);
    res.status(500).json({
      success: false,
      error: "Positioning data unavailable",
      message: error.message,
      timestamp: new Date().toISOString(),
    });
  }
});

module.exports = router;
