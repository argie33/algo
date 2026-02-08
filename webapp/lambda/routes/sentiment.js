const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Root endpoint - returns available sub-endpoints
router.get("/", (req, res) => {
  return res.json({
    data: {
      endpoint: "sentiment",
      available_routes: [
        "/analyst - Analyst sentiment data",
        "/current - Current sentiment readings",
        "/history - Historical sentiment data",
        "/divergence - Sentiment divergence analysis"
      ]
    },
    success: true
  });
});

// GET /api/sentiment/data - Get sentiment data (stocks with analyst sentiment)
router.get("/data", async (req, res) => {
  try {
    const { limit = "100", page = "1", symbol } = req.query;
    const limitNum = Math.min(parseInt(limit), 500);
    const pageNum = Math.max(parseInt(page), 1);
    const offset = (pageNum - 1) * limitNum;

    // Query analyst sentiment analysis data which contains stock sentiment metrics
    let countQueryStr = `SELECT COUNT(*) as total FROM analyst_sentiment_analysis WHERE symbol IS NOT NULL`;
    let queryStr = `
      SELECT
        symbol,
        date_recorded as date,
        total_analysts as analyst_count,
        bullish_count,
        bearish_count,
        neutral_count,
        target_price,
        current_price,
        upside_downside_percent
      FROM analyst_sentiment_analysis
      WHERE symbol IS NOT NULL
      ORDER BY date_recorded DESC, symbol ASC
      LIMIT $1 OFFSET $2
    `;
    let countParams = [];
    let params = [limitNum, offset];

    if (symbol) {
      countQueryStr = `SELECT COUNT(*) as total FROM analyst_sentiment_analysis WHERE symbol = $1`;
      countParams = [symbol.toUpperCase()];
      queryStr = `
        SELECT
          symbol,
          date_recorded as date,
          total_analysts as analyst_count,
          bullish_count,
          bearish_count,
          neutral_count,
          target_price,
          current_price,
          upside_downside_percent
        FROM analyst_sentiment_analysis
        WHERE symbol = $1
        ORDER BY date_recorded DESC
        LIMIT $2 OFFSET $3
      `;
      params = [symbol.toUpperCase(), limitNum, offset];
    }

    const countResult = await query(countQueryStr, countParams);
    const total = parseInt(countResult.rows[0]?.total || 0);
    const totalPages = Math.ceil(total / limitNum);

    const result = await query(queryStr, params);

    return res.json({
      items: result.rows || [],
      pagination: {
        page: pageNum,
        limit: limitNum,
        total,
        totalPages,
        hasNext: pageNum < totalPages,
        hasPrev: pageNum > 1
      },
      success: true
    });
  } catch (error) {
    console.error("Sentiment data error:", error.message);
    return res.status(500).json({
      error: "Failed to fetch sentiment data",
      success: false
    });
  }
});

// AAII endpoint removed - consolidated in market.js /aaii
// Use GET /api/market/aaii for AAII sentiment data instead

// GET /api/sentiment/analyst - Analyst sentiment
router.get("/analyst", async (req, res) => {
  try {
    const { symbol, limit = "50", page = "1" } = req.query;
    const limitNum = Math.min(parseInt(limit), 500);
    const pageNum = Math.max(parseInt(page), 1);
    const offset = (pageNum - 1) * limitNum;

    let countQueryStr = `SELECT COUNT(*) as total FROM analyst_sentiment_analysis`;
    let queryStr = `
      SELECT symbol, date_recorded as date, total_analysts as analyst_count, bullish_count, bearish_count, neutral_count FROM analyst_sentiment_analysis
      ORDER BY date_recorded DESC
      LIMIT $1 OFFSET $2
    `;
    let countParams = [];
    let params = [limitNum, offset];

    if (symbol) {
      countQueryStr = `SELECT COUNT(*) as total FROM analyst_sentiment_analysis WHERE symbol = $1`;
      countParams = [symbol.toUpperCase()];
      queryStr = `
        SELECT symbol, date_recorded as date, total_analysts as analyst_count, bullish_count, bearish_count, neutral_count FROM analyst_sentiment_analysis
        WHERE symbol = $1
        ORDER BY date_recorded DESC
        LIMIT $2 OFFSET $3
      `;
      params = [symbol.toUpperCase(), limitNum, offset];
    }

    const countResult = await query(countQueryStr, countParams);
    const total = parseInt(countResult.rows[0]?.total || 0);
    const totalPages = Math.ceil(total / limitNum);

    const result = await query(queryStr, params);
    return res.json({
      items: result.rows || [],
      pagination: {
        page: pageNum,
        limit: limitNum,
        total,
        totalPages,
        hasNext: pageNum < totalPages,
        hasPrev: pageNum > 1
      },
      success: true
    });
  } catch (error) {
    console.error("Analyst sentiment error:", error);
    return res.status(500).json({ error: "Failed to fetch analyst sentiment data", success: false });
  }
});

// GET /api/sentiment/history - Sentiment history (with fear/greed, NAAIM, AAII data)
router.get("/history", async (req, res) => {
  try {
    const { days = "30" } = req.query;
    const daysNum = Math.max(parseInt(days), 1);

    // Try to fetch analyst sentiment history
    let queryStr = `
      SELECT
        date_recorded as date,
        total_analysts as analyst_count,
        bullish_count,
        bearish_count,
        neutral_count
      FROM analyst_sentiment_analysis
      ORDER BY date_recorded DESC
      LIMIT $1
    `;

    try {
      const result = await query(queryStr, [daysNum]);
      return res.json({
        data: result.rows || [],
        period_days: daysNum,
        success: true
      });
    } catch (tableError) {
      // If analyst table doesn't exist, return empty history
      console.warn("Analyst sentiment table not available:", tableError.message);
      return res.json({
        data: [],
        period_days: daysNum,
        message: "Historical data not available",
        success: true
      });
    }
  } catch (error) {
    console.error("Sentiment history error:", error);
    return res.status(500).json({
      error: "Failed to fetch sentiment history",
      success: false
    });
  }
});

// GET /api/sentiment/current - Current market sentiment (fear/greed, NAAIM, AAII)
router.get("/current", async (req, res) => {
  try {
    // Get the latest sentiment readings
    // Note: market_metrics table doesn't exist, returning null values for now
    return res.json({
      data: {
        fear_greed: null,
        naaim: null,
        aaii: null,
        note: "Sentiment metrics data not available"
      },
      success: true
    });
  } catch (error) {
    console.error("Current sentiment error:", error);
    return res.status(500).json({
      error: "Failed to fetch current sentiment",
      success: false
    });
  }
});

// GET /api/sentiment/divergence - Sentiment divergence between retail and professionals
router.get("/divergence", async (req, res) => {
  try {
    const { symbol } = req.query;

    let queryStr = `
      SELECT
        symbol,
        date,
        analyst_count,
        bull_count,
        bear_count,
        hold_count,
        ROUND((bull_count::float / NULLIF(analyst_count, 0) * 100)::numeric, 2) as bull_percent,
        ROUND((bear_count::float / NULLIF(analyst_count, 0) * 100)::numeric, 2) as bear_percent,
        ROUND((hold_count::float / NULLIF(analyst_count, 0) * 100)::numeric, 2) as hold_percent
      FROM analyst_sentiment_analysis
      WHERE date >= NOW() - INTERVAL '90 days'
    `;

    const params = [];

    if (symbol) {
      queryStr += ` AND symbol = $1`;
      params.push(symbol.toUpperCase());
    }

    queryStr += ` ORDER BY date DESC LIMIT 100`;

    const result = await query(queryStr, params);

    return res.json({
      items: result.rows || [],
      success: true
    });
  } catch (error) {
    console.error("Sentiment divergence error:", error);
    return res.status(500).json({
      error: "Failed to fetch sentiment divergence",
      success: false
    });
  }
});

module.exports = router;
