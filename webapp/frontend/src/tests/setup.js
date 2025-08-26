import { afterEach, afterAll } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom";

// Mock ResizeObserver for recharts
global.ResizeObserver = class ResizeObserver {
  constructor(cb) {
    this.cb = cb;
  }
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Mock recharts components globally to avoid canvas issues
import { vi } from 'vitest';
import React from 'react';

// REAL SITE TESTING - API SERVICE SETUP
// Mock the API service to handle environment variables properly and avoid ES module cycles
vi.mock('../services/api', () => {
  // Create a simple mock that matches the expected axios-like interface
  const mockApi = {
    get: vi.fn(() => Promise.resolve({ data: { success: true, data: {} } })),
    post: vi.fn(() => Promise.resolve({ data: { success: true } })),
    put: vi.fn(() => Promise.resolve({ data: { success: true } })),
    delete: vi.fn(() => Promise.resolve({ data: { success: true } })),
    patch: vi.fn(() => Promise.resolve({ data: { success: true } })),
    request: vi.fn(() => Promise.resolve({ data: { success: true } })),
    defaults: { baseURL: 'http://localhost:3001' },
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() }
    }
  };

  // Mock functions that are in the default export
  const mockApiFunction = vi.fn(() => Promise.resolve({ data: { success: true, data: {} } }));
  
  // Create default export object that mimics the actual default export structure
  // but with the axios instance methods for components that expect `api.get()`
  const defaultExportMock = {
    ...mockApi, // Include axios methods for components that use api.get() directly
    
    // API functions that are in the default export
    healthCheck: mockApiFunction,
    getMarketOverview: mockApiFunction,
    getPortfolioData: mockApiFunction,
    getPortfolio: mockApiFunction, // Alias
    addHolding: mockApiFunction,
    updateHolding: mockApiFunction,
    deleteHolding: mockApiFunction,
    getApiKeys: mockApiFunction,
    addApiKey: mockApiFunction,
    updateApiKey: mockApiFunction,
    deleteApiKey: mockApiFunction,
    placeOrder: mockApiFunction,
    getQuote: mockApiFunction,
  };
  
  return {
    api: mockApi, // Named export for the axios instance
    default: defaultExportMock, // Default export that includes both axios methods and API functions
    getApiConfig: vi.fn(() => ({
      apiUrl: 'http://localhost:3001',
      environment: 'test',
      baseURL: 'http://localhost:3001',
      isServerless: false,
      isConfigured: true,
      isDevelopment: true,
      isProduction: false
    }))
  };
});

// Mock logger globally and as ES module
const mockLogger = {
  info: vi.fn(),
  error: vi.fn(),
  warn: vi.fn(),
  debug: vi.fn()
};

global.logger = mockLogger;

// Mock logger as ES module for imports
vi.mock('../services/logger', () => ({
  default: mockLogger,
  logger: mockLogger
}));

vi.mock('../utils/logger', () => ({
  default: mockLogger,
  logger: mockLogger
}));

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children, ...props }) =>
    React.createElement('div', { 'data-testid': 'responsive-container', ...props }, children),
  LineChart: ({ children, data, ...props }) =>
    React.createElement('div', { 'data-testid': 'line-chart', 'data-chart-data': JSON.stringify(data), ...props }, children),
  Line: ({ dataKey, stroke, ...props }) =>
    React.createElement('div', { 'data-testid': 'chart-line', 'data-key': dataKey, 'data-stroke': stroke, ...props }),
  AreaChart: ({ children, data, ...props }) =>
    React.createElement('div', { 'data-testid': 'area-chart', 'data-chart-data': JSON.stringify(data), ...props }, children),
  Area: ({ dataKey, fill, ...props }) =>
    React.createElement('div', { 'data-testid': 'chart-area', 'data-key': dataKey, 'data-fill': fill, ...props }),
  BarChart: ({ children, data, ...props }) =>
    React.createElement('div', { 'data-testid': 'bar-chart', 'data-chart-data': JSON.stringify(data), ...props }, children),
  Bar: ({ dataKey, fill, ...props }) =>
    React.createElement('div', { 'data-testid': 'chart-bar', 'data-key': dataKey, 'data-fill': fill, ...props }),
  PieChart: ({ children, ...props }) =>
    React.createElement('div', { 'data-testid': 'pie-chart', ...props }, children),
  Pie: ({ data: _data, dataKey, outerRadius, innerRadius, label: _label, labelLine: _labelLine, ...props }) => {
    const { cx: _cx, cy: _cy, startAngle: _startAngle, endAngle: _endAngle, fill: _fill, stroke: _stroke, ...safeProps } = props;
    return React.createElement('div', { 
      'data-testid': 'pie', 
      'data-key': dataKey,
      'data-outer-radius': outerRadius,
      'data-inner-radius': innerRadius,
      ...safeProps 
    });
  },
  Cell: ({ fill, value, name, payload: _payload, ...props }) => {
    const { cx: _cx, cy: _cy, midAngle: _midAngle, innerRadius: _innerRadius, outerRadius: _outerRadius, percent: _percent, index: _index, ...safeProps } = props;
    return React.createElement('div', { 
      'data-testid': 'pie-cell', 
      'data-fill': fill, 
      'data-value': value,
      'data-name': name,
      ...safeProps 
    });
  },
  XAxis: ({ dataKey, ...props }) =>
    React.createElement('div', { 'data-testid': 'x-axis', 'data-key': dataKey, ...props }),
  YAxis: ({ domain, ...props }) =>
    React.createElement('div', { 'data-testid': 'y-axis', 'data-domain': JSON.stringify(domain), ...props }),
  CartesianGrid: (props) => React.createElement('div', { 'data-testid': 'cartesian-grid', ...props }),
  Tooltip: ({ content, formatter: _formatter, labelFormatter: _labelFormatter, ...props }) => {
    const { active, payload: _payload, label: _label, ...safeProps } = props;
    return React.createElement('div', { 
      'data-testid': 'chart-tooltip',
      'data-content': typeof content,
      'data-active': active,
      ...safeProps 
    }, typeof content === 'function' ? 'Custom Tooltip' : 'Default Tooltip');
  },
  Legend: (props) => React.createElement('div', { 'data-testid': 'chart-legend', ...props }),
  ReferenceLine: ({ y, stroke, ...props }) =>
    React.createElement('div', { 'data-testid': 'reference-line', 'data-y': y, 'data-stroke': stroke, ...props }),
  ComposedChart: ({ children, data, ...props }) =>
    React.createElement('div', { 'data-testid': 'composed-chart', 'data-chart-data': JSON.stringify(data), ...props }, children),
  ScatterChart: ({ children, data, ...props }) =>
    React.createElement('div', { 'data-testid': 'scatter-chart', 'data-chart-data': JSON.stringify(data), ...props }, children),
  Scatter: ({ dataKey, fill, ...props }) =>
    React.createElement('div', { 'data-testid': 'scatter', 'data-key': dataKey, 'data-fill': fill, ...props }),
  RadarChart: ({ children, data, ...props }) =>
    React.createElement('div', { 'data-testid': 'radar-chart', 'data-chart-data': JSON.stringify(data), ...props }, children),
  Radar: ({ dataKey, fill, ...props }) =>
    React.createElement('div', { 'data-testid': 'radar', 'data-key': dataKey, 'data-fill': fill, ...props }),
  PolarGrid: (props) => React.createElement('div', { 'data-testid': 'polar-grid', ...props }),
  PolarAngleAxis: ({ dataKey, ...props }) =>
    React.createElement('div', { 'data-testid': 'polar-angle-axis', 'data-key': dataKey, ...props }),
  PolarRadiusAxis: ({ domain, ...props }) =>
    React.createElement('div', { 'data-testid': 'polar-radius-axis', 'data-domain': JSON.stringify(domain), ...props })
}));

// Mock window.matchMedia for MUI
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => {},
  }),
});

// Configure fetch for real site testing
const _REAL_API_URL = process.env.VITE_API_URL || "http://localhost:3001"; // Dynamic URL from CloudFormation

// Only mock fetch in specific test scenarios
global.originalFetch = global.fetch;

// Default to real fetch unless specifically mocked
global.fetch = global.originalFetch || fetch;

// API service configuration for real site testing
// Only mock API when specifically needed - prefer real API calls

// Mock console methods to reduce test noise but preserve important logs
const originalConsole = { ...console };
console.error = (...args) => {
  const message = args[0];
  if (
    typeof message === "string" &&
    (message.includes("Warning: An update to") ||
      message.includes("act()") ||
      message.includes("React Router Future Flag"))
  ) {
    return; // Suppress React warnings
  }
  originalConsole.error.apply(console, args);
};

console.warn = (...args) => {
  const message = args[0];
  if (
    typeof message === "string" &&
    (message.includes("React Router") ||
      message.includes("Warning: An update to"))
  ) {
    return; // Suppress React warnings
  }
  originalConsole.warn.apply(console, args);
};

// Restore original console on cleanup
afterAll(() => {
  console.warn = originalConsole.warn;
  console.error = originalConsole.error;
});

// Cleanup after each test case
afterEach(() => {
  cleanup();
});
