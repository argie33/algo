const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Debug endpoint to check stocks tables status
router.get('/debug', async (req, res) => {
  try {
    console.log('Stocks debug endpoint called');
    
    const tables = ['company_profile', 'market_data', 'key_metrics'];
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
          } else {
            sampleQuery = `
              SELECT ticker, trailing_pe, forward_pe
              FROM ${table} 
              ORDER BY ticker 
              LIMIT 3
            `;
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
        ticker,
        short_name,
        sector,
        industry
      FROM company_profile
      ORDER BY ticker
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

// Get all stocks with basic info and pagination - simplified
router.get('/', async (req, res) => {
  try {
    console.log('Stocks endpoint called');
    
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;
    const search = req.query.search || '';
    const sector = req.query.sector || '';
    
    let whereClause = 'WHERE 1=1';
    const params = [];
    let paramCount = 0;

    if (search) {
      paramCount++;
      whereClause += ` AND (ticker ILIKE $${paramCount} OR short_name ILIKE $${paramCount})`;
      params.push(`%${search}%`);
    }

    if (sector) {
      paramCount++;
      whereClause += ` AND sector = $${paramCount}`;
      params.push(sector);
    }

    // Simple query without complex joins
    const stocksQuery = `
      SELECT 
        ticker,
        short_name,
        long_name,
        sector,
        industry,
        currency,
        exchange
      FROM company_profile
      ${whereClause}
      ORDER BY ticker ASC
      LIMIT $${paramCount + 1} OFFSET $${paramCount + 2}
    `;

    params.push(limit, offset);

    const countQuery = `
      SELECT COUNT(*) as total
      FROM company_profile
      ${whereClause}
    `;

    const [stocksResult, countResult] = await Promise.all([
      query(stocksQuery, params),
      query(countQuery, params.slice(0, -2)) // Remove limit and offset params
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    res.json({
      data: stocksResult.rows,
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
    console.error('Error fetching stocks:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stocks',
      message: error.message 
    });
  }
});

// Get stock details by ticker
router.get('/:ticker', async (req, res) => {
  try {
    const { ticker } = req.params;
    
    const stockQuery = `
      SELECT 
        ticker,
        short_name,
        long_name,
        sector,
        industry,
        currency,
        exchange,
        website,
        description
      FROM company_profile
      WHERE ticker = $1
    `;

    const result = await query(stockQuery, [ticker.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({ 
        error: 'Stock not found',
        ticker: ticker.toUpperCase()
      });
    }

    res.json({
      ticker: ticker.toUpperCase(),
      data: result.rows[0]
    });

  } catch (error) {
    console.error('Error fetching stock details:', error);
    res.status(500).json({ 
      error: 'Failed to fetch stock details',
      message: error.message 
    });
  }
});

// Get available sectors
router.get('/sectors/list', async (req, res) => {
  try {
    const sectorsQuery = `
      SELECT DISTINCT sector
      FROM company_profile
      WHERE sector IS NOT NULL AND sector != ''
      ORDER BY sector
    `;

    const result = await query(sectorsQuery);

    res.json({
      sectors: result.rows.map(row => row.sector)
    });

  } catch (error) {
    console.error('Error fetching sectors:', error);
    res.status(500).json({ 
      error: 'Failed to fetch sectors',
      message: error.message 
    });
  }
});

module.exports = router;
