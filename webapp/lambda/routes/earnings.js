/**
 * Earnings API Routes
 *
 * Endpoints:
 * - GET /api/earnings - Earnings calendar
 */

const express = require('express');
const { getPool } = require('../utils/database');
const { sendSuccess, sendError } = require('../utils/apiResponse');
const logger = require('../utils/logger');
const { validateQueryResult, validateAndCoerceRows } = require('../utils/responseValidation');

const router = express.Router();

/**
 * GET /api/earnings
 * Earnings calendar - upcoming and recent earnings dates
 *
 * Query params:
 * - symbol: Filter by symbol
 * - days: Look ahead N days (default: 30)
 * - limit: Max results (default: 1000)
 */
router.get('/', async (req, res) => {
  try {
    const symbol = req.query.symbol;
    const days = parseInt(req.query.days) || 30;
    const limit = Math.min(parseInt(req.query.limit) || 1000, 10000);

    const pool = getPool();
    let whereClause = "earnings_date >= CURRENT_DATE - INTERVAL '90 days' AND earnings_date <= CURRENT_DATE + INTERVAL '180 days'";
    let params = [];

    if (symbol) {
      whereClause += ` AND symbol = $${params.length + 1}`;
      params.push(symbol.toUpperCase());
    }

    const result = await pool.query(`
      SELECT
        symbol,
        company_name,
        earnings_date,
        fiscal_quarter,
        fiscal_year,
        eps_estimate as estimated_eps,
        actual_eps as reported_eps,
        surprise_pct,
        status
      FROM earnings_calendar
      WHERE ${whereClause}
      ORDER BY earnings_date ASC
      LIMIT $${params.length + 1}
    `, [...params, limit]);

    // Validate query result structure
    validateQueryResult(result, { requireRows: false });

    // Validate and coerce field types
    const validated = validateAndCoerceRows(result, {
      symbol: { type: 'string', required: true },
      company_name: { type: 'string', required: false },
      earnings_date: { type: 'date', required: true },
      fiscal_quarter: { type: 'string', required: false },
      fiscal_year: { type: 'int', required: false },
      estimated_eps: { type: 'float', required: false, defaultValue: null },
      reported_eps: { type: 'float', required: false, defaultValue: null },
      surprise_pct: { type: 'float', required: false, defaultValue: null },
      status: { type: 'string', required: false }
    });

    return sendSuccess(res, {
      items: validated,
      pagination: {
        total: validated.length,
        limit: limit
      }
    });

  } catch (error) {
    logger.error('Error fetching earnings calendar:', { error: error.message });
    return sendError(res, `Failed to fetch earnings calendar: ${error.message}`, 500);
  }
});

module.exports = router;
