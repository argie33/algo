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

// Trading Signals
export function useTradingSignals(limit = 10, options = {}) {
  return useQuery({
    queryKey: ['trading', 'signals', 'daily', limit],
    queryFn: () => fetchData(`${API_BASE}/api/trading/signals/daily?limit=${limit}`),
    staleTime: 60000, // 1 minute for trading signals
    retry: 3,
    ...options
  })
}

// Calendar Events
export function useCalendarEvents(options = {}) {
  return useQuery({
    queryKey: ['calendar', 'events'],
    queryFn: () => fetchData(`${API_BASE}/api/calendar/events`),
    staleTime: 5 * 60 * 1000, // 5 minutes for calendar events
    retry: 3,
    ...options
  })
}

// News
export function useNews(limit = 5, options = {}) {
  return useQuery({
    queryKey: ['news', limit],
    queryFn: () => fetchData(`${API_BASE}/api/news?limit=${limit}`),
    staleTime: 2 * 60 * 1000, // 2 minutes for news
    retry: 3,
    ...options
  })
}