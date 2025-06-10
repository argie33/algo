const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Get market overview with key indices and sentiment
router.get('/overview', async (req, res) => {
  try {
    // Get latest Fear & Greed index
    const fearGreedQuery = `
      SELECT value, value_text, timestamp
      FROM fear_greed_index 
      ORDER BY timestamp DESC 
      LIMIT 1
    `;

    // Get latest NAAIM sentiment
    const naaimQuery = `
      SELECT bullish_8100, bearish, average, week_ending
      FROM naaim_sentiment 
      ORDER BY week_ending DESC 
      LIMIT 1
    `;

    // Get top gainers today
    const gainersQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        md.regular_market_price,
        md.regular_market_change,
        md.regular_market_change_percent
      FROM company_profile cp
      JOIN market_data md ON cp.ticker = md.ticker
      WHERE md.regular_market_change_percent > 0
      ORDER BY md.regular_market_change_percent DESC
      LIMIT 10
    `;

    // Get top losers today  
    const losersQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        md.regular_market_price,
        md.regular_market_change,
        md.regular_market_change_percent
      FROM company_profile cp
      JOIN market_data md ON cp.ticker = md.ticker
      WHERE md.regular_market_change_percent < 0
      ORDER BY md.regular_market_change_percent ASC
      LIMIT 10
    `;

    // Get most active stocks by volume
    const activeQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        md.regular_market_price,
        md.regular_market_change_percent,
        pd.volume
      FROM company_profile cp
      JOIN market_data md ON cp.ticker = md.ticker
      JOIN price_daily pd ON cp.ticker = pd.symbol
      WHERE pd.date = (SELECT MAX(date) FROM price_daily WHERE symbol = cp.ticker)
      ORDER BY pd.volume DESC
      LIMIT 10
    `;

    const [fearGreedResult, naaimResult, gainersResult, losersResult, activeResult] = await Promise.all([
      query(fearGreedQuery),
      query(naaimQuery), 
      query(gainersQuery),
      query(losersQuery),
      query(activeQuery)
    ]);

    res.json({
      sentiment: {
        fearGreed: fearGreedResult.rows[0] || null,
        naaim: naaimResult.rows[0] || null
      },
      movers: {
        gainers: gainersResult.rows,
        losers: losersResult.rows,
        mostActive: activeResult.rows
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching market overview:', error);
    res.status(500).json({ error: 'Failed to fetch market overview' });
  }
});

// Get economic indicators history
router.get('/sentiment/history', async (req, res) => {
  try {
    const days = parseInt(req.query.days) || 30;
    
    const fearGreedQuery = `
      SELECT value, value_text, timestamp
      FROM fear_greed_index 
      WHERE timestamp >= NOW() - INTERVAL '${days} days'
      ORDER BY timestamp DESC
    `;

    const naaimQuery = `
      SELECT bullish_8100, bearish, average, week_ending
      FROM naaim_sentiment 
      WHERE week_ending >= NOW() - INTERVAL '${days} days'
      ORDER BY week_ending DESC
    `;

    const [fearGreedResult, naaimResult] = await Promise.all([
      query(fearGreedQuery),
      query(naaimQuery)
    ]);

    res.json({
      fearGreed: fearGreedResult.rows,
      naaim: naaimResult.rows
    });

  } catch (error) {
    console.error('Error fetching sentiment history:', error);
    res.status(500).json({ error: 'Failed to fetch sentiment history' });
  }
});

// Get sector performance
router.get('/sectors', async (req, res) => {
  try {
    const sectorQuery = `
      SELECT 
        cp.sector,
        COUNT(*) as stock_count,
        AVG(md.regular_market_change_percent) as avg_change,
        AVG(km.trailing_pe) as avg_pe,
        SUM(cp.market_cap) as total_market_cap
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      WHERE cp.sector IS NOT NULL
      GROUP BY cp.sector
      ORDER BY avg_change DESC
    `;

    const result = await query(sectorQuery);

    res.json({
      sectors: result.rows,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching sector performance:', error);
    res.status(500).json({ error: 'Failed to fetch sector performance' });
  }
});

module.exports = router;
