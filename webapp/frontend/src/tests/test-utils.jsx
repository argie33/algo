/**
 * Test Utilities - Real Site Testing Setup
 * Provides wrapper components and utilities for testing actual site functionality
 */

/* eslint-disable react-refresh/only-export-components */

import { render } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import { vi } from "vitest";

// Import the real AuthContext
import { AuthProvider } from "../contexts/AuthContext";
import AuthContext from "../contexts/AuthContext";

// Mock for dev auth with debug logging
vi.mock("../services/devAuth", () => ({
  default: {
    signIn: vi.fn(() => {
      console.log('🧪 devAuth.signIn called in test');
      return Promise.resolve({ user: { email: "test@example.com" }, tokens: {} });
    }),
    signOut: vi.fn(() => Promise.resolve()),
    signUp: vi.fn(() => Promise.resolve({
      isSignUpComplete: false,
      nextStep: { signUpStep: 'CONFIRM_SIGN_UP' }
    })),
    confirmSignUp: vi.fn(() => Promise.resolve({
      isSignUpComplete: true
    })),
    resetPassword: vi.fn(() => Promise.resolve({
      nextStep: { resetPasswordStep: 'CONFIRM_RESET_PASSWORD_WITH_CODE' }
    })),
    confirmResetPassword: vi.fn(() => Promise.resolve()),
    getCurrentUser: vi.fn(() => {
      console.log('🧪 devAuth.getCurrentUser called in test');
      return Promise.resolve({ 
        username: "testuser",
        userId: "dev-testuser",
        email: "test@example.com",
        firstName: "Test",
        lastName: "User"
      });
    }),
    fetchAuthSession: vi.fn(() => {
      console.log('🧪 devAuth.fetchAuthSession called in test');
      return Promise.resolve({ 
        tokens: {
          accessToken: "dev-access-testuser-1234567890",
          idToken: "dev-id-testuser-1234567890",
          refreshToken: "dev-refresh-testuser-1234567890"
        }
      });
    }),
  },
}));

// Mock session manager
vi.mock("../services/sessionManager", () => ({
  default: {
    initialize: vi.fn(),
    setCallbacks: vi.fn(),
    startSession: vi.fn(),
    endSession: vi.fn(),
    extendSession: vi.fn(),
    getSessionStatus: vi.fn(() => ({ isActive: true, timeRemaining: 3600 })),
  },
}));

// Mock amplify config
vi.mock("../config/amplify", () => ({
  isCognitoConfigured: vi.fn(() => false), // Use dev auth instead
}));

// Mock amplify auth
vi.mock("@aws-amplify/auth", () => ({
  fetchAuthSession: vi.fn(() => Promise.resolve({ tokens: null })),
  signIn: vi.fn(() => Promise.resolve()),
  signUp: vi.fn(() => Promise.resolve()),
  confirmSignUp: vi.fn(() => Promise.resolve()),
  signOut: vi.fn(() => Promise.resolve()),
  resetPassword: vi.fn(() => Promise.resolve()),
  confirmResetPassword: vi.fn(() => Promise.resolve()),
  getCurrentUser: vi.fn(() => Promise.resolve({ email: "test@example.com" })),
}));

// Mock API service with reliable responses that match real API structure
vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal();
  
  // Mock API response data that matches your actual backend structure
  const mockPortfolioData = {
    data: [
      {
        id: "1",
        symbol: "AAPL",
        quantity: 100,
        averageCost: 150.25,
        currentPrice: 175.50,
        marketValue: 17550.00,
        totalReturn: 2525.00,
        totalReturnPercent: 16.79,
        dayChange: 2.50,
        dayChangePercent: 1.44
      },
      {
        id: "2", 
        symbol: "GOOGL",
        quantity: 50,
        averageCost: 2200.00,
        currentPrice: 2350.75,
        marketValue: 117537.50,
        totalReturn: 7537.50,
        totalReturnPercent: 6.84,
        dayChange: -15.25,
        dayChangePercent: -0.64
      }
    ]
  };

  const mockMarketOverview = {
    data: {
      indices: {
        SPX: { value: 4500.25, change: 15.75, changePercent: 0.35 },
        DJI: { value: 35000.50, change: -125.25, changePercent: -0.36 },
        NDX: { value: 15250.75, change: 45.50, changePercent: 0.30 }
      },
      sectors: [
        { name: "Technology", performance: 1.25, volume: 125000000 },
        { name: "Healthcare", performance: -0.75, volume: 95000000 },
        { name: "Financials", performance: 0.45, volume: 105000000 }
      ],
      sentiment: {
        overall: 0.65,
        fearGreed: 58,
        trend: "bullish"
      }
    }
  };

  const mockPerformanceData = {
    data: {
      totalValue: 135087.50,
      totalReturn: 10062.50,
      totalReturnPercent: 8.04,
      dayChange: -12.75,
      dayChangePercent: -0.09,
      performance: [
        { date: "2024-01-01", value: 125025.00 },
        { date: "2024-02-01", value: 128500.25 },
        { date: "2024-03-01", value: 135087.50 }
      ]
    }
  };

  const mockApiKeys = {
    data: [
      {
        id: "1",
        provider: "alpaca",
        keyId: "PKTEST***",
        status: "active",
        sandbox: true,
        createdAt: "2024-01-15T10:00:00Z"
      }
    ]
  };

  return {
    ...actual,
    // Configuration
    getApiConfig: vi.fn(() => ({
      baseURL: "http://localhost:3001",
      isServerless: false,
      apiUrl: "http://localhost:3001", 
      isConfigured: true,
      environment: "test",
      isDevelopment: true,
      isProduction: false,
      baseUrl: "/",
    })),
    
    // Portfolio API functions
    getPortfolioData: vi.fn(() => Promise.resolve(mockPortfolioData)),
    getPortfolioPerformance: vi.fn(() => Promise.resolve(mockPerformanceData)),
    getBenchmarkData: vi.fn(() => Promise.resolve(mockPerformanceData)),
    getPortfolioOptimizationData: vi.fn(() => Promise.resolve({ data: {} })),
    runPortfolioOptimization: vi.fn(() => Promise.resolve({ data: { success: true } })),
    getRebalancingRecommendations: vi.fn(() => Promise.resolve({ data: [] })),
    getRiskAnalysis: vi.fn(() => Promise.resolve({ data: { riskScore: 0.65 } })),
    
    // Holdings management
    addHolding: vi.fn(() => Promise.resolve({ data: { success: true } })),
    updateHolding: vi.fn(() => Promise.resolve({ data: { success: true } })),
    deleteHolding: vi.fn(() => Promise.resolve({ data: { success: true } })),
    importPortfolioFromBroker: vi.fn(() => Promise.resolve({ data: { imported: 5 } })),
    
    // API Keys management
    getApiKeys: vi.fn(() => Promise.resolve(mockApiKeys)),
    addApiKey: vi.fn(() => Promise.resolve({ data: { success: true } })),
    updateApiKey: vi.fn(() => Promise.resolve({ data: { success: true } })),
    deleteApiKey: vi.fn(() => Promise.resolve({ data: { success: true } })),
    
    // Market data
    getMarketOverview: vi.fn(() => Promise.resolve(mockMarketOverview)),
    getMarketSentimentHistory: vi.fn(() => Promise.resolve({ data: [] })),
    
    // Stock data functions used by Dashboard
    getStockPrices: vi.fn(() => Promise.resolve({
      data: [
        { date: "2024-01-01", open: 175.00, high: 177.50, low: 174.25, close: 176.50, volume: 1250000 },
        { date: "2024-01-02", open: 176.50, high: 178.75, low: 175.80, close: 177.25, volume: 1100000 },
        { date: "2024-01-03", open: 177.25, high: 179.00, low: 176.50, close: 178.80, volume: 1350000 }
      ]
    })),
    getStockMetrics: vi.fn(() => Promise.resolve({
      data: {
        symbol: "AAPL",
        price: 178.80,
        change: 2.30,
        changePercent: 1.30,
        volume: 1350000,
        marketCap: 2800000000000,
        pe: 28.5,
        beta: 1.2,
        dividend: 0.96,
        yield: 0.54
      }
    })),
    
    // Utility functions
    getCurrentBaseURL: vi.fn(() => "http://localhost:3001"),
    updateApiBaseUrl: vi.fn(),
    
    // Export mock axios instance
    api: {
      get: vi.fn(() => Promise.resolve({ data: { success: true } })),
      post: vi.fn(() => Promise.resolve({ data: { success: true } })),
      put: vi.fn(() => Promise.resolve({ data: { success: true } })),
      delete: vi.fn(() => Promise.resolve({ data: { success: true } })),
      defaults: { baseURL: "http://localhost:3001" }
    }
  };
});

// Test-specific AuthProvider that doesn't trigger side effects during tests
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
      accessToken: 'mock-access-token',
      refreshToken: 'mock-refresh-token'
    } : null,
    error: null,
    login: vi.fn().mockResolvedValue({ success: true }),
    logout: vi.fn().mockResolvedValue(undefined),
    register: vi.fn().mockResolvedValue({ success: true }),
    refreshSession: vi.fn().mockResolvedValue({ success: true }),
    clearError: vi.fn(),
    updateTokens: vi.fn()
  };

  return (
    <AuthContext.Provider value={mockAuthValue}>
      {children}
    </AuthContext.Provider>
  );
};

// Remove mock auth hook since we're using real AuthProvider

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

// Mock user data helper
export const createMockUser = () => ({
  id: "test-user-123",
  email: "test@example.com",
  name: "Test User",
  roles: ["user"],
  preferences: {},
  createdAt: "2025-01-01T00:00:00Z",
  lastLogin: "2025-01-15T10:00:00Z",
});

// Render function with all providers for testing
export const renderWithProviders = (ui, options = {}) => {
  return render(ui, {
    wrapper: TestWrapper,
    ...options,
  });
};

// Re-export commonly used testing utilities
export { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
export { userEvent } from "@testing-library/user-event";
