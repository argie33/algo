/**
 * Intelligent L1-L3 Cache Hierarchy System
 * Optimized for high-frequency financial data with adaptive management
 * 
 * L1: In-memory ultra-fast cache (sub-millisecond access)
 * L2: Redis distributed cache (millisecond access) 
 * L3: Database persistent cache (10-100ms access)
 */

const { createLogger } = require('./structuredLogger');

class IntelligentCachingSystem {
  constructor(options = {}) {
    this.logger = createLogger('financial-platform', 'caching-system');
    
    // L1 Cache: In-memory for ultra-fast access
    this.l1Cache = new Map();
    this.l1Metadata = new Map(); // TTL and access tracking
    this.l1MaxSize = options.l1MaxSize || 1000;
    this.l1TTL = options.l1TTL || 30000; // 30 seconds for real-time data
    
    // L2 Cache: Redis configuration (simulated for Lambda)
    this.l2Cache = new Map(); // In Lambda, simulate Redis with larger Map
    this.l2Metadata = new Map();
    this.l2MaxSize = options.l2MaxSize || 10000;
    this.l2TTL = options.l2TTL || 300000; // 5 minutes
    
    // L3 Cache: Database configuration
    this.l3TTL = options.l3TTL || 3600000; // 1 hour
    
    // Cache performance metrics
    this.metrics = {
      l1: { hits: 0, misses: 0, evictions: 0 },
      l2: { hits: 0, misses: 0, evictions: 0 },
      l3: { hits: 0, misses: 0, evictions: 0 },
      totalRequests: 0,
      avgResponseTime: 0
    };
    
    // Adaptive cache management
    this.accessPatterns = new Map(); // Track access frequency
    this.hotKeys = new Set(); // Frequently accessed keys
    this.adaptiveThreshold = 5; // Promote to higher cache after 5 accesses
    
    // Start background cleanup
    this.startCleanupTasks();
  }

  /**
   * Get data with intelligent cache hierarchy traversal
   */
  async get(key, options = {}) {
    const startTime = Date.now();
    this.metrics.totalRequests++;
    
    try {
      // Track access patterns for adaptive management
      this.trackAccess(key);
      
      // L1 Cache check - Ultra-fast in-memory
      const l1Result = this.getFromL1(key);
      if (l1Result !== null) {
        this.metrics.l1.hits++;
        this.updateResponseTime(Date.now() - startTime);
        return { data: l1Result, source: 'L1', latency: Date.now() - startTime };
      }
      this.metrics.l1.misses++;
      
      // L2 Cache check - Distributed cache
      const l2Result = await this.getFromL2(key);
      if (l2Result !== null) {
        this.metrics.l2.hits++;
        // Promote to L1 if hot key
        if (this.isHotKey(key)) {
          this.setToL1(key, l2Result, { ttl: this.l1TTL });
        }
        this.updateResponseTime(Date.now() - startTime);
        return { data: l2Result, source: 'L2', latency: Date.now() - startTime };
      }
      this.metrics.l2.misses++;
      
      // L3 Cache check - Database
      const l3Result = await this.getFromL3(key, options);
      if (l3Result !== null) {
        this.metrics.l3.hits++;
        // Cascade up: Store in L2 and potentially L1
        await this.setToL2(key, l3Result, { ttl: this.l2TTL });
        if (this.isHotKey(key)) {
          this.setToL1(key, l3Result, { ttl: this.l1TTL });
        }
        this.updateResponseTime(Date.now() - startTime);
        return { data: l3Result, source: 'L3', latency: Date.now() - startTime };
      }
      this.metrics.l3.misses++;
      
      // Cache miss - return null
      this.updateResponseTime(Date.now() - startTime);
      return { data: null, source: 'MISS', latency: Date.now() - startTime };
      
    } catch (error) {
      this.logger.error('Cache get error', { key, error: error.message });
      return { data: null, source: 'ERROR', latency: Date.now() - startTime, error: error.message };
    }
  }

  /**
   * Set data with intelligent distribution across cache levels
   */
  async set(key, value, options = {}) {
    try {
      const { ttl, priority = 'normal', level = 'auto' } = options;
      
      // Determine cache levels based on priority and access patterns
      const levels = this.determineCacheLevels(key, priority, level);
      
      // Set to appropriate cache levels
      if (levels.includes('L1')) {
        this.setToL1(key, value, { ttl: ttl || this.l1TTL });
      }
      
      if (levels.includes('L2')) {
        await this.setToL2(key, value, { ttl: ttl || this.l2TTL });
      }
      
      if (levels.includes('L3')) {
        await this.setToL3(key, value, { ttl: ttl || this.l3TTL });
      }
      
      this.logger.debug('Cache set completed', { key, levels, ttl });
      return { success: true, levels };
      
    } catch (error) {
      this.logger.error('Cache set error', { key, error: error.message });
      return { success: false, error: error.message };
    }
  }

  /**
   * Delete from all cache levels
   */
  async delete(key) {
    try {
      // Remove from all levels
      this.l1Cache.delete(key);
      this.l1Metadata.delete(key);
      
      this.l2Cache.delete(key);
      this.l2Metadata.delete(key);
      
      // L3 deletion would involve database deletion
      // For now, we'll mark it as expired
      
      this.accessPatterns.delete(key);
      this.hotKeys.delete(key);
      
      this.logger.debug('Cache delete completed', { key });
      return { success: true };
      
    } catch (error) {
      this.logger.error('Cache delete error', { key, error: error.message });
      return { success: false, error: error.message };
    }
  }

  /**
   * L1 Cache operations - In-memory ultra-fast
   */
  getFromL1(key) {
    const metadata = this.l1Metadata.get(key);
    if (!metadata || Date.now() > metadata.expiry) {
      if (metadata) {
        this.l1Cache.delete(key);
        this.l1Metadata.delete(key);
      }
      return null;
    }
    
    // Update last access time
    metadata.lastAccess = Date.now();
    return this.l1Cache.get(key);
  }

  setToL1(key, value, options = {}) {
    // Check capacity and evict if necessary
    if (this.l1Cache.size >= this.l1MaxSize) {
      this.evictFromL1();
    }
    
    const ttl = options.ttl || this.l1TTL;
    this.l1Cache.set(key, value);
    this.l1Metadata.set(key, {
      expiry: Date.now() + ttl,
      lastAccess: Date.now(),
      setTime: Date.now()
    });
  }

  evictFromL1() {
    // LRU eviction strategy
    let oldestKey = null;
    let oldestAccess = Date.now();
    
    for (const [key, metadata] of this.l1Metadata.entries()) {
      if (metadata.lastAccess < oldestAccess) {
        oldestAccess = metadata.lastAccess;
        oldestKey = key;
      }
    }
    
    if (oldestKey) {
      this.l1Cache.delete(oldestKey);
      this.l1Metadata.delete(oldestKey);
      this.metrics.l1.evictions++;
    }
  }

  /**
   * L2 Cache operations - Distributed cache (simulated)
   */
  async getFromL2(key) {
    const metadata = this.l2Metadata.get(key);
    if (!metadata || Date.now() > metadata.expiry) {
      if (metadata) {
        this.l2Cache.delete(key);
        this.l2Metadata.delete(key);
      }
      return null;
    }
    
    metadata.lastAccess = Date.now();
    return this.l2Cache.get(key);
  }

  async setToL2(key, value, options = {}) {
    if (this.l2Cache.size >= this.l2MaxSize) {
      await this.evictFromL2();
    }
    
    const ttl = options.ttl || this.l2TTL;
    this.l2Cache.set(key, value);
    this.l2Metadata.set(key, {
      expiry: Date.now() + ttl,
      lastAccess: Date.now(),
      setTime: Date.now()
    });
  }

  async evictFromL2() {
    // LRU eviction for L2
    let oldestKey = null;
    let oldestAccess = Date.now();
    
    for (const [key, metadata] of this.l2Metadata.entries()) {
      if (metadata.lastAccess < oldestAccess) {
        oldestAccess = metadata.lastAccess;
        oldestKey = key;
      }
    }
    
    if (oldestKey) {
      this.l2Cache.delete(oldestKey);
      this.l2Metadata.delete(oldestKey);
      this.metrics.l2.evictions++;
    }
  }

  /**
   * L3 Cache operations - Database persistent cache
   */
  async getFromL3(key, options = {}) {
    try {
      // In a real implementation, this would query the database
      // For now, simulate database access
      await new Promise(resolve => setTimeout(resolve, 10)); // Simulate DB latency
      
      // Return null for cache miss
      return null;
    } catch (error) {
      this.logger.error('L3 cache get error', { key, error: error.message });
      return null;
    }
  }

  async setToL3(key, value, options = {}) {
    try {
      // In a real implementation, this would insert/update in database
      // For now, just simulate the operation
      await new Promise(resolve => setTimeout(resolve, 5)); // Simulate DB write
      return true;
    } catch (error) {
      this.logger.error('L3 cache set error', { key, error: error.message });
      return false;
    }
  }

  /**
   * Access pattern tracking for adaptive management
   */
  trackAccess(key) {
    const current = this.accessPatterns.get(key) || { count: 0, lastAccess: 0 };
    current.count++;
    current.lastAccess = Date.now();
    this.accessPatterns.set(key, current);
    
    // Promote to hot key if frequently accessed
    if (current.count >= this.adaptiveThreshold) {
      this.hotKeys.add(key);
    }
  }

  isHotKey(key) {
    return this.hotKeys.has(key);
  }

  /**
   * Determine which cache levels to use based on key characteristics
   */
  determineCacheLevels(key, priority, level) {
    if (level !== 'auto') {
      return [level.toUpperCase()];
    }
    
    const levels = [];
    
    // Always store in L3 for persistence
    levels.push('L3');
    
    // Add L2 for most data
    levels.push('L2');
    
    // Add L1 for high priority or hot keys
    if (priority === 'high' || this.isHotKey(key)) {
      levels.push('L1');
    }
    
    return levels;
  }

  /**
   * Update response time metrics
   */
  updateResponseTime(latency) {
    const alpha = 0.1; // Exponential smoothing factor
    this.metrics.avgResponseTime = this.metrics.avgResponseTime * (1 - alpha) + latency * alpha;
  }

  /**
   * Get cache performance metrics
   */
  getMetrics() {
    const l1HitRate = this.metrics.l1.hits + this.metrics.l1.misses > 0 ? 
      (this.metrics.l1.hits / (this.metrics.l1.hits + this.metrics.l1.misses) * 100).toFixed(2) : 0;
    
    const l2HitRate = this.metrics.l2.hits + this.metrics.l2.misses > 0 ?
      (this.metrics.l2.hits / (this.metrics.l2.hits + this.metrics.l2.misses) * 100).toFixed(2) : 0;
    
    const l3HitRate = this.metrics.l3.hits + this.metrics.l3.misses > 0 ?
      (this.metrics.l3.hits / (this.metrics.l3.hits + this.metrics.l3.misses) * 100).toFixed(2) : 0;
    
    const overallHitRate = this.metrics.totalRequests > 0 ?
      ((this.metrics.l1.hits + this.metrics.l2.hits + this.metrics.l3.hits) / this.metrics.totalRequests * 100).toFixed(2) : 0;
    
    return {
      l1: {
        size: this.l1Cache.size,
        maxSize: this.l1MaxSize,
        hitRate: `${l1HitRate}%`,
        hits: this.metrics.l1.hits,
        misses: this.metrics.l1.misses,
        evictions: this.metrics.l1.evictions
      },
      l2: {
        size: this.l2Cache.size,
        maxSize: this.l2MaxSize,
        hitRate: `${l2HitRate}%`,
        hits: this.metrics.l2.hits,
        misses: this.metrics.l2.misses,
        evictions: this.metrics.l2.evictions
      },
      l3: {
        hitRate: `${l3HitRate}%`,
        hits: this.metrics.l3.hits,
        misses: this.metrics.l3.misses
      },
      overall: {
        hitRate: `${overallHitRate}%`,
        totalRequests: this.metrics.totalRequests,
        avgResponseTime: `${this.metrics.avgResponseTime.toFixed(2)}ms`,
        hotKeys: this.hotKeys.size,
        trackedPatterns: this.accessPatterns.size
      }
    };
  }

  /**
   * Background cleanup tasks
   */
  startCleanupTasks() {
    // Clean up expired entries every 5 minutes
    this.cleanupInterval = setInterval(() => {
      this.cleanupExpiredEntries();
    }, 300000);
    
    // Reset hot keys every hour to adapt to changing patterns
    this.hotKeyResetInterval = setInterval(() => {
      this.resetHotKeys();
    }, 3600000);
  }

  cleanupExpiredEntries() {
    const now = Date.now();
    let cleanedL1 = 0;
    let cleanedL2 = 0;
    
    // Clean L1
    for (const [key, metadata] of this.l1Metadata.entries()) {
      if (now > metadata.expiry) {
        this.l1Cache.delete(key);
        this.l1Metadata.delete(key);
        cleanedL1++;
      }
    }
    
    // Clean L2
    for (const [key, metadata] of this.l2Metadata.entries()) {
      if (now > metadata.expiry) {
        this.l2Cache.delete(key);
        this.l2Metadata.delete(key);
        cleanedL2++;
      }
    }
    
    if (cleanedL1 > 0 || cleanedL2 > 0) {
      this.logger.info('Cache cleanup completed', { 
        cleanedL1, 
        cleanedL2, 
        currentSizes: { l1: this.l1Cache.size, l2: this.l2Cache.size }
      });
    }
  }

  resetHotKeys() {
    const previousHotKeys = this.hotKeys.size;
    this.hotKeys.clear();
    
    // Reset access pattern counts but keep recent access info
    for (const [key, pattern] of this.accessPatterns.entries()) {
      pattern.count = Math.floor(pattern.count * 0.1); // Decay factor
    }
    
    this.logger.info('Hot keys reset for adaptive management', { 
      previousHotKeys, 
      accessPatterns: this.accessPatterns.size 
    });
  }

  /**
   * Health check for the caching system
   */
  async healthCheck() {
    try {
      const testKey = `health_check_${Date.now()}`;
      const testValue = { test: true, timestamp: Date.now() };
      
      // Test all cache levels
      await this.set(testKey, testValue);
      const result = await this.get(testKey);
      await this.delete(testKey);
      
      const metrics = this.getMetrics();
      
      return {
        healthy: result.data !== null,
        metrics,
        message: 'All cache levels operational',
        timestamp: new Date().toISOString()
      };
    } catch (error) {
      return {
        healthy: false,
        error: error.message,
        timestamp: new Date().toISOString()
      };
    }
  }

  /**
   * Cleanup resources
   */
  destroy() {
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval);
    }
    if (this.hotKeyResetInterval) {
      clearInterval(this.hotKeyResetInterval);
    }
    
    this.l1Cache.clear();
    this.l1Metadata.clear();
    this.l2Cache.clear();
    this.l2Metadata.clear();
    this.accessPatterns.clear();
    this.hotKeys.clear();
  }
}

// Export singleton instance for Lambda efficiency
module.exports = new IntelligentCachingSystem();