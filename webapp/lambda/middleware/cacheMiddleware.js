/**
 * Cache Middleware for Express API
 * In-memory caching with TTL support
 * Optimizes slow endpoints (signals: 876ms → <100ms target)
 */

class CacheManager {
  constructor() {
    this.cache = new Map();
    this.ttl = new Map();
  }

  get(key) {
    if (!this.cache.has(key)) {
      return null;
    }

    const expiry = this.ttl.get(key);
    if (expiry && Date.now() > expiry) {
      this.cache.delete(key);
      this.ttl.delete(key);
      return null;
    }

    return this.cache.get(key);
  }

  set(key, value, ttlSeconds = 300) {
    this.cache.set(key, value);
    this.ttl.set(key, Date.now() + ttlSeconds * 1000);
  }

  clear() {
    this.cache.clear();
    this.ttl.clear();
  }

  getStats() {
    return {
      cached_items: this.cache.size,
      cache_size_bytes: JSON.stringify(Array.from(this.cache.values())).length,
      timestamp: new Date().toISOString()
    };
  }

  // Cleanup expired entries periodically
  startCleanupInterval(intervalSeconds = 300) {
    setInterval(() => {
      const now = Date.now();
      let cleaned = 0;
      for (const [key, expiry] of this.ttl.entries()) {
        if (expiry && now > expiry) {
          this.cache.delete(key);
          this.ttl.delete(key);
          cleaned++;
        }
      }
      if (cleaned > 0) {
        console.log(`[Cache] Cleaned ${cleaned} expired entries`);
      }
    }, intervalSeconds * 1000);
  }
}

const globalCache = new CacheManager();
globalCache.startCleanupInterval(300); // Cleanup every 5 minutes

// Middleware factory: create caching middleware for specific routes
function cacheMiddleware(ttlSeconds = 300, keyGenerator = null) {
  return (req, res, next) => {
    // Only cache GET requests
    if (req.method !== 'GET') {
      return next();
    }

    // Generate cache key from request URL and important query params
    const defaultKeyGenerator = () => {
      const baseUrl = req.originalUrl.split('?')[0];
      const params = new URLSearchParams(req.query);
      // Sort params for consistent key generation
      params.sort();
      return `${baseUrl}?${params.toString()}`;
    };

    const cacheKey = keyGenerator ? keyGenerator(req) : defaultKeyGenerator();

    // Try to get from cache
    const cachedResult = globalCache.get(cacheKey);
    if (cachedResult) {
      res.set('X-Cache', 'HIT');
      return res.json(cachedResult);
    }

    // Store original res.json to intercept response
    const originalJson = res.json.bind(res);
    res.json = function(data) {
      if (res.statusCode === 200 && data && data.success !== false) {
        globalCache.set(cacheKey, data, ttlSeconds);
        res.set('X-Cache', 'MISS');
      }
      return originalJson(data);
    };

    next();
  };
}

// Decorator pattern: wrap async functions with caching
function cached(ttlSeconds = 300) {
  return function(target, propertyKey, descriptor) {
    const originalMethod = descriptor.value;

    descriptor.value = async function(...args) {
      const req = args[0]; // Express request object
      const cacheKey = `${propertyKey}:${JSON.stringify(req.query || {})}`;

      const cachedResult = globalCache.get(cacheKey);
      if (cachedResult) {
        return cachedResult;
      }

      const result = await originalMethod.apply(this, args);
      globalCache.set(cacheKey, result, ttlSeconds);
      return result;
    };

    return descriptor;
  };
}

module.exports = {
  cacheMiddleware,
  globalCache,
  cached,
  CacheManager
};
