/**
 * PROTECTED COMPONENTS INTEGRATION TESTS
 * Tests all pages and components that require API keys with graceful degradation
 */

import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from '../../components/auth/AuthProvider'
import { ApiKeyProvider } from '../../components/ApiKeyProvider'
import Portfolio from '../../pages/Portfolio'
import TradingSignals from '../../pages/TradingSignals'
import LiveDataEnhanced from '../../pages/LiveDataEnhanced'
import Dashboard from '../../pages/Dashboard'
import Settings from '../../pages/Settings'
import RequiresApiKeys from '../../components/RequiresApiKeys'
import ApiKeyOnboarding from '../../components/ApiKeyOnboarding'
import { dbTestUtils } from '../../../lambda/tests/utils/database-test-utils'

// Mock API calls
jest.mock('../../services/api', () => ({
  get: jest.fn(),
  post: jest.fn(),
  put: jest.fn(),
  delete: jest.fn()
}))

jest.mock('../../services/apiKeyService', () => ({
  getApiKeys: jest.fn(),
  saveApiKeys: jest.fn(),
  validateApiKeys: jest.fn(),
  testConnection: jest.fn()
}))

jest.mock('../../services/liveDataService', () => ({
  connect: jest.fn(),
  disconnect: jest.fn(),
  subscribe: jest.fn(),
  unsubscribe: jest.fn()
}))

const api = require('../../services/api')
const apiKeyService = require('../../services/apiKeyService')
const liveDataService = require('../../services/liveDataService')

// Test wrapper component
const TestWrapper = ({ children, hasApiKeys = false, isAuthenticated = true }) => {
  const mockApiKeys = hasApiKeys ? {
    alpaca_api_key: 'PKTEST123456789',
    alpaca_secret_key: 'test-secret',
    polygon_api_key: 'test-polygon-key',
    finnhub_api_key: 'test-finnhub-key'
  } : null

  const mockUser = isAuthenticated ? {
    sub: 'test-user-123',
    email: 'test@example.com',
    username: 'testuser'
  } : null

  // Mock API key service responses
  apiKeyService.getApiKeys.mockResolvedValue(mockApiKeys)
  
  return (
    <BrowserRouter>
      <AuthProvider initialUser={mockUser}>
        <ApiKeyProvider initialApiKeys={mockApiKeys}>
          {children}
        </ApiKeyProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}

describe('Protected Components Integration Tests', () => {
  beforeAll(async () => {
    await dbTestUtils.initialize()
  })

  afterAll(async () => {
    await dbTestUtils.cleanup()
  })

  beforeEach(() => {
    jest.clearAllMocks()
    
    // Default API mocks
    api.get.mockResolvedValue({ data: { success: true, data: {} } })
    api.post.mockResolvedValue({ data: { success: true, data: {} } })
    apiKeyService.validateApiKeys.mockResolvedValue({ valid: true })
    apiKeyService.testConnection.mockResolvedValue({ success: true })
  })

  describe('Portfolio Page Protection', () => {
    test('shows onboarding when no API keys present', async () => {
      render(
        <TestWrapper hasApiKeys={false}>
          <Portfolio />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText(/API keys required/i)).toBeInTheDocument()
        expect(screen.getByText(/configure your trading accounts/i)).toBeInTheDocument()
      })
    })

    test('shows full portfolio when API keys present', async () => {
      api.get.mockResolvedValue({
        data: {
          success: true,
          data: {
            positions: [
              { symbol: 'AAPL', quantity: 100, avgCost: 150.00, currentPrice: 155.00 },
              { symbol: 'MSFT', quantity: 50, avgCost: 300.00, currentPrice: 310.00 }
            ],
            totalValue: 31000.00,
            totalGainLoss: 1000.00
          }
        }
      })

      render(
        <TestWrapper hasApiKeys={true}>
          <Portfolio />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument()
        expect(screen.getByText('MSFT')).toBeInTheDocument()
        expect(screen.getByText(/31,000/)).toBeInTheDocument()
      })
    })

    test('handles portfolio API errors gracefully', async () => {
      api.get.mockRejectedValue(new Error('Portfolio API failed'))

      render(
        <TestWrapper hasApiKeys={true}>
          <Portfolio />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText(/error loading portfolio/i)).toBeInTheDocument()
        expect(screen.getByText(/retry/i)).toBeInTheDocument()
      })
    })

    test('shows demo data when API keys invalid', async () => {
      apiKeyService.validateApiKeys.mockResolvedValue({ valid: false, error: 'Invalid Alpaca credentials' })
      
      render(
        <TestWrapper hasApiKeys={true}>
          <Portfolio />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText(/demo data/i)).toBeInTheDocument()
        expect(screen.getByText(/update your API keys/i)).toBeInTheDocument()
      })
    })
  })

  describe('Trading Signals Page Protection', () => {
    test('requires API keys for trading signals', async () => {
      render(
        <TestWrapper hasApiKeys={false}>
          <TradingSignals />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText(/trading signals require API access/i)).toBeInTheDocument()
        expect(screen.getByText(/setup API keys/i)).toBeInTheDocument()
      })
    })

    test('displays trading signals with valid API keys', async () => {
      api.get.mockResolvedValue({
        data: {
          success: true,
          data: {
            signals: [
              { symbol: 'TSLA', signal: 'BUY', confidence: 0.85, price: 220.00 },
              { symbol: 'NVDA', signal: 'SELL', confidence: 0.72, price: 450.00 }
            ]
          }
        }
      })

      render(
        <TestWrapper hasApiKeys={true}>
          <TradingSignals />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('TSLA')).toBeInTheDocument()
        expect(screen.getByText('BUY')).toBeInTheDocument()
        expect(screen.getByText('NVDA')).toBeInTheDocument()
        expect(screen.getByText('SELL')).toBeInTheDocument()
      })
    })

    test('filters signals based on user preferences', async () => {
      api.get.mockResolvedValue({
        data: {
          success: true,
          data: {
            signals: [
              { symbol: 'AAPL', signal: 'BUY', confidence: 0.95, price: 155.00 },
              { symbol: 'MSFT', signal: 'BUY', confidence: 0.60, price: 310.00 }
            ]
          }
        }
      })

      render(
        <TestWrapper hasApiKeys={true}>
          <TradingSignals />
        </TestWrapper>
      )

      // Wait for signals to load
      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument()
      })

      // Test confidence filter
      const confidenceFilter = screen.getByLabelText(/minimum confidence/i)
      fireEvent.change(confidenceFilter, { target: { value: '0.8' } })

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument() // 0.95 confidence
        expect(screen.queryByText('MSFT')).not.toBeInTheDocument() // 0.60 confidence filtered out
      })
    })
  })

  describe('Live Data Page Protection', () => {
    test('shows connection setup for live data without API keys', async () => {
      render(
        <TestWrapper hasApiKeys={false}>
          <LiveDataEnhanced />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText(/live data requires API access/i)).toBeInTheDocument()
        expect(screen.getByText(/configure data providers/i)).toBeInTheDocument()
      })
    })

    test('establishes live data connection with valid API keys', async () => {
      liveDataService.connect.mockResolvedValue({ connected: true })
      liveDataService.subscribe.mockImplementation((symbols, callback) => {
        // Simulate live data updates
        setTimeout(() => {
          callback({
            symbol: 'AAPL',
            price: 155.25,
            change: 2.15,
            changePercent: 1.41,
            timestamp: Date.now()
          })
        }, 100)
      })

      render(
        <TestWrapper hasApiKeys={true}>
          <LiveDataEnhanced />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText(/live data connected/i)).toBeInTheDocument()
      })

      // Wait for simulated data update
      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument()
        expect(screen.getByText('155.25')).toBeInTheDocument()
      }, { timeout: 1000 })
    })

    test('handles live data connection failures', async () => {
      liveDataService.connect.mockRejectedValue(new Error('WebSocket connection failed'))

      render(
        <TestWrapper hasApiKeys={true}>
          <LiveDataEnhanced />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText(/connection failed/i)).toBeInTheDocument()
        expect(screen.getByText(/retry connection/i)).toBeInTheDocument()
      })
    })
  })

  describe('Dashboard Page Protection', () => {
    test('shows limited dashboard without API keys', async () => {
      render(
        <TestWrapper hasApiKeys={false}>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText(/limited functionality/i)).toBeInTheDocument()
        expect(screen.getByText(/setup API keys for full access/i)).toBeInTheDocument()
        // Should still show some basic market data
        expect(screen.getByText(/market overview/i)).toBeInTheDocument()
      })
    })

    test('shows full dashboard with API keys', async () => {
      // Mock comprehensive dashboard data
      api.get.mockImplementation((url) => {
        if (url.includes('/portfolio')) {
          return Promise.resolve({
            data: {
              success: true,
              data: { totalValue: 50000, dayGainLoss: 500 }
            }
          })
        }
        if (url.includes('/watchlist')) {
          return Promise.resolve({
            data: {
              success: true,
              data: { symbols: ['AAPL', 'MSFT', 'TSLA'] }
            }
          })
        }
        return Promise.resolve({ data: { success: true, data: {} } })
      })

      render(
        <TestWrapper hasApiKeys={true}>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText(/50,000/)).toBeInTheDocument() // Portfolio value
        expect(screen.getByText(/500/)).toBeInTheDocument() // Day gain/loss
        expect(screen.getByText(/watchlist/i)).toBeInTheDocument()
      })
    })
  })

  describe('Settings Page API Key Management', () => {
    test('shows API key configuration section', async () => {
      render(
        <TestWrapper hasApiKeys={false}>
          <Settings />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText(/API Keys/i)).toBeInTheDocument()
        expect(screen.getByText(/Trading Accounts/i)).toBeInTheDocument()
        expect(screen.getByText(/Data Providers/i)).toBeInTheDocument()
      })
    })

    test('can save API keys through settings', async () => {
      apiKeyService.saveApiKeys.mockResolvedValue({ success: true })

      render(
        <TestWrapper hasApiKeys={false}>
          <Settings />
        </TestWrapper>
      )

      // Fill in API key form
      const alpacaKeyInput = screen.getByLabelText(/alpaca api key/i)
      const alpacaSecretInput = screen.getByLabelText(/alpaca secret key/i)
      
      fireEvent.change(alpacaKeyInput, { target: { value: 'PKTEST123456789' } })
      fireEvent.change(alpacaSecretInput, { target: { value: 'test-secret-key' } })

      const saveButton = screen.getByText(/save api keys/i)
      fireEvent.click(saveButton)

      await waitFor(() => {
        expect(apiKeyService.saveApiKeys).toHaveBeenCalledWith({
          alpaca_api_key: 'PKTEST123456789',
          alpaca_secret_key: 'test-secret-key'
        })
        expect(screen.getByText(/api keys saved successfully/i)).toBeInTheDocument()
      })
    })

    test('validates API key format in settings', async () => {
      render(
        <TestWrapper hasApiKeys={false}>
          <Settings />
        </TestWrapper>
      )

      const alpacaKeyInput = screen.getByLabelText(/alpaca api key/i)
      fireEvent.change(alpacaKeyInput, { target: { value: 'invalid-format' } })
      fireEvent.blur(alpacaKeyInput)

      await waitFor(() => {
        expect(screen.getByText(/invalid alpaca api key format/i)).toBeInTheDocument()
      })
    })
  })

  describe('RequiresApiKeys Component', () => {
    test('blocks access without required API keys', async () => {
      const TestComponent = () => <div>Protected Content</div>

      render(
        <TestWrapper hasApiKeys={false}>
          <RequiresApiKeys requiredProviders={['alpaca']}>
            <TestComponent />
          </RequiresApiKeys>
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
        expect(screen.getByText(/alpaca api keys required/i)).toBeInTheDocument()
      })
    })

    test('allows access with required API keys', async () => {
      const TestComponent = () => <div>Protected Content</div>

      render(
        <TestWrapper hasApiKeys={true}>
          <RequiresApiKeys requiredProviders={['alpaca']}>
            <TestComponent />
          </RequiresApiKeys>
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText('Protected Content')).toBeInTheDocument()
      })
    })

    test('shows custom message for missing providers', async () => {
      const TestComponent = () => <div>Protected Content</div>

      render(
        <TestWrapper hasApiKeys={false}>
          <RequiresApiKeys 
            requiredProviders={['polygon']}
            customMessage="Polygon API access required for market data"
          >
            <TestComponent />
          </RequiresApiKeys>
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText(/polygon api access required for market data/i)).toBeInTheDocument()
      })
    })
  })

  describe('API Key Onboarding Flow', () => {
    test('guides user through API key setup', async () => {
      render(
        <TestWrapper hasApiKeys={false}>
          <ApiKeyOnboarding />
        </TestWrapper>
      )

      // Step 1: Welcome
      await waitFor(() => {
        expect(screen.getByText(/welcome to financial platform/i)).toBeInTheDocument()
        expect(screen.getByText(/get started/i)).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText(/get started/i))

      // Step 2: Provider Selection
      await waitFor(() => {
        expect(screen.getByText(/choose your data providers/i)).toBeInTheDocument()
        expect(screen.getByText(/alpaca/i)).toBeInTheDocument()
        expect(screen.getByText(/polygon/i)).toBeInTheDocument()
      })

      // Select Alpaca
      fireEvent.click(screen.getByText(/alpaca/i))
      fireEvent.click(screen.getByText(/continue/i))

      // Step 3: API Key Entry
      await waitFor(() => {
        expect(screen.getByText(/enter your alpaca api keys/i)).toBeInTheDocument()
        expect(screen.getByLabelText(/api key/i)).toBeInTheDocument()
      })
    })

    test('validates API keys during onboarding', async () => {
      apiKeyService.testConnection.mockResolvedValue({ 
        success: false, 
        error: 'Invalid credentials' 
      })

      render(
        <TestWrapper hasApiKeys={false}>
          <ApiKeyOnboarding />
        </TestWrapper>
      )

      // Navigate to API key entry step
      fireEvent.click(screen.getByText(/get started/i))
      await waitFor(() => screen.getByText(/alpaca/i))
      fireEvent.click(screen.getByText(/alpaca/i))
      fireEvent.click(screen.getByText(/continue/i))

      // Enter invalid API keys
      await waitFor(() => screen.getByLabelText(/api key/i))
      fireEvent.change(screen.getByLabelText(/api key/i), { 
        target: { value: 'invalid-key' } 
      })
      fireEvent.click(screen.getByText(/test connection/i))

      await waitFor(() => {
        expect(screen.getByText(/invalid credentials/i)).toBeInTheDocument()
      })
    })

    test('completes onboarding successfully', async () => {
      apiKeyService.testConnection.mockResolvedValue({ success: true })
      apiKeyService.saveApiKeys.mockResolvedValue({ success: true })

      render(
        <TestWrapper hasApiKeys={false}>
          <ApiKeyOnboarding />
        </TestWrapper>
      )

      // Complete full onboarding flow
      fireEvent.click(screen.getByText(/get started/i))
      await waitFor(() => screen.getByText(/alpaca/i))
      fireEvent.click(screen.getByText(/alpaca/i))
      fireEvent.click(screen.getByText(/continue/i))

      await waitFor(() => screen.getByLabelText(/api key/i))
      fireEvent.change(screen.getByLabelText(/api key/i), { 
        target: { value: 'PKTEST123456789' } 
      })
      fireEvent.change(screen.getByLabelText(/secret key/i), { 
        target: { value: 'test-secret' } 
      })
      fireEvent.click(screen.getByText(/save and continue/i))

      await waitFor(() => {
        expect(screen.getByText(/setup complete/i)).toBeInTheDocument()
        expect(screen.getByText(/start trading/i)).toBeInTheDocument()
      })
    })
  })

  describe('Error Handling and Recovery', () => {
    test('handles API service outages gracefully', async () => {
      api.get.mockRejectedValue(new Error('Service temporarily unavailable'))

      render(
        <TestWrapper hasApiKeys={true}>
          <Portfolio />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText(/service temporarily unavailable/i)).toBeInTheDocument()
        expect(screen.getByText(/using cached data/i)).toBeInTheDocument()
      })
    })

    test('shows API key expiration warnings', async () => {
      apiKeyService.validateApiKeys.mockResolvedValue({ 
        valid: false, 
        error: 'API key expired',
        needsRenewal: true
      })

      render(
        <TestWrapper hasApiKeys={true}>
          <Portfolio />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText(/api key expired/i)).toBeInTheDocument()
        expect(screen.getByText(/renew your api keys/i)).toBeInTheDocument()
      })
    })

    test('handles network connectivity issues', async () => {
      api.get.mockRejectedValue(new Error('Network Error'))

      render(
        <TestWrapper hasApiKeys={true}>
          <Dashboard />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText(/network error/i)).toBeInTheDocument()
        expect(screen.getByText(/check your connection/i)).toBeInTheDocument()
      })
    })
  })
})