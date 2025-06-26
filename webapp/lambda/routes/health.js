/**
 * Robustness patch: Ensures all health endpoints always return valid JSON, never HTML or undefined.
 * - Defines HEALTH_TIMEOUT_MS to avoid ReferenceError.
 * - Adds global error handlers for unhandled promise rejections and uncaught exceptions.
 * - Adds Express error middleware to always return JSON.
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
    // Full health check with database
    console.log('Starting health check with database...');
    // Initialize database if not already done
    try {
      getPool(); // This will throw if not initialized
    } catch (initError) {
      console.log('Database not initialized, initializing now...');
      try {
        await initializeDatabase();
      } catch (dbInitError) {
        console.error('Failed to initialize database:', dbInitError.message);
        return res.status(503).json({
          status: 'unhealthy',
          healthy: false,
          service: 'Financial Dashboard API',
          timestamp: new Date().toISOString(),
          environment: process.env.NODE_ENV || 'development',
          database: {
            status: 'initialization_failed',
            error: dbInitError.message,
            lastAttempt: new Date().toISOString(),
            tables: {}
          },
          api: { version: '1.0.0', environment: process.env.NODE_ENV || 'development' },
          memory: process.memoryUsage(),
          uptime: process.uptime()
        });
      }
    }
    // Check if database error was passed from middleware
    if (req.dbError) {
      return res.status(503).json({
        status: 'unhealthy',
        healthy: false,
        service: 'Financial Dashboard API',
        timestamp: new Date().toISOString(),
        environment: process.env.NODE_ENV || 'development',
        database: {
          status: 'unavailable',
          error: req.dbError.message,
          lastAttempt: new Date().toISOString(),
          tables: {}
        },
        api: { version: '1.0.0', environment: process.env.NODE_ENV || 'development' },
        memory: process.memoryUsage(),
        uptime: process.uptime()
      });
    }
    // Test database connection with timeout and detailed error reporting
    const dbStart = Date.now();
    let result;
    try {
      result = await Promise.race([
        query('SELECT 1 as ok'),
        new Promise((_, reject) => setTimeout(() => reject(new Error('Database health check timeout')), 5000))
      ]);
    } catch (dbError) {
      // Enhanced error logging
      console.error('Database health check query failed:', dbError);
      return res.status(503).json({
        status: 'unhealthy',
        healthy: false,
        service: 'Financial Dashboard API',
        timestamp: new Date().toISOString(),
        environment: process.env.NODE_ENV || 'development',
        database: {
          status: 'disconnected',
          error: dbError.message,
          stack: dbError.stack,
          lastAttempt: new Date().toISOString(),
          tables: {}
        },
        api: { version: '1.0.0', environment: process.env.NODE_ENV || 'development' },
        memory: process.memoryUsage(),
        uptime: process.uptime()
      });
    }
    // Additional: test a real table if DB connection works
    try {
      await query('SELECT COUNT(*) FROM stock_symbols');
    } catch (tableError) {
      console.error('Table query failed:', tableError);
      return res.status(503).json({
        status: 'unhealthy',
        healthy: false,
        service: 'Financial Dashboard API',
        timestamp: new Date().toISOString(),
        environment: process.env.NODE_ENV || 'development',
        database: {
          status: 'connected_but_table_error',
          error: tableError.message,
          stack: tableError.stack,
          lastAttempt: new Date().toISOString(),
          tables: {}
        },
        api: { version: '1.0.0', environment: process.env.NODE_ENV || 'development' },
        memory: process.memoryUsage(),
        uptime: process.uptime()
      });
    }
    const dbTime = Date.now() - dbStart;
    // Get table information (check existence first) with global timeout
    let tables = {};
    try {
      const tableExistenceCheck = await Promise.race([
        query(`
          SELECT table_name 
          FROM information_schema.tables 
          WHERE table_schema = 'public' 
          AND table_name IN ('stock_symbols', 'fear_greed_index', 'naaim_exposure', 'technical_data_daily', 'earnings_estimates')
        `),
        new Promise((_, reject) => setTimeout(() => reject(new Error('Table existence check timeout')), 2000))
      ]);
      const existingTables = tableExistenceCheck.rows.map(row => row.table_name);
      if (existingTables.length > 0) {
        const countQueries = existingTables.map(tableName => 
          Promise.race([
            query(`SELECT COUNT(*) as count FROM ${tableName}`),
            new Promise((_, reject) => setTimeout(() => reject(new Error(`Count timeout for ${tableName}`)), 3000))
          ]).then(result => ({
            table: tableName,
            count: parseInt(result.rows[0].count)
          })).catch(err => ({
            table: tableName,
            count: null,
            error: err.message
          }))
        );
        const tableResults = await Promise.race([
          Promise.all(countQueries),
          new Promise((_, reject) => setTimeout(() => reject(new Error('Table count global timeout')), HEALTH_TIMEOUT_MS))
        ]);
        tableResults.forEach(result => {
          tables[result.table] = result.count !== null ? result.count : `Error: ${result.error}`;
        });
      }
      // Add missing tables as "not_found"
      ['stock_symbols', 'fear_greed_index', 'naaim_exposure', 'technical_data_daily', 'earnings_estimates'].forEach(tableName => {
        if (!existingTables.includes(tableName)) {
          tables[tableName] = 'not_found';
        }
      });
    } catch (tableError) {
      tables = { error: tableError.message };
    }
    const health = {
      status: 'healthy',
      healthy: true,
      timestamp: new Date().toISOString(),
      database: {
        status: 'connected',
        tables: tables
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
        tables: {}
      },
      api: { version: '1.0.0', environment: process.env.NODE_ENV || 'development' },
      memory: process.memoryUsage(),
      uptime: process.uptime()
    });
  }
});

// Comprehensive database health check endpoint
router.get('/database', async (req, res) => {
  console.log('Received request for /health/database');
  try {
    // Ensure database pool is initialized before running any queries
    try {
      getPool(); // Throws if not initialized
    } catch (initError) {
      console.log('Database not initialized, initializing now...');
      try {
        await initializeDatabase();
      } catch (dbInitError) {
        console.error('Failed to initialize database:', dbInitError.message);
        return res.status(503).json({
          status: 'unhealthy',
          healthy: false,
          service: 'Financial Dashboard API',
          timestamp: new Date().toISOString(),
          environment: process.env.NODE_ENV || 'development',
          database: {
            status: 'initialization_failed',
            error: dbInitError.message,
            lastAttempt: new Date().toISOString(),
            tables: {}
          },
          api: { version: '1.0.0', environment: process.env.NODE_ENV || 'development' },
          memory: process.memoryUsage(),
          uptime: process.uptime()
        });
      }
    }
    console.log('Database health check endpoint called');
    const results = {};
    const warnings = [];
    // Check all important tables
    const tables = [
      'technical_data_daily',
      'technical_data_weekly', 
      'technical_data_monthly',
      'stock_symbols',
      'fear_greed_index',
      'naaim_exposure',
      'balance_sheet',
      'ttm_income_stmt',
      'ttm_cashflow',
      'quarterly_balance_sheet',
      'quarterly_income_stmt',
      'quarterly_cashflow',
      'buy_sell_daily',
      'buy_sell_weekly',
      'buy_sell_monthly',
      'eps_revisions',
      'eps_trend',
      'earnings_estimate',
      'growth_estimates',
      'price_daily',
      'price_weekly',
      'price_monthly',
      'stock_symbols',
      'naaim_exposure',
      'fear_greed_index',
      'economic_data'
    ];
    for (const table of tables) {
      try {
        // Add timeout to each table check
        const tableExistsQuery = `
          SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = '${table}'
          );
        `;
        const tableExists = await Promise.race([
          query(tableExistsQuery),
          new Promise((_, reject) => setTimeout(() => reject(new Error(`Timeout checking existence of ${table}`)), 3000))
        ]);
        if (tableExists.rows[0].exists) {
          // Count total records with timeout
          const countQuery = `SELECT COUNT(*) as total FROM ${table}`;
          const countResult = await Promise.race([
            query(countQuery),
            new Promise((_, reject) => setTimeout(() => reject(new Error(`Timeout counting ${table}`)), 3000))
          ]);
          // Get last updated timestamp if available
          const columns = await query(`
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = '${table}' 
            AND column_name IN ('fetched_at', 'created_at', 'updated_at', 'date', 'period_end')
            ORDER BY 
              CASE column_name 
                WHEN 'fetched_at' THEN 1
                WHEN 'updated_at' THEN 2
                WHEN 'created_at' THEN 3
                WHEN 'date' THEN 4
                WHEN 'period_end' THEN 5
                ELSE 6
              END
            LIMIT 1
          `);
          let lastUpdate = null;
          if (columns.rows.length > 0) {
            const timestampColumn = columns.rows[0].column_name;
            const timestampQuery = `SELECT MAX(${timestampColumn}) as last_update FROM ${table}`;
            const timestampResult = await query(timestampQuery);
            lastUpdate = timestampResult.rows[0].last_update;
          }
          // Get table size
          let size = null;
          try {
            const sizeResult = await query(`
              SELECT pg_size_pretty(pg_total_relation_size('${table}')) as size
            `);
            size = sizeResult.rows[0].size;
          } catch (e) { size = null; }
          // Get index info
          let indexes = [];
          try {
            const indexResult = await query(`
              SELECT indexname, indexdef FROM pg_indexes WHERE tablename = '${table}'
            `);
            indexes = indexResult.rows;
          } catch (e) { indexes = []; }
          // Add warning for empty or stale tables
          if (parseInt(countResult.rows[0].total) === 0) {
            warnings.push(`${table} is empty`);
          } else if (lastUpdate) {
            const daysOld = (Date.now() - new Date(lastUpdate).getTime()) / (1000*60*60*24);
            if (daysOld > 30) {
              warnings.push(`${table} has not been updated in ${Math.round(daysOld)} days`);
            }
          }
          results[table] = {
            exists: true,
            totalRecords: parseInt(countResult.rows[0].total),
            lastUpdate: lastUpdate,
            size: size,
            indexes: indexes
          };
        } else {
          results[table] = {
            exists: false,
            totalRecords: 0,
            lastUpdate: null,
            size: null,
            indexes: []
          };
        }
      } catch (error) {
        results[table] = {
          exists: false,
          totalRecords: 0,
          lastUpdate: null,
          size: null,
          indexes: [],
          error: error.message
        };
      }
    }
    // Pool stats (if available)
    let poolStats = null;
    try {
      const { getPool } = require('../utils/database');
      const pool = getPool();
      poolStats = {
        totalCount: pool.totalCount,
        idleCount: pool.idleCount,
        waitingCount: pool.waitingCount
      };
    } catch (e) { poolStats = null; }
    // Overall health summary
    const totalTables = tables.length;
    const existingTables = Object.values(results).filter(r => r.exists).length;
    const tablesWithData = Object.values(results).filter(r => r.exists && r.totalRecords > 0).length;
    // Health summary section
    const healthSummary = {
      status: 'ok',
      timestamp: new Date().toISOString(),
      uptimeSeconds: process.uptime(),
      memory: process.memoryUsage(),
      environment: process.env.NODE_ENV || 'development',
      dbConnection: poolStats ? 'connected' : 'unknown',
      totalTables,
      existingTables,
      tablesWithData,
      healthPercentage: Math.round((tablesWithData / totalTables) * 100),
      warnings,
      poolStats
    };
    res.json({
      healthSummary,
      tables: results
    });
  } catch (error) {
    console.error('Error in database health check:', error);
    res.status(500).json({ 
      status: 'error',
      error: 'Health check failed', 
      message: error.message,
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
