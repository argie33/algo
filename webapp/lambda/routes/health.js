const express = require('express');
const { query, initializeDatabase, getPool } = require('../utils/database');

const router = express.Router();

// Health check endpoint
router.get('/', async (req, res) => {
    // --- BEGIN: API endpoint health checks ---
    // Only run these if not a quick check
    const apiEndpoints = [
      { name: 'stocks', path: '/api/stocks' },
      { name: 'stocks_quick', path: '/api/stocks/quick/overview' },
      { name: 'market_overview', path: '/api/market/overview' },
      { name: 'market_sentiment', path: '/api/market/sentiment/history?days=1' },
      { name: 'market_sectors', path: '/api/market/sectors/performance' },
      { name: 'market_breadth', path: '/api/market/breadth' },
      { name: 'economic_indicators', path: '/api/market/economic?days=1' },
      { name: 'financials', path: '/api/financials/AAPL/income' },
      { name: 'metrics_valuation', path: '/api/metrics/valuation' },
      { name: 'metrics_growth', path: '/api/metrics/growth' },
      { name: 'metrics_dividends', path: '/api/metrics/dividends' },
      { name: 'metrics_financial_strength', path: '/api/metrics/financial-strength' },
      { name: 'earnings_estimates', path: '/api/earnings/estimates' },
      { name: 'earnings_history', path: '/api/earnings/history' },
      { name: 'stock_detail', path: '/api/stocks/AAPL' },
      { name: 'stock_profile', path: '/api/stocks/AAPL/profile' },
      { name: 'stock_metrics', path: '/api/stocks/AAPL/metrics' },
      { name: 'stock_financials_balance', path: '/api/financials/AAPL/balance' },
      { name: 'stock_financials_cashflow', path: '/api/financials/AAPL/cashflow' },
      { name: 'stock_prices', path: '/api/stocks/AAPL/prices?timeframe=daily&limit=1' },
      { name: 'stock_prices_recent', path: '/api/stocks/AAPL/price-recent?limit=1' },
      { name: 'stock_recommendations', path: '/api/stocks/AAPL/recommendations' },
      { name: 'sectors', path: '/api/stocks/filters/sectors' },
      { name: 'screen_stocks', path: '/api/stocks/screen' },
      { name: 'buy_signals', path: '/api/signals/buy' },
      { name: 'sell_signals', path: '/api/signals/sell' },
      { name: 'ticker_earnings_estimates', path: '/api/earnings/AAPL/estimates' },
      { name: 'ticker_earnings_history', path: '/api/earnings/AAPL/history' },
      { name: 'ticker_revenue_estimates', path: '/api/earnings/AAPL/revenue-estimates' }
    ];
    const apiResults = {};
    const fetch = require('node-fetch');
    const baseUrl = req.protocol + '://' + req.get('host');
    for (const endpoint of apiEndpoints) {
      try {
        const url = baseUrl + endpoint.path;
        const resp = await fetch(url, { method: 'GET', timeout: 4000 });
        apiResults[endpoint.name] = {
          status: resp.status,
          ok: resp.ok
        };
      } catch (err) {
        apiResults[endpoint.name] = {
          status: 'error',
          ok: false
        };
      }
    }
    // --- END: API endpoint health checks ---
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
        environment: process.env.NODE_ENV || 'development',
        endpoints: apiResults
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

// Comprehensive database health check endpoint (RESTORED health_status logic)
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
    // Query health_status table for summary
    let summary = {
      total_tables: 0,
      healthy_tables: 0,
      stale_tables: 0,
      empty_tables: 0,
      error_tables: 0,
      missing_tables: 0,
      total_records: 0,
      total_missing_data: 0
    };
    let tables = {};
    try {
      const result = await query('SELECT * FROM health_status');
      summary.total_tables = result.rowCount;
      for (const row of result.rows) {
        tables[row.table_name] = {
          status: row.status,
          record_count: row.record_count,
          missing_data_count: row.missing_data_count,
          last_updated: row.last_updated,
          last_checked: row.last_checked,
          is_stale: row.is_stale,
          error: row.error
        };
        summary.total_records += row.record_count || 0;
        summary.total_missing_data += row.missing_data_count || 0;
        if (row.status === 'healthy') summary.healthy_tables++;
        else if (row.status === 'stale') summary.stale_tables++;
        else if (row.status === 'empty') summary.empty_tables++;
        else if (row.status === 'error') summary.error_tables++;
        else if (row.status === 'missing') summary.missing_tables++;
      }
    } catch (err) {
      // If health_status table is missing or empty, return fallback
      console.error('Error querying health_status table:', err.message);
      return res.json({
        status: 'ok',
        healthy: true,
        timestamp: new Date().toISOString(),
        database: {
          status: 'connected',
          tables: {},
          summary: summary,
          note: 'health_status table is missing or empty'
        },
        api: { version: '1.0.0', environment: process.env.NODE_ENV || 'development' },
        memory: process.memoryUsage(),
        uptime: process.uptime()
      });
    }
    return res.json({
      status: 'ok',
      healthy: true,
      timestamp: new Date().toISOString(),
      database: {
        status: 'connected',
        tables: tables,
        summary: summary
      },
      api: { version: '1.0.0', environment: process.env.NODE_ENV || 'development' },
      memory: process.memoryUsage(),
      uptime: process.uptime()
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

module.exports = router;
