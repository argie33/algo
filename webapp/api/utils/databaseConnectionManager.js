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
      const config = await secretsLoader.getSecret(process.env.DB_SECRET_ARN);
      
      // Config is already parsed by secretsLoader - no need to parse again
      const dbConfig = typeof config === 'string' ? JSON.parse(config) : config;
      
      return {
        host: dbConfig.host || process.env.DB_ENDPOINT,
        port: dbConfig.port || 5432,
        database: dbConfig.dbname || 'stocks',
        user: dbConfig.username,
        password: dbConfig.password,
        ssl: { rejectUnauthorized: false },
        // Resilience settings - INCREASED TIMEOUTS
        max: 5, // Maximum pool size
        min: 0, // Minimum pool size - allow complete pool drain
        acquireTimeoutMillis: 30000, // 30 seconds to get connection from pool
        createTimeoutMillis: 45000, // 45 seconds to create new connection
        destroyTimeoutMillis: 10000, // 10 seconds to destroy connection
        idleTimeoutMillis: 60000, // 60 seconds idle timeout
        reapIntervalMillis: 5000, // Check for idle connections every 5 seconds
        createRetryIntervalMillis: 1000, // 1 second between retry attempts
        connectionTimeoutMillis: 45000, // 45 seconds connection timeout
        // Additional PostgreSQL specific settings
        keepAlive: true,
        keepAliveInitialDelayMillis: 10000,
        statement_timeout: 30000, // 30 second query timeout
        query_timeout: 30000, // 30 second query timeout
        // Connection monitoring settings
        monitorConnections: true,
        poolIdleTimeoutMillis: 30000, // 30 seconds idle timeout
        poolMaxUses: 5000, // Maximum uses per connection
        poolEvictionRunIntervalMillis: 30000 // Run eviction every 30 seconds
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
    console.log('✅ Circuit breaker recording success - transitioning to CLOSED');
    this.connectionAttempts = 0;
    this.circuitBreakerState = 'CLOSED';
    this.isConnected = true;
    this.lastFailureTime = null;
  }

  /**
   * Force circuit breaker reset (for admin/recovery purposes)
   */
  forceReset() {
    console.log('🔄 Force resetting circuit breaker to CLOSED state');
    this.connectionAttempts = 0;
    this.circuitBreakerState = 'CLOSED';
    this.isConnected = false;
    this.lastFailureTime = null;
  }

  /**
   * Get circuit breaker health status
   */
  getCircuitBreakerStatus() {
    return {
      state: this.circuitBreakerState,
      connectionAttempts: this.connectionAttempts,
      lastFailureTime: this.lastFailureTime,
      isConnected: this.isConnected,
      nextAttemptAllowed: this.circuitBreakerState === 'OPEN' 
        ? this.lastFailureTime + this.circuitBreakerTimeout 
        : Date.now(),
      timeUntilNextAttempt: this.circuitBreakerState === 'OPEN' 
        ? Math.max(0, (this.lastFailureTime + this.circuitBreakerTimeout) - Date.now())
        : 0
    };
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
   * Get database pool with health check and monitoring
   */
  async getPool() {
    if (!this.pool || !this.isConnected) {
      console.log('🔄 Database not connected, initializing...');
      await this.initializeConnection();
    }
    
    // Monitor pool health
    if (this.pool) {
      const poolStats = {
        totalCount: this.pool.totalCount,
        idleCount: this.pool.idleCount,
        waitingCount: this.pool.waitingCount
      };
      
      // Log pool stats if concerning
      if (poolStats.waitingCount > 0) {
        console.log('⚠️ Database pool waiting queue detected:', poolStats);
      }
      
      if (poolStats.idleCount === 0 && poolStats.totalCount >= 5) {
        console.log('🔥 Database pool at maximum capacity:', poolStats);
      }
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
   * Health check for monitoring with pool statistics
   */
  async healthCheck() {
    try {
      const start = Date.now();
      const result = await this.query('SELECT 1 as health_check', [], { timeout: 5000 });
      const duration = Date.now() - start;
      
      // Get pool statistics
      const poolStats = this.pool ? {
        totalCount: this.pool.totalCount,
        idleCount: this.pool.idleCount,
        waitingCount: this.pool.waitingCount,
        maxConnections: this.pool.options.max,
        minConnections: this.pool.options.min
      } : null;
      
      return {
        healthy: true,
        duration,
        circuitBreakerState: this.circuitBreakerState,
        isConnected: this.isConnected,
        connectionAttempts: this.connectionAttempts,
        poolStats,
        recommendations: this.generatePoolRecommendations(poolStats)
      };
    } catch (error) {
      return {
        healthy: false,
        error: error.message,
        circuitBreakerState: this.circuitBreakerState,
        isConnected: this.isConnected,
        connectionAttempts: this.connectionAttempts,
        poolStats: null
      };
    }
  }

  /**
   * Generate pool optimization recommendations
   */
  generatePoolRecommendations(poolStats) {
    if (!poolStats) return [];
    
    const recommendations = [];
    
    // Check for high utilization
    const utilization = (poolStats.totalCount - poolStats.idleCount) / poolStats.maxConnections;
    if (utilization > 0.8) {
      recommendations.push({
        type: 'high_utilization',
        message: `Pool utilization at ${Math.round(utilization * 100)}%`,
        action: 'Consider increasing max pool size'
      });
    }
    
    // Check for waiting connections
    if (poolStats.waitingCount > 0) {
      recommendations.push({
        type: 'connection_waiting',
        message: `${poolStats.waitingCount} connections waiting`,
        action: 'Pool may be undersized for current load'
      });
    }
    
    // Check for over-provisioning
    if (poolStats.idleCount > poolStats.maxConnections * 0.7) {
      recommendations.push({
        type: 'over_provisioned',
        message: `${poolStats.idleCount} idle connections`,
        action: 'Consider reducing max pool size'
      });
    }
    
    return recommendations;
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