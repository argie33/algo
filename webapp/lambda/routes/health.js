/**
 * Health Check Routes - CONSOLIDATED VERSION
 * Combines all the best features from health-old, health-v2, health-v3
 * 
 * Features:
 * - Smart caching for performance (from v2)
 * - Comprehensive diagnostics (from old)
 * - Circuit breaker integration (from v3)
 * - Multiple health check levels
 * - Legacy compatibility
 * - Debug endpoints
 */

const express = require('express');

// Safe database imports with error handling
let query, initializeDatabase, getPool, healthCheck, DatabaseCircuitBreaker, databaseCircuitBreaker;

try {
  const dbUtils = require('../utils/database');
  ({ query, initializeDatabase, getPool, healthCheck } = dbUtils);
  DatabaseCircuitBreaker = require('../utils/databaseCircuitBreaker');
  databaseCircuitBreaker = new DatabaseCircuitBreaker();
} catch (error) {
  console.error('⚠️ Database dependencies not available:', error.message);
  // Create fallback functions
  query = () => Promise.reject(new Error('Database unavailable'));
  initializeDatabase = () => Promise.reject(new Error('Database unavailable'));
  getPool = () => null;
  healthCheck = () => Promise.resolve({ healthy: false, error: 'Database unavailable' });
  databaseCircuitBreaker = {
    execute: (fn) => Promise.reject(new Error('Circuit breaker unavailable')),
    getStatus: () => ({ state: 'OPEN', error: 'Circuit breaker unavailable' })
  };
}

const router = express.Router();

// Health cache for performance (from v2)
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
 * GET /health/simple
 * Ultra-simple health check - no dependencies, immediate response
 */
router.get('/simple', (req, res) => {
  res.status(200).json({
    success: true,
    status: 'healthy',
    service: 'Financial Dashboard API',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    environment: process.env.ENVIRONMENT || 'dev',
    version: '1.0-consolidated'
  });
});

/**
 * GET /health/quick
 * Quick health check for load balancers
 */
router.get('/quick', (req, res) => {
  res.json({
    success: true,
    status: 'healthy',
    service: 'Financial Dashboard API',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    environment: process.env.ENVIRONMENT || 'dev',
    memory: process.memoryUsage(),
    config: {
      hasDbSecret: !!process.env.DB_SECRET_ARN,
      hasDbEndpoint: !!process.env.DB_ENDPOINT,
      hasAwsRegion: !!process.env.AWS_REGION
    }
  });
});

/**
 * GET /health/connection
 * Cached database connection check (from v2)
 */
router.get('/connection', async (req, res) => {
  const cacheKey = 'connection';
  const now = Date.now();
  
  // Return cached data if still valid
  if (healthCache[cacheKey].data && (now - healthCache[cacheKey].timestamp) < healthCache[cacheKey].ttl) {
    return res.json({
      ...healthCache[cacheKey].data,
      cached: true,
      cacheAge: now - healthCache[cacheKey].timestamp
    });
  }
  
  try {
    // Test basic database connection
    const startTime = Date.now();
    const result = await databaseCircuitBreaker.execute(async () => {
      return await query('SELECT 1 as connection_test, NOW() as server_time');
    });
    
    const responseTime = Date.now() - startTime;
    const healthData = {
      success: true,
      status: 'healthy',
      connection: {
        status: 'connected',
        responseTime: responseTime,
        serverTime: result.rows[0].server_time,
        testResult: result.rows[0].connection_test
      },
      circuitBreaker: databaseCircuitBreaker.getStatus(),
      timestamp: new Date().toISOString(),
      cached: false
    };
    
    // Cache the result
    healthCache[cacheKey] = {
      data: healthData,
      timestamp: now
    };
    
    res.json(healthData);
    
  } catch (error) {
    const errorData = {
      success: false,
      status: 'unhealthy',
      connection: {
        status: 'failed',
        error: error.message,
        circuitBreakerState: databaseCircuitBreaker.getStatus().state
      },
      timestamp: new Date().toISOString(),
      cached: false
    };
    
    res.status(503).json(errorData);
  }
});

/**
 * GET /health/critical
 * Check critical tables (from v2)
 */
router.get('/critical', async (req, res) => {
  const cacheKey = 'critical';
  const now = Date.now();
  
  // Return cached data if still valid
  if (healthCache[cacheKey].data && (now - healthCache[cacheKey].timestamp) < healthCache[cacheKey].ttl) {
    return res.json({
      ...healthCache[cacheKey].data,
      cached: true,
      cacheAge: now - healthCache[cacheKey].timestamp
    });
  }
  
  try {
    const tableChecks = {};
    let allHealthy = true;
    
    // Check each critical table
    for (const tableName of CRITICAL_TABLES) {
      try {
        const startTime = Date.now();
        const result = await databaseCircuitBreaker.execute(async () => {
          return await query(`SELECT COUNT(*) as count, MAX(updated_at) as last_updated FROM ${tableName} LIMIT 1`);
        });
        
        const responseTime = Date.now() - startTime;
        tableChecks[tableName] = {
          status: 'healthy',
          rowCount: parseInt(result.rows[0]?.count || 0),
          lastUpdated: result.rows[0]?.last_updated,
          responseTime: responseTime
        };
      } catch (error) {
        allHealthy = false;
        tableChecks[tableName] = {
          status: 'error',
          error: error.message,
          timestamp: new Date().toISOString()
        };
      }
    }
    
    const healthData = {
      success: allHealthy,
      status: allHealthy ? 'healthy' : 'degraded',
      tables: tableChecks,
      summary: {
        totalTables: CRITICAL_TABLES.length,
        healthyTables: Object.values(tableChecks).filter(t => t.status === 'healthy').length,
        errorTables: Object.values(tableChecks).filter(t => t.status === 'error').length
      },
      circuitBreaker: databaseCircuitBreaker.getStatus(),
      timestamp: new Date().toISOString(),
      cached: false
    };
    
    // Cache the result
    healthCache[cacheKey] = {
      data: healthData,
      timestamp: now
    };
    
    res.status(allHealthy ? 200 : 503).json(healthData);
    
  } catch (error) {
    const errorData = {
      success: false,
      status: 'unhealthy',
      error: 'Critical table check failed',
      message: error.message,
      timestamp: new Date().toISOString(),
      cached: false
    };
    
    res.status(503).json(errorData);
  }
});

/**
 * GET /health/database/quick
 * Quick database health check
 */
router.get('/database/quick', async (req, res) => {
  try {
    const startTime = Date.now();
    const dbHealth = await databaseCircuitBreaker.execute(async () => {
      return await query('SELECT 1 as healthy, NOW() as timestamp');
    });
    
    const responseTime = Date.now() - startTime;
    
    res.json({
      success: true,
      status: 'healthy',
      database: {
        status: 'connected',
        responseTime: responseTime,
        serverTime: dbHealth.rows[0].timestamp,
        testResult: dbHealth.rows[0].healthy
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Quick database health check failed:', error);
    
    res.status(503).json({
      success: false,
      status: 'unhealthy',
      database: {
        status: 'failed',
        error: error.message,
        circuitBreakerState: databaseCircuitBreaker.getStatus().state
      },
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * GET /health/database
 * Comprehensive database health check
 */
router.get('/database', async (req, res) => {
  try {
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
          success: false,
          status: 'unhealthy',
          database: {
            status: 'initialization_failed',
            error: dbInitError.message,
            lastAttempt: new Date().toISOString()
          },
          timestamp: new Date().toISOString()
        });
      }
    }

    const startTime = Date.now();
    const dbHealth = await databaseCircuitBreaker.execute(async () => {
      return await healthCheck();
    });
    
    const responseTime = Date.now() - startTime;
    
    res.json({
      success: true,
      status: 'healthy',
      database: {
        ...dbHealth,
        responseTime: responseTime,
        pool: getPool() ? {
          totalCount: getPool().totalCount,
          idleCount: getPool().idleCount,
          waitingCount: getPool().waitingCount
        } : null
      },
      circuitBreaker: databaseCircuitBreaker.getStatus(),
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Database health check failed:', error);
    
    res.status(503).json({
      success: false,
      status: 'unhealthy',
      database: {
        status: 'failed',
        error: error.message,
        circuitBreakerState: databaseCircuitBreaker.getStatus().state
      },
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * GET /health/full
 * Full health check with all systems (from v2)
 */
router.get('/full', async (req, res) => {
  const cacheKey = 'full';
  const now = Date.now();
  
  // Return cached data if still valid
  if (healthCache[cacheKey].data && (now - healthCache[cacheKey].timestamp) < healthCache[cacheKey].ttl) {
    return res.json({
      ...healthCache[cacheKey].data,
      cached: true,
      cacheAge: now - healthCache[cacheKey].timestamp
    });
  }
  
  try {
    const startTime = Date.now();
    
    // Get all health checks
    const [connectionHealth, dbHealth] = await Promise.allSettled([
      databaseCircuitBreaker.execute(async () => {
        return await query('SELECT 1 as test, NOW() as time');
      }),
      healthCheck()
    ]);
    
    // Check table categories
    const categoryHealth = {};
    for (const [category, tables] of Object.entries(TABLE_CATEGORIES)) {
      const categoryResults = {};
      for (const table of tables) {
        try {
          const result = await query(`SELECT COUNT(*) as count FROM ${table} LIMIT 1`);
          categoryResults[table] = {
            status: 'healthy',
            rowCount: parseInt(result.rows[0]?.count || 0)
          };
        } catch (error) {
          categoryResults[table] = {
            status: 'error',
            error: error.message
          };
        }
      }
      categoryHealth[category] = categoryResults;
    }
    
    const responseTime = Date.now() - startTime;
    const healthData = {
      success: true,
      status: 'healthy',
      service: 'Financial Dashboard API - Full Health',
      version: '1.0-consolidated',
      responseTime: responseTime,
      database: {
        connection: connectionHealth.status === 'fulfilled' ? {
          status: 'connected',
          serverTime: connectionHealth.value.rows[0].time
        } : {
          status: 'failed',
          error: connectionHealth.reason?.message
        },
        health: dbHealth.status === 'fulfilled' ? dbHealth.value : {
          healthy: false,
          error: dbHealth.reason?.message
        },
        categories: categoryHealth
      },
      system: {
        uptime: process.uptime(),
        memory: process.memoryUsage(),
        environment: process.env.ENVIRONMENT || 'dev',
        nodeVersion: process.version,
        platform: process.platform
      },
      circuitBreaker: databaseCircuitBreaker.getStatus(),
      timestamp: new Date().toISOString(),
      cached: false
    };
    
    // Cache the result
    healthCache[cacheKey] = {
      data: healthData,
      timestamp: now
    };
    
    res.json(healthData);
    
  } catch (error) {
    const errorData = {
      success: false,
      status: 'unhealthy',
      error: 'Full health check failed',
      message: error.message,
      timestamp: new Date().toISOString(),
      cached: false
    };
    
    res.status(503).json(errorData);
  }
});

/**
 * GET /health/diagnostics
 * Comprehensive diagnostic information (from old)
 */
router.get('/diagnostics', async (req, res) => {
  try {
    const diagnostics = {
      success: true,
      service: 'Financial Dashboard API - Diagnostics',
      timestamp: new Date().toISOString(),
      version: '1.0-consolidated',
      environment: {
        NODE_ENV: process.env.NODE_ENV || 'unknown',
        ENVIRONMENT: process.env.ENVIRONMENT || 'dev',
        AWS_REGION: process.env.AWS_REGION || 'not_set',
        IS_LAMBDA: !!process.env.AWS_LAMBDA_FUNCTION_NAME,
        DB_SECRET_ARN: !!process.env.DB_SECRET_ARN,
        DB_ENDPOINT: !!process.env.DB_ENDPOINT
      },
      system: {
        uptime: process.uptime(),
        memory: process.memoryUsage(),
        pid: process.pid,
        nodeVersion: process.version,
        platform: process.platform
      },
      database: {
        poolStats: getPool() ? {
          totalCount: getPool().totalCount,
          idleCount: getPool().idleCount,
          waitingCount: getPool().waitingCount,
          ended: getPool().ended
        } : { status: 'uninitialized' },
        circuitBreaker: databaseCircuitBreaker.getStatus()
      },
      cache: {
        connection: {
          hasData: !!healthCache.connection.data,
          age: healthCache.connection.timestamp ? Date.now() - healthCache.connection.timestamp : 0,
          ttl: healthCache.connection.ttl
        },
        critical: {
          hasData: !!healthCache.critical.data,
          age: healthCache.critical.timestamp ? Date.now() - healthCache.critical.timestamp : 0,
          ttl: healthCache.critical.ttl
        },
        full: {
          hasData: !!healthCache.full.data,
          age: healthCache.full.timestamp ? Date.now() - healthCache.full.timestamp : 0,
          ttl: healthCache.full.ttl
        }
      }
    };
    
    res.json(diagnostics);
    
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Diagnostics failed',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * POST /health/refresh-cache
 * Clear health cache (from v3)
 */
router.post('/refresh-cache', (req, res) => {
  // Clear all cache entries
  healthCache = {
    connection: { data: null, timestamp: 0, ttl: 30000 },
    critical: { data: null, timestamp: 0, ttl: 60000 },
    full: { data: null, timestamp: 0, ttl: 300000 }
  };
  
  res.json({
    success: true,
    message: 'Health cache cleared',
    timestamp: new Date().toISOString()
  });
});

/**
 * POST /health/update-status
 * Update health status (from old)
 */
router.post('/update-status', async (req, res) => {
  try {
    const { status, message, component } = req.body;
    
    await databaseCircuitBreaker.execute(async () => {
      await query(
        'INSERT INTO health_status (component, status, message, updated_at) VALUES ($1, $2, $3, NOW()) ON CONFLICT (component) DO UPDATE SET status = $2, message = $3, updated_at = NOW()',
        [component || 'system', status, message]
      );
    });
    
    // Clear cache to force refresh
    healthCache.critical.data = null;
    healthCache.full.data = null;
    
    res.json({
      success: true,
      message: 'Health status updated',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Failed to update health status',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * GET /health/debug
 * Debug information (from old)
 */
router.get('/debug', async (req, res) => {
  try {
    const debug = {
      success: true,
      timestamp: new Date().toISOString(),
      environment: process.env,
      database: {
        hasPool: !!getPool(),
        poolStats: getPool() ? {
          totalCount: getPool().totalCount,
          idleCount: getPool().idleCount,
          waitingCount: getPool().waitingCount
        } : null,
        circuitBreaker: databaseCircuitBreaker.getStatus()
      },
      system: {
        uptime: process.uptime(),
        memory: process.memoryUsage(),
        cpuUsage: process.cpuUsage(),
        pid: process.pid,
        versions: process.versions
      },
      cache: healthCache
    };
    
    res.json(debug);
    
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Debug information failed',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * GET /health (default route)
 * Main health check endpoint with backward compatibility
 */
router.get('/', async (req, res) => {
  try {
    // Quick check for query parameter
    if (req.query.quick === 'true') {
      return res.json({
        success: true,
        status: 'healthy',
        service: 'Financial Dashboard API',
        timestamp: new Date().toISOString(),
        environment: process.env.ENVIRONMENT || 'dev',
        memory: process.memoryUsage(),
        uptime: process.uptime(),
        note: 'Quick health check - database not tested',
        database: { status: 'not_tested' },
        version: '1.0-consolidated'
      });
    }
    
    // Full health check
    const startTime = Date.now();
    const dbHealth = await databaseCircuitBreaker.execute(async () => {
      return await healthCheck();
    });
    
    const responseTime = Date.now() - startTime;
    
    res.json({
      success: true,
      status: 'healthy',
      service: 'Financial Dashboard API',
      version: '1.0-consolidated',
      database: {
        ...dbHealth,
        responseTime: responseTime
      },
      system: {
        uptime: process.uptime(),
        memory: process.memoryUsage(),
        environment: process.env.ENVIRONMENT || 'dev'
      },
      circuitBreaker: databaseCircuitBreaker.getStatus(),
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Health check failed:', error);
    
    res.status(503).json({
      success: false,
      status: 'unhealthy',
      service: 'Financial Dashboard API',
      version: '1.0-consolidated',
      database: {
        status: 'failed',
        error: error.message,
        circuitBreakerState: databaseCircuitBreaker.getStatus().state
      },
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;