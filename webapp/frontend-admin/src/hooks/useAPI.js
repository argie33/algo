/**
 * Custom React Query Hooks with Proper API Response Handling
 *
 * These hooks handle the data extraction properly so you never have to
 * worry about .data.data or response structure inconsistencies
 */

import { useQuery, useMutation } from '@tanstack/react-query';
import api from '../services/api';

/**
 * Hook for fetching sectors data
 *
 * Usage:
 * const { data, isLoading, error } = useSectors();
 * // data.sectors = array of sectors
 * // data.industries = array of industries
 */
export const useSectors = (options = {}) => {
  return useQuery({
    queryKey: ['sectors'],
    queryFn: async () => {
      const response = await api.get('/api/sectors/sectors?limit=20');
      // API returns: { items: [...sectors], pagination: {...}, success: true }
      return {
        sectors: response.data?.items || [],
        rankings: response.data?.items || [], // Same data, different naming convention
        success: response.data?.success ?? true,
      };
    },
    staleTime: 60000,
    retry: 1,
    ...options,
  });
};

/**
 * Hook for fetching industries data
 */
export const useIndustries = (options = {}) => {
  return useQuery({
    queryKey: ['industries'],
    queryFn: async () => {
      const response = await api.get('/api/industries/industries');
      // API returns: { items: [...industries], pagination: {...}, success: true }
      return {
        items: response.data?.items || [],
        success: response.data?.success ?? true,
      };
    },
    staleTime: 60000,
    retry: 1,
    ...options,
  });
};

/**
 * Hook for fetching trading signals
 *
 * Usage:
 * const { data, isLoading } = useSignals({ timeframe: 'daily', limit: 5000 });
 * // data = { items: array of signals, pagination: {...} }
 */
export const useSignals = (params = {}, options = {}) => {
  const { timeframe = 'daily', limit = 100, page = 1 } = params;

  return useQuery({
    queryKey: ['signals', { timeframe, limit, page }],
    queryFn: async () => {
      const response = await api.get('/api/signals/list', {
        params: { timeframe, limit, page },
      });
      // API returns: { items: [...], pagination: {...}, success: true }
      return {
        items: response.data?.items || [],
        pagination: response.data?.pagination || {},
        success: response.data?.success ?? true,
      };
    },
    staleTime: 30000,
    retry: 1,
    ...options,
  });
};

/**
 * Hook for fetching stock scores
 *
 * Usage:
 * const { data, isLoading } = useStockScores({ symbol: 'AAPL' });
 * // data = { items: array of scores, pagination: {...} }
 */
export const useStockScores = (params = {}, options = {}) => {
  const { symbol, limit = 10, offset = 0, search, sortBy, sortOrder } = params;

  return useQuery({
    queryKey: ['scores', { symbol, limit, offset, search, sortBy, sortOrder }],
    queryFn: async () => {
      const response = await api.get('/api/scores/stockscores', {
        params: { symbol, limit, offset, search, sortBy, sortOrder },
      });
      // API returns: { items: [...], pagination: {...}, success: true }
      return {
        items: response.data?.items || [],
        pagination: response.data?.pagination || {},
        success: response.data?.success ?? true,
      };
    },
    staleTime: 60000,
    retry: 1,
    ...options,
  });
};

/**
 * Hook for portfolio optimization
 *
 * Usage:
 * const { data, isLoading } = usePortfolioOptimization();
 * // data = { analysis, efficientFrontier, recommendations, ... }
 */
export const usePortfolioOptimization = (options = {}) => {
  return useQuery({
    queryKey: ['portfolio-optimization'],
    queryFn: async () => {
      const response = await api.get('/api/optimization/analysis');
      // API returns: { data: {...}, success: true } or { analysis, efficientFrontier, ... }
      const data = response.data?.data || response.data;
      return {
        ...data,
        success: response.data?.success ?? true,
      };
    },
    staleTime: 60000,
    retry: 1,
    ...options,
  });
};

/**
 * Hook for market sentiment data
 *
 * Usage:
 * const { data, isLoading } = useMarketSentiment();
 * // data = { fear_greed_history, naaim_history, aaii_history }
 */
export const useMarketSentiment = (options = {}) => {
  return useQuery({
    queryKey: ['market-sentiment'],
    queryFn: async () => {
      const response = await api.get('/api/sentiment/history');
      // API returns: { data: {...}, success: true }
      const data = response.data?.data || response.data;
      return {
        ...data,
        success: response.data?.success ?? true,
      };
    },
    staleTime: 300000, // 5 minutes
    retry: 1,
    ...options,
  });
};

/**
 * Hook for price history
 *
 * Usage:
 * const { data, isLoading } = usePriceHistory('AAPL', { days: 365 });
 * // data = { items: array of price data }
 */
export const usePriceHistory = (symbol, params = {}, options = {}) => {
  const { days = 365, interval = 'daily', limit = 100 } = params;

  return useQuery({
    queryKey: ['price-history', { symbol, days, interval, limit }],
    queryFn: async () => {
      const response = await api.get(`/api/price/history/${symbol}`, {
        params: { days, interval, limit },
      });
      // API returns: { data: {...}, success: true } or { items: [...] }
      const data = response.data?.data || response.data;
      return {
        items: data?.items || data || [],
        success: response.data?.success ?? true,
      };
    },
    staleTime: 60000,
    enabled: !!symbol,
    retry: 1,
    ...options,
  });
};

/**
 * Hook for technical indicators - DEPRECATED
 * Removed: /api/technical endpoint no longer exists
 */
// export const useTechnicalData = (symbol, params = {}, options = {}) => { ... }

/**
 * Hook for sector trend data
 *
 * Usage:
 * const { data, isLoading } = useSectorTrend('Technology');
 * // data = { trend data for the sector }
 */
export const useSectorTrend = (sector, options = {}) => {
  return useQuery({
    queryKey: ['sector-trend', sector],
    queryFn: async () => {
      const response = await api.get(`/api/sectors/trend/sector/${encodeURIComponent(sector)}`);
      // API returns: { data: {...}, success: true } or direct data
      const data = response.data?.data || response.data;
      return {
        ...data,
        success: response.data?.success ?? true,
      };
    },
    staleTime: 60000,
    enabled: !!sector,
    retry: 1,
    ...options,
  });
};

/**
 * Hook for generic API calls with custom data extraction
 *
 * Usage:
 * const { data } = useAPIQuery(
 *   '/api/endpoint',
 *   { param1: 'value' },
 *   ['data', 'items'], // Try these keys in order
 *   60000  // stale time
 * );
 */
export const useAPIQuery = (
  endpoint,
  params = {},
  dataKeys = ['data', 'items'],
  staleTime = 60000,
  options = {}
) => {
  return useQuery({
    queryKey: [endpoint, params],
    queryFn: async () => {
      const response = await api.get(endpoint, { params });
      // Handle multiple response formats
      let data = response.data;

      // Try extracting from nested data wrapper
      if (response.data?.data) {
        data = response.data.data;
      } else if (response.data?.items) {
        data = { items: response.data.items, pagination: response.data.pagination };
      }

      return {
        data,
        raw: response.data,
        items: response.data?.items,
        pagination: response.data?.pagination,
        success: response.data?.success ?? true,
        timestamp: response.data?.timestamp,
      };
    },
    staleTime,
    retry: 1,
    ...options,
  });
};

/**
 * Hook for API mutations (POST, PUT, DELETE)
 *
 * Usage:
 * const mutation = useAPIMutation('/api/endpoint', 'POST');
 * mutation.mutate({ data: 'value' });
 */
export const useAPIMutation = (endpoint, method = 'POST', options = {}) => {
  return useMutation({
    mutationFn: async (data) => {
      const response = await api({
        url: endpoint,
        method,
        data,
      });
      // Handle multiple response formats
      const returnData = response.data?.data || response.data;
      return {
        data: returnData,
        success: response.data?.success ?? true,
        message: response.data?.message,
      };
    },
    ...options,
  });
};

export default {
  useSectors,
  useIndustries,
  useSignals,
  useStockScores,
  usePortfolioOptimization,
  useMarketSentiment,
  usePriceHistory,
  useSectorTrend,
  useAPIQuery,
  useAPIMutation,
};
