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
          
          // Get sample records
          const sampleQuery = `
            SELECT symbol, date, rsi, macd, sma_20
            FROM ${table} 
            ORDER BY date DESC 
            LIMIT 3
          `;
          const sampleResult = await query(sampleQuery);
          
          results[table] = {
            exists: true,
            totalRecords: parseInt(countResult.rows[0].total),
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

// Simple test endpoint that returns raw data
router.get('/test', async (req, res) => {
  try {
    console.log('Technical test endpoint called');
    
    const testQuery = `
      SELECT 
        symbol,
        date,
        rsi,
        macd,
        sma_20
      FROM technical_data_daily
      ORDER BY date DESC
      LIMIT 5
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

module.exports = router;
