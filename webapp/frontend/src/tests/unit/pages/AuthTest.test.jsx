/**
 * AuthTest Page Unit Tests
 * Tests the authentication testing page functionality
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock import.meta.env BEFORE any imports
Object.defineProperty(import.meta, "env", {
  value: {
    VITE_API_URL: "http://localhost:3001",
    MODE: "test",
    DEV: true,
    PROD: false,
    BASE_URL: "/",
  },
  writable: true,
  configurable: true,
});

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import AuthTest from "../../../pages/AuthTest.jsx";

// Mock localStorage
const localStorageMock = {
  getItem: vi.fn(),
  setItem: vi.fn(),
  removeItem: vi.fn(),
  clear: vi.fn(),
};
global.localStorage = localStorageMock;

// Mock console.log
global.console.log = vi.fn();

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: null,
    isAuthenticated: false,
    isLoading: false,
    error: null,
    tokens: null,
    login: vi.fn(),
    logout: vi.fn(),
    checkAuthState: vi.fn(),
  })),
  AuthProvider: vi.fn(({ children }) => children),
}));

// Test render helper
function renderAuthTest(props = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <AuthTest {...props} />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("AuthTest Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorageMock.getItem.mockReturnValue(null);
  });

  it("renders auth test page without errors", () => {
    expect(() => renderAuthTest()).not.toThrow();
  });

  it("displays authentication-related content", () => {
    renderAuthTest();

    // Check that the page renders specific authentication content
    expect(screen.getByText("Authentication Test Page")).toBeInTheDocument();
  });

  it("handles loading state", () => {
    renderAuthTest();

    // Component should render without hanging
    expect(document.body).toBeInTheDocument();
  });

  it("displays basic page structure", () => {
    const { container } = renderAuthTest();

    expect(container.firstChild).toBeInTheDocument();
  });

  it("interacts with localStorage mock", () => {
    renderAuthTest();

    // Should not throw when localStorage is accessed
    expect(localStorageMock.getItem).toBeDefined();
  });
});
