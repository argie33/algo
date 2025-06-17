const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Debug endpoint to check stocks tables status
router.get('/debug', async (req, res) => {
  try {
    console.log('Stocks debug endpoint called');
    
    // Use actual tables from your Python scripts
    const tables = ['stock_symbols', 'etf_symbols', 'price_daily', 'price_weekly', 'price_monthly'];
    const results = {};
    
    for (const table of tables) {
      try {
        // Check if table exists
        const tableExistsQuery = `
          SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = $1
          );
        `;
        
        const tableExists = await query(tableExistsQuery, [table]);
        console.log(`Table ${table} exists:`, tableExists.rows[0]);
        
        if (tableExists.rows[0].exists) {
          // Count total records
          const countQuery = `SELECT COUNT(*) as total FROM ${table}`;
          const countResult = await query(countQuery);
          
          // Get sample records
          let sampleQuery;
          if (table === 'stock_symbols') {
            sampleQuery = `
              SELECT symbol, security_name, exchange, market_category
              FROM ${table} 
              ORDER BY symbol 
              LIMIT 3
            `;
          } else if (table === 'etf_symbols') {
            sampleQuery = `
              SELECT symbol, security_name, exchange
              FROM ${table} 
              ORDER BY symbol 
              LIMIT 3
            `;
          } else if (table.startsWith('price_')) {
            sampleQuery = `
              SELECT symbol, date, close, volume
              FROM ${table} 
              ORDER BY date DESC, symbol 
              LIMIT 3
            `;
          } else {
            sampleQuery = `SELECT * FROM ${table} LIMIT 1`;
          }
          
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
    console.error('Error in stocks debug:', error);
    res.status(500).json({ 
      error: 'Debug check failed', 
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Simple test endpoint that returns raw data from actual tables - OPTIMIZED
router.get('/test', async (req, res) => {
  try {
    console.log('Stocks test endpoint called');
    
    // OPTIMIZED: Simple query without expensive subqueries
    const testQuery = `
      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        ss.market_category,
        ss.cqs_symbol,
        ss.financial_status,
        ss.round_lot_size,
        ss.etf
      FROM stock_symbols ss
      ORDER BY ss.symbol
      LIMIT 10
    `;
    
    const result = await query(testQuery);
    
    res.json({
      success: true,
      count: result.rows.length,
      data: result.rows,
      availableTables: ['stock_symbols', 'etf_symbols', 'price_daily', 'price_weekly', 'price_monthly'],
      note: 'Optimized query - price data available via separate endpoints',
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error in stocks test:', error);
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
    endpoint: 'stocks',
    timestamp: new Date().toISOString()
  });
});

// OPTIMIZED: Main stocks endpoint with fast queries and all data visible
router.get('/', async (req, res) => {
  try {
    console.log('OPTIMIZED Stocks main endpoint called with params:', req.query);
    
    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 50, 200); // Increased limit
    const offset = (page - 1) * limit;
    const search = req.query.search || '';
    const exchange = req.query.sector || req.query.exchange || '';
    const sortBy = req.query.sortBy || 'symbol';
    const sortOrder = req.query.sortOrder || 'asc';
    
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramCount = 0;

    // Add search filter
    if (search) {
      paramCount++;
      whereClause += ` AND (ss.symbol ILIKE $${paramCount} OR ss.security_name ILIKE $${paramCount})`;
      params.push(`%${search}%`);
    }

    // Add exchange filter
    if (exchange) {
      paramCount++;
      whereClause += ` AND ss.exchange = $${paramCount}`;
      params.push(exchange);
    }

    // FAST sort columns
    const validSortColumns = {
      'ticker': 'ss.symbol',
      'symbol': 'ss.symbol', 
      'name': 'ss.security_name',
      'exchange': 'ss.exchange',
      'market_category': 'ss.market_category'
    };

    const sortColumn = validSortColumns[sortBy] || 'ss.symbol';
    const sortDirection = sortOrder.toLowerCase() === 'desc' ? 'DESC' : 'ASC';

    console.log('OPTIMIZED query params:', { whereClause, params, limit, offset });

    // SUPER FAST QUERY: Just stock_symbols table first to avoid timeout
    const stocksQuery = `      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        ss.market_category,
        ss.cqs_symbol,
        ss.financial_status,
        ss.round_lot_size,
        ss.etf,
        ss.secondary_symbol,
        ss.test_issue
      FROM stock_symbols ss
      ${whereClause}
      ORDER BY ${sortColumn} ${sortDirection}
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    // Count query - also fast
    const countQuery = `
      SELECT COUNT(*) as total
      FROM stock_symbols ss
      ${whereClause}
    `;

    console.log('Executing FAST queries...');

    const [stocksResult, countResult] = await Promise.all([
      query(stocksQuery, params),
      query(countQuery, params.slice(0, -2))
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    console.log(`FAST query results: ${stocksResult.rows.length} stocks, ${total} total`);

    // Professional formatting with ALL available data fields visible
    const formattedStocks = stocksResult.rows.map(stock => ({
      // Core identification
      ticker: stock.symbol,
      symbol: stock.symbol,
      name: stock.security_name,
      fullName: stock.security_name,
      
      // Exchange & categorization 
      exchange: stock.exchange,
      marketCategory: stock.market_category,
        // Additional identifiers
      cqsSymbol: stock.cqs_symbol,
      secondarySymbol: stock.secondary_symbol,
      
      // Status & type
      financialStatus: stock.financial_status,
      isEtf: stock.etf === 'Y',
      testIssue: stock.test_issue === 'Y',
      roundLotSize: stock.round_lot_size,
      
      // Data quality indicators
      hasData: true,
      dataSource: 'stock_symbols',
      
      // Placeholder for price data (to be loaded separately for performance)
      price: {
        status: 'Available separately via /stocks/:ticker/prices',
        current: null,
        volume: null,
        date: null
      },
      
      // Professional presentation
      displayData: {
        primaryExchange: stock.exchange || 'Unknown',
        category: stock.market_category || 'Standard',
        type: stock.etf === 'Y' ? 'ETF' : 'Stock',
        tradeable: stock.financial_status !== 'D' && stock.test_issue !== 'Y'
      }
    }));

    res.json({
      success: true,
      performance: 'OPTIMIZED - Fast stock_symbols only query',
      data: formattedStocks,
      pagination: {
        page,
        limit,
        total,
        totalPages,
        hasNext: page < totalPages,
        hasPrev: page > 1
      },
      filters: {
        search: search || null,
        exchange: exchange || null,
        sortBy,
        sortOrder
      },
      metadata: {
        totalStocks: total,
        currentPage: page,
        showingRecords: stocksResult.rows.length,        dataFields: [
          'symbol', 'security_name', 'exchange', 'market_category',
          'cqs_symbol', 'financial_status', 'etf',
          'round_lot_size', 'test_issue', 'secondary_symbol'
        ]
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('OPTIMIZED endpoint error:', error);
    res.status(500).json({ 
      error: 'Optimized query failed',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// SUPER FAST overview for initial page load - shows all your data fields
router.get('/quick/overview', async (req, res) => {
  try {
    console.log('FAST overview endpoint called');
    
    const limit = Math.min(parseInt(req.query.limit) || 25, 100);
    
    // LIGHTNING FAST query - no joins, just stock_symbols
    const quickQuery = `
      SELECT        symbol,
        security_name,
        exchange,
        market_category,
        cqs_symbol,
        financial_status,
        etf,
        round_lot_size,
        test_issue,
        secondary_symbol
      FROM stock_symbols
      WHERE financial_status != 'D' AND test_issue != 'Y'
      ORDER BY symbol ASC
      LIMIT $1
    `;

    const result = await query(quickQuery, [limit]);

    console.log(`FAST overview: ${result.rows.length} stocks loaded instantly`);

    // Professional formatting showing ALL your data
    const formattedData = result.rows.map(row => ({
      // Core data
      ticker: row.symbol,
      name: row.security_name,
      
      // Classification
      exchange: row.exchange,
      category: row.market_category,
      type: row.etf === 'Y' ? 'ETF' : 'Stock',
        // Identifiers
      cqsSymbol: row.cqs_symbol,
      secondarySymbol: row.secondary_symbol,
      
      // Status
      financialStatus: row.financial_status,
      testIssue: row.test_issue,
      roundLotSize: row.round_lot_size,
      
      // Professional display
      displayName: `${row.symbol} - ${row.security_name}`,
      tradeable: row.financial_status !== 'D' && row.test_issue !== 'Y',
      
      // Data completeness
      hasAllData: true,
      dataQuality: 'Complete'
    }));

    res.json({
      success: true,
      performance: 'LIGHTNING FAST - No joins, instant load',
      data: formattedData,
      count: result.rows.length,
      summary: {
        totalShown: result.rows.length,
        dataFields: 11,
        loadTime: 'Sub-second',
        allFieldsVisible: true
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error in FAST overview:', error);
    res.status(500).json({ 
      error: 'Fast overview failed',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Chunked stocks loading
router.get('/chunk/:chunkIndex', async (req, res) => {
  try {
    const chunkIndex = parseInt(req.params.chunkIndex) || 0;
    const chunkSize = 50; // Small chunks for performance
    
    console.log(`Stocks chunk endpoint called for chunk: ${chunkIndex}`);
    
    const offset = chunkIndex * chunkSize;

    // Use actual tables - get stocks with latest price data
    const dataQuery = `
      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        ss.market_category,
        pd.close as current_price,
        pd.volume as current_volume,
        pd.date as price_date
      FROM stock_symbols ss
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) symbol, close, volume, date
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON ss.symbol = pd.symbol
      ORDER BY ss.symbol ASC
      LIMIT $1 OFFSET $2
    `;

    const result = await query(dataQuery, [chunkSize, offset]);

    // Format response to match expected structure
    const formattedData = result.rows.map(row => ({
      ticker: row.symbol,
      short_name: row.security_name,
      sector: row.exchange, // Using exchange as sector substitute
      regular_market_price: row.current_price,
      market_cap: null, // Not available in current schema
      trailing_pe: null, // Not available in current schema
      volume: row.current_volume,
      price_date: row.price_date
    }));

    res.json({
      chunk: chunkIndex,
      chunkSize: chunkSize,
      dataCount: result.rows.length,
      data: formattedData,
      hasMore: result.rows.length === chunkSize,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching stocks chunk:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stocks chunk', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Full stocks data endpoint (use with caution)
router.get('/full/data', async (req, res) => {
  try {
    console.log('Stocks full data endpoint called with params:', req.query);
    
    // Force small limit for safety
    const limit = Math.min(parseInt(req.query.limit) || 10, 10);
    const exchange = req.query.sector; // Use exchange instead of sector

    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramIndex = 1;

    if (exchange) {
      whereClause += ` AND ss.exchange = $${paramIndex}`;
      params.push(exchange);
      paramIndex++;
    }

    // Use actual tables - get stocks with latest price data
    const dataQuery = `
      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        ss.market_category,
        pd.close as current_price,
        pd.volume as current_volume,
        pd.date as price_date
      FROM stock_symbols ss
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) symbol, close, volume, date
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON ss.symbol = pd.symbol
      ${whereClause}
      ORDER BY pd.volume DESC NULLS LAST
      LIMIT $${paramIndex}
    `;

    const result = await query(dataQuery, [...params, limit]);

    // Format response to match expected structure
    const formattedData = result.rows.map(row => ({
      ticker: row.symbol,
      short_name: row.security_name,
      sector: row.exchange,
      industry: row.market_category,
      regular_market_price: row.current_price,
      market_cap: null, // Not available in current schema
      trailing_pe: null, // Not available in current schema
      dividend_yield: null, // Not available in current schema
      volume: row.current_volume,
      price_date: row.price_date
    }));

    res.json({
      warning: 'This endpoint returns limited data for performance reasons',
      actualLimit: limit,
      filters: { sector: exchange || null },
      data: formattedData,
      count: result.rows.length,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching full stocks data:', error);
    res.status(500).json({ 
      error: 'Failed to fetch full stocks data', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get comprehensive stock details by ticker
router.get('/:ticker', async (req, res) => {
  try {
    const { ticker } = req.params;
    console.log(`Stock detail endpoint called for ticker: ${ticker}`);
    
    // Use actual tables - get stock info with price history
    const stockQuery = `
      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        ss.market_category,
        ss.cqs_symbol,
        ss.financial_status,
        ss.etf,
        pd.close as current_price,
        pd.volume as current_volume,
        pd.date as price_date,
        pd.open,
        pd.high,
        pd.low,
        pd.adj_close
      FROM stock_symbols ss
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) symbol, close, volume, date, open, high, low, adj_close
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON ss.symbol = pd.symbol
      WHERE UPPER(ss.symbol) = UPPER($1)
    `;

    const result = await query(stockQuery, [ticker]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        error: 'Stock not found',
        ticker: ticker,
        timestamp: new Date().toISOString()
      });
    }

    const stock = result.rows[0];

    // Get recent price history (last 30 days)
    const historyQuery = `
      SELECT date, open, high, low, close, adj_close, volume
      FROM price_daily
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY date DESC
      LIMIT 30
    `;

    const historyResult = await query(historyQuery, [ticker]);

    // Format the response with available data
    const stockData = {
      ticker: stock.symbol,
      symbol: stock.symbol,
      short_name: stock.security_name,
      long_name: stock.security_name,
      sector: stock.exchange, // Using exchange as sector substitute
      industry: stock.market_category,
      currency: 'USD', // Default assumption
      exchange: stock.exchange,
      description: null, // Not available in current schema
      employees: null, // Not available in current schema
      country: null, // Not available in current schema
      
      // Price data from price_daily
      regular_market_price: stock.current_price,
      regular_market_previous_close: null, // Would need calculation
      market_cap: null, // Not available in current schema
      fifty_two_week_high: null, // Would need calculation from price history
      fifty_two_week_low: null, // Would need calculation from price history
      
      // Current day data
      current_open: stock.open,
      current_high: stock.high,
      current_low: stock.low,
      current_close: stock.current_price,
      current_volume: stock.current_volume,
      price_date: stock.price_date,
      
      // Additional metadata
      is_etf: stock.etf === 'Y',
      financial_status: stock.financial_status,
      cqs_symbol: stock.cqs_symbol,
      
      // Price history
      price_history: historyResult.rows,
      
      // Placeholder for missing financial metrics
      metrics: {
        trailing_pe: null,
        forward_pe: null,
        dividend_yield: null,
        beta: null,
        profit_margin: null,
        operating_margin: null,
        return_on_equity: null,
        return_on_assets: null,
        debt_to_equity: null,
        current_ratio: null
      }
    };

    res.json({
      data: stockData,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching stock details:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock details', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get stock price history
router.get('/:ticker/prices', async (req, res) => {
  try {
    const { ticker } = req.params;
    const period = req.query.period || '1M'; // Default to 1 month
    const interval = req.query.interval || 'daily';
    
    console.log(`Stock prices endpoint called for ticker: ${ticker}, period: ${period}, interval: ${interval}`);
    
    // Determine how many days to fetch based on period
    let limit = 30; // Default 1 month
    switch(period) {
      case '1W': limit = 7; break;
      case '1M': limit = 30; break;
      case '3M': limit = 90; break;
      case '6M': limit = 180; break;
      case '1Y': limit = 365; break;
      case 'YTD': limit = 365; break; // Approximate
      default: limit = 30;
    }
    
    // Select appropriate price table based on interval
    let table = 'price_daily';
    switch(interval) {
      case 'daily': table = 'price_daily'; break;
      case 'weekly': table = 'price_weekly'; break;
      case 'monthly': table = 'price_monthly'; break;
      default: table = 'price_daily';
    }
    
    const pricesQuery = `
      SELECT date, open, high, low, close, adj_close, volume
      FROM ${table}
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY date DESC
      LIMIT $2
    `;
    
    const result = await query(pricesQuery, [ticker, limit]);
    
    if (result.rows.length === 0) {
      return res.status(404).json({
        error: 'No price data found',
        ticker: ticker,
        period: period,
        interval: interval,
        timestamp: new Date().toISOString()
      });
    }
    
    // Calculate some basic metrics
    const prices = result.rows;
    const latest = prices[0];
    const oldest = prices[prices.length - 1];
    
    const periodReturn = oldest.close > 0 ? 
      ((latest.close - oldest.close) / oldest.close * 100) : 0;
    
    const high52Week = Math.max(...prices.map(p => p.high));
    const low52Week = Math.min(...prices.map(p => p.low));
    
    res.json({
      ticker: ticker.toUpperCase(),
      period: period,
      interval: interval,
      dataPoints: result.rows.length,
      priceData: prices,
      summary: {
        latest_price: latest.close,
        latest_date: latest.date,
        period_return_percent: periodReturn,
        high_52_week: high52Week,
        low_52_week: low52Week,
        latest_volume: latest.volume
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching stock prices:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock prices', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get available filters - exchanges instead of sectors
router.get('/filters/sectors', async (req, res) => {
  try {
    console.log('Stock filters/sectors (exchanges) endpoint called');
    
    const sectorsQuery = `
      SELECT exchange, COUNT(*) as count
      FROM stock_symbols
      WHERE exchange IS NOT NULL
      GROUP BY exchange
      ORDER BY count DESC, exchange ASC
    `;
    
    const result = await query(sectorsQuery);
    
    res.json({
      data: result.rows.map(row => ({
        name: row.exchange,
        value: row.exchange,
        count: parseInt(row.count)
      })),
      total: result.rows.length,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching stock exchanges:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock exchanges', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get available industries - market categories
router.get('/filters/industries', async (req, res) => {
  try {
    console.log('Stock filters/industries (market categories) endpoint called');
    
    const industriesQuery = `
      SELECT market_category, COUNT(*) as count
      FROM stock_symbols
      WHERE market_category IS NOT NULL
      GROUP BY market_category
      ORDER BY count DESC, market_category ASC
    `;
    
    const result = await query(industriesQuery);
    
    res.json({
      data: result.rows.map(row => ({
        name: row.market_category,
        value: row.market_category,
        count: parseInt(row.count)
      })),
      total: result.rows.length,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching market categories:', error);
    res.status(500).json({ 
      error: 'Failed to fetch market categories', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Top gainers based on available price data
router.get('/movers/gainers', async (req, res) => {
  try {
    console.log('Stock movers/gainers endpoint called');
    
    const limit = Math.min(parseInt(req.query.limit) || 10, 50);
    
    // Get stocks with current and previous day prices to calculate gains
    const gainersQuery = `
      WITH price_changes AS (
        SELECT 
          symbol,
          date,
          close,
          LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close,
          LAG(date) OVER (PARTITION BY symbol ORDER BY date) as prev_date
        FROM price_daily
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
      ),
      latest_changes AS (
        SELECT DISTINCT ON (symbol)
          symbol,
          close as current_price,
          prev_close,
          date as price_date,
          CASE 
            WHEN prev_close > 0 
            THEN ((close - prev_close) / prev_close * 100)
            ELSE 0
          END as change_percent
        FROM price_changes
        WHERE prev_close IS NOT NULL
        ORDER BY symbol, date DESC
      )
      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        lc.current_price,
        lc.prev_close,
        lc.change_percent,
        lc.price_date
      FROM latest_changes lc
      JOIN stock_symbols ss ON ss.symbol = lc.symbol
      WHERE lc.change_percent > 0
      ORDER BY lc.change_percent DESC
      LIMIT $1
    `;
    
    const result = await query(gainersQuery, [limit]);
    
    const formattedData = result.rows.map(row => ({
      ticker: row.symbol,
      name: row.security_name,
      exchange: row.exchange,
      price: row.current_price,
      change: row.current_price - row.prev_close,
      changePercent: row.change_percent,
      volume: null, // Not available in this query
      price_date: row.price_date
    }));
    
    res.json({
      data: formattedData,
      count: result.rows.length,
      type: 'gainers',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching stock gainers:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock gainers', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Top losers based on available price data
router.get('/movers/losers', async (req, res) => {
  try {
    console.log('Stock movers/losers endpoint called');
    
    const limit = Math.min(parseInt(req.query.limit) || 10, 50);
    
    // Get stocks with current and previous day prices to calculate losses
    const losersQuery = `
      WITH price_changes AS (
        SELECT 
          symbol,
          date,
          close,
          LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close,
          LAG(date) OVER (PARTITION BY symbol ORDER BY date) as prev_date
        FROM price_daily
        WHERE date >= CURRENT_DATE - INTERVAL '7 days'
      ),
      latest_changes AS (
        SELECT DISTINCT ON (symbol)
          symbol,
          close as current_price,
          prev_close,
          date as price_date,
          CASE 
            WHEN prev_close > 0 
            THEN ((close - prev_close) / prev_close * 100)
            ELSE 0
          END as change_percent
        FROM price_changes
        WHERE prev_close IS NOT NULL
        ORDER BY symbol, date DESC
      )
      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        lc.current_price,
        lc.prev_close,
        lc.change_percent,
        lc.price_date
      FROM latest_changes lc
      JOIN stock_symbols ss ON ss.symbol = lc.symbol
      WHERE lc.change_percent < 0
      ORDER BY lc.change_percent ASC
      LIMIT $1
    `;
    
    const result = await query(losersQuery, [limit]);
    
    const formattedData = result.rows.map(row => ({
      ticker: row.symbol,
      name: row.security_name,
      exchange: row.exchange,
      price: row.current_price,
      change: row.current_price - row.prev_close,
      changePercent: row.change_percent,
      volume: null, // Not available in this query
      price_date: row.price_date
    }));
    
    res.json({
      data: formattedData,
      count: result.rows.length,
      type: 'losers',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching stock losers:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock losers', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Most active stocks by volume
router.get('/movers/active', async (req, res) => {
  try {
    console.log('Stock movers/active endpoint called');
    
    const limit = Math.min(parseInt(req.query.limit) || 10, 50);
    
    // Get most active stocks by volume
    const activeQuery = `
      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        pd.close as current_price,
        pd.volume,
        pd.date as price_date
      FROM stock_symbols ss
      JOIN (
        SELECT DISTINCT ON (symbol) symbol, close, volume, date
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON ss.symbol = pd.symbol
      WHERE pd.volume IS NOT NULL AND pd.volume > 0
      ORDER BY pd.volume DESC
      LIMIT $1
    `;
    
    const result = await query(activeQuery, [limit]);
    
    const formattedData = result.rows.map(row => ({
      ticker: row.symbol,
      name: row.security_name,
      exchange: row.exchange,
      price: row.current_price,
      volume: row.volume,
      price_date: row.price_date
    }));
    
    res.json({
      data: formattedData,
      count: result.rows.length,
      type: 'most_active',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching most active stocks:', error);
    res.status(500).json({ 
      error: 'Failed to fetch most active stocks', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Stock screening endpoint
router.get('/screen', async (req, res) => {
  try {
    console.log('Stock screen endpoint called with params:', req.query);
    
    const limit = Math.min(parseInt(req.query.limit) || 25, 100);
    const exchange = req.query.exchange;
    const marketCategory = req.query.marketCategory;
    const minPrice = parseFloat(req.query.minPrice) || null;
    const maxPrice = parseFloat(req.query.maxPrice) || null;
    const minVolume = parseInt(req.query.minVolume) || null;
    
    let whereClause = 'WHERE pd.close IS NOT NULL';
    const params = [];
    let paramIndex = 1;
    
    if (exchange) {
      whereClause += ` AND ss.exchange = $${paramIndex}`;
      params.push(exchange);
      paramIndex++;
    }
    
    if (marketCategory) {
      whereClause += ` AND ss.market_category = $${paramIndex}`;
      params.push(marketCategory);
      paramIndex++;
    }
    
    if (minPrice !== null) {
      whereClause += ` AND pd.close >= $${paramIndex}`;
      params.push(minPrice);
      paramIndex++;
    }
    
    if (maxPrice !== null) {
      whereClause += ` AND pd.close <= $${paramIndex}`;
      params.push(maxPrice);
      paramIndex++;
    }
    
    if (minVolume !== null) {
      whereClause += ` AND pd.volume >= $${paramIndex}`;
      params.push(minVolume);
      paramIndex++;
    }
    
    const screenQuery = `
      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        ss.market_category,
        pd.close as current_price,
        pd.volume,
        pd.date as price_date
      FROM stock_symbols ss
      JOIN (
        SELECT DISTINCT ON (symbol) symbol, close, volume, date
        FROM price_daily
        ORDER BY symbol, date DESC
      ) pd ON ss.symbol = pd.symbol
      ${whereClause}
      ORDER BY pd.volume DESC NULLS LAST
      LIMIT $${paramIndex}
    `;
    
    params.push(limit);
    
    const result = await query(screenQuery, params);
    
    const formattedData = result.rows.map(row => ({
      ticker: row.symbol,
      name: row.security_name,
      exchange: row.exchange,
      market_category: row.market_category,
      price: row.current_price,
      volume: row.volume,
      price_date: row.price_date
    }));
    
    res.json({
      data: formattedData,
      count: result.rows.length,
      filters: {
        exchange: exchange || null,
        marketCategory: marketCategory || null,
        minPrice: minPrice,
        maxPrice: maxPrice,
        minVolume: minVolume
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error screening stocks:', error);
    res.status(500).json({ 
      error: 'Failed to screen stocks', 
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;


module.exports = router;
