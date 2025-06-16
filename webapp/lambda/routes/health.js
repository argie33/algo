const express = require('express');
const { query, initializeDatabase, getPool } = require('../utils/database');

const router = express.Router();

router.get('/', async (req, res) => {
  try {
    // Basic health check without database (for quick status)
    // Use ?quick=true for fast health check without database queries
    if (req.query.quick === 'true') {
      return res.json({
        status: 'healthy',
        service: 'Financial Dashboard API',
        timestamp: new Date().toISOString(),
        environment: process.env.NODE_ENV || 'development',
        memory: process.memoryUsage(),
        uptime: process.uptime(),
        note: 'Quick health check - database not tested'
      });
    }// Full health check with database
    console.log('Starting health check with database...');
    
    // Initialize database if not already done
    try {
      getPool(); // This will throw if not initialized
    } catch (initError) {
      console.log('Database not initialized, initializing now...');
      await initializeDatabase();
    }
    
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
      // Get table information (check existence first)
    let tables = {};
    try {
      const tableExistenceCheck = await Promise.race([
        query(`
          SELECT table_name 
          FROM information_schema.tables 
          WHERE table_schema = 'public' 
          AND table_name IN ('company_profile', 'key_metrics', 'market_data', 'ttm_income_stmt', 'ttm_cash_flow')
        `),
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Table existence check timeout')), 2000)
        )
      ]);

      const existingTables = tableExistenceCheck.rows.map(row => row.table_name);
      
      // Only count tables that exist
      if (existingTables.length > 0) {
        const countQueries = existingTables.map(tableName => 
          query(`SELECT COUNT(*) as count FROM ${tableName}`).then(result => ({
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
          new Promise((_, reject) => 
            setTimeout(() => reject(new Error('Table count timeout')), 5000)
          )
        ]);

        // Build tables object
        tableResults.forEach(result => {
          tables[result.table] = result.count !== null ? result.count : `Error: ${result.error}`;
        });
      }

      // Add missing tables as "not_found"
      ['company_profile', 'key_metrics', 'market_data', 'ttm_income_stmt', 'ttm_cash_flow'].forEach(tableName => {
        if (!existingTables.includes(tableName)) {
          tables[tableName] = 'not_found';
        }
      });

    } catch (tableError) {
      console.log('Table check failed:', tableError.message);
      tables = { error: tableError.message };
    }

    const health = {
      status: 'healthy',
      timestamp: result.rows[0].timestamp,
      database: {
        status: 'connected',
        version: result.rows[0].db_version.split(' ')[0],
        tables: tables
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

// Comprehensive database health check endpoint
router.get('/database', async (req, res) => {
  try {
    console.log('Database health check endpoint called');
    
    const results = {};
    
    // Check all important tables
    const tables = [
      'technical_data_daily',
      'technical_data_weekly', 
      'technical_data_monthly',
      'company_profile',
      'market_data',
      'key_metrics',
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
      'stock_symbols',      'naaim_exposure',
      'fear_greed_index',
      'economic_data'
    ];
    
    for (const table of tables) {
      try {
        // Check if table exists
        const tableExistsQuery = `
          SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = '${table}'
          );
        `;
        
        const tableExists = await query(tableExistsQuery);
        
        if (tableExists.rows[0].exists) {
          // Count total records
          const countQuery = `SELECT COUNT(*) as total FROM ${table}`;
          const countResult = await query(countQuery);
          
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
          
          results[table] = {
            exists: true,
            totalRecords: parseInt(countResult.rows[0].total),
            lastUpdate: lastUpdate
          };
        } else {
          results[table] = {
            exists: false,
            totalRecords: 0,
            lastUpdate: null
          };
        }
        
      } catch (error) {
        results[table] = {
          exists: false,
          totalRecords: 0,
          lastUpdate: null,
          error: error.message
        };
      }
    }
    
    // Overall health summary
    const totalTables = tables.length;
    const existingTables = Object.values(results).filter(r => r.exists).length;
    const tablesWithData = Object.values(results).filter(r => r.exists && r.totalRecords > 0).length;
    
    res.json({
      status: 'ok',
      timestamp: new Date().toISOString(),
      summary: {
        totalTables,
        existingTables,
        tablesWithData,
        healthPercentage: Math.round((tablesWithData / totalTables) * 100)
      },
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

// Enhanced database diagnostics endpoint
router.get('/database/diagnostics', async (req, res) => {
  try {
    console.log('Database diagnostics endpoint called');
    
    // Get database connection info (similar to your Python scripts)
    const connectionInfo = {
      environment: process.env.NODE_ENV || 'unknown',
      dbEndpoint: process.env.DB_ENDPOINT ? 'SET' : 'NOT_SET',
      dbSecretArn: process.env.DB_SECRET_ARN ? 'SET' : 'NOT_SET',
      awsRegion: process.env.WEBAPP_AWS_REGION || 'unknown',
      timestamp: new Date().toISOString()
    };
    
    // Test basic database connectivity
    const connectivityTest = await query('SELECT NOW() as current_time, version() as postgres_version');
    
    // Get database size information
    const sizeQuery = `
      SELECT 
        pg_database.datname as database_name,
        pg_size_pretty(pg_database_size(pg_database.datname)) as size
      FROM pg_database 
      WHERE datname = current_database()
    `;
    const sizeResult = await query(sizeQuery);
    
    // Get table statistics
    const tableStatsQuery = `
      SELECT 
        schemaname,
        tablename,
        n_tup_ins as inserts,
        n_tup_upd as updates,
        n_tup_del as deletes,
        n_live_tup as live_tuples,
        n_dead_tup as dead_tuples,
        last_vacuum,
        last_autovacuum,
        last_analyze,
        last_autoanalyze
      FROM pg_stat_user_tables 
      WHERE schemaname = 'public'
      ORDER BY n_live_tup DESC
      LIMIT 10
    `;
    const tableStatsResult = await query(tableStatsQuery);
    
    // Get connection information
    const connectionQuery = `
      SELECT 
        count(*) as total_connections,
        count(*) FILTER (WHERE state = 'active') as active_connections,
        count(*) FILTER (WHERE state = 'idle') as idle_connections
      FROM pg_stat_activity
    `;
    const connectionResult = await query(connectionQuery);
    
    // Get recent activity
    const activityQuery = `
      SELECT 
        datname,
        usename,
        application_name,
        client_addr,
        state,
        query_start,
        state_change
      FROM pg_stat_activity 
      WHERE state != 'idle' 
      AND pid != pg_backend_pid()
      ORDER BY query_start DESC
      LIMIT 5
    `;
    const activityResult = await query(activityQuery);
    
    res.json({
      status: 'ok',
      connection: connectionInfo,
      connectivity: {
        successful: true,
        currentTime: connectivityTest.rows[0].current_time,
        postgresVersion: connectivityTest.rows[0].postgres_version
      },
      database: {
        size: sizeResult.rows[0],
        connections: connectionResult.rows[0],
        topTables: tableStatsResult.rows,
        recentActivity: activityResult.rows
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Error in database diagnostics:', error);
    res.status(500).json({ 
      status: 'error',
      error: 'Database diagnostics failed', 
      message: error.message,
      connection: {
        environment: process.env.NODE_ENV || 'unknown',
        dbEndpoint: process.env.DB_ENDPOINT ? 'SET' : 'NOT_SET',
        dbSecretArn: process.env.DB_SECRET_ARN ? 'SET' : 'NOT_SET',
        awsRegion: process.env.WEBAPP_AWS_REGION || 'unknown'
      },
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
