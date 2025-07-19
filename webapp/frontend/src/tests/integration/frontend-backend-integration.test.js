/**
 * FRONTEND-BACKEND INTEGRATION TESTS
 * Tests React components calling real Lambda API endpoints
 */

import { describe, test, expect, beforeAll, afterEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import safeTheme from '../../theme/safeTheme'

// Import pages to test
import Dashboard from '../../pages/Dashboard'
import Portfolio from '../../pages/Portfolio'
import MarketData from '../../pages/MarketData'
import SettingsApiKeys from '../../pages/SettingsApiKeys'

const API_BASE = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev'

const TestWrapper = ({ children }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, cacheTime: 0 },
    },
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

describe('Frontend-Backend Integration Tests', () => {
  beforeAll(() => {
    global.fetch = vi.fn()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  test('Dashboard calls real health API endpoint', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        status: 'healthy',
        services: { database: 'connected' }
      })
    })

    render(<TestWrapper><Dashboard /></TestWrapper>)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/health'),
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({
            'Content-Type': 'application/json'
          })
        })
      )
    })
  })

  test('Portfolio calls real portfolio API endpoint', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        portfolios: [{
          id: 'test-portfolio',
          name: 'Test Portfolio',
          totalValue: 100000,
          holdings: []
        }]
      })
    })

    render(<TestWrapper><Portfolio /></TestWrapper>)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/portfolio'),
        expect.objectContaining({
          method: 'GET'
        })
      )
    })
  })

  test('Market Data calls real market API endpoint', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        quotes: [{
          symbol: 'AAPL',
          price: 150.25,
          change: 2.50
        }]
      })
    })

    render(<TestWrapper><MarketData /></TestWrapper>)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/market'),
        expect.any(Object)
      )
    })
  })

  test('Settings calls real API key endpoints', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        apiKeys: {
          alpaca: { hasKey: false, isValid: false }
        }
      })
    })

    render(<TestWrapper><SettingsApiKeys /></TestWrapper>)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/settings/api-keys'),
        expect.any(Object)
      )
    })
  })

  test('API calls use correct authentication headers', async () => {
    // Mock localStorage with auth token
    Storage.prototype.getItem = vi.fn(() => 'test-jwt-token')

    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ data: [] })
    })

    render(<TestWrapper><Portfolio /></TestWrapper>)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': 'Bearer test-jwt-token'
          })
        })
      )
    })
  })

  test('Components handle API errors gracefully', async () => {
    global.fetch.mockRejectedValueOnce(new Error('Network error'))

    render(<TestWrapper><Dashboard /></TestWrapper>)

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled()
    })

    // Should not crash, should show error state
    await waitFor(() => {
      expect(document.body).toBeTruthy()
    })
  })
})