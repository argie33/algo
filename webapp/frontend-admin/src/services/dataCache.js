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
    try {
      // Handle null/undefined params safely
      const safeParams = params || {};
      return `${endpoint}-${JSON.stringify(safeParams)}`;
    } catch (error) {
      console.warn(
        "[Cache] Failed to stringify params, using endpoint only:",
        error
      );
      return endpoint;
    }
  }

  async get(endpoint, params = {}, options = {}) {
    const cacheKey = this.getCacheKey(endpoint, params);
    const cached = this.cache.get(cacheKey);

    // Determine cache duration based on endpoint type
    const cacheType = options.cacheType || "default";
    const cacheDuration =
      this.refreshIntervals[cacheType] || this.refreshIntervals.marketData;

    // Check if we have valid cached data
    if (cached && !options.forceRefresh) {
      const age = Date.now() - cached.timestamp;
      if (age < cacheDuration) {
        if (import.meta.env.DEV) {
          console.log(
            `[Cache Hit] ${endpoint} - Age: ${Math.round(age / 1000)}s`
          );
        }
        return cached?.data;
      }
    }

    // Check rate limiting
    if (!this.checkRateLimit(options.apiType || "default")) {
      if (import.meta.env.DEV) {
        console.warn(`[Rate Limit] Blocked request to ${endpoint}`);
      }
      if (cached) {
        if (import.meta.env.DEV) {
          console.log(`[Cache Fallback] Using stale cache for ${endpoint}`);
        }
        return cached?.data;
      }
      throw new Error("Rate limit exceeded - please try again later");
    }

    // Fetch fresh data
    try {
      if (import.meta.env.DEV) {
        console.log(`[API Call] Fetching ${endpoint}`);
      }
      const fetchFunction = options.fetchFunction;
      if (!fetchFunction) {
        throw new Error("No fetch function provided");
      }

      const data = await fetchFunction();

      // Cache the result
      this.cache.set(cacheKey, {
        data,
        timestamp: Date.now(),
        endpoint,
      });

      // Clean up old cache entries periodically
      if (this.cache.size > 100) {
        this.cleanupCache();
      }

      return data;
    } catch (error) {
      if (import.meta.env.DEV) {
        console.error(`[API Error] ${endpoint}:`, error.message);
      }

      // Return stale cache if available
      if (cached) {
        if (import.meta.env.DEV) {
          console.log(
            `[Cache Fallback] Using stale cache after error for ${endpoint}`
          );
        }
        return cached?.data;
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
    const recentCalls = calls.filter((timestamp) => timestamp > windowStart);
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
    try {
      const now = Date.now();
      const maxAge = 24 * 60 * 60 * 1000; // 24 hours
      const keysToDelete = [];

      for (const [cacheKey, value] of this.cache.entries()) {
        // Handle invalid cache entries
        if (
          !value ||
          typeof value !== "object" ||
          typeof value.timestamp !== "number"
        ) {
          keysToDelete.push(cacheKey);
          continue;
        }

        if (now - value.timestamp > maxAge) {
          keysToDelete.push(cacheKey);
        }
      }

      // Delete entries outside the iteration to avoid modification during iteration
      keysToDelete.forEach((key) => this.cache.delete(key));

      if (import.meta.env.DEV && keysToDelete.length > 0) {
        console.log(
          `[Cache] Cleaned up ${keysToDelete.length} expired entries`
        );
      }
    } catch (error) {
      console.error("[Cache] Error during cleanup:", error);
    }
  }

  // Batch fetch to reduce API calls
  async batchFetch(requests, options = {}) {
    // Handle empty or invalid requests array
    if (!requests || !Array.isArray(requests) || requests.length === 0) {
      return [];
    }

    const results = await Promise.allSettled(
      requests.map((req) => {
        // Validate request object
        if (!req || typeof req !== "object" || !req.endpoint) {
          return Promise.reject(new Error("Invalid request object"));
        }

        return this.get(req.endpoint, req.params, {
          ...options,
          ...req.options,
        });
      })
    );

    return results.map((result, index) => ({
      ...(requests[index] || {}),
      success: result.status === "fulfilled",
      data: result.status === "fulfilled" ? result.value : null,
      error: result.status === "rejected" ? result.reason : null,
    }));
  }

  // Preload common data during low-activity periods
  async preloadCommonData() {
    if (!this.isMarketHours()) {
      if (import.meta.env.DEV) {
        console.log("[Cache] Preloading common data during off-hours");
      }

      const commonEndpoints = [
        { endpoint: "/api/market/overview", cacheType: "marketData" },
        { endpoint: "/api/sectors/sectors-with-history", cacheType: "sectorData" },
        { endpoint: "/api/sentiment/current", cacheType: "sentiment" },
      ];

      // Stagger requests to avoid spike
      for (const endpoint of commonEndpoints) {
        try {
          await this.get(
            endpoint.endpoint,
            {},
            {
              cacheType: endpoint.cacheType,
              fetchFunction: () =>
                fetch(endpoint.endpoint).then((r) => r.json()),
            }
          );
          await new Promise((resolve) => setTimeout(resolve, 2000)); // 2s delay
        } catch (error) {
          if (import.meta.env.DEV) {
            console.error("[Preload Error]", endpoint.endpoint, error);
          }
        }
      }
    }
  }

  // Get cache statistics
  getStats() {
    const stats = {
      cacheSize: this.cache.size,
      cacheEntries: [],
      apiCallCounts: {},
    };

    try {
      for (const [cacheKey, value] of this.cache.entries()) {
        // Handle invalid cache entries gracefully
        if (!value || typeof value !== "object") {
          stats.cacheEntries.push({
            endpoint: cacheKey,
            age: 0,
            expired: true,
            invalid: true,
          });
          continue;
        }

        const timestamp =
          typeof value.timestamp === "number" ? value.timestamp : 0;
        const age = Date.now() - timestamp;
        const cacheType = value.cacheType || "marketData";

        stats.cacheEntries.push({
          endpoint: value.endpoint || cacheKey,
          age: Math.round(age / 1000),
          expired:
            age >
            (this.refreshIntervals[cacheType] ||
              this.refreshIntervals.marketData),
        });
      }

      for (const [apiType, calls] of this.apiCallCounts.entries()) {
        // Handle invalid call tracking gracefully
        if (!Array.isArray(calls)) {
          stats.apiCallCounts[apiType] = {
            recent: 0,
            limit: 0,
            window: "0s",
            invalid: true,
          };
          continue;
        }

        const limit = this.rateLimits[apiType] || this.rateLimits.default;
        const windowStart = Date.now() - limit.window;
        const recentCalls = calls.filter(
          (timestamp) =>
            typeof timestamp === "number" && timestamp > windowStart
        );

        stats.apiCallCounts[apiType] = {
          recent: recentCalls.length,
          limit: limit.calls,
          window: limit.window / 1000 + "s",
        };
      }
    } catch (error) {
      console.error("[Cache] Error generating stats:", error);
    }

    return stats;
  }
}

// Create singleton instance
const dataCache = new DataCacheService();

// Start preloading during off-hours - DISABLED in development to prevent console errors
// if (!dataCache.isMarketHours()) {
//   setTimeout(() => dataCache.preloadCommonData(), 5000);
// }

export default dataCache;
