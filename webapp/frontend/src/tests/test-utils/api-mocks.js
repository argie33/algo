/**
 * Shared API mocks for testing
 * Provides consistent mocking for the api.js service across all tests
 */

import { vi } from 'vitest'

// Standard API config mock
export const mockApiConfig = {
  baseURL: "http://localhost:3001",
  isServerless: false,
  apiUrl: "http://localhost:3001",
  isConfigured: true,
  environment: "test",
  isDevelopment: true,
  isProduction: false,
  baseUrl: "/",
  allEnvVars: {
    MODE: "test",
    DEV: true,
    PROD: false,
  }
}

// Standard API service mock
export const mockApiService = {
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  patch: vi.fn(),
}

// Complete API module mock
export const createApiMock = () => ({
  getApiConfig: vi.fn(() => mockApiConfig),
  api: mockApiService,
  default: mockApiService,
  
  // Portfolio functions
  getPortfolioData: vi.fn(() => Promise.resolve({ data: { holdings: [] } })),
  getPortfolioAnalytics: vi.fn(() => Promise.resolve({ data: {} })),
  
  // API Key functions
  getApiKeys: vi.fn(() => Promise.resolve({ data: [] })),
  addApiKey: vi.fn(() => Promise.resolve({ success: true })),
  updateApiKey: vi.fn(() => Promise.resolve({ success: true })),
  deleteApiKey: vi.fn(() => Promise.resolve({ success: true })),
  
  // Market data functions
  getMarketOverview: vi.fn(() => Promise.resolve({ data: {} })),
  getStocks: vi.fn(() => Promise.resolve({ data: [] })),
  getHealth: vi.fn(() => Promise.resolve({ status: 'ok' })),
  
  // Dashboard functions
  getDashboardSummary: vi.fn(() => Promise.resolve({ data: {} })),
  getDashboardPortfolio: vi.fn(() => Promise.resolve({ data: {} })),
  
  // Technical data
  getTechnicalData: vi.fn(() => Promise.resolve({ data: [] })),
  getTechnicalHistory: vi.fn(() => Promise.resolve({ data: [] })),
  
  // Risk analysis
  getRiskAnalysis: vi.fn(() => Promise.resolve({ data: {} })),
})

// Helper to reset all mocks
export const resetApiMocks = () => {
  Object.values(mockApiService).forEach(mock => mock.mockClear())
}

// Common API response mocks
export const mockApiResponses = {
  success: (data = {}) => ({ data, status: 200, statusText: 'OK' }),
  error: (message = 'API Error', status = 500) => {
    const error = new Error(message)
    error.response = { status, statusText: 'Internal Server Error' }
    return Promise.reject(error)
  },
  loading: () => new Promise(() => {}), // Never resolves for loading tests
}