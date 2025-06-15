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

// Lightweight endpoint for initial page load - returns only essential data
router.get('/:timeframe/summary', async (req, res) => {
  try {
    const { timeframe } = req.params;
    const { limit = 20, page = 1 } = req.query; // Increased from 50 to 20 for better balance
    
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = `technical_data_${timeframe}`;
    const offset = (parseInt(page) - 1) * parseInt(limit);
    
    // Set aggressive caching for summary data
    res.set({
      'Cache-Control': 'public, max-age=300', // 5 minutes cache
    });
    
    // Only return 3 essential indicators for quick overview
    const sqlQuery = `
    SELECT DISTINCT ON (symbol)
        symbol,
        date,
        rsi,
        macd,
        sma_20
    FROM ${tableName}
    ORDER BY symbol ASC, date DESC
    LIMIT $1 OFFSET $2
    `;
    
    const result = await query(sqlQuery, [parseInt(limit), offset]);

    res.json({
      success: true,
      data: result.rows,
      timeframe,
      count: result.rows.length,
      metadata: {
        limit: parseInt(limit),
        page: parseInt(page),
        isSummary: true
      }
    });

  } catch (error) {
    console.error('Error fetching technical summary:', error);
    res.status(500).json({ 
      error: 'Failed to fetch technical summary',
      message: error.message 
    });
  }
});

// Get technical data by timeframe
router.get('/:timeframe', async (req, res) => {  try {
    const { timeframe } = req.params;
    const { limit = 20, symbol, page = 1 } = req.query; // Increased from 10 to 20 for better performance

    // Validate timeframe
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = `technical_data_${timeframe}`;
    const offset = (parseInt(page) - 1) * parseInt(limit);
    
    // Add response headers for better performance
    res.set({
      'Cache-Control': 'public, max-age=300', // 5 minutes cache
      'Content-Type': 'application/json',
    });
    
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
    let queryParams;    if (symbol) {
      // If symbol specified, get historical data for that symbol with pagination - simplified to 3 indicators
      sqlQuery = `
        SELECT 
          symbol,
          date,
          rsi,
          macd,
          sma_20
        FROM ${tableName}
        WHERE symbol = $1
        ORDER BY date DESC
        LIMIT $2 OFFSET $3
      `;
      
      queryParams = [symbol.toUpperCase(), parseInt(limit), offset];
        } else {
      // Get all technical data with only 3 key indicators for better performance
      sqlQuery = `
      SELECT DISTINCT ON (symbol)
          symbol,
          date,
          rsi,
          macd,
          sma_20
        FROM ${tableName}
        ORDER BY symbol ASC, date DESC
        LIMIT $1 OFFSET $2
      `;
      
      queryParams = [parseInt(limit), offset];
    }
    
    const result = await query(sqlQuery, queryParams);

    // Skip optimization loop - return raw data for better performance
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
        totalDataPoints: tableCheck.rows[0]?.count || 0,
        dataSize: JSON.stringify(result.rows).length // Fixed reference
      }
    });
  } catch (error) {
    console.error('Error fetching technical data:', error);
    console.error('Error details:', {
      message: error.message,
      code: error.code,
      timeframe,
      limit,
      symbol: symbol || 'all',
      timestamp: new Date().toISOString()
    });
    res.status(500).json({ 
      error: 'Failed to fetch technical data',
      message: error.message,
      details: process.env.NODE_ENV === 'development' ? error.stack : undefined
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

    const tableName = `technical_data_${timeframe}`;    const sqlQuery = `
      SELECT 
        symbol,
        date,
        rsi,
        macd,
        sma_20
      FROM ${tableName}
      WHERE symbol = $1      ORDER BY date DESC
      LIMIT 10
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

// Chunked loading endpoint - returns full data in smaller chunks
router.get('/:timeframe/chunk/:chunkIndex', async (req, res) => {
  try {
    const { timeframe, chunkIndex } = req.params;
    const chunkSize = 5; // Load 5 symbols at a time
    const chunk = parseInt(chunkIndex) || 0;
    
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = `technical_data_${timeframe}`;
    const offset = chunk * chunkSize;
    
    // Set caching headers
    res.set({
      'Cache-Control': 'public, max-age=300',
      'Content-Type': 'application/json',
    });

    // Get ALL technical data columns for this chunk
    const sqlQuery = `
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
      ORDER BY symbol ASC, date DESC
      LIMIT $1 OFFSET $2
    `;
    
    const result = await query(sqlQuery, [chunkSize, offset]);
    
    // Get total count for pagination info
    const countQuery = `SELECT COUNT(DISTINCT symbol) as total FROM ${tableName}`;
    const countResult = await query(countQuery);
    const totalSymbols = parseInt(countResult.rows[0]?.total || 0);
    const totalChunks = Math.ceil(totalSymbols / chunkSize);

    // Clean up the data but keep all columns
    const cleanData = result.rows.map(row => {
      const cleaned = {};
      for (const [key, value] of Object.entries(row)) {
        if (value !== null && value !== undefined) {
          if (typeof value === 'number' && !Number.isInteger(value)) {
            // Round to 4 decimal places for cleaner data
            cleaned[key] = Math.round(value * 10000) / 10000;
          } else {
            cleaned[key] = value;
          }
        }
      }
      return cleaned;
    });

    res.json({
      success: true,
      data: cleanData,
      timeframe,
      chunk: {
        index: chunk,
        size: chunkSize,
        count: cleanData.length,
        totalChunks,
        totalSymbols,
        hasMore: chunk < totalChunks - 1
      },
      metadata: {
        dataSize: JSON.stringify(cleanData).length,
        loadingStrategy: 'chunked'
      }
    });

  } catch (error) {
    console.error('Error fetching technical data chunk:', error);
    res.status(500).json({ 
      error: 'Failed to fetch technical data chunk',
      message: error.message
    });
  }
});

// Full data endpoint - use with caution for large datasets
router.get('/:timeframe/full', async (req, res) => {
  try {
    const { timeframe } = req.params;
    const { limit = 5, page = 1 } = req.query; // Very small default limit for safety
    
    console.log(`Full data request - timeframe: ${timeframe}, limit: ${limit}, page: ${page}`);
    
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = `technical_data_${timeframe}`;
    const offset = (parseInt(page) - 1) * parseInt(limit);
    
    // Warning for large requests
    if (parseInt(limit) > 20) {
      console.warn(`Large data request detected: ${limit} symbols requested`);
    }
    
    // Set headers for large responses
    res.set({
      'Cache-Control': 'public, max-age=300',
      'Content-Type': 'application/json',
    });

    // Get ALL technical data columns - full dataset
    const sqlQuery = `
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
      ORDER BY symbol ASC, date DESC
      LIMIT $1 OFFSET $2
    `;
    
    const startTime = Date.now();
    const result = await query(sqlQuery, [parseInt(limit), offset]);
    const queryTime = Date.now() - startTime;
    
    console.log(`Query completed in ${queryTime}ms, returned ${result.rows.length} rows`);

    // Process data but keep ALL columns
    const processedData = result.rows.map(row => {
      const processed = {};
      for (const [key, value] of Object.entries(row)) {
        // Keep all data, just clean up null values and round numbers
        if (value !== null && value !== undefined) {
          if (typeof value === 'number' && !Number.isInteger(value)) {
            processed[key] = Math.round(value * 10000) / 10000;
          } else {
            processed[key] = value;
          }
        } else {
          processed[key] = null; // Keep null structure for consistency
        }
      }
      return processed;
    });

    const responseSize = JSON.stringify(processedData).length;
    console.log(`Response size: ${responseSize} bytes for ${processedData.length} symbols`);

    res.json({
      success: true,
      data: processedData,
      timeframe,
      count: processedData.length,
      metadata: {
        limit: parseInt(limit),
        page: parseInt(page),
        queryTimeMs: queryTime,
        dataSize: responseSize,
        averageSizePerSymbol: Math.round(responseSize / processedData.length),
        loadingStrategy: 'full',
        warning: parseInt(limit) > 10 ? `Large dataset requested (${limit} symbols)` : null
      }
    });

  } catch (error) {
    console.error('Error fetching full technical data:', error);
    res.status(500).json({ 
      error: 'Failed to fetch full technical data',
      message: error.message,
      stack: error.stack
    });
  }
});

// Ultra-lightweight endpoint for emergency use - minimal data only
router.get('/simple/:timeframe', async (req, res) => {
  try {
    const { timeframe } = req.params;
    const { limit = 10 } = req.query; // Very small limit
    
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: 'Invalid timeframe' });
    }

    const tableName = `technical_data_${timeframe}`;
    
    // Aggressive caching
    res.set({
      'Cache-Control': 'public, max-age=600', // 10 minutes cache
    });

    // Minimal query - just symbol, date, and RSI
    const sqlQuery = `
    SELECT DISTINCT ON (symbol)
        symbol,
        date,
        rsi
    FROM ${tableName}
    ORDER BY symbol ASC, date DESC
    LIMIT $1
    `;
    
    const result = await query(sqlQuery, [parseInt(limit)]);

    res.json({
      success: true,
      data: result.rows,
      timeframe,
      count: result.rows.length,
      isSimple: true
    });

  } catch (error) {
    console.error('Error fetching simple technical data:', error);
    res.status(500).json({ 
      error: 'Failed to fetch simple technical data',
      message: error.message 
    });
  }
});

module.exports = router;
