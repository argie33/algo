/**
 * Test Utilities - Comprehensive Test Setup
 * Provides wrapper components and utilities for testing React components
 */

import { render } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { vi } from 'vitest';
import { createContext, useContext } from 'react';

// Mock AuthContext that matches the real one
const mockAuthContext = {
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,
  login: vi.fn(),
  logout: vi.fn(),
  register: vi.fn(),
  confirmSignUp: vi.fn(),
  resetPassword: vi.fn(),
  confirmResetPassword: vi.fn(),
  resendSignUpCode: vi.fn(),
  clearError: vi.fn(),
  refreshSession: vi.fn(),
  updateProfile: vi.fn(),
  mfaSetup: {
    isEnabled: false,
    qrCode: null,
    backupCodes: []
  },
  setupMFA: vi.fn(),
  verifyMFA: vi.fn(),
  disableMFA: vi.fn()
};

const MockAuthContext = createContext(mockAuthContext);

// Mock AuthProvider component
export const MockAuthProvider = ({ children, value = {} }) => {
  const contextValue = { ...mockAuthContext, ...value };
  return (
    <MockAuthContext.Provider value={contextValue}>
      {children}
    </MockAuthContext.Provider>
  );
};

// Mock useAuth hook
export const mockUseAuth = () => useContext(MockAuthContext);

// Test wrapper that includes all necessary providers
export const TestWrapper = ({ children, authValue = {} }) => (
  <BrowserRouter>
    <MockAuthProvider value={authValue}>
      {children}
    </MockAuthProvider>
  </BrowserRouter>
);

// Custom render function that includes the wrapper
export const renderWithProviders = (ui, options = {}) => {
  const { authValue, ...renderOptions } = options;
  
  const Wrapper = ({ children }) => (
    <TestWrapper authValue={authValue}>
      {children}
    </TestWrapper>
  );

  return render(ui, { wrapper: Wrapper, ...renderOptions });
};

// Mock API responses
export const mockApiResponses = {
  portfolio: {
    success: true,
    data: {
      positions: [
        {
          symbol: 'AAPL',
          quantity: 10,
          market_value: 1500.00,
          cost_basis: 1200.00,
          unrealized_pl: 300.00,
          unrealized_plpc: 25.0
        },
        {
          symbol: 'GOOGL',
          quantity: 5,
          market_value: 2500.00,
          cost_basis: 2000.00,
          unrealized_pl: 500.00,
          unrealized_plpc: 25.0
        }
      ],
      account: {
        portfolio_value: 4000.00,
        buying_power: 1000.00,
        cash: 500.00
      }
    }
  },
  quote: {
    success: true,
    data: {
      symbol: 'AAPL',
      price: 150.00,
      change: 2.50,
      change_percent: 1.69
    }
  }
};

// Component test helpers
export const waitForLoadingToFinish = async () => {
  // Wait for loading states to complete
  await new Promise(resolve => setTimeout(resolve, 0));
};

export const createMockUser = (overrides = {}) => ({
  userId: 'test-user-123',
  username: 'testuser',
  email: 'test@example.com',
  attributes: {
    email: 'test@example.com',
    email_verified: 'true'
  },
  ...overrides
});

// Export test utilities
export * from '@testing-library/react';
export { vi } from 'vitest';