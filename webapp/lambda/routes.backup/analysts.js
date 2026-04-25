const express = require("express");

const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');

const router = express.Router();

// Root endpoint - returns available sub-endpoints
router.get("/", (req, res) => {
  return sendSuccess(res, {
    endpoint: "analysts",
    available_routes: [
      "/upgrades - Analyst upgrades and downgrades",
      "/sentiment - Analyst sentiment summary",
      "/by-symbol/:symbol - Analyst data for a specific stock"
    ]
  });
});

// GET /api/analysts/upgrades - Get analyst upgrades and downgrades
router.get("/upgrades", async (req, res) => {
  try {
    const { limit = "100", page = "1", symbol } = req.query;
    const limitNum = Math.min(parseInt(limit), 500);
    const pageNum = Math.max(parseInt(page), 1);
    const offset = (pageNum - 1) * limitNum;

    // Build query based on filters - include company names
    let countQueryStr = `SELECT COUNT(*) as total FROM analyst_upgrade_downgrade WHERE symbol IS NOT NULL`;
    let queryStr = `
      SELECT
        aud.*,
        COALESCE(cp.short_name, cp.long_name) as company_name
      FROM analyst_upgrade_downgrade aud
      LEFT JOIN company_profile cp ON aud.symbol = cp.ticker
      WHERE aud.symbol IS NOT NULL
      ORDER BY aud.action_date DESC
      LIMIT $1 OFFSET $2
    `;
    let countParams = [];
    let params = [limitNum, offset];

    // Filter by symbol if provided
    if (symbol) {
      countQueryStr = `SELECT COUNT(*) as total FROM analyst_upgrade_downgrade WHERE symbol = $1`;
      countParams = [symbol.toUpperCase()];
      queryStr = `
        SELECT
          aud.*,
          COALESCE(cp.short_name, cp.long_name) as company_name
        FROM analyst_upgrade_downgrade aud
        LEFT JOIN company_profile cp ON aud.symbol = cp.ticker
        WHERE aud.symbol = $1
        ORDER BY aud.action_date DESC
        LIMIT $2 OFFSET $3
      `;
      params = [symbol.toUpperCase(), limitNum, offset];
    }

    const countResult = await query(countQueryStr, countParams);
    const total = parseInt(countResult.rows[0]?.total || 0);
    const totalPages = Math.ceil(total / limitNum);

    const result = await query(queryStr, params);

    return sendPaginated(res, result.rows || [], {
      page: pageNum,
      limit: limitNum,
      total,
      totalPages,
      hasNext: pageNum < totalPages,
      hasPrev: pageNum > 1
    });
  } catch (error) {
    console.error("Analyst upgrades error:", error.message);
    return sendError(res, "Failed to fetch analyst upgrades: " + error.message, 500);
  }
});

// GET /api/analysts/sentiment - Analyst sentiment summary
router.get("/sentiment", async (req, res) => {
  try {
    const { limit = "100", page = "1" } = req.query;
    const limitNum = Math.min(parseInt(limit), 500);
    const pageNum = Math.max(parseInt(page), 1);
    const offset = (pageNum - 1) * limitNum;

    const countQueryStr = `SELECT COUNT(*) as total FROM analyst_sentiment_analysis WHERE symbol IS NOT NULL`;
    const queryStr = `
      SELECT *
      FROM analyst_sentiment_analysis
      WHERE symbol IS NOT NULL
      ORDER BY date DESC
      LIMIT $1 OFFSET $2
    `;

    const countResult = await query(countQueryStr, []);
    const total = parseInt(countResult.rows[0]?.total || 0);
    const totalPages = Math.ceil(total / limitNum);

    const result = await query(queryStr, [limitNum, offset]);

    return sendPaginated(res, result.rows || [], {
      page: pageNum,
      limit: limitNum,
      total,
      totalPages,
      hasNext: pageNum < totalPages,
      hasPrev: pageNum > 1
    });
  } catch (error) {
    console.error("Analyst sentiment error:", error.message);
    return sendError(res, "Failed to fetch analyst sentiment data", 500);
  }
});

// GET /api/analysts/by-symbol/:symbol - Analyst data for specific stock
router.get("/by-symbol/:symbol", async (req, res) => {
  try {
    const symbol = req.params.symbol.toUpperCase();
    const { limit = "50" } = req.query;
    const limitNum = Math.min(parseInt(limit), 500);

    // Get recent upgrades/downgrades
    const upgradesQuery = `
      SELECT *
      FROM analyst_upgrade_downgrade
      WHERE symbol = $1
      ORDER BY action_date DESC
      LIMIT $2
    `;

    // Get analyst sentiment for this symbol
    const sentimentQuery = `
      SELECT *
      FROM analyst_sentiment_analysis
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 1
    `;

    const [upgradesResult, sentimentResult] = await Promise.all([
      query(upgradesQuery, [symbol, limitNum]),
      query(sentimentQuery, [symbol])
    ]);

    return sendSuccess(res, {
      symbol,
      upgrades: upgradesResult.rows || [],
      sentiment: sentimentResult.rows[0] || null
    });
  } catch (error) {
    console.error("Analyst data error:", error.message);
    return sendError(res, "Failed to fetch analyst data", 500);
  }
});

// Alias: /list -> /upgrades for backward compatibility
router.get("/list", (req, res) => {
  res.redirect(301, '/api/analysts/upgrades');
});

// Alias: /:symbol -> /by-symbol/:symbol (redirect to actual endpoint)
router.get("/:symbol", (req, res) => {
  res.redirect(301, `/api/analysts/by-symbol/${req.params.symbol}`);
});

module.exports = router;
