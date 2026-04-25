const express = require("express");
const { query } = require("../utils/database");

const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const router = express.Router();

// Helper function to fetch stocks list
async function fetchStocksList(req, res) {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 1000);
    const offset = parseInt(req.query.offset) || 0;

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
    console.error("Error fetching stocks:", error);
    return sendError(res, `Failed to fetch stocks: ${error.message}`, 500);
  }
}

// GET /api/stocks - List all stocks
router.get("/", fetchStocksList);

// GET /api/stocks/search - Search stocks by symbol or name
router.get("/search", async (req, res) => {
  try {
    const q = req.query.q || req.query.symbol || '';
    const limit = Math.min(parseInt(req.query.limit) || 100, 1000);
    const offset = parseInt(req.query.offset) || 0;

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
    console.error("Error searching stocks:", error);
    return sendError(res, `Failed to search stocks: ${error.message}`, 500);
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
    console.error("Error fetching deep value stocks:", error);
    return sendError(res, `Failed to fetch deep value stocks: ${error.message}`, 500);
  }
});

// GET /api/stocks/quick/overview - Quick stock overview (limited data)
router.get("/quick/overview", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 100, 500);
    const offset = parseInt(req.query.offset) || 0;
    const search = req.query.search || '';

    let countSql = "SELECT COUNT(*) as total FROM stock_symbols WHERE 1=1";
    let sql = "SELECT symbol, security_name as name, market_category as category, exchange FROM stock_symbols WHERE 1=1";
    const params = [];
    let paramIndex = 1;

    if (search) {
      params.push(`%${search.toUpperCase()}%`);
      countSql += ` AND (symbol ILIKE $${paramIndex} OR security_name ILIKE $${paramIndex})`;
      sql += ` AND (symbol ILIKE $${paramIndex} OR security_name ILIKE $${paramIndex})`;
      paramIndex++;
    }

    const countResult = await query(countSql, params);
    const total = parseInt(countResult.rows[0]?.total || 0);

    params.push(limit, offset);
    const result = await query(
      sql + ` ORDER BY symbol ASC LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`,
      params
    );

    return sendPaginated(res, result.rows, {
      limit,
      offset,
      total,
      page: Math.max(1, Math.ceil((offset / limit) + 1))
    });
  } catch (error) {
    console.error("Error fetching quick overview:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch quick overview",
      message: error.message
    });
  }
});

// GET /api/stocks/full/data - Full stock data with detailed metrics
router.get("/full/data", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 50, 100);
    const offset = parseInt(req.query.offset) || 0;
    const search = req.query.search || '';

    let countSql = "SELECT COUNT(*) as total FROM stock_symbols WHERE 1=1";
    let sql = `
      SELECT
        ss.symbol,
        ss.security_name as name,
        ss.market_category as category,
        ss.exchange,
        COALESCE(vm.pe_ratio, 0) as valuation,
        COALESCE(gm.revenue_growth_yoy, 0) as growth,
        COALESCE(mm.momentum_1m, 0) as momentum
      FROM stock_symbols ss
      LEFT JOIN value_metrics vm ON ss.symbol = vm.symbol
      LEFT JOIN growth_metrics gm ON ss.symbol = gm.symbol
      LEFT JOIN momentum_metrics mm ON ss.symbol = mm.symbol
      WHERE 1=1
    `;
    const params = [];
    let paramIndex = 1;

    if (search) {
      params.push(`%${search.toUpperCase()}%`);
      countSql += ` AND (symbol ILIKE $${paramIndex} OR security_name ILIKE $${paramIndex})`;
      sql += ` AND (ss.symbol ILIKE $${paramIndex} OR ss.security_name ILIKE $${paramIndex})`;
      paramIndex++;
    }

    const countResult = await query(countSql, params);
    const total = parseInt(countResult.rows[0]?.total || 0);

    params.push(limit, offset);
    const result = await query(
      sql + ` ORDER BY ss.symbol ASC LIMIT $${paramIndex} OFFSET $${paramIndex + 1}`,
      params
    );

    return sendPaginated(res, result.rows, {
      limit,
      offset,
      total,
      page: Math.max(1, Math.ceil((offset / limit) + 1))
    });
  } catch (error) {
    console.error("Error fetching full data:", error);
    return res.status(500).json({
      success: false,
      error: "Failed to fetch full data",
      message: error.message
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
      return res.status(404).json({
        success: false,
        error: "Stock not found"
      });
    }

    res.json({
      success: true,
      data: result.rows[0]
    });
  } catch (error) {
    console.error("Error fetching stock:", error);
    res.status(500).json({
      success: false,
      error: "Failed to fetch stock",
      message: error.message
    });
  }
});

module.exports = router;
