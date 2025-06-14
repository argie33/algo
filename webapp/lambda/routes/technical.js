const express = require('express');
const router = express.Router();
const { query } = require('../utils/database');

// Health check endpoint
router.get('/health', async (req, res) => {
  try {
    const tables = ['technical_data_daily', 'technical_data_weekly', 'technical_data_monthly'];
    const status = {};
    
    for (const table of tables) {
      try {
        const result = await query(`SELECT COUNT(*) as count FROM ${table} LIMIT 1`);
        status[table] = {
          exists: true,
          count: result.rows[0]?.count || 0
        };
      } catch (error) {
        status[table] = {
          exists: false,
          error: error.message
        };
      }
    }
    
    res.json({
      status: 'OK',
      tables: status,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    res.status(500).json({
      status: 'ERROR',
      error: error.message
    });
  }
});

// Get technical data by timeframe
router.get('/:timeframe', async (req, res) => {
  try {
    const { timeframe } = req.params;
    const { limit = 25, symbol, page = 1 } = req.query; // Reduced default limit

    // Validate timeframe
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = `technical_data_${timeframe}`;
    const offset = (parseInt(page) - 1) * parseInt(limit);
    
    // First, check if table exists and has data
    const tableCheckQuery = `
      SELECT COUNT(*) as count FROM ${tableName} LIMIT 1
    `;
    
    let tableCheck;
    try {
      tableCheck = await query(tableCheckQuery);
    } catch (tableError) {
      console.error(`Table ${tableName} does not exist:`, tableError.message);
      return res.status(404).json({ 
        error: `Technical data table for ${timeframe} timeframe not found`,
        timeframe 
      });
    }

    let sqlQuery;
    let queryParams;

    if (symbol) {
      // If symbol specified, get historical data for that symbol with pagination
      sqlQuery = `
        SELECT 
          symbol,
          date,
          rsi,
          macd,
          macd_signal,
          macd_hist,
          mom,
          roc,
          adx,
          atr,
          ad,
          cmf,
          mfi,
          td_sequential,
          td_combo,
          marketwatch,
          dm,
          sma_10,
          sma_20,
          sma_50,
          sma_150,
          sma_200,
          ema_4,
          ema_9,
          ema_21,
          bbands_lower,
          bbands_middle,
          bbands_upper,
          pivot_high,
          pivot_low
        FROM ${tableName}
        WHERE symbol = $1
        ORDER BY date DESC
        LIMIT $2 OFFSET $3
      `;
      
      queryParams = [symbol.toUpperCase(), parseInt(limit), offset];
      
    } else {
      // Simplified query - just get recent data directly instead of complex CTE
      sqlQuery = `
        SELECT DISTINCT ON (symbol)
          symbol,
          date,
          rsi,
          macd,
          macd_signal,
          macd_hist,
          mom,
          roc,
          adx,
          atr,
          ad,
          cmf,
          mfi,
          td_sequential,
          td_combo,
          marketwatch,
          dm,
          sma_10,
          sma_20,
          sma_50,
          sma_150,
          sma_200,
          ema_4,
          ema_9,
          ema_21,
          bbands_lower,
          bbands_middle,
          bbands_upper,
          pivot_high,
          pivot_low
        FROM ${tableName}
        ORDER BY symbol, date DESC
        LIMIT $1 OFFSET $2
      `;
      
      queryParams = [parseInt(limit), offset];
    }

    const result = await query(sqlQuery, queryParams);

    res.json({
      success: true,
      data: result.rows,
      timeframe,
      count: result.rows.length,
      metadata: {
        limit: parseInt(limit),
        page: parseInt(page),
        symbol: symbol || null,
        hasSymbolFilter: !!symbol,
        totalDataPoints: tableCheck.rows[0]?.count || 0
      }
    });

  } catch (error) {
    console.error('Error fetching technical data:', error);
    res.status(500).json({ 
      error: 'Failed to fetch technical data',
      message: error.message,
      details: error.stack
    });
  }
});

// Get technical summary for a specific symbol
router.get('/:timeframe/:symbol', async (req, res) => {
  try {
    const { timeframe, symbol } = req.params;
    
    // Validate timeframe
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = `technical_data_${timeframe}`;
    const sqlQuery = `
      SELECT 
        symbol,
        date,
        rsi,
        macd,
        macd_signal,
        macd_hist,
        adx,
        mfi,
        sma_20,
        sma_50,
        sma_200,
        bbands_lower,
        bbands_middle,
        bbands_upper,
        mom,
        roc,
        atr,
        ad,
        cmf,
        td_sequential,
        td_combo,
        marketwatch,
        dm,
        sma_10,
        sma_150,
        ema_4,
        ema_9,
        ema_21,
        pivot_high,
        pivot_low
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 30
    `;

    const result = await query(sqlQuery, [symbol.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({ 
        error: 'No technical data found for this symbol',
        symbol,
        timeframe 
      });
    }

    res.json({
      success: true,
      data: result.rows,
      symbol: symbol.toUpperCase(),
      timeframe,
      count: result.rows.length
    });

  } catch (error) {
    console.error('Error fetching technical data for symbol:', error);
    res.status(500).json({ 
      error: 'Failed to fetch technical data for symbol',
      message: error.message 
    });
  }
});

module.exports = router;
