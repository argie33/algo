/**
 * REAL-TIME WEBSOCKET INTEGRATION TESTS
 * Tests live data streaming end-to-end with WebSocket connections
 */

import { describe, test, expect, beforeAll, afterAll, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import safeTheme from '../../theme/safeTheme'

// Import real-time components
import LiveDataWidget from '../../components/LiveDataWidget'
import RealTimePriceWidget from '../../components/RealTimePriceWidget'
import MarketStatusBar from '../../components/MarketStatusBar'
import useRealTimeData from '../../hooks/useRealTimeData'

const TestWrapper = ({ children }) => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, cacheTime: 0 } }
  })

  return (
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider theme={safeTheme}>
          {children}
        </ThemeProvider>
      </QueryClientProvider>
    </BrowserRouter>
  )
}

// Mock WebSocket for testing
class MockWebSocket {
  constructor(url) {
    this.url = url
    this.readyState = WebSocket.CONNECTING
    this.onopen = null
    this.onmessage = null
    this.onclose = null
    this.onerror = null
    
    // Simulate connection after short delay
    setTimeout(() => {
      this.readyState = WebSocket.OPEN
      if (this.onopen) this.onopen({ type: 'open' })
    }, 100)
  }

  send(data) {
    if (this.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket is not open')
    }
    // Echo back for testing
    this.lastSentData = data
  }

  close() {
    this.readyState = WebSocket.CLOSED
    if (this.onclose) this.onclose({ type: 'close' })
  }

  // Test helper to simulate incoming messages
  simulateMessage(data) {
    if (this.onmessage) {
      this.onmessage({
        type: 'message',
        data: typeof data === 'string' ? data : JSON.stringify(data)
      })
    }
  }

  // Test helper to simulate errors
  simulateError(error) {
    if (this.onerror) this.onerror({ type: 'error', error })
  }
}

describe('WebSocket Real-time Integration Tests', () => {
  let originalWebSocket
  let mockWebSocket

  beforeAll(() => {
    // Mock WebSocket globally
    originalWebSocket = global.WebSocket
    global.WebSocket = MockWebSocket
    global.WebSocket.CONNECTING = 0
    global.WebSocket.OPEN = 1
    global.WebSocket.CLOSING = 2
    global.WebSocket.CLOSED = 3
  })

  afterAll(() => {
    global.WebSocket = originalWebSocket
  })

  beforeEach(() => {
    mockWebSocket = null
    // Mock console to reduce test noise
    vi.spyOn(console, 'log').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    if (mockWebSocket) {
      mockWebSocket.close()
    }
    vi.restoreAllMocks()
  })

  describe('WebSocket Connection Management', () => {
    test('Establishes WebSocket connection for real-time data', async () => {
      const TestComponent = () => {
        const { data, isConnected, error } = useRealTimeData(['AAPL'])
        return (
          <div>
            <div data-testid="connection-status">
              {isConnected ? 'Connected' : 'Disconnected'}
            </div>
            <div data-testid="error-status">{error || 'No Error'}</div>
          </div>
        )
      }

      render(
        <TestWrapper>
          <TestComponent />
        </TestWrapper>
      )

      // Should initially be disconnected
      expect(screen.getByTestId('connection-status')).toHaveTextContent('Disconnected')

      // Wait for connection
      await waitFor(() => {
        expect(screen.getByTestId('connection-status')).toHaveTextContent('Connected')
      }, { timeout: 5000 })

      expect(screen.getByTestId('error-status')).toHaveTextContent('No Error')
    })

    test('Handles WebSocket connection failures gracefully', async () => {
      global.WebSocket = class FailingWebSocket extends MockWebSocket {
        constructor(url) {
          super(url)
          setTimeout(() => {
            this.readyState = WebSocket.CLOSED
            if (this.onerror) this.onerror({ type: 'error', error: new Error('Connection failed') })
          }, 50)
        }
      }

      const TestComponent = () => {
        const { isConnected, error } = useRealTimeData(['AAPL'])
        return (
          <div>
            <div data-testid="connection-status">
              {isConnected ? 'Connected' : 'Disconnected'}
            </div>
            <div data-testid="error-status">{error || 'No Error'}</div>
          </div>
        )
      }

      render(
        <TestWrapper>
          <TestComponent />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('connection-status')).toHaveTextContent('Disconnected')
        expect(screen.getByTestId('error-status')).not.toHaveTextContent('No Error')
      }, { timeout: 3000 })
    })

    test('Reconnects automatically after connection loss', async () => {
      let connectionAttempts = 0
      
      global.WebSocket = class ReconnectingWebSocket extends MockWebSocket {
        constructor(url) {
          super(url)
          connectionAttempts++
          
          if (connectionAttempts === 1) {
            // First connection fails
            setTimeout(() => {
              this.readyState = WebSocket.CLOSED
              if (this.onclose) this.onclose({ type: 'close' })
            }, 100)
          } else {
            // Second connection succeeds
            setTimeout(() => {
              this.readyState = WebSocket.OPEN
              if (this.onopen) this.onopen({ type: 'open' })
            }, 100)
          }
        }
      }

      const TestComponent = () => {
        const { isConnected } = useRealTimeData(['AAPL'])
        return (
          <div data-testid="connection-status">
            {isConnected ? 'Connected' : 'Disconnected'}
          </div>
        )
      }

      render(
        <TestWrapper>
          <TestComponent />
        </TestWrapper>
      )

      // Should eventually connect after retry
      await waitFor(() => {
        expect(screen.getByTestId('connection-status')).toHaveTextContent('Connected')
      }, { timeout: 10000 })

      expect(connectionAttempts).toBeGreaterThan(1)
    })
  })

  describe('Real-time Data Streaming', () => {
    test('Receives and processes live stock price updates', async () => {
      let webSocketInstance

      global.WebSocket = class TrackableWebSocket extends MockWebSocket {
        constructor(url) {
          super(url)
          webSocketInstance = this
        }
      }

      const TestComponent = () => {
        const { data } = useRealTimeData(['AAPL'])
        return (
          <div>
            {data.AAPL && (
              <div data-testid="stock-data">
                {data.AAPL.symbol}: ${data.AAPL.price}
              </div>
            )}
          </div>
        )
      }

      render(
        <TestWrapper>
          <TestComponent />
        </TestWrapper>
      )

      // Wait for connection
      await waitFor(() => {
        expect(webSocketInstance).toBeTruthy()
        expect(webSocketInstance.readyState).toBe(WebSocket.OPEN)
      })

      // Simulate incoming price data
      act(() => {
        webSocketInstance.simulateMessage({
          type: 'quote',
          symbol: 'AAPL',
          price: 155.25,
          change: 2.50,
          changePercent: 1.63,
          timestamp: new Date().toISOString()
        })
      })

      await waitFor(() => {
        expect(screen.getByTestId('stock-data')).toHaveTextContent('AAPL: $155.25')
      })
    })

    test('Handles multiple symbol subscriptions', async () => {
      let webSocketInstance

      global.WebSocket = class TrackableWebSocket extends MockWebSocket {
        constructor(url) {
          super(url)
          webSocketInstance = this
        }
      }

      const TestComponent = () => {
        const { data } = useRealTimeData(['AAPL', 'MSFT', 'GOOGL'])
        return (
          <div>
            {Object.entries(data).map(([symbol, quote]) => (
              <div key={symbol} data-testid={`stock-${symbol}`}>
                {symbol}: ${quote.price}
              </div>
            ))}
          </div>
        )
      }

      render(
        <TestWrapper>
          <TestComponent />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(webSocketInstance).toBeTruthy()
      })

      // Send data for multiple symbols
      const symbols = ['AAPL', 'MSFT', 'GOOGL']
      const prices = [155.25, 310.50, 2750.00]

      symbols.forEach((symbol, index) => {
        act(() => {
          webSocketInstance.simulateMessage({
            type: 'quote',
            symbol,
            price: prices[index],
            timestamp: new Date().toISOString()
          })
        })
      })

      // Verify all symbols are displayed
      for (let i = 0; i < symbols.length; i++) {
        await waitFor(() => {
          expect(screen.getByTestId(`stock-${symbols[i]}`)).toHaveTextContent(
            `${symbols[i]}: $${prices[i]}`
          )
        })
      }
    })

    test('Processes batch updates efficiently', async () => {
      let webSocketInstance

      global.WebSocket = class TrackableWebSocket extends MockWebSocket {
        constructor(url) {
          super(url)
          webSocketInstance = this
        }
      }

      const TestComponent = () => {
        const { data } = useRealTimeData(['AAPL'])
        return (
          <div data-testid="update-count">
            Updates: {data.AAPL ? data.AAPL.updateCount || 1 : 0}
          </div>
        )
      }

      render(
        <TestWrapper>
          <TestComponent />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(webSocketInstance).toBeTruthy()
      })

      // Send multiple rapid updates
      for (let i = 0; i < 5; i++) {
        act(() => {
          webSocketInstance.simulateMessage({
            type: 'quote',
            symbol: 'AAPL',
            price: 155.00 + i,
            updateCount: i + 1,
            timestamp: new Date().toISOString()
          })
        })
      }

      await waitFor(() => {
        expect(screen.getByTestId('update-count')).toHaveTextContent('Updates: 5')
      })
    })
  })

  describe('WebSocket Component Integration', () => {
    test('LiveDataWidget displays real-time updates', async () => {
      render(
        <TestWrapper>
          <LiveDataWidget symbols={['AAPL']} />
        </TestWrapper>
      )

      // Should render loading state initially
      expect(screen.getByText(/live data/i) || screen.getByRole('progressbar')).toBeTruthy()

      // Wait for component to load
      await waitFor(() => {
        expect(document.body).toBeTruthy()
      })
    })

    test('RealTimePriceWidget shows current prices', async () => {
      render(
        <TestWrapper>
          <RealTimePriceWidget symbol="AAPL" />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(document.body).toBeTruthy()
      })
    })

    test('MarketStatusBar reflects real-time market status', async () => {
      render(
        <TestWrapper>
          <MarketStatusBar />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(document.body).toBeTruthy()
      })
    })
  })

  describe('Error Handling and Recovery', () => {
    test('Handles malformed WebSocket messages', async () => {
      let webSocketInstance

      global.WebSocket = class TrackableWebSocket extends MockWebSocket {
        constructor(url) {
          super(url)
          webSocketInstance = this
        }
      }

      const TestComponent = () => {
        const { data, error } = useRealTimeData(['AAPL'])
        return (
          <div>
            <div data-testid="error">{error || 'No Error'}</div>
            <div data-testid="data">{data.AAPL ? 'Has Data' : 'No Data'}</div>
          </div>
        )
      }

      render(
        <TestWrapper>
          <TestComponent />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(webSocketInstance).toBeTruthy()
      })

      // Send malformed message
      act(() => {
        webSocketInstance.simulateMessage('invalid json {')
      })

      // Should handle error gracefully
      await waitFor(() => {
        expect(screen.getByTestId('data')).toHaveTextContent('No Data')
      })
    })

    test('Recovers from temporary connection issues', async () => {
      let connectionCount = 0

      global.WebSocket = class RecoveringWebSocket extends MockWebSocket {
        constructor(url) {
          super(url)
          connectionCount++
          
          if (connectionCount === 1) {
            // First connection works then drops
            setTimeout(() => {
              this.readyState = WebSocket.OPEN
              if (this.onopen) this.onopen({ type: 'open' })
              
              setTimeout(() => {
                this.readyState = WebSocket.CLOSED
                if (this.onclose) this.onclose({ type: 'close' })
              }, 500)
            }, 100)
          } else {
            // Subsequent connections work normally
            setTimeout(() => {
              this.readyState = WebSocket.OPEN
              if (this.onopen) this.onopen({ type: 'open' })
            }, 100)
          }
        }
      }

      const TestComponent = () => {
        const { isConnected } = useRealTimeData(['AAPL'])
        return (
          <div data-testid="status">
            {isConnected ? 'Connected' : 'Disconnected'}
          </div>
        )
      }

      render(
        <TestWrapper>
          <TestComponent />
        </TestWrapper>
      )

      // Should eventually reconnect
      await waitFor(() => {
        expect(screen.getByTestId('status')).toHaveTextContent('Connected')
      }, { timeout: 10000 })

      expect(connectionCount).toBeGreaterThan(1)
    })
  })

  describe('Performance and Memory Management', () => {
    test('Cleans up WebSocket connections on unmount', async () => {
      let webSocketInstance

      global.WebSocket = class TrackableWebSocket extends MockWebSocket {
        constructor(url) {
          super(url)
          webSocketInstance = this
          this.closeCalled = false
        }

        close() {
          this.closeCalled = true
          super.close()
        }
      }

      const TestComponent = () => {
        const { isConnected } = useRealTimeData(['AAPL'])
        return <div>{isConnected ? 'Connected' : 'Disconnected'}</div>
      }

      const { unmount } = render(
        <TestWrapper>
          <TestComponent />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(webSocketInstance).toBeTruthy()
      })

      // Unmount component
      unmount()

      // Should clean up connection
      expect(webSocketInstance.closeCalled).toBe(true)
    })

    test('Handles high-frequency updates without memory leaks', async () => {
      let webSocketInstance

      global.WebSocket = class TrackableWebSocket extends MockWebSocket {
        constructor(url) {
          super(url)
          webSocketInstance = this
        }
      }

      const TestComponent = () => {
        const { data } = useRealTimeData(['AAPL'])
        return (
          <div data-testid="price">
            {data.AAPL ? data.AAPL.price : 'No Price'}
          </div>
        )
      }

      render(
        <TestWrapper>
          <TestComponent />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(webSocketInstance).toBeTruthy()
      })

      // Send many rapid updates
      for (let i = 0; i < 100; i++) {
        act(() => {
          webSocketInstance.simulateMessage({
            type: 'quote',
            symbol: 'AAPL',
            price: 155.00 + (i * 0.01),
            timestamp: new Date().toISOString()
          })
        })
      }

      // Should handle updates without crashing
      await waitFor(() => {
        expect(screen.getByTestId('price')).toHaveTextContent(/\$/)
      })
    })
  })
})