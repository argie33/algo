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
      });    }// Full health check with database
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
          status: 'degraded',
          service: 'Financial Dashboard API',
          timestamp: new Date().toISOString(),
          environment: process.env.NODE_ENV || 'development',
          database: {
            status: 'initialization_failed',
            error: dbInitError.message,
            lastAttempt: new Date().toISOString()
          },
          memory: process.memoryUsage(),
          uptime: process.uptime()
        });
      }
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

// Comprehensive database diagnostics endpoint using Secrets Manager
router.get('/database/diagnostics', async (req, res) => {
  try {
    console.log('Database diagnostics endpoint called');
    
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
        details: {}
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
        list: []
      }
    };

    try {
      // Test basic connection
      const connectionTest = await query('SELECT NOW() as current_time, version() as postgres_version, current_database() as db_name');
      
      if (connectionTest.rows.length > 0) {
        const row = connectionTest.rows[0];
        diagnostics.connection.status = 'connected';
        diagnostics.connection.method = process.env.DB_SECRET_ARN ? 'AWS Secrets Manager' : 'Environment Variables';
        diagnostics.connection.details = {
          connectedAt: row.current_time,
          connectionMethod: diagnostics.connection.method
        };
        
        diagnostics.database.name = row.db_name;
        diagnostics.database.version = row.postgres_version;
        
        // Get host info if available
        try {
          const hostInfo = await query("SELECT inet_server_addr() as host, inet_server_port() as port");
          if (hostInfo.rows.length > 0) {
            diagnostics.database.host = hostInfo.rows[0].host || 'localhost';
            diagnostics.database.port = hostInfo.rows[0].port || 5432;
          }
        } catch (e) {
          console.log('Could not get host info:', e.message);
        }

        // Get schemas
        try {
          const schemas = await query("SELECT schema_name FROM information_schema.schemata WHERE schema_name NOT LIKE 'pg_%' AND schema_name != 'information_schema'");
          diagnostics.database.schemas = schemas.rows.map(r => r.schema_name);
        } catch (e) {
          console.log('Could not get schemas:', e.message);
        }

        // Get table information
        try {
          const tables = await query(`
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
          
          diagnostics.tables.total = tables.rows.length;
          diagnostics.tables.list = tables.rows;

          // Count tables with data
          let tablesWithData = 0;
          for (const table of tables.rows) {
            try {
              const count = await query(`SELECT COUNT(*) as count FROM ${table.table_name}`);
              const recordCount = parseInt(count.rows[0].count);
              table.record_count = recordCount;
              if (recordCount > 0) tablesWithData++;
            } catch (e) {
              table.record_count = 'Error: ' + e.message;
            }
          }
          diagnostics.tables.withData = tablesWithData;

        } catch (e) {
          console.log('Could not get table info:', e.message);
          diagnostics.tables.error = e.message;
        }

      } else {
        diagnostics.connection.status = 'connected_no_data';
        diagnostics.connection.details = { error: 'Connected but no data returned' };
      }

    } catch (error) {
      console.error('Database connection failed:', error);
      diagnostics.connection.status = 'failed';
      diagnostics.connection.details = {
        error: error.message,
        code: error.code,
        hint: error.hint
      };
    }

    res.json({
      status: 'ok',
      diagnostics,
      summary: {
        environment: diagnostics.environment.NODE_ENV || 'unknown',
        database: diagnostics.database.name,
        connection: diagnostics.connection.status,
        tablesWithData: `${diagnostics.tables.withData}/${diagnostics.tables.total}`
      }
    });

  } catch (error) {
    console.error('Error in database diagnostics:', error);
    res.status(500).json({ 
      status: 'error',
      error: 'Diagnostics failed', 
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
