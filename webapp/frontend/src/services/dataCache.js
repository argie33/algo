/**
 * Data Caching Layer
 * Provides in-memory caching for API responses with TTL and refresh strategies
 * Includes schema validation to prevent returning stale mismatched data
 */

const cacheStore = new Map();

const DEFAULT_TTL = 5 * 60 * 1000; // 5 minutes

/**
 * Validate cached data has expected structure
 * @param {any} data - Data to validate
 * @param {object} expectedSchema - Schema with required fields/types
 * @returns {boolean} True if data matches schema
 */
function validateSchema(data, expectedSchema) {
  if (!expectedSchema) return true; // No schema validation if not specified
  if (typeof data !== 'object' || data === null) return false;

  // Check that all required fields exist and have correct type
  for (const [field, expectedType] of Object.entries(expectedSchema)) {
    if (!(field in data)) {
      console.warn(`[Cache] Schema validation failed: missing field "${field}"`);
      return false;
    }
    const actualType = typeof data[field];
    // Skip type check for null values (they may be intentional)
    if (data[field] !== null && actualType !== expectedType) {
      console.warn(`[Cache] Schema validation failed: field "${field}" is ${actualType}, expected ${expectedType}`);
      return false;
    }
  }
  return true;
}

/**
 * Get cached data or fetch fresh data
 * @param {string} key - Cache key
 * @param {object} params - Query parameters
 * @param {object} options - Caching options (ttl, fetchFunction, cacheType, forceRefresh, expectedSchema)
 * @returns {Promise<any>} Cached or fresh data
 */
async function get(key, params = {}, options = {}) {
  const {
    ttl = DEFAULT_TTL,
    fetchFunction = null,
    cacheType = 'default',
    forceRefresh = false,
    expectedSchema = null,
  } = options;

  const cacheKey = `${cacheType}:${key}:${JSON.stringify(params)}`;

  // Return cached data if valid and not forced refresh
  if (!forceRefresh && cacheStore.has(cacheKey)) {
    const cached = cacheStore.get(cacheKey);
    if (Date.now() < cached.expiresAt) {
      // Validate schema before returning
      if (expectedSchema && !validateSchema(cached.data, expectedSchema)) {
        console.warn(`[Cache] Schema mismatch for "${key}", treating as cache miss`);
        cacheStore.delete(cacheKey);
      } else {
        return cached.data;
      }
    } else {
      // Expired, delete it
      cacheStore.delete(cacheKey);
    }
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
 * @param {object} options - Options including ttl, cacheType, expectedSchema
 */
function set(key, data, options = {}) {
  const { ttl = DEFAULT_TTL, cacheType = 'default', expectedSchema = null } = options;
  const cacheKey = `${cacheType}:${key}`;

  // Validate schema before caching
  if (expectedSchema && !validateSchema(data, expectedSchema)) {
    console.warn(`[Cache] Schema validation failed for "${key}", not caching`);
    return;
  }

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

