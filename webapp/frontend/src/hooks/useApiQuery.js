import { useQuery } from '@tanstack/react-query';
import { extractData, extractPaginatedData } from '../utils/responseNormalizer';

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
    retry = 5,
    enabled = true,
    ...restOptions
  } = {}
) => {
  const { data: rawData, isLoading, error, ...rest } = useQuery({
    queryKey: Array.isArray(queryKey) ? queryKey : [queryKey],
    queryFn: async () => {
      try {
        const response = await queryFn();
        return extractData(response);
      } catch (err) {
        console.warn('[useApiQuery] Query failed:', err.message);
        throw err;
      }
    },
    staleTime,
    gcTime,
    retry: retry === false ? false : (failureCount, err) => {
      const status = err?.response?.status ?? err?.status;
      if (status === 401 || status === 403 || status === 404) return false;
      // Retry on 5xx errors up to specified retry count (default 5)
      // This handles transient failures during deployments/RDS restarts
      return failureCount < retry;
    },
    retryDelay: (attemptIndex) => Math.min(1000 * Math.pow(2, attemptIndex), 60000),
    enabled,
    ...restOptions,
  });

  const enrichedError = error ? {
    message: error?.message || 'Unknown error',
    status: error?.response?.status,
    code: error?.code,
    url: error?.config?.url,
    responseData: error?.response?.data,
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
    retry = 5,
    enabled = true,
    ...restOptions
  } = {}
) => {
  const { data: rawData, isLoading, error, ...rest } = useQuery({
    queryKey: Array.isArray(queryKey) ? queryKey : [queryKey],
    queryFn: async () => {
      try {
        const response = await queryFn();
        return extractPaginatedData(response);
      } catch (err) {
        console.warn('[useApiPaginatedQuery] Query failed:', err.message);
        throw err;
      }
    },
    staleTime,
    gcTime,
    retry: retry === false ? false : (failureCount, err) => {
      const status = err?.response?.status ?? err?.status;
      if (status === 401 || status === 403 || status === 404) return false;
      // Retry on 5xx errors up to specified retry count (default 5)
      // This handles transient failures during deployments/RDS restarts
      return failureCount < retry;
    },
    retryDelay: (attemptIndex) => Math.min(1000 * Math.pow(2, attemptIndex), 60000),
    enabled,
    ...restOptions,
  });

  const enrichedError = error ? {
    message: error?.message || 'Unknown error',
    status: error?.response?.status,
    code: error?.code,
    url: error?.config?.url,
    responseData: error?.response?.data,
  } : null;

  return {
    items: (rawData && Array.isArray(rawData.items)) ? rawData.items : [],
    pagination: (rawData && rawData.pagination) ? rawData.pagination : {
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

