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

// Portfolio Watchlist
export function useWatchlist(options = {}) {
  return useQuery({
    queryKey: ['portfolio', 'watchlist'],
    queryFn: () => fetchData(`${API_BASE}/api/portfolio/watchlist`),
    staleTime: 30000,
    retry: 3,
    ...options
  })
}

// Portfolio Activity
export function usePortfolioActivity(options = {}) {
  return useQuery({
    queryKey: ['portfolio', 'activity'],
    queryFn: () => fetchData(`${API_BASE}/api/portfolio/activity`),
    staleTime: 30000,
    retry: 3,
    ...options
  })
}

// User Profile
export function useUserProfile(options = {}) {
  return useQuery({
    queryKey: ['user', 'profile'],
    queryFn: () => fetchData(`${API_BASE}/api/user/profile`),
    staleTime: 5 * 60 * 1000, // 5 minutes for user profile
    retry: 3,
    ...options
  })
}