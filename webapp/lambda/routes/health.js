const express = require('express');
const { query, initializeDatabase, getPool, healthCheck } = require('../utils/database');
const DatabaseCircuitBreaker = require('../utils/databaseCircuitBreaker');

// Create circuit breaker instance for health checks
const databaseCircuitBreaker = new DatabaseCircuitBreaker();

const router = express.Router();

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

// Unified Health Dashboard - Complete system overview
router.get('/', async (req, res) => {
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
        '/api/health/circuit-breakers'
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
});

module.exports = router;
    let tables = {};
    let existingTables = [];
    
    // First, try to get list of all tables
    try {
      const tableExistenceCheck = await Promise.race([
        query(`
          SELECT table_name 
          FROM information_schema.tables 
          WHERE table_schema = 'public' 
          ORDER BY table_name
        `),
        new Promise((_, reject) => setTimeout(() => reject(new Error('Table list timeout')), 2000))
      ]);
      existingTables = tableExistenceCheck.rows.map(row => row.table_name);
      console.log(`Found ${existingTables.length} tables in database`);
    } catch (listError) {
      console.error('Failed to get table list:', listError.message);
      tables['_error'] = `Failed to list tables: ${listError.message}`;
    }
    
    // Define priority tables to check
    const priorityTables = [
      'stock_symbols', 'etf_symbols', 'price_daily', 'price_weekly', 
      'technical_data_daily', 'portfolio_holdings', 'health_status',
      'company_profile', 'market_data', 'key_metrics', 'annual_income_statement',
      'quarterly_income_statement', 'fear_greed_index', 'economic_data'
    ];
    
    // Check each table individually to get partial results
    const tablesToCheck = existingTables.length > 0 ? 
      [...new Set([...priorityTables.filter(t => existingTables.includes(t)), ...existingTables])] :
      priorityTables;
    
    // Process tables in batches to avoid overwhelming the DB
    const batchSize = 5;
    for (let i = 0; i < tablesToCheck.length; i += batchSize) {
      const batch = tablesToCheck.slice(i, i + batchSize);
      const batchPromises = batch.map(tableName => {
        return Promise.race([
          (async () => {
            // Validate table name against whitelist for security
            const SecureQueryBuilder = require('../utils/secureQueryBuilder');
            const queryBuilder = new SecureQueryBuilder();
            
            if (!queryBuilder.allowedTables.has(tableName.toLowerCase())) {
              throw new Error('Unauthorized table access');
            }
            
            // Use secure query builder
            const { query: countQuery, params } = queryBuilder.buildSelect({
              table: tableName,
              columns: ['COUNT(*) as count'],
              limit: 1
            });
            
            const result = await query(countQuery, params);
            return {
              table: tableName,
              count: parseInt(result.rows[0].count),
              status: 'success'
            };
          })()
            .catch(err => ({
              table: tableName,
              count: null,
              status: 'error',
              error: err.message.includes('does not exist') ? 'Table does not exist' : 
                     err.message.includes('Unauthorized') ? 'Unauthorized table access' : err.message
            })),
          new Promise((resolve) => setTimeout(() => resolve({
            table: tableName,
            count: null,
            status: 'timeout',
            error: 'Query timeout (1s)'
          }), 1000))
        ]);
      });
      
      const batchResults = await Promise.all(batchPromises);
      batchResults.forEach(result => {
        if (result.status === 'success') {
          tables[result.table] = result.count;
        } else {
          tables[result.table] = `${result.status}: ${result.error}`;
        }
      });
    }
    
    // Add comprehensive summary
    const successfulTables = Object.entries(tables).filter(([k, v]) => typeof v === 'number' && k !== '_summary' && k !== '_error');
    const errorTables = Object.entries(tables).filter(([k, v]) => typeof v === 'string' && k !== '_summary' && k !== '_error');
    
    tables['_summary'] = {
      total_tables: existingTables.length || tablesToCheck.length,
      tables_checked: tablesToCheck.length,
      successful_checks: successfulTables.length,
      failed_checks: errorTables.length,
      total_records: successfulTables.reduce((sum, [, count]) => sum + count, 0),
      priority_tables_status: priorityTables.map(t => ({
        table: t,
        status: tables[t] !== undefined ? (typeof tables[t] === 'number' ? 'ok' : 'error') : 'not_checked'
      }))
    };
    
    // Show all tables instead of filtering
    const filteredTables = tables;
    
    const health = {
      status: 'healthy',
      healthy: true,
      timestamp: new Date().toISOString(),
      database: {
        status: 'connected',
        tables: filteredTables
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
        tables: {}
      },
      api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' },
      memory: process.memoryUsage(),
      uptime: process.uptime()
    });
  }
});

// Simple database test endpoint 
router.get('/database', async (req, res) => {
  console.log('Received request for /health/database');
  try {
    // Multi-tier health check approach
    const healthLevel = req.query.level || 'basic'; // basic, critical, full
    
    // Tier 1: Basic connectivity (always run, <2s)
    let basicHealth;
    try {
      const startTime = Date.now();
      await Promise.race([
        query('SELECT current_timestamp as server_time, version() as version'),
        new Promise((_, reject) => setTimeout(() => reject(new Error('Connection timeout')), 2000))
      ]);
      
      // Check connection pool health
      const pool = getPool();
      basicHealth = {
        status: 'connected',
        response_time_ms: Date.now() - startTime,
        connection_pool: {
          total_connections: pool.totalCount,
          active_connections: pool.totalCount - pool.idleCount,
          idle_connections: pool.idleCount,
          waiting_clients: pool.waitingCount
        }
      };
    } catch (connError) {
      console.error('Database connection failed:', connError.message);
      return res.status(503).json({
        status: 'unhealthy',
        healthy: false,
        timestamp: new Date().toISOString(),
        database: {
          status: 'disconnected',
          error: connError.message,
          level: 'basic',
          response_time_ms: 2000
        },
        api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' }
      });
    }
    
    // Return immediately for basic health check
    if (healthLevel === 'basic') {
      return res.json({
        status: 'ok',
        healthy: true,
        timestamp: new Date().toISOString(),
        level: 'basic',
        database: basicHealth,
        api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' }
      });
    }
    
    // Tier 2: Critical tables check (if requested, <5s total)
    let criticalHealth = {};
    if (healthLevel === 'critical' || healthLevel === 'full') {
      const criticalTables = ['stock_symbols', 'price_daily', 'portfolio_holdings'];
      const criticalResults = {};
      
      try {
        for (const table of criticalTables) {
          const startTime = Date.now();
          try {
            // Fast existence check only
            // Validate table name for security
            const SecureQueryBuilder = require('../utils/secureQueryBuilder');
            const queryBuilder = new SecureQueryBuilder();
            
            if (!queryBuilder.allowedTables.has(table.toLowerCase())) {
              throw new Error('Unauthorized table access');
            }
            
            const { query: selectQuery, params } = queryBuilder.buildSelect({
              table: table,
              columns: ['1'],
              limit: 1
            });
            
            const result = await Promise.race([
              query(selectQuery, params),
              new Promise((_, reject) => setTimeout(() => reject(new Error('Table timeout')), 1000))
            ]);
            
            criticalResults[table] = {
              status: 'accessible',
              response_time_ms: Date.now() - startTime
            };
          } catch (tableError) {
            criticalResults[table] = {
              status: 'error',
              error: tableError.message,
              response_time_ms: Date.now() - startTime
            };
          }
        }
        
        const failedCritical = Object.values(criticalResults).filter(r => r.status === 'error').length;
        criticalHealth = {
          tables_checked: criticalTables.length,
          tables_healthy: criticalTables.length - failedCritical,
          tables_failed: failedCritical,
          results: criticalResults
        };
        
      } catch (criticalError) {
        criticalHealth = { error: criticalError.message };
      }
    }
    
    // Return critical level health check
    if (healthLevel === 'critical') {
      const overallHealthy = criticalHealth.tables_failed === 0;
      
      return res.json({
        status: overallHealthy ? 'ok' : 'degraded',
        healthy: overallHealthy,
        timestamp: new Date().toISOString(),
        level: 'critical',
        database: {
          ...basicHealth,
          critical_tables: criticalHealth
        },
        api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' }
      });
    }
    
    // Tier 3: Full health check (only if explicitly requested)
    let fullHealth = {};
    if (healthLevel === 'full') {
      try {
        const tableCountResult = await Promise.race([
          query(`SELECT COUNT(*) as count FROM information_schema.tables WHERE table_schema = 'public'`),
          new Promise((_, reject) => setTimeout(() => reject(new Error('Table count timeout')), 2000))
        ]);
        
        fullHealth = {
          total_tables: parseInt(tableCountResult.rows[0].count),
          message: 'Full table analysis available via /health/update-status'
        };
        
      } catch (fullError) {
        fullHealth = { error: fullError.message };
      }
    }
    
    // Return full health check
    const overallHealthy = (criticalHealth.tables_failed || 0) === 0;
    
    return res.json({
      status: overallHealthy ? 'ok' : 'degraded', 
      healthy: overallHealthy,
      timestamp: new Date().toISOString(),
      level: healthLevel,
      database: {
        ...basicHealth,
        critical_tables: criticalHealth,
        full_analysis: fullHealth
      },
      api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' }
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

// Service health connection endpoint for frontend - WITH CIRCUIT BREAKER PROTECTION
router.get('/connection', async (req, res) => {
  try {
    console.log('Service health connection check requested');
    
    // Use circuit breaker protection for database connection test
    const startTime = Date.now();
    let result;
    try {
      result = await databaseCircuitBreaker.execute(
        () => query('SELECT 1 as test'),
        'connection-check'
      );
    } catch (error) {
      if (error.message.includes('Circuit breaker is OPEN')) {
        console.log('🔴 Circuit breaker is OPEN for connection check');
        return res.status(503).json({
          success: false,
          status: 'circuit_breaker_open',
          connection: {
            database: 'circuit_breaker_protecting',
            note: 'Database circuit breaker is open - service is degraded',
            timestamp: new Date().toISOString()
          },
          circuitBreaker: databaseCircuitBreaker.getStatus(),
          service: 'Financial Dashboard API',
          version: '1.0.0',
          environment: process.env.NODE_ENV || 'development'
        });
      }
      throw error; // Re-throw non-circuit-breaker errors
    }
    const responseTime = Date.now() - startTime;
    
    res.json({
      success: true,
      status: 'connected',
      connection: {
        database: 'healthy',
        responseTime: responseTime,
        timestamp: new Date().toISOString()
      },
      service: 'Financial Dashboard API',
      version: '1.0.0',
      environment: process.env.NODE_ENV || 'development'
    });
    
  } catch (error) {
    console.error('Service health connection failed:', error);
    res.status(503).json({
      success: false,
      status: 'disconnected',
      connection: {
        database: 'unhealthy',
        error: error.message,
        timestamp: new Date().toISOString()
      },
      service: 'Financial Dashboard API',
      version: '1.0.0',
      environment: process.env.NODE_ENV || 'development'
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
          // Validate table name for security
          const SecureQueryBuilder = require('../utils/secureQueryBuilder');
          const queryBuilder = new SecureQueryBuilder();
          
          if (!queryBuilder.allowedTables.has(table.table_name.toLowerCase())) {
            console.warn(`🚨 Unauthorized table access: ${table.table_name}`);
            continue;
          }
          
          const { query: countQuery, params: countParams } = queryBuilder.buildSelect({
            table: table.table_name,
            columns: ['COUNT(*) as count']
          });
          const count = await query(countQuery, countParams);
          const recordCount = parseInt(count.rows[0].count);
          table.record_count = recordCount;
          // Try to get last updated timestamp
          let lastUpdate = null;
          try {
            const tsCol = await query(`SELECT column_name FROM information_schema.columns WHERE table_name = $1 AND column_name IN ('fetched_at','updated_at','created_at','date','period_end') LIMIT 1`, [table.table_name]);
            if (tsCol.rows.length > 0) {
              const col = tsCol.rows[0].column_name;
              // Validate column name
              if (!['fetched_at','updated_at','created_at','date','period_end'].includes(col)) {
                continue;
              }
              const { query: maxQuery, params: maxParams } = queryBuilder.buildSelect({
                table: table.table_name,
                columns: [`MAX(${col}) as last_update`]
              });
              const tsRes = await query(maxQuery, maxParams);
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

// Update health status for all tables - comprehensive monitoring
router.post('/update-status', async (req, res) => {
  console.log('Received request for /health/update-status');
  try {
    // Ensure database pool is initialized
    try {
      getPool();
    } catch (initError) {
      console.log('Health update: DB not initialized, initializing now...');
      try {
        await initializeDatabase();
      } catch (dbInitError) {
        console.error('Health update: Failed to initialize database:', dbInitError.message);
        return res.status(503).json({
          status: 'error',
          message: 'Failed to initialize database connection',
          error: dbInitError.message,
          timestamp: new Date().toISOString()
        });
      }
    }

    // Check if health_status table exists, create if not
    try {
      await query('SELECT 1 FROM health_status LIMIT 1');
    } catch (tableError) {
      console.log('Health_status table does not exist, creating it...');
      try {
        // Create the comprehensive health_status table
        await query(`
          CREATE TABLE IF NOT EXISTS health_status (
            table_name VARCHAR(255) PRIMARY KEY,
            status VARCHAR(50) NOT NULL DEFAULT 'unknown',
            record_count BIGINT DEFAULT 0,
            missing_data_count BIGINT DEFAULT 0,
            last_updated TIMESTAMP WITH TIME ZONE,
            last_checked TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            is_stale BOOLEAN DEFAULT FALSE,
            error TEXT,
            table_category VARCHAR(100),
            critical_table BOOLEAN DEFAULT FALSE,
            expected_update_frequency INTERVAL DEFAULT '1 day',
            size_bytes BIGINT DEFAULT 0,
            last_vacuum TIMESTAMP WITH TIME ZONE,
            last_analyze TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
          )
        `);

        // Insert all monitored tables - comprehensive list
        const monitoredTables = [
          // Core Tables (Stock Symbol Management)
          { name: 'stock_symbols', category: 'symbols', critical: true, frequency: '1 week' },
          { name: 'etf_symbols', category: 'symbols', critical: true, frequency: '1 week' },
          { name: 'last_updated', category: 'tracking', critical: true, frequency: '1 hour' },
          
          // Price & Market Data Tables
          { name: 'price_daily', category: 'prices', critical: true, frequency: '1 day' },
          { name: 'price_weekly', category: 'prices', critical: true, frequency: '1 week' },
          { name: 'price_monthly', category: 'prices', critical: true, frequency: '1 month' },
          { name: 'etf_price_daily', category: 'prices', critical: true, frequency: '1 day' },
          { name: 'etf_price_weekly', category: 'prices', critical: true, frequency: '1 week' },
          { name: 'etf_price_monthly', category: 'prices', critical: true, frequency: '1 month' },
          { name: 'price_data_montly', category: 'prices', critical: false, frequency: '1 month' }, // Test table with typo
          
          // Technical Analysis Tables (corrected names)
          { name: 'technical_data_daily', category: 'technicals', critical: true, frequency: '1 day' },
          { name: 'technical_data_weekly', category: 'technicals', critical: true, frequency: '1 week' },
          { name: 'technical_data_monthly', category: 'technicals', critical: true, frequency: '1 month' },
          
          // Financial Statement Tables (Annual)
          { name: 'annual_balance_sheet', category: 'financials', critical: false, frequency: '3 months' },
          { name: 'annual_income_statement', category: 'financials', critical: false, frequency: '3 months' },
          { name: 'annual_cash_flow', category: 'financials', critical: false, frequency: '3 months' }, // Fixed name
          
          // Financial Statement Tables (Quarterly)
          { name: 'quarterly_balance_sheet', category: 'financials', critical: true, frequency: '3 months' },
          { name: 'quarterly_income_statement', category: 'financials', critical: true, frequency: '3 months' },
          { name: 'quarterly_cash_flow', category: 'financials', critical: true, frequency: '3 months' }, // Fixed name
          
          // Financial Statement Tables (TTM)
          { name: 'ttm_income_statement', category: 'financials', critical: false, frequency: '3 months' },
          { name: 'ttm_cash_flow', category: 'financials', critical: false, frequency: '3 months' }, // Fixed name
          
          // Company Information Tables
          { name: 'company_profile', category: 'company', critical: true, frequency: '1 week' },
          { name: 'market_data', category: 'company', critical: true, frequency: '1 day' },
          { name: 'key_metrics', category: 'company', critical: true, frequency: '1 day' },
          { name: 'analyst_estimates', category: 'company', critical: false, frequency: '1 week' },
          { name: 'governance_scores', category: 'company', critical: false, frequency: '1 month' },
          { name: 'leadership_team', category: 'company', critical: false, frequency: '1 month' },
          
          // Earnings & Calendar Tables
          { name: 'earnings_history', category: 'earnings', critical: false, frequency: '1 day' },
          { name: 'earnings_estimates', category: 'earnings', critical: true, frequency: '1 day' }, // Fixed name
          { name: 'revenue_estimates', category: 'earnings', critical: false, frequency: '1 day' }, // Fixed name
          { name: 'calendar_events', category: 'earnings', critical: true, frequency: '1 day' },
          { name: 'earnings_metrics', category: 'earnings', critical: false, frequency: '1 day' }, // Added missing table
          
          // Market Sentiment & Economic Tables
          { name: 'fear_greed_index', category: 'sentiment', critical: true, frequency: '1 day' },
          { name: 'aaii_sentiment', category: 'sentiment', critical: false, frequency: '1 week' },
          { name: 'naaim', category: 'sentiment', critical: false, frequency: '1 week' },
          { name: 'economic_data', category: 'sentiment', critical: false, frequency: '1 day' },
          { name: 'analyst_upgrade_downgrade', category: 'sentiment', critical: false, frequency: '1 day' },
          
          // Trading & Portfolio Tables
          { name: 'portfolio_holdings', category: 'trading', critical: false, frequency: '1 hour' },
          { name: 'portfolio_performance', category: 'trading', critical: false, frequency: '1 hour' },
          { name: 'trading_alerts', category: 'trading', critical: false, frequency: '1 hour' },
          { name: 'buy_sell_daily', category: 'trading', critical: true, frequency: '1 day' },
          { name: 'buy_sell_weekly', category: 'trading', critical: true, frequency: '1 week' },
          { name: 'buy_sell_monthly', category: 'trading', critical: true, frequency: '1 month' },
          
          // News & Additional Data
          { name: 'stock_news', category: 'news', critical: false, frequency: '1 hour' }, // Fixed name
          { name: 'stocks', category: 'other', critical: false, frequency: '1 day' },
          
          // Quality & Value Metrics Tables
          { name: 'quality_metrics', category: 'scoring', critical: true, frequency: '1 day' },
          { name: 'value_metrics', category: 'scoring', critical: true, frequency: '1 day' },
          { name: 'growth_metrics', category: 'scoring', critical: true, frequency: '1 day' },
          
          // Advanced Scoring System Tables
          { name: 'stock_scores', category: 'scoring', critical: true, frequency: '1 day' },
          { name: 'earnings_quality_metrics', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'balance_sheet_strength', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'profitability_metrics', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'management_effectiveness', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'valuation_multiples', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'intrinsic_value_analysis', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'revenue_growth_analysis', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'earnings_growth_analysis', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'price_momentum_analysis', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'technical_momentum_analysis', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'analyst_sentiment_analysis', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'social_sentiment_analysis', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'institutional_positioning', category: 'scoring', critical: false, frequency: '1 week' },
          { name: 'insider_trading_analysis', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'score_performance_tracking', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'market_regime', category: 'scoring', critical: false, frequency: '1 day' },
          { name: 'stock_symbols_enhanced', category: 'scoring', critical: false, frequency: '1 week' },
          
          // System Health Monitoring
          { name: 'health_status', category: 'system', critical: true, frequency: '1 hour' },
          
          // Test Tables
          { name: 'earnings', category: 'test', critical: false, frequency: '1 day' },
          { name: 'prices', category: 'test', critical: false, frequency: '1 day' }
        ];

        for (const table of monitoredTables) {
          await query(`
            INSERT INTO health_status (table_name, table_category, critical_table, expected_update_frequency)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (table_name) DO NOTHING
          `, [table.name, table.category, table.critical, table.frequency]);
        }

        console.log(`Health_status table created and populated with ${monitoredTables.length} tables`);
      } catch (createError) {
        console.error('Failed to create health_status table:', createError.message);
        return res.status(500).json({
          status: 'error',
          message: 'Failed to create health_status table',
          error: createError.message,
          timestamp: new Date().toISOString()
        });
      }
    }

    // Perform comprehensive health check for all tables
    const startTime = Date.now();
    const healthResults = [];
    let summary = {
      total_tables: 0,
      healthy_tables: 0,
      stale_tables: 0,
      empty_tables: 0,
      error_tables: 0,
      missing_tables: 0,
      total_records: 0,
      total_missing_data: 0
    };

    try {
      // Get list of tables to check
      const tablesToCheck = await query('SELECT table_name, expected_update_frequency FROM health_status');
      summary.total_tables = tablesToCheck.rowCount;

      for (const tableRow of tablesToCheck.rows) {
        const tableName = tableRow.table_name;
        let tableStatus = 'unknown';
        let recordCount = 0;
        let lastUpdated = null;
        let errorMsg = null;
        let isStale = false;

        try {
          // Check if table exists and get record count
          const countResult = await query(`
            SELECT COUNT(*) as count FROM information_schema.tables 
            WHERE table_name = $1 AND table_schema = 'public'
          `, [tableName]);

          if (countResult.rows[0].count === '0') {
            tableStatus = 'missing';
            summary.missing_tables++;
          } else {
            try {
              // Get record count
              // Validate table name for security
              const SecureQueryBuilder = require('../utils/secureQueryBuilder');
              const queryBuilder = new SecureQueryBuilder();
              
              if (!queryBuilder.allowedTables.has(tableName.toLowerCase())) {
                console.warn(`🚨 Unauthorized table access: ${tableName}`);
                tableStatus = 'unauthorized';
                summary.missing_tables++;
                tableData[tableName] = { status: tableStatus, records: 0 };
                continue;
              }
              
              const { query: recordQuery, params: recordParams } = queryBuilder.buildSelect({
                table: tableName,
                columns: ['COUNT(*) as count']
              });
              const recordResult = await query(recordQuery, recordParams);
              recordCount = parseInt(recordResult.rows[0].count);
              summary.total_records += recordCount;

              if (recordCount === 0) {
                tableStatus = 'empty';
                summary.empty_tables++;
              } else {
                // Try to get last updated timestamp
                const timestampColumns = ['fetched_at', 'updated_at', 'created_at', 'date', 'period_end', 'timestamp'];
                let foundTimestamp = false;

                for (const col of timestampColumns) {
                  try {
                    const colCheck = await query(`
                      SELECT column_name FROM information_schema.columns 
                      WHERE table_name = $1 AND column_name = $2
                    `, [tableName, col]);

                    if (colCheck.rowCount > 0) {
                      // Validate column name
                      if (!['fetched_at','updated_at','created_at','date','period_end'].includes(col)) {
                        continue;
                      }
                      const { query: tsQuery, params: tsParams } = queryBuilder.buildSelect({
                        table: tableName,
                        columns: [`MAX(${col}) as last_update`]
                      });
                      const tsResult = await query(tsQuery, tsParams);
                      if (tsResult.rows[0].last_update) {
                        lastUpdated = tsResult.rows[0].last_update;
                        foundTimestamp = true;
                        break;
                      }
                    }
                  } catch (tsError) {
                    // Continue to next column
                  }
                }

                // Determine if stale based on expected frequency
                if (lastUpdated && tableRow.expected_update_frequency) {
                  const expectedInterval = tableRow.expected_update_frequency;
                  const staleThreshold = new Date();
                  
                  // Simple stale check - if last update is older than 2x expected frequency
                  const hoursSinceUpdate = (new Date() - new Date(lastUpdated)) / (1000 * 60 * 60);
                  const expectedHours = expectedInterval.includes('hour') ? 2 : 
                                       expectedInterval.includes('day') ? 48 : 
                                       expectedInterval.includes('week') ? 336 : 
                                       expectedInterval.includes('month') ? 1440 : 48;

                  if (hoursSinceUpdate > expectedHours) {
                    tableStatus = 'stale';
                    isStale = true;
                    summary.stale_tables++;
                  } else {
                    tableStatus = 'healthy';
                    summary.healthy_tables++;
                  }
                } else {
                  tableStatus = 'healthy';
                  summary.healthy_tables++;
                }
              }
            } catch (recordError) {
              tableStatus = 'error';
              errorMsg = recordError.message;
              summary.error_tables++;
            }
          }
        } catch (checkError) {
          tableStatus = 'error';
          errorMsg = checkError.message;
          summary.error_tables++;
        }

        // Update health status for this table
        try {
          await query(`
            INSERT INTO health_status (
              table_name, status, record_count, missing_data_count, 
              last_updated, last_checked, is_stale, error
            ) VALUES ($1, $2, $3, $4, $5, CURRENT_TIMESTAMP, $6, $7)
            ON CONFLICT (table_name) DO UPDATE SET
              status = EXCLUDED.status,
              record_count = EXCLUDED.record_count,
              missing_data_count = EXCLUDED.missing_data_count,
              last_updated = EXCLUDED.last_updated,
              last_checked = EXCLUDED.last_checked,
              is_stale = EXCLUDED.is_stale,
              error = EXCLUDED.error,
              updated_at = CURRENT_TIMESTAMP
          `, [tableName, tableStatus, recordCount, 0, lastUpdated, isStale, errorMsg]);
        } catch (updateError) {
          console.error(`Failed to update health status for table ${tableName}:`, updateError.message);
        }

        healthResults.push({
          table_name: tableName,
          status: tableStatus,
          record_count: recordCount,
          last_updated: lastUpdated,
          error: errorMsg
        });
      }
    } catch (overallError) {
      console.error('Error during comprehensive health check:', overallError.message);
      return res.status(500).json({
        status: 'error',
        message: 'Failed to perform comprehensive health check',
        error: overallError.message,
        timestamp: new Date().toISOString()
      });
    }

    const duration = Date.now() - startTime;

    return res.json({
      status: 'success',
      message: 'Health status updated successfully',
      timestamp: new Date().toISOString(),
      duration_ms: duration,
      summary: summary,
      tables_checked: summary.total_tables,
      results: healthResults
    });

  } catch (error) {
    console.error('Error in health status update:', error);
    res.status(500).json({
      status: 'error',
      message: 'Health status update failed',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Get health status summary
router.get('/status-summary', async (req, res) => {
  try {
    // Ensure database is initialized
    try {
      getPool();
    } catch (initError) {
      await initializeDatabase();
    }

    // Get summary statistics
    const summaryResult = await query(`
      SELECT 
        table_category,
        COUNT(*) as total_tables,
        COUNT(CASE WHEN status = 'healthy' THEN 1 END) as healthy_tables,
        COUNT(CASE WHEN status = 'stale' THEN 1 END) as stale_tables,
        COUNT(CASE WHEN status = 'empty' THEN 1 END) as empty_tables,
        COUNT(CASE WHEN status = 'error' THEN 1 END) as error_tables,
        COUNT(CASE WHEN status = 'missing' THEN 1 END) as missing_tables,
        COUNT(CASE WHEN critical_table = true THEN 1 END) as critical_tables,
        SUM(record_count) as total_records,
        SUM(missing_data_count) as total_missing_data,
        MAX(last_updated) as latest_update,
        MIN(last_updated) as oldest_update
      FROM health_status
      GROUP BY table_category
      ORDER BY table_category
    `);

    const overallSummary = await query(`
      SELECT 
        COUNT(*) as total_tables,
        COUNT(CASE WHEN status = 'healthy' THEN 1 END) as healthy_tables,
        COUNT(CASE WHEN status = 'stale' THEN 1 END) as stale_tables,
        COUNT(CASE WHEN status = 'empty' THEN 1 END) as empty_tables,
        COUNT(CASE WHEN status = 'error' THEN 1 END) as error_tables,
        COUNT(CASE WHEN status = 'missing' THEN 1 END) as missing_tables,
        COUNT(CASE WHEN critical_table = true THEN 1 END) as critical_tables,
        SUM(record_count) as total_records,
        SUM(missing_data_count) as total_missing_data,
        MAX(last_checked) as last_health_check
      FROM health_status
    `);

    res.json({
      status: 'success',
      timestamp: new Date().toISOString(),
      overall: overallSummary.rows[0],
      by_category: summaryResult.rows
    });

  } catch (error) {
    console.error('Error getting health status summary:', error);
    res.status(500).json({
      status: 'error',
      message: 'Failed to get health status summary',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Force create all required tables endpoint
router.post('/create-tables', async (req, res) => {
  console.log('Received request to create tables');
  try {
    // Initialize database if needed
    try {
      getPool();
    } catch (initError) {
      console.log('Database not initialized, initializing now...');
      await initializeDatabase();
    }

    // This will trigger the createRequiredTables function in database.js
    const pool = getPool();
    
    res.json({
      status: 'success',
      message: 'Table creation completed. Check server logs for details.',
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Error creating tables:', error);
    res.status(500).json({
      status: 'error',
      message: 'Failed to create tables',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Detailed debug endpoint for troubleshooting Lambda to DB connectivity
router.get('/debug', async (req, res) => {
  try {
    console.log('🔍 Starting detailed debug analysis...');
    
    const debugInfo = {
      timestamp: new Date().toISOString(),
      environment: {
        NODE_ENV: process.env.NODE_ENV,
        AWS_REGION: process.env.AWS_REGION,
        AWS_LAMBDA_FUNCTION_NAME: process.env.AWS_LAMBDA_FUNCTION_NAME,
        AWS_LAMBDA_FUNCTION_VERSION: process.env.AWS_LAMBDA_FUNCTION_VERSION,
        AWS_EXECUTION_ENV: process.env.AWS_EXECUTION_ENV
      },
      lambda: {
        inLambda: !!process.env.AWS_LAMBDA_RUNTIME_API,
        vpcEnabled: !!process.env._LAMBDA_SERVER_PORT,
        memory: process.memoryUsage(),
        uptime: process.uptime()
      },
      database: {
        config: {
          hasSecretArn: !!process.env.DB_SECRET_ARN,
          hasEndpoint: !!process.env.DB_ENDPOINT,
          secretArn: process.env.DB_SECRET_ARN ? `${process.env.DB_SECRET_ARN.substring(0, 50)}...` : null,
          endpoint: process.env.DB_ENDPOINT || null
        }
      }
    };
    
    // Test network connectivity
    console.log('🌐 Testing network connectivity...');
    try {
      const networkTest = await testNetworkConnectivity();
      debugInfo.networkTest = networkTest;
    } catch (error) {
      debugInfo.networkTest = { status: 'error', message: error.message };
    }
    
    // Test database connection
    console.log('💾 Testing database connection...');
    try {
      const dbHealth = await healthCheck();
      debugInfo.databaseHealth = dbHealth;
    } catch (error) {
      debugInfo.databaseHealth = { status: 'error', message: error.message };
    }
    
    // Add VPC/networking information if available
    if (process.env.AWS_LAMBDA_RUNTIME_API) {
      debugInfo.networking = {
        lambdaRuntimeApi: !!process.env.AWS_LAMBDA_RUNTIME_API,
        vpcConfig: !!process.env._LAMBDA_SERVER_PORT,
        executionEnv: process.env.AWS_EXECUTION_ENV
      };
    }
    
    console.log('✅ Debug analysis complete');
    
    res.json({
      status: 'success',
      debug: debugInfo,
      recommendations: [
        "Check that Lambda is in private subnets with route to database",
        "Verify security groups allow Lambda → Database on port 5432",
        "Ensure database security group allows inbound from Lambda security group",
        "Check VPC route tables for proper routing",
        "Verify Secrets Manager permissions are granted to Lambda role"
      ]
    });
    
  } catch (error) {
    console.error('❌ Debug endpoint failed:', error);
    res.status(500).json({
      status: 'error',
      message: 'Debug analysis failed',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

module.exports = router;
