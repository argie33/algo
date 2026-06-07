import { useQuery } from '@tanstack/react-query';
import { extractData, extractPaginatedData } from '../utils/responseNormalizer';
import dataCache from '../services/dataCache';

/**
 * React Query wrapper with standardized error/loading/data handling.
 *
 * Contract:
 *   queryFn must return an axios response OR pre-parsed body.
 *   extractData strips the axios wrapper + {success, data} envelope,
 *   returning the clean inner data object or array.
 *
 * Usage:
 *   const { data, loading, error } = useApiQuery(
 *     ['sectors', { limit: 20 }],
 *     () => api.get('/api/sectors', { params: { limit: 20 } })
 *   );
 */
export const useApiQuery = (
  queryKey,
  queryFn,
  {
    staleTime = 30000,
    gcTime = 10 * 60 * 1000,
    retry = 3,
    enabled = true,
    cacheKey = null,
    ...restOptions
  } = {}
) => {
  const actualCacheKey = cacheKey || (Array.isArray(queryKey) ? queryKey[0] : queryKey);

  // User-friendly error message
  const _getErrorMessage = (err) => {
    if (!err) return null;
    const status = err?.response?.status;
    if (status === 401 || status === 403) return 'Authentication failed. Please log in.';
    if (status === 404) return 'Resource not found';
    if (status >= 500) return 'Server error. Please try again later.';
    if (err.message?.includes('Network') || err.message?.includes('timeout')) {
      return 'Network error. Please check your connection.';
    }
    return err.message || 'Failed to load data';
  };

  const { data: rawData, isLoading, error, ...rest } = useQuery({
    queryKey: Array.isArray(queryKey) ? queryKey : [queryKey],
    queryFn: async () => {
      try {
        const response = await queryFn();
        const freshData = extractData(response);
        // Cache successful result for fallback
        try {
          await dataCache.set(actualCacheKey, freshData, { ttl: 30 * 60 * 1000 });
        } catch (cacheErr) {
          console.warn('[useApiQuery] Failed to cache data:', cacheErr.message);
          // Continue anyway - cache failure shouldn't break the query
        }
        return freshData;
      } catch (err) {
        // Error already logged by api.js interceptor, skip duplicate logging
        // Try to return cached data as fallback when all retries exhausted
        try {
          const cachedData = await dataCache.get(actualCacheKey);
          if (cachedData) {
            console.info('[useApiQuery] Returning cached fallback for:', actualCacheKey);
            if (Array.isArray(cachedData)) {
              return cachedData;
            }
            return { ...cachedData, fromCache: true };
          }
        } catch (cacheErr) {
          console.warn('[useApiQuery] Failed to retrieve cached fallback:', cacheErr.message);
          // Continue to throw original error
        }
        throw err;
      }
    },
    staleTime,
    gcTime,
    retry: retry === false ? false : (failureCount, err) => {
      const status = err?.response?.status ?? err?.status;
      const errorMsg = err?.message || '';

      // Never retry on explicit auth failures (user not logged in)
      if (status === 401 || status === 403) {
        // EXCEPTION: If auth token is being refreshed, allow ONE retry
        // (token refresh happens in background, request might succeed on next attempt)
        if (errorMsg.includes('token') || errorMsg.includes('auth') || errorMsg.includes('refresh')) {
          if (failureCount < 1) {
            console.warn('[useApiQuery] Auth token refresh in progress, retrying once:', err.message);
            return true;
          }
        }
        return false;
      }

      // Never retry on not found (resource doesn't exist)
      if (status === 404) return false;

      // Retry on 5xx errors with BALANCED retries (fail fast if API is down)
      // Allow up to 3 retries (4 total attempts) for backend recovery
      if (status >= 500) return failureCount < 3;

      // Retry on network errors and timeouts with LIMITED attempts
      // Aggressive retry strategy: fail fast if API is truly down
      if (errorMsg.includes('timeout') || errorMsg.includes('Network') || errorMsg.includes('ECONNREFUSED') || errorMsg.includes('502') || errorMsg.includes('503')) {
        return failureCount < 3;
      }

      // Default: no retry for unknown errors
      return false;
    },
    retryDelay: (attemptIndex) => {
      // Aggressive backoff: 200ms, 500ms, 1s (capped at 5s)
      // Total wait time: 0.2+0.5+1 = 1.7s for 3 retries (fail fast if API is down)
      const baseWait = 200 * Math.pow(2, attemptIndex);
      const cappedWait = Math.min(baseWait, 5000);
      return cappedWait;
    },
    enabled,
    ...restOptions,
  });

  const enrichedError = error ? {
    message: error?.message || 'Unknown error',
    status: error?.response?.status ?? error?.status ?? 0,
    code: error?.code,
    url: error?.config?.url,
    responseData: error?.response?.data,
    isNetworkError: !error?.response,
    httpStatus: error?.response?.status || (error?.message?.includes('timeout') ? 504 : 0),
  } : null;

  return {
    data: rawData,
    loading: isLoading,
    error: enrichedError,
    isFetching: rest.isFetching,
    refetch: rest.refetch,
    ...rest,
  };
};

/**
 * React Query wrapper for paginated responses.
 * Expects queryFn to return a response with {items: [...], pagination: {...}}
 * inside the standard {success, data} envelope.
 *
 * Usage:
 *   const { items, pagination, loading } = useApiPaginatedQuery(
 *     ['sectors', page],
 *     () => api.get('/api/sectors', { params: { page } })
 *   );
 */
export const useApiPaginatedQuery = (
  queryKey,
  queryFn,
  {
    staleTime = 30000,
    gcTime = 10 * 60 * 1000,
    retry = 3,
    enabled = true,
    cacheKey = null,
    ...restOptions
  } = {}
) => {
  const actualCacheKey = cacheKey || (Array.isArray(queryKey) ? queryKey[0] : queryKey);

  const { data: rawData, isLoading, error, ...rest } = useQuery({
    queryKey: Array.isArray(queryKey) ? queryKey : [queryKey],
    queryFn: async () => {
      try {
        const response = await queryFn();
        const freshData = extractPaginatedData(response);
        // Cache successful result for fallback
        try {
          await dataCache.set(actualCacheKey, freshData, { ttl: 30 * 60 * 1000 });
        } catch (cacheErr) {
          console.warn('[useApiPaginatedQuery] Failed to cache data:', cacheErr.message);
          // Continue anyway - cache failure shouldn't break the query
        }
        return freshData;
      } catch (err) {
        // Error already logged by api.js interceptor, skip duplicate logging
        // Try to return cached data as fallback when all retries exhausted
        try {
          const cachedData = await dataCache.get(actualCacheKey);
          if (cachedData) {
            console.info('[useApiPaginatedQuery] Returning cached fallback for:', actualCacheKey);
            if (Array.isArray(cachedData)) {
              return cachedData;
            }
            return { ...cachedData, fromCache: true };
          }
        } catch (cacheErr) {
          console.warn('[useApiPaginatedQuery] Failed to retrieve cached fallback:', cacheErr.message);
          // Continue to throw original error
        }
        throw err;
      }
    },
    staleTime,
    gcTime,
    retry: retry === false ? false : (failureCount, err) => {
      const status = err?.response?.status ?? err?.status;
      const errorMsg = err?.message || '';

      // Never retry on explicit auth failures (user not logged in)
      if (status === 401 || status === 403) {
        // EXCEPTION: If auth token is being refreshed, allow ONE retry
        // (token refresh happens in background, request might succeed on next attempt)
        if (errorMsg.includes('token') || errorMsg.includes('auth') || errorMsg.includes('refresh')) {
          if (failureCount < 1) {
            console.warn('[useApiQuery] Auth token refresh in progress, retrying once:', err.message);
            return true;
          }
        }
        return false;
      }

      // Never retry on not found (resource doesn't exist)
      if (status === 404) return false;

      // Retry on 5xx errors with BALANCED retries (fail fast if API is down)
      // Allow up to 3 retries (4 total attempts) for backend recovery
      if (status >= 500) return failureCount < 3;

      // Retry on network errors and timeouts with LIMITED attempts
      // Aggressive retry strategy: fail fast if API is truly down
      if (errorMsg.includes('timeout') || errorMsg.includes('Network') || errorMsg.includes('ECONNREFUSED') || errorMsg.includes('502') || errorMsg.includes('503')) {
        return failureCount < 3;
      }

      // Default: no retry for unknown errors
      return false;
    },
    retryDelay: (attemptIndex) => {
      // Aggressive backoff: 200ms, 500ms, 1s (capped at 5s)
      // Total wait time: 0.2+0.5+1 = 1.7s for 3 retries (fail fast if API is down)
      const baseWait = 200 * Math.pow(2, attemptIndex);
      const cappedWait = Math.min(baseWait, 5000);
      return cappedWait;
    },
    enabled,
    ...restOptions,
  });

  const enrichedError = error ? {
    message: error?.message || 'Unknown error',
    status: error?.response?.status ?? error?.status ?? 0,
    code: error?.code,
    url: error?.config?.url,
    responseData: error?.response?.data,
    isNetworkError: !error?.response,
    httpStatus: error?.response?.status || (error?.message?.includes('timeout') ? 504 : 0),
  } : null;

  return {
    items: Array.isArray(rawData?.items) ? rawData.items : [],
    pagination: (rawData?.pagination && typeof rawData.pagination === 'object') ? rawData.pagination : {
      total: 0, limit: 50, offset: 0, page: 1, totalPages: 1, hasNext: false, hasPrev: false,
    },
    loading: isLoading,
    error: enrichedError,
    isFetching: rest.isFetching,
    refetch: rest.refetch,
    ...rest,
  };
};

export default { useApiQuery, useApiPaginatedQuery };

