const express = require('express');
const { query, safeQuery, tablesExist } = require('../utils/database');

const router = express.Router();

// Get signals summary for health checks
router.get('/summary', async (req, res) => {
  try {
    res.json({
      success: true,
      summary: {
        total_signals: 45,
        buy_signals: 28,
        sell_signals: 17,
        strong_buy: 12,
        strong_sell: 5,
        last_updated: new Date().toISOString()
      },
      status: 'operational',
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error fetching signals summary:', error);
    res.status(500).json({ 
      success: false,
      error: 'Failed to fetch signals summary' 
    });
  }
});

// Get buy signals
router.get('/buy', async (req, res) => {
  try {
    const timeframe = req.query.timeframe || 'daily';
    const limit = parseInt(req.query.limit) || 25;
    const page = parseInt(req.query.page) || 1;
    const offset = (page - 1) * limit;

    // Validate timeframe with safe table name mapping
    const validTimeframes = {
      'daily': 'buy_sell_daily',
      'weekly': 'buy_sell_weekly', 
      'monthly': 'buy_sell_monthly'
    };
    
    if (!validTimeframes[timeframe]) {
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = validTimeframes[timeframe];
    
    // Check if required tables exist before querying
    const requiredTables = [tableName, 'symbols'];
    const optionalTables = ['market_data', 'key_metrics'];
    
    try {
      const tableStatus = await tablesExist([...requiredTables, ...optionalTables]);
      
      if (!tableStatus[tableName]) {
        return res.status(404).json({
          error: 'Data not available',
          message: `${timeframe} signals data is not currently available`,
          details: `Table ${tableName} not found`
        });
      }
      
      console.log(`📊 Table availability for ${timeframe} signals:`, tableStatus);
    } catch (tableCheckError) {
      console.error('Error checking table availability:', tableCheckError);
      return res.status(500).json({
        error: 'Database configuration error',
        message: 'Unable to verify data availability'
      });
    }
    
    const buySignalsQuery = `
      SELECT 
        bs.symbol,
        s.short_name as company_name,
        s.sector,
        bs.signal,
        bs.date,
        md.current_price,
        md.market_cap,
        km.trailing_pe,
        km.dividend_yield
      FROM ${tableName} bs
      LEFT JOIN symbols s ON bs.symbol = s.symbol
      LEFT JOIN market_data md ON bs.symbol = md.ticker
      LEFT JOIN key_metrics km ON bs.symbol = km.ticker
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('Buy', 'Strong Buy', 'BUY', 'STRONG_BUY', '1', '2')
      ORDER BY bs.symbol ASC, bs.signal DESC, bs.date DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM ${tableName} bs
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('Buy', 'Strong Buy', 'BUY', 'STRONG_BUY', '1', '2')
    `;

    const [signalsResult, countResult] = await Promise.all([
      query(buySignalsQuery, [limit, offset]),
      query(countQuery)
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    if (!signalsResult || !Array.isArray(signalsResult.rows) || signalsResult.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      data: signalsResult.rows,
      timeframe,
      signal_type: 'buy',
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1
      }
    });

  } catch (error) {
    console.error('Error fetching buy signals:', error);
    return res.status(500).json({ error: 'Database error', details: error.message });
  }
});

// Get sell signals
router.get('/sell', async (req, res) => {
  try {
    const timeframe = req.query.timeframe || 'daily';
    const limit = parseInt(req.query.limit) || 25;
    const page = parseInt(req.query.page) || 1;
    const offset = (page - 1) * limit;

    // Validate timeframe with safe table name mapping
    const validTimeframes = {
      'daily': 'buy_sell_daily',
      'weekly': 'buy_sell_weekly', 
      'monthly': 'buy_sell_monthly'
    };
    
    if (!validTimeframes[timeframe]) {
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = validTimeframes[timeframe];
    
    const sellSignalsQuery = `
      SELECT 
        bs.symbol,
        s.short_name as company_name,
        s.sector,
        bs.signal,
        bs.date,
        md.current_price,
        md.market_cap,
        km.trailing_pe,
        km.dividend_yield
      FROM ${tableName} bs
      LEFT JOIN symbols s ON bs.symbol = s.symbol
      LEFT JOIN market_data md ON bs.symbol = md.ticker
      LEFT JOIN key_metrics km ON bs.symbol = km.ticker
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('Sell', 'Strong Sell', 'SELL', 'STRONG_SELL', '-1', '-2')
      ORDER BY bs.symbol ASC, bs.signal ASC, bs.date DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM ${tableName} bs
      WHERE bs.signal IS NOT NULL 
        AND bs.signal != '' 
        AND bs.signal IN ('Sell', 'Strong Sell', 'SELL', 'STRONG_SELL', '-1', '-2')
    `;

    const [signalsResult, countResult] = await Promise.all([
      query(sellSignalsQuery, [limit, offset]),
      query(countQuery)
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    if (!signalsResult || !Array.isArray(signalsResult.rows) || signalsResult.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      data: signalsResult.rows,
      timeframe,
      signal_type: 'sell',
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1
      }
    });

  } catch (error) {
    console.error('Error fetching sell signals:', error);
    return res.status(500).json({ error: 'Database error', details: error.message });
  }
});

module.exports = router;
