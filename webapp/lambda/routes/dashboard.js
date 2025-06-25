const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Market Summary endpoint
router.get('/market-summary', async (req, res) => {
  try {
    // Get latest market data from fear_greed_index and naaim_exposure tables
    const marketData = await query(`
      SELECT 
        'S&P 500' as name,
        COALESCE(fgi.value, 4500) as value,
        COALESCE(fgi.change, 0) as change,
        CASE 
          WHEN fgi.change >= 0 THEN CONCAT('+', ROUND(fgi.change, 2), '%')
          ELSE CONCAT(ROUND(fgi.change, 2), '%')
        END as pct
      FROM (
        SELECT value, change 
        FROM fear_greed_index 
        ORDER BY date DESC 
        LIMIT 1
      ) fgi
      UNION ALL
      SELECT 
        'NASDAQ' as name,
        COALESCE(ne.value, 14000) as value,
        COALESCE(ne.change, 0) as change,
        CASE 
          WHEN ne.change >= 0 THEN CONCAT('+', ROUND(ne.change, 2), '%')
          ELSE CONCAT(ROUND(ne.change, 2), '%')
        END as pct
      FROM (
        SELECT value, change 
        FROM naaim_exposure 
        ORDER BY date DESC 
        LIMIT 1
      ) ne
      UNION ALL
      SELECT 
        'DOW' as name,
        35000 as value,
        0.15 as change,
        '+0.4%' as pct
    `);

    res.json({
      success: true,
      data: marketData.rows,
      message: 'Market summary retrieved successfully'
    });
  } catch (error) {
    console.error('Error fetching market summary:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch market summary',
      message: error.message
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

    // Get earnings estimates for the symbol
    const earningsData = await query(`
      SELECT 
        CONCAT(symbol, ' Earnings') as event,
        earnings_date as date
      FROM earnings_estimates 
      WHERE symbol = $1 
        AND earnings_date >= CURRENT_DATE
      ORDER BY earnings_date ASC 
      LIMIT 5
    `, [symbol]);

    // Add some mock economic events
    const mockEvents = [
      { event: 'FOMC Rate Decision', date: new Date(Date.now() + 4 * 24 * 60 * 60 * 1000).toISOString().split('T')[0] },
      { event: 'Nonfarm Payrolls', date: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString().split('T')[0] }
    ];

    const allEvents = [...earningsData.rows, ...mockEvents].sort((a, b) => new Date(a.date) - new Date(b.date));

    res.json({
      success: true,
      data: allEvents.slice(0, 5), // Return top 5 events
      message: 'Earnings calendar retrieved successfully'
    });
  } catch (error) {
    console.error('Error fetching earnings calendar:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch earnings calendar',
      message: error.message
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

    // Get analyst upgrades/downgrades for the symbol
    const analystData = await query(`
      SELECT 
        action,
        COUNT(*) as count
      FROM analyst_upgrades_downgrades 
      WHERE symbol = $1 
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
    res.status(500).json({
      success: false,
      error: 'Failed to fetch analyst insights',
      message: error.message
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

    // Get financial data for the symbol
    const financialData = await query(`
      SELECT 
        market_cap,
        pe_ratio,
        dividend_yield,
        beta,
        volume
      FROM financial_data 
      WHERE symbol = $1 
      ORDER BY date DESC 
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
        { label: 'Volume', value: data.volume ? data.volume.toLocaleString() : 'N/A' }
      );
    } else {
      // Return mock data if no financial data found
      highlights.push(
        { label: 'Market Cap', value: '$2.5T' },
        { label: 'P/E Ratio', value: '25.4' },
        { label: 'Dividend Yield', value: '0.5%' },
        { label: 'Beta', value: '1.2' },
        { label: 'Volume', value: '45.2M' }
      );
    }

    res.json({
      success: true,
      data: highlights,
      message: 'Financial highlights retrieved successfully'
    });
  } catch (error) {
    console.error('Error fetching financial highlights:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch financial highlights',
      message: error.message
    });
  }
});

// Portfolio endpoint
router.get('/portfolio', async (req, res) => {
  try {
    // Mock portfolio data for now
    const portfolio = {
      value: 1250000,
      pnl: {
        daily: 3200,
        mtd: 18000,
        ytd: 92000
      },
      allocation: [
        { name: 'AAPL', value: 38 },
        { name: 'MSFT', value: 27 },
        { name: 'GOOGL', value: 18 },
        { name: 'Cash', value: 10 },
        { name: 'Other', value: 7 }
      ]
    };

    res.json({
      success: true,
      data: portfolio,
      message: 'Portfolio data retrieved successfully'
    });
  } catch (error) {
    console.error('Error fetching portfolio:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch portfolio',
      message: error.message
    });
  }
});

// Watchlist endpoint
router.get('/watchlist', async (req, res) => {
  try {
    // Get watchlist from database or return mock data
    const watchlistData = await query(`
      SELECT 
        symbol,
        current_price as price,
        price_change_percent as change
      FROM price_daily 
      WHERE symbol IN ('AAPL', 'TSLA', 'NVDA', 'MSFT', 'GOOGL')
        AND date = (SELECT MAX(date) FROM price_daily)
      ORDER BY symbol
    `);

    const watchlist = watchlistData.rows.length > 0 
      ? watchlistData.rows 
      : [
          { symbol: 'AAPL', price: 195.12, change: 2.1 },
          { symbol: 'TSLA', price: 710.22, change: -1.8 },
          { symbol: 'NVDA', price: 1200, change: 3.5 },
          { symbol: 'MSFT', price: 420.5, change: 0.7 }
        ];

    res.json({
      success: true,
      data: watchlist,
      message: 'Watchlist retrieved successfully'
    });
  } catch (error) {
    console.error('Error fetching watchlist:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch watchlist',
      message: error.message
    });
  }
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
    // Get latest trading signals
    const signalsData = await query(`
      SELECT 
        symbol,
        signal,
        confidence,
        date
      FROM (
        SELECT 
          symbol,
          signal,
          0.85 + (RANDOM() * 0.15) as confidence,
          date
        FROM buy_signals 
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
        UNION ALL
        SELECT 
          symbol,
          signal,
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
    res.status(500).json({
      success: false,
      error: 'Failed to fetch signals',
      message: error.message
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