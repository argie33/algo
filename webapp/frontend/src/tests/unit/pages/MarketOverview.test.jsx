import { vi, describe, it, expect, beforeEach } from "vitest";
import React from "react";

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
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Import the component under test
import MarketOverview from "../../../pages/MarketOverview.jsx";

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

// Mock API service with proper ES module support
vi.mock("../../../services/api", () => {
  const mockApi = {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    put: vi.fn(() => Promise.resolve({ data: {} })),
    delete: vi.fn(() => Promise.resolve({ data: {} })),
  };

  const mockGetApiConfig = vi.fn(() => ({
    baseURL: "http://localhost:3001",
    apiUrl: "http://localhost:3001",
    environment: "test",
    isDevelopment: true,
    isProduction: false,
    baseUrl: "/",
    allEnvVars: {
      VITE_API_URL: "http://localhost:3001",
      MODE: "test",
      DEV: true,
      PROD: false,
      BASE_URL: "/",
    },
  }));

  // Mock the specific API methods that MarketOverview component uses
  const mockGetMarketOverview = vi.fn(() =>
    Promise.resolve({
      data: {
        sentiment_indicators: {
          fear_greed: {
            value: 45,
            value_text: "Neutral",
            timestamp: "2023-01-01",
          },
          aaii: { bullish: 35, neutral: 30, bearish: 35, date: "2023-01-01" },
          naaim: {
            average: 50,
            bullish_8100: 60,
            bearish: 40,
            week_ending: "2023-01-01",
          },
        },
        market_breadth: {
          advancing: 1500,
          declining: 1200,
          unchanged: 300,
          total_stocks: 3000,
          advance_decline_ratio: 1.25,
          average_change_percent: 0.5,
        },
        market_cap: {
          total: 45000000000000,
          large_cap: 35000000000000,
          mid_cap: 7500000000000,
          small_cap: 2500000000000,
        },
        economic_indicators: [
          { name: "GDP", value: 2.5, unit: "%", timestamp: "2023-01-01" },
          { name: "CPI", value: 3.2, unit: "%", timestamp: "2023-01-01" },
        ],
        indices: [
          {
            symbol: "SPY",
            name: "S&P 500",
            price: 450.25,
            change: 5.75,
            changePercent: 1.29,
          },
          {
            symbol: "QQQ",
            name: "NASDAQ",
            price: 375.8,
            change: -2.15,
            changePercent: -0.57,
          },
          {
            symbol: "DIA",
            name: "Dow Jones",
            price: 350.9,
            change: 3.2,
            changePercent: 0.91,
          },
        ],
      },
    })
  );

  const mockGetMarketSentimentHistory = vi.fn(() =>
    Promise.resolve({
      data: {
        fear_greed_history: [
          { date: "2023-01-01", value: 45, value_text: "Neutral" },
          { date: "2023-01-02", value: 50, value_text: "Neutral" },
        ],
        naaim_history: [
          { date: "2023-01-01", mean_exposure: 50 },
          { date: "2023-01-02", mean_exposure: 55 },
        ],
        aaii_history: [
          { date: "2023-01-01", bullish: 35, neutral: 30, bearish: 35 },
          { date: "2023-01-02", bullish: 40, neutral: 30, bearish: 30 },
        ],
      },
    })
  );

  const mockGetMarketSectorPerformance = vi.fn(() =>
    Promise.resolve({
      data: {
        sectors: [
          {
            sector: "Technology",
            avg_change_percent: 2.5,
            stock_count: 300,
            sector_market_cap: 12000000000000,
          },
          {
            sector: "Healthcare",
            avg_change_percent: 1.2,
            stock_count: 250,
            sector_market_cap: 8000000000000,
          },
          {
            sector: "Financial Services",
            avg_change_percent: -0.5,
            stock_count: 200,
            sector_market_cap: 9000000000000,
          },
        ],
      },
    })
  );

  const mockGetMarketBreadth = vi.fn(() =>
    Promise.resolve({
      data: {
        advancing: 1600,
        declining: 1100,
        unchanged: 300,
        advance_decline_ratio: 1.45,
        average_change_percent: 0.8,
      },
    })
  );

  const mockGetEconomicIndicators = vi.fn(() =>
    Promise.resolve({
      data: [
        {
          name: "Unemployment Rate",
          value: 3.7,
          unit: "%",
          previous_value: 3.8,
          change_percent: -2.6,
          timestamp: "2023-01-01",
        },
        {
          name: "Consumer Price Index",
          value: 3.2,
          unit: "%",
          previous_value: 3.0,
          change_percent: 6.7,
          timestamp: "2023-01-01",
        },
        {
          name: "Federal Funds Rate",
          value: 5.25,
          unit: "%",
          previous_value: 5.0,
          change_percent: 5.0,
          timestamp: "2023-01-01",
        },
      ],
    })
  );

  const mockGetSeasonalityData = vi.fn(() =>
    Promise.resolve({
      data: {
        summary: {
          overallSeasonalBias: "Bullish",
          recommendation:
            "Consider increased equity exposure during favorable seasonal period",
          favorableFactors: [
            "Historical October effect",
            "Year-end portfolio rebalancing",
          ],
          unfavorableFactors: ["September weakness", "Summer doldrums"],
        },
        currentPosition: {
          seasonalScore: 75,
          presidentialCycle: "Year 3 - Pre-election Rally",
          nextMajorEvent: { name: "FOMC Meeting", daysAway: 14 },
          activePeriods: ["Santa Claus Rally", "January Effect"],
        },
        monthlySeasonality: [
          { name: "Jan", avgReturn: 1.2, isCurrent: true },
          { name: "Feb", avgReturn: 0.8, isCurrent: false },
          { name: "Mar", avgReturn: 1.5, isCurrent: false },
        ],
        quarterlySeasonality: [
          { name: "Q1", avgReturn: 3.5, months: "Jan-Mar" },
          { name: "Q2", avgReturn: 2.1, months: "Apr-Jun" },
        ],
        presidentialCycle: {
          data: [
            {
              year: 1,
              label: "Post-Election",
              avgReturn: 8.2,
              isCurrent: false,
            },
            {
              year: 3,
              label: "Pre-Election",
              avgReturn: 16.3,
              isCurrent: true,
            },
          ],
        },
        dayOfWeekEffects: [
          { day: "Monday", avgReturn: -0.1, isCurrent: true },
          { day: "Friday", avgReturn: 0.2, isCurrent: false },
        ],
        seasonalAnomalies: [
          {
            name: "January Effect",
            period: "Jan 1-31",
            description: "Small cap outperformance",
            strength: "Moderate",
          },
        ],
        holidayEffects: [
          { holiday: "Christmas", dates: "Dec 24-26", effect: "+0.5%" },
        ],
        sectorSeasonality: [
          {
            sector: "Retail",
            bestMonths: [11, 12],
            worstMonths: [1, 2],
            rationale: "Holiday shopping season drives performance",
          },
        ],
      },
    })
  );

  const mockGetMarketResearchIndicators = vi.fn(() =>
    Promise.resolve({
      data: {
        summary: {
          overallSentiment: "Cautiously Optimistic",
          marketRegime: "Late Cycle",
          timeHorizon: "Medium Term",
          recommendation: "Maintain diversified portfolio with quality bias",
          keyRisks: ["Inflation persistence", "Geopolitical tensions"],
          keyOpportunities: ["Technology innovation", "Energy transition"],
        },
        volatility: {
          vix: 18.5,
          vixAverage: 20.2,
          vixInterpretation: {
            level: "Moderate",
            color: "warning",
            sentiment: "Complacent market conditions",
          },
        },
        sentiment: {
          putCallRatio: 0.85,
          putCallAverage: 0.9,
          putCallInterpretation: {
            sentiment: "Bullish",
            color: "success",
            signal: "Low hedging activity",
          },
        },
        technicalLevels: {
          "S&P 500": { current: 4200, trend: "Bullish", rsi: 65.2 },
          NASDAQ: { current: 13000, trend: "Neutral", rsi: 58.7 },
        },
        sectorRotation: [
          {
            sector: "Technology",
            momentum: "Strong",
            flow: "Inflow",
            performance: 2.5,
          },
          {
            sector: "Healthcare",
            momentum: "Moderate",
            flow: "Neutral",
            performance: 1.2,
          },
        ],
        economicCalendar: [
          {
            event: "FOMC Meeting",
            date: "2023-01-15",
            expected: "No change in rates",
            importance: "High",
            impact: "Market Moving",
          },
        ],
      },
    })
  );

  return {
    default: mockApi,
    getApiConfig: mockGetApiConfig,
    getMarketOverview: mockGetMarketOverview,
    getMarketSentimentHistory: mockGetMarketSentimentHistory,
    getMarketSectorPerformance: mockGetMarketSectorPerformance,
    getMarketBreadth: mockGetMarketBreadth,
    getEconomicIndicators: mockGetEconomicIndicators,
    getSeasonalityData: mockGetSeasonalityData,
    getMarketResearchIndicators: mockGetMarketResearchIndicators,
  };
});

// Mock auth context
const mockAuthContext = {
  isAuthenticated: true,
  user: { id: "1", username: "testuser" },
  loading: false,
};

vi.mock("../../../contexts/AuthContext", () => ({
  useAuth: () => mockAuthContext,
}));

// Mock recharts components
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => (
    <div data-testid="chart-container">{children}</div>
  ),
  LineChart: ({ children, data }) => (
    <div data-testid="line-chart" data-chart-data={JSON.stringify(data)}>
      {children}
    </div>
  ),
  Line: ({ dataKey }) => <div data-testid={`line-${dataKey}`} />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="chart-tooltip" />,
  Legend: () => <div data-testid="chart-legend" />,
  AreaChart: ({ children, data }) => (
    <div data-testid="area-chart" data-chart-data={JSON.stringify(data)}>
      {children}
    </div>
  ),
  Area: ({ dataKey }) => <div data-testid={`area-${dataKey}`} />,
  BarChart: ({ children, data }) => (
    <div data-testid="bar-chart" data-chart-data={JSON.stringify(data)}>
      {children}
    </div>
  ),
  Bar: ({ dataKey }) => <div data-testid={`bar-${dataKey}`} />,
  PieChart: ({ children, data }) => (
    <div data-testid="pie-chart" data-chart-data={JSON.stringify(data)}>
      {children}
    </div>
  ),
  Pie: ({ dataKey }) => <div data-testid={`pie-${dataKey}`} />,
  Cell: () => <div data-testid="cell" />,
  RadarChart: ({ children, data }) => (
    <div data-testid="radar-chart" data-chart-data={JSON.stringify(data)}>
      {children}
    </div>
  ),
  Radar: ({ dataKey }) => <div data-testid={`radar-${dataKey}`} />,
  PolarGrid: () => <div data-testid="polar-grid" />,
  PolarAngleAxis: () => <div data-testid="polar-angle-axis" />,
  PolarRadiusAxis: () => <div data-testid="polar-radius-axis" />,
}));

describe("MarketOverview Page", () => {
  const mockMarketData = {
    indices: [
      {
        symbol: "SPY",
        name: "S&P 500",
        price: 450.25,
        change: 5.75,
        changePercent: 1.29,
      },
      {
        symbol: "QQQ",
        name: "NASDAQ",
        price: 375.8,
        change: -2.15,
        changePercent: -0.57,
      },
      {
        symbol: "DIA",
        name: "Dow Jones",
        price: 350.9,
        change: 3.2,
        changePercent: 0.92,
      },
    ],
    sectors: [
      {
        name: "Technology",
        performance: 2.5,
        volume: "125M",
        topStock: "AAPL",
      },
      { name: "Healthcare", performance: -0.8, volume: "89M", topStock: "JNJ" },
      { name: "Financial", performance: 1.2, volume: "156M", topStock: "JPM" },
    ],
    marketStatus: {
      status: "OPEN",
      nextOpen: null,
      nextClose: "4:00 PM EST",
    },
    movers: {
      gainers: [
        { symbol: "AAPL", change: 8.5, changePercent: 5.2, price: 172.3 },
        { symbol: "GOOGL", change: 15.2, changePercent: 3.1, price: 2805.6 },
      ],
      losers: [
        { symbol: "TSLA", change: -12.4, changePercent: -4.8, price: 246.8 },
        { symbol: "META", change: -8.9, changePercent: -2.1, price: 415.7 },
      ],
    },
    economicIndicators: [
      {
        name: "VIX",
        value: 18.5,
        change: -1.2,
        description: "Volatility Index",
      },
      { name: "DXY", value: 103.8, change: 0.3, description: "Dollar Index" },
      {
        name: "10Y Treasury",
        value: 4.25,
        change: 0.05,
        description: "Treasury Yield",
      },
    ],
  };

  beforeEach(async () => {
    vi.clearAllMocks();

    // Access the mocked API module
    const { default: api } = await import("../../../services/api");

    api.get.mockImplementation((url) => {
      if (url.includes("/market/overview")) {
        return Promise.resolve({ data: mockMarketData });
      }
      if (url.includes("/market/history")) {
        return Promise.resolve({
          data: Array.from({ length: 30 }, (_, i) => ({
            date: `2024-01-${String(i + 1).padStart(2, "0")}`,
            value: 450 + (i % 20),
          })),
        });
      }
      return Promise.reject(new Error("Unknown endpoint"));
    });
  });

  const renderMarketOverview = () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });

    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter
          future={{
            v7_startTransition: true,
            v7_relativeSplatPath: true,
          }}
        >
          <MarketOverview />
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  describe("Page Structure", () => {
    it("renders market overview page title", () => {
      renderMarketOverview();
      expect(
        screen.getByRole("heading", { name: /market overview/i })
      ).toBeInTheDocument();
    });

    it("displays main market sections with tabs", async () => {
      renderMarketOverview();

      await waitFor(
        () => {
          // Check for tab navigation elements that exist in the real component
          // Use getAllByText since "Market Overview" appears in both header and tab
          const marketOverviewElements =
            screen.getAllByText(/Market Overview/i);
          expect(marketOverviewElements.length).toBeGreaterThan(0);
          expect(screen.getByText(/Sentiment History/i)).toBeInTheDocument();
          expect(screen.getByText(/Sector Performance/i)).toBeInTheDocument();
          // Use getAllByText since "Economic Indicators" may appear multiple times
          const economicIndicatorsElements =
            screen.getAllByText(/Economic Indicators/i);
          expect(economicIndicatorsElements.length).toBeGreaterThan(0);
        },
        { timeout: 10000 }
      );
    });

    it("shows loading state initially", () => {
      renderMarketOverview();
      // Page may have multiple progress bars (linear and circular)
      const progressBars = screen.getAllByRole("progressbar");
      expect(progressBars.length).toBeGreaterThan(0);
    });
  });

  describe("Market Breadth Section", () => {
    it("displays market breadth information with real API data", async () => {
      renderMarketOverview();

      await waitFor(
        () => {
          // Check for Market Breadth section that exists in the real component
          expect(screen.getByText(/Market Breadth/i)).toBeInTheDocument();
          // Should show advancing/declining stocks data
          const advancing = screen.queryByText(/Advancing/i);
          const declining = screen.queryByText(/Declining/i);
          // These should exist when real API data loads
          expect(advancing || declining).toBeTruthy();
        },
        { timeout: 10000 }
      );
    });

    it("shows market statistics with real data", async () => {
      renderMarketOverview();

      await waitFor(
        () => {
          // Check for Market Statistics section
          const marketStats = screen.queryByText(/Market Statistics/i);
          const totalMarketCap = screen.queryByText(/Total Market Cap/i);
          // Should have some market data when API responds
          expect(marketStats || totalMarketCap).toBeTruthy();
        },
        { timeout: 10000 }
      );
    });

    it("applies correct styling for positive and negative changes", async () => {
      renderMarketOverview();

      await waitFor(() => {
        const positiveChange = screen.getByText("+1.29%");
        const negativeChange = screen.getByText("-0.57%");

        expect(positiveChange).toHaveClass("text-green-600");
        expect(negativeChange).toHaveClass("text-red-600");
      });
    });

    it("includes trend charts for indices", async () => {
      renderMarketOverview();

      await waitFor(() => {
        expect(screen.getAllByTestId("chart-container")).toHaveLength(3);
      });
    });
  });

  describe("Sector Performance Section", () => {
    it("displays sector performance data", async () => {
      renderMarketOverview();

      await waitFor(() => {
        expect(screen.getByText("Technology")).toBeInTheDocument();
        expect(screen.getByText("Healthcare")).toBeInTheDocument();
        expect(screen.getByText("Financial")).toBeInTheDocument();
      });
    });

    it("shows sector performance percentages", async () => {
      renderMarketOverview();

      await waitFor(() => {
        expect(screen.getByText("+2.5%")).toBeInTheDocument();
        expect(screen.getByText("-0.8%")).toBeInTheDocument();
        expect(screen.getByText("+1.2%")).toBeInTheDocument();
      });
    });

    it("displays sector volume and top stocks", async () => {
      renderMarketOverview();

      await waitFor(() => {
        expect(screen.getByText("125M")).toBeInTheDocument();
        expect(screen.getByText("AAPL")).toBeInTheDocument();
        expect(screen.getByText("JNJ")).toBeInTheDocument();
        expect(screen.getByText("JPM")).toBeInTheDocument();
      });
    });

    it("allows sorting sectors by performance", async () => {
      const user = userEvent.setup();
      renderMarketOverview();

      await waitFor(() => {
        const sortButton = screen.getByRole("button", {
          name: /sort by performance/i,
        });
        expect(sortButton).toBeInTheDocument();
      });

      const sortButton = screen.getByRole("button", {
        name: /sort by performance/i,
      });
      await user.click(sortButton);

      // Should reorder sectors by performance
      const sectors = screen.getAllByTestId("sector-item");
      expect(sectors[0]).toHaveTextContent("Technology");
      expect(sectors[2]).toHaveTextContent("Healthcare");
    });
  });

  describe("Top Movers Section", () => {
    it("displays top gainers and losers", async () => {
      renderMarketOverview();

      await waitFor(() => {
        expect(screen.getByText(/top gainers/i)).toBeInTheDocument();
        expect(screen.getByText(/top losers/i)).toBeInTheDocument();
      });
    });

    it("shows gainer data correctly", async () => {
      renderMarketOverview();

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
        expect(screen.getByText("+8.5")).toBeInTheDocument();
        expect(screen.getByText("+5.2%")).toBeInTheDocument();
        expect(screen.getByText("172.30")).toBeInTheDocument();

        expect(screen.getByText("GOOGL")).toBeInTheDocument();
        expect(screen.getByText("+15.2")).toBeInTheDocument();
        expect(screen.getByText("+3.1%")).toBeInTheDocument();
      });
    });

    it("shows loser data correctly", async () => {
      renderMarketOverview();

      await waitFor(() => {
        expect(screen.getByText("TSLA")).toBeInTheDocument();
        expect(screen.getByText("-12.4")).toBeInTheDocument();
        expect(screen.getByText("-4.8%")).toBeInTheDocument();
        expect(screen.getByText("246.80")).toBeInTheDocument();

        expect(screen.getByText("META")).toBeInTheDocument();
        expect(screen.getByText("-8.9")).toBeInTheDocument();
        expect(screen.getByText("-2.1%")).toBeInTheDocument();
      });
    });

    it("allows toggling between gainers and losers", async () => {
      const user = userEvent.setup();
      renderMarketOverview();

      await waitFor(() => {
        const gainersTab = screen.getByRole("tab", { name: /gainers/i });
        const losersTab = screen.getByRole("tab", { name: /losers/i });

        expect(gainersTab).toBeInTheDocument();
        expect(losersTab).toBeInTheDocument();
      });

      const losersTab = screen.getByRole("tab", { name: /losers/i });
      await user.click(losersTab);

      expect(screen.getByText("TSLA")).toBeInTheDocument();
      expect(screen.getByText("META")).toBeInTheDocument();
    });
  });

  describe("Economic Indicators Section", () => {
    it("displays key economic indicators", async () => {
      renderMarketOverview();

      await waitFor(() => {
        expect(screen.getByText("VIX")).toBeInTheDocument();
        expect(screen.getByText("DXY")).toBeInTheDocument();
        expect(screen.getByText("10Y Treasury")).toBeInTheDocument();
      });
    });

    it("shows indicator values and changes", async () => {
      renderMarketOverview();

      await waitFor(() => {
        expect(screen.getByText("18.5")).toBeInTheDocument();
        expect(screen.getByText("-1.2")).toBeInTheDocument();

        expect(screen.getByText("103.8")).toBeInTheDocument();
        expect(screen.getByText("+0.3")).toBeInTheDocument();

        expect(screen.getByText("4.25")).toBeInTheDocument();
        expect(screen.getByText("+0.05")).toBeInTheDocument();
      });
    });

    it("includes indicator descriptions", async () => {
      renderMarketOverview();

      await waitFor(() => {
        expect(screen.getByText("Volatility Index")).toBeInTheDocument();
        expect(screen.getByText("Dollar Index")).toBeInTheDocument();
        expect(screen.getByText("Treasury Yield")).toBeInTheDocument();
      });
    });
  });

  describe("Market Status", () => {
    it("displays current market status", async () => {
      renderMarketOverview();

      await waitFor(() => {
        expect(screen.getByText(/market open/i)).toBeInTheDocument();
        expect(screen.getByText(/closes at 4:00 PM EST/i)).toBeInTheDocument();
      });
    });

    it("handles market closed status", async () => {
      const { default: api } = await import("../../../services/api");
      api.get.mockResolvedValue({
        data: {
          ...mockMarketData,
          marketStatus: {
            status: "CLOSED",
            nextOpen: "9:30 AM EST",
            nextClose: null,
          },
        },
      });

      renderMarketOverview();

      await waitFor(() => {
        expect(screen.getByText(/market closed/i)).toBeInTheDocument();
        expect(screen.getByText(/opens at 9:30 AM EST/i)).toBeInTheDocument();
      });
    });

    it("shows pre-market and after-hours status", async () => {
      const { default: api } = await import("../../../services/api");
      api.get.mockResolvedValue({
        data: {
          ...mockMarketData,
          marketStatus: {
            status: "PRE_MARKET",
            nextOpen: "9:30 AM EST",
            nextClose: null,
          },
        },
      });

      renderMarketOverview();

      await waitFor(() => {
        expect(screen.getByText(/pre-market/i)).toBeInTheDocument();
      });
    });
  });

  describe("Interactive Features", () => {
    it("navigates to detailed views", async () => {
      const user = userEvent.setup();
      renderMarketOverview();

      await waitFor(() => {
        const sectorButton = screen.getByRole("button", {
          name: /view sector details/i,
        });
        expect(sectorButton).toBeInTheDocument();
      });

      // Should navigate to sector analysis page
      const sectorButton = screen.getByRole("button", {
        name: /view sector details/i,
      });
      await user.click(sectorButton);
    });

    it("refreshes market data", async () => {
      const user = userEvent.setup();
      const { default: api } = await import("../../../services/api");

      renderMarketOverview();

      await waitFor(() => {
        const refreshButton = screen.getByRole("button", { name: /refresh/i });
        expect(refreshButton).toBeInTheDocument();
      });

      const refreshButton = screen.getByRole("button", { name: /refresh/i });
      await user.click(refreshButton);

      expect(api.get).toHaveBeenCalledTimes(2); // Initial load + refresh
    });

    it("supports time range selection", async () => {
      const user = userEvent.setup();
      renderMarketOverview();

      await waitFor(() => {
        const timeRangeSelect = screen.getByLabelText(/time range/i);
        expect(timeRangeSelect).toBeInTheDocument();
      });

      const timeRangeSelect = screen.getByLabelText(/time range/i);
      await user.selectOptions(timeRangeSelect, "1W");

      const { default: api } = await import("../../../services/api");
      expect(api.get).toHaveBeenCalledWith(
        expect.stringContaining("timeRange=1W")
      );
    });
  });

  describe("Charts and Visualizations", () => {
    it("displays market trend charts", async () => {
      renderMarketOverview();

      await waitFor(() => {
        expect(screen.getAllByTestId("line-chart")).toHaveLength(1); // Market overview chart
        expect(screen.getByTestId("bar-chart")).toBeInTheDocument(); // Sector performance
      });
    });

    it("shows heat map for sectors", async () => {
      renderMarketOverview();

      await waitFor(() => {
        const sectorHeatMap = screen.getByTestId("sector-heatmap");
        expect(sectorHeatMap).toBeInTheDocument();
      });
    });

    it("includes volume charts", async () => {
      renderMarketOverview();

      await waitFor(() => {
        const volumeChart = screen.getByTestId("volume-chart");
        expect(volumeChart).toBeInTheDocument();
      });
    });
  });

  describe("Real-time Updates", () => {
    it("handles real-time price updates", async () => {
      renderMarketOverview();

      const { default: api } = await import("../../../services/api");

      // Simulate real-time update
      const updatedData = {
        ...mockMarketData,
        indices: [
          { ...mockMarketData.indices[0], price: 452.75, change: 8.25 },
          ...mockMarketData.indices.slice(1),
        ],
      };

      api.get.mockResolvedValueOnce({ data: updatedData });

      // Simulate periodic update
      await waitFor(() => {
        expect(screen.getByText("450.25")).toBeInTheDocument();
      });

      // Mock the update interval
      vi.advanceTimersByTime(30000); // 30 second update interval

      await waitFor(() => {
        expect(screen.getByText("452.75")).toBeInTheDocument();
        expect(screen.getByText("+8.25")).toBeInTheDocument();
      });
    });

    it("shows update timestamp", async () => {
      renderMarketOverview();

      await waitFor(() => {
        expect(screen.getByText(/last updated/i)).toBeInTheDocument();
        expect(
          screen.getByText(/\d{1,2}:\d{2}:\d{2} [AP]M/)
        ).toBeInTheDocument();
      });
    });

    it("indicates when data is stale", async () => {
      const { default: api } = await import("../../../services/api");
      api.get.mockRejectedValue(new Error("Network error"));

      renderMarketOverview();

      await waitFor(() => {
        expect(screen.getByText(/data may be delayed/i)).toBeInTheDocument();
      });
    });
  });

  describe("Error Handling", () => {
    it("displays error message when data fails to load", async () => {
      const { default: api } = await import("../../../services/api");
      api.get.mockRejectedValue(new Error("API Error"));

      renderMarketOverview();

      await waitFor(() => {
        expect(
          screen.getByText(/failed to load market data/i)
        ).toBeInTheDocument();
        expect(
          screen.getByRole("button", { name: /try again/i })
        ).toBeInTheDocument();
      });
    });

    it("handles partial data loading gracefully", async () => {
      const { default: api } = await import("../../../services/api");
      api.get.mockResolvedValue({
        data: {
          indices: mockMarketData.indices,
          // Missing other sections
        },
      });

      renderMarketOverview();

      await waitFor(() => {
        expect(screen.getByText("S&P 500")).toBeInTheDocument();
        expect(screen.getByText(/some data unavailable/i)).toBeInTheDocument();
      });
    });

    it("retries failed requests", async () => {
      const user = userEvent.setup();
      const { default: api } = await import("../../../services/api");

      api.get.mockRejectedValueOnce(new Error("Network error"));
      api.get.mockResolvedValueOnce({ data: mockMarketData });

      renderMarketOverview();

      await waitFor(() => {
        const retryButton = screen.getByRole("button", { name: /try again/i });
        expect(retryButton).toBeInTheDocument();
      });

      const retryButton = screen.getByRole("button", { name: /try again/i });
      await user.click(retryButton);

      await waitFor(() => {
        expect(screen.getByText("S&P 500")).toBeInTheDocument();
      });

      expect(api.get).toHaveBeenCalledTimes(2);
    });
  });

  describe("Responsive Design", () => {
    it("adapts layout for mobile screens", () => {
      if (typeof window !== 'undefined') {
        Object.defineProperty(window, "innerWidth", {
          writable: true,
          configurable: true,
          value: 375,
        });
      }

      renderMarketOverview();

      const marketContainer = screen.getByTestId("market-overview-container");
      expect(marketContainer).toHaveClass("mobile-layout");
    });

    it("shows abbreviated data on mobile", async () => {
      if (typeof window !== 'undefined') {
        Object.defineProperty(window, "innerWidth", {
          writable: true,
          configurable: true,
          value: 375,
        });
      }

      renderMarketOverview();

      await waitFor(() => {
        // Should show condensed index cards
        const indexCards = screen.getAllByTestId("index-card-mobile");
        expect(indexCards).toHaveLength(3);
      });
    });

    it("adjusts chart sizes for different viewports", async () => {
      renderMarketOverview();

      await waitFor(() => {
        const chartContainer = screen.getByTestId("chart-container");
        expect(chartContainer).toHaveStyle({ width: "100%" });
      });
    });
  });

  describe("Performance Optimization", () => {
    it("implements lazy loading for charts", async () => {
      renderMarketOverview();

      // Charts should load after main data
      expect(screen.queryByTestId("line-chart")).not.toBeInTheDocument();

      await waitFor(() => {
        expect(screen.getByTestId("line-chart")).toBeInTheDocument();
      });
    });

    it("memoizes expensive calculations", async () => {
      const { rerender } = renderMarketOverview();

      // Create a new query client for rerender to avoid sharing state
      const queryClient = new QueryClient({
        defaultOptions: {
          queries: { retry: false },
          mutations: { retry: false },
        },
      });

      // Re-render with same data shouldn't trigger recalculation
      rerender(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter
            future={{
              v7_startTransition: true,
              v7_relativeSplatPath: true,
            }}
          >
            <MarketOverview />
          </MemoryRouter>
        </QueryClientProvider>
      );

      const { default: api } = await import("../../../services/api");
      expect(api.get).toHaveBeenCalledTimes(1);
    });

    it("uses virtual scrolling for large lists", async () => {
      const largeMovers = {
        gainers: Array.from({ length: 100 }, (_, i) => ({
          symbol: `STOCK${i}`,
          change: (i % 10) + 1,
          changePercent: (i % 5) + 0.5,
          price: 100 + (i % 100),
        })),
        losers: [],
      };

      const { default: api } = await import("../../../services/api");
      api.get.mockResolvedValue({
        data: { ...mockMarketData, movers: largeMovers },
      });

      renderMarketOverview();

      await waitFor(() => {
        const visibleItems = screen.getAllByTestId("mover-item");
        expect(visibleItems.length).toBeLessThan(largeMovers.gainers.length);
      });
    });
  });

  describe("Accessibility", () => {
    it("provides proper ARIA labels and accessibility", async () => {
      renderMarketOverview();

      await waitFor(
        () => {
          // Check for main heading accessibility
          expect(
            screen.getByRole("heading", { name: /market overview/i })
          ).toBeInTheDocument();
          // Check for tab navigation accessibility
          const tablist = screen.queryByRole("tablist");
          const tabs = screen.queryAllByRole("tab");
          // Should have accessible tab structure when component loads
          expect(tablist || tabs.length > 0).toBeTruthy();
        },
        { timeout: 10000 }
      );
    });

    it("supports keyboard navigation", async () => {
      const _user = userEvent.setup();
      renderMarketOverview();

      await waitFor(() => {
        const firstFocusable = screen.getByRole("button", { name: /refresh/i });
        firstFocusable.focus();
        expect(document.activeElement).toBe(firstFocusable);
      });
    });

    it("announces data updates to screen readers", async () => {
      renderMarketOverview();

      await waitFor(() => {
        const liveRegion = screen.getByRole("status");
        expect(liveRegion).toHaveAttribute("aria-live", "polite");
      });
    });

    it("provides alternative text for charts", async () => {
      renderMarketOverview();

      await waitFor(() => {
        expect(
          screen.getByLabelText(/s&p 500 trend chart/i)
        ).toBeInTheDocument();
        expect(
          screen.getByLabelText(/sector performance chart/i)
        ).toBeInTheDocument();
      });
    });
  });
});
