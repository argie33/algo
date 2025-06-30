const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Helper: fallback stocks data
const fallbackStocks = [
  {
    symbol: 'AAPL',
    company_name: 'Apple Inc.',
    sector: 'Technology',
    industry: 'Consumer Electronics',
    current_price: 150.25,
    previous_close: 148.50,
    change_percent: 1.18,
    volume: 100000000,
    market_capitalization: 2500000000000,
    pe_ratio: 28.5,
    dividend_yield: 0.006,
    beta: 1.2,
    fifty_two_week_high: 180.00,
    fifty_two_week_low: 120.00,
    avg_volume: 90000000,
    return_on_equity: 0.32,
    revenue_growth: 0.12,
    current_ratio: 1.1,
    debt_to_equity: 1.5,
    last_updated: new Date().toISOString(),
    exchange: 'NASDAQ',
    country: 'US'
  },
  {
    symbol: 'MSFT',
    company_name: 'Microsoft Corporation',
    sector: 'Technology',
    industry: 'Software',
    current_price: 320.50,
    previous_close: 318.00,
    change_percent: 0.79,
    volume: 50000000,
    market_capitalization: 2400000000000,
    pe_ratio: 35.2,
    dividend_yield: 0.008,
    beta: 0.95,
    fifty_two_week_high: 340.00,
    fifty_two_week_low: 250.00,
    avg_volume: 40000000,
    return_on_equity: 0.28,
    revenue_growth: 0.10,
    current_ratio: 1.5,
    debt_to_equity: 1.0,
    last_updated: new Date().toISOString(),
    exchange: 'NASDAQ',
    country: 'US'
  },
  {
    symbol: 'GOOGL',
    company_name: 'Alphabet Inc.',
    sector: 'Communication Services',
    industry: 'Internet Content & Information',
    current_price: 2750.00,
    previous_close: 2735.00,
    change_percent: 0.55,
    volume: 2000000,
    market_capitalization: 1800000000000,
    pe_ratio: 30.1,
    dividend_yield: 0.0,
    beta: 1.1,
    fifty_two_week_high: 2900.00,
    fifty_two_week_low: 2000.00,
    avg_volume: 1800000,
    return_on_equity: 0.25,
    revenue_growth: 0.15,
    current_ratio: 2.0,
    debt_to_equity: 0.8,
    last_updated: new Date().toISOString(),
    exchange: 'NASDAQ',
    country: 'US'
  }
];

// Basic ping endpoint
router.get('/ping', (req, res) => {
  res.json({
    status: 'ok',
    endpoint: 'stocks',
    timestamp: new Date().toISOString()
  });
});

// Test endpoint to check stocks table structure and data
router.get('/test', async (req, res) => {
  try {
    // Check if table exists
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'stocks'
      );
    `, []);

    if (!tableExists.rows[0].exists) {
      return res.json({
        tableExists: false,
        message: 'Stocks table not found'
      });
    }

    // Get table structure
    const columns = await query(`
      SELECT column_name, data_type 
      FROM information_schema.columns 
      WHERE table_name = 'stocks' 
      ORDER BY ordinal_position
    `, []);

    // Get sample data
    const sampleData = await query(`
      SELECT * FROM stocks LIMIT 3
    `, []);

    // Get total count
    const countResult = await query(`
      SELECT COUNT(*) as total FROM stocks
    `, []);

    res.json({
      tableExists: true,
      totalRecords: parseInt(countResult.rows[0].total),
      columns: columns.rows,
      sampleData: sampleData.rows,
      message: 'Stocks table structure and sample data retrieved'
    });
  } catch (error) {
    console.error('Error in stocks test endpoint:', error);
    res.status(500).json({
      error: 'Failed to test stocks table',
      message: error.message
    });
  }
});

// Get stocks with filtering and pagination
router.get('/', async (req, res) => {
  const { 
    page = 1, 
    limit = 50, 
    sector, 
    market_cap_min, 
    market_cap_max, 
    volume_min, 
    price_min, 
    price_max,
    pe_ratio_min,
    pe_ratio_max,
    dividend_yield_min,
    dividend_yield_max,
    return_on_equity_min,
    return_on_equity_max,
    revenue_growth_min,
    revenue_growth_max,
    current_ratio_min,
    current_ratio_max,
    debt_to_equity_min,
    debt_to_equity_max,
    exchange,
    country,
    sortBy = 'market_cap',
    sortOrder = 'desc'
  } = req.query;

  console.log('Stocks endpoint called with params:', {
    page, limit, sector, market_cap_min, market_cap_max, 
    price_min, price_max, sortBy, sortOrder
  });

  try {
    const offset = (parseInt(page) - 1) * parseInt(limit);
    const maxLimit = Math.min(parseInt(limit), 200);

    console.log('Query parameters:', { offset, maxLimit });

    // Build WHERE clause
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramIndex = 1;

    // Sector filter
    if (sector && sector.trim()) {
      whereClause += ` AND sector = $${paramIndex}`;
      params.push(sector);
      paramIndex++;
    }

    // Exchange filter
    if (exchange && exchange.trim()) {
      whereClause += ` AND exchange = $${paramIndex}`;
      params.push(exchange);
      paramIndex++;
    }

    // Country filter
    if (country && country.trim()) {
      whereClause += ` AND country = $${paramIndex}`;
      params.push(country);
      paramIndex++;
    }

    // Market cap filters
    if (market_cap_min) {
      whereClause += ` AND market_cap >= $${paramIndex}`;
      params.push(parseFloat(market_cap_min) * 1e9); // Convert billions to actual value
      paramIndex++;
    }

    if (market_cap_max) {
      whereClause += ` AND market_cap <= $${paramIndex}`;
      params.push(parseFloat(market_cap_max) * 1e9); // Convert billions to actual value
      paramIndex++;
    }

    // Volume filter
    if (volume_min) {
      whereClause += ` AND volume >= $${paramIndex}`;
      params.push(parseFloat(volume_min));
      paramIndex++;
    }

    // Price filters
    if (price_min) {
      whereClause += ` AND current_price >= $${paramIndex}`;
      params.push(parseFloat(price_min));
      paramIndex++;
    }

    if (price_max) {
      whereClause += ` AND current_price <= $${paramIndex}`;
      params.push(parseFloat(price_max));
      paramIndex++;
    }

    // P/E ratio filters
    if (pe_ratio_min) {
      whereClause += ` AND pe_ratio >= $${paramIndex}`;
      params.push(parseFloat(pe_ratio_min));
      paramIndex++;
    }

    if (pe_ratio_max) {
      whereClause += ` AND pe_ratio <= $${paramIndex}`;
      params.push(parseFloat(pe_ratio_max));
      paramIndex++;
    }

    // Dividend yield filters
    if (dividend_yield_min) {
      whereClause += ` AND dividend_yield >= $${paramIndex}`;
      params.push(parseFloat(dividend_yield_min) / 100); // Convert percentage to decimal
      paramIndex++;
    }

    if (dividend_yield_max) {
      whereClause += ` AND dividend_yield <= $${paramIndex}`;
      params.push(parseFloat(dividend_yield_max) / 100); // Convert percentage to decimal
      paramIndex++;
    }

    // ROE filters
    if (return_on_equity_min) {
      whereClause += ` AND return_on_equity >= $${paramIndex}`;
      params.push(parseFloat(return_on_equity_min) / 100); // Convert percentage to decimal
      paramIndex++;
    }

    if (return_on_equity_max) {
      whereClause += ` AND return_on_equity <= $${paramIndex}`;
      params.push(parseFloat(return_on_equity_max) / 100); // Convert percentage to decimal
      paramIndex++;
    }

    // Revenue growth filters
    if (revenue_growth_min) {
      whereClause += ` AND revenue_growth >= $${paramIndex}`;
      params.push(parseFloat(revenue_growth_min) / 100); // Convert percentage to decimal
      paramIndex++;
    }

    if (revenue_growth_max) {
      whereClause += ` AND revenue_growth <= $${paramIndex}`;
      params.push(parseFloat(revenue_growth_max) / 100); // Convert percentage to decimal
      paramIndex++;
    }

    // Current ratio filters
    if (current_ratio_min) {
      whereClause += ` AND current_ratio >= $${paramIndex}`;
      params.push(parseFloat(current_ratio_min));
      paramIndex++;
    }

    if (current_ratio_max) {
      whereClause += ` AND current_ratio <= $${paramIndex}`;
      params.push(parseFloat(current_ratio_max));
      paramIndex++;
    }

    // Debt to equity filters
    if (debt_to_equity_min) {
      whereClause += ` AND debt_to_equity >= $${paramIndex}`;
      params.push(parseFloat(debt_to_equity_min));
      paramIndex++;
    }

    if (debt_to_equity_max) {
      whereClause += ` AND debt_to_equity <= $${paramIndex}`;
      params.push(parseFloat(debt_to_equity_max));
      paramIndex++;
    }

    // Check if stocks table exists
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'stocks'
      );
    `, []);

    if (!tableExists.rows[0].exists) {
      return res.status(500).json({ error: 'Stocks table not found in database' });
    }

    // Get total count
    const countQuery = `
      SELECT COUNT(*) as total
      FROM stocks
      ${whereClause}
    `;
    const countResult = await query(countQuery, params);
    const total = parseInt(countResult.rows[0].total);

    // Validate sortBy field
    const validSortFields = [
      'symbol', 'company_name', 'current_price', 'market_cap', 'pe_ratio', 
      'dividend_yield', 'return_on_equity', 'revenue_growth', 'sector'
    ];
    const safeSortBy = validSortFields.includes(sortBy) ? sortBy : 'market_cap';
    const safeSortOrder = sortOrder.toLowerCase() === 'asc' ? 'ASC' : 'DESC';

    // Get stocks data with proper field mapping
    const dataQuery = `
      SELECT 
        symbol,
        company_name,
        sector,
        industry,
        current_price as price,
        previous_close,
        change_percent,
        volume,
        market_cap as market_capitalization,
        pe_ratio,
        dividend_yield,
        beta,
        fifty_two_week_high,
        fifty_two_week_low,
        avg_volume,
        COALESCE(return_on_equity, 0) as return_on_equity,
        COALESCE(revenue_growth, 0) as revenue_growth,
        COALESCE(current_ratio, 0) as current_ratio,
        COALESCE(debt_to_equity, 0) as debt_to_equity,
        last_updated
      FROM stocks
      ${whereClause}
      ORDER BY ${safeSortBy} ${safeSortOrder}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    const finalParams = [...params, maxLimit, offset];
    const dataResult = await query(dataQuery, finalParams);

    const totalPages = Math.ceil(total / maxLimit);

    console.log('Stocks query results:', {
      total,
      returnedRows: dataResult.rows.length,
      sampleRow: dataResult.rows[0] || 'No data',
      whereClause,
      params: params.slice(0, 5) // Show first 5 params for debugging
    });

    res.json({
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
      metadata: {
        filters: {
          sector: sector || null,
          market_cap_min: market_cap_min || null,
          market_cap_max: market_cap_max || null,
          volume_min: volume_min || null,
          price_min: price_min || null,
          price_max: price_max || null,
          pe_ratio_min: pe_ratio_min || null,
          pe_ratio_max: pe_ratio_max || null,
          dividend_yield_min: dividend_yield_min || null,
          dividend_yield_max: dividend_yield_max || null,
          return_on_equity_min: return_on_equity_min || null,
          return_on_equity_max: return_on_equity_max || null,
          revenue_growth_min: revenue_growth_min || null,
          revenue_growth_max: revenue_growth_max || null,
          current_ratio_min: current_ratio_min || null,
          current_ratio_max: current_ratio_max || null,
          debt_to_equity_min: debt_to_equity_min || null,
          debt_to_equity_max: debt_to_equity_max || null,
          exchange: exchange || null,
          country: country || null
        },
        sorting: {
          sortBy: safeSortBy,
          sortOrder: safeSortOrder
        }
      }
    });
  } catch (error) {
    return res.status(500).json({ error: 'Database error', details: error.message });
  }
});

// Get individual stock details
router.get('/:symbol', async (req, res) => {
  const { symbol } = req.params;

  try {
    // Check if stocks table exists
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'stocks'
      );
    `, []);

    if (!tableExists.rows[0].exists) {
      return res.status(500).json({ error: 'Stocks table not found in database' });
    }

    // Get stock details
    const stockQuery = `
      SELECT 
        symbol,
        company_name,
        sector,
        industry,
        current_price,
        previous_close,
        change_percent,
        volume,
        market_cap,
        pe_ratio,
        dividend_yield,
        beta,
        fifty_two_week_high,
        fifty_two_week_low,
        avg_volume,
        last_updated
      FROM stocks
      WHERE symbol = $1
    `;

    const result = await query(stockQuery, [symbol.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'Stock not found' });
    }

    res.json({
      data: result.rows[0]
    });
  } catch (error) {
    return res.status(500).json({ error: 'Database error', details: error.message });
  }
});

// Get stock price history
router.get('/price-history/:symbol', async (req, res) => {
  const { symbol } = req.params;
  const { limit = 90 } = req.query;

  try {
    // Check if price data table exists
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'price_data_daily'
      );
    `, []);

    if (!tableExists.rows[0].exists) {
      return res.status(500).json({ error: 'Price data table not found in database' });
    }

    // Get price history
    const priceQuery = `
      SELECT 
        date,
        open,
        high,
        low,
        close,
        volume
      FROM price_data_daily
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT $2
    `;

    const result = await query(priceQuery, [symbol.toUpperCase(), parseInt(limit)]);

    res.json({
      data: result.rows.reverse(), // Return in chronological order
      count: result.rows.length,
      symbol: symbol.toUpperCase()
    });
  } catch (error) {
    return res.status(500).json({ error: 'Database error', details: error.message });
  }
});

// Get sectors for filtering
router.get('/filters/sectors', async (req, res) => {
  try {
    // Check if stocks table exists
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'stocks'
      );
    `, []);

    if (!tableExists.rows[0].exists) {
      return res.status(500).json({ error: 'Stocks table not found in database' });
    }

    // Get unique sectors
    const sectorsQuery = `
      SELECT DISTINCT sector
      FROM stocks
      WHERE sector IS NOT NULL AND sector != ''
      ORDER BY sector
    `;

    const result = await query(sectorsQuery);

    res.json({
      data: result.rows.map(row => row.sector),
      count: result.rows.length
    });
  } catch (error) {
    return res.status(500).json({ error: 'Database error', details: error.message });
  }
});

// Get market cap categories
router.get('/market-cap-categories', async (req, res) => {
  try {
    // Get market cap categories from stocks table
    const categoriesQuery = `
      SELECT DISTINCT market_cap_category
      FROM stocks
      WHERE market_cap_category IS NOT NULL
        AND market_cap_category != ''
      ORDER BY market_cap_category
    `;
    
    const result = await query(categoriesQuery);
    
    const categories = result.rows.map(row => ({
      category: row.market_cap_category,
      label: getMarketCapLabel(row.market_cap_category)
    }));

    res.json({
      data: categories,
      count: categories.length
    });
  } catch (error) {
    console.error('Error fetching market cap categories:', error);
    res.status(500).json({ error: 'Failed to fetch market cap categories' });
  }
});

// Get volume data for a specific stock
router.get('/:symbol/volume', async (req, res) => {
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
    
    const volumeQuery = `
      SELECT 
        symbol,
        date,
        volume,
        close,
        high,
        low
      FROM ${tableName}
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 100
    `;
    
    const result = await query(volumeQuery, [symbol.toUpperCase()]);
    
    res.json({
      data: result.rows,
      count: result.rows.length,
      symbol: symbol.toUpperCase(),
      timeframe
    });
  } catch (error) {
    console.error('Error fetching volume data:', error);
    res.status(500).json({ error: 'Failed to fetch volume data' });
  }
});

// Helper function to get market cap labels
function getMarketCapLabel(category) {
  const labels = {
    'Q': 'Large Cap',
    'G': 'Mid Cap', 
    'S': 'Small Cap',
    'N': 'Nano Cap'
  };
  return labels[category] || category;
}

// Get stock info for a specific symbol
router.get('/info/:symbol', async (req, res) => {
  const { symbol } = req.params;
  console.log(`ℹ️ [STOCKS] Fetching stock info for ${symbol}`);
  
  try {
    // Get stock information
    const infoQuery = `
      SELECT 
        symbol,
        company_name,
        sector,
        industry,
        exchange,
        country,
        market_cap,
        current_price,
        volume,
        pe_ratio,
        dividend_yield,
        return_on_equity,
        revenue_growth,
        current_ratio,
        debt_to_equity,
        updated_at
      FROM stocks
      WHERE symbol = $1
    `;

    const result = await query(infoQuery, [symbol.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: `No stock info found for symbol ${symbol}`
      });
    }

    res.json({
      success: true,
      data: result.rows[0],
      symbol: symbol.toUpperCase()
    });
  } catch (error) {
    return res.status(500).json({ error: 'Database error', details: error.message });
  }
});

// Get stock price for a specific symbol
router.get('/price/:symbol', async (req, res) => {
  const { symbol } = req.params;
  console.log(`💰 [STOCKS] Fetching stock price for ${symbol}`);
  
  try {
    // Get latest price data
    const priceQuery = `
      SELECT 
        symbol,
        current_price,
        previous_close,
        change_amount,
        change_percent,
        volume,
        market_cap,
        date
      FROM latest_price_daily
      WHERE symbol = $1
      ORDER BY date DESC
      LIMIT 1
    `;

    const result = await query(priceQuery, [symbol.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: `No price data found for symbol ${symbol}`
      });
    }

    res.json({
      success: true,
      data: result.rows[0],
      symbol: symbol.toUpperCase()
    });
  } catch (error) {
    return res.status(500).json({ error: 'Database error', details: error.message });
  }
});

// Get stock history for a specific symbol
router.get('/history/:symbol', async (req, res) => {
  const { symbol } = req.params;
  const { days = 90 } = req.query;
  console.log(`📊 [STOCKS] Fetching stock history for ${symbol} (${days} days)`);
  
  try {
    // Get price history
    const historyQuery = `
      SELECT 
        symbol,
        date,
        open,
        high,
        low,
        close,
        volume,
        adjusted_close
      FROM price_daily
      WHERE symbol = $1
        AND date >= CURRENT_DATE - INTERVAL '${days} days'
      ORDER BY date ASC
    `;

    const result = await query(historyQuery, [symbol.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        success: false,
        error: `No price history found for symbol ${symbol}`
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
    return res.status(500).json({ error: 'Database error', details: error.message });
  }
});

// Search stocks
router.get('/search', async (req, res) => {
  const { q } = req.query;
  console.log(`🔍 [STOCKS] Searching stocks with query: ${q}`);
  
  if (!q || q.trim().length === 0) {
    return res.status(400).json({
      success: false,
      error: 'Search query is required'
    });
  }
  
  try {
    // Search stocks by symbol or company name
    const searchQuery = `
      SELECT 
        symbol,
        company_name,
        sector,
        industry,
        exchange,
        current_price,
        market_cap
      FROM stocks
      WHERE symbol ILIKE $1 
        OR company_name ILIKE $1
      ORDER BY 
        CASE WHEN symbol ILIKE $1 THEN 1 ELSE 2 END,
        market_cap DESC
      LIMIT 20
    `;

    const result = await query(searchQuery, [`%${q.trim()}%`]);

    res.json({
      success: true,
      data: result.rows,
      count: result.rows.length,
      query: q.trim()
    });
  } catch (error) {
    return res.status(500).json({ error: 'Database error', details: error.message });
  }
});

// Screen stocks with advanced filtering
router.get('/screen', async (req, res) => {
  console.log('🔍 [STOCKS] Screen endpoint called with query:', req.query);

  const { 
    search,
    sector,
    industry,
    country,
    exchange,
    priceMin,
    priceMax,
    marketCapMin,
    marketCapMax,
    peRatioMin,
    peRatioMax,
    pegRatioMin,
    pegRatioMax,
    pbRatioMin,
    pbRatioMax,
    roeMin,
    roeMax,
    roaMin,
    roaMax,
    netMarginMin,
    netMarginMax,
    revenueGrowthMin,
    revenueGrowthMax,
    earningsGrowthMin,
    earningsGrowthMax,
    dividendYieldMin,
    dividendYieldMax,
    payoutRatioMin,
    payoutRatioMax,
    currentRatioMin,
    currentRatioMax,
    debtToEquityMin,
    debtToEquityMax,
    minAnalystRating,
    hasEarningsGrowth,
    hasPositiveCashFlow,
    paysDividends,
    page = 1,
    limit = 25,
    sortBy = 'symbol',
    sortOrder = 'asc'
  } = req.query;

  try {
    // Check if stocks table exists
    console.log('🔍 [STOCKS] Checking if stocks table exists...');
    const tableExists = await query(`
      SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'stocks'
      );
    `, []);

    if (!tableExists.rows[0].exists) {
      console.error('❌ [STOCKS] Table does not exist');
      return res.status(500).json({ 
        success: false,
        error: 'Stocks table not found in database',
        details: 'The stocks table does not exist in the database. Please ensure the database is properly initialized.'
      });
    }

    console.log('✅ [STOCKS] Table exists, proceeding with query...');

    const offset = (parseInt(page) - 1) * parseInt(limit);
    const maxLimit = Math.min(parseInt(limit), 200);

    // Build WHERE clause
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramIndex = 1;

    // Search filter
    if (search && search.trim()) {
      whereClause += ` AND (symbol ILIKE $${paramIndex} OR company_name ILIKE $${paramIndex})`;
      params.push(`%${search.trim()}%`);
      paramIndex++;
    }

    // Sector filter
    if (sector && sector.trim()) {
      whereClause += ` AND sector = $${paramIndex}`;
      params.push(sector);
      paramIndex++;
    }

    // Industry filter
    if (industry && industry.trim()) {
      whereClause += ` AND industry = $${paramIndex}`;
      params.push(industry);
      paramIndex++;
    }

    // Country filter
    if (country && country.trim()) {
      whereClause += ` AND country = $${paramIndex}`;
      params.push(country);
      paramIndex++;
    }

    // Exchange filter
    if (exchange && exchange.trim()) {
      whereClause += ` AND exchange = $${paramIndex}`;
      params.push(exchange);
      paramIndex++;
    }

    // Price filters
    if (priceMin) {
      whereClause += ` AND current_price >= $${paramIndex}`;
      params.push(parseFloat(priceMin));
      paramIndex++;
    }

    if (priceMax) {
      whereClause += ` AND current_price <= $${paramIndex}`;
      params.push(parseFloat(priceMax));
      paramIndex++;
    }

    // Market cap filters
    if (marketCapMin) {
      whereClause += ` AND market_cap >= $${paramIndex}`;
      params.push(parseFloat(marketCapMin) * 1e9); // Convert billions to actual value
      paramIndex++;
    }

    if (marketCapMax) {
      whereClause += ` AND market_cap <= $${paramIndex}`;
      params.push(parseFloat(marketCapMax) * 1e9); // Convert billions to actual value
      paramIndex++;
    }

    // P/E ratio filters
    if (peRatioMin) {
      whereClause += ` AND pe_ratio >= $${paramIndex}`;
      params.push(parseFloat(peRatioMin));
      paramIndex++;
    }

    if (peRatioMax) {
      whereClause += ` AND pe_ratio <= $${paramIndex}`;
      params.push(parseFloat(peRatioMax));
      paramIndex++;
    }

    // ROE filters
    if (roeMin) {
      whereClause += ` AND return_on_equity >= $${paramIndex}`;
      params.push(parseFloat(roeMin) / 100); // Convert percentage to decimal
      paramIndex++;
    }

    if (roeMax) {
      whereClause += ` AND return_on_equity <= $${paramIndex}`;
      params.push(parseFloat(roeMax) / 100); // Convert percentage to decimal
      paramIndex++;
    }

    // Revenue growth filters
    if (revenueGrowthMin) {
      whereClause += ` AND revenue_growth >= $${paramIndex}`;
      params.push(parseFloat(revenueGrowthMin) / 100); // Convert percentage to decimal
      paramIndex++;
    }

    if (revenueGrowthMax) {
      whereClause += ` AND revenue_growth <= $${paramIndex}`;
      params.push(parseFloat(revenueGrowthMax) / 100); // Convert percentage to decimal
      paramIndex++;
    }

    // Dividend yield filters
    if (dividendYieldMin) {
      whereClause += ` AND dividend_yield >= $${paramIndex}`;
      params.push(parseFloat(dividendYieldMin) / 100); // Convert percentage to decimal
      paramIndex++;
    }

    if (dividendYieldMax) {
      whereClause += ` AND dividend_yield <= $${paramIndex}`;
      params.push(parseFloat(dividendYieldMax) / 100); // Convert percentage to decimal
      paramIndex++;
    }

    // Current ratio filters
    if (currentRatioMin) {
      whereClause += ` AND current_ratio >= $${paramIndex}`;
      params.push(parseFloat(currentRatioMin));
      paramIndex++;
    }

    if (currentRatioMax) {
      whereClause += ` AND current_ratio <= $${paramIndex}`;
      params.push(parseFloat(currentRatioMax));
      paramIndex++;
    }

    // Debt to equity filters
    if (debtToEquityMin) {
      whereClause += ` AND debt_to_equity >= $${paramIndex}`;
      params.push(parseFloat(debtToEquityMin));
      paramIndex++;
    }

    if (debtToEquityMax) {
      whereClause += ` AND debt_to_equity <= $${paramIndex}`;
      params.push(parseFloat(debtToEquityMax));
      paramIndex++;
    }

    // Boolean filters
    if (hasEarningsGrowth === 'true') {
      whereClause += ` AND revenue_growth > 0`;
    }

    if (hasPositiveCashFlow === 'true') {
      whereClause += ` AND current_ratio > 1`;
    }

    if (paysDividends === 'true') {
      whereClause += ` AND dividend_yield > 0`;
    }

    // Get total count first
    const countQuery = `
      SELECT COUNT(*) as total
      FROM stocks
      ${whereClause}
    `;
    console.log('🔍 [STOCKS] Executing count query:', countQuery);
    const countResult = await query(countQuery, params);
    const total = parseInt(countResult.rows[0].total);
    console.log(`✅ [STOCKS] Found ${total} total matching records`);

    // Validate sortBy field
    const validSortFields = [
      'symbol', 'company_name', 'current_price', 'market_cap', 'pe_ratio', 
      'dividend_yield', 'return_on_equity', 'revenue_growth', 'sector'
    ];
    const safeSortBy = validSortFields.includes(sortBy) ? sortBy : 'market_cap';
    const safeSortOrder = sortOrder.toLowerCase() === 'asc' ? 'ASC' : 'DESC';

    // Get stocks data
    const dataQuery = `
      SELECT 
        symbol,
        company_name,
        sector,
        industry,
        current_price,
        previous_close,
        change_percent,
        volume,
        market_cap,
        pe_ratio,
        dividend_yield,
        beta,
        fifty_two_week_high,
        fifty_two_week_low,
        avg_volume,
        COALESCE(return_on_equity, 0) as return_on_equity,
        COALESCE(revenue_growth, 0) as revenue_growth,
        COALESCE(current_ratio, 0) as current_ratio,
        COALESCE(debt_to_equity, 0) as debt_to_equity,
        last_updated
      FROM stocks
      ${whereClause}
      ORDER BY ${safeSortBy} ${safeSortOrder}
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    console.log('🔍 [STOCKS] Executing data query:', {
      query: dataQuery,
      params: [...params, maxLimit, offset]
    });

    const finalParams = [...params, maxLimit, offset];
    const dataResult = await query(dataQuery, finalParams);
    console.log(`✅ [STOCKS] Retrieved ${dataResult.rows.length} records`);

    const totalPages = Math.ceil(total / maxLimit);

    const response = {
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
      }
    };

    console.log('✅ [STOCKS] Sending response:', {
      total: response.total,
      returnedRows: response.data.length,
      page: response.pagination.page,
      totalPages: response.pagination.totalPages
    });

    res.json(response);
  } catch (error) {
    console.error('❌ [STOCKS] Error in screen endpoint:', error);
    return res.status(500).json({ 
      success: false,
      error: 'Database error', 
      details: error.message,
      stack: error.stack
    });
  }
});

module.exports = router;
