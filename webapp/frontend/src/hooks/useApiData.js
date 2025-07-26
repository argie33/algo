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

// Generic API hook for custom endpoints
export function useApiData(url, queryKey, options = {}) {
  return useQuery({
    queryKey: Array.isArray(queryKey) ? queryKey : [queryKey],
    queryFn: () => fetchData(url),
    staleTime: 30000,
    retry: 3,
    ...options
  })
}

// Service Health
export function useServiceHealth(options = {}) {
  return useQuery({
    queryKey: ['service', 'health'],
    queryFn: () => fetchData(`${API_BASE}/api/health`),
    staleTime: 10000, // 10 seconds for health checks
    retry: 3,
    refetchInterval: 30000, // Refetch every 30 seconds
    ...options
  })
}

// Financial Data endpoints
export function useFinancialData(endpoint, options = {}) {
  return useQuery({
    queryKey: ['financial', endpoint],
    queryFn: () => fetchData(`${API_BASE}/api/financial/${endpoint}`),
    staleTime: 60000, // 1 minute for financial data
    retry: 3,
    ...options
  })
}

// Stock Detail Data
export function useStockDetail(symbol, options = {}) {
  return useQuery({
    queryKey: ['stock', 'detail', symbol],
    queryFn: () => fetchData(`${API_BASE}/api/stocks/${symbol}`),
    enabled: !!symbol,
    staleTime: 30000,
    retry: 3,
    ...options
  })
}

// Earnings Calendar
export function useEarningsCalendar(options = {}) {
  return useQuery({
    queryKey: ['earnings', 'calendar'],
    queryFn: () => fetchData(`${API_BASE}/api/earnings/calendar`),
    staleTime: 5 * 60 * 1000, // 5 minutes for earnings
    retry: 3,
    ...options
  })
}

// Sentiment Analysis
export function useSentimentAnalysis(options = {}) {
  return useQuery({
    queryKey: ['sentiment', 'analysis'],
    queryFn: () => fetchData(`${API_BASE}/api/sentiment/analysis`),
    staleTime: 2 * 60 * 1000, // 2 minutes for sentiment
    retry: 3,
    ...options
  })
}

// Analyst Insights
export function useAnalystInsights(options = {}) {
  return useQuery({
    queryKey: ['analyst', 'insights'],
    queryFn: () => fetchData(`${API_BASE}/api/analyst/insights`),
    staleTime: 5 * 60 * 1000, // 5 minutes for analyst insights
    retry: 3,
    ...options
  })
}

// Commodities Data
export function useCommoditiesData(options = {}) {
  return useQuery({
    queryKey: ['commodities'],
    queryFn: () => fetchData(`${API_BASE}/api/commodities`),
    staleTime: 2 * 60 * 1000, // 2 minutes for commodities
    retry: 3,
    ...options
  })
}

// Backtest Data
export function useBacktestData(params, options = {}) {
  const queryString = params ? `?${new URLSearchParams(params).toString()}` : ''
  return useQuery({
    queryKey: ['backtest', params],
    queryFn: () => fetchData(`${API_BASE}/api/backtest${queryString}`),
    enabled: !!params,
    staleTime: 5 * 60 * 1000, // 5 minutes for backtest results
    retry: 3,
    ...options
  })
}