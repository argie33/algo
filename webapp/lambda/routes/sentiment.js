const express = require("express");

const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const router = express.Router();

router.get("/", (req, res) => {
  return sendSuccess(res, {
    endpoint: "sentiment",
    available_routes: [
      "/data - Analyst sentiment data",
      "/summary - Consolidated sentiment (fear/greed, analyst, AAII, NAAIM)"
    ]
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
        total_analysts,
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
          date as date,
          total_analysts as total_analysts,
          bullish_count,
          bearish_count,
          neutral_count,
          target_price,
          current_price,
          upside_downside_percent
        FROM analyst_sentiment_analysis
        WHERE symbol = $1
        ORDER BY date DESC
        LIMIT $2 OFFSET $3
      `;
      params = [symbol.toUpperCase(), limitNum, offset];
    }

    const countResult = await query(countQueryStr, countParams);
    const total = parseInt(countResult.rows[0]?.total || 0);

    const result = await query(queryStr, params);

    return sendPaginated(res, result.rows || [], {
      limit: limitNum,
      offset,
      total,
      page: pageNum,
      totalPages: Math.ceil(total / limitNum)
    });
  } catch (error) {
    return sendError(res, `Failed to fetch sentiment data: ${error.message}`, 500);
  }
});

// GET /api/sentiment/summary - Consolidated sentiment summary
router.get("/summary", async (req, res) => {
  try {
    // Fetch all sentiment data sources
    let fearGreed = null, naaim = null, aaii = null, analyst = null;

    try {
      const fearGreedResult = await query(
        `SELECT fear_greed_value as value, date FROM fear_greed_index ORDER BY date DESC LIMIT 1`
      );
      fearGreed = fearGreedResult.rows[0] || null;
    } catch (e) {
      console.warn("fear_greed_index not available:", e.message);
    }

    try {
      const naaImResult = await query(
        `SELECT naaim_number_mean, bullish, bearish, date FROM naaim ORDER BY date DESC LIMIT 1`
      );
      naaim = naaImResult.rows[0] || null;
    } catch (e) {
      console.warn("naaim not available:", e.message);
    }

    try {
      const aaiiResult = await query(
        `SELECT bullish, neutral, bearish, date FROM aaii_sentiment ORDER BY date DESC LIMIT 1`
      );
      aaii = aaiiResult.rows[0] || null;
    } catch (e) {
      console.warn("aaii_sentiment not available:", e.message);
    }

    try {
      const analystResult = await query(
        `SELECT total_analysts, bullish_count, bearish_count, neutral_count, date_recorded as date FROM analyst_sentiment_analysis ORDER BY date_recorded DESC LIMIT 1`
      );
      analyst = analystResult.rows[0] || null;
    } catch (e) {
      console.warn("analyst_sentiment_analysis not available:", e.message);
    }

    return res.json({
      success: true,
      data: {
        fear_greed: fearGreed,
        naaim: naaim,
        aaii: aaii,
        analyst: analyst,
        timestamp: new Date().toISOString()
      }
    });
  } catch (error) {
    console.error("Sentiment summary error:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch sentiment summary",
      timestamp: new Date().toISOString()
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
      SELECT symbol, date_recorded as date, total_analysts as total_analysts, bullish_count, bearish_count, neutral_count FROM analyst_sentiment_analysis
      ORDER BY date DESC
      LIMIT $1 OFFSET $2
    `;
    let countParams = [];
    let params = [limitNum, offset];

    if (symbol) {
      countQueryStr = `SELECT COUNT(*) as total FROM analyst_sentiment_analysis WHERE symbol = $1`;
      countParams = [symbol.toUpperCase()];
      queryStr = `
        SELECT symbol, date_recorded as date, total_analysts as total_analysts, bullish_count, bearish_count, neutral_count FROM analyst_sentiment_analysis
        WHERE symbol = $1
        ORDER BY date DESC
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
    return sendError(res, "Failed to fetch analyst sentiment data", 500);
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
        date as date,
        total_analysts as total_analysts,
        bullish_count,
        bearish_count,
        neutral_count
      FROM analyst_sentiment_analysis
      ORDER BY date DESC
      LIMIT $1
    `;

    try {
      const result = await query(queryStr, [daysNum]);
      return sendSuccess(res, {
        data: result.rows || [],
        period_days: daysNum});
    } catch (tableError) {
      // If analyst table doesn't exist, return empty history
      console.warn("Analyst sentiment table not available:", tableError.message);
      return sendSuccess(res, {
        data: [],
        period_days: daysNum,
        message: "Historical data not available"});
    }
  } catch (error) {
    console.error("Sentiment history error:", error);
    return sendError(res, "Failed to fetch sentiment history", 500);
  }
});

// GET /api/sentiment/current - Current market sentiment (fear/greed, NAAIM, AAII)
router.get("/current", async (req, res) => {
  try {
    // Try to fetch sentiment data from actual tables, handle gracefully if missing
    let fearGreed = null, naaim = null, aaii = null;

    try {
      const fearGreedResult = await query(
        `SELECT fear_greed_value as value, date FROM fear_greed_index ORDER BY date DESC LIMIT 1`
      );
      fearGreed = fearGreedResult.rows[0] || null;
    } catch (e) {
      console.warn("fear_greed_index table not available:", e.message);
    }

    try {
      const naaImResult = await query(
        `SELECT naaim_number_mean, bullish, bearish, date FROM naaim ORDER BY date DESC LIMIT 1`
      );
      naaim = naaImResult.rows[0] || null;
    } catch (e) {
      console.warn("naaim table not available:", e.message);
    }

    try {
      const aaiiResult = await query(
        `SELECT bullish, neutral, bearish, date FROM aaii_sentiment ORDER BY date DESC LIMIT 1`
      );
      aaii = aaiiResult.rows[0] || null;
    } catch (e) {
      console.warn("aaii_sentiment table not available:", e.message);
    }

    return res.json({
      data: {
        fear_greed: fearGreed,
        naaim: naaim,
        aaii: aaii,
        timestamp: new Date().toISOString()
      },
      success: true
    });
  } catch (error) {
    console.error("Current sentiment error:", error);
    return res.json({
      data: {
        fear_greed: null,
        naaim: null,
        aaii: null,
        timestamp: new Date().toISOString()
      },
      success: true
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
        total_analysts,
        bullish_count,
        bearish_count,
        neutral_count,
        ROUND((bullish_count::float / NULLIF(total_analysts, 0) * 100)::numeric, 2) as bull_percent,
        ROUND((bearish_count::float / NULLIF(total_analysts, 0) * 100)::numeric, 2) as bear_percent,
        ROUND((neutral_count::float / NULLIF(total_analysts, 0) * 100)::numeric, 2) as neutral_percent
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

    return sendSuccess(res, {
      items: result.rows || []});
  } catch (error) {
    console.error("Sentiment divergence error:", error);
    return sendError(res, "Failed to fetch sentiment divergence", 500);
  }
});

// GET /api/sentiment/social/insights/:symbol - Social sentiment insights for a specific symbol
router.get("/social/insights/:symbol", (req, res) => {
  const { symbol } = req.params;
  res.status(404).json({
    success: false,
    error: "Social sentiment data not available",
    symbol: symbol.toUpperCase()
  });
});

// GET /api/sentiment/analyst/insights/:symbol - Analyst sentiment insights for a specific symbol
router.get("/analyst/insights/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;

    // Try to fetch analyst data from database
    const result = await query(
      `SELECT
        symbol,
        date as date,
        total_analysts as total_analysts,
        bullish_count,
        bearish_count,
        neutral_count,
        target_price,
        current_price,
        upside_downside_percent
      FROM analyst_sentiment_analysis
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 1`,
      [symbol.toUpperCase()]
    );

    if (result.rows.length === 0) {
      return res.json({
        symbol: symbol.toUpperCase(),
        total_analysts: 0,
        bullish_count: 0,
        bearish_count: 0,
        neutral_count: 0,
        target_price: null,
        current_price: null,
        upside_downside_percent: null,
        message: "No analyst data available"
      });
    }

    const row = result.rows[0];
    const bullish_pct = row.total_analysts > 0 ? ((row.bullish_count / row.total_analysts) * 100).toFixed(2) : 0;
    const bearish_pct = row.total_analysts > 0 ? ((row.bearish_count / row.total_analysts) * 100).toFixed(2) : 0;
    const neutral_pct = row.total_analysts > 0 ? ((row.neutral_count / row.total_analysts) * 100).toFixed(2) : 0;

    // Determine consensus based on percentages
    let consensus = 'hold';
    if (bullish_pct > 50) consensus = 'buy';
    else if (bearish_pct > 50) consensus = 'sell';

    return res.json({
      symbol: row.symbol,
      date: row.date,
      total_analysts: row.total_analysts || 0,
      bullish_count: row.bullish_count || 0,
      bearish_count: row.bearish_count || 0,
      neutral_count: row.neutral_count || 0,
      bullish_percent: bullish_pct,
      bearish_percent: bearish_pct,
      neutral_percent: neutral_pct,
      target_price: row.target_price,
      current_price: row.current_price,
      upside_downside_percent: row.upside_downside_percent,
      consensus: consensus
    });
  } catch (error) {
    console.error("Analyst insights error:", error);
    return sendError(res, "Failed to fetch analyst insights", 500);
  }
});

// GET /api/sentiment/aaii - AAII sentiment (alias for /current)
router.get("/aaii", async (req, res) => {
  try {
    let aaii = null;

    try {
      const aaiiResult = await query(
        `SELECT bullish, neutral, bearish, date FROM aaii_sentiment ORDER BY date DESC LIMIT 1`
      );
      aaii = aaiiResult.rows[0] || null;
    } catch (e) {
      console.warn("aaii_sentiment table not available:", e.message);
    }

    return sendSuccess(res, {
      data: aaii,
      timestamp: new Date().toISOString()});
  } catch (error) {
    console.error("AAII sentiment error:", error);
    return sendSuccess(res, {
      data: null,
      timestamp: new Date().toISOString()});
  }
});

module.exports = router;
