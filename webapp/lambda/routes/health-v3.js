/**
 * Health Check V3 - Smart Cached Health Monitoring
 * High-performance health checks with intelligent caching
 */

const express = require('express');
const SmartHealthMonitor = require('../services/smartHealthMonitor');

// Safe database imports with error handling
let query, databaseCircuitBreaker;

try {
  const dbUtils = require('../utils/database');
  ({ query } = dbUtils);
  const DatabaseCircuitBreaker = require('../utils/databaseCircuitBreaker');
  databaseCircuitBreaker = new DatabaseCircuitBreaker();
} catch (error) {
  console.error('⚠️ Database dependencies not available:', error.message);
  query = () => Promise.reject(new Error('Database unavailable'));
  databaseCircuitBreaker = {
    execute: (fn) => Promise.reject(new Error('Circuit breaker unavailable')),
    getStatus: () => ({ state: 'OPEN', error: 'Circuit breaker unavailable' })
  };
}

const router = express.Router();

// Initialize smart health monitor
const healthMonitor = new SmartHealthMonitor();

// Initialize on first use
let initPromise = null;
const ensureInitialized = async () => {
  if (!initPromise) {
    initPromise = healthMonitor.initialize().catch(error => {
      console.error('Health monitor initialization failed:', error);
      initPromise = null; // Reset for retry
      throw error;
    });
  }
  return initPromise;
};

/**
 * GET /health/database
 * Ultra-fast database health check (sub-100ms) with intelligent caching
 */
router.get('/database', async (req, res) => {
  try {
    await ensureInitialized();
    
    const health = await healthMonitor.getInstantHealth();
    
    // Format to match legacy health API
    res.json({
      success: true,
      database: {
        connection: {
          status: health.connection?.status || 'connected',
          host: process.env.DB_ENDPOINT || 'localhost',
          database: 'financial_dashboard',
          lastConnected: health.timestamp,
          responseTime: health.connection?.responseTime || health.responseTime,
          serverTime: health.connection?.serverTime || health.timestamp
        },
        tables: health.tables || {},
        performance: {
          totalExecutionTime: health.responseTime,
          activeConnections: health.performance?.activeConnections || 0,
          cacheEfficiency: health.performance?.cacheEfficiency || 'unknown',
          ...health.performance
        }
      },
      timestamp: health.timestamp,
      note: 'Cached health check'
    });
    
  } catch (error) {
    console.error('Instant health check failed:', error);
    
    res.status(503).json({
      success: false,
      error: 'Database health unavailable',
      message: error.message,
      database: {
        connection: {
          status: 'failed',
          error: error.message
        },
        tables: {},
        performance: {}
      },
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * GET /health/comprehensive  
 * Detailed health with smart caching fallback
 */
router.get('/comprehensive', async (req, res) => {
  try {
    await ensureInitialized();
    
    const health = await healthMonitor.getInstantHealth();
    
    // Add circuit breaker status
    const circuitBreakerStatus = databaseCircuitBreaker.getStatus();
    health.circuitBreaker = {
      state: circuitBreakerStatus.state,
      failures: circuitBreakerStatus.failureCount,
      lastFailure: circuitBreakerStatus.lastFailureTime
    };
    
    // Add environment info
    health.environment = {
      nodeEnv: process.env.NODE_ENV || 'unknown',
      environment: process.env.ENVIRONMENT || 'dev',
      region: process.env.AWS_REGION || 'not_configured',
      isLambda: !!process.env.AWS_LAMBDA_FUNCTION_NAME
    };
    
    res.json({
      success: true,
      data: health,
      version: '3.0',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Detailed health check failed:', error);
    
    res.status(503).json({
      success: false,
      error: 'Detailed health check failed',
      message: error.message,
      version: '3.0',
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * GET /health/v3/cache-status
 * Cache performance and status metrics
 */
router.get('/cache-status', async (req, res) => {
  try {
    await ensureInitialized();
    
    const metrics = healthMonitor.getMonitoringMetrics();
    
    res.json({
      success: true,
      cache: {
        status: metrics.isInitialized ? 'active' : 'initializing',
        performance: {
          hitRate: metrics.cacheHitRate,
          hits: metrics.cacheHits,
          misses: metrics.cacheMisses,
          avgResponseTime: metrics.avgResponseTime
        },
        background: {
          updatesCompleted: metrics.backgroundUpdates,
          jobsActive: metrics.backgroundJobsActive,
          errorCount: metrics.errorCount
        },
        data: {
          cacheAge: metrics.cacheAge,
          lastUpdate: healthMonitor.healthCache.lastUpdate,
          validUntil: new Date(healthMonitor.healthCache.cacheValidUntil).toISOString()
        }
      },
      version: '3.0',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Cache status unavailable',
      message: error.message,
      version: '3.0',
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * POST /health/v3/refresh-cache
 * Force cache refresh (for debugging/manual updates)
 */
router.post('/refresh-cache', async (req, res) => {
  try {
    await ensureInitialized();
    
    const startTime = Date.now();
    await healthMonitor.updateHealthCache();
    const updateTime = Date.now() - startTime;
    
    res.json({
      success: true,
      message: 'Cache refreshed successfully',
      updateTime,
      version: '3.0',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Cache refresh failed',
      message: error.message,
      version: '3.0',
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * GET /health/v3/monitoring
 * System monitoring dashboard data
 */
router.get('/monitoring', async (req, res) => {
  try {
    await ensureInitialized();
    
    const health = await healthMonitor.getInstantHealth();
    const metrics = healthMonitor.getMonitoringMetrics();
    
    const monitoring = {
      overview: {
        status: health.status,
        responseTime: health.responseTime,
        dataSource: health.source,
        lastUpdate: health.cache?.lastUpdate || health.timestamp
      },
      performance: {
        cacheHitRate: metrics.cacheHitRate,
        avgResponseTime: metrics.avgResponseTime,
        errorRate: metrics.errorCount > 0 ? 
          (metrics.errorCount / (metrics.cacheHits + metrics.cacheMisses + metrics.errorCount) * 100).toFixed(2) + '%' : '0%'
      },
      database: {
        connectionStatus: health.connection?.status || 'unknown',
        activeConnections: health.performance?.activeConnections || 0,
        cacheEfficiency: health.performance?.cacheEfficiency || 'unknown',
        tableCount: Object.keys(health.tables || {}).length
      },
      system: {
        uptime: process.uptime(),
        memory: process.memoryUsage(),
        environment: process.env.NODE_ENV || 'unknown'
      }
    };
    
    res.json({
      success: true,
      monitoring,
      version: '3.0',
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Monitoring data unavailable',
      message: error.message,
      version: '3.0',
      timestamp: new Date().toISOString()
    });
  }
});

/**
 * GET /health/v3/legacy-compatible
 * Legacy compatibility endpoint that matches old health check format
 */
router.get('/legacy-compatible', async (req, res) => {
  try {
    await ensureInitialized();
    
    const health = await healthMonitor.getInstantHealth();
    
    // Transform to legacy format for backward compatibility
    const legacyHealth = {
      success: true,
      database: {
        connection: {
          status: health.connection?.status || 'unknown',
          host: process.env.DB_ENDPOINT || 'localhost',
          database: 'financial_dashboard',
          lastConnected: health.timestamp,
          responseTime: health.connection?.responseTime || 0
        },
        tables: health.tables || {},
        performance: health.performance || {}
      },
      timestamp: health.timestamp,
      note: 'V3 Smart Health with legacy compatibility'
    };
    
    res.json(legacyHealth);
    
  } catch (error) {
    res.status(503).json({
      success: false,
      error: 'Database health unavailable',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
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
    environment: process.env.ENVIRONMENT || 'dev'
  });
});

/**
 * GET /health/simple
 * Ultra-simple health check
 */
router.get('/simple', (req, res) => {
  res.status(200).json({
    success: true,
    status: 'healthy',
    service: 'Financial Dashboard API',
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
    message: 'Basic health check passed'
  });
});

/**
 * GET /health/
 * Main health dashboard endpoint
 */
router.get('/', async (req, res) => {
  try {
    await ensureInitialized();
    
    const health = await healthMonitor.getInstantHealth();
    
    res.json({
      success: true,
      service: 'Financial Dashboard API - Smart Health V3',
      status: health.status,
      responseTime: health.responseTime,
      dataSource: health.source,
      version: '3.0',
      endpoints: {
        instant: '/health/v3/instant',
        detailed: '/health/v3/detailed',
        monitoring: '/health/v3/monitoring',
        cacheStatus: '/health/v3/cache-status',
        legacyCompatible: '/health/v3/legacy-compatible'
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    res.status(503).json({
      success: false,
      error: 'Smart health system unavailable',
      message: error.message,
      version: '3.0',
      timestamp: new Date().toISOString()
    });
  }
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('Shutting down Smart Health Monitor...');
  healthMonitor.shutdown();
});

process.on('SIGINT', () => {
  console.log('Shutting down Smart Health Monitor...');
  healthMonitor.shutdown();
});

module.exports = router;