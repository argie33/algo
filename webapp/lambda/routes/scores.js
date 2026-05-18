const express = require("express");
const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require("../utils/apiResponse");
const logger = require('../utils/logger');
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

// GET /stockscores - Per API_CONTRACT.md: Returns swing scores with price + market cap data
// FIXED: Now returns correct fields (swing_score, grade, trend_score, date, price, change_pct, market_cap)
router.get("/stockscores", async (req, res) => {
  try {
    const {
      limit = 50,
      page = 1,
      offset,
      symbol,
      sort = "score",
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
      whereClause = "WHERE s.symbol = $1";
      params.push(symbol.toUpperCase());
    }

    // Validate sort field (supports score, symbol, or price)
    const validSortFields = ["score", "symbol", "swing_score"];
    const sortField = validSortFields.includes(sortBy) ? sortBy : validSortFields.includes(sort) ? sort : "score";
    const sortDir = ["ASC", "DESC"].includes((sortOrder || sort_order || "DESC").toUpperCase()) ? (sortOrder || sort_order).toUpperCase() : "DESC";

    // Get total count
    const countResult = await query(
      `SELECT COUNT(*) as total FROM swing_trader_scores s ${whereClause}`,
      params
    );
    const total = parseInt(countResult?.rows[0]?.total || 0);

    // Get paginated results - Join with latest prices and company profile
    const paramIndex = params.length + 1;
    const resultObj = await query(`
      SELECT
        s.symbol,
        s.score as swing_score,
        s.score,
        s.date,
        s.components,
        pd.close as price,
        pd.high,
        pd.low,
        pd.volume,
        ROUND(((pd.close - pd.open) / pd.open * 100)::numeric, 2) as change_pct,
        cp.market_cap,
        cp.display_name as company_name,
        cp.sector,
        cp.industry
      FROM swing_trader_scores s
      LEFT JOIN price_daily pd ON s.symbol = pd.symbol AND pd.date = (SELECT MAX(date) FROM price_daily WHERE symbol = s.symbol)
      LEFT JOIN company_profile cp ON s.symbol = cp.symbol
      ${whereClause}
      ORDER BY s.${sortField === 'score' || sortField === 'swing_score' ? 'score' : sortField} ${sortDir}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `, [...params, limitNum, offsetNum]);

    const scores = (resultObj?.rows || []).map(row => {
      const score = parseFloat(row.swing_score || 0);
      let grade = 'F';
      if (score >= 80) grade = 'A+';
      else if (score >= 75) grade = 'A';
      else if (score >= 70) grade = 'B';
      else if (score >= 60) grade = 'C';
      else if (score >= 50) grade = 'D';

      return {
        symbol: row.symbol,
        swing_score: score,
        grade: grade,
        trend_score: score, // Computed as equal to swing_score (can be refined later)
        date: row.date,
        price: parseFloat(row.price || 0),
        change_pct: parseFloat(row.change_pct || 0),
        market_cap: row.market_cap,
        company_name: row.company_name,
        sector: row.sector,
        industry: row.industry,
        components: row.components ? (typeof row.components === 'string' ? JSON.parse(row.components) : row.components) : {}
      };
    });

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
