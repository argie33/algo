/**
 * Test Utilities - Comprehensive Test Setup
 * Provides wrapper components and utilities for testing React components
 */

import { render } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { vi } from "vitest";
import { createContext, useContext } from "react";

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
    backupCodes: [],
  },
  setupMFA: vi.fn(),
  verifyMFA: vi.fn(),
  disableMFA: vi.fn(),
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
// eslint-disable-next-line react-refresh/only-export-components
export const useMockAuth = () => useContext(MockAuthContext);

// Test wrapper that includes all necessary providers
export const TestWrapper = ({ children, authValue = {} }) => (
  <BrowserRouter>
    <MockAuthProvider value={authValue}>{children}</MockAuthProvider>
  </BrowserRouter>
);

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

// Export test utilities
// eslint-disable-next-line react-refresh/only-export-components
export * from "@testing-library/react";
// eslint-disable-next-line react-refresh/only-export-components
export { vi } from "vitest";
