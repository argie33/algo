const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Debug endpoint to check technical table status
router.get('/debug', async (req, res) => {
  try {
    console.log('Technical debug endpoint called');
    
    // Check if table exists
    const tableExistsQuery = `
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'technical_data_daily'
      );
    `;
    
    const tableExists = await query(tableExistsQuery);
    console.log('Table exists check:', tableExists.rows[0]);
    
    if (tableExists.rows[0].exists) {
      // Count total records
      const countQuery = `SELECT COUNT(*) as total FROM technical_data_daily`;
      const countResult = await query(countQuery);
      console.log('Total technical records:', countResult.rows[0]);
        // Get sample records
      const sampleQuery = `
        SELECT symbol, date, rsi, macd, sma_20, sma_50
        FROM technical_data_daily 
        ORDER BY date DESC 
        LIMIT 5
      `;
      const sampleResult = await query(sampleQuery);
      console.log('Sample records:', sampleResult.rows);
      
      // Check distinct symbols
      const symbolsQuery = `SELECT COUNT(DISTINCT symbol) as unique_symbols FROM technical_data_daily`;
      const symbolsResult = await query(symbolsQuery);
      
      res.json({
        tableExists: true,
        totalRecords: parseInt(countResult.rows[0].total),
        uniqueSymbols: parseInt(symbolsResult.rows[0].unique_symbols),
        sampleRecords: sampleResult.rows,
        timestamp: new Date().toISOString()
      });
    } else {
      res.json({
        tableExists: false,
        message: 'technical_data_daily table does not exist',
        timestamp: new Date().toISOString()
      });
    }
    
  } catch (error) {
    console.error('Error in technical debug:', error);
    res.status(500).json({ 
      error: 'Debug check failed', 
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Simple test endpoint that returns raw data
router.get('/test', async (req, res) => {
  try {
    console.log('Technical test endpoint called');
    
    const testQuery = `
      SELECT 
        t.symbol,
        t.date,
        t.rsi,
        t.macd,
        t.sma_20,
        t.sma_50,
        cp.short_name as company_name
      FROM technical_data_daily t
      LEFT JOIN company_profile cp ON t.symbol = cp.ticker
      ORDER BY t.date DESC
      LIMIT 10
    `;
    
    const result = await query(testQuery);
    
    res.json({
      success: true,
      count: result.rows.length,
      data: result.rows,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error in technical test:', error);
    res.status(500).json({ 
      error: 'Test failed', 
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Basic ping endpoint
router.get('/ping', (req, res) => {
  res.json({
    status: 'ok',
    endpoint: 'technical',
    timestamp: new Date().toISOString()
  });
});

// Main technical data endpoint - timeframe-based (daily, weekly, monthly)
router.get('/:timeframe', async (req, res) => {
  try {
    const { timeframe } = req.params;
    console.log(`Technical data endpoint called for timeframe: ${timeframe}, params:`, req.query);
    
    // Support all available timeframes
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        error: 'Unsupported timeframe',
        message: `Supported timeframes: ${validTimeframes.join(', ')}, got: ${timeframe}`,
        availableTimeframes: validTimeframes
      });
    }

    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 25, 100); // Cap at 100 for performance
    const offset = (page - 1) * limit;
    const symbol = req.query.symbol;

    // Use the correct table based on timeframe
    const tableName = `technical_data_${timeframe}`;

    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramIndex = 1;

    // Add symbol filter if provided
    if (symbol) {
      whereClause += ` AND t.symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    // Add date filters
    if (req.query.start_date) {
      whereClause += ` AND t.date >= $${paramIndex}`;
      params.push(req.query.start_date);
      paramIndex++;
    }

    if (req.query.end_date) {
      whereClause += ` AND t.date <= $${paramIndex}`;
      params.push(req.query.end_date);
      paramIndex++;
    }

    console.log('Using whereClause:', whereClause, 'params:', params);
    const dataQuery = `
      SELECT 
        t.symbol,
        t.date,
        t.rsi,
        t.macd,
        t.macd_signal,
        t.macd_hist,
        t.mom,
        t.roc,
        t.adx,
        t.atr,
        t.sma_10,
        t.sma_20,
        t.sma_50,
        t.sma_150,
        t.sma_200,
        t.ema_4,
        t.ema_9,
        t.ema_21,
        t.bbands_lower,
        t.bbands_middle,
        t.bbands_upper,
        cp.short_name as company_name
      FROM ${tableName} t
      LEFT JOIN company_profile cp ON t.symbol = cp.ticker
      ${whereClause}
      ORDER BY t.date DESC, t.symbol ASC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM ${tableName} t
      ${whereClause}
    `;

    console.log('Executing queries with limit:', limit, 'offset:', offset);

    const [dataResult, countResult] = await Promise.all([
      query(dataQuery, [...params, limit, offset]),
      query(countQuery, params)
    ]);

    console.log('Query results - data:', dataResult.rows.length, 'total:', countResult.rows[0].total);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    res.json({
      data: dataResult.rows,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1
      },
      filters: {
        timeframe,
        symbol: symbol || null,
        start_date: req.query.start_date || null,
        end_date: req.query.end_date || null
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching technical data:', error);
    console.error('Error stack:', error.stack);
    res.status(500).json({ 
      error: 'Failed to fetch technical data', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Technical data summary endpoint
router.get('/:timeframe/summary', async (req, res) => {
  try {    const { timeframe } = req.params;
    console.log(`Technical summary endpoint called for timeframe: ${timeframe}`);
    
    // Support all available timeframes
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        error: 'Unsupported timeframe',
        message: `Supported timeframes: ${validTimeframes.join(', ')}, got: ${timeframe}`,
        availableTimeframes: validTimeframes
      });
    }

    const tableName = `technical_data_${timeframe}`;

    const summaryQuery = `
      SELECT 
        COUNT(*) as total_records,
        COUNT(DISTINCT symbol) as unique_symbols,
        MAX(date) as latest_date,
        MIN(date) as earliest_date,
        COUNT(CASE WHEN rsi > 70 THEN 1 END) as overbought_count,
        COUNT(CASE WHEN rsi < 30 THEN 1 END) as oversold_count,
        COUNT(CASE WHEN macd > macd_signal THEN 1 END) as macd_bullish_count,
        AVG(rsi) as avg_rsi,
        AVG(sma_20) as avg_sma_20
      FROM ${tableName} t
      WHERE date = (SELECT MAX(date) FROM ${tableName})
    `;

    const result = await query(summaryQuery);
    const summary = result.rows[0];

    res.json({
      timeframe,
      summary: {
        total_records: parseInt(summary.total_records),
        unique_symbols: parseInt(summary.unique_symbols),
        latest_date: summary.latest_date,
        earliest_date: summary.earliest_date,
        market_conditions: {
          overbought_stocks: parseInt(summary.overbought_count),
          oversold_stocks: parseInt(summary.oversold_count),
          macd_bullish_stocks: parseInt(summary.macd_bullish_count),
          average_rsi: parseFloat(summary.avg_rsi || 0).toFixed(2),
          average_sma_20: parseFloat(summary.avg_sma_20 || 0).toFixed(2)
        }
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching technical summary:', error);
    res.status(500).json({ 
      error: 'Failed to fetch technical summary', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Chunked technical data loading endpoint
router.get('/:timeframe/chunk/:chunkIndex', async (req, res) => {
  try {
    const { timeframe, chunkIndex } = req.params;
    const chunk = parseInt(chunkIndex) || 0;
    const chunkSize = 50; // Small chunks for performance
    
    console.log(`Technical chunk endpoint called for timeframe: ${timeframe}, chunk: ${chunk}`);
    
    if (timeframe !== 'daily') {
      return res.status(400).json({
        error: 'Unsupported timeframe',
        message: `Only 'daily' timeframe is currently supported, got: ${timeframe}`
      });
    }

    const offset = chunk * chunkSize;

    const dataQuery = `
      SELECT 
        t.symbol,
        t.date,
        t.rsi,
        t.macd,
        t.sma_20,
        t.sma_50,
        cp.short_name as company_name
      FROM technical_data_daily t
      LEFT JOIN company_profile cp ON t.symbol = cp.ticker
      ORDER BY t.date DESC, t.symbol ASC
      LIMIT $1 OFFSET $2
    `;

    const result = await query(dataQuery, [chunkSize, offset]);

    res.json({
      chunk: chunk,
      chunkSize: chunkSize,
      dataCount: result.rows.length,
      data: result.rows,
      hasMore: result.rows.length === chunkSize,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching technical chunk:', error);
    res.status(500).json({ 
      error: 'Failed to fetch technical chunk', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Full technical data endpoint (use with caution)
router.get('/:timeframe/full', async (req, res) => {
  try {
    const { timeframe } = req.params;
    console.log(`Technical full endpoint called for timeframe: ${timeframe}, params:`, req.query);
    
    if (timeframe !== 'daily') {
      return res.status(400).json({
        error: 'Unsupported timeframe',
        message: `Only 'daily' timeframe is currently supported, got: ${timeframe}`
      });
    }

    // Force small limit for safety
    const limit = Math.min(parseInt(req.query.limit) || 10, 10);
    const symbol = req.query.symbol;

    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramIndex = 1;

    if (symbol) {
      whereClause += ` AND t.symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    const dataQuery = `
      SELECT 
        t.symbol,
        t.date,
        t.rsi,
        t.macd,
        t.macd_signal,
        t.macd_hist,
        t.mom,
        t.roc,
        t.adx,
        t.atr,
        t.sma_10,
        t.sma_20,
        t.sma_50,
        t.sma_150,
        t.sma_200,
        t.ema_4,
        t.ema_9,
        t.ema_21,
        t.bbands_lower,
        t.bbands_middle,
        t.bbands_upper,
        cp.short_name as company_name
      FROM technical_data_daily t
      LEFT JOIN company_profile cp ON t.symbol = cp.ticker
      ${whereClause}
      ORDER BY t.date DESC, t.symbol ASC
      LIMIT $${paramIndex}
    `;

    const result = await query(dataQuery, [...params, limit]);

    res.json({
      warning: 'This endpoint returns limited data for performance reasons',
      actualLimit: limit,
      data: result.rows,
      count: result.rows.length,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching full technical data:', error);
    res.status(500).json({ 
      error: 'Failed to fetch full technical data', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
