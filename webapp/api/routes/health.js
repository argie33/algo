const express = require('express');
const { healthCheck, query, validateDatabaseSchema, REQUIRED_SCHEMA } = require('../utils/database');
const apiKeyService = require('../utils/apiKeyServiceResilient');
const AlpacaService = require('../utils/alpacaService');
const timeoutHelper = require('../utils/timeoutHelper');
const schemaValidator = require('../utils/schemaValidator');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const { CognitoIdentityProviderClient, DescribeUserPoolCommand } = require('@aws-sdk/client-cognito-identity-provider');
const crypto = require('crypto');

const router = express.Router();

// Infrastructure health check - tests database connectivity only
router.get('/', async (req, res) => {
  const startTime = Date.now();
  const maxTimeout = 10000; // 10 second max timeout
  
  try {
    // Quick health check without database
    if (req.query.quick === 'true') {
      return res.success({
        status: 'healthy',
        healthy: true,
        service: 'Financial Dashboard API',
        environment: process.env.ENVIRONMENT || 'dev',
        memory: process.memoryUsage(),
        uptime: process.uptime(),
        note: 'Quick infrastructure check - database not tested',
        database: { status: 'not_tested' },
        api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' },
        config: {
          hasDbSecret: !!process.env.DB_SECRET_ARN,
          hasDbEndpoint: !!process.env.DB_ENDPOINT,
          hasAwsRegion: !!process.env.AWS_REGION
        }
      });
    }

    // Full health check with timeout protection
    const dbHealthPromise = getComprehensiveDbHealth();
    const timeoutPromise = new Promise((_, reject) => 
      setTimeout(() => reject(new Error('Health check timeout')), maxTimeout)
    );
    
    const dbHealth = await Promise.race([dbHealthPromise, timeoutPromise]);
    const isHealthy = dbHealth.status === 'connected';

    if (isHealthy) {
      return res.success({
        status: 'healthy',
        healthy: true,
        service: 'Financial Dashboard API',
        environment: process.env.ENVIRONMENT || 'dev',
        database: dbHealth.database,
        api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' },
        memory: process.memoryUsage(),
        uptime: process.uptime()
      });
    } else {
      return res.serviceUnavailable('Database', {
        status: 'unhealthy',
        healthy: false,
        service: 'Financial Dashboard API',
        environment: process.env.ENVIRONMENT || 'dev',
        database: dbHealth.database,
        api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' },
        memory: process.memoryUsage(),
        uptime: process.uptime()
      });
    }

  } catch (error) {
    const duration = Date.now() - startTime;
    console.error('Health check failed:', error);
    
    // Handle timeout specifically
    if (error.message === 'Health check timeout') {
      return res.status(408).json({
        status: 'timeout',
        healthy: false,
        message: 'Health check timed out after 10 seconds',
        database: { status: 'timeout', error: 'Database health check exceeded timeout' },
        api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' },
        duration: duration,
        memory: process.memoryUsage(),
        uptime: process.uptime(),
        timestamp: new Date().toISOString()
      });
    }
    
    res.serverError('Health check failed', {
      status: 'unhealthy',
      healthy: false,
      database: { status: 'error', error: error.message },
      api: { version: '1.0.0', environment: process.env.ENVIRONMENT || 'dev' },
      duration: duration,
      memory: process.memoryUsage(),
      uptime: process.uptime()
    });
  }
});

// Application readiness check - tests if database has tables
router.get('/ready', async (req, res) => {
  try {
    const { query } = require('../utils/database');
    
    // First check what tables actually exist
    const tablesResult = await query(`
      SELECT table_name 
      FROM information_schema.tables 
      WHERE table_schema = 'public' 
      AND table_type = 'BASE TABLE'
      ORDER BY table_name;
    `);
    
    const existingTables = tablesResult.rows.map(r => r.table_name);
    
    // Check critical webapp tables (not stock_symbols - that comes from data loading)
    const criticalWebappTables = ['last_updated', 'health_status'];
    const results = {};
    
    for (const table of criticalWebappTables) {
      if (existingTables.includes(table)) {
        try {
          const result = await query(`SELECT COUNT(*) as count FROM ${table} LIMIT 1`);
          results[table] = { 
            exists: true, 
            count: parseInt(result.rows[0].count),
            status: 'ready'
          };
        } catch (error) {
          results[table] = { 
            exists: true,
            error: error.message,
            status: 'error'
          };
        }
      } else {
        results[table] = { 
          exists: false,
          status: 'not_ready'
        };
      }
    }
    
    // Check if data loading tables exist (but don't fail if they don't)
    const dataLoadingTables = ['stock_symbols', 'company_profiles', 'prices'];
    const dataTablesInfo = {};
    
    for (const table of dataLoadingTables) {
      dataTablesInfo[table] = {
        exists: existingTables.includes(table),
        note: 'Created by data loading scripts'
      };
    }
    
    const webappTablesReady = Object.values(results).every(r => r.status === 'ready');
    
    return res.status(webappTablesReady ? 200 : 503).json({
      status: webappTablesReady ? 'ready' : 'not_ready',
      ready: webappTablesReady,
      service: 'Financial Dashboard API',
      timestamp: new Date().toISOString(),
      environment: process.env.ENVIRONMENT || 'dev',
      webapp_tables: results,
      data_loading_tables: dataTablesInfo,
      total_tables_found: existingTables.length,
      all_tables: existingTables,
      note: 'Webapp tables must be ready; data tables are optional'
    });
    
  } catch (error) {
    console.error('Readiness check failed:', error);
    res.status(503).json({
      status: 'not_ready',
      ready: false,
      timestamp: new Date().toISOString(),
      error: error.message,
      note: 'Application readiness check failed'
    });
  }
});

// REMOVED: Emergency table creation endpoint - use proper IaC deployment instead

// Debug endpoint for raw database queries
router.get('/debug/db-test', async (req, res) => {
  try {
    const { query } = require('../utils/database');
    
    const result = await query(`
      SELECT 
        NOW() as current_time,
        current_database() as db_name,
        current_user as db_user,
        version() as db_version,
        inet_server_addr() as server_ip,
        inet_server_port() as server_port
    `);
    
    res.json({
      status: 'success',
      database_info: result.rows[0],
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('DB test failed:', error);
    res.status(500).json({
      status: 'error',
      error: error.message,
      code: error.code,
      timestamp: new Date().toISOString()
    });
  }
});

// Debug endpoint to list all tables in database
router.get('/debug/tables', async (req, res) => {
  try {
    const { query } = require('../utils/database');
    
    const result = await query(`
      SELECT 
        table_name,
        table_type,
        is_insertable_into
      FROM information_schema.tables 
      WHERE table_schema = 'public'
      ORDER BY table_name
    `);
    
    res.json({
      status: 'success',
      table_count: result.rows.length,
      tables: result.rows,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Tables list failed:', error);
    res.status(500).json({
      status: 'error',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// External services health check - tests all external dependencies
router.get('/external-services', async (req, res) => {
  try {
    console.log('🔍 Starting external services health check...');
    const startTime = Date.now();
    
    const services = {
      database: await checkDatabaseHealth(),
      alpacaApi: await checkAlpacaApiHealth(),
      awsSecretsManager: await checkAwsSecretsManagerHealth(),
      awsRds: await checkAwsRdsHealth(),
      awsCognito: await checkAwsCognitoHealth()
    };
    
    const healthyServices = Object.values(services).filter(s => s.status === 'healthy').length;
    const totalServices = Object.keys(services).length;
    const allHealthy = healthyServices === totalServices;
    const duration = Date.now() - startTime;
    
    console.log(`✅ External services health check completed in ${duration}ms`);
    console.log(`📊 Services: ${healthyServices}/${totalServices} healthy`);
    
    const responseData = {
      status: allHealthy ? 'healthy' : 'degraded',
      healthy: allHealthy,
      service: 'External Services Health',
      duration: `${duration}ms`,
      services,
      summary: {
        total_services: totalServices,
        healthy_services: healthyServices,
        degraded_services: Object.values(services).filter(s => s.status === 'degraded').length,
        failed_services: Object.values(services).filter(s => s.status === 'failed').length,
        health_percentage: Math.round((healthyServices / totalServices) * 100)
      }
    };
    
    if (allHealthy) {
      res.success(responseData);
    } else {
      res.serviceUnavailable('External services', responseData);
    }
    
  } catch (error) {
    console.error('❌ External services health check failed:', error);
    res.serverError('External services health check failed', {
      service: 'External Services Health',
      error: error.message
    });
  }
});

// API services health check - tests API key service and related functionality
router.get('/api-services', async (req, res) => {
  try {
    const services = {
      apiKeyService: await checkApiKeyServiceHealth(),
      database: await checkDatabaseTablesForApiKeys(),
      secrets: await checkSecretsManagerHealth()
    };
    
    const allHealthy = Object.values(services).every(service => service.status === 'healthy');
    
    res.status(allHealthy ? 200 : 503).json({
      status: allHealthy ? 'healthy' : 'degraded',
      healthy: allHealthy,
      service: 'API Services Health',
      timestamp: new Date().toISOString(),
      services,
      summary: {
        total_services: Object.keys(services).length,
        healthy_services: Object.values(services).filter(s => s.status === 'healthy').length,
        degraded_services: Object.values(services).filter(s => s.status === 'degraded').length,
        failed_services: Object.values(services).filter(s => s.status === 'failed').length
      }
    });
    
  } catch (error) {
    console.error('API services health check failed:', error);
    res.status(500).json({
      status: 'error',
      healthy: false,
      service: 'API Services Health',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Debug endpoint to test specific table queries
router.get('/debug/test-query', async (req, res) => {
  try {
    const { query } = require('../utils/database');
    const tableName = req.query.table || 'stock_symbols';
    
    // First check if table exists
    const tableCheck = await query(`
      SELECT COUNT(*) as exists 
      FROM information_schema.tables 
      WHERE table_schema = 'public' AND table_name = $1
    `, [tableName]);
    
    const tableExists = parseInt(tableCheck.rows[0].exists) > 0;
    
    let tableData = null;
    if (tableExists) {
      const data = await query(`SELECT COUNT(*) as record_count FROM "${tableName}"`);
      tableData = { record_count: parseInt(data.rows[0].record_count) };
    }
    
    res.json({
      status: 'success',
      table: tableName,
      exists: tableExists,
      data: tableData,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Test query failed:', error);
    res.status(500).json({
      status: 'error',
      table: req.query.table || 'stock_symbols',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Timeout and circuit breaker monitoring endpoint
router.get('/timeout-status', async (req, res) => {
  try {
    const circuitBreakers = timeoutHelper.getCircuitBreakerStatus();
    const timeoutConfig = {
      database: timeoutHelper.defaultTimeouts.database,
      alpaca: timeoutHelper.defaultTimeouts.alpaca,
      news: timeoutHelper.defaultTimeouts.news,
      sentiment: timeoutHelper.defaultTimeouts.sentiment,
      external: timeoutHelper.defaultTimeouts.external,
      upload: timeoutHelper.defaultTimeouts.upload,
      websocket: timeoutHelper.defaultTimeouts.websocket
    };

    res.success({
      timeouts: timeoutConfig,
      circuitBreakers: circuitBreakers,
      summary: {
        totalCircuitBreakers: Object.keys(circuitBreakers).length,
        openCircuitBreakers: Object.values(circuitBreakers).filter(cb => cb.state === 'open').length,
        halfOpenCircuitBreakers: Object.values(circuitBreakers).filter(cb => cb.state === 'half-open').length,
        healthyServices: Object.values(circuitBreakers).filter(cb => cb.state === 'closed').length
      },
      recommendations: generateTimeoutRecommendations(circuitBreakers)
    });
  } catch (error) {
    console.error('❌ Timeout status check failed:', error);
    res.serverError('Failed to get timeout status', error.message);
  }
});

// Schema validation endpoint - comprehensive database schema analysis
router.get('/schema-validation', async (req, res) => {
  try {
    console.log('🔍 Starting comprehensive schema validation...');
    const startTime = Date.now();
    
    const options = {
      includeOptional: req.query.include_optional !== 'false',
      strict: req.query.strict === 'true'
    };
    
    const report = await schemaValidator.getSchemaValidationReport(options);
    const duration = Date.now() - startTime;
    
    console.log(`✅ Schema validation completed in ${duration}ms`);
    console.log(`📊 Summary: ${report.summary.existingTables}/${report.summary.totalTables} tables exist, ${report.summary.validSchemas} valid schemas`);
    
    // Determine overall health status
    const isHealthy = report.summary.missingRequired === 0 && report.summary.invalidSchemas === 0;
    
    const responseData = {
      ...report,
      duration: `${duration}ms`,
      status: isHealthy ? 'healthy' : 'degraded',
      healthy: isHealthy
    };
    
    if (isHealthy) {
      res.success(responseData);
    } else {
      res.serviceUnavailable('Database schema', responseData);
    }
  } catch (error) {
    console.error('❌ Schema validation failed:', error);
    res.serverError('Schema validation failed', error.message);
  }
});

// Table existence check endpoint
router.get('/table-exists/:tableName', async (req, res) => {
  try {
    const tableName = req.params.tableName;
    const throwOnMissing = req.query.throw === 'true';
    
    const exists = await schemaValidator.validateTableExists(tableName, {
      throwOnMissing,
      useCache: req.query.no_cache !== 'true'
    });
    
    const expectedTable = schemaValidator.expectedTables[tableName];
    
    res.success({
      table: tableName,
      exists,
      expected: expectedTable || null,
      message: exists 
        ? `Table '${tableName}' exists`
        : `Table '${tableName}' does not exist`
    });
  } catch (error) {
    console.error(`❌ Table existence check failed for '${req.params.tableName}':`, error);
    res.serverError('Table existence check failed', error.message);
  }
});

// Schema validation cache management
router.post('/schema-validation/clear-cache', async (req, res) => {
  try {
    const cacheStatus = schemaValidator.getCacheStatus();
    schemaValidator.clearCache();
    
    res.success({
      message: 'Schema validation cache cleared',
      previousCacheSize: cacheStatus.size,
      clearedEntries: cacheStatus.entries.length
    });
  } catch (error) {
    console.error('❌ Failed to clear schema cache:', error);
    res.serverError('Failed to clear schema cache', error.message);
  }
});

// Debug endpoint to check table structure
router.get('/debug/table-structure', async (req, res) => {
  try {
    const { query } = require('../utils/database');
    const tableName = req.query.table || 'users';
    
    // Get table column information
    const result = await query(`
      SELECT 
        column_name,
        data_type,
        is_nullable,
        column_default,
        character_maximum_length
      FROM information_schema.columns 
      WHERE table_schema = 'public' AND table_name = $1
      ORDER BY ordinal_position
    `, [tableName]);
    
    res.json({
      status: 'success',
      table: tableName,
      column_count: result.rows.length,
      columns: result.rows,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    console.error('Table structure check failed:', error);
    res.status(500).json({
      status: 'error',
      table: req.query.table || 'users',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
});

// Diagnostics endpoint - comprehensive system information
router.get('/diagnostics', async (req, res) => {
  try {
    const startTime = Date.now();
    
    // Gather comprehensive system diagnostics
    const diagnostics = {
      service: 'Financial Dashboard API',
      version: '1.0.0',
      status: 'operational',
      environment: process.env.ENVIRONMENT || 'dev',
      region: process.env.AWS_REGION || process.env.WEBAPP_AWS_REGION || 'us-east-1',
      
      // System info
      system: {
        memory: process.memoryUsage(),
        uptime: process.uptime(),
        platform: process.platform,
        nodeVersion: process.version,
        timestamp: new Date().toISOString()
      },
      
      // Configuration status
      configuration: {
        database: {
          endpoint: process.env.DB_ENDPOINT ? 'configured' : 'not_configured',
          secretArn: process.env.DB_SECRET_ARN ? 'configured' : 'not_configured',
          connectTimeout: process.env.DB_CONNECT_TIMEOUT || 'default',
          poolMax: process.env.DB_POOL_MAX || 'default'
        },
        authentication: {
          cognitoUserPool: process.env.COGNITO_USER_POOL_ID ? 'configured' : 'not_configured',
          cognitoClient: process.env.COGNITO_CLIENT_ID ? 'configured' : 'not_configured'
        },
        apiKeys: {
          encryptionSecret: process.env.API_KEY_ENCRYPTION_SECRET_ARN ? 'configured' : 'not_configured'
        },
        lambda: {
          functionName: process.env.AWS_LAMBDA_FUNCTION_NAME || 'unknown',
          functionVersion: process.env.AWS_LAMBDA_FUNCTION_VERSION || 'unknown',
          region: process.env.AWS_REGION || 'unknown'
        }
      },
      
      // Quick health checks
      healthChecks: {
        database: 'checking...',
        apiKeyService: 'checking...',
        secretsManager: 'checking...'
      }
    };
    
    // Perform basic health checks
    try {
      const dbHealth = await healthCheck();
      diagnostics.healthChecks.database = dbHealth.status === 'healthy' ? 'healthy' : 'unhealthy';
    } catch (error) {
      diagnostics.healthChecks.database = 'failed';
    }
    
    try {
      await apiKeyService.ensureInitialized();
      diagnostics.healthChecks.apiKeyService = 'healthy';
    } catch (error) {
      diagnostics.healthChecks.apiKeyService = 'failed';
    }
    
    try {
      const secretArn = process.env.API_KEY_ENCRYPTION_SECRET_ARN;
      if (secretArn) {
        diagnostics.healthChecks.secretsManager = 'healthy';
      } else {
        diagnostics.healthChecks.secretsManager = 'not_configured';
      }
    } catch (error) {
      diagnostics.healthChecks.secretsManager = 'failed';
    }
    
    const duration = Date.now() - startTime;
    diagnostics.diagnosticsDuration = `${duration}ms`;
    
    res.success(diagnostics);
  } catch (error) {
    console.error('Diagnostics endpoint failed:', error);
    res.serverError('Diagnostics failed', {
      error: error.message,
      service: 'Financial Dashboard API',
      timestamp: new Date().toISOString()
    });
  }
});

// Lambda performance metrics endpoint
router.get('/lambda-metrics', async (req, res) => {
  try {
    const lambdaOptimizer = require('../utils/lambdaOptimizer');
    const metrics = lambdaOptimizer.getMetrics();
    
    res.success({
      lambdaMetrics: metrics,
      endpoint: 'lambda-metrics',
      timestamp: new Date().toISOString()
    });
  } catch (error) {
    console.error('Lambda metrics endpoint failed:', error);
    res.serverError('Lambda metrics failed', {
      error: error.message,
      endpoint: 'lambda-metrics',
      timestamp: new Date().toISOString()
    });
  }
});

// Debug endpoint for environment and configuration
router.get('/debug/env', async (req, res) => {
  try {
    res.json({
      status: 'success',
      environment: {
        NODE_ENV: process.env.NODE_ENV,
        ENVIRONMENT: process.env.ENVIRONMENT,
        AWS_REGION: process.env.AWS_REGION,
        WEBAPP_AWS_REGION: process.env.WEBAPP_AWS_REGION,
        AWS_LAMBDA_FUNCTION_NAME: process.env.AWS_LAMBDA_FUNCTION_NAME,
        AWS_LAMBDA_FUNCTION_VERSION: process.env.AWS_LAMBDA_FUNCTION_VERSION
      },
      database_config: {
        DB_ENDPOINT: process.env.DB_ENDPOINT,
        DB_SECRET_ARN: process.env.DB_SECRET_ARN ? 'SET' : 'NOT_SET',
        DB_CONNECT_TIMEOUT: process.env.DB_CONNECT_TIMEOUT,
        DB_POOL_MAX: process.env.DB_POOL_MAX
      },
      lambda_info: {
        memory: process.memoryUsage(),
        uptime: process.uptime(),
        platform: process.platform,
        node_version: process.version
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

// Debug endpoint to test CORS
router.get('/debug/cors-test', async (req, res) => {
  res.header('Access-Control-Allow-Origin', '*');
  res.header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.header('Access-Control-Allow-Headers', 'Content-Type');
  
  res.json({
    status: 'success',
    message: 'CORS test successful',
    headers: req.headers,
    origin: req.get('origin'),
    timestamp: new Date().toISOString()
  });
});

// Update health status endpoint - for "Update All Tables" button
router.post('/update-status', async (req, res) => {
  try {
    console.log('🔄 Health status update requested');
    
    // Get comprehensive database health
    const healthData = await getComprehensiveDbHealth();
    
    // Optionally store in health_status table if it exists
    try {
      // Check if health_status table exists
      const tableCheck = await query(`
        SELECT COUNT(*) as exists 
        FROM information_schema.tables 
        WHERE table_schema = 'public' AND table_name = 'health_status'
      `);
      
      if (parseInt(tableCheck.rows[0].exists) > 0) {
        console.log('💾 Storing health data in health_status table...');
        
        // Store each table's health data
        for (const [tableName, tableData] of Object.entries(healthData.database.tables)) {
          await query(`
            INSERT INTO health_status (
              table_name, record_count, status, last_updated, 
              last_checked, critical_table, table_category, error_message
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (table_name) DO UPDATE SET
              record_count = EXCLUDED.record_count,
              status = EXCLUDED.status,
              last_updated = EXCLUDED.last_updated,
              last_checked = EXCLUDED.last_checked,
              critical_table = EXCLUDED.critical_table,
              table_category = EXCLUDED.table_category,
              error_message = EXCLUDED.error_message
          `, [
            tableName,
            tableData.record_count,
            tableData.status,
            tableData.last_updated,
            tableData.last_checked,
            tableData.critical_table,
            tableData.table_category,
            tableData.error
          ]);
        }
        
        console.log('✅ Health data stored in health_status table');
      } else {
        console.log('⚠️ health_status table does not exist - skipping storage');
      }
    } catch (storeError) {
      console.warn('⚠️ Failed to store health data in health_status table:', storeError.message);
      // Don't fail the whole request if storage fails
    }
    
    res.json({
      status: 'success',
      message: 'Database health status updated successfully',
      data: healthData,
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
 * Comprehensive database health check that analyzes all tables
 * This is what the frontend ServiceHealth.jsx expects to receive
 */
async function getComprehensiveDbHealth() {
  try {
    console.log('🔍 Starting optimized database health check...');
    const startTime = Date.now();
    
    // First test basic connectivity
    const basicHealth = await healthCheck();
    if (basicHealth.status !== 'healthy') {
      return {
        status: 'disconnected',
        error: basicHealth.error,
        database: {
          status: 'error',
          tables: {},
          summary: {
            total_tables: 0,
            healthy_tables: 0,
            stale_tables: 0,
            error_tables: 0,
            empty_tables: 0,
            missing_tables: 0,
            total_records: 0,
            total_missing_data: 0
          }
        },
        timestamp: new Date().toISOString()
      };
    }
    
    // Define table categories and critical tables
    const tableCategorization = {
      'symbols': ['symbols', 'stock_symbols', 'etf_symbols'],
      'prices': ['price_daily', 'price_weekly', 'price_monthly', 'latest_prices'],
      'technicals': ['technicals_daily', 'technicals_weekly', 'technicals_monthly', 'latest_technicals'],
      'financials': ['balance_sheet', 'income_statement', 'cash_flow', 'key_metrics'],
      'company': ['company_profile', 'company_profiles'],
      'earnings': ['earnings_estimates', 'earnings_history', 'earnings_metrics'],
      'sentiment': ['fear_greed_index', 'naaim', 'aaii_sentiment'],
      'trading': ['buy_sell_daily', 'buy_sell_weekly', 'swing_trader', 'trade_executions'],
      'portfolio': ['portfolio_holdings', 'position_history', 'user_api_keys'],
      'system': ['health_status', 'last_updated']
    };
    
    const criticalTables = [
      'symbols', 'stock_symbols', 'price_daily', 'latest_prices', 
      'portfolio_holdings', 'user_api_keys', 'health_status', 'last_updated'
    ];
    
    // Function to categorize table
    function categorizeTable(tableName) {
      for (const [category, tables] of Object.entries(tableCategorization)) {
        if (tables.includes(tableName)) {
          return category;
        }
      }
      return 'other';
    }
    
    // OPTIMIZED: Get table info and record counts in one efficient query
    console.log('📋 Getting table info and record counts efficiently...');
    const batchQuery = `
      SELECT 
        t.table_name,
        t.table_type,
        COALESCE(s.n_tup_ins - s.n_tup_del, 0) as estimated_rows,
        s.last_vacuum,
        s.last_autovacuum,
        s.last_analyze,
        s.last_autoanalyze
      FROM information_schema.tables t
      LEFT JOIN pg_stat_user_tables s ON s.relname = t.table_name
      WHERE t.table_schema = 'public' 
      AND t.table_type = 'BASE TABLE'
      ORDER BY t.table_name
    `;
    
    const tablesResult = await query(batchQuery, [], 15000);
    const allTables = tablesResult.rows;
    console.log(`📋 Found ${allTables.length} tables in database`);
    
    // Build table health data efficiently
    const tableHealth = {};
    let totalRecords = 0;
    let healthyTables = 0;
    let staleTables = 0;
    let errorTables = 0;
    let emptyTables = 0;
    
    console.log('🔍 Processing table health data...');
    for (const table of allTables) {
      const tableName = table.table_name;
      const estimatedRows = parseInt(table.estimated_rows) || 0;
      totalRecords += estimatedRows;
      
      // Use pg_stat timestamps for freshness check
      const lastUpdated = table.last_analyze || table.last_autoanalyze || table.last_vacuum || table.last_autovacuum;
      
      // Determine table status
      let status = 'healthy';
      let isStale = false;
      
      if (estimatedRows === 0) {
        status = 'empty';
        emptyTables++;
      } else if (lastUpdated) {
        const hoursSinceUpdate = (new Date() - new Date(lastUpdated)) / (1000 * 60 * 60);
        if (hoursSinceUpdate > 72) { // 3 days
          status = 'stale';
          isStale = true;
          staleTables++;
        } else {
          healthyTables++;
        }
      } else {
        // No timestamp available, assume healthy if has data
        healthyTables++;
      }
      
      tableHealth[tableName] = {
        status: status,
        record_count: estimatedRows,
        last_updated: lastUpdated,
        last_checked: new Date().toISOString(),
        table_category: categorizeTable(tableName),
        critical_table: criticalTables.includes(tableName),
        is_stale: isStale,
        missing_data_count: 0,
        error: null,
        note: 'Using pg_stat estimated counts for performance'
      };
    }
    
    // Calculate summary statistics
    const summary = {
      total_tables: allTables.length,
      healthy_tables: healthyTables,
      stale_tables: staleTables,
      error_tables: errorTables,
      empty_tables: emptyTables,
      missing_tables: 0, // Tables we expect but don't exist
      total_records: totalRecords,
      total_missing_data: 0 // Could be enhanced
    };
    
    const duration = Date.now() - startTime;
    console.log(`✅ Comprehensive database health check completed in ${duration}ms`);
    console.log(`📊 Summary: ${summary.total_tables} tables, ${summary.healthy_tables} healthy, ${summary.total_records} total records`);
    
    return {
      status: 'connected',
      database: {
        status: 'connected',
        currentTime: basicHealth.timestamp,
        postgresVersion: basicHealth.version,
        tables: tableHealth,
        summary: summary
      },
      timestamp: new Date().toISOString(),
      note: `Analyzed ${allTables.length} database tables in ${duration}ms`
    };
    
  } catch (error) {
    console.error('❌ Comprehensive database health check failed:', error);
    return {
      status: 'error',
      error: error.message,
      database: {
        status: 'error',
        tables: {},
        summary: {
          total_tables: 0,
          healthy_tables: 0,
          stale_tables: 0,
          error_tables: 0,
          empty_tables: 0,
          missing_tables: 0,
          total_records: 0,
          total_missing_data: 0
        }
      },
      timestamp: new Date().toISOString()
    };
  }
}

// Create health_status table if it doesn't exist (for storing health data)
// REMOVED: Table creation endpoints - tables should be created by db-init infrastructure

// External Service Health Check Functions

/**
 * Database health check with timeout and circuit breaker
 */
async function checkDatabaseHealth() {
  try {
    console.log('🔍 Checking database health...');
    const startTime = Date.now();
    
    // Test basic connectivity with timeout
    const dbHealth = await Promise.race([
      healthCheck(),
      new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Database health check timeout')), 5000)
      )
    ]);
    
    const duration = Date.now() - startTime;
    
    if (dbHealth.status === 'healthy') {
      return {
        status: 'healthy',
        message: 'Database is connected and responsive',
        responseTime: `${duration}ms`,
        version: dbHealth.version || 'unknown',
        connection: {
          host: process.env.DB_ENDPOINT ? 'configured' : 'not_configured',
          pool: 'active',
          ssl: 'enabled'
        }
      };
    } else {
      return {
        status: 'failed',
        message: 'Database connection failed',
        error: dbHealth.error,
        responseTime: `${duration}ms`
      };
    }
  } catch (error) {
    console.error('❌ Database health check failed:', error);
    return {
      status: 'failed',
      message: 'Database health check failed',
      error: error.message,
      timeout: error.message.includes('timeout')
    };
  }
}

/**
 * Alpaca API health check with sample credentials
 */
async function checkAlpacaApiHealth() {
  try {
    console.log('🔍 Checking Alpaca API health...');
    const startTime = Date.now();
    
    // Check if we have any valid Alpaca credentials to test with
    let testCredentials = null;
    
    try {
      // Try to get any user's API credentials for testing
      const credentialsQuery = await query(`
        SELECT api_key_encrypted, api_secret_encrypted, is_sandbox 
        FROM user_api_keys 
        WHERE provider = 'alpaca' AND status = 'active' 
        LIMIT 1
      `);
      
      if (credentialsQuery.rows.length > 0) {
        const row = credentialsQuery.rows[0];
        
        // Decrypt credentials for testing
        const decryptedKey = await apiKeyService.decryptApiKey(row.api_key_encrypted);
        const decryptedSecret = await apiKeyService.decryptApiKey(row.api_secret_encrypted);
        
        testCredentials = {
          apiKey: decryptedKey,
          apiSecret: decryptedSecret,
          isSandbox: row.is_sandbox
        };
      }
    } catch (dbError) {
      console.log('⚠️ Could not fetch test credentials from database:', dbError.message);
    }
    
    if (testCredentials) {
      // Test with real credentials
      const alpaca = new AlpacaService(
        testCredentials.apiKey,
        testCredentials.apiSecret,
        testCredentials.isSandbox
      );
      
      // Test API connectivity with account info (lightweight call)
      const accountInfo = await Promise.race([
        alpaca.getAccount(),
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Alpaca API timeout')), 10000)
        )
      ]);
      
      const duration = Date.now() - startTime;
      
      return {
        status: 'healthy',
        message: 'Alpaca API is accessible and responsive',
        responseTime: `${duration}ms`,
        environment: testCredentials.isSandbox ? 'sandbox' : 'live',
        account: {
          status: accountInfo?.status || 'unknown',
          tradingBlocked: accountInfo?.trading_blocked || false
        },
        features: {
          trading: true,
          marketData: true,
          portfolio: true
        }
      };
    } else {
      // No credentials available - check basic API availability
      return {
        status: 'degraded',
        message: 'No API credentials available for testing',
        responseTime: 'N/A',
        environment: 'unknown',
        features: {
          trading: false,
          marketData: false,
          portfolio: false
        },
        note: 'Add API credentials in Settings to enable full functionality'
      };
    }
  } catch (error) {
    console.error('❌ Alpaca API health check failed:', error);
    return {
      status: 'failed',
      message: 'Alpaca API health check failed',
      error: error.message,
      timeout: error.message.includes('timeout'),
      circuitBreakerTriggered: error.message.includes('circuit breaker')
    };
  }
}

/**
 * AWS Secrets Manager health check
 */
async function checkAwsSecretsManagerHealth() {
  try {
    console.log('🔍 Checking AWS Secrets Manager health...');
    const startTime = Date.now();
    
    const secretsManager = new SecretsManagerClient({
      region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
    });
    
    // Test basic Secrets Manager connectivity
    const testSecretArn = process.env.DB_SECRET_ARN || process.env.API_KEY_ENCRYPTION_SECRET_ARN;
    
    if (!testSecretArn) {
      return {
        status: 'degraded',
        message: 'No Secrets Manager ARNs configured',
        configured: false,
        region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
      };
    }
    
    // Test secrets access with timeout
    await Promise.race([
      secretsManager.send(new GetSecretValueCommand({ SecretId: testSecretArn })),
      new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Secrets Manager timeout')), 5000)
      )
    ]);
    
    const duration = Date.now() - startTime;
    
    return {
      status: 'healthy',
      message: 'AWS Secrets Manager is accessible',
      responseTime: `${duration}ms`,
      configured: true,
      region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1',
      secrets: {
        dbSecret: !!process.env.DB_SECRET_ARN,
        apiKeySecret: !!process.env.API_KEY_ENCRYPTION_SECRET_ARN
      }
    };
  } catch (error) {
    console.error('❌ AWS Secrets Manager health check failed:', error);
    return {
      status: 'failed',
      message: 'AWS Secrets Manager health check failed',
      error: error.message,
      timeout: error.message.includes('timeout'),
      region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
    };
  }
}

/**
 * AWS RDS health check
 */
async function checkAwsRdsHealth() {
  try {
    console.log('🔍 Checking AWS RDS health...');
    
    if (!process.env.DB_ENDPOINT) {
      return {
        status: 'degraded',
        message: 'DB_ENDPOINT not configured',
        configured: false
      };
    }
    
    // RDS health is primarily determined by database connectivity
    // We can also check RDS-specific metrics if needed
    const dbHealth = await checkDatabaseHealth();
    
    return {
      status: dbHealth.status,
      message: dbHealth.status === 'healthy' ? 'AWS RDS instance is accessible' : 'AWS RDS connection issues',
      responseTime: dbHealth.responseTime,
      configured: true,
      endpoint: 'configured',
      ssl: 'enforced',
      multiAz: 'unknown', // Would need RDS API to check
      backups: 'unknown'  // Would need RDS API to check
    };
  } catch (error) {
    console.error('❌ AWS RDS health check failed:', error);
    return {
      status: 'failed',
      message: 'AWS RDS health check failed',
      error: error.message
    };
  }
}

/**
 * AWS Cognito health check
 */
async function checkAwsCognitoHealth() {
  try {
    console.log('🔍 Checking AWS Cognito health...');
    const startTime = Date.now();
    
    const userPoolId = process.env.COGNITO_USER_POOL_ID;
    const clientId = process.env.COGNITO_CLIENT_ID;
    
    if (!userPoolId || !clientId) {
      return {
        status: 'degraded',
        message: 'Cognito configuration not complete',
        configured: false,
        region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1',
        userPool: !!userPoolId,
        clientId: !!clientId
      };
    }
    
    const cognitoIdp = new CognitoIdentityProviderClient({
      region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
    });
    
    // Test Cognito connectivity by describing the user pool
    await Promise.race([
      cognitoIdp.send(new DescribeUserPoolCommand({ UserPoolId: userPoolId })),
      new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Cognito timeout')), 5000)
      )
    ]);
    
    const duration = Date.now() - startTime;
    
    return {
      status: 'healthy',
      message: 'AWS Cognito is accessible',
      responseTime: `${duration}ms`,
      configured: true,
      region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1',
      userPool: !!userPoolId,
      clientId: !!clientId,
      features: {
        authentication: true,
        userManagement: true,
        mfa: 'unknown' // Would need to check user pool config
      }
    };
  } catch (error) {
    console.error('❌ AWS Cognito health check failed:', error);
    return {
      status: 'failed',
      message: 'AWS Cognito health check failed',
      error: error.message,
      timeout: error.message.includes('timeout'),
      region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1'
    };
  }
}

// API Service Health Check Functions
async function checkApiKeyServiceHealth() {
  try {
    // Check if API key service is initialized and enabled
    await apiKeyService.ensureInitialized();
    
    return {
      status: 'healthy',
      enabled: apiKeyService.isEnabled,
      message: 'API key service is initialized and enabled',
      features: {
        encryption: apiKeyService.isEnabled,
        secretsManager: !!process.env.API_KEY_ENCRYPTION_SECRET_ARN
      }
    };
  } catch (error) {
    return {
      status: 'failed',
      enabled: false,
      error: error.message,
      message: 'API key service is not available',
      features: {
        encryption: false,
        secretsManager: !!process.env.API_KEY_ENCRYPTION_SECRET_ARN
      }
    };
  }
}

async function checkDatabaseTablesForApiKeys() {
  try {
    const requiredTables = [
      'user_api_keys',
      'portfolio_holdings', 
      'portfolio_metadata',
      'portfolio_data_refresh_requests'
    ];
    
    const tableStatus = {};
    
    for (const table of requiredTables) {
      try {
        const result = await query(`SELECT COUNT(*) as count FROM ${table} LIMIT 1`);
        tableStatus[table] = {
          exists: true,
          status: 'healthy',
          count: parseInt(result.rows[0].count)
        };
      } catch (error) {
        if (error.message.includes('does not exist')) {
          tableStatus[table] = {
            exists: false,
            status: 'missing',
            error: 'Table does not exist'
          };
        } else {
          tableStatus[table] = {
            exists: true,
            status: 'error',
            error: error.message
          };
        }
      }
    }
    
    const allHealthy = Object.values(tableStatus).every(t => t.status === 'healthy');
    
    return {
      status: allHealthy ? 'healthy' : 'degraded',
      tables: tableStatus,
      summary: {
        total_tables: requiredTables.length,
        healthy_tables: Object.values(tableStatus).filter(t => t.status === 'healthy').length,
        missing_tables: Object.values(tableStatus).filter(t => t.status === 'missing').length,
        error_tables: Object.values(tableStatus).filter(t => t.status === 'error').length
      }
    };
  } catch (error) {
    return {
      status: 'failed',
      error: error.message,
      message: 'Failed to check database tables'
    };
  }
}

async function checkSecretsManagerHealth() {
  try {
    const secretArn = process.env.API_KEY_ENCRYPTION_SECRET_ARN;
    
    if (!secretArn) {
      return {
        status: 'degraded',
        message: 'API_KEY_ENCRYPTION_SECRET_ARN not configured',
        configured: false
      };
    }
    
    // Try to load the secret (this will test both permissions and secret existence)
    try {
      await apiKeyService.ensureInitialized();
      return {
        status: 'healthy',
        message: 'Secrets Manager access is working',
        configured: true,
        secretArn: secretArn.substring(0, 50) + '...' // Truncate for security
      };
    } catch (error) {
      return {
        status: 'failed',
        message: 'Cannot access encryption secret',
        configured: true,
        error: error.message,
        secretArn: secretArn.substring(0, 50) + '...'
      };
    }
  } catch (error) {
    return {
      status: 'failed',
      error: error.message,
      message: 'Secrets Manager health check failed'
    };
  }
}

/**
 * Generate timeout recommendations based on circuit breaker status
 */
function generateTimeoutRecommendations(circuitBreakers) {
  const recommendations = [];
  
  for (const [serviceKey, breaker] of Object.entries(circuitBreakers)) {
    if (breaker.state === 'open') {
      recommendations.push({
        service: serviceKey,
        issue: 'Circuit breaker is open',
        recommendation: 'Service is currently unavailable due to repeated failures. Check service health.',
        priority: 'high'
      });
    } else if (breaker.state === 'half-open') {
      recommendations.push({
        service: serviceKey,
        issue: 'Circuit breaker is half-open',
        recommendation: 'Service is recovering from failures. Monitor closely.',
        priority: 'medium'
      });
    } else if (breaker.failures > 2) {
      recommendations.push({
        service: serviceKey,
        issue: 'Recent failures detected',
        recommendation: 'Service has recent failures but is still operational. Consider investigating.',
        priority: 'low'
      });
    }
  }
  
  if (recommendations.length === 0) {
    recommendations.push({
      service: 'all',
      issue: 'none',
      recommendation: 'All services are operating normally with proper timeout handling.',
      priority: 'info'
    });
  }
  
  return recommendations;
}

// Comprehensive Database Schema Validation Endpoint
router.get('/database/schema', async (req, res) => {
  const requestId = crypto.randomUUID().split('-')[0];
  const requestStart = Date.now();
  
  try {
    console.log(`🚀 [${requestId}] Database schema validation endpoint called`, {
      userAgent: req.headers['user-agent'],
      ip: req.ip,
      timestamp: new Date().toISOString()
    });

    // Perform comprehensive database schema validation
    console.log(`🔍 [${requestId}] Starting comprehensive database schema validation`);
    const schemaValidation = await validateDatabaseSchema(requestId);
    
    const responseData = {
      success: true,
      schema_validation: {
        overall: {
          status: schemaValidation.valid ? 'valid' : 'invalid',
          health_percentage: schemaValidation.healthPercentage,
          critical_missing: schemaValidation.criticalMissing || [],
          total_required: schemaValidation.totalRequired,
          total_existing: schemaValidation.totalExisting
        },
        categories: schemaValidation.validation ? {
          core: {
            status: schemaValidation.validation.core.missing.length === 0 ? 'complete' : 'incomplete',
            required: schemaValidation.validation.core.required.length,
            existing: schemaValidation.validation.core.existing.length,
            missing: schemaValidation.validation.core.missing,
            existing_tables: schemaValidation.validation.core.existing
          },
          portfolio: {
            status: schemaValidation.validation.portfolio.missing.length === 0 ? 'complete' : 'incomplete',
            required: schemaValidation.validation.portfolio.required.length,
            existing: schemaValidation.validation.portfolio.existing.length,
            missing: schemaValidation.validation.portfolio.missing,
            existing_tables: schemaValidation.validation.portfolio.existing
          },
          market_data: {
            status: schemaValidation.validation.market_data.missing.length === 0 ? 'complete' : 'incomplete',
            required: schemaValidation.validation.market_data.required.length,
            existing: schemaValidation.validation.market_data.existing.length,
            missing: schemaValidation.validation.market_data.missing,
            existing_tables: schemaValidation.validation.market_data.existing
          },
          analytics: {
            status: schemaValidation.validation.analytics.missing.length === 0 ? 'complete' : 'incomplete',
            required: schemaValidation.validation.analytics.required.length,
            existing: schemaValidation.validation.analytics.existing.length,
            missing: schemaValidation.validation.analytics.missing,
            existing_tables: schemaValidation.validation.analytics.existing
          },
          optional: {
            status: 'optional',
            required: schemaValidation.validation.optional.required.length,
            existing: schemaValidation.validation.optional.existing.length,
            missing: schemaValidation.validation.optional.missing,
            existing_tables: schemaValidation.validation.optional.existing
          }
        } : null,
        schema_definition: REQUIRED_SCHEMA,
        recommendations: generateSchemaRecommendations(schemaValidation),
        validation_info: {
          duration_ms: schemaValidation.validationDuration,
          timestamp: schemaValidation.timestamp,
          request_id: requestId
        }
      },
      request_info: {
        request_id: requestId,
        total_duration_ms: Date.now() - requestStart,
        timestamp: new Date().toISOString()
      }
    };

    // Set appropriate HTTP status based on schema health
    let statusCode = 200;
    if (schemaValidation.error) {
      statusCode = 500;
    } else if (schemaValidation.criticalMissing && schemaValidation.criticalMissing.length > 0) {
      statusCode = 503; // Service unavailable due to missing critical tables
    } else if (schemaValidation.healthPercentage < 80) {
      statusCode = 206; // Partial content - some tables missing but not critical
    }

    const totalDuration = Date.now() - requestStart;
    console.log(`✅ [${requestId}] Database schema validation completed in ${totalDuration}ms`, {
      status: statusCode,
      schemaHealth: `${schemaValidation.healthPercentage}%`,
      criticalMissing: schemaValidation.criticalMissing?.length || 0,
      totalRequired: schemaValidation.totalRequired,
      totalExisting: schemaValidation.totalExisting
    });

    res.status(statusCode).json(responseData);

  } catch (error) {
    const errorDuration = Date.now() - requestStart;
    console.error(`❌ [${requestId}] Database schema validation FAILED after ${errorDuration}ms:`, {
      error: error.message,
      errorStack: error.stack,
      impact: 'Cannot validate database schema',
      recommendation: 'Check database connectivity and permissions'
    });
    
    res.status(500).json({
      success: false,
      error: 'Database schema validation failed',
      details: process.env.NODE_ENV === 'development' ? error.message : 'Internal server error',
      request_info: {
        request_id: requestId,
        error_duration_ms: errorDuration,
        timestamp: new Date().toISOString()
      }
    });
  }
});

/**
 * Generate schema-specific recommendations based on validation results
 */
function generateSchemaRecommendations(schemaValidation) {
  const recommendations = [];
  
  if (schemaValidation.error) {
    recommendations.push({
      type: 'error',
      priority: 'critical',
      message: 'Database schema validation failed',
      action: 'Check database connectivity and permissions',
      details: schemaValidation.error
    });
    return recommendations;
  }
  
  if (schemaValidation.criticalMissing && schemaValidation.criticalMissing.length > 0) {
    recommendations.push({
      type: 'critical_tables_missing',
      priority: 'critical',
      message: `${schemaValidation.criticalMissing.length} critical tables missing`,
      action: 'Run database initialization scripts immediately',
      details: schemaValidation.criticalMissing,
      impact: 'Core application functionality will not work'
    });
  }
  
  if (schemaValidation.validation) {
    const categories = ['core', 'portfolio', 'market_data', 'analytics'];
    
    categories.forEach(category => {
      const categoryData = schemaValidation.validation[category];
      if (categoryData && categoryData.missing.length > 0) {
        recommendations.push({
          type: 'category_tables_missing',
          priority: category === 'core' ? 'high' : 'medium',
          message: `Missing ${categoryData.missing.length} ${category} tables`,
          action: `Create missing ${category} tables: ${categoryData.missing.join(', ')}`,
          details: categoryData.missing,
          impact: getCategoryImpact(category)
        });
      }
    });
  }
  
  if (schemaValidation.healthPercentage < 100 && schemaValidation.healthPercentage >= 80) {
    recommendations.push({
      type: 'partial_schema',
      priority: 'low',
      message: `Schema is ${schemaValidation.healthPercentage}% complete`,
      action: 'Consider creating missing optional tables for full functionality',
      details: 'Some advanced features may be limited'
    });
  }
  
  if (recommendations.length === 0) {
    recommendations.push({
      type: 'schema_complete',
      priority: 'info',
      message: 'Database schema is complete and healthy',
      action: 'No action required',
      details: 'All required tables are present and accessible'
    });
  }
  
  return recommendations;
}

/**
 * Get category-specific impact description for recommendations
 */
function getCategoryImpact(category) {
  const impacts = {
    core: 'User authentication and API key management will fail',
    portfolio: 'Portfolio tracking and management features will be broken',
    market_data: 'Stock data and market information will be unavailable',
    analytics: 'Trading signals and analysis features will not work'
  };
  
  return impacts[category] || 'Some application features may be limited';
}

module.exports = router;