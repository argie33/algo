/**
 * SectorAnalysis Page Unit Tests
 * Tests the sector analysis functionality - sector performance, comparison, allocation
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

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SectorAnalysis from "../../../pages/SectorAnalysis.jsx";

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
    getSectorAnalysis: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getSectorPerformance: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getSectorAllocation: vi.fn().mockResolvedValue({ success: true, data: {} }),
  },
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    environment: "test",
    isDevelopment: true,
    isProduction: false,
    baseUrl: "/",
  })),
}));

// Mock data matching real backend API response structure
const mockSectorPerformanceData = {
  success: true,
  data: [
    {
      sector: "Technology",
      performance_pct: 2.5,
      stock_count: 145,
      avg_price: 125.5,
      total_volume: 89500000,
      gaining_stocks: 95,
      losing_stocks: 45,
      win_rate_pct: 67.86,
    },
    {
      sector: "Healthcare",
      performance_pct: 1.8,
      stock_count: 98,
      avg_price: 98.75,
      total_volume: 65200000,
      gaining_stocks: 60,
      losing_stocks: 35,
      win_rate_pct: 63.16,
    },
    {
      sector: "Financials",
      performance_pct: 1.2,
      stock_count: 87,
      avg_price: 78.25,
      total_volume: 52000000,
      gaining_stocks: 50,
      losing_stocks: 35,
      win_rate_pct: 58.82,
    },
    {
      sector: "Energy",
      performance_pct: -0.3,
      stock_count: 45,
      avg_price: 65.5,
      total_volume: 48000000,
      gaining_stocks: 15,
      losing_stocks: 28,
      win_rate_pct: 34.88,
    },
  ],
  metadata: {
    period: "1m",
    limit: 10,
    total_sectors: 4,
    gaining_sectors: 3,
    losing_sectors: 1,
  },
  timestamp: new Date().toISOString(),
};

const mockRotationData = {
  data: {
    sectors: [
      {
        sector: "Technology",
        symbol: "XLK",
        overall_rank: 1,
        rsi: 65,
        momentum: "Strong",
        flow: "Inflow",
        performance_1d: 2.5,
        performance_5d: 5.2,
        performance_20d: 12.8,
      },
      {
        sector: "Healthcare",
        symbol: "XLV",
        overall_rank: 2,
        rsi: 58,
        momentum: "Moderate",
        flow: "Inflow",
        performance_1d: 1.8,
        performance_5d: 3.5,
        performance_20d: 8.7,
      },
      {
        sector: "Financials",
        symbol: "XLF",
        overall_rank: 3,
        rsi: 52,
        momentum: "Moderate",
        flow: "Neutral",
        performance_1d: 1.2,
        performance_5d: 2.1,
        performance_20d: 5.3,
      },
      {
        sector: "Energy",
        symbol: "XLE",
        overall_rank: 4,
        rsi: 42,
        momentum: "Weak",
        flow: "Outflow",
        performance_1d: -0.3,
        performance_5d: -1.2,
        performance_20d: -2.8,
      },
    ],
  },
};

const mockIndustryData = {
  data: {
    industries: [
      {
        sector: "Technology",
        industry: "Software Infrastructure",
        rs_rating: 85,
        momentum: "Strong",
        trend: "Uptrend",
        performance_20d: 15.2,
        performance_1d: 2.3,
        performance_5d: 6.8,
        stock_count: 45,
        overall_rank: 1,
        total_market_cap: 2500000000000,
        stock_symbols: ["MSFT", "GOOGL", "ORCL"],
      },
      {
        sector: "Healthcare",
        industry: "Drug Manufacturers",
        rs_rating: 72,
        momentum: "Moderate",
        trend: "Uptrend",
        performance_20d: 8.7,
        performance_1d: 1.2,
        performance_5d: 3.5,
        stock_count: 38,
        overall_rank: 5,
        total_market_cap: 1800000000000,
        stock_symbols: ["JNJ", "PFE", "MRK"],
      },
    ],
    summary: {
      total_industries: 2,
      avg_performance_20d: 11.95,
    },
  },
};

// Test render helper
function renderSectorAnalysis(props = {}) {
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
        <SectorAnalysis {...props} />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("SectorAnalysis Component", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const api = await import("../../../services/api.js");

    // Mock different endpoints with appropriate responses
    api.default.get.mockImplementation((url) => {
      if (url.includes("/market/sectors")) {
        return Promise.resolve({ data: mockRotationData });
      }
      if (url.includes("/market/industries")) {
        return Promise.resolve({ data: mockIndustryData });
      }
      if (url.includes("/sectors/performance")) {
        return Promise.resolve({ data: mockSectorPerformanceData });
      }
      return Promise.resolve({ data: { success: true, data: [] } });
    });

    // Mock getMarketResearchIndicators
    api.getMarketResearchIndicators = vi.fn().mockResolvedValue(mockRotationData);
  });

  it("renders sector analysis page", async () => {
    renderSectorAnalysis();

    expect(screen.getAllByText(/sector analysis/i)[0]).toBeInTheDocument();

    await waitFor(async () => {
      const api = await import("../../../services/api.js");
      expect(api.default.get).toHaveBeenCalled();
    });
  });

  it("displays sector performance data", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      expect(screen.getByText("Technology")).toBeInTheDocument();
      expect(screen.getByText(/2\.5%/)).toBeInTheDocument();
      expect(screen.getByText("Healthcare")).toBeInTheDocument();
      expect(screen.getByText(/1\.8%/)).toBeInTheDocument();
      expect(screen.getByText("Financials")).toBeInTheDocument();
      expect(screen.getByText(/1\.2%/)).toBeInTheDocument();
    });
  });

  it("shows sector stock counts", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      expect(screen.getByText("145")).toBeInTheDocument(); // Tech stock count
      expect(screen.getByText("98")).toBeInTheDocument(); // Healthcare stock count
      expect(screen.getByText("87")).toBeInTheDocument(); // Finance stock count
    });
  });

  it("displays sector volume information", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      // Check that volume data is displayed (formatted as millions)
      const volumeElements = screen.getAllByText(/M|B/);
      expect(volumeElements.length).toBeGreaterThan(0);
    });
  });

  it("shows industry stock symbols", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      // Industry data should display stock symbols
      expect(screen.getByText("MSFT") || screen.getByText("GOOGL") || screen.getByText("JNJ")).toBeTruthy();
    });
  });

  it("displays sector performance with positive and negative values", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      // Check for positive performance
      expect(screen.getByText(/2\.5%/)).toBeInTheDocument(); // Technology
      // Check for negative performance
      expect(screen.getByText(/-0\.3%/) || screen.getByText(/0\.3%/)).toBeTruthy(); // Energy
    });
  });

  it("shows sector momentum indicators", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      expect(screen.getByText(/strong/i) || screen.getByText(/moderate/i) || screen.getByText(/weak/i)).toBeTruthy();
    });
  });

  it("displays sector trends and flow", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      expect(screen.getByText(/inflow/i) || screen.getByText(/outflow/i) || screen.getByText(/neutral/i)).toBeTruthy();
      expect(screen.getByText(/uptrend/i) || screen.getByText(/downtrend/i) || screen.getByText(/sideways/i)).toBeTruthy();
    });
  });

  it("shows sector rotation analysis", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      expect(screen.getByText(/rotation|sector rankings/i) || screen.getByText(/inflow/i) || screen.getByText(/outflow/i)).toBeTruthy();
    });
  });

  it("renders sector allocation chart", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      // Should have pie chart or other allocation visualization
      expect(screen.getByRole("img", { hidden: true })).toBeInTheDocument();
    });
  });

  it("displays performance chart", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      // Should have performance comparison chart
      const chartElements = screen.getAllByRole("img", { hidden: true });
      expect(chartElements.length).toBeGreaterThan(0);
    });
  });

  it("handles sector selection/filtering", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      // Click on a sector to view details
      const techSector = screen.getByText("Technology");
      fireEvent.click(techSector);

      // Should show detailed view or update data
      expect(techSector).toBeInTheDocument();
    });
  });

  it("shows positive and negative performance with styling", async () => {
    const { container: _container } = renderSectorAnalysis();

    await waitFor(() => {
      // Positive performance should be styled differently from negative
      const positivePerf = screen.getByText(/\+15.2%|15.2%/);
      const negativePerf = screen.getByText(/-2.1%/);

      expect(positivePerf).toBeInTheDocument();
      expect(negativePerf).toBeInTheDocument();
    });
  });

  it("displays industry rankings table with correct columns", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      const tables = screen.getAllByRole("table");
      expect(tables.length).toBeGreaterThan(0);

      // Check for table headers
      expect(screen.getByText(/Rank/i)).toBeInTheDocument();
      expect(screen.getByText(/Industry/i)).toBeInTheDocument();
      expect(screen.getByText(/Sector/i)).toBeInTheDocument();
      expect(screen.getByText(/RS Rating/i)).toBeInTheDocument();
      expect(screen.getByText(/Momentum/i)).toBeInTheDocument();
      expect(screen.getByText(/Trend/i)).toBeInTheDocument();
    });
  });

  it("handles time period selection", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      const periodControls = screen.getAllByRole("button");
      expect(periodControls.length).toBeGreaterThan(0);
    });

    const periodControls = screen.getAllByRole("button");
    const periodButton = periodControls.find(
      (btn) =>
        btn.textContent &&
        (btn.textContent.includes("1Y") || btn.textContent.includes("6M"))
    );

    if (periodButton) {
      fireEvent.click(periodButton);

      await waitFor(async () => {
        const api = await import("../../../services/api.js");
        expect(api.default.get).toHaveBeenCalled();
      });
    }
  });

  it("shows loading state", async () => {
    const api = await import("../../../services/api.js");
    api.default.get.mockImplementation(() => new Promise(() => {}));

    renderSectorAnalysis();

    expect(
      screen.getByRole("progressbar") || screen.getByText(/loading/i)
    ).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    const api = await import("../../../services/api.js");
    api.default.get.mockRejectedValue(new Error("Failed to load sector data"));

    renderSectorAnalysis();

    await waitFor(() => {
      expect(screen.getByText(/error|failed to load/i)).toBeInTheDocument();
    });
  });

  it("displays RS (Relative Strength) ratings", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      // Should show RS ratings for industries
      expect(screen.getByText("85") || screen.getByText("72")).toBeTruthy(); // RS ratings from mock data
    });
  });

  it("handles empty sector data", async () => {
    const api = await import("../../../services/api.js");
    api.default.get.mockResolvedValue({
      data: {
        success: true,
        data: { data: {} },
      },
    });

    renderSectorAnalysis();

    await waitFor(() => {
      expect(
        screen.getByText(/no sector data|no data/i) ||
          screen.getByText(/limited data available/i)
      ).toBeInTheDocument();
    });
  });

  it("shows industry count per sector", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      expect(screen.getByText(/industries/i) || screen.getByText(/industry/i)).toBeTruthy();
    });
  });

  it("displays 20-day performance metrics", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      // Should show 20-day performance data
      expect(screen.getByText(/15\.2%/) || screen.getByText(/8\.7%/)).toBeTruthy();
    });
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
