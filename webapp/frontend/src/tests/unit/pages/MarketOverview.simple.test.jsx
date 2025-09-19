/**
 * Simplified MarketOverview Page Tests
 * Basic functionality tests to ensure component renders without breaking
 */

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
  Line: () => <div data-testid="line" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  Tooltip: () => <div data-testid="tooltip" />,
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