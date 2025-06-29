const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

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
      return res.status(404).json({ 
        error: 'Stocks table not found',
        message: 'Stocks data has not been loaded yet'
      });
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
    console.error('Error fetching stocks:', error);
    res.status(500).json({ error: 'Failed to fetch stocks' });
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
      return res.status(404).json({ 
        error: 'Stocks table not found',
        message: 'Stocks data has not been loaded yet'
      });
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
    console.error('Error fetching stock:', error);
    res.status(500).json({ error: 'Failed to fetch stock' });
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
      return res.status(404).json({ 
        error: 'Price data table not found',
        message: 'Price data has not been loaded yet'
      });
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
    console.error('Error fetching price history:', error);
    res.status(500).json({ error: 'Failed to fetch price history' });
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
      return res.json({
        data: [],
        count: 0
      });
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
    console.error('Error fetching sectors:', error);
    res.status(500).json({ error: 'Failed to fetch sectors' });
  }
});

module.exports = router;
