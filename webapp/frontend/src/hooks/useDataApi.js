/**
 * Domain-specific API hooks
 * Decouples pages from API structure, enables easy endpoint swapping
 * Each hook encapsulates a logical data fetch with error handling + normalization
 */

import { useApiQuery, useApiPaginatedQuery } from './useApiQuery';
import { api } from '../services/api';

/**
 * Get sectors list with rankings and performance
 */
export const useSectors = (params = {}) => {
  const { limit = 20, page = 1 } = params;
  return useApiPaginatedQuery(
    ['sectors', limit, page],
    () => api.get('/api/sectors', { params: { limit, page } })
  );
};

/**
 * Get stock scores with filtering
 */
export const useStockScores = (params = {}) => {
  const { limit = 10, page = 1, search = '', sortBy = '', sortOrder = 'desc' } = params;
  return useApiPaginatedQuery(
    ['scores', { limit, page, search, sortBy, sortOrder }],
    () => api.get('/api/scores/stockscores', { params: { limit, page, search, sortBy, sortOrder } })
  );
};

/**
 * Get trading signals with timeframe filtering
 */
export const useSignals = (params = {}) => {
  const { timeframe = 'daily', limit = 100, page = 1 } = params;
  return useApiPaginatedQuery(
    ['signals', { timeframe, limit, page }],
    () => api.get('/api/signals/stocks', { params: { timeframe, limit, page } })
  );
};

/**
 * Get sentiment indices (NAAIM, Fear/Greed, AAII, etc.)
 */
export const useMarketSentiment = () => {
  return useApiQuery(
    ['sentiment'],
    () => api.get('/api/sentiment/data')
  );
};

/**
 * Get price history for a symbol
 */
export const usePriceHistory = (symbol, params = {}) => {
  const { days = 365, interval = 'daily' } = params;
  return useApiQuery(
    ['priceHistory', symbol, days, interval],
    () => api.get(`/api/prices/history/${symbol}`, { params: { days, interval } }),
    { enabled: !!symbol }
  );
};

/**
 * Get industries list
 */
export const useIndustries = (params = {}) => {
  const { limit = 500 } = params;
  return useApiQuery(
    ['industries', limit],
    () => api.get('/api/industries', { params: { limit } })
  );
};

/**
 * Get economic indicators
 */
export const useEconomicData = (params = {}) => {
  return useApiQuery(
    ['economic', params],
    () => api.get('/api/economic', { params })
  );
};

/**
 * Get commodities data
 */
export const useCommodities = (params = {}) => {
  const { limit = 50 } = params;
  return useApiQuery(
    ['commodities', limit],
    () => api.get('/api/commodities/prices', { params: { limit } })
  );
};

/**
 * Get health status of all services
 */
export const useServiceHealth = () => {
  return useApiQuery(
    ['health'],
    () => api.get('/api/health'),
    { staleTime: 60000 } // 60s
  );
};

export default {
  useSectors,
  useStockScores,
  useSignals,
  useMarketSentiment,
  usePriceHistory,
  useIndustries,
  useEconomicData,
  useCommodities,
  useServiceHealth,
};
