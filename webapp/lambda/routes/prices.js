/**
 * Price Data API Routes
 *
 * Endpoints:
 * - GET /api/prices/history/:symbol - Get historical price data
 */

const express = require('express');
const { getPool } = require('../utils/database');
const { sendSuccess, sendError } = require('../utils/apiResponse');

const router = express.Router();

/**
 * GET /api/prices/history/:symbol
 * Historical OHLCV price data
 *
 * Query params:
 * - limit: Number of records to return (default: 252, max: 5000)
 * - offset: Skip N records (default: 0)
 * - timeframe: 'daily', 'weekly', 'monthly' (default: 'daily')
 */
router.get('/history/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const limit = Math.min(parseInt(req.query.limit) || 252, 5000);
    const offset = parseInt(req.query.offset) || 0;
    const timeframe = req.query.timeframe || 'daily';

    if (!symbol) {
      return sendError(res, 'Missing symbol parameter', 400);
    }

    // Map timeframe to table
    const tableMap = {
      'daily': 'price_daily',
      'weekly': 'price_weekly',
      'monthly': 'price_monthly'
    };
    const table = tableMap[timeframe] || 'price_daily';

    const pool = getPool();

    // Get price data
    const result = await pool.query(`
      SELECT
        date,
        open,
        high,
        low,
        close,
        volume,
        adj_close
      FROM ${table}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT $2 OFFSET $3
    `, [symbol.toUpperCase(), limit, offset]);

    // Get total count
    const countResult = await pool.query(`
      SELECT COUNT(*) as total FROM ${table} WHERE symbol = $1
    `, [symbol.toUpperCase()]);

    const data = result.rows.map(row => ({
      date: row.date,
      open: parseFloat(row.open),
      high: parseFloat(row.high),
      low: parseFloat(row.low),
      close: parseFloat(row.close),
      volume: parseInt(row.volume),
      adj_close: parseFloat(row.adj_close)
    }));

    return sendSuccess(res, {
      symbol: symbol.toUpperCase(),
      timeframe: timeframe,
      data: data.reverse(), // Return oldest first
      pagination: {
        total: parseInt(countResult.rows[0].total),
        limit: limit,
        offset: offset
      }
    });

  } catch (error) {
    console.error('Error fetching price history:', error);
    return sendError(res, `Failed to fetch price history: ${error.message}`, 500);
  }
});

module.exports = router;
