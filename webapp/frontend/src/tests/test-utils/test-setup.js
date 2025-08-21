/**
 * Shared test setup utilities for consistent testing across all components
 */

import { vi } from "vitest";
import { render } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createApiMock, resetApiMocks } from "./api-mocks.js";

// Global setup for all tests
export const setupTestEnvironment = () => {
  // Mock global fetch
  global.fetch = vi.fn();
  
  // Setup default successful fetch response
  global.fetch.mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      data: [],
      total: 0,
      page: 1,
      limit: 25
    })
  });

  // Mock the API service
  vi.mock("../../services/api.js", async () => createApiMock());
  
  // Mock the logger service
  vi.mock("../../utils/apiService.jsx", () => ({
    createLogger: vi.fn(() => ({
      info: vi.fn(),
      error: vi.fn(),
      success: vi.fn(),
      warn: vi.fn(),
      debug: vi.fn(),
      queryError: vi.fn(),
    })),
  }));

  // Mock utility functions
  vi.mock("../../utils/formatters.js", () => ({
    formatPercentage: (value) => {
      if (value === null || value === undefined || isNaN(value)) return "N/A%";
      return `${(value * 100).toFixed(2)}%`;
    },
    formatCurrency: (value) => {
      if (value === null || value === undefined || isNaN(value)) return "N/A";
      return `$${value.toLocaleString()}`;
    },
  }));
};

// Test wrapper component for consistent providers
export const TestWrapper = ({ children }) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        cacheTime: 0,
      },
    },
  });

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>{children}</BrowserRouter>
    </QueryClientProvider>
  );
};

// Enhanced render function with all providers
export const renderWithProviders = (ui, options = {}) => {
  return render(ui, {
    wrapper: TestWrapper,
    ...options,
  });
};

// Test cleanup function
export const cleanupTests = () => {
  vi.restoreAllMocks();
  resetApiMocks();
};

// Mock data generators for consistent test data
export const mockTradingData = {
  signals: (count = 2) => ({
    data: Array.from({ length: count }, (_, i) => ({
      id: `signal${i + 1}`,
      symbol: `STOCK${i + 1}`,
      signal: i % 2 === 0 ? "Buy" : "Sell",
      signal_type: i % 2 === 0 ? "buy" : "sell",
      strength: 0.7 + (i * 0.1),
      price: 100 + (i * 50),
      target_price: 110 + (i * 50),
      confidence: 0.8 + (i * 0.05),
      date: new Date(Date.now() - i * 24 * 60 * 60 * 1000).toISOString(),
    })),
    total: count,
    page: 1,
    limit: 25,
  }),

  portfolio: (count = 3) => ({
    data: Array.from({ length: count }, (_, i) => ({
      id: `holding${i + 1}`,
      symbol: `STOCK${i + 1}`,
      quantity: 100 + (i * 50),
      current_price: 50 + (i * 25),
      total_value: (100 + (i * 50)) * (50 + (i * 25)),
      gain_loss: (i % 2 === 0 ? 1 : -1) * (10 + i * 5),
      gain_loss_percentage: (i % 2 === 0 ? 1 : -1) * (0.05 + i * 0.02),
    })),
    total_value: 15000,
    total_gain_loss: 500,
    total_gain_loss_percentage: 0.03,
  }),

  performance: () => ({
    data: {
      total_return: 0.15,
      ytd_return: 0.12,
      monthly_returns: Array.from({ length: 12 }, (_, i) => ({
        month: `2024-${(i + 1).toString().padStart(2, '0')}`,
        return: (Math.random() - 0.5) * 0.1,
      })),
    },
  }),
};

// Common test scenarios
export const testScenarios = {
  loading: () => {
    global.fetch.mockImplementation(() => new Promise(() => {})); // Never resolves
  },
  
  error: (message = "API Error") => {
    global.fetch.mockRejectedValue(new Error(message));
  },
  
  success: (data) => {
    global.fetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => data,
    });
  },
  
  empty: () => {
    global.fetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ data: [], total: 0, page: 1, limit: 25 }),
    });
  },
};