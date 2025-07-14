const express = require('express');
const { healthCheck, query } = require('../utils/database');

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

    // Full health check with comprehensive database table analysis
    const dbHealth = await getComprehensiveDbHealth();
    const isHealthy = dbHealth.status === 'connected';

    return res.status(isHealthy ? 200 : 503).json({
      status: isHealthy ? 'healthy' : 'unhealthy',
      healthy: isHealthy,
      service: 'Financial Dashboard API',
      timestamp: new Date().toISOString(),
      environment: process.env.ENVIRONMENT || 'dev',
      database: dbHealth.database, // Fix: Remove double nesting
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

// Debug endpoint to check table structure
router.get('/debug/table-structure', async (req, res) => {
  try {
    const { query } = require('../utils/database');
    const tableName = req.query.table || 'users';
    
    // Get table column information
    const result = await query(`
      SELECT 
        column_name,
        data_type,
        is_nullable,
        column_default,
        character_maximum_length
      FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = $1
      ORDER BY ordinal_position
    `, [tableName]);
    
    res.json({
      status: 'success',
      table: tableName,
      column_count: result.rows.length,
      columns: result.rows,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Table structure check failed:', error);
    res.status(500).json({
      status: 'error',
      table: req.query.table || 'users',
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

// Update health status endpoint - for "Update All Tables" button
router.post('/update-status', async (req, res) => {
  try {
    console.log('🔄 Health status update requested');
    
    // Get comprehensive database health
    const healthData = await getComprehensiveDbHealth();
    
    // Optionally store in health_status table if it exists
    try {
      // Check if health_status table exists
      const tableCheck = await query(`
        SELECT COUNT(*) as exists 
        FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'health_status'
      `);
      
      if (parseInt(tableCheck.rows[0].exists) > 0) {
        console.log('💾 Storing health data in health_status table...');
        
        // Store each table's health data
        for (const [tableName, tableData] of Object.entries(healthData.database.tables)) {
          await query(`
            INSERT INTO health_status (
              table_name, record_count, status, last_updated, 
              last_checked, critical_table, table_category, error_message
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (table_name) DO UPDATE SET
              record_count = EXCLUDED.record_count,
              status = EXCLUDED.status,
              last_updated = EXCLUDED.last_updated,
              last_checked = EXCLUDED.last_checked,
              critical_table = EXCLUDED.critical_table,
              table_category = EXCLUDED.table_category,
              error_message = EXCLUDED.error_message
          `, [
            tableName,
            tableData.record_count,
            tableData.status,
            tableData.last_updated,
            tableData.last_checked,
            tableData.critical_table,
            tableData.table_category,
            tableData.error
          ]);
        }
        
        console.log('✅ Health data stored in health_status table');
      } else {
        console.log('⚠️ health_status table does not exist - skipping storage');
      }
    } catch (storeError) {
      console.warn('⚠️ Failed to store health data in health_status table:', storeError.message);
      // Don't fail the whole request if storage fails
    }
    
    res.json({
      status: 'success',
      message: 'Database health status updated successfully',
      data: healthData,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Failed to update health status:', error);
    res.status(500).json({
      status: 'error',
      error: 'Failed to update health status',
      details: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * Comprehensive database health check that analyzes all tables
 * This is what the frontend ServiceHealth.jsx expects to receive
 */
async function getComprehensiveDbHealth() {
  try {
    console.log('🔍 Starting optimized database health check...');
    const startTime = Date.now();
    
    // First test basic connectivity
    const basicHealth = await healthCheck();
    if (basicHealth.status !== 'healthy') {
      return {
        status: 'disconnected',
        error: basicHealth.error,
        database: {
          status: 'error',
          tables: {},
          summary: {
            total_tables: 0,
            healthy_tables: 0,
            stale_tables: 0,
            error_tables: 0,
            empty_tables: 0,
            missing_tables: 0,
            total_records: 0,
            total_missing_data: 0
          }
        },
        timestamp: new Date().toISOString()
      };
    }
    
    // Define table categories and critical tables
    const tableCategorization = {
      'symbols': ['symbols', 'stock_symbols', 'etf_symbols'],
      'prices': ['price_daily', 'price_weekly', 'price_monthly', 'latest_prices'],
      'technicals': ['technicals_daily', 'technicals_weekly', 'technicals_monthly', 'latest_technicals'],
      'financials': ['balance_sheet', 'income_statement', 'cash_flow', 'key_metrics'],
      'company': ['company_profile', 'company_profiles'],
      'earnings': ['earnings_estimates', 'earnings_history', 'earnings_metrics'],
      'sentiment': ['fear_greed_index', 'naaim', 'aaii_sentiment'],
      'trading': ['buy_sell_daily', 'buy_sell_weekly', 'swing_trader', 'trade_executions'],
      'portfolio': ['portfolio_holdings', 'position_history', 'user_api_keys'],
      'system': ['health_status', 'last_updated']
    };
    
    const criticalTables = [
      'symbols', 'stock_symbols', 'price_daily', 'latest_prices', 
      'portfolio_holdings', 'user_api_keys', 'health_status', 'last_updated'
    ];
    
    // Function to categorize table
    function categorizeTable(tableName) {
      for (const [category, tables] of Object.entries(tableCategorization)) {
        if (tables.includes(tableName)) {
          return category;
        }
      }
      return 'other';
    }
    
    // OPTIMIZED: Get table info and record counts in one efficient query
    console.log('📋 Getting table info and record counts efficiently...');
    const batchQuery = `
      SELECT 
        t.table_name,
        t.table_type,
        COALESCE(s.n_tup_ins - s.n_tup_del, 0) as estimated_rows,
        s.last_vacuum,
        s.last_autovacuum,
        s.last_analyze,
        s.last_autoanalyze
      FROM information_schema.tables t
      LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name
      WHERE t.table_schema = 'public' 
      AND t.table_type = 'BASE TABLE'
      ORDER BY t.table_name
    `;
    
    const tablesResult = await query(batchQuery, [], 15000);
    const allTables = tablesResult.rows;
    console.log(`📋 Found ${allTables.length} tables in database`);
    
    // Build table health data efficiently
    const tableHealth = {};
    let totalRecords = 0;
    let healthyTables = 0;
    let staleTables = 0;
    let errorTables = 0;
    let emptyTables = 0;
    
    console.log('🔍 Processing table health data...');
    for (const table of allTables) {
      const tableName = table.table_name;
      const estimatedRows = parseInt(table.estimated_rows) || 0;
      totalRecords += estimatedRows;
      
      // Use pg_stat timestamps for freshness check
      const lastUpdated = table.last_analyze || table.last_autoanalyze || table.last_vacuum || table.last_autovacuum;
      
      // Determine table status
      let status = 'healthy';
      let isStale = false;
      
      if (estimatedRows === 0) {
        status = 'empty';
        emptyTables++;
      } else if (lastUpdated) {
        const hoursSinceUpdate = (new Date() - new Date(lastUpdated)) / (1000 * 60 * 60);
        if (hoursSinceUpdate > 72) { // 3 days
          status = 'stale';
          isStale = true;
          staleTables++;
        } else {
          healthyTables++;
        }
      } else {
        // No timestamp available, assume healthy if has data
        healthyTables++;
      }
      
      tableHealth[tableName] = {
        status: status,
        record_count: estimatedRows,
        last_updated: lastUpdated,
        last_checked: new Date().toISOString(),
        table_category: categorizeTable(tableName),
        critical_table: criticalTables.includes(tableName),
        is_stale: isStale,
        missing_data_count: 0,
        error: null,
        note: 'Using pg_stat estimated counts for performance'
      };
    }
    
    // Calculate summary statistics
    const summary = {
      total_tables: allTables.length,
      healthy_tables: healthyTables,
      stale_tables: staleTables,
      error_tables: errorTables,
      empty_tables: emptyTables,
      missing_tables: 0, // Tables we expect but don't exist
      total_records: totalRecords,
      total_missing_data: 0 // Could be enhanced
    };
    
    const duration = Date.now() - startTime;
    console.log(`✅ Comprehensive database health check completed in ${duration}ms`);
    console.log(`📊 Summary: ${summary.total_tables} tables, ${summary.healthy_tables} healthy, ${summary.total_records} total records`);
    
    return {
      status: 'connected',
      database: {
        status: 'connected',
        currentTime: basicHealth.timestamp,
        postgresVersion: basicHealth.version,
        tables: tableHealth,
        summary: summary
      },
      timestamp: new Date().toISOString(),
      note: `Analyzed ${allTables.length} database tables in ${duration}ms`
    };
    
  } catch (error) {
    console.error('❌ Comprehensive database health check failed:', error);
    return {
      status: 'error',
      error: error.message,
      database: {
        status: 'error',
        tables: {},
        summary: {
          total_tables: 0,
          healthy_tables: 0,
          stale_tables: 0,
          error_tables: 0,
          empty_tables: 0,
          missing_tables: 0,
          total_records: 0,
          total_missing_data: 0
        }
      },
      timestamp: new Date().toISOString()
    };
  }
}

// Create health_status table if it doesn't exist (for storing health data)
// REMOVED: Table creation endpoints - tables should be created by db-init infrastructure

module.exports = router;