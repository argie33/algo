const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Get all stocks with basic info and pagination
router.get('/', async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 10; // Reduced from 50 to 10
    const offset = (page - 1) * limit;
    const search = req.query.search || '';
    const sector = req.query.sector || '';
    
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramCount = 0;

    if (search) {
      paramCount++;
      whereClause += ` AND (cp.ticker ILIKE $${paramCount} OR cp.short_name ILIKE $${paramCount} OR cp.long_name ILIKE $${paramCount})`;
      params.push(`%${search}%`);
    }

    if (sector) {
      paramCount++;
      whereClause += ` AND cp.sector = $${paramCount}`;
      params.push(sector);
    }

    const stocksQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.long_name,
        cp.sector,
        cp.industry,
        md.market_cap,
        cp.currency,
        cp.exchange,
        md.regular_market_price,
        (md.regular_market_price - md.regular_market_previous_close) as regular_market_change,
        ((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close * 100) as regular_market_change_percent,
        md.fifty_two_week_high,
        md.fifty_two_week_low,
        km.trailing_pe,
        km.forward_pe,
        km.price_to_book,
        km.dividend_yield
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      ${whereClause}
      ORDER BY cp.ticker ASC
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    const result = await query(stocksQuery, params);

    // Count query for pagination
    const countQuery = `
      SELECT COUNT(*) as total
      FROM company_profile cp
      ${whereClause}
    `;

    const countResult = await query(countQuery, params.slice(0, -2)); // Remove limit and offset params

    const totalStocks = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(totalStocks / limit);

    res.json({
      stocks: result.rows,
      pagination: {
        currentPage: page,
        totalPages,
        totalStocks,
        hasNextPage: page < totalPages,
        hasPrevPage: page > 1
      }
    });

  } catch (error) {
    console.error('Error fetching stocks:', error);
    res.status(500).json({ error: 'Failed to fetch stocks' });
  }
});

// Stock screening endpoint
router.get('/screen', async (req, res) => {
  try {
    console.log('Stock screening endpoint called with params:', req.query);
    
    const {
      minPrice = 0,
      maxPrice = null,
      minMarketCap = null,
      maxMarketCap = null,
      minPE = null,
      maxPE = null,
      minDividendYield = null,
      sector = null,
      exchange = null,
      limit = 50,
      page = 1
    } = req.query;

    const offset = (parseInt(page) - 1) * parseInt(limit);
    let whereConditions = ['1=1'];
    const params = [];
    let paramCount = 0;

    // Price filters
    if (minPrice && parseFloat(minPrice) > 0) {
      paramCount++;
      whereConditions.push(`md.regular_market_price >= $${paramCount}`);
      params.push(parseFloat(minPrice));
    }

    if (maxPrice && parseFloat(maxPrice) > 0) {
      paramCount++;
      whereConditions.push(`md.regular_market_price <= $${paramCount}`);
      params.push(parseFloat(maxPrice));
    }

    // Market cap filters
    if (minMarketCap && parseFloat(minMarketCap) > 0) {
      paramCount++;
      whereConditions.push(`md.market_cap >= $${paramCount}`);
      params.push(parseFloat(minMarketCap));
    }

    if (maxMarketCap && parseFloat(maxMarketCap) > 0) {
      paramCount++;
      whereConditions.push(`md.market_cap <= $${paramCount}`);
      params.push(parseFloat(maxMarketCap));
    }

    // PE ratio filters
    if (minPE && parseFloat(minPE) > 0) {
      paramCount++;
      whereConditions.push(`km.trailing_pe >= $${paramCount}`);
      params.push(parseFloat(minPE));
    }

    if (maxPE && parseFloat(maxPE) > 0) {
      paramCount++;
      whereConditions.push(`km.trailing_pe <= $${paramCount}`);
      params.push(parseFloat(maxPE));
    }

    // Dividend yield filter
    if (minDividendYield && parseFloat(minDividendYield) > 0) {
      paramCount++;
      whereConditions.push(`km.dividend_yield >= $${paramCount}`);
      params.push(parseFloat(minDividendYield));
    }

    // Sector filter
    if (sector && sector !== 'all') {
      paramCount++;
      whereConditions.push(`cp.sector = $${paramCount}`);
      params.push(sector);
    }

    // Exchange filter
    if (exchange && exchange !== 'all') {
      paramCount++;
      whereConditions.push(`cp.exchange = $${paramCount}`);
      params.push(exchange);
    }

    const whereClause = whereConditions.join(' AND ');

    const screenQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.long_name,
        cp.sector,
        cp.industry,
        cp.exchange,
        md.regular_market_price,
        md.market_cap,
        km.trailing_pe,
        km.forward_pe,
        km.price_to_book,
        km.dividend_yield,
        (md.regular_market_price - md.regular_market_previous_close) as change,
        ((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close * 100) as change_percent
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      WHERE ${whereClause}
        AND md.regular_market_price IS NOT NULL
        AND md.market_cap IS NOT NULL
      ORDER BY md.market_cap DESC
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(parseInt(limit), offset);

    console.log('Executing screen query with params:', params);
    const result = await query(screenQuery, params);

    console.log('Screen query results:', result.rows.length, 'stocks found');

    res.json({
      stocks: result.rows,
      filters: {
        minPrice: parseFloat(minPrice) || 0,
        maxPrice: maxPrice ? parseFloat(maxPrice) : null,
        minMarketCap: minMarketCap ? parseFloat(minMarketCap) : null,
        maxMarketCap: maxMarketCap ? parseFloat(maxMarketCap) : null,
        minPE: minPE ? parseFloat(minPE) : null,
        maxPE: maxPE ? parseFloat(maxPE) : null,
        minDividendYield: minDividendYield ? parseFloat(minDividendYield) : null,
        sector: sector || 'all',
        exchange: exchange || 'all'
      },
      pagination: {
        page: parseInt(page),
        limit: parseInt(limit),
        count: result.rows.length
      }
    });

  } catch (error) {
    console.error('Error in stock screening:', error);
    res.status(500).json({ 
      error: 'Failed to screen stocks',
      message: error.message 
    });
  }
});

// SPECIFIC ROUTES MUST COME BEFORE /:ticker

// Quick overview endpoint for dashboard
router.get('/quick/overview', async (req, res) => {
  try {
    const limit = parseInt(req.query.limit) || 20;
    
    const quickQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.sector,
        md.regular_market_price,
        (md.regular_market_price - md.regular_market_previous_close) as change,
        ((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close * 100) as change_percent,
        md.market_cap
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      WHERE md.regular_market_price IS NOT NULL
        AND md.market_cap IS NOT NULL
      ORDER BY md.market_cap DESC
      LIMIT $1
    `;

    const result = await query(quickQuery, [limit]);

    res.json({
      success: true,
      data: result.rows,
      count: result.rows.length
    });

  } catch (error) {
    console.error('Error fetching quick overview:', error);
    res.status(500).json({ 
      error: 'Failed to fetch quick overview',
      message: error.message 
    });
  }
});

// Get available filter options
router.get('/filters/sectors', async (req, res) => {
  try {
    const sectorsQuery = `
      SELECT DISTINCT sector
      FROM company_profile
      WHERE sector IS NOT NULL
      ORDER BY sector ASC
    `;

    const result = await query(sectorsQuery);

    res.json({
      sectors: result.rows.map(row => row.sector)
    });

  } catch (error) {
    console.error('Error fetching sectors:', error);
    res.status(500).json({ error: 'Failed to fetch sectors' });
  }
});

// Chunked loading endpoint
router.get('/chunk/:chunkIndex', async (req, res) => {
  try {
    const chunkIndex = parseInt(req.params.chunkIndex) || 0;
    const chunkSize = 10;
    const offset = chunkIndex * chunkSize;

    const chunkQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.long_name,
        cp.sector,
        md.regular_market_price,
        (md.regular_market_price - md.regular_market_previous_close) as change,
        ((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close * 100) as change_percent,
        md.market_cap
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      WHERE md.regular_market_price IS NOT NULL
      ORDER BY md.market_cap DESC
      LIMIT $1 OFFSET $2
    `;

    const result = await query(chunkQuery, [chunkSize, offset]);

    res.json({
      success: true,
      data: result.rows,
      chunkIndex,
      chunkSize,
      count: result.rows.length
    });

  } catch (error) {
    console.error('Error fetching stock chunk:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock chunk',
      message: error.message 
    });
  }
});

// Full data endpoint
router.get('/full/data', async (req, res) => {
  try {
    const limit = parseInt(req.query.limit) || 100;
    
    const fullQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.long_name,
        cp.sector,
        cp.industry,
        cp.exchange,
        md.regular_market_price,
        md.market_cap,
        km.trailing_pe,
        km.forward_pe,
        km.price_to_book,
        km.dividend_yield,
        (md.regular_market_price - md.regular_market_previous_close) as change,
        ((md.regular_market_price - md.regular_market_previous_close) / md.regular_market_previous_close * 100) as change_percent
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      WHERE md.regular_market_price IS NOT NULL
      ORDER BY md.market_cap DESC
      LIMIT $1
    `;

    const result = await query(fullQuery, [limit]);

    res.json({
      success: true,
      data: result.rows,
      count: result.rows.length
    });

  } catch (error) {
    console.error('Error fetching full stock data:', error);
    res.status(500).json({ 
      error: 'Failed to fetch full stock data',
      message: error.message 
    });
  }
});

// Get detailed info for a specific stock - MUST BE LAST
router.get('/:ticker', async (req, res) => {
  try {
    const { ticker } = req.params;
    console.log(`Stock detail endpoint called for ticker: ${ticker}`);

    const stockQuery = `
      SELECT 
        cp.ticker,
        cp.short_name,
        cp.long_name,
        cp.sector,
        cp.industry,
        cp.website,
        cp.description,
        cp.employees,
        cp.city,
        cp.state,
        cp.country,
        cp.exchange,
        cp.currency,
        md.*,
        km.*,
        fs.*
      FROM company_profile cp
      LEFT JOIN market_data md ON cp.ticker = md.ticker
      LEFT JOIN key_metrics km ON cp.ticker = km.ticker
      LEFT JOIN financial_summary fs ON cp.ticker = fs.ticker
      WHERE UPPER(cp.ticker) = UPPER($1)
    `;

    const result = await query(stockQuery, [ticker]);

    if (result.rows.length === 0) {
      return res.status(404).json({ 
        error: 'Stock not found',
        ticker: ticker.toUpperCase()
      });
    }

    const stock = result.rows[0];

    res.json({
      success: true,
      stock,
      metadata: {
        ticker: ticker.toUpperCase(),
        hasFinancialData: !!stock.total_revenue,
        hasMarketData: !!stock.regular_market_price
      }
    });

  } catch (error) {
    console.error('Error fetching stock details:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock details',
      message: error.message 
    });
  }
});

module.exports = router;
