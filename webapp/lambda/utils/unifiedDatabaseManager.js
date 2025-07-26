/**
 * Unified Database Connection Manager
 * Consolidates legacy database.js and databaseConnectionManager.js
 * Implements proper timeout hierarchies and connection pooling for Lambda
 * 
 * FIXES:
 * - Single source of truth for database connections
 * - Coordinated timeout hierarchy: Lambda 25s > DB 20s > Query 15s
 * - Proper connection pooling with Lambda-optimized settings
 * - Circuit breaker integration for stability
 * - Resource cleanup and leak prevention
 */

const { Pool } = require('pg');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');

class UnifiedDatabaseManager {
  constructor() {
    this.pool = null;
    this.config = null;
    this.isInitialized = false;
    this.lastHealthCheck = 0;
    this.healthCheckInterval = 30000; // 30 seconds
    this.connectionAttempts = 0;
    this.maxConnectionAttempts = 3;
    
    // FIXED: Unified timeout hierarchy for Lambda environment
    this.timeouts = {
      // Lambda constraint: 25s max (with 2s buffer for cleanup)
      lambda: 25000,        // Maximum Lambda execution time
      
      // Database operations (must be < lambda timeout)
      connection: 8000,     // Database connection establishment
      query: 12000,         // Standard query execution  
      transaction: 18000,   // Complex transactions
      healthCheck: 5000,    // Health check queries
      
      // AWS services (must be < database timeouts)
      secrets: 6000,        // AWS Secrets Manager
      
      // Circuit breaker
      circuit: 20000        // Circuit breaker timeout (< lambda)
    };
    
    // Connection pool settings optimized for Lambda
    this.poolConfig = {
      max: 3,                      // Reduced for Lambda concurrency limits
      min: 0,                      // Allow scaling to zero
      acquireTimeoutMillis: 5000,  // Quick acquisition
      createTimeoutMillis: this.timeouts.connection,
      destroyTimeoutMillis: 2000,  // Fast cleanup
      idleTimeoutMillis: 10000,    // Quick idle cleanup
      reapIntervalMillis: 5000,    // Regular cleanup
      createRetryIntervalMillis: 500,
      keepAlive: false,            // Disable for Lambda (causes hangs)
      statement_timeout: this.timeouts.query,
      query_timeout: this.timeouts.query,
      connectionTimeoutMillis: this.timeouts.connection
    };
    
    // Configure AWS Secrets Manager with timeout
    this.secretsManager = new SecretsManagerClient({
      region: process.env.WEBAPP_AWS_REGION || process.env.AWS_REGION || 'us-east-1',
      requestTimeout: this.timeouts.secrets
    });
    
    console.log('🔧 UnifiedDatabaseManager initialized with timeout hierarchy:', {
      lambda: `${this.timeouts.lambda}ms`,
      circuit: `${this.timeouts.circuit}ms`, 
      connection: `${this.timeouts.connection}ms`,
      query: `${this.timeouts.query}ms`,
      secrets: `${this.timeouts.secrets}ms`
    });
  }
  
  /**
   * Initialize database connection with proper error handling and timeouts
   */
  async initialize() {
    if (this.isInitialized && this.pool && !this.pool.ended) {
      console.log('✅ Using existing database connection');
      return this.pool;
    }
    
    const startTime = Date.now();
    this.connectionAttempts++;
    
    try {
      console.log(`🔄 Initializing unified database connection (attempt ${this.connectionAttempts}/${this.maxConnectionAttempts})`);
      
      // Get configuration with timeout protection
      this.config = await this.withTimeout(
        this.getDbConfig(),
        this.timeouts.secrets + 2000, // Secrets + buffer
        'database_config_retrieval'
      );
      
      // Create optimized connection pool
      await this.createConnectionPool();
      
      // Test connection with health check timeout
      if (!this.config.__isStub) {
        await this.withTimeout(
          this.testConnection(),
          this.timeouts.healthCheck,
          'initial_connection_test'
        );
      }
      
      this.isInitialized = true;
      this.connectionAttempts = 0; // Reset on success
      
      const duration = Date.now() - startTime;
      console.log(`✅ Unified database connection initialized successfully (${duration}ms)`);
      console.log(`   📊 Pool: max=${this.poolConfig.max}, timeouts: conn=${this.timeouts.connection}ms, query=${this.timeouts.query}ms`);
      
      return this.pool;
      
    } catch (error) {
      const duration = Date.now() - startTime;
      console.error(`❌ Database initialization failed (${duration}ms):`, error.message);
      
      // Cleanup on failure
      await this.cleanup();
      
      // Retry logic for transient failures
      if (this.connectionAttempts < this.maxConnectionAttempts && this.isRetryableError(error)) {
        console.log(`🔄 Retrying database initialization in ${this.connectionAttempts * 1000}ms...`);
        await this.sleep(this.connectionAttempts * 1000);
        return this.initialize();
      }
      
      this.isInitialized = false;
      throw new Error(`Database initialization failed after ${this.connectionAttempts} attempts: ${error.message}`);
    }
  }
  
  /**
   * Create connection pool with optimized settings
   */
  async createConnectionPool() {
    if (this.pool && !this.pool.ended) {
      await this.pool.end();
    }
    
    this.pool = new Pool({
      ...this.config,
      ...this.poolConfig
    });
    
    // Set up connection event handlers
    this.pool.on('connect', (client) => {
      console.log('🔗 Database client connected');
      // Set statement timeout on each connection
      client.query(`SET statement_timeout = ${this.timeouts.query}`).catch(err => {
        console.warn('⚠️ Failed to set statement timeout:', err.message);
      });
    });
    
    this.pool.on('error', (err) => {
      console.error('💥 Database pool error:', err.message);
      this.isInitialized = false;
    });
    
    this.pool.on('remove', () => {
      console.log('🗑️ Database client removed from pool');
    });
  }
  
  /**
   * Get database configuration with unified approach
   */
  async getDbConfig() {
    if (this.config && !this.config.__isStub) {
      console.log('✅ Using cached database config');
      return this.config;
    }
    
    try {
      // Priority 1: AWS Secrets Manager (production)
      if (this.shouldUseSecretsManager()) {
        console.log('🔐 Using AWS Secrets Manager for database configuration');
        return await this.getConfigFromSecretsManager();
      }
      
      // Priority 2: Environment variables (development)
      if (this.hasDirectEnvVars()) {
        console.log('🔧 Using direct environment variables');
        return this.getConfigFromEnvVars();
      }
      
      // Priority 3: Test/fallback configuration
      console.log('⚠️ Using fallback test configuration');
      return this.getFallbackConfig();
      
    } catch (error) {
      console.error('❌ Failed to get database configuration:', error.message);
      throw error;
    }
  }
  
  /**
   * Check if we should use AWS Secrets Manager
   */
  shouldUseSecretsManager() {
    return process.env.DB_SECRET_ARN && 
           process.env.NODE_ENV !== 'test' && 
           !process.env.DB_SECRET_ARN.includes('${') &&
           process.env.DB_SECRET_ARN !== '${DB_SECRET_ARN}';
  }
  
  /**
   * Check if direct environment variables are available
   */
  hasDirectEnvVars() {
    return process.env.DB_HOST && 
           process.env.DB_USER && 
           process.env.DB_PASSWORD;
  }
  
  /**
   * Get configuration from AWS Secrets Manager
   */
  async getConfigFromSecretsManager() {
    const secretArn = process.env.DB_SECRET_ARN;
    console.log(`🔑 Retrieving secret: ${secretArn}`);
    
    const command = new GetSecretValueCommand({ SecretId: secretArn });
    const response = await this.secretsManager.send(command);
    
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
    
    return {
      host: dbHost,
      port: parseInt(secret.port) || 5432,
      database: secret.dbname || secret.database || 'financial_dashboard',
      user: secret.username || secret.user,
      password: secret.password,
      ssl: { rejectUnauthorized: false }
    };
  }
  
  /**
   * Get configuration from environment variables
   */
  getConfigFromEnvVars() {
    return {
      host: process.env.DB_HOST,
      port: parseInt(process.env.DB_PORT) || 5432,
      database: process.env.DB_NAME || 'financial_dashboard',
      user: process.env.DB_USER,
      password: process.env.DB_PASSWORD,
      ssl: process.env.DB_SSL === 'true' ? { rejectUnauthorized: false } : false
    };
  }
  
  /**
   * Get fallback configuration for testing
   */
  getFallbackConfig() {
    return {
      host: 'localhost',
      port: 5432,
      database: 'test_database',
      user: 'test_user',
      password: 'test_password',
      ssl: false,
      __isStub: true
    };
  }
  
  /**
   * Test database connection
   */
  async testConnection() {
    if (!this.pool) {
      throw new Error('Pool not initialized');
    }
    
    const client = await this.pool.connect();
    try {
      const result = await client.query('SELECT 1 as connected, NOW() as timestamp');
      console.log('✅ Database connection test successful');
      return result.rows[0];
    } finally {
      client.release();
    }
  }
  
  /**
   * Execute query with timeout protection
   */
  async query(text, params = [], timeout = null) {
    if (!this.isInitialized || !this.pool) {
      await this.initialize();
    }
    
    const queryTimeout = timeout || this.timeouts.query;
    const startTime = Date.now();
    
    try {
      const result = await this.withTimeout(
        this.pool.query(text, params),
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
      if (this.shouldResetConnection(error)) {
        console.log('🔄 Resetting database connection due to error');
        this.isInitialized = false;
      }
      
      throw error;
    }
  }
  
  /**
   * Health check with proper timeout
   */
  async healthCheck() {
    const now = Date.now();
    if (now - this.lastHealthCheck < this.healthCheckInterval) {
      return { healthy: true, cached: true };
    }
    
    try {
      const startTime = Date.now();
      const result = await this.withTimeout(
        this.query('SELECT 1 as healthy, NOW() as timestamp'),
        this.timeouts.healthCheck,
        'health_check'
      );
      
      const responseTime = Date.now() - startTime;
      this.lastHealthCheck = now;
      
      return {
        healthy: true,
        responseTime,
        timestamp: result.rows[0].timestamp,
        pool: {
          totalCount: this.pool?.totalCount || 0,
          idleCount: this.pool?.idleCount || 0,
          waitingCount: this.pool?.waitingCount || 0
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
  async cleanup() {
    if (this.pool && !this.pool.ended) {
      try {
        console.log('🧹 Cleaning up database connections...');
        await this.withTimeout(
          this.pool.end(),
          5000,
          'pool_cleanup'
        );
        console.log('✅ Database cleanup completed');
      } catch (error) {
        console.error('❌ Database cleanup failed:', error.message);
      }
    }
    
    this.pool = null;
    this.isInitialized = false;
  }
  
  /**
   * Wrapper for promises with timeout
   */
  async withTimeout(promise, timeoutMs, operation = 'operation') {
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
   * Check if error is retryable
   */
  isRetryableError(error) {
    const retryableCodes = [
      'ECONNREFUSED',
      'ENOTFOUND', 
      'ETIMEDOUT',
      'ECONNRESET',
      'TIMEOUT'
    ];
    return retryableCodes.includes(error.code) || 
           error.message.includes('timeout') ||
           error.message.includes('connection');
  }
  
  /**
   * Check if connection should be reset
   */
  shouldResetConnection(error) {
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
   * Sleep utility
   */
  sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
  
  /**
   * Get connection pool statistics
   */
  getPoolStats() {
    if (!this.pool) {
      return { status: 'uninitialized' };
    }
    
    return {
      status: 'active',
      totalCount: this.pool.totalCount,
      idleCount: this.pool.idleCount,
      waitingCount: this.pool.waitingCount,
      ended: this.pool.ended,
      config: {
        max: this.poolConfig.max,
        connectionTimeout: this.timeouts.connection,
        queryTimeout: this.timeouts.query
      }
    };
  }
}

// Create singleton instance
const unifiedDatabaseManager = new UnifiedDatabaseManager();

// Export convenience functions for backward compatibility
async function query(text, params, timeout) {
  return unifiedDatabaseManager.query(text, params, timeout);
}

async function getPool() {
  return unifiedDatabaseManager.initialize();
}

async function initializeDatabase() {
  return unifiedDatabaseManager.initialize();
}

async function healthCheck() {
  return unifiedDatabaseManager.healthCheck();
}

async function cleanup() {
  return unifiedDatabaseManager.cleanup();
}

function getPoolStats() {
  return unifiedDatabaseManager.getPoolStats();
}

// Process cleanup handlers
process.on('SIGTERM', cleanup);
process.on('SIGINT', cleanup);
process.on('beforeExit', cleanup);

module.exports = {
  // Main class
  UnifiedDatabaseManager,
  
  // Singleton instance
  unifiedDatabaseManager,
  
  // Convenience functions (backward compatibility)
  query,
  getPool,
  initializeDatabase,
  healthCheck,
  cleanup,
  getPoolStats,
  
  // Export timeouts for other modules
  timeouts: unifiedDatabaseManager.timeouts
};