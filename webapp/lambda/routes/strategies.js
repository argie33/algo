const express = require("express");

const { query } = require("../utils/database");
const { sendSuccess, sendError, sendPaginated } = require('../utils/apiResponse');
const router = express.Router();

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

// Get covered call opportunities with NEW METHODOLOGY filtering
router.get("/covered-calls", async (req, res) => {
  try {
    const {
      symbol,
      min_return_pct = 0,
      sort_by = "return_pct",
      limit = 100,
      page = 1
    } = req.query;

    // Validate pagination parameters
    const pageNum = Math.max(1, parseInt(page) || 1);
    const limitNum = Math.min(200, Math.max(1, parseInt(limit) || 100));
    const offset = (pageNum - 1) * limitNum;

    // Build WHERE clause
    let whereClause = `WHERE cco.data_date = (SELECT MAX(data_date) FROM covered_call_opportunities)`;
    const params = [];
    let paramIndex = 1;

    // Filter by minimum return %
    if (min_return_pct && parseFloat(min_return_pct) > 0) {
      whereClause += ` AND cco.return_pct >= $${paramIndex}`;
      params.push(parseFloat(min_return_pct));
      paramIndex++;
    }

    // Optional: Filter by specific symbol
    if (symbol) {
      whereClause += ` AND cco.symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    // Sort options based on available columns
    const validSortColumns = ['return_pct', 'premium', 'breakeven_pct', 'expiration_date', 'created_at'];
    const sortColumn = validSortColumns.includes(sort_by) ? sort_by : 'return_pct';
    const sortOrder = sort_by === 'expiration_date' ? 'ASC' : 'DESC';

    // Get total count for pagination
    const countSql = `SELECT COUNT(*) as total FROM covered_call_opportunities cco ${whereClause}`;

    const countResult = await query(countSql, params);
    const total = countResult.rows && countResult.rows[0] ? parseInt(countResult.rows[0].total) : 0;
    const totalPages = total > 0 ? Math.ceil(total / limitNum) : 0;

    // Get paginated results - only select columns that exist in the table
    const sql = `
      SELECT
        cco.id,
        cco.symbol,
        cco.expiration_date,
        cco.strike,
        cco.premium,
        cco.breakeven_pct,
        cco.return_pct,
        cco.days_to_expiration,
        cco.data_date,
        cco.created_at
      FROM covered_call_opportunities cco
      ${whereClause}
      ORDER BY cco.${sortColumn} ${sortOrder}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    params.push(limitNum, offset);

    const result = await query(sql, params);

    return sendPaginated(res, result.rows, {
      page: pageNum,
      limit: limitNum,
      total,
      totalPages,
      hasNext: pageNum < totalPages,
      hasPrev: pageNum > 1
    });

  } catch (error) {
    console.error("Error fetching covered call opportunities:", error.message);
    console.error("Full error:", error);
    return sendError(res, "Failed to fetch covered call opportunities: " + error.message, 500);
  }
});

// Alias: /list -> /covered-calls for backward compatibility
router.get("/list", (req, res) => {
  res.redirect(301, '/api/strategies/covered-calls');
});

module.exports = router;
