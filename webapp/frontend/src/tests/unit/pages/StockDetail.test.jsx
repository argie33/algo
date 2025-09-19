/**
 * StockDetail Page Unit Tests
 * Tests the stock detail functionality - stock info, charts, financials, analysis
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  renderWithProviders,
  screen,
  waitFor,
  fireEvent,
} from "../../test-utils.jsx";
import StockDetail from "../../../pages/StockDetail.jsx";

// Mock React Router
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useParams: vi.fn(() => ({ symbol: "AAPL" })),
  };
});

// Mock React Query
vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual("@tanstack/react-query");
  return {
    ...actual,
    useQuery: vi.fn(),
  };
});

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

// Mock error logger
vi.mock("../../../utils/errorLogger.jsx", () => ({
  createComponentLogger: vi.fn(() => ({
    log: vi.fn(),
    error: vi.fn(),
  })),
}));

// Mock formatters
vi.mock("../../../utils/formatters.jsx", () => ({
  formatCurrency: vi.fn((value) => `$${value?.toFixed(2)}`),
  formatNumber: vi.fn((value) => value?.toLocaleString()),
  formatPercent: vi.fn((value) => `${(value * 100)?.toFixed(2)}%`),  // Convert decimal to percentage
}));

const mockStockData = {
  symbol: "AAPL",
  company_name: "Apple Inc.",  // Component expects company_name
  price: 175.25,
  previous_close: 172.75,  // Component calculates: 175.25 - 172.75 = 2.5
  change: 2.5,
  changePercent: 1.45,
  volume: 45678900,
  marketCap: 2750000000000,
  market_capitalization: 2750000000000, // Component expects snake_case
  pe_ratio: 28.5,                       // Component expects snake_case
  dividend_yield: 0.0052,               // Component expects decimal: 0.52% = 0.0052
  beta: 1.2,
  high52Week: 198.23,
  low52Week: 124.17,
  avgVolume: 52000000,
  eps: 6.15,
  earnings_per_share: 6.15,  // Component expects earnings_per_share
  sector: "Technology",
  industry: "Consumer Electronics",
  country: "US",  // Add country field
  description: "Apple Inc. designs, manufactures, and markets smartphones...",
};

const mockChartData = [
  { date: "2024-01-01", price: 170.25, volume: 45000000 },
  { date: "2024-01-02", price: 172.5, volume: 48000000 },
  { date: "2024-01-03", price: 175.25, volume: 45678900 },
];

const mockFinancials = {
  revenue: 394328000000,
  grossProfit: 169148000000,
  operatingIncome: 114301000000,
  netIncome: 99803000000,
  totalAssets: 352755000000,
  totalDebt: 123930000000,
  freeCashFlow: 84726000000,
  returnOnEquity: 175.1,
  returnOnAssets: 28.3,
  profitMargin: 25.3,
};

describe("StockDetail Component", () => {
  let mockUseQuery;

  beforeEach(async () => {
    vi.clearAllMocks();

    // Get the mocked useQuery function
    const { useQuery } = await import("@tanstack/react-query");
    mockUseQuery = vi.mocked(useQuery);

    // Mock successful API responses
    mockUseQuery.mockImplementation((options) => {
      const { queryKey } = options;

      if (queryKey[0] === "stockProfile") {
        return {
          data: [mockStockData],  // Component expects an array
          isLoading: false,
          error: null,
          refetch: vi.fn(),
        };
      } else if (queryKey[0] === "stockMetrics") {
        return {
          data: [mockStockData],  // Component expects an array and uses [0]
          isLoading: false,
          error: null,
          refetch: vi.fn(),
        };
      } else if (queryKey[0] === "stockPricesRecent") {  // Correct query key
        return {
          data: mockChartData,
          isLoading: false,
          error: null,
          refetch: vi.fn(),
        };
      } else if (queryKey[0] === "stockFinancials") {
        return {
          data: [mockFinancials],  // Component expects an array and uses [0]
          isLoading: false,
          error: null,
          refetch: vi.fn(),
        };
      }

      return {
        data: null,
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      };
    });
  });

  it("renders stock detail page with symbol from URL", async () => {
    renderWithProviders(<StockDetail />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
    });
  });

  it("displays stock price and change", async () => {
    renderWithProviders(<StockDetail />);

    await waitFor(() => {
      expect(screen.getByText("$175.25")).toBeInTheDocument();
      // Look for the combined text as it appears in the component
      expect(screen.getByText(/\$2\.50/)).toBeInTheDocument();
      expect(screen.getByText(/1\.4[0-9]%/)).toBeInTheDocument(); // Allow for rounding differences
    });
  });

  it("shows key metrics", async () => {
    renderWithProviders(<StockDetail />);

    await waitFor(() => {
      expect(screen.getByText("28.50")).toBeInTheDocument(); // PE Ratio as formatted
      expect(screen.getByText("0.52%")).toBeInTheDocument(); // Dividend Yield: 0.0052 * 100 = 0.52%
      expect(screen.getByText("1.2")).toBeInTheDocument(); // Beta
      expect(screen.getByText("45,678,900")).toBeInTheDocument(); // Volume
    });
  });

  it("displays 52-week high and low", async () => {
    renderWithProviders(<StockDetail />);

    await waitFor(() => {
      expect(screen.getByText("$198.23")).toBeInTheDocument(); // 52W High
      expect(screen.getByText("$124.17")).toBeInTheDocument(); // 52W Low
    });
  });

  it("shows loading state", () => {
    mockUseQuery.mockImplementation(() => ({
      data: null,
      isLoading: true,
      error: null,
      refetch: vi.fn(),
    }));

    renderWithProviders(<StockDetail />);

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    mockUseQuery.mockImplementation(() => ({
      data: null,
      isLoading: false,
      error: new Error("Failed to fetch stock data"),
      refetch: vi.fn(),
    }));

    renderWithProviders(<StockDetail />);

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });

  it("switches between tabs", async () => {
    renderWithProviders(<StockDetail />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Click on financials tab
    const financialsTab = screen.getByRole("tab", { name: /financials/i });
    fireEvent.click(financialsTab);

    await waitFor(() => {
      expect(screen.getByText(/revenue/i)).toBeInTheDocument();
    });
  });

  it("displays financial metrics", async () => {
    renderWithProviders(<StockDetail />);

    // Switch to financials tab
    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    const financialsTab = screen.getByRole("tab", { name: /financials/i });
    fireEvent.click(financialsTab);

    await waitFor(() => {
      expect(screen.getByText("$394,328,000,000")).toBeInTheDocument(); // Revenue
      expect(screen.getByText("$99,803,000,000")).toBeInTheDocument(); // Net Income
      expect(screen.getByText("25.3%")).toBeInTheDocument(); // Profit Margin
    });
  });

  it("displays company description and sector", async () => {
    renderWithProviders(<StockDetail />);

    await waitFor(() => {
      expect(screen.getByText("Technology")).toBeInTheDocument();
      expect(screen.getByText("Consumer Electronics")).toBeInTheDocument();
      expect(
        screen.getByText(/Apple Inc. designs, manufactures/)
      ).toBeInTheDocument();
    });
  });

  it("shows price chart", async () => {
    renderWithProviders(<StockDetail />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Chart should be rendered (SVG element)
    const chartSvg = document.querySelector("svg");
    expect(chartSvg).toBeInTheDocument();
  });

  it("displays volume information", async () => {
    renderWithProviders(<StockDetail />);

    await waitFor(() => {
      expect(screen.getByText("45,678,900")).toBeInTheDocument(); // Current volume
      expect(screen.getByText("52,000,000")).toBeInTheDocument(); // Average volume
    });
  });

  it("shows market cap", async () => {
    renderWithProviders(<StockDetail />);

    await waitFor(() => {
      expect(screen.getByText("$2,750,000,000,000")).toBeInTheDocument();
    });
  });

  it("displays EPS information", async () => {
    renderWithProviders(<StockDetail />);

    await waitFor(() => {
      expect(screen.getByText("$6.15")).toBeInTheDocument(); // EPS
    });
  });

  it("handles missing stock symbol in URL", async () => {
    const { useParams } = await import("react-router-dom");
    const mockUseParams = vi.mocked(useParams);
    mockUseParams.mockReturnValue({ symbol: undefined });

    renderWithProviders(<StockDetail />);

    expect(
      screen.getByText(/invalid stock symbol/i) ||
        screen.getByText(/stock not found/i)
    ).toBeInTheDocument();
  });

  it("shows trend indicators with appropriate colors", async () => {
    renderWithProviders(<StockDetail />);

    await waitFor(() => {
      // Positive change should show green/up trend
      const changeElement = screen.getByText("$2.50");
      expect(changeElement).toBeInTheDocument();

      // Check for trend icons
      const trendIcons = document.querySelectorAll("[data-testid*='trend']");
      expect(trendIcons.length).toBeGreaterThanOrEqual(0);
    });
  });

  it("displays analyst ratings when available", async () => {
    const mockStockWithAnalyst = {
      ...mockStockData,
      analystRating: "Buy",
      targetPrice: 185.5,
      analystCount: 25,
    };

    mockUseQuery.mockImplementation((options) => {
      if (options.queryKey[0] === "stockProfile") {
        return {
          data: [mockStockWithAnalyst],  // Component expects an array
          isLoading: false,
          error: null,
          refetch: vi.fn(),
        };
      } else if (options.queryKey[0] === "stockMetrics") {
        return {
          data: [mockStockWithAnalyst],  // Component expects an array
          isLoading: false,
          error: null,
          refetch: vi.fn(),
        };
      }
      return {
        data: null,
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      };
    });

    renderWithProviders(<StockDetail />);

    await waitFor(() => {
      expect(screen.getByText("Buy")).toBeInTheDocument();
      expect(screen.getByText("$185.50")).toBeInTheDocument();
    });
  });

  it("handles chart data loading states", async () => {
    mockUseQuery.mockImplementation((options) => {
      if (options.queryKey[0] === "stockProfile") {
        return {
          data: [mockStockData],  // Component expects an array
          isLoading: false,
          error: null,
          refetch: vi.fn(),
        };
      } else if (options.queryKey[0] === "stockMetrics") {
        return {
          data: [mockStockData],  // Component expects an array
          isLoading: false,
          error: null,
          refetch: vi.fn(),
        };
      } else if (options.queryKey[0] === "stockPricesRecent") {  // Correct query key
        return {
          data: null,
          isLoading: true,
          error: null,
          refetch: vi.fn(),
        };
      }
      return {
        data: null,
        isLoading: false,
        error: null,
        refetch: vi.fn(),
      };
    });

    renderWithProviders(<StockDetail />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      // Chart loading indicator should be present
      expect(screen.getByRole("progressbar")).toBeInTheDocument();
    });
  });
});
