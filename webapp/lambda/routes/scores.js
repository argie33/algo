const express = require("express");

const { query } = require("../utils/database");
const {
  sendSuccess,
  sendError,
  sendPaginated,
} = require("../utils/apiResponse");
const { validateQueryResult } = require("../utils/responseValidation");
const {
  requireNumericField,
  isDataError,
} = require("../utils/strictValidation");
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
    // Explicit NaN checks for pagination parameters
    const limitVal = parseInt(limit, 10);
    const pageVal = parseInt(page, 10);
    const limitNum = Math.min(!isNaN(limitVal) ? limitVal : 50, 1000);
    const pageNum = Math.max(!isNaN(pageVal) ? pageVal : 1, 1);
    const offset = (pageNum - 1) * limitNum;

    // Build WHERE clause - exclude ETFs using stock_symbols table
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

    // Combined query to get both count and data in a single pass
    // This reduces database round-trips and improves Lambda performance
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
        ss.stability_score,
        COUNT(*) OVER() as total_count
      FROM stock_scores ss
      LEFT JOIN stock_symbols sy ON sy.symbol = ss.symbol
      ${whereClause}
      ORDER BY ss.${sortField} ${sortDir}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `,
      [...params, limitNum, offset]
    );
    validateQueryResult(resultObj, { requireRows: false });

    const scores = resultObj?.rows ?? [];
    const total = scores.length > 0 ? parseInt(scores[0].total_count) : 0;
    const totalPages = Math.ceil(total / limitNum);

    return sendPaginated(
      res,
      scores.map((row) => ({
        symbol: row.symbol,
        composite_score: row.composite_score,
        momentum_score: row.momentum_score,
        value_score: row.value_score,
        quality_score: row.quality_score,
        growth_score: row.growth_score,
        stability_score: row.stability_score,
      })),
      {
        page: pageNum,
        limit: limitNum,
        total,
        totalPages,
        hasNext: pageNum < totalPages,
        hasPrev: pageNum > 1,
      }
    );
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
    } = req.query;

    const parsedLimit = parseInt(limit);
    const limitNum = Math.min(!isNaN(parsedLimit) ? parsedLimit : 50, 5000);
    const parsedOffset = parseInt(offset);
    const parsedPage = parseInt(page);
    const pageNum = offset
      ? Math.max((!isNaN(parsedOffset) ? parsedOffset : 0) / limitNum + 1, 1)
      : Math.max(!isNaN(parsedPage) ? parsedPage : 1, 1);
    const offsetNum = offset
      ? Math.max(!isNaN(parsedOffset) ? parsedOffset : 0, 0)
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
    // Count fallback affects pagination - must be actual count or error
    const totalValidation = requireNumericField(
      countResult?.rows[0]?.total,
      "total_count",
      { min: 0, allowZero: true }
    );
    const total = isDataError(totalValidation) ? 0 : totalValidation;

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

    const scores = (resultObj?.rows ?? []).map((row) => {
      // Validate composite score - used for grading and sorting, cannot default to 0
      const compositeValidation = requireNumericField(
        row.composite_score,
        "composite_score",
        { min: 0, max: 100, allowZero: true }
      );

      let compositeScore = 0;
      let grade = "F";

      if (!isDataError(compositeValidation)) {
        compositeScore = compositeValidation;
        if (compositeScore >= 90) grade = "A+";
        else if (compositeScore >= 80) grade = "A";
        else if (compositeScore >= 70) grade = "B";
        else if (compositeScore >= 60) grade = "C";
        else if (compositeScore >= 50) grade = "D";
      }

      // Validate all component scores - these drive investment decisions
      const momentumValidation = requireNumericField(
        row.momentum_score,
        "momentum_score"
      );
      const qualityValidation = requireNumericField(
        row.quality_score,
        "quality_score"
      );
      const valueValidation = requireNumericField(
        row.value_score,
        "value_score"
      );
      const growthValidation = requireNumericField(
        row.growth_score,
        "growth_score"
      );
      const positioningValidation = requireNumericField(
        row.positioning_score,
        "positioning_score"
      );
      const stabilityValidation = requireNumericField(
        row.stability_score,
        "stability_score"
      );

      return {
        symbol: row.symbol,
        company_name: row.company_name,
        sector: row.sector,
        industry: row.industry,
        composite_score: !isDataError(compositeValidation)
          ? compositeValidation
          : null,
        momentum_score: !isDataError(momentumValidation)
          ? momentumValidation
          : null,
        quality_score: !isDataError(qualityValidation)
          ? qualityValidation
          : null,
        value_score: !isDataError(valueValidation) ? valueValidation : null,
        growth_score: !isDataError(growthValidation) ? growthValidation : null,
        positioning_score: !isDataError(positioningValidation)
          ? positioningValidation
          : null,
        stability_score: !isDataError(stabilityValidation)
          ? stabilityValidation
          : null,
        grade: grade,
        price: row.price,
        change_pct: row.change_pct,
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
