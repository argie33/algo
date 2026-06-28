/**
 * Stocks API Routes
 *
 * Endpoints:
 * - GET /api/stocks - List all stocks
 * - GET /api/stocks/deep-value - List stocks with value metrics
 */

const express = require("express");

const { getPool } = require("../utils/database");
const { sendSuccess, sendError } = require("../utils/apiResponse");
const logger = require("../utils/logger");
const {
  validateQueryResult,
  validateAndCoerceRows,
  extractSingleRow,
  extractCount,
} = require("../utils/responseValidation");

const router = express.Router();

/**
 * GET /api/stocks
 * List stocks with optional filtering
 *
 * Query params:
 * - limit: Number to return (default: 500, max: 50000)
 * - offset: Skip N (default: 0)
 * - search: Filter by symbol or name
 * - sector: Filter by sector
 */
router.get("/", async (req, res) => {
  try {
    const limitVal = parseInt(req.query.limit, 10);
    const limit = !isNaN(limitVal) ? Math.min(Math.max(limitVal, 1), 50000) : 500;

    const offsetVal = parseInt(req.query.offset, 10);
    const offset = !isNaN(offsetVal) ? Math.max(offsetVal, 0) : 0;
    const search = req.query.search;
    const sector = req.query.sector;

    const pool = getPool();
    let whereClause = "ss.symbol NOT LIKE '^%%'";
    let params = [];

    if (search) {
      whereClause += ` AND (ss.symbol ILIKE $${params.length + 1} OR ss.security_name ILIKE $${params.length + 2})`;
      params.push(`%${search}%`, `%${search}%`);
    }

    if (sector) {
      whereClause += ` AND cp.sector = $${params.length + 1}`;
      params.push(sector);
    }

    // Get stocks
    const result = await pool.query(
      `
      SELECT
        ss.symbol,
        ss.security_name as company_name,
        cp.sector,
        cp.industry,
        km.market_cap,
        ss.is_sp500
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN key_metrics km ON ss.symbol = km.ticker
      WHERE ${whereClause}
      ORDER BY ss.symbol
      LIMIT $${params.length + 1} OFFSET $${params.length + 2}
    `,
      [...params, limit, offset]
    );

    // Get total count
    const countResult = await pool.query(
      `
      SELECT COUNT(*) as total
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      WHERE ${whereClause}
    `,
      params
    );

    // Validate query results
    validateQueryResult(result, { requireRows: false });
    const total = extractCount(countResult, "total");

    // Validate and coerce field types
    const validated = validateAndCoerceRows(result, {
      symbol: { type: "string", required: true },
      company_name: { type: "string", required: false },
      sector: { type: "string", required: false },
      industry: { type: "string", required: false },
      market_cap: { type: "float", required: false, defaultValue: null },
      is_sp500: { type: "bool", required: false, defaultValue: false },
    });

    return sendSuccess(res, {
      items: validated,
      pagination: {
        total: total,
        limit: limit,
        offset: offset,
      },
    });
  } catch (error) {
    logger.error("Error fetching stocks:", {
      error: error.message,
      stack: error.stack,
    });
    return sendError(res, `Failed to fetch stocks: ${error.message}`, 500);
  }
});

/**
 * GET /api/stocks/deep-value
 * List stocks with value metrics
 */
router.get("/deep-value", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 600, 1000);
    const pool = getPool();

    const result = await pool.query(
      `
      SELECT DISTINCT
        ss.symbol,
        ss.security_name as company_name,
        cp.sector,
        cp.industry,
        km.market_cap,
        vm.pe_ratio as trailing_pe,
        vm.pb_ratio as price_to_book,
        NULL as price_to_sales,
        NULL as roe_pct,
        NULL as op_margin_pct,
        NULL as gross_margin_pct,
        NULL as net_margin_pct,
        NULL as roa_pct,
        NULL as ev_to_ebitda,
        NULL as peg_ratio,
        NULL as dividend_yield,
        NULL as debt_to_equity,
        NULL as current_ratio,
        vm.pe_ratio as sector_median_pe,
        vm.pe_ratio as market_median_pe,
        NULL as discount_vs_sector_pe_pct,
        NULL as discount_vs_market_pe_pct,
        NULL as high_52w,
        NULL as high_3y,
        NULL as low_52w,
        NULL as drop_from_52w_high_pct,
        NULL as drop_from_3y_high_pct,
        NULL as intrinsic_value_per_share,
        NULL as revenue_growth_3y_pct,
        NULL as eps_growth_3y_pct,
        NULL as revenue_growth_yoy_pct,
        NULL as fcf_growth_yoy_pct,
        NULL as sustainable_growth_pct,
        NULL as op_margin_trend_pp,
        NULL as gross_margin_trend_pp,
        NULL as roe_trend_pp,
        pd.close as current_price,
        CAST(vm.pe_ratio as DECIMAL(10,2)) as generational_score
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN key_metrics km ON ss.symbol = km.symbol
      LEFT JOIN value_metrics vm ON ss.symbol = vm.symbol
      LEFT JOIN price_daily pd ON ss.symbol = pd.symbol AND pd.date = CURRENT_DATE - INTERVAL '1 day'
      WHERE ss.symbol NOT LIKE '^%%'
      ORDER BY ss.symbol
      LIMIT $1
    `,
      [limit]
    );

    // Validate query result - for this large numeric query, keep flexible coercion
    validateQueryResult(result, { requireRows: false });

    const validated = result.rows.map((row) => {
      const coerced = {};
      for (const [key, value] of Object.entries(row)) {
        // Coerce all numeric-looking fields
        if (
          typeof value === "number" ||
          (typeof value === "string" && !isNaN(value) && value !== "")
        ) {
          coerced[key] = typeof value === "number" ? value : parseFloat(value);
        } else {
          coerced[key] = value;
        }
      }
      return coerced;
    });

    return sendSuccess(res, {
      items: validated,
    });
  } catch (error) {
    logger.error("Error fetching deep-value stocks:", {
      error: error.message,
      stack: error.stack,
    });
    return sendError(
      res,
      `Failed to fetch deep-value stocks: ${error.message}`,
      500
    );
  }
});

/**
 * GET /api/stocks/:ticker
 * Get individual stock details
 */
router.get("/:ticker", async (req, res) => {
  try {
    const { ticker } = req.params;
    const pool = getPool();

    const result = await pool.query(
      `
      SELECT
        ss.symbol,
        ss.security_name as company_name,
        cp.sector,
        cp.industry,
        cp.website,
        cp.exchange,
        km.market_cap,
        vm.pe_ratio,
        vm.pb_ratio,
        vm.ps_ratio,
        vm.dividend_yield
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN key_metrics km ON ss.symbol = km.symbol
      LEFT JOIN value_metrics vm ON ss.symbol = vm.symbol
      WHERE ss.symbol = $1
    `,
      [ticker.toUpperCase()]
    );

    // Validate query result
    validateQueryResult(result, { requireRows: false });

    if (result.rows.length === 0) {
      return sendError(res, `Stock ${ticker} not found`, 404);
    }

    // Validate and coerce field types
    const validated = extractSingleRow(result, {
      symbol: { type: "string", required: true },
      company_name: { type: "string", required: false },
      sector: { type: "string", required: false },
      industry: { type: "string", required: false },
      website: { type: "string", required: false },
      exchange: { type: "string", required: false },
      market_cap: { type: "float", required: false, defaultValue: null },
      pe_ratio: { type: "float", required: false, defaultValue: null },
      pb_ratio: { type: "float", required: false, defaultValue: null },
      ps_ratio: { type: "float", required: false, defaultValue: null },
      dividend_yield: { type: "float", required: false, defaultValue: null },
    });

    return sendSuccess(res, validated);
  } catch (error) {
    logger.error("Error fetching stock detail:", {
      error: error.message,
      stack: error.stack,
    });
    return sendError(
      res,
      `Failed to fetch stock details: ${error.message}`,
      500
    );
  }
});

module.exports = router;
