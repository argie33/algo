/**
 * Test Providers and Wrappers
 * Comprehensive providers for testing React components
 */

import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'
import { vi } from 'vitest'

// Import the safe theme
import { lightTheme } from '../../theme/safeTheme'

// Mock AuthContext
const MockAuthContext = React.createContext({
  user: null,
  isAuthenticated: false,
  login: vi.fn(),
  logout: vi.fn(),
  register: vi.fn(),
  loading: false,
  error: null
})

export const MockAuthProvider = ({ children, mockUser = null, isAuthenticated = false }) => {
  const mockValue = {
    user: mockUser,
    isAuthenticated,
    login: vi.fn().mockResolvedValue({}),
    logout: vi.fn().mockResolvedValue({}),
    register: vi.fn().mockResolvedValue({}),
    loading: false,
    error: null,
    updateUser: vi.fn(),
    refreshToken: vi.fn(),
    checkAuthStatus: vi.fn()
  }

  return (
    <MockAuthContext.Provider value={mockValue}>
      {children}
    </MockAuthContext.Provider>
  )
}

// Mock API Key Context
const MockApiKeyContext = React.createContext({
  apiKeys: {},
  setApiKey: vi.fn(),
  removeApiKey: vi.fn(),
  validateApiKey: vi.fn(),
  loading: false,
  error: null
})

export const MockApiKeyProvider = ({ children, mockApiKeys = {} }) => {
  const mockValue = {
    apiKeys: mockApiKeys,
    setApiKey: vi.fn(),
    removeApiKey: vi.fn(),
    validateApiKey: vi.fn().mockResolvedValue({ valid: true }),
    loading: false,
    error: null
  }

  return (
    <MockApiKeyContext.Provider value={mockValue}>
      {children}
    </MockApiKeyContext.Provider>
  )
}

// Create a test QueryClient
const createTestQueryClient = () => new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      cacheTime: Infinity,
    },
  },
})

// Comprehensive test wrapper with all providers
export const AllTheProviders = ({ children, options = {} }) => {
  const {
    mockUser = null,
    isAuthenticated = false,
    mockApiKeys = {},
    queryClient = createTestQueryClient(),
    theme = lightTheme
  } = options

  return (
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider theme={theme}>
          <CssBaseline />
          <MockAuthProvider mockUser={mockUser} isAuthenticated={isAuthenticated}>
            <MockApiKeyProvider mockApiKeys={mockApiKeys}>
              {children}
            </MockApiKeyProvider>
          </MockAuthProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </BrowserRouter>
  )
}

// Simplified wrapper for basic component testing (without CssBaseline to avoid theme issues)
export const BasicTestWrapper = ({ children }) => {
  return (
    <ThemeProvider theme={lightTheme}>
      {children}
    </ThemeProvider>
  )
}

// Auth-specific wrapper (without CssBaseline to avoid theme issues)
export const AuthTestWrapper = ({ children, mockUser = null, isAuthenticated = false }) => {
  return (
    <ThemeProvider theme={lightTheme}>
      <MockAuthProvider mockUser={mockUser} isAuthenticated={isAuthenticated}>
        {children}
      </MockAuthProvider>
    </ThemeProvider>
  )
}

// Custom render function with providers
export const renderWithProviders = (ui, options = {}) => {
  const { render } = require('@testing-library/react')
  
  return render(ui, {
    wrapper: (props) => <AllTheProviders {...props} options={options} />,
    ...options
  })
}

// Export mock contexts for use in tests
export { MockAuthContext, MockApiKeyContext }

// Mock hooks
export const useAuth = () => React.useContext(MockAuthContext)
export const useApiKeys = () => React.useContext(MockApiKeyContext)