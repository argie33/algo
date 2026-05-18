const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require("../utils/apiResponse");
const router = express.Router();

// GET / - Get stock scores with optional filters
router.get("/", async (req, res) => {
  try {
    const { limit = 50, page = 1, symbol, sort = "composite_score", sort_order = "DESC" } = req.query;
    const limitNum = Math.min(parseInt(limit) || 50, 1000);
    const pageNum = Math.max(parseInt(page) || 1, 1);
    const offset = (pageNum - 1) * limitNum;

    // Build WHERE clause
    let whereClause = "";
    const params = [];

    if (symbol) {
      whereClause = "WHERE symbol = $1";
      params.push(symbol.toUpperCase());
    }

    // Validate sort field
    const validSortFields = ["composite_score", "momentum_score", "value_score", "quality_score", "growth_score", "stability_score", "symbol"];
    const sortField = validSortFields.includes(sort) ? sort : "composite_score";
    const sortDir = ["ASC", "DESC"].includes((sort_order || "DESC").toUpperCase()) ? sort_order.toUpperCase() : "DESC";

    // Get total count
    const countResult = await query(
      `SELECT COUNT(*) as total FROM stock_scores ${whereClause}`,
      params
    );
    const total = parseInt(countResult?.rows[0]?.total || 0);

    // Get paginated results
    const paramIndex = params.length + 1;
    const resultObj = await query(`
      SELECT
        symbol,
        composite_score,
        momentum_score,
        value_score,
        quality_score,
        growth_score,
        stability_score
      FROM stock_scores
      ${whereClause}
      ORDER BY ${sortField} ${sortDir}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `, [...params, limitNum, offset]);

    const scores = resultObj?.rows || [];
    const totalPages = Math.ceil(total / limitNum);

    return sendPaginated(res, scores, {
      page: pageNum,
      limit: limitNum,
      total,
      totalPages,
      hasNext: pageNum < totalPages,
      hasPrev: pageNum > 1
    });
  } catch (error) {
    console.error("Error fetching scores:", error.message);
    return sendError(res, `Failed to fetch scores: ${error.message.substring(0, 100)}`, 500);
  }
});

// GET /stockscores - Alias endpoint with support for alternative parameter names (sortBy, sp500Only)
router.get("/stockscores", async (req, res) => {
  try {
    const {
      limit = 50,
      page = 1,
      offset,
      symbol,
      sort = "composite_score",
      sortBy = sort,
      sort_order = "DESC",
      sortOrder = sort_order,
      sp500Only = false
    } = req.query;

    const limitNum = Math.min(parseInt(limit) || 50, 5000);
    const pageNum = offset ? Math.max(parseInt(offset) / limitNum + 1, 1) : Math.max(parseInt(page) || 1, 1);
    const offsetNum = offset ? Math.max(parseInt(offset), 0) : (pageNum - 1) * limitNum;

    // Build WHERE clause
    let whereClause = "";
    const params = [];

    if (symbol) {
      whereClause = "WHERE symbol = $1";
      params.push(symbol.toUpperCase());
    }

    // Validate sort field (supports both sortBy and sort parameter names)
    const validSortFields = ["composite_score", "momentum_score", "value_score", "quality_score", "growth_score", "stability_score", "symbol"];
    const sortField = validSortFields.includes(sortBy) ? sortBy : validSortFields.includes(sort) ? sort : "composite_score";
    const sortDir = ["ASC", "DESC"].includes((sortOrder || sort_order || "DESC").toUpperCase()) ? (sortOrder || sort_order).toUpperCase() : "DESC";

    // Get total count
    const countResult = await query(
      `SELECT COUNT(*) as total FROM stock_scores ${whereClause}`,
      params
    );
    const total = parseInt(countResult?.rows[0]?.total || 0);

    // Get paginated results
    const paramIndex = params.length + 1;
    const resultObj = await query(`
      SELECT
        symbol,
        composite_score,
        momentum_score,
        value_score,
        quality_score,
        growth_score,
        stability_score
      FROM stock_scores
      ${whereClause}
      ORDER BY ${sortField} ${sortDir}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `, [...params, limitNum, offsetNum]);

    const scores = resultObj?.rows || [];
    const totalPages = Math.ceil(total / limitNum);

    return sendPaginated(res, scores, {
      page: pageNum,
      limit: limitNum,
      total,
      totalPages,
      offset: offsetNum,
      hasNext: pageNum < totalPages,
      hasPrev: pageNum > 1
    });
  } catch (error) {
    console.error("Error fetching stockscores:", error.message);
    return sendError(res, `Failed to fetch scores: ${error.message.substring(0, 100)}`, 500);
  }
});

// GET /:symbol - Get score for specific symbol
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;

    const result = await query(
      `SELECT * FROM stock_scores WHERE symbol = $1`,
      [symbol.toUpperCase()]
    );

    if (!result?.rows || result.rows.length === 0) {
      return sendError(res, `No scores found for symbol ${symbol}`, 404);
    }

    return sendSuccess(res, result.rows[0]);
  } catch (error) {
    console.error("Error fetching score:", error.message);
    return sendError(res, `Failed to fetch score: ${error.message}`, 500);
  }
});

module.exports = router;
