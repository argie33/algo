// Test setup file for Vitest
import { vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeAll } from 'vitest';

// Mock environment variables
Object.defineProperty(import.meta, 'env', {
  value: {
    VITE_API_URL: 'http://localhost:3000',
    VITE_ALPACA_API_KEY: 'test_key',
    VITE_ALPACA_API_SECRET: 'test_secret',
    VITE_FRED_API_KEY: 'test_fred_key',
    MODE: 'test'
  },
  writable: true
});

// Mock process.env for compatibility
global.process = {
  env: {
    NODE_ENV: 'test',
    REACT_APP_API_URL: 'http://localhost:3000',
    REACT_APP_ALPACA_API_KEY: 'test_key',
    REACT_APP_ALPACA_API_SECRET: 'test_secret',
    REACT_APP_FRED_API_KEY: 'test_fred_key'
  }
};

// Mock WebSocket
global.WebSocket = vi.fn(() => ({
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  send: vi.fn(),
  close: vi.fn(),
  readyState: 1, // OPEN
  CONNECTING: 0,
  OPEN: 1,
  CLOSING: 2,
  CLOSED: 3
}));

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
  key: vi.fn(),
  length: 0
};

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock
});

// Mock sessionStorage
Object.defineProperty(window, 'sessionStorage', {
  value: localStorageMock
});

// Mock IntersectionObserver
global.IntersectionObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn()
}));

// Mock ResizeObserver
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn()
}));

// Mock URL.createObjectURL
global.URL.createObjectURL = vi.fn(() => 'mock-url');

// Mock fetch
global.fetch = vi.fn();

// Mock console methods to reduce noise in tests
global.console = {
  ...console,
  warn: vi.fn(),
  error: vi.fn(),
  log: vi.fn(),
  info: vi.fn()
};

// Mock Date.now for consistent testing
const mockDateNow = 1640995200000; // 2022-01-01T00:00:00.000Z
vi.spyOn(Date, 'now').mockReturnValue(mockDateNow);

// Mock Math.random for predictable results in tests
let randomIndex = 0;
const randomValues = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.0];
vi.spyOn(Math, 'random').mockImplementation(() => {
  const value = randomValues[randomIndex % randomValues.length];
  randomIndex++;
  return value;
});

// Setup and cleanup
beforeAll(() => {
  // Reset all mocks before all tests
  vi.clearAllMocks();
});

afterEach(() => {
  // Cleanup DOM after each test
  cleanup();
  
  // Clear localStorage and sessionStorage
  localStorageMock.clear();
  
  // Reset mock implementations
  vi.clearAllTimers();
  
  // Reset random index for predictable Math.random
  randomIndex = 0;
});

// Global test utilities
global.testUtils = {
  mockApiResponse: (data, success = true) => ({
    data: success ? { success: true, data } : { success: false, error: 'API Error' },
    status: success ? 200 : 500,
    statusText: success ? 'OK' : 'Internal Server Error'
  }),
  
  mockWebSocketMessage: (type, data) => ({
    data: JSON.stringify({ type, data }),
    origin: 'ws://localhost:8080',
    type: 'message'
  }),
  
  waitFor: (ms) => new Promise(resolve => setTimeout(resolve, ms)),
  
  createMockUser: (overrides = {}) => ({
    id: 'user_123',
    email: 'test@example.com',
    name: 'Test User',
    username: 'testuser',
    avatar: 'https://example.com/avatar.jpg',
    isVerified: true,
    createdAt: new Date().toISOString(),
    ...overrides
  }),
  
  createMockStock: (symbol = 'AAPL', overrides = {}) => ({
    symbol,
    name: 'Apple Inc.',
    price: 150.00,
    change: 2.50,
    changePercent: 1.69,
    volume: 50000000,
    marketCap: 2500000000000,
    ...overrides
  }),
  
  createMockPortfolio: (overrides = {}) => ({
    totalValue: 100000,
    totalPnl: 5000,
    totalPnlPercent: 5.0,
    positions: [],
    cash: 10000,
    ...overrides
  })
};