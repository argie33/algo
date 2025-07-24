/**
 * Database Health Check System - WORKING VERSION
 * Comprehensive health monitoring with all data points
 * Based on proven health-old.js with enhancements
 */

const express = require('express');
const { query, initializeDatabase, getPool, healthCheck } = require('../utils/database');

const router = express.Router();

// Health check endpoint with comprehensive data
router.get('/', async (req, res) => {
  try {
    // Basic health check without database (for quick status)
    if (req.query.quick === 'true') {
      return res.json({
        status: 'healthy',
        healthy: true,
        service: 'Financial Dashboard API',
        timestamp: new Date().toISOString(),
        environment: process.env.ENVIRONMENT || 'dev',
        memory: process.memoryUsage(),
        uptime: process.uptime(),
        note: 'Quick health check - database not tested',
        database: { status: 'not_tested' },
        api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' },
        config: {
          hasDbSecret: !!process.env.DB_SECRET_ARN,
          hasDbEndpoint: !!process.env.DB_ENDPOINT,
          hasAwsRegion: !!process.env.AWS_REGION
        }
      });
    }

    console.log('Starting comprehensive health check with database...');
    
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
          environment: process.env.ENVIRONMENT || 'dev',
          database: {
            status: 'initialization_failed',
            error: dbInitError.message,
            lastAttempt: new Date().toISOString(),
            tables: {}
          },
          api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' },
          memory: process.memoryUsage(),
          uptime: process.uptime()
        });
      }
    }

    // Test database connection with comprehensive table analysis
    const dbStart = Date.now();
    let result;
    
    try {
      // Basic connection test
      result = await query('SELECT NOW() as current_time, version() as db_version');
      console.log('✅ Database connection successful');
      
      // Get comprehensive table information
      const tableInfoQuery = `
        SELECT 
          t.table_name,
          COALESCE(s.n_live_tup, 0) as estimated_rows,
          COALESCE(s.n_tup_ins + s.n_tup_upd + s.n_tup_del, 0) as total_activity,  
          s.last_vacuum, s.last_analyze, s.last_autoanalyze, s.last_autovacuum,
          pg_size_pretty(pg_total_relation_size(c.oid)) as table_size,
          pg_total_relation_size(c.oid) as size_bytes,
          (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name) as column_count,
          CASE 
            WHEN s.n_live_tup = 0 THEN 'empty'
            WHEN s.last_analyze < NOW() - INTERVAL '7 days' OR s.last_autoanalyze < NOW() - INTERVAL '7 days' THEN 'stale'
            WHEN s.n_live_tup > 0 THEN 'healthy'
            ELSE 'unknown'
          END as status
        FROM information_schema.tables t
        LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name
        LEFT JOIN pg_class c ON c.relname = t.table_name
        WHERE t.table_schema = 'public'
        ORDER BY total_activity DESC, estimated_rows DESC
      `;
      
      const tableInfo = await query(tableInfoQuery);
      console.log(`📊 Found ${tableInfo.rows.length} tables in database`);
      
      // Categorize tables for better organization
      const TABLE_CATEGORIES = {
        symbols: ['symbols', 'stock_symbols', 'etf_symbols', 'stock_symbols_enhanced'],
        prices: ['price_daily', 'price_weekly', 'price_monthly', 'latest_prices', 'etf_price_daily', 'etf_price_weekly', 'etf_price_monthly', 'price_data_montly'],
        technicals: ['technical_data_daily', 'technical_data_weekly', 'technical_data_monthly'],
        financials: ['annual_balance_sheet', 'annual_income_statement', 'annual_cash_flow', 'quarterly_balance_sheet', 'quarterly_income_statement', 'quarterly_cash_flow', 'ttm_income_statement', 'ttm_cash_flow'],
        company: ['company_profile', 'market_data', 'key_metrics', 'analyst_estimates', 'governance_scores', 'leadership_team'],
        earnings: ['earnings_history', 'earnings_estimates', 'revenue_estimates', 'calendar_events', 'earnings_metrics'],
        sentiment: ['fear_greed_index', 'aaii_sentiment', 'naaim', 'economic_data', 'analyst_upgrade_downgrade'],
        trading: ['portfolio_holdings', 'portfolio_performance', 'trading_alerts', 'buy_sell_daily', 'buy_sell_weekly', 'buy_sell_monthly'],
        scoring: ['quality_metrics', 'value_metrics', 'growth_metrics', 'stock_scores', 'earnings_quality_metrics', 'balance_sheet_strength', 'profitability_metrics', 'management_effectiveness', 'valuation_multiples', 'intrinsic_value_analysis', 'revenue_growth_analysis', 'earnings_growth_analysis', 'price_momentum_analysis', 'technical_momentum_analysis', 'analyst_sentiment_analysis', 'social_sentiment_analysis', 'institutional_positioning', 'insider_trading_analysis', 'score_performance_tracking', 'market_regime'],
        news: ['stock_news'],
        system: ['health_status', 'last_updated', 'user_api_keys'],
        test: ['earnings', 'prices', 'stocks'],
        other: []
      };
      
      // Organize tables by category
      const categorizedTables = {};
      const allTables = {};
      
      // Initialize categories
      Object.keys(TABLE_CATEGORIES).forEach(category => {
        categorizedTables[category] = {};
      });
      
      // Process each table
      tableInfo.rows.forEach(table => {
        const tableName = table.table_name;
        const tableData = {
          name: tableName,
          rows: parseInt(table.estimated_rows) || 0,
          activity: parseInt(table.total_activity) || 0,
          size: table.table_size || '0 bytes',
          size_bytes: parseInt(table.size_bytes) || 0,
          columns: parseInt(table.column_count) || 0,
          status: table.status || 'unknown',
          last_vacuum: table.last_vacuum,
          last_analyze: table.last_analyze || table.last_autoanalyze,
          health: table.status === 'healthy' ? 'good' : table.status === 'empty' ? 'empty' : 'needs_attention'
        };
        
        // Add to all tables
        allTables[tableName] = tableData;
        
        // Categorize table
        let categorized = false;
        for (const [category, tableNames] of Object.entries(TABLE_CATEGORIES)) {
          if (tableNames.includes(tableName)) {
            categorizedTables[category][tableName] = tableData;
            categorized = true;
            break;
          }
        }
        
        // Add to 'other' if not categorized
        if (!categorized) {
          categorizedTables.other[tableName] = tableData;
        }
      });
      
      // Calculate summary statistics
      const totalTables = tableInfo.rows.length;
      const totalRows = tableInfo.rows.reduce((sum, table) => sum + (parseInt(table.estimated_rows) || 0), 0);
      const totalSize = tableInfo.rows.reduce((sum, table) => sum + (parseInt(table.size_bytes) || 0), 0);
      const healthyTables = tableInfo.rows.filter(table => table.status === 'healthy').length;
      const emptyTables = tableInfo.rows.filter(table => table.status === 'empty').length;
      const staleTables = tableInfo.rows.filter(table => table.status === 'stale').length;
      
      // Format total size
      const formatBytes = (bytes) => {
        if (bytes === 0) return '0 bytes';
        const k = 1024;
        const sizes = ['bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
      };
      
      const dbResponseTime = Date.now() - dbStart;
      
      // Successful health check response with ALL data points
      res.json({
        status: 'operational',
        healthy: true,
        service: 'Financial Dashboard API',
        timestamp: new Date().toISOString(),
        environment: process.env.ENVIRONMENT || 'dev',
        database: {
          status: 'connected',
          connection_time: result.rows[0].current_time,
          version: result.rows[0].db_version,
          response_time: `${dbResponseTime}ms`,
          tables: categorizedTables,      // Categorized view
          all_tables: allTables,          // Flat view for compatibility
          summary: {
            total_tables: totalTables,
            total_rows: totalRows,
            total_size: formatBytes(totalSize),
            total_size_bytes: totalSize,
            healthy_tables: healthyTables,
            empty_tables: emptyTables,
            stale_tables: staleTables,
            categories: Object.keys(TABLE_CATEGORIES).map(category => ({
              name: category,
              table_count: Object.keys(categorizedTables[category]).length,
              tables: Object.keys(categorizedTables[category])
            }))
          }
        },
        api: { 
          version: '2.0.0', 
          environment: process.env.ENVIRONMENT || 'dev',
          lambda_timeout: '14min 50s',
          routes_loaded: 'health system operational'
        },
        memory: process.memoryUsage(),
        uptime: process.uptime(),
        config: {
          hasDbSecret: !!process.env.DB_SECRET_ARN,
          hasDbEndpoint: !!process.env.DB_ENDPOINT,
          hasAwsRegion: !!process.env.AWS_REGION,
          lambdaFunction: process.env.AWS_LAMBDA_FUNCTION_NAME || 'local'
        }
      });
      
    } catch (dbError) {
      console.error('❌ Database health check failed:', dbError.message);
      const dbResponseTime = Date.now() - dbStart;
      
      res.status(503).json({
        status: 'unhealthy',
        healthy: false,
        service: 'Financial Dashboard API',
        timestamp: new Date().toISOString(),
        environment: process.env.ENVIRONMENT || 'dev',  
        database: {
          status: 'error',
          error: dbError.message,
          response_time: `${dbResponseTime}ms`,
          lastAttempt: new Date().toISOString(),
          tables: "Database connection failed"
        },
        api: { version: '2.0.0', environment: process.env.ENVIRONMENT || 'dev' },
        memory: process.memoryUsage(),
        uptime: process.uptime()
      });
    }
    
  } catch (error) {
    console.error('❌ Health check system error:', error.message);
    res.status(500).json({
      status: 'error',
      healthy: false,
      service: 'Financial Dashboard API',
      timestamp: new Date().toISOString(),
      environment: process.env.ENVIRONMENT || 'dev',
      error: error.message,
      database: { status: 'error' },
      api: { version: '2.0.0' },
      memory: process.memoryUsage(),
      uptime: process.uptime()
    });
  }
});

// Connection health endpoint (for frontend compatibility)
router.get('/connection', async (req, res) => {
  try {
    const result = await query('SELECT 1 as test');
    res.json({
      status: 'connected',
      healthy: true,
      database: { status: 'connected' },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    res.status(503).json({
      status: 'error',
      healthy: false,
      database: { status: 'disconnected' },
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Critical tables health endpoint
router.get('/critical', async (req, res) => {
  try {
    const criticalTables = ['symbols', 'stock_symbols', 'price_daily', 'latest_prices', 'portfolio_holdings'];
    const result = await query(`
      SELECT table_name, 
             COALESCE(s.n_live_tup, 0) as estimated_rows,
             CASE WHEN s.n_live_tup > 0 THEN 'healthy' ELSE 'empty' END as status
      FROM information_schema.tables t
      LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name
      WHERE t.table_schema = 'public' AND t.table_name = ANY($1)
    `, [criticalTables]);
    
    const tables = {};
    result.rows.forEach(row => {
      tables[row.table_name] = {
        rows: parseInt(row.estimated_rows),
        status: row.status
      };
    });
    
    res.json({
      status: 'operational',
      healthy: true,
      critical_tables: tables,
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    res.status(503).json({
      status: 'error',
      healthy: false,
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Full health scan endpoint
router.get('/full', async (req, res) => {
  // Redirect to main health endpoint for full data
  req.query = {}; // Remove any quick flags
  return router.handle(req, res);
});

module.exports = router;