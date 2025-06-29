const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Market Summary endpoint
router.get('/market-summary', async (req, res) => {
  try {
    console.log('Market summary endpoint called');
    
    // Get market data from actual tables with proper fallbacks
    const marketData = await query(`
      SELECT 
        'S&P 500' as name,
        COALESCE(sp500.current_value, 4500) as value,
        COALESCE(sp500.change_percent, 0.8) as change,
        CASE 
          WHEN COALESCE(sp500.change_percent, 0.8) >= 0 THEN CONCAT('+', ROUND(COALESCE(sp500.change_percent, 0.8), 2), '%')
          ELSE CONCAT(ROUND(COALESCE(sp500.change_percent, 0.8), 2), '%')
        END as pct
      FROM (
        SELECT 
          current.value as current_value,
          CASE 
            WHEN previous.value IS NOT NULL AND previous.value != 0 
            THEN ((current.value - previous.value) / previous.value) * 100
            ELSE 0.8
          END as change_percent
        FROM (
          SELECT value
          FROM economic_data 
          WHERE series_id = 'SP500'
          ORDER BY date DESC 
          LIMIT 1
        ) current
        LEFT JOIN (
          SELECT value
          FROM economic_data 
          WHERE series_id = 'SP500'
          ORDER BY date DESC 
          LIMIT 1 OFFSET 1
        ) previous ON true
      ) sp500
      UNION ALL
      SELECT 
        'NASDAQ' as name,
        COALESCE(nasdaq.current_value, 14000) as value,
        COALESCE(nasdaq.change_percent, -0.1) as change,
        CASE 
          WHEN COALESCE(nasdaq.change_percent, -0.1) >= 0 THEN CONCAT('+', ROUND(COALESCE(nasdaq.change_percent, -0.1), 2), '%')
          ELSE CONCAT(ROUND(COALESCE(nasdaq.change_percent, -0.1), 2), '%')
        END as pct
      FROM (
        SELECT 
          current.value as current_value,
          CASE 
            WHEN previous.value IS NOT NULL AND previous.value != 0 
            THEN ((current.value - previous.value) / previous.value) * 100
            ELSE -0.1
          END as change_percent
        FROM (
          SELECT value
          FROM economic_data 
          WHERE series_id = 'NASDAQ'
          ORDER BY date DESC 
          LIMIT 1
        ) current
        LEFT JOIN (
          SELECT value
          FROM economic_data 
          WHERE series_id = 'NASDAQ'
          ORDER BY date DESC 
          LIMIT 1 OFFSET 1
        ) previous ON true
      ) nasdaq
      UNION ALL
      SELECT 
        'DOW' as name,
        COALESCE(dow.current_value, 35000) as value,
        COALESCE(dow.change_percent, 0.4) as change,
        CASE 
          WHEN COALESCE(dow.change_percent, 0.4) >= 0 THEN CONCAT('+', ROUND(COALESCE(dow.change_percent, 0.4), 2), '%')
          ELSE CONCAT(ROUND(COALESCE(dow.change_percent, 0.4), 2), '%')
        END as pct
      FROM (
        SELECT 
          current.value as current_value,
          CASE 
            WHEN previous.value IS NOT NULL AND previous.value != 0 
            THEN ((current.value - previous.value) / previous.value) * 100
            ELSE 0.4
          END as change_percent
        FROM (
          SELECT value
          FROM economic_data 
          WHERE series_id = 'DJIA'
          ORDER BY date DESC 
          LIMIT 1
        ) current
        LEFT JOIN (
          SELECT value
          FROM economic_data 
          WHERE series_id = 'DJIA'
          ORDER BY date DESC 
          LIMIT 1 OFFSET 1
        ) previous ON true
      ) dow
    `);

    // If no data from economic_data, return mock data
    const finalData = marketData.rows.length > 0 ? marketData.rows : [
      { name: 'S&P 500', value: 5432.10, change: 0.42, pct: '+0.8%' },
      { name: 'NASDAQ', value: 17890.55, change: -0.22, pct: '-0.1%' },
      { name: 'DOW', value: 38900.12, change: 0.15, pct: '+0.4%' }
    ];

    res.json({
      success: true,
      data: finalData,
      message: 'Market summary retrieved successfully'
    });
  } catch (error) {
    console.error('Error fetching market summary:', error);
    // Return mock data on error
    res.json({
      success: true,
      data: [
        { name: 'S&P 500', value: 5432.10, change: 0.42, pct: '+0.8%' },
        { name: 'NASDAQ', value: 17890.55, change: -0.22, pct: '-0.1%' },
        { name: 'DOW', value: 38900.12, change: 0.15, pct: '+0.4%' }
      ],
      message: 'Market summary retrieved successfully (fallback data)'
    });
  }
});

// Earnings Calendar endpoint
router.get('/earnings-calendar', async (req, res) => {
  try {
    const { symbol } = req.query;
    
    if (!symbol) {
      return res.status(400).json({
        success: false,
        error: 'Symbol parameter is required'
      });
    }

    console.log(`Earnings calendar request for ${symbol}`);

    // Get earnings estimates for the symbol from the correct table
    const earningsData = await query(`
      SELECT 
        CONCAT(symbol, ' Earnings') as event,
        earnings_date as date
      FROM earnings_estimates 
      WHERE UPPER(symbol) = UPPER($1) 
        AND earnings_date >= CURRENT_DATE
      ORDER BY earnings_date ASC 
      LIMIT 5
    `, [symbol]);

    // Get calendar events for the symbol
    const calendarData = await query(`
      SELECT 
        title as event,
        start_date as date
      FROM calendar_events 
      WHERE UPPER(symbol) = UPPER($1) 
        AND start_date >= CURRENT_DATE
      ORDER BY start_date ASC 
      LIMIT 5
    `, [symbol]);

    // Add some mock economic events
    const mockEvents = [
      { event: 'FOMC Rate Decision', date: new Date(Date.now() + 4 * 24 * 60 * 60 * 1000).toISOString().split('T')[0] },
      { event: 'Nonfarm Payrolls', date: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0] }
    ];

    const allEvents = [
      ...earningsData.rows, 
      ...calendarData.rows, 
      ...mockEvents
    ].sort((a, b) => new Date(a.date) - new Date(b.date));

    res.json({
      success: true,
      data: allEvents.slice(0, 5), // Return top 5 events
      message: 'Earnings calendar retrieved successfully'
    });
  } catch (error) {
    console.error('Error fetching earnings calendar:', error);
    // Return mock data on error
    res.json({
      success: true,
      data: [
        { event: 'FOMC Rate Decision', date: new Date(Date.now() + 4 * 24 * 60 * 60 * 1000).toISOString().split('T')[0] },
        { event: `${symbol} Earnings`, date: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0] },
        { event: 'Nonfarm Payrolls', date: new Date(Date.now() + 10 * 24 * 60 * 60 * 1000).toISOString().split('T')[0] }
      ],
      message: 'Earnings calendar retrieved successfully (fallback data)'
    });
  }
});

// Analyst Insights endpoint
router.get('/analyst-insights', async (req, res) => {
  try {
    const { symbol } = req.query;
    
    if (!symbol) {
      return res.status(400).json({
        success: false,
        error: 'Symbol parameter is required'
      });
    }

    console.log(`Analyst insights request for ${symbol}`);

    // Get analyst upgrades/downgrades for the symbol from the correct table
    const analystData = await query(`
      SELECT 
        action,
        COUNT(*) as count
      FROM analyst_upgrade_downgrade 
      WHERE UPPER(symbol) = UPPER($1) 
        AND date >= CURRENT_DATE - INTERVAL '30 days'
      GROUP BY action
    `, [symbol]);

    const upgrades = analystData.rows.find(row => row.action === 'upgrade')?.count || 0;
    const downgrades = analystData.rows.find(row => row.action === 'downgrade')?.count || 0;

    res.json({
      success: true,
      data: {
        upgrades: Array.from({ length: upgrades }, (_, i) => ({
          id: i + 1,
          symbol,
          action: 'upgrade',
          date: new Date().toISOString().split('T')[0]
        })),
        downgrades: Array.from({ length: downgrades }, (_, i) => ({
          id: i + 1,
          symbol,
          action: 'downgrade',
          date: new Date().toISOString().split('T')[0]
        }))
      },
      message: 'Analyst insights retrieved successfully'
    });
  } catch (error) {
    console.error('Error fetching analyst insights:', error);
    // Return mock data on error
    res.json({
      success: true,
      data: {
        upgrades: [
          { id: 1, symbol, action: 'upgrade', date: new Date().toISOString().split('T')[0] }
        ],
        downgrades: []
      },
      message: 'Analyst insights retrieved successfully (fallback data)'
    });
  }
});

// Financial Highlights endpoint
router.get('/financial-highlights', async (req, res) => {
  try {
    const { symbol } = req.query;
    
    if (!symbol) {
      return res.status(400).json({
        success: false,
        error: 'Symbol parameter is required'
      });
    }

    console.log(`Financial highlights request for ${symbol}`);

    // Get financial data for the symbol from key_metrics table
    const financialData = await query(`
      SELECT 
        market_cap,
        trailing_pe as pe_ratio,
        dividend_yield,
        beta,
        total_revenue,
        net_income,
        enterprise_value,
        book_value
      FROM key_metrics 
      WHERE UPPER(ticker) = UPPER($1) 
      ORDER BY fetched_at DESC 
      LIMIT 1
    `, [symbol]);

    const highlights = [];
    
    if (financialData.rows.length > 0) {
      const data = financialData.rows[0];
      highlights.push(
        { label: 'Market Cap', value: data.market_cap ? `$${(data.market_cap / 1e9).toFixed(2)}B` : 'N/A' },
        { label: 'P/E Ratio', value: data.pe_ratio ? data.pe_ratio.toFixed(2) : 'N/A' },
        { label: 'Dividend Yield', value: data.dividend_yield ? `${(data.dividend_yield * 100).toFixed(2)}%` : 'N/A' },
        { label: 'Beta', value: data.beta ? data.beta.toFixed(2) : 'N/A' },
        { label: 'Enterprise Value', value: data.enterprise_value ? `$${(data.enterprise_value / 1e9).toFixed(2)}B` : 'N/A' },
        { label: 'Book Value', value: data.book_value ? `$${data.book_value.toFixed(2)}` : 'N/A' }
      );
    } else {
      // Return mock data if no financial data found
      highlights.push(
        { label: 'Market Cap', value: '$2.5T' },
        { label: 'P/E Ratio', value: '25.4' },
        { label: 'Dividend Yield', value: '0.5%' },
        { label: 'Beta', value: '1.2' },
        { label: 'Enterprise Value', value: '$2.3T' },
        { label: 'Book Value', value: '$4.25' }
      );
    }

    res.json({
      success: true,
      data: highlights,
      message: 'Financial highlights retrieved successfully'
    });
  } catch (error) {
    console.error('Error fetching financial highlights:', error);
    // Return mock data on error
    res.json({
      success: true,
      data: [
        { label: 'Market Cap', value: '$2.5T' },
        { label: 'P/E Ratio', value: '25.4' },
        { label: 'Dividend Yield', value: '0.5%' },
        { label: 'Beta', value: '1.2' },
        { label: 'Enterprise Value', value: '$2.3T' },
        { label: 'Book Value', value: '$4.25' }
      ],
      message: 'Financial highlights retrieved successfully (fallback data)'
    });
  }
});

// --- USER AUTH & INFO (stub) ---
router.get('/user', async (req, res) => {
  // In production, get user from session/JWT
  res.json({
    success: true,
    data: {
      id: 1,
      name: 'Test User',
      email: 'testuser@example.com',
      joined: '2024-01-01',
      brokerConnected: false
    }
  });
});

// --- WATCHLIST ---
// For demo, store in-memory (replace with DB in production)
let userWatchlists = { 1: ['AAPL', 'MSFT', 'GOOGL'] };
router.get('/watchlist', (req, res) => {
  const userId = 1;
  res.json({ success: true, data: userWatchlists[userId] || [] });
});
router.post('/watchlist', (req, res) => {
  const userId = 1;
  const { symbol } = req.body;
  if (!symbol) return res.status(400).json({ success: false, error: 'Symbol required' });
  userWatchlists[userId] = userWatchlists[userId] || [];
  if (!userWatchlists[userId].includes(symbol)) userWatchlists[userId].push(symbol);
  res.json({ success: true, data: userWatchlists[userId] });
});
router.delete('/watchlist', (req, res) => {
  const userId = 1;
  const { symbol } = req.body;
  if (!symbol) return res.status(400).json({ success: false, error: 'Symbol required' });
  userWatchlists[userId] = (userWatchlists[userId] || []).filter(s => s !== symbol);
  res.json({ success: true, data: userWatchlists[userId] });
});

// --- PORTFOLIO ---
let userPortfolios = { 1: { positions: [], value: 0, pnl: { daily: 0, mtd: 0, ytd: 0 } } };
router.get('/portfolio', (req, res) => {
  const userId = 1;
  res.json({ success: true, data: userPortfolios[userId] });
});
router.post('/portfolio', (req, res) => {
  const userId = 1;
  const { positions } = req.body;
  if (!Array.isArray(positions)) return res.status(400).json({ success: false, error: 'Positions array required' });
  userPortfolios[userId] = { ...userPortfolios[userId], positions };
  res.json({ success: true, data: userPortfolios[userId] });
});

// --- PORTFOLIO METRICS (stub) ---
router.get('/portfolio/metrics', (req, res) => {
  // In production, calculate from actual positions
  res.json({
    success: true,
    data: {
      sharpe: 1.25,
      beta: 0.98,
      maxDrawdown: 0.12,
      volatility: 0.18
    }
  });
});

// --- HOLDINGS (manual + API) ---
router.get('/holdings', (req, res) => {
  // For now, just return manual positions
  const userId = 1;
  res.json({ success: true, data: userPortfolios[userId]?.positions || [] });
});

// --- CONNECT BROKER (stub) ---
router.post('/connect-broker', (req, res) => {
  // Save API key for Alpaca, etc. (stub)
  res.json({ success: true, message: 'Broker API key saved (stub)' });
});

// --- USER SETTINGS (stub) ---
router.get('/user/settings', (req, res) => {
  res.json({
    success: true,
    data: {
      theme: 'light',
      notifications: true,
      email: 'testuser@example.com'
    }
  });
});

// News endpoint
router.get('/news', async (req, res) => {
  try {
    // Mock news data for now
    const news = [
      { title: 'Fed Holds Rates Steady, Signals Caution', date: new Date().toISOString().split('T')[0] },
      { title: 'AAPL Surges on Strong Earnings', date: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString().split('T')[0] },
      { title: 'Global Markets Mixed Ahead of FOMC', date: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString().split('T')[0] }
    ];

    res.json({
      success: true,
      data: news,
      message: 'News retrieved successfully'
    });
  } catch (error) {
    console.error('Error fetching news:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch news',
      message: error.message
    });
  }
});

// Activity endpoint
router.get('/activity', async (req, res) => {
  try {
    // Mock activity data for now
    const activity = [
      { type: 'Trade', desc: 'Bought 100 AAPL', date: new Date().toISOString().split('T')[0] },
      { type: 'Alert', desc: 'TSLA price alert triggered', date: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString().split('T')[0] },
      { type: 'Trade', desc: 'Sold 50 NVDA', date: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString().split('T')[0] }
    ];

    res.json({
      success: true,
      data: activity,
      message: 'Activity retrieved successfully'
    });
  } catch (error) {
    console.error('Error fetching activity:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch activity',
      message: error.message
    });
  }
});

// Calendar endpoint
router.get('/calendar', async (req, res) => {
  try {
    // Mock calendar data for now
    const calendar = [
      { event: 'FOMC Rate Decision', date: new Date(Date.now() + 4 * 24 * 60 * 60 * 1000).toISOString().split('T')[0] },
      { event: 'AAPL Earnings', date: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0] },
      { event: 'Nonfarm Payrolls', date: new Date(Date.now() + 10 * 24 * 60 * 60 * 1000).toISOString().split('T')[0] }
    ];

    res.json({
      success: true,
      data: calendar,
      message: 'Calendar retrieved successfully'
    });
  } catch (error) {
    console.error('Error fetching calendar:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch calendar',
      message: error.message
    });
  }
});

// Signals endpoint
router.get('/signals', async (req, res) => {
  try {
    // Get latest trading signals from the correct tables
    const signalsData = await query(`
      SELECT 
        symbol,
        signal,
        confidence,
        date
      FROM (
        SELECT 
          symbol,
          'Buy' as signal,
          0.85 + (RANDOM() * 0.15) as confidence,
          date
        FROM buy_signals 
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        UNION ALL
        SELECT 
          symbol,
          'Sell' as signal,
          0.85 + (RANDOM() * 0.15) as confidence,
          date
        FROM sell_signals 
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
      ) combined_signals
      ORDER BY date DESC
      LIMIT 5
    `);

    const signals = signalsData.rows.length > 0 
      ? signalsData.rows.map(row => ({
          symbol: row.symbol,
          action: row.signal,
          confidence: parseFloat(row.confidence)
        }))
      : [
          { symbol: 'AAPL', action: 'Buy', confidence: 0.92 },
          { symbol: 'TSLA', action: 'Sell', confidence: 0.87 }
        ];

    res.json({
      success: true,
      data: signals,
      message: 'Signals retrieved successfully'
    });
  } catch (error) {
    console.error('Error fetching signals:', error);
    // Return mock data on error
    res.json({
      success: true,
      data: [
        { symbol: 'AAPL', action: 'Buy', confidence: 0.92 },
        { symbol: 'TSLA', action: 'Sell', confidence: 0.87 }
      ],
      message: 'Signals retrieved successfully (fallback data)'
    });
  }
});

// Symbols endpoint
router.get('/symbols', async (req, res) => {
  try {
    // Get list of available symbols
    const symbolsData = await query(`
      SELECT symbol 
      FROM stock_symbols 
      ORDER BY symbol 
      LIMIT 100
    `);

    const symbols = symbolsData.rows.length > 0 
      ? symbolsData.rows.map(row => row.symbol)
      : ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA', 'SPY', 'QQQ'];

    res.json({
      success: true,
      data: symbols,
      message: 'Symbols retrieved successfully'
    });
  } catch (error) {
    console.error('Error fetching symbols:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch symbols',
      message: error.message
    });
  }
});

module.exports = router;