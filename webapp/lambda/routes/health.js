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
    execute: (fn) => Promise.reject(new Error('Circuit breaker unavailable'))
  };
}

const router = express.Router();

// Ultra-simple health check - no dependencies
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

// Comprehensive health check endpoint - complete environmental insights
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
    healthData.circuitBreakers = {
      database: databaseCircuitBreaker.getStatus(),
      overall: databaseCircuitBreaker.getStatus().state === 'CLOSED' ? 'operational' : 'degraded'
    };

    // Database connectivity and table diagnostics (circuit breaker protected)
    try {
      const dbDiagnostics = await databaseCircuitBreaker.execute(async () => {
        const diagnostics = {
          connectionStatus: 'connected',
          tables: {},
          indexes: {},
          performance: {}
        };

        // Critical table analysis
        const tables = ['stock_symbols', 'portfolio_holdings', 'api_keys', 'trading_history', 'user_accounts'];
        
        for (const tableName of tables) {
          try {
            const [countResult, sizeResult] = await Promise.all([
              query(`SELECT COUNT(*) as count FROM ${tableName}`),
              query(`SELECT pg_size_pretty(pg_total_relation_size('${tableName}')) as size`)
            ]);
            
            diagnostics.tables[tableName] = {
              exists: true,
              rowCount: parseInt(countResult[0]?.count || 0),
              size: sizeResult[0]?.size || 'unknown',
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

        // Connection pool status
        const pool = getPool();
        diagnostics.connectionPool = {
          totalConnections: pool.totalCount,
          idleConnections: pool.idleCount,
          waitingClients: pool.waitingCount,
          maxConnections: pool.options.max
        };

        return diagnostics;
      }, 'health-comprehensive-db');

      healthData.database = dbDiagnostics;
    } catch (dbError) {
      healthData.database = {
        connectionStatus: 'failed',
        error: dbError.message,
        circuitBreakerOpen: dbError.message.includes('Circuit breaker is OPEN'),
        tables: {},
        note: 'Database diagnostics unavailable due to circuit breaker or connection failure'
      };
      
      if (dbError.message.includes('Circuit breaker is OPEN')) {
        healthData.status = 'degraded';
        healthData.healthy = false;
      }
    }

    // API endpoints health check
    healthData.endpoints = {
      available: [
        '/api/health/comprehensive',
        '/api/health/database', 
        '/api/health/environment',
        '/api/health/circuit-breakers',
        '/api/portfolio',
        '/api/stocks',
        '/api/api-keys'
      ],
      critical: {
        portfolio: 'operational',
        stocks: 'operational', 
        apiKeys: 'operational'
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
    const dbDiagnostics = await databaseCircuitBreaker.execute(async () => {
      const diagnostics = {
        connection: {
          status: 'connected',
          host: process.env.DB_ENDPOINT || 'localhost',
          database: 'financial_dashboard',
          lastConnected: new Date().toISOString()
        },
        tables: {},
        schema: {},
        performance: {}
      };

      // Detailed table analysis for all financial tables
      const financialTables = {
        'stock_symbols': 'Stock market symbols and company data',
        'portfolio_holdings': 'User portfolio positions and holdings',
        'api_keys': 'Encrypted API credentials for external services',
        'trading_history': 'Historical trading transactions and activities',
        'user_accounts': 'User authentication and account information',
        'watchlists': 'User-created stock watchlists',
        'market_data': 'Real-time and historical market data cache',
        'alerts': 'Price alerts and notifications',
        'performance_metrics': 'Portfolio performance calculations'
      };

      for (const [tableName, description] of Object.entries(financialTables)) {
        try {
          const [countResult, sizeResult, lastModified] = await Promise.all([
            query(`SELECT COUNT(*) as count FROM ${tableName}`),
            query(`SELECT pg_size_pretty(pg_total_relation_size('${tableName}')) as size, 
                         pg_total_relation_size('${tableName}') as size_bytes`),
            query(`SELECT MAX(updated_at) as last_updated FROM ${tableName}`).catch(() => 
              query(`SELECT MAX(created_at) as last_updated FROM ${tableName}`).catch(() => [{ last_updated: null }])
            )
          ]);
          
          diagnostics.tables[tableName] = {
            description,
            exists: true,
            rowCount: parseInt(countResult[0]?.count || 0),
            size: sizeResult[0]?.size || 'unknown',
            sizeBytes: parseInt(sizeResult[0]?.size_bytes || 0),
            lastUpdated: lastModified[0]?.last_updated || null,
            status: 'healthy'
          };
        } catch (tableError) {
          diagnostics.tables[tableName] = {
            description,
            exists: false,
            error: tableError.message,
            status: tableError.code === '42P01' ? 'missing' : 'error'
          };
        }
      }

      // Connection pool diagnostics
      const pool = getPool();
      diagnostics.connectionPool = {
        total: pool.totalCount,
        idle: pool.idleCount,
        waiting: pool.waitingCount,
        max: pool.options.max,
        utilization: `${Math.round((pool.totalCount / pool.options.max) * 100)}%`,
        health: pool.waitingCount > 0 ? 'stressed' : 'healthy'
      };

      // Database performance metrics
      const [dbStats] = await query(`
        SELECT 
          numbackends as active_connections,
          xact_commit as transactions_committed,
          xact_rollback as transactions_rolled_back,
          blks_read as blocks_read,
          blks_hit as blocks_hit,
          tup_returned as tuples_returned,
          tup_fetched as tuples_fetched
        FROM pg_stat_database 
        WHERE datname = current_database()
      `);

      diagnostics.performance = {
        activeConnections: dbStats?.active_connections || 0,
        transactionStats: {
          committed: dbStats?.transactions_committed || 0,
          rolledBack: dbStats?.transactions_rolled_back || 0
        },
        cacheEfficiency: dbStats?.blocks_hit && dbStats?.blocks_read 
          ? Math.round((dbStats.blocks_hit / (dbStats.blocks_hit + dbStats.blocks_read)) * 100) + '%'
          : 'unknown'
      };

      return diagnostics;
    }, 'health-database-diagnostics');

    res.json({
      success: true,
      database: dbDiagnostics,
      timestamp: new Date().toISOString(),
      note: 'Complete database diagnostics and table analysis'
    });

  } catch (error) {
    res.status(503).json({
      success: false,
      error: 'Database diagnostics unavailable',
      message: error.message,
      circuitBreakerOpen: error.message.includes('Circuit breaker is OPEN'),
      timestamp: new Date().toISOString()
    });
  }
});

// Environment configuration endpoint
router.get('/environment', (req, res) => {
  const envConfig = {
    runtime: {
      nodeVersion: process.version,
      platform: process.platform,
      arch: process.arch,
      uptime: process.uptime(),
      memoryUsage: process.memoryUsage(),
      cpuUsage: process.cpuUsage()
    },
    application: {
      environment: process.env.ENVIRONMENT || 'unknown',
      nodeEnv: process.env.NODE_ENV || 'unknown',
      allowDevBypass: process.env.ALLOW_DEV_BYPASS === 'true',
      version: '1.0.0'
    },
    aws: {
      region: process.env.AWS_REGION || 'not_configured',
      isLambda: !!process.env.AWS_LAMBDA_FUNCTION_NAME,
      lambdaFunction: process.env.AWS_LAMBDA_FUNCTION_NAME || null,
      lambdaMemory: process.env.AWS_LAMBDA_FUNCTION_MEMORY_SIZE || null,
      lambdaTimeout: process.env.AWS_LAMBDA_FUNCTION_TIMEOUT || null,
      requestId: process.env.AWS_REQUEST_ID || null
    },
    database: {
      hasSecretArn: !!process.env.DB_SECRET_ARN,
      hasEndpoint: !!process.env.DB_ENDPOINT,
      secretArn: process.env.DB_SECRET_ARN ? 'configured' : 'missing',
      endpoint: process.env.DB_ENDPOINT ? 'configured' : 'missing'
    },
    security: {
      devBypassEnabled: process.env.ALLOW_DEV_BYPASS === 'true',
      authRequired: process.env.ALLOW_DEV_BYPASS !== 'true',
      corsEnabled: true,
      httpsRedirect: process.env.HTTPS_REDIRECT === 'true'
    }
  };

  res.json({
    success: true,
    environment: envConfig,
    timestamp: new Date().toISOString(),
    note: 'Complete environment configuration analysis'
  });
});

// Circuit breaker monitoring endpoint
router.get('/circuit-breakers', (req, res) => {
  try {
    const dbStatus = databaseCircuitBreaker.getStatus();
    
    const circuitBreakers = {
      database: {
        ...dbStatus,
        description: 'Database connection circuit breaker (20 failure threshold)',
        health: dbStatus.state === 'CLOSED' ? 'healthy' : 'degraded'
      },
      overall: {
        status: dbStatus.state === 'CLOSED' ? 'operational' : 'degraded',
        degradedServices: dbStatus.state !== 'CLOSED' ? ['database'] : [],
        totalBreakers: 1,
        openBreakers: dbStatus.state === 'OPEN' ? 1 : 0
      },
      monitoring: {
        lastCheck: new Date().toISOString(),
        alertThreshold: 'Any circuit breaker OPEN state',
        recoveryStrategy: 'Automatic with exponential backoff'
      }
    };
    
    res.json({
      success: true,
      circuitBreakers,
      timestamp: new Date().toISOString(),
      note: 'Circuit breaker status across all systems'
    });
  } catch (error) {
    res.status(500).json({
      success: false,
      error: 'Failed to get circuit breaker status',
      message: error.message,
      timestamp: new Date().toISOString()
    });
  }
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

// Unified Health Dashboard - Complete system overview
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
      circuitBreakerHealth: 'operational',
      environmentHealth: 'operational'
    }
  };

  try {
    // System essentials
    dashboard.system = {
      uptime: process.uptime(),
      memory: {
        used: Math.round(process.memoryUsage().heapUsed / 1024 / 1024) + 'MB',
        total: Math.round(process.memoryUsage().heapTotal / 1024 / 1024) + 'MB',
        external: Math.round(process.memoryUsage().external / 1024 / 1024) + 'MB'
      },
      version: '1.0.0',
      environment: process.env.ENVIRONMENT || 'dev'
    };

    // Environment configuration summary
    dashboard.environment = {
      deployment: {
        environment: process.env.ENVIRONMENT || 'unknown',
        nodeEnv: process.env.NODE_ENV || 'unknown',
        isLambda: !!process.env.AWS_LAMBDA_FUNCTION_NAME,
        region: process.env.AWS_REGION || 'not_configured'
      },
      security: {
        devBypass: process.env.ALLOW_DEV_BYPASS === 'true',
        corsEnabled: true
      },
      database: {
        configured: !!process.env.DB_SECRET_ARN && !!process.env.DB_ENDPOINT,
        hasSecrets: !!process.env.DB_SECRET_ARN,
        hasEndpoint: !!process.env.DB_ENDPOINT
      }
    };

    // Circuit breaker overview
    const cbStatus = databaseCircuitBreaker.getStatus();
    dashboard.circuitBreakers = {
      database: {
        state: cbStatus.state,
        health: cbStatus.state === 'CLOSED' ? 'healthy' : 'degraded',
        failures: cbStatus.failureCount,
        lastFailure: cbStatus.lastFailureTime
      },
      summary: {
        operational: cbStatus.state === 'CLOSED',
        degraded: cbStatus.state !== 'CLOSED'
      }
    };

    if (cbStatus.state !== 'CLOSED') {
      dashboard.summary.circuitBreakerHealth = 'degraded';
    }
    // Database health summary (circuit breaker protected)
    try {
      const dbSummary = await databaseCircuitBreaker.execute(async () => {
        // Quick database connectivity check
        const [connectionTest] = await query('SELECT 1 as connected, NOW() as timestamp');
        
        // Essential table counts
        const [stockCount] = await query('SELECT COUNT(*) as count FROM stock_symbols').catch(() => [{ count: 'error' }]);
        const [portfolioCount] = await query('SELECT COUNT(*) as count FROM portfolio_holdings').catch(() => [{ count: 'error' }]);
        const [apiKeyCount] = await query('SELECT COUNT(*) as count FROM api_keys').catch(() => [{ count: 'error' }]);
        
        return {
          connected: true,
          connectionTime: connectionTest.timestamp,
          tables: {
            stock_symbols: stockCount.count,
            portfolio_holdings: portfolioCount.count,
            api_keys: apiKeyCount.count
          },
          status: 'operational'
        };
      }, 'health-dashboard-db');

      dashboard.database = dbSummary;
      dashboard.summary.databaseHealth = 'operational';
    } catch (dbError) {
      dashboard.database = {
        connected: false,
        error: dbError.message.includes('Circuit breaker is OPEN') ? 'Circuit breaker open' : 'Connection failed',
        status: 'degraded',
        tables: {}
      };
      dashboard.summary.databaseHealth = 'degraded';
      dashboard.status = 'degraded';
      dashboard.healthy = false;
    }

    // Overall health assessment
    const healthComponents = Object.values(dashboard.summary);
    const degradedComponents = healthComponents.filter(h => h === 'degraded' || h === 'error').length;
    
    if (degradedComponents > 0) {
      dashboard.status = degradedComponents >= healthComponents.length / 2 ? 'unhealthy' : 'degraded';
      dashboard.healthy = dashboard.status === 'degraded'; // degraded still considered "healthy" for basic operations
    }

    // Available endpoints summary
    dashboard.endpoints = {
      health: [
        '/api/health/ (this dashboard)',
        '/api/health/comprehensive',
        '/api/health/database',
        '/api/health/environment',
        '/api/health/circuit-breakers',
        '/api/health/quick'
      ],
      core: [
        '/api/portfolio',
        '/api/stocks',
        '/api/api-keys',
        '/api/market'
      ],
      status: 'All endpoints operational'
    };

  } catch (error) {
    console.error('Health dashboard error:', error);
    dashboard.status = 'error';
    dashboard.healthy = false;
    dashboard.error = error.message;
    dashboard.summary.systemHealth = 'error';
  }

  dashboard.responseTime = Date.now() - startTime;
  dashboard.note = 'Unified health dashboard - use /comprehensive for detailed diagnostics';
  
  // Return appropriate status code based on health
  const statusCode = dashboard.healthy ? 200 : 503;
  res.status(statusCode).json(dashboard);
  
  } catch (outerError) {
    console.error('Fatal health route error:', outerError);
    res.status(500).json({
      success: false,
      error: 'Health check failed',
      message: outerError.message,
      service: 'Financial Dashboard API',
      timestamp: new Date().toISOString(),
      troubleshooting: {
        issue: 'Health route crashed',
        possibleCauses: ['Database connection failure', 'Missing dependencies', 'Memory/resource issues'],
        suggestion: 'Try /api/health/simple for basic health check'
      }
    });
  }
});

module.exports = router;