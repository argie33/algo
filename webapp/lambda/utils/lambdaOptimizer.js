/**
 * Lambda Performance Optimizer
 * Fixes slow response times and cold starts
 */

const os = require('os');
const { performance } = require('perf_hooks');

class LambdaOptimizer {
  constructor() {
    this.startTime = Date.now();
    this.connections = new Map();
    this.cache = new Map();
    this.warmupComplete = false;
    this.metrics = {
      requests: 0,
      coldStarts: 0,
      avgResponseTime: 0,
      totalResponseTime: 0
    };
  }

  // Warm up Lambda function
  async warmup() {
    if (this.warmupComplete) return;
    
    console.log('🔥 Lambda warmup starting...');
    const warmupStart = performance.now();
    
    try {
      // Pre-load modules
      await this.preloadModules();
      
      // Pre-establish database connections
      await this.preestablishConnections();
      
      // Pre-cache common data
      await this.precacheCommonData();
      
      this.warmupComplete = true;
      const warmupDuration = performance.now() - warmupStart;
      console.log(`✅ Lambda warmup completed in ${warmupDuration.toFixed(2)}ms`);
      
    } catch (error) {
      console.error('❌ Lambda warmup failed:', error);
    }
  }

  async preloadModules() {
    // Pre-load heavy modules during warmup
    const modules = [
      require('../utils/database'),
      require('../utils/apiKeyService'),
      require('../utils/alpacaService'),
      require('../middleware/auth'),
      require('../middleware/validation')
    ];
    
    console.log(`📦 Pre-loaded ${modules.length} modules`);
  }

  async preestablishConnections() {
    try {
      const { healthCheck } = require('../utils/database');
      await healthCheck();
      console.log('🔗 Database connection pre-established');
    } catch (error) {
      console.warn('⚠️ Database pre-connection failed:', error.message);
    }
  }

  async precacheCommonData() {
    try {
      // Cache common queries
      const commonQueries = [
        'SELECT COUNT(*) FROM stock_symbols_enhanced WHERE is_active = true',
        'SELECT DISTINCT sector FROM stock_symbols_enhanced WHERE sector IS NOT NULL LIMIT 20'
      ];
      
      const { query } = require('../utils/database');
      
      for (const sql of commonQueries) {
        try {
          const result = await query(sql);
          this.cache.set(sql, result);
        } catch (error) {
          console.warn('⚠️ Pre-cache query failed:', sql, error.message);
        }
      }
      
      console.log(`💾 Pre-cached ${this.cache.size} common queries`);
    } catch (error) {
      console.warn('⚠️ Pre-caching failed:', error.message);
    }
  }

  // Request tracking
  trackRequest(req, res, next) {
    const requestStart = performance.now();
    this.metrics.requests++;
    
    // Check if this is a cold start
    if (!this.warmupComplete) {
      this.metrics.coldStarts++;
      console.log('🥶 Cold start detected');
    }
    
    // Track response time
    const originalSend = res.send;
    res.send = function(data) {
      const responseTime = performance.now() - requestStart;
      this.metrics.totalResponseTime += responseTime;
      this.metrics.avgResponseTime = this.metrics.totalResponseTime / this.metrics.requests;
      
      if (responseTime > 1000) {
        console.warn(`🐌 Slow response: ${req.path} took ${responseTime.toFixed(2)}ms`);
      }
      
      originalSend.call(this, data);
    }.bind(this);
    
    next();
  }

  // Connection pooling optimization
  optimizeConnectionPool() {
    const { Pool } = require('pg');
    
    // Optimize based on Lambda memory
    const memorySize = parseInt(process.env.AWS_LAMBDA_FUNCTION_MEMORY_SIZE) || 512;
    const maxConnections = Math.min(Math.floor(memorySize / 64), 10);
    
    console.log(`🔧 Optimizing connection pool for ${memorySize}MB Lambda (max: ${maxConnections})`);
    
    return {
      max: maxConnections,
      min: 1,
      acquireTimeoutMillis: 5000,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 10000
    };
  }

  // Memory optimization
  optimizeMemory() {
    // Force garbage collection if available
    if (global.gc) {
      global.gc();
      console.log('♻️ Manual garbage collection triggered');
    }
    
    // Log memory usage
    const memUsage = process.memoryUsage();
    console.log('📊 Memory usage:', {
      rss: `${Math.round(memUsage.rss / 1024 / 1024)}MB`,
      heapUsed: `${Math.round(memUsage.heapUsed / 1024 / 1024)}MB`,
      heapTotal: `${Math.round(memUsage.heapTotal / 1024 / 1024)}MB`
    });
  }

  // Response optimization
  optimizeResponse(req, res, next) {
    // Compression
    res.setHeader('Content-Encoding', 'gzip');
    
    // Caching headers for static content
    if (req.path.includes('/health') || req.path.includes('/diagnostics')) {
      res.setHeader('Cache-Control', 'public, max-age=30');
    }
    
    // Connection keep-alive
    res.setHeader('Connection', 'keep-alive');
    
    next();
  }

  // Get performance metrics
  getMetrics() {
    const uptime = Date.now() - this.startTime;
    
    return {
      uptime: `${Math.round(uptime / 1000)}s`,
      requests: this.metrics.requests,
      coldStarts: this.metrics.coldStarts,
      avgResponseTime: `${this.metrics.avgResponseTime.toFixed(2)}ms`,
      warmupComplete: this.warmupComplete,
      cacheSize: this.cache.size,
      memoryUsage: process.memoryUsage(),
      cpuUsage: process.cpuUsage(),
      loadAverage: os.loadavg(),
      freeMemory: `${Math.round(os.freemem() / 1024 / 1024)}MB`,
      totalMemory: `${Math.round(os.totalmem() / 1024 / 1024)}MB`
    };
  }

  // Express middleware factory
  createMiddleware() {
    return {
      warmup: this.warmup.bind(this),
      trackRequest: this.trackRequest.bind(this),
      optimizeResponse: this.optimizeResponse.bind(this),
      optimizeMemory: this.optimizeMemory.bind(this)
    };
  }
}

// Singleton instance
const optimizer = new LambdaOptimizer();

module.exports = optimizer;