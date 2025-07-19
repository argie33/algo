/**
 * COMPLETE USER JOURNEY INTEGRATION TESTS
 * Tests end-to-end user workflows from login through API key setup to data access
 */

import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from '../../components/auth/AuthProvider'
import { ApiKeyProvider } from '../../components/ApiKeyProvider'
import App from '../../App'

// Mock services
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

// Test utilities
const TestWrapper = ({ children, initialUser = null, initialApiKeys = null }) => (
  <BrowserRouter>
    <AuthProvider initialUser={initialUser}>
      <ApiKeyProvider initialApiKeys={initialApiKeys}>
        {children}
      </ApiKeyProvider>
    </AuthProvider>
  </BrowserRouter>
)

describe('Complete User Journey Integration Tests', () => {
  let user

  beforeEach(async () => {
    user = userEvent.setup()
    jest.clearAllMocks()

    // Default successful API responses
    api.get.mockResolvedValue({ data: { success: true, data: {} } })
    api.post.mockResolvedValue({ data: { success: true, data: {} } })
    apiKeyService.getApiKeys.mockResolvedValue(null)
    apiKeyService.saveApiKeys.mockResolvedValue({ success: true })
    apiKeyService.validateApiKeys.mockResolvedValue({ valid: true })
    apiKeyService.testConnection.mockResolvedValue({ success: true })
  })

  describe('New User Journey - No API Keys', () => {
    test('complete new user onboarding flow', async () => {
      const newUser = {
        sub: 'new-user-123',
        email: 'newuser@example.com',
        username: 'newuser'
      }

      render(
        <TestWrapper initialUser={newUser}>
          <App />
        </TestWrapper>
      )

      // 1. User lands on dashboard but sees limited functionality
      await waitFor(() => {
        expect(screen.getByText(/welcome/i)).toBeInTheDocument()
        expect(screen.getByText(/setup api keys/i)).toBeInTheDocument()
      })

      // 2. User clicks to set up API keys
      fireEvent.click(screen.getByText(/setup api keys/i))

      // 3. Onboarding wizard starts
      await waitFor(() => {
        expect(screen.getByText(/welcome to financial platform/i)).toBeInTheDocument()
        expect(screen.getByText(/get started/i)).toBeInTheDocument()
      })

      // 4. User proceeds through welcome step
      fireEvent.click(screen.getByText(/get started/i))

      // 5. Provider selection screen
      await waitFor(() => {
        expect(screen.getByText(/choose your data providers/i)).toBeInTheDocument()
        expect(screen.getByText(/alpaca/i)).toBeInTheDocument()
      })

      // 6. User selects Alpaca
      fireEvent.click(screen.getByText(/alpaca/i))
      fireEvent.click(screen.getByText(/continue/i))

      // 7. API key entry form
      await waitFor(() => {
        expect(screen.getByText(/enter your alpaca api keys/i)).toBeInTheDocument()
      })

      const apiKeyInput = screen.getByLabelText(/api key/i)
      const secretKeyInput = screen.getByLabelText(/secret key/i)

      await user.type(apiKeyInput, 'PKTEST123456789')
      await user.type(secretKeyInput, 'test-secret-key')

      // 8. Test connection
      apiKeyService.testConnection.mockResolvedValue({ 
        success: true, 
        data: { account: 'test-account', balance: 10000 }
      })

      fireEvent.click(screen.getByText(/test connection/i))

      await waitFor(() => {
        expect(screen.getByText(/connection successful/i)).toBeInTheDocument()
      })

      // 9. Save and complete setup
      apiKeyService.saveApiKeys.mockResolvedValue({ 
        success: true,
        data: { 
          alpaca_api_key: 'PKTEST123456789',
          alpaca_secret_key: 'test-secret-key'
        }
      })

      fireEvent.click(screen.getByText(/save and continue/i))

      // 10. Setup completion
      await waitFor(() => {
        expect(screen.getByText(/setup complete/i)).toBeInTheDocument()
        expect(screen.getByText(/start trading/i)).toBeInTheDocument()
      })

      // 11. Navigate to dashboard with full functionality
      fireEvent.click(screen.getByText(/start trading/i))

      await waitFor(() => {
        expect(screen.getByText(/portfolio/i)).toBeInTheDocument()
        expect(screen.queryByText(/setup api keys/i)).not.toBeInTheDocument()
      })
    })

    test('user tries to access protected pages without API keys', async () => {
      const userWithoutKeys = {
        sub: 'user-no-keys',
        email: 'nokeys@example.com',
        username: 'nokeys'
      }

      render(
        <TestWrapper initialUser={userWithoutKeys}>
          <App />
        </TestWrapper>
      )

      // Try to navigate to portfolio
      fireEvent.click(screen.getByText(/portfolio/i))

      await waitFor(() => {
        expect(screen.getByText(/api keys required/i)).toBeInTheDocument()
        expect(screen.getByText(/configure your trading accounts/i)).toBeInTheDocument()
      })

      // Try to navigate to trading signals
      fireEvent.click(screen.getByText(/trading signals/i))

      await waitFor(() => {
        expect(screen.getByText(/trading signals require api access/i)).toBeInTheDocument()
      })

      // Dashboard should show limited functionality
      fireEvent.click(screen.getByText(/dashboard/i))

      await waitFor(() => {
        expect(screen.getByText(/limited functionality/i)).toBeInTheDocument()
        expect(screen.getByText(/setup api keys for full access/i)).toBeInTheDocument()
      })
    })
  })

  describe('Existing User Journey - With API Keys', () => {
    test('user with existing API keys gets full functionality', async () => {
      const existingUser = {
        sub: 'existing-user-456',
        email: 'existing@example.com',
        username: 'existing'
      }

      const existingApiKeys = {
        alpaca_api_key: 'PKTEST987654321',
        alpaca_secret_key: 'existing-secret',
        polygon_api_key: 'existing-polygon-key'
      }

      // Mock portfolio data
      api.get.mockImplementation((url) => {
        if (url.includes('/portfolio')) {
          return Promise.resolve({
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
        }
        if (url.includes('/signals')) {
          return Promise.resolve({
            data: {
              success: true,
              data: {
                signals: [
                  { symbol: 'TSLA', signal: 'BUY', confidence: 0.85, price: 220.00 }
                ]
              }
            }
          })
        }
        return Promise.resolve({ data: { success: true, data: {} } })
      })

      render(
        <TestWrapper initialUser={existingUser} initialApiKeys={existingApiKeys}>
          <App />
        </TestWrapper>
      )

      // Dashboard should show full functionality
      await waitFor(() => {
        expect(screen.getByText(/31,000/)).toBeInTheDocument() // Portfolio value
        expect(screen.queryByText(/setup api keys/i)).not.toBeInTheDocument()
      })

      // Portfolio page should show positions
      fireEvent.click(screen.getByText(/portfolio/i))

      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument()
        expect(screen.getByText('MSFT')).toBeInTheDocument()
        expect(screen.getByText(/31,000/)).toBeInTheDocument()
      })

      // Trading signals should work
      fireEvent.click(screen.getByText(/trading signals/i))

      await waitFor(() => {
        expect(screen.getByText('TSLA')).toBeInTheDocument()
        expect(screen.getByText('BUY')).toBeInTheDocument()
      })
    })

    test('user can manage existing API keys', async () => {
      const userWithKeys = {
        sub: 'user-with-keys',
        email: 'withkeys@example.com',
        username: 'withkeys'
      }

      const currentApiKeys = {
        alpaca_api_key: 'PKTEST123456789',
        polygon_api_key: 'current-polygon-key'
      }

      apiKeyService.getApiKeys.mockResolvedValue(currentApiKeys)

      render(
        <TestWrapper initialUser={userWithKeys} initialApiKeys={currentApiKeys}>
          <App />
        </TestWrapper>
      )

      // Navigate to settings
      fireEvent.click(screen.getByText(/settings/i))

      await waitFor(() => {
        expect(screen.getByText(/api keys/i)).toBeInTheDocument()
      })

      // Should see current API keys (masked)
      await waitFor(() => {
        expect(screen.getByText(/alpaca/i)).toBeInTheDocument()
        expect(screen.getByText(/polygon/i)).toBeInTheDocument()
      })

      // User adds new Finnhub API key
      const finnhubInput = screen.getByLabelText(/finnhub api key/i)
      await user.type(finnhubInput, 'new-finnhub-key-123')

      apiKeyService.saveApiKeys.mockResolvedValue({ 
        success: true,
        data: {
          ...currentApiKeys,
          finnhub_api_key: 'new-finnhub-key-123'
        }
      })

      fireEvent.click(screen.getByText(/save api keys/i))

      await waitFor(() => {
        expect(screen.getByText(/api keys saved successfully/i)).toBeInTheDocument()
      })

      // Test connection for new key
      apiKeyService.testConnection.mockResolvedValue({ success: true })

      fireEvent.click(screen.getByText(/test finnhub connection/i))

      await waitFor(() => {
        expect(screen.getByText(/finnhub connection successful/i)).toBeInTheDocument()
      })
    })
  })

  describe('Error Recovery User Journey', () => {
    test('user recovers from API service failures', async () => {
      const resilientUser = {
        sub: 'resilient-user',
        email: 'resilient@example.com',
        username: 'resilient'
      }

      const workingApiKeys = {
        alpaca_api_key: 'PKTEST123456789',
        alpaca_secret_key: 'working-secret'
      }

      // Simulate API failure initially
      api.get.mockRejectedValueOnce(new Error('Service temporarily unavailable'))

      render(
        <TestWrapper initialUser={resilientUser} initialApiKeys={workingApiKeys}>
          <App />
        </TestWrapper>
      )

      // Navigate to portfolio
      fireEvent.click(screen.getByText(/portfolio/i))

      // Should show error message
      await waitFor(() => {
        expect(screen.getByText(/service temporarily unavailable/i)).toBeInTheDocument()
        expect(screen.getByText(/retry/i)).toBeInTheDocument()
      })

      // Fix API and retry
      api.get.mockResolvedValue({
        data: {
          success: true,
          data: {
            positions: [{ symbol: 'AAPL', quantity: 100, avgCost: 150.00, currentPrice: 155.00 }],
            totalValue: 15500.00
          }
        }
      })

      fireEvent.click(screen.getByText(/retry/i))

      // Should now show portfolio data
      await waitFor(() => {
        expect(screen.getByText('AAPL')).toBeInTheDocument()
        expect(screen.getByText(/15,500/)).toBeInTheDocument()
        expect(screen.queryByText(/service temporarily unavailable/i)).not.toBeInTheDocument()
      })
    })

    test('user handles API key expiration gracefully', async () => {
      const userWithExpiredKeys = {
        sub: 'expired-keys-user',
        email: 'expired@example.com',
        username: 'expired'
      }

      const expiredApiKeys = {
        alpaca_api_key: 'PKTEST_expired',
        alpaca_secret_key: 'expired-secret'
      }

      // Simulate API key validation failure
      apiKeyService.validateApiKeys.mockResolvedValue({
        valid: false,
        error: 'API key expired',
        needsRenewal: true
      })

      render(
        <TestWrapper initialUser={userWithExpiredKeys} initialApiKeys={expiredApiKeys}>
          <App />
        </TestWrapper>
      )

      // Navigate to portfolio
      fireEvent.click(screen.getByText(/portfolio/i))

      // Should show API key expiration warning
      await waitFor(() => {
        expect(screen.getByText(/api key expired/i)).toBeInTheDocument()
        expect(screen.getByText(/renew your api keys/i)).toBeInTheDocument()
      })

      // User clicks to renew keys
      fireEvent.click(screen.getByText(/renew your api keys/i))

      // Should navigate to settings
      await waitFor(() => {
        expect(screen.getByText(/api keys/i)).toBeInTheDocument()
        expect(screen.getByText(/update your credentials/i)).toBeInTheDocument()
      })

      // User enters new API key
      const newApiKeyInput = screen.getByLabelText(/alpaca api key/i)
      await user.clear(newApiKeyInput)
      await user.type(newApiKeyInput, 'PKTEST_renewed_key')

      // Save renewed keys
      apiKeyService.validateApiKeys.mockResolvedValue({ valid: true })
      apiKeyService.saveApiKeys.mockResolvedValue({ success: true })

      fireEvent.click(screen.getByText(/save api keys/i))

      await waitFor(() => {
        expect(screen.getByText(/api keys updated successfully/i)).toBeInTheDocument()
      })
    })
  })

  describe('Multi-Provider User Journey', () => {
    test('user sets up multiple data providers', async () => {
      const powerUser = {
        sub: 'power-user',
        email: 'power@example.com',
        username: 'poweruser'
      }

      render(
        <TestWrapper initialUser={powerUser}>
          <App />
        </TestWrapper>
      )

      // Start with API key setup
      fireEvent.click(screen.getByText(/setup api keys/i))

      // Go through onboarding
      await waitFor(() => screen.getByText(/get started/i))
      fireEvent.click(screen.getByText(/get started/i))

      // Select multiple providers
      await waitFor(() => screen.getByText(/choose your data providers/i))
      
      fireEvent.click(screen.getByText(/alpaca/i))
      fireEvent.click(screen.getByText(/polygon/i))
      fireEvent.click(screen.getByText(/finnhub/i))
      fireEvent.click(screen.getByText(/continue/i))

      // Enter Alpaca credentials
      await waitFor(() => screen.getByText(/enter your alpaca api keys/i))
      
      await user.type(screen.getByLabelText(/api key/i), 'PKTEST123456789')
      await user.type(screen.getByLabelText(/secret key/i), 'alpaca-secret')
      
      fireEvent.click(screen.getByText(/next provider/i))

      // Enter Polygon credentials
      await waitFor(() => screen.getByText(/enter your polygon api key/i))
      
      await user.type(screen.getByLabelText(/polygon api key/i), 'polygon-key-123')
      
      fireEvent.click(screen.getByText(/next provider/i))

      // Enter Finnhub credentials
      await waitFor(() => screen.getByText(/enter your finnhub api key/i))
      
      await user.type(screen.getByLabelText(/finnhub api key/i), 'finnhub-key-456')

      // Test all connections
      apiKeyService.testConnection.mockResolvedValue({ success: true })
      
      fireEvent.click(screen.getByText(/test all connections/i))

      await waitFor(() => {
        expect(screen.getByText(/all providers connected successfully/i)).toBeInTheDocument()
      })

      // Save all keys
      apiKeyService.saveApiKeys.mockResolvedValue({
        success: true,
        data: {
          alpaca_api_key: 'PKTEST123456789',
          alpaca_secret_key: 'alpaca-secret',
          polygon_api_key: 'polygon-key-123',
          finnhub_api_key: 'finnhub-key-456'
        }
      })

      fireEvent.click(screen.getByText(/save all and continue/i))

      // Complete setup
      await waitFor(() => {
        expect(screen.getByText(/multi-provider setup complete/i)).toBeInTheDocument()
        expect(screen.getByText(/3 providers configured/i)).toBeInTheDocument()
      })
    })

    test('user manages mixed provider functionality', async () => {
      const partialUser = {
        sub: 'partial-user',
        email: 'partial@example.com', 
        username: 'partial'
      }

      const partialApiKeys = {
        alpaca_api_key: 'PKTEST123456789',
        alpaca_secret_key: 'alpaca-secret'
        // Missing polygon and finnhub
      }

      // Mock different responses based on provider availability
      api.get.mockImplementation((url) => {
        if (url.includes('/portfolio')) {
          return Promise.resolve({
            data: {
              success: true,
              data: { positions: [], totalValue: 0 }
            }
          })
        }
        if (url.includes('/market-data')) {
          return Promise.resolve({
            data: {
              success: false,
              error: 'Polygon API key required for market data'
            }
          })
        }
        return Promise.resolve({ data: { success: true, data: {} } })
      })

      render(
        <TestWrapper initialUser={partialUser} initialApiKeys={partialApiKeys}>
          <App />
        </TestWrapper>
      )

      // Portfolio should work (has Alpaca)
      fireEvent.click(screen.getByText(/portfolio/i))

      await waitFor(() => {
        expect(screen.getByText(/portfolio/i)).toBeInTheDocument()
        expect(screen.queryByText(/api keys required/i)).not.toBeInTheDocument()
      })

      // Market data should show upgrade prompt
      fireEvent.click(screen.getByText(/market data/i))

      await waitFor(() => {
        expect(screen.getByText(/polygon api key required/i)).toBeInTheDocument()
        expect(screen.getByText(/upgrade your data access/i)).toBeInTheDocument()
      })

      // User clicks to add Polygon
      fireEvent.click(screen.getByText(/add polygon api/i))

      // Should navigate to settings
      await waitFor(() => {
        expect(screen.getByText(/add polygon api key/i)).toBeInTheDocument()
      })

      // Add Polygon key
      await user.type(screen.getByLabelText(/polygon api key/i), 'new-polygon-key')
      
      apiKeyService.saveApiKeys.mockResolvedValue({ success: true })
      
      fireEvent.click(screen.getByText(/save polygon key/i))

      await waitFor(() => {
        expect(screen.getByText(/polygon api key added/i)).toBeInTheDocument()
      })
    })
  })

  describe('Performance and User Experience', () => {
    test('app loads quickly for returning users', async () => {
      const returningUser = {
        sub: 'returning-user',
        email: 'returning@example.com',
        username: 'returning'
      }

      const cachedApiKeys = {
        alpaca_api_key: 'PKTEST123456789',
        polygon_api_key: 'cached-polygon-key'
      }

      const startTime = Date.now()

      render(
        <TestWrapper initialUser={returningUser} initialApiKeys={cachedApiKeys}>
          <App />
        </TestWrapper>
      )

      // Should load dashboard quickly
      await waitFor(() => {
        expect(screen.getByText(/dashboard/i)).toBeInTheDocument()
      })

      const loadTime = Date.now() - startTime
      expect(loadTime).toBeLessThan(1000) // Should load within 1 second
    })

    test('handles slow API responses gracefully', async () => {
      const patientUser = {
        sub: 'patient-user',
        email: 'patient@example.com',
        username: 'patient'
      }

      // Simulate slow API response
      api.get.mockImplementation(() => {
        return new Promise(resolve => {
          setTimeout(() => {
            resolve({
              data: {
                success: true,
                data: { positions: [], totalValue: 0 }
              }
            })
          }, 2000) // 2 second delay
        })
      })

      render(
        <TestWrapper initialUser={patientUser}>
          <App />
        </TestWrapper>
      )

      fireEvent.click(screen.getByText(/portfolio/i))

      // Should show loading state
      await waitFor(() => {
        expect(screen.getByText(/loading/i)).toBeInTheDocument()
      })

      // Should eventually load data
      await waitFor(() => {
        expect(screen.getByText(/portfolio/i)).toBeInTheDocument()
        expect(screen.queryByText(/loading/i)).not.toBeInTheDocument()
      }, { timeout: 3000 })
    })
  })
})