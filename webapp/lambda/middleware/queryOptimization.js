/**
 * Query Optimization Middleware
 * Enforces best practices for all database queries:
 * - Reasonable pagination limits
 * - Symbol-based filtering requirements
 * - Result caching for frequently accessed data
 * - Query timeouts and fallbacks
 */

const queryCache = new Map();
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

/**
 * Cache-aside pattern for expensive queries
 */
const withCache = async (key, queryFn, ttl = CACHE_TTL) => {
  const cached = queryCache.get(key);

  if (cached && Date.now() - cached.timestamp < ttl) {
    return cached.data;
  }

  try {
    const data = await queryFn();
    queryCache.set(key, { data, timestamp: Date.now() });
    return data;
  } catch (error) {
    // Return stale cache if available during errors
    if (cached) {
      console.warn(`Using stale cache for ${key} due to error:`, error.message);
      return cached.data;
    }
    throw error;
  }
};

/**
 * Enforce reasonable pagination
 */
const validatePagination = (query) => {
  let limit = parseInt(query.limit) || 50;
  let page = Math.max(1, parseInt(query.page) || 1);
  let offset = parseInt(query.offset);

  // Enforce limits
  const MAX_LIMIT = 500;
  const DEFAULT_LIMIT = 50;

  if (limit > MAX_LIMIT) {
    limit = MAX_LIMIT;
  }
  if (limit < 1) {
    limit = DEFAULT_LIMIT;
  }

  // Use offset if provided, otherwise calculate from page
  if (!offset || offset < 0) {
    offset = (page - 1) * limit;
  }

  return { limit, offset, page: Math.max(1, Math.ceil((offset / limit) + 1)) };
};

/**
 * Require symbol filter for expensive tables
 */
const requireSymbolFilter = (symbol) => {
  if (!symbol) {
    return {
      error: 'Symbol parameter required for this endpoint',
      success: false,
      hint: 'Add ?symbol=AAPL to your request'
    };
  }
  return null;
};

/**
 * Safe query wrapper with timeouts
 */
const withTimeout = async (queryFn, timeoutMs = 10000) => {
  return Promise.race([
    queryFn(),
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error(`Query timeout after ${timeoutMs}ms`)), timeoutMs)
    )
  ]);
};

module.exports = {
  withCache,
  validatePagination,
  requireSymbolFilter,
  withTimeout,
  clearCache: () => queryCache.clear(),
  getCacheStats: () => ({
    size: queryCache.size,
    keys: Array.from(queryCache.keys())
  })
};
