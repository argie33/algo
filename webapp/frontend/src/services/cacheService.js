// Cache Service for Performance Optimization
// Manages in-memory caching, localStorage persistence, and data freshness

class CacheService {
  constructor() {
    this.cache = new Map();
    this.timestamps = new Map();
    this.maxSize = 1000; // Maximum number of cached items
    this.defaultTTL = 5 * 60 * 1000; // 5 minutes in milliseconds
    
    // Cache statistics
    this.stats = {
      hits: 0,
      misses: 0,
      sets: 0,
      evictions: 0,
      lastCleanup: Date.now()
    };
    
    // Cleanup expired entries every 5 minutes
    this.cleanupInterval = setInterval(() => {
      this.cleanup();
    }, 5 * 60 * 1000);
    
    // Load persistent cache from localStorage
    this.loadPersistentCache();
  }

  // Generate cache key
  generateKey(prefix, params = {}) {
    const paramString = Object.keys(params)
      .sort()
      .map(key => `${key}=${params[key]}`)
      .join('&');
    return `${prefix}${paramString ? `?${paramString}` : ''}`;
  }

  // Set cache entry
  set(key, value, ttl = this.defaultTTL, persist = false) {
    // Evict oldest entries if cache is full
    if (this.cache.size >= this.maxSize) {
      this.evictOldest();
    }

    const entry = {
      value,
      timestamp: Date.now(),
      ttl,
      persist,
      accessCount: 0,
      lastAccess: Date.now()
    };

    this.cache.set(key, entry);
    this.timestamps.set(key, entry.timestamp);
    this.stats.sets++;

    // Persist to localStorage if requested
    if (persist) {
      this.persistToLocalStorage(key, entry);
    }

    return true;
  }

  // Get cache entry
  get(key) {
    const entry = this.cache.get(key);
    
    if (!entry) {
      this.stats.misses++;
      return null;
    }

    // Check if expired
    if (this.isExpired(entry)) {
      this.delete(key);
      this.stats.misses++;
      return null;
    }

    // Update access statistics
    entry.accessCount++;
    entry.lastAccess = Date.now();
    this.stats.hits++;

    return entry.value;
  }

  // Check if entry exists and is not expired
  has(key) {
    const entry = this.cache.get(key);
    return entry && !this.isExpired(entry);
  }

  // Delete cache entry
  delete(key) {
    const deleted = this.cache.delete(key);
    this.timestamps.delete(key);
    
    // Remove from localStorage if it exists
    if (typeof window !== 'undefined' && window.localStorage) {
      try {
        localStorage.removeItem(`cache_${key}`);
      } catch (e) {
        console.warn('Failed to remove from localStorage:', e);
      }
    }
    
    return deleted;
  }

  // Clear all cache
  clear() {
    this.cache.clear();
    this.timestamps.clear();
    this.stats.evictions += this.cache.size;
    
    // Clear localStorage cache
    if (typeof window !== 'undefined' && window.localStorage) {
      try {
        Object.keys(localStorage).forEach(key => {
          if (key.startsWith('cache_')) {
            localStorage.removeItem(key);
          }
        });
      } catch (e) {
        console.warn('Failed to clear localStorage cache:', e);
      }
    }
  }

  // Check if entry is expired
  isExpired(entry) {
    return Date.now() - entry.timestamp > entry.ttl;
  }

  // Evict oldest entries
  evictOldest() {
    const sortedByTimestamp = Array.from(this.timestamps.entries())
      .sort((a, b) => a[1] - b[1]);
    
    // Remove oldest 10% of entries
    const toRemove = Math.floor(this.cache.size * 0.1);
    for (let i = 0; i < toRemove; i++) {
      const [key] = sortedByTimestamp[i];
      this.delete(key);
      this.stats.evictions++;
    }
  }

  // Cleanup expired entries
  cleanup() {
    const now = Date.now();
    const expired = [];

    for (const [key, entry] of this.cache.entries()) {
      if (this.isExpired(entry)) {
        expired.push(key);
      }
    }

    expired.forEach(key => this.delete(key));
    this.stats.lastCleanup = now;
    
    console.log(`Cache cleanup: removed ${expired.length} expired entries`);
  }

  // Get cache statistics
  getStats() {
    const hitRate = this.stats.hits / (this.stats.hits + this.stats.misses) * 100;
    
    return {
      ...this.stats,
      hitRate: isNaN(hitRate) ? 0 : hitRate,
      size: this.cache.size,
      maxSize: this.maxSize,
      memoryUsage: this.estimateMemoryUsage()
    };
  }

  // Estimate memory usage (rough calculation)
  estimateMemoryUsage() {
    let totalSize = 0;
    
    for (const [key, entry] of this.cache.entries()) {
      totalSize += key.length * 2; // Rough estimate for string
      totalSize += JSON.stringify(entry.value).length * 2; // Rough estimate for value
      totalSize += 100; // Overhead for entry metadata
    }
    
    return totalSize;
  }

  // Persist to localStorage
  persistToLocalStorage(key, entry) {
    if (typeof window === 'undefined' || !window.localStorage) {
      return;
    }

    try {
      const persistData = {
        value: entry.value,
        timestamp: entry.timestamp,
        ttl: entry.ttl
      };
      
      localStorage.setItem(`cache_${key}`, JSON.stringify(persistData));
    } catch (e) {
      console.warn('Failed to persist to localStorage:', e);
    }
  }

  // Load persistent cache from localStorage
  loadPersistentCache() {
    if (typeof window === 'undefined' || !window.localStorage) {
      return;
    }

    try {
      Object.keys(localStorage).forEach(storageKey => {
        if (storageKey.startsWith('cache_')) {
          const key = storageKey.replace('cache_', '');
          const data = JSON.parse(localStorage.getItem(storageKey));
          
          const entry = {
            value: data.value,
            timestamp: data.timestamp,
            ttl: data.ttl,
            persist: true,
            accessCount: 0,
            lastAccess: Date.now()
          };

          // Only load if not expired
          if (!this.isExpired(entry)) {
            this.cache.set(key, entry);
            this.timestamps.set(key, entry.timestamp);
          } else {
            // Remove expired entry from localStorage
            localStorage.removeItem(storageKey);
          }
        }
      });
    } catch (e) {
      console.warn('Failed to load persistent cache:', e);
    }
  }

  // Cache wrapper for API calls
  async cacheApiCall(key, apiCall, ttl = this.defaultTTL, persist = false) {
    // Check cache first
    const cached = this.get(key);
    if (cached) {
      return cached;
    }

    try {
      // Make API call
      const result = await apiCall();
      
      // Cache the result
      this.set(key, result, ttl, persist);
      
      return result;
    } catch (error) {
      console.error('API call failed:', error);
      throw error;
    }
  }

  // Cache with refresh strategy
  async getWithRefresh(key, apiCall, ttl = this.defaultTTL, refreshThreshold = 0.8) {
    const entry = this.cache.get(key);
    
    if (entry) {
      const age = Date.now() - entry.timestamp;
      const shouldRefresh = age > (entry.ttl * refreshThreshold);
      
      if (shouldRefresh) {
        // Return cached data immediately, refresh in background
        this.backgroundRefresh(key, apiCall, ttl);
      }
      
      if (!this.isExpired(entry)) {
        entry.accessCount++;
        entry.lastAccess = Date.now();
        this.stats.hits++;
        return entry.value;
      }
    }

    // Cache miss or expired - fetch fresh data
    return this.cacheApiCall(key, apiCall, ttl);
  }

  // Background refresh
  async backgroundRefresh(key, apiCall, ttl) {
    try {
      const result = await apiCall();
      this.set(key, result, ttl, this.cache.get(key)?.persist || false);
    } catch (error) {
      console.warn('Background refresh failed:', error);
    }
  }

  // Get most accessed items
  getMostAccessed(limit = 10) {
    return Array.from(this.cache.entries())
      .sort((a, b) => b[1].accessCount - a[1].accessCount)
      .slice(0, limit)
      .map(([key, entry]) => ({
        key,
        accessCount: entry.accessCount,
        lastAccess: entry.lastAccess,
        age: Date.now() - entry.timestamp
      }));
  }

  // Destroy cache service
  destroy() {
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval);
    }
    this.clear();
  }
}

// Cache configurations for different data types
export const CacheConfigs = {
  STOCK_QUOTE: {
    ttl: 30 * 1000, // 30 seconds
    persist: false
  },
  STOCK_HISTORY: {
    ttl: 5 * 60 * 1000, // 5 minutes
    persist: true
  },
  COMPANY_INFO: {
    ttl: 24 * 60 * 60 * 1000, // 24 hours
    persist: true
  },
  MARKET_DATA: {
    ttl: 60 * 1000, // 1 minute
    persist: false
  },
  NEWS: {
    ttl: 10 * 60 * 1000, // 10 minutes
    persist: true
  },
  WATCHLIST: {
    ttl: Infinity, // Never expire
    persist: true
  },
  USER_PREFERENCES: {
    ttl: Infinity, // Never expire
    persist: true
  }
};

// Create singleton instance
const cacheService = new CacheService();

export default cacheService;