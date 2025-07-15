/**
 * Database Connection Manager - Production-Grade Resilience
 * Handles connection pooling, timeouts, retries, and circuit breaker pattern
 */

const { Pool } = require('pg');

class DatabaseConnectionManager {
  constructor() {
    this.pool = null;
    this.isConnected = false;
    this.connectionAttempts = 0;
    this.maxRetries = 3;
    this.retryDelayMs = 1000;
    this.circuitBreakerState = 'CLOSED'; // CLOSED, OPEN, HALF_OPEN
    this.circuitBreakerTimeout = 30000; // 30 seconds
    this.lastFailureTime = null;
    this.connectionPromise = null;
  }

  /**
   * Get database configuration with resilience settings
   */
  async getDatabaseConfig() {
    const secretsLoader = require('./secretsLoader');
    
    try {
      console.log('🔍 Loading database configuration...');
      const config = await secretsLoader.getSecretsValue(process.env.DB_SECRET_ARN);
      
      const dbConfig = JSON.parse(config);
      
      return {
        host: dbConfig.host || process.env.DB_ENDPOINT,
        port: dbConfig.port || 5432,
        database: dbConfig.dbname || 'stocks',
        user: dbConfig.username,
        password: dbConfig.password,
        ssl: { rejectUnauthorized: false },
        // Resilience settings
        max: 3, // Maximum pool size
        min: 1, // Minimum pool size
        acquireTimeoutMillis: 10000, // 10 seconds to get connection from pool
        createTimeoutMillis: 15000, // 15 seconds to create new connection
        destroyTimeoutMillis: 5000, // 5 seconds to destroy connection
        idleTimeoutMillis: 30000, // 30 seconds idle timeout
        reapIntervalMillis: 1000, // Check for idle connections every second
        createRetryIntervalMillis: 200,
        connectionTimeoutMillis: 15000 // 15 seconds connection timeout
      };
    } catch (error) {
      console.error('❌ Failed to get database configuration:', error);
      throw new Error(`Database configuration failed: ${error.message}`);
    }
  }

  /**
   * Circuit breaker pattern for database connections
   */
  async checkCircuitBreaker() {
    if (this.circuitBreakerState === 'OPEN') {
      const timeSinceFailure = Date.now() - this.lastFailureTime;
      
      if (timeSinceFailure > this.circuitBreakerTimeout) {
        console.log('🔄 Circuit breaker transitioning to HALF_OPEN');
        this.circuitBreakerState = 'HALF_OPEN';
      } else {
        const remainingTime = Math.ceil((this.circuitBreakerTimeout - timeSinceFailure) / 1000);
        throw new Error(`Circuit breaker is OPEN. Database unavailable for ${remainingTime} more seconds.`);
      }
    }
  }

  /**
   * Record circuit breaker failure
   */
  recordFailure() {
    this.connectionAttempts++;
    this.lastFailureTime = Date.now();
    
    if (this.connectionAttempts >= this.maxRetries) {
      console.error('🚨 Circuit breaker opening due to repeated failures');
      this.circuitBreakerState = 'OPEN';
      this.connectionAttempts = 0;
    }
  }

  /**
   * Record circuit breaker success
   */
  recordSuccess() {
    this.connectionAttempts = 0;
    this.circuitBreakerState = 'CLOSED';
    this.isConnected = true;
  }

  /**
   * Initialize database connection with retry logic
   */
  async initializeConnection() {
    // Prevent multiple simultaneous initialization attempts
    if (this.connectionPromise) {
      console.log('🔄 Database connection already in progress, waiting...');
      return this.connectionPromise;
    }

    this.connectionPromise = this._doInitializeConnection();
    
    try {
      const result = await this.connectionPromise;
      return result;
    } finally {
      this.connectionPromise = null;
    }
  }

  async _doInitializeConnection() {
    try {
      // Check circuit breaker
      await this.checkCircuitBreaker();

      console.log('🚀 Initializing database connection with resilience patterns...');
      
      const config = await this.getDatabaseConfig();
      
      // Create connection pool
      this.pool = new Pool(config);
      
      // Setup pool event handlers
      this.pool.on('connect', (client) => {
        console.log('✅ Database client connected');
      });
      
      this.pool.on('acquire', (client) => {
        console.log('🔗 Database client acquired from pool');
      });
      
      this.pool.on('remove', (client) => {
        console.log('🗑️ Database client removed from pool');
      });
      
      this.pool.on('error', (err, client) => {
        console.error('❌ Database pool error:', err);
        this.recordFailure();
      });

      // Test connection with timeout
      console.log('🧪 Testing database connection...');
      const testStart = Date.now();
      
      const testClient = await Promise.race([
        this.pool.connect(),
        new Promise((_, reject) => 
          setTimeout(() => reject(new Error('Connection test timeout')), 10000)
        )
      ]);
      
      const testResult = await testClient.query('SELECT NOW() as current_time');
      testClient.release();
      
      const testDuration = Date.now() - testStart;
      console.log(`✅ Database connection test successful in ${testDuration}ms`);
      console.log(`🕐 Database time: ${testResult.rows[0].current_time}`);
      
      this.recordSuccess();
      
      return {
        success: true,
        pool: this.pool,
        testDuration,
        serverTime: testResult.rows[0].current_time
      };
      
    } catch (error) {
      console.error('❌ Database connection failed:', error);
      this.recordFailure();
      
      // Cleanup failed pool
      if (this.pool) {
        try {
          await this.pool.end();
        } catch (cleanupError) {
          console.error('❌ Error cleaning up failed pool:', cleanupError);
        }
        this.pool = null;
      }
      
      throw new Error(`Database connection failed: ${error.message}`);
    }
  }

  /**
   * Get database pool with health check
   */
  async getPool() {
    if (!this.pool || !this.isConnected) {
      console.log('🔄 Database not connected, initializing...');
      await this.initializeConnection();
    }
    
    return this.pool;
  }

  /**
   * Execute query with error handling and retries
   */
  async query(text, params = [], options = {}) {
    const { timeout = 15000, retries = 1 } = options;
    
    for (let attempt = 1; attempt <= retries; attempt++) {
      try {
        await this.checkCircuitBreaker();
        
        const pool = await this.getPool();
        
        const result = await Promise.race([
          pool.query(text, params),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error('Query timeout')), timeout)
          )
        ]);
        
        this.recordSuccess();
        return result;
        
      } catch (error) {
        console.error(`❌ Query attempt ${attempt} failed:`, error);
        
        if (attempt === retries) {
          this.recordFailure();
          throw error;
        }
        
        // Wait before retry
        await new Promise(resolve => setTimeout(resolve, this.retryDelayMs * attempt));
      }
    }
  }

  /**
   * Health check for monitoring
   */
  async healthCheck() {
    try {
      const start = Date.now();
      const result = await this.query('SELECT 1 as health_check', [], { timeout: 5000 });
      const duration = Date.now() - start;
      
      return {
        healthy: true,
        duration,
        circuitBreakerState: this.circuitBreakerState,
        isConnected: this.isConnected,
        connectionAttempts: this.connectionAttempts
      };
    } catch (error) {
      return {
        healthy: false,
        error: error.message,
        circuitBreakerState: this.circuitBreakerState,
        isConnected: this.isConnected,
        connectionAttempts: this.connectionAttempts
      };
    }
  }

  /**
   * Graceful shutdown
   */
  async shutdown() {
    if (this.pool) {
      console.log('🛑 Shutting down database connection pool...');
      await this.pool.end();
      this.pool = null;
      this.isConnected = false;
    }
  }
}

// Singleton instance
const databaseManager = new DatabaseConnectionManager();

module.exports = databaseManager;