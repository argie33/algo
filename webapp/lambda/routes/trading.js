const express = require('express');
const router = express.Router();
const { query } = require('../utils/database');

// Helper function to check if required tables exist
async function checkRequiredTables(tableNames) {
  const results = {};
  for (const tableName of tableNames) {
    try {
      const tableExistsResult = await query(
        `SELECT EXISTS (
          SELECT FROM information_schema.tables 
          WHERE table_schema = 'public' 
          AND table_name = $1
        );`,
        [tableName]
      );
      results[tableName] = tableExistsResult.rows[0].exists;
    } catch (error) {
      console.error(`Error checking table ${tableName}:`, error.message);
      results[tableName] = false;
    }
  }
  return results;
}

// Debug endpoint to check trading tables status
router.get('/debug', async (req, res) => {
  console.log('[TRADING] Debug endpoint called');
  
  try {
    // Check all trading tables
    const requiredTables = [
      'buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly',
      'market_data', 'company_profile', 'swing_trader'
    ];
    
    const tableStatus = await checkRequiredTables(requiredTables);
    
    // Get record counts for existing tables
    const recordCounts = {};
    for (const [tableName, exists] of Object.entries(tableStatus)) {
      if (exists) {
        try {
          const countResult = await query(`SELECT COUNT(*) as count FROM ${tableName}`);
          recordCounts[tableName] = parseInt(countResult.rows[0].count);
        } catch (error) {
          recordCounts[tableName] = { error: error.message };
        }
      } else {
        recordCounts[tableName] = 'Table does not exist';
      }
    }

    res.json({
      status: 'ok',
      timestamp: new Date().toISOString(),
      tables: tableStatus,
      recordCounts: recordCounts,
      endpoint: 'trading'
    });
  } catch (error) {
    console.error('[TRADING] Error in debug endpoint:', error);
    res.status(500).json({ 
      error: 'Failed to check trading tables', 
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get buy/sell signals by timeframe
router.get('/signals/:timeframe', async (req, res) => {
  console.log('[TRADING] Received request for /signals/:timeframe', {
    params: req.params,
    query: req.query,
    path: req.path,
    method: req.method,
    time: new Date().toISOString()
  });
  try {
    const { timeframe } = req.params;
    const { limit = 100, page = 1, symbol, signal_type, latest_only } = req.query;
    const pageNum = Math.max(1, parseInt(page));
    const pageSize = Math.max(1, parseInt(limit));
    const offset = (pageNum - 1) * pageSize;

    // Validate timeframe
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      console.warn('[TRADING] Invalid timeframe:', timeframe);
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = `buy_sell_${timeframe}`;
    
    // Defensive: Check if table exists before querying
    const tableExistsResult = await query(
      `SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      );`,
      [tableName]
    );
    if (!tableExistsResult.rows[0].exists) {
      console.error(`[TRADING] Table does not exist: ${tableName}`);
      return res.status(500).json({ 
        error: `Table ${tableName} does not exist in the database.`,
        details: `Expected table ${tableName} for trading signals. Please check your database schema.`
      });
    }

    // Build WHERE clause
    let whereClause = '';
    const queryParams = [];
    let paramCount = 0;

    const conditions = [];
    
    if (symbol) {
      paramCount++;
      conditions.push(`symbol = $${paramCount}`);
      queryParams.push(symbol.toUpperCase());
    }
    
    if (signal_type === 'buy') {
      conditions.push("signal = 'Buy'");
    } else if (signal_type === 'sell') {
      conditions.push("signal = 'Sell'");
    }

    if (conditions.length > 0) {
      whereClause = 'WHERE ' + conditions.join(' AND ');
    }

    // Build the main query - handle latest_only with window function
    let sqlQuery;
    if (latest_only === 'true') {
      sqlQuery = `
        WITH ranked_signals AS (
          SELECT 
            bs.symbol,
            bs.date,
            bs.signal,
            bs.buylevel as price,
            bs.stoplevel,
            bs.inposition,
            bs.strength,
            md.current_price,
            cp.short_name as company_name,
            cp.sector,
            md.market_cap,
            km.trailing_pe,
            km.dividend_yield,
            CASE 
              WHEN bs.signal = 'Buy' AND md.current_price > bs.buylevel 
              THEN ((md.regular_market_price - bs.buylevel) / bs.buylevel * 100)
              WHEN bs.signal = 'Sell' AND md.current_price < bs.buylevel 
              THEN ((bs.buylevel - md.regular_market_price) / bs.buylevel * 100)
              ELSE 0
            END as performance_percent,
            ROW_NUMBER() OVER (PARTITION BY bs.symbol ORDER BY bs.date DESC) as rn
          FROM ${tableName} bs
          LEFT JOIN market_data md ON bs.symbol = md.ticker
          LEFT JOIN company_profile cp ON bs.symbol = cp.ticker
          LEFT JOIN key_metrics km ON bs.symbol = km.ticker
          ${whereClause}
        )
        SELECT * FROM ranked_signals 
        WHERE rn = 1
        ORDER BY date DESC, symbol ASC
        LIMIT $${queryParams.length + 1} OFFSET $${queryParams.length + 2}
      `;
    } else {
      sqlQuery = `
        SELECT 
          bs.symbol,
          bs.date,
          bs.signal,
          bs.buylevel as price,
          bs.stoplevel,
          bs.inposition,
          bs.strength,
          md.current_price,
          cp.short_name as company_name,
          cp.sector,
          md.market_cap,
          km.trailing_pe,
          km.dividend_yield,
          CASE 
            WHEN bs.signal = 'Buy' AND md.current_price > bs.buylevel 
            THEN ((md.regular_market_price - bs.buylevel) / bs.buylevel * 100)
            WHEN bs.signal = 'Sell' AND md.current_price < bs.buylevel 
            THEN ((bs.buylevel - md.regular_market_price) / bs.buylevel * 100)
            ELSE 0
          END as performance_percent
        FROM ${tableName} bs
        LEFT JOIN market_data md ON bs.symbol = md.ticker
        LEFT JOIN company_profile cp ON bs.symbol = cp.ticker
        LEFT JOIN key_metrics km ON bs.symbol = km.ticker
        ${whereClause}
        ORDER BY bs.date DESC, bs.symbol ASC
        LIMIT $${queryParams.length + 1} OFFSET $${queryParams.length + 2}
      `;
    }

    // Count query for pagination
    let countQuery;
    if (latest_only === 'true') {
      countQuery = `
        WITH ranked_signals AS (
          SELECT bs.symbol,
            ROW_NUMBER() OVER (PARTITION BY bs.symbol ORDER BY bs.date DESC) as rn
          FROM ${tableName} bs
          ${whereClause}
        )
        SELECT COUNT(*) as total
        FROM ranked_signals 
        WHERE rn = 1
      `;
    } else {
      countQuery = `
        SELECT COUNT(*) as total
        FROM ${tableName} bs
        ${whereClause}
      `;
    }

    queryParams.push(pageSize, offset);

    console.log('[TRADING] Executing SQL:', sqlQuery, 'Params:', queryParams);
    console.log('[TRADING] Executing count SQL:', countQuery, 'Params:', queryParams.slice(0, paramCount));

    const [result, countResult] = await Promise.all([
      query(sqlQuery, queryParams),
      query(countQuery, queryParams.slice(0, paramCount))
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / pageSize);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      console.warn('[TRADING] No data found for query:', { timeframe, params: req.query });
      return res.status(200).json({ 
        success: true,
        data: [],
        timeframe,
        count: 0,
        pagination: {
          page: pageNum,
          limit: pageSize,
          total: 0,
          totalPages: 0,
          hasNext: false,
          hasPrev: false
        },
        metadata: {
          signal_type: signal_type || 'all',
          symbol: symbol || null,
          message: 'No trading signals found for the specified criteria'
        }
      });
    }

    console.log('[TRADING] Query returned', result.rows.length, 'rows out of', total, 'total');

    res.json({
      success: true,
      data: result.rows,
      timeframe,
      count: result.rows.length,
      pagination: {
        page: pageNum,
        limit: pageSize,
        total,
        totalPages,
        hasNext: pageNum < totalPages,
        hasPrev: pageNum > 1
      },
      metadata: {
        signal_type: signal_type || 'all',
        symbol: symbol || null
      }
    });

  } catch (error) {
    console.error('[TRADING] Error fetching trading signals:', error);
    res.status(500).json({ 
      error: 'Failed to fetch trading signals',
      message: error.message,
      stack: error.stack
    });
  }
});

// Get signals summary
router.get('/summary/:timeframe', async (req, res) => {
  try {
    const { timeframe } = req.params;
    
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: 'Invalid timeframe' });
    }

    const tableName = `buy_sell_${timeframe}`;
      const sqlQuery = `
      SELECT 
        COUNT(*) as total_signals,
        COUNT(CASE WHEN signal = 'Buy' THEN 1 END) as buy_signals,
        COUNT(CASE WHEN signal = 'Sell' THEN 1 END) as sell_signals,
        COUNT(CASE WHEN signal = 'Buy' THEN 1 END) as strong_buy,
        COUNT(CASE WHEN signal = 'Sell' THEN 1 END) as strong_sell,
        COUNT(CASE WHEN signal != 'None' AND signal IS NOT NULL THEN 1 END) as active_signals
      FROM ${tableName}
      WHERE date >= CURRENT_DATE - INTERVAL '30 days'
    `;

    const result = await query(sqlQuery);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      success: true,
      data: result.rows[0],
      timeframe,
      period: 'last_30_days'
    });

  } catch (error) {
    console.error('Error fetching signals summary:', error);
    res.status(500).json({ 
      error: 'Failed to fetch signals summary',
      message: error.message 
    });  }
});

// Get swing trading signals
router.get('/swing-signals', async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;

    const swingQuery = `
      SELECT 
        st.symbol,
        cp.short_name as company_name,
        st.signal,
        st.entry_price,
        st.stop_loss,
        st.target_price,
        st.risk_reward_ratio,
        st.date,
        md.current_price,
        CASE 
          WHEN st.signal = 'BUY' AND md.current_price >= st.target_price 
          THEN 'TARGET_HIT'
          WHEN st.signal = 'BUY' AND md.current_price <= st.stop_loss 
          THEN 'STOP_LOSS_HIT'
          WHEN st.signal = 'SELL' AND md.current_price <= st.target_price 
          THEN 'TARGET_HIT'
          WHEN st.signal = 'SELL' AND md.current_price >= st.stop_loss 
          THEN 'STOP_LOSS_HIT'
          ELSE 'ACTIVE'
        END as status
      FROM swing_trader st
      JOIN company_profile cp ON st.symbol = cp.ticker
      LEFT JOIN market_data md ON st.symbol = md.ticker
      ORDER BY st.date DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM swing_trader
    `;

    const [swingResult, countResult] = await Promise.all([
      query(swingQuery, [limit, offset]),
      query(countQuery)
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    if (!swingResult || !Array.isArray(swingResult.rows) || swingResult.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      data: swingResult.rows,
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
    console.error('Error fetching swing signals:', error);
    res.status(500).json({ error: 'Failed to fetch swing signals' });
  }
});

// Get technical indicators for a stock
router.get('/:ticker/technicals', async (req, res) => {
  try {
    const { ticker } = req.params;
    const timeframe = req.query.timeframe || 'daily'; // daily, weekly, monthly

    let tableName = 'latest_technicals_daily';
    if (timeframe === 'weekly') tableName = 'latest_technicals_weekly';
    if (timeframe === 'monthly') tableName = 'latest_technicals_monthly';

    const techQuery = `
      SELECT 
        symbol,
        date,
        sma_20,
        sma_50,
        sma_200,
        ema_12,
        ema_26,
        rsi_14,
        macd,
        macd_signal,
        macd_histogram,
        bb_upper,
        bb_middle,
        bb_lower,
        volume_sma
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 1
    `;

    const result = await query(techQuery, [ticker.toUpperCase()]);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      ticker: ticker.toUpperCase(),
      timeframe,
      data: result.rows[0]
    });

  } catch (error) {
    console.error('Error fetching technical indicators:', error);
    res.status(500).json({ error: 'Failed to fetch technical indicators' });
  }
});

// Get performance summary of recent signals
router.get('/performance', async (req, res) => {
  try {
    const days = parseInt(req.query.days) || 30;

    const performanceQuery = `
      SELECT 
        signal,
        COUNT(*) as total_signals,
        AVG(
          CASE 
            WHEN signal = 'BUY' AND md.current_price > bs.price 
            THEN ((md.current_price - bs.price) / bs.price * 100)
            WHEN signal = 'SELL' AND md.current_price < bs.price 
            THEN ((bs.price - md.current_price) / bs.price * 100)
            ELSE 0
          END
        ) as avg_performance,
        COUNT(
          CASE 
            WHEN signal = 'BUY' AND md.current_price > bs.price THEN 1
            WHEN signal = 'SELL' AND md.current_price < bs.price THEN 1
          END
        ) as winning_trades,
        (COUNT(
          CASE 
            WHEN signal = 'BUY' AND md.current_price > bs.price THEN 1
            WHEN signal = 'SELL' AND md.current_price < bs.price THEN 1
          END
        ) * 100.0 / COUNT(*)) as win_rate
      FROM buy_sell_daily bs
      LEFT JOIN market_data md ON bs.symbol = md.ticker
      WHERE bs.date >= NOW() - INTERVAL '${days} days'
      GROUP BY signal
    `;

    const result = await query(performanceQuery);

    if (!result || !Array.isArray(result.rows) || result.rows.length === 0) {
      return res.status(404).json({ error: 'No data found for this query' });
    }

    res.json({
      period_days: days,
      performance: result.rows,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching performance data:', error);
    res.status(500).json({ error: 'Failed to fetch performance data' });
  }
});

// Get current period active signals with enhanced filtering
router.get('/signals/current/:timeframe', async (req, res) => {
  console.log('[TRADING] Current period signals endpoint called');
  
  try {
    const { timeframe } = req.params;
    const { limit = 50, page = 1, signal_type, sector, min_strength = 0.4 } = req.query;
    const pageNum = Math.max(1, parseInt(page));
    const pageSize = Math.max(1, parseInt(limit));
    const offset = (pageNum - 1) * pageSize;

    // Validate timeframe
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: 'Invalid timeframe. Must be daily, weekly, or monthly' });
    }

    const tableName = `buy_sell_${timeframe}`;
    
    // Check if table exists
    const tableExistsResult = await query(
      `SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      );`,
      [tableName]
    );
    
    if (!tableExistsResult.rows[0].exists) {
      return res.status(500).json({ 
        error: `Table ${tableName} does not exist in the database.`
      });
    }

    // Build WHERE clause for current period active signals
    let whereClause = '';
    const queryParams = [];
    let paramCount = 0;

    const conditions = [];
    
    // Only get recent signals (last 30 days for daily, 12 weeks for weekly, 6 months for monthly)
    let dateFilter;
    if (timeframe === 'daily') {
      dateFilter = "date >= CURRENT_DATE - INTERVAL '30 days'";
    } else if (timeframe === 'weekly') {
      dateFilter = "date >= CURRENT_DATE - INTERVAL '12 weeks'";
    } else {
      dateFilter = "date >= CURRENT_DATE - INTERVAL '6 months'";
    }
    conditions.push(dateFilter);
    
    // Only get actual signals (not None or null)
    conditions.push("signal IS NOT NULL");
    conditions.push("signal != 'None'");
    conditions.push("signal != ''");
    
    // Filter by signal type if specified
    if (signal_type === 'buy') {
      conditions.push("signal = 'Buy'");
    } else if (signal_type === 'sell') {
      conditions.push("signal = 'Sell'");
    }
    
    // Filter by sector if specified
    if (sector && sector !== 'all') {
      paramCount++;
      conditions.push(`cp.sector = $${paramCount}`);
      queryParams.push(sector);
    }

    if (conditions.length > 0) {
      whereClause = 'WHERE ' + conditions.join(' AND ');
    }

    // Enhanced query with current period focus and signal strength calculation
    const sqlQuery = `
      WITH latest_signals AS (
        SELECT 
          bs.symbol,
          bs.date,
          bs.signal,
          bs.buylevel as entry_price,
          bs.stoplevel as stop_loss,
          bs.inposition,
          md.current_price,
          md.regular_market_price,
          cp.short_name as company_name,
          cp.sector,
          cp.industry,
          md.market_cap,
          km.trailing_pe,
          km.dividend_yield,
          km.beta,
          -- Calculate signal strength based on price movement and position
          CASE 
            WHEN bs.signal = 'Buy' THEN 
              LEAST(1.0, GREATEST(0.0, 
                (ABS(CAST(bs.signal AS NUMERIC)) / 100.0) * 
                CASE 
                  WHEN md.current_price > bs.buylevel THEN 1.2
                  ELSE 0.8
                END
              ))
            WHEN bs.signal = 'Sell' THEN 
              LEAST(1.0, GREATEST(0.0, 
                (ABS(CAST(bs.signal AS NUMERIC)) / 100.0) * 
                CASE 
                  WHEN md.current_price < bs.buylevel THEN 1.2
                  ELSE 0.8
                END
              ))
            ELSE 0.0
          END as signal_strength,
          -- Calculate performance since signal
          CASE 
            WHEN bs.signal = 'Buy' AND md.current_price > bs.buylevel AND bs.buylevel > 0
            THEN ((md.current_price - bs.buylevel) / bs.buylevel * 100)
            WHEN bs.signal = 'Sell' AND md.current_price < bs.buylevel AND bs.buylevel > 0
            THEN ((bs.buylevel - md.current_price) / bs.buylevel * 100)
            ELSE 0
          END as performance_percent,
          -- Days since signal
          EXTRACT(DAY FROM (CURRENT_DATE - bs.date)) as days_since_signal,
          -- Signal status
          CASE 
            WHEN bs.signal = 'Buy' AND md.current_price > bs.buylevel THEN 'WINNING'
            WHEN bs.signal = 'Sell' AND md.current_price < bs.buylevel THEN 'WINNING'
            WHEN bs.signal = 'Buy' AND bs.stoplevel > 0 AND md.current_price <= bs.stoplevel THEN 'STOPPED'
            WHEN bs.signal = 'Sell' AND bs.stoplevel > 0 AND md.current_price >= bs.stoplevel THEN 'STOPPED'
            ELSE 'ACTIVE'
          END as signal_status,
          ROW_NUMBER() OVER (PARTITION BY bs.symbol ORDER BY bs.date DESC) as rn
        FROM ${tableName} bs
        LEFT JOIN market_data md ON bs.symbol = md.ticker
        LEFT JOIN company_profile cp ON bs.symbol = cp.ticker
        LEFT JOIN key_metrics km ON bs.symbol = km.ticker
        ${whereClause}
      )
      SELECT *
      FROM latest_signals 
      WHERE rn = 1 
        AND signal_strength >= $${queryParams.length + 1}
      ORDER BY 
        signal_strength DESC,
        ABS(performance_percent) DESC,
        date DESC
      LIMIT $${queryParams.length + 2} OFFSET $${queryParams.length + 3}
    `;

    // Count query for pagination
    const countQuery = `
      WITH latest_signals AS (
        SELECT 
          bs.symbol,
          CASE 
            WHEN bs.signal = 'Buy' THEN 
              LEAST(1.0, GREATEST(0.0, (ABS(CAST(bs.signal AS NUMERIC)) / 100.0)))
            WHEN bs.signal = 'Sell' THEN 
              LEAST(1.0, GREATEST(0.0, (ABS(CAST(bs.signal AS NUMERIC)) / 100.0)))
            ELSE 0.0
          END as signal_strength,
          ROW_NUMBER() OVER (PARTITION BY bs.symbol ORDER BY bs.date DESC) as rn
        FROM ${tableName} bs
        LEFT JOIN company_profile cp ON bs.symbol = cp.ticker
        ${whereClause}
      )
      SELECT COUNT(*) as total
      FROM latest_signals 
      WHERE rn = 1 
        AND signal_strength >= $${queryParams.length + 1}
    `;

    queryParams.push(parseFloat(min_strength), pageSize, offset);

    console.log('[TRADING] Executing current period query:', sqlQuery);
    console.log('[TRADING] Query params:', queryParams);

    const [result, countResult] = await Promise.all([
      query(sqlQuery, queryParams),
      query(countQuery, queryParams.slice(0, queryParams.length - 2))
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / pageSize);

    res.json({
      success: true,
      data: result.rows,
      timeframe,
      current_period: true,
      count: result.rows.length,
      pagination: {
        page: pageNum,
        limit: pageSize,
        total,
        totalPages,
        hasNext: pageNum < totalPages,
        hasPrev: pageNum > 1
      },
      metadata: {
        signal_type: signal_type || 'all',
        sector: sector || 'all',
        min_strength: parseFloat(min_strength),
        period_description: timeframe === 'daily' ? 'Last 30 days' : 
                           timeframe === 'weekly' ? 'Last 12 weeks' : 'Last 6 months',
        message: result.rows.length === 0 ? 'No active signals found for current period' : null
      }
    });

  } catch (error) {
    console.error('[TRADING] Error fetching current period signals:', error);
    res.status(500).json({ 
      error: 'Failed to fetch current period signals',
      message: error.message
    });
  }
});

// Get signal analytics and summary for current period
router.get('/analytics/:timeframe', async (req, res) => {
  try {
    const { timeframe } = req.params;
    
    const validTimeframes = ['daily', 'weekly', 'monthly'];
    if (!validTimeframes.includes(timeframe)) {
      return res.status(400).json({ error: 'Invalid timeframe' });
    }

    const tableName = `buy_sell_${timeframe}`;
    
    // Get comprehensive analytics
    const analyticsQuery = `
      WITH signal_analytics AS (
        SELECT 
          bs.symbol,
          bs.signal,
          bs.date,
          bs.buylevel,
          md.current_price,
          cp.sector,
          CASE 
            WHEN bs.signal = 'Buy' AND md.current_price > bs.buylevel AND bs.buylevel > 0
            THEN ((md.current_price - bs.buylevel) / bs.buylevel * 100)
            WHEN bs.signal = 'Sell' AND md.current_price < bs.buylevel AND bs.buylevel > 0
            THEN ((bs.buylevel - md.current_price) / bs.buylevel * 100)
            ELSE 0
          END as performance_percent,
          CASE 
            WHEN bs.signal = 'Buy' AND md.current_price > bs.buylevel THEN 1
            WHEN bs.signal = 'Sell' AND md.current_price < bs.buylevel THEN 1
            ELSE 0
          END as is_winning
        FROM ${tableName} bs
        LEFT JOIN market_data md ON bs.symbol = md.ticker
        LEFT JOIN company_profile cp ON bs.symbol = cp.ticker
        WHERE bs.date >= CURRENT_DATE - INTERVAL '30 days'
          AND bs.signal IS NOT NULL 
          AND bs.signal != 'None'
          AND bs.signal != ''
      )
      SELECT 
        COUNT(*) as total_signals,
        COUNT(CASE WHEN signal = 'Buy' THEN 1 END) as buy_signals,
        COUNT(CASE WHEN signal = 'Sell' THEN 1 END) as sell_signals,
        COUNT(CASE WHEN is_winning = 1 THEN 1 END) as winning_signals,
        AVG(CASE WHEN is_winning = 1 THEN performance_percent END) as avg_winning_performance,
        AVG(CASE WHEN is_winning = 0 THEN performance_percent END) as avg_losing_performance,
        MAX(performance_percent) as best_performance,
        MIN(performance_percent) as worst_performance,
        COUNT(DISTINCT sector) as sectors_covered,
        COUNT(DISTINCT symbol) as unique_symbols
      FROM signal_analytics
    `;

    // Get sector breakdown
    const sectorQuery = `
      SELECT 
        cp.sector,
        COUNT(*) as signal_count,
        AVG(CASE 
          WHEN bs.signal = 'Buy' AND md.current_price > bs.buylevel AND bs.buylevel > 0
          THEN ((md.current_price - bs.buylevel) / bs.buylevel * 100)
          WHEN bs.signal = 'Sell' AND md.current_price < bs.buylevel AND bs.buylevel > 0
          THEN ((bs.buylevel - md.current_price) / bs.buylevel * 100)
          ELSE 0
        END) as avg_performance
      FROM ${tableName} bs
      LEFT JOIN market_data md ON bs.symbol = md.ticker
      LEFT JOIN company_profile cp ON bs.symbol = cp.ticker
      WHERE bs.date >= CURRENT_DATE - INTERVAL '30 days'
        AND bs.signal IS NOT NULL 
        AND bs.signal != 'None'
        AND bs.signal != ''
        AND cp.sector IS NOT NULL
      GROUP BY cp.sector
      ORDER BY signal_count DESC
    `;

    const [analyticsResult, sectorResult] = await Promise.all([
      query(analyticsQuery),
      query(sectorQuery)
    ]);

    const analytics = analyticsResult.rows[0];
    const sectorBreakdown = sectorResult.rows;

    // Calculate win rate
    const winRate = analytics.total_signals > 0 ? 
      (analytics.winning_signals / analytics.total_signals * 100) : 0;

    res.json({
      success: true,
      timeframe,
      period: 'last_30_days',
      summary: {
        total_signals: parseInt(analytics.total_signals),
        buy_signals: parseInt(analytics.buy_signals),
        sell_signals: parseInt(analytics.sell_signals),
        winning_signals: parseInt(analytics.winning_signals),
        win_rate: winRate,
        avg_winning_performance: parseFloat(analytics.avg_winning_performance) || 0,
        avg_losing_performance: parseFloat(analytics.avg_losing_performance) || 0,
        best_performance: parseFloat(analytics.best_performance) || 0,
        worst_performance: parseFloat(analytics.worst_performance) || 0,
        sectors_covered: parseInt(analytics.sectors_covered),
        unique_symbols: parseInt(analytics.unique_symbols)
      },
      sector_breakdown: sectorBreakdown.map(sector => ({
        sector: sector.sector,
        signal_count: parseInt(sector.signal_count),
        avg_performance: parseFloat(sector.avg_performance) || 0
      })),
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('[TRADING] Error fetching analytics:', error);
    res.status(500).json({ 
      error: 'Failed to fetch signal analytics',
      message: error.message 
    });
  }
});

// Get aggregate signals across all timeframes for a symbol
router.get('/aggregate/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    
    // Get latest signals from all timeframes for the symbol
    const aggregateQuery = `
      WITH daily_signals AS (
        SELECT 
          symbol, signal, strength, date, 'daily' as timeframe,
          ROW_NUMBER() OVER (ORDER BY date DESC) as rn
        FROM buy_sell_daily 
        WHERE symbol = $1 AND signal != 'None'
        ORDER BY date DESC
        LIMIT 1
      ),
      weekly_signals AS (
        SELECT 
          symbol, signal, strength, date, 'weekly' as timeframe,
          ROW_NUMBER() OVER (ORDER BY date DESC) as rn
        FROM buy_sell_weekly 
        WHERE symbol = $1 AND signal != 'None'
        ORDER BY date DESC
        LIMIT 1
      ),
      monthly_signals AS (
        SELECT 
          symbol, signal, strength, date, 'monthly' as timeframe,
          ROW_NUMBER() OVER (ORDER BY date DESC) as rn
        FROM buy_sell_monthly 
        WHERE symbol = $1 AND signal != 'None'
        ORDER BY date DESC
        LIMIT 1
      )
      SELECT * FROM daily_signals WHERE rn = 1
      UNION ALL
      SELECT * FROM weekly_signals WHERE rn = 1
      UNION ALL
      SELECT * FROM monthly_signals WHERE rn = 1
    `;

    const signalsResult = await query(aggregateQuery, [symbol.toUpperCase()]);
    const signals = signalsResult.rows;

    if (signals.length === 0) {
      return res.json({
        symbol: symbol.toUpperCase(),
        aggregate_signal: 'Hold',
        confidence: 50.0,
        score: 0.0,
        signals: {},
        recommendation: 'Hold - No recent signals found',
        timestamp: new Date().toISOString()
      });
    }

    // Calculate aggregate signal using weighted approach
    const timeframeWeights = { daily: 0.50, weekly: 0.30, monthly: 0.20 };
    let totalWeight = 0;
    let weightedScore = 0;
    const signalAlignment = {};

    signals.forEach(signal => {
      const weight = timeframeWeights[signal.timeframe] || 0;
      const strength = parseFloat(signal.strength) || 50;
      
      let signalScore = 0;
      if (signal.signal === 'Buy') {
        signalScore = strength;
      } else if (signal.signal === 'Sell') {
        signalScore = -strength;
      }

      weightedScore += signalScore * weight;
      totalWeight += weight;
      signalAlignment[signal.timeframe] = signal.signal;
    });

    const finalScore = totalWeight > 0 ? weightedScore / totalWeight : 0;

    // Determine aggregate signal
    let aggregateSignal = 'Hold';
    let confidence = 50;

    if (finalScore > 20) {
      aggregateSignal = 'Buy';
      confidence = Math.min(100, Math.abs(finalScore));
    } else if (finalScore < -20) {
      aggregateSignal = 'Sell';
      confidence = Math.min(100, Math.abs(finalScore));
    } else {
      confidence = 50 - Math.abs(finalScore);
    }

    // Calculate alignment bonus
    const signalTypes = Object.values(signalAlignment);
    let alignmentBonus = 0;
    
    if (signalTypes.length >= 2) {
      const uniqueSignals = [...new Set(signalTypes)];
      if (uniqueSignals.length === 1 && uniqueSignals[0] !== 'None') {
        alignmentBonus = 15; // All aligned
      } else {
        const buyCount = signalTypes.filter(s => s === 'Buy').length;
        const sellCount = signalTypes.filter(s => s === 'Sell').length;
        if (buyCount >= 2 || sellCount >= 2) {
          alignmentBonus = 10; // Majority aligned
        }
      }
    }

    confidence = Math.min(100, confidence + alignmentBonus);

    // Get recommendation
    let recommendation;
    if (confidence < 40) {
      recommendation = "Watch - Low confidence signal";
    } else if (confidence < 60) {
      recommendation = `Consider ${aggregateSignal} - Moderate confidence`;
    } else if (confidence < 80) {
      recommendation = `Strong ${aggregateSignal} signal - High confidence`;
    } else {
      recommendation = `Very Strong ${aggregateSignal} signal - Execute trade`;
    }

    // Format signals object
    const signalsObj = {};
    signals.forEach(signal => {
      signalsObj[signal.timeframe] = {
        signal: signal.signal,
        strength: parseFloat(signal.strength),
        date: signal.date
      };
    });

    res.json({
      symbol: symbol.toUpperCase(),
      aggregate_signal: aggregateSignal,
      confidence: Math.round(confidence * 10) / 10,
      score: Math.round(finalScore * 10) / 10,
      signals: signalsObj,
      alignment_bonus: alignmentBonus,
      recommendation,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('[TRADING] Error fetching aggregate signals:', error);
    res.status(500).json({ 
      error: 'Failed to fetch aggregate signals',
      message: error.message 
    });
  }
});

// Get aggregate signals summary for all symbols
router.get('/aggregate', async (req, res) => {
  try {
    const { limit = 50, min_confidence = 60, signal_type } = req.query;
    
    // Get symbols with recent signals
    const symbolsQuery = `
      SELECT DISTINCT symbol 
      FROM (
        SELECT symbol FROM buy_sell_daily WHERE date >= CURRENT_DATE - INTERVAL '30 days' AND signal != 'None'
        UNION
        SELECT symbol FROM buy_sell_weekly WHERE date >= CURRENT_DATE - INTERVAL '12 weeks' AND signal != 'None'
        UNION
        SELECT symbol FROM buy_sell_monthly WHERE date >= CURRENT_DATE - INTERVAL '6 months' AND signal != 'None'
      ) symbols
      LIMIT $1
    `;

    const symbolsResult = await query(symbolsQuery, [parseInt(limit)]);
    const symbols = symbolsResult.rows.map(row => row.symbol);

    const aggregateSignals = [];

    // Process each symbol for aggregate signals
    for (const symbol of symbols) {
      const aggregateQuery = `
        WITH daily_signals AS (
          SELECT signal, strength, date, 'daily' as timeframe
          FROM buy_sell_daily 
          WHERE symbol = $1 AND signal != 'None'
          ORDER BY date DESC LIMIT 1
        ),
        weekly_signals AS (
          SELECT signal, strength, date, 'weekly' as timeframe
          FROM buy_sell_weekly 
          WHERE symbol = $1 AND signal != 'None'
          ORDER BY date DESC LIMIT 1
        ),
        monthly_signals AS (
          SELECT signal, strength, date, 'monthly' as timeframe
          FROM buy_sell_monthly 
          WHERE symbol = $1 AND signal != 'None'
          ORDER BY date DESC LIMIT 1
        )
        SELECT * FROM daily_signals
        UNION ALL
        SELECT * FROM weekly_signals
        UNION ALL
        SELECT * FROM monthly_signals
      `;

      const signalsResult = await query(aggregateQuery, [symbol]);
      const signals = signalsResult.rows;

      if (signals.length === 0) continue;

      // Calculate aggregate for this symbol
      const timeframeWeights = { daily: 0.50, weekly: 0.30, monthly: 0.20 };
      let totalWeight = 0;
      let weightedScore = 0;

      signals.forEach(signal => {
        const weight = timeframeWeights[signal.timeframe] || 0;
        const strength = parseFloat(signal.strength) || 50;
        
        let signalScore = 0;
        if (signal.signal === 'Buy') {
          signalScore = strength;
        } else if (signal.signal === 'Sell') {
          signalScore = -strength;
        }

        weightedScore += signalScore * weight;
        totalWeight += weight;
      });

      const finalScore = totalWeight > 0 ? weightedScore / totalWeight : 0;
      let aggregateSignal = 'Hold';
      let confidence = 50;

      if (finalScore > 20) {
        aggregateSignal = 'Buy';
        confidence = Math.min(100, Math.abs(finalScore));
      } else if (finalScore < -20) {
        aggregateSignal = 'Sell';
        confidence = Math.min(100, Math.abs(finalScore));
      } else {
        confidence = 50 - Math.abs(finalScore);
      }

      // Apply filters
      if (confidence >= parseFloat(min_confidence)) {
        if (!signal_type || aggregateSignal.toLowerCase() === signal_type.toLowerCase()) {
          aggregateSignals.push({
            symbol,
            aggregate_signal: aggregateSignal,
            confidence: Math.round(confidence * 10) / 10,
            score: Math.round(finalScore * 10) / 10,
            signal_count: signals.length
          });
        }
      }
    }

    // Sort by confidence descending
    aggregateSignals.sort((a, b) => b.confidence - a.confidence);

    res.json({
      success: true,
      data: aggregateSignals,
      count: aggregateSignals.length,
      filters: {
        min_confidence: parseFloat(min_confidence),
        signal_type: signal_type || 'all',
        limit: parseInt(limit)
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('[TRADING] Error fetching aggregate signals summary:', error);
    res.status(500).json({ 
      error: 'Failed to fetch aggregate signals summary',
      message: error.message 
    });
  }
});

module.exports = router;
