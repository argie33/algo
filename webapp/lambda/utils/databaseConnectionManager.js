/**
 * Database Connection Manager with Circuit Breaker Integration
 */
const { Pool } = require('pg');
const DatabaseCircuitBreaker = require('./databaseCircuitBreaker');

class DatabaseConnectionManager {
  constructor() {
    this.pool = null;
    this.circuitBreaker = new DatabaseCircuitBreaker();
    this.isInitialized = false;
    this.config = null;
    this.lastHealthCheck = 0;
    this.healthCheckInterval = 30000; // 30 seconds
  }
  
  async initialize() {
    if (this.isInitialized && this.pool) {
      return this.pool;
    }
    
    try {
      console.log('🔄 Initializing database connection with circuit breaker...');
      
      // Get database configuration
      this.config = await this.getDbConfig();
      
      // Create connection pool
      this.pool = new Pool({
        ...this.config,
        // Lambda-optimized settings
        max: 10, // Maximum connections
        min: 1,  // Minimum connections
        acquireTimeoutMillis: 15000, // 15 seconds
        createTimeoutMillis: 20000,  // 20 seconds
        destroyTimeoutMillis: 5000,  // 5 seconds
        idleTimeoutMillis: 30000,    // 30 seconds
        reapIntervalMillis: 1000,    // 1 second
        createRetryIntervalMillis: 200, // 200ms
        keepAlive: true,
        keepAliveInitialDelayMillis: 10000
      });
      
      // Test initial connection (skip for stub configuration)
      if (!this.config.__isStub) {
        await this.testConnection();
      } else {
        console.log('⚠️ Skipping connection test for stub configuration');
      }
      
      this.isInitialized = true;
      console.log('✅ Database connection initialized successfully');
      
      return this.pool;
    } catch (error) {
      console.error('❌ Database initialization failed:', error);
      this.pool = null;
      this.isInitialized = false;
      throw error;
    }
  }
  
  async getDbConfig() {
    // Try environment variables first
    if (process.env.DB_HOST && process.env.DB_USER && process.env.DB_PASSWORD) {
      console.log('🔧 Using direct environment variables');
      return {
        host: process.env.DB_HOST,
        port: parseInt(process.env.DB_PORT) || 5432,
        database: process.env.DB_NAME || 'stocks',
        user: process.env.DB_USER,
        password: process.env.DB_PASSWORD,
        ssl: process.env.DB_SSL === 'true' ? { rejectUnauthorized: false } : false
      };
    }
    
    // Fallback to AWS Secrets Manager (skip in test environment and invalid ARNs)
    if (process.env.DB_SECRET_ARN && 
        process.env.NODE_ENV !== 'test' && 
        !process.env.DB_SECRET_ARN.includes('${') && 
        process.env.DB_SECRET_ARN !== '${DB_SECRET_ARN}') {
      console.log('🔧 Using AWS Secrets Manager fallback');
      const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
      
      const client = new SecretsManagerClient({
        region: process.env.AWS_REGION || 'us-east-1'
      });
      
      try {
        const response = await client.send(new GetSecretValueCommand({
          SecretId: process.env.DB_SECRET_ARN
        }));
        
        // Enhanced JSON parsing with error handling
        let secret;
        try {
          secret = JSON.parse(response.SecretString);
        } catch (parseError) {
          console.error('❌ JSON parsing error for secret:', parseError);
          console.error('Secret string length:', response.SecretString?.length);
          console.error('Secret string preview:', response.SecretString?.substring(0, 100));
          throw new Error('Failed to parse database secret JSON: ' + parseError.message);
        }
        
        return {
          host: secret.host || process.env.DB_HOST,
          port: secret.port || parseInt(process.env.DB_PORT) || 5432,
          database: secret.dbname || secret.database || 'stocks',
          user: secret.username || secret.user,
          password: secret.password,
          ssl: secret.ssl || process.env.DB_SSL === 'true' ? { rejectUnauthorized: false } : false
        };
      } catch (error) {
        console.error('❌ Failed to get secret from AWS Secrets Manager:', error);
        throw error;
      }
    }
    
    // Final fallback for test environment or misconfigured production
    const isConfigurationError = process.env.DB_SECRET_ARN && process.env.DB_SECRET_ARN.includes('${');
    if (isConfigurationError) {
      console.error('❌ Invalid DB_SECRET_ARN detected - returning stub configuration');
      return {
        host: 'localhost',
        port: 5432,
        database: 'unavailable',
        user: 'unavailable',
        password: 'unavailable',
        __isStub: true,
        __error: `Invalid DB_SECRET_ARN: ${process.env.DB_SECRET_ARN}`
      };
    }
    
    console.log('🔧 Using test environment database fallback');
    return {
      host: 'localhost',
      port: 5432,
      database: 'financial_platform_test',
      user: 'postgres',
      password: ''
    };
  }
  
  async testConnection() {
    return this.circuitBreaker.execute(async () => {
      const client = await this.pool.connect();
      try {
        await client.query('SELECT 1');
        return true;
      } finally {
        client.release();
      }
    }, 'connection-test');
  }
  
  async query(text, params = []) {
    // Initialize if needed
    if (!this.isInitialized) {
      await this.initialize();
    }
    
    // Handle stub configuration
    if (this.config.__isStub) {
      throw new Error(`Database unavailable: ${this.config.__error}`);
    }
    
    // Periodic health check
    const now = Date.now();
    if (now - this.lastHealthCheck > this.healthCheckInterval) {
      try {
        await this.testConnection();
        this.lastHealthCheck = now;
      } catch (error) {
        console.warn('⚠️ Health check failed:', error.message);
      }
    }
    
    // Execute query through circuit breaker
    return this.circuitBreaker.execute(async () => {
      const client = await this.pool.connect();
      try {
        const result = await client.query(text, params);
        return result;
      } finally {
        client.release();
      }
    }, 'database-query');
  }
  
  getStatus() {
    return {
      initialized: this.isInitialized,
      pool: this.pool ? {
        totalCount: this.pool.totalCount,
        idleCount: this.pool.idleCount,
        waitingCount: this.pool.waitingCount
      } : null,
      circuitBreaker: this.circuitBreaker.getStatus()
    };
  }
  
  async healthCheck() {
    try {
      // Initialize database if not already done
      if (!this.isInitialized || !this.pool) {
        await this.initialize();
      }
      
      await this.testConnection();
      const status = this.getStatus();
      
      return {
        healthy: true,
        status: status,
        message: 'Database connection healthy'
      };
    } catch (error) {
      return {
        healthy: false,
        error: error.message,
        status: this.getStatus()
      };
    }
  }
  
  // Emergency recovery methods
  async forceReset() {
    console.log('🚨 EMERGENCY: Force resetting database connection...');
    this.circuitBreaker.forceReset();
    
    if (this.pool) {
      await this.pool.end();
      this.pool = null;
    }
    
    this.isInitialized = false;
    await this.initialize();
    console.log('✅ Database connection force reset completed');
  }
}

// Export singleton instance
module.exports = new DatabaseConnectionManager();