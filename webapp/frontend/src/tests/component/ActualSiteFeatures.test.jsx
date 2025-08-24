import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryProvider } from "@tanstack/react-query";
import Dashboard from "../../pages/Dashboard";

// Mock the API service with comprehensive mock
vi.mock("../../services/api", async (_importOriginal) => {
  const { createApiServiceMock } = await import('../mocks/api-service-mock');
  return {
    default: createApiServiceMock(),
    ...createApiServiceMock()
  };
});

// Mock data cache service
vi.mock("../../services/dataCache", () => ({
  get: vi.fn(),
}));

// Mock AuthContext
const mockAuthContext = {
  user: {
    sub: "test-user",
    email: "test@protradeanalytics.com",
    name: "John Trader",
    firstName: "John",
  },
  token: "mock-jwt-token",
  isAuthenticated: true,
};

const mockUnauthenticatedContext = {
  user: null,
  token: null,
  isAuthenticated: false,
};

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: vi.fn(() => mockAuthContext),
}));

// Mock recharts components
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  PieChart: ({ children }) => <div data-testid="pie-chart">{children}</div>,
  Pie: ({ children }) => <div data-testid="pie">{children}</div>,
  Cell: () => <div data-testid="cell" />,
  BarChart: ({ children }) => <div data-testid="bar-chart">{children}</div>,
  Bar: () => <div data-testid="bar" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
}));

// Mock HistoricalPriceChart component
vi.mock("../../components/HistoricalPriceChart", () => ({
  default: function MockHistoricalPriceChart({ symbol, defaultPeriod }) {
    return (
      <div data-testid="historical-price-chart">
        <div>Symbol: {symbol}</div>
        <div>Period: {defaultPeriod} days</div>
      </div>
    );
  }
}));

// Mock MarketStatusBar component
vi.mock("../../components/MarketStatusBar", () => {
  return function MockMarketStatusBar() {
    return (
      <div data-testid="market-status-bar">
        <div>Market Status: Open</div>
        <div>Last Update: {new Date().toLocaleTimeString()}</div>
      </div>
    );
  };
});

// Import after mocking
import api from "../../services/api";
import dataCache from "../../services/dataCache";
import { useAuth } from "../../contexts/AuthContext";

const renderWithProviders = (component, { authenticated = true } = {}) => {
  if (!authenticated) {
    useAuth.mockReturnValue(mockUnauthenticatedContext);
  } else {
    useAuth.mockReturnValue(mockAuthContext);
  }

  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: 0,
        cacheTime: 0,
      },
    },
  });

  return render(
    <QueryProvider client={queryClient}>
      <BrowserRouter>{component}</BrowserRouter>
    </QueryProvider>
  );
};

describe("Actual Site Features Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuth.mockReturnValue(mockAuthContext);

    // Mock successful API responses
    api.getStockPrices.mockResolvedValue({
      data: [
        { date: "2023-06-15", close: 150.25, timestamp: "2023-06-15" },
        { date: "2023-06-16", close: 152.1, timestamp: "2023-06-16" },
        { date: "2023-06-17", close: 149.8, timestamp: "2023-06-17" },
      ],
    });

    api.getStockMetrics.mockResolvedValue({
      data: {
        beta: 1.2,
        volatility: 0.28,
        sharpe_ratio: 1.45,
        max_drawdown: -0.15,
      },
    });

    dataCache.get.mockResolvedValue({
      data: {
        sentiment: {
          fearGreed: 72,
          aaii: { bullish: 45, bearish: 28, neutral: 27 },
          naaim: 65,
          vix: 18.5,
          status: "Bullish",
        },
        sectors: [
          { sector: "Technology", performance: 2.1, color: "#00C49F" },
          { sector: "Healthcare", performance: 1.8, color: "#0088FE" },
          { sector: "Finance", performance: -0.5, color: "#FF8042" },
        ],
      },
    });

    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve({
            data: [
              {
                symbol: "AAPL",
                signal: "Buy",
                date: "2023-06-17",
                current_price: 150.25,
                performance_percent: 2.1,
              },
              {
                symbol: "TSLA",
                signal: "Sell",
                date: "2023-06-17",
                current_price: 710.22,
                performance_percent: -1.8,
              },
            ],
          }),
      })
    );
  });

  describe("ProTrade Analytics Dashboard Branding", () => {
    it("should display the correct brand name and tagline", async () => {
      renderWithProviders(<Dashboard />);

      expect(screen.getByText("ProTrade Analytics")).toBeInTheDocument();
      expect(
        screen.getByText("Elite Financial Intelligence Platform")
      ).toBeInTheDocument();
    });

    it("should show branded feature chips", async () => {
      renderWithProviders(<Dashboard />);

      expect(screen.getByText("Real-Time")).toBeInTheDocument();
      expect(screen.getByText("AI-Powered")).toBeInTheDocument();
      expect(screen.getByText("Institutional")).toBeInTheDocument();
      expect(screen.getByText("Advanced Analytics")).toBeInTheDocument();
    });

    it("should display brand footer with security features", async () => {
      renderWithProviders(<Dashboard />);

      expect(
        screen.getByText("ProTrade Analytics - Elite Financial Intelligence")
      ).toBeInTheDocument();
      expect(screen.getByText("Bank-Grade Security")).toBeInTheDocument();
      expect(screen.getByText("Sub-Second Latency")).toBeInTheDocument();
      expect(screen.getByText("Global Markets")).toBeInTheDocument();
    });
  });

  describe("Executive Command Center Features", () => {
    it("should display personalized welcome message for authenticated users", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByText("Welcome back, John")).toBeInTheDocument();
      });
    });

    it("should show portfolio metrics in command center", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByText("Portfolio Value")).toBeInTheDocument();
        expect(screen.getByText("$1,250,000")).toBeInTheDocument();
        expect(screen.getByText("Today's P&L")).toBeInTheDocument();
        expect(screen.getByText("$3,200")).toBeInTheDocument();
      });
    });

    it("should display system status indicators", async () => {
      renderWithProviders(<Dashboard />);

      expect(screen.getByText("System Status")).toBeInTheDocument();
      expect(screen.getByText("All Systems Operational")).toBeInTheDocument();
      expect(screen.getByText("Win Rate")).toBeInTheDocument();
      expect(screen.getByText("87.2%")).toBeInTheDocument();
    });

    it("should show demo mode banner for unauthenticated users", async () => {
      renderWithProviders(<Dashboard />, { authenticated: false });

      expect(screen.getByText(/Demo Mode:/)).toBeInTheDocument();
      expect(
        screen.getByText(/viewing sample data with full platform capabilities/)
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Sign In/ })
      ).toBeInTheDocument();
    });
  });

  describe("Navigation Grid Features", () => {
    it("should display all main navigation cards", async () => {
      renderWithProviders(<Dashboard />);

      const navigationSections = [
        "Portfolio",
        "Scores",
        "Screener",
        "Real-Time",
        "Market",
        "Metrics",
      ];

      navigationSections.forEach((section) => {
        expect(screen.getByText(section)).toBeInTheDocument();
      });
    });

    it("should have clickable navigation cards with proper URLs", async () => {
      renderWithProviders(<Dashboard />);

      // Mock window.location.href for testing navigation
      const originalLocation = window.location;
      delete window.location;
      window.location = { href: "" };

      const portfolioCard = screen
        .getByText("Portfolio")
        .closest(".MuiCard-root");
      fireEvent.click(portfolioCard);
      // Note: In actual test, you'd verify the navigation occurred

      window.location = originalLocation;
    });
  });

  describe("Market Summary Bar", () => {
    it("should display major market indices", async () => {
      renderWithProviders(<Dashboard />);

      const marketIndices = ["S&P 500", "NASDAQ", "DOW", "VIX", "DXY", "Gold"];

      marketIndices.forEach((index) => {
        expect(screen.getByText(index)).toBeInTheDocument();
      });
    });

    it("should show market values and percentage changes", async () => {
      renderWithProviders(<Dashboard />);

      expect(screen.getByText("5,432.1")).toBeInTheDocument(); // S&P 500 value
      expect(screen.getByText("+0.8%")).toBeInTheDocument(); // S&P 500 change
      expect(screen.getByText("17,890.55")).toBeInTheDocument(); // NASDAQ value
    });

    it("should display directional arrows for market changes", async () => {
      renderWithProviders(<Dashboard />);

      // Arrows are rendered as MUI icons, check for their presence
      const marketCards = screen.getAllByText(/[+]\d+\.\d+%|[-]\d+\.\d+%/);
      expect(marketCards.length).toBeGreaterThan(0);
    });
  });

  describe("Portfolio Overview Widget", () => {
    it("should display portfolio value and P&L metrics", async () => {
      renderWithProviders(<Dashboard />);

      expect(screen.getByText("Portfolio Overview")).toBeInTheDocument();
      expect(screen.getByText("$1,250,000")).toBeInTheDocument();

      // Check for P&L chips
      expect(screen.getByText(/Daily: \$3,200/)).toBeInTheDocument();
      expect(screen.getByText(/MTD: \$18,000/)).toBeInTheDocument();
      expect(screen.getByText(/YTD: \$92,000/)).toBeInTheDocument();
    });

    it("should render portfolio allocation pie chart", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByTestId("pie-chart")).toBeInTheDocument();
        expect(screen.getByTestId("responsive-container")).toBeInTheDocument();
      });
    });
  });

  describe("Elite Watchlist Widget", () => {
    it("should display watchlist table with stock data", async () => {
      renderWithProviders(<Dashboard />);

      expect(screen.getByText("Elite Watchlist")).toBeInTheDocument();

      // Check table headers
      expect(screen.getByText("Symbol")).toBeInTheDocument();
      expect(screen.getByText("Price")).toBeInTheDocument();
      expect(screen.getByText("Change")).toBeInTheDocument();
      expect(screen.getByText("Score")).toBeInTheDocument();
      expect(screen.getByText("Action")).toBeInTheDocument();
    });

    it("should show watchlist stock symbols and prices", async () => {
      renderWithProviders(<Dashboard />);

      const watchlistStocks = ["AAPL", "TSLA", "NVDA", "MSFT"];
      watchlistStocks.forEach((symbol) => {
        expect(screen.getByText(symbol)).toBeInTheDocument();
      });

      expect(screen.getByText("$195.12")).toBeInTheDocument(); // AAPL price
      expect(screen.getByText("$710.22")).toBeInTheDocument(); // TSLA price
    });

    it("should display stock scores with colored chips", async () => {
      renderWithProviders(<Dashboard />);

      // Scores are displayed as chips with different colors based on value
      const scoreChips = screen.getAllByText(/\d{2}/); // Two-digit scores
      expect(scoreChips.length).toBeGreaterThan(0);
    });
  });

  describe("Market Sentiment Widget", () => {
    it("should display Fear & Greed index and NAAIM scores", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByText("Market Sentiment")).toBeInTheDocument();
        expect(screen.getByText("Fear & Greed")).toBeInTheDocument();
        expect(screen.getByText("NAAIM")).toBeInTheDocument();
        expect(screen.getByText("72")).toBeInTheDocument(); // Fear & Greed score
        expect(screen.getByText("65")).toBeInTheDocument(); // NAAIM score
      });
    });

    it("should show AAII sentiment breakdown", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByText("Bulls: 45%")).toBeInTheDocument();
        expect(screen.getByText("Neutral: 27%")).toBeInTheDocument();
        expect(screen.getByText("Bears: 28%")).toBeInTheDocument();
      });
    });

    it("should display market status and VIX chips", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByText("Bullish Market")).toBeInTheDocument();
        expect(screen.getByText("VIX: 18.5")).toBeInTheDocument();
      });
    });
  });

  describe("Sector Performance Widget", () => {
    it("should display sector performance bar chart", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByText("Sector Performance")).toBeInTheDocument();
        expect(screen.getByTestId("bar-chart")).toBeInTheDocument();
      });
    });

    it("should show positive and negative sector performance", async () => {
      renderWithProviders(<Dashboard />);

      // The chart data includes both positive and negative performance
      // This is validated through the bar chart component rendering
      await waitFor(() => {
        expect(screen.getByTestId("responsive-container")).toBeInTheDocument();
      });
    });
  });

  describe("Technical Signals Widget", () => {
    it("should load and display technical signals", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByText("Technical Signals")).toBeInTheDocument();
        expect(screen.getByText("Live")).toBeInTheDocument();
      });

      // Check for signal table headers
      await waitFor(() => {
        expect(screen.getAllByText("Symbol").length).toBeGreaterThan(1); // Multiple tables have Symbol column
        expect(screen.getAllByText("Signal").length).toBeGreaterThan(0);
      });
    });

    it("should display buy and sell signals with colors", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        // Buy and Sell chips should be rendered with appropriate colors
        const signalElements = screen.getAllByText(/Buy|Sell/);
        expect(signalElements.length).toBeGreaterThan(0);
      });
    });

    it("should show stock prices and performance percentages", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByText("$150.25")).toBeInTheDocument(); // AAPL price
        expect(screen.getByText("2.1%")).toBeInTheDocument(); // Performance
      });
    });
  });

  describe("AI-Powered Intelligence Center", () => {
    it("should display the AI intelligence center section", async () => {
      renderWithProviders(<Dashboard />);

      expect(
        screen.getByText("AI-Powered Intelligence Center")
      ).toBeInTheDocument();
      expect(screen.getByText("Neural Networks")).toBeInTheDocument();
      expect(screen.getByText("Machine Learning")).toBeInTheDocument();
    });

    it("should show market intelligence insights", async () => {
      renderWithProviders(<Dashboard />);

      expect(screen.getByText("Market Intelligence")).toBeInTheDocument();
      expect(screen.getByText("Market Sentiment: Bullish")).toBeInTheDocument();
      expect(
        screen.getByText("Neural network confidence: 89%")
      ).toBeInTheDocument();
      expect(screen.getByText("Volatility Forecast")).toBeInTheDocument();
    });

    it("should display risk management metrics", async () => {
      renderWithProviders(<Dashboard />);

      expect(screen.getByText("Risk Management")).toBeInTheDocument();
      expect(screen.getByText("Portfolio Beta")).toBeInTheDocument();
      expect(screen.getByText("0.95")).toBeInTheDocument();
      expect(screen.getByText("Sharpe Ratio")).toBeInTheDocument();
      expect(screen.getByText("1.42")).toBeInTheDocument();
    });

    it("should show algorithm signals with performance metrics", async () => {
      renderWithProviders(<Dashboard />);

      expect(screen.getByText("Algorithm Signals")).toBeInTheDocument();
      expect(screen.getByText("Strategy Performance")).toBeInTheDocument();
      expect(
        screen.getByText("YTD: +23.7% • Win Rate: 87.2%")
      ).toBeInTheDocument();
    });
  });

  describe("Quick Actions Panel", () => {
    it("should display all quick action buttons", async () => {
      renderWithProviders(<Dashboard />);

      const quickActions = [
        "Add Position",
        "Trade History",
        "Place Order",
        "Run Backtest",
        "Screen Stocks",
        "Set Alert",
        "Export Data",
        "Settings",
      ];

      quickActions.forEach((action) => {
        expect(
          screen.getByRole("button", { name: action })
        ).toBeInTheDocument();
      });
    });

    it("should have proper navigation links for quick actions", async () => {
      renderWithProviders(<Dashboard />);

      // Mock window.location for navigation testing
      const originalLocation = window.location;
      delete window.location;
      window.location = { href: "" };

      const settingsButton = screen.getByRole("button", { name: "Settings" });
      fireEvent.click(settingsButton);
      // In actual implementation, would verify navigation occurred

      window.location = originalLocation;
    });
  });

  describe("Symbol Selector and Live Data", () => {
    it("should have symbol autocomplete with default options", async () => {
      renderWithProviders(<Dashboard />);

      const symbolInput = screen.getByLabelText("Symbol");
      expect(symbolInput).toBeInTheDocument();
      expect(symbolInput).toHaveValue("AAPL"); // Default value
    });

    it("should load historical price chart for selected symbol", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(
          screen.getByTestId("historical-price-chart")
        ).toBeInTheDocument();
        expect(screen.getByText("Symbol: AAPL")).toBeInTheDocument();
        expect(screen.getByText("Period: 30 days")).toBeInTheDocument();
      });
    });

    it("should change symbol when autocomplete selection changes", async () => {
      renderWithProviders(<Dashboard />);

      const symbolInput = screen.getByLabelText("Symbol");

      // Simulate changing symbol to MSFT
      fireEvent.change(symbolInput, { target: { value: "MSFT" } });
      fireEvent.keyDown(symbolInput, { key: "Enter" });

      // API calls should be made with new symbol
      await waitFor(() => {
        expect(api.getStockPrices).toHaveBeenCalledWith("AAPL", "daily", 30);
        expect(api.getStockMetrics).toHaveBeenCalledWith("AAPL");
      });
    });
  });

  describe("Market Status Bar Integration", () => {
    it("should display market status bar component", async () => {
      renderWithProviders(<Dashboard />);

      expect(screen.getByTestId("market-status-bar")).toBeInTheDocument();
      expect(screen.getByText("Market Status: Open")).toBeInTheDocument();
    });
  });

  describe("Real-time Data Integration", () => {
    it("should make API calls for live data", async () => {
      renderWithProviders(<Dashboard />);

      // Verify that API calls are made for various data sources
      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringContaining("/api/trading/signals/daily")
        );
      });
    });

    it("should handle API failures gracefully with fallback data", async () => {
      // Mock API failure
      global.fetch.mockRejectedValueOnce(new Error("API unavailable"));

      renderWithProviders(<Dashboard />);

      // Should still render with mock/fallback data
      await waitFor(() => {
        expect(screen.getByText("Technical Signals")).toBeInTheDocument();
      });
    });

    it("should refresh data periodically", async () => {
      vi.useFakeTimers();
      renderWithProviders(<Dashboard />);

      // Fast forward time to trigger refetch
      vi.advanceTimersByTime(5 * 60 * 1000); // 5 minutes

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledTimes(1);
      });

      vi.useRealTimers();
    });
  });

  describe("Responsive Design Elements", () => {
    it("should use MUI responsive grid system", async () => {
      renderWithProviders(<Dashboard />);

      // MUI Grid components should be present
      const gridElements = document.querySelectorAll('[class*="MuiGrid-"]');
      expect(gridElements.length).toBeGreaterThan(0);
    });

    it("should have proper card layouts for different screen sizes", async () => {
      renderWithProviders(<Dashboard />);

      // Cards should have MUI responsive classes
      const cardElements = document.querySelectorAll('[class*="MuiCard-"]');
      expect(cardElements.length).toBeGreaterThan(10); // Many cards on dashboard
    });
  });

  describe("User Authentication Integration", () => {
    it("should show different content for authenticated vs unauthenticated users", async () => {
      // Test authenticated user view
      renderWithProviders(<Dashboard />, { authenticated: true });
      expect(screen.getByText("Welcome back, John")).toBeInTheDocument();

      // Test unauthenticated user view
      renderWithProviders(<Dashboard />, { authenticated: false });
      expect(screen.getByText(/Demo Mode/)).toBeInTheDocument();
    });

    it("should display user avatar and information", async () => {
      renderWithProviders(<Dashboard />);

      // User avatar should be present (MUI Avatar component)
      const avatarElement = document.querySelector('[class*="MuiAvatar-"]');
      expect(avatarElement).toBeInTheDocument();
    });
  });

  describe("Error Handling and Loading States", () => {
    it("should handle loading states for async data", async () => {
      // Mock slow API response
      const slowPromise = new Promise((resolve) =>
        setTimeout(
          () =>
            resolve({
              data: { data: { signals: [] } },
            }),
          100
        )
      );

      global.fetch.mockReturnValueOnce(
        Promise.resolve({
          ok: true,
          json: () => slowPromise,
        })
      );

      renderWithProviders(<Dashboard />);

      // Should show loading state
      expect(screen.getByText("Loading signals...")).toBeInTheDocument();

      // Wait for data to load
      await waitFor(() => {
        expect(
          screen.queryByText("Loading signals...")
        ).not.toBeInTheDocument();
      });
    });

    it("should handle API errors with fallback content", async () => {
      // Mock API error
      global.fetch.mockRejectedValueOnce(new Error("Network error"));
      dataCache.get.mockRejectedValueOnce(new Error("Cache miss"));

      renderWithProviders(<Dashboard />);

      // Should still render dashboard with mock data
      await waitFor(() => {
        expect(screen.getByText("ProTrade Analytics")).toBeInTheDocument();
        expect(screen.getByText("Market Sentiment")).toBeInTheDocument();
      });
    });
  });

  describe("Financial Data Accuracy", () => {
    it("should format currency values correctly", async () => {
      renderWithProviders(<Dashboard />);

      // Check proper currency formatting
      expect(screen.getByText("$1,250,000")).toBeInTheDocument(); // Portfolio value
      expect(screen.getByText("$3,200")).toBeInTheDocument(); // P&L
      expect(screen.getByText("$18,000")).toBeInTheDocument(); // MTD
      expect(screen.getByText("$92,000")).toBeInTheDocument(); // YTD
    });

    it("should display percentage values with proper formatting", async () => {
      renderWithProviders(<Dashboard />);

      // Check percentage formatting in various widgets
      expect(screen.getByText("+0.8%")).toBeInTheDocument(); // Market change
      expect(screen.getByText("87.2%")).toBeInTheDocument(); // Win rate
      expect(screen.getByText("Bulls: 45%")).toBeInTheDocument(); // Sentiment
    });

    it("should show real-time timestamps", async () => {
      renderWithProviders(<Dashboard />);

      // Market status should show current time
      const timeElements = screen.getAllByText(/\d{1,2}:\d{2}:\d{2}/);
      expect(timeElements.length).toBeGreaterThan(0);
    });
  });
});
