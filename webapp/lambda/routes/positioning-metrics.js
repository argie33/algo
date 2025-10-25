const express = require('express');
const router = express.Router();
const pool = require('../db');

/**
 * Positioning Metrics Routes
 * Provides institutional ownership, insider ownership, short interest, etc.
 */

/**
 * GET /api/positioning/stocks/:symbol
 * Get positioning metrics for a single stock
 */
router.get('/stocks/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;

    const result = await pool.query(
      `SELECT
        symbol,
        date,
        institutional_ownership_pct,
        top_10_institutions_pct,
        institutional_holders_count,
        insider_ownership_pct,
        short_ratio,
        short_interest_pct
       FROM positioning_metrics
       WHERE symbol = $1
       ORDER BY date DESC
       LIMIT 1`,
      [symbol.toUpperCase()]
    );

    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'No positioning data found for symbol', symbol });
    }

    const row = result.rows[0];
    res.json({
      symbol: row.symbol,
      date: row.date,
      institutional_ownership: parseFloat(row.institutional_ownership_pct || 0).toFixed(2),
      top_10_institutions: parseFloat(row.top_10_institutions_pct || 0).toFixed(2),
      institutional_holders: parseInt(row.institutional_holders_count || 0),
      insider_ownership: parseFloat(row.insider_ownership_pct || 0).toFixed(2),
      short_ratio: parseFloat(row.short_ratio || 0).toFixed(2),
      short_interest: parseFloat(row.short_interest_pct || 0).toFixed(2)
    });
  } catch (error) {
    console.error('Error fetching positioning:', error);
    res.status(500).json({ error: 'Failed to fetch positioning data' });
  }
});

/**
 * GET /api/positioning/institutional-holders
 * Get stocks sorted by institutional ownership
 */
router.get('/institutional-holders', async (req, res) => {
  try {
    const { limit = 50, minOwnership = 0 } = req.query;

    const result = await pool.query(
      `SELECT
        symbol,
        institutional_ownership_pct,
        institutional_holders_count,
        date
       FROM positioning_metrics
       WHERE institutional_ownership_pct >= $1
       ORDER BY institutional_ownership_pct DESC
       LIMIT $2`,
      [parseFloat(minOwnership), parseInt(limit)]
    );

    res.json({
      count: result.rows.length,
      data: result.rows.map(row => ({
        symbol: row.symbol,
        institutional_ownership: parseFloat(row.institutional_ownership_pct || 0).toFixed(2),
        institutional_holders: parseInt(row.institutional_holders_count || 0),
        date: row.date
      }))
    });
  } catch (error) {
    console.error('Error fetching institutional holders:', error);
    res.status(500).json({ error: 'Failed to fetch institutional holders data' });
  }
});

/**
 * GET /api/positioning/insider-ownership
 * Get stocks with highest insider ownership
 */
router.get('/insider-ownership', async (req, res) => {
  try {
    const { limit = 50, minOwnership = 0 } = req.query;

    const result = await pool.query(
      `SELECT
        symbol,
        insider_ownership_pct,
        date
       FROM positioning_metrics
       WHERE insider_ownership_pct >= $1
       ORDER BY insider_ownership_pct DESC
       LIMIT $2`,
      [parseFloat(minOwnership), parseInt(limit)]
    );

    res.json({
      count: result.rows.length,
      data: result.rows.map(row => ({
        symbol: row.symbol,
        insider_ownership: parseFloat(row.insider_ownership_pct || 0).toFixed(2),
        date: row.date
      }))
    });
  } catch (error) {
    console.error('Error fetching insider ownership:', error);
    res.status(500).json({ error: 'Failed to fetch insider ownership data' });
  }
});

/**
 * GET /api/positioning/short-interest
 * Get stocks sorted by short interest
 */
router.get('/short-interest', async (req, res) => {
  try {
    const { limit = 50, minShort = 0 } = req.query;

    const result = await pool.query(
      `SELECT
        symbol,
        short_interest_pct,
        short_ratio,
        date
       FROM positioning_metrics
       WHERE short_interest_pct >= $1
       ORDER BY short_interest_pct DESC
       LIMIT $2`,
      [parseFloat(minShort), parseInt(limit)]
    );

    res.json({
      count: result.rows.length,
      data: result.rows.map(row => ({
        symbol: row.symbol,
        short_interest: parseFloat(row.short_interest_pct || 0).toFixed(2),
        short_ratio: parseFloat(row.short_ratio || 0).toFixed(2),
        date: row.date
      }))
    });
  } catch (error) {
    console.error('Error fetching short interest:', error);
    res.status(500).json({ error: 'Failed to fetch short interest data' });
  }
});

/**
 * GET /api/positioning/metrics
 * Get aggregate positioning statistics
 */
router.get('/metrics', async (req, res) => {
  try {
    const result = await pool.query(
      `SELECT
        COUNT(*) as total_symbols,
        AVG(institutional_ownership_pct) as avg_institutional,
        AVG(insider_ownership_pct) as avg_insider,
        AVG(short_interest_pct) as avg_short,
        MAX(institutional_ownership_pct) as max_institutional,
        MAX(short_interest_pct) as max_short
       FROM positioning_metrics
       WHERE institutional_ownership_pct IS NOT NULL`
    );

    const stats = result.rows[0];
    res.json({
      total_symbols: parseInt(stats.total_symbols || 0),
      avg_institutional_ownership: parseFloat(stats.avg_institutional || 0).toFixed(2),
      avg_insider_ownership: parseFloat(stats.avg_insider || 0).toFixed(2),
      avg_short_interest: parseFloat(stats.avg_short || 0).toFixed(2),
      max_institutional_ownership: parseFloat(stats.max_institutional || 0).toFixed(2),
      max_short_interest: parseFloat(stats.max_short || 0).toFixed(2)
    });
  } catch (error) {
    console.error('Error fetching positioning metrics:', error);
    res.status(500).json({ error: 'Failed to fetch positioning metrics' });
  }
});

/**
 * GET /api/positioning/comparison
 * Compare positioning between multiple stocks
 */
router.get('/comparison', async (req, res) => {
  try {
    const { symbols } = req.query;

    if (!symbols) {
      return res.status(400).json({ error: 'symbols query parameter required (comma-separated)' });
    }

    const symbolList = symbols.split(',').map(s => s.toUpperCase().trim());

    const result = await pool.query(
      `SELECT
        symbol,
        institutional_ownership_pct,
        insider_ownership_pct,
        short_interest_pct,
        date
       FROM positioning_metrics
       WHERE symbol = ANY($1)
       ORDER BY symbol`,
      [symbolList]
    );

    res.json({
      count: result.rows.length,
      requested: symbolList.length,
      found: result.rows.length,
      data: result.rows.map(row => ({
        symbol: row.symbol,
        institutional_ownership: parseFloat(row.institutional_ownership_pct || 0).toFixed(2),
        insider_ownership: parseFloat(row.insider_ownership_pct || 0).toFixed(2),
        short_interest: parseFloat(row.short_interest_pct || 0).toFixed(2),
        date: row.date
      }))
    });
  } catch (error) {
    console.error('Error comparing positioning:', error);
    res.status(500).json({ error: 'Failed to compare positioning data' });
  }
});

module.exports = router;
