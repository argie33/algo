const express = require("express");

let query;
try {
  ({ query } = require("../utils/database"));
} catch (error) {
  console.log("Database service not available in financials routes:", error.message);
  query = null;
}

const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const router = express.Router();

// Root endpoint - provides overview of available financial endpoints
router.get("/", async (req, res) => {
  return sendSuccess(res, {
    message: "Financials API - Ready",
    status: "operational",
    endpoints: [
      "/:symbol/balance-sheet?period=annual|quarterly - Get balance sheet",
      "/:symbol/income-statement?period=annual|quarterly - Get income statement",
      "/:symbol/cash-flow?period=annual|quarterly - Get cash flow statement",
      "/:symbol/key-metrics - Get key financial metrics",
    ],
  });
});

// GET /api/financials/:symbol/balance-sheet - Get balance sheet
router.get("/:symbol/balance-sheet", async (req, res) => {
  const { symbol } = req.params;
  const { period = "annual" } = req.query;
  const upperSymbol = symbol.toUpperCase();

  console.log(`📊 [FINANCIALS] Fetching balance sheet for ${upperSymbol} (${period})`);

  // Financial statement tables not yet populated - return empty structure
  return sendSuccess(res, {
    symbol: upperSymbol,
    period: period,
    financialData: []
  });
});

// GET /api/financials/:symbol/income-statement - Get income statement
router.get("/:symbol/income-statement", async (req, res) => {
  const { symbol } = req.params;
  const { period = "annual" } = req.query;
  const upperSymbol = symbol.toUpperCase();

  console.log(`📊 [FINANCIALS] Fetching income statement for ${upperSymbol} (${period})`);

  // Financial statement tables not yet populated - return empty structure
  return sendSuccess(res, {
    symbol: upperSymbol,
    period: period,
    financialData: []
  });
});

// GET /api/financials/:symbol/cash-flow - Get cash flow statement
router.get("/:symbol/cash-flow", async (req, res) => {
  const { symbol } = req.params;
  const { period = "annual" } = req.query;
  const upperSymbol = symbol.toUpperCase();

  console.log(`📊 [FINANCIALS] Fetching cash flow for ${upperSymbol} (${period})`);

  // Financial statement tables not yet populated - return empty structure
  return sendSuccess(res, {
    symbol: upperSymbol,
    period: period,
    financialData: []
  });
});

// GET /api/financials/:symbol/key-metrics - Get key financial metrics
router.get("/:symbol/key-metrics", async (req, res) => {
  const { symbol } = req.params;
  const upperSymbol = symbol.toUpperCase();

  console.log(`📊 [FINANCIALS] Fetching key metrics for ${upperSymbol}`);

  // Financial metrics tables not yet populated - return empty structure
  return sendSuccess(res, {
    symbol: upperSymbol,
    metricsData: {}
  });
});

// GET /api/financials/all - Get all financial data for all stocks (bulk operation)
router.get("/all", async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 50, 200);
    const offset = parseInt(req.query.offset) || 0;
    const symbol = req.query.symbol;

    console.log(`📊 [FINANCIALS] Fetching all financials with limit=${limit}, offset=${offset}`);

    let whereClause = "1=1";
    const params = [];
    let paramIndex = 1;

    if (symbol) {
      params.push(symbol.toUpperCase());
      whereClause += ` AND cp.ticker = $${paramIndex}`;
      paramIndex++;
    }

    // Get company profile with financial data (simple version without JOINs due to schema complexity)
    const result = await query(`
      SELECT
        cp.ticker as symbol,
        cp.short_name as name,
        cp.sector,
        cp.industry
      FROM company_profile cp
      WHERE ${whereClause}
      ORDER BY cp.ticker ASC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `, [...params, limit, offset]);

    // Get total count
    const countResult = await query(
      `SELECT COUNT(DISTINCT ticker) as total FROM company_profile WHERE ${whereClause}`,
      params
    );
    const total = parseInt(countResult.rows[0]?.total || 0);

    return sendPaginated(res, result.rows || [], {
      limit,
      offset,
      total,
      page: Math.max(1, Math.ceil((offset / limit) + 1))
    });
  } catch (error) {
    console.error("All financials error:", error);
    return sendSuccess(res, { symbol: upperSymbol, data: [] });
  }
});

module.exports = router;
