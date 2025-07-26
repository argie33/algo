/**
 * DEPRECATED: useSimpleFetch Migration Guide
 * 
 * This custom hook has been replaced with standard React Query patterns.
 * Please use the appropriate hooks from:
 * - useMarketData.js - for market-related data
 * - usePortfolioData.js - for portfolio-related data  
 * - useTradingData.js - for trading-related data
 * - useApiData.js - for generic API calls
 * 
 * Migration examples:
 * 
 * Before:
 * const { data, loading, error } = useSimpleFetch('/api/market/overview')
 * 
 * After:
 * import { useMarketOverview } from '../hooks/useMarketData'
 * const { data, isLoading, error } = useMarketOverview()
 */

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

// Compatibility wrapper - converts useSimpleFetch to React Query
export function useSimpleFetch(urlOrOptions, options = {}) {
  console.warn('⚠️ DEPRECATED: useSimpleFetch is deprecated. Please migrate to React Query hooks from useMarketData.js, usePortfolioData.js, useTradingData.js, or useApiData.js')
  
  // Handle both React Query style objects and simple URL strings
  let url, queryFn, actualOptions
  
  if (typeof urlOrOptions === 'string') {
    url = urlOrOptions
    queryFn = () => fetchData(url)
    actualOptions = options
  } else if (typeof urlOrOptions === 'object' && urlOrOptions !== null) {
    if (urlOrOptions.queryFn && typeof urlOrOptions.queryFn === 'function') {
      url = JSON.stringify(urlOrOptions.queryKey || 'query')
      queryFn = urlOrOptions.queryFn
      actualOptions = { ...options, ...urlOrOptions }
    } else {
      console.error('useSimpleFetch: Invalid object parameter. Missing queryFn function.', urlOrOptions)
      url = null
      queryFn = null
      actualOptions = { ...options, enabled: false }
    }
  } else {
    console.error('useSimpleFetch: Invalid first parameter. Expected string URL or options object with queryFn.', urlOrOptions)
    url = null
    queryFn = null
    actualOptions = { ...options, enabled: false }
  }

  const {
    enabled = true,
    retry = 3,
    staleTime = 30000,
    refetchOnWindowFocus = false,
    onError
  } = actualOptions

  // Convert to React Query using the new pattern
  const queryKey = url ? ['legacy', url] : ['legacy', 'disabled']
  
  const query = useQuery({
    queryKey,
    queryFn,
    enabled: enabled && !!queryFn,
    retry,
    staleTime,
    refetchOnWindowFocus,
    onError
  })

  // Return in the old format for compatibility
  return {
    data: query.data,
    loading: query.isLoading,
    error: query.error?.message,
    refetch: query.refetch,
    isLoading: query.isLoading,
    isError: query.isError,
    isSuccess: query.isSuccess
  }
}

// Simple query client replacement - now uses React Query
export class SimpleQueryClient {
  constructor(options = {}) {
    console.warn('⚠️ DEPRECATED: SimpleQueryClient is deprecated. Use QueryClient from @tanstack/react-query directly.')
    this.options = {
      staleTime: 30000,
      cacheTime: 10 * 60 * 1000,
      retry: 3,
      ...options.defaultOptions?.queries
    }
  }

  invalidateQueries() {
    console.warn('⚠️ DEPRECATED: Use queryClient.invalidateQueries() from React Query')
  }

  setQueryData(key, data) {
    console.warn('⚠️ DEPRECATED: Use queryClient.setQueryData() from React Query')
  }

  getQueryData(key) {
    console.warn('⚠️ DEPRECATED: Use queryClient.getQueryData() from React Query')
    return undefined
  }
}

// Provider replacement - no longer needed with React Query
export function SimpleQueryProvider({ children }) {
  console.warn('⚠️ DEPRECATED: SimpleQueryProvider is deprecated. Use QueryClientProvider from @tanstack/react-query')
  return children
}

export default useSimpleFetch