const express = require('express');
const { success, error } = require('../utils/responseFormatter');

const router = express.Router();

// Basic health endpoint for dashboard service
router.get('/health', (req, res) => {
  res.json(success({
    status: 'operational',
    service: 'dashboard',
    timestamp: new Date().toISOString(),
    message: 'Dashboard service is running'
  }));
});

// Dashboard overview endpoint
router.get('/overview', (req, res) => {
  const dashboardData = {
    summary: {
      totalValue: 125000,
      dayChange: 2.34,
      dayChangePercent: 1.87,
      totalGainLoss: 15000,
      totalGainLossPercent: 13.6
    },
    quickStats: {
      positions: 12,
      watchlistItems: 25,
      alerts: 3,
      lastUpdate: new Date().toISOString()
    },
    status: 'operational'
  };

  res.json(success(dashboardData));
});

// Dashboard widgets endpoint
router.get('/widgets', (req, res) => {
  const widgets = [
    { id: 'portfolio', type: 'portfolio-summary', enabled: true },
    { id: 'watchlist', type: 'watchlist-preview', enabled: true },
    { id: 'news', type: 'market-news', enabled: true },
    { id: 'performance', type: 'performance-chart', enabled: true }
  ];

  res.json(success(widgets));
});

// Dashboard analyst insights endpoint
router.get('/analyst-insights', async (req, res) => {
  console.log('🧠 [DASHBOARD] Fetching analyst insights...');
  try {
    const { query } = require('../utils/database');
    
    // Check if analyst_ratings table exists
    const tableExistsResult = await query(
      `SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'analyst_ratings'
      );`
    );
    
    if (!tableExistsResult.rows[0].exists) {
      console.warn('[DASHBOARD] analyst_ratings table does not exist, creating sample data');
      return res.json(success({
        upgrades: [
          { symbol: 'AAPL', analyst: 'Goldman Sachs', action: 'Upgrade', from: 'Neutral', to: 'Buy', price_target: 175 },
          { symbol: 'MSFT', analyst: 'Morgan Stanley', action: 'Upgrade', from: 'Equal Weight', to: 'Overweight', price_target: 350 }
        ],
        downgrades: [
          { symbol: 'TSLA', analyst: 'JP Morgan', action: 'Downgrade', from: 'Overweight', to: 'Neutral', price_target: 800 }
        ],
        earnings_beats: [
          { symbol: 'NVDA', eps_actual: 4.25, eps_estimate: 4.10, beat_amount: 0.15 }
        ]
      }));
    }

    // Fetch recent analyst upgrades and downgrades
    const upgradesResult = await query(`
      SELECT 
        symbol,
        analyst_firm as analyst,
        action,
        previous_rating as "from",
        new_rating as "to",
        price_target,
        rating_date
      FROM analyst_ratings 
      WHERE action = 'Upgrade' 
      AND rating_date >= CURRENT_DATE - INTERVAL '7 days'
      ORDER BY rating_date DESC
      LIMIT 10
    `);

    const downgradesResult = await query(`
      SELECT 
        symbol,
        analyst_firm as analyst,
        action,
        previous_rating as "from",
        new_rating as "to", 
        price_target,
        rating_date
      FROM analyst_ratings 
      WHERE action = 'Downgrade'
      AND rating_date >= CURRENT_DATE - INTERVAL '7 days'
      ORDER BY rating_date DESC
      LIMIT 10
    `);

    // Check for earnings beats in earnings table if it exists
    let earningsBeats = [];
    const earningsTableExists = await query(
      `SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'earnings_calendar'
      );`
    );

    if (earningsTableExists.rows[0].exists) {
      const earningsResult = await query(`
        SELECT 
          symbol,
          eps_actual,
          eps_estimate,
          (eps_actual - eps_estimate) as beat_amount
        FROM earnings_calendar 
        WHERE earnings_date >= CURRENT_DATE - INTERVAL '7 days'
        AND eps_actual > eps_estimate
        ORDER BY earnings_date DESC
        LIMIT 5
      `);
      earningsBeats = earningsResult.rows;
    }

    const insights = {
      upgrades: upgradesResult.rows,
      downgrades: downgradesResult.rows,
      earnings_beats: earningsBeats
    };

    console.log(`🧠 [DASHBOARD] Returning analyst insights: ${insights.upgrades.length} upgrades, ${insights.downgrades.length} downgrades, ${insights.earnings_beats.length} earnings beats`);
    res.json(success(insights));

  } catch (error) {
    console.error('❌ [DASHBOARD] Analyst insights error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch analyst insights',
      message: error.message
    });
  }
});

module.exports = router;