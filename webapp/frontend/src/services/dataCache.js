/**
 * Data Caching Layer
 * Provides in-memory caching for API responses with TTL and refresh strategies
 */

const cacheStore = new Map();

const DEFAULT_TTL = 5 * 60 * 1000; // 5 minutes

/**
 * Get cached data or fetch fresh data
 * @param {string} key - Cache key
 * @param {object} params - Query parameters
 * @param {object} options - Caching options
 * @returns {Promise<any>} Cached or fresh data
 */
async function get(key, params = {}, options = {}) {
  const {
    ttl = DEFAULT_TTL,
    fetchFunction = null,
    cacheType = 'default',
    forceRefresh = false,
  } = options;

  const cacheKey = `${cacheType}:${key}:${JSON.stringify(params)}`;

  // Return cached data if valid and not forced refresh
  if (!forceRefresh && cacheStore.has(cacheKey)) {
    const cached = cacheStore.get(cacheKey);
    if (Date.now() < cached.expiresAt) {
      return cached.data;
    }
    // Expired, delete it
    cacheStore.delete(cacheKey);
  }

  // Fetch fresh data
  if (fetchFunction) {
    const data = await fetchFunction();
    // Cache the result
    cacheStore.set(cacheKey, {
      data,
      expiresAt: Date.now() + ttl,
    });
    return data;
  }

  return null;
}

/**
 * Manually set cached data
 * @param {string} key - Cache key
 * @param {any} data - Data to cache
 * @param {object} options - Options including ttl, cacheType
 */
function set(key, data, options = {}) {
  const { ttl = DEFAULT_TTL, cacheType = 'default' } = options;
  const cacheKey = `${cacheType}:${key}`;

  cacheStore.set(cacheKey, {
    data,
    expiresAt: Date.now() + ttl,
  });
}

/**
 * Clear specific cache entry or all cache
 * @param {string} pattern - Pattern to clear (regex), or undefined for all
 */
function clear(pattern = null) {
  if (pattern === null) {
    cacheStore.clear();
    return;
  }

  const regex = new RegExp(pattern);
  for (const key of cacheStore.keys()) {
    if (regex.test(key)) {
      cacheStore.delete(key);
    }
  }
}

/**
 * Get cache size (for debugging)
 * @returns {number} Number of cached items
 */
function size() {
  return cacheStore.size;
}

export default {
  get,
  set,
  clear,
  size,
};
