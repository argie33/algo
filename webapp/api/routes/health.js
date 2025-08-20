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
    // const _dbStart = Date.now();
    try {
      await Promise.race([
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
    // Get table information (check existence first) with global timeout
    let tables = {};
    try {
      const tableExistenceCheck = await Promise.race([
        query(`
          SELECT table_name 
          FROM information_schema.tables 
          WHERE table_schema = 'public' 
          AND table_name IN (
            'stock_symbols', 'etf_symbols', 'last_updated',
            'price_daily', 'price_weekly', 'price_monthly', 'etf_price_daily', 'etf_price_weekly', 'etf_price_monthly', 'price_data_montly',
            'technical_data_daily', 'technical_data_weekly', 'technical_data_monthly',
            'annual_balance_sheet', 'annual_income_statement', 'annual_cash_flow',
            'quarterly_balance_sheet', 'quarterly_income_statement', 'quarterly_cash_flow',
            'ttm_income_statement', 'ttm_cash_flow',
            'company_profile', 'market_data', 'key_metrics', 'analyst_estimates', 'governance_scores', 'leadership_team',
            'earnings_history', 'earnings_estimates', 'revenue_estimates', 'calendar_events', 'earnings_metrics',
            'fear_greed_index', 'aaii_sentiment', 'naaim', 'economic_data', 'analyst_upgrade_downgrade',
            'portfolio_holdings', 'portfolio_performance', 'trading_alerts',
            'buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly',
            'stock_news', 'stocks',
            'quality_metrics', 'value_metrics', 'stock_scores',
            'earnings_quality_metrics', 'balance_sheet_strength', 'profitability_metrics', 'management_effectiveness',
            'valuation_multiples', 'intrinsic_value_analysis', 'revenue_growth_analysis', 'earnings_growth_analysis',
            'price_momentum_analysis', 'technical_momentum_analysis', 'analyst_sentiment_analysis', 'social_sentiment_analysis',
            'institutional_positioning', 'insider_trading_analysis', 'score_performance_tracking', 'market_regime', 'stock_symbols_enhanced',
            'health_status', 'earnings', 'prices'
          )
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
          new Promise((_, reject) => setTimeout(() => reject(new Error('Table count global timeout')), 10000)) // 10 second timeout
        ]);
        tableResults.forEach(result => {
          tables[result.table] = result.count !== null ? result.count : `Error: ${result.error}`;
        });
      }
      // Add missing tables as "not_found" - comprehensive list
      [
        'stock_symbols', 'etf_symbols', 'last_updated',
        'price_daily', 'price_weekly', 'price_monthly', 'etf_price_daily', 'etf_price_weekly', 'etf_price_monthly', 'price_data_montly',
        'technical_data_daily', 'technical_data_weekly', 'technical_data_monthly',
        'annual_balance_sheet', 'annual_income_statement', 'annual_cash_flow',
        'quarterly_balance_sheet', 'quarterly_income_statement', 'quarterly_cash_flow',
        'ttm_income_statement', 'ttm_cash_flow',
        'company_profile', 'market_data', 'key_metrics', 'analyst_estimates', 'governance_scores', 'leadership_team',
        'earnings_history', 'earnings_estimates', 'revenue_estimates', 'calendar_events', 'earnings_metrics',
        'fear_greed_index', 'aaii_sentiment', 'naaim', 'economic_data', 'analyst_upgrade_downgrade',
        'portfolio_holdings', 'portfolio_performance', 'trading_alerts',
        'buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly',
        'stock_news', 'stocks',
        'quality_metrics', 'value_metrics', 'stock_scores',
        'earnings_quality_metrics', 'balance_sheet_strength', 'profitability_metrics', 'management_effectiveness',
        'valuation_multiples', 'intrinsic_value_analysis', 'revenue_growth_analysis', 'earnings_growth_analysis',
        'price_momentum_analysis', 'technical_momentum_analysis', 'analyst_sentiment_analysis', 'social_sentiment_analysis',
        'institutional_positioning', 'insider_trading_analysis', 'score_performance_tracking', 'market_regime', 'stock_symbols_enhanced',
        'health_status', 'earnings', 'prices'
      ].forEach(tableName => {
        if (!existingTables.includes(tableName)) {
          tables[tableName] = 'not_found';
        }
      });
    } catch (tableError) {
      tables = { error: tableError.message };
    }
    
    // Filter to only keep naaim table if it exists
    const filteredTables = {};
    if (tables.naaim !== undefined) {
      filteredTables.naaim = tables.naaim;
    }
    
    const health = {
      status: 'healthy',
      healthy: true,
      timestamp: new Date().toISOString(),
      database: {
        status: 'connected',
        tables: filteredTables
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

// Debug AWS Secrets Manager secret format
router.get('/debug-secret', async (req, res) => {
  try {
    const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
    
    const secretsManager = new SecretsManagerClient({
      region: process.env.AWS_REGION || 'us-east-1'
    });
    
    const secretArn = process.env.DB_SECRET_ARN;
    if (!secretArn) {
      return res.json({ error: 'DB_SECRET_ARN not set' });
    }
    
    const command = new GetSecretValueCommand({ SecretId: secretArn });
    const result = await secretsManager.send(command);
    
    const debugInfo = {
      secretType: typeof result.SecretString,
      secretLength: result.SecretString?.length,
      secretPreview: result.SecretString?.substring(0, 100),
      first5Chars: JSON.stringify(result.SecretString?.substring(0, 5)),
      isString: typeof result.SecretString === 'string',
      isObject: typeof result.SecretString === 'object',
      parseAttempt: null,
      parseError: null
    };
    
    if (typeof result.SecretString === 'string') {
      try {
        const parsed = JSON.parse(result.SecretString);
        debugInfo.parseAttempt = 'SUCCESS';
        debugInfo.parsedKeys = Object.keys(parsed);
      } catch (parseError) {
        debugInfo.parseAttempt = 'FAILED';
        debugInfo.parseError = parseError.message;
      }
    } else if (typeof result.SecretString === 'object' && result.SecretString !== null) {
      debugInfo.parseAttempt = 'OBJECT_ALREADY_PARSED';
      debugInfo.parsedKeys = Object.keys(result.SecretString);
    }
    
    res.json({
      status: 'debug',
      timestamp: new Date().toISOString(),
      debugInfo: debugInfo
    });
    
  } catch (error) {
    console.error('Error debugging secret:', error);
    res.status(500).json({ 
      status: 'error',
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

// Update health status for all tables - comprehensive monitoring
router.post('/update-status', async (req, res) => {
  console.log('Received request for /health/update-status');
  try {
    // Ensure database pool is initialized
    try {
      getPool();
    } catch (initError) {
      console.log('Health update: DB not initialized, initializing now...');
      try {
        await initializeDatabase();
      } catch (dbInitError) {
        console.error('Health update: Failed to initialize database:', dbInitError.message);
        return res.status(503).json({
          status: 'error',
          message: 'Failed to initialize database connection',
          error: dbInitError.message,
          timestamp: new Date().toISOString()
        });
      }
    }

    // Check if health_status table exists, create if not
    try {
      await query('SELECT 1 FROM health_status LIMIT 1');
    } catch (tableError) {
      console.log('Health_status table does not exist, creating it...');
      try {
        // Create the health_status table with all 52 tables
        await query(`
          CREATE TABLE IF NOT EXISTS health_status (
            table_name VARCHAR(255) PRIMARY KEY,
            status VARCHAR(50) NOT NULL DEFAULT 'unknown',
            record_count BIGINT DEFAULT 0,
            missing_data_count BIGINT DEFAULT 0,
            last_updated TIMESTAMP WITH TIME ZONE,
            last_checked TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            is_stale BOOLEAN DEFAULT FALSE,
            error TEXT,
            table_category VARCHAR(100),
            critical_table BOOLEAN DEFAULT FALSE,
            expected_update_frequency INTERVAL DEFAULT '1 day',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
          )
        `);

        // Insert all monitored tables - comprehensive list
        const monitoredTables = [
          // Core Tables (Stock Symbol Management)
          { name: 'stock_symbols', category: 'symbols', critical: true, frequency: '1 week' },
          { name: 'etf_symbols', category: 'symbols', critical: true, frequency: '1 week' },
          { name: 'last_updated', category: 'tracking', critical: true, frequency: '1 hour' },
          
          // Price & Market Data Tables
          { name: 'price_daily', category: 'prices', critical: true, frequency: '1 day' },
          { name: 'price_weekly', category: 'prices', critical: true, frequency: '1 week' },
          { name: 'price_monthly', category: 'prices', critical: true, frequency: '1 month' },
          { name: 'etf_price_daily', category: 'prices', critical: true, frequency: '1 day' },
          { name: 'etf_price_weekly', category: 'prices', critical: true, frequency: '1 week' },
          { name: 'etf_price_monthly', category: 'prices', critical: true, frequency: '1 month' },
          { name: 'price_data_montly', category: 'prices', critical: false, frequency: '1 month' }, // Test table with typo
          
          // Technical Analysis Tables (corrected names)
          { name: 'technical_data_daily', category: 'technicals', critical: true, frequency: '1 day' },
          { name: 'technical_data_weekly', category: 'technicals', critical: true, frequency: '1 week' },
          { name: 'technical_data_monthly', category: 'technicals', critical: true, frequency: '1 month' },
          
          // Financial Statement Tables (Annual)
          { name: 'annual_balance_sheet', category: 'financials', critical: false, frequency: '3 months' },
          { name: 'annual_income_statement', category: 'financials', critical: false, frequency: '3 months' },
          { name: 'annual_cash_flow', category: 'financials', critical: false, frequency: '3 months' }, // Fixed name
          
          // Financial Statement Tables (Quarterly)
          { name: 'quarterly_balance_sheet', category: 'financials', critical: true, frequency: '3 months' },
          { name: 'quarterly_income_statement', category: 'financials', critical: true, frequency: '3 months' },
          { name: 'quarterly_cash_flow', category: 'financials', critical: true, frequency: '3 months' }, // Fixed name
          
          // Financial Statement Tables (TTM)
          { name: 'ttm_income_statement', category: 'financials', critical: false, frequency: '3 months' },
          { name: 'ttm_cash_flow', category: 'financials', critical: false, frequency: '3 months' }, // Fixed name
          
          // Company Information Tables
          { name: 'company_profile', category: 'company', critical: true, frequency: '1 week' },
          { name: 'market_data', category: 'company', critical: true, frequency: '1 day' },
          { name: 'key_metrics', category: 'company', critical: true, frequency: '1 day' },
          { name: 'analyst_estimates', category: 'company', critical: false, frequency: '1 week' },
          { name: 'governance_scores', category: 'company', critical: false, frequency: '1 month' },
          { name: 'leadership_team', category: 'company', critical: false, frequency: '1 month' },
          
          // Earnings & Calendar Tables
          { name: 'earnings_history', category: 'earnings', critical: false, frequency: '1 day' },
          { name: 'earnings_estimates', category: 'earnings', critical: true, frequency: '1 day' }, // Fixed name
          { name: 'revenue_estimates', category: 'earnings', critical: false, frequency: '1 day' }, // Fixed name
          { name: 'calendar_events', category: 'earnings', critical: true, frequency: '1 day' },
          { name: 'earnings_metrics', category: 'earnings', critical: false, frequency: '1 day' }, // Added missing table
          
          // Market Sentiment & Economic Tables
          { name: 'fear_greed_index', category: 'sentiment', critical: true, frequency: '1 day' },
          { name: 'aaii_sentiment', category: 'sentiment', critical: false, frequency: '1 week' },
          { name: 'naaim', category: 'sentiment', critical: false, frequency: '1 week' },
          { name: 'economic_data', category: 'sentiment', critical: false, frequency: '1 day' },
          { name: 'analyst_upgrade_downgrade', category: 'sentiment', critical: false, frequency: '1 day' },
          
          // Trading & Portfolio Tables
          { name: 'portfolio_holdings', category: 'trading', critical: false, frequency: '1 hour' },
          { name: 'portfolio_performance', category: 'trading', critical: false, frequency: '1 hour' },
          { name: 'trading_alerts', category: 'trading', critical: false, frequency: '1 hour' },
          { name: 'buy_sell_daily', category: 'trading', critical: true, frequency: '1 day' },
          { name: 'buy_sell_weekly', category: 'trading', critical: true, frequency: '1 week' },
          { name: 'buy_sell_monthly', category: 'trading', critical: true, frequency: '1 month' },
          
          // News & Additional Data
          { name: 'stock_news', category: 'news', critical: false, frequency: '1 hour' }, // Fixed name
          { name: 'stocks', category: 'other', critical: false, frequency: '1 day' },
          
          // Quality & Value Metrics Tables
          { name: 'quality_metrics', category: 'scoring', critical: true, frequency: '1 day' },
          { name: 'value_metrics', category: 'scoring', critical: true, frequency: '1 day' },
          { name: 'growth_metrics', category: 'scoring', critical: true, frequency: '1 day' },
          
          // Advanced Scoring System Tables
          { name: 'stock_scores', category: 'scoring', critical: true, frequency: '1 day' },
          { name: 'earnings_quality_metrics', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'balance_sheet_strength', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'profitability_metrics', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'management_effectiveness', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'valuation_multiples', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'intrinsic_value_analysis', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'revenue_growth_analysis', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'earnings_growth_analysis', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'price_momentum_analysis', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'technical_momentum_analysis', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'analyst_sentiment_analysis', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'social_sentiment_analysis', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'institutional_positioning', category: 'scoring', critical: false, frequency: '1 week' },
          { name: 'insider_trading_analysis', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'score_performance_tracking', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'market_regime', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'stock_symbols_enhanced', category: 'scoring', critical: false, frequency: '1 week' },
          
          // System Health Monitoring
          { name: 'health_status', category: 'system', critical: true, frequency: '1 hour' },
          
          // Test Tables
          { name: 'earnings', category: 'test', critical: false, frequency: '1 day' },
          { name: 'prices', category: 'test', critical: false, frequency: '1 day' }
        ];

        for (const table of monitoredTables) {
          await query(`
            INSERT INTO health_status (table_name, table_category, critical_table, expected_update_frequency)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (table_name) DO NOTHING
          `, [table.name, table.category, table.critical, table.frequency]);
        }

        console.log(`Health_status table created and populated with ${monitoredTables.length} tables`);
      } catch (createError) {
        console.error('Failed to create health_status table:', createError.message);
        return res.status(500).json({
          status: 'error',
          message: 'Failed to create health_status table',
          error: createError.message,
          timestamp: new Date().toISOString()
        });
      }
    }

    // Perform comprehensive health check for all tables
    const startTime = Date.now();
    const healthResults = [];
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

    try {
      // Get list of tables to check
      const tablesToCheck = await query('SELECT table_name, expected_update_frequency FROM health_status');
      summary.total_tables = tablesToCheck.rowCount;

      for (const tableRow of tablesToCheck.rows) {
        const tableName = tableRow.table_name;
        let tableStatus = 'unknown';
        let recordCount = 0;
        let lastUpdated = null;
        let errorMsg = null;
        let isStale = false;

        try {
          // Check if table exists and get record count
          const countResult = await query(`
            SELECT COUNT(*) as count FROM information_schema.tables 
            WHERE table_name = $1 AND table_schema = 'public'
          `, [tableName]);

          if (countResult.rows[0].count === '0') {
            tableStatus = 'missing';
            summary.missing_tables++;
          } else {
            try {
              // Get record count
              const recordResult = await query(`SELECT COUNT(*) as count FROM "${tableName}"`);
              recordCount = parseInt(recordResult.rows[0].count);
              summary.total_records += recordCount;

              if (recordCount === 0) {
                tableStatus = 'empty';
                summary.empty_tables++;
              } else {
                // Try to get last updated timestamp
                const timestampColumns = ['fetched_at', 'updated_at', 'created_at', 'date', 'period_end', 'timestamp'];

                for (const col of timestampColumns) {
                  try {
                    const colCheck = await query(`
                      SELECT column_name FROM information_schema.columns 
                      WHERE table_name = $1 AND column_name = $2
                    `, [tableName, col]);

                    if (colCheck.rowCount > 0) {
                      const tsResult = await query(`SELECT MAX("${col}") as last_update FROM "${tableName}"`);
                      if (tsResult.rows[0].last_update) {
                        lastUpdated = tsResult.rows[0].last_update;
                        break;
                      }
                    }
                  } catch (tsError) {
                    // Continue to next column
                  }
                }

                // Determine if stale based on expected frequency
                if (lastUpdated && tableRow.expected_update_frequency) {
                  const expectedInterval = tableRow.expected_update_frequency;
                  
                  // Simple stale check - if last update is older than 2x expected frequency
                  const hoursSinceUpdate = (new Date() - new Date(lastUpdated)) / (1000 * 60 * 60);
                  const expectedHours = expectedInterval.includes('hour') ? 2 : 
                                       expectedInterval.includes('day') ? 48 : 
                                       expectedInterval.includes('week') ? 336 : 
                                       expectedInterval.includes('month') ? 1440 : 48;

                  if (hoursSinceUpdate > expectedHours) {
                    tableStatus = 'stale';
                    isStale = true;
                    summary.stale_tables++;
                  } else {
                    tableStatus = 'healthy';
                    summary.healthy_tables++;
                  }
                } else {
                  tableStatus = 'healthy';
                  summary.healthy_tables++;
                }
              }
            } catch (recordError) {
              tableStatus = 'error';
              errorMsg = recordError.message;
              summary.error_tables++;
            }
          }
        } catch (checkError) {
          tableStatus = 'error';
          errorMsg = checkError.message;
          summary.error_tables++;
        }

        // Update health status for this table
        try {
          await query(`
            INSERT INTO health_status (
              table_name, status, record_count, missing_data_count, 
              last_updated, last_checked, is_stale, error
            ) VALUES ($1, $2, $3, $4, $5, CURRENT_TIMESTAMP, $6, $7)
            ON CONFLICT (table_name) DO UPDATE SET
              status = EXCLUDED.status,
              record_count = EXCLUDED.record_count,
              missing_data_count = EXCLUDED.missing_data_count,
              last_updated = EXCLUDED.last_updated,
              last_checked = EXCLUDED.last_checked,
              is_stale = EXCLUDED.is_stale,
              error = EXCLUDED.error,
              updated_at = CURRENT_TIMESTAMP
          `, [tableName, tableStatus, recordCount, 0, lastUpdated, isStale, errorMsg]);
        } catch (updateError) {
          console.error(`Failed to update health status for table ${tableName}:`, updateError.message);
        }

        healthResults.push({
          table_name: tableName,
          status: tableStatus,
          record_count: recordCount,
          last_updated: lastUpdated,
          error: errorMsg
        });
      }
    } catch (overallError) {
      console.error('Error during comprehensive health check:', overallError.message);
      return res.status(500).json({
        status: 'error',
        message: 'Failed to perform comprehensive health check',
        error: overallError.message,
        timestamp: new Date().toISOString()
      });
    }

    const duration = Date.now() - startTime;

    return res.json({
      status: 'success',
      message: 'Health status updated successfully',
      timestamp: new Date().toISOString(),
      duration_ms: duration,
      summary: summary,
      tables_checked: summary.total_tables,
      results: healthResults
    });

  } catch (error) {
    console.error('Error in health status update:', error);
    res.status(500).json({
      status: 'error',
      message: 'Health status update failed',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get health status summary
router.get('/status-summary', async (req, res) => {
  try {
    // Ensure database is initialized
    try {
      getPool();
    } catch (initError) {
      await initializeDatabase();
    }

    // Get summary statistics
    const summaryResult = await query(`
      SELECT 
        table_category,
        COUNT(*) as total_tables,
        COUNT(CASE WHEN status = 'healthy' THEN 1 END) as healthy_tables,
        COUNT(CASE WHEN status = 'stale' THEN 1 END) as stale_tables,
        COUNT(CASE WHEN status = 'empty' THEN 1 END) as empty_tables,
        COUNT(CASE WHEN status = 'error' THEN 1 END) as error_tables,
        COUNT(CASE WHEN status = 'missing' THEN 1 END) as missing_tables,
        COUNT(CASE WHEN critical_table = true THEN 1 END) as critical_tables,
        SUM(record_count) as total_records,
        SUM(missing_data_count) as total_missing_data,
        MAX(last_updated) as latest_update,
        MIN(last_updated) as oldest_update
      FROM health_status
      GROUP BY table_category
      ORDER BY table_category
    `);

    const overallSummary = await query(`
      SELECT 
        COUNT(*) as total_tables,
        COUNT(CASE WHEN status = 'healthy' THEN 1 END) as healthy_tables,
        COUNT(CASE WHEN status = 'stale' THEN 1 END) as stale_tables,
        COUNT(CASE WHEN status = 'empty' THEN 1 END) as empty_tables,
        COUNT(CASE WHEN status = 'error' THEN 1 END) as error_tables,
        COUNT(CASE WHEN status = 'missing' THEN 1 END) as missing_tables,
        COUNT(CASE WHEN critical_table = true THEN 1 END) as critical_tables,
        SUM(record_count) as total_records,
        SUM(missing_data_count) as total_missing_data,
        MAX(last_checked) as last_health_check
      FROM health_status
    `);

    res.json({
      status: 'success',
      timestamp: new Date().toISOString(),
      overall: overallSummary.rows[0],
      by_category: summaryResult.rows
    });

  } catch (error) {
    console.error('Error getting health status summary:', error);
    res.status(500).json({
      status: 'error',
      message: 'Failed to get health status summary',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
