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
  },
  api: {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    put: vi.fn(() => Promise.resolve({ data: {} })),
    delete: vi.fn(() => Promise.resolve({ data: {} })),
    patch: vi.fn(() => Promise.resolve({ data: {} })),
  },
}));
