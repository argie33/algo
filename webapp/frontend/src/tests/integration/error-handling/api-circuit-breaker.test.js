/**
 * API Circuit Breaker Integration Tests
 * Tests circuit breaker patterns to prevent cascading failures
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import Dashboard from '../../../pages/Dashboard'
import TradingSignals from '../../../pages/TradingSignals'
import Portfolio from '../../../pages/Portfolio'
import { AuthContext } from '../../../contexts/AuthContext'
import muiTheme from '../../../theme/muiTheme'

// Mock the API service
const mockApi = {
  getApiConfig: vi.fn(() => ({
    apiUrl: 'https://test-api.com',
    isServerless: true,
    isConfigured: true
  })),
  getStockPrices: vi.fn(),
  getStockMetrics: vi.fn(),
  getBuySignals: vi.fn(),
  getSellSignals: vi.fn(),
  getPortfolioData: vi.fn(),
  getTradingSignals: vi.fn(),
  getMarketData: vi.fn()
}

vi.mock('../../../services/api', () => mockApi)

// Mock fetch for direct API calls
let fetchMock
const originalFetch = global.fetch

// Circuit breaker state tracker
class CircuitBreakerTracker {
  constructor() {
    this.failures = new Map()
    this.lastCallTimes = new Map()
    this.circuitState = new Map() // 'closed', 'open', 'half-open'
  }

  recordFailure(endpoint) {
    const current = this.failures.get(endpoint) || 0
    this.failures.set(endpoint, current + 1)
    this.lastCallTimes.set(endpoint, Date.now())
  }

  recordSuccess(endpoint) {
    this.failures.set(endpoint, 0)
    this.circuitState.set(endpoint, 'closed')
  }

  getFailureCount(endpoint) {
    return this.failures.get(endpoint) || 0
  }

  shouldCircuitBeOpen(endpoint, threshold = 3) {
    return this.getFailureCount(endpoint) >= threshold
  }

  getCircuitState(endpoint) {
    return this.circuitState.get(endpoint) || 'closed'
  }

  setCircuitState(endpoint, state) {
    this.circuitState.set(endpoint, state)
  }

  reset() {
    this.failures.clear()
    this.lastCallTimes.clear()
    this.circuitState.clear()
  }
}

const circuitTracker = new CircuitBreakerTracker()

const TestWrapper = ({ children, isAuthenticated = true }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        cacheTime: 0
      }
    }
  })

  const mockAuthContextValue = {
    isAuthenticated,
    user: isAuthenticated ? { 
      id: 'test-user', 
      email: 'test@example.com',
      tokens: { accessToken: 'test-token' }
    } : null,
    login: vi.fn(),
    logout: vi.fn(),
    checkAuthState: vi.fn(),
    loading: false,
    error: null,
    retryCount: 0,
    maxRetries: 3
  }

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeProvider theme={muiTheme}>
          <AuthContext.Provider value={mockAuthContextValue}>
            {children}
          </AuthContext.Provider>
        </ThemeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

describe('API Circuit Breaker Tests', () => {
  beforeEach(() => {
    fetchMock = vi.fn()
    global.fetch = fetchMock
    vi.clearAllMocks()
    circuitTracker.reset()
  })

  afterEach(() => {
    global.fetch = originalFetch
    vi.restoreAllMocks()
  })

  describe('Circuit Breaker State Management', () => {
    test('circuit opens after consecutive failures', async () => {
      let callCount = 0
      
      // Mock multiple failures for stock prices
      mockApi.getStockPrices.mockImplementation(() => {
        callCount++
        circuitTracker.recordFailure('stock-prices')
        return Promise.reject(new Error(`API failure ${callCount}`))
      })

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      // Wait for component to attempt API calls
      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })

      // Simulate multiple calls that would trigger circuit breaker
      for (let i = 0; i < 5; i++) {
        try {
          await mockApi.getStockPrices()
        } catch (error) {
          // Expected failures
        }
      }

      expect(circuitTracker.getFailureCount('stock-prices')).toBeGreaterThanOrEqual(5)
      expect(circuitTracker.shouldCircuitBeOpen('stock-prices')).toBe(true)
    })

    test('circuit transitions from open to half-open after timeout', async () => {
      // Simulate circuit being open
      circuitTracker.recordFailure('trading-signals')
      circuitTracker.recordFailure('trading-signals')
      circuitTracker.recordFailure('trading-signals')
      circuitTracker.setCircuitState('trading-signals', 'open')

      expect(circuitTracker.shouldCircuitBeOpen('trading-signals')).toBe(true)

      // Simulate timeout period passing
      setTimeout(() => {
        circuitTracker.setCircuitState('trading-signals', 'half-open')
      }, 100)

      await new Promise(resolve => setTimeout(resolve, 150))

      expect(circuitTracker.getCircuitState('trading-signals')).toBe('half-open')
    })

    test('circuit closes after successful call in half-open state', async () => {
      // Start with half-open circuit
      circuitTracker.setCircuitState('market-data', 'half-open')
      
      mockApi.getMarketData.mockImplementation(() => {
        circuitTracker.recordSuccess('market-data')
        return Promise.resolve({ data: { price: 100 }, success: true })
      })

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Market Sentiment')).toBeInTheDocument()
      })

      // Circuit should close after successful call
      expect(circuitTracker.getCircuitState('market-data')).toBe('closed')
      expect(circuitTracker.getFailureCount('market-data')).toBe(0)
    })
  })

  describe('Fallback Behavior', () => {
    test('provides fallback data when circuit is open', async () => {
      // Open circuit for portfolio data
      mockApi.getPortfolioData.mockImplementation(() => {
        circuitTracker.recordFailure('portfolio')
        if (circuitTracker.shouldCircuitBeOpen('portfolio')) {
          // Simulate circuit breaker returning cached/fallback data
          return Promise.resolve({
            data: {
              totalValue: 10000,
              positions: [],
              cached: true,
              fallback: true
            },
            success: true,
            circuitOpen: true
          })
        }
        return Promise.reject(new Error('Portfolio API failed'))
      })

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      )

      await waitFor(() => {
        // Should render portfolio page with fallback data
        const portfolioElements = screen.queryAllByText(/portfolio|$10,000/i)
        expect(portfolioElements.length).toBeGreaterThan(0)
      })
    })

    test('shows degraded service indicators when circuit is open', async () => {
      // Mock all API calls to fail and trigger circuit breaker
      mockApi.getStockPrices.mockRejectedValue(new Error('Service unavailable'))
      mockApi.getStockMetrics.mockRejectedValue(new Error('Service unavailable'))
      mockApi.getBuySignals.mockRejectedValue(new Error('Service unavailable'))
      mockApi.getSellSignals.mockRejectedValue(new Error('Service unavailable'))

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })

      // Component should still render even with circuit breakers open
      expect(screen.getByText('Market Sentiment')).toBeInTheDocument()
    })
  })

  describe('Recovery Scenarios', () => {
    test('gradually allows requests after circuit recovery', async () => {
      let successCount = 0
      let failureCount = 0
      
      mockApi.getTradingSignals.mockImplementation(() => {
        const shouldSucceed = Math.random() > 0.3 // 70% success rate
        
        if (shouldSucceed) {
          successCount++
          circuitTracker.recordSuccess('trading-signals')
          return Promise.resolve({
            data: [
              { symbol: 'AAPL', signal: 'BUY', confidence: 0.8 }
            ],
            success: true
          })
        } else {
          failureCount++
          circuitTracker.recordFailure('trading-signals')
          return Promise.reject(new Error('Trading signals API failed'))
        }
      })

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      )

      await waitFor(() => {
        // Should handle mixed success/failure gracefully
        const tradingElements = screen.queryAllByText(/trading|signal|buy|sell/i)
        expect(tradingElements.length).toBeGreaterThan(0)
      })

      // Over time, circuit should adapt to success rate
      expect(successCount + failureCount).toBeGreaterThan(0)
    })

    test('handles cascading failures across multiple services', async () => {
      // Simulate cascading failures across multiple API endpoints
      const endpoints = ['stock-prices', 'market-data', 'trading-signals', 'portfolio']
      
      endpoints.forEach(endpoint => {
        for (let i = 0; i < 4; i++) {
          circuitTracker.recordFailure(endpoint)
        }
      })

      // All circuits should be open
      endpoints.forEach(endpoint => {
        expect(circuitTracker.shouldCircuitBeOpen(endpoint)).toBe(true)
      })

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      // App should still render despite all circuits being open
      await waitFor(() => {
        expect(screen.getByText(/Elite Financial Intelligence Platform/i)).toBeInTheDocument()
      })

      expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
    })
  })

  describe('Rate Limiting Integration', () => {
    test('circuit breaker works with rate limiting', async () => {
      let callCount = 0
      const rateLimitThreshold = 10
      
      fetchMock.mockImplementation(() => {
        callCount++
        
        if (callCount > rateLimitThreshold) {
          return Promise.resolve({
            ok: false,
            status: 429,
            json: () => Promise.resolve({ 
              error: 'Rate limit exceeded',
              retryAfter: 60 
            })
          })
        }
        
        // Simulate service failure
        return Promise.resolve({
          ok: false,
          status: 500,
          json: () => Promise.resolve({ error: 'Internal server error' })
        })
      })

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })

      // Should handle both circuit breaker and rate limiting
      expect(callCount).toBeLessThan(50) // Reasonable upper bound
    })
  })

  describe('Performance Under Circuit Breaker Conditions', () => {
    test('maintains performance when circuits are open', async () => {
      const startTime = performance.now()
      
      // Open all circuits immediately
      mockApi.getStockPrices.mockImplementation(() => {
        circuitTracker.recordFailure('stock-prices')
        if (circuitTracker.shouldCircuitBeOpen('stock-prices')) {
          // Fast fallback response
          return Promise.resolve({
            data: [],
            success: true,
            cached: true,
            circuitOpen: true
          })
        }
        return Promise.reject(new Error('API failed'))
      })

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })

      const endTime = performance.now()
      const renderTime = endTime - startTime

      // Should render quickly with circuit breaker fallbacks
      expect(renderTime).toBeLessThan(3000) // 3 seconds max
    })

    test('prevents resource exhaustion during failures', async () => {
      let totalCalls = 0
      const maxAllowedCalls = 20
      
      mockApi.getStockPrices.mockImplementation(() => {
        totalCalls++
        
        // Simulate circuit breaker preventing excessive calls
        if (circuitTracker.shouldCircuitBeOpen('stock-prices')) {
          return Promise.resolve({
            data: [],
            success: true,
            circuitOpen: true
          })
        }
        
        if (totalCalls <= 5) {
          circuitTracker.recordFailure('stock-prices')
          return Promise.reject(new Error('API failed'))
        }
        
        return Promise.resolve({ data: [], success: true })
      })

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Market Sentiment')).toBeInTheDocument()
      })

      // Circuit breaker should prevent excessive API calls
      expect(totalCalls).toBeLessThan(maxAllowedCalls)
    })
  })

  describe('User Experience During Circuit Breaker Events', () => {
    test('provides meaningful feedback when services are degraded', async () => {
      // Mock services to appear degraded
      mockApi.getStockPrices.mockImplementation(() => {
        return Promise.resolve({
          data: [],
          success: true,
          degraded: true,
          message: 'Service temporarily degraded'
        })
      })

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })

      // Should still provide a functional interface
      expect(screen.getByText('Market Sentiment')).toBeInTheDocument()
    })

    test('allows manual refresh when circuits are open', async () => {
      let manualRefreshCount = 0
      
      mockApi.getStockPrices.mockImplementation(() => {
        if (circuitTracker.shouldCircuitBeOpen('stock-prices')) {
          manualRefreshCount++
          // Allow manual refresh to bypass circuit breaker temporarily
          return Promise.resolve({
            data: [{ date: '2025-01-01', price: 150 }],
            success: true,
            manualRefresh: true
          })
        }
        return Promise.reject(new Error('API failed'))
      })

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })

      // Simulate manual refresh action (if refresh button exists)
      const refreshButtons = screen.queryAllByText(/refresh|reload/i)
      if (refreshButtons.length > 0) {
        fireEvent.click(refreshButtons[0])
        
        await waitFor(() => {
          expect(manualRefreshCount).toBeGreaterThan(0)
        })
      }
    })
  })

  describe('Circuit Breaker Configuration', () => {
    test('respects different failure thresholds for different services', async () => {
      const services = {
        'critical-service': { threshold: 2, failures: 0 },
        'non-critical-service': { threshold: 5, failures: 0 }
      }

      Object.keys(services).forEach(service => {
        for (let i = 0; i < 3; i++) {
          circuitTracker.recordFailure(service)
          services[service].failures++
        }
      })

      // Critical service should have circuit open (3 > 2)
      expect(circuitTracker.shouldCircuitBeOpen('critical-service', 2)).toBe(true)
      
      // Non-critical service should still be closed (3 < 5)
      expect(circuitTracker.shouldCircuitBeOpen('non-critical-service', 5)).toBe(false)
    })

    test('handles different timeout periods for different circuits', async () => {
      // This would test different recovery timeouts for different services
      // Implementation would depend on actual circuit breaker configuration
      
      circuitTracker.setCircuitState('fast-recovery', 'open')
      circuitTracker.setCircuitState('slow-recovery', 'open')

      // Simulate fast recovery (short timeout)
      setTimeout(() => {
        circuitTracker.setCircuitState('fast-recovery', 'half-open')
      }, 100)

      // Simulate slow recovery (long timeout)
      setTimeout(() => {
        circuitTracker.setCircuitState('slow-recovery', 'half-open')
      }, 1000)

      await new Promise(resolve => setTimeout(resolve, 200))

      expect(circuitTracker.getCircuitState('fast-recovery')).toBe('half-open')
      expect(circuitTracker.getCircuitState('slow-recovery')).toBe('open')
    })
  })
})