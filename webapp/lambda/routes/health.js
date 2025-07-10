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

// Application readiness check - tests if database has tables
router.get('/ready', async (req, res) => {
  try {
    const { query } = require('../utils/database');
    
    // First check what tables actually exist
    const tablesResult = await query(`
      SELECT table_name 
      FROM information_schema.tables 
      WHERE table_schema = 'public' 
      AND table_type = 'BASE TABLE'
      ORDER BY table_name;
    `);
    
    const existingTables = tablesResult.rows.map(r => r.table_name);
    
    // Check critical webapp tables (not stock_symbols - that comes from data loading)
    const criticalWebappTables = ['last_updated', 'health_status'];
    const results = {};
    
    for (const table of criticalWebappTables) {
      if (existingTables.includes(table)) {
        try {
          const result = await query(`SELECT COUNT(*) as count FROM ${table} LIMIT 1`);
          results[table] = { 
            exists: true, 
            count: parseInt(result.rows[0].count),
            status: 'ready'
          };
        } catch (error) {
          results[table] = { 
            exists: true,
            error: error.message,
            status: 'error'
          };
        }
      } else {
        results[table] = { 
          exists: false,
          status: 'not_ready'
        };
      }
    }
    
    // Check if data loading tables exist (but don't fail if they don't)
    const dataLoadingTables = ['stock_symbols', 'company_profiles', 'prices'];
    const dataTablesInfo = {};
    
    for (const table of dataLoadingTables) {
      dataTablesInfo[table] = {
        exists: existingTables.includes(table),
        note: 'Created by data loading scripts'
      };
    }
    
    const webappTablesReady = Object.values(results).every(r => r.status === 'ready');
    
    return res.status(webappTablesReady ? 200 : 503).json({
      status: webappTablesReady ? 'ready' : 'not_ready',
      ready: webappTablesReady,
      service: 'Financial Dashboard API',
      timestamp: new Date().toISOString(),
      environment: process.env.ENVIRONMENT || 'dev',
      webapp_tables: results,
      data_loading_tables: dataTablesInfo,
      total_tables_found: existingTables.length,
      all_tables: existingTables,
      note: 'Webapp tables must be ready; data tables are optional'
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

// REMOVED: Emergency table creation endpoint - use proper IaC deployment instead

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