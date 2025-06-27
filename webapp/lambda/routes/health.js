/**
 * Robustness patch: Ensures all health endpoints always return valid JSON, never HTML or undefined.
 * - Defines HEALTH_TIMEOUT_MS to avoid ReferenceError.
 * - Adds global error handlers for unhandled promise rejections and uncaught exceptions.
 * - Adds Express error middleware to always return JSON.
 * - Uses cached health status table to avoid expensive COUNT queries.
 */
const HEALTH_TIMEOUT_MS = 5000; // 5 seconds default for all health timeouts

process.on('unhandledRejection', (reason, promise) => {
  console.error('Unhandled Rejection at:', promise, 'reason:', reason);
});
process.on('uncaughtException', (err) => {
  console.error('Uncaught Exception thrown:', err);
});

const express = require('express');
const { query, initializeDatabase, getPool } = require('../utils/database');

const router = express.Router();

// Health check endpoint
router.get('/', async (req, res) => {
  try {
    // Basic health check without database (for quick status)
    if (req.query.quick === 'true') {
      return res.json({
        status: 'healthy',
        healthy: true,
        service: 'Financial Dashboard API',
        timestamp: new Date().toISOString(),
        environment: process.env.NODE_ENV || 'development',
        memory: process.memoryUsage(),
        uptime: process.uptime(),
        note: 'Quick health check - database not tested',
        database: { status: 'not_tested' },
        api: { version: '1.0.0', environment: process.env.NODE_ENV || 'development' }
      });
    }
    
    // Full health check with simple database test
    console.log('Starting health check with database...');
    
    // Simple database connection test - just like other working APIs
    const result = await query('SELECT NOW() as current_time');
    
    const health = {
      status: 'healthy',
      healthy: true,
      timestamp: new Date().toISOString(),
      database: {
        status: 'connected',
        currentTime: result.rows[0].current_time
      },
      api: {
        version: '1.0.0',
        environment: process.env.NODE_ENV || 'development'
      },
      memory: process.memoryUsage(),
      uptime: process.uptime()
    };
    
    res.json(health);
    
  } catch (error) {
    console.error('Health check failed:', error);
    res.status(503).json({
      status: 'unhealthy',
      healthy: false,
      timestamp: new Date().toISOString(),
      error: error.message,
      database: {
        status: 'disconnected',
        error: error.message
      },
      api: { version: '1.0.0', environment: process.env.NODE_ENV || 'development' },
      memory: process.memoryUsage(),
      uptime: process.uptime()
    });
  }
});

// Cached database health check endpoint - reads from health_status table
router.get('/database', async (req, res) => {
  console.log('Received request for /health/database');
  
  try {
    // First, ensure the health_status table exists
    await query(`
      CREATE TABLE IF NOT EXISTS health_status (
        id SERIAL PRIMARY KEY,
        table_name VARCHAR(100) NOT NULL,
        record_count BIGINT,
        status VARCHAR(20) NOT NULL,
        last_checked TIMESTAMP NOT NULL DEFAULT NOW(),
        error_message TEXT,
        UNIQUE(table_name)
      );
    `);
    
    // Get cached health status
    const healthResult = await query(`
      SELECT 
        table_name, 
        record_count, 
        status, 
        last_checked, 
        error_message
      FROM health_status 
      ORDER BY table_name;
    `);
    
    // Get current database time
    const dbTimeResult = await query('SELECT NOW() as current_time, version() as postgres_version');
    
    const tableStats = {};
    healthResult.rows.forEach(row => {
      tableStats[row.table_name] = {
        record_count: row.record_count,
        status: row.status,
        last_checked: row.last_checked,
        error: row.error_message
      };
    });
    
    res.json({
      status: 'healthy',
      timestamp: new Date().toISOString(),
      database: {
        status: 'connected',
        currentTime: dbTimeResult.rows[0].current_time,
        postgresVersion: dbTimeResult.rows[0].postgres_version,
        tables: tableStats,
        note: 'Data from cached health status table - run /health/update-status to refresh'
      }
    });
    
  } catch (error) {
    console.error('Database health check failed:', error);
    res.status(503).json({
      status: 'unhealthy',
      timestamp: new Date().toISOString(),
      database: {
        status: 'disconnected',
        error: error.message
      }
    });
  }
});

// Background job to update health status table
router.post('/update-status', async (req, res) => {
  console.log('Received request to update health status');
  
  try {
    // Ensure the health_status table exists
    await query(`
      CREATE TABLE IF NOT EXISTS health_status (
        id SERIAL PRIMARY KEY,
        table_name VARCHAR(100) NOT NULL,
        record_count BIGINT,
        status VARCHAR(20) NOT NULL,
        last_checked TIMESTAMP NOT NULL DEFAULT NOW(),
        error_message TEXT,
        UNIQUE(table_name)
      );
    `);
    
    const expectedTables = [
      'stock_symbols', 'etf_symbols', 'last_updated',
      'fear_greed_index', 'naaim_exposure', 'aaii_sentiment',
      'analyst_upgrade_downgrade', 'calendar_events',
      'earnings_estimates', 'earnings_history', 'revenue_estimates',
      'economic_data', 'company_profile', 'leadership_team',
      'governance_scores', 'market_data', 'key_metrics', 'analyst_estimates',
      'price_daily', 'price_weekly', 'price_monthly',
      'etf_price_daily', 'etf_price_weekly', 'etf_price_monthly',
      'technical_data_daily', 'technical_data_weekly', 'technical_data_monthly',
      'buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly',
      'balance_sheet_annual', 'balance_sheet_quarterly', 'balance_sheet_ttm',
      'income_statement_annual', 'income_statement_quarterly', 'income_statement_ttm',
      'cash_flow_annual', 'cash_flow_quarterly', 'cash_flow_ttm',
      'financials', 'financials_quarterly', 'financials_ttm'
    ];
    
    let processed = 0;
    let errors = 0;
    
    for (const tableName of expectedTables) {
      try {
        // Check if table exists
        const tableExists = await query(`
          SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = $1
          );
        `, [tableName]);
        
        if (tableExists.rows[0].exists) {
          // Table exists, get count
          const countResult = await query(`SELECT COUNT(*) as count FROM ${tableName}`);
          const recordCount = parseInt(countResult.rows[0].count);
          
          // Update or insert health status
          await query(`
            INSERT INTO health_status (table_name, record_count, status, last_checked)
            VALUES ($1, $2, 'healthy', NOW())
            ON CONFLICT (table_name) DO UPDATE SET
              record_count = EXCLUDED.record_count,
              status = EXCLUDED.status,
              last_checked = EXCLUDED.last_checked,
              error_message = NULL;
          `, [tableName, recordCount]);
        } else {
          // Table doesn't exist
          await query(`
            INSERT INTO health_status (table_name, record_count, status, last_checked, error_message)
            VALUES ($1, NULL, 'not_found', NOW(), 'Table does not exist')
            ON CONFLICT (table_name) DO UPDATE SET
              record_count = NULL,
              status = EXCLUDED.status,
              last_checked = EXCLUDED.last_checked,
              error_message = EXCLUDED.error_message;
          `, [tableName]);
        }
        
        processed++;
      } catch (error) {
        console.error(`Error processing table ${tableName}:`, error);
        
        // Record error in health status
        await query(`
          INSERT INTO health_status (table_name, record_count, status, last_checked, error_message)
          VALUES ($1, NULL, 'error', NOW(), $2)
          ON CONFLICT (table_name) DO UPDATE SET
            record_count = NULL,
            status = EXCLUDED.status,
            last_checked = EXCLUDED.last_checked,
            error_message = EXCLUDED.error_message;
        `, [tableName, error.message]);
        
        errors++;
      }
    }
    
    res.json({
      status: 'success',
      message: 'Health status updated',
      processed,
      errors,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Failed to update health status:', error);
    res.status(500).json({
      status: 'error',
      message: 'Failed to update health status',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Test database connection
router.get('/test-connection', async (req, res) => {
  try {
    const result = await query('SELECT NOW() as current_time, version() as postgres_version');
    
    res.json({
      status: 'ok',
      connection: 'successful',
      currentTime: result.rows[0].current_time,
      postgresVersion: result.rows[0].postgres_version,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error testing database connection:', error);
    res.status(500).json({ 
      status: 'error',
      connection: 'failed',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Enhanced comprehensive database diagnostics endpoint
router.get('/database/diagnostics', async (req, res) => {
  console.log('Received request for /health/database/diagnostics');
  // Ensure DB pool is initialized (like in /stocks and main health check)
  try {
    try {
      getPool(); // Throws if not initialized
    } catch (initError) {
      console.log('Diagnostics: DB not initialized, initializing now...');
      try {
        await initializeDatabase();
      } catch (dbInitError) {
        console.error('Diagnostics: Failed to initialize database:', dbInitError.message);
        return res.status(503).json({
          status: 'error',
          diagnostics: { connection: { status: 'initialization_failed', error: dbInitError.message } },
          message: 'Failed to initialize database connection',
          timestamp: new Date().toISOString()
        });
      }
    }
    // Now proceed with diagnostics as before
  } catch (fatalInitError) {
    return res.status(503).json({
      status: 'error',
      diagnostics: { connection: { status: 'fatal_init_error', error: fatalInitError.message } },
      message: 'Fatal error initializing database connection',
      timestamp: new Date().toISOString()
    });
  }
  const diagnostics = {
    timestamp: new Date().toISOString(),
    environment: {
      NODE_ENV: process.env.NODE_ENV,
      DB_SECRET_ARN: process.env.DB_SECRET_ARN ? 'SET' : 'NOT_SET',
      DB_ENDPOINT: process.env.DB_ENDPOINT ? 'SET' : 'NOT_SET',
      WEBAPP_AWS_REGION: process.env.WEBAPP_AWS_REGION,
      AWS_REGION: process.env.AWS_REGION,
      IS_LOCAL: process.env.NODE_ENV === 'development' || !process.env.DB_SECRET_ARN,
      RUNTIME: 'AWS Lambda Node.js'
    },
    connection: {
      status: 'unknown',
      method: 'unknown',
      details: {},
      durationMs: null
    },
    database: {
      name: 'unknown',
      version: 'unknown',
      host: 'unknown',
      schemas: []
    },
    tables: {
      total: 0,
      withData: 0,
      list: [],
      errors: [],
      durationMs: null
    },
    errors: [],
    recommendations: []
  };
  let overallStatus = 'healthy';
  try {
    // Connection step
    let connectionTest, connectStart = Date.now();
    try {
      connectionTest = await query('SELECT NOW() as current_time, version() as postgres_version, current_database() as db_name');
      diagnostics.connection.durationMs = Date.now() - connectStart;
      if (connectionTest.rows.length > 0) {
        const row = connectionTest.rows[0];
        diagnostics.connection.status = 'connected';
        diagnostics.connection.method = process.env.DB_SECRET_ARN ? 'AWS Secrets Manager' : 'Environment Variables';
        diagnostics.connection.details = { connectedAt: row.current_time };
        diagnostics.database.name = row.db_name;
        diagnostics.database.version = row.postgres_version;
      } else {
        diagnostics.connection.status = 'connected_no_data';
        diagnostics.connection.details = { error: 'Connected but no data returned' };
        overallStatus = 'degraded';
        diagnostics.recommendations.push('Database connection established but no data returned. Check DB user permissions and schema.');
      }
    } catch (err) {
      diagnostics.connection.status = 'failed';
      diagnostics.connection.details = { error: err.message };
      diagnostics.errors.push({ step: 'connection', error: err.message });
      overallStatus = 'unhealthy';
      diagnostics.recommendations.push('Database connection failed. Check credentials, network, and DB status.');
      return res.status(500).json({ status: 'error', overallStatus, diagnostics, summary: {
        environment: diagnostics.environment.NODE_ENV || 'unknown',
        database: diagnostics.database.name,
        connection: diagnostics.connection.status,
        tablesWithData: `${diagnostics.tables.withData}/${diagnostics.tables.total}`,
        errors: diagnostics.errors.concat(diagnostics.tables.errors),
        recommendations: diagnostics.recommendations
      }});
    }
    // Host info
    try {
      const hostInfo = await query("SELECT inet_server_addr() as host, inet_server_port() as port");
      if (hostInfo.rows.length > 0) {
        diagnostics.database.host = hostInfo.rows[0].host || 'localhost';
        diagnostics.database.port = hostInfo.rows[0].port || 5432;
      }
    } catch (e) {
      diagnostics.errors.push({ step: 'host', error: e.message });
    }
    // Schemas
    try {
      const schemas = await query("SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT LIKE 'pg_%' AND schema_name != 'information_schema'");
      diagnostics.database.schemas = schemas.rows.map(r => r.schema_name);
    } catch (e) {
      diagnostics.errors.push({ step: 'schemas', error: e.message });
    }
    // Table info and record counts
    let tables = [], tableStart = Date.now();
    try {
      const tablesResult = await query(`
        SELECT 
          t.table_name,
          (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name) as column_count,
          pg_size_pretty(pg_total_relation_size(c.oid)) as size
        FROM information_schema.tables t
        LEFT JOIN pg_class c ON c.relname = t.table_name
        WHERE t.table_schema = 'public' 
        AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_name
      `);
      tables = tablesResult.rows;
      diagnostics.tables.total = tables.length;
      let tablesWithData = 0;
      for (const table of tables) {
        try {
          const count = await query(`SELECT COUNT(*) as count FROM ${table.table_name}`);
          const recordCount = parseInt(count.rows[0].count);
          table.record_count = recordCount;
          // Try to get last updated timestamp
          let lastUpdate = null;
          try {
            const tsCol = await query(`SELECT column_name FROM information_schema.columns WHERE table_name = '${table.table_name}' AND column_name IN ('fetched_at','updated_at','created_at','date','period_end') LIMIT 1`);
            if (tsCol.rows.length > 0) {
              const col = tsCol.rows[0].column_name;
              const tsRes = await query(`SELECT MAX(${col}) as last_update FROM ${table.table_name}`);
              lastUpdate = tsRes.rows[0].last_update;
            }
          } catch (e) { /* ignore */ }
          table.last_update = lastUpdate;
          if (recordCount > 0) tablesWithData++;
        } catch (e) {
          table.record_count = null;
          diagnostics.tables.errors.push({ table: table.table_name, error: e.message });
        }
      }
      diagnostics.tables.withData = tablesWithData;
      diagnostics.tables.list = tables;
      diagnostics.tables.durationMs = Date.now() - tableStart;
      if (tablesWithData === 0) {
        overallStatus = 'degraded';
        diagnostics.recommendations.push('No tables have data. Check ETL/loader jobs and DB population.');
      } else if (tablesWithData < tables.length) {
        overallStatus = 'degraded';
        diagnostics.recommendations.push('Some tables are empty. Review loader jobs and data sources.');
      }
    } catch (e) {
      diagnostics.errors.push({ step: 'tables', error: e.message });
      overallStatus = 'degraded';
      diagnostics.recommendations.push('Failed to fetch table info. Check DB permissions and schema.');
    }
    // Final summary
    if (diagnostics.errors.length > 0 || diagnostics.tables.errors.length > 0) {
      overallStatus = 'degraded';
    }
    res.json({
      status: diagnostics.connection.status === 'connected' ? 'ok' : 'error',
      overallStatus,
      diagnostics,
      summary: {
        environment: diagnostics.environment.NODE_ENV || 'unknown',
        database: diagnostics.database.name,
        connection: diagnostics.connection.status,
        tablesWithData: `${diagnostics.tables.withData}/${diagnostics.tables.total}`,
        errors: diagnostics.errors.concat(diagnostics.tables.errors),
        recommendations: diagnostics.recommendations
      }
    });
  } catch (error) {
    diagnostics.errors.push({ step: 'fatal', error: error.message });
    overallStatus = 'unhealthy';
    diagnostics.recommendations.push('Fatal error in diagnostics. Check backend logs.');
    res.status(500).json({ status: 'error', overallStatus, diagnostics, summary: {
      environment: diagnostics.environment.NODE_ENV || 'unknown',
      database: diagnostics.database.name,
      connection: diagnostics.connection.status,
      tablesWithData: `${diagnostics.tables.withData}/${diagnostics.tables.total}`,
      errors: diagnostics.errors.concat(diagnostics.tables.errors),
      recommendations: diagnostics.recommendations
    }});
  }
});

// Minimal DB test endpoint for debugging
router.get('/db-test', async (req, res) => {
  console.log('Received request for /health/db-test');
  try {
    const result = await query('SELECT 1 as ok');
    res.json({ ok: true, result: result.rows });
  } catch (e) {
    res.status(500).json({ ok: false, error: e.message });
  }
});

// Express error-handling middleware to always return JSON
router.use((err, req, res, next) => {
  console.error('Express error handler:', err);
  if (res.headersSent) return next(err);
  res.status(500).json({
    status: 'error',
    error: err.message || 'Internal server error',
    stack: process.env.NODE_ENV === 'development' ? err.stack : undefined,
    timestamp: new Date().toISOString()
  });
});

module.exports = router;
