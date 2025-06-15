const express = require('express');
const router = express.Router();
const { query } = require('../utils/database');

// Debug endpoint to check technical tables status
router.get('/debug', async (req, res) => {
  try {
    console.log('Technical debug endpoint called');
    
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
        console.log(`Table ${table} exists:`, tableExists.rows[0]);
          if (tableExists.rows[0].exists) {
          // Count total records
          const countQuery = `SELECT COUNT(*) as total FROM ${table}`;
          const countResult = await query(countQuery);
          
          // Get all column names for this table
          const columnsQuery = `
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = 'public' 
            AND table_name = '${table}'
            ORDER BY ordinal_position
          `;
          const columnsResult = await query(columnsQuery);
          
          // Get sample records with ALL technical indicators
          const sampleQuery = `
            SELECT *
            FROM ${table} 
            WHERE symbol IS NOT NULL
            ORDER BY date DESC 
            LIMIT 2
          `;
          const sampleResult = await query(sampleQuery);
          
          results[table] = {
            exists: true,
            totalRecords: parseInt(countResult.rows[0].total),
            columns: columnsResult.rows,
            sampleRecords: sampleResult.rows
          };
        } else {
          results[table] = {
            exists: false,
            message: `${table} table does not exist`
          };
        }
        
      } catch (error) {
        results[table] = {
          exists: false,
          error: error.message
        };
      }
    }
    
    res.json({
      tables: results,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error in technical debug:', error);
    res.status(500).json({ 
      error: 'Debug check failed', 
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Extended test endpoint that returns all available technical indicators
router.get('/test', async (req, res) => {
  try {
    console.log('Technical test endpoint called');
    
    const testQuery = `
      SELECT *
      FROM technical_data_daily
      WHERE symbol IS NOT NULL
      ORDER BY date DESC
      LIMIT 3
    `;
    
    const result = await query(testQuery);
    
    // Also get the column information
    const columnsQuery = `
      SELECT column_name, data_type 
      FROM information_schema.columns 
      WHERE table_schema = 'public' 
      AND table_name = 'technical_data_daily'
      ORDER BY ordinal_position
    `;
    const columnsResult = await query(columnsQuery);
    
    res.json({
      success: true,
      count: result.rows.length,
      availableIndicators: columnsResult.rows,
      sampleData: result.rows,
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

// Get technical data - simplified like the working endpoints
router.get('/:timeframe', async (req, res) => {
  try {
    console.log('Technical data endpoint called:', req.params.timeframe);
    
    const { timeframe } = req.params;
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;
    
    // Validate timeframe
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = `technical_data_${timeframe}`;
    
    // Simple query like the working endpoints
    const technicalQuery = `
      SELECT 
        symbol,
        date,
        rsi,
        macd,
        sma_20
      FROM ${tableName}
      ORDER BY date DESC, symbol ASC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM ${tableName}
    `;

    const [technicalResult, countResult] = await Promise.all([
      query(technicalQuery, [limit, offset]),
      query(countQuery)
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    res.json({
      data: technicalResult.rows,
      timeframe,
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
    console.error('Error fetching technical data:', error);
    res.status(500).json({ 
      error: 'Failed to fetch technical data',
      message: error.message 
    });
  }
});

// Get technical data for a specific symbol
router.get('/:timeframe/:symbol', async (req, res) => {
  try {
    const { timeframe, symbol } = req.params;
    
    // Validate timeframe
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = `technical_data_${timeframe}`;
    
    const technicalQuery = `
      SELECT 
        symbol,
        date,
        rsi,
        macd,
        sma_20
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 30
    `;

    const result = await query(technicalQuery, [symbol.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({ 
        error: 'No technical data found for this symbol',
        symbol: symbol.toUpperCase(),
        timeframe
      });
    }

    res.json({
      symbol: symbol.toUpperCase(),
      timeframe,
      data: result.rows
    });

  } catch (error) {
    console.error('Error fetching symbol technical data:', error);
    res.status(500).json({ 
      error: 'Failed to fetch symbol technical data',
      message: error.message 
    });
  }
});

// Get all available technical indicators with sample data
router.get('/indicators/all', async (req, res) => {
  try {
    console.log('All technical indicators endpoint called');
    
    const timeframe = req.query.timeframe || 'daily';
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = `technical_data_${timeframe}`;
    
    // Get all columns
    const columnsQuery = `
      SELECT column_name, data_type, is_nullable
      FROM information_schema.columns 
      WHERE table_schema = 'public' 
      AND table_name = '${tableName}'
      ORDER BY ordinal_position
    `;
    const columnsResult = await query(columnsQuery);
    
    // Get one complete record with all indicators
    const sampleQuery = `
      SELECT *
      FROM ${tableName}
      WHERE symbol IS NOT NULL
      ORDER BY date DESC
      LIMIT 1
    `;
    const sampleResult = await query(sampleQuery);
    
    // Categorize indicators
    const indicators = {
      basic: ['symbol', 'date', 'fetched_at'],
      momentum: [],
      trend: [],
      volatility: [],
      volume: [],
      patterns: [],
      other: []
    };
    
    columnsResult.rows.forEach(col => {
      const name = col.column_name.toLowerCase();
      if (indicators.basic.includes(name)) return;
      
      if (name.includes('rsi') || name.includes('mom') || name.includes('roc') || name.includes('macd')) {
        indicators.momentum.push(col);
      } else if (name.includes('sma') || name.includes('ema') || name.includes('adx') || name.includes('trend')) {
        indicators.trend.push(col);
      } else if (name.includes('atr') || name.includes('bbands') || name.includes('volatility')) {
        indicators.volatility.push(col);
      } else if (name.includes('ad') || name.includes('cmf') || name.includes('mfi') || name.includes('volume')) {
        indicators.volume.push(col);
      } else if (name.includes('pivot') || name.includes('td_') || name.includes('pattern')) {
        indicators.patterns.push(col);
      } else {
        indicators.other.push(col);
      }
    });
    
    res.json({
      success: true,
      timeframe,
      totalIndicators: columnsResult.rows.length,
      indicatorCategories: indicators,
      sampleRecord: sampleResult.rows[0] || null,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching all indicators:', error);
    res.status(500).json({ 
      error: 'Failed to fetch all indicators',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Basic connectivity test - no database
router.get('/ping', async (req, res) => {
  res.json({ 
    status: 'ok', 
    service: 'technical', 
    timestamp: new Date().toISOString() 
  });
});

module.exports = router;
