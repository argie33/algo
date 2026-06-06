/**
 * Vitest Setup File
 * Configures test environment, mocks, and global utilities
 */

import { afterEach, beforeEach, vi, afterAll } from "vitest";
import { cleanup, render as rtlRender } from "@testing-library/react";
import "@testing-library/jest-dom";
import React from "react";
import { MemoryRouter } from "react-router-dom";
import * as RTL from "@testing-library/react";

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

// Auto-wrap render calls with MemoryRouter to provide Router context
// This allows tests that render components with Navigate/useNavigate to work properly
const originalRender = RTL.render;
RTL.render = function(ui, options = {}) {
  const Wrapper = ({ children }) => (
    <MemoryRouter
      initialEntries={options.initialRoutes || ["/"]}
      future={{
        v7_startTransition: true,
        v7_relativeSplatPath: true,
      }}
    >
      {children}
    </MemoryRouter>
  );

  return originalRender(ui, {
    ...options,
    wrapper: options.wrapper
      ? ({ children }) => <Wrapper><options.wrapper>{children}</options.wrapper></Wrapper>
      : Wrapper,
  });
};

// Also override global.render if it exists
if (typeof global !== 'undefined' && global.render) {
  global.render = RTL.render;
}
