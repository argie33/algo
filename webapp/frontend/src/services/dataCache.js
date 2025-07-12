// Smart data caching service to reduce API calls and prevent rate limiting
class DataCacheService {
  constructor() {
    this.cache = new Map();
    this.refreshIntervals = {
      // All data refreshes at reasonable intervals to avoid costs
      marketData: 3600000, // 1 hour
      portfolio: 3600000, // 1 hour
      
      // Less critical data
      sentiment: 3600000, // 1 hour
      earnings: 86400000, // 24 hours
      financials: 86400000, // 24 hours
      news: 3600000, // 1 hour
      
      // Mostly static data
      companyInfo: 86400000, // 24 hours
      sectorData: 3600000, // 1 hour
      economicData: 3600000, // 1 hour
    };
    
    // Track API call counts for rate limiting
    this.apiCallCounts = new Map();
    this.rateLimits = {
      default: { calls: 100, window: 60000 }, // 100 calls per minute
      yfinance: { calls: 50, window: 60000 }, // 50 calls per minute
      newsapi: { calls: 100, window: 3600000 }, // 100 calls per hour
    };
  }

  isMarketHours() {
    const now = new Date();
    const day = now.getDay();
    const hour = now.getHours();
    const minute = now.getMinutes();
    
    // Market hours: Mon-Fri 9:30 AM - 4:00 PM ET
    if (day === 0 || day === 6) return false; // Weekend
    
    const marketOpen = 9.5; // 9:30 AM
    const marketClose = 16; // 4:00 PM
    const currentTime = hour + minute / 60;
    
    return currentTime >= marketOpen && currentTime < marketClose;
  }

  getCacheKey(endpoint, params = {}) {
    return `${endpoint}-${JSON.stringify(params)}`;
  }

  async get(endpoint, params = {}, options = {}) {
    const cacheKey = this.getCacheKey(endpoint, params);
    const cached = this.cache.get(cacheKey);
    
    // Determine cache duration based on endpoint type
    const cacheType = options.cacheType || 'default';
    const cacheDuration = this.refreshIntervals[cacheType] || this.refreshIntervals.marketData;
    
    // Check if we have valid cached data
    if (cached && !options.forceRefresh) {
      const age = Date.now() - cached.timestamp;
      if (age < cacheDuration) {
        console.log(`[Cache Hit] ${endpoint} - Age: ${Math.round(age/1000)}s`);
        return cached.data;
      }
    }
    
    // Check rate limiting
    if (!this.checkRateLimit(options.apiType || 'default')) {
      console.warn(`[Rate Limit] Blocked request to ${endpoint}`);
      if (cached) {
        console.log(`[Cache Fallback] Using stale cache for ${endpoint}`);
        return cached.data;
      }
      throw new Error('Rate limit exceeded - please try again later');
    }
    
    // Fetch fresh data
    try {
      console.log(`[API Call] Fetching ${endpoint}`);
      const fetchFunction = options.fetchFunction;
      if (!fetchFunction) {
        throw new Error('No fetch function provided');
      }
      
      const data = await fetchFunction();
      
      // Cache the result
      this.cache.set(cacheKey, {
        data,
        timestamp: Date.now(),
        endpoint
      });
      
      // Clean up old cache entries periodically
      if (this.cache.size > 100) {
        this.cleanupCache();
      }
      
      return data;
    } catch (error) {
      console.error(`[API Error] ${endpoint}:`, error.message);
      
      // Return stale cache if available
      if (cached) {
        console.log(`[Cache Fallback] Using stale cache after error for ${endpoint}`);
        return cached.data;
      }
      
      throw error;
    }
  }

  checkRateLimit(apiType) {
    const limit = this.rateLimits[apiType] || this.rateLimits.default;
    const now = Date.now();
    
    // Get or create rate limit tracker
    if (!this.apiCallCounts.has(apiType)) {
      this.apiCallCounts.set(apiType, []);
    }
    
    const calls = this.apiCallCounts.get(apiType);
    
    // Remove calls outside the window
    const windowStart = now - limit.window;
    const recentCalls = calls.filter(timestamp => timestamp > windowStart);
    this.apiCallCounts.set(apiType, recentCalls);
    
    // Check if we're under the limit
    if (recentCalls.length >= limit.calls) {
      return false;
    }
    
    // Record this call
    recentCalls.push(now);
    return true;
  }

  cleanupCache() {
    const now = Date.now();
    const maxAge = 24 * 60 * 60 * 1000; // 24 hours
    
    for (const [key, value] of this.cache.entries()) {
      if (now - value.timestamp > maxAge) {
        this.cache.delete(key);
      }
    }
  }

  // Batch fetch to reduce API calls
  async batchFetch(requests, options = {}) {
    const results = await Promise.allSettled(
      requests.map(req => 
        this.get(req.endpoint, req.params, {
          ...options,
          ...req.options
        })
      )
    );
    
    return results.map((result, index) => ({
      ...requests[index],
      success: result.status === 'fulfilled',
      data: result.status === 'fulfilled' ? result.value : null,
      error: result.status === 'rejected' ? result.reason : null
    }));
  }

  // Preload common data during low-activity periods
  async preloadCommonData() {
    if (!this.isMarketHours()) {
      console.log('[Cache] Preloading common data during off-hours');
      
      const commonEndpoints = [
        { endpoint: '/market/overview', cacheType: 'marketData' },
        { endpoint: '/stocks?limit=10', cacheType: 'stockData' },
        { endpoint: '/metrics', cacheType: 'metricsData' }
      ];
      
      // Stagger requests to avoid spike
      for (const endpoint of commonEndpoints) {
        try {
          await this.get(endpoint.endpoint, {}, {
            cacheType: endpoint.cacheType,
            fetchFunction: () => fetch(endpoint.endpoint).then(r => r.json())
          });
          await new Promise(resolve => setTimeout(resolve, 2000)); // 2s delay
        } catch (error) {
          console.error('[Preload Error]', endpoint.endpoint, error);
        }
      }
    }
  }

  // Get cache statistics
  getStats() {
    const stats = {
      cacheSize: this.cache.size,
      cacheEntries: [],
      apiCallCounts: {}
    };
    
    for (const [key, value] of this.cache.entries()) {
      const age = Date.now() - value.timestamp;
      stats.cacheEntries.push({
        endpoint: value.endpoint,
        age: Math.round(age / 1000),
        expired: age > (this.refreshIntervals[value.cacheType] || this.refreshIntervals.default)
      });
    }
    
    for (const [apiType, calls] of this.apiCallCounts.entries()) {
      const limit = this.rateLimits[apiType] || this.rateLimits.default;
      const windowStart = Date.now() - limit.window;
      const recentCalls = calls.filter(timestamp => timestamp > windowStart);
      
      stats.apiCallCounts[apiType] = {
        recent: recentCalls.length,
        limit: limit.calls,
        window: limit.window / 1000 + 's'
      };
    }
    
    return stats;
  }
}

// Create singleton instance
const dataCache = new DataCacheService();

// Start preloading during off-hours
if (!dataCache.isMarketHours()) {
  setTimeout(() => dataCache.preloadCommonData(), 5000);
}

export default dataCache;