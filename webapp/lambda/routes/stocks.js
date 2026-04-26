const express = require("express");

const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const router = express.Router();

// Helper function to fetch stocks list
async function fetchStocksList(req, res) {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 1000);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    const result = await query(
      "SELECT symbol, security_name as name, market_category as category, exchange FROM stock_symbols ORDER BY symbol LIMIT $1 OFFSET $2",
      [limit, offset]
    );

    const countResult = await query("SELECT COUNT(*) as total FROM stock_symbols");
    const total = parseInt(countResult.rows[0].total);

    return sendPaginated(res, result.rows, {
      limit,
      offset,
      total,
      page: Math.max(1, Math.ceil((offset / limit) + 1))
    });
  } catch (error) {
    const errorMsg = error && typeof error === 'object' ? (error.message || String(error)) : String(error);
    console.error("❌ Error fetching stocks:", errorMsg);
    return sendError(res, `Failed to fetch stocks: ${errorMsg}`, 500);
  }
}

// GET /api/stocks - List all stocks
router.get("/", fetchStocksList);

// GET /api/stocks/search - Search stocks by symbol or name
router.get("/search", async (req, res) => {
  try {
    const q = req.query.q || req.query.symbol || '';
    const limit = Math.min(parseInt(req.query.limit) || 100, 1000);
    const page = Math.max(1, parseInt(req.query.page) || 1);
    const offset = (page - 1) * limit;

    if (!q) {
      return sendPaginated(res, [], { limit, offset, total: 0, page: 1 });
    }

    const searchTerm = `%${q.toUpperCase()}%`;
    const result = await query(
      "SELECT symbol, security_name as name, market_category as category, exchange FROM stock_symbols WHERE symbol ILIKE $1 OR security_name ILIKE $1 ORDER BY symbol LIMIT $2 OFFSET $3",
      [searchTerm, limit, offset]
    );

    const countResult = await query(
      "SELECT COUNT(*) as total FROM stock_symbols WHERE symbol ILIKE $1 OR security_name ILIKE $1",
      [searchTerm]
    );
    const total = parseInt(countResult.rows[0].total);

    return sendPaginated(res, result.rows, {
      limit,
      offset,
      total,
      page: Math.max(1, Math.ceil((offset / limit) + 1))
    });
  } catch (error) {
    const errorMsg = error && typeof error === 'object' ? (error.message || String(error)) : String(error);
    console.error("❌ Error searching stocks:", errorMsg);
    return sendError(res, `Failed to search stocks: ${errorMsg}`, 500);
  }
});

// GET /api/stocks/gainers - Top gaining stocks
router.get("/gainers", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 20, 100);
    const result = await query(
      `SELECT symbol, security_name as name, market_category as category, exchange
       FROM stock_symbols
       ORDER BY symbol ASC
       LIMIT $1`,
      [limit]
    );
    return sendPaginated(res, result.rows || [], {
      limit,
      offset: 0,
      total: result.rows?.length || 0,
      page: 1
    });
  } catch (error) {
    console.error("Error fetching gainers:", error.message);
    return sendError(res, `Failed to fetch gainers: ${error.message}`, 500);
  }
});

// GET /api/stocks/deep-value - Get deep value stock picks (high value, low composite)
router.get("/deep-value", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 500, 5000);
    const offset = parseInt(req.query.offset) || 0;

    // Deep value = high value score + low composite score (undervalued)
    // Also include other quality metrics
    const result = await query(
      `SELECT
        ss.symbol,
        ss.security_name,
        ss.market_category,
        ss.exchange,
        ROUND(CAST(sc.composite_score AS NUMERIC), 2) as composite_score,
        ROUND(CAST(sc.value_score AS NUMERIC), 2) as value_score,
        ROUND(CAST(sc.quality_score AS NUMERIC), 2) as quality_score,
        ROUND(CAST(sc.growth_score AS NUMERIC), 2) as growth_score,
        ROUND(CAST(sc.momentum_score AS NUMERIC), 2) as momentum_score,
        ROUND(CAST(sc.stability_score AS NUMERIC), 2) as stability_score,
        ROUND(CAST(sc.positioning_score AS NUMERIC), 2) as positioning_score,
        sc.created_at as last_updated
      FROM stock_scores sc
      JOIN stock_symbols ss ON ss.symbol = sc.symbol
      WHERE sc.composite_score IS NOT NULL
        AND sc.value_score IS NOT NULL
      ORDER BY
        (COALESCE(sc.value_score, 0) - COALESCE(sc.composite_score, 0)) DESC,
        sc.value_score DESC,
        sc.composite_score ASC
      LIMIT $1 OFFSET $2`,
      [limit, offset]
    );

    const countResult = await query(
      "SELECT COUNT(*) as total FROM stock_scores WHERE composite_score IS NOT NULL AND value_score IS NOT NULL"
    );
    const total = parseInt(countResult.rows[0].total);

    // Use standard pagination format like all other list endpoints
    return sendPaginated(res, result.rows, {
      limit,
      offset,
      total,
      page: Math.ceil((offset / limit) + 1),
      totalPages: Math.ceil(total / limit),
      hasNext: (offset + limit) < total,
      hasPrev: offset > 0
    });
  } catch (error) {
    console.error("❌ Error fetching deep value stocks:", {
      message: error.message,
      code: error.code,
      tables: ['stock_scores', 'stock_symbols'],
      possibleCauses: [
        'Tables not yet created',
        'No data in stock_scores table',
        'Missing stock symbol references'
      ]
    });
    const userMessage = error.code === '42P01'
      ? 'Stock scores data not yet available - please check database setup'
      : `Failed to fetch deep value stocks: ${error.message}`;
    return sendError(res, userMessage, 500, {
      code: error.code,
      tables: ['stock_scores', 'stock_symbols'],
      possibleCauses: ['Tables not yet created', 'No data populated']
    });
  }
});

// GET /api/stocks/:symbol - Get specific stock
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;

    const result = await query(
      "SELECT symbol, security_name as name, market_category as category, exchange FROM stock_symbols WHERE symbol = $1",
      [symbol.toUpperCase()]
    );

    if (result.rows.length === 0) {
      return sendError(res, "Stock not found", 404);
    }

    return sendSuccess(res, result.rows[0]);
  } catch (error) {
    console.error("Error fetching stock:", error);
    return sendError(res, error.message, 500);
  }
});

module.exports = router;
