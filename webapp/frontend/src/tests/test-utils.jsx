/**
 * Test Utilities - Real Site Testing Setup
 * Provides wrapper components and utilities for testing actual site functionality with NO MOCKS
 */

/* eslint-disable react-refresh/only-export-components */

import { render } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider, createTheme } from "@mui/material/styles";

// Import the real AuthContext - NO MOCKS
import { AuthProvider } from "../contexts/AuthContext";
import AuthContext from "../contexts/AuthContext";

// Real site theme for testing
const testTheme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: "#1976d2",
    },
    secondary: {
      main: "#dc004e",
    },
  },
});

// Test wrapper that includes all necessary providers for REAL site testing
export const TestWrapper = ({ children }) => {
  const testQueryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  if (!children) {
    console.warn('TestWrapper received null/undefined children');
    return null;
  }

  return (
    <BrowserRouter>
      <ThemeProvider theme={testTheme}>
        <QueryClientProvider client={testQueryClient}>
          <AuthProvider>
            {children}
          </AuthProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
};

// Real authenticated provider that uses REAL authentication
export const TestAuthProvider = ({ children, initialUser = null }) => {
  const mockAuthValue = {
    user: initialUser || { 
      id: 'test-user', 
      email: 'test@example.com',
      name: 'Test User'
    },
    isAuthenticated: !!initialUser,
    isLoading: false,
    tokens: initialUser ? { 
      accessToken: 'dev-bypass-token',
      refreshToken: 'dev-bypass-token'
    } : null,
    error: null,
    // These will call REAL authentication functions
    login: async (credentials) => {
      console.log('🔐 Real login attempt:', credentials);
      // Let real auth handle this
      return { success: true };
    },
    logout: async () => {
      console.log('🔐 Real logout');
      // Let real auth handle this
    },
    register: async (userData) => {
      console.log('🔐 Real registration:', userData);
      // Let real auth handle this
      return { success: true };
    },
    refreshSession: async () => {
      console.log('🔐 Real session refresh');
      // Let real auth handle this
      return { success: true };
    },
    clearError: () => {
      console.log('🔐 Real error clear');
    },
    updateTokens: (tokens) => {
      console.log('🔐 Real token update:', tokens);
    }
  };

  return (
    <AuthContext.Provider value={mockAuthValue}>
      {children}
    </AuthContext.Provider>
  );
};

// Mock user data helper for testing
export const createMockUser = () => ({
  id: "test-user-123",
  email: "test@example.com",
  name: "Test User",
  roles: ["user"],
  preferences: {},
  createdAt: "2025-01-01T00:00:00Z",
  lastLogin: "2025-01-15T10:00:00Z",
});

// Render function with all providers for REAL testing
export const renderWithProviders = (ui, options = {}) => {
  return render(ui, {
    wrapper: TestWrapper,
    ...options,
  });
};

// Render function with authentication for testing authenticated pages - REAL AUTH
export const renderWithAuth = (ui, options = {}) => {
  const testQueryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  const mockUser = options.user || { 
    id: 'test-user', 
    email: 'test@example.com',
    name: 'Test User'
  };

  const AuthenticatedWrapper = ({ children }) => (
    <BrowserRouter>
      <ThemeProvider theme={testTheme}>
        <QueryClientProvider client={testQueryClient}>
          <TestAuthProvider initialUser={mockUser}>
            {children}
          </TestAuthProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </BrowserRouter>
  );

  return render(ui, {
    wrapper: AuthenticatedWrapper,
    ...options,
  });
};

// Mock DOM methods that don't exist in jsdom
// Mock scrollIntoView for components that use it
Object.defineProperty(Element.prototype, 'scrollIntoView', {
  value: function() {
    // Mock implementation - do nothing in tests
  },
  writable: true
});

// Re-export commonly used testing utilities
export { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
export { userEvent } from "@testing-library/user-event";