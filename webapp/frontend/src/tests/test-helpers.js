/**
 * Test Helper Functions and Constants
 * Non-component utilities for testing
 */

// Real API configuration for testing actual site
export const REAL_API_CONFIG = {
  apiUrl: process.env.VITE_API_URL || 'http://localhost:3001', // Dynamic URL from CloudFormation
  timeout: 30000,
};

// Mock API responses
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
export const waitForLoadingToFinish = async () => {
  // Wait for loading states to complete
  await new Promise((resolve) => setTimeout(resolve, 0));
};

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


// Re-export testing library utilities
export * from "@testing-library/react";
export { vi } from "vitest";