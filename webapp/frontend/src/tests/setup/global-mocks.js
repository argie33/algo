/**
 * Global Mocks for Test Environment
 * These mocks are applied immediately when imported
 */

import { vi } from 'vitest'

// Immediately mock localStorage if not available
if (typeof localStorage === 'undefined') {
  global.localStorage = {
    getItem: vi.fn(),
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
    length: 0,
    key: vi.fn()
  }
}

// Immediately mock sessionStorage if not available
if (typeof sessionStorage === 'undefined') {
  global.sessionStorage = {
    getItem: vi.fn(),
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
    length: 0,
    key: vi.fn()
  }
}

// Mock window and document immediately
if (typeof window === 'undefined') {
  global.window = {
    localStorage: global.localStorage,
    sessionStorage: global.sessionStorage,
    location: { href: 'http://localhost' },
    navigator: { userAgent: 'vitest' }
  }
}

if (typeof document === 'undefined') {
  global.document = {
    createElement: vi.fn(),
    getElementById: vi.fn(),
    querySelector: vi.fn(),
    querySelectorAll: vi.fn()
  }
}

// Mock other browser APIs
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

// Mock fetch
global.fetch = vi.fn()

// Mock URL and Blob APIs
global.URL = {
  createObjectURL: vi.fn(),
  revokeObjectURL: vi.fn(),
}

global.Blob = vi.fn()
global.FileReader = vi.fn()
global.FormData = vi.fn()

export default {}