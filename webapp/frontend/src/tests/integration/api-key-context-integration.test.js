/**
 * API KEY CONTEXT INTEGRATION TESTS
 * Tests React Context provider state management across components
 */

import { render, screen, waitFor, fireEvent, act } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { ApiKeyProvider, useApiKeys } from '../../components/ApiKeyProvider'
import { AuthProvider } from '../../components/auth/AuthProvider'

// Mock API services
jest.mock('../../services/apiKeyService', () => ({
  getApiKeys: jest.fn(),
  saveApiKeys: jest.fn(),
  validateApiKeys: jest.fn(),
  testConnection: jest.fn(),
  deleteApiKeys: jest.fn()
}))

jest.mock('../../services/api', () => ({
  get: jest.fn(),
  post: jest.fn(),
  put: jest.fn(),
  delete: jest.fn()
}))

const apiKeyService = require('../../services/apiKeyService')
const api = require('../../services/api')

// Test component that consumes API key context
const ApiKeyConsumer = () => {
  const {
    apiKeys,
    isLoading,
    error,
    hasApiKeys,
    hasProvider,
    saveApiKeys,
    deleteApiKeys,
    refreshApiKeys,
    testConnection,
    getStatus
  } = useApiKeys()

  return (
    <div>
      <div data-testid="loading-state">{isLoading ? 'loading' : 'loaded'}</div>
      <div data-testid="error-state">{error || 'no-error'}</div>
      <div data-testid="has-keys">{hasApiKeys ? 'has-keys' : 'no-keys'}</div>
      <div data-testid="has-alpaca">{hasProvider('alpaca') ? 'has-alpaca' : 'no-alpaca'}</div>
      <div data-testid="has-polygon">{hasProvider('polygon') ? 'has-polygon' : 'no-polygon'}</div>
      <div data-testid="status">{JSON.stringify(getStatus())}</div>
      
      {apiKeys && (
        <div data-testid="api-keys">
          {Object.entries(apiKeys).map(([key, value]) => (
            <div key={key} data-testid={`key-${key}`}>{value}</div>
          ))}
        </div>
      )}

      <button onClick={() => saveApiKeys({ 
        alpaca_api_key: 'new-key', 
        alpaca_secret_key: 'new-secret' 
      })}>
        Save Keys
      </button>
      
      <button onClick={() => deleteApiKeys('alpaca')}>
        Delete Alpaca
      </button>
      
      <button onClick={() => refreshApiKeys()}>
        Refresh Keys
      </button>
      
      <button onClick={() => testConnection('alpaca')}>
        Test Alpaca
      </button>
    </div>
  )
}

const TestWrapper = ({ children, initialApiKeys = null, authenticated = true }) => {
  const mockUser = authenticated ? {
    sub: 'test-user-123',
    email: 'test@example.com',
    username: 'testuser'
  } : null

  return (
    <BrowserRouter>
      <AuthProvider initialUser={mockUser}>
        <ApiKeyProvider initialApiKeys={initialApiKeys}>
          {children}
        </ApiKeyProvider>
      </AuthProvider>
    </BrowserRouter>
  )
}

describe('API Key Context Integration Tests', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    
    // Default mock implementations
    apiKeyService.getApiKeys.mockResolvedValue(null)
    apiKeyService.saveApiKeys.mockResolvedValue({ success: true })
    apiKeyService.validateApiKeys.mockResolvedValue({ valid: true })
    apiKeyService.testConnection.mockResolvedValue({ success: true })
    apiKeyService.deleteApiKeys.mockResolvedValue({ success: true })
  })

  describe('Context Initialization', () => {
    test('initializes with no API keys', async () => {
      render(
        <TestWrapper>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading-state')).toHaveTextContent('loaded')
        expect(screen.getByTestId('has-keys')).toHaveTextContent('no-keys')
        expect(screen.getByTestId('has-alpaca')).toHaveTextContent('no-alpaca')
        expect(screen.getByTestId('has-polygon')).toHaveTextContent('no-polygon')
      })
    })

    test('initializes with existing API keys', async () => {
      const initialKeys = {
        alpaca_api_key: 'test-alpaca-key',
        alpaca_secret_key: 'test-alpaca-secret',
        polygon_api_key: 'test-polygon-key'
      }

      render(
        <TestWrapper initialApiKeys={initialKeys}>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('has-keys')).toHaveTextContent('has-keys')
        expect(screen.getByTestId('has-alpaca')).toHaveTextContent('has-alpaca')
        expect(screen.getByTestId('has-polygon')).toHaveTextContent('has-polygon')
        expect(screen.getByTestId('key-alpaca_api_key')).toHaveTextContent('test-alpaca-key')
      })
    })

    test('loads API keys from backend on initialization', async () => {
      const backendKeys = {
        alpaca_api_key: 'backend-alpaca-key',
        polygon_api_key: 'backend-polygon-key'
      }

      apiKeyService.getApiKeys.mockResolvedValue(backendKeys)

      render(
        <TestWrapper>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(apiKeyService.getApiKeys).toHaveBeenCalled()
        expect(screen.getByTestId('has-keys')).toHaveTextContent('has-keys')
        expect(screen.getByTestId('key-alpaca_api_key')).toHaveTextContent('backend-alpaca-key')
      })
    })

    test('handles backend loading errors gracefully', async () => {
      apiKeyService.getApiKeys.mockRejectedValue(new Error('Backend unavailable'))

      render(
        <TestWrapper>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('error-state')).toHaveTextContent('Backend unavailable')
        expect(screen.getByTestId('has-keys')).toHaveTextContent('no-keys')
      })
    })
  })

  describe('API Key Management Operations', () => {
    test('can save new API keys', async () => {
      apiKeyService.saveApiKeys.mockResolvedValue({ 
        success: true, 
        data: { 
          alpaca_api_key: 'new-key',
          alpaca_secret_key: 'new-secret'
        }
      })

      render(
        <TestWrapper>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('has-keys')).toHaveTextContent('no-keys')
      })

      fireEvent.click(screen.getByText('Save Keys'))

      await waitFor(() => {
        expect(apiKeyService.saveApiKeys).toHaveBeenCalledWith({
          alpaca_api_key: 'new-key',
          alpaca_secret_key: 'new-secret'
        })
        expect(screen.getByTestId('has-keys')).toHaveTextContent('has-keys')
        expect(screen.getByTestId('has-alpaca')).toHaveTextContent('has-alpaca')
      })
    })

    test('handles save API key errors', async () => {
      apiKeyService.saveApiKeys.mockRejectedValue(new Error('Save failed'))

      render(
        <TestWrapper>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      fireEvent.click(screen.getByText('Save Keys'))

      await waitFor(() => {
        expect(screen.getByTestId('error-state')).toHaveTextContent('Save failed')
        expect(screen.getByTestId('has-keys')).toHaveTextContent('no-keys')
      })
    })

    test('can delete specific API keys', async () => {
      const initialKeys = {
        alpaca_api_key: 'test-alpaca-key',
        polygon_api_key: 'test-polygon-key'
      }

      apiKeyService.deleteApiKeys.mockResolvedValue({ success: true })

      render(
        <TestWrapper initialApiKeys={initialKeys}>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('has-alpaca')).toHaveTextContent('has-alpaca')
        expect(screen.getByTestId('has-polygon')).toHaveTextContent('has-polygon')
      })

      fireEvent.click(screen.getByText('Delete Alpaca'))

      await waitFor(() => {
        expect(apiKeyService.deleteApiKeys).toHaveBeenCalledWith('alpaca')
        expect(screen.getByTestId('has-alpaca')).toHaveTextContent('no-alpaca')
        expect(screen.getByTestId('has-polygon')).toHaveTextContent('has-polygon') // Should remain
      })
    })

    test('can refresh API keys from backend', async () => {
      const updatedKeys = {
        alpaca_api_key: 'updated-alpaca-key',
        polygon_api_key: 'updated-polygon-key',
        finnhub_api_key: 'new-finnhub-key'
      }

      apiKeyService.getApiKeys.mockResolvedValueOnce(null) // Initial load
      apiKeyService.getApiKeys.mockResolvedValueOnce(updatedKeys) // Refresh call

      render(
        <TestWrapper>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('has-keys')).toHaveTextContent('no-keys')
      })

      fireEvent.click(screen.getByText('Refresh Keys'))

      await waitFor(() => {
        expect(apiKeyService.getApiKeys).toHaveBeenCalledTimes(2)
        expect(screen.getByTestId('has-keys')).toHaveTextContent('has-keys')
        expect(screen.getByTestId('key-alpaca_api_key')).toHaveTextContent('updated-alpaca-key')
        expect(screen.getByTestId('key-finnhub_api_key')).toHaveTextContent('new-finnhub-key')
      })
    })
  })

  describe('Provider-Specific Functionality', () => {
    test('can test connection for specific provider', async () => {
      const initialKeys = {
        alpaca_api_key: 'test-alpaca-key',
        alpaca_secret_key: 'test-alpaca-secret'
      }

      apiKeyService.testConnection.mockResolvedValue({ 
        success: true, 
        data: { connected: true, account: 'test-account' }
      })

      render(
        <TestWrapper initialApiKeys={initialKeys}>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      fireEvent.click(screen.getByText('Test Alpaca'))

      await waitFor(() => {
        expect(apiKeyService.testConnection).toHaveBeenCalledWith('alpaca')
      })
    })

    test('handles provider connection test failures', async () => {
      const initialKeys = {
        alpaca_api_key: 'invalid-key',
        alpaca_secret_key: 'invalid-secret'
      }

      apiKeyService.testConnection.mockRejectedValue(new Error('Invalid credentials'))

      render(
        <TestWrapper initialApiKeys={initialKeys}>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      fireEvent.click(screen.getByText('Test Alpaca'))

      await waitFor(() => {
        expect(screen.getByTestId('error-state')).toHaveTextContent('Invalid credentials')
      })
    })

    test('provides accurate provider status', async () => {
      const partialKeys = {
        alpaca_api_key: 'test-alpaca-key',
        alpaca_secret_key: 'test-alpaca-secret'
        // Missing polygon and finnhub keys
      }

      render(
        <TestWrapper initialApiKeys={partialKeys}>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      await waitFor(() => {
        const status = JSON.parse(screen.getByTestId('status').textContent)
        expect(status.hasAlpaca).toBe(true)
        expect(status.hasPolygon).toBe(false)
        expect(status.hasFinnhub).toBe(false)
        expect(status.providers).toEqual(['alpaca'])
      })
    })
  })

  describe('State Synchronization', () => {
    test('synchronizes state across multiple consumers', async () => {
      const Consumer1 = () => {
        const { hasApiKeys, saveApiKeys } = useApiKeys()
        return (
          <div>
            <div data-testid="consumer1-has-keys">{hasApiKeys ? 'has-keys' : 'no-keys'}</div>
            <button onClick={() => saveApiKeys({ test_key: 'test-value' })}>
              Consumer1 Save
            </button>
          </div>
        )
      }

      const Consumer2 = () => {
        const { hasApiKeys } = useApiKeys()
        return (
          <div data-testid="consumer2-has-keys">{hasApiKeys ? 'has-keys' : 'no-keys'}</div>
        )
      }

      apiKeyService.saveApiKeys.mockResolvedValue({ 
        success: true, 
        data: { test_key: 'test-value' }
      })

      render(
        <TestWrapper>
          <Consumer1 />
          <Consumer2 />
        </TestWrapper>
      )

      // Initially both should show no keys
      await waitFor(() => {
        expect(screen.getByTestId('consumer1-has-keys')).toHaveTextContent('no-keys')
        expect(screen.getByTestId('consumer2-has-keys')).toHaveTextContent('no-keys')
      })

      // Save keys through consumer 1
      fireEvent.click(screen.getByText('Consumer1 Save'))

      // Both consumers should reflect the change
      await waitFor(() => {
        expect(screen.getByTestId('consumer1-has-keys')).toHaveTextContent('has-keys')
        expect(screen.getByTestId('consumer2-has-keys')).toHaveTextContent('has-keys')
      })
    })

    test('handles concurrent operations correctly', async () => {
      let saveCallCount = 0
      apiKeyService.saveApiKeys.mockImplementation(() => {
        saveCallCount++
        return Promise.resolve({ 
          success: true, 
          data: { call_number: saveCallCount }
        })
      })

      render(
        <TestWrapper>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      // Trigger multiple saves rapidly
      fireEvent.click(screen.getByText('Save Keys'))
      fireEvent.click(screen.getByText('Save Keys'))
      fireEvent.click(screen.getByText('Save Keys'))

      await waitFor(() => {
        expect(apiKeyService.saveApiKeys).toHaveBeenCalledTimes(3)
        expect(screen.getByTestId('has-keys')).toHaveTextContent('has-keys')
      })
    })
  })

  describe('Authentication Integration', () => {
    test('clears API keys when user logs out', async () => {
      const initialKeys = {
        alpaca_api_key: 'test-key'
      }

      const { rerender } = render(
        <TestWrapper initialApiKeys={initialKeys} authenticated={true}>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('has-keys')).toHaveTextContent('has-keys')
      })

      // Simulate logout by changing authentication state
      rerender(
        <TestWrapper initialApiKeys={initialKeys} authenticated={false}>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('has-keys')).toHaveTextContent('no-keys')
      })
    })

    test('reloads API keys when user logs back in', async () => {
      const userKeys = {
        alpaca_api_key: 'user-specific-key'
      }

      apiKeyService.getApiKeys.mockResolvedValue(userKeys)

      const { rerender } = render(
        <TestWrapper authenticated={false}>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('has-keys')).toHaveTextContent('no-keys')
      })

      // Simulate login
      rerender(
        <TestWrapper authenticated={true}>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(apiKeyService.getApiKeys).toHaveBeenCalled()
        expect(screen.getByTestId('has-keys')).toHaveTextContent('has-keys')
      })
    })
  })

  describe('Error Recovery and Resilience', () => {
    test('recovers from network errors', async () => {
      // First call fails
      apiKeyService.getApiKeys.mockRejectedValueOnce(new Error('Network error'))
      // Second call succeeds
      apiKeyService.getApiKeys.mockResolvedValueOnce({ alpaca_api_key: 'recovered-key' })

      render(
        <TestWrapper>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('error-state')).toHaveTextContent('Network error')
      })

      // Trigger refresh to retry
      fireEvent.click(screen.getByText('Refresh Keys'))

      await waitFor(() => {
        expect(screen.getByTestId('error-state')).toHaveTextContent('no-error')
        expect(screen.getByTestId('has-keys')).toHaveTextContent('has-keys')
      })
    })

    test('handles malformed API key data', async () => {
      apiKeyService.getApiKeys.mockResolvedValue('invalid-response-format')

      render(
        <TestWrapper>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('error-state')).not.toHaveTextContent('no-error')
        expect(screen.getByTestId('has-keys')).toHaveTextContent('no-keys')
      })
    })

    test('provides loading state during operations', async () => {
      // Delay the API response
      apiKeyService.saveApiKeys.mockImplementation(() => {
        return new Promise(resolve => {
          setTimeout(() => resolve({ success: true, data: { test: 'key' } }), 100)
        })
      })

      render(
        <TestWrapper>
          <ApiKeyConsumer />
        </TestWrapper>
      )

      expect(screen.getByTestId('loading-state')).toHaveTextContent('loaded')

      fireEvent.click(screen.getByText('Save Keys'))

      // Should show loading during save operation
      expect(screen.getByTestId('loading-state')).toHaveTextContent('loading')

      await waitFor(() => {
        expect(screen.getByTestId('loading-state')).toHaveTextContent('loaded')
        expect(screen.getByTestId('has-keys')).toHaveTextContent('has-keys')
      })
    })
  })
})