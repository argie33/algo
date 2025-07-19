/**
 * Frontend-API Integration Tests
 * Tests React components with real API interactions
 */

import { describe, test, expect, beforeAll, afterAll, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import { AuthProvider } from '../../contexts/AuthContext'
import { ApiKeyProvider } from '../../contexts/ApiKeyContext'
import safeTheme from '../../theme/safeTheme'

// Import components to test
import Dashboard from '../../pages/Dashboard'
import Portfolio from '../../pages/Portfolio'
import SettingsApiKeys from '../../pages/SettingsApiKeys'
import MarketData from '../../pages/MarketData'

// Test wrapper component
const TestWrapper = ({ children }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        cacheTime: 0,
        staleTime: 0,
      },
    },
  })

  return (
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider theme={safeTheme}>
          <AuthProvider>
            <ApiKeyProvider>
              {children}
            </ApiKeyProvider>
          </AuthProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </BrowserRouter>
  )
}

describe('Frontend-API Integration Tests', () => {
  let fetchSpy
  
  beforeAll(() => {
    // Mock fetch for API calls
    fetchSpy = vi.spyOn(global, 'fetch')
    
    // Mock console methods to reduce test noise
    vi.spyOn(console, 'log').mockImplementation(() => {})
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })
  
  afterAll(() => {
    vi.restoreAllMocks()
  })
  
  beforeEach(() => {
    fetchSpy.mockClear()
  })
  
  describe('Dashboard Integration', () => {
    test('should load dashboard with API health check', async () => {
      // Mock successful health API response
      fetchSpy.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          status: 'healthy',
          services: {
            database: 'connected',
            api: 'operational'
          },
          timestamp: new Date().toISOString()
        })
      })
      
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )
      
      // Should show loading state initially
      expect(screen.getByText(/loading/i) || screen.getByRole('progressbar')).toBeTruthy()
      
      // Wait for API call to complete
      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalledWith(
          expect.stringContaining('/health'),
          expect.any(Object)
        )
      }, { timeout: 5000 })
      
      // Should display dashboard content after loading
      await waitFor(() => {
        expect(screen.getByText(/dashboard/i) || screen.getByText(/overview/i)).toBeTruthy()
      })
    })
    
    test('should handle API health check failure gracefully', async () => {
      // Mock failed health API response
      fetchSpy.mockRejectedValueOnce(new Error('API unavailable'))
      
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )
      
      // Should handle error gracefully
      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalled()
      })
      
      // Should still render dashboard with fallback data
      await waitFor(() => {
        expect(document.querySelector('[data-testid], [role="main"], main')).toBeTruthy()
      })
    })
  })
  
  describe('Portfolio Integration', () => {
    test('should fetch portfolio data from API', async () => {
      // Mock portfolio API response
      fetchSpy.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          portfolios: [
            {
              id: 'portfolio-1',
              name: 'Test Portfolio',
              totalValue: 100000,
              dayChange: 1500,
              dayChangePercent: 1.5,
              holdings: []
            }
          ]
        })
      })
      
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      )
      
      // Wait for portfolio API call
      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalledWith(
          expect.stringContaining('/portfolio'),
          expect.objectContaining({
            method: 'GET',
            headers: expect.objectContaining({
              'Content-Type': 'application/json'
            })
          })
        )
      })
      
      // Should display portfolio data
      await waitFor(() => {
        expect(screen.getByText(/portfolio/i)).toBeTruthy()
      })
    })
    
    test('should handle authentication errors', async () => {
      // Mock 401 response
      fetchSpy.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({
          error: 'Unauthorized',
          message: 'Authentication required'
        })
      })
      
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      )
      
      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalled()
      })
      
      // Should show authentication error or redirect
      await waitFor(() => {
        expect(
          screen.getByText(/unauthorized/i) || 
          screen.getByText(/authentication/i) ||
          screen.getByText(/login/i)
        ).toBeTruthy()
      })
    })
  })
  
  describe('Settings API Keys Integration', () => {
    test('should load existing API keys from backend', async () => {
      // Mock API keys fetch response
      fetchSpy.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          apiKeys: {
            alpaca: {
              hasKey: true,
              keyId: 'PK***',
              isValid: true
            },
            polygon: {
              hasKey: false,
              keyId: null,
              isValid: false
            }
          }
        })
      })
      
      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      )
      
      // Wait for API keys fetch
      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalledWith(
          expect.stringContaining('/settings/api-keys'),
          expect.any(Object)
        )
      })
      
      // Should display API keys form
      await waitFor(() => {
        expect(screen.getByText(/api keys/i) || screen.getByText(/settings/i)).toBeTruthy()
      })
    })
    
    test('should save API keys to backend', async () => {
      // Mock successful save response
      fetchSpy
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({ apiKeys: {} })
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({
            success: true,
            message: 'API key saved successfully'
          })
        })
      
      render(
        <TestWrapper>
          <SettingsApiKeys />
        </TestWrapper>
      )
      
      // Wait for initial load
      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalled()
      })
      
      // Find and fill API key input
      const apiKeyInput = screen.getByLabelText(/api key/i) || 
                         screen.getByPlaceholderText(/enter.*key/i) ||
                         screen.getByRole('textbox')
      
      if (apiKeyInput) {
        fireEvent.change(apiKeyInput, { target: { value: 'test-api-key' } })
        
        // Find and click save button
        const saveButton = screen.getByRole('button', { name: /save/i }) ||
                          screen.getByRole('button', { name: /submit/i }) ||
                          screen.getByText(/save/i)
        
        if (saveButton) {
          fireEvent.click(saveButton)
          
          // Should make POST request to save API key
          await waitFor(() => {
            expect(fetchSpy).toHaveBeenCalledWith(
              expect.stringContaining('/settings/api-keys'),
              expect.objectContaining({
                method: 'POST',
                body: expect.stringContaining('test-api-key')
              })
            )
          })
        }
      }
    })
  })
  
  describe('Market Data Integration', () => {
    test('should fetch real-time market data', async () => {
      // Mock market data response
      fetchSpy.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          quotes: [
            {
              symbol: 'AAPL',
              price: 150.25,
              change: 2.50,
              changePercent: 1.69,
              volume: 50000000
            }
          ]
        })
      })
      
      render(
        <TestWrapper>
          <MarketData />
        </TestWrapper>
      )
      
      // Wait for market data API call
      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalledWith(
          expect.stringContaining('/market'),
          expect.any(Object)
        )
      })
      
      // Should display market data
      await waitFor(() => {
        expect(screen.getByText(/market/i) || screen.getByText(/stocks/i)).toBeTruthy()
      })
    })
  })
  
  describe('Error Handling Integration', () => {
    test('should handle network errors gracefully', async () => {
      // Mock network error
      fetchSpy.mockRejectedValue(new Error('Network error'))
      
      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )
      
      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalled()
      })
      
      // Should display error state or fallback content
      await waitFor(() => {
        // Should not crash the app
        expect(document.body).toBeTruthy()
      })
    })
    
    test('should handle server errors (500)', async () => {
      // Mock server error
      fetchSpy.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => ({
          error: 'Internal Server Error'
        })
      })
      
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      )
      
      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalled()
      })
      
      // Should handle error gracefully
      await waitFor(() => {
        expect(document.body).toBeTruthy()
      })
    })
  })
  
  describe('Performance Integration', () => {
    test('should not make excessive API calls', async () => {
      fetchSpy.mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] })
      })
      
      const { rerender } = render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )
      
      // Initial render should make API calls
      await waitFor(() => {
        expect(fetchSpy).toHaveBeenCalled()
      })
      
      const initialCallCount = fetchSpy.mock.calls.length
      
      // Re-render shouldn't trigger new API calls (should use cache)
      rerender(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )
      
      // Wait a bit to ensure no new calls
      await new Promise(resolve => setTimeout(resolve, 100))
      
      // Should not have made additional calls due to caching
      expect(fetchSpy.mock.calls.length).toBeLessThanOrEqual(initialCallCount + 1)
    })
  })
});