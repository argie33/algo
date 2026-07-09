/**
 * Data Caching Layer
 * Provides in-memory caching for API responses with TTL and event-driven invalidation
 * TTL-based: Cached data expires after configurable timeout (default: 5 minutes)
 * Event-driven: Cache entries are automatically cleared on API errors (5xx, timeouts, etc.)
 * Schema validation: Prevents returning stale mismatched data on schema changes
 * Fetch tracking: Tracks fetch timestamps to indicate data freshness
 */

const cacheStore = new Map();

const DEFAULT_TTL = 5 * 60 * 1000; // 5 minutes
// FIXED: Reduced MAX_STALE_AGE from 2 hours to 30 minutes for intraday trading
// Positions can close, orders fill, and market regime changes within 2 hours
const MAX_STALE_AGE = 30 * 60 * 1000; // 30 minutes - age at which data is considered phantom

/**
 * Validate cached data has expected structure
 * @param {any} data - Data to validate
 * @param {object} expectedSchema - Schema with required fields/types
 * @returns {boolean} True if data matches schema
 */
function validateSchema(data, expectedSchema) {
  if (!expectedSchema) return true; // No schema validation if not specified
  if (typeof data !== "object" || data === null) return false;

  // Check that all required fields exist and have correct type
  for (const [field, expectedType] of Object.entries(expectedSchema)) {
    if (!(field in data)) {
      console.warn(
        `[Cache] Schema validation failed: missing field "${field}"`
      );
      return false;
    }
    const actualType = typeof data[field];
    // Skip type check for null values (they may be intentional)
    if (data[field] !== null && actualType !== expectedType) {
      console.warn(
        `[Cache] Schema validation failed: field "${field}" is ${actualType}, expected ${expectedType}`
      );
      return false;
    }
  }
  return true;
}

/**
 * Get cached data or fetch fresh data
 * @param {string} key - Cache key
 * @param {object} params - Query parameters
 * @param {object} options - Caching options (ttl, fetchFunction, cacheType, forceRefresh, expectedSchema, onError)
 *   - onError: Function called when fetch fails; receives error and cacheKey. Defaults to clearing cache entry.
 * @returns {Promise<any>} Cached or fresh data
 */
async function get(key, params = {}, options = {}) {
  const {
    ttl = DEFAULT_TTL,
    fetchFunction = null,
    cacheType = "default",
    forceRefresh = false,
    expectedSchema = null,
    onError = null,
  } = options;

  const cacheKey = `${cacheType}:${key}:${JSON.stringify(params)}`;

  // Return cached data if valid and not forced refresh
  if (!forceRefresh && cacheStore.has(cacheKey)) {
    const cached = cacheStore.get(cacheKey);
    if (Date.now() < cached.expiresAt) {
      // Validate schema before returning
      if (expectedSchema && !validateSchema(cached.data, expectedSchema)) {
        console.warn(
          `[Cache] Schema mismatch for "${key}", treating as cache miss`
        );
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
    try {
      const data = await fetchFunction();
      // Cache the result
      cacheStore.set(cacheKey, {
        data,
        expiresAt: Date.now() + ttl,
      });
      return data;
    } catch (error) {
      // Call error handler (default: invalidate cache entry on error)
      const errorHandler = onError || ((err, key) => cacheStore.delete(key));
      errorHandler(error, cacheKey);
      throw error;
    }
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
  const {
    ttl = DEFAULT_TTL,
    cacheType = "default",
    expectedSchema = null,
  } = options;
  const cacheKey = `${cacheType}:${key}`;

  // Validate schema before caching
  if (expectedSchema && !validateSchema(data, expectedSchema)) {
    console.warn(`[Cache] Schema validation failed for "${key}", not caching`);
    return;
  }

  const now = Date.now();
  cacheStore.set(cacheKey, {
    data,
    expiresAt: now + ttl,
    fetchedAt: now,
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
 * Invalidate cache entry on API error (used as error handler)
 * Prevents stale data from being served after API 500 errors
 * @param {string} key - Cache key to invalidate
 * @param {object} options - Options including cacheType
 */
function invalidateOnError(key, options = {}) {
  const { cacheType = "default" } = options;
  const pattern = `^${cacheType}:${key}`;
  clear(pattern);
  console.debug(`[Cache] Invalidated "${key}" on API error`);
}

/**
 * Get cache size (for debugging)
 * @returns {number} Number of cached items
 */
function size() {
  return cacheStore.size;
}

/**
 * Get metadata about cached data (age, freshness)
 * @param {string} key - Cache key
 * @param {object} options - Options including cacheType
 * @returns {object|null} Metadata with fetchedAt, age (ms), isStale
 */
function getMetadata(key, options = {}) {
  const { cacheType = "default" } = options;
  const cacheKey = `${cacheType}:${key}`;

  if (!cacheStore.has(cacheKey)) {
    return null;
  }

  const cached = cacheStore.get(cacheKey);
  const now = Date.now();
  const age = cached.fetchedAt ? now - cached.fetchedAt : 0;
  const isStale = age > MAX_STALE_AGE;

  return {
    fetchedAt: cached.fetchedAt || null,
    age,
    isStale,
    isExpired: now >= cached.expiresAt,
    expiresAt: cached.expiresAt,
  };
}

export default {
  get,
  set,
  clear,
  invalidateOnError,
  size,
  getMetadata,
};
