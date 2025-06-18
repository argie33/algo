const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Debug endpoint to check technical table column structure
router.get('/debug/columns', async (req, res) => {
  try {
    console.log('Technical columns debug endpoint called');
    
    const tables = ['technical_data_daily', 'technical_data_weekly', 'technical_data_monthly'];
    const results = {};
    
    for (const table of tables) {
      try {
        // Check if table exists
        const tableExistsQuery = `
          SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = '${table}'
          );
        `;
        
        const tableExists = await query(tableExistsQuery);
        
        if (tableExists.rows[0].exists) {
          // Get column information
          const columnsQuery = `
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = '${table}' 
            AND table_schema = 'public'
            ORDER BY ordinal_position
          `;
          
          const columnsResult = await query(columnsQuery);
          
          // Count total records
          const countQuery = `SELECT COUNT(*) as total FROM ${table}`;
          const countResult = await query(countQuery);
          
          results[table] = {
            exists: true,
            totalRecords: parseInt(countResult.rows[0].total),
            columns: columnsResult.rows
          };
        } else {
          results[table] = {
            exists: false,
            columns: []
          };
        }
        
      } catch (error) {
        results[table] = {
          exists: false,
          error: error.message,
          columns: []
        };
      }
    }
    
    res.json({
      tables: results,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error in technical columns debug:', error);
    res.status(500).json({ 
      error: 'Columns debug check failed', 
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Debug endpoint to check technical table status
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

    // Add date filters - with default recent data limits for performance
    if (req.query.start_date) {
      whereClause += ` AND t.date >= $${paramIndex}`;
      params.push(req.query.start_date);
      paramIndex++;
    } else {
      // Default: Only get recent data to prevent timeouts
      if (timeframe === 'daily') {
        whereClause += ` AND t.date >= CURRENT_DATE - INTERVAL '30 days'`; // Last 30 days for daily
      } else if (timeframe === 'weekly') {
        whereClause += ` AND t.date >= CURRENT_DATE - INTERVAL '90 days'`; // Last ~13 weeks for weekly
      } else if (timeframe === 'monthly') {
        whereClause += ` AND t.date >= CURRENT_DATE - INTERVAL '365 days'`; // Last 12 months for monthly
      }
    }

    if (req.query.end_date) {
      whereClause += ` AND t.date <= $${paramIndex}`;
      params.push(req.query.end_date);
      paramIndex++;
    }
    console.log('Using whereClause:', whereClause, 'params:', params);
    console.log('Using tableName:', tableName);
    
    const dataQuery = `
      SELECT 
        t.symbol,
        t.date,
        p.close,
        p.volume,
        p.open,
        p.high,
        p.low,
        t.rsi,
        t.macd,
        t.macd_signal,
        t.macd_hist,
        t.adx,
        t.atr,
        t.mfi,
        t.roc,
        t.mom,
        t.sma_10,
        t.sma_20,
        t.sma_50,
        t.sma_150,
        t.sma_200,
        t.ema_4,
        t.ema_9,
        t.ema_21,
        t.bbands_upper,
        t.bbands_middle,
        t.bbands_lower,
        t.ad,
        t.cmf,
        t.td_sequential,
        t.td_combo,
        t.marketwatch,
        t.dm,
        t.pivot_high,
        t.pivot_low,
        ss.security_name as company_name
      FROM ${tableName} t
      LEFT JOIN price_${timeframe} p ON t.symbol = p.symbol AND t.date = p.date
      LEFT JOIN stock_symbols ss ON t.symbol = ss.symbol
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
    
    // Support all available timeframes
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        error: 'Unsupported timeframe',
        message: `Supported timeframes: ${validTimeframes.join(', ')}, got: ${timeframe}`,
        availableTimeframes: validTimeframes
      });
    }
    const offset = chunk * chunkSize;
    const tableName = `technical_data_${timeframe}`;

    // Add default date restrictions for performance
    let dateFilter = '';
    if (timeframe === 'daily') {
      dateFilter = `WHERE t.date >= CURRENT_DATE - INTERVAL '30 days'`; // Last 30 days for daily
    } else if (timeframe === 'weekly') {
      dateFilter = `WHERE t.date >= CURRENT_DATE - INTERVAL '90 days'`; // Last ~13 weeks for weekly
    } else if (timeframe === 'monthly') {
      dateFilter = `WHERE t.date >= CURRENT_DATE - INTERVAL '365 days'`; // Last 12 months for monthly
    } else {
      dateFilter = 'WHERE 1=1';
    }

    const dataQuery = `
      SELECT 
        t.symbol,
        t.date,
        p.close,
        p.volume,
        p.open,
        p.high,
        p.low,
        t.rsi,
        t.macd,
        t.macd_signal,
        t.macd_hist,
        t.adx,
        t.atr,
        t.mfi,
        t.roc,
        t.mom,
        t.sma_10,
        t.sma_20,
        t.sma_50,
        t.sma_150,
        t.sma_200,
        t.ema_4,
        t.ema_9,
        t.ema_21,
        t.bbands_upper,
        t.bbands_middle,
        t.bbands_lower,
        t.ad,
        t.cmf,
        t.td_sequential,
        t.td_combo,
        t.marketwatch,
        t.dm,
        t.pivot_high,
        t.pivot_low,
        ss.security_name as company_name
      FROM ${tableName} t
      LEFT JOIN price_${timeframe} p ON t.symbol = p.symbol AND t.date = p.date
      LEFT JOIN stock_symbols ss ON t.symbol = ss.symbol
      ${dateFilter}
      ORDER BY t.date DESC, t.symbol ASC
      LIMIT $1 OFFSET $2
    `;

    const result = await query(dataQuery, [chunkSize, offset]);

    res.json({
      timeframe,
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
    
    // Support all available timeframes
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        error: 'Unsupported timeframe',
        message: `Supported timeframes: ${validTimeframes.join(', ')}, got: ${timeframe}`,
        availableTimeframes: validTimeframes
      });
    }    // Force small limit for safety and add date restrictions
    const limit = Math.min(parseInt(req.query.limit) || 10, 50);
    const symbol = req.query.symbol;
    const tableName = `technical_data_${timeframe}`;

    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramIndex = 1;

    if (symbol) {
      whereClause += ` AND t.symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    // Add default date restrictions for performance - same as main endpoint
    if (!req.query.start_date) {
      if (timeframe === 'daily') {
        whereClause += ` AND t.date >= CURRENT_DATE - INTERVAL '30 days'`; // Last 30 days for daily
      } else if (timeframe === 'weekly') {
        whereClause += ` AND t.date >= CURRENT_DATE - INTERVAL '90 days'`; // Last ~13 weeks for weekly
      } else if (timeframe === 'monthly') {
        whereClause += ` AND t.date >= CURRENT_DATE - INTERVAL '365 days'`; // Last 12 months for monthly
      }
    } else {
      whereClause += ` AND t.date >= $${paramIndex}`;
      params.push(req.query.start_date);
      paramIndex++;
    }

    if (req.query.end_date) {
      whereClause += ` AND t.date <= $${paramIndex}`;
      params.push(req.query.end_date);
      paramIndex++;
    }

    const dataQuery = `
      SELECT 
        t.symbol,
        t.date,
        p.close,
        p.volume,
        p.open,
        p.high,
        p.low,
        t.rsi,
        t.macd,
        t.macd_signal,
        t.macd_hist,
        t.adx,
        t.atr,
        t.mfi,
        t.roc,
        t.mom,
        t.sma_10,
        t.sma_20,
        t.sma_50,
        t.sma_150,
        t.sma_200,
        t.ema_4,
        t.ema_9,
        t.ema_21,
        t.bbands_upper,
        t.bbands_middle,
        t.bbands_lower,
        t.ad,
        t.cmf,
        t.td_sequential,
        t.td_combo,
        t.marketwatch,
        t.dm,
        t.pivot_high,
        t.pivot_low,
        ss.security_name as company_name
      FROM ${tableName} t
      LEFT JOIN price_${timeframe} p ON t.symbol = p.symbol AND t.date = p.date
      LEFT JOIN stock_symbols ss ON t.symbol = ss.symbol
      ${whereClause}
      ORDER BY t.date DESC, t.symbol ASC
      LIMIT $${paramIndex}
    `;

    const result = await query(dataQuery, [...params, limit]);

    res.json({
      timeframe,
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

// Root technical endpoint - returns daily technical data by default (like calendar)
router.get('/', async (req, res) => {
  try {
    console.log('Root technical endpoint called with params:', req.query);
      const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;
    const symbol = req.query.symbol;

    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramIndex = 1;

    // Add symbol filter if provided
    if (symbol) {
      whereClause += ` AND t.symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    // Add default date restriction for performance - daily data, last 30 days
    if (!req.query.start_date) {
      whereClause += ` AND t.date >= CURRENT_DATE - INTERVAL '30 days'`;
    } else {
      whereClause += ` AND t.date >= $${paramIndex}`;
      params.push(req.query.start_date);
      paramIndex++;
    }

    if (req.query.end_date) {
      whereClause += ` AND t.date <= $${paramIndex}`;
      params.push(req.query.end_date);
      paramIndex++;
    }

    console.log('Using whereClause:', whereClause);
    
    const dataQuery = `
      SELECT 
        t.symbol,
        t.date,
        p.close,
        p.volume,
        p.open,
        p.high,
        p.low,
        t.rsi,
        t.macd,
        t.macd_signal,
        t.macd_hist,
        t.adx,
        t.atr,
        t.mfi,
        t.roc,
        t.mom,
        t.sma_10,
        t.sma_20,
        t.sma_50,
        t.sma_150,
        t.sma_200,
        t.ema_4,
        t.ema_9,
        t.ema_21,
        t.bbands_upper,
        t.bbands_middle,
        t.bbands_lower,
        t.ad,
        t.cmf,
        t.td_sequential,
        t.td_combo,
        t.marketwatch,
        t.dm,
        t.pivot_high,
        t.pivot_low,
        ss.security_name as company_name
      FROM technical_data_daily t
      LEFT JOIN price_daily p ON t.symbol = p.symbol AND t.date = p.date
      LEFT JOIN stock_symbols ss ON t.symbol = ss.symbol
      ${whereClause}
      ORDER BY t.date DESC, t.symbol ASC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM technical_data_daily t
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
      summary: {
        timeframe: 'daily',
        total_records: total
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error in root technical endpoint:', error);
    res.status(500).json({ 
      error: 'Failed to fetch technical data overview',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get technical data (simple endpoint like calendar/events)
module.exports = router;
