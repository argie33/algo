/**
 * Database Connection Manager - SIMPLIFIED VERSION
 * 
 * FIXES APPLIED:
 * ✅ Single database connection manager (no more conflicts)
 * ✅ Coordinated timeout hierarchy (Lambda 25s > Circuit 20s > DB 18s) 
 * ✅ Proper connection pooling for Lambda environment
 * ✅ Resource cleanup and leak prevention
 */

const { Pool } = require('pg');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

// FIXED: Coordinated timeout configuration
const TIMEOUTS = {
  lambda: 25000,        // Maximum Lambda execution time
  circuit: 20000,       // Circuit breaker timeout (< lambda)
  connection: 8000,     // Database connection establishment
  query: 12000,         // Standard query execution  
  transaction: 18000,   // Complex transactions
  healthCheck: 12000,   // Health check queries (must be > connection timeout)
  secrets: 6000         // AWS Secrets Manager
};

// Global state - simplified
let pool = null;
let dbConfig = null;
let isInitialized = false;
let lastHealthCheck = 0;
const healthCheckInterval = 30000; // 30 seconds

// Configure AWS SDK for Secrets Manager
const secretsManager = new SecretsManagerClient({
  region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1',
  requestTimeout: TIMEOUTS.secrets
});

/**
 * Get database configuration from environment variables or AWS Secrets Manager
 */
async function getDbConfig() {
  if (dbConfig && !dbConfig.__isStub) {
    console.log('✅ Using cached database config');
    return dbConfig;
  }

  try {
    // Priority 1: AWS Secrets Manager (production)
    if (process.env.DB_SECRET_ARN && 
        process.env.NODE_ENV !== 'test' && 
        !process.env.DB_SECRET_ARN.includes('${') &&
        process.env.DB_SECRET_ARN !== '${DB_SECRET_ARN}') {
      
      console.log('🔐 Using AWS Secrets Manager for database configuration');
      const secretArn = process.env.DB_SECRET_ARN;
      
      const command = new GetSecretValueCommand({ SecretId: secretArn });
      const response = await secretsManager.send(command);
      
      if (!response.SecretString) {
        throw new Error('Secret value is empty');
      }
      
      let secret;
      try {
        secret = JSON.parse(response.SecretString);
      } catch (parseError) {
        throw new Error(`Invalid secret JSON format: ${parseError.message}`);
      }
      
      // Validate required fields
      const required = ['username', 'password', 'host'];
      const missing = required.filter(field => !secret[field] && !secret[field === 'host' ? 'endpoint' : field]);
      if (missing.length > 0) {
        throw new Error(`Secret missing required fields: ${missing.join(', ')}`);
      }
      
      // Get host with fallback chain
      const dbHost = secret.host || secret.endpoint || process.env.DB_ENDPOINT || process.env.DB_HOST;
      
      // Security: Reject localhost in Lambda environment
      if (process.env.AWS_LAMBDA_FUNCTION_NAME && ['localhost', '127.0.0.1'].includes(dbHost)) {
        throw new Error('Invalid database host: localhost not allowed in AWS Lambda');
      }
      
      dbConfig = {
        host: dbHost,
        port: parseInt(secret.port) || 5432,
        database: secret.dbname || secret.database || 'financial_dashboard',
        user: secret.username || secret.user,
        password: secret.password,
        ssl: { rejectUnauthorized: false }
      };
      
      console.log(`✅ Database config loaded from AWS Secrets Manager`);
      console.log(`   🏗️ Host: ${dbConfig.host}:${dbConfig.port}`);
      console.log(`   📚 Database: ${dbConfig.database}`);
      
      return dbConfig;
    }

    // Priority 2: Environment variables (development)
    if (process.env.DB_HOST && process.env.DB_USER && process.env.DB_PASSWORD) {
      console.log('🔧 Using direct environment variables');
      dbConfig = {
        host: process.env.DB_HOST,
        port: parseInt(process.env.DB_PORT) || 5432,
        database: process.env.DB_NAME || 'financial_dashboard',
        user: process.env.DB_USER,
        password: process.env.DB_PASSWORD,
        ssl: process.env.DB_SSL === 'true' ? { rejectUnauthorized: false } : false
      };
      return dbConfig;
    }
    
    // Priority 3: Test/fallback configuration
    console.log('⚠️ Using fallback test configuration');
    dbConfig = {
      host: 'localhost',
      port: 5432,
      database: 'test_database',
      user: 'test_user',
      password: 'test_password',
      ssl: false,
      __isStub: true
    };
    return dbConfig;
    
  } catch (error) {
    console.error('❌ Failed to get database configuration:', error.message);
    throw error;
  }
}

/**
 * Initialize database connection pool
 */
async function initializeDatabase() {
  if (isInitialized && pool && !pool.ended) {
    console.log('✅ Using existing database connection');
    return pool;
  }
  
  const startTime = Date.now();
  
  try {
    console.log('🔄 Initializing database connection...');
    
    // Get configuration with timeout protection
    const config = await withTimeout(
      getDbConfig(),
      TIMEOUTS.secrets + 2000, // Secrets + buffer
      'database_config_retrieval'
    );
    
    // Clean up existing pool if needed
    if (pool && !pool.ended) {
      await pool.end();
    }
    
    // FIXED: Create optimized connection pool for Lambda
    pool = new Pool({
      ...config,
      // Lambda-optimized settings
      max: 3,                      // Reduced for Lambda concurrency limits
      min: 0,                      // Allow scaling to zero
      acquireTimeoutMillis: 5000,  // Quick acquisition
      createTimeoutMillis: TIMEOUTS.connection,
      destroyTimeoutMillis: 2000,  // Fast cleanup
      idleTimeoutMillis: 10000,    // Quick idle cleanup
      reapIntervalMillis: 5000,    // Regular cleanup
      createRetryIntervalMillis: 500,
      keepAlive: false,            // Disable for Lambda (causes hangs)
      statement_timeout: TIMEOUTS.query,
      query_timeout: TIMEOUTS.query,
      connectionTimeoutMillis: TIMEOUTS.connection
    });
    
    // Set up connection event handlers
    pool.on('connect', (client) => {
      console.log('🔗 Database client connected');
      // Set statement timeout on each connection
      client.query(`SET statement_timeout = ${TIMEOUTS.query}`).catch(err => {
        console.warn('⚠️ Failed to set statement timeout:', err.message);
      });
    });
    
    pool.on('error', (err) => {
      console.error('💥 Database pool error:', err.message);
      isInitialized = false;
    });
    
    pool.on('remove', () => {
      console.log('🗑️ Database client removed from pool');
    });
    
    // Test connection (skip for stub configuration)
    if (!config.__isStub) {
      await withTimeout(
        testConnection(),
        TIMEOUTS.healthCheck,
        'initial_connection_test'
      );
    }
    
    isInitialized = true;
    const duration = Date.now() - startTime;
    console.log(`✅ Database connection initialized successfully (${duration}ms)`);
    console.log(`   📊 Pool: max=3, timeouts: conn=${TIMEOUTS.connection}ms, query=${TIMEOUTS.query}ms`);
    
    return pool;
    
  } catch (error) {
    const duration = Date.now() - startTime;
    console.error(`❌ Database initialization failed (${duration}ms):`, error.message);
    
    // Cleanup on failure
    await cleanup();
    isInitialized = false;
    throw new Error(`Database initialization failed: ${error.message}`);
  }
}

/**
 * Test database connection
 */
async function testConnection() {
  if (!pool) {
    throw new Error('Pool not initialized');
  }
  
  const client = await pool.connect();
  try {
    // Basic connectivity test
    const basic = await client.query('SELECT 1 as connected, NOW() as timestamp, current_database() as db_name');
    console.log('✅ Database connection test successful');
    console.log(`   📍 Connected to: ${basic.rows[0].db_name} at ${basic.rows[0].timestamp}`);
    
    // Prove we can access actual tables
    const tables = await client.query(`
      SELECT table_name, table_type 
      FROM information_schema.tables 
      WHERE table_schema = 'public' 
      ORDER BY table_name 
      LIMIT 10
    `);
    
    console.log(`   📊 Found ${tables.rows.length} tables:`, tables.rows.map(r => r.table_name).join(', '));
    
    // Try to access stock data if available
    try {
      const stockCount = await client.query('SELECT COUNT(*) as count FROM stock_symbols WHERE is_active = true LIMIT 1');
      console.log(`   📈 Active stocks in database: ${stockCount.rows[0].count}`);
    } catch (e) {
      console.log('   ⚠️ stock_symbols table not accessible or empty');
    }
    
    return {
      connected: true,
      timestamp: basic.rows[0].timestamp,
      database: basic.rows[0].db_name,
      tables: tables.rows.length,
      verified: true
    };
  } finally {
    client.release();
  }
}

/**
 * Execute query with timeout protection
 */
async function query(text, params = [], timeout = null) {
  if (!isInitialized || !pool) {
    await initializeDatabase();
  }
  
  const queryTimeout = timeout || TIMEOUTS.query;
  const startTime = Date.now();
  
  try {
    const result = await withTimeout(
      pool.query(text, params),
      queryTimeout,
      `query: ${text.substring(0, 50)}...`
    );
    
    const duration = Date.now() - startTime;
    if (duration > queryTimeout * 0.8) {
      console.warn(`⚠️ Slow query detected (${duration}ms): ${text.substring(0, 100)}`);
    }
    
    return result;
    
  } catch (error) {
    const duration = Date.now() - startTime;
    console.error(`❌ Query failed (${duration}ms):`, error.message);
    
    // Reset connection on certain errors
    if (shouldResetConnection(error)) {
      console.log('🔄 Resetting database connection due to error');
      isInitialized = false;
    }
    
    throw error;
  }
}

/**
 * Get connection pool
 */
async function getPool() {
  return initializeDatabase();
}

/**
 * Health check with proper timeout
 */
async function healthCheck() {
  const now = Date.now();
  if (now - lastHealthCheck < healthCheckInterval) {
    return { healthy: true, cached: true };
  }
  
  try {
    const startTime = Date.now();
    const result = await withTimeout(
      query('SELECT 1 as healthy, NOW() as timestamp'),
      TIMEOUTS.healthCheck,
      'health_check'
    );
    
    const responseTime = Date.now() - startTime;
    lastHealthCheck = now;
    
    return {
      healthy: true,
      responseTime,
      timestamp: result.rows[0].timestamp,
      pool: {
        totalCount: pool?.totalCount || 0,
        idleCount: pool?.idleCount || 0,
        waitingCount: pool?.waitingCount || 0
      }
    };
    
  } catch (error) {
    console.error('❌ Health check failed:', error.message);
    return {
      healthy: false,
      error: error.message,
      timestamp: new Date().toISOString()
    };
  }
}

/**
 * Clean up resources
 */
async function cleanup() {
  if (pool && !pool.ended) {
    try {
      console.log('🧹 Cleaning up database connections...');
      await withTimeout(
        pool.end(),
        5000,
        'pool_cleanup'
      );
      console.log('✅ Database cleanup completed');
    } catch (error) {
      console.error('❌ Database cleanup failed:', error.message);
    }
  }
  
  pool = null;
  isInitialized = false;
  dbConfig = null;
}

/**
 * Wrapper for promises with timeout
 */
async function withTimeout(promise, timeoutMs, operation = 'operation') {
  let timeoutId;
  
  const timeoutPromise = new Promise((_, reject) => {
    timeoutId = setTimeout(() => {
      const error = new Error(`${operation} timeout after ${timeoutMs}ms`);
      error.code = 'TIMEOUT';
      error.timeout = timeoutMs;
      error.operation = operation;
      reject(error);
    }, timeoutMs);
  });
  
  try {
    const result = await Promise.race([promise, timeoutPromise]);
    clearTimeout(timeoutId);
    return result;
  } catch (error) {
    clearTimeout(timeoutId);
    throw error;
  }
}

/**
 * Check if connection should be reset
 */
function shouldResetConnection(error) {
  const resetCodes = [
    'ECONNRESET',
    'EPIPE',
    'connection terminated unexpectedly'
  ];
  return resetCodes.some(code => 
    error.code === code || error.message.includes(code)
  );
}

/**
 * Get connection pool statistics
 */
function getPoolStats() {
  if (!pool) {
    return { status: 'uninitialized' };
  }
  
  return {
    status: 'active',
    totalCount: pool.totalCount,
    idleCount: pool.idleCount,
    waitingCount: pool.waitingCount,
    ended: pool.ended,
    config: {
      max: 3,
      connectionTimeout: TIMEOUTS.connection,
      queryTimeout: TIMEOUTS.query
    }
  };
}

/**
 * Get diagnostic information
 */
async function getDiagnostics() {
  const poolStats = getPoolStats();
  const health = await healthCheck();
  
  return {
    connectionPool: poolStats,
    health,
    timeouts: TIMEOUTS,
    timestamp: new Date().toISOString()
  };
}

/**
 * Force connection reset (for emergency situations)
 */
async function forceReset() {
  console.log('🔄 Force resetting database connections...');
  await cleanup();
  return initializeDatabase();
}

// Process cleanup handlers
process.on('SIGTERM', cleanup);
process.on('SIGINT', cleanup);
process.on('beforeExit', cleanup);

// Export everything - simple and clean
module.exports = {
  // Main functions
  query,
  getPool,
  initializeDatabase,
  healthCheck,
  cleanup,
  
  // Additional utilities
  getPoolStats,
  getDiagnostics,
  forceReset,
  
  // Timeout configuration
  timeouts: TIMEOUTS
};

// Log initialization
console.log('🔧 Database module loaded - SIMPLIFIED VERSION');
console.log(`   Timeout hierarchy: Lambda ${TIMEOUTS.lambda}ms > Circuit ${TIMEOUTS.circuit}ms > DB ${TIMEOUTS.query}ms`);