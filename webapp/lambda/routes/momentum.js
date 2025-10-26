const express = require('express');
const router = express.Router();
const pool = require('../utils/database');

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
      'SELECT symbol, date, jt_momentum_12_1, jt_momentum_volatility, risk_adjusted_momentum FROM momentum_metrics WHERE symbol = $1 ORDER BY date DESC LIMIT 1',
      [symbol.toUpperCase()]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'No momentum data found for symbol', symbol });
    }

    res.json({
      symbol: result.rows[0].symbol,
      momentum_12_1: parseFloat(result.rows[0].jt_momentum_12_1 || 0).toFixed(4),
      volatility: parseFloat(result.rows[0].jt_momentum_volatility || 0).toFixed(4),
      risk_adjusted_momentum: parseFloat(result.rows[0].risk_adjusted_momentum || 0).toFixed(4),
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
      `SELECT symbol, jt_momentum_12_1, jt_momentum_volatility, date
       FROM momentum_metrics
       WHERE jt_momentum_12_1 > $1
       ORDER BY jt_momentum_12_1 DESC
       LIMIT $2`,
      [minVol, parseInt(limit)]
    );

    res.json({
      count: result.rows.length,
      data: result.rows.map(row => ({
        symbol: row.symbol,
        momentum_12_1: parseFloat(row.jt_momentum_12_1 || 0).toFixed(4),
        volatility: parseFloat(row.jt_momentum_volatility || 0).toFixed(4),
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
      `SELECT symbol, jt_momentum_12_1, jt_momentum_volatility, date
       FROM momentum_metrics
       ORDER BY jt_momentum_12_1 ASC
       LIMIT $1`,
      [parseInt(limit)]
    );

    res.json({
      count: result.rows.length,
      data: result.rows.map(row => ({
        symbol: row.symbol,
        momentum_12_1: parseFloat(row.jt_momentum_12_1 || 0).toFixed(4),
        volatility: parseFloat(row.jt_momentum_volatility || 0).toFixed(4),
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
        AVG(jt_momentum_12_1) as avg_momentum,
        MIN(jt_momentum_12_1) as min_momentum,
        MAX(jt_momentum_12_1) as max_momentum,
        AVG(jt_momentum_volatility) as avg_volatility,
        MAX(jt_momentum_volatility) as max_volatility
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
      `SELECT symbol, jt_momentum_12_1, jt_momentum_volatility, date
       FROM momentum_metrics
       WHERE jt_momentum_12_1 >= $1 AND jt_momentum_12_1 <= $2
       ORDER BY jt_momentum_12_1 DESC
       LIMIT $3`,
      [parseFloat(min), parseFloat(max), parseInt(limit)]
    );

    res.json({
      range: { min: parseFloat(min), max: parseFloat(max) },
      count: result.rows.length,
      data: result.rows.map(row => ({
        symbol: row.symbol,
        momentum_12_1: parseFloat(row.jt_momentum_12_1).toFixed(4),
        volatility: parseFloat(row.jt_momentum_volatility).toFixed(4),
        date: row.date
      }))
    });
  } catch (error) {
    console.error('Error fetching momentum range:', error);
    res.status(500).json({ error: 'Failed to fetch momentum range' });
  }
});

module.exports = router;
