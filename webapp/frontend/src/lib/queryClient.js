import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      gcTime: 10 * 60 * 1000,   // 10 minutes
      retry: (failureCount, error) => {
        // Don't retry on client errors (4xx) except for 408 (timeout) and 429 (rate limit)
        if (error.status >= 400 && error.status < 500 && ![408, 429].includes(error.status)) {
          return false
        }
        return failureCount < 3
      },
      refetchOnWindowFocus: false,
      // Add network error handling
      networkMode: 'online',
      // Reduce memory usage by limiting concurrent queries
      maxPages: 3
    },
    mutations: {
      // Add retry for mutations on network errors
      retry: (failureCount, error) => {
        if (error.status >= 500 || error.name === 'NetworkError') {
          return failureCount < 2
        }
        return false
      }
    }
  }
})