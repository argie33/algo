const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

/**
 * GET /api/signals/range
 * Range trading signals with pagination and filtering
 */
router.get('/', async (req, res, next) => {
  try {
    const {
      timeframe = 'daily',
      signal,
      signal_type,
      symbol,
      limit = 50,
      offset = 0,
      days = 30
    } = req.query;

    let q = `
      SELECT
        rs.id, rs.symbol, rs.date, rs.timeframe,
        rs.open, rs.high, rs.low, rs.close, rs.volume,
        rs.signal, rs.signal_type,
        rs.range_high, rs.range_low, rs.range_position, rs.range_age_days, rs.range_strength, rs.range_height_pct,
        rs.entry_price, rs.stop_level, rs.target_1, rs.target_2,
        rs.risk_pct, rs.risk_reward_ratio,
        rs.rsi, rs.adx, rs.atr,
        rs.td_buy_setup_count, rs.td_sell_setup_count, rs.td_buy_setup_complete, rs.td_sell_setup_complete,
        rs.td_pressure,
        ss.security_name
      FROM range_signals_daily rs
      LEFT JOIN stock_symbols ss ON rs.symbol = ss.symbol
      WHERE rs.timeframe = $1
        AND rs.date >= NOW() - INTERVAL '%d days'
    `;

    const params = [timeframe, days];
    let paramCount = 2;

    if (signal) {
      paramCount++;
      q += ` AND rs.signal = $${paramCount}`;
      params.push(signal);
    }

    if (signal_type) {
      paramCount++;
      q += ` AND rs.signal_type = $${paramCount}`;
      params.push(signal_type);
    }

    if (symbol) {
      paramCount++;
      q += ` AND rs.symbol = $${paramCount}`;
      params.push(symbol.toUpperCase());
    }

    // Count total
    const countResult = await query(`SELECT COUNT(*) as total FROM (${q.split('ORDER BY').shift()}) t`, params);
    const total = countResult.rows[0].total;

    q += ` ORDER BY rs.date DESC, rs.risk_reward_ratio DESC`;
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
 * GET /api/signals/range/:symbol
 * Range signals for specific symbol
 */
router.get('/:symbol', async (req, res, next) => {
  try {
    const { symbol } = req.params;
    const { limit = 100, offset = 0 } = req.query;

    const q = `
      SELECT
        rs.*,
        ss.security_name
      FROM range_signals_daily rs
      LEFT JOIN stock_symbols ss ON rs.symbol = ss.symbol
      WHERE rs.symbol = $1
      ORDER BY rs.date DESC
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
