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

// Get stocks with filtering and pagination
router.get('/', async (req, res) => {
  const { page = 1, limit = 50, sector, market_cap_min, market_cap_max, volume_min, price_min, price_max } = req.query;

  try {
    const offset = (parseInt(page) - 1) * parseInt(limit);
    const maxLimit = Math.min(parseInt(limit), 200);

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

    // Market cap filters
    if (market_cap_min) {
      whereClause += ` AND market_cap >= $${paramIndex}`;
      params.push(parseFloat(market_cap_min));
      paramIndex++;
    }

    if (market_cap_max) {
      whereClause += ` AND market_cap <= $${paramIndex}`;
      params.push(parseFloat(market_cap_max));
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
        last_updated
      FROM stocks
      ${whereClause}
      ORDER BY market_cap DESC
      LIMIT $${paramIndex} OFFSET $${paramIndex + 1}
    `;

    const finalParams = [...params, maxLimit, offset];
    const dataResult = await query(dataQuery, finalParams);

    const totalPages = Math.ceil(total / maxLimit);

    res.json({
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
        filters: {
          sector: sector || null,
          market_cap_min: market_cap_min || null,
          market_cap_max: market_cap_max || null,
          volume_min: volume_min || null,
          price_min: price_min || null,
          price_max: price_max || null
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
