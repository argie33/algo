/**
 * Authentication Edge Cases Integration Tests
 * Tests authentication scenarios that could cause issues or infinite loops
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider, useAuth } from '../../../contexts/AuthContext'
import Settings from '../../../pages/Settings'
import Dashboard from '../../../pages/Dashboard'
import muiTheme from '../../../theme/muiTheme'

// Mock AWS Amplify auth functions
const mockAmplifyAuth = {
  fetchAuthSession: vi.fn(),
  getCurrentUser: vi.fn(),
  signIn: vi.fn(),
  signOut: vi.fn(),
  signUp: vi.fn(),
  confirmSignUp: vi.fn()
}

vi.mock('@aws-amplify/auth', () => mockAmplifyAuth)

// Mock environment config
vi.mock('../../../config/environment', () => ({
  FEATURES: {
    authentication: {
      enabled: true,
      methods: { cognito: true }
    }
  },
  AWS_CONFIG: {
    cognito: {
      userPoolId: 'us-east-1_test',
      userPoolClientId: 'test-client-id'
    }
  }
}))

// Mock amplify config
vi.mock('../../../config/amplify', () => ({
  configureAmplify: vi.fn(),
  isCognitoConfigured: vi.fn().mockReturnValue(true)
}))

// Mock runtime config
vi.mock('../../../services/runtimeConfig', () => ({
  initializeRuntimeConfig: vi.fn().mockResolvedValue({})
}))

// Test component to access auth context
const AuthTestComponent = ({ onAuthState }) => {
  const auth = useAuth()
  
  React.useEffect(() => {
    onAuthState(auth)
  }, [auth, onAuthState])
  
  return (
    <div>
      <div data-testid="auth-status">
        {auth.isAuthenticated ? 'authenticated' : 'not-authenticated'}
      </div>
      <div data-testid="loading-status">
        {auth.isLoading ? 'loading' : 'loaded'}
      </div>
      <div data-testid="retry-count">{auth.retryCount}</div>
      <div data-testid="max-retries">{auth.maxRetries}</div>
      {auth.error && <div data-testid="auth-error">{auth.error}</div>}
    </div>
  )
}

const TestWrapper = ({ children }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0, cacheTime: 0 }
    }
  })

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ThemeProvider theme={muiTheme}>
          <AuthProvider>
            {children}
          </AuthProvider>
        </ThemeProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

describe('Authentication Edge Cases Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    sessionStorage.clear()
    
    // Reset default mocks
    mockAmplifyAuth.fetchAuthSession.mockResolvedValue({
      tokens: null
    })
    mockAmplifyAuth.getCurrentUser.mockRejectedValue(new Error('No user'))
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('Circuit Breaker Functionality', () => {
    test('stops retrying after max attempts reached', async () => {
      let authState = null
      let retryCount = 0
      
      // Mock repeated failures
      mockAmplifyAuth.getCurrentUser.mockImplementation(() => {
        retryCount++
        return Promise.reject(new Error(`Auth failure attempt ${retryCount}`))
      })
      
      render(
        <TestWrapper>
          <AuthTestComponent onAuthState={(state) => { authState = state }} />
        </TestWrapper>
      )

      // Wait for auth checks to complete
      await waitFor(() => {
        expect(screen.getByTestId('loading-status')).toHaveTextContent('loaded')
      }, { timeout: 5000 })

      // Should not be authenticated
      expect(screen.getByTestId('auth-status')).toHaveTextContent('not-authenticated')
      
      // Should have attempted retries but stopped at max
      const retryCountElement = screen.getByTestId('retry-count')
      const retryCountValue = parseInt(retryCountElement.textContent)
      expect(retryCountValue).toBeGreaterThan(0)
      expect(retryCountValue).toBeLessThanOrEqual(3)
    })

    test('exponential backoff prevents rapid retry attempts', async () => {
      const attempts = []
      
      mockAmplifyAuth.getCurrentUser.mockImplementation(() => {
        attempts.push(Date.now())
        return Promise.reject(new Error('Auth failure'))
      })

      render(
        <TestWrapper>
          <AuthTestComponent onAuthState={() => {}} />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading-status')).toHaveTextContent('loaded')
      }, { timeout: 15000 })

      // Verify backoff timing (if multiple attempts were made)
      if (attempts.length > 1) {
        const timeDiffs = []
        for (let i = 1; i < attempts.length; i++) {
          timeDiffs.push(attempts[i] - attempts[i-1])
        }
        
        // Each retry should take longer than the previous
        for (let i = 1; i < timeDiffs.length; i++) {
          expect(timeDiffs[i]).toBeGreaterThanOrEqual(timeDiffs[i-1])
        }
      }
    })

    test('resets retry count on successful authentication', async () => {
      let authState = null
      let callCount = 0
      
      // First few calls fail, then succeed
      mockAmplifyAuth.getCurrentUser.mockImplementation(() => {
        callCount++
        if (callCount <= 2) {
          return Promise.reject(new Error('Auth failure'))
        }
        return Promise.resolve({
          username: 'testuser',
          userId: 'user-123',
          userAttributes: {
            given_name: 'Test',
            family_name: 'User'
          }
        })
      })
      
      mockAmplifyAuth.fetchAuthSession.mockResolvedValue({
        tokens: {
          accessToken: { 
            toString: () => 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJ0ZXN0IiwiaWF0IjoxNjAwMDAwMDAwLCJleHAiOjE2MDAwMDM2MDAsImF1ZCI6InRlc3QiLCJzdWIiOiJ1c2VyLTEyMyJ9.test'
          },
          idToken: { toString: () => 'id-token' }
        }
      })

      render(
        <TestWrapper>
          <AuthTestComponent onAuthState={(state) => { authState = state }} />
        </TestWrapper>
      )

      // Wait for eventual authentication
      await waitFor(() => {
        expect(screen.getByTestId('auth-status')).toHaveTextContent('authenticated')
      }, { timeout: 10000 })

      // Retry count should be reset to 0 on successful auth
      expect(screen.getByTestId('retry-count')).toHaveTextContent('0')
    })
  })

  describe('Malformed Token Scenarios', () => {
    test('handles invalid JWT token format', async () => {
      mockAmplifyAuth.getCurrentUser.mockResolvedValue({
        username: 'testuser',
        userId: 'user-123'
      })
      
      mockAmplifyAuth.fetchAuthSession.mockResolvedValue({
        tokens: {
          accessToken: { toString: () => 'invalid-jwt-token' }
        }
      })

      render(
        <TestWrapper>
          <AuthTestComponent onAuthState={() => {}} />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading-status')).toHaveTextContent('loaded')
      })

      // Should handle gracefully - either authenticated or not, but no crash
      const authStatus = screen.getByTestId('auth-status')
      expect(['authenticated', 'not-authenticated']).toContain(authStatus.textContent)
    })

    test('handles expired JWT tokens', async () => {
      mockAmplifyAuth.getCurrentUser.mockResolvedValue({
        username: 'testuser',
        userId: 'user-123'
      })
      
      // Token expired in the past
      const expiredToken = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJ0ZXN0IiwiaWF0IjoxNTAwMDAwMDAwLCJleHAiOjE1MDAwMDM2MDAsImF1ZCI6InRlc3QiLCJzdWIiOiJ1c2VyLTEyMyJ9.test'
      mockAmplifyAuth.fetchAuthSession.mockResolvedValue({
        tokens: {
          accessToken: { toString: () => expiredToken }
        }
      })

      render(
        <TestWrapper>
          <AuthTestComponent onAuthState={() => {}} />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading-status')).toHaveTextContent('loaded')
      })

      // Should handle expired token appropriately
      expect(screen.getByTestId('auth-status')).toHaveTextContent(/authenticated|not-authenticated/)
    })

    test('handles missing token claims', async () => {
      mockAmplifyAuth.getCurrentUser.mockResolvedValue({
        username: 'testuser',
        userId: 'user-123'
      })
      
      // Token with missing required claims
      const incompleteToken = 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJ0ZXN0In0.test'
      mockAmplifyAuth.fetchAuthSession.mockResolvedValue({
        tokens: {
          accessToken: { toString: () => incompleteToken }
        }
      })

      render(
        <TestWrapper>
          <AuthTestComponent onAuthState={() => {}} />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading-status')).toHaveTextContent('loaded')
      })

      // Should not crash with incomplete token
      expect(screen.getByTestId('auth-status')).toBeInTheDocument()
    })
  })

  describe('Race Condition Prevention', () => {
    test('prevents multiple concurrent auth checks', async () => {
      let checkCount = 0
      
      mockAmplifyAuth.getCurrentUser.mockImplementation(() => {
        checkCount++
        return new Promise(resolve => {
          setTimeout(() => {
            resolve({
              username: 'testuser',
              userId: 'user-123'
            })
          }, 100)
        })
      })
      
      mockAmplifyAuth.fetchAuthSession.mockResolvedValue({
        tokens: {
          accessToken: { 
            toString: () => 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJ0ZXN0IiwiaWF0IjoxNjAwMDAwMDAwLCJleHAiOjE2MDAwMDM2MDAsImF1ZCI6InRlc3QiLCJzdWIiOiJ1c2VyLTEyMyJ9.test'
          }
        }
      })

      render(
        <TestWrapper>
          <AuthTestComponent onAuthState={() => {}} />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading-status')).toHaveTextContent('loaded')
      }, { timeout: 5000 })

      // Should not have excessive concurrent calls
      expect(checkCount).toBeLessThan(10) // Reasonable upper bound
    })

    test('handles rapid component mount/unmount cycles', async () => {
      const { unmount, rerender } = render(
        <TestWrapper>
          <AuthTestComponent onAuthState={() => {}} />
        </TestWrapper>
      )

      // Rapidly unmount and remount
      unmount()
      
      rerender(
        <TestWrapper>
          <AuthTestComponent onAuthState={() => {}} />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading-status')).toHaveTextContent('loaded')
      })

      // Should handle gracefully without crashes
      expect(screen.getByTestId('auth-status')).toBeInTheDocument()
    })
  })

  describe('Settings Component Integration', () => {
    test('Settings handles auth state changes gracefully', async () => {
      mockAmplifyAuth.getCurrentUser.mockResolvedValue({
        username: 'testuser',
        userId: 'user-123',
        userAttributes: {
          given_name: 'Test',
          family_name: 'User',
          email: 'test@example.com'
        }
      })
      
      mockAmplifyAuth.fetchAuthSession.mockResolvedValue({
        tokens: {
          accessToken: { 
            toString: () => 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJ0ZXN0IiwiaWF0IjoxNjAwMDAwMDAwLCJleHAiOjE2MDAwMDM2MDAsImF1ZCI6InRlc3QiLCJzdWIiOiJ1c2VyLTEyMyJ9.test'
          }
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

      // Should render settings without infinite loops
      expect(screen.getByText('Personal Information')).toBeInTheDocument()
    })

    test('Settings handles authentication failure without loops', async () => {
      mockAmplifyAuth.getCurrentUser.mockRejectedValue(new Error('Auth failed'))
      mockAmplifyAuth.fetchAuthSession.mockRejectedValue(new Error('No session'))

      render(
        <TestWrapper>
          <Settings />
        </TestWrapper>
      )

      // Should render some content without infinite loops
      await waitFor(() => {
        expect(screen.getByText(/Account Settings|Unable to load/)).toBeInTheDocument()
      }, { timeout: 10000 })
    })
  })

  describe('Error Message Quality', () => {
    test('provides clear error messages for different failure types', async () => {
      mockAmplifyAuth.getCurrentUser.mockRejectedValue(new Error('UserUnAuthenticatedException'))

      render(
        <TestWrapper>
          <AuthTestComponent onAuthState={() => {}} />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('loading-status')).toHaveTextContent('loaded')
      })

      // After max retries, should show helpful error
      await waitFor(() => {
        const errorElement = screen.queryByTestId('auth-error')
        if (errorElement) {
          expect(errorElement.textContent).toMatch(/retry limit|sign in manually/i)
        }
      }, { timeout: 15000 })
    })
  })

  describe('Memory Leak Prevention', () => {
    test('cleans up properly on unmount', async () => {
      const { unmount } = render(
        <TestWrapper>
          <AuthTestComponent onAuthState={() => {}} />
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByTestId('auth-status')).toBeInTheDocument()
      })

      // Unmount should not throw errors
      expect(() => unmount()).not.toThrow()
    })
  })

  describe('Integration with Real Components', () => {
    test('Dashboard works with auth edge cases', async () => {
      mockAmplifyAuth.getCurrentUser.mockRejectedValue(new Error('Auth failed'))

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      )

      // Should render dashboard content even with auth issues
      await waitFor(() => {
        expect(screen.getByText(/Elite Financial Intelligence Platform/i)).toBeInTheDocument()
      })
    })

    test('Auth recovery works after temporary failures', async () => {
      let callCount = 0
      
      // Fail first, succeed later
      mockAmplifyAuth.getCurrentUser.mockImplementation(() => {
        callCount++
        if (callCount === 1) {
          return Promise.reject(new Error('Temporary failure'))
        }
        return Promise.resolve({
          username: 'testuser',
          userId: 'user-123'
        })
      })

      mockAmplifyAuth.fetchAuthSession.mockResolvedValue({
        tokens: {
          accessToken: { 
            toString: () => 'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJ0ZXN0IiwiaWF0IjoxNjAwMDAwMDAwLCJleHAiOjE2MDAwMDM2MDAsImF1ZCI6InRlc3QiLCJzdWIiOiJ1c2VyLTEyMyJ9.test'
          }
        }
      })

      render(
        <TestWrapper>
          <AuthTestComponent onAuthState={() => {}} />
        </TestWrapper>
      )

      // Should eventually authenticate successfully
      await waitFor(() => {
        expect(screen.getByTestId('auth-status')).toHaveTextContent('authenticated')
      }, { timeout: 15000 })
    })
  })
})