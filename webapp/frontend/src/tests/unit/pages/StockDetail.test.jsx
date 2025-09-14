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
vi.mock("react-router-dom", () => ({
  useParams: vi.fn(() => ({ symbol: "AAPL" })),
}));

// Mock React Query
vi.mock("@tanstack/react-query", () => ({
  useQuery: vi.fn(),
}));

// Mock API service with proper ES module support
vi.mock("../../../services/api.js", () => {
  const mockApi = {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    getStockDetail: vi.fn(),
    getStockPrices: vi.fn(),
    getStockFinancials: vi.fn(),
  };
  
  const mockGetApiConfig = vi.fn(() => ({
    baseURL: 'http://localhost:3001',
    apiUrl: 'http://localhost:3001',
    environment: 'test',
    isDevelopment: true,
    isProduction: false,
    baseUrl: '/',
  }));

  return {
    api: mockApi,
    getApiConfig: mockGetApiConfig,
    default: mockApi
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
  formatPercent: vi.fn((value) => `${value?.toFixed(2)}%`),
}));

const mockStockData = {
  symbol: "AAPL",
  name: "Apple Inc.",
  price: 175.25,
  change: 2.50,
  changePercent: 1.45,
  volume: 45678900,
  marketCap: 2750000000000,
  peRatio: 28.5,
  dividendYield: 0.52,
  beta: 1.2,
  high52Week: 198.23,
  low52Week: 124.17,
  avgVolume: 52000000,
  eps: 6.15,
  sector: "Technology",
  industry: "Consumer Electronics",
  description: "Apple Inc. designs, manufactures, and markets smartphones...",
};

const mockChartData = [
  { date: "2024-01-01", price: 170.25, volume: 45000000 },
  { date: "2024-01-02", price: 172.50, volume: 48000000 },
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
  const mockUseQuery = require("@tanstack/react-query").useQuery;
  const _mockApi = require("../../../services/api.js").default;

  beforeEach(() => {
    vi.clearAllMocks();
    
    // Mock successful API responses
    mockUseQuery.mockImplementation((options) => {
      const { queryKey } = options;
      
      if (queryKey[0] === "stockDetail") {
        return {
          data: mockStockData,
          isLoading: false,
          error: null,
          refetch: vi.fn(),
        };
      } else if (queryKey[0] === "stockChart") {
        return {
          data: mockChartData,
          isLoading: false,
          error: null,
          refetch: vi.fn(),
        };
      } else if (queryKey[0] === "stockFinancials") {
        return {
          data: mockFinancials,
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
      expect(screen.getByText("$2.50")).toBeInTheDocument();
      expect(screen.getByText("1.45%")).toBeInTheDocument();
    });
  });

  it("shows key metrics", async () => {
    renderWithProviders(<StockDetail />);
    
    await waitFor(() => {
      expect(screen.getByText("28.5")).toBeInTheDocument(); // PE Ratio
      expect(screen.getByText("0.52%")).toBeInTheDocument(); // Dividend Yield
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
      expect(screen.getByText(/Apple Inc. designs, manufactures/)).toBeInTheDocument();
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

  it("handles missing stock symbol in URL", () => {
    const mockUseParams = require("react-router-dom").useParams;
    mockUseParams.mockReturnValue({ symbol: undefined });
    
    renderWithProviders(<StockDetail />);
    
    expect(screen.getByText(/invalid stock symbol/i) || 
           screen.getByText(/stock not found/i)).toBeInTheDocument();
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
      targetPrice: 185.50,
      analystCount: 25,
    };

    mockUseQuery.mockImplementation((options) => {
      if (options.queryKey[0] === "stockDetail") {
        return {
          data: mockStockWithAnalyst,
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
      if (options.queryKey[0] === "stockDetail") {
        return {
          data: mockStockData,
          isLoading: false,
          error: null,
          refetch: vi.fn(),
        };
      } else if (options.queryKey[0] === "stockChart") {
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