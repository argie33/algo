/**
 * Financials API Routes
 *
 * Endpoints:
 * - GET /api/financials/:ticker/balance-sheet - Balance sheet data
 * - GET /api/financials/:ticker/income-statement - Income statement
 * - GET /api/financials/:ticker/cash-flow - Cash flow statement
 * - GET /api/financials/:ticker/key-metrics - Key financial metrics
 */

const express = require("express");

const { getPool } = require("../utils/database");
const { sendSuccess, sendError } = require("../utils/apiResponse");
const logger = require("../utils/logger");
const {
  validateQueryResult,
  extractSingleRow,
} = require("../utils/responseValidation");

const router = express.Router();

/**
 * GET /api/financials/:ticker/balance-sheet
 * Balance sheet data (annual or quarterly)
 */
router.get("/:ticker/balance-sheet", async (req, res) => {
  try {
    const { ticker } = req.params;
    const period = req.query.period || "annual";

    if (!ticker) {
      return sendError(res, "Missing ticker parameter", 400);
    }

    const pool = getPool();
    const table =
      period === "quarterly"
        ? "quarterly_balance_sheet"
        : "annual_balance_sheet";

    const result = await pool.query(
      `
      SELECT *
      FROM ${table}
      WHERE symbol = $1
      ORDER BY fiscal_year DESC ${period === "quarterly" ? ", fiscal_quarter DESC" : ""}
      LIMIT 20
    `,
      [ticker.toUpperCase()]
    );

    // Validate query result structure
    validateQueryResult(result, { requireRows: false });

    // Validate and coerce field types - flexible schema since SELECT * returns all columns
    const validated = result.rows.map((row) => {
      const coerced = {};
      for (const [key, value] of Object.entries(row)) {
        // Coerce numeric-looking field names to numbers
        if (
          key.includes("_pct") ||
          key.includes("ratio") ||
          key.includes("yield")
        ) {
          coerced[key] =
            typeof value === "number"
              ? value
              : isNaN(value)
                ? null
                : parseFloat(value);
        } else if (
          key.includes("amount") ||
          key.includes("value") ||
          key.includes("per_share")
        ) {
          coerced[key] =
            typeof value === "number"
              ? value
              : isNaN(value)
                ? null
                : parseFloat(value);
        } else if (key === "fiscal_year") {
          coerced[key] =
            typeof value === "number"
              ? value
              : isNaN(value)
                ? null
                : parseInt(value);
        } else {
          coerced[key] = value;
        }
      }
      return coerced;
    });

    return sendSuccess(res, {
      ticker: ticker.toUpperCase(),
      period: period,
      data: validated,
    });
  } catch (error) {
    logger.error("Error fetching balance sheet:", {
      error: error.message,
      stack: error.stack,
    });
    return sendError(
      res,
      `Failed to fetch balance sheet: ${error.message}`,
      500
    );
  }
});

/**
 * GET /api/financials/:ticker/income-statement
 * Income statement data
 */
router.get("/:ticker/income-statement", async (req, res) => {
  try {
    const { ticker } = req.params;
    const period = req.query.period || "annual";

    if (!ticker) {
      return sendError(res, "Missing ticker parameter", 400);
    }

    const pool = getPool();
    const table =
      period === "quarterly"
        ? "quarterly_income_statement"
        : "annual_income_statement";

    const result = await pool.query(
      `
      SELECT *
      FROM ${table}
      WHERE symbol = $1
      ORDER BY fiscal_year DESC ${period === "quarterly" ? ", fiscal_quarter DESC" : ""}
      LIMIT 20
    `,
      [ticker.toUpperCase()]
    );

    // Validate query result structure
    validateQueryResult(result, { requireRows: false });

    // Validate and coerce field types - flexible schema since SELECT * returns all columns
    const validated = result.rows.map((row) => {
      const coerced = {};
      for (const [key, value] of Object.entries(row)) {
        // Coerce numeric-looking field names to numbers
        if (
          key.includes("_pct") ||
          key.includes("ratio") ||
          key.includes("yield")
        ) {
          coerced[key] =
            typeof value === "number"
              ? value
              : isNaN(value)
                ? null
                : parseFloat(value);
        } else if (
          key.includes("amount") ||
          key.includes("value") ||
          key.includes("per_share")
        ) {
          coerced[key] =
            typeof value === "number"
              ? value
              : isNaN(value)
                ? null
                : parseFloat(value);
        } else if (key === "fiscal_year") {
          coerced[key] =
            typeof value === "number"
              ? value
              : isNaN(value)
                ? null
                : parseInt(value);
        } else {
          coerced[key] = value;
        }
      }
      return coerced;
    });

    return sendSuccess(res, {
      ticker: ticker.toUpperCase(),
      period: period,
      data: validated,
    });
  } catch (error) {
    logger.error("Error fetching income statement:", {
      error: error.message,
      stack: error.stack,
    });
    return sendError(
      res,
      `Failed to fetch income statement: ${error.message}`,
      500
    );
  }
});

/**
 * GET /api/financials/:ticker/cash-flow
 * Cash flow statement data
 */
router.get("/:ticker/cash-flow", async (req, res) => {
  try {
    const { ticker } = req.params;
    const period = req.query.period || "annual";

    if (!ticker) {
      return sendError(res, "Missing ticker parameter", 400);
    }

    const pool = getPool();
    const table =
      period === "quarterly" ? "quarterly_cash_flow" : "annual_cash_flow";

    const result = await pool.query(
      `
      SELECT *
      FROM ${table}
      WHERE symbol = $1
      ORDER BY fiscal_year DESC ${period === "quarterly" ? ", fiscal_quarter DESC" : ""}
      LIMIT 20
    `,
      [ticker.toUpperCase()]
    );

    // Validate query result structure
    validateQueryResult(result, { requireRows: false });

    // Validate and coerce field types - flexible schema since SELECT * returns all columns
    const validated = result.rows.map((row) => {
      const coerced = {};
      for (const [key, value] of Object.entries(row)) {
        // Coerce numeric-looking field names to numbers
        if (
          key.includes("_pct") ||
          key.includes("ratio") ||
          key.includes("yield")
        ) {
          coerced[key] =
            typeof value === "number"
              ? value
              : isNaN(value)
                ? null
                : parseFloat(value);
        } else if (
          key.includes("amount") ||
          key.includes("value") ||
          key.includes("per_share")
        ) {
          coerced[key] =
            typeof value === "number"
              ? value
              : isNaN(value)
                ? null
                : parseFloat(value);
        } else if (key === "fiscal_year") {
          coerced[key] =
            typeof value === "number"
              ? value
              : isNaN(value)
                ? null
                : parseInt(value);
        } else {
          coerced[key] = value;
        }
      }
      return coerced;
    });

    return sendSuccess(res, {
      ticker: ticker.toUpperCase(),
      period: period,
      data: validated,
    });
  } catch (error) {
    logger.error("Error fetching cash flow:", {
      error: error.message,
      stack: error.stack,
    });
    return sendError(res, `Failed to fetch cash flow: ${error.message}`, 500);
  }
});

/**
 * GET /api/financials/:ticker/key-metrics
 * Key financial metrics
 */
router.get("/:ticker/key-metrics", async (req, res) => {
  try {
    const { ticker } = req.params;

    if (!ticker) {
      return sendError(res, "Missing ticker parameter", 400);
    }

    const pool = getPool();

    const result = await pool.query(
      `
      SELECT
        symbol,
        market_cap,
        held_percent_insiders,
        held_percent_institutions
      FROM key_metrics
      WHERE symbol = $1
    `,
      [ticker.toUpperCase()]
    );

    // Validate query result structure
    validateQueryResult(result, { requireRows: false });

    if (result.rows.length === 0) {
      return sendSuccess(res, { ticker: ticker.toUpperCase(), data: {} });
    }

    // Validate and coerce field types
    const validated = extractSingleRow(result, {
      symbol: { type: "string", required: true },
      market_cap: { type: "float", required: false, defaultValue: null },
      held_percent_insiders: {
        type: "float",
        required: false,
        defaultValue: null,
      },
      held_percent_institutions: {
        type: "float",
        required: false,
        defaultValue: null,
      },
    });

    return sendSuccess(res, {
      ticker: ticker.toUpperCase(),
      data: validated || {},
    });
  } catch (error) {
    logger.error("Error fetching key metrics:", {
      error: error.message,
      stack: error.stack,
    });
    return sendError(res, `Failed to fetch key metrics: ${error.message}`, 500);
  }
});

/**
 * GET /api/financials/:ticker/ownership
 * Insider and segment ownership/diversification metrics
 */
router.get("/:ticker/ownership", async (req, res) => {
  try {
    const { ticker } = req.params;

    if (!ticker) {
      return sendError(res, "Missing ticker parameter", 400);
    }

    const pool = getPool();

    // Query both insider holdings and segment metrics
    const result = await pool.query(
      `
      SELECT
        COALESCE(i.symbol, s.symbol) as symbol,
        i.insider_ownership_pct,
        i.number_of_insiders,
        i.recent_buys,
        s.segment_count,
        s.largest_segment_revenue_pct,
        s.revenue_concentration_hhi,
        s.is_diversified
      FROM insider_holdings_sec i
      FULL OUTER JOIN sec_segment_metrics s ON i.symbol = s.symbol
      WHERE COALESCE(i.symbol, s.symbol) = $1
    `,
      [ticker.toUpperCase()]
    );

    validateQueryResult(result, { requireRows: false });

    if (result.rows.length === 0) {
      return sendSuccess(res, { ticker: ticker.toUpperCase(), data: {} });
    }

    const validated = extractSingleRow(result, {
      symbol: { type: "string", required: true },
      insider_ownership_pct: {
        type: "float",
        required: false,
        defaultValue: null,
      },
      number_of_insiders: {
        type: "integer",
        required: false,
        defaultValue: null,
      },
      recent_buys: {
        type: "integer",
        required: false,
        defaultValue: null,
      },
      segment_count: {
        type: "integer",
        required: false,
        defaultValue: null,
      },
      largest_segment_revenue_pct: {
        type: "float",
        required: false,
        defaultValue: null,
      },
      revenue_concentration_hhi: {
        type: "float",
        required: false,
        defaultValue: null,
      },
      is_diversified: {
        type: "boolean",
        required: false,
        defaultValue: null,
      },
    });

    return sendSuccess(res, {
      ticker: ticker.toUpperCase(),
      data: validated || {},
    });
  } catch (error) {
    logger.error("Error fetching ownership metrics:", {
      error: error.message,
      stack: error.stack,
    });
    return sendError(res, `Failed to fetch ownership metrics: ${error.message}`, 500);
  }
});

module.exports = router;
