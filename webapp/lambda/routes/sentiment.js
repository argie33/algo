const express = require("express");

const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const { validateQueryResult, validateAndCoerceRows, extractCount } = require('../utils/responseValidation');
const logger = require('../utils/logger');
const router = express.Router();

// GET /api/sentiment - Root endpoint
router.get("/", async (req, res) => {
  try {
    return sendSuccess(res, { message: "Sentiment API - use /summary, /data, /analyst for specific endpoints" });
  } catch (error) {
    return sendError(res, error.message, 500);
  }
});

// GET /api/sentiment/data - Get sentiment data (stocks with analyst sentiment)
router.get("/data", async (req, res) => {
  try {
    const { limit = "100", page = "1", symbol } = req.query;
    const limitNum = Math.min(parseInt(limit), 5000);
    const pageNum = Math.max(parseInt(page), 1);
    const offset = (pageNum - 1) * limitNum;

    // Query analyst sentiment analysis data which contains stock sentiment metrics
    let countQueryStr = `SELECT COUNT(*) as total FROM analyst_sentiment_analysis WHERE symbol IS NOT NULL`;
    let queryStr = `
      SELECT
        symbol,
        date,
        analyst_count,
        bullish_count,
        bearish_count,
        neutral_count
      FROM analyst_sentiment_analysis
      WHERE symbol IS NOT NULL
      ORDER BY date DESC, symbol ASC
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
          analyst_count as analyst_count,
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

    const [countResult, result] = await Promise.all([
      query(countQueryStr, countParams),
      query(queryStr, params)
    ]);
    validateQueryResult(countResult, { requireRows: false });
    validateQueryResult(result, { requireRows: false });
    const total = parseInt(countResult.rows[0]?.total || 0);

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
    // Parallelize 4 sentiment data sources
    const results = await Promise.allSettled([
      query(`SELECT fear_greed_value as value, date FROM fear_greed_index ORDER BY date DESC LIMIT 1`),
      query(`SELECT naaim_number_mean, bullish, bearish, date FROM naaim ORDER BY date DESC LIMIT 1`),
      query(`SELECT bullish, neutral, bearish, date FROM aaii_sentiment ORDER BY date DESC LIMIT 1`),
      query(`SELECT analyst_count as analyst_count, bullish_count, bearish_count, neutral_count, date as date FROM analyst_sentiment_analysis ORDER BY date DESC LIMIT 1`)
    ]);

    const [fearGreedRes, naaImRes, aaiiRes, analystRes] = results;

    const fearGreed = fearGreedRes.status === 'fulfilled' ? (fearGreedRes.value.rows[0] || null) : null;
    const naaim = naaImRes.status === 'fulfilled' ? (naaImRes.value.rows[0] || null) : null;
    const aaii = aaiiRes.status === 'fulfilled' ? (aaiiRes.value.rows[0] || null) : null;
    const analyst = analystRes.status === 'fulfilled' ? (analystRes.value.rows[0] || null) : null;

    if (fearGreedRes.status === 'rejected') console.warn("fear_greed_index not available:", fearGreedRes.reason?.message);
    if (naaImRes.status === 'rejected') console.warn("naaim not available:", naaImRes.reason?.message);
    if (aaiiRes.status === 'rejected') console.warn("aaii_sentiment not available:", aaiiRes.reason?.message);
    if (analystRes.status === 'rejected') console.warn("analyst_sentiment_analysis not available:", analystRes.reason?.message);

    const summary = {
      fear_greed: fearGreed,
      naaim: naaim,
      aaii: aaii,
      analyst: analyst
    };
    return sendSuccess(res, summary);
  } catch (error) {
    console.error("Sentiment summary error:", error);
    return sendError(res, "Failed to fetch sentiment summary", 500);
  }
});

// AAII endpoint removed - consolidated in market.js /aaii
// Use GET /api/market/aaii for AAII sentiment data instead

// GET /api/sentiment/analyst - Analyst sentiment
router.get("/analyst", async (req, res) => {
  try {
    const { symbol, limit = "50", page = "1" } = req.query;
    const limitNum = Math.min(parseInt(limit), 5000);
    const pageNum = Math.max(parseInt(page), 1);
    const offset = (pageNum - 1) * limitNum;

    let countQueryStr = `SELECT COUNT(*) as total FROM analyst_sentiment_analysis`;
    let queryStr = `
      SELECT symbol, date as date, analyst_count as analyst_count, bullish_count, bearish_count, neutral_count FROM analyst_sentiment_analysis
      ORDER BY date DESC
      LIMIT $1 OFFSET $2
    `;
    let countParams = [];
    let params = [limitNum, offset];

    if (symbol) {
      countQueryStr = `SELECT COUNT(*) as total FROM analyst_sentiment_analysis WHERE symbol = $1`;
      countParams = [symbol.toUpperCase()];
      queryStr = `
        SELECT symbol, date as date, analyst_count as analyst_count, bullish_count, bearish_count, neutral_count FROM analyst_sentiment_analysis
        WHERE symbol = $1
        ORDER BY date DESC
        LIMIT $2 OFFSET $3
      `;
      params = [symbol.toUpperCase(), limitNum, offset];
    }

    const countResult = await query(countQueryStr, countParams);
    validateQueryResult(countResult, { requireRows: false });
    const total = parseInt(countResult.rows[0]?.total || 0);
    const totalPages = Math.ceil(total / limitNum);

    const result = await query(queryStr, params);
    validateQueryResult(result, { requireRows: false });
    return sendPaginated(res, result.rows || [], {
      page: pageNum,
      limit: limitNum,
      total,
      totalPages,
      offset: offset
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
        analyst_count as analyst_count,
        bullish_count,
        bearish_count,
        neutral_count
      FROM analyst_sentiment_analysis
      ORDER BY date DESC
      LIMIT $1
    `;

    try {
      const result = await query(queryStr, [daysNum]);
      return sendSuccess(res, result.rows || []);
    } catch (tableError) {
      // If analyst table doesn't exist, return empty history
      console.warn("Analyst sentiment table not available:", tableError.message);
      return sendSuccess(res, []);
    }
  } catch (error) {
    console.error("Sentiment history error:", error);
    return sendError(res, "Failed to fetch sentiment history", 500);
  }
});

// GET /api/sentiment/current - Current market sentiment (fear/greed, NAAIM, AAII)
router.get("/current", async (req, res) => {
  try {
    // Parallelize 3 sentiment data sources
    const results = await Promise.allSettled([
      query(`SELECT fear_greed_value as value, date FROM fear_greed_index ORDER BY date DESC LIMIT 1`),
      query(`SELECT naaim_number_mean, bullish, bearish, date FROM naaim ORDER BY date DESC LIMIT 1`),
      query(`SELECT bullish, neutral, bearish, date FROM aaii_sentiment ORDER BY date DESC LIMIT 1`)
    ]);

    const [fearGreedRes, naaImRes, aaiiRes] = results;

    const fearGreed = fearGreedRes.status === 'fulfilled' ? (fearGreedRes.value.rows[0] || null) : null;
    const naaim = naaImRes.status === 'fulfilled' ? (naaImRes.value.rows[0] || null) : null;
    const aaii = aaiiRes.status === 'fulfilled' ? (aaiiRes.value.rows[0] || null) : null;

    if (fearGreedRes.status === 'rejected') console.warn("fear_greed_index table not available:", fearGreedRes.reason?.message);
    if (naaImRes.status === 'rejected') console.warn("naaim table not available:", naaImRes.reason?.message);
    if (aaiiRes.status === 'rejected') console.warn("aaii_sentiment table not available:", aaiiRes.reason?.message);

    const current = {
      fear_greed: fearGreed,
      naaim: naaim,
      aaii: aaii
    };
    return sendSuccess(res, current);
  } catch (error) {
    console.error("Current sentiment error:", error);
    return sendSuccess(res, {
      fear_greed: null,
      naaim: null,
      aaii: null
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
        date as date,
        analyst_count,
        bullish_count,
        bearish_count,
        neutral_count,
        ROUND((bullish_count::float / NULLIF(analyst_count, 0) * 100)::numeric, 2) as bull_percent,
        ROUND((bearish_count::float / NULLIF(analyst_count, 0) * 100)::numeric, 2) as bear_percent,
        ROUND((neutral_count::float / NULLIF(analyst_count, 0) * 100)::numeric, 2) as neutral_percent
      FROM analyst_sentiment_analysis
      WHERE date >= NOW() - INTERVAL '90 days'
    `;

    const params = [];

    if (symbol) {
      queryStr += ` AND symbol = $1`;
      params.push(symbol.toUpperCase());
    }

    queryStr += ` ORDER BY date DESC LIMIT 10000`;

    const result = await query(queryStr, params);

    return sendSuccess(res, result.rows || []);
  } catch (error) {
    console.error("Sentiment divergence error:", error);
    return sendError(res, "Failed to fetch sentiment divergence", 500);
  }
});

// GET /api/sentiment/social/insights/:symbol - Social sentiment insights for a specific symbol
router.get("/social/insights/:symbol", (req, res) => {
  const { symbol } = req.params;
  return sendError(res, "Social sentiment data not available", 404);
});

// GET /api/sentiment/aaii - AAII sentiment (alias for /current)
router.get("/aaii", async (req, res) => {
  try {
    let aaii = null;

    try {
      const aaiiResult = await query(`SELECT bullish, neutral, bearish, date FROM aaii_sentiment ORDER BY date DESC LIMIT 1`);
      aaii = aaiiResult.rows[0] || null;
    } catch (e) {
      console.warn("aaii_sentiment table not available:", e.message);
    }

    return sendSuccess(res, aaii);
  } catch (error) {
    console.error("AAII sentiment error:", error);
    return sendSuccess(res, null);
  }
});

// GET /api/sentiment/analyst/insights/:symbol - Symbol-specific analyst insights
router.get("/analyst/insights/:symbol", async (req, res) => {
  const symbol = req.params.symbol.toUpperCase();
  try {
    const [sentimentResult, upgradeResult, momentumResult] = await Promise.all([
      query(
        `SELECT analyst_count, bullish_count, bearish_count, neutral_count
         FROM analyst_sentiment_analysis
         WHERE symbol = $1
         ORDER BY date DESC LIMIT 1`,
        [symbol]
      ),
      query(
        `SELECT firm, action, old_rating AS from_grade, new_rating AS to_grade, action_date AS date, company_name AS details
         FROM analyst_upgrade_downgrade
         WHERE symbol = $1
         ORDER BY action_date DESC LIMIT 20`,
        [symbol]
      ),
      query(
        `SELECT
           COUNT(*) FILTER (WHERE action = 'up' AND action_date >= CURRENT_DATE - INTERVAL '30 days') AS upgrades30d,
           COUNT(*) FILTER (WHERE action = 'down' AND action_date >= CURRENT_DATE - INTERVAL '30 days') AS downgrades30d
         FROM analyst_upgrade_downgrade
         WHERE symbol = $1`,
        [symbol]
      )
    ]);
    validateQueryResult(sentimentResult, { requireRows: false });
    validateQueryResult(upgradeResult, { requireRows: false });
    validateQueryResult(momentumResult, { requireRows: false });

    const row = sentimentResult.rows[0] || null;
    const total = row ? (parseInt(row.analyst_count) || 0) : 0;
    const bullish = row ? (parseInt(row.bullish_count) || 0) : 0;
    const bearish = row ? (parseInt(row.bearish_count) || 0) : 0;
    const neutral = row ? (parseInt(row.neutral_count) || 0) : 0;
    const pct = (n) => total > 0 ? Math.round((n / total) * 100) : 0;

    const momentumRow = momentumResult.rows[0] || {};

    return sendSuccess(res, {
      metrics: row ? {
        bullish,
        neutral,
        bearish,
        bullishPercent: pct(bullish),
        neutralPercent: pct(neutral),
        bearishPercent: pct(bearish),
        totalAnalysts: total,
        avgPriceTarget: null,
        priceTargetVsCurrent: null
      } : null,
      momentum: {
        upgrades30d: parseInt(momentumRow.upgrades30d) || 0,
        downgrades30d: parseInt(momentumRow.downgrades30d) || 0
      },
      priceTargets: [],
      coverage: null,
      recentUpgrades: upgradeResult.rows || []
    });
  } catch (error) {
    console.error("Analyst insights error:", error);
    return sendError(res, "Failed to fetch analyst insights", 500);
  }
});

module.exports = router;
