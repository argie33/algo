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

    return sendSuccess(res, {
      items: result.rows || [],
      pagination: {
        total: result.rows.length,
        limit: limit
      }
    });

  } catch (error) {
    logger.error('Error fetching earnings calendar:', { error: error.message });
    return sendError(res, `Failed to fetch earnings calendar: ${error.message}`, 500);
  }
});

module.exports = router;
