/**
 * Test Environment Setup
 * Provides proper environment variable isolation for tests
 */

import { vi } from 'vitest';

// Store original values
const originalEnv = { ...import.meta.env };
const originalWindow = global.window;

/**
 * Setup isolated test environment
 */
export const setupTestEnvironment = (customEnv = {}) => {
  // Mock import.meta.env
  const mockEnv = {
    ...originalEnv,
    MODE: 'test',
    DEV: true,
    PROD: false,
    VITE_API_URL: undefined, // Clear by default
    ...customEnv
  };

  // Replace import.meta.env
  vi.stubGlobal('import', {
    meta: {
      env: mockEnv
    }
  });

  // Setup clean window object
  global.window = {
    location: { href: 'http://localhost:3000' },
    navigator: { userAgent: 'test' },
    innerWidth: 1024,
    innerHeight: 768,
    localStorage: {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    },
    sessionStorage: {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    },
    fetch: vi.fn(() => 
      Promise.resolve({
        ok: false,
        status: 404,
        json: () => Promise.resolve({}),
        text: () => Promise.resolve('')
      })
    ),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
    matchMedia: vi.fn(() => ({
      matches: false,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
    getComputedStyle: vi.fn(() => ({})),
    ResizeObserver: class MockResizeObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
    IntersectionObserver: class MockIntersectionObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  };

  return mockEnv;
};

/**
 * Cleanup test environment
 */
export const cleanupTestEnvironment = () => {
  vi.unstubAllGlobals();
  global.window = originalWindow;
};

/**
 * Setup environment for API configuration tests
 */
export const setupApiTestEnvironment = (windowConfig = null, envConfig = null) => {
  const env = setupTestEnvironment(envConfig ? { VITE_API_URL: envConfig } : {});
  
  if (windowConfig) {
    global.window.__CONFIG__ = { API_URL: windowConfig };
  }

  return env;
};

/**
 * Create isolated API config function for testing
 */
export const createTestApiConfig = (windowApiUrl = null, envApiUrl = null) => {
  // Mock the environment variables directly
  const mockImportMeta = {
    env: {
      VITE_API_URL: envApiUrl,
      MODE: 'test',
      DEV: true,
      PROD: false,
      BASE_URL: '/'
    }
  };

  // Mock window config
  const mockWindow = {
    __CONFIG__: windowApiUrl ? { API_URL: windowApiUrl } : undefined
  };

  // Create isolated config function
  return () => {
    const apiUrl = mockWindow.__CONFIG__?.API_URL || mockImportMeta.env.VITE_API_URL;
    
    if (!apiUrl) {
      throw new Error('API URL not configured - set VITE_API_URL environment variable or window.__CONFIG__.API_URL');
    }

    return {
      baseURL: apiUrl,
      isServerless: !!apiUrl && !apiUrl.includes('localhost'),
      apiUrl: apiUrl,
      isConfigured: !!apiUrl && !apiUrl.includes('localhost') && !apiUrl.includes('PLACEHOLDER'),
      environment: mockImportMeta.env.MODE,
      isDevelopment: mockImportMeta.env.DEV,
      isProduction: mockImportMeta.env.PROD,
      baseUrl: mockImportMeta.env.BASE_URL,
      allEnvVars: mockImportMeta.env
    };
  };
};