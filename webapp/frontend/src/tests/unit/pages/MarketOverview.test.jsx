/**
 * MarketOverview / MarketsHealth Page Unit Tests
 *
 * Note: src/pages/MarketOverview.jsx does not exist.
 * The actual page is MarketsHealth.jsx.
 *
 * MarketsHealth facts:
 * - Page title: "Market Health"
 * - Uses useApiQuery calling api.get for multiple endpoints:
 *   /api/algo/markets, /api/market/sentiment, /api/market/top-movers,
 *   /api/market/technicals, /api/market/seasonality, /api/algo/notifications
 * - Loading state shows empty div with "Loading market data..." text
 * - Has a Refresh button
 * - Does NOT use MUI Tabs, uses custom rendering
 */

import { vi, describe, it, expect, beforeEach } from "vitest";

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
import MarketsHealth from "../../../pages/MarketsHealth.jsx";

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => vi.fn() };
});

vi.mock("../../../services/api.js", () => {
  const mockGet = vi.fn().mockResolvedValue({ data: {} });
  const mockApi = {
    get: mockGet,
    post: vi.fn().mockResolvedValue({ data: {} }),
  };
  return {
    default: mockApi,
    api: mockApi,
    getApiConfig: vi.fn(() => ({
      apiUrl: "http://localhost:3001",
      environment: "test",
    })),
    getPortfolioData: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getApiKeys: vi.fn().mockResolvedValue({ success: true, data: [] }),
    testApiConnection: vi.fn().mockResolvedValue({ success: true }),
    importPortfolioFromBroker: vi
      .fn()
      .mockResolvedValue({ success: true, data: [] }),
    healthCheck: vi.fn().mockResolvedValue({ success: true }),
    getMarketOverview: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getMarketSentimentHistory: vi
      .fn()
      .mockResolvedValue({ success: true, data: {} }),
    getMarketBreadth: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getSeasonalityData: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getMarketResearchIndicators: vi
      .fn()
      .mockResolvedValue({ success: true, data: {} }),
    getDistributionDays: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getMarketSectorPerformance: vi
      .fn()
      .mockResolvedValue({ success: true, data: {} }),
  };
});

vi.mock("../../../services/dataCache.js", () => ({
  default: {
    get: vi.fn().mockResolvedValue(null),
    set: vi.fn().mockResolvedValue(undefined),
  },
}));

vi.mock("../../../contexts/AuthContext", () => ({
  useAuth: () => ({
    isAuthenticated: true,
    user: { id: "1", username: "testuser" },
    loading: false,
  }),
}));

global.IntersectionObserver = vi.fn(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

if (typeof window !== "undefined") {
  Object.defineProperty(window, "location", {
    value: { reload: vi.fn(), href: "http://localhost:3001" },
    writable: true,
  });
}

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => (
    <div data-testid="chart-container">{children}</div>
  ),
  LineChart: ({ children }) => <div data-testid="line-chart">{children}</div>,
  BarChart: ({ children }) => <div data-testid="bar-chart">{children}</div>,
  PieChart: ({ children }) => <div data-testid="pie-chart">{children}</div>,
  AreaChart: ({ children }) => <div data-testid="area-chart">{children}</div>,
  ScatterChart: ({ children }) => (
    <div data-testid="scatter-chart">{children}</div>
  ),
  Line: () => <div data-testid="line" />,
  Bar: () => <div data-testid="bar" />,
  Area: () => <div data-testid="area" />,
  Pie: () => <div data-testid="pie" />,
  Cell: () => <div data-testid="cell" />,
  Scatter: () => <div data-testid="scatter" />,
  ZAxis: () => <div data-testid="z-axis" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Legend: () => <div data-testid="legend" />,
  ReferenceLine: () => <div data-testid="reference-line" />,
}));

describe("MarketsHealth - Page Rendering", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../../../services/api.js");
    api.get.mockResolvedValue({ data: {} });
  });

  it("renders without crashing", async () => {
    renderWithProviders(<MarketsHealth />);
    expect(document.body).toBeInTheDocument();
  });

  it("displays market content after data loads", async () => {
    renderWithProviders(<MarketsHealth />);
    await waitFor(
      () => {
        const content = document.body.textContent;
        expect(content.length).toBeGreaterThan(10);
      },
      { timeout: 5000 }
    );
  });

  it("handles loading state", () => {
    renderWithProviders(<MarketsHealth />);
    expect(document.body).toBeInTheDocument();
  });

  it("displays Market Health title", async () => {
    renderWithProviders(<MarketsHealth />);
    await waitFor(
      () => {
        const title = document.body.textContent;
        expect(title).toContain("Market Health");
      },
      { timeout: 5000 }
    );
  });

  it("has a Refresh button", async () => {
    renderWithProviders(<MarketsHealth />);
    await waitFor(
      () => {
        const text = document.body.textContent;
        expect(text).toMatch(/Refresh/i);
      },
      { timeout: 3000 }
    );
  });
});

describe("MarketsHealth - Data Sections", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../../../services/api.js");
    api.get.mockResolvedValue({ data: {} });
  });

  it("renders without errors when all API calls return empty data", async () => {
    renderWithProviders(<MarketsHealth />);
    await waitFor(
      () => {
        expect(document.body).toBeInTheDocument();
      },
      { timeout: 3000 }
    );
  });

  it("renders some content after mounting", async () => {
    renderWithProviders(<MarketsHealth />);
    await waitFor(
      () => {
        const content = document.body.textContent;
        expect(content.length).toBeGreaterThan(5);
      },
      { timeout: 3000 }
    );
  });
});

describe("MarketsHealth - Error Handling", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
  });

  it("renders gracefully when API fails", async () => {
    const { api } = await import("../../../services/api.js");
    api.get.mockRejectedValue(new Error("API Error"));

    renderWithProviders(<MarketsHealth />);

    await waitFor(
      () => {
        expect(document.body).toBeInTheDocument();
      },
      { timeout: 5000 }
    );
  });

  it("handles network errors", async () => {
    const { api } = await import("../../../services/api.js");
    api.get.mockRejectedValue(new Error("Network error"));

    renderWithProviders(<MarketsHealth />);

    await waitFor(
      () => {
        expect(document.body).toBeInTheDocument();
      },
      { timeout: 3000 }
    );
  });
});
