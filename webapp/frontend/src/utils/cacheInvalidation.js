/**
 * Cache Invalidation Utilities
 * Provides explicit cache clearing after mutations (trade entry/exit, position updates)
 *
 * When mutations occur, we must invalidate related cache entries so the UI reflects
 * the actual state. This prevents users from seeing stale data until the 5-min TTL expires.
 */

import dataCache from "../services/dataCache";
import { useQueryClient } from "@tanstack/react-query";

/**
 * Invalidate all position-related cache entries after mutations
 * @param {string} symbol - Optional: if provided, only invalidate cache for this symbol
 */
export function invalidatePositionCache(symbol = null) {
  const patterns = [
    "algo-positions", // all positions
    "portfolio-summary", // portfolio totals
    "trade-history", // trade list
  ];

  if (symbol) {
    // Also invalidate symbol-specific caches
    patterns.push(`.*${symbol}.*`);
  }

  patterns.forEach((pattern) => {
    dataCache.clear(pattern);
  });

  console.debug(
    `[Cache] Invalidated position cache${symbol ? ` for ${symbol}` : " (all)"}`
  );
}

/**
 * Invalidate all trading-related cache after entry/exit
 * @param {string} symbol - Symbol that was traded
 */
export function invalidateTradeCache(symbol) {
  const patterns = [
    "algo-positions",
    "portfolio-summary",
    "trade-history",
    "algo-trades",
    "active-trades",
    `.*${symbol}.*`,
  ];

  patterns.forEach((pattern) => {
    dataCache.clear(pattern);
  });

  console.debug(`[Cache] Invalidated trade cache for ${symbol}`);
}

/**
 * Hook to get React Query client for programmatic cache invalidation
 * Use this in components that perform mutations
 *
 * @returns {object} React Query client with invalidation methods
 *
 * Example usage in a component:
 *   const { invalidateQueries } = useInvalidateCache();
 *   // After mutation succeeds:
 *   invalidateQueries('algo-positions');
 */
export function useInvalidateCache() {
  const queryClient = useQueryClient();

  return {
    /**
     * Invalidate queries by key pattern
     * @param {string|string[]} keys - Query key(s) to invalidate
     */
    invalidateQueries: async (keys) => {
      const keyArray = Array.isArray(keys) ? keys : [keys];
      for (const key of keyArray) {
        await queryClient.invalidateQueries({ queryKey: [key] });
      }
      // Also clear from dataCache as fallback
      keyArray.forEach((key) => {
        dataCache.clear(key);
      });
    },

    /**
     * Refetch specific queries immediately
     * @param {string|string[]} keys - Query key(s) to refetch
     */
    refetchQueries: async (keys) => {
      const keyArray = Array.isArray(keys) ? keys : [keys];
      for (const key of keyArray) {
        await queryClient.refetchQueries({ queryKey: [key] });
      }
    },

    /**
     * Clear all cache (nuclear option, use sparingly)
     */
    clearAll: () => {
      queryClient.clear();
      dataCache.clear();
    },
  };
}

/**
 * Higher-order wrapper for mutation callbacks
 * Automatically invalidates relevant caches after mutation success/failure
 *
 * @param {function} mutationFn - The actual mutation function
 * @param {string|string[]} invalidateCacheKeys - Keys to invalidate on success
 * @returns {function} Wrapped mutation function
 */
export function withCacheInvalidation(mutationFn, invalidateCacheKeys = []) {
  return async (...args) => {
    try {
      const result = await mutationFn(...args);

      // On success, invalidate cache
      const keys = Array.isArray(invalidateCacheKeys)
        ? invalidateCacheKeys
        : [invalidateCacheKeys];
      keys.forEach((key) => {
        dataCache.clear(key);
      });

      return result;
    } catch (error) {
      // On error, still invalidate cache to force refresh on retry
      const keys = Array.isArray(invalidateCacheKeys)
        ? invalidateCacheKeys
        : [invalidateCacheKeys];
      keys.forEach((key) => {
        dataCache.clear(key);
      });
      throw error;
    }
  };
}

export default {
  invalidatePositionCache,
  invalidateTradeCache,
  useInvalidateCache,
  withCacheInvalidation,
};
