const express = require('express');
const router = express.Router();
const pool = require('../db');

/**
 * Momentum Metrics Routes
 * Provides Jegadeesh-Titman 12-1 month momentum and related analytics
 */

/**
 * GET /api/momentum/stocks/:symbol
 * Get momentum metrics for a single stock
 */
router.get('/stocks/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;

    const result = await pool.query(
      'SELECT symbol, date, jt_momentum, volatility, turnover FROM momentum_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT 1',
      [symbol.toUpperCase()]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'No momentum data found for symbol', symbol });
    }

    res.json({
      symbol: result.rows[0].symbol,
      momentum: result.rows[0].jt_momentum,
      volatility: result.rows[0].volatility,
      turnover: result.rows[0].turnover,
      date: result.rows[0].date
    });
  } catch (error) {
    console.error('Error fetching momentum:', error);
    res.status(500).json({ error: 'Failed to fetch momentum data' });
  }
});

/**
 * GET /api/momentum/leaders
 * Get top momentum stocks
 */
router.get('/leaders', async (req, res) => {
  try {
    const { limit = 20, minVol = 0 } = req.query;

    const result = await pool.query(
      `SELECT symbol, jt_momentum, volatility, date
       FROM momentum_metrics
       WHERE jt_momentum > $1
       ORDER BY jt_momentum DESC
       LIMIT $2`,
      [minVol, parseInt(limit)]
    );

    res.json({
      count: result.rows.length,
      data: result.rows.map(row => ({
        symbol: row.symbol,
        momentum: row.jt_momentum,
        volatility: row.volatility,
        date: row.date
      }))
    });
  } catch (error) {
    console.error('Error fetching momentum leaders:', error);
    res.status(500).json({ error: 'Failed to fetch momentum leaders' });
  }
});

/**
 * GET /api/momentum/laggards
 * Get lowest momentum stocks
 */
router.get('/laggards', async (req, res) => {
  try {
    const { limit = 20 } = req.query;

    const result = await pool.query(
      `SELECT symbol, jt_momentum, volatility, date
       FROM momentum_metrics
       ORDER BY jt_momentum ASC
       LIMIT $1`,
      [parseInt(limit)]
    );

    res.json({
      count: result.rows.length,
      data: result.rows.map(row => ({
        symbol: row.symbol,
        momentum: row.jt_momentum,
        volatility: row.volatility,
        date: row.date
      }))
    });
  } catch (error) {
    console.error('Error fetching momentum laggards:', error);
    res.status(500).json({ error: 'Failed to fetch momentum laggards' });
  }
});

/**
 * GET /api/momentum/metrics
 * Get aggregate momentum statistics
 */
router.get('/metrics', async (req, res) => {
  try {
    const result = await pool.query(
      `SELECT
        COUNT(*) as total_symbols,
        AVG(jt_momentum) as avg_momentum,
        MIN(jt_momentum) as min_momentum,
        MAX(jt_momentum) as max_momentum,
        AVG(volatility) as avg_volatility,
        MAX(volatility) as max_volatility
       FROM momentum_metrics`
    );

    const stats = result.rows[0];
    res.json({
      total_symbols: parseInt(stats.total_symbols),
      avg_momentum: parseFloat(stats.avg_momentum || 0).toFixed(4),
      min_momentum: parseFloat(stats.min_momentum || 0).toFixed(4),
      max_momentum: parseFloat(stats.max_momentum || 0).toFixed(4),
      avg_volatility: parseFloat(stats.avg_volatility || 0).toFixed(4),
      max_volatility: parseFloat(stats.max_volatility || 0).toFixed(4)
    });
  } catch (error) {
    console.error('Error fetching momentum metrics:', error);
    res.status(500).json({ error: 'Failed to fetch momentum metrics' });
  }
});

/**
 * GET /api/momentum/range
 * Get stocks within momentum range
 */
router.get('/range', async (req, res) => {
  try {
    const { min = -1, max = 1, limit = 100 } = req.query;

    const result = await pool.query(
      `SELECT symbol, jt_momentum, volatility, date
       FROM momentum_metrics
       WHERE jt_momentum >= $1 AND jt_momentum <= $2
       ORDER BY jt_momentum DESC
       LIMIT $3`,
      [parseFloat(min), parseFloat(max), parseInt(limit)]
    );

    res.json({
      range: { min: parseFloat(min), max: parseFloat(max) },
      count: result.rows.length,
      data: result.rows.map(row => ({
        symbol: row.symbol,
        momentum: parseFloat(row.jt_momentum).toFixed(4),
        volatility: row.volatility,
        date: row.date
      }))
    });
  } catch (error) {
    console.error('Error fetching momentum range:', error);
    res.status(500).json({ error: 'Failed to fetch momentum range' });
  }
});

module.exports = router;
