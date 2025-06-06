const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

router.get('/', async (req, res) => {
  try {
    // Test database connection
    const result = await query('SELECT NOW() as timestamp, version() as db_version');
    
    // Get basic table counts
    const tableChecks = await Promise.all([
      query('SELECT COUNT(*) as count FROM company_profile'),
      query('SELECT COUNT(*) as count FROM key_metrics'),
      query('SELECT COUNT(*) as count FROM market_data'),
      query('SELECT COUNT(*) as count FROM ttm_income_stmt'),
      query('SELECT COUNT(*) as count FROM ttm_cash_flow')
    ]);

    const health = {
      status: 'healthy',
      timestamp: result.rows[0].timestamp,
      database: {
        status: 'connected',
        version: result.rows[0].db_version.split(' ')[0],
        tables: {
          company_profile: parseInt(tableChecks[0].rows[0].count),
          key_metrics: parseInt(tableChecks[1].rows[0].count),
          market_data: parseInt(tableChecks[2].rows[0].count),
          ttm_income_stmt: parseInt(tableChecks[3].rows[0].count),
          ttm_cash_flow: parseInt(tableChecks[4].rows[0].count)
        }
      },
      api: {
        version: '1.0.0',
        environment: process.env.NODE_ENV || 'development'
      }
    };

    res.json(health);
  } catch (error) {
    console.error('Health check failed:', error);
    res.status(503).json({
      status: 'unhealthy',
      timestamp: new Date().toISOString(),
      error: error.message,
      database: {
        status: 'disconnected'
      }
    });
  }
});

module.exports = router;
