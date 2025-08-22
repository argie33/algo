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
