/**
 * Database Health Check System
 * Multi-tier health monitoring with progressive loading and background processing
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
 * Main health endpoint - progressive loading
 * GET /health
 */
router.get('/', async (req, res) => {
  try {
    const startTime = Date.now();
    const mode = req.query.mode || 'progressive';
    
    // Quick health check without database
    if (req.query.quick === 'true') {
      return res.json({
        status: 'healthy',
        healthy: true,
        service: 'Financial Dashboard API',
        environment: process.env.ENVIRONMENT || 'dev',
        memory: process.memoryUsage(),
        uptime: process.uptime(),
        note: 'Quick infrastructure check - database not tested',
        database: { status: 'not_tested' },
        api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' },
        responseTime: Date.now() - startTime,
        timestamp: new Date().toISOString()
      });
    }
    
    if (mode === 'progressive') {
      // Progressive loading: connection → critical → full (background)
      const connectionHealth = await getConnectionHealth();
      
      if (!connectionHealth || connectionHealth.status !== 'connected') {
        return res.status(503).json({
          status: 'error',
          error: 'Database connection failed',
          database: { status: 'disconnected' },
          responseTime: Date.now() - startTime,
          timestamp: new Date().toISOString()
        });
      }
      
      // Start critical tables check
      const criticalHealth = await getCriticalHealth();
      
      // Trigger background full scan if needed
      if (!isCacheValid('full')) {
        backgroundFullHealthScan().catch(err => 
          console.error('Background health scan failed:', err)
        );
      }
      
      return res.json({
        status: criticalHealth.status,
        healthy: criticalHealth.status === 'operational',
        database: {
          status: 'connected',
          ...connectionHealth.database,
          critical_tables: criticalHealth.critical_tables,
          summary: criticalHealth.summary
        },
        full_scan_available: isCacheValid('full'),
        responseTime: Date.now() - startTime,
        timestamp: new Date().toISOString()
      });
    }
    
    // Fallback to critical health only
    const criticalHealth = await getCriticalHealth();
    return res.json({
      ...criticalHealth,
      responseTime: Date.now() - startTime
    });
    
  } catch (error) {
    console.error('❌ Health check failed:', error);
    res.status(503).json({
      status: 'error',
      error: error.message,
      database: { status: 'error' },
      timestamp: new Date().toISOString()
    });
  }
});

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
    
    const connectionHealth = await getConnectionHealth();
    updateCache('connection', connectionHealth);
    
    res.json({
      ...connectionHealth,
      responseTime: Date.now() - startTime
    });
    
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
    
    const criticalHealth = await getCriticalHealth();
    updateCache('critical', criticalHealth);
    
    res.json({
      ...criticalHealth,
      responseTime: Date.now() - startTime
    });
    
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
    const criticalData = await getCriticalHealth();
    
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
 * Health status update endpoint (for frontend compatibility)
 * POST /health/update-status
 */
router.post('/update-status', async (req, res) => {
  try {
    console.log('🔄 Health status update requested');
    
    // Force refresh critical tables cache
    healthCache.critical.timestamp = 0;
    
    const criticalHealth = await getCriticalHealth();
    updateCache('critical', criticalHealth);
    
    // Trigger background full scan
    backgroundFullHealthScan().catch(err => 
      console.error('Background scan failed:', err)
    );
    
    res.json({
      status: 'success',
      message: 'Database health status updated successfully',
      data: {
        status: criticalHealth.status,
        database: {
          status: criticalHealth.status === 'operational' ? 'connected' : 'degraded',
          tables: criticalHealth.critical_tables,
          summary: criticalHealth.summary
        },
        timestamp: new Date().toISOString()
      },
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
 * Core health check functions
 */

async function getConnectionHealth() {
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
  
  return {
    status: 'connected',
    database: {
      name: result.rows[0].db_name,
      user: result.rows[0].db_user,
      total_tables: parseInt(result.rows[0].total_tables),
      critical_tables_present: parseInt(result.rows[0].critical_tables_present),
      expected_critical_tables: CRITICAL_TABLES.length
    },
    timestamp: new Date().toISOString(),
    cached: false
  };
}

async function getCriticalHealth() {
  // Critical tables batch query
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
  
  return {
    status: summary.healthy_tables > 0 ? 'operational' : 'degraded',
    critical_tables: criticalTableHealth,
    summary,
    missing_critical_tables: CRITICAL_TABLES.filter(t => !criticalTableHealth[t]),
    timestamp: new Date().toISOString(),
    cached: false
  };
}

/**
 * Background full health scan (non-blocking)
 */
async function backgroundFullHealthScan() {
  try {
    console.log('🔄 Starting background full health scan...');
    const startTime = Date.now();
    
    // Get all tables in one query
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
    
    const fullHealth = {
      status: summary.healthy_tables > summary.total_tables * 0.8 ? 'healthy' : 'degraded',
      all_tables: allTableHealth,
      summary,
      scan_duration: Date.now() - startTime,
      timestamp: new Date().toISOString(),
      cached: false
    };
    
    // Update cache
    updateCache('full', fullHealth);
    console.log(`✅ Background full health scan completed in ${Date.now() - startTime}ms`);
    
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

// Initialize background scanning
setInterval(() => {
  if (!isCacheValid('full')) {
    backgroundFullHealthScan().catch(err => 
      console.error('Scheduled background scan failed:', err)
    );
  }
}, 300000); // Every 5 minutes

module.exports = router;