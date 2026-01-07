const express = require("express");

const { query } = require("../utils/database");

const router = express.Router();

// Root endpoint - returns available sub-endpoints
router.get("/", (req, res) => {
  return res.json({
    data: {
      endpoint: "analysts",
      available_routes: [
        "/upgrades - Analyst upgrades and downgrades",
        "/sentiment - Analyst sentiment summary",
        "/by-symbol/:symbol - Analyst data for a specific stock"
      ]
    },
    success: true
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
      ORDER BY aud.date DESC
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
        ORDER BY aud.date DESC
        LIMIT $2 OFFSET $3
      `;
      params = [symbol.toUpperCase(), limitNum, offset];
    }

    const countResult = await query(countQueryStr, countParams);
    const total = parseInt(countResult.rows[0]?.total || 0);
    const totalPages = Math.ceil(total / limitNum);

    const result = await query(queryStr, params);

    return res.json({
      data: result.rows || [],
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
    console.error("Analyst upgrades error:", error.message);
    return res.status(500).json({
      error: "Failed to fetch analyst upgrades",
      details: error.message,
      success: false
    });
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

    return res.json({
      data: result.rows || [],
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
    console.error("Analyst sentiment error:", error.message);
    return res.status(500).json({
      error: "Failed to fetch analyst sentiment data",
      success: false
    });
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
      ORDER BY date DESC
      LIMIT $2
    `;

    // Get analyst sentiment for this symbol
    const sentimentQuery = `
      SELECT *
      FROM analyst_sentiment_analysis
      WHERE symbol = $1
      ORDER BY date_recorded DESC
      LIMIT 1
    `;

    const [upgradesResult, sentimentResult] = await Promise.all([
      query(upgradesQuery, [symbol, limitNum]),
      query(sentimentQuery, [symbol])
    ]);

    return res.json({
      data: {
        symbol,
        upgrades: upgradesResult.rows || [],
        sentiment: sentimentResult.rows[0] || null
      },
      success: true
    });
  } catch (error) {
    console.error("Analyst data error:", error.message);
    return res.status(500).json({
      error: "Failed to fetch analyst data",
      success: false
    });
  }
});

module.exports = router;
