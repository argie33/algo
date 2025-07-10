const express = require('express');
const { healthCheck } = require('../utils/database');

const router = express.Router();

// Infrastructure health check - tests database connectivity only
router.get('/', async (req, res) => {
  try {
    // Quick health check without database
    if (req.query.quick === 'true') {
      return res.json({
        status: 'healthy',
        healthy: true,
        service: 'Financial Dashboard API',
        timestamp: new Date().toISOString(),
        environment: process.env.ENVIRONMENT || 'dev',
        memory: process.memoryUsage(),
        uptime: process.uptime(),
        note: 'Quick infrastructure check - database not tested',
        database: { status: 'not_tested' },
        api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' },
        config: {
          hasDbSecret: !!process.env.DB_SECRET_ARN,
          hasDbEndpoint: !!process.env.DB_ENDPOINT,
          hasAwsRegion: !!process.env.AWS_REGION
        }
      });
    }

    // Full health check with database
    const dbHealth = await healthCheck();
    const isHealthy = dbHealth.status === 'healthy';

    return res.status(isHealthy ? 200 : 503).json({
      status: isHealthy ? 'healthy' : 'unhealthy',
      healthy: isHealthy,
      service: 'Financial Dashboard API',
      timestamp: new Date().toISOString(),
      environment: process.env.ENVIRONMENT || 'dev',
      database: dbHealth,
      api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' },
      memory: process.memoryUsage(),
      uptime: process.uptime()
    });

  } catch (error) {
    console.error('Health check failed:', error);
    res.status(503).json({
      status: 'unhealthy',
      healthy: false,
      timestamp: new Date().toISOString(),
      error: error.message,
      database: { status: 'error', error: error.message },
      api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' },
      memory: process.memoryUsage(),
      uptime: process.uptime()
    });
  }
});

// Application readiness check - tests if app tables exist and have data
router.get('/ready', async (req, res) => {
  try {
    const { query } = require('../utils/database');
    
    // Check if critical application tables exist
    const tables = ['stock_symbols'];
    const results = {};
    
    for (const table of tables) {
      try {
        const result = await query(`SELECT COUNT(*) as count FROM ${table} LIMIT 1`);
        results[table] = { 
          exists: true, 
          count: parseInt(result.rows[0].count),
          status: 'ready'
        };
      } catch (error) {
        results[table] = { 
          exists: false, 
          error: error.message,
          status: 'not_ready'
        };
      }
    }
    
    const allReady = Object.values(results).every(r => r.status === 'ready');
    
    return res.status(allReady ? 200 : 503).json({
      status: allReady ? 'ready' : 'not_ready',
      ready: allReady,
      service: 'Financial Dashboard API',
      timestamp: new Date().toISOString(),
      environment: process.env.ENVIRONMENT || 'dev',
      application_tables: results,
      note: 'Application readiness check - tests if app tables exist with data'
    });
    
  } catch (error) {
    console.error('Readiness check failed:', error);
    res.status(503).json({
      status: 'not_ready',
      ready: false,
      timestamp: new Date().toISOString(),
      error: error.message,
      note: 'Application readiness check failed'
    });
  }
});

// Quick fix endpoint to create missing stock_symbols table
router.post('/create-table', async (req, res) => {
  try {
    const { query } = require('../utils/database');
    
    await query(`
      CREATE TABLE IF NOT EXISTS stock_symbols (
        symbol VARCHAR(10) PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        type VARCHAR(50) DEFAULT 'stock',
        exchange VARCHAR(10),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      )
    `);
    
    // Insert a test record
    await query(`
      INSERT INTO stock_symbols (symbol, name, exchange) 
      VALUES ('AAPL', 'Apple Inc.', 'NASDAQ') 
      ON CONFLICT (symbol) DO NOTHING
    `);
    
    res.json({
      status: 'success',
      message: 'stock_symbols table created and test data inserted',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Table creation failed:', error);
    res.status(500).json({
      status: 'error',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;