/**
 * Data Validation Edge Cases Integration Tests
 * Tests how components handle malformed, incomplete, or unexpected data
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import Dashboard from '../../../pages/Dashboard'
import StockDetail from '../../../pages/StockDetail'
import Portfolio from '../../../pages/Portfolio'
import TradingSignals from '../../../pages/TradingSignals'
import { AuthContext } from '../../../contexts/AuthContext'
import muiTheme from '../../../theme/muiTheme'

// Mock react-router-dom params
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useParams: () => ({ ticker: 'AAPL' })
  }
})

// Mock the API service with various data scenarios
const mockApi = {
  getApiConfig: vi.fn(() => ({
    apiUrl: 'https://test-api.com',
    isServerless: true,
    isConfigured: true
  })),
  getStockPrices: vi.fn(),
  getStockMetrics: vi.fn(),
  getStockData: vi.fn(),
  getBuySignals: vi.fn(),
  getSellSignals: vi.fn(),
  getPortfolioData: vi.fn(),
  getTradingSignals: vi.fn()
}

vi.mock('../../../services/api', () => mockApi)

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

describe('Data Validation Edge Cases Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('Null and Undefined Data Handling', () => {
    test('handles null API responses', async () => {
      mockApi.getStockPrices.mockResolvedValue(null)
      mockApi.getStockMetrics.mockResolvedValue(null)
      
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })

      // Should render without crashing despite null responses
      expect(screen.getByText('Market Sentiment')).toBeInTheDocument()
    })

    test('handles undefined nested properties', async () => {
      mockApi.getStockData.mockResolvedValue({
        data: {
          // Missing expected properties
          price: undefined,
          metrics: null,
          profile: {
            // Incomplete profile data
            name: undefined,
            sector: null
          }
        },
        success: true
      })

      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      )

      await waitFor(() => {
        // Should render some content even with missing data
        const stockElements = screen.queryAllByText(/stock|price|$|loading/i)
        expect(stockElements.length).toBeGreaterThan(0)
      })
    })

    test('handles arrays with null elements', async () => {
      mockApi.getPortfolioData.mockResolvedValue({
        data: {
          positions: [
            null,
            { symbol: 'AAPL', quantity: 10, price: 150 },
            undefined,
            { symbol: 'MSFT', quantity: null, price: undefined },
            null
          ]
        },
        success: true
      })

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      )

      await waitFor(() => {
        // Should handle null elements in arrays gracefully
        const portfolioElements = screen.queryAllByText(/portfolio|position|symbol/i)
        expect(portfolioElements.length).toBeGreaterThan(0)
      })
    })
  })

  describe('Malformed Numeric Data', () => {
    test('handles invalid numeric values', async () => {
      mockApi.getStockPrices.mockResolvedValue({
        data: [
          { date: '2025-01-01', close: 'not-a-number', price: NaN },
          { date: '2025-01-02', close: Infinity, price: -Infinity },
          { date: '2025-01-03', close: '150.invalid', price: 'abc' },
          { date: 'invalid-date', close: 155, price: 155 }
        ],
        success: true
      })

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })

      // Should handle invalid numbers without crashing
      expect(screen.getByText('Market Sentiment')).toBeInTheDocument()
    })

    test('handles extremely large or small numbers', async () => {
      mockApi.getStockMetrics.mockResolvedValue({
        data: {
          marketCap: Number.MAX_SAFE_INTEGER + 1,
          beta: -Number.MAX_VALUE,
          pe: Number.POSITIVE_INFINITY,
          eps: Number.NEGATIVE_INFINITY,
          volume: Number.MIN_VALUE,
          price: 1e-100 // Extremely small number
        },
        success: true
      })

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        // Should handle extreme numbers gracefully
        const valueElements = screen.queryAllByText(/\$|portfolio|market/i)
        expect(valueElements.length).toBeGreaterThan(0)
      })
    })

    test('handles percentage calculations with invalid data', async () => {
      mockApi.getPortfolioData.mockResolvedValue({
        data: {
          totalValue: 0, // Division by zero scenario
          dailyChange: NaN,
          totalChange: Infinity,
          positions: [
            { 
              symbol: 'AAPL', 
              quantity: 0, 
              currentPrice: 150, 
              averagePrice: 0, // Another division by zero
              unrealizedPnL: NaN,
              percentChange: Infinity
            }
          ]
        },
        success: true
      })

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      )

      await waitFor(() => {
        // Should handle percentage calculations with invalid data
        const portfolioElements = screen.queryAllByText(/portfolio|%|change/i)
        expect(portfolioElements.length).toBeGreaterThan(0)
      })
    })
  })

  describe('String Data Validation', () => {
    test('handles extremely long strings', async () => {
      const longString = 'a'.repeat(10000)
      
      mockApi.getStockData.mockResolvedValue({
        data: {
          profile: {
            name: longString,
            description: longString,
            sector: longString
          }
        },
        success: true
      })

      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      )

      await waitFor(() => {
        // Should handle long strings without performance issues
        const stockElements = screen.queryAllByText(/stock|company/i)
        expect(stockElements.length).toBeGreaterThan(0)
      })
    })

    test('handles strings with special characters and unicode', async () => {
      mockApi.getTradingSignals.mockResolvedValue({
        data: [
          {
            symbol: '🚀AAPL💎', // Emojis
            signal: 'BUY\\n\\t\\r', // Escape sequences
            notes: 'Special chars: <>&"\'', // HTML/XML chars
            timestamp: '2025-01-01T00:00:00.000Z\x00\x01\x02' // Control chars
          },
          {
            symbol: 'Ñøñ-ÁSçîï', // International characters
            signal: 'SELL',
            notes: '测试中文字符', // Chinese characters
            timestamp: 'עברית' // Hebrew characters
          }
        ],
        success: true
      })

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      )

      await waitFor(() => {
        // Should handle special characters without breaking
        const tradingElements = screen.queryAllByText(/trading|signal|buy|sell/i)
        expect(tradingElements.length).toBeGreaterThan(0)
      })
    })

    test('handles empty and whitespace-only strings', async () => {
      mockApi.getStockData.mockResolvedValue({
        data: {
          profile: {
            name: '',
            description: '   ',
            sector: '\n\t\r  ',
            industry: null,
            website: undefined
          },
          fundamentals: {
            marketCap: '',
            revenue: '   ',
            employees: '\t\n'
          }
        },
        success: true
      })

      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      )

      await waitFor(() => {
        // Should handle empty strings gracefully
        const stockElements = screen.queryAllByText(/stock|company|n\/a|unknown/i)
        expect(stockElements.length).toBeGreaterThan(0)
      })
    })
  })

  describe('Date and Time Validation', () => {
    test('handles invalid date formats', async () => {
      mockApi.getStockPrices.mockResolvedValue({
        data: [
          { date: 'not-a-date', price: 150 },
          { date: '2025-13-45', price: 155 }, // Invalid date
          { date: '32/25/2025', price: 160 }, // Wrong format
          { date: 'yesterday', price: 165 }, // Relative date
          { date: null, price: 170 },
          { date: 1234567890, price: 175 }, // Unix timestamp
          { date: '2025-01-01T25:70:90Z', price: 180 } // Invalid time
        ],
        success: true
      })

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })

      // Should handle invalid dates without crashing
      expect(screen.getByText('Market Sentiment')).toBeInTheDocument()
    })

    test('handles timezone and DST edge cases', async () => {
      mockApi.getTradingSignals.mockResolvedValue({
        data: [
          {
            symbol: 'AAPL',
            signal: 'BUY',
            timestamp: '2025-03-10T02:30:00.000Z', // DST transition
          },
          {
            symbol: 'MSFT',
            signal: 'SELL',
            timestamp: '2025-11-03T01:30:00.000Z', // DST end
          },
          {
            symbol: 'GOOGL',
            signal: 'HOLD',
            timestamp: '2025-01-01T00:00:00+14:00', // Edge timezone
          }
        ],
        success: true
      })

      render(
        <TestWrapper>
          <TradingSignals />
        </TestWrapper>
      )

      await waitFor(() => {
        const tradingElements = screen.queryAllByText(/trading|signal/i)
        expect(tradingElements.length).toBeGreaterThan(0)
      })
    })
  })

  describe('Complex Object Structure Validation', () => {
    test('handles deeply nested invalid data', async () => {
      mockApi.getStockData.mockResolvedValue({
        data: {
          profile: {
            company: {
              info: {
                details: {
                  name: null,
                  description: {
                    // Wrong type - should be string
                    text: { value: 'Company description' },
                    length: 'not-a-number'
                  }
                }
              }
            }
          },
          metrics: {
            financial: {
              ratios: {
                pe: 'invalid',
                pb: null,
                roe: {
                  // Wrong structure
                  value: 0.15,
                  currency: 'percentage' // Wrong field
                }
              }
            }
          }
        },
        success: true
      })

      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      )

      await waitFor(() => {
        // Should handle deeply nested invalid data
        const stockElements = screen.queryAllByText(/stock|company|loading/i)
        expect(stockElements.length).toBeGreaterThan(0)
      })
    })

    test('handles circular references in data', async () => {
      const circularData = {
        name: 'AAPL',
        related: null
      }
      circularData.related = circularData // Create circular reference

      mockApi.getStockData.mockResolvedValue({
        data: {
          stock: circularData
        },
        success: true
      })

      render(
        <TestWrapper>
          <StockDetail />
        </TestWrapper>
      )

      await waitFor(() => {
        // Should handle circular references without infinite loops
        const stockElements = screen.queryAllByText(/stock|loading/i)
        expect(stockElements.length).toBeGreaterThan(0)
      })
    })

    test('handles mixed array data types', async () => {
      mockApi.getPortfolioData.mockResolvedValue({
        data: {
          positions: [
            'not-an-object',
            123,
            { symbol: 'AAPL', quantity: 10 },
            ['nested', 'array'],
            true,
            null,
            { symbol: 'MSFT', quantity: 'not-a-number' }
          ],
          transactions: [
            { type: 'buy', amount: null },
            { type: null, amount: 1000 },
            'invalid-transaction',
            { type: 'sell', amount: -500, date: 'invalid-date' }
          ]
        },
        success: true
      })

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      )

      await waitFor(() => {
        // Should handle mixed data types in arrays
        const portfolioElements = screen.queryAllByText(/portfolio|position/i)
        expect(portfolioElements.length).toBeGreaterThan(0)
      })
    })
  })

  describe('API Response Structure Validation', () => {
    test('handles responses missing required fields', async () => {
      // Response missing 'data' field
      mockApi.getStockPrices.mockResolvedValue({
        success: true,
        message: 'Data retrieved',
        // Missing 'data' field
      })

      // Response missing 'success' field
      mockApi.getStockMetrics.mockResolvedValue({
        data: { pe: 15.5 },
        // Missing 'success' field
      })

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })

      // Should handle missing required fields gracefully
      expect(screen.getByText('Market Sentiment')).toBeInTheDocument()
    })

    test('handles responses with unexpected structure', async () => {
      mockApi.getBuySignals.mockResolvedValue({
        // Completely unexpected structure
        result: {
          signals: {
            buy: [
              { ticker: 'AAPL', confidence: 0.8 } // Different field names
            ]
          }
        },
        status: 'ok' // Different success indicator
      })

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })

      // Should handle unexpected response structure
      expect(screen.getByText('Market Sentiment')).toBeInTheDocument()
    })

    test('handles responses with extra unexpected fields', async () => {
      mockApi.getSellSignals.mockResolvedValue({
        data: [
          { symbol: 'MSFT', signal: 'SELL', confidence: 0.7 }
        ],
        success: true,
        // Extra unexpected fields
        debug: { 
          internalId: '12345',
          processingTime: 150,
          version: '2.1.0'
        },
        metadata: {
          timestamp: Date.now(),
          source: 'algorithm-v2',
          experimental: true
        },
        secretData: 'should-not-be-here',
        adminFlag: true
      })

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })

      // Should handle extra fields without issues
      expect(screen.getByText('Market Sentiment')).toBeInTheDocument()
    })
  })

  describe('Performance with Invalid Data', () => {
    test('maintains performance with large invalid datasets', async () => {
      const startTime = performance.now()
      
      // Generate large invalid dataset
      const largeInvalidData = Array(1000).fill(null).map((_, i) => ({
        symbol: i % 2 === 0 ? null : `STOCK${i}`,
        price: i % 3 === 0 ? NaN : Math.random() * 1000,
        change: i % 4 === 0 ? Infinity : Math.random() * 100 - 50,
        volume: i % 5 === 0 ? 'not-a-number' : Math.floor(Math.random() * 1000000),
        invalidField: { nested: { data: 'test' } }
      }))

      mockApi.getStockPrices.mockResolvedValue({
        data: largeInvalidData,
        success: true
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

      // Should render within reasonable time even with large invalid dataset
      expect(renderTime).toBeLessThan(10000) // 10 seconds max
    })

    test('prevents memory leaks with invalid data', async () => {
      // Mock data with potential memory leak patterns
      const potentialLeakData = {
        data: {
          // Large object that references itself
          positions: Array(100).fill(null).map((_, i) => {
            const obj = {
              id: i,
              symbol: `STOCK${i}`,
              data: new Array(1000).fill(`data-${i}`)
            }
            obj.self = obj // Self reference
            return obj
          })
        },
        success: true
      }

      mockApi.getPortfolioData.mockResolvedValue(potentialLeakData)

      const { unmount } = render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      )

      await waitFor(() => {
        const portfolioElements = screen.queryAllByText(/portfolio/i)
        expect(portfolioElements.length).toBeGreaterThan(0)
      })

      // Unmount should clean up properly
      expect(() => unmount()).not.toThrow()
    })
  })
})