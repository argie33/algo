const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Debug endpoint to check stocks tables status
router.get('/debug', async (req, res) => {
  try {
    console.log('Stocks debug endpoint called');
    
    const tables = ['company_profile', 'market_data', 'key_metrics', 'price_daily', 'financial_data'];
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
          let sampleQuery;
          if (table === 'company_profile') {
            sampleQuery = `
              SELECT ticker, short_name, sector, industry
              FROM ${table} 
              ORDER BY ticker 
              LIMIT 3
            `;
          } else if (table === 'market_data') {
            sampleQuery = `
              SELECT ticker, regular_market_price, market_cap
              FROM ${table} 
              ORDER BY ticker 
              LIMIT 3
            `;
          } else if (table === 'key_metrics') {
            sampleQuery = `
              SELECT ticker, trailing_pe, forward_pe, dividend_yield
              FROM ${table} 
              ORDER BY ticker 
              LIMIT 3
            `;
          } else if (table === 'price_daily') {
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

// Simple test endpoint that returns raw data
router.get('/test', async (req, res) => {
  try {
    console.log('Stocks test endpoint called');
    
    const testQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.sector,
        md.regular_market_price,
        km.trailing_pe
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      ORDER BY cp.ticker
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

// Main stocks endpoint with comprehensive data and filters
router.get('/', async (req, res) => {  try {
    console.log('Stocks main endpoint called with params:', req.query);
    
    // First check if stock_symbols table exists
    try {
      const tableCheck = await query(`
        SELECT EXISTS (
          SELECT FROM information_schema.tables 
          WHERE table_schema = 'public' 
          AND table_name = 'stock_symbols'
        );
      `);
      
      if (!tableCheck.rows[0].exists) {
        return res.status(503).json({
          error: 'Stock data not available',
          message: 'The stock_symbols table does not exist. Please run the data loading scripts first.',
          timestamp: new Date().toISOString()
        });
      }
    } catch (tableCheckError) {
      console.error('Error checking if stock_symbols table exists:', tableCheckError);
      return res.status(500).json({
        error: 'Database connectivity issue',
        message: 'Unable to check database schema',
        details: tableCheckError.message,
        timestamp: new Date().toISOString()
      });
    }
    
    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 25, 100); // Cap at 100 for performance
    const offset = (page - 1) * limit;
    const search = req.query.search || '';
    const sector = req.query.sector || '';
    const minPrice = parseFloat(req.query.minPrice) || null;
    const maxPrice = parseFloat(req.query.maxPrice) || null;
    const minMarketCap = parseFloat(req.query.minMarketCap) || null;
    const maxMarketCap = parseFloat(req.query.maxMarketCap) || null;
    const sortBy = req.query.sortBy || 'ticker';
    const sortOrder = req.query.sortOrder || 'asc';
    
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramCount = 0;    // Add search filter
    if (search) {
      paramCount++;
      whereClause += ` AND (ss.symbol ILIKE $${paramCount} OR ss.security_name ILIKE $${paramCount})`;
      params.push(`%${search}%`);
    }

    // Add exchange filter (instead of sector)
    if (sector) {
      paramCount++;
      whereClause += ` AND ss.exchange = $${paramCount}`;
      params.push(sector);
    }    // Remove price and market cap filters since we don't have that data in stock_symbols
    // These filters are removed because stock_symbols only contains basic symbol info    // Determine sort column and validate (adjusted for stock_symbols table)
    const validSortColumns = {
      'ticker': 'ss.symbol',
      'symbol': 'ss.symbol',
      'name': 'ss.security_name',
      'exchange': 'ss.exchange',
      'market_category': 'ss.market_category'
    };

    const sortColumn = validSortColumns[sortBy] || 'ss.symbol';
    const sortDirection = sortOrder.toLowerCase() === 'desc' ? 'DESC' : 'ASC';

    console.log('Using whereClause:', whereClause, 'params:', params);    // Simple stocks query using actual stock_symbols table
    const stocksQuery = `
      SELECT 
        ss.symbol,
        ss.security_name,
        ss.exchange,
        ss.market_category,
        ss.cqs_symbol,
        ss.financial_status,
        ss.round_lot_size,
        ss.etf,
        ss.secondary_symbol
      FROM stock_symbols ss
      ${whereClause}
      ORDER BY ${sortColumn} ${sortDirection}
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    const countQuery = `
      SELECT COUNT(*) as total
      FROM stock_symbols ss
      ${whereClause}
    `;

    console.log('Executing queries with limit:', limit, 'offset:', offset);

    const [stocksResult, countResult] = await Promise.all([
      query(stocksQuery, params),
      query(countQuery, params.slice(0, -2)) // Remove limit and offset params
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);    // Format the response with available data from stock_symbols table    const formattedStocks = stocksResult.rows.map(stock => ({
      ticker: stock.symbol,
      symbol: stock.symbol,
      name: stock.security_name,
      fullName: stock.security_name,
      exchange: stock.exchange,
      marketCategory: stock.market_category,
      cqsSymbol: stock.cqs_symbol,
      financialStatus: stock.financial_status,
      roundLotSize: stock.round_lot_size,
      isEtf: stock.etf === 'Y',
      secondarySymbol: stock.secondary_symbol,
      // Placeholder values for missing financial data
      price: {
        current: null,
        previous: null,
        change: null,
        changePercent: null,
        fiftyTwoWeekHigh: null,
        fiftyTwoWeekLow: null
      },
      marketData: {
        marketCap: null,
        volume: null,
        lastPriceDate: null
      },
      valuation: {
        trailingPE: null,
        forwardPE: null,
        priceToBook: null,
        beta: null
      },
      dividends: {
        yield: null,
        rate: null
      },
      profitability: {
        returnOnEquity: null,
        returnOnAssets: null,
        profitMargin: null,
        operatingMargin: null,
        earningsPerShare: null
      },
      financialHealth: {
        debtToEquity: null,
        currentRatio: null
      }
    }));

    res.json({
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
        sector: sector || null,
        minPrice: minPrice,
        maxPrice: maxPrice,
        minMarketCap: minMarketCap,
        maxMarketCap: maxMarketCap,
        sortBy,
        sortOrder
      },
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching stocks:', error);
    console.error('Error stack:', error.stack);
    res.status(500).json({ 
      error: 'Failed to fetch stocks',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Quick stocks overview for initial page load
router.get('/quick/overview', async (req, res) => {
  try {
    console.log('Stocks quick overview endpoint called');
    
    const limit = Math.min(parseInt(req.query.limit) || 10, 25);
    
    const quickQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.sector,
        md.regular_market_price,
        md.market_cap,
        (md.regular_market_price - md.regular_market_previous_close) as price_change,
        CASE 
          WHEN md.regular_market_previous_close > 0 
          THEN ((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close * 100)
          ELSE 0
        END as price_change_percent,
        km.trailing_pe
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      WHERE md.regular_market_price IS NOT NULL
      ORDER BY md.market_cap DESC NULLS LAST
      LIMIT $1
    `;

    const result = await query(quickQuery, [limit]);

    res.json({
      data: result.rows,
      count: result.rows.length,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching quick stocks overview:', error);
    res.status(500).json({ 
      error: 'Failed to fetch quick stocks overview',
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

    const dataQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.sector,
        md.regular_market_price,
        md.market_cap,
        km.trailing_pe
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      ORDER BY cp.ticker ASC
      LIMIT $1 OFFSET $2
    `;

    const result = await query(dataQuery, [chunkSize, offset]);

    res.json({
      chunk: chunkIndex,
      chunkSize: chunkSize,
      dataCount: result.rows.length,
      data: result.rows,
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
    const sector = req.query.sector;

    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramIndex = 1;

    if (sector) {
      whereClause += ` AND cp.sector = $${paramIndex}`;
      params.push(sector);
      paramIndex++;
    }

    const dataQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.sector,
        cp.industry,
        md.regular_market_price,
        md.market_cap,
        km.trailing_pe,
        km.dividend_yield
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      ${whereClause}
      ORDER BY md.market_cap DESC NULLS LAST
      LIMIT $${paramIndex}
    `;

    const result = await query(dataQuery, [...params, limit]);

    res.json({
      warning: 'This endpoint returns limited data for performance reasons',
      actualLimit: limit,
      filters: { sector: sector || null },
      data: result.rows,
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
    
    const stockQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.long_name,
        cp.sector,        cp.industry,
        cp.currency,
        cp.exchange,
        cp.description,
        cp.employees,
        cp.country,
        md.regular_market_price,
        md.regular_market_previous_close,
        md.market_cap,
        md.fifty_two_week_high,
        md.fifty_two_week_low,
        md.average_volume,
        km.trailing_pe,
        km.forward_pe,
        km.price_to_book,
        km.dividend_yield,
        km.dividend_rate,
        km.beta,
        km.return_on_equity,
        km.return_on_assets,
        km.profit_margin,
        km.operating_margin,
        km.debt_to_equity,
        km.current_ratio,
        km.earnings_per_share,
        km.book_value,
        km.revenue_growth,
        km.earnings_growth
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      WHERE cp.ticker = $1
    `;

    const result = await query(stockQuery, [ticker.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({ 
        error: 'Stock not found',
        ticker: ticker.toUpperCase(),
        timestamp: new Date().toISOString()
      });
    }

    const stock = result.rows[0];
    const priceChange = stock.regular_market_price - (stock.regular_market_previous_close || stock.regular_market_price);
    const priceChangePercent = stock.regular_market_previous_close > 0 
      ? ((priceChange / stock.regular_market_previous_close) * 100) 
      : 0;

    res.json({
      ticker: ticker.toUpperCase(),
      data: {
        profile: {
          ticker: stock.ticker,
          name: stock.short_name,
          fullName: stock.long_name,
          sector: stock.sector,
          industry: stock.industry,
          currency: stock.currency,
          exchange: stock.exchange,
          website: stock.website,
          description: stock.description,
          employees: stock.employees,
          country: stock.country
        },
        pricing: {
          current: parseFloat(stock.regular_market_price || 0),
          previous: parseFloat(stock.regular_market_previous_close || 0),
          change: parseFloat(priceChange || 0),
          changePercent: parseFloat(priceChangePercent || 0),
          fiftyTwoWeekHigh: parseFloat(stock.fifty_two_week_high || 0),
          fiftyTwoWeekLow: parseFloat(stock.fifty_two_week_low || 0)
        },
        marketData: {
          marketCap: parseFloat(stock.market_cap || 0),
          averageVolume: parseInt(stock.average_volume || 0),
          beta: parseFloat(stock.beta || 0) || null
        },
        valuation: {
          trailingPE: parseFloat(stock.trailing_pe || 0) || null,
          forwardPE: parseFloat(stock.forward_pe || 0) || null,
          priceToBook: parseFloat(stock.price_to_book || 0) || null,
          bookValue: parseFloat(stock.book_value || 0) || null
        },
        dividends: {
          yield: parseFloat(stock.dividend_yield || 0) || null,
          rate: parseFloat(stock.dividend_rate || 0) || null
        },
        profitability: {
          returnOnEquity: parseFloat(stock.return_on_equity || 0) || null,
          returnOnAssets: parseFloat(stock.return_on_assets || 0) || null,
          profitMargin: parseFloat(stock.profit_margin || 0) || null,
          operatingMargin: parseFloat(stock.operating_margin || 0) || null,
          earningsPerShare: parseFloat(stock.earnings_per_share || 0) || null
        },
        growth: {
          revenueGrowth: parseFloat(stock.revenue_growth || 0) || null,
          earningsGrowth: parseFloat(stock.earnings_growth || 0) || null
        },
        financialHealth: {
          debtToEquity: parseFloat(stock.debt_to_equity || 0) || null,
          currentRatio: parseFloat(stock.current_ratio || 0) || null
        }
      },
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

// Get stock profile only
router.get('/:ticker/profile', async (req, res) => {
  try {
    const { ticker } = req.params;
    
    const profileQuery = `
      SELECT 
        ticker, short_name, long_name, sector, industry, 
        currency, exchange, website, description, employees, country
      FROM company_profile
      WHERE ticker = $1
    `;

    const result = await query(profileQuery, [ticker.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({ 
        error: 'Stock profile not found',
        ticker: ticker.toUpperCase()
      });
    }

    res.json({
      ticker: ticker.toUpperCase(),
      profile: result.rows[0],
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching stock profile:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock profile',
      details: error.message 
    });
  }
});

// Get stock metrics only
router.get('/:ticker/metrics', async (req, res) => {
  try {
    const { ticker } = req.params;
    
    const metricsQuery = `
      SELECT *
      FROM key_metrics
      WHERE ticker = $1
    `;

    const result = await query(metricsQuery, [ticker.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({ 
        error: 'Stock metrics not found',
        ticker: ticker.toUpperCase()
      });
    }

    res.json({
      ticker: ticker.toUpperCase(),
      metrics: result.rows[0],
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching stock metrics:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock metrics',
      details: error.message 
    });
  }
});

// Get stock price history
router.get('/:ticker/prices', async (req, res) => {
  try {
    const { ticker } = req.params;
    const timeframe = req.query.timeframe || 'daily';
    const limit = Math.min(parseInt(req.query.limit) || 100, 250);
    
    let tableName = 'price_daily';
    if (timeframe === 'weekly') tableName = 'price_weekly';
    if (timeframe === 'monthly') tableName = 'price_monthly';
    
    const pricesQuery = `
      SELECT symbol, date, open, high, low, close, volume
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT $2
    `;

    const result = await query(pricesQuery, [ticker.toUpperCase(), limit]);

    res.json({
      ticker: ticker.toUpperCase(),
      timeframe,
      prices: result.rows,
      count: result.rows.length,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching stock prices:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock prices',
      details: error.message 
    });
  }
});

// Get available sectors
router.get('/filters/sectors', async (req, res) => {
  try {
    const sectorsQuery = `
      SELECT DISTINCT sector, COUNT(*) as stock_count
      FROM company_profile
      WHERE sector IS NOT NULL AND sector != ''
      GROUP BY sector
      ORDER BY stock_count DESC, sector ASC
    `;

    const result = await query(sectorsQuery);

    res.json({
      sectors: result.rows,
      count: result.rows.length,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching sectors:', error);
    res.status(500).json({ 
      error: 'Failed to fetch sectors',
      details: error.message 
    });
  }
});

// Get available industries
router.get('/filters/industries', async (req, res) => {
  try {
    const industriesQuery = `
      SELECT DISTINCT industry, sector, COUNT(*) as stock_count
      FROM company_profile
      WHERE industry IS NOT NULL AND industry != ''
      GROUP BY industry, sector
      ORDER BY stock_count DESC, industry ASC
    `;

    const result = await query(industriesQuery);

    res.json({
      industries: result.rows,
      count: result.rows.length,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching industries:', error);
    res.status(500).json({ 
      error: 'Failed to fetch industries',
      details: error.message 
    });
  }
});

// Get market movers (now under stocks, not markets)
router.get('/movers/gainers', async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 10, 50);
    
    const gainersQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.sector,
        md.regular_market_price,
        (md.regular_market_price - md.regular_market_previous_close) as price_change,
        ((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close * 100) as price_change_percent,
        md.market_cap,
        pd.volume as latest_volume
      FROM company_profile cp
      JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN LATERAL (
        SELECT volume 
        FROM price_daily 
        WHERE symbol = cp.ticker 
        ORDER BY date DESC 
        LIMIT 1
      ) pd ON true
      WHERE md.regular_market_price IS NOT NULL 
        AND md.regular_market_previous_close IS NOT NULL 
        AND md.regular_market_previous_close > 0
        AND md.regular_market_price > md.regular_market_previous_close
      ORDER BY ((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close * 100) DESC
      LIMIT $1
    `;

    const result = await query(gainersQuery, [limit]);

    res.json({
      type: 'gainers',
      data: result.rows,
      count: result.rows.length,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching gainers:', error);
    res.status(500).json({ 
      error: 'Failed to fetch gainers',
      details: error.message 
    });
  }
});

// Get market losers
router.get('/movers/losers', async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 10, 50);
    
    const losersQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.sector,
        md.regular_market_price,
        (md.regular_market_price - md.regular_market_previous_close) as price_change,
        ((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close * 100) as price_change_percent,
        md.market_cap,
        pd.volume as latest_volume
      FROM company_profile cp
      JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN LATERAL (
        SELECT volume 
        FROM price_daily 
        WHERE symbol = cp.ticker 
        ORDER BY date DESC 
        LIMIT 1
      ) pd ON true
      WHERE md.regular_market_price IS NOT NULL 
        AND md.regular_market_previous_close IS NOT NULL 
        AND md.regular_market_previous_close > 0
        AND md.regular_market_price < md.regular_market_previous_close
      ORDER BY ((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close * 100) ASC
      LIMIT $1
    `;

    const result = await query(losersQuery, [limit]);

    res.json({
      type: 'losers',
      data: result.rows,
      count: result.rows.length,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching losers:', error);
    res.status(500).json({ 
      error: 'Failed to fetch losers',
      details: error.message 
    });
  }
});

// Get most active stocks
router.get('/movers/active', async (req, res) => {
  try {
    const limit = Math.min(parseInt(req.query.limit) || 10, 50);
    
    const activeQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.sector,
        md.regular_market_price,
        ((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close * 100) as price_change_percent,
        md.market_cap,
        pd.volume as latest_volume,
        pd.date as volume_date
      FROM company_profile cp
      JOIN market_data md ON cp.ticker = md.ticker
      JOIN LATERAL (
        SELECT volume, date 
        FROM price_daily 
        WHERE symbol = cp.ticker 
        ORDER BY date DESC 
        LIMIT 1
      ) pd ON true
      WHERE pd.volume IS NOT NULL
      ORDER BY pd.volume DESC
      LIMIT $1
    `;

    const result = await query(activeQuery, [limit]);

    res.json({
      type: 'most_active',
      data: result.rows,
      count: result.rows.length,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    console.error('Error fetching most active stocks:', error);
    res.status(500).json({ 
      error: 'Failed to fetch most active stocks',
      details: error.message 
    });
  }
});

// Stock screening endpoint
router.get('/screen', async (req, res) => {
  try {
    console.log('Stock screener endpoint called with params:', req.query);
    
    const page = parseInt(req.query.page) || 1;
    const limit = Math.min(parseInt(req.query.limit) || 25, 100);
    const offset = (page - 1) * limit;
    const search = req.query.search || '';
    const exchange = req.query.exchange || '';
    const marketCategory = req.query.marketCategory || '';
    const sortBy = req.query.sortBy || 'symbol';
    const sortOrder = req.query.sortOrder || 'asc';
    
    let whereClause = 'WHERE etf = \'N\''; // Only stocks, not ETFs
    const params = [];
    let paramCount = 0;

    // Add search filter
    if (search) {
      paramCount++;
      whereClause += ` AND (symbol ILIKE $${paramCount} OR security_name ILIKE $${paramCount})`;
      params.push(`%${search}%`);
    }

    // Add exchange filter
    if (exchange) {
      paramCount++;
      whereClause += ` AND exchange = $${paramCount}`;
      params.push(exchange);
    }

    // Add market category filter
    if (marketCategory) {
      paramCount++;
      whereClause += ` AND market_category = $${paramCount}`;
      params.push(marketCategory);
    }

    // Determine sort column
    const validSortColumns = {
      'symbol': 'symbol',
      'name': 'security_name',
      'exchange': 'exchange',
      'marketCategory': 'market_category'
    };

    const sortColumn = validSortColumns[sortBy] || 'symbol';
    const sortDirection = sortOrder.toLowerCase() === 'desc' ? 'DESC' : 'ASC';

    // Screen stocks query
    const screenQuery = `
      SELECT 
        symbol,
        security_name,
        exchange,
        market_category,
        financial_status,
        round_lot_size
      FROM stock_symbols
      ${whereClause}
      ORDER BY ${sortColumn} ${sortDirection}
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    const countQuery = `
      SELECT COUNT(*) as total
      FROM stock_symbols
      ${whereClause}
    `;

    const [screenResult, countResult] = await Promise.all([
      query(screenQuery, params),
      query(countQuery, params.slice(0, -2))
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    res.json({
      data: screenResult.rows.map(stock => ({
        symbol: stock.symbol,
        name: stock.security_name,
        exchange: stock.exchange,
        marketCategory: stock.market_category,
        financialStatus: stock.financial_status,
        roundLotSize: stock.round_lot_size,
        // Placeholder for screening metrics that would come from other tables
        metrics: {
          price: null,
          marketCap: null,
          peRatio: null,
          dividendYield: null,
          volume: null
        }
      })),
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
        marketCategory: marketCategory || null,
        sortBy,
        sortOrder
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
