const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

// Health check endpoint for analyst data tables
router.get('/health', async (req, res) => {
  try {
    const tables = [
      'analyst_upgrade_downgrade',
      'analyst_recommendations', 
      'earnings_estimates',
      'revenue_estimates',
      'earnings_history'
    ];
    
    const status = {};
    
    for (const table of tables) {
      try {
        const result = await query(`SELECT COUNT(*) as count FROM ${table} LIMIT 1`);
        status[table] = {
          exists: true,
          count: result.rows[0]?.count || 0
        };
      } catch (error) {
        status[table] = {
          exists: false,
          error: error.message
        };
      }
    }
    
    res.json({
      status: 'OK',
      tables: status,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    res.status(500).json({
      status: 'ERROR',
      error: error.message
    });
  }
});

// Get analyst upgrades/downgrades
router.get('/upgrades', async (req, res) => {
  try {
    const page = parseInt(req.query.page) || 1;
    const limit = parseInt(req.query.limit) || 25;
    const offset = (page - 1) * limit;
    
    // Check if table exists first
    const tableCheckQuery = `
      SELECT COUNT(*) as count FROM analyst_upgrade_downgrade LIMIT 1
    `;
    
    let tableExists = true;
    try {
      await query(tableCheckQuery);
    } catch (tableError) {
      console.error('analyst_upgrade_downgrade table does not exist:', tableError.message);
      return res.status(404).json({ 
        error: 'Analyst upgrade/downgrade data not available',
        message: 'Data table not found'
      });
    }
    
    const upgradesQuery = `
      SELECT 
        symbol,
        company,
        from_grade,
        to_grade,
        action,
        firm,
        date
      FROM analyst_upgrade_downgrade 
      ORDER BY symbol ASC, date DESC
      LIMIT $1 OFFSET $2
    `;

    const countQuery = `
      SELECT COUNT(*) as total
      FROM analyst_upgrade_downgrade
    `;

    const [upgradesResult, countResult] = await Promise.all([
      query(upgradesQuery, [limit, offset]),
      query(countQuery)
    ]);

    const total = parseInt(countResult.rows[0].total);
    const totalPages = Math.ceil(total / limit);

    res.json({
      data: upgradesResult.rows,
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
    console.error('Error fetching analyst upgrades:', error);
    res.status(500).json({ error: 'Failed to fetch analyst upgrades' });
  }
});

// Get recommendations for specific stock
router.get('/:ticker/recommendations', async (req, res) => {
  try {
    const { ticker } = req.params;

    // Check if table exists first
    const tableCheckQuery = `
      SELECT COUNT(*) as count FROM analyst_recommendations LIMIT 1
    `;
    
    try {
      await query(tableCheckQuery);
    } catch (tableError) {
      console.error('analyst_recommendations table does not exist:', tableError.message);
      return res.status(404).json({ 
        error: 'Analyst recommendations data not available',
        message: 'Data table not found',
        ticker: ticker.toUpperCase()
      });
    }

    const recQuery = `
      SELECT 
        period,
        strong_buy,
        buy,
        hold,
        sell,
        strong_sell,
        collected_date
      FROM analyst_recommendations
      WHERE symbol = $1
      ORDER BY collected_date DESC
      LIMIT 12
    `;

    const result = await query(recQuery, [ticker.toUpperCase()]);

    if (result.rows.length === 0) {
      return res.status(404).json({
        error: 'No analyst recommendations found for this symbol',
        ticker: ticker.toUpperCase()
      });
    }

    res.json({
      ticker: ticker.toUpperCase(),
      recommendations: result.rows
    });

  } catch (error) {
    console.error('Error fetching recommendations:', error);
    res.status(500).json({ error: 'Failed to fetch recommendations' });
  }
});

// Get earnings estimates
router.get('/:ticker/earnings-estimates', async (req, res) => {
  try {
    const { ticker } = req.params;

    // Check if table exists first
    const tableCheckQuery = `
      SELECT COUNT(*) as count FROM earnings_estimates LIMIT 1
    `;
    
    try {
      await query(tableCheckQuery);
    } catch (tableError) {
      console.error('earnings_estimates table does not exist:', tableError.message);
      return res.status(404).json({ 
        error: 'Earnings estimates data not available',
        message: 'Data table not found',
        ticker: ticker.toUpperCase()
      });
    }

    const estimatesQuery = `
      SELECT 
        period,
        estimate,
        actual,
        difference,
        surprise_percent,
        reported_date
        FROM earnings_estimates
      WHERE symbol = $1
      ORDER BY reported_date DESC
      LIMIT 8
    `;

    const result = await query(estimatesQuery, [ticker.toUpperCase()]);

    res.json({
      ticker: ticker.toUpperCase(),
      estimates: result.rows
    });

  } catch (error) {
    console.error('Error fetching earnings estimates:', error);
    res.status(500).json({ error: 'Failed to fetch earnings estimates' });
  }
});

// Get revenue estimates
router.get('/:ticker/revenue-estimates', async (req, res) => {  try {
    const { ticker } = req.params;

    // Check if table exists first
    const tableCheckQuery = `
      SELECT COUNT(*) as count FROM revenue_estimates LIMIT 1
    `;
    
    try {
      await query(tableCheckQuery);
    } catch (tableError) {
      console.error('revenue_estimates table does not exist:', tableError.message);
      return res.status(404).json({ 
        error: 'Revenue estimates data not available',
        message: 'Data table not found',
        ticker: ticker.toUpperCase()
      });
    }

    const revenueQuery = `
      SELECT 
        period,
        estimate,
        actual,
        difference,
        surprise_percent,
        reported_date
      FROM revenue_estimates
      WHERE symbol = $1
      ORDER BY reported_date DESC
      LIMIT 8
    `;

    const result = await query(revenueQuery, [ticker.toUpperCase()]);

    res.json({
      ticker: ticker.toUpperCase(),
      estimates: result.rows
    });

  } catch (error) {
    console.error('Error fetching revenue estimates:', error);
    res.status(500).json({ error: 'Failed to fetch revenue estimates' });
  }
});

// Get earnings history
router.get('/:ticker/earnings-history', async (req, res) => {
  try {
    const { ticker } = req.params;

    // Check if table exists first
    const tableCheckQuery = `
      SELECT COUNT(*) as count FROM earnings_history LIMIT 1
    `;
    
    try {
      await query(tableCheckQuery);
    } catch (tableError) {
      console.error('earnings_history table does not exist:', tableError.message);
      return res.status(404).json({ 
        error: 'Earnings history data not available',
        message: 'Data table not found',
        ticker: ticker.toUpperCase()
      });
    }

    const historyQuery = `
      SELECT 
        quarter,
        estimate,
        actual,
        difference,
        surprise_percent,
        earnings_date
      FROM earnings_history
      WHERE symbol = $1
      ORDER BY earnings_date DESC
      LIMIT 12
    `;

    const result = await query(historyQuery, [ticker.toUpperCase()]);

    res.json({
      ticker: ticker.toUpperCase(),
      history: result.rows
    });

  } catch (error) {
    console.error('Error fetching earnings history:', error);
    res.status(500).json({ error: 'Failed to fetch earnings history' });
  }
});

module.exports = router;
