import { useQuery } from '@tanstack/react-query';
import { extractData, extractPaginatedData, validateItems } from '../utils/responseNormalizer';
import { validateResponse, validateArrayItems } from '../utils/responseValidator';
import {
  getEndpointSchema, getRequiredFields, getItemRequiredFields, getDecimalFields,
} from '../utils/endpointSchemas';
import dataCache from '../services/dataCache';
import { toFixed } from '../utils/decimalMath';

/**
 * React Query wrapper with standardized error/loading/data handling.
 *
 * Contract:
 *   queryFn must return an axios response OR pre-parsed body.
 *   extractData strips the axios wrapper + {success, data} envelope,
 *   returning the clean inner data object or array.
 *
 * Tracks fetch timestamps and timeout. Returns data with metadata:
 *   - _fetchedAt: timestamp when data was last fetched
 *   - _age: age of data in milliseconds
 *   - _fromCache: true if using fallback cache
 *   - _isStale: true if data is older than MAX_STALE_AGE (2 hours)
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
    staleTime = Infinity,
    gcTime = 10 * 60 * 1000,
    retry = 3,
    enabled = true,
    cacheKey = null,
    timeout = 15000,
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

  // Helper to add timeout to a promise
  const withTimeout = (promise, ms) => {
    const timeoutPromise = new Promise((_, reject) =>
      setTimeout(() => reject(new Error(`Request timeout after ${ms}ms`)), ms)
    );
    return Promise.race([promise, timeoutPromise]);
  };

  // Helper to format decimal fields for financial precision
  const formatDecimalFields = (data, endpoint) => {
    if (!data || typeof data !== 'object') return data;

    const decimalFields = getDecimalFields(endpoint);
    if (decimalFields.length === 0) return data;

    const formatValue = (val) => {
      if (val === null || val === undefined) return val;
      const num = parseFloat(val);
      if (isNaN(num)) return val;
      return parseFloat(num.toFixed(2));
    };

    if (Array.isArray(data)) {
      return data.map(item => {
        if (!item || typeof item !== 'object') return item;
        const formatted = { ...item };
        for (const field of decimalFields) {
          if (field in formatted) {
            formatted[field] = formatValue(formatted[field]);
          }
        }
        return formatted;
      });
    }

    const formatted = { ...data };
    for (const field of decimalFields) {
      if (field in formatted) {
        formatted[field] = formatValue(formatted[field]);
      }
    }
    return formatted;
  };

  // Helper to add fetch metadata to data
  const addMetadata = (data, fetchedAt = Date.now(), isFromCache = false) => {
    if (!data || typeof data !== 'object') return data;

    const now = Date.now();
    const age = now - fetchedAt;
    const isStale = age > (2 * 60 * 60 * 1000); // 2 hours

    if (Array.isArray(data)) {
      return data.map(item => ({
        ...item,
        _fetchedAt: fetchedAt,
        _age: age,
        _fromCache: isFromCache,
        _isStale: isStale,
      }));
    }

    return {
      ...data,
      _fetchedAt: fetchedAt,
      _age: age,
      _fromCache: isFromCache,
      _isStale: isStale,
    };
  };

  const { data: rawData, isLoading, error, ...rest } = useQuery({
    queryKey: Array.isArray(queryKey) ? queryKey : [queryKey],
    queryFn: async () => {
      const fetchStartTime = Date.now();
      try {
        const response = await withTimeout(queryFn(), timeout);
        const freshData = extractData(response);

        // Get endpoint schema to validate required fields
        const endpointSchema = getEndpointSchema(actualCacheKey);
        const requiredFields = getRequiredFields(actualCacheKey);

        // Validate response based on schema
        let result;
        if (freshData && typeof freshData === 'object' && !Array.isArray(freshData)) {
          if (freshData.data !== undefined && !freshData.items) {
            // Single-object response structure
            const validation = validateResponse(freshData, {
              requiredFields,
              requireNonEmpty: endpointSchema?.requireNonEmpty || false,
              context: `${actualCacheKey} response`,
            });

            // Log warnings even if validation passed
            if (validation.warnings && validation.warnings.length > 0) {
              validation.warnings.forEach(w => console.warn(w, { endpoint: actualCacheKey }));
            }

            if (!validation.valid) {
              throw new Error(`Invalid response envelope: ${validation.errors.join('; ')}`);
            }

            result = validation.data;
            if (result === null) {
              throw new Error(`Response validation failed: ${actualCacheKey} returned null data`);
            }
          } else if (freshData.items !== undefined) {
            // Paginated structure detected (shouldn't happen in useApiQuery, but handle it)
            result = freshData;
          } else {
            // No standard envelope
            result = freshData;
          }
        } else {
          // Direct array or other format
          result = freshData;
        }

        // Format decimal fields for financial precision
        const formattedResult = formatDecimalFields(result, actualCacheKey);

        // Cache the validated result
        try {
          await dataCache.set(actualCacheKey, formattedResult, { ttl: 30 * 60 * 1000 });
        } catch (cacheErr) {
          console.warn('[useApiQuery] Failed to cache data:', cacheErr.message);
          // Continue anyway - cache failure shouldn't break the query
        }
        return addMetadata(formattedResult, fetchStartTime, false);
      } catch (err) {
        console.warn('[useApiQuery] Query failed', err);
        // Try to return cached data as fallback when all retries exhausted
        try {
          const cachedData = await dataCache.get(actualCacheKey);
          const metadata = await dataCache.getMetadata(actualCacheKey);
          if (cachedData) {
            console.info('[useApiQuery] Returning cached fallback for:', actualCacheKey, metadata);
            const cachedFetchTime = metadata?.fetchedAt || fetchStartTime;
            return addMetadata(cachedData, cachedFetchTime, true);
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
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
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
      if (status >= 500) {
        if (failureCount < 3) {
          console.warn(`[useApiQuery] Server error (${status}), retrying (attempt ${failureCount + 1}/3)`, errorMsg);
          return true;
        }
        return false;
      }

      // Retry on network errors and timeouts with LIMITED attempts
      // Aggressive retry strategy: fail fast if API is truly down
      if (errorMsg.includes('timeout') || errorMsg.includes('Network') || errorMsg.includes('ECONNREFUSED') || errorMsg.includes('502') || errorMsg.includes('503')) {
        if (failureCount < 3) {
          console.warn(`[useApiQuery] Network error, retrying (attempt ${failureCount + 1}/3):`, errorMsg);
          return true;
        }
        return false;
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

        // Validate items array structure
        const endpointSchema = getEndpointSchema(actualCacheKey);
        const itemRequiredFields = getItemRequiredFields(actualCacheKey);
        const requireNonEmptyList = endpointSchema?.requireNonEmptyList || false;

        const itemValidation = validateArrayItems(
          freshData.items || [],
          itemRequiredFields,
          `${actualCacheKey} items`,
          { requireNonEmpty: requireNonEmptyList }
        );

        if (!itemValidation.valid) {
          // If array is non-empty and has malformed items, filter them out
          // If array must be non-empty but is empty, that's an error that should propagate
          if ((freshData.items?.length || 0) > 0 && itemValidation.invalidItems.length > 0) {
            console.warn(`[useApiPaginatedQuery] ${itemValidation.errors[0]}`, {
              endpoint: actualCacheKey,
              invalidItemIndices: itemValidation.invalidItems.map(iv => iv.index),
              totalItems: freshData.items.length,
            });
            // Filter out invalid items
            const validItems = freshData.items.filter((_, idx) =>
              !itemValidation.invalidItems.some(iv => iv.index === idx)
            );
            freshData.items = validItems;
            freshData.pagination.total = Math.max(0, freshData.pagination.total - itemValidation.invalidItems.length);
          } else if (requireNonEmptyList && freshData.items?.length === 0) {
            throw new Error(`Invalid response: ${itemValidation.errors.join('; ')}`);
          }
        }

        // Cache successful result for fallback
        try {
          await dataCache.set(actualCacheKey, freshData, { ttl: 30 * 60 * 1000 });
        } catch (cacheErr) {
          console.warn('[useApiPaginatedQuery] Failed to cache data:', cacheErr.message);
          // Continue anyway - cache failure shouldn't break the query
        }
        return freshData;
      } catch (err) {
        console.warn('[useApiPaginatedQuery] Query failed', err);
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
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
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
      if (status >= 500) {
        if (failureCount < 3) {
          console.warn(`[useApiPaginatedQuery] Server error (${status}), retrying (attempt ${failureCount + 1}/3)`, errorMsg);
          return true;
        }
        return false;
      }

      // Retry on network errors and timeouts with LIMITED attempts
      // Aggressive retry strategy: fail fast if API is truly down
      if (errorMsg.includes('timeout') || errorMsg.includes('Network') || errorMsg.includes('ECONNREFUSED') || errorMsg.includes('502') || errorMsg.includes('503')) {
        if (failureCount < 3) {
          console.warn(`[useApiPaginatedQuery] Network error, retrying (attempt ${failureCount + 1}/3):`, errorMsg);
          return true;
        }
        return false;
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

