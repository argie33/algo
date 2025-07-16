const express = require('express');
const { query, safeQuery, tablesExist } = require('../utils/database');
const { authenticateToken } = require('../middleware/auth');
const { 
  createValidationMiddleware, 
  rateLimitConfigs, 
  sqlInjectionPrevention, 
  xssPrevention,
  sanitizers
} = require('../middleware/validation');
const validator = require('validator');

const router = express.Router();

// Apply authentication to all technical analysis routes
router.use(authenticateToken);

// Technical analysis validation schemas
const technicalValidationSchemas = {
  technicalData: {
    timeframe: {
      required: true,
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 20, alphaNumOnly: true }),
      validator: (value) => ['daily', 'weekly', 'monthly'].includes(value),
      errorMessage: 'Timeframe must be one of: daily, weekly, monthly'
    },
    page: {
      type: 'integer',
      sanitizer: (value) => sanitizers.integer(value, { min: 1, max: 10000, defaultValue: 1 }),
      validator: (value) => value >= 1 && value <= 10000,
      errorMessage: 'Page must be between 1 and 10,000'
    },
    limit: {
      type: 'integer',
      sanitizer: (value) => sanitizers.integer(value, { min: 1, max: 200, defaultValue: 50 }),
      validator: (value) => value >= 1 && value <= 200,
      errorMessage: 'Limit must be between 1 and 200'
    },
    symbol: {
      type: 'string',
      sanitizer: sanitizers.symbol,
      validator: (value) => !value || /^[A-Z]{1,10}$/.test(value),
      errorMessage: 'Symbol must be 1-10 uppercase letters'
    },
    start_date: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10 }),
      validator: (value) => !value || validator.isDate(value, { format: 'YYYY-MM-DD' }),
      errorMessage: 'Start date must be in YYYY-MM-DD format'
    },
    end_date: {
      type: 'string',
      sanitizer: (value) => sanitizers.string(value, { maxLength: 10 }),
      validator: (value) => !value || validator.isDate(value, { format: 'YYYY-MM-DD' }),
      errorMessage: 'End date must be in YYYY-MM-DD format'
    },
    rsi_min: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 0, max: 100 }),
      validator: (value) => !value || (value >= 0 && value <= 100),
      errorMessage: 'RSI minimum must be between 0 and 100'
    },
    rsi_max: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 0, max: 100 }),
      validator: (value) => !value || (value >= 0 && value <= 100),
      errorMessage: 'RSI maximum must be between 0 and 100'
    },
    macd_min: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: -1000, max: 1000 }),
      validator: (value) => !value || (value >= -1000 && value <= 1000),
      errorMessage: 'MACD minimum must be between -1000 and 1000'
    },
    macd_max: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: -1000, max: 1000 }),
      validator: (value) => !value || (value >= -1000 && value <= 1000),
      errorMessage: 'MACD maximum must be between -1000 and 1000'
    },
    sma_min: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 0, max: 100000 }),
      validator: (value) => !value || (value >= 0 && value <= 100000),
      errorMessage: 'SMA minimum must be between 0 and 100,000'
    },
    sma_max: {
      type: 'number',
      sanitizer: (value) => sanitizers.number(value, { min: 0, max: 100000 }),
      validator: (value) => !value || (value >= 0 && value <= 100000),
      errorMessage: 'SMA maximum must be between 0 and 100,000'
    }
  }
};

// Apply security middleware to all technical routes
router.use(sqlInjectionPrevention);
router.use(xssPrevention);
router.use(rateLimitConfigs.api);

// Basic ping endpoint
router.get('/ping', (req, res) => {
  res.json({
    status: 'ok',
    endpoint: 'technical',
    timestamp: new Date().toISOString()
  });
});

// Main technical data endpoint - timeframe-based (daily, weekly, monthly)
router.get('/:timeframe', createValidationMiddleware(technicalValidationSchemas.technicalData), async (req, res) => {
  try {
    const { timeframe, page, limit, symbol, start_date, end_date, rsi_min, rsi_max, macd_min, macd_max, sma_min, sma_max } = req.validated;
    
    const offset = (page - 1) * limit;
    console.log(`📊 Technical data request: ${timeframe}, page ${page}, limit ${limit}`);

    // Build WHERE clause
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramIndex = 1;

    // Symbol filter
    if (symbol && symbol.trim()) {
      whereClause += ` AND symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    // Date filters
    if (start_date) {
      whereClause += ` AND date >= $${paramIndex}`;
      params.push(start_date);
      paramIndex++;
    }

    if (end_date) {
      whereClause += ` AND date <= $${paramIndex}`;
      params.push(end_date);
      paramIndex++;
    }

    // Technical indicator filters (using validated and sanitized values)
    if (rsi_min !== undefined && rsi_min !== null) {
      whereClause += ` AND rsi >= $${paramIndex}`;
      params.push(rsi_min);
      paramIndex++;
    }

    if (rsi_max !== undefined && rsi_max !== null) {
      whereClause += ` AND rsi <= $${paramIndex}`;
      params.push(rsi_max);
      paramIndex++;
    }

    if (macd_min !== undefined && macd_min !== null) {
      whereClause += ` AND macd >= $${paramIndex}`;
      params.push(macd_min);
      paramIndex++;
    }

    if (macd_max !== undefined && macd_max !== null) {
      whereClause += ` AND macd <= $${paramIndex}`;
      params.push(macd_max);
      paramIndex++;
    }

    if (sma_min !== undefined && sma_min !== null) {
      whereClause += ` AND sma_20 >= $${paramIndex}`;
      params.push(sma_min);
      paramIndex++;
    }

    if (sma_max !== undefined && sma_max !== null) {
      whereClause += ` AND sma_20 <= $${paramIndex}`;
      params.push(sma_max);
      paramIndex++;
    }

    // Determine table name based on timeframe
    const tableName = `technical_data_${timeframe}`;

    // Check if table exists using enhanced table checking
    const tableStatusCheck = await tablesExist([tableName]);
    
    if (!tableStatusCheck[tableName]) {
      console.log(`Technical data table for ${timeframe} timeframe not found, returning empty data`);
      return res.json({
        success: true,
        data: [],
        pagination: {
          page: page,
          limit: limit,
          total: 0,
          totalPages: 0,
          hasNext: false,
          hasPrev: false
        },
        metadata: {
          timeframe,
          filters: {
            symbol: symbol || null,
            start_date: start_date || null,
            end_date: end_date || null,
            rsi_min: rsi_min || null,
            rsi_max: rsi_max || null,
            macd_min: macd_min || null,
            macd_max: macd_max || null,
            sma_min: sma_min || null,
            sma_max: sma_max || null
          },
          message: `No ${timeframe} technical data available`
        }
      });
    }

    // Get total count
    const countQuery = `
      SELECT COUNT(*) as total
      FROM ${tableName}
      ${whereClause}
    `;
    const countResult = await query(countQuery, params);
    const total = parseInt(countResult.rows[0].total);

    // Get technical data - updated to match actual table structure
    const dataQuery = `
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
        plus_di,
        minus_di,
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
        pivot_low,
        pivot_high_triggered,
        pivot_low_triggered,
        fetched_at
      FROM ${tableName}
      ${whereClause}
      ORDER BY date DESC, symbol
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    const finalParams = [...params, limit, offset];
    const dataResult = await query(dataQuery, finalParams);

    const totalPages = Math.ceil(total / limit);

    if (!dataResult || !Array.isArray(dataResult.rows) || dataResult.rows.length === 0) {
      return res.json({
        success: true,
        data: [],
        pagination: {
          page: parseInt(page),
          limit: maxLimit,
          total: 0,
          totalPages: 0,
          hasNext: false,
          hasPrev: false
        },
        metadata: {
          timeframe,
          filters: {
            symbol: symbol || null,
            start_date: start_date || null,
            end_date: end_date || null,
            rsi_min: rsi_min || null,
            rsi_max: rsi_max || null,
            macd_min: macd_min || null,
            macd_max: macd_max || null,
            sma_min: sma_min || null,
            sma_max: sma_max || null
          }
        }
      });
    }

    res.json({
      success: true,
      data: dataResult.rows,
      pagination: {
        page: parseInt(page),
        limit: maxLimit,
        total,
        totalPages,
        hasNext: parseInt(page) < totalPages,
        hasPrev: parseInt(page) > 1
      },
      metadata: {
        timeframe,
        filters: {
          symbol: symbol || null,
          start_date: start_date || null,
          end_date: end_date || null,
          rsi_min: rsi_min || null,
          rsi_max: rsi_max || null,
          macd_min: macd_min || null,
          macd_max: macd_max || null,
          sma_min: sma_min || null,
          sma_max: sma_max || null
        }
      }
    });
  } catch (error) {
    console.error('Technical data error:', error);
    return res.json({
      success: false,
      data: [],
      pagination: {
        page: parseInt(page) || 1,
        limit: parseInt(limit) || 50,
        total: 0,
        totalPages: 0,
        hasNext: false,
        hasPrev: false
      },
      metadata: {
        timeframe,
        error: error.message
      }
    });
  }
});

// Technical summary endpoint
router.get('/:timeframe/summary', async (req, res) => {
  const { timeframe } = req.params;
  
  // console.log(`Technical summary endpoint called for timeframe: ${timeframe}`);

  try {
    const tableName = `technical_data_${timeframe}`;

    // Check if table exists
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      );
    `, [tableName]);

    if (!tableExists.rows[0].exists) {
      console.log(`Technical data table for ${timeframe} timeframe not found`);
      return res.status(404).json({
        success: false,
        error: `Technical data table for ${timeframe} timeframe not available`,
        message: `Table ${tableName} does not exist. Please ensure technical data has been loaded.`
      });
    }

    // Get summary statistics
    const summaryQuery = `
      SELECT 
        COUNT(*) as total_records,
        COUNT(DISTINCT symbol) as unique_symbols,
        MIN(date) as earliest_date,
        MAX(date) as latest_date,
        AVG(rsi) as avg_rsi,
        AVG(macd) as avg_macd,
        AVG(sma_20) as avg_sma_20,
        AVG(volume) as avg_volume
      FROM ${tableName}
      WHERE rsi IS NOT NULL OR macd IS NOT NULL
    `;

    const summaryResult = await query(summaryQuery);
    const summary = summaryResult.rows[0];

    // Get top symbols by record count
    const topSymbolsQuery = `
      SELECT symbol, COUNT(*) as record_count
      FROM ${tableName}
      GROUP BY symbol
      ORDER BY record_count DESC
      LIMIT 10
    `;

    const topSymbolsResult = await query(topSymbolsQuery);

    res.json({
      timeframe,
      summary: {
        totalRecords: parseInt(summary.total_records),
        uniqueSymbols: parseInt(summary.unique_symbols),
        dateRange: {
          earliest: summary.earliest_date,
          latest: summary.latest_date
        },
        averages: {
          rsi: summary.avg_rsi ? parseFloat(summary.avg_rsi).toFixed(2) : null,
          macd: summary.avg_macd ? parseFloat(summary.avg_macd).toFixed(4) : null,
          sma20: summary.avg_sma_20 ? parseFloat(summary.avg_sma_20).toFixed(2) : null,
          volume: summary.avg_volume ? parseInt(summary.avg_volume) : null
        }
      },
      topSymbols: topSymbolsResult.rows.map(row => ({
        symbol: row.symbol,
        recordCount: parseInt(row.record_count)
      }))
    });
  } catch (error) {
    console.error('Error fetching technical summary:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch technical summary',
      details: error.message,
      timeframe
    });
  }
});

// Root technical endpoint - defaults to daily data
router.get('/', async (req, res) => {
  try {
    // Only fetch the latest technicals for each symbol (overview)
    const timeframe = req.query.timeframe || 'daily';
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        error: 'Unsupported timeframe',
        message: `Supported timeframes: ${validTimeframes.join(', ')}, got: ${timeframe}`
      });
    }
    const tableName = `technical_data_${timeframe}`;
    
    // Check if table exists
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      );
    `, [tableName]);

    if (!tableExists.rows[0].exists) {
      console.log(`Technical data table for ${timeframe} timeframe not found`);
      return res.status(404).json({
        success: false,
        error: `Technical data table for ${timeframe} timeframe not available`,
        message: `Table ${tableName} does not exist. Please ensure technical data has been loaded.`,
        timeframe
      });
    }
    
    // Subquery to get latest date per symbol
    const latestQuery = `
      SELECT t1.* FROM ${tableName} t1
      INNER JOIN (
        SELECT symbol, MAX(date) AS max_date
        FROM ${tableName}
        GROUP BY symbol
      ) t2 ON t1.symbol = t2.symbol AND t1.date = t2.max_date
      LEFT JOIN stock_symbols ss ON t1.symbol = ss.symbol
      ORDER BY t1.symbol ASC
      LIMIT 500
    `;
    const result = await query(latestQuery);
    res.json({
      success: true,
      data: result.rows,
      count: result.rows.length,
      metadata: {
        timeframe,
        timestamp: new Date().toISOString()
      }
    });
  } catch (error) {
    console.error('Error in technical overview endpoint:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch technical overview',
      details: error.message,
      timeframe: req.query.timeframe || 'daily'
    });
  }
});

// Get technical data for a specific symbol
router.get('/data/:symbol', async (req, res) => {
  const { symbol } = req.params;
  console.log(`📊 [TECHNICAL] Fetching technical data for ${symbol}`);
  
  try {
    // Check if table exists
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'technical_data_daily'
      );
    `, []);

    if (!tableExists.rows[0].exists) {
      console.log(`Technical data table not found for ${symbol}`);
      return res.status(404).json({
        success: false,
        error: 'Technical data table not available',
        message: 'Technical data table does not exist. Please ensure technical data has been loaded.',
        symbol: symbol.toUpperCase()
      });
    }

    // Get latest technical data for the symbol
    const dataQuery = `
      SELECT 
        symbol,
        date,
        open,
        high,
        low,
        close,
        volume,
        rsi,
        macd,
        macd_signal,
        macd_histogram,
        sma_20,
        sma_50,
        ema_12,
        ema_26,
        bollinger_upper,
        bollinger_lower,
        bollinger_middle,
        stochastic_k,
        stochastic_d,
        williams_r,
        cci,
        adx,
        atr,
        obv,
        mfi,
        roc,
        momentum
      FROM technical_data_daily
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 1
    `;

    const result = await query(dataQuery, [symbol.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: `No technical data found for symbol ${symbol}`
      });
    }

    res.json({
      success: true,
      data: result.rows[0],
      symbol: symbol.toUpperCase()
    });
  } catch (error) {
    console.error(`❌ [TECHNICAL] Error fetching technical data for ${symbol}:`, error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch technical data',
      details: error.message,
      symbol: symbol.toUpperCase()
    });
  }
});

// Get technical indicators for a specific symbol
router.get('/indicators/:symbol', async (req, res) => {
  const { symbol } = req.params;
  console.log(`📈 [TECHNICAL] Fetching technical indicators for ${symbol}`);
  
  try {
    // Check if table exists
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'technical_data_daily'
      );
    `, []);

    if (!tableExists.rows[0].exists) {
      console.log(`Technical data table not found for ${symbol}`);
      return res.status(404).json({
        success: false,
        error: 'Technical data table not available',
        message: 'Technical data table does not exist. Please ensure technical data has been loaded.',
        symbol: symbol.toUpperCase()
      });
    }

    // Get latest technical indicators for the symbol
    const indicatorsQuery = `
      SELECT 
        symbol,
        date,
        rsi,
        macd,
        macd_signal,
        macd_histogram,
        sma_20,
        sma_50,
        ema_12,
        ema_26,
        bollinger_upper,
        bollinger_lower,
        bollinger_middle,
        stochastic_k,
        stochastic_d,
        williams_r,
        cci,
        adx,
        atr,
        obv,
        mfi,
        roc,
        momentum
      FROM technical_data_daily
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 30
    `;

    const result = await query(indicatorsQuery, [symbol.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: `No technical indicators found for symbol ${symbol}`
      });
    }

    res.json({
      success: true,
      data: result.rows,
      count: result.rows.length,
      symbol: symbol.toUpperCase()
    });
  } catch (error) {
    console.error(`❌ [TECHNICAL] Error fetching technical indicators for ${symbol}:`, error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch technical indicators',
      details: error.message,
      symbol: symbol.toUpperCase()
    });
  }
});

// Get technical history for a specific symbol
router.get('/history/:symbol', async (req, res) => {
  const { symbol } = req.params;
  const { days = 90 } = req.query;
  console.log(`📊 [TECHNICAL] Fetching technical history for ${symbol} (${days} days)`);
  
  try {
    // Check if table exists
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'technical_data_daily'
      );
    `, []);

    if (!tableExists.rows[0].exists) {
      console.log(`Technical data table not found for ${symbol}`);
      return res.status(404).json({
        success: false,
        error: 'Technical data table not available',
        message: 'Technical data table does not exist. Please ensure technical data has been loaded.',
        symbol: symbol.toUpperCase()
      });
    }

    // Get technical history for the symbol
    const historyQuery = `
      SELECT 
        symbol,
        date,
        open,
        high,
        low,
        close,
        volume,
        rsi,
        macd,
        macd_signal,
        macd_histogram,
        sma_20,
        sma_50,
        ema_12,
        ema_26,
        bollinger_upper,
        bollinger_lower,
        bollinger_middle,
        stochastic_k,
        stochastic_d,
        williams_r,
        cci,
        adx,
        atr,
        obv,
        mfi,
        roc,
        momentum
      FROM technical_data_daily
      WHERE symbol = $1
        AND date >= CURRENT_DATE - INTERVAL '${days} days'
      ORDER BY date ASC
    `;

    const result = await query(historyQuery, [symbol.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: `No technical history found for symbol ${symbol}`
      });
    }

    res.json({
      success: true,
      data: result.rows,
      count: result.rows.length,
      symbol: symbol.toUpperCase(),
      period_days: days
    });
  } catch (error) {
    console.error(`❌ [TECHNICAL] Error fetching technical history for ${symbol}:`, error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch technical history',
      details: error.message,
      symbol: symbol.toUpperCase()
    });
  }
});

// Get support and resistance levels for a symbol
router.get('/support-resistance/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const { timeframe = 'daily' } = req.query;
    
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        error: 'Unsupported timeframe',
        message: `Supported timeframes: ${validTimeframes.join(', ')}, got: ${timeframe}`
      });
    }
    
    const tableName = `technical_data_${timeframe}`;
    
    // Check if table exists
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      );
    `, [tableName]);

    if (!tableExists.rows[0].exists) {
      console.log(`Technical data table for ${timeframe} timeframe not found for ${symbol}`);
      return res.status(404).json({
        success: false,
        error: `Technical data table for ${timeframe} timeframe not available`,
        message: `Table ${tableName} does not exist. Please ensure technical data has been loaded.`,
        symbol: symbol.toUpperCase(),
        timeframe
      });
    }
    
    // Get recent price data and pivot points
    const query = `
      SELECT 
        symbol,
        date,
        high,
        low,
        close,
        pivot_high,
        pivot_low,
        bbands_upper,
        bbands_lower,
        sma_20,
        sma_50,
        sma_200
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 50
    `;
    
    const result = await query(query, [symbol.toUpperCase()]);
    
    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'No technical data found for symbol' });
    }
    
    // Calculate support and resistance levels
    const latest = result.rows[0];
    const recentData = result.rows.slice(0, 20); // Last 20 periods
    
    const highs = recentData.map(d => d.high).filter(h => h !== null);
    const lows = recentData.map(d => d.low).filter(l => l !== null);
    
    const resistance = Math.max(...highs);
    const support = Math.min(...lows);
    
    res.json({
      symbol: symbol.toUpperCase(),
      timeframe,
      current_price: latest.close,
      support_levels: [
        { level: support, type: 'dynamic', strength: 'strong' },
        { level: latest.bbands_lower, type: 'bollinger', strength: 'medium' },
        { level: latest.sma_200, type: 'moving_average', strength: 'strong' }
      ],
      resistance_levels: [
        { level: resistance, type: 'dynamic', strength: 'strong' },
        { level: latest.bbands_upper, type: 'bollinger', strength: 'medium' },
        { level: latest.sma_50, type: 'moving_average', strength: 'medium' }
      ],
      last_updated: latest.date
    });
  } catch (error) {
    console.error('Error fetching support resistance levels:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch support resistance levels',
      details: error.message,
      symbol: req.params.symbol.toUpperCase(),
      timeframe: req.query.timeframe || 'daily'
    });
  }
});

// Get technical data with filtering and pagination
router.get('/data', async (req, res) => {
  const { 
    symbol,
    timeframe = 'daily',
    limit = 25,
    page = 1,
    startDate,
    endDate,
    sortBy = 'date',
    sortOrder = 'desc'
  } = req.query;

  console.log(`📊 [TECHNICAL] Fetching technical data with params:`, {
    symbol, timeframe, limit, page, startDate, endDate, sortBy, sortOrder
  });

  try {
    const offset = (parseInt(page) - 1) * parseInt(limit);
    const maxLimit = Math.min(parseInt(limit), 200);

    // Build WHERE clause
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramIndex = 1;

    // Symbol filter
    if (symbol && symbol.trim()) {
      whereClause += ` AND symbol = $${paramIndex}`;
      params.push(symbol.toUpperCase());
      paramIndex++;
    }

    // Date filters
    if (startDate) {
      whereClause += ` AND date >= $${paramIndex}`;
      params.push(startDate);
      paramIndex++;
    }

    if (endDate) {
      whereClause += ` AND date <= $${paramIndex}`;
      params.push(endDate);
      paramIndex++;
    }

    // Determine table name based on timeframe
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({
        success: false,
        error: 'Invalid timeframe',
        message: `Supported timeframes: ${validTimeframes.join(', ')}, got: ${timeframe}`
      });
    }

    const tableName = `technical_data_${timeframe}`;

    // Check if table exists
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      );
    `, [tableName]);

    if (!tableExists.rows[0].exists) {
      console.log(`Technical data table for ${timeframe} timeframe not found`);
      return res.status(404).json({
        success: false,
        error: `Technical data table for ${timeframe} timeframe not available`,
        message: `Table ${tableName} does not exist. Please ensure technical data has been loaded.`,
        timeframe
      });
    }

    // Get total count
    const countQuery = `
      SELECT COUNT(*) as total
      FROM ${tableName}
      ${whereClause}
    `;
    const countResult = await query(countQuery, params);
    const total = parseInt(countResult.rows[0].total);

    // Validate sortBy field
    const validSortFields = [
      'date', 'symbol', 'open', 'high', 'low', 'close', 'volume',
      'rsi', 'macd', 'macd_signal', 'macd_histogram', 'sma_20', 'sma_50',
      'ema_12', 'ema_26', 'bollinger_upper', 'bollinger_lower', 'bollinger_middle'
    ];
    const safeSortBy = validSortFields.includes(sortBy) ? sortBy : 'date';
    const safeSortOrder = sortOrder.toLowerCase() === 'asc' ? 'ASC' : 'DESC';

    // Get technical data
    const dataQuery = `
      SELECT 
        symbol,
        date,
        open,
        high,
        low,
        close,
        volume,
        rsi,
        macd,
        macd_signal,
        macd_histogram,
        sma_10,
        sma_20,
        sma_50,
        sma_150,
        sma_200,
        ema_4,
        ema_9,
        ema_21,
        ema_12,
        ema_26,
        bollinger_upper,
        bollinger_lower,
        bollinger_middle,
        stochastic_k,
        stochastic_d,
        williams_r,
        cci,
        adx,
        atr,
        obv,
        mfi,
        roc,
        momentum,
        ad,
        cmf,
        td_sequential,
        td_combo,
        marketwatch,
        dm,
        pivot_high,
        pivot_low,
        pivot_high_triggered,
        pivot_low_triggered
      FROM ${tableName}
      ${whereClause}
      ORDER BY ${safeSortBy} ${safeSortOrder}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    const finalParams = [...params, maxLimit, offset];
    const dataResult = await query(dataQuery, finalParams);

    const totalPages = Math.ceil(total / maxLimit);

    console.log(`✅ [TECHNICAL] Data query completed: ${dataResult.rows.length} results, total: ${total}`);

    if (!dataResult || !Array.isArray(dataResult.rows) || dataResult.rows.length === 0) {
      return res.json({
        success: true,
        data: [],
        total: 0,
        pagination: {
          page: parseInt(page),
          limit: maxLimit,
          total: 0,
          totalPages: 0,
          hasNext: false,
          hasPrev: false
        },
        filters: {
          symbol: symbol || null,
          timeframe,
          startDate: startDate || null,
          endDate: endDate || null
        },
        sorting: {
          sortBy: safeSortBy,
          sortOrder: safeSortOrder
        }
      });
    }

    res.json({
      success: true,
      data: dataResult.rows,
      total: total,
      pagination: {
        page: parseInt(page),
        limit: maxLimit,
        total,
        totalPages,
        hasNext: parseInt(page) < totalPages,
        hasPrev: parseInt(page) > 1
      },
      filters: {
        symbol: symbol || null,
        timeframe,
        startDate: startDate || null,
        endDate: endDate || null
      },
      sorting: {
        sortBy: safeSortBy,
        sortOrder: safeSortOrder
      }
    });

  } catch (error) {
    console.error('❌ [TECHNICAL] Technical data error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch technical data',
      details: error.message,
      timeframe
    });
  }
});

module.exports = router;
