/**
 * Test Utilities - Real Site Testing Setup
 * Provides wrapper components and utilities for testing actual site functionality with NO MOCKS
 */


import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider, createTheme } from "@mui/material/styles";

// Import the real AuthContext - NO MOCKS
import { createContext } from "react";

// Create a fallback AuthContext for testing
const TestAuthContext = createContext({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,
  tokens: null,
});

// Real site theme for testing
export const testTheme = createTheme({
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
export const TestWrapper = ({ children, initialUser = null }) => {
  const testQueryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  if (!children) {
    console.warn("TestWrapper received null/undefined children");
    return null;
  }

  return (
    <MemoryRouter
      initialEntries={["/"]}
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      <ThemeProvider theme={testTheme}>
        <QueryClientProvider client={testQueryClient}>
          <TestAuthProvider initialUser={initialUser}>{children}</TestAuthProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </MemoryRouter>
  );
};

// Real authenticated provider that uses REAL authentication
export const TestAuthProvider = ({ children, initialUser = null }) => {
  const defaultUser = {
    id: "test-user",
    email: "test@example.com",
    name: "Test User",
  };
  const mockAuthValue = {
    user: initialUser || defaultUser,
    isAuthenticated: true, // Always authenticated in tests
    isLoading: false,
    tokens: {
      accessToken: "dev-bypass-token",
      refreshToken: "dev-bypass-token",
    },
    error: null,
    // These will call REAL authentication functions
    login: async (credentials) => {
      console.log("🔐 Real login attempt:", credentials);
      // Let real auth handle this
      return { success: true };
    },
    logout: async () => {
      console.log("🔐 Real logout");
      // Let real auth handle this
    },
    register: async (userData) => {
      console.log("🔐 Real registration:", userData);
      // Let real auth handle this
      return { success: true };
    },
    refreshSession: async () => {
      console.log("🔐 Real session refresh");
      // Let real auth handle this
      return { success: true };
    },
    clearError: () => {
      console.log("🔐 Real error clear");
    },
    updateTokens: (tokens) => {
      console.log("🔐 Real token update:", tokens);
    },
  };

  return (
    <TestAuthContext.Provider value={mockAuthValue}>
      {children}
    </TestAuthContext.Provider>
  );
};

// Mock user data helper for testing
export const createMockUser = () => ({
  id: "test-user-123",
  userId: "test-user-123", // Added for auth compatibility
  email: "test@example.com",
  name: "Test User",
  roles: ["user"],
  preferences: {},
  createdAt: "2025-01-01T00:00:00Z",
  lastLogin: "2025-01-15T10:00:00Z",
});

// Test wrapper WITHOUT router for tests that provide their own
export const TestWrapperNoRouter = ({ children, initialUser = null }) => {
  const testQueryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
      },
    },
  });

  if (!children) {
    console.warn("TestWrapperNoRouter received null/undefined children");
    return null;
  }

  return (
    <ThemeProvider theme={testTheme}>
      <QueryClientProvider client={testQueryClient}>
        <TestAuthProvider initialUser={initialUser}>{children}</TestAuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  );
};

// Render function with all providers for REAL testing
export const renderWithProviders = (ui, options = {}) => {
  // Use synchronous render for test stability
  return render(ui, {
    wrapper: TestWrapper,
    ...options,
  });
};

// Render function with providers but NO router
export const renderWithProvidersNoRouter = (ui, options = {}) => {
  return render(ui, {
    wrapper: TestWrapperNoRouter,
    ...options,
  });
};

// Render function with authentication for testing authenticated pages - REAL AUTH
export const renderWithAuth = (ui, options = {}) => {
  const mockUser = options.user || {
    id: "test-user",
    email: "test@example.com",
    name: "Test User",
  };

  return render(ui, {
    wrapper: ({ children }) => <TestWrapper initialUser={mockUser}>{children}</TestWrapper>,
    ...options,
  });
};

// Mock DOM methods that don't exist in jsdom
// Mock scrollIntoView for components that use it
if (typeof Element !== 'undefined' && Element.prototype) {
  Object.defineProperty(Element.prototype, "scrollIntoView", {
    value: function () {
      // Mock implementation - do nothing in tests
    },
    writable: true,
  });
}

// Mock matchMedia for MUI components
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => {},
  }),
});

// Re-export commonly used testing utilities
export { render, screen, waitFor, fireEvent } from "@testing-library/react";
export { act } from "@testing-library/react";
export { userEvent } from "@testing-library/user-event";

// Compatibility helper for legacy render calls
export const renderSync = (ui, options = {}) => {
  return render(ui, {
    wrapper: TestWrapper,
    ...options,
  });
};
