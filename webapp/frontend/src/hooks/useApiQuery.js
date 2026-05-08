import { useQuery } from '@tanstack/react-query';
import { extractData, extractPaginatedData } from '../utils/responseNormalizer';

/**
 * React Query wrapper with standardized error/loading/data handling
 * Reduces boilerplate and ensures consistency across pages
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
    retry = 2,
    onSuccess,
    onError,
    enabled = true,
    ...restOptions
  } = {}
) => {
  const { data: rawData, isLoading, error, ...rest } = useQuery({
    queryKey: Array.isArray(queryKey) ? queryKey : [queryKey],
    queryFn: async () => {
      const response = await queryFn();
      return extractData(response);
    },
    staleTime,
    gcTime,
    retry: (failureCount, error) => {
      // Don't retry on 404s
      if (error?.response?.status === 404) return false;
      return failureCount < retry;
    },
    enabled,
    onSuccess,
    onError: (error) => {
      if (onError) onError(error);
    },
    ...restOptions,
  });

  return {
    data: rawData,
    loading: isLoading,
    error: error?.message || null,
    ...rest,
  };
};

/**
 * React Query wrapper for paginated responses
 * Automatically handles pagination metadata
 *
 * Usage:
 *   const { items, pagination, loading, error } = useApiPaginatedQuery(
 *     ['sectors', page, limit],
 *     () => api.get('/api/sectors', { params: { page, limit } })
 *   );
 */
export const useApiPaginatedQuery = (
  queryKey,
  queryFn,
  options = {}
) => {
  const { data: rawData, isLoading, error, ...rest } = useQuery({
    queryKey: Array.isArray(queryKey) ? queryKey : [queryKey],
    queryFn: async () => {
      const response = await queryFn();
      return extractPaginatedData(response);
    },
    staleTime: 30000,
    gcTime: 10 * 60 * 1000,
    retry: 2,
    ...options,
  });

  return {
    items: rawData?.items || [],
    pagination: rawData?.pagination || {},
    loading: isLoading,
    error: error?.message || null,
    ...rest,
  };
};

export default { useApiQuery, useApiPaginatedQuery };
