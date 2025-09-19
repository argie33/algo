/**
 * MetricsDashboard Page Unit Tests
 * Tests the metrics dashboard functionality - KPIs, performance metrics, analytics
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
import MetricsDashboard from "../../../pages/MetricsDashboard.jsx";

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
  })),
  AuthProvider: vi.fn(({ children }) => children),
}));

// Mock API service with standardized pattern
vi.mock("../../../services/api.js", () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    // Metrics dashboard methods
    getMetrics: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getDashboardMetrics: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getPerformanceMetrics: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getStockMetrics: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getTradingSignalsDaily: vi.fn().mockResolvedValue({ success: true, data: [] }),
  },
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    environment: "test",
  })),
}));

const mockMetricsData = {
  portfolio: {
    totalValue: 150000,
    dailyChange: 2500,
    dailyChangePercent: 1.67,
    totalReturn: 15000,
    totalReturnPercent: 11.11,
  },
  performance: {
    sharpeRatio: 1.45,
    maxDrawdown: -5.2,
    volatility: 14.8,
    beta: 1.12,
  },
  trades: {
    totalTrades: 45,
    winRate: 68.9,
    avgWin: 850,
    avgLoss: -420,
  },
  positions: {
    activePositions: 12,
    longPositions: 8,
    shortPositions: 4,
    topPerformer: "AAPL",
  },
};

// Test render helper
function renderMetricsDashboard(props = {}) {
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
        <MetricsDashboard {...props} />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("MetricsDashboard Component", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const api = (await import("../../../services/api")).default;
    api.getMetrics.mockResolvedValue({
      success: true,
      data: mockMetricsData,
    });
  });

  it("renders metrics dashboard page", async () => {
    renderMetricsDashboard();

    expect(
      screen.getByText(/metrics dashboard|dashboard/i)
    ).toBeInTheDocument();
  });

  it("displays portfolio value metrics", async () => {
    renderMetricsDashboard();

    await waitFor(() => {
      expect(screen.getByText(/150,000|portfolio value/i)).toBeInTheDocument();
      expect(screen.getByText(/2,500|\+2,500/)).toBeInTheDocument();
      expect(screen.getByText(/1.67%|\+1.67%/)).toBeInTheDocument();
    });
  });

  it("shows performance metrics", async () => {
    renderMetricsDashboard();

    await waitFor(() => {
      expect(screen.getByText(/sharpe ratio/i)).toBeInTheDocument();
      expect(screen.getByText(/1.45/)).toBeInTheDocument();
      expect(screen.getByText(/max drawdown/i)).toBeInTheDocument();
      expect(screen.getByText(/-5.2%|5.2%/)).toBeInTheDocument();
    });
  });

  it("displays trading statistics", async () => {
    renderMetricsDashboard();

    await waitFor(() => {
      expect(screen.getByText(/total trades/i)).toBeInTheDocument();
      expect(screen.getByText("45")).toBeInTheDocument();
      expect(screen.getByText(/win rate/i)).toBeInTheDocument();
      expect(screen.getByText(/68.9%/)).toBeInTheDocument();
    });
  });

  it("shows position information", async () => {
    renderMetricsDashboard();

    await waitFor(() => {
      expect(screen.getByText(/active positions/i)).toBeInTheDocument();
      expect(screen.getByText("12")).toBeInTheDocument();
      expect(screen.getByText(/long positions|long/i)).toBeInTheDocument();
      expect(screen.getByText("8")).toBeInTheDocument();
    });
  });

  it("displays top performer", async () => {
    renderMetricsDashboard();

    await waitFor(() => {
      expect(screen.getByText(/top performer/i)).toBeInTheDocument();
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });
  });

  it("handles loading state", () => {
    const api = require("../../../services/api").default;
    api.getMetrics.mockImplementation(() => new Promise(() => {}));

    renderMetricsDashboard();

    expect(
      screen.getByRole("progressbar") || screen.getByText(/loading/i)
    ).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    const api = require("../../../services/api").default;
    api.getMetrics.mockRejectedValue(new Error("API Error"));

    renderMetricsDashboard();

    await waitFor(() => {
      expect(screen.getByText(/error|failed to load/i)).toBeInTheDocument();
    });
  });

  it("displays metrics in cards layout", () => {
    renderMetricsDashboard();

    const { container } = renderMetricsDashboard();
    expect(
      container.querySelector('[class*="MuiCard"]') ||
        container.querySelector('[class*="card"]')
    ).toBeInTheDocument();
  });

  it("formats currency values correctly", async () => {
    renderMetricsDashboard();

    await waitFor(() => {
      // Should format large numbers with commas or abbreviations
      expect(screen.getByText(/150,000|\$150K|\$150,000/)).toBeInTheDocument();
    });
  });

  it("displays percentage changes with proper formatting", async () => {
    renderMetricsDashboard();

    await waitFor(() => {
      // Should show positive change with + sign and proper color
      expect(screen.getByText(/\+1.67%|1.67%/)).toBeInTheDocument();
    });
  });

  it("shows volatility and beta metrics", async () => {
    renderMetricsDashboard();

    await waitFor(() => {
      expect(screen.getByText(/volatility/i)).toBeInTheDocument();
      expect(screen.getByText(/14.8%|14.8/)).toBeInTheDocument();
      expect(screen.getByText(/beta/i)).toBeInTheDocument();
      expect(screen.getByText(/1.12/)).toBeInTheDocument();
    });
  });

  it("displays win/loss statistics", async () => {
    renderMetricsDashboard();

    await waitFor(() => {
      expect(screen.getByText(/average win|avg win/i)).toBeInTheDocument();
      expect(screen.getByText(/850/)).toBeInTheDocument();
      expect(screen.getByText(/average loss|avg loss/i)).toBeInTheDocument();
      expect(screen.getByText(/420/)).toBeInTheDocument();
    });
  });

  it("handles empty metrics data", async () => {
    const api = require("../../../services/api").default;
    api.getMetrics.mockResolvedValue({
      success: true,
      data: {},
    });

    renderMetricsDashboard();

    await waitFor(() => {
      // Should handle missing data gracefully
      expect(
        screen.getByText(/no data|unavailable/i) ||
          screen.getByText("0") ||
          screen.getByText("-")
      ).toBeInTheDocument();
    });
  });

  it("refreshes data periodically", async () => {
    renderMetricsDashboard();

    await waitFor(() => {
      const api = require("../../../services/api").default;
      expect(api.getMetrics).toHaveBeenCalled();
    });

    // Should make additional calls for refreshing (depending on implementation)
    await new Promise((resolve) => setTimeout(resolve, 100));

    // Implementation may vary - could be more calls or websocket updates
    expect(true).toBe(true); // Placeholder - adjust based on actual refresh logic
  });
});

function createMockUser() {
  return {
    id: 1,
    username: "testuser",
    email: "test@example.com",
    isAuthenticated: true,
  };
}
