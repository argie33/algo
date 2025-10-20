/**
 * Native Data Service - Replaces React Query
 * Provides caching, error handling, and loading states without external dependencies
 */

class DataService {
  constructor() {
    this.cache = new Map();
    this.loadingStates = new Map();
    this.errorStates = new Map();
    this.subscribers = new Map();

    // Cache settings
    this.defaultStaleTime = 5 * 60 * 1000; // 5 minutes
    this.defaultCacheTime = 10 * 60 * 1000; // 10 minutes

    // Cleanup interval
    this.cleanupInterval = setInterval(() => {
      this.cleanup();
    }, 60 * 1000); // Cleanup every minute
  }

  // Generate cache key from query parameters
  getCacheKey(url, options = {}) {
    const params = new URLSearchParams(options.params || {}).toString();
    return `${url}${params ? `?${params}` : ""}`;
  }

  // Check if cached data is still fresh
  isFresh(cacheEntry, staleTime = this.defaultStaleTime) {
    return Date.now() - cacheEntry.timestamp < staleTime;
  }

  // Fetch data with caching and error handling
  async fetchData(url, options = {}) {
    const cacheKey = this.getCacheKey(url, options);
    const staleTime = options.staleTime || this.defaultStaleTime;

    // Return cached data if fresh
    const cached = this.cache.get(cacheKey);
    if (cached && this.isFresh(cached, staleTime)) {
      return {
        data: cached?.data,
        isLoading: false,
        error: null,
        isStale: false,
      };
    }

    // Return loading state if already fetching
    if (this.loadingStates.get(cacheKey)) {
      return {
        data: cached?.data || null,
        isLoading: true,
        error: null,
        isStale: cached ? !this.isFresh(cached, staleTime) : false,
      };
    }

    // Set loading state
    this.loadingStates.set(cacheKey, true);
    this.errorStates.delete(cacheKey);

    try {
      // Get API base URL
      const apiUrl = this.getApiUrl();
      const fullUrl = url.startsWith("http") ? url : `${apiUrl}${url}`;

      // Prepare fetch options
      const fetchOptions = {
        method: options.method || "GET",
        headers: {
          "Content-Type": "application/json",
          ...options.headers,
        },
        ...options.fetchOptions,
      };

      // Add auth token if available
      const token = await this.getAuthToken();
      if (token) {
        fetchOptions.headers.Authorization = `Bearer ${token}`;
      }

      // Add body for POST/PUT requests
      if (options.body) {
        fetchOptions.body = JSON.stringify(options.body);
      }

      // Add timeout and performance monitoring based on testing insights
      const startTime = Date.now();
      const timeoutPromise = new Promise((_, reject) =>
        setTimeout(
          () => reject(new Error("Request timeout after 30 seconds")),
          30000
        )
      );

      const response = await Promise.race([
        fetch(fullUrl, fetchOptions),
        timeoutPromise,
      ]);

      const duration = Date.now() - startTime;

      // Log slow requests based on testing insights
      if (duration > 10000) {
        console.warn(`⚠️ Very slow API request (${duration}ms):`, fullUrl);
      } else if (duration > 5000) {
        console.warn(`⏱️ Slow API request (${duration}ms):`, fullUrl);
      }

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();

      // Cache the response
      this.cache.set(cacheKey, {
        data,
        timestamp: Date.now(),
      });

      // Clear loading and error states
      this.loadingStates.delete(cacheKey);
      this.errorStates.delete(cacheKey);

      // Notify subscribers
      this.notifySubscribers(cacheKey, {
        data,
        isLoading: false,
        error: null,
        isStale: false,
      });

      return {
        data,
        isLoading: false,
        error: null,
        isStale: false,
      };
    } catch (error) {
      console.error(`DataService fetch error for ${url}:`, error);

      // Set error state
      this.errorStates.set(cacheKey, error);
      this.loadingStates.delete(cacheKey);

      // Notify subscribers
      this.notifySubscribers(cacheKey, {
        data: cached?.data || null,
        isLoading: false,
        error,
        isStale: cached ? !this.isFresh(cached, staleTime) : false,
      });

      return {
        data: cached?.data || null,
        isLoading: false,
        error,
        isStale: cached ? !this.isFresh(cached, staleTime) : false,
      };
    }
  }

  // Get API URL from config
  getApiUrl() {
    // Check runtime config first
    if (typeof window !== "undefined" && window.__CONFIG__?.API_URL) {
      return window.__CONFIG__.API_URL;
    }

    // Fallback to environment variable
    return (
      (import.meta.env && import.meta.env.VITE_API_URL) ||
      "http://localhost:3001"
    );
  }

  // Get authentication token
  async getAuthToken() {
    try {
      // Import auth service dynamically to avoid circular dependencies
      const devAuth = await import("./devAuth");
      const session = devAuth.default.session;
      return session?.accessToken || null;
    } catch (error) {
      console.warn("Failed to get auth token:", error);
      return null;
    }
  }

  // Subscribe to data changes
  subscribe(cacheKey, callback) {
    if (!this.subscribers.has(cacheKey)) {
      this.subscribers.set(cacheKey, new Set());
    }
    this.subscribers.get(cacheKey).add(callback);

    // Return unsubscribe function
    return () => {
      const callbacks = this.subscribers.get(cacheKey);
      if (callbacks) {
        callbacks.delete(callback);
        if (callbacks.size === 0) {
          this.subscribers.delete(cacheKey);
        }
      }
    };
  }

  // Notify subscribers of data changes
  notifySubscribers(cacheKey, result) {
    const callbacks = this.subscribers.get(cacheKey);
    if (callbacks) {
      callbacks.forEach((callback) => {
        try {
          callback(result);
        } catch (error) {
          console.error("Error notifying subscriber:", error);
        }
      });
    }
  }

  // Invalidate cache entry
  invalidate(url, options = {}) {
    const cacheKey = this.getCacheKey(url, options);
    this.cache.delete(cacheKey);
    this.errorStates.delete(cacheKey);
  }

  // Refetch data (bypass cache)
  async refetch(url, options = {}) {
    const cacheKey = this.getCacheKey(url, options);
    this.cache.delete(cacheKey);
    this.errorStates.delete(cacheKey);
    return this.fetchData(url, options);
  }

  // Cleanup expired cache entries
  cleanup() {
    const now = Date.now();
    for (const [key, entry] of this.cache.entries()) {
      if (now - entry.timestamp > this.defaultCacheTime) {
        this.cache.delete(key);
      }
    }
  }

  // Clear all cache
  clearCache() {
    this.cache.clear();
    this.loadingStates.clear();
    this.errorStates.clear();
  }

  // Destroy service (cleanup)
  destroy() {
    if (this.cleanupInterval) {
      clearInterval(this.cleanupInterval);
    }
    this.clearCache();
    this.subscribers.clear();
  }
}

// Create singleton instance
const dataService = new DataService();

export default dataService;

// Export convenience methods
export const fetchData = (url, options) => dataService.fetchData(url, options);
export const invalidateCache = (url, options) =>
  dataService.invalidate(url, options);
export const refetchData = (url, options) => dataService.refetch(url, options);
export const clearAllCache = () => dataService.clearCache();
