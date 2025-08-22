/**
 * Test Utilities - Real Site Testing Setup
 * Provides wrapper components and utilities for testing actual site functionality
 */

import React from 'react';
import { render } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { vi } from "vitest";

// Import the real AuthContext
import { AuthProvider } from '../contexts/AuthContext';

// Mock for dev auth
vi.mock('../services/devAuth', () => ({
  default: {
    login: vi.fn(() => Promise.resolve({ user: { email: 'test@example.com' }, tokens: {} })),
    logout: vi.fn(() => Promise.resolve()),
    register: vi.fn(() => Promise.resolve()),
    getCurrentUser: vi.fn(() => Promise.resolve({ email: 'test@example.com' })),
    refreshSession: vi.fn(() => Promise.resolve()),
  }
}));

// Mock session manager
vi.mock('../services/sessionManager', () => ({
  default: {
    startSession: vi.fn(),
    endSession: vi.fn(),
    extendSession: vi.fn(),
    getSessionStatus: vi.fn(() => ({ isActive: true, timeRemaining: 3600 })),
  }
}));

// Mock amplify config
vi.mock('../config/amplify', () => ({
  isCognitoConfigured: vi.fn(() => false), // Use dev auth instead
}));

// Mock amplify auth
vi.mock('@aws-amplify/auth', () => ({
  fetchAuthSession: vi.fn(() => Promise.resolve({ tokens: null })),
  signIn: vi.fn(() => Promise.resolve()),
  signUp: vi.fn(() => Promise.resolve()),
  confirmSignUp: vi.fn(() => Promise.resolve()),
  signOut: vi.fn(() => Promise.resolve()),
  resetPassword: vi.fn(() => Promise.resolve()),
  confirmResetPassword: vi.fn(() => Promise.resolve()),
  getCurrentUser: vi.fn(() => Promise.resolve({ email: 'test@example.com' })),
}));

// Use real AuthProvider with mocked dependencies
export const TestAuthProvider = ({ children, _initialUser = null }) => {
  return (
    <AuthProvider>
      {children}
    </AuthProvider>
  );
};

// Remove mock auth hook since we're using real AuthProvider

// Real site theme for testing
const testTheme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
  },
});

// Real API configuration for testing actual site
const REAL_API_CONFIG = {
  apiUrl: process.env.VITE_API_URL || 'http://localhost:3001', // Dynamic URL from CloudFormation
  timeout: 30000,
};

// Test wrapper that includes all necessary providers for real site testing
export const TestWrapper = ({ children, _authValue = {} }) => {
  const testQueryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  return (
    <BrowserRouter>
      <ThemeProvider theme={testTheme}>
        <QueryClientProvider client={testQueryClient}>
          <TestAuthProvider>{children}</TestAuthProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
};

// Custom render function that includes the wrapper
// eslint-disable-next-line react-refresh/only-export-components
export const renderWithProviders = (ui, options = {}) => {
  const { authValue, ...renderOptions } = options;

  const Wrapper = ({ children }) => (
    <TestWrapper authValue={authValue}>{children}</TestWrapper>
  );

  return render(ui, { wrapper: Wrapper, ...renderOptions });
};

// Mock API responses
// eslint-disable-next-line react-refresh/only-export-components
export const mockApiResponses = {
  portfolio: {
    success: true,
    data: {
      positions: [
        {
          symbol: "AAPL",
          quantity: 10,
          market_value: 1500.0,
          cost_basis: 1200.0,
          unrealized_pl: 300.0,
          unrealized_plpc: 25.0,
        },
        {
          symbol: "GOOGL",
          quantity: 5,
          market_value: 2500.0,
          cost_basis: 2000.0,
          unrealized_pl: 500.0,
          unrealized_plpc: 25.0,
        },
      ],
      account: {
        portfolio_value: 4000.0,
        buying_power: 1000.0,
        cash: 500.0,
      },
    },
  },
  quote: {
    success: true,
    data: {
      symbol: "AAPL",
      price: 150.0,
      change: 2.5,
      change_percent: 1.69,
    },
  },
};

// Component test helpers
// eslint-disable-next-line react-refresh/only-export-components
export const waitForLoadingToFinish = async () => {
  // Wait for loading states to complete
  await new Promise((resolve) => setTimeout(resolve, 0));
};

// eslint-disable-next-line react-refresh/only-export-components
export const createMockUser = (overrides = {}) => ({
  userId: "test-user-123",
  username: "testuser",
  email: "test@example.com",
  attributes: {
    email: "test@example.com",
    email_verified: "true",
  },
  ...overrides,
});

// Helper to make real API calls during tests
export const makeRealApiCall = async (endpoint, options = {}) => {
  const url = `${REAL_API_CONFIG.apiUrl}${endpoint}`;
  
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });
    
    return {
      ok: response.ok,
      status: response.status,
      data: await response.json(),
    };
  } catch (error) {
    return {
      ok: false,
      status: 500,
      error: error.message,
    };
  }
};

// Helper for authenticated tests
export const renderWithAuth = (ui, options = {}) => {
  const authenticatedUser = createMockUser({ 
    isAuthenticated: true,
    token: 'test-jwt-token' 
  });
  
  return renderWithProviders(ui, {
    ...options,
    authValue: { 
      user: authenticatedUser, 
      isAuthenticated: true,
      token: 'test-jwt-token'
    },
  });
};

// Export API config for test assertions
export { REAL_API_CONFIG };

// Export test utilities
// eslint-disable-next-line react-refresh/only-export-components
export * from "@testing-library/react";
// eslint-disable-next-line react-refresh/only-export-components
export { vi } from "vitest";
