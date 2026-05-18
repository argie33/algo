/**
 * Stocks API Routes
 *
 * Endpoints:
 * - GET /api/stocks - List all stocks
 * - GET /api/stocks/deep-value - List stocks with value metrics
 */

const express = require('express');
const { getPool } = require('../utils/database');
const { sendSuccess, sendError } = require('../utils/apiResponse');

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
router.get('/', async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 500, 50000);
    const offset = parseInt(req.query.offset) || 0;
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
    const result = await pool.query(`
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
    `, [...params, limit, offset]);

    // Get total count
    const countResult = await pool.query(`
      SELECT COUNT(*) as total
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      WHERE ${whereClause}
    `, params);

    return sendSuccess(res, {
      items: result.rows,
      pagination: {
        total: parseInt(countResult.rows[0].total),
        limit: limit,
        offset: offset
      }
    });

  } catch (error) {
    console.error('Error fetching stocks:', error);
    return sendError(res, `Failed to fetch stocks: ${error.message}`, 500);
  }
});

/**
 * GET /api/stocks/deep-value
 * List stocks with value metrics
 */
router.get('/deep-value', async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 600, 1000);
    const pool = getPool();

    const result = await pool.query(`
      SELECT DISTINCT
        ss.symbol,
        ss.security_name as company_name,
        cp.sector,
        cp.industry,
        cp.market_cap,
        vm.pe_ratio,
        vm.pb_ratio,
        pd.close as price
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN value_metrics vm ON ss.symbol = vm.symbol
      LEFT JOIN price_daily pd ON ss.symbol = pd.symbol AND pd.date = CURRENT_DATE - INTERVAL 1 DAY
      WHERE ss.symbol NOT LIKE '^%%'
      ORDER BY ss.symbol
      LIMIT $1
    `, [limit]);

    return sendSuccess(res, {
      items: result.rows
    });

  } catch (error) {
    console.error('Error fetching deep-value stocks:', error);
    return sendError(res, `Failed to fetch deep-value stocks: ${error.message}`, 500);
  }
});

module.exports = router;
