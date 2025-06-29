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
    // Ensure database is initialized first
    try {
      await initializeDatabase();
      console.log('Database initialized successfully');
    } catch (dbInitError) {
      console.error('Database initialization failed:', dbInitError);
      return res.status(503).json({
        status: 'error',
        message: 'Database initialization failed',
        details: dbInitError.message,
        timestamp: new Date().toISOString(),
        debug: {
          config: dbInitError.config,
          env: dbInitError.env
        }
      });
    }

    console.log('Step 1: Creating health_status table...');
    // First, check if health_status table exists and has the correct schema
    try {
      const tableCheck = await query(`
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'health_status' 
        AND column_name = 'last_updated';
      `);
      
      // If table exists but doesn't have last_updated column, drop and recreate it
      if (tableCheck.rows.length === 0) {
        console.log('Step 1a: Migrating health_status table schema...');
        await query('DROP TABLE IF EXISTS health_status;');
      }
    } catch (e) {
      console.log('Step 1a: Error checking table schema, dropping table:', e.message);
      await query('DROP TABLE IF EXISTS health_status;');
    }
    
    // Create the health_status table with enhanced schema
    await query(`
      CREATE TABLE IF NOT EXISTS health_status (
        id SERIAL PRIMARY KEY,
        table_name VARCHAR(100) NOT NULL,
        record_count BIGINT,
        status VARCHAR(20) NOT NULL,
        last_checked TIMESTAMP NOT NULL DEFAULT NOW(),
        error_message TEXT,
        last_updated TIMESTAMP,
        stale_threshold_hours INTEGER DEFAULT 24,
        is_stale BOOLEAN DEFAULT FALSE,
        missing_data_count BIGINT DEFAULT 0,
        UNIQUE(table_name)
      );
    `);
    
    console.log('Step 2: Getting cached health status...');
    // Get cached health status
    const healthResult = await query(`
      SELECT 
        table_name, 
        record_count, 
        status, 
        last_checked, 
        error_message,
        last_updated,
        stale_threshold_hours,
        is_stale,
        missing_data_count
      FROM health_status 
      ORDER BY table_name;
    `);
    
    console.log('Step 3: Getting database time...');
    // Get current database time
    const dbTimeResult = await query('SELECT NOW() as current_time, version() as postgres_version');
    
    console.log('Step 4: Processing table stats...');
    const tableStats = {};
    healthResult.rows.forEach(row => {
      tableStats[row.table_name] = {
        record_count: row.record_count,
        status: row.status,
        last_checked: row.last_checked,
        error: row.error_message,
        last_updated: row.last_updated,
        stale_threshold_hours: row.stale_threshold_hours,
        is_stale: row.is_stale,
        missing_data_count: row.missing_data_count
      };
    });
    
    // If no cached data exists, populate it automatically with enhanced analysis
    if (Object.keys(tableStats).length === 0) {
      console.log('Step 5: No cached data found, populating automatically...');
      
      // First, get all actual tables from the database
      const allTablesResult = await query(`
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_type = 'BASE TABLE'
        ORDER BY table_name;
      `);
      
      const actualTables = allTablesResult.rows.map(row => row.table_name);
      console.log(`Found ${actualTables.length} actual tables in database:`, actualTables);
      
      const expectedTables = [
        // Core symbol tables
        'stock_symbols', 'etf_symbols', 'last_updated',
        
        // Market sentiment and indicators
        'fear_greed_index', 'naaim_exposure', 'aaii_sentiment', 'naaim',
        
        // Analyst and earnings data
        'analyst_upgrade_downgrade', 'calendar_events',
        'earnings_estimates', 'earnings_history', 'revenue_estimates',
        'earnings_metrics',
        
        // Economic and company data
        'economic_data', 'company_profile', 'leadership_team',
        'governance_scores', 'market_data', 'key_metrics', 'analyst_estimates',
        
        // Price data tables
        'price_daily', 'price_weekly', 'price_monthly',
        'etf_price_daily', 'etf_price_weekly', 'etf_price_monthly',
        'price_data_montly', // from test file (with typo)
        
        // Technical analysis tables
        'technical_data_daily', 'technical_data_weekly', 'technical_data_monthly',
        
        // Trading signals
        'buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly',
        
        // Financial statements (from loadfinancialdata.py)
        'balance_sheet_annual', 'balance_sheet_quarterly', 'balance_sheet_ttm',
        'income_statement_annual', 'income_statement_quarterly', 'income_statement_ttm',
        'cash_flow_annual', 'cash_flow_quarterly', 'cash_flow_ttm',
        'financials', 'financials_quarterly', 'financials_ttm',
        
        // New modular financial data loaders
        'quarterly_balance_sheet', 'annual_balance_sheet',
        'quarterly_income_statement', 'annual_income_statement',
        'quarterly_cash_flow', 'annual_cash_flow',
        'ttm_income_statement', 'ttm_cash_flow',
        
        // Latest price and technical data (these use the same tables as regular price/technical)
        'latest_price_daily', 'latest_price_weekly', 'latest_price_monthly',
        'latest_technical_data_daily', 'latest_technical_data_weekly', 'latest_technical_data_monthly',
        
        // Additional tables that might be created
        'health_status' // the health check table itself
      ];
      
      // Combine expected tables with actual tables to ensure we check everything
      const allTablesToCheck = [...new Set([...expectedTables, ...actualTables])];
      console.log(`Will check ${allTablesToCheck.length} tables total (${expectedTables.length} expected + ${actualTables.length} actual)`);
      
      for (const tableName of allTablesToCheck) {
        try {
          console.log(`Processing table: ${tableName}`);
          // Check if table exists
          const tableExists = await query(`
            SELECT EXISTS (
              SELECT FROM information_schema.tables 
              WHERE table_schema = 'public' 
              AND table_name = $1
            );
          `, [tableName]);
          
          if (tableExists.rows[0].exists) {
            // Get record count
            const countResult = await query(`SELECT COUNT(*) as count FROM ${tableName}`);
            const recordCount = parseInt(countResult.rows[0].count);
            
            // Check for fetched_at column and get last updated
            let lastUpdated = null;
            let isStale = false;
            let missingDataCount = 0;
            let staleThresholdHours = 24; // Default threshold
            
            try {
              // Check if fetched_at column exists
              const columnExists = await query(`
                SELECT EXISTS (
                  SELECT FROM information_schema.columns 
                  WHERE table_name = $1 
                  AND column_name = 'fetched_at'
                );
              `, [tableName]);
              
              if (columnExists.rows[0].exists) {
                // Get last updated timestamp
                const lastUpdateResult = await query(`
                  SELECT MAX(fetched_at) as last_updated 
                  FROM ${tableName} 
                  WHERE fetched_at IS NOT NULL
                `);
                
                if (lastUpdateResult.rows[0].last_updated) {
                  lastUpdated = lastUpdateResult.rows[0].last_updated;
                  
                  // Check if data is stale (older than threshold)
                  const hoursSinceUpdate = (new Date() - new Date(lastUpdated)) / (1000 * 60 * 60);
                  isStale = hoursSinceUpdate > staleThresholdHours;
                  
                  // Count records with missing fetched_at
                  const missingDataResult = await query(`
                    SELECT COUNT(*) as missing_count 
                    FROM ${tableName} 
                    WHERE fetched_at IS NULL
                  `);
                  missingDataCount = parseInt(missingDataResult.rows[0].missing_count);
                }
              } else {
                // Try alternative timestamp columns
                const altColumns = ['updated_at', 'created_at', 'date', 'period_end', 'timestamp'];
                for (const col of altColumns) {
                  try {
                    const altColumnExists = await query(`
                      SELECT EXISTS (
                        SELECT FROM information_schema.columns 
                        WHERE table_name = $1 
                        AND column_name = $2
                      );
                    `, [tableName, col]);
                    
                    if (altColumnExists.rows[0].exists) {
                      const altLastUpdateResult = await query(`
                        SELECT MAX(${col}) as last_updated 
                        FROM ${tableName} 
                        WHERE ${col} IS NOT NULL
                      `);
                      
                      if (altLastUpdateResult.rows[0].last_updated) {
                        lastUpdated = altLastUpdateResult.rows[0].last_updated;
                        const hoursSinceUpdate = (new Date() - new Date(lastUpdated)) / (1000 * 60 * 60);
                        isStale = hoursSinceUpdate > staleThresholdHours;
                        break;
                      }
                    }
                  } catch (e) {
                    // Continue to next column
                  }
                }
              }
            } catch (e) {
              console.log(`Could not analyze timestamp for table ${tableName}:`, e.message);
            }
            
            // Determine status based on analysis
            let status = 'healthy';
            if (recordCount === 0) {
              status = 'empty';
            } else if (isStale) {
              status = 'stale';
            } else if (missingDataCount > 0) {
              status = 'incomplete';
            }
            
            // Insert enhanced health status
            await query(`
              INSERT INTO health_status (
                table_name, record_count, status, last_checked, 
                last_updated, stale_threshold_hours, is_stale, missing_data_count
              )
              VALUES ($1, $2, $3, NOW(), $4, $5, $6, $7)
              ON CONFLICT (table_name) DO UPDATE SET
                record_count = EXCLUDED.record_count,
                status = EXCLUDED.status,
                last_checked = EXCLUDED.last_checked,
                last_updated = EXCLUDED.last_updated,
                stale_threshold_hours = EXCLUDED.stale_threshold_hours,
                is_stale = EXCLUDED.is_stale,
                missing_data_count = EXCLUDED.missing_data_count,
                error_message = NULL;
            `, [tableName, recordCount, status, lastUpdated, staleThresholdHours, isStale, missingDataCount]);
            
            tableStats[tableName] = {
              record_count: recordCount,
              status: status,
              last_checked: new Date().toISOString(),
              error: null,
              last_updated: lastUpdated,
              stale_threshold_hours: staleThresholdHours,
              is_stale: isStale,
              missing_data_count: missingDataCount
            };
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
            
            tableStats[tableName] = {
              record_count: null,
              status: 'not_found',
              last_checked: new Date().toISOString(),
              error: 'Table does not exist',
              last_updated: null,
              stale_threshold_hours: 24,
              is_stale: false,
              missing_data_count: 0
            };
          }
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
          
          tableStats[tableName] = {
            record_count: null,
            status: 'error',
            last_checked: new Date().toISOString(),
            error: error.message,
            last_updated: null,
            stale_threshold_hours: 24,
            is_stale: false,
            missing_data_count: 0
          };
        }
      }
    }
    
    console.log('Step 6: Calculating summary statistics...');
    // Calculate summary statistics
    const summary = {
      total_tables: Object.keys(tableStats).length,
      healthy_tables: Object.values(tableStats).filter(t => t.status === 'healthy').length,
      stale_tables: Object.values(tableStats).filter(t => t.is_stale).length,
      empty_tables: Object.values(tableStats).filter(t => t.status === 'empty').length,
      error_tables: Object.values(tableStats).filter(t => t.status === 'error').length,
      missing_tables: Object.values(tableStats).filter(t => t.status === 'not_found').length,
      total_records: Object.values(tableStats).reduce((sum, t) => sum + (t.record_count || 0), 0),
      total_missing_data: Object.values(tableStats).reduce((sum, t) => sum + (t.missing_data_count || 0), 0)
    };
    
    console.log('Step 7: Sending response...');
    res.json({
      status: 'healthy',
      timestamp: new Date().toISOString(),
      database: {
        status: 'connected',
        currentTime: dbTimeResult.rows[0].current_time,
        postgresVersion: dbTimeResult.rows[0].postgres_version,
        tables: tableStats,
        summary: summary,
        note: Object.keys(tableStats).length === 0 ? 'No tables found' : 
              'Data from cached health status table - run /health/update-status to refresh'
      }
    });
    
  } catch (error) {
    console.error('Database health check failed:', error);
    console.error('Error stack:', error.stack);
    res.status(503).json({
      status: 'unhealthy',
      timestamp: new Date().toISOString(),
      error: error.message,
      errorStack: error.stack,
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
    // Ensure the health_status table exists with enhanced schema
    await query(`
      CREATE TABLE IF NOT EXISTS health_status (
        id SERIAL PRIMARY KEY,
        table_name VARCHAR(100) NOT NULL,
        record_count BIGINT,
        status VARCHAR(20) NOT NULL,
        last_checked TIMESTAMP NOT NULL DEFAULT NOW(),
        error_message TEXT,
        last_updated TIMESTAMP,
        stale_threshold_hours INTEGER DEFAULT 24,
        is_stale BOOLEAN DEFAULT FALSE,
        missing_data_count BIGINT DEFAULT 0,
        UNIQUE(table_name)
      );
    `);
    
    const expectedTables = [
      // Core symbol tables
      'stock_symbols', 'etf_symbols', 'last_updated',
      
      // Market sentiment and indicators
      'fear_greed_index', 'naaim_exposure', 'aaii_sentiment', 'naaim',
      
      // Analyst and earnings data
      'analyst_upgrade_downgrade', 'calendar_events',
      'earnings_estimates', 'earnings_history', 'revenue_estimates',
      'earnings_metrics',
      
      // Economic and company data
      'economic_data', 'company_profile', 'leadership_team',
      'governance_scores', 'market_data', 'key_metrics', 'analyst_estimates',
      
      // Price data tables
      'price_daily', 'price_weekly', 'price_monthly',
      'etf_price_daily', 'etf_price_weekly', 'etf_price_monthly',
      'price_data_montly', // from test file (with typo)
      
      // Technical analysis tables
      'technical_data_daily', 'technical_data_weekly', 'technical_data_monthly',
      
      // Trading signals
      'buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly',
      
      // Financial statements (from loadfinancialdata.py)
      'balance_sheet_annual', 'balance_sheet_quarterly', 'balance_sheet_ttm',
      'income_statement_annual', 'income_statement_quarterly', 'income_statement_ttm',
      'cash_flow_annual', 'cash_flow_quarterly', 'cash_flow_ttm',
      'financials', 'financials_quarterly', 'financials_ttm',
      
      // New modular financial data loaders
      'quarterly_balance_sheet', 'annual_balance_sheet',
      'quarterly_income_statement', 'annual_income_statement',
      'quarterly_cash_flow', 'annual_cash_flow',
      'ttm_income_statement', 'ttm_cash_flow',
      
      // Latest price and technical data (these use the same tables as regular price/technical)
      'latest_price_daily', 'latest_price_weekly', 'latest_price_monthly',
      'latest_technical_data_daily', 'latest_technical_data_weekly', 'latest_technical_data_monthly',
      
      // Additional tables that might be created
      'health_status' // the health check table itself
    ];
    
    // Get all actual tables from the database for comprehensive checking
    const allTablesResult = await query(`
      SELECT table_name 
      FROM information_schema.tables 
      WHERE table_schema = 'public' 
      AND table_type = 'BASE TABLE'
      ORDER BY table_name;
    `);
    
    const actualTables = allTablesResult.rows.map(row => row.table_name);
    console.log(`Found ${actualTables.length} actual tables in database:`, actualTables);
    
    // Combine expected tables with actual tables to ensure we check everything
    const allTablesToCheck = [...new Set([...expectedTables, ...actualTables])];
    console.log(`Will check ${allTablesToCheck.length} tables total (${expectedTables.length} expected + ${actualTables.length} actual)`);
    
    let processed = 0;
    let errors = 0;
    
    for (const tableName of allTablesToCheck) {
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
          // Get record count
          const countResult = await query(`SELECT COUNT(*) as count FROM ${tableName}`);
          const recordCount = parseInt(countResult.rows[0].count);
          
          // Check for fetched_at column and get last updated
          let lastUpdated = null;
          let isStale = false;
          let missingDataCount = 0;
          let staleThresholdHours = 24; // Default threshold
          
          try {
            // Check if fetched_at column exists
            const columnExists = await query(`
              SELECT EXISTS (
                SELECT FROM information_schema.columns 
                WHERE table_name = $1 
                AND column_name = 'fetched_at'
              );
            `, [tableName]);
            
            if (columnExists.rows[0].exists) {
              // Get last updated timestamp
              const lastUpdateResult = await query(`
                SELECT MAX(fetched_at) as last_updated 
                FROM ${tableName} 
                WHERE fetched_at IS NOT NULL
              `);
              
              if (lastUpdateResult.rows[0].last_updated) {
                lastUpdated = lastUpdateResult.rows[0].last_updated;
                
                // Check if data is stale (older than threshold)
                const hoursSinceUpdate = (new Date() - new Date(lastUpdated)) / (1000 * 60 * 60);
                isStale = hoursSinceUpdate > staleThresholdHours;
                
                // Count records with missing fetched_at
                const missingDataResult = await query(`
                  SELECT COUNT(*) as missing_count 
                  FROM ${tableName} 
                  WHERE fetched_at IS NULL
                `);
                missingDataCount = parseInt(missingDataResult.rows[0].missing_count);
              }
            } else {
              // Try alternative timestamp columns
              const altColumns = ['updated_at', 'created_at', 'date', 'period_end', 'timestamp'];
              for (const col of altColumns) {
                try {
                  const altColumnExists = await query(`
                    SELECT EXISTS (
                      SELECT FROM information_schema.columns 
                      WHERE table_name = $1 
                      AND column_name = $2
                    );
                  `, [tableName, col]);
                  
                  if (altColumnExists.rows[0].exists) {
                    const altLastUpdateResult = await query(`
                      SELECT MAX(${col}) as last_updated 
                      FROM ${tableName} 
                      WHERE ${col} IS NOT NULL
                    `);
                    
                    if (altLastUpdateResult.rows[0].last_updated) {
                      lastUpdated = altLastUpdateResult.rows[0].last_updated;
                      const hoursSinceUpdate = (new Date() - new Date(lastUpdated)) / (1000 * 60 * 60);
                      isStale = hoursSinceUpdate > staleThresholdHours;
                      break;
                    }
                  }
                } catch (e) {
                  // Continue to next column
                }
              }
            }
          } catch (e) {
            console.log(`Could not analyze timestamp for table ${tableName}:`, e.message);
          }
          
          // Determine status based on analysis
          let status = 'healthy';
          if (recordCount === 0) {
            status = 'empty';
          } else if (isStale) {
            status = 'stale';
          } else if (missingDataCount > 0) {
            status = 'incomplete';
          }
          
          // Update or insert enhanced health status
          await query(`
            INSERT INTO health_status (
              table_name, record_count, status, last_checked, 
              last_updated, stale_threshold_hours, is_stale, missing_data_count
            )
            VALUES ($1, $2, $3, NOW(), $4, $5, $6, $7)
            ON CONFLICT (table_name) DO UPDATE SET
              record_count = EXCLUDED.record_count,
              status = EXCLUDED.status,
              last_checked = EXCLUDED.last_checked,
              last_updated = EXCLUDED.last_updated,
              stale_threshold_hours = EXCLUDED.stale_threshold_hours,
              is_stale = EXCLUDED.is_stale,
              missing_data_count = EXCLUDED.missing_data_count,
              error_message = NULL;
          `, [tableName, recordCount, status, lastUpdated, staleThresholdHours, isStale, missingDataCount]);
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
