const express = require("express");

const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated, sendPlaceholder } = require('../utils/apiResponse');
const { authenticateToken } = require("../middleware/auth");
const logger = require('../utils/logger');
const { validateQueryResult, validateAndCoerceRows, extractCount } = require('../utils/responseValidation');
const router = express.Router();
router.use(authenticateToken);

// Root endpoint - documentation
router.get("/", (req, res) => {
  return sendSuccess(res, {
    endpoint: "strategies",
    documentation: "Options strategies and opportunity analysis",
    available_routes: [
      "GET /covered-calls - Get covered call opportunities with filters and pagination",
      "  Query params: symbol={ticker}, min_score={0-100}, min_premium_pct={num}, max_days_to_exp={num}",
      "                trend={uptrend|sideways|downtrend}, min_iv_rank={0-100}, sort_by={score|premium|max_profit|iv_rank|expiration}",
      "                limit={1-200, default 100}, page={1,2,3...}"
    ],
    examples: [
      "GET /api/strategies/covered-calls",
      "GET /api/strategies/covered-calls?symbol=AAPL&min_score=70",
      "GET /api/strategies/covered-calls?trend=uptrend&min_premium_pct=1.5&sort_by=score",
      "GET /api/strategies/covered-calls?symbol=AAPL&limit=50&page=1"
    ]
  });
});

// Get covered call opportunities
router.get("/covered-calls", async (req, res) => {
  const { limit = 100, page = 1 } = req.query;
  const pageNum = Math.max(1, parseInt(page) || 1);
  const limitNum = Math.min(200, Math.max(1, parseInt(limit) || 100));
  try {
    const offset = (pageNum - 1) * limitNum;

    const countSql = `SELECT COUNT(*) as total FROM covered_call_opportunities`;
    const countResult = await query(countSql, []);
    validateQueryResult(countResult, { requireRows: false });
    const total = extractCount(countResult, 'total');
    const totalPages = Math.ceil(total / limitNum);

    if (total === 0) {
      return sendPlaceholder(res, 'No covered call opportunities available - data may not be populated yet', 200, 'items');
    }

    const sql = `
      SELECT
        id, symbol, strike, expiration_date, premium,
        breakeven_pct, return_pct, days_to_expiration, data_date, created_at
      FROM covered_call_opportunities
      ORDER BY created_at DESC
      LIMIT $1 OFFSET $2
    `;

    const result = await query(sql, [limitNum, offset]);
    validateQueryResult(result, { requireRows: false });

    const validated = validateAndCoerceRows(result, {
      id: { type: 'int' },
      symbol: { type: 'string', required: true },
      strike: { type: 'float' },
      expiration_date: { type: 'date' },
      premium: { type: 'float' },
      breakeven_pct: { type: 'float' },
      return_pct: { type: 'float' },
      days_to_expiration: { type: 'int' },
      data_date: { type: 'date' },
      created_at: { type: 'date' }
    });

    const opportunities = validated.map(row => ({
      id: row.id,
      symbol: row.symbol,
      strike: row.strike,
      expiration_date: row.expiration_date,
      premium: row.premium,
      breakeven_pct: row.breakeven_pct,
      return_pct: row.return_pct,
      days_to_expiration: row.days_to_expiration,
      data_date: row.data_date,
      created_at: row.created_at
    }));

    return sendPaginated(res, opportunities, {
      page: pageNum,
      limit: limitNum,
      total,
      totalPages,
      hasNext: pageNum < totalPages,
      hasPrev: pageNum > 1
    });
  } catch (error) {
    console.error("Error fetching covered call opportunities:", error.message);
    return sendPlaceholder(res, `Failed to fetch covered call opportunities: ${error.message}`, 500, 'items');
  }
});

// Alias: /list -> /covered-calls for backward compatibility
router.get("/list", (req, res) => {
  res.redirect(301, '/api/strategies/covered-calls');
});

module.exports = router;
