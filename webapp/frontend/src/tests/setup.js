/**
 * Test Setup Configuration
 * Main entry point for test environment setup
 */

import { beforeAll, afterAll, beforeEach, afterEach, vi } from 'vitest'
// import { cleanup } from '@testing-library/react' // Disabled to prevent React issues
import '@testing-library/jest-dom'

// Disable automatic cleanup from RTL
process.env.RTL_SKIP_AUTO_CLEANUP = 'true'

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
  
  // Mock import.meta.env globally using vitest
  const mockImportMeta = {
    env: {
      MODE: 'test',
      DEV: true,
      PROD: false,
      BASE_URL: '/',
      VITE_API_URL: 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'
    }
  };
  
  // Use vitest's stubGlobal to properly mock import.meta
  vi.stubGlobal('import', { meta: mockImportMeta });
  
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
  
  // Mock browser APIs for notifications and audio
  global.AudioContext = class MockAudioContext {
    constructor() {
      this.destination = {};
      this.sampleRate = 44100;
      this.currentTime = 0;
      this.state = 'running';
    }
    createOscillator() {
      return {
        frequency: { value: 440 },
        connect: vi.fn(),
        start: vi.fn(),
        stop: vi.fn()
      };
    }
    createGain() {
      return {
        gain: { value: 1 },
        connect: vi.fn()
      };
    }
    close() { return Promise.resolve(); }
  };
  
  global.webkitAudioContext = global.AudioContext;
  
  global.Notification = class MockNotification {
    constructor(title, options) {
      this.title = title;
      this.body = options?.body;
      this.icon = options?.icon;
    }
    static requestPermission() {
      return Promise.resolve('granted');
    }
    static permission = 'granted';
  };

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

  // Ensure browser APIs are available on window
  global.window.AudioContext = global.AudioContext;
  global.window.webkitAudioContext = global.webkitAudioContext;
  global.window.Notification = global.Notification;

  // Mock performance API
  global.performance = {
    now: vi.fn(() => Date.now()),
    mark: vi.fn(),
    measure: vi.fn(),
    getEntriesByType: vi.fn(() => []),
    getEntriesByName: vi.fn(() => []),
    clearMarks: vi.fn(),
    clearMeasures: vi.fn(),
  };
  global.window.performance = global.performance;
  
  if (typeof document === 'undefined') {
    const mockElement = {
      style: {},
      setAttribute: vi.fn(),
      getAttribute: vi.fn(() => null),
      appendChild: vi.fn(),
      removeChild: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      querySelector: vi.fn(() => null),
      querySelectorAll: vi.fn(() => []),
      textContent: '',
      innerHTML: '',
      children: [],
      parentNode: null,
      nextSibling: null,
      previousSibling: null,
      nodeName: 'DIV',
      nodeType: 1,
      ownerDocument: null,
      getBoundingClientRect: () => ({ x: 0, y: 0, width: 0, height: 0, top: 0, left: 0, bottom: 0, right: 0 }),
      scrollIntoView: vi.fn(),
      focus: vi.fn(),
      blur: vi.fn(),
      click: vi.fn(),
    };

    global.document = {
      body: { ...mockElement, tagName: 'BODY' },
      head: { ...mockElement, tagName: 'HEAD' },
      documentElement: { ...mockElement, tagName: 'HTML' },
      createElement: vi.fn(() => ({ ...mockElement })),
      createTextNode: vi.fn(text => ({
        ...mockElement,
        textContent: text,
        nodeType: 3,
        nodeName: '#text'
      })),
      getElementById: vi.fn(() => mockElement),
      querySelector: vi.fn(() => mockElement),
      querySelectorAll: vi.fn(() => [mockElement]),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      createEvent: vi.fn(() => ({
        initEvent: vi.fn(),
        preventDefault: vi.fn(),
        stopPropagation: vi.fn(),
      })),
      createDocumentFragment: vi.fn(() => mockElement),
      defaultView: global.window,
      readyState: 'complete',
    };
    
    // Set ownerDocument for created elements
    global.document.createElement = vi.fn(() => ({
      ...mockElement,
      ownerDocument: global.document,
    }));
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

// Cleanup after each test - disabled to prevent React concurrent issues
afterEach(() => {
  // cleanup() // Disabled - causing React concurrent work conflicts
  vi.clearAllMocks()
  
  // Manual cleanup approach
  try {
    document.body.innerHTML = '';
  } catch (e) {
    // Ignore cleanup errors
  }
})

// Global teardown
afterAll(() => {
  console.log('🧹 Cleaning up test environment...')
})

export default {}