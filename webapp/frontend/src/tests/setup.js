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
  
  // Add timeout to prevent hanging
  const setupTimeout = setTimeout(() => {
    console.error('⚠️ Test setup timeout - forcing completion');
  }, 5000);
  
  // Set up global test environment variables
  process.env.NODE_ENV = 'test'
  process.env.VITE_API_URL = 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'
  
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
    global.document = {
      body: {},
      head: {},
      documentElement: {},
      createElement: vi.fn(() => ({
        style: {},
        setAttribute: vi.fn(),
        getAttribute: vi.fn(),
        appendChild: vi.fn(),
        removeChild: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        querySelector: vi.fn(),
        querySelectorAll: vi.fn(() => []),
      })),
      getElementById: vi.fn(),
      querySelector: vi.fn(),
      querySelectorAll: vi.fn(() => []),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      createEvent: vi.fn(() => ({
        initEvent: vi.fn(),
      })),
    }
  }
  
  // Additional browser API mocks
  global.URL = {
    createObjectURL: vi.fn(),
    revokeObjectURL: vi.fn(),
  }
  
  global.Blob = vi.fn()
  global.FileReader = vi.fn()
  global.FormData = vi.fn()
  
  // Chart component mocks for Recharts
  global.SVGElement = class SVGElement extends Element {
    getBBox() {
      return { x: 0, y: 0, width: 0, height: 0 };
    }
    createSVGMatrix() {
      return { a: 1, b: 0, c: 0, d: 1, e: 0, f: 0 };
    }
  }
  
  global.Element = class Element {
    getBBox() { return { x: 0, y: 0, width: 100, height: 100 }; }
    getBoundingClientRect() { 
      return { x: 0, y: 0, width: 100, height: 100, top: 0, left: 0, bottom: 100, right: 100 }; 
    }
  }
  
  // Mock HTMLCanvasElement for chart rendering
  global.HTMLCanvasElement = class HTMLCanvasElement {
    constructor() {
      this.width = 300;
      this.height = 150;
    }
    getContext() {
      return {
        fillRect: vi.fn(),
        clearRect: vi.fn(),
        getImageData: vi.fn(() => ({ data: new Array(4) })),
        putImageData: vi.fn(),
        createImageData: vi.fn(() => ({ data: new Array(4) })),
        setTransform: vi.fn(),
        drawImage: vi.fn(),
        save: vi.fn(),
        fillText: vi.fn(),
        restore: vi.fn(),
        beginPath: vi.fn(),
        moveTo: vi.fn(),
        lineTo: vi.fn(),
        closePath: vi.fn(),
        stroke: vi.fn(),
        translate: vi.fn(),
        scale: vi.fn(),
        rotate: vi.fn(),
        arc: vi.fn(),
        fill: vi.fn(),
        measureText: vi.fn(() => ({ width: 0 })),
        transform: vi.fn(),
        rect: vi.fn(),
        clip: vi.fn()
      };
    }
    toDataURL() { return 'data:image/png;base64,'; }
  }
  
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
  
  clearTimeout(setupTimeout);
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