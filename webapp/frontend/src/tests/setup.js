/**
 * Vitest Setup File
 * Configures test environment, mocks, and global utilities
 */

import { afterEach, beforeEach, vi, afterAll } from "vitest";
import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";

// Mock ResizeObserver for recharts and other components
global.ResizeObserver = class ResizeObserver {
  constructor(cb) {
    this.cb = cb;
  }
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Mock window.matchMedia for MUI and media queries
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

// Mock localStorage and sessionStorage
const storageMock = () => {
  const store = {};
  return {
    getItem: (key) => store[key] || null,
    setItem: (key, value) => { store[key] = value.toString(); },
    removeItem: (key) => { delete store[key]; },
    clear: () => { Object.keys(store).forEach(key => delete store[key]); },
    key: (index) => Object.keys(store)[index] || null,
    get length() { return Object.keys(store).length; },
  };
};

Object.defineProperty(window, 'localStorage', {
  value: storageMock(),
  writable: true,
});

Object.defineProperty(window, 'sessionStorage', {
  value: storageMock(),
  writable: true,
});

// Mock environment variables
process.env.VITE_API_URL = "http://localhost:3001";
process.env.NODE_ENV = "test";

// Mock aws-amplify auth module
vi.mock("aws-amplify/auth", () => ({
  fetchAuthSession: vi.fn(() =>
    Promise.resolve({
      tokens: { accessToken: "test-token", idToken: "test-id" },
    })
  ),
  signIn: vi.fn(() => Promise.resolve({ userId: "test-user" })),
  signUp: vi.fn(() => Promise.resolve({ userId: "test-user" })),
  confirmSignUp: vi.fn(() => Promise.resolve()),
  resendSignUpCode: vi.fn(() => Promise.resolve()),
  signOut: vi.fn(() => Promise.resolve()),
  resetPassword: vi.fn(() => Promise.resolve()),
  confirmResetPassword: vi.fn(() => Promise.resolve()),
  getCurrentUser: vi.fn(() =>
    Promise.resolve({ userId: "test-user", username: "testuser" })
  ),
}));

// Mock amplify config
vi.mock("../config/amplify", () => ({
  isCognitoConfigured: vi.fn(() => false),
  getAmplifyConfig: vi.fn(() => ({ Auth: { Cognito: {} } })),
  configureAmplify: vi.fn(),
  default: vi.fn(() => ({ Auth: { Cognito: {} } })),
}));

// Mock ApiKeyProvider globally
vi.mock("../components/ApiKeyProvider", () => ({
  ApiKeyProvider: ({ children }) => children,
  useApiKey: vi.fn(() => ({
    apiKeys: [],
    addApiKey: vi.fn(),
    deleteApiKey: vi.fn(),
  })),
  default: ({ children }) => children,
}));

// Mock tokenManager
vi.mock("../services/tokenManager", () => ({
  tokenManager: {
    getAccessToken: vi.fn(() => "test-token"),
    getIdToken: vi.fn(() => "test-id-token"),
    getTokens: vi.fn(() => ({ accessToken: "test-token", idToken: "test-id-token" })),
    setTokens: vi.fn(),
    clearTokens: vi.fn(),
    isTokenValid: vi.fn(() => true),
  },
}));

// Mock sessionManager
vi.mock("../services/sessionManager", () => ({
  default: {
    initialize: vi.fn(),
    setCallbacks: vi.fn(),
    startSession: vi.fn(),
    endSession: vi.fn(),
    startTokenRefreshTimer: vi.fn(),
    scheduleWarningAfterRefreshFailure: vi.fn(),
    extendSession: vi.fn(),
    clearAllTimers: vi.fn(),
    getSessionInfo: vi.fn(),
  },
}));

// Mock SessionWarningDialog
vi.mock("../components/auth/SessionWarningDialog", () => ({
  default: () => null,
}));

// Mock console methods to reduce test noise
const originalConsole = { ...console };
console.error = (...args) => {
  const message = args[0];
  if (
    typeof message === "string" &&
    (message.includes("Warning: An update to") ||
      message.includes("act()") ||
      message.includes("React Router Future Flag") ||
      message.includes("Each child in a list should have a unique"))
  ) {
    return;
  }
  originalConsole.error.apply(console, args);
};

console.warn = (...args) => {
  const message = args[0];
  if (
    typeof message === "string" &&
    (message.includes("React Router") ||
      message.includes("Warning: An update to") ||
      message.includes("componentWillReceiveProps"))
  ) {
    return;
  }
  originalConsole.warn.apply(console, args);
};

// Setup before each test
beforeEach(() => {
  // Reset any state needed before each test
});

// Cleanup after each test
afterEach(() => {
  cleanup();
  vi.clearAllTimers();
  vi.clearAllMocks();
});

// Cleanup after all tests
afterAll(() => {
  console.warn = originalConsole.warn;
  console.error = originalConsole.error;
});

// Mock recharts globally — JSDOM has no canvas/SVG; use testid divs so tests can query rendered charts
// Must use React.createElement (not JSX) since this file has .js extension
const ce = React.createElement;
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children, ...props }) => ce("div", { "data-testid": "responsive-container", ...props }, children),
  LineChart: ({ children, data, ...props }) => ce("div", { "data-testid": "line-chart", "data-chart-data": JSON.stringify(data), ...props }, children),
  Line: ({ dataKey, stroke, ...props }) => ce("div", { "data-testid": "chart-line", "data-key": dataKey, "data-stroke": stroke, ...props }),
  AreaChart: ({ children, data, ...props }) => ce("div", { "data-testid": "area-chart", "data-chart-data": JSON.stringify(data), ...props }, children),
  Area: ({ dataKey, fill, ...props }) => ce("div", { "data-testid": "chart-area", "data-key": dataKey, "data-fill": fill, ...props }),
  BarChart: ({ children, data, ...props }) => ce("div", { "data-testid": "bar-chart", "data-chart-data": JSON.stringify(data), ...props }, children),
  Bar: ({ dataKey, fill, ...props }) => ce("div", { "data-testid": "chart-bar", "data-key": dataKey, "data-fill": fill, ...props }),
  ComposedChart: ({ children, data, ...props }) => ce("div", { "data-testid": "composed-chart", "data-chart-data": JSON.stringify(data), ...props }, children),
  PieChart: ({ children, ...props }) => ce("div", { "data-testid": "pie-chart", ...props }, children),
  Pie: ({ dataKey, outerRadius, innerRadius, data: _d, label: _l, labelLine: _ll, cx: _cx, cy: _cy, startAngle: _sa, endAngle: _ea, fill: _f, stroke: _s, ...props }) =>
    ce("div", { "data-testid": "pie", "data-key": dataKey, "data-outer-radius": outerRadius, "data-inner-radius": innerRadius, ...props }),
  Cell: ({ fill, value, name, payload: _payload, cx: _cx, cy: _cy, midAngle: _ma, innerRadius: _ir, outerRadius: _or, percent: _pct, index: _i, ...props }) =>
    ce("div", { "data-testid": "pie-cell", "data-fill": fill, "data-value": value, "data-name": name, ...props }),
  ScatterChart: ({ children, data, ...props }) => ce("div", { "data-testid": "scatter-chart", "data-chart-data": JSON.stringify(data), ...props }, children),
  Scatter: ({ dataKey, fill, ...props }) => ce("div", { "data-testid": "scatter", "data-key": dataKey, "data-fill": fill, ...props }),
  RadarChart: ({ children, data, ...props }) => ce("div", { "data-testid": "radar-chart", "data-chart-data": JSON.stringify(data), ...props }, children),
  Radar: ({ dataKey, stroke, ...props }) => ce("div", { "data-testid": "radar", "data-key": dataKey, "data-stroke": stroke, ...props }),
  XAxis: ({ dataKey, ...props }) => ce("div", { "data-testid": "x-axis", "data-key": dataKey, ...props }),
  YAxis: ({ domain, ...props }) => ce("div", { "data-testid": "y-axis", "data-domain": JSON.stringify(domain), ...props }),
  CartesianGrid: (props) => ce("div", { "data-testid": "cartesian-grid", ...props }),
  Tooltip: ({ content, formatter: _f, labelFormatter: _lf, active, payload: _p, label: _l, ...props }) =>
    ce("div", { "data-testid": "chart-tooltip", "data-content": typeof content, "data-active": active, ...props },
      typeof content === "function" ? "Custom Tooltip" : "Default Tooltip"),
  Legend: (props) => ce("div", { "data-testid": "chart-legend", ...props }),
  ReferenceLine: ({ y, stroke, ...props }) => ce("div", { "data-testid": "reference-line", "data-y": y, "data-stroke": stroke, ...props }),
  Brush: (props) => ce("div", { "data-testid": "chart-brush", ...props }),
  PolarGrid: (props) => ce("div", { "data-testid": "polar-grid", ...props }),
  PolarAngleAxis: ({ dataKey, ...props }) => ce("div", { "data-testid": "polar-angle-axis", "data-key": dataKey, ...props }),
  PolarRadiusAxis: ({ domain, ...props }) => ce("div", { "data-testid": "polar-radius-axis", "data-domain": JSON.stringify(domain), ...props }),
}));

// Mock Navigate to work outside of Router context in tests
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    Navigate: ({ to, ...props }) => {
      // In tests, just return null instead of trying to navigate
      // This allows components that use Navigate to render in tests without a Router
      return null;
    },
  };
});

// Global mock for API service - provides default implementation for all tests
vi.mock("../services/api", () => ({
  default: {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    put: vi.fn(() => Promise.resolve({ data: {} })),
    delete: vi.fn(() => Promise.resolve({ data: {} })),
    patch: vi.fn(() => Promise.resolve({ data: {} })),
    getChartData: vi.fn(() => Promise.resolve({ data: Array.from({ length: 30 }, (_, i) => ({ date: `2024-01-${String(i + 1).padStart(2, "0")}`, close: 150, open: 149, high: 152, low: 148, volume: 1000000 })) })),
    getStockPrices: vi.fn(() => Promise.resolve({ data: Array.from({ length: 30 }, (_, i) => ({ date: `2024-01-${String(i + 1).padStart(2, "0")}`, close: 150, open: 149, high: 152, low: 148, volume: 1000000 })) })),
    getHistoricalData: vi.fn(() => Promise.resolve({ data: [] })),
  },
  api: {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    put: vi.fn(() => Promise.resolve({ data: {} })),
    delete: vi.fn(() => Promise.resolve({ data: {} })),
    patch: vi.fn(() => Promise.resolve({ data: {} })),
  },
  setRefreshCallback: vi.fn(),
  getApiConfig: vi.fn(() => ({
    baseURL: "http://localhost:3001",
    apiUrl: "http://localhost:3001",
    isServerless: false,
    isDev: true,
    isDevelopment: true,
    isProduction: false,
  })),
  initializeApiConfig: vi.fn(),
}));
