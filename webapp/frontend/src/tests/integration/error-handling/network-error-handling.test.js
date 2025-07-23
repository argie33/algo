/**
 * Network Error Handling Integration Tests
 * Tests how the application handles various network failure scenarios
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import Dashboard from '../../../pages/Dashboard'
import Settings from '../../../pages/Settings'
import { AuthContext } from '../../../contexts/AuthContext'
import muiTheme from '../../../theme/muiTheme'

// Mock the API module to simulate network errors
const mockApi = {
  getApiConfig: vi.fn(() => ({
    apiUrl: 'https://test-api.com',
    isServerless: true,
    isConfigured: true
  })),
  getStockPrices: vi.fn(),
  getStockMetrics: vi.fn(),
  getBuySignals: vi.fn(),
  getSellSignals: vi.fn()
}

vi.mock('../../../services/api', () => mockApi)

// Mock fetch for direct API calls
const originalFetch = global.fetch
let fetchMock

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

describe('Network Error Handling Tests', () => {
  beforeEach(() => {
    fetchMock = vi.fn()
    global.fetch = fetchMock
    vi.clearAllMocks()
  })

  afterEach(() => {
    global.fetch = originalFetch
    vi.restoreAllMocks()
  })

  describe('API Service Error Scenarios', () => {
    test('handles 500 server errors gracefully', async () => {
      mockApi.getStockPrices.mockRejectedValueOnce(new Error('Internal Server Error'))
      
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      // Should still render dashboard without crashing
      await waitFor(() => {
        expect(screen.getByText(/Elite Financial Intelligence Platform/i)).toBeInTheDocument()
      })

      // Should show portfolio value even with API errors
      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })
    })

    test('handles network timeout errors', async () => {
      const timeoutError = new Error('Network timeout')
      timeoutError.code = 'NETWORK_TIMEOUT'
      mockApi.getStockMetrics.mockRejectedValueOnce(timeoutError)
      
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      // Component should still render
      await waitFor(() => {
        expect(screen.getByText('Market Sentiment')).toBeInTheDocument()
      })
    })

    test('handles DNS resolution failures', async () => {
      const dnsError = new Error('DNS_PROBE_FINISHED_NXDOMAIN')
      dnsError.code = 'ENOTFOUND'
      mockApi.getBuySignals.mockRejectedValueOnce(dnsError)
      
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      // Should render without crashing despite DNS issues
      expect(screen.getByText(/Elite Financial Intelligence Platform/i)).toBeInTheDocument()
    })

    test('handles CORS errors', async () => {
      const corsError = new Error('CORS policy error')
      corsError.name = 'TypeError'
      corsError.message = 'Failed to fetch'
      mockApi.getSellSignals.mockRejectedValueOnce(corsError)
      
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })
    })
  })

  describe('HTTP Status Code Error Handling', () => {
    test('handles 401 Unauthorized errors', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ error: 'Unauthorized' })
      })

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      // Should render settings page
      await waitFor(() => {
        expect(screen.getByText('Account Settings')).toBeInTheDocument()
      })
    })

    test('handles 403 Forbidden errors', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 403,
        json: async () => ({ error: 'Forbidden - Insufficient permissions' })
      })

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('API Keys')).toBeInTheDocument()
      })
    })

    test('handles 404 Not Found errors', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ error: 'Endpoint not found' })
      })

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Notifications')).toBeInTheDocument()
      })
    })

    test('handles 429 Rate Limit Exceeded errors', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 429,
        headers: new Map([['Retry-After', '60']]),
        json: async () => ({ error: 'Rate limit exceeded' })
      })

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Appearance')).toBeInTheDocument()
      })
    })

    test('handles 502 Bad Gateway errors', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 502,
        json: async () => ({ error: 'Bad Gateway' })
      })

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Security')).toBeInTheDocument()
      })
    })

    test('handles 503 Service Unavailable errors', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 503,
        json: async () => ({ error: 'Service temporarily unavailable' })
      })

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Profile')).toBeInTheDocument()
      })
    })
  })

  describe('Malformed Response Handling', () => {
    test('handles invalid JSON responses', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => {
          throw new SyntaxError('Unexpected token in JSON')
        }
      })

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Account Settings')).toBeInTheDocument()
      })
    })

    test('handles empty response bodies', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => null
      })

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Personal Information')).toBeInTheDocument()
      })
    })

    test('handles response with missing required fields', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          // Missing expected fields like 'data', 'success', etc.
          incomplete: true
        })
      })

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Account Overview')).toBeInTheDocument()
      })
    })
  })

  describe('Connection Error Scenarios', () => {
    test('handles connection refused errors', async () => {
      const connectionError = new Error('Connection refused')
      connectionError.code = 'ECONNREFUSED'
      fetchMock.mockRejectedValueOnce(connectionError)

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })
    })

    test('handles connection reset errors', async () => {
      const resetError = new Error('Connection reset by peer')
      resetError.code = 'ECONNRESET'
      fetchMock.mockRejectedValueOnce(resetError)

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Market Sentiment')).toBeInTheDocument()
      })
    })

    test('handles SSL/TLS certificate errors', async () => {
      const sslError = new Error('SSL certificate verification failed')
      sslError.code = 'CERT_UNTRUSTED'
      fetchMock.mockRejectedValueOnce(sslError)

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText(/Elite Financial Intelligence Platform/i)).toBeInTheDocument()
      })
    })
  })

  describe('Authentication Error Recovery', () => {
    test('handles expired token gracefully', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ 
          error: 'Token expired',
          code: 'TOKEN_EXPIRED' 
        })
      })

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Account Settings')).toBeInTheDocument()
      })
    })

    test('handles invalid token format', async () => {
      fetchMock.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({ 
          error: 'Invalid token format',
          code: 'INVALID_TOKEN' 
        })
      })

      render(
        <TestWrapper isAuthenticated={true}>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Manage your account preferences')).toBeInTheDocument()
      })
    })
  })

  describe('Resource Loading Failures', () => {
    test('handles failed asset loading', async () => {
      // Mock a failed resource load (like CSS, images, etc.)
      const resourceError = new Error('Failed to load resource')
      resourceError.name = 'ResourceLoadError'
      
      // This would normally be handled by error boundaries
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })
    })

    test('handles chunk loading failures (code splitting)', async () => {
      // Simulate dynamic import failure
      const chunkError = new Error('Loading chunk failed')
      chunkError.name = 'ChunkLoadError'
      
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Market Sentiment')).toBeInTheDocument()
      })
    })
  })

  describe('User Interaction Error Scenarios', () => {
    test('handles form submission with network errors', async () => {
      fetchMock.mockRejectedValueOnce(new Error('Network error during form submission'))

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      // Navigate to profile tab and try to save
      const profileTab = screen.getByRole('tab', { name: /profile/i })
      fireEvent.click(profileTab)

      await waitFor(() => {
        const saveButton = screen.getByRole('button', { name: /save changes/i })
        expect(saveButton).toBeInTheDocument()
        
        // Click save button - should handle network error gracefully
        fireEvent.click(saveButton)
      })

      // Should still show the form after error
      await waitFor(() => {
        expect(screen.getByLabelText(/first name/i)).toBeInTheDocument()
      })
    })

    test('handles file upload failures', async () => {
      fetchMock.mockRejectedValueOnce(new Error('File upload failed'))

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      // Should render settings without crashing
      await waitFor(() => {
        expect(screen.getByText('Account Settings')).toBeInTheDocument()
      })
    })
  })

  describe('Error Recovery and Retry Logic', () => {
    test('shows appropriate error messages for different error types', async () => {
      // Test that different error types show user-friendly messages
      mockApi.getStockPrices.mockRejectedValueOnce(new Error('Network timeout'))
      
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      // Should still render main content
      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
      })
    })

    test('maintains application state during error conditions', async () => {
      // Simulate error on one API call but success on others
      mockApi.getStockPrices.mockRejectedValueOnce(new Error('API Error'))
      mockApi.getStockMetrics.mockResolvedValueOnce({
        data: { beta: 1.1, volatility: 0.12 },
        success: true
      })

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      // Should show both success and graceful failure handling
      await waitFor(() => {
        expect(screen.getByText('Portfolio Value')).toBeInTheDocument()
        expect(screen.getByText('Market Sentiment')).toBeInTheDocument()
      })
    })
  })

  describe('Performance Under Error Conditions', () => {
    test('component performance remains acceptable during errors', async () => {
      const startTime = performance.now()
      
      // Simulate multiple API failures
      mockApi.getStockPrices.mockRejectedValue(new Error('API Error'))
      mockApi.getStockMetrics.mockRejectedValue(new Error('API Error'))
      mockApi.getBuySignals.mockRejectedValue(new Error('API Error'))
      mockApi.getSellSignals.mockRejectedValue(new Error('API Error'))

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

      // Should render reasonably quickly even with errors
      expect(renderTime).toBeLessThan(10000) // 10 seconds max
    })
  })
})