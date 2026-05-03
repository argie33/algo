const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

/**
 * GET /api/signals/mean-reversion
 * Mean reversion (Connors RSI) signals with pagination and filtering
 */
router.get('/', async (req, res, next) => {
  try {
    const {
      timeframe = 'daily',
      dataType = 'stocks',
      signal,
      symbol,
      limit = 50,
      offset = 0,
      days = 30,
      min_confluence = 0
    } = req.query;

    // Validate dataType
    if (!['stocks', 'etf'].includes(dataType)) {
      return res.status(400).json({
        success: false,
        error: "Invalid dataType. Must be 'stocks' or 'etf'",
        timestamp: new Date().toISOString()
      });
    }

    // Map dataType to table name
    const tableSuffix = dataType === 'etf' ? '_etf' : '';
    const tableName = `mean_reversion_signals_daily${tableSuffix}`;
    const symbolsTable = dataType === 'etf' ? 'etf_symbols' : 'stock_symbols';

    let q = `
      SELECT
        mrs.*,
        ss.security_name as company_name
      FROM ${tableName} mrs
      LEFT JOIN ${symbolsTable} ss ON mrs.symbol = ss.symbol
      WHERE mrs.timeframe = $1
        AND mrs.date >= NOW() - INTERVAL '${days} days'
        AND mrs.confluence_score >= $2
    `;

    const params = [timeframe, parseInt(min_confluence)];
    let paramCount = 2;

    if (signal) {
      paramCount++;
      q += ` AND mrs.signal = $${paramCount}`;
      params.push(signal);
    }

    if (symbol) {
      paramCount++;
      q += ` AND mrs.symbol = $${paramCount}`;
      params.push(symbol.toUpperCase());
    }

    // Count total
    const countResult = await query(`SELECT COUNT(*) as total FROM (${q.split('ORDER BY').shift()}) t`, params);
    const total = countResult.rows[0].total;

    q += ` ORDER BY mrs.date DESC, mrs.confluence_score DESC`;
    q += ` LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}`;

    const result = await query(q, [...params, parseInt(limit), parseInt(offset)]);

    res.json({
      success: true,
      items: result.rows,
      pagination: {
        limit: parseInt(limit),
        offset: parseInt(offset),
        total,
        page: Math.floor(parseInt(offset) / parseInt(limit)) + 1,
        totalPages: Math.ceil(total / parseInt(limit)),
        hasNext: parseInt(offset) + parseInt(limit) < total,
        hasPrev: parseInt(offset) > 0
      },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    next(error);
  }
});

/**
 * GET /api/signals/mean-reversion/:symbol
 * Mean reversion signals for specific symbol
 */
router.get('/:symbol', async (req, res, next) => {
  try {
    const { symbol } = req.params;
    const { limit = 100, offset = 0 } = req.query;

    const q = `
      SELECT
        mrs.*,
        ss.security_name
      FROM mean_reversion_signals_daily mrs
      LEFT JOIN stock_symbols ss ON mrs.symbol = ss.symbol
      WHERE mrs.symbol = $1
      ORDER BY mrs.date DESC
      LIMIT $2 OFFSET $3
    `;

    const result = await query(q, [symbol.toUpperCase(), parseInt(limit), parseInt(offset)]);

    res.json({
      success: true,
      items: result.rows,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    next(error);
  }
});

module.exports = router;
