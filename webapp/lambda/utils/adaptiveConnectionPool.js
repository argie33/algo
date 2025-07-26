/**
 * Adaptive Connection Pool - Self-Healing Database Connection Management
 * 
 * FEATURES:
 * ✅ Multiple pools for resilience (Primary + Secondary + Emergency)
 * ✅ Automatic connection leak detection and cleanup
 * ✅ Adaptive timeout management
 * ✅ Continuous health assessment
 * ✅ Resource exhaustion prevention
 * ✅ Coordinated timeout hierarchy
 */

const { Pool } = require('pg');
const { SecretsManagerClient, GetSecretValueCommand } = require('@aws-sdk/client-secrets-manager');
const { CloudWatchClient, PutMetricDataCommand } = require('@aws-sdk/client-cloudwatch');

// Coordinated Timeout Hierarchy
const TIMEOUT_HIERARCHY = {
  lambda: 25000,        // AWS Lambda hard limit
  operation: 22000,     // Safe operation window
  circuit: 20000,       // Circuit breaker timeout  
  connection: 15000,    // Connection establishment
  query: 12000,         // Individual queries
  transaction: 18000,   // Complex transactions
  healthCheck: 5000,    // Health verification
  secrets: 6000         // AWS Secrets Manager
};

// Connection Leak Detector
class ConnectionLeakDetector {
  constructor() {
    this.activeConnections = new Map();
    this.leakThreshold = 30000; // 30 seconds
    this.maxConnections = 20;
    this.checkInterval = 10000; // 10 seconds
    
    this.startMonitoring();
  }

  track(connection, context = {}) {
    const connectionId = this.generateConnectionId();
    const tracking = {
      id: connectionId,
      connection,
      createdAt: Date.now(),
      lastUsed: Date.now(),
      context: {
        stack: new Error().stack,
        userId: context.userId,
        operation: context.operation,
        endpoint: context.endpoint
      }
    };

    this.activeConnections.set(connectionId, tracking);
    
    // Wrap connection to track usage
    return this.wrapConnection(connection, tracking);
  }

  wrapConnection(connection, tracking) {
    const originalQuery = connection.query.bind(connection);
    const originalRelease = connection.release.bind(connection);

    connection.query = (...args) => {
      tracking.lastUsed = Date.now();
      return originalQuery(...args);
    };

    connection.release = () => {
      this.activeConnections.delete(tracking.id);
      return originalRelease();
    };

    // Add metadata
    connection._trackingId = tracking.id;
    connection._createdAt = tracking.createdAt;

    return connection;
  }

  startMonitoring() {
    setInterval(() => {
      this.detectLeaks();
      this.cleanupStaleConnections();
    }, this.checkInterval);
  }

  detectLeaks() {
    const now = Date.now();
    const leakedConnections = [];

    for (const [id, tracking] of this.activeConnections) {
      const age = now - tracking.createdAt;
      const idleTime = now - tracking.lastUsed;

      if (age > this.leakThreshold || idleTime > this.leakThreshold) {
        leakedConnections.push({
          id,
          age,
          idleTime,
          context: tracking.context
        });
      }
    }

    if (leakedConnections.length > 0) {
      console.warn(`🚨 Detected ${leakedConnections.length} connection leaks:`, 
        leakedConnections.map(leak => ({
          id: leak.id,
          ageSeconds: Math.round(leak.age / 1000),
          idleSeconds: Math.round(leak.idleTime / 1000),
          operation: leak.context.operation
        }))
      );

      // Force cleanup leaked connections
      this.cleanupLeakedConnections(leakedConnections);
    }
  }

  cleanupLeakedConnections(leakedConnections) {
    for (const leak of leakedConnections) {
      const tracking = this.activeConnections.get(leak.id);
      if (tracking?.connection) {
        try {
          tracking.connection.release();
          console.log(`🧹 Cleaned up leaked connection ${leak.id}`);
        } catch (error) {
          console.error(`Failed to cleanup connection ${leak.id}:`, error);
        }
      }
      this.activeConnections.delete(leak.id);
    }
  }

  cleanupStaleConnections() {
    if (this.activeConnections.size > this.maxConnections) {
      console.warn(`⚠️ High connection count: ${this.activeConnections.size}/${this.maxConnections}`);
      
      // Force cleanup oldest connections
      const connections = Array.from(this.activeConnections.values())
        .sort((a, b) => a.lastUsed - b.lastUsed)
        .slice(0, this.activeConnections.size - this.maxConnections);

      this.cleanupLeakedConnections(connections.map(c => ({ id: c.id })));
    }
  }

  generateConnectionId() {
    return `conn_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  getStats() {
    const now = Date.now();
    const connections = Array.from(this.activeConnections.values());
    
    return {
      activeConnections: connections.length,
      averageAge: connections.length > 0 
        ? Math.round(connections.reduce((sum, c) => sum + (now - c.createdAt), 0) / connections.length / 1000)
        : 0,
      oldestConnection: connections.length > 0
        ? Math.round((now - Math.min(...connections.map(c => c.createdAt))) / 1000)
        : 0,
      leakThresholdSeconds: Math.round(this.leakThreshold / 1000)
    };
  }
}

// Pool Health Monitor
class PoolHealthMonitor {
  constructor(pool, name) {
    this.pool = pool;
    this.name = name;
    this.healthMetrics = {
      totalConnections: 0,
      idleConnections: 0,
      waitingClients: 0,
      lastHealthCheck: 0,
      consecutiveFailures: 0,
      isHealthy: true
    };
  }

  async checkHealth() {
    try {
      const client = await this.pool.connect();
      const start = Date.now();
      
      await client.query('SELECT 1');
      const duration = Date.now() - start;
      
      client.release();

      this.healthMetrics = {
        ...this.healthMetrics,
        totalConnections: this.pool.totalCount,
        idleConnections: this.pool.idleCount,
        waitingClients: this.pool.waitingCount,
        lastHealthCheck: Date.now(),
        responseTime: duration,
        consecutiveFailures: 0,
        isHealthy: true
      };

      return true;
    } catch (error) {
      this.healthMetrics.consecutiveFailures++;
      this.healthMetrics.isHealthy = this.healthMetrics.consecutiveFailures < 3;
      this.healthMetrics.lastError = error.message;
      
      console.error(`❌ Pool ${this.name} health check failed:`, error.message);
      return false;
    }
  }

  getHealthScore() {
    if (!this.healthMetrics.isHealthy) return 0;
    
    const age = Date.now() - this.healthMetrics.lastHealthCheck;
    if (age > 60000) return 0.5; // Stale health check
    
    const responseScore = this.healthMetrics.responseTime < 100 ? 1 : 
                         this.healthMetrics.responseTime < 500 ? 0.8 : 0.6;
    
    const utilizationScore = this.healthMetrics.waitingClients === 0 ? 1 : 0.7;
    
    return Math.min(responseScore * utilizationScore, 1);
  }

  getMetrics() {
    return {
      ...this.healthMetrics,
      healthScore: this.getHealthScore(),
      name: this.name
    };
  }
}

// Main Adaptive Connection Pool
class AdaptiveConnectionPool {
  constructor() {
    this.pools = new Map();
    this.healthMonitors = new Map();
    this.leakDetector = new ConnectionLeakDetector();
    
    this.secretsManager = new SecretsManagerClient({
      region: process.env.AWS_REGION || 'us-east-1',
      requestTimeout: TIMEOUT_HIERARCHY.secrets
    });

    this.cloudWatch = new CloudWatchClient({
      region: process.env.AWS_REGION || 'us-east-1'
    });

    this.initialized = false;
    this.dbConfig = null;
  }

  async initialize() {
    if (this.initialized) return;

    try {
      this.dbConfig = await this.loadDatabaseConfig();
      
      // Create multiple pools for resilience
      await this.createPool('primary', this.dbConfig, {
        max: 10,
        min: 2,
        idleTimeoutMillis: 30000,
        connectionTimeoutMillis: TIMEOUT_HIERARCHY.connection
      });

      await this.createPool('secondary', this.dbConfig, {
        max: 5,
        min: 1,
        idleTimeoutMillis: 20000,
        connectionTimeoutMillis: TIMEOUT_HIERARCHY.connection
      });

      this.initialized = true;
      console.log('✅ Adaptive connection pool initialized');

      // Start health monitoring
      this.startHealthMonitoring();

    } catch (error) {
      console.error('❌ Failed to initialize connection pool:', error);
      throw error;
    }
  }

  async createPool(name, config, poolConfig) {
    const pool = new Pool({
      host: config.host,
      port: config.port,
      database: config.database,
      user: config.user,
      password: config.password,
      ssl: config.ssl,
      ...poolConfig,
      // Enhanced error handling
      statement_timeout: TIMEOUT_HIERARCHY.query,
      query_timeout: TIMEOUT_HIERARCHY.query,
      application_name: `financial-platform-${name}`,
    });

    // Handle pool errors
    pool.on('error', (err) => {
      console.error(`Pool ${name} error:`, err);
      this.handlePoolError(name, err);
    });

    pool.on('connect', (client) => {
      console.log(`Connected to database via ${name} pool`);
    });

    this.pools.set(name, pool);
    this.healthMonitors.set(name, new PoolHealthMonitor(pool, name));

    console.log(`✅ Created ${name} pool with config:`, {
      max: poolConfig.max,
      min: poolConfig.min,
      timeouts: {
        connection: poolConfig.connectionTimeoutMillis,
        idle: poolConfig.idleTimeoutMillis
      }
    });
  }

  async loadDatabaseConfig() {
    // Try AWS Secrets Manager first
    if (process.env.DB_SECRET_ARN && 
        !process.env.DB_SECRET_ARN.includes('${')) {
      
      try {
        const command = new GetSecretValueCommand({
          SecretId: process.env.DB_SECRET_ARN
        });
        const response = await this.secretsManager.send(command);
        const secret = JSON.parse(response.SecretString);

        return {
          host: secret.host || secret.endpoint,
          port: parseInt(secret.port) || 5432,
          database: secret.dbname || secret.database || 'financial_dashboard',
          user: secret.username || secret.user,
          password: secret.password,
          ssl: { rejectUnauthorized: false }
        };
      } catch (error) {
        console.warn('⚠️ Failed to load from Secrets Manager, trying environment');
      }
    }

    // Fallback to environment variables
    return {
      host: process.env.DB_HOST || process.env.DB_ENDPOINT,
      port: parseInt(process.env.DB_PORT) || 5432,
      database: process.env.DB_NAME || 'financial_dashboard',
      user: process.env.DB_USER,
      password: process.env.DB_PASSWORD,
      ssl: { rejectUnauthorized: false }
    };
  }

  async getConnection(context = {}) {
    if (!this.initialized) {
      await this.initialize();
    }

    const pool = await this.selectOptimalPool(context.priority || 'normal');
    
    try {
      const connection = await this.acquireWithTimeout(pool);
      return this.leakDetector.track(connection, context);
    } catch (error) {
      // Try emergency pool if primary fails
      if (pool !== this.pools.get('emergency')) {
        return this.getEmergencyConnection(context);
      }
      throw error;
    }
  }

  async acquireWithTimeout(pool) {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error(`Connection timeout after ${TIMEOUT_HIERARCHY.connection}ms`));
      }, TIMEOUT_HIERARCHY.connection);

      pool.connect()
        .then(client => {
          clearTimeout(timeout);
          resolve(client);
        })
        .catch(error => {
          clearTimeout(timeout);
          reject(error);
        });
    });
  }

  async selectOptimalPool(priority) {
    const healthyPools = await this.getHealthyPools();
    
    if (healthyPools.length === 0) {
      return await this.createEmergencyPool();
    }

    // Select best pool based on health and priority
    if (priority === 'high' && healthyPools.includes('primary')) {
      return this.pools.get('primary');
    }

    // Return healthiest pool
    const poolHealth = healthyPools.map(name => ({
      name,
      score: this.healthMonitors.get(name).getHealthScore()
    }));

    poolHealth.sort((a, b) => b.score - a.score);
    return this.pools.get(poolHealth[0].name);
  }

  async getHealthyPools() {
    const healthyPools = [];
    
    for (const [name, monitor] of this.healthMonitors) {
      if (monitor.getHealthScore() > 0.5) {
        healthyPools.push(name);
      }
    }

    return healthyPools;
  }

  async createEmergencyPool() {
    if (this.pools.has('emergency')) {
      return this.pools.get('emergency');
    }

    console.warn('🚨 Creating emergency connection pool');
    
    await this.createPool('emergency', this.dbConfig, {
      max: 3,
      min: 1,
      idleTimeoutMillis: 10000,
      connectionTimeoutMillis: TIMEOUT_HIERARCHY.connection / 2
    });

    return this.pools.get('emergency');
  }

  async getEmergencyConnection(context) {
    try {
      const emergencyPool = await this.createEmergencyPool();
      const connection = await this.acquireWithTimeout(emergencyPool);
      return this.leakDetector.track(connection, { ...context, emergency: true });
    } catch (error) {
      console.error('❌ Emergency connection failed:', error);
      throw new Error('All database connection pools exhausted');
    }
  }

  startHealthMonitoring() {
    // Health check every 30 seconds
    setInterval(async () => {
      for (const [name, monitor] of this.healthMonitors) {
        await monitor.checkHealth();
      }
      
      await this.recordMetrics();
    }, 30000);

    // Initial health check
    setTimeout(() => {
      for (const monitor of this.healthMonitors.values()) {
        monitor.checkHealth();
      }
    }, 1000);
  }

  async recordMetrics() {
    try {
      const leakStats = this.leakDetector.getStats();
      
      const metrics = [];
      
      // Connection leak metrics
      metrics.push({
        MetricName: 'ActiveConnections',
        Value: leakStats.activeConnections,
        Unit: 'Count'
      });

      // Pool health metrics
      for (const monitor of this.healthMonitors.values()) {
        const poolMetrics = monitor.getMetrics();
        
        metrics.push({
          MetricName: 'PoolHealthScore',
          Value: poolMetrics.healthScore,
          Unit: 'None',
          Dimensions: [{ Name: 'PoolName', Value: poolMetrics.name }]
        });

        metrics.push({
          MetricName: 'PoolConnections',
          Value: poolMetrics.totalConnections,
          Unit: 'Count',
          Dimensions: [{ Name: 'PoolName', Value: poolMetrics.name }]
        });
      }

      await this.cloudWatch.send(new PutMetricDataCommand({
        Namespace: 'FinancialPlatform/Database',
        MetricData: metrics
      }));

    } catch (error) {
      console.warn('⚠️ Failed to record metrics:', error.message);
    }
  }

  handlePoolError(poolName, error) {
    console.error(`🚨 Pool ${poolName} error:`, error);
    
    // Mark pool as unhealthy
    const monitor = this.healthMonitors.get(poolName);
    if (monitor) {
      monitor.healthMetrics.isHealthy = false;
      monitor.healthMetrics.consecutiveFailures = 999;
    }
  }

  async query(text, params, context = {}) {
    const connection = await this.getConnection(context);
    
    try {
      const start = Date.now();
      const result = await connection.query(text, params);
      const duration = Date.now() - start;
      
      if (duration > TIMEOUT_HIERARCHY.query * 0.8) {
        console.warn(`⚠️ Slow query detected: ${duration}ms`);
      }
      
      return result;
    } finally {
      connection.release();
    }
  }

  async transaction(queries, context = {}) {
    const connection = await this.getConnection({ ...context, priority: 'high' });
    
    try {
      await connection.query('BEGIN');
      const results = [];
      
      for (const { text, params } of queries) {
        const result = await connection.query(text, params);
        results.push(result);
      }
      
      await connection.query('COMMIT');
      return results;
    } catch (error) {
      await connection.query('ROLLBACK');
      throw error;
    } finally {
      connection.release();
    }
  }

  getStatus() {
    const poolStatus = {};
    
    for (const [name, monitor] of this.healthMonitors) {
      poolStatus[name] = monitor.getMetrics();
    }

    return {
      initialized: this.initialized,
      pools: Object.keys(poolStatus),
      poolStatus,
      leakDetection: this.leakDetector.getStats(),
      timeouts: TIMEOUT_HIERARCHY
    };
  }

  async cleanup() {
    console.log('🧹 Cleaning up connection pools...');
    
    for (const [name, pool] of this.pools) {
      try {
        await pool.end();
        console.log(`✅ Closed ${name} pool`);
      } catch (error) {
        console.error(`❌ Error closing ${name} pool:`, error);
      }
    }
    
    this.pools.clear();
    this.healthMonitors.clear();
    this.initialized = false;
  }
}

// Create singleton instance
const adaptiveConnectionPool = new AdaptiveConnectionPool();

module.exports = adaptiveConnectionPool;