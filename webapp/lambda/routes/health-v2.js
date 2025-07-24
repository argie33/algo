/**
 * Database Health Check System V2
 * Fast, scalable, multi-tier health monitoring
 */

const express = require('express');
const { query } = require('../utils/database');
const router = express.Router();

// Health cache for performance
let healthCache = {
  connection: { data: null, timestamp: 0, ttl: 30000 },
  critical: { data: null, timestamp: 0, ttl: 60000 },
  full: { data: null, timestamp: 0, ttl: 300000 }
};

// Critical tables that need immediate monitoring
const CRITICAL_TABLES = [
  'symbols', 'stock_symbols', 'price_daily', 'latest_prices',
  'portfolio_holdings', 'user_api_keys', 'health_status'
];

// Table categorization for business logic
const TABLE_CATEGORIES = {
  symbols: ['symbols', 'stock_symbols', 'etf_symbols'],
  prices: ['price_daily', 'price_weekly', 'latest_prices'],
  portfolio: ['portfolio_holdings', 'position_history'],
  system: ['health_status', 'last_updated', 'user_api_keys']
};

/**
 * Tier 1: Ultra-fast connection health (< 1 second)
 * GET /health/connection
 */
router.get('/connection', async (req, res) => {
  try {
    const startTime = Date.now();
    
    // Check cache first
    if (isCacheValid('connection')) {
      return res.json({
        ...healthCache.connection.data,
        cached: true,
        responseTime: Date.now() - startTime
      });
    }
    
    // Minimal connection test
    const connectionQuery = `
      SELECT 
        current_database() as db_name,
        current_user as db_user,
        NOW() as current_time,
        (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public') as total_tables,
        (SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name = ANY($1)) as critical_tables_present
    `;
    
    const result = await Promise.race([
      query(connectionQuery, [CRITICAL_TABLES]),
      new Promise((_, reject) => setTimeout(() => reject(new Error('Connection timeout')), 5000))
    ]);
    
    const connectionHealth = {
      status: 'connected',
      database: {
        name: result.rows[0].db_name,
        user: result.rows[0].db_user,
        total_tables: parseInt(result.rows[0].total_tables),
        critical_tables_present: parseInt(result.rows[0].critical_tables_present),
        expected_critical_tables: CRITICAL_TABLES.length
      },
      responseTime: Date.now() - startTime,
      timestamp: new Date().toISOString(),
      cached: false
    };
    
    // Update cache
    updateCache('connection', connectionHealth);
    
    res.json(connectionHealth);
    
  } catch (error) {
    console.error('❌ Connection health check failed:', error);
    res.status(503).json({
      status: 'error',
      error: error.message,
      database: { status: 'disconnected' },
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * Tier 2: Critical tables health (< 3 seconds)
 * GET /health/critical
 */
router.get('/critical', async (req, res) => {
  try {
    const startTime = Date.now();
    
    // Check cache first
    if (isCacheValid('critical')) {
      return res.json({
        ...healthCache.critical.data,
        cached: true,
        responseTime: Date.now() - startTime
      });
    }
    
    // Use enhanced critical health data function
    const criticalData = await getCriticalHealthData();
    
    const result = {
      ...criticalData,
      responseTime: Date.now() - startTime,
      cached: false
    };
    
    // Update cache
    updateCache('critical', result);
    
    res.json(result);
    
  } catch (error) {
    console.error('❌ Critical health check failed:', error);
    res.status(503).json({
      status: 'error',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Remove the old critical query logic that's now in getCriticalHealthData
/*
    // Critical tables batch query (moved to getCriticalHealthData)
    const criticalQuery = `
      SELECT 
        t.table_name,
        COALESCE(s.n_live_tup, 0) as estimated_rows,
        COALESCE(s.n_tup_ins + s.n_tup_upd + s.n_tup_del, 0) as total_activity,
        s.last_vacuum,
        s.last_analyze,
        s.last_autoanalyze,
        CASE 
          WHEN s.n_live_tup = 0 THEN 'empty'
          WHEN s.last_analyze < NOW() - INTERVAL '7 days' OR s.last_autoanalyze < NOW() - INTERVAL '7 days' THEN 'stale'
          WHEN s.n_live_tup > 0 THEN 'healthy'
          ELSE 'unknown'
        END as status,
        CASE 
          WHEN s.last_analyze > s.last_autoanalyze THEN s.last_analyze
          ELSE s.last_autoanalyze
        END as last_analyzed
      FROM information_schema.tables t
      LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name
      WHERE t.table_schema = 'public' 
        AND t.table_name = ANY($1)
      ORDER BY total_activity DESC
    `;
    
    const result = await Promise.race([
      query(criticalQuery, [CRITICAL_TABLES]),
      new Promise((_, reject) => setTimeout(() => reject(new Error('Critical health timeout')), 8000))
    ]);
    
    // Process critical table results
    const criticalTableHealth = {};
    let summary = {
      total_tables: result.rows.length,
      healthy_tables: 0,
      stale_tables: 0,
      empty_tables: 0,
      error_tables: 0,
      total_records: 0
    };
    
    result.rows.forEach(table => {
      const rows = parseInt(table.estimated_rows) || 0;
      summary.total_records += rows;
      
      if (table.status === 'healthy') summary.healthy_tables++;
      else if (table.status === 'stale') summary.stale_tables++;
      else if (table.status === 'empty') summary.empty_tables++;
      else summary.error_tables++;
      
      criticalTableHealth[table.table_name] = {
        status: table.status,
        estimated_rows: rows,
        total_activity: parseInt(table.total_activity) || 0,
        last_analyzed: table.last_analyzed,
        category: getCategoryForTable(table.table_name),
        is_critical: true
      };
    });
    
    const criticalHealth = {
      status: summary.healthy_tables > 0 ? 'operational' : 'degraded',
      critical_tables: criticalTableHealth,
      summary,
      missing_critical_tables: CRITICAL_TABLES.filter(t => !criticalTableHealth[t]),
      responseTime: Date.now() - startTime,
      timestamp: new Date().toISOString(),
      cached: false
    };
    
    // Update cache
    updateCache('critical', criticalHealth);
    
    res.json(criticalHealth);
    
  } catch (error) {
    console.error('❌ Critical health check failed:', error);
    res.status(503).json({
      status: 'error',
      error: error.message,
      critical_tables: {},
      summary: { total_tables: 0, healthy_tables: 0, stale_tables: 0, empty_tables: 0, error_tables: 0, total_records: 0 },
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * Tier 3: Full system health (cached/background)
 * GET /health/full
 */
router.get('/full', async (req, res) => {
  try {
    const startTime = Date.now();
    
    // Always return cached data for full scan to avoid timeouts
    if (healthCache.full.data) {
      return res.json({
        ...healthCache.full.data,
        cached: true,
        responseTime: Date.now() - startTime,
        cache_age: Date.now() - healthCache.full.timestamp
      });
    }
    
    // If no cache available, trigger background scan and return critical data
    console.log('🔄 No full health cache available, triggering background scan...');
    backgroundFullHealthScan(); // Non-blocking
    
    // Return critical data immediately
    const criticalData = await getCriticalHealthData();
    
    res.json({
      status: 'partial',
      message: 'Full scan running in background, returning critical data',
      ...criticalData,
      full_scan_status: 'in_progress',
      responseTime: Date.now() - startTime,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('❌ Full health check failed:', error);
    res.status(503).json({
      status: 'error',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * Background full health scan (non-blocking)
 */
async function backgroundFullHealthScan() {
  try {
    const startTime = Date.now();
    console.log('🔄 Starting background full health scan...');
    
    // Get all tables in batches
    const allTablesQuery = `
      SELECT 
        t.table_name,
        COALESCE(s.n_live_tup, 0) as estimated_rows,
        COALESCE(s.n_tup_ins + s.n_tup_upd + s.n_tup_del, 0) as total_activity,
        s.last_vacuum,
        s.last_analyze,
        s.last_autoanalyze,
        s.last_autovacuum,
        CASE 
          WHEN s.n_live_tup = 0 THEN 'empty'
          WHEN s.last_analyze < NOW() - INTERVAL '7 days' OR s.last_autoanalyze < NOW() - INTERVAL '7 days' THEN 'stale'
          WHEN s.n_live_tup > 0 THEN 'healthy'
          ELSE 'unknown'
        END as status
      FROM information_schema.tables t
      LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name
      WHERE t.table_schema = 'public' 
        AND t.table_type = 'BASE TABLE'
      ORDER BY total_activity DESC
    `;
    
    const result = await query(allTablesQuery, [], 30000); // 30 second timeout for background
    
    // Process all table results
    const allTableHealth = {};
    let summary = {
      total_tables: result.rows.length,
      healthy_tables: 0,
      stale_tables: 0,
      empty_tables: 0,
      error_tables: 0,
      total_records: 0,
      categories: {}
    };
    
    result.rows.forEach(table => {
      const rows = parseInt(table.estimated_rows) || 0;
      summary.total_records += rows;
      
      if (table.status === 'healthy') summary.healthy_tables++;
      else if (table.status === 'stale') summary.stale_tables++;
      else if (table.status === 'empty') summary.empty_tables++;
      else summary.error_tables++;
      
      const category = getCategoryForTable(table.table_name);
      if (!summary.categories[category]) {
        summary.categories[category] = { tables: 0, healthy: 0, total_rows: 0 };
      }
      summary.categories[category].tables++;
      summary.categories[category].total_rows += rows;
      if (table.status === 'healthy') summary.categories[category].healthy++;
      
      allTableHealth[table.table_name] = {
        status: table.status,
        estimated_rows: rows,
        total_activity: parseInt(table.total_activity) || 0,
        last_analyzed: table.last_analyzed || table.last_autoanalyze,
        last_vacuum: table.last_vacuum || table.last_autovacuum,
        category,
        is_critical: CRITICAL_TABLES.includes(table.table_name)
      };
    });
    
    // Generate missing data analysis
    const missingDataTables = Object.entries(allTableHealth)
      .filter(([_, data]) => data.status === 'empty' || data.estimated_rows === 0)
      .map(([table, _]) => table);

    // Enhanced summary with detailed formatting
    const enhancedSummary = {
      ...summary,
      formatted_summary: {
        title: "📊 Database Tables Summary:",
        total_tables: `Total Tables: ${summary.total_tables}`,
        healthy: `Healthy: ${summary.healthy_tables}`,
        stale: `Stale: ${summary.stale_tables}`,
        errors: `Errors: ${summary.error_tables}`,
        empty: `Empty: ${summary.empty_tables}`,
        missing: missingDataTables.length > 0 ? `Missing: ${missingDataTables.join(', ')}` : 'Missing: None',
        total_records: `Total Records: ${summary.total_records.toLocaleString()}`,
        missing_data: missingDataTables.length > 0 ? `Missing Data: ${missingDataTables.length} tables need data` : 'No missing data detected'
      },
      missing_tables: missingDataTables,
      health_percentage: Math.round((summary.healthy_tables / summary.total_tables) * 100),
      data_coverage: Math.round(((summary.total_tables - summary.empty_tables) / summary.total_tables) * 100)
    };

    const fullHealth = {
      status: summary.healthy_tables > summary.total_tables * 0.8 ? 'healthy' : 'degraded',
      all_tables: allTableHealth,
      summary: enhancedSummary,
      scan_duration: Date.now() - startTime, // Fix duration calculation
      timestamp: new Date().toISOString(),
      cached: false
    };
    
    // Update cache
    updateCache('full', fullHealth);
    console.log('✅ Background full health scan completed');
    
  } catch (error) {
    console.error('❌ Background full health scan failed:', error);
  }
}

/**
 * Utility functions
 */

function isCacheValid(type) {
  const cache = healthCache[type];
  return cache.data && (Date.now() - cache.timestamp) < cache.ttl;
}

function updateCache(type, data) {
  healthCache[type] = {
    data,
    timestamp: Date.now(),
    ttl: healthCache[type].ttl
  };
}

function getCategoryForTable(tableName) {
  for (const [category, tables] of Object.entries(TABLE_CATEGORIES)) {
    if (tables.includes(tableName)) return category;
  }
  return 'other';
}

async function getCriticalHealthData() {
  try {
    // Check critical tables with detailed analysis
    const criticalQuery = `
      SELECT 
        t.table_name,
        COALESCE(s.n_live_tup, 0) as estimated_rows,
        COALESCE(s.n_tup_ins + s.n_tup_upd + s.n_tup_del, 0) as total_activity,
        s.last_analyze,
        s.last_autoanalyze,
        CASE 
          WHEN s.n_live_tup = 0 THEN 'empty'
          WHEN s.last_analyze < NOW() - INTERVAL '7 days' OR s.last_autoanalyze < NOW() - INTERVAL '7 days' THEN 'stale'
          WHEN s.n_live_tup > 0 THEN 'healthy'
          ELSE 'unknown'
        END as status
      FROM information_schema.tables t
      LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name
      WHERE t.table_schema = 'public' 
        AND t.table_type = 'BASE TABLE'
        AND t.table_name = ANY($1)
      ORDER BY s.n_live_tup DESC
    `;
    
    const result = await query(criticalQuery, [CRITICAL_TABLES], 15000);
    
    // Process critical table results
    const criticalTableHealth = {};
    let summary = {
      total_tables: result.rows.length,
      healthy_tables: 0,
      stale_tables: 0,
      empty_tables: 0,
      error_tables: 0,
      total_records: 0
    };
    
    result.rows.forEach(table => {
      const rows = parseInt(table.estimated_rows) || 0;
      summary.total_records += rows;
      
      if (table.status === 'healthy') summary.healthy_tables++;
      else if (table.status === 'stale') summary.stale_tables++;
      else if (table.status === 'empty') summary.empty_tables++;
      else summary.error_tables++;
      
      criticalTableHealth[table.table_name] = {
        status: table.status,
        estimated_rows: rows,
        total_activity: parseInt(table.total_activity) || 0,
        last_analyzed: table.last_analyze || table.last_autoanalyze,
        is_critical: true
      };
    });

    // Generate missing data analysis for critical tables
    const missingCriticalTables = Object.entries(criticalTableHealth)
      .filter(([_, data]) => data.status === 'empty' || data.estimated_rows === 0)
      .map(([table, _]) => table);

    // Enhanced summary with detailed formatting
    const enhancedSummary = {
      ...summary,
      formatted_summary: {
        title: "📊 Critical Tables Summary:",
        total_tables: `Critical Tables: ${summary.total_tables}`,
        healthy: `Healthy: ${summary.healthy_tables}`,
        stale: `Stale: ${summary.stale_tables}`,
        errors: `Errors: ${summary.error_tables}`,
        empty: `Empty: ${summary.empty_tables}`,
        missing: missingCriticalTables.length > 0 ? `Missing: ${missingCriticalTables.join(', ')}` : 'Missing: None',
        total_records: `Total Records: ${summary.total_records.toLocaleString()}`,
        missing_data: missingCriticalTables.length > 0 ? `Missing Data: ${missingCriticalTables.length} critical tables need data` : 'All critical data present'
      },
      missing_tables: missingCriticalTables,
      health_percentage: Math.round((summary.healthy_tables / summary.total_tables) * 100),
      data_coverage: Math.round(((summary.total_tables - summary.empty_tables) / summary.total_tables) * 100)
    };
    
    return {
      status: summary.healthy_tables === summary.total_tables ? 'healthy' : 'degraded',
      critical_tables: criticalTableHealth,
      summary: enhancedSummary,
      scan_type: 'critical_only',
      timestamp: new Date().toISOString()
    };
    
  } catch (error) {
    console.error('❌ Critical health data failed:', error);
    return {
      status: 'error',
      error: error.message,
      timestamp: new Date().toISOString()
    };
  }
}

// Initialize background scanning
setInterval(() => {
  if (!isCacheValid('full')) {
    backgroundFullHealthScan();
  }
}, 300000); // Every 5 minutes

/**
 * Additional endpoints for frontend compatibility
 */

// Ready endpoint - similar to connection but returns simple status
router.get('/ready', async (req, res) => {
  try {
    // Quick connection test
    const result = await query('SELECT 1 as test');
    res.json({
      status: 'ready',
      healthy: true,
      timestamp: new Date().toISOString(),
      database: { connected: true }
    });
  } catch (error) {
    res.status(503).json({
      status: 'not_ready',
      healthy: false,
      timestamp: new Date().toISOString(),
      database: { connected: false, error: error.message }
    });
  }
});

// Update status endpoint for frontend health management
router.post('/update-status', async (req, res) => {
  try {
    console.log('Health status update requested');
    
    // Trigger fresh health scans
    healthCache.connection.timestamp = 0;
    healthCache.critical.timestamp = 0;
    healthCache.full.timestamp = 0;
    
    // Trigger background scan
    backgroundFullHealthScan();
    
    res.json({
      status: 'update_triggered',
      message: 'Health caches cleared and background scan initiated',
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    res.status(500).json({
      status: 'update_failed',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Debug endpoints for troubleshooting
router.get('/debug/db-test', async (req, res) => {
  try {
    const result = await query('SELECT 1 as test, NOW() as timestamp');
    res.json({
      status: 'success',
      database: { connected: true, test_result: result.rows[0] },
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    res.status(500).json({
      status: 'error',
      database: { connected: false, error: error.message },
      timestamp: new Date().toISOString()
    });
  }
});

router.get('/debug/tables', async (req, res) => {
  try {
    const result = await query(`
      SELECT table_name, table_rows 
      FROM information_schema.tables 
      WHERE table_schema = DATABASE()
      ORDER BY table_name
    `);
    res.json({
      status: 'success',
      tables: result.rows,
      count: result.rows.length,
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

router.get('/debug/test-query', async (req, res) => {
  try {
    const result = await query('SELECT COUNT(*) as total FROM symbols LIMIT 1');
    res.json({
      status: 'success',
      query_result: result.rows[0],
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

router.get('/debug/env', async (req, res) => {
  try {
    res.json({
      status: 'success',
      environment: {
        NODE_ENV: process.env.NODE_ENV,
        AWS_REGION: process.env.AWS_REGION,
        DB_ENDPOINT: !!process.env.DB_ENDPOINT,
        DB_SECRET_ARN: !!process.env.DB_SECRET_ARN,
        ENVIRONMENT: process.env.ENVIRONMENT
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

router.get('/debug/cors-test', async (req, res) => {
  try {
    res.json({
      status: 'success',
      cors: {
        origin: req.headers.origin || 'none',
        method: req.method,
        headers: Object.keys(req.headers)
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

module.exports = router;