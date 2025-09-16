const express = require("express");

const { query } = require("../utils/database");

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

    const offset = (page - 1) * limit;
    console.log(
      `📊 Stock positioning data requested - symbol: ${symbol || "all"}, timeframe: ${timeframe}`
    );

    // Get institutional positioning
    let institutionalQuery = `
      SELECT 
        symbol,
        institution_type,
        institution_name,
        position_size,
        position_change_percent,
        market_share,
        filing_date,
        quarter
      FROM institutional_positioning
    `;

    let params = [];
    if (symbol) {
      institutionalQuery += ` WHERE symbol = $1`;
      params.push(symbol);
    }

    institutionalQuery += ` ORDER BY filing_date DESC, position_size DESC LIMIT $${params.length + 1} OFFSET $${params.length + 2}`;
    params.push(limit, offset);

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

    const [institutionalResult, sentimentResult] = await Promise.all([
      query(institutionalQuery, params).catch((err) => {
        console.warn("Institutional positioning query failed:", err.message);
        return { rows: [] };
      }),
      query(sentimentQuery, sentimentParams).catch((err) => {
        console.warn("Retail sentiment query failed:", err.message);
        return { rows: [] };
      }),
    ]);

    if (!institutionalResult.rows.length && !sentimentResult.rows.length) {
      return res.notFound("No positioning data found");
    }

    res.json({
      institutional_positioning: institutionalResult.rows,
      retail_sentiment: sentimentResult.rows,
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
    res
      .status(500)
      .json({
        success: false,
        error: "Failed to fetch stock positioning data",
      });
  }
});

// Get positioning summary
router.get("/summary", async (req, res) => {
  try {
    // Get institutional flow summary
    const institutionalSummary = await query(`
      SELECT 
        AVG(position_change_percent) as avg_change,
        COUNT(CASE WHEN position_change_percent > 0 THEN 1 END) as bullish_count,
        COUNT(CASE WHEN position_change_percent < 0 THEN 1 END) as bearish_count,
        COUNT(*) as total_positions
      FROM institutional_positioning
      WHERE filing_date >= CURRENT_DATE - INTERVAL '90 days'
    `);

    // Get retail sentiment summary
    const retailSummary = await query(`
      SELECT 
        AVG(bullish_percentage) as avg_bullish,
        AVG(bearish_percentage) as avg_bearish,
        AVG(net_sentiment) as avg_net_sentiment
      FROM retail_sentiment  
      WHERE date >= CURRENT_DATE - INTERVAL '30 days'
    `);

    const institutional = institutionalSummary.rows[0];
    const retail = retailSummary.rows[0];

    // Calculate overall sentiment
    let overall_positioning = "NEUTRAL";
    if (institutional.avg_change > 2 && retail.avg_net_sentiment > 40) {
      overall_positioning = "BULLISH";
    } else if (institutional.avg_change > 0 && retail.avg_net_sentiment > 20) {
      overall_positioning = "MODERATELY_BULLISH";
    } else if (
      institutional.avg_change < -2 &&
      retail.avg_net_sentiment < -20
    ) {
      overall_positioning = "BEARISH";
    } else if (institutional.avg_change < 0 && retail.avg_net_sentiment < 0) {
      overall_positioning = "MODERATELY_BEARISH";
    }

    res.json({
      market_overview: {
        institutional_flow:
          institutional.avg_change > 0 ? "BULLISH" : "BEARISH",
        retail_sentiment:
          retail.avg_net_sentiment > 20
            ? "BULLISH"
            : retail.avg_net_sentiment < -20
              ? "BEARISH"
              : "MIXED",
        overall_positioning: overall_positioning,
      },
      key_metrics: {
        institutional_avg_change: parseFloat(institutional.avg_change || 0),
        retail_net_sentiment: parseFloat(retail.avg_net_sentiment || 0),
      },
      data_freshness: {
        institutional_positions: parseInt(institutional.total_positions || 0),
        retail_readings: "last_30_days",
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

module.exports = router;
