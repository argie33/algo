const express = require('express');
const { query } = require('../utils/database');

const router = express.Router();

router.get('/', async (req, res) => {
  try {
    // Basic health check without database (for quick status)
    if (req.query.quick === 'true') {
      return res.json({
        status: 'healthy',
        service: 'Financial Dashboard API',
        timestamp: new Date().toISOString(),
        environment: process.env.NODE_ENV || 'development',
        memory: process.memoryUsage(),
        uptime: process.uptime()
      });
    }

    // Full health check with database
    console.log('Starting health check with database...');
    
    // Check if database error was passed from middleware
    if (req.dbError) {
      return res.status(503).json({
        status: 'degraded',
        service: 'Financial Dashboard API',
        timestamp: new Date().toISOString(),
        environment: process.env.NODE_ENV || 'development',
        database: {
          status: 'unavailable',
          error: req.dbError.message,
          lastAttempt: new Date().toISOString()
        },
        memory: process.memoryUsage(),
        uptime: process.uptime()
      });
    }
    
    // Test database connection with timeout
    const dbStart = Date.now();
    const result = await Promise.race([
      query('SELECT NOW() as timestamp, version() as db_version'),
      new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Database health check timeout')), 5000)
      )
    ]);
    const dbTime = Date.now() - dbStart;
    
    console.log(`Database connection test completed in ${dbTime}ms`);
    
    // Get basic table counts (with shorter timeout)
    const tableChecks = await Promise.race([
      Promise.all([
        query('SELECT COUNT(*) as count FROM company_profile'),
        query('SELECT COUNT(*) as count FROM key_metrics'), 
        query('SELECT COUNT(*) as count FROM market_data'),
        query('SELECT COUNT(*) as count FROM ttm_income_stmt'),
        query('SELECT COUNT(*) as count FROM ttm_cash_flow')
      ]),
      new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Table count timeout')), 3000)
      )
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
