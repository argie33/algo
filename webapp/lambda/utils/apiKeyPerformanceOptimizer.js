/**
 * API Key Performance Optimizer
 * Optimizations for handling thousands of concurrent users
 * Memory-efficient caching and request batching
 */

class ApiKeyPerformanceOptimizer {
  constructor() {
    // Connection pooling for Parameter Store
    this.connectionPool = new Map();
    this.maxConnections = 50;
    this.connectionTimeout = 30000; // 30 seconds
    
    // Request batching for efficient Parameter Store access
    this.batchQueue = new Map();
    this.batchTimeout = 100; // 100ms batch window
    this.maxBatchSize = 10;
    
    // Performance metrics
    this.metrics = {
      requestCount: 0,
      batchedRequests: 0,
      cacheHits: 0,
      cacheMisses: 0,
      avgResponseTime: 0,
      errors: 0
    };
    
    this.startTime = Date.now();
  }

  /**
   * Batch multiple API key requests for efficiency
   */
  async batchGetApiKeys(userIds) {
    const batchId = Date.now().toString();
    
    return new Promise((resolve, reject) => {
      // Add to batch queue
      this.batchQueue.set(batchId, {
        userIds,
        resolve,
        reject,
        timestamp: Date.now()
      });
      
      // Process batch after timeout
      setTimeout(() => this.processBatch(), this.batchTimeout);
    });
  }

  /**
   * Process batched requests
   */
  async processBatch() {
    if (this.batchQueue.size === 0) return;
    
    const batches = Array.from(this.batchQueue.values());
    this.batchQueue.clear();
    
    try {
      // Combine all user IDs
      const allUserIds = batches.flatMap(batch => batch.userIds);
      const uniqueUserIds = [...new Set(allUserIds)];
      
      // Batch fetch from Parameter Store
      const results = await this.batchFetchFromParameterStore(uniqueUserIds);
      
      // Resolve all promises
      batches.forEach(batch => {
        const batchResults = batch.userIds.map(userId => results[userId] || null);
        batch.resolve(batchResults);
      });
      
      this.metrics.batchedRequests += batches.length;
      
    } catch (error) {
      // Reject all promises
      batches.forEach(batch => batch.reject(error));
      this.metrics.errors++;
    }
  }

  /**
   * Optimized Parameter Store batch fetching
   */
  async batchFetchFromParameterStore(userIds) {
    const simpleApiKeyService = require('./simpleApiKeyService');
    const results = {};
    
    // Process in smaller chunks to avoid AWS limits
    const chunkSize = 10;
    const chunks = this.chunkArray(userIds, chunkSize);
    
    const promises = chunks.map(async (chunk) => {
      const chunkResults = {};
      
      await Promise.all(chunk.map(async (userId) => {
        try {
          const apiKeyData = await simpleApiKeyService.getApiKey(userId, 'alpaca');
          chunkResults[userId] = apiKeyData;
        } catch (error) {
          console.error(`Error fetching API key for user ${userId}:`, error);
          chunkResults[userId] = null;
        }
      }));
      
      return chunkResults;
    });
    
    const chunkResults = await Promise.all(promises);
    
    // Combine results
    chunkResults.forEach(chunkResult => {
      Object.assign(results, chunkResult);
    });
    
    return results;
  }

  /**
   * Memory-efficient rate limiting for high-scale
   */
  checkRateLimit(userId) {
    const now = Date.now();
    const windowMs = 60000; // 1 minute window
    const maxRequests = 100; // per user per minute
    
    if (!this.rateLimitMap) {
      this.rateLimitMap = new Map();
    }
    
    const userLimit = this.rateLimitMap.get(userId) || { count: 0, windowStart: now };
    
    // Reset window if expired
    if (now - userLimit.windowStart > windowMs) {
      userLimit.count = 0;
      userLimit.windowStart = now;
    }
    
    userLimit.count++;
    this.rateLimitMap.set(userId, userLimit);
    
    // Clean up old entries periodically
    if (this.rateLimitMap.size > 10000) {
      this.cleanupRateLimitMap();
    }
    
    return userLimit.count <= maxRequests;
  }

  /**
   * Clean up old rate limit entries
   */
  cleanupRateLimitMap() {
    const now = Date.now();
    const windowMs = 60000;
    
    for (const [userId, limit] of this.rateLimitMap.entries()) {
      if (now - limit.windowStart > windowMs * 2) {
        this.rateLimitMap.delete(userId);
      }
    }
  }

  /**
   * Circuit breaker for Parameter Store failures
   */
  checkCircuitBreaker() {
    const errorThreshold = 10;
    const timeWindow = 60000; // 1 minute
    
    if (!this.circuitBreaker) {
      this.circuitBreaker = {
        errors: 0,
        lastError: 0,
        state: 'CLOSED' // CLOSED, OPEN, HALF_OPEN
      };
    }
    
    const now = Date.now();
    
    // Reset error count if window expired
    if (now - this.circuitBreaker.lastError > timeWindow) {
      this.circuitBreaker.errors = 0;
    }
    
    // Check if circuit should be open
    if (this.circuitBreaker.errors >= errorThreshold) {
      this.circuitBreaker.state = 'OPEN';
      return false;
    }
    
    return true;
  }

  /**
   * Record error for circuit breaker
   */
  recordError() {
    if (!this.circuitBreaker) {
      this.checkCircuitBreaker();
    }
    
    this.circuitBreaker.errors++;
    this.circuitBreaker.lastError = Date.now();
    this.metrics.errors++;
  }

  /**
   * Utility: Chunk array into smaller arrays
   */
  chunkArray(array, chunkSize) {
    const chunks = [];
    for (let i = 0; i < array.length; i += chunkSize) {
      chunks.push(array.slice(i, i + chunkSize));
    }
    return chunks;
  }

  /**
   * Get performance metrics
   */
  getMetrics() {
    const uptime = Date.now() - this.startTime;
    const requestsPerSecond = this.metrics.requestCount / (uptime / 1000);
    
    return {
      ...this.metrics,
      uptime: Math.floor(uptime / 1000),
      requestsPerSecond: requestsPerSecond.toFixed(2),
      cacheHitRate: this.metrics.requestCount > 0 ? 
        ((this.metrics.cacheHits / this.metrics.requestCount) * 100).toFixed(2) + '%' : '0%',
      errorRate: this.metrics.requestCount > 0 ? 
        ((this.metrics.errors / this.metrics.requestCount) * 100).toFixed(2) + '%' : '0%',
      batchEfficiency: this.metrics.requestCount > 0 ? 
        ((this.metrics.batchedRequests / this.metrics.requestCount) * 100).toFixed(2) + '%' : '0%'
    };
  }

  /**
   * Reset metrics
   */
  resetMetrics() {
    this.metrics = {
      requestCount: 0,
      batchedRequests: 0,
      cacheHits: 0,
      cacheMisses: 0,
      avgResponseTime: 0,
      errors: 0
    };
    this.startTime = Date.now();
  }
}

// Export singleton instance
module.exports = new ApiKeyPerformanceOptimizer();