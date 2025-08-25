/* eslint-disable react-refresh/only-export-components */
/**
 * Component Test Utilities
 * Helpers for React component unit testing
 */

import React from "react";
import { render, screen } from "@testing-library/react";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { vi } from "vitest";

// Create test QueryClient with disabled retries and caching
export const createTestQueryClient = () => new QueryClient({
  defaultOptions: {
    queries: {
      retry: false,
      cacheTime: 0,
      staleTime: 0,
    },
    mutations: {
      retry: false,
    },
  },
});

// Default MUI theme for component testing
export const createTestTheme = () => createTheme({
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

// Minimal wrapper for MUI components with React Query
export const MuiWrapper = ({ children, theme = createTestTheme(), queryClient = createTestQueryClient() }) => (
  <QueryClientProvider client={queryClient}>
    <ThemeProvider theme={theme}>
      {children}
    </ThemeProvider>
  </QueryClientProvider>
);

// Render with MUI theme provider and React Query
export const renderWithTheme = (ui, options = {}) => {
  const { theme = createTestTheme(), queryClient = createTestQueryClient(), ...renderOptions } = options;
  
  const Wrapper = ({ children }) => (
    <MuiWrapper theme={theme} queryClient={queryClient}>
      {children}
    </MuiWrapper>
  );
  
  return render(ui, { wrapper: Wrapper, ...renderOptions });
};

// Mock portfolio data for components
export const createMockPortfolioData = (overrides = {}) => ({
  totalValue: 125750.50,
  todaysPnL: 2500.75,
  totalPnL: 25750.50,
  holdings: [
    {
      symbol: "AAPL",
      quantity: 100,
      currentPrice: 150.25,
      marketValue: 15025,
      avgCost: 145.0,
      unrealizedPnL: 525,
      percentageReturn: 3.62,
    },
    {
      symbol: "MSFT", 
      quantity: 50,
      currentPrice: 280.5,
      marketValue: 14025,
      avgCost: 275.0,
      unrealizedPnL: 275,
      percentageReturn: 2.0,
    },
  ],
  lastUpdated: "2025-08-23T12:00:00Z",
  ...overrides,
});

// Mock market data for components
export const createMockMarketData = (overrides = {}) => ({
  isOpen: true,
  session: "Open",
  nextChange: "Closes at 4:00 PM",
  indices: [
    {
      symbol: "SPX",
      name: "S&P 500", 
      value: 4500.25,
      change: 25.50,
      changePercent: 0.57,
    },
    {
      symbol: "DJI",
      name: "Dow Jones",
      value: 35250.75,
      change: -125.25,
      changePercent: -0.35,
    },
    {
      symbol: "IXIC",
      name: "Nasdaq",
      value: 14125.50,
      change: 85.75,
      changePercent: 0.62,
    },
  ],
  ...overrides,
});

// Mock stock data for components
export const createMockStockData = (symbol = "AAPL", overrides = {}) => ({
  symbol,
  name: symbol === "AAPL" ? "Apple Inc." : `${symbol} Company`,
  currentPrice: 150.25,
  change: 2.50,
  changePercent: 1.69,
  volume: 50000000,
  marketCap: 2500000000000,
  high52Week: 180.50,
  low52Week: 125.25,
  dividend: 0.92,
  dividendYield: 0.61,
  pe: 25.5,
  beta: 1.2,
  lastUpdated: "2025-08-23T12:00:00Z",
  ...overrides,
});

// Mock user data for components
export const createMockUser = (overrides = {}) => ({
  id: "user-123",
  username: "testuser",
  email: "test@example.com",
  firstName: "Test",
  lastName: "User",
  isVerified: true,
  subscriptionTier: "premium",
  ...overrides,
});

// Mock API key data for components
export const createMockApiKey = (provider = "alpaca", overrides = {}) => ({
  provider,
  keyId: `${provider.toUpperCase()}***ABC123`,
  isValid: true,
  lastValidated: "2025-08-23T10:00:00Z",
  permissions: ["read", "write"],
  ...overrides,
});

// Mock event handlers
export const createMockEventHandlers = () => ({
  onClick: vi.fn(),
  onChange: vi.fn(),
  onSubmit: vi.fn(),
  onFocus: vi.fn(),
  onBlur: vi.fn(),
  onKeyDown: vi.fn(),
  onMouseEnter: vi.fn(),
  onMouseLeave: vi.fn(),
});

// Component prop builders
export const buildButtonProps = (overrides = {}) => ({
  variant: "contained",
  size: "medium",
  color: "primary",
  disabled: false,
  ...overrides,
});

export const buildCardProps = (overrides = {}) => ({
  elevation: 1,
  variant: "elevation",
  ...overrides,
});

export const buildTextFieldProps = (overrides = {}) => ({
  variant: "outlined",
  size: "medium",
  fullWidth: false,
  disabled: false,
  required: false,
  ...overrides,
});

// Error boundary test helper
export const ErrorThrowingComponent = ({ shouldThrow = true, error = new Error("Test error") }) => {
  if (shouldThrow) {
    throw error;
  }
  return <div>No error</div>;
};

// Async component test helper
export const AsyncComponent = ({ delay = 100, children }) => {
  const [loaded, setLoaded] = React.useState(false);
  
  React.useEffect(() => {
    const timer = setTimeout(() => setLoaded(true), delay);
    return () => clearTimeout(timer);
  }, [delay]);
  
  return loaded ? children : <div>Loading...</div>;
};

// Form test helpers
export const submitForm = async (form, user) => {
  await user.click(screen.getByRole("button", { name: /submit/i }));
};

export const fillTextField = async (label, value, user) => {
  const field = screen.getByLabelText(label);
  await user.clear(field);
  await user.type(field, value);
};

// Accessibility test helpers
export const checkAccessibility = (element) => {
  const violations = [];
  
  // Check for basic accessibility attributes
  if (element.getAttribute("role") === "button" && !element.getAttribute("aria-label") && !element.textContent.trim()) {
    violations.push("Button missing accessible name");
  }
  
  if (element.tagName === "INPUT" && !element.getAttribute("aria-label") && !element.labels?.length) {
    violations.push("Input missing label");
  }
  
  return violations;
};

// Performance test helper
export const measureRenderTime = (renderFn) => {
  const start = performance.now();
  const result = renderFn();
  const end = performance.now();
  
  return {
    result,
    renderTime: end - start,
  };
};

// Component lifecycle test helpers
export const testComponentLifecycle = (Component, props = {}) => ({
  mount: () => render(<Component {...props} />),
  unmount: (result) => result.unmount(),
  rerender: (result, newProps) => result.rerender(<Component {...props} {...newProps} />),
});

// Snapshot test helper (for visual regression)
export const createSnapshot = (component) => {
  const { container } = renderWithTheme(component);
  return container.firstChild;
};

export default {
  renderWithTheme,
  MuiWrapper,
  createTestQueryClient,
  createMockPortfolioData,
  createMockMarketData,
  createMockStockData,
  createMockUser,
  createMockApiKey,
  createMockEventHandlers,
  buildButtonProps,
  buildCardProps,
  buildTextFieldProps,
  ErrorThrowingComponent,
  AsyncComponent,
  submitForm,
  fillTextField,
  checkAccessibility,
  measureRenderTime,
  testComponentLifecycle,
  createSnapshot,
};