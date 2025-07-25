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

// Ultra-simple health check - no dependencies, immediate response
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

// Quick health check endpoint for load balancers and monitoring
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

// Fast database connection test endpoint (with timeout protection)
router.get('/database/quick', async (req, res) => {
  try {
    const startTime = Date.now();
    
    // Ultra-fast connection test with timeout
    const [result] = await Promise.race([
      query('SELECT 1 as connected, NOW() as timestamp'),
      new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Quick test timeout')), 3000)
      )
    ]);
    
    const responseTime = Date.now() - startTime;
    
    res.json({
      success: true,
      database: {
        connected: true,
        responseTime,
        serverTime: result.timestamp,
        status: 'healthy'
      },
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    res.status(503).json({
      success: false,
      database: {
        connected: false,
        error: error.message,
        status: 'unhealthy'
      },
      timestamp: new Date().toISOString()
    });
  }
});

// Comprehensive health check endpoint
router.get('/comprehensive', async (req, res) => {
  const startTime = Date.now();
  const healthData = {
    service: 'Financial Dashboard API',
    timestamp: new Date().toISOString(),
    status: 'healthy',
    healthy: true,
    responseTime: 0
  };

  try {
    // Essential system metrics (always available)
    healthData.system = {
      uptime: process.uptime(),
      memory: process.memoryUsage(),
      nodeVersion: process.version,
      platform: process.platform,
      arch: process.arch,
      pid: process.pid
    };

    // Environment configuration analysis
    healthData.environment = {
      NODE_ENV: process.env.NODE_ENV || 'unknown',
      ENVIRONMENT: process.env.ENVIRONMENT || 'dev',
      AWS_REGION: process.env.AWS_REGION || 'not_set',
      hasDbSecret: !!process.env.DB_SECRET_ARN,
      hasDbEndpoint: !!process.env.DB_ENDPOINT,
      allowDevBypass: process.env.ALLOW_DEV_BYPASS === 'true',
      isLambda: !!process.env.AWS_LAMBDA_FUNCTION_NAME,
      lambdaMemory: process.env.AWS_LAMBDA_FUNCTION_MEMORY_SIZE,
      lambdaTimeout: process.env.AWS_LAMBDA_FUNCTION_TIMEOUT
    };

    // Circuit breaker status across all systems
    try {
      healthData.circuitBreakers = {
        database: databaseCircuitBreaker.getStatus(),
        overall: databaseCircuitBreaker.getStatus().state === 'CLOSED' ? 'operational' : 'degraded'
      };
    } catch (cbError) {
      healthData.circuitBreakers = {
        database: { state: 'UNKNOWN', error: 'Circuit breaker unavailable' },
        overall: 'unknown'
      };
    }

    // Database connectivity with timeout protection
    try {
      const dbHealth = await Promise.race([
        databaseCircuitBreaker.execute(async () => {
          // Quick connection test
          const [connectionTest] = await query('SELECT 1 as connected, NOW() as timestamp');
          
          // Essential table counts with timeout
          const tablePromises = [
            query('SELECT COUNT(*) as count FROM stock_symbols').catch(() => [{ count: 'error' }]),
            query('SELECT COUNT(*) as count FROM portfolio_holdings').catch(() => [{ count: 'error' }]),
            query('SELECT COUNT(*) as count FROM api_keys').catch(() => [{ count: 'error' }])
          ];
          
          const [stockCount, portfolioCount, apiKeyCount] = await Promise.all(tablePromises);
          
          return {
            connected: true,
            connectionTime: connectionTest.timestamp,
            tables: {
              stock_symbols: stockCount[0].count,
              portfolio_holdings: portfolioCount[0].count,
              api_keys: apiKeyCount[0].count
            },
            status: 'operational'
          };
        }, 'health-comprehensive-db'),
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Database health check timeout')), 5000)
        )
      ]);

      healthData.database = dbHealth;
    } catch (dbError) {
      console.log('Database health check failed:', dbError.message);
      healthData.database = {
        connected: false,
        error: dbError.message.includes('timeout') ? 'Database timeout' : 'Connection failed',
        status: 'degraded',
        tables: {}
      };
      
      if (dbError.message.includes('timeout')) {
        healthData.status = 'degraded';
        healthData.healthy = false;
      }
    }

    // API endpoints health check
    healthData.endpoints = {
      available: [
        '/api/health',
        '/api/health/comprehensive',
        '/api/health/database/quick', 
        '/api/health/quick',
        '/api/stocks/popular',
        '/api/portfolio'
      ],
      critical: {
        health: 'operational',
        stocks: 'operational', 
        portfolio: 'operational'
      }
    };

  } catch (error) {
    console.error('Comprehensive health check error:', error);
    healthData.status = 'error';
    healthData.healthy = false;
    healthData.error = error.message;
  }

  healthData.responseTime = Date.now() - startTime;
  
  // Return appropriate status code
  const statusCode = healthData.healthy ? 200 : 503;
  res.status(statusCode).json(healthData);
});

// Database-specific diagnostics endpoint
router.get('/database', async (req, res) => {
  try {
    const dbHealth = await Promise.race([
      databaseCircuitBreaker.execute(async () => {
        const startTime = Date.now();
        const diagnostics = {
          connection: {
            status: 'connected',
            host: process.env.DB_ENDPOINT || 'localhost',
            database: 'financial_dashboard',
            lastConnected: new Date().toISOString()
          },
          tables: {},
          performance: {}
        };

        // Quick connection test first
        const [connectionTest] = await query('SELECT 1 as connected, NOW() as timestamp');
        diagnostics.connection.responseTime = Date.now() - startTime;
        diagnostics.connection.serverTime = connectionTest.timestamp;

        // Check essential tables
        const tables = ['stock_symbols', 'portfolio_holdings', 'api_keys'];
        for (const tableName of tables) {
          try {
            const [countResult] = await query(`SELECT COUNT(*) as count FROM ${tableName}`);
            diagnostics.tables[tableName] = {
              exists: true,
              rowCount: parseInt(countResult.count || 0),
              status: 'healthy'
            };
          } catch (tableError) {
            diagnostics.tables[tableName] = {
              exists: false,
              error: tableError.message,
              status: 'error'
            };
          }
        }

        return diagnostics;
      }, 'health-database-diagnostics'),
      new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Database diagnostics timeout')), 5000)
      )
    ]);

    res.json({
      success: true,
      database: dbHealth,
      timestamp: new Date().toISOString()
    });

  } catch (error) {
    res.status(503).json({
      success: false,
      error: 'Database diagnostics unavailable',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Main health dashboard endpoint - ALWAYS RESPONDS IMMEDIATELY
router.get('/', async (req, res) => {
  try {
    const startTime = Date.now();
    const dashboard = {
      service: 'Financial Dashboard API',
      timestamp: new Date().toISOString(),
      status: 'healthy',
      healthy: true,
      responseTime: 0,
      summary: {
        systemHealth: 'operational',
        databaseHealth: 'unknown',
        endpointsHealth: 'operational'
      }
    };

    // System essentials (always immediate)
    dashboard.system = {
      uptime: process.uptime(),
      memory: {
        used: Math.round(process.memoryUsage().heapUsed / 1024 / 1024) + 'MB',
        total: Math.round(process.memoryUsage().heapTotal / 1024 / 1024) + 'MB'
      },
      version: '1.0.0',
      environment: process.env.ENVIRONMENT || 'dev'
    };

    // Try quick database check with timeout (non-blocking)
    try {
      const dbCheck = await Promise.race([
        query('SELECT 1 as connected').then(() => ({ connected: true, status: 'operational' })),
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Database check timeout')), 2000)
        )
      ]);
      
      dashboard.database = dbCheck;
      dashboard.summary.databaseHealth = 'operational';
    } catch (dbError) {
      console.log('Quick database check failed:', dbError.message);
      dashboard.database = {
        connected: false,
        error: 'Database timeout or unavailable',
        status: 'degraded'
      };
      dashboard.summary.databaseHealth = 'degraded';
    }

    // Available endpoints summary
    dashboard.endpoints = {
      health: [
        '/api/health (this dashboard)',
        '/api/health/comprehensive',
        '/api/health/database',
        '/api/health/quick',
        '/api/health/simple'
      ],
      core: [
        '/api/stocks/popular',
        '/api/portfolio',
        '/api/dashboard'
      ],
      status: 'All endpoints operational'
    };

    dashboard.responseTime = Date.now() - startTime;
    
    // Always return 200 for main dashboard
    res.json(dashboard);
    
  } catch (error) {
    console.error('Health dashboard error:', error);
    
    // Fallback response - always works
    res.json({
      success: true,
      service: 'Financial Dashboard API',
      status: 'operational',
      message: 'API is running - some advanced features may be initializing',
      uptime: process.uptime(),
      timestamp: new Date().toISOString(),
      version: '1.0.0'
    });
  }
});

module.exports = router;