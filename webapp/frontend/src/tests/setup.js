import { afterEach, afterAll, beforeEach, vi } from "vitest";
import { cleanup, configure } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";

// Mock missing optional dependencies that some components might use
vi.mock("react-markdown", () => ({
  default: ({ children }) =>
    React.createElement("div", { "data-testid": "markdown" }, children),
}));

vi.mock("react-syntax-highlighter", () => ({
  Prism: ({ children }) =>
    React.createElement(
      "pre",
      { "data-testid": "syntax-highlighter" },
      children
    ),
}));

vi.mock("react-syntax-highlighter/dist/esm/styles/prism", () => ({
  vscDarkPlus: {},
}));

// ResizeObserver mock will be defined below as a class for better compatibility

// Configure React Testing Library for React 18
configure({
  testIdAttribute: "data-testid",
  // Disable act warnings in tests - we'll handle async operations properly
  asyncUtilTimeout: 5000,
  // Configure for React 18 concurrent features
  reactStrictMode: false,
});

// Prevent React 18 concurrent mode issues in tests
global.IS_REACT_ACT_ENVIRONMENT = true;

// Ensure NODE_ENV is properly set for all our test guards
if (typeof process !== "undefined") {
  process.env.NODE_ENV = "test";
}

// Mock React's scheduler to prevent "Should not already be working" errors
vi.mock("scheduler", () => ({
  unstable_scheduleCallback: vi.fn((priority, callback) => {
    // Execute synchronously in tests to prevent scheduling conflicts
    const _result = callback();
    return 1;
  }),
  unstable_cancelCallback: vi.fn(),
  unstable_shouldYield: vi.fn(() => false),
  unstable_getCurrentPriorityLevel: vi.fn(() => 3),
  unstable_requestIdleCallback: vi.fn((callback) => {
    // Execute synchronously to prevent async scheduling issues
    callback();
    return 1;
  }),
  unstable_cancelIdleCallback: vi.fn(),
  unstable_now: vi.fn(() => Date.now()),
  unstable_runWithPriority: vi.fn((priority, callback) => callback()),
  unstable_next: vi.fn((callback) => callback()),
  unstable_wrapCallback: vi.fn((callback) => callback),
  unstable_scheduleWork: vi.fn(),
  unstable_IdlePriority: 5,
  unstable_ImmediatePriority: 1,
  unstable_LowPriority: 4,
  unstable_NormalPriority: 3,
  unstable_UserBlockingPriority: 2,
}));

// Enhanced ResizeObserver mock for MUI Tabs and Recharts compatibility
class MockResizeObserver {
  constructor(callback) {
    this.callback = callback;
    this.elements = new Set();
  }

  observe(element) {
    this.elements.add(element);
    // Trigger callback immediately with mock dimensions to satisfy MUI Tabs
    if (this.callback && element) {
      // Use setTimeout to match real ResizeObserver async behavior
      setTimeout(() => {
        if (this.callback) {
          this.callback([
            {
              target: element,
              contentRect: {
                width: 600,
                height: 400,
                top: 0,
                left: 0,
                right: 600,
                bottom: 400,
                x: 0,
                y: 0,
              },
              borderBoxSize: [
                {
                  blockSize: 400,
                  inlineSize: 600,
                },
              ],
              contentBoxSize: [
                {
                  blockSize: 400,
                  inlineSize: 600,
                },
              ],
            },
          ]);
        }
      }, 0);
    }
  }

  unobserve(element) {
    this.elements.delete(element);
  }

  disconnect() {
    this.elements.clear();
  }
}

// Set the mock globally
global.ResizeObserver = MockResizeObserver;
window.ResizeObserver = MockResizeObserver;

// Mock getBoundingClientRect for chart components
if (typeof HTMLElement !== "undefined") {
  HTMLElement.prototype.getBoundingClientRect = function () {
    return {
      width: 600,
      height: 400,
      top: 0,
      left: 0,
      right: 600,
      bottom: 400,
      x: 0,
      y: 0,
      toJSON: function () {},
    };
  };
}

// Fix React DOM createRoot issue for React 18 and disable concurrent features in tests
// Ensure proper DOM structure for testing
if (typeof global.document !== "undefined") {
  // Ensure document.body exists with proper structure
  if (!global.document.body) {
    global.document.body = global.document.createElement("body");
    global.document.documentElement =
      global.document.documentElement || global.document.createElement("html");
    global.document.documentElement.appendChild(global.document.body);
  }

  // Create a root div for React rendering
  if (!global.document.getElementById("root")) {
    const rootDiv = global.document.createElement("div");
    rootDiv.id = "root";
    global.document.body.appendChild(rootDiv);
  }
}

// Mock React's internal scheduler to prevent concurrent mode issues in tests

beforeEach(() => {
  // Ensure ResizeObserver mock is applied for each test
  global.ResizeObserver = MockResizeObserver;
  window.ResizeObserver = MockResizeObserver;

  // Reset React internal state to prevent "Should not already be working" errors
  const internals =
    global.React?.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED;
  if (internals) {
    if (internals.ReactCurrentDispatcher) {
      internals.ReactCurrentDispatcher.current = null;
    }
    if (internals.ReactCurrentBatchConfig) {
      internals.ReactCurrentBatchConfig.transition = null;
    }
    // Also reset the fiber reconciler internal state
    if (internals.ReactCurrentOwner) {
      internals.ReactCurrentOwner.current = null;
    }
    if (internals.ReactFiberWorkLoop) {
      internals.ReactFiberWorkLoop.workInProgress = null;
    }
  }

  // Clear any pending timers that might interfere
  vi.clearAllTimers();
});

// Ensure document has proper methods for testing-library
if (typeof global.document !== "undefined" && global.document.body) {
  // Ensure body has proper properties for DOM testing
  if (!global.document.body.querySelector) {
    global.document.body.querySelector = function (selector) {
      return global.document.querySelector(selector);
    };
  }

  if (!global.document.body.querySelectorAll) {
    global.document.body.querySelectorAll = function (selector) {
      return global.document.querySelectorAll(selector);
    };
  }
}

// Mock recharts components globally to avoid canvas issues

// Mock MUI icons to prevent test failures - comprehensive mock using importOriginal
vi.mock("@mui/icons-material", async (importOriginal) => {
  const actual = await importOriginal();
  const createIconMock = (iconName) => (props) =>
    React.createElement("div", {
      "data-testid": `${iconName.toLowerCase()}-icon`,
      "data-icon": iconName,
      ...props,
    });

  return {
    ...actual,
    VideoLibrary: createIconMock("VideoLibrary"),
    School: createIconMock("School"),
    Article: createIconMock("Article"),
    MenuBook: createIconMock("MenuBook"),
    PlayArrow: createIconMock("PlayArrow"),
    BookmarkBorder: createIconMock("BookmarkBorder"),
    Share: createIconMock("Share"),
    AccessTime: createIconMock("AccessTime"),
    Description: createIconMock("Description"),
    Assessment: createIconMock("Assessment"),
    TrendingUp: createIconMock("TrendingUp"),
    ShowChart: createIconMock("ShowChart"),
    AccountBalance: createIconMock("AccountBalance"),
    AttachMoney: createIconMock("AttachMoney"),
    Dashboard: createIconMock("Dashboard"),
    List: createIconMock("List"),
    Settings: createIconMock("Settings"),
    Person: createIconMock("Person"),
    Home: createIconMock("Home"),
    Search: createIconMock("Search"),
    Notifications: createIconMock("Notifications"),
    MoreVert: createIconMock("MoreVert"),
    ArrowDropDown: createIconMock("ArrowDropDown"),
    Close: createIconMock("Close"),
    Check: createIconMock("Check"),
    Error: createIconMock("Error"),
    Warning: createIconMock("Warning"),
    Info: createIconMock("Info"),
    Success: createIconMock("Success"),
    Fullscreen: createIconMock("Fullscreen"),
    FullscreenExit: createIconMock("FullscreenExit"),
    Expand: createIconMock("Expand"),
    ExpandMore: createIconMock("ExpandMore"),
    ExpandLess: createIconMock("ExpandLess"),
    // Add other common icons
    Add: createIconMock("Add"),
    Remove: createIconMock("Remove"),
    Delete: createIconMock("Delete"),
    Edit: createIconMock("Edit"),
    Save: createIconMock("Save"),
    Cancel: createIconMock("Cancel"),
    ArrowBack: createIconMock("ArrowBack"),
    ArrowForward: createIconMock("ArrowForward"),
    Menu: createIconMock("Menu"),
    FilterList: createIconMock("FilterList"),
    Refresh: createIconMock("Refresh"),
    Download: createIconMock("Download"),
    Upload: createIconMock("Upload"),
    Visibility: createIconMock("Visibility"),
    VisibilityOff: createIconMock("VisibilityOff"),
    default: createIconMock("DefaultIcon"),
  };
});

// REAL SITE TESTING - NO MOCKS AT ALL
// Use the real API service and real database for proper integration testing

// NO LOGGER MOCKS - Use real logger
// NO API MOCKS - Use real API service
// NO DATABASE MOCKS - Use real database

// Mock AuthContext for test compatibility while maintaining real functionality
vi.mock("../contexts/AuthContext.jsx", async () => {
  const React = await import("react");

  const mockAuthContext = React.default.createContext({
    user: null,
    isAuthenticated: false,
    isLoading: false,
    error: null,
    tokens: null,
    login: async () => ({ success: true }),
    register: async () => ({ success: true }),
    confirmRegistration: async () => ({ success: true }),
    logout: async () => ({ success: true }),
    forgotPassword: async () => ({ success: true }),
    confirmForgotPassword: async () => ({ success: true }),
    refreshSession: async () => ({ success: true }),
    clearError: () => {},
    checkAuthState: () => {},
  });

  const AuthProvider = ({ children }) => {
    const authValue = {
      user: { id: "test-user", email: "test@example.com", name: "Test User" },
      isAuthenticated: true,
      isLoading: false,
      error: null,
      tokens: { accessToken: "test-token" },
      login: async () => ({ success: true }),
      register: async () => ({ success: true }),
      confirmRegistration: async () => ({ success: true }),
      logout: async () => ({ success: true }),
      forgotPassword: async () => ({ success: true }),
      confirmForgotPassword: async () => ({ success: true }),
      refreshSession: async () => ({ success: true }),
      clearError: () => {},
      checkAuthState: () => {},
    };

    return React.default.createElement(
      mockAuthContext.Provider,
      { value: authValue },
      children
    );
  };

  const useAuth = () => {
    const context = React.default.useContext(mockAuthContext);
    if (!context) {
      throw new Error("useAuth must be used within an AuthProvider");
    }
    return context;
  };

  return {
    default: mockAuthContext,
    AuthProvider,
    useAuth,
  };
});

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children, ...props }) =>
    React.createElement(
      "div",
      { "data-testid": "responsive-container", ...props },
      children
    ),
  LineChart: ({ children, data, ...props }) =>
    React.createElement(
      "div",
      {
        "data-testid": "line-chart",
        "data-chart-data": JSON.stringify(data),
        ...props,
      },
      children
    ),
  Line: ({ dataKey, stroke, ...props }) =>
    React.createElement("div", {
      "data-testid": "chart-line",
      "data-key": dataKey,
      "data-stroke": stroke,
      ...props,
    }),
  AreaChart: ({ children, data, ...props }) =>
    React.createElement(
      "div",
      {
        "data-testid": "area-chart",
        "data-chart-data": JSON.stringify(data),
        ...props,
      },
      children
    ),
  Area: ({ dataKey, fill, ...props }) =>
    React.createElement("div", {
      "data-testid": "chart-area",
      "data-key": dataKey,
      "data-fill": fill,
      ...props,
    }),
  BarChart: ({ children, data, ...props }) =>
    React.createElement(
      "div",
      {
        "data-testid": "bar-chart",
        "data-chart-data": JSON.stringify(data),
        ...props,
      },
      children
    ),
  Bar: ({ dataKey, fill, ...props }) =>
    React.createElement("div", {
      "data-testid": "chart-bar",
      "data-key": dataKey,
      "data-fill": fill,
      ...props,
    }),
  PieChart: ({ children, ...props }) =>
    React.createElement(
      "div",
      { "data-testid": "pie-chart", ...props },
      children
    ),
  Pie: ({
    data: _data,
    dataKey,
    outerRadius,
    innerRadius,
    label: _label,
    labelLine: _labelLine,
    ...props
  }) => {
    const {
      cx: _cx,
      cy: _cy,
      startAngle: _startAngle,
      endAngle: _endAngle,
      fill: _fill,
      stroke: _stroke,
      ...safeProps
    } = props;
    return React.createElement("div", {
      "data-testid": "pie",
      "data-key": dataKey,
      "data-outer-radius": outerRadius,
      "data-inner-radius": innerRadius,
      ...safeProps,
    });
  },
  Cell: ({ fill, value, name, payload: _payload, ...props }) => {
    const {
      cx: _cx,
      cy: _cy,
      midAngle: _midAngle,
      innerRadius: _innerRadius,
      outerRadius: _outerRadius,
      percent: _percent,
      index: _index,
      ...safeProps
    } = props;
    return React.createElement("div", {
      "data-testid": "pie-cell",
      "data-fill": fill,
      "data-value": value,
      "data-name": name,
      ...safeProps,
    });
  },
  XAxis: ({ dataKey, ...props }) =>
    React.createElement("div", {
      "data-testid": "x-axis",
      "data-key": dataKey,
      ...props,
    }),
  YAxis: ({ domain, ...props }) =>
    React.createElement("div", {
      "data-testid": "y-axis",
      "data-domain": JSON.stringify(domain),
      ...props,
    }),
  CartesianGrid: (props) =>
    React.createElement("div", { "data-testid": "cartesian-grid", ...props }),
  Tooltip: ({
    content,
    formatter: _formatter,
    labelFormatter: _labelFormatter,
    ...props
  }) => {
    const { active, payload: _payload, label: _label, ...safeProps } = props;
    return React.createElement(
      "div",
      {
        "data-testid": "chart-tooltip",
        "data-content": typeof content,
        "data-active": active,
        ...safeProps,
      },
      typeof content === "function" ? "Custom Tooltip" : "Default Tooltip"
    );
  },
  Legend: (props) =>
    React.createElement("div", { "data-testid": "chart-legend", ...props }),
  ReferenceLine: ({ y, stroke, ...props }) =>
    React.createElement("div", {
      "data-testid": "reference-line",
      "data-y": y,
      "data-stroke": stroke,
      ...props,
    }),
  ComposedChart: ({ children, data, ...props }) =>
    React.createElement(
      "div",
      {
        "data-testid": "composed-chart",
        "data-chart-data": JSON.stringify(data),
        ...props,
      },
      children
    ),
  ScatterChart: ({ children, data, ...props }) =>
    React.createElement(
      "div",
      {
        "data-testid": "scatter-chart",
        "data-chart-data": JSON.stringify(data),
        ...props,
      },
      children
    ),
  Scatter: ({ dataKey, fill, ...props }) =>
    React.createElement("div", {
      "data-testid": "scatter",
      "data-key": dataKey,
      "data-fill": fill,
      ...props,
    }),
  RadarChart: ({ children, data, ...props }) =>
    React.createElement(
      "div",
      {
        "data-testid": "radar-chart",
        "data-chart-data": JSON.stringify(data),
        ...props,
      },
      children
    ),
  Radar: ({ dataKey, fill, ...props }) =>
    React.createElement("div", {
      "data-testid": "radar",
      "data-key": dataKey,
      "data-fill": fill,
      ...props,
    }),
  PolarGrid: (props) =>
    React.createElement("div", { "data-testid": "polar-grid", ...props }),
  PolarAngleAxis: ({ dataKey, ...props }) =>
    React.createElement("div", {
      "data-testid": "polar-angle-axis",
      "data-key": dataKey,
      ...props,
    }),
  PolarRadiusAxis: ({ domain, ...props }) =>
    React.createElement("div", {
      "data-testid": "polar-radius-axis",
      "data-domain": JSON.stringify(domain),
      ...props,
    }),
}));

// Mock AWS Amplify to prevent hanging on page component imports
vi.mock("@aws-amplify/auth", () => ({
  fetchAuthSession: vi.fn(() =>
    Promise.resolve({
      tokens: { accessToken: { toString: () => "mock-token" } },
    })
  ),
  signIn: vi.fn(() => Promise.resolve({ isSignedIn: true })),
  signUp: vi.fn(() => Promise.resolve({ userId: "test-user" })),
  confirmSignUp: vi.fn(() => Promise.resolve({ isSignUpComplete: true })),
  signOut: vi.fn(() => Promise.resolve()),
  resetPassword: vi.fn(() => Promise.resolve()),
  confirmResetPassword: vi.fn(() => Promise.resolve()),
  getCurrentUser: vi.fn(() => Promise.resolve({ userId: "test-user" })),
}));

// Mock amplify config
vi.mock("../config/amplify", () => ({
  isCognitoConfigured: vi.fn(() => false),
}));

// Mock localStorage for tests
Object.defineProperty(window, "localStorage", {
  value: {
    getItem: vi.fn(),
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
    key: vi.fn(),
    length: 0,
  },
  writable: true,
});

// Mock sessionStorage for tests
Object.defineProperty(window, "sessionStorage", {
  value: {
    getItem: vi.fn(),
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
    key: vi.fn(),
    length: 0,
  },
  writable: true,
});

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

// Mock devAuth service for auth function tests
vi.mock("../services/devAuth.js", () => ({
  default: {
    // User Registration
    signUp: vi.fn().mockResolvedValue({
      success: true,
      user: { username: "testuser", email: "test@example.com" },
      userConfirmed: false,
    }),
    signUpWrapper: vi.fn().mockResolvedValue({
      success: true,
      user: { username: "testuser", email: "test@example.com" },
      userConfirmed: false,
    }),

    // Authentication
    signIn: vi.fn().mockResolvedValue({
      success: true,
      user: { username: "devuser", email: "argeropolos@gmail.com" },
      tokens: { accessToken: "dev-bypass-token" },
    }),
    signOut: vi.fn().mockResolvedValue({ success: true }),

    // Session Management
    getCurrentUser: vi.fn().mockResolvedValue({
      success: true,
      user: { username: "devuser", email: "argeropolos@gmail.com" },
    }),
    getJwtToken: vi.fn().mockResolvedValue("dev-bypass-token"),

    // Password Management
    forgotPassword: vi.fn().mockResolvedValue({ success: true }),
    confirmResetPasswordWrapper: vi.fn().mockResolvedValue({ success: true }),
    changePassword: vi.fn().mockResolvedValue({ success: true }),

    // Validation
    validatePassword: vi.fn().mockReturnValue({ isValid: true, errors: [] }),
    validateJwtToken: vi.fn().mockReturnValue(true),
    isTokenExpired: vi.fn().mockReturnValue(false),

    // MFA
    confirmMFA: vi.fn().mockResolvedValue({
      success: true,
      user: { username: "testuser" },
    }),

    // User Management
    updateUserAttributes: vi.fn().mockResolvedValue({ success: true }),

    // Helper Methods
    isAuthenticated: vi.fn().mockReturnValue(false), // Default to false, tests will change as needed
    getCurrentUserInfo: vi.fn().mockReturnValue(null), // Default to null, tests will change as needed
    getAuthToken: vi.fn().mockReturnValue("mock-token"),
    isValidTokenFormat: vi.fn().mockReturnValue(true),
  },
}));

// Mock API service for specific tests that need it
vi.mock("../services/api.js", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    api: {
      get: vi.fn().mockResolvedValue({ data: { success: true, data: [] } }),
      post: vi.fn().mockResolvedValue({ data: { success: true } }),
      put: vi.fn().mockResolvedValue({ data: { success: true } }),
      delete: vi.fn().mockResolvedValue({ data: { success: true } }),
    },
    // Core API functions used by Dashboard
    getPortfolioData: vi.fn().mockResolvedValue({ success: true, data: [] }),
    getWatchlistData: vi.fn().mockResolvedValue({ success: true, data: [] }),
    getMarketData: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getMarketOverview: vi.fn().mockResolvedValue({
      success: true,
      data: {
        sentiment_indicators: { fear_greed: { value: 50, status: "neutral" } },
        market_breadth: { advancing: 1500, declining: 1200 },
        market_cap: { total: 45000000000000 },
      },
    }),
    getTopStocks: vi.fn().mockResolvedValue({
      success: true,
      data: [
        {
          symbol: "AAPL",
          name: "Apple Inc.",
          price: 150.25,
          change: 2.5,
          change_percent: 1.69,
        },
        {
          symbol: "MSFT",
          name: "Microsoft Corp.",
          price: 280.75,
          change: -1.2,
          change_percent: -0.43,
        },
      ],
    }),
    getStockData: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getTradeHistory: vi.fn().mockResolvedValue({ success: true, data: [] }),
    searchStocks: vi.fn().mockResolvedValue({ success: true, data: [] }),
    getTradingSignalsDaily: vi.fn().mockResolvedValue({
      success: true,
      data: [
        {
          symbol: "AAPL",
          signal: "BUY",
          strength: 0.8,
          timestamp: new Date().toISOString(),
        },
        {
          symbol: "MSFT",
          signal: "HOLD",
          strength: 0.6,
          timestamp: new Date().toISOString(),
        },
      ],
    }),
    getTradingSignalsWeekly: vi
      .fn()
      .mockResolvedValue({ success: true, data: [] }),
    getTechnicalAnalysis: vi
      .fn()
      .mockResolvedValue({ success: true, data: {} }),
    getNewsAnalysis: vi.fn().mockResolvedValue({ success: true, data: [] }),
    getSectorData: vi.fn().mockResolvedValue({ success: true, data: [] }),
    getDashboardSummary: vi.fn().mockResolvedValue({
      success: true,
      data: {
        portfolio_value: 100000,
        daily_change: 1500,
        daily_change_percent: 1.5,
      },
    }),
    getScores: vi.fn().mockResolvedValue({
      success: true,
      data: [
        { symbol: "AAPL", score: 85, category: "Large Cap" },
        { symbol: "MSFT", score: 92, category: "Large Cap" },
      ],
    }),
    getPortfolioAnalytics: vi.fn().mockResolvedValue({
      success: true,
      data: {
        total_value: 100000,
        daily_change: 1500,
        daily_change_percent: 1.5,
        holdings: [],
        performance: { ytd: 12.5, month: 2.1, week: 0.8 },
      },
    }),
    // Additional Dashboard-specific functions
    getMarketStatus: vi
      .fn()
      .mockResolvedValue({
        success: true,
        data: { isOpen: true, status: "OPEN" },
      }),
    getPortfolioHoldings: vi
      .fn()
      .mockResolvedValue({ success: true, data: [] }),
    getStockPrices: vi.fn().mockResolvedValue({ success: true, data: [] }),
    getPriceHistory: vi.fn().mockResolvedValue({ success: true, data: [] }),
  };
});

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

// Mock DOM methods that don't exist in jsdom
// Mock scrollIntoView for components that use it
Object.defineProperty(Element.prototype, "scrollIntoView", {
  value: function () {
    // Mock implementation - do nothing in tests
  },
  writable: true,
});

// Restore original console on cleanup
afterAll(() => {
  console.warn = originalConsole.warn;
  console.error = originalConsole.error;
});

// Cleanup after each test case
afterEach(() => {
  cleanup();
});
