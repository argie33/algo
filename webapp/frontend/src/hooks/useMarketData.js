import { useQuery } from '@tanstack/react-query'
import { extractResponseData } from '../utils/dataFormatHelper'

const API_BASE = window.__CONFIG__?.API?.BASE_URL || process.env.VITE_API_URL || 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'

// Generic fetch function for API calls
async function fetchData(url) {
  const response = await fetch(url)
  
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  }
  
  const contentType = response.headers.get('content-type')
  const text = await response.text()
  
  // Detect HTML response (routing issue)
  if (text.includes('<!DOCTYPE html>') || contentType?.includes('text/html')) {
    throw new Error('API routing misconfiguration - receiving HTML instead of JSON')
  }
  
  try {
    const result = JSON.parse(text)
    const normalized = extractResponseData(result)
    
    if (normalized.success) {
      return normalized.data
    } else {
      throw new Error(normalized.error || 'API request failed')
    }
  } catch (parseError) {
    throw new Error(`Invalid JSON response: ${parseError.message}`)
  }
}

// Market Overview
export function useMarketOverview(options = {}) {
  return useQuery({
    queryKey: ['market', 'overview'],
    queryFn: () => fetchData(`${API_BASE}/api/market/overview`),
    staleTime: 30000,
    retry: 3,
    ...options
  })
}

// Market Sentiment
export function useMarketSentiment(options = {}) {
  return useQuery({
    queryKey: ['market', 'sentiment'],
    queryFn: () => fetchData(`${API_BASE}/api/market/sentiment`),
    staleTime: 30000,
    retry: 3,
    ...options
  })
}

// Sector Performance
export function useSectorPerformance(options = {}) {
  return useQuery({
    queryKey: ['market', 'sectors', 'performance'],
    queryFn: () => fetchData(`${API_BASE}/api/market/sectors/performance`),
    staleTime: 30000,
    retry: 3,
    ...options
  })
}

// Economic Indicators
export function useEconomicIndicators(limit = 6, options = {}) {
  return useQuery({
    queryKey: ['economic', 'indicators', limit],
    queryFn: () => fetchData(`${API_BASE}/api/economic/indicators?limit=${limit}`),
    staleTime: 60000, // 1 minute for economic data
    retry: 3,
    ...options
  })
}

// Stock Prices
export function useStockPrices(symbol, options = {}) {
  return useQuery({
    queryKey: ['market', 'prices', symbol],
    queryFn: () => fetchData(`${API_BASE}/api/market/prices/${symbol}`),
    enabled: !!symbol,
    staleTime: 10000, // 10 seconds for stock prices
    retry: 3,
    ...options
  })
}

// Stock Metrics
export function useStockMetrics(symbol, options = {}) {
  return useQuery({
    queryKey: ['market', 'metrics', symbol],
    queryFn: () => fetchData(`${API_BASE}/api/market/metrics/${symbol}`),
    enabled: !!symbol,
    staleTime: 30000,
    retry: 3,
    ...options
  })
}

// Stock Scores
export function useStockScores(limit = 10, sortBy = 'composite_score', sortOrder = 'desc', options = {}) {
  return useQuery({
    queryKey: ['scores', limit, sortBy, sortOrder],
    queryFn: () => fetchData(`${API_BASE}/api/scores/?limit=${limit}&sortBy=${sortBy}&sortOrder=${sortOrder}`),
    staleTime: 60000, // 1 minute for scores
    retry: 3,
    ...options
  })
}