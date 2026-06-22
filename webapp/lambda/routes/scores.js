const express = require("express");

const { query } = require("../utils/database");
const {
  sendSuccess,
  sendError,
  sendPaginated,
} = require("../utils/apiResponse");
const {
  validateQueryResult,
  validateAndCoerceRows,
  extractCount,
} = require("../utils/responseValidation");
const logger = require("../utils/logger");
const router = express.Router();

// GET / - Get stock scores with optional filters
router.get("/", async (req, res) => {
  try {
    const {
      limit = 50,
      page = 1,
      symbol,
      sort = "composite_score",
      sort_order = "DESC",
    } = req.query;
    const limitNum = Math.min(parseInt(limit) || 50, 1000);
    const pageNum = Math.max(parseInt(page) || 1, 1);
    const offset = (pageNum - 1) * limitNum;

    // Build WHERE clause
    let whereClause = "WHERE (sy.etf IS NULL OR sy.etf != 'Y')";
    const params = [];

    if (symbol) {
      whereClause += " AND ss.symbol = $1";
      params.push(symbol.toUpperCase());
    }

    // Validate sort field
    const validSortFields = [
      "composite_score",
      "momentum_score",
      "value_score",
      "quality_score",
      "growth_score",
      "stability_score",
      "symbol",
    ];
    const sortField = validSortFields.includes(sort) ? sort : "composite_score";
    const sortDir = ["ASC", "DESC"].includes(
      (sort_order || "DESC").toUpperCase()
    )
      ? sort_order.toUpperCase()
      : "DESC";

    // Get total count
    const countResult = await query(
      `SELECT COUNT(*) as total FROM stock_scores ss LEFT JOIN stock_symbols sy ON sy.symbol = ss.symbol ${whereClause}`,
      params
    );
    validateQueryResult(countResult, { requireRows: false });
    const total = parseInt(countResult?.rows[0]?.total || 0);

    // Get paginated results
    const paramIndex = params.length + 1;
    const resultObj = await query(
      `
      SELECT
        ss.symbol,
        ss.composite_score,
        ss.momentum_score,
        ss.value_score,
        ss.quality_score,
        ss.growth_score,
        ss.stability_score
      FROM stock_scores ss
      LEFT JOIN stock_symbols sy ON sy.symbol = ss.symbol
      ${whereClause}
      ORDER BY ss.${sortField} ${sortDir}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `,
      [...params, limitNum, offset]
    );
    validateQueryResult(resultObj, { requireRows: false });

    const scores = resultObj?.rows || [];
    const totalPages = Math.ceil(total / limitNum);

    return sendPaginated(res, scores, {
      page: pageNum,
      limit: limitNum,
      total,
      totalPages,
      hasNext: pageNum < totalPages,
      hasPrev: pageNum > 1,
    });
  } catch (error) {
    console.error("Error fetching scores:", error.message);
    return sendError(
      res,
      `Failed to fetch scores: ${error.message.substring(0, 100)}`,
      500
    );
  }
});

// GET /stockscores - Returns composite stock scores with multi-factor rankings
router.get("/stockscores", async (req, res) => {
  try {
    const {
      limit = 50,
      page = 1,
      offset,
      symbol,
      sortBy = "composite_score",
      sortOrder = "DESC",
      sp500Only = false,
    } = req.query;

    const limitNum = Math.min(parseInt(limit) || 50, 5000);
    const pageNum = offset
      ? Math.max(parseInt(offset) / limitNum + 1, 1)
      : Math.max(parseInt(page) || 1, 1);
    const offsetNum = offset
      ? Math.max(parseInt(offset), 0)
      : (pageNum - 1) * limitNum;

    // Build WHERE clause - only show stocks with good data coverage, exclude ETFs
    let whereClause =
      "WHERE sc.composite_score > 0 AND (ss.etf IS NULL OR ss.etf != 'Y')";
    const params = [];

    if (symbol) {
      whereClause += " AND sc.symbol = $" + (params.length + 1);
      params.push(symbol.toUpperCase());
    }

    // Validate sort field
    const validSortFields = [
      "composite_score",
      "momentum_score",
      "quality_score",
      "value_score",
      "growth_score",
      "positioning_score",
      "stability_score",
      "symbol",
    ];
    const sortField = validSortFields.includes(sortBy)
      ? sortBy
      : "composite_score";
    const sortDir = ["ASC", "DESC"].includes(
      (sortOrder || "DESC").toUpperCase()
    )
      ? sortOrder.toUpperCase()
      : "DESC";

    // Get total count
    const countResult = await query(
      `SELECT COUNT(*) as total FROM stock_scores sc LEFT JOIN stock_symbols ss ON ss.symbol = sc.symbol ${whereClause}`,
      params
    );
    validateQueryResult(countResult, { requireRows: false });
    const total = parseInt(countResult?.rows[0]?.total || 0);

    // Get paginated results - Optimized: removed slow price_daily join with window function
    const paramIndex = params.length + 1;
    const resultObj = await query(
      `
      SELECT
        sc.symbol,
        ss.security_name as company_name,
        cp.sector,
        cp.industry,
        sc.composite_score,
        sc.momentum_score,
        sc.quality_score,
        sc.value_score,
        sc.growth_score,
        sc.positioning_score,
        sc.stability_score,
        NULL::numeric as price,
        NULL::numeric as change_pct,
        km.market_cap,
        vm.pe_ratio,
        vm.pb_ratio,
        qm.roe,
        qm.debt_to_equity
      FROM stock_scores sc
      LEFT JOIN stock_symbols ss ON ss.symbol = sc.symbol
      LEFT JOIN company_profile cp ON cp.ticker = sc.symbol
      LEFT JOIN key_metrics km ON km.symbol = sc.symbol
      LEFT JOIN value_metrics vm ON vm.symbol = sc.symbol
      LEFT JOIN quality_metrics qm ON qm.symbol = sc.symbol
      ${whereClause}
      ORDER BY sc.${sortField} ${sortDir}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `,
      [...params, limitNum, offsetNum]
    );
    validateQueryResult(resultObj, { requireRows: false });

    const scores = (resultObj?.rows || []).map((row) => {
      const compositeScore = parseFloat(row.composite_score || 0);
      let grade = "F";
      if (compositeScore >= 90) grade = "A+";
      else if (compositeScore >= 80) grade = "A";
      else if (compositeScore >= 70) grade = "B";
      else if (compositeScore >= 60) grade = "C";
      else if (compositeScore >= 50) grade = "D";

      return {
        symbol: row.symbol,
        company_name: row.company_name,
        sector: row.sector,
        industry: row.industry,
        composite_score: parseFloat(row.composite_score || 0),
        momentum_score: parseFloat(row.momentum_score || 0),
        quality_score: parseFloat(row.quality_score || 0),
        value_score: parseFloat(row.value_score || 0),
        growth_score: parseFloat(row.growth_score || 0),
        positioning_score: parseFloat(row.positioning_score || 0),
        stability_score: parseFloat(row.stability_score || 0),
        grade: grade,
        price: parseFloat(row.price || 0),
        change_pct: parseFloat(row.change_pct || 0),
        market_cap: row.market_cap,
        pe_ratio: row.pe_ratio,
        pb_ratio: row.pb_ratio,
        roe: row.roe,
        debt_to_equity: row.debt_to_equity,
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
      hasPrev: pageNum > 1,
    });
  } catch (error) {
    console.error("Error fetching stockscores:", error.message);
    return sendError(
      res,
      `Failed to fetch scores: ${error.message.substring(0, 100)}`,
      500
    );
  }
});

// GET /:symbol - Get score for specific symbol
router.get("/:symbol", async (req, res) => {
  try {
    const { symbol } = req.params;

    const result = await query(`SELECT * FROM stock_scores WHERE symbol = $1`, [
      symbol.toUpperCase(),
    ]);
    validateQueryResult(result, { requireRows: false });

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
