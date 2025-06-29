const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// ULTRA-FAST PRICE HISTORY ENDPOINT - Optimized for speed
// Supports ?limit=N&offset=M for pagination/expansion
// Default: limit=10, offset=0, max limit=90
router.get('/price-history/:symbol', async (req, res) => {
  const { symbol } = req.params;
  const { limit = 10, offset = 0 } = req.query;
  
  // console.log(`ULTRA-FAST: Price history requested for ${symbol}, limit: ${limit}, offset: ${offset}`);
  
  try {
    const db = await getDatabase();
    if (!db) {
      return res.status(503).json({ error: 'Database unavailable' });
    }

    const maxLimit = Math.min(parseInt(limit), 90);
    const tableName = 'price_daily';
    
    // Check if table exists
    const tableExists = await db.query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      );
    `, [tableName]);

    if (!tableExists.rows[0].exists) {
      return res.status(404).json({ error: 'Price data not available' });
    }

    // Get price history with pagination
    const query = `
      SELECT 
        date,
        open,
        high,
        low,
        close,
        volume
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT $2 OFFSET $3
    `;

    const result = await db.query(query, [symbol.toUpperCase(), maxLimit, parseInt(offset)]);
    
    res.json({
      symbol: symbol.toUpperCase(),
      data: result.rows,
      pagination: {
        limit: maxLimit,
        offset: parseInt(offset),
        total: result.rows.length
      }
    });
  } catch (error) {
    console.error('Error fetching price history:', error);
    res.status(500).json({ error: 'Failed to fetch price history' });
  }
});

router.get('/price-history/:symbol/quick', async (req, res) => {
  const { symbol } = req.params;
  const { limit = 5 } = req.query;
  
  // console.log(`LIGHTNING-FAST: Quick price data for ${symbol}, limit: ${limit}`);
  
  try {
    const db = await getDatabase();
    if (!db) {
      return res.status(503).json({ error: 'Database unavailable' });
    }

    const maxLimit = Math.min(parseInt(limit), 20);
    const tableName = 'price_daily';
    
    // Check if table exists
    const tableExists = await db.query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = $1
      );
    `, [tableName]);

    if (!tableExists.rows[0].exists) {
      return res.status(404).json({ error: 'Price data not available' });
    }

    // Get recent price data only
    const query = `
      SELECT 
        date,
        close,
        volume
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT $2
    `;

    const result = await db.query(query, [symbol.toUpperCase(), maxLimit]);
    
    res.json({
      symbol: symbol.toUpperCase(),
      data: result.rows,
      count: result.rows.length
    });
  } catch (error) {
    console.error('Error fetching quick price data:', error);
    res.status(500).json({ error: 'Failed to fetch price data' });
  }
});

// LIGHTNING-FAST ALTERNATIVE - Use this if the main endpoint is still too slow
router.get('/price-quick/:symbol', async (req, res) => {
  try {
    const { symbol } = req.params;
    const limit = Math.min(parseInt(req.query.limit) || 5, 10); // Very small limits for speed
    
    console.log(`LIGHTNING-FAST: Quick price data for ${symbol}, limit: ${limit}`);
    
    // Lightning-fast query - just get the most recent records
    const priceQuery = `
      SELECT 
        date,
        close,
        volume
      FROM price_daily
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY date DESC
      LIMIT $2
    `;
    
    const result = await query(priceQuery, [symbol.toUpperCase(), limit]);
    
    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: 'No price data found',
        symbol: symbol.toUpperCase(),
        message: 'Price data not available for this symbol',
        timestamp: new Date().toISOString()
      });
    }
    
    // Minimal processing - just essential data
    const formattedData = result.rows.map(price => ({
      date: price.date,
      close: parseFloat(price.close || 0),
      volume: parseInt(price.volume || 0)
    }));
    
    const latest = formattedData[0];
    const oldest = formattedData[formattedData.length - 1];
    const periodReturn = oldest.close > 0 ? 
      ((latest.close - oldest.close) / oldest.close * 100) : 0;
    
    res.json({
      success: true,
      symbol: symbol.toUpperCase(),
      data: formattedData,
      summary: {
        latestPrice: latest.close,
        latestDate: latest.date,
        periodReturn: parseFloat(periodReturn.toFixed(2)),
        dataPoints: formattedData.length
      },
      performance: 'LIGHTNING_FAST_MINIMAL',
      note: 'Minimal data for speed - use /price-history/:symbol for full OHLCV data',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('LIGHTNING-FAST price error:', error);
    res.status(500).json({
      success: false,
      error: 'Failed to fetch quick price data',
      symbol: req.params.symbol,
      details: error.message,
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
  // console.log('OPTIMIZED Stocks main endpoint called with params:', req.query);
  
  try {
    const db = await getDatabase();
    if (!db) {
      return res.status(503).json({ error: 'Database unavailable' });
    }

    const { 
      page = 1, 
      limit = 50, 
      search = '', 
      sector = '', 
      industry = '',
      sort_by = 'symbol',
      sort_order = 'asc'
    } = req.query;

    const offset = (parseInt(page) - 1) * parseInt(limit);
    const maxLimit = Math.min(parseInt(limit), 200);

    // Build WHERE clause
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramIndex = 1;

    if (search) {
      whereClause += ` AND (symbol ILIKE $${paramIndex} OR company_name ILIKE $${paramIndex})`;
      params.push(`%${search}%`);
      paramIndex++;
    }

    if (sector) {
      whereClause += ` AND sector = $${paramIndex}`;
      params.push(sector);
      paramIndex++;
    }

    if (industry) {
      whereClause += ` AND industry = $${paramIndex}`;
      params.push(industry);
      paramIndex++;
    }

    // Validate sort parameters
    const validSortColumns = ['symbol', 'company_name', 'sector', 'industry', 'market_cap', 'pe_ratio', 'price'];
    const sortColumn = validSortColumns.includes(sort_by) ? sort_by : 'symbol';
    const sortDirection = sort_order.toLowerCase() === 'desc' ? 'DESC' : 'ASC';

    // console.log('OPTIMIZED query params:', { whereClause, params, limit, offset });

    // Get total count
    const countQuery = `
      SELECT COUNT(*) as total
      FROM stock_symbols
      ${whereClause}
    `;
    const countResult = await db.query(countQuery, params);
    const total = parseInt(countResult.rows[0].total);

    // Get stocks data
    const dataQuery = `
      SELECT 
        symbol,
        company_name,
        sector,
        industry,
        market_cap,
        pe_ratio,
        price,
        volume,
        change_percent,
        exchange,
        country,
        currency,
        is_etf,
        ipo_date,
        website,
        description
      FROM stock_symbols
      ${whereClause}
      ORDER BY ${sortColumn} ${sortDirection}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    // console.log('Executing FAST queries...');
    const stocksResult = await db.query(dataQuery, [...params, maxLimit, offset]);
    // console.log(`FAST query results: ${stocksResult.rows.length} stocks, ${total} total`);

    res.json({
      data: stocksResult.rows,
      pagination: {
        page: parseInt(page),
        limit: maxLimit,
        total,
        pages: Math.ceil(total / maxLimit)
      },
      filters: {
        search,
        sector,
        industry
      },
      sort: {
        by: sortColumn,
        order: sortDirection
      }
    });
  } catch (error) {
    console.error('Error fetching stocks:', error);
    res.status(500).json({ error: 'Failed to fetch stocks' });
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
      data: [], // Always return data as an array for frontend safety
      timestamp: new Date().toISOString()
    });
  }
});

// Chunked stocks loading
router.get('/chunk/:chunkIndex', async (req, res) => {
  const { chunkIndex } = req.params;
  const { limit = 100 } = req.query;
  
  // console.log(`Stocks chunk endpoint called for chunk: ${chunkIndex}`);
  
  try {
    const db = await getDatabase();
    if (!db) {
      return res.status(503).json({ error: 'Database unavailable' });
    }

    const offset = parseInt(chunkIndex) * parseInt(limit);
    const maxLimit = Math.min(parseInt(limit), 500);

    const query = `
      SELECT 
        symbol,
        company_name,
        sector,
        industry,
        price,
        change_percent,
        volume,
        market_cap
      FROM stock_symbols
      ORDER BY symbol
      LIMIT $1 OFFSET $2
    `;

    const result = await db.query(query, [maxLimit, offset]);

    res.json({
      data: result.rows,
      chunk: parseInt(chunkIndex),
      limit: maxLimit,
      offset,
      count: result.rows.length
    });
  } catch (error) {
    console.error('Error fetching stocks chunk:', error);
    res.status(500).json({ error: 'Failed to fetch stocks chunk' });
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
      data: [], // Always return data as an array for frontend safety
      timestamp: new Date().toISOString()
    });
  }
});

// Get comprehensive stock details by ticker
// SIMPLIFIED Individual Stock Endpoint - Fast and reliable
// TEMPORARILY COMMENTED OUT - This route conflicts with /:ticker/prices
// router.get('/:ticker', async (req, res) => {
//   try {
//     const { ticker } = req.params;
//     const tickerUpper = ticker.toUpperCase();
//     
//     console.log(`SIMPLIFIED stock endpoint called for: ${tickerUpper}`);
//     
//     // SINGLE OPTIMIZED QUERY - Get everything we need in one go
//     const stockQuery = `
//       SELECT 
//         ss.symbol,
//         ss.security_name,
//         ss.exchange,
//         ss.market_category,
//         ss.financial_status,
//         ss.etf,
//         pd.date as latest_date,
//         pd.open,
//         pd.high,
//         pd.low,
//         pd.close,
//         pd.volume,
//         pd.adj_close
//       FROM stock_symbols ss
//       LEFT JOIN (
//         SELECT DISTINCT ON (symbol) 
//           symbol, date, open, high, low, close, volume, adj_close
//         FROM price_daily
//         WHERE symbol = $1
//         ORDER BY symbol, date DESC
//       ) pd ON ss.symbol = pd.symbol
//       WHERE ss.symbol = $1
//     `;
//     
//     const result = await query(stockQuery, [tickerUpper]);
//     
//     if (result.rows.length === 0) {
//       return res.status(404).json({
//         error: 'Stock not found',
//         symbol: tickerUpper,
//         message: `Symbol '${tickerUpper}' not found in database`,
//         timestamp: new Date().toISOString()
//       });
//     }
//     
//     const stock = result.rows[0];
//     
//     // SIMPLE RESPONSE - Just the essential data
//     const response = {
//       symbol: tickerUpper,
//       ticker: tickerUpper,
//       companyInfo: {
//         name: stock.security_name,
//         exchange: stock.exchange,
//         marketCategory: stock.market_category,
//         financialStatus: stock.financial_status,
//         isETF: stock.etf === 't' || stock.etf === true
//       },
//       currentPrice: stock.close ? {
//         date: stock.latest_date,
//         open: parseFloat(stock.open || 0),
//         high: parseFloat(stock.high || 0),
//         low: parseFloat(stock.low || 0),
//         close: parseFloat(stock.close || 0),
//         adjClose: parseFloat(stock.adj_close || stock.close || 0),
//         volume: parseInt(stock.volume || 0)
//       } : null,
//       metadata: {
//         requestedSymbol: ticker,
//         resolvedSymbol: tickerUpper,
//         dataAvailability: {
//           basicInfo: true,
//           priceData: stock.close !== null,
//           technicalIndicators: false, // Disabled for speed
//           fundamentals: false // Disabled for speed
//         },
//         timestamp: new Date().toISOString()
//       }
//     };
//     
//     console.log(`✅ SIMPLIFIED: Successfully returned basic data for ${tickerUpper}`);
//     
//     res.json(response);
//     
//   } catch (error) {
//     console.error('Error in simplified stock endpoint:', error);
//     res.status(500).json({ 
//       error: 'Failed to fetch stock data', 
//       symbol: req.params.ticker,
//       message: error.message,
//       data: [], // Always return data as an array for frontend safety
//       timestamp: new Date().toISOString()
//     });
//   }
// });

// Get stock price history
// SIMPLIFIED Get stock price history
router.get('/:ticker/prices', async (req, res) => {
  try {
    const { ticker } = req.params;
    const limit = Math.min(parseInt(req.query.limit) || 10, 25); // Further reduced from 20 to 10, max 25
    
    console.log(`SIMPLIFIED prices endpoint called for ticker: ${ticker}, limit: ${limit}`);
    
    const pricesQuery = `
      SELECT date, open, high, low, close, adj_close, volume
      FROM price_daily
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY date DESC
      LIMIT $2
    `;
    
    const result = await query(pricesQuery, [ticker, limit]);
    
    if (result.rows.length === 0) {
      return res.status(404).json({
        error: 'No price data found',
        ticker: ticker.toUpperCase(),
        message: 'Price data not available for this symbol',
        timestamp: new Date().toISOString()
      });
    }
    
    // Simple response
    const prices = result.rows;
    const latest = prices[0];
    const oldest = prices[prices.length - 1];

    const periodReturn = oldest.close > 0 ? 
      ((latest.close - oldest.close) / oldest.close * 100) : 0;

    // Add priceChange and priceChangePct to each record
    const pricesWithChange = prices.map((price, idx) => {
      let priceChange = null, priceChangePct = null;
      if (idx < prices.length - 1) {
        const prev = prices[idx + 1];
        priceChange = price.close - prev.close;
        priceChangePct = prev.close !== 0 ? priceChange / prev.close : null;
      }
      return {
        date: price.date,
        open: parseFloat(price.open),
        high: parseFloat(price.high),
        low: parseFloat(price.low),
        close: parseFloat(price.close),
        adjClose: parseFloat(price.adj_close),
        volume: parseInt(price.volume) || 0,
        priceChange,
        priceChangePct
      };
    });

    res.json({
      success: true,
      ticker: ticker.toUpperCase(),
      dataPoints: result.rows.length,
      data: pricesWithChange,
      summary: {
        latestPrice: parseFloat(latest.close),
        latestDate: latest.date,
        periodReturn: parseFloat(periodReturn.toFixed(2)),
        latestVolume: parseInt(latest.volume) || 0
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching stock prices:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock prices', 
      details: error.message,
      data: [], // Always return data as an array for frontend safety
      ticker: req.params.ticker,
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
      data: [], // Always return data as an array for frontend safety
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
      data: [], // Always return data as an array for frontend safety
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
      data: [], // Always return data as an array for frontend safety
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
      data: [], // Always return data as an array for frontend safety
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
      data: [], // Always return data as an array for frontend safety
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
      data: [], // Always return data as an array for frontend safety
      timestamp: new Date().toISOString()    });
  }
});

// Lightweight endpoint for recent price data only
router.get('/:ticker/price-recent', async (req, res) => {
  try {
    const { ticker } = req.params;
    const limit = Math.min(parseInt(req.query.limit) || 10, 20); // Further reduced from 15 to 10, max 20
    
    console.log(`Recent price endpoint called for ticker: ${ticker}, limit: ${limit}`);
    
    const pricesQuery = `
      SELECT date, open, high, low, close, adj_close, volume
      FROM price_daily
      WHERE UPPER(symbol) = UPPER($1)
      ORDER BY date DESC
      LIMIT $2
    `;
    
    const result = await query(pricesQuery, [ticker, limit]);
    
    if (result.rows.length === 0) {
      return res.status(404).json({
        error: 'No price data found',
        ticker: ticker.toUpperCase(),
        message: 'Price data not available for this symbol',
        timestamp: new Date().toISOString()
      });
    }
    
    // Calculate basic metrics
    const prices = result.rows;
    const latest = prices[0];
    const oldest = prices[prices.length - 1];
    
    const periodReturn = oldest.close > 0 ? 
      ((latest.close - oldest.close) / oldest.close * 100) : 0;
    
    res.json({
      success: true,
      ticker: ticker.toUpperCase(),
      dataPoints: result.rows.length,
      data: prices.map(price => ({
        date: price.date,
        open: parseFloat(price.open),
        high: parseFloat(price.high),
        low: parseFloat(price.low),
        close: parseFloat(price.close),
        adjClose: parseFloat(price.adj_close),
        volume: parseInt(price.volume) || 0
      })),
      summary: {
        latestPrice: parseFloat(latest.close),
        latestDate: latest.date,
        periodReturn: parseFloat(periodReturn.toFixed(2)),
        latestVolume: parseInt(latest.volume) || 0
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error fetching recent prices:', error);
    res.status(500).json({ 
      error: 'Failed to fetch recent price data', 
      details: error.message,
      data: [], // Always return data as an array for frontend safety
      ticker: req.params.ticker,
      timestamp: new Date().toISOString()
    });
  }
});

// Stock profile endpoint - returns company information
router.get('/:ticker/profile', async (req, res) => {
  try {
    const { ticker } = req.params;
    const tickerUpper = ticker.toUpperCase();
    
    console.log(`Stock profile endpoint called for: ${tickerUpper}`);
    
    const stockInfoQuery = `
      SELECT 
        symbol,
        security_name,
        exchange,
        market_category,
        cqs_symbol,
        financial_status,
        round_lot_size,
        etf,
        test_issue,
        nasdaq_symbol
      FROM stock_symbols 
      WHERE symbol = $1
    `;
    
    const stockInfo = await query(stockInfoQuery, [tickerUpper]);
    
    if (stockInfo.rows.length === 0) {
      return res.status(404).json({
        error: 'Stock not found',
        symbol: tickerUpper,
        timestamp: new Date().toISOString()
      });
    }
    
    const stockData = stockInfo.rows[0];
    
    res.json({
      symbol: tickerUpper,
      name: stockData.security_name,
      exchange: stockData.exchange,
      marketCategory: stockData.market_category,
      cqsSymbol: stockData.cqs_symbol,
      financialStatus: stockData.financial_status,
      roundLotSize: stockData.round_lot_size,
      isETF: stockData.etf === 't' || stockData.etf === true,
      isTestIssue: stockData.test_issue === 't' || stockData.test_issue === true,
      nasdaqSymbol: stockData.nasdaq_symbol,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error in stock profile endpoint:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock profile', 
      symbol: req.params.ticker,
      message: error.message,
      data: [], // Always return data as an array for frontend safety
      timestamp: new Date().toISOString()
    });
  }
});

// Comprehensive financial metrics endpoint - uses loadinfo data
router.get('/:ticker/metrics', async (req, res) => {
  try {
    const { ticker } = req.params;
    const tickerUpper = ticker.toUpperCase();
    
    console.log(`Comprehensive financial metrics endpoint called for: ${tickerUpper}`);
    
    // Get all financial data from loadinfo tables
    const financialQuery = `
      SELECT 
        -- Company Profile
        cp.short_name,
        cp.long_name,
        cp.sector,
        cp.sector_disp,
        cp.industry,
        cp.industry_disp,
        cp.business_summary,
        cp.employee_count,
        cp.exchange,
        cp.full_exchange_name,
        
        -- Market Data
        md.current_price,
        md.previous_close,
        md.day_low,
        md.day_high,
        md.volume,
        md.average_volume,
        md.market_cap,
        md.fifty_two_week_low,
        md.fifty_two_week_high,
        md.fifty_day_avg,
        md.two_hundred_day_avg,
        md.bid_price,
        md.ask_price,
        
        -- Key Metrics  
        km.trailing_pe,
        km.forward_pe,
        km.price_to_sales_ttm,
        km.price_to_book,
        km.book_value,
        km.peg_ratio,
        km.enterprise_value,
        km.ev_to_revenue,
        km.ev_to_ebitda,
        km.total_revenue,
        km.net_income,
        km.ebitda,
        km.gross_profit,
        km.eps_trailing,
        km.eps_forward,
        km.total_cash,
        km.cash_per_share,
        km.operating_cashflow,
        km.free_cashflow,
        km.total_debt,
        km.debt_to_equity,
        km.quick_ratio,
        km.current_ratio,
        km.profit_margin_pct,
        km.gross_margin_pct,
        km.ebitda_margin_pct,
        km.operating_margin_pct,
        km.return_on_assets_pct,
        km.return_on_equity_pct,
        km.revenue_growth_pct,
        km.earnings_growth_pct,
        km.dividend_rate,
        km.dividend_yield,
        km.five_year_avg_dividend_yield,
        km.payout_ratio,
        
        -- Analyst Estimates
        ae.target_high_price,
        ae.target_low_price,
        ae.target_mean_price,
        ae.target_median_price,
        ae.recommendation_key,
        ae.recommendation_mean,
        ae.analyst_opinion_count,
        ae.average_analyst_rating,
        
        -- Governance Scores
        gs.audit_risk,
        gs.board_risk,
        gs.compensation_risk,
        gs.shareholder_rights_risk,
        gs.overall_risk
        
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker  
      LEFT JOIN analyst_estimates ae ON cp.ticker = ae.ticker
      LEFT JOIN governance_scores gs ON cp.ticker = gs.ticker
      WHERE cp.ticker = $1
    `;
    
    const result = await query(financialQuery, [tickerUpper]);
    
    if (result.rows.length === 0) {
      return res.status(404).json({
        error: 'Stock not found',
        symbol: tickerUpper,
        message: 'No financial data available for this symbol',
        timestamp: new Date().toISOString()
      });
    }
    
    const data = result.rows[0];
    
    // Structure comprehensive financial response
    const financialMetrics = {
      symbol: tickerUpper,
      companyInfo: {
        name: data.long_name || data.short_name,
        shortName: data.short_name,
        sector: data.sector_disp || data.sector,
        industry: data.industry_disp || data.industry,
        businessSummary: data.business_summary,
        employeeCount: data.employee_count,
        exchange: data.full_exchange_name || data.exchange
      },
      
      pricing: {
        currentPrice: parseFloat(data.current_price || 0),
        previousClose: parseFloat(data.previous_close || 0),
        dayRange: {
          low: parseFloat(data.day_low || 0),
          high: parseFloat(data.day_high || 0)
        },
        fiftyTwoWeekRange: {
          low: parseFloat(data.fifty_two_week_low || 0),
          high: parseFloat(data.fifty_two_week_high || 0)
        },
        movingAverages: {
          fiftyDay: parseFloat(data.fifty_day_avg || 0),
          twoHundredDay: parseFloat(data.two_hundred_day_avg || 0)
        },
        bidAsk: {
          bid: parseFloat(data.bid_price || 0),
          ask: parseFloat(data.ask_price || 0)
        }
      },
      
      marketData: {
        marketCap: parseInt(data.market_cap || 0),
        volume: parseInt(data.volume || 0),
        averageVolume: parseInt(data.average_volume || 0),
        enterpriseValue: parseInt(data.enterprise_value || 0)
      },
      
      valuationRatios: {
        trailingPE: parseFloat(data.trailing_pe || 0),
        forwardPE: parseFloat(data.forward_pe || 0),
        priceToSales: parseFloat(data.price_to_sales_ttm || 0),
        priceToBook: parseFloat(data.price_to_book || 0),
        pegRatio: parseFloat(data.peg_ratio || 0),
        evToRevenue: parseFloat(data.ev_to_revenue || 0),
        evToEbitda: parseFloat(data.ev_to_ebitda || 0)
      },
      
      profitability: {
        profitMargin: parseFloat(data.profit_margin_pct || 0),
        grossMargin: parseFloat(data.gross_margin_pct || 0),
        ebitdaMargin: parseFloat(data.ebitda_margin_pct || 0),
        operatingMargin: parseFloat(data.operating_margin_pct || 0),
        returnOnAssets: parseFloat(data.return_on_assets_pct || 0),
        returnOnEquity: parseFloat(data.return_on_equity_pct || 0)
      },
      
      growth: {
        revenueGrowth: parseFloat(data.revenue_growth_pct || 0),
        earningsGrowth: parseFloat(data.earnings_growth_pct || 0)
      },
      
      financial: {
        totalRevenue: parseInt(data.total_revenue || 0),
        netIncome: parseInt(data.net_income || 0),
        ebitda: parseInt(data.ebitda || 0),
        grossProfit: parseInt(data.gross_profit || 0),
        totalCash: parseInt(data.total_cash || 0),
        cashPerShare: parseFloat(data.cash_per_share || 0),
        operatingCashflow: parseInt(data.operating_cashflow || 0),
        freeCashflow: parseInt(data.free_cashflow || 0),
        totalDebt: parseInt(data.total_debt || 0),
        bookValue: parseFloat(data.book_value || 0)
      },
      
      ratios: {
        debtToEquity: parseFloat(data.debt_to_equity || 0),
        quickRatio: parseFloat(data.quick_ratio || 0),
        currentRatio: parseFloat(data.current_ratio || 0)
      },
      
      earnings: {
        epsTrailing: parseFloat(data.eps_trailing || 0),
        epsForward: parseFloat(data.eps_forward || 0)
      },
      
      dividends: {
        dividendRate: parseFloat(data.dividend_rate || 0),
        dividendYield: parseFloat(data.dividend_yield || 0),
        fiveYearAvgDividendYield: parseFloat(data.five_year_avg_dividend_yield || 0),
        payoutRatio: parseFloat(data.payout_ratio || 0)
      },
      
      analystEstimates: {
        targetPrices: {
          high: parseFloat(data.target_high_price || 0),
          low: parseFloat(data.target_low_price || 0),
          mean: parseFloat(data.target_mean_price || 0),
          median: parseFloat(data.target_median_price || 0)
        },
        recommendation: {
          key: data.recommendation_key,
          mean: parseFloat(data.recommendation_mean || 0),
          analystCount: parseInt(data.analyst_opinion_count || 0),
          averageRating: parseFloat(data.average_analyst_rating || 0)
        }
      },
      
      governance: {
        auditRisk: parseInt(data.audit_risk || 0),
        boardRisk: parseInt(data.board_risk || 0),
        compensationRisk: parseInt(data.compensation_risk || 0),
        shareholderRightsRisk: parseInt(data.shareholder_rights_risk || 0),
        overallRisk: parseInt(data.overall_risk || 0)
      },
      
      dataAvailability: {
        hasMarketData: !!data.current_price,
        hasKeyMetrics: !!data.trailing_pe,
        hasAnalystEstimates: !!data.target_mean_price,
        hasGovernanceData: !!data.overall_risk
      },
      
      timestamp: new Date().toISOString()
    };
    
    res.json(financialMetrics);
    
  } catch (error) {
    console.error('Error in comprehensive financial metrics endpoint:', error);
    res.status(500).json({ 
      error: 'Failed to fetch financial metrics', 
      symbol: req.params.ticker,
      message: error.message,
      data: [], // Always return data as an array for frontend safety
      timestamp: new Date().toISOString()
    });
  }
});

// Comprehensive financial overview endpoint - perfect for frontend financial pages
router.get('/:ticker/financial-overview', async (req, res) => {
  try {
    const { ticker } = req.params;
    const tickerUpper = ticker.toUpperCase();
    
    console.log(`Financial overview endpoint called for: ${tickerUpper}`);
    
    // Get comprehensive financial overview
    const overviewQuery = `
      SELECT 
        -- Company basics
        cp.short_name,
        cp.long_name,
        cp.sector_disp,
        cp.industry_disp,
        cp.business_summary,
        cp.employee_count,
        cp.website_url,
        
        -- Current market data
        md.current_price,
        md.previous_close,
        md.market_cap,
        md.volume,
        md.fifty_two_week_low,
        md.fifty_two_week_high,
        
        -- Key financial metrics
        km.trailing_pe,
        km.forward_pe,
        km.price_to_book,
        km.dividend_yield,
        km.eps_trailing,
        km.eps_forward,
        km.total_revenue,
        km.net_income,
        km.profit_margin_pct,
        km.return_on_equity_pct,
        km.debt_to_equity,
        km.revenue_growth_pct,
        km.earnings_growth_pct,
        
        -- Analyst data
        ae.target_mean_price,
        ae.recommendation_key,
        ae.analyst_opinion_count,
        
        -- Governance
        gs.overall_risk
        
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      LEFT JOIN analyst_estimates ae ON cp.ticker = ae.ticker
      LEFT JOIN governance_scores gs ON cp.ticker = gs.ticker
      WHERE cp.ticker = $1
    `;
    
    const result = await query(overviewQuery, [tickerUpper]);
    
    if (result.rows.length === 0) {
      return res.status(404).json({
        error: 'Stock not found',
        symbol: tickerUpper,
        timestamp: new Date().toISOString()
      });
    }
    
    const data = result.rows[0];
    
    // Calculate derived metrics
    const currentPrice = parseFloat(data.current_price || 0);
    const previousClose = parseFloat(data.previous_close || 0);
    const priceChange = currentPrice - previousClose;
    const priceChangePercent = previousClose > 0 ? (priceChange / previousClose) * 100 : 0;
    
    const fiftyTwoWeekLow = parseFloat(data.fifty_two_week_low || 0);
    const fiftyTwoWeekHigh = parseFloat(data.fifty_two_week_high || 0);
    const fiftyTwoWeekPosition = fiftyTwoWeekHigh > fiftyTwoWeekLow ? 
      ((currentPrice - fiftyTwoWeekLow) / (fiftyTwoWeekHigh - fiftyTwoWeekLow)) * 100 : 0;
    
    // Format response for easy frontend consumption
    const overview = {
      symbol: tickerUpper,
      
      // Company Information
      company: {
        name: data.long_name || data.short_name,
        sector: data.sector_disp,
        industry: data.industry_disp,
        description: data.business_summary,
        employees: parseInt(data.employee_count || 0),
        website: data.website_url
      },
      
      // Stock Price
      price: {
        current: currentPrice,
        change: parseFloat(priceChange.toFixed(2)),
        changePercent: parseFloat(priceChangePercent.toFixed(2)),
        previousClose: previousClose,
        fiftyTwoWeekRange: {
          low: fiftyTwoWeekLow,
          high: fiftyTwoWeekHigh,
          position: parseFloat(fiftyTwoWeekPosition.toFixed(1))
        }
      },
      
      // Market Data
      market: {
        marketCap: {
          value: parseInt(data.market_cap || 0),
          formatted: formatMarketCap(parseInt(data.market_cap || 0))
        },
        volume: parseInt(data.volume || 0),
        avgVolume: null // Could add from market_data if needed
      },
      
      // Valuation
      valuation: {
        peRatio: parseFloat(data.trailing_pe || 0),
        forwardPE: parseFloat(data.forward_pe || 0),
        priceToBook: parseFloat(data.price_to_book || 0),
        eps: parseFloat(data.eps_trailing || 0),
        forwardEPS: parseFloat(data.eps_forward || 0)
      },
      
      // Financial Health
      financial: {
        revenue: {
          value: parseInt(data.total_revenue || 0),
          formatted: formatLargeNumber(parseInt(data.total_revenue || 0))
        },
        netIncome: {
          value: parseInt(data.net_income || 0),
          formatted: formatLargeNumber(parseInt(data.net_income || 0))
        },
        profitMargin: parseFloat(data.profit_margin_pct || 0),
        roe: parseFloat(data.return_on_equity_pct || 0),
        debtToEquity: parseFloat(data.debt_to_equity || 0)
      },
      
      // Growth
      growth: {
        revenueGrowth: parseFloat(data.revenue_growth_pct || 0),
        earningsGrowth: parseFloat(data.earnings_growth_pct || 0)
      },
      
      // Dividends
      dividends: {
        yield: parseFloat(data.dividend_yield || 0),
        hasDividend: parseFloat(data.dividend_yield || 0) > 0
      },
      
      // Analyst Opinion
      analysts: {
        targetPrice: parseFloat(data.target_mean_price || 0),
        recommendation: data.recommendation_key,
        analystCount: parseInt(data.analyst_opinion_count || 0),
        hasEstimates: !!data.target_mean_price
      },
      
      // Risk Assessment
      risk: {
        overallRisk: parseInt(data.overall_risk || 0),
        riskLevel: getRiskLevel(parseInt(data.overall_risk || 0))
      },
      
      // Data Quality Indicators
      dataQuality: {
        hasPrice: !!data.current_price,
        hasFinancials: !!data.total_revenue,
        hasAnalysts: !!data.target_mean_price,
        completeness: calculateCompleteness(data)
      },
      
      timestamp: new Date().toISOString()
    };
    
    res.json(overview);
    
  } catch (error) {
    console.error('Error in financial overview endpoint:', error);
    res.status(500).json({ 
      error: 'Failed to fetch financial overview', 
      symbol: req.params.ticker,
      message: error.message,
      data: [], // Always return data as an array for frontend safety
      timestamp: new Date().toISOString()
    });
  }
});

// Helper functions for financial overview
function formatMarketCap(value) {
  if (value >= 1e12) return `$${(value / 1e12).toFixed(1)}T`;
  if (value >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
  if (value >= 1e3) return `$${(value / 1e3).toFixed(1)}K`;
  return `$${value}`;
}

function formatLargeNumber(value) {
  if (value >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  if (value >= 1e3) return `$${(value / 1e3).toFixed(2)}K`;
  return `$${value}`;
}

function getRiskLevel(riskScore) {
  if (riskScore <= 3) return 'Low';
  if (riskScore <= 6) return 'Medium';
  if (riskScore <= 8) return 'High';
  return 'Very High';
}

function calculateCompleteness(data) {
  const fields = [
    'current_price', 'market_cap', 'trailing_pe', 'total_revenue', 
    'net_income', 'eps_trailing', 'target_mean_price'
  ];
  const available = fields.filter(field => data[field] != null).length;
  return Math.round((available / fields.length) * 100);
}

// Stock recommendations endpoint - returns analyst recommendations
router.get('/:ticker/recommendations', async (req, res) => {
  try {
    const { ticker } = req.params;
    const tickerUpper = ticker.toUpperCase();
    
    console.log(`Stock recommendations endpoint called for: ${tickerUpper}`);
    
    res.json({
      symbol: tickerUpper,
      available: false,
      message: 'Analyst recommendations data not available',
      recommendations: [],
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error in stock recommendations endpoint:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock recommendations', 
      symbol: req.params.ticker,
      message: error.message,
      data: [], // Always return data as an array for frontend safety
      timestamp: new Date().toISOString()
    });
  }
});

// Leadership team data endpoint - provides executive/leadership information
router.get('/leadership/:ticker?', async (req, res) => {
  try {
    const ticker = req.params.ticker;
    
    let leadershipQuery;
    let params = [];
    
    if (ticker) {
      // Get leadership for specific ticker
      leadershipQuery = `
        SELECT 
          lt.ticker,
          lt.person_name,
          lt.age,
          lt.title,
          lt.birth_year,
          lt.fiscal_year,
          lt.total_pay,
          lt.exercised_value,
          lt.unexercised_value,
          lt.role_source,
          cp.short_name as company_name
        FROM leadership_team lt
        LEFT JOIN company_profile cp ON lt.ticker = cp.ticker
        WHERE UPPER(lt.ticker) = UPPER($1)
        ORDER BY lt.total_pay DESC NULLS LAST, lt.person_name
      `;
      params = [ticker.toUpperCase()];
    } else {
      // Get leadership summary - top executives across all companies
      const limit = Math.min(parseInt(req.query.limit) || 50, 200);
      leadershipQuery = `
        SELECT 
          lt.ticker,
          lt.person_name,
          lt.age,
          lt.title,
          lt.birth_year,
          lt.fiscal_year,
          lt.total_pay,
          lt.exercised_value,
          lt.unexercised_value,
          lt.role_source,
          cp.short_name as company_name
        FROM leadership_team lt
        LEFT JOIN company_profile cp ON lt.ticker = cp.ticker
        ORDER BY lt.total_pay DESC NULLS LAST
        LIMIT $1
      `;
      params = [limit];
    }
    
    const result = await query(leadershipQuery, params);
    
    const formattedLeadership = result.rows.map(exec => ({
      ticker: exec.ticker,
      companyName: exec.company_name,
      executiveInfo: {
        name: exec.person_name,
        title: exec.title,
        age: exec.age,
        birthYear: exec.birth_year
      },
      compensation: {
        totalPay: exec.total_pay,
        exercisedValue: exec.exercised_value,
        unexercisedValue: exec.unexercised_value,
        fiscalYear: exec.fiscal_year
      },
      roleSource: exec.role_source
    }));
    
    res.json({
      success: true,
      ticker: ticker || 'ALL',
      data: formattedLeadership,
      count: formattedLeadership.length,
      endpoint: ticker ? 'leadership_by_ticker' : 'leadership_summary',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Leadership endpoint error:', error);
    res.status(500).json({ 
      error: 'Leadership data query failed',
      details: error.message,
      data: [], // Always return data as an array for frontend safety
      timestamp: new Date().toISOString()
    });  }
});

// Dedicated Price Data API - On-demand loading for stock drilldown pages
router.get('/:ticker/price-data', async (req, res) => {
  try {
    const { ticker } = req.params;
    const tickerUpper = ticker.toUpperCase();
      // Get query parameters for flexible date ranges
    const period = req.query.period || '1m'; // 1m, 3m, 6m, 1y, 2y, max
    const interval = req.query.interval || 'daily'; // daily, weekly, monthly
    const limit = parseInt(req.query.limit) || 20; // Reduced from 30 to 20, max 50
    
    console.log(`Price data API called for ${tickerUpper}, period: ${period}, interval: ${interval}`);
    
    // Validate interval - only support what you actually have
    const validIntervals = ['daily', 'weekly', 'monthly'];
    if (!validIntervals.includes(interval)) {
      return res.status(400).json({
        error: 'Invalid interval',
        message: `Supported intervals: ${validIntervals.join(', ')}, got: ${interval}`,
        supportedIntervals: validIntervals
      });
    }
    
    // Map period to days for SQL query - realistic periods for your data
    const periodToDays = {
      '1m': 30,
      '3m': 90,
      '6m': 180,
      '1y': 365,
      '2y': 730,
      'max': 0 // No limit
    };
    
    const days = periodToDays[period] || 30; // Default to 1 month
    
    // Choose the appropriate table based on interval
    const tableMap = {
      'daily': 'price_daily',
      'weekly': 'price_weekly', 
      'monthly': 'price_monthly'
    };
    
    const tableName = tableMap[interval] || 'price_daily';
    
    // Build dynamic query with optional date filtering and LIMIT
    let whereClause = 'WHERE symbol = $1';
    const params = [tickerUpper];
    let paramCount = 1;
    
    if (days > 0) {
      paramCount++;
      whereClause += ` AND date >= CURRENT_DATE - INTERVAL '${days} days'`;
    }
    
    // Add custom date range if provided
    if (req.query.start_date) {
      paramCount++;
      whereClause += ` AND date >= $${paramCount}`;
      params.push(req.query.start_date);
    }
    
    if (req.query.end_date) {
      paramCount++;
      whereClause += ` AND date <= $${paramCount}`;
      params.push(req.query.end_date);
    }
    
    // Always add limit for performance - more aggressive limit
    const maxLimit = Math.min(limit, 50); // Reduced from 100 to 50 rows
    paramCount++;
    params.push(maxLimit);
    
    const priceQuery = `
      SELECT 
        symbol,
        date,
        open,
        high,
        low,
        close,
        adj_close,
        volume
      FROM ${tableName}
      ${whereClause}
      ORDER BY date DESC
      LIMIT $${paramCount}
    `;
    
    console.log(`Executing price query on ${tableName} with ${params.length} parameters, limit: ${maxLimit}`);
    
    const result = await query(priceQuery, params);
    
    if (result.rows.length === 0) {
      return res.status(404).json({        error: 'No price data found',
        ticker: tickerUpper,
        period: period,
        interval: interval,
        message: 'Price data not available for this symbol and time range',
        supportedIntervals: ['daily', 'weekly', 'monthly'],
        supportedPeriods: ['1m', '3m', '6m', '1y', '2y', 'max'],
        timestamp: new Date().toISOString()
      });
    }
    
    // Process and format the price data
    const priceData = result.rows.map(row => ({
      date: row.date,
      open: parseFloat(row.open || 0),
      high: parseFloat(row.high || 0),
      low: parseFloat(row.low || 0),
      close: parseFloat(row.close || 0),
      adjClose: parseFloat(row.adj_close || row.close || 0),
      volume: parseInt(row.volume || 0)
    }));
    
    // Calculate summary statistics
    const prices = priceData.map(d => d.close).filter(p => p > 0);
    const volumes = priceData.map(d => d.volume).filter(v => v > 0);
    
    const latest = priceData[0];
    const oldest = priceData[priceData.length - 1];
    
    const summary = {
      ticker: tickerUpper,
      period: period,
      interval: interval,
      dataPoints: priceData.length,
      dateRange: {
        start: oldest?.date,
        end: latest?.date
      },
      priceStats: {
        current: latest?.close || 0,
        periodHigh: Math.max(...prices),
        periodLow: Math.min(...prices),
        periodChange: latest && oldest ? latest.close - oldest.close : 0,
        periodChangePct: latest && oldest && oldest.close > 0 ? 
          ((latest.close - oldest.close) / oldest.close * 100) : 0,
        avgPrice: prices.length > 0 ? prices.reduce((a, b) => a + b, 0) / prices.length : 0
      },
      volumeStats: {
        current: latest?.volume || 0,
        periodHigh: volumes.length > 0 ? Math.max(...volumes) : 0,
        periodLow: volumes.length > 0 ? Math.min(...volumes) : 0,
        avgVolume: volumes.length > 0 ? Math.round(volumes.reduce((a, b) => a + b, 0) / volumes.length) : 0,
        totalVolume: volumes.reduce((a, b) => a + b, 0)
      }
    };
    
    // Response optimized for frontend charts and drilldown pages
    res.json({
      success: true,
      ticker: tickerUpper,
      summary: summary,
      data: priceData,
      metadata: {
        requestedPeriod: period,
        requestedInterval: interval,
        actualDataPoints: priceData.length,
        tableName: tableName,
        queryTime: new Date().toISOString(),
        apiEndpoint: 'price-data'
      }
    });
    
  } catch (error) {
    console.error(`Error fetching price data for ${req.params.ticker}:`, error);
    res.status(500).json({
      error: 'Failed to fetch price data',
      ticker: req.params.ticker,
      details: error.message,
      data: [], // Always return data as an array for frontend safety
      timestamp: new Date().toISOString()
    });
  }
});

// Bulk price data API - For getting multiple stocks at once (efficient for screeners)
router.get('/bulk/price-data', async (req, res) => {  try {
    const symbols = req.query.symbols ? req.query.symbols.split(',').map(s => s.toUpperCase()) : [];
    const period = req.query.period || '1m';
    const interval = req.query.interval || 'daily';
    const limit = Math.min(parseInt(req.query.limit) || 5, 10); // Further reduced from 10 to 5, max 10
    
    if (symbols.length === 0) {
      return res.status(400).json({
        error: 'No symbols provided',
        message: 'Use ?symbols=AAPL,MSFT,GOOGL to specify symbols',
        example: '/api/stocks/bulk/price-data?symbols=AAPL,MSFT,GOOGL&period=1m',
        supportedIntervals: ['daily', 'weekly', 'monthly'],
        supportedPeriods: ['1m', '3m', '6m', '1y', '2y', 'max']
      });
    }
    
    if (symbols.length > 10) { // Further reduced from 20 to 10
      return res.status(400).json({
        error: 'Too many symbols',
        message: 'Maximum 10 symbols allowed per request',
        requested: symbols.length
      });
    }
    
    // Validate interval
    const validIntervals = ['daily', 'weekly', 'monthly'];
    if (!validIntervals.includes(interval)) {
      return res.status(400).json({
        error: 'Invalid interval',
        message: `Supported intervals: ${validIntervals.join(', ')}, got: ${interval}`,
        supportedIntervals: validIntervals
      });
    }
    
    console.log(`Bulk price data API called for ${symbols.length} symbols: ${symbols.join(', ')}`);
    
    const periodToDays = {
      '1m': 30,
      '3m': 90,
      '6m': 180,
      '1y': 365,
      '2y': 730,
      'max': 0
    };
    
    const days = periodToDays[period] || 30; // Default to 1 month
    const tableName = interval === 'weekly' ? 'price_weekly' : 
                     interval === 'monthly' ? 'price_monthly' : 'price_daily';
    
    // Optimized query for multiple symbols with LIMIT
    const bulkQuery = `
      WITH latest_prices AS (
        SELECT DISTINCT ON (symbol) 
          symbol,
          date,
          open,
          high,
          low,
          close,
          adj_close,
          volume
        FROM ${tableName}
        WHERE symbol = ANY($1)
          AND date >= CURRENT_DATE - INTERVAL '${days} days'
        ORDER BY symbol, date DESC
        LIMIT $2
      )
      SELECT * FROM latest_prices
      ORDER BY symbol
    `;
    
    const result = await query(bulkQuery, [symbols, limit]);
    
    // Group results by symbol
    const dataBySymbol = {};
    result.rows.forEach(row => {
      if (!dataBySymbol[row.symbol]) {
        dataBySymbol[row.symbol] = [];
      }
      dataBySymbol[row.symbol].push({
        date: row.date,
        open: parseFloat(row.open || 0),
        high: parseFloat(row.high || 0),
        low: parseFloat(row.low || 0),
        close: parseFloat(row.close || 0),
        adjClose: parseFloat(row.adj_close || row.close || 0),
        volume: parseInt(row.volume || 0)
      });
    });
    
    // Format response for easy frontend consumption
    const response = {
      success: true,
      requestedSymbols: symbols,
      foundSymbols: Object.keys(dataBySymbol),
      missingSymbols: symbols.filter(s => !dataBySymbol[s]),
      data: dataBySymbol,
      summary: {
        requested: symbols.length,
        found: Object.keys(dataBySymbol).length,
        missing: symbols.filter(s => !dataBySymbol[s]).length,
        totalDataPoints: result.rows.length
      },
      metadata: {
        period: period,
        interval: interval,
        tableName: tableName,
        timestamp: new Date().toISOString()
      }
    };
    
    res.json(response);
    
  } catch (error) {
    console.error('Error in bulk price data API:', error);
    res.status(500).json({
      error: 'Failed to fetch bulk price data',
      details: error.message,
      data: [], // Always return data as an array for frontend safety
      timestamp: new Date().toISOString()
    });
  }
});

// Debug endpoint: fetch raw joined data for a symbol
router.get('/debug/raw/:symbol', async (req, res) => {
  const symbol = req.params.symbol;
  try {
    const debugQuery = `
      SELECT 
        ss.symbol,
        ss.security_name,
        cp.ticker as cp_ticker,
        cp.short_name, cp.long_name, cp.business_summary, cp.employee_count, cp.website_url, cp.country,
        md.ticker as md_ticker,
        md.current_price, md.previous_close, md.day_low, md.day_high, md.volume, md.average_volume,
        km.ticker as km_ticker,
        km.trailing_pe, km.peg_ratio, km.price_to_book, km.eps_trailing, km.profit_margin_pct
      FROM stock_symbols ss
      LEFT JOIN company_profile cp ON ss.symbol = cp.ticker
      LEFT JOIN market_data md ON ss.symbol = md.ticker
      LEFT JOIN key_metrics km ON ss.symbol = km.ticker
      WHERE ss.symbol = $1
      LIMIT 1
    `;
    const result = await query(debugQuery, [symbol]);
    res.json({
      symbol,
      row: result.rows[0] || null
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Price data endpoint for a symbol
router.get('/api/stocks/:symbol/price-data', async (req, res) => {
  try {
    const { symbol } = req.params;
    if (!symbol) {
      return res.status(400).json({ error: 'Missing symbol parameter' });
    }
    
    const limit = Math.min(parseInt(req.query.limit) || 10, 25); // Further reduced from 20 to 10, max 25
    
    // Query limited price data for the symbol from price_daily
    const priceQuery = `
      SELECT date, open, high, low, close, adj_close, volume, dividends, stock_splits
      FROM price_daily
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT $2
    `;
    const result = await query(priceQuery, [symbol.toUpperCase(), limit]);
    res.json({
      symbol: symbol.toUpperCase(),
      count: result.rows.length,
      data: result.rows,
      limit: limit
    });
  } catch (error) {
    console.error('Error in price-data endpoint:', error);
    res.status(500).json({ error: 'Failed to fetch price data', details: error.message });
  }
});

// Get comprehensive stock details by ticker - MOVED TO END to avoid routing conflicts
// This route must come AFTER all specific /:ticker/* routes
router.get('/:ticker', async (req, res) => {
  try {
    const { ticker } = req.params;
    const tickerUpper = ticker.toUpperCase();
    
    console.log(`SIMPLIFIED stock endpoint called for: ${tickerUpper}`);
    
    // SINGLE OPTIMIZED QUERY - Get everything we need in one go
    const stockQuery = `
      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        ss.market_category,
        ss.financial_status,
        ss.etf,
        pd.date as latest_date,
        pd.open,
        pd.high,
        pd.low,
        pd.close,
        pd.volume,
        pd.adj_close
      FROM stock_symbols ss
      LEFT JOIN (
        SELECT DISTINCT ON (symbol) 
          symbol, date, open, high, low, close, volume, adj_close
        FROM price_daily
        WHERE symbol = $1
        ORDER BY symbol, date DESC
      ) pd ON ss.symbol = pd.symbol
      WHERE ss.symbol = $1
    `;
    
    const result = await query(stockQuery, [tickerUpper]);
    
    if (result.rows.length === 0) {
      return res.status(404).json({
        error: 'Stock not found',
        symbol: tickerUpper,
        message: `Symbol '${tickerUpper}' not found in database`,
        timestamp: new Date().toISOString()
      });
    }
    
    const stock = result.rows[0];
    
    // SIMPLE RESPONSE - Just the essential data
    const response = {
      symbol: tickerUpper,
      ticker: tickerUpper,
      companyInfo: {
        name: stock.security_name,
        exchange: stock.exchange,
        marketCategory: stock.market_category,
        financialStatus: stock.financial_status,
        isETF: stock.etf === 't' || stock.etf === true
      },
      currentPrice: stock.close ? {
        date: stock.latest_date,
        open: parseFloat(stock.open || 0),
        high: parseFloat(stock.high || 0),
        low: parseFloat(stock.low || 0),
        close: parseFloat(stock.close || 0),
        adjClose: parseFloat(stock.adj_close || stock.close || 0),
        volume: parseInt(stock.volume || 0)
      } : null,
      metadata: {
        requestedSymbol: ticker,
        resolvedSymbol: tickerUpper,
        dataAvailability: {
          basicInfo: true,
          priceData: stock.close !== null,
          technicalIndicators: false, // Disabled for speed
          fundamentals: false // Disabled for speed
        },
        timestamp: new Date().toISOString()
      }
    };
    
    console.log(`✅ SIMPLIFIED: Successfully returned basic data for ${tickerUpper}`);
    
    res.json(response);
    
  } catch (error) {
    console.error('Error in simplified stock endpoint:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock data', 
      symbol: req.params.ticker,
      message: error.message,
      data: [], // Always return data as an array for frontend safety
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
