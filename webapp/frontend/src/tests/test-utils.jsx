/**
 * Test Utilities - Real Site Testing Setup
 * Provides wrapper components and utilities for testing actual site functionality
 */

/* eslint-disable react-refresh/only-export-components */

import React from 'react';
import { render } from '@testing-library/react';
import { BrowserRouter } from "react-router-dom";
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


// Test wrapper that includes all necessary providers for real site testing
export const TestWrapper = ({ children, _authValue = {} }) => {
  return (
    <BrowserRouter>
      <ThemeProvider theme={testTheme}>
        <TestAuthProvider>{children}</TestAuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
};

// Mock user data helper
export const createMockUser = () => ({
  id: 'test-user-123',
  email: 'test@example.com',
  name: 'Test User',
  roles: ['user'],
  preferences: {},
  createdAt: '2025-01-01T00:00:00Z',
  lastLogin: '2025-01-15T10:00:00Z'
});

// Render function with all providers for testing
export const renderWithProviders = (ui, options = {}) => {
  return render(ui, {
    wrapper: TestWrapper,
    ...options,
  });
};

// Re-export commonly used testing utilities
export { render, screen, waitFor, fireEvent } from '@testing-library/react';
export { userEvent } from '@testing-library/user-event';

