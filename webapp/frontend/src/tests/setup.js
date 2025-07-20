/**
 * Test Setup Configuration
 * Main entry point for test environment setup
 */

import { beforeAll, afterAll, beforeEach, afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'
import '@testing-library/jest-dom'

// Global test setup
beforeAll(async () => {
  console.log('🧪 Setting up test environment...')
  
  // Set up global test environment variables
  process.env.NODE_ENV = 'test'
  process.env.VITE_API_URL = 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev'
  
  // Mock console methods to reduce noise in tests
  global.console = {
    ...console,
    log: vi.fn(),
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }
  
  // Setup DOM globals for JSDOM
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  
  global.IntersectionObserver = class IntersectionObserver {
    constructor() {}
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  
  // Mock window.matchMedia
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation(query => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  })
  
  // Mock localStorage with working implementation
  const localStorageData = {}
  const localStorageMock = {
    getItem: vi.fn((key) => localStorageData[key] || null),
    setItem: vi.fn((key, value) => { localStorageData[key] = String(value) }),
    removeItem: vi.fn((key) => { delete localStorageData[key] }),
    clear: vi.fn(() => { Object.keys(localStorageData).forEach(key => delete localStorageData[key]) }),
    length: 0,
    key: vi.fn((index) => Object.keys(localStorageData)[index] || null)
  }
  global.localStorage = localStorageMock
  
  // Mock window and document if not available
  if (typeof window === 'undefined') {
    global.window = {}
  }
  
  if (typeof document === 'undefined') {
    global.document = {}
  }
  
  // Additional browser API mocks
  global.URL = {
    createObjectURL: vi.fn(),
    revokeObjectURL: vi.fn(),
  }
  
  global.Blob = vi.fn()
  global.FileReader = vi.fn()
  global.FormData = vi.fn()
  
  // Mock common React hooks that might be used
  global.React = global.React || {}
  
  // Mock fetch if not available
  if (!global.fetch) {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({}),
      text: vi.fn().mockResolvedValue(''),
      status: 200
    })
  }
  
  console.log('✅ Test environment setup complete')
})

// Cleanup after each test
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

// Global teardown
afterAll(() => {
  console.log('🧹 Cleaning up test environment...')
})

export default {}