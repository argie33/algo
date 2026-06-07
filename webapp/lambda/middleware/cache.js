/**
 * Simple in-memory caching middleware
 * Caches GET requests for configurable duration
 */

const cache = new Map();

const getCacheKey = (req) => {
  return `${req.method}:${req.originalUrl}`;
};

const cacheMiddleware = (duration = 5 * 60 * 1000) => {
  return (req, res, next) => {
    // Only cache GET requests
    if (req.method !== 'GET') {
      return next();
    }

    const key = getCacheKey(req);
    const cached = cache.get(key);

    // Return cached response if available and not expired
    if (cached && Date.now() - cached.timestamp < duration) {
      res.set('X-Cache', 'HIT');
      return res.status(cached.status).json(cached.data);
    }

    // Store original json method
    const originalJson = res.json.bind(res);

    // Override json method to cache responses
    res.json = (data) => {
      // Cache successful responses (2xx)
      if (res.statusCode >= 200 && res.statusCode < 300) {
        cache.set(key, {
          data,
          status: res.statusCode,
          timestamp: Date.now()
        });
      }

      res.set('X-Cache', 'MISS');
      return originalJson(data);
    };

    next();
  };
};

// Clear cache for a specific pattern
const clearCache = (pattern) => {
  let cleared = 0;
  for (const key of cache.keys()) {
    if (key.includes(pattern)) {
      cache.delete(key);
      cleared++;
    }
  }
  return cleared;
};

// Clear all cache
const clearAllCache = () => {
  cache.clear();
};

module.exports = {
  cacheMiddleware,
  clearCache,
  clearAllCache,
  cache
};
