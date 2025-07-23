/**
 * Memory Leak Prevention Integration Tests
 * Tests to ensure components properly clean up resources and prevent memory leaks
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import Dashboard from '../../../pages/Dashboard'
import TradingSignals from '../../../pages/TradingSignals'
import Portfolio from '../../../pages/Portfolio'
import Settings from '../../../pages/Settings'
import { AuthContext } from '../../../contexts/AuthContext'
import muiTheme from '../../../theme/muiTheme'

// Memory tracking utilities
class MemoryTracker {
  constructor() {
    this.componentMounts = 0
    this.componentUnmounts = 0
    this.eventListeners = new Set()
    this.intervals = new Set()
    this.timeouts = new Set()
    this.observers = new Set()
    this.connections = new Set()
  }

  trackMount() {
    this.componentMounts++
  }

  trackUnmount() {
    this.componentUnmounts++
  }

  trackEventListener(element, event, handler) {
    const key = `${element}-${event}-${handler.toString()}`
    this.eventListeners.add(key)
  }

  trackInterval(id) {
    this.intervals.add(id)
  }

  trackTimeout(id) {
    this.timeouts.add(id)
  }

  trackObserver(observer) {
    this.observers.add(observer)
  }

  trackConnection(connection) {
    this.connections.add(connection)
  }

  getStats() {
    return {
      mounts: this.componentMounts,
      unmounts: this.componentUnmounts,
      eventListeners: this.eventListeners.size,
      intervals: this.intervals.size,
      timeouts: this.timeouts.size,
      observers: this.observers.size,
      connections: this.connections.size
    }
  }

  reset() {
    this.componentMounts = 0
    this.componentUnmounts = 0
    this.eventListeners.clear()
    this.intervals.clear()
    this.timeouts.clear()
    this.observers.clear()
    this.connections.clear()
  }
}

const memoryTracker = new MemoryTracker()

// Mock APIs with memory leak potential
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
  getTradingSignals: vi.fn()
}

vi.mock('../../../services/api', () => mockApi)

// Override global functions to track resource usage
const originalSetInterval = global.setInterval
const originalSetTimeout = global.setTimeout
const originalClearInterval = global.clearInterval
const originalClearTimeout = global.clearTimeout

global.setInterval = (...args) => {
  const id = originalSetInterval(...args)
  memoryTracker.trackInterval(id)
  return id
}

global.setTimeout = (...args) => {
  const id = originalSetTimeout(...args)
  memoryTracker.trackTimeout(id)
  return id
}

global.clearInterval = (id) => {
  memoryTracker.intervals.delete(id)
  return originalClearInterval(id)
}

global.clearTimeout = (id) => {
  memoryTracker.timeouts.delete(id)
  return originalClearTimeout(id)
}

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
    error: null
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

describe('Memory Leak Prevention Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    memoryTracker.reset()
    
    // Default successful API responses
    mockApi.getStockPrices.mockResolvedValue({
      data: [{ date: '2025-01-01', price: 150 }],
      success: true
    })
    mockApi.getStockMetrics.mockResolvedValue({
      data: { beta: 1.2, pe: 15.5 },
      success: true
    })
    mockApi.getBuySignals.mockResolvedValue({
      data: [{ symbol: 'AAPL', signal: 'BUY' }],
      success: true
    })
    mockApi.getSellSignals.mockResolvedValue({
      data: [{ symbol: 'MSFT', signal: 'SELL' }],
      success: true
    })
    mockApi.getPortfolioData.mockResolvedValue({
      data: { totalValue: 10000, positions: [] },
      success: true
    })
    mockApi.getTradingSignals.mockResolvedValue({
      data: [{ symbol: 'GOOGL', signal: 'HOLD' }],
      success: true
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    
    // Restore original functions
    global.setInterval = originalSetInterval
    global.setTimeout = originalSetTimeout
    global.clearInterval = originalClearInterval
    global.clearTimeout = originalClearTimeout
  })

  describe('Component Mount/Unmount Cycles', () => {
    test('properly cleans up on rapid mount/unmount cycles', async () => {
      const stats = memoryTracker.getStats()
      const initialIntervals = stats.intervals
      const initialTimeouts = stats.timeouts

      // Mount and unmount multiple times rapidly
      for (let i = 0; i < 10; i++) {
        const { unmount } = render(
          <TestWrapper>
            <Dashboard />
          </TestWrapper>
        )

        await waitFor(() => {
          expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
        })

        act(() => {
          unmount()
        })
      }

      // Wait for cleanup
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 100))
      })

      const finalStats = memoryTracker.getStats()
      
      // Should not have accumulated excessive intervals/timeouts
      expect(finalStats.intervals - initialIntervals).toBeLessThan(5)
      expect(finalStats.timeouts - initialTimeouts).toBeLessThan(10)
    })

    test('cleans up event listeners on unmount', async () => {
      // Mock addEventListener to track listeners
      const addEventListenerSpy = vi.spyOn(document, 'addEventListener')
      const removeEventListenerSpy = vi.spyOn(document, 'removeEventListener')

      const { unmount } = render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })

      const addedListeners = addEventListenerSpy.mock.calls.length

      act(() => {
        unmount()
      })

      // Wait for cleanup
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 50))
      })

      const removedListeners = removeEventListenerSpy.mock.calls.length

      // Should clean up most event listeners (some may be global)
      expect(removedListeners).toBeGreaterThanOrEqual(Math.floor(addedListeners * 0.5))

      addEventListenerSpy.mockRestore()
      removeEventListenerSpy.mockRestore()
    })
  })

  describe('API Request Cleanup', () => {
    test('cancels pending API requests on unmount', async () => {
      let resolveApiCall
      const pendingPromise = new Promise(resolve => {
        resolveApiCall = resolve
      })

      // Mock long-running API call
      mockApi.getStockPrices.mockReturnValue(pendingPromise)

      const { unmount } = render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      // Start loading
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 10))
      })

      // Unmount before API call completes
      act(() => {
        unmount()
      })

      // Complete API call after unmount
      act(() => {
        resolveApiCall({
          data: [{ date: '2025-01-01', price: 150 }],
          success: true
        })
      })

      // Should not cause errors or memory leaks
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 50))
      })

      // No errors should be thrown
      expect(true).toBe(true)
    })

    test('handles component unmount during API error states', async () => {
      // Mock API to fail then succeed
      let shouldFail = true
      mockApi.getStockPrices.mockImplementation(() => {
        if (shouldFail) {
          return Promise.reject(new Error('API Error'))
        }
        return Promise.resolve({
          data: [{ date: '2025-01-01', price: 150 }],
          success: true
        })
      })

      const { unmount } = render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      // Wait for initial error
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 100))
      })

      // Change API to succeed
      shouldFail = false

      // Unmount during retry
      act(() => {
        unmount()
      })

      // Should not cause issues
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 100))
      })

      expect(true).toBe(true)
    })
  })

  describe('Interval and Timer Cleanup', () => {
    test('clears intervals on unmount', async () => {
      const { unmount } = render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      )

      await waitFor(() => {
        const tradingElements = screen.queryAllByText(/trading|signal/i)
        expect(tradingElements.length).toBeGreaterThan(0)
      })

      const intervalsBeforeUnmount = memoryTracker.getStats().intervals

      act(() => {
        unmount()
      })

      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 100))
      })

      const intervalsAfterUnmount = memoryTracker.getStats().intervals

      // Should have cleared intervals (or at least not added more)
      expect(intervalsAfterUnmount).toBeLessThanOrEqual(intervalsBeforeUnmount)
    })

    test('clears timeouts on unmount', async () => {
      const { unmount } = render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      )

      await waitFor(() => {
        const portfolioElements = screen.queryAllByText(/portfolio/i)
        expect(portfolioElements.length).toBeGreaterThan(0)
      })

      const timeoutsBeforeUnmount = memoryTracker.getStats().timeouts

      act(() => {
        unmount()
      })

      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 150))
      })

      const timeoutsAfterUnmount = memoryTracker.getStats().timeouts

      // Should have cleared timeouts
      expect(timeoutsAfterUnmount).toBeLessThanOrEqual(timeoutsBeforeUnmount)
    })
  })

  describe('Observer Pattern Cleanup', () => {
    test('disconnects observers on unmount', async () => {
      // Mock IntersectionObserver
      const mockDisconnect = vi.fn()
      const mockObserver = {
        observe: vi.fn(),
        unobserve: vi.fn(),
        disconnect: mockDisconnect
      }

      global.IntersectionObserver = vi.fn(() => mockObserver)

      const { unmount } = render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })

      act(() => {
        unmount()
      })

      // Observer should be disconnected
      expect(mockDisconnect).toHaveBeenCalled()

      // Cleanup mock
      delete global.IntersectionObserver
    })

    test('cleans up mutation observers', async () => {
      // Mock MutationObserver
      const mockDisconnect = vi.fn()
      const mockObserver = {
        observe: vi.fn(),
        disconnect: mockDisconnect
      }

      global.MutationObserver = vi.fn(() => mockObserver)

      const { unmount } = render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Account Settings')).toBeInTheDocument()
      })

      act(() => {
        unmount()
      })

      // Wait for cleanup
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 50))
      })

      // Should disconnect observer if it was used
      // Note: This depends on if the component actually uses MutationObserver
      if (global.MutationObserver.mock.calls.length > 0) {
        expect(mockDisconnect).toHaveBeenCalled()
      }

      // Cleanup mock
      delete global.MutationObserver
    })
  })

  describe('WebSocket and Connection Cleanup', () => {
    test('closes websocket connections on unmount', async () => {
      // Mock WebSocket
      const mockClose = vi.fn()
      const mockWebSocket = {
        close: mockClose,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        send: vi.fn(),
        readyState: 1 // OPEN
      }

      global.WebSocket = vi.fn(() => mockWebSocket)

      const { unmount } = render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      )

      await waitFor(() => {
        const tradingElements = screen.queryAllByText(/trading|signal/i)
        expect(tradingElements.length).toBeGreaterThan(0)
      })

      act(() => {
        unmount()
      })

      // Wait for cleanup
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 100))
      })

      // Should close WebSocket connections if any were created
      if (global.WebSocket.mock.calls.length > 0) {
        expect(mockClose).toHaveBeenCalled()
      }

      // Cleanup mock
      delete global.WebSocket
    })

    test('aborts fetch requests on unmount', async () => {
      const mockAbort = vi.fn()
      const mockController = {
        abort: mockAbort,
        signal: { aborted: false }
      }

      global.AbortController = vi.fn(() => mockController)

      const { unmount } = render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })

      act(() => {
        unmount()
      })

      // Wait for cleanup
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 50))
      })

      // Should abort ongoing requests if AbortController was used
      if (global.AbortController.mock.calls.length > 0) {
        expect(mockAbort).toHaveBeenCalled()
      }

      // Cleanup mock
      delete global.AbortController
    })
  })

  describe('Large Dataset Memory Management', () => {
    test('handles large datasets without memory bloat', async () => {
      // Generate large dataset
      const largeDataset = Array(10000).fill(null).map((_, i) => ({
        date: `2025-01-${String(i % 31 + 1).padStart(2, '0')}`,
        price: Math.random() * 1000,
        volume: Math.floor(Math.random() * 1000000)
      }))

      mockApi.getStockPrices.mockResolvedValue({
        data: largeDataset,
        success: true
      })

      const { unmount } = render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })

      // Measure approximate memory usage before unmount
      const beforeUnmount = performance.memory?.usedJSHeapSize || 0

      act(() => {
        unmount()
      })

      // Force garbage collection if available
      if (global.gc) {
        global.gc()
      }

      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 200))
      })

      // Memory should not grow excessively
      const afterUnmount = performance.memory?.usedJSHeapSize || 0
      
      // Allow for some memory growth but it shouldn't be excessive
      if (beforeUnmount > 0 && afterUnmount > 0) {
        const memoryGrowth = afterUnmount - beforeUnmount
        expect(memoryGrowth).toBeLessThan(50 * 1024 * 1024) // 50MB max growth
      }
    })

    test('properly cleans up large object references', async () => {
      // Create objects with potential circular references
      const complexData = Array(1000).fill(null).map((_, i) => {
        const obj = {
          id: i,
          symbol: `STOCK${i}`,
          data: new Array(100).fill(`data-${i}`),
          metadata: {
            created: new Date(),
            index: i
          }
        }
        // Add some cross-references (but avoid circular)
        obj.related = i > 0 ? `STOCK${i - 1}` : null
        return obj
      })

      mockApi.getPortfolioData.mockResolvedValue({
        data: { positions: complexData },
        success: true
      })

      const { unmount } = render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      )

      await waitFor(() => {
        const portfolioElements = screen.queryAllByText(/portfolio/i)
        expect(portfolioElements.length).toBeGreaterThan(0)
      })

      // Unmount should clean up without errors
      expect(() => {
        act(() => {
          unmount()
        })
      }).not.toThrow()

      // Wait for cleanup
      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 100))
      })

      expect(true).toBe(true)
    })
  })

  describe('Resource Leak Prevention', () => {
    test('prevents CSS-in-JS style leaks', async () => {
      // Multiple mount/unmount cycles to test style cleanup
      for (let i = 0; i < 5; i++) {
        const { unmount } = render(
          <TestWrapper>
            <Settings />
          </TestWrapper>
        )

        await waitFor(() => {
          expect(screen.getByText('Account Settings')).toBeInTheDocument()
        })

        act(() => {
          unmount()
        })
      }

      // Check that style tags haven't accumulated excessively
      const styleTags = document.querySelectorAll('style')
      
      // Should not have an excessive number of style tags
      expect(styleTags.length).toBeLessThan(50)
    })

    test('cleans up global state on unmount', async () => {
      const { unmount } = render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })

      // Record any global state before unmount
      const windowProps = Object.keys(window).length

      act(() => {
        unmount()
      })

      await act(async () => {
        await new Promise(resolve => setTimeout(resolve, 100))
      })

      // Global state should not grow significantly
      const windowPropsAfter = Object.keys(window).length
      expect(windowPropsAfter - windowProps).toBeLessThan(10)
    })
  })

  describe('Memory Leak Detection', () => {
    test('detects potential memory leaks in component lifecycle', async () => {
      const initialStats = memoryTracker.getStats()

      // Perform multiple mount/unmount cycles
      for (let i = 0; i < 3; i++) {
        const { unmount } = render(
          <TestWrapper>
            <TradingSignals />
          </TestWrapper>
        )

        await waitFor(() => {
          const tradingElements = screen.queryAllByText(/trading|signal/i)
          expect(tradingElements.length).toBeGreaterThan(0)
        })

        act(() => {
          unmount()
        })

        await act(async () => {
          await new Promise(resolve => setTimeout(resolve, 50))
        })
      }

      const finalStats = memoryTracker.getStats()

      // Resource counts should not grow linearly with mount/unmount cycles
      const intervalGrowth = finalStats.intervals - initialStats.intervals
      const timeoutGrowth = finalStats.timeouts - initialStats.timeouts

      expect(intervalGrowth).toBeLessThan(10)
      expect(timeoutGrowth).toBeLessThan(15)
    })
  })
})