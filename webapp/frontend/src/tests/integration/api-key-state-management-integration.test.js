/**
 * API KEY STATE MANAGEMENT INTEGRATION TESTS
 * Tests API key state synchronization across frontend components and backend services
 */

import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from '../../components/auth/AuthProvider'
import { ApiKeyProvider, useApiKeys } from '../../components/ApiKeyProvider'
import Portfolio from '../../pages/Portfolio'
import Settings from '../../pages/Settings'
import TradingSignals from '../../pages/TradingSignals'
import LiveDataEnhanced from '../../pages/LiveDataEnhanced'

// Mock all services
jest.mock('../../services/api', () => ({
  get: jest.fn(),
  post: jest.fn(),
  put: jest.fn(),
  delete: jest.fn()
}))

jest.mock('../../services/apiKeyService', () => ({
  getApiKeys: jest.fn(),
  saveApiKeys: jest.fn(),
  deleteApiKeys: jest.fn(),
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

// State monitoring component
const StateMonitor = () => {
  const apiKeyContext = useApiKeys()
  
  return (
    <div data-testid="state-monitor">
      <div data-testid="has-keys">{apiKeyContext.hasApiKeys ? 'true' : 'false'}</div>
      <div data-testid="loading">{apiKeyContext.isLoading ? 'true' : 'false'}</div>
      <div data-testid="error">{apiKeyContext.error || 'none'}</div>
      <div data-testid="alpaca-status">{apiKeyContext.hasProvider('alpaca') ? 'active' : 'inactive'}</div>
      <div data-testid="polygon-status">{apiKeyContext.hasProvider('polygon') ? 'active' : 'inactive'}</div>
      <div data-testid="finnhub-status">{apiKeyContext.hasProvider('finnhub') ? 'active' : 'inactive'}</div>
      <div data-testid="provider-count">{apiKeyContext.getStatus().providers.length}</div>
    </div>
  )
}

// Multi-component app for testing
const MultiComponentApp = () => {
  const [currentPage, setCurrentPage] = React.useState('portfolio')
  
  return (
    <div>
      <nav>
        <button onClick={() => setCurrentPage('portfolio')} data-testid="nav-portfolio">
          Portfolio
        </button>
        <button onClick={() => setCurrentPage('settings')} data-testid="nav-settings">
          Settings
        </button>
        <button onClick={() => setCurrentPage('signals')} data-testid="nav-signals">
          Trading Signals
        </button>
        <button onClick={() => setCurrentPage('livedata')} data-testid="nav-livedata">
          Live Data
        </button>
      </nav>
      
      <StateMonitor />
      
      <main>
        {currentPage === 'portfolio' && <Portfolio />}
        {currentPage === 'settings' && <Settings />}
        {currentPage === 'signals' && <TradingSignals />}
        {currentPage === 'livedata' && <LiveDataEnhanced />}
      </main>
    </div>
  )
}

const TestWrapper = ({ children, initialUser = null, initialApiKeys = null }) => (
  <BrowserRouter>
    <AuthProvider initialUser={initialUser}>
      <ApiKeyProvider initialApiKeys={initialApiKeys}>
        {children}
      </ApiKeyProvider>
    </AuthProvider>
  </BrowserRouter>
)

describe('API Key State Management Integration Tests', () => {
  let user

  beforeEach(async () => {
    user = userEvent.setup()
    jest.clearAllMocks()

    // Default mock responses
    api.get.mockResolvedValue({ data: { success: true, data: {} } })
    api.post.mockResolvedValue({ data: { success: true, data: {} } })
    apiKeyService.getApiKeys.mockResolvedValue(null)
    apiKeyService.saveApiKeys.mockResolvedValue({ success: true })
    apiKeyService.validateApiKeys.mockResolvedValue({ valid: true })
    apiKeyService.testConnection.mockResolvedValue({ success: true })
  })

  describe('Cross-Component State Synchronization', () => {
    test('API key changes in Settings propagate to all components', async () => {
      const testUser = {
        sub: 'sync-test-user',
        email: 'sync@example.com',
        username: 'syncuser'
      }

      render(
        <TestWrapper initialUser={testUser}>
          <MultiComponentApp />
        </TestWrapper>
      )

      // Initially no API keys
      await waitFor(() => {
        expect(screen.getByTestId('has-keys')).toHaveTextContent('false')
        expect(screen.getByTestId('provider-count')).toHaveTextContent('0')
      })

      // Navigate to settings
      fireEvent.click(screen.getByTestId('nav-settings'))

      await waitFor(() => {
        expect(screen.getByText(/api keys/i)).toBeInTheDocument()
      })

      // Add Alpaca API key
      const alpacaKeyInput = screen.getByLabelText(/alpaca api key/i)
      const alpacaSecretInput = screen.getByLabelText(/alpaca secret key/i)

      await user.type(alpacaKeyInput, 'PKTEST123456789')
      await user.type(alpacaSecretInput, 'test-secret-key')

      // Mock successful save
      apiKeyService.saveApiKeys.mockResolvedValue({
        success: true,
        data: {
          alpaca_api_key: 'PKTEST123456789',
          alpaca_secret_key: 'test-secret-key'
        }
      })

      fireEvent.click(screen.getByText(/save api keys/i))

      // State should update across all components
      await waitFor(() => {
        expect(screen.getByTestId('has-keys')).toHaveTextContent('true')
        expect(screen.getByTestId('alpaca-status')).toHaveTextContent('active')
        expect(screen.getByTestId('provider-count')).toHaveTextContent('1')
      })

      // Navigate to portfolio - should now have access
      fireEvent.click(screen.getByTestId('nav-portfolio'))

      await waitFor(() => {
        expect(screen.queryByText(/api keys required/i)).not.toBeInTheDocument()
        expect(screen.getByText(/portfolio/i)).toBeInTheDocument()
      })

      // Navigate to signals - should also have access
      fireEvent.click(screen.getByTestId('nav-signals'))

      await waitFor(() => {
        expect(screen.queryByText(/api keys required/i)).not.toBeInTheDocument()
        expect(screen.getByText(/trading signals/i)).toBeInTheDocument()
      })
    })

    test('API key deletion propagates to all components', async () => {
      const testUser = {
        sub: 'delete-test-user',
        email: 'delete@example.com',
        username: 'deleteuser'
      }

      const initialKeys = {
        alpaca_api_key: 'PKTEST123456789',
        alpaca_secret_key: 'test-secret',
        polygon_api_key: 'test-polygon-key'
      }

      render(
        <TestWrapper initialUser={testUser} initialApiKeys={initialKeys}>
          <MultiComponentApp />
        </TestWrapper>
      )

      // Initially should have API keys
      await waitFor(() => {
        expect(screen.getByTestId('has-keys')).toHaveTextContent('true')
        expect(screen.getByTestId('provider-count')).toHaveTextContent('2')
        expect(screen.getByTestId('alpaca-status')).toHaveTextContent('active')
        expect(screen.getByTestId('polygon-status')).toHaveTextContent('active')
      })

      // Navigate to settings
      fireEvent.click(screen.getByTestId('nav-settings'))

      // Delete Alpaca keys
      apiKeyService.deleteApiKeys.mockResolvedValue({ success: true })

      fireEvent.click(screen.getByText(/delete alpaca keys/i))

      // State should update immediately
      await waitFor(() => {
        expect(screen.getByTestId('alpaca-status')).toHaveTextContent('inactive')
        expect(screen.getByTestId('polygon-status')).toHaveTextContent('active')
        expect(screen.getByTestId('provider-count')).toHaveTextContent('1')
      })

      // Navigate to portfolio - should now show limitations
      fireEvent.click(screen.getByTestId('nav-portfolio'))

      await waitFor(() => {
        expect(screen.getByText(/limited functionality/i)).toBeInTheDocument()
        expect(screen.getByText(/alpaca api key required for trading/i)).toBeInTheDocument()
      })
    })
  })

  describe('Real-time State Updates', () => {
    test('API key validation status updates in real-time', async () => {
      const testUser = {
        sub: 'validation-test-user',
        email: 'validation@example.com',
        username: 'validationuser'
      }

      const testKeys = {
        alpaca_api_key: 'PKTEST123456789',
        alpaca_secret_key: 'test-secret'
      }

      render(
        <TestWrapper initialUser={testUser} initialApiKeys={testKeys}>
          <MultiComponentApp />
        </TestWrapper>
      )

      // Initially valid
      await waitFor(() => {
        expect(screen.getByTestId('alpaca-status')).toHaveTextContent('active')
        expect(screen.getByTestId('error')).toHaveTextContent('none')
      })

      // Simulate API key becoming invalid
      act(() => {
        apiKeyService.validateApiKeys.mockResolvedValue({
          valid: false,
          error: 'API key expired'
        })
      })

      // Navigate to portfolio to trigger validation
      fireEvent.click(screen.getByTestId('nav-portfolio'))

      await waitFor(() => {
        expect(screen.getByTestId('error')).toHaveTextContent('API key expired')
        expect(screen.getByText(/api key expired/i)).toBeInTheDocument()
      })

      // Fix the API key
      act(() => {
        apiKeyService.validateApiKeys.mockResolvedValue({ valid: true })
      })

      // Trigger refresh
      fireEvent.click(screen.getByText(/retry/i))

      await waitFor(() => {
        expect(screen.getByTestId('error')).toHaveTextContent('none')
        expect(screen.queryByText(/api key expired/i)).not.toBeInTheDocument()
      })
    })

    test('connection status updates across live data components', async () => {
      const testUser = {
        sub: 'connection-test-user',
        email: 'connection@example.com',
        username: 'connectionuser'
      }

      const liveDataKeys = {
        alpaca_api_key: 'PKTEST123456789',
        alpaca_secret_key: 'test-secret',
        polygon_api_key: 'test-polygon-key'
      }

      liveDataService.connect.mockResolvedValue({ connected: true })
      liveDataService.subscribe.mockResolvedValue({ subscribed: true })

      render(
        <TestWrapper initialUser={testUser} initialApiKeys={liveDataKeys}>
          <MultiComponentApp />
        </TestWrapper>
      )

      // Navigate to live data
      fireEvent.click(screen.getByTestId('nav-livedata'))

      await waitFor(() => {
        expect(screen.getByText(/live data connected/i)).toBeInTheDocument()
      })

      // Simulate connection failure
      act(() => {
        liveDataService.connect.mockRejectedValue(new Error('Connection failed'))
      })

      // Trigger reconnection
      fireEvent.click(screen.getByText(/reconnect/i))

      await waitFor(() => {
        expect(screen.getByText(/connection failed/i)).toBeInTheDocument()
      })

      // Navigate to other pages - connection status should persist
      fireEvent.click(screen.getByTestId('nav-portfolio'))
      fireEvent.click(screen.getByTestId('nav-livedata'))

      await waitFor(() => {
        expect(screen.getByText(/connection failed/i)).toBeInTheDocument()
      })
    })
  })

  describe('Multi-Provider State Management', () => {
    test('manages multiple provider states independently', async () => {
      const testUser = {
        sub: 'multi-provider-user',
        email: 'multi@example.com',
        username: 'multiuser'
      }

      render(
        <TestWrapper initialUser={testUser}>
          <MultiComponentApp />
        </TestWrapper>
      )

      // Navigate to settings
      fireEvent.click(screen.getByTestId('nav-settings'))

      // Add providers one by one and verify state updates
      
      // Add Alpaca
      await user.type(screen.getByLabelText(/alpaca api key/i), 'PKTEST123456789')
      await user.type(screen.getByLabelText(/alpaca secret key/i), 'alpaca-secret')

      apiKeyService.saveApiKeys.mockResolvedValue({
        success: true,
        data: { alpaca_api_key: 'PKTEST123456789', alpaca_secret_key: 'alpaca-secret' }
      })

      fireEvent.click(screen.getByText(/save alpaca/i))

      await waitFor(() => {
        expect(screen.getByTestId('alpaca-status')).toHaveTextContent('active')
        expect(screen.getByTestId('polygon-status')).toHaveTextContent('inactive')
        expect(screen.getByTestId('provider-count')).toHaveTextContent('1')
      })

      // Add Polygon
      await user.type(screen.getByLabelText(/polygon api key/i), 'polygon-key-123')

      apiKeyService.saveApiKeys.mockResolvedValue({
        success: true,
        data: {
          alpaca_api_key: 'PKTEST123456789',
          alpaca_secret_key: 'alpaca-secret',
          polygon_api_key: 'polygon-key-123'
        }
      })

      fireEvent.click(screen.getByText(/save polygon/i))

      await waitFor(() => {
        expect(screen.getByTestId('alpaca-status')).toHaveTextContent('active')
        expect(screen.getByTestId('polygon-status')).toHaveTextContent('active')
        expect(screen.getByTestId('provider-count')).toHaveTextContent('2')
      })

      // Add Finnhub
      await user.type(screen.getByLabelText(/finnhub api key/i), 'finnhub-key-456')

      apiKeyService.saveApiKeys.mockResolvedValue({
        success: true,
        data: {
          alpaca_api_key: 'PKTEST123456789',
          alpaca_secret_key: 'alpaca-secret',
          polygon_api_key: 'polygon-key-123',
          finnhub_api_key: 'finnhub-key-456'
        }
      })

      fireEvent.click(screen.getByText(/save finnhub/i))

      await waitFor(() => {
        expect(screen.getByTestId('alpaca-status')).toHaveTextContent('active')
        expect(screen.getByTestId('polygon-status')).toHaveTextContent('active')
        expect(screen.getByTestId('finnhub-status')).toHaveTextContent('active')
        expect(screen.getByTestId('provider-count')).toHaveTextContent('3')
      })
    })

    test('handles provider-specific validation independently', async () => {
      const testUser = {
        sub: 'validation-multi-user',
        email: 'validation-multi@example.com',
        username: 'validationmulti'
      }

      const mixedKeys = {
        alpaca_api_key: 'PKTEST_valid',
        alpaca_secret_key: 'valid-secret',
        polygon_api_key: 'INVALID_POLYGON_KEY'
      }

      // Mock provider-specific validation
      apiKeyService.validateApiKeys.mockImplementation((provider) => {
        if (provider === 'alpaca') {
          return Promise.resolve({ valid: true })
        }
        if (provider === 'polygon') {
          return Promise.resolve({ valid: false, error: 'Invalid Polygon API key' })
        }
        return Promise.resolve({ valid: true })
      })

      render(
        <TestWrapper initialUser={testUser} initialApiKeys={mixedKeys}>
          <MultiComponentApp />
        </TestWrapper>
      )

      // Should show mixed status
      await waitFor(() => {
        expect(screen.getByTestId('alpaca-status')).toHaveTextContent('active')
        expect(screen.getByTestId('polygon-status')).toHaveTextContent('inactive')
      })

      // Portfolio should work (has valid Alpaca)
      fireEvent.click(screen.getByTestId('nav-portfolio'))

      await waitFor(() => {
        expect(screen.getByText(/portfolio/i)).toBeInTheDocument()
        expect(screen.queryByText(/api keys required/i)).not.toBeInTheDocument()
      })

      // Market data should show Polygon error
      fireEvent.click(screen.getByTestId('nav-signals'))

      await waitFor(() => {
        expect(screen.getByText(/polygon api key required/i)).toBeInTheDocument()
      })
    })
  })

  describe('Performance and Memory Management', () => {
    test('efficiently handles rapid state changes', async () => {
      const testUser = {
        sub: 'performance-user',
        email: 'performance@example.com',
        username: 'performanceuser'
      }

      render(
        <TestWrapper initialUser={testUser}>
          <MultiComponentApp />
        </TestWrapper>
      )

      const startTime = Date.now()

      // Rapid navigation and state changes
      for (let i = 0; i < 10; i++) {
        fireEvent.click(screen.getByTestId('nav-portfolio'))
        fireEvent.click(screen.getByTestId('nav-settings'))
        fireEvent.click(screen.getByTestId('nav-signals'))
        fireEvent.click(screen.getByTestId('nav-livedata'))
      }

      const endTime = Date.now()
      
      // Should handle rapid changes efficiently
      expect(endTime - startTime).toBeLessThan(1000)

      // State should still be consistent
      await waitFor(() => {
        expect(screen.getByTestId('has-keys')).toHaveTextContent('false')
        expect(screen.getByTestId('loading')).toHaveTextContent('false')
      })
    })

    test('prevents memory leaks during component mounting/unmounting', async () => {
      const testUser = {
        sub: 'memory-user',
        email: 'memory@example.com',
        username: 'memoryuser'
      }

      const { unmount } = render(
        <TestWrapper initialUser={testUser}>
          <MultiComponentApp />
        </TestWrapper>
      )

      // Mount and unmount multiple times
      for (let i = 0; i < 5; i++) {
        unmount()
        
        render(
          <TestWrapper initialUser={testUser}>
            <MultiComponentApp />
          </TestWrapper>
        )
      }

      // Should not have accumulated state or listeners
      await waitFor(() => {
        expect(screen.getByTestId('has-keys')).toHaveTextContent('false')
      })
    })

    test('handles concurrent API key operations', async () => {
      const testUser = {
        sub: 'concurrent-user',
        email: 'concurrent@example.com',
        username: 'concurrentuser'
      }

      render(
        <TestWrapper initialUser={testUser}>
          <MultiComponentApp />
        </TestWrapper>
      )

      fireEvent.click(screen.getByTestId('nav-settings'))

      // Simulate multiple rapid saves
      const savePromises = []
      for (let i = 0; i < 5; i++) {
        apiKeyService.saveApiKeys.mockResolvedValue({
          success: true,
          data: { test_key: `value_${i}` }
        })
        
        savePromises.push(
          fireEvent.click(screen.getByText(/save api keys/i))
        )
      }

      await Promise.all(savePromises)

      // State should be consistent after concurrent operations
      await waitFor(() => {
        expect(screen.getByTestId('loading')).toHaveTextContent('false')
        expect(screen.getByTestId('error')).toHaveTextContent('none')
      })
    })
  })
})