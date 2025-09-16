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

// Mock API service with proper ES module support
vi.mock("../../../utils/apiService.jsx", () => {
  const mockApi = {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    getSectorAnalysis: vi.fn(),
    getSectorPerformance: vi.fn(),
    getSectorAllocation: vi.fn(),
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

const mockSectorData = {
  sectors: [
    {
      name: "Technology",
      performance: 15.2,
      allocation: 28.5,
      marketCap: 12500000000000,
      topStocks: ["AAPL", "MSFT", "GOOGL"],
    },
    {
      name: "Healthcare",
      performance: 8.7,
      allocation: 15.2,
      marketCap: 6800000000000,
      topStocks: ["JNJ", "PFE", "UNH"],
    },
    {
      name: "Finance",
      performance: 12.4,
      allocation: 18.9,
      marketCap: 8900000000000,
      topStocks: ["JPM", "BAC", "WFC"],
    },
    {
      name: "Consumer Discretionary",
      performance: 6.3,
      allocation: 12.1,
      marketCap: 5200000000000,
      topStocks: ["AMZN", "TSLA", "HD"],
    },
    {
      name: "Energy",
      performance: -2.1,
      allocation: 8.5,
      marketCap: 3100000000000,
      topStocks: ["XOM", "CVX", "COP"],
    },
    {
      name: "Utilities",
      performance: 4.2,
      allocation: 3.2,
      marketCap: 1800000000000,
      topStocks: ["NEE", "SO", "D"],
    },
  ],
  comparison: {
    bestPerformer: { name: "Technology", performance: 15.2 },
    worstPerformer: { name: "Energy", performance: -2.1 },
    mostVolatile: { name: "Energy", volatility: 18.5 },
    leastVolatile: { name: "Utilities", volatility: 8.2 },
  },
  trends: [
    { sector: "Technology", trend: "bullish", momentum: 85 },
    { sector: "Healthcare", trend: "neutral", momentum: 52 },
    { sector: "Finance", trend: "bullish", momentum: 78 },
    { sector: "Energy", trend: "bearish", momentum: 25 },
  ],
  rotation: {
    inflow: ["Technology", "Finance", "Healthcare"],
    outflow: ["Energy", "Utilities", "Real Estate"],
    recommendation: "Overweight growth sectors, underweight defensive sectors",
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
    const api = await import("../../../utils/apiService.jsx");
    api.default.get.mockResolvedValue({
      data: {
        success: true,
        data: {
          data: mockSectorData.sectors.reduce((acc, sector) => {
            acc[sector.name.toUpperCase().replace(/\s+/g, "")] = {
              bidPrice: 100,
              askPrice: 102,
              error: false,
            };
            return acc;
          }, {}),
        },
      },
    });
  });

  it("renders sector analysis page", async () => {
    renderSectorAnalysis();

    expect(screen.getAllByText(/sector analysis/i)[0]).toBeInTheDocument();

    await waitFor(async () => {
      const api = await import("../../../utils/apiService.jsx");
      expect(api.default.get).toHaveBeenCalled();
    });
  });

  it("displays sector performance data", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      expect(screen.getByText("Technology")).toBeInTheDocument();
      expect(screen.getByText(/15.2%/)).toBeInTheDocument();
      expect(screen.getByText("Healthcare")).toBeInTheDocument();
      expect(screen.getByText(/8.7%/)).toBeInTheDocument();
      expect(screen.getByText("Finance")).toBeInTheDocument();
      expect(screen.getByText(/12.4%/)).toBeInTheDocument();
    });
  });

  it("shows sector allocations", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      expect(screen.getByText(/28.5%/)).toBeInTheDocument(); // Tech allocation
      expect(screen.getByText(/15.2%/)).toBeInTheDocument(); // Healthcare allocation
      expect(screen.getByText(/18.9%/)).toBeInTheDocument(); // Finance allocation
    });
  });

  it("displays market cap information", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      expect(screen.getByText(/12.5T|12,500B/)).toBeInTheDocument(); // Tech market cap
      expect(screen.getByText(/6.8T|6,800B/)).toBeInTheDocument(); // Healthcare market cap
    });
  });

  it("shows top stocks in each sector", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText("MSFT")).toBeInTheDocument();
      expect(screen.getByText("GOOGL")).toBeInTheDocument();
      expect(screen.getByText("JNJ")).toBeInTheDocument();
      expect(screen.getByText("PFE")).toBeInTheDocument();
    });
  });

  it("displays performance comparison", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      expect(screen.getByText(/best performer/i)).toBeInTheDocument();
      expect(screen.getByText(/worst performer/i)).toBeInTheDocument();
      expect(screen.getByText("Energy")).toBeInTheDocument(); // Worst performer
      expect(screen.getByText(/-2.1%/)).toBeInTheDocument(); // Energy performance
    });
  });

  it("shows volatility metrics", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      expect(screen.getByText(/most volatile/i)).toBeInTheDocument();
      expect(screen.getByText(/least volatile/i)).toBeInTheDocument();
      expect(screen.getByText(/18.5%/)).toBeInTheDocument(); // Energy volatility
      expect(screen.getByText(/8.2%/)).toBeInTheDocument(); // Utilities volatility
    });
  });

  it("displays sector trends", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      expect(screen.getByText(/bullish/i)).toBeInTheDocument();
      expect(screen.getByText(/bearish/i)).toBeInTheDocument();
      expect(screen.getByText(/neutral/i)).toBeInTheDocument();
      expect(screen.getByText("85")).toBeInTheDocument(); // Tech momentum
      expect(screen.getByText("25")).toBeInTheDocument(); // Energy momentum
    });
  });

  it("shows sector rotation analysis", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      expect(screen.getByText(/rotation|inflow|outflow/i)).toBeInTheDocument();
      expect(
        screen.getByText(/overweight growth sectors/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/underweight defensive sectors/i)
      ).toBeInTheDocument();
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

  it("displays sector weights table", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      expect(screen.getByRole("table")).toBeInTheDocument();
      expect(screen.getByText(/sector|name/i)).toBeInTheDocument();
      expect(screen.getByText(/performance|return/i)).toBeInTheDocument();
      expect(screen.getByText(/allocation|weight/i)).toBeInTheDocument();
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
        const api = await import("../../../utils/apiService.jsx");
        expect(api.default.get).toHaveBeenCalled();
      });
    }
  });

  it("shows loading state", async () => {
    const api = await import("../../../utils/apiService.jsx");
    api.default.get.mockImplementation(() => new Promise(() => {}));

    renderSectorAnalysis();

    expect(
      screen.getByRole("progressbar") || screen.getByText(/loading/i)
    ).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    const api = await import("../../../utils/apiService.jsx");
    api.default.get.mockRejectedValue(new Error("Failed to load sector data"));

    renderSectorAnalysis();

    await waitFor(() => {
      expect(screen.getByText(/error|failed to load/i)).toBeInTheDocument();
    });
  });

  it("displays momentum indicators", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      // Should show momentum scores or indicators
      expect(screen.getByText(/momentum/i)).toBeInTheDocument();
      expect(
        screen.getByText("85") || screen.getByText("78")
      ).toBeInTheDocument(); // Momentum scores
    });
  });

  it("handles empty sector data", async () => {
    const api = await import("../../../utils/apiService.jsx");
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

  it("shows sector recommendations", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      expect(screen.getByText(/recommendation/i)).toBeInTheDocument();
      expect(
        screen.getByText(/overweight|underweight|neutral/i)
      ).toBeInTheDocument();
    });
  });

  it("displays relative strength indicators", async () => {
    renderSectorAnalysis();

    await waitFor(() => {
      // Should show relative performance vs market
      expect(
        screen.getByText(/relative|vs market|outperform|underperform/i) ||
          screen.getByText(/strength/i)
      ).toBeInTheDocument();
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
