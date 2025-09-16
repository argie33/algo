/**
 * FinancialData Page Unit Tests
 * Tests the financial data analysis functionality - balance sheet, income statement, cash flow
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

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import FinancialData from "../../../pages/FinancialData.jsx";

// Create mock user function locally
const createMockUser = () => ({
  id: "test-user-123",
  email: "test@example.com",
  name: "Test User",
  roles: ["user"],
  preferences: {},
  createdAt: "2025-01-01T00:00:00Z",
  lastLogin: "2025-01-15T10:00:00Z",
});

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
  })),
  AuthProvider: vi.fn(({ children }) => children),
}));

// Mock error logger
vi.mock("../../../utils/errorLogger", () => ({
  createComponentLogger: vi.fn(() => ({
    info: vi.fn(),
    error: vi.fn(),
    queryError: vi.fn(),
  })),
}));

// Mock API service with proper ES module support
vi.mock("../../../services/api", () => {
  const mockApi = {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    getBalanceSheet: vi.fn(),
    getIncomeStatement: vi.fn(),
    getCashFlowStatement: vi.fn(),
    getKeyMetrics: vi.fn(),
    getStocks: vi.fn(),
  };

  const mockGetApiConfig = vi.fn(() => ({
    baseURL: "http://localhost:3001",
    apiUrl: "http://localhost:3001",
    environment: "test",
    isDevelopment: true,
    isProduction: false,
    baseUrl: "/",
  }));

  return {
    api: mockApi,
    getApiConfig: mockGetApiConfig,
    default: mockApi,
  };
});

const mockStocksData = [
  { symbol: "AAPL", name: "Apple Inc." },
  { symbol: "GOOGL", name: "Alphabet Inc." },
  { symbol: "MSFT", name: "Microsoft Corporation" },
];

// Test render helper
function renderFinancialData(props = {}) {
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
        <FinancialData {...props} />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("FinancialData Component", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../../../services/api");

    // Setup default mocks
    api.getStocks.mockResolvedValue({
      success: true,
      data: mockStocksData,
    });
  });

  it("renders financial data page", async () => {
    renderFinancialData();

    expect(screen.getByText(/financial data/i)).toBeInTheDocument();
  });

  it("displays stock search autocomplete", async () => {
    renderFinancialData();

    await waitFor(() => {
      expect(screen.getByRole("combobox")).toBeInTheDocument();
    });
  });

  it("displays financial statement tabs", () => {
    renderFinancialData();

    expect(screen.getByText(/balance sheet/i)).toBeInTheDocument();
    expect(screen.getByText(/income statement/i)).toBeInTheDocument();
    expect(screen.getByText(/cash flow/i)).toBeInTheDocument();
    expect(screen.getByText(/key metrics/i)).toBeInTheDocument();
  });

  it("handles loading state", async () => {
    const { api } = await import("../../../services/api");
    api.getStocks.mockImplementation(() => new Promise(() => {}));

    renderFinancialData();

    expect(
      screen.getByRole("progressbar") || screen.getByText(/loading/i)
    ).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    const { api } = await import("../../../services/api");
    api.getStocks.mockRejectedValue(new Error("API Error"));

    renderFinancialData();

    await waitFor(() => {
      expect(
        screen.getByText(/error|no data/i) ||
          screen.getByText(/financial data/i)
      ).toBeInTheDocument();
    });
  });
});

// Mock user helper function (unused but keeping for future tests)
function _createMockUserFinData() {
  return {
    id: 1,
    username: "testuser",
    email: "test@example.com",
    isAuthenticated: true,
  };
}
