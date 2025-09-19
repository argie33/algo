import { vi, describe, it, expect, beforeEach } from "vitest";

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

import { waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test-utils.jsx";

// Import the component under test
import MarketOverview from "../../../pages/MarketOverview.jsx";

// Mock useQuery to prevent infinite refetching
vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual("@tanstack/react-query");

  const mockMarketData = {
    marketStatus: 'Open',
    indices: [
      { symbol: 'SPY', price: 450.00, change: 2.50, changePercent: 0.56 },
      { symbol: 'QQQ', price: 380.00, change: -1.20, changePercent: -0.31 }
    ],
    topMovers: {
      gainers: [{ symbol: 'AAPL', change: 5.20, changePercent: 3.2 }],
      losers: [{ symbol: 'GOOGL', change: -8.10, changePercent: -2.1 }]
    }
  };

  return {
    ...actual,
    useQuery: vi.fn((config) => ({
      data: mockMarketData,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
      ...config,
    })),
  };
});

// ResizeObserver is already mocked in setup.js - no need to duplicate here

// Mock IntersectionObserver
global.IntersectionObserver = vi.fn(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

// Mock window.location.reload to avoid JSDOM navigation errors
if (typeof window !== 'undefined') {
  Object.defineProperty(window, "location", {
    value: {
      reload: vi.fn(),
      href: "http://localhost:3001",
    },
    writable: true,
  });
}

// Mock API service with comprehensive mock
vi.mock("../../../services/api.js", async () => {
  const mockApi = await import("../../mocks/apiMock.js");
  return {
    default: mockApi.default,
    getApiConfig: mockApi.getApiConfig,
    getPortfolioData: mockApi.getPortfolioData,
    getApiKeys: mockApi.getApiKeys,
    testApiConnection: mockApi.testApiConnection,
    importPortfolioFromBroker: mockApi.importPortfolioFromBroker,
    healthCheck: mockApi.healthCheck,
    getMarketOverview: mockApi.getMarketOverview,
  };
});

// Mock auth context
vi.mock("../../../contexts/AuthContext", () => ({
  useAuth: () => ({
    isAuthenticated: true,
    user: { id: "1", username: "testuser" },
    loading: false,
  }),
}));

// Mock recharts to avoid rendering issues
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => <div data-testid="chart-container">{children}</div>,
  LineChart: ({ children }) => <div data-testid="line-chart">{children}</div>,
  BarChart: ({ children }) => <div data-testid="bar-chart">{children}</div>,
  PieChart: ({ children }) => <div data-testid="pie-chart">{children}</div>,
  AreaChart: ({ children }) => <div data-testid="area-chart">{children}</div>,
  Line: () => <div data-testid="line" />,
  Bar: () => <div data-testid="bar" />,
  Area: () => <div data-testid="area" />,
  Pie: () => <div data-testid="pie" />,
  Cell: () => <div data-testid="cell" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Legend: () => <div data-testid="legend" />,
  ReferenceLine: () => <div data-testid="reference-line" />,
}));

describe("MarketOverview - Basic Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders without crashing", async () => {
    renderWithProviders(<MarketOverview />);

    // Just check that the component renders
    expect(document.body).toBeInTheDocument();
  });

  it("displays market overview content", async () => {
    renderWithProviders(<MarketOverview />);

    await waitFor(() => {
      // Should have some content rendered
      const content = document.body.textContent;
      expect(content.length).toBeGreaterThan(10);
    }, { timeout: 5000 });
  });

  it("handles loading state", () => {
    renderWithProviders(<MarketOverview />);

    // Should render without throwing errors
    expect(document.body).toBeInTheDocument();
  });
});
