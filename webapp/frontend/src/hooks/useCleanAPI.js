/**
 * CLEAN React Query Hooks
 *
 * These hooks use the normalized apiClient, so data is ALWAYS in this format:
 * {
 *   items: array,           // For lists
 *   pagination: object,     // For paginated lists
 *   data: any,              // For single objects
 *   isLoading: boolean,
 *   error: Error | null,
 *   isSuccess: boolean
 * }
 *
 * No more .data?.data nonsense. Just use data.items or data.data directly.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../services/apiClient';

/**
 * Hook for getting a list of stocks
 * Usage: const { data, isLoading, error } = useStocks({ limit: 50, offset: 0 });
 * Returns: { items: [...], pagination: {...} }
 */
export function useStocks(params = {}) {
  return useQuery({
    queryKey: ['stocks', params],
    queryFn: async () => {
      const response = await apiClient.get('/api/stocks', params);
      return {
        items: response.items || [],
        pagination: response.pagination || {},
        isSuccess: response.success
      };
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
    gcTime: 10 * 60 * 1000, // 10 minutes (was cacheTime)
  });
}

/**
 * Hook for searching stocks
 * Usage: const { data } = useStockSearch('AAPL');
 * Returns: { items: [...], pagination: {...} }
 */
export function useStockSearch(query, params = {}) {
  return useQuery({
    queryKey: ['stocks-search', query, params],
    queryFn: async () => {
      const response = await apiClient.get('/api/stocks/search', {
        q: query,
        ...params
      });
      return {
        items: response.items || [],
        pagination: response.pagination || {},
        isSuccess: response.success
      };
    },
    enabled: !!query,
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });
}

/**
 * Hook for getting stock scores
 * Usage: const { data } = useStockScores({ limit: 10 });
 * Returns: { items: [{symbol, composite_score, ...}], pagination: {...} }
 */
export function useStockScores(params = {}) {
  return useQuery({
    queryKey: ['stock-scores', params],
    queryFn: async () => {
      const response = await apiClient.get('/api/scores/stockscores', params);
      return {
        items: response.items || [],
        pagination: response.pagination || {},
        isSuccess: response.success
      };
    },
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });
}

/**
 * Hook for getting market overview
 * Usage: const { data } = useMarketOverview();
 * Returns: { overview, breadth, indices, ... }
 */
export function useMarketOverview() {
  return useQuery({
    queryKey: ['market-overview'],
    queryFn: async () => {
      const response = await apiClient.get('/api/market/overview');
      return response.data || response;
    },
    staleTime: 1 * 60 * 1000, // 1 minute
    gcTime: 5 * 60 * 1000,
  });
}

/**
 * Hook for getting market breadth
 * Usage: const { data } = useMarketBreadth();
 * Returns: { total_stocks, advancing, declining, ... }
 */
export function useMarketBreadth() {
  return useQuery({
    queryKey: ['market-breadth'],
    queryFn: async () => {
      const response = await apiClient.get('/api/market/breadth');
      return response.data || response;
    },
    staleTime: 1 * 60 * 1000,
    gcTime: 5 * 60 * 1000,
  });
}

/**
 * Hook for getting sector data
 * Usage: const { data } = useSectors();
 * Returns: { items: [...sectors], pagination: {...} }
 */
export function useSectors(params = {}) {
  return useQuery({
    queryKey: ['sectors', params],
    queryFn: async () => {
      const response = await apiClient.get('/api/sectors', params);
      return {
        items: response.items || [],
        pagination: response.pagination || {},
        isSuccess: response.success
      };
    },
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000,
  });
}

/**
 * Hook for creating any resource (generic mutation)
 * Usage:
 *   const mutation = useCreateResource('/api/endpoint');
 *   mutation.mutate({ field: 'value' });
 */
export function useCreateResource(endpoint) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data) => {
      const response = await apiClient.post(endpoint, data);
      return response.data || response;
    },
    onSuccess: () => {
      // Invalidate related queries to refetch
      queryClient.invalidateQueries();
    }
  });
}

/**
 * Hook for updating any resource (generic mutation)
 * Usage:
 *   const mutation = useUpdateResource('/api/endpoint/:id');
 *   mutation.mutate({ id: '123', field: 'newValue' });
 */
export function useUpdateResource(endpoint) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data) => {
      const response = await apiClient.put(endpoint, data);
      return response.data || response;
    },
    onSuccess: () => {
      queryClient.invalidateQueries();
    }
  });
}

/**
 * Hook for deleting any resource (generic mutation)
 * Usage:
 *   const mutation = useDeleteResource('/api/endpoint/:id');
 *   mutation.mutate({ id: '123' });
 */
export function useDeleteResource(endpoint) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      const response = await apiClient.delete(endpoint);
      return response;
    },
    onSuccess: () => {
      queryClient.invalidateQueries();
    }
  });
}

export default {
  useStocks,
  useStockSearch,
  useStockScores,
  useMarketOverview,
  useMarketBreadth,
  useSectors,
  useCreateResource,
  useUpdateResource,
  useDeleteResource
};
