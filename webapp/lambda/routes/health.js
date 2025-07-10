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
    const tables = ['stock_symbols', 'stocks', 'last_updated'];
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

// Debug endpoint for raw database queries
router.get('/debug/db-test', async (req, res) => {
  try {
    const { query } = require('../utils/database');
    
    const result = await query(`
      SELECT 
        NOW() as current_time,
        current_database() as db_name,
        current_user as db_user,
        version() as db_version,
        inet_server_addr() as server_ip,
        inet_server_port() as server_port
    `);
    
    res.json({
      status: 'success',
      database_info: result.rows[0],
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('DB test failed:', error);
    res.status(500).json({
      status: 'error',
      error: error.message,
      code: error.code,
      timestamp: new Date().toISOString()
    });
  }
});

// Debug endpoint to list all tables in database
router.get('/debug/tables', async (req, res) => {
  try {
    const { query } = require('../utils/database');
    
    const result = await query(`
      SELECT 
        table_name,
        table_type,
        is_insertable_into
      FROM information_schema.tables 
      WHERE table_schema = 'public'
      ORDER BY table_name
    `);
    
    res.json({
      status: 'success',
      table_count: result.rows.length,
      tables: result.rows,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Tables list failed:', error);
    res.status(500).json({
      status: 'error',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Debug endpoint to test specific table queries
router.get('/debug/test-query', async (req, res) => {
  try {
    const { query } = require('../utils/database');
    const tableName = req.query.table || 'stock_symbols';
    
    // First check if table exists
    const tableCheck = await query(`
      SELECT COUNT(*) as exists 
      FROM information_schema.tables 
      WHERE table_schema = 'public' AND table_name = $1
    `, [tableName]);
    
    const tableExists = parseInt(tableCheck.rows[0].exists) > 0;
    
    let tableData = null;
    if (tableExists) {
      const data = await query(`SELECT COUNT(*) as record_count FROM "${tableName}"`);
      tableData = { record_count: parseInt(data.rows[0].record_count) };
    }
    
    res.json({
      status: 'success',
      table: tableName,
      exists: tableExists,
      data: tableData,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Test query failed:', error);
    res.status(500).json({
      status: 'error',
      table: req.query.table || 'stock_symbols',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Debug endpoint for environment and configuration
router.get('/debug/env', async (req, res) => {
  try {
    res.json({
      status: 'success',
      environment: {
        NODE_ENV: process.env.NODE_ENV,
        ENVIRONMENT: process.env.ENVIRONMENT,
        AWS_REGION: process.env.AWS_REGION,
        WEBAPP_AWS_REGION: process.env.WEBAPP_AWS_REGION,
        AWS_LAMBDA_FUNCTION_NAME: process.env.AWS_LAMBDA_FUNCTION_NAME,
        AWS_LAMBDA_FUNCTION_VERSION: process.env.AWS_LAMBDA_FUNCTION_VERSION
      },
      database_config: {
        DB_ENDPOINT: process.env.DB_ENDPOINT,
        DB_SECRET_ARN: process.env.DB_SECRET_ARN ? 'SET' : 'NOT_SET',
        DB_CONNECT_TIMEOUT: process.env.DB_CONNECT_TIMEOUT,
        DB_POOL_MAX: process.env.DB_POOL_MAX
      },
      lambda_info: {
        memory: process.memoryUsage(),
        uptime: process.uptime(),
        platform: process.platform,
        node_version: process.version
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    res.status(500).json({
      status: 'error',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Debug endpoint to test CORS
router.get('/debug/cors-test', async (req, res) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type');
  
  res.json({
    status: 'success',
    message: 'CORS test successful',
    headers: req.headers,
    origin: req.get('origin'),
    timestamp: new Date().toISOString()
  });
});

module.exports = router;