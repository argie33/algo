import { afterEach, afterAll, beforeEach, vi } from "vitest";
import { cleanup, configure } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from 'react';

// Configure React Testing Library for React 18
configure({ 
  testIdAttribute: 'data-testid',
  asyncUtilTimeout: 5000,
  reactStrictMode: false
});

// Prevent React 18 concurrent mode issues in tests
global.IS_REACT_ACT_ENVIRONMENT = true;

// Ensure NODE_ENV is properly set for all our test guards
if (typeof process !== 'undefined') {
  process.env.NODE_ENV = 'test';
}

// Mock ResizeObserver for recharts
global.ResizeObserver = class ResizeObserver {
  constructor(cb) {
    this.cb = cb;
  }
  observe(element) {
    if (this.cb && element) {
      this.cb([{
        target: element,
        contentRect: { width: 600, height: 400, top: 0, left: 0, right: 600, bottom: 400 }
      }]);
    }
  }
  unobserve() {}
  disconnect() {}
};

// Mock getBoundingClientRect for chart components
if (typeof HTMLElement !== 'undefined') {
  HTMLElement.prototype.getBoundingClientRect = function() {
    return {
      width: 600, height: 400, top: 0, left: 0, right: 600, bottom: 400, x: 0, y: 0,
      toJSON: function() {}
    };
  };
}

// Ensure document structure
if (typeof global.document !== 'undefined') {
  if (!global.document.body) {
    global.document.body = global.document.createElement('body');
    global.document.documentElement = global.document.documentElement || global.document.createElement('html');
    global.document.documentElement.appendChild(global.document.body);
  }
  
  if (!global.document.getElementById('root')) {
    const rootDiv = global.document.createElement('div');
    rootDiv.id = 'root';
    global.document.body.appendChild(rootDiv);
  }
}

// Essential mocks
vi.mock('@mui/icons-material', () => {
  return new Proxy({}, {
    get(target, iconName) {
      if (typeof iconName === 'string') {
        return (props) => React.createElement('div', { 
          'data-testid': `${iconName.toLowerCase()}-icon`,
          'data-icon': iconName,
          ...props 
        });
      }
      return undefined;
    }
  });
});

// Mock localStorage/sessionStorage
Object.defineProperty(window, 'localStorage', {
  value: {
    getItem: vi.fn(), setItem: vi.fn(), removeItem: vi.fn(), clear: vi.fn(), key: vi.fn(), length: 0
  },
  writable: true
});

Object.defineProperty(window, 'sessionStorage', {
  value: {
    getItem: vi.fn(), setItem: vi.fn(), removeItem: vi.fn(), clear: vi.fn(), key: vi.fn(), length: 0
  },
  writable: true
});

// Mock window.matchMedia for MUI
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query) => ({
    matches: false, media: query, onchange: null,
    addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => {},
  }),
});

// Mock scrollIntoView
Object.defineProperty(Element.prototype, 'scrollIntoView', {
  value: function() {}, writable: true
});

// Mock console to reduce noise
const originalConsole = { ...console };
console.error = (...args) => {
  const message = args[0];
  if (typeof message === "string" && 
      (message.includes("Warning: An update to") || message.includes("act()") || 
       message.includes("React Router Future Flag"))) {
    return;
  }
  originalConsole.error.apply(console, args);
};

console.warn = (...args) => {
  const message = args[0];
  if (typeof message === "string" && 
      (message.includes("React Router") || message.includes("Warning: An update to"))) {
    return;
  }
  originalConsole.warn.apply(console, args);
};

beforeEach(() => {
  vi.clearAllTimers();
});

afterAll(() => {
  console.warn = originalConsole.warn;
  console.error = originalConsole.error;
});

afterEach(() => {
  cleanup();
});