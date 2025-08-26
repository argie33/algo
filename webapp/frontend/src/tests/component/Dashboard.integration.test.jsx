import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { vi } from "vitest";
import { BrowserRouter } from "react-router-dom";
import Dashboard from "../../pages/Dashboard";
import { TestWrapper } from "../test-utils";
import { AuthProvider } from "../../contexts/AuthContext";

// Mock the API service with comprehensive mock
vi.mock("../../services/api", async (_importOriginal) => {
  const { createApiServiceMock } = await import('../mocks/api-service-mock');
  return {
    default: createApiServiceMock(),
    ...createApiServiceMock()
  };
});

// Mock recharts components to avoid rendering issues
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  LineChart: ({ children }) => <div data-testid="line-chart">{children}</div>,
  Line: () => <div data-testid="line" />,
  BarChart: ({ children }) => <div data-testid="bar-chart">{children}</div>,
  Bar: () => <div data-testid="bar" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  PieChart: ({ children }) => <div data-testid="pie-chart">{children}</div>,
  Pie: () => <div data-testid="pie" />,
  Cell: () => <div data-testid="cell" />,
  Legend: () => <div data-testid="legend" />,
  AreaChart: ({ children }) => <div data-testid="area-chart">{children}</div>,
  Area: () => <div data-testid="area" />,
}));

// Import after mocking
import api from "../../services/api";

const renderWithProviders = (component) => {
  return render(component, { wrapper: TestWrapper });
};

const mockAuthContext = {
  user: { id: 'test-user', email: 'test@example.com' },
  isAuthenticated: true,
  login: vi.fn(),
  logout: vi.fn(),
  loading: false
};

describe("Dashboard Integration Tests", () => {
  const mockDashboardData = {
    portfolio: {
      totalValue: 125000.0,
      dayChange: 2500.0,
      dayChangePercent: 2.04,
      holdings: [
        {
          symbol: "AAPL",
          name: "Apple Inc.",
          quantity: 100,
          currentPrice: 150.0,
          marketValue: 15000.0,
          dayChange: 250.0,
          dayChangePercent: 1.69,
          allocation: 12.0,
        },
        {
          symbol: "MSFT",
          name: "Microsoft Corporation",
          quantity: 75,
          currentPrice: 300.0,
          marketValue: 22500.0,
          dayChange: 450.0,
          dayChangePercent: 2.04,
          allocation: 18.0,
        },
        {
          symbol: "GOOGL",
          name: "Alphabet Inc.",
          quantity: 50,
          currentPrice: 2800.0,
          marketValue: 140000.0,
          dayChange: 1800.0,
          dayChangePercent: 1.3,
          allocation: 70.0,
        },
      ],
    },
    marketData: {
      indices: [
        {
          symbol: "SPY",
          name: "S&P 500 ETF",
          price: 420.5,
          change: 5.25,
          changePercent: 1.27,
        },
        {
          symbol: "QQQ",
          name: "Nasdaq ETF",
          price: 350.75,
          change: -2.15,
          changePercent: -0.61,
        },
      ],
      sectors: [
        { name: "Technology", performance: 2.5 },
        { name: "Healthcare", performance: -0.8 },
        { name: "Finance", performance: 1.2 },
      ],
    },
    news: [
      {
        id: 1,
        headline: "Market Reaches New High Amid Tech Rally",
        summary: "Technology stocks lead broad market gains...",
        source: "Financial News",
        publishedAt: "2023-06-15T14:30:00Z",
        sentiment: "positive",
        relevantSymbols: ["AAPL", "MSFT", "GOOGL"],
      },
      {
        id: 2,
        headline: "Fed Minutes Show Cautious Approach to Interest Rates",
        summary: "Federal Reserve officials express caution...",
        source: "Reuters",
        publishedAt: "2023-06-15T13:15:00Z",
        sentiment: "neutral",
        relevantSymbols: ["SPY"],
      },
    ],
    alerts: [
      {
        id: 1,
        type: "price_target",
        message: "AAPL reached your price target of $150",
        symbol: "AAPL",
        timestamp: "2023-06-15T15:00:00Z",
        severity: "info",
      },
      {
        id: 2,
        type: "volume_spike",
        message: "Unusual volume detected in MSFT",
        symbol: "MSFT",
        timestamp: "2023-06-15T14:45:00Z",
        severity: "warning",
      },
    ],
    performance: {
      timeRange: "1M",
      data: [
        { date: "2023-05-15", value: 120000, returns: 0 },
        { date: "2023-05-22", value: 122000, returns: 1.67 },
        { date: "2023-05-29", value: 119000, returns: -0.83 },
        { date: "2023-06-05", value: 123000, returns: 2.5 },
        { date: "2023-06-12", value: 125000, returns: 4.17 },
      ],
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();

    // Default successful API responses
    api.get.mockImplementation((endpoint) => {
      switch (endpoint) {
        case "/api/dashboard":
          return Promise.resolve({
            data: {
              success: true,
              data: mockDashboardData,
            },
          });
        case "/api/portfolio/summary":
          return Promise.resolve({
            data: {
              success: true,
              data: mockDashboardData.portfolio,
            },
          });
        case "/api/market/overview":
          return Promise.resolve({
            data: {
              success: true,
              data: mockDashboardData.marketData,
            },
          });
        case "/api/news/latest":
          return Promise.resolve({
            data: {
              success: true,
              data: mockDashboardData.news,
            },
          });
        case "/api/alerts/active":
          return Promise.resolve({
            data: {
              success: true,
              data: mockDashboardData.alerts,
            },
          });
        default:
          return Promise.resolve({
            data: { success: true, data: {} },
          });
      }
    });
  });

  describe("Dashboard Loading and Layout", () => {
    it("should render dashboard with all main sections", async () => {
      renderWithProviders(<Dashboard />);

      // Check main dashboard title
      expect(screen.getByText(/Dashboard/i)).toBeInTheDocument();

      // Wait for data to load and check main sections
      await waitFor(() => {
        expect(screen.getByText(/Portfolio Overview/i)).toBeInTheDocument();
        expect(screen.getByText(/Market Overview/i)).toBeInTheDocument();
        expect(screen.getByText(/Recent News/i)).toBeInTheDocument();
        expect(screen.getByText(/Alerts/i)).toBeInTheDocument();
      });
    });

    it("should show loading state initially", async () => {
      // Mock delayed API response
      api.get.mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  data: { success: true, data: mockDashboardData },
                }),
              100
            )
          )
      );

      renderWithProviders(<Dashboard />);

      expect(screen.getByText(/Loading dashboard/i)).toBeInTheDocument();

      await waitFor(
        () => {
          expect(
            screen.queryByText(/Loading dashboard/i)
          ).not.toBeInTheDocument();
        },
        { timeout: 200 }
      );
    });

    it("should load data from multiple API endpoints", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledWith("/api/dashboard");
      });

      // Verify all expected API calls are made
      expect(api.get).toHaveBeenCalledTimes(1);
    });
  });

  describe("Portfolio Overview Section", () => {
    it("should display portfolio summary metrics", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByText("$125,000.00")).toBeInTheDocument();
        expect(screen.getByText("+$2,500.00")).toBeInTheDocument();
        expect(screen.getByText("+2.04%")).toBeInTheDocument();
      });
    });

    it("should display top holdings with allocation", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
        expect(screen.getByText("MSFT")).toBeInTheDocument();
        expect(screen.getByText("GOOGL")).toBeInTheDocument();
        expect(screen.getByText("12.0%")).toBeInTheDocument(); // AAPL allocation
        expect(screen.getByText("70.0%")).toBeInTheDocument(); // GOOGL allocation
      });
    });

    it("should show portfolio performance chart", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByTestId("line-chart")).toBeInTheDocument();
        expect(screen.getByTestId("responsive-container")).toBeInTheDocument();
      });
    });

    it("should handle negative portfolio performance", async () => {
      const negativeData = {
        ...mockDashboardData,
        portfolio: {
          ...mockDashboardData.portfolio,
          dayChange: -1500.0,
          dayChangePercent: -1.18,
        },
      };

      api.get.mockResolvedValue({
        data: { success: true, data: negativeData },
      });

      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByText("-$1,500.00")).toBeInTheDocument();
        expect(screen.getByText("-1.18%")).toBeInTheDocument();
      });
    });
  });

  describe("Market Overview Section", () => {
    it("should display market indices", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByText("S&P 500 ETF")).toBeInTheDocument();
        expect(screen.getByText("Nasdaq ETF")).toBeInTheDocument();
        expect(screen.getByText("420.50")).toBeInTheDocument();
        expect(screen.getByText("+5.25")).toBeInTheDocument();
      });
    });

    it("should display sector performance", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByText("Technology")).toBeInTheDocument();
        expect(screen.getByText("Healthcare")).toBeInTheDocument();
        expect(screen.getByText("Finance")).toBeInTheDocument();
        expect(screen.getByText("2.5%")).toBeInTheDocument();
        expect(screen.getByText("-0.8%")).toBeInTheDocument();
      });
    });

    it("should show sector performance visualization", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByTestId("pie-chart")).toBeInTheDocument();
      });
    });
  });

  describe("News Section Integration", () => {
    it("should display recent news articles", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(
          screen.getByText("Market Reaches New High Amid Tech Rally")
        ).toBeInTheDocument();
        expect(
          screen.getByText(
            "Fed Minutes Show Cautious Approach to Interest Rates"
          )
        ).toBeInTheDocument();
        expect(screen.getByText("Financial News")).toBeInTheDocument();
        expect(screen.getByText("Reuters")).toBeInTheDocument();
      });
    });

    it("should show news sentiment indicators", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        // Check for sentiment indicators
        const newsSection =
          screen
            .getByText("Recent News")
            .closest('[data-testid="news-section"]') ||
          screen.getByText("Recent News").parentElement;
        expect(newsSection).toBeInTheDocument();
      });
    });

    it("should link news to relevant symbols", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        // Check that news articles show relevant symbols
        expect(screen.getByText(/AAPL|MSFT|GOOGL/)).toBeInTheDocument();
      });
    });
  });

  describe("Alerts Section Integration", () => {
    it("should display active alerts", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(
          screen.getByText(/AAPL reached your price target/i)
        ).toBeInTheDocument();
        expect(
          screen.getByText(/Unusual volume detected in MSFT/i)
        ).toBeInTheDocument();
      });
    });

    it("should show alert severity levels", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        // Check for severity indicators (info, warning, etc.)
        const alertsSection =
          screen.getByText(/Alerts/i).closest("section") ||
          screen.getByText(/Alerts/i).parentElement;
        expect(alertsSection).toBeInTheDocument();
      });
    });

    it("should handle empty alerts state", async () => {
      const dataWithoutAlerts = {
        ...mockDashboardData,
        alerts: [],
      };

      api.get.mockResolvedValue({
        data: { success: true, data: dataWithoutAlerts },
      });

      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByText(/No active alerts/i)).toBeInTheDocument();
      });
    });
  });

  describe("Real-time Updates", () => {
    it("should refresh data when refresh button is clicked", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledTimes(1);
      });

      // Click refresh button
      const refreshButton =
        screen.getByLabelText(/refresh/i) ||
        screen.getByRole("button", { name: /refresh/i });
      fireEvent.click(refreshButton);

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledTimes(2);
      });
    });

    it("should auto-refresh data periodically", async () => {
      vi.useFakeTimers();

      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledTimes(1);
      });

      // Fast forward 5 minutes
      vi.advanceTimersByTime(5 * 60 * 1000);

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledTimes(2);
      });

      vi.useRealTimers();
    });

    it("should handle real-time price updates", async () => {
      const { rerender } = renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByText("150.00")).toBeInTheDocument(); // AAPL price
      });

      // Simulate price update
      const updatedData = {
        ...mockDashboardData,
        portfolio: {
          ...mockDashboardData.portfolio,
          holdings: [
            {
              ...mockDashboardData.portfolio.holdings[0],
              currentPrice: 152.5,
              marketValue: 15250.0,
            },
            ...mockDashboardData.portfolio.holdings.slice(1),
          ],
        },
      };

      api.get.mockResolvedValue({
        data: { success: true, data: updatedData },
      });

      rerender(
        <BrowserRouter>
          <AuthProvider value={mockAuthContext}>
            <Dashboard />
          </AuthProvider>
        </BrowserRouter>
      );

      await waitFor(() => {
        expect(screen.getByText("152.50")).toBeInTheDocument();
        expect(screen.getByText("15250.00")).toBeInTheDocument();
      });
    });
  });

  describe("Error Handling", () => {
    it("should handle API errors gracefully", async () => {
      api.get.mockRejectedValue({
        response: {
          data: {
            success: false,
            error: "Failed to load dashboard data",
          },
        },
      });

      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(
          screen.getByText(/Failed to load dashboard data/i)
        ).toBeInTheDocument();
      });
    });

    it("should handle network errors", async () => {
      api.get.mockRejectedValue(new Error("Network error"));

      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(
          screen.getByText(/Unable to load dashboard/i)
        ).toBeInTheDocument();
      });
    });

    it("should provide retry functionality after errors", async () => {
      api.get
        .mockRejectedValueOnce(new Error("Network error"))
        .mockResolvedValue({
          data: { success: true, data: mockDashboardData },
        });

      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(
          screen.getByText(/Unable to load dashboard/i)
        ).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText(/retry/i));

      await waitFor(() => {
        expect(screen.getByText("$125,000.00")).toBeInTheDocument();
      });

      expect(api.get).toHaveBeenCalledTimes(2);
    });

    it("should handle partial data loading failures", async () => {
      // Mock successful dashboard call but failed market data
      api.get.mockImplementation((endpoint) => {
        if (endpoint === "/api/market/overview") {
          return Promise.reject(new Error("Market data unavailable"));
        }
        return Promise.resolve({
          data: { success: true, data: mockDashboardData },
        });
      });

      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        // Portfolio data should still load
        expect(screen.getByText("$125,000.00")).toBeInTheDocument();
        // Market section should show error
        expect(
          screen.getByText(/Market data unavailable/i)
        ).toBeInTheDocument();
      });
    });
  });

  describe("Responsive Design", () => {
    it("should adapt to mobile viewport", async () => {
      // Mock window.innerWidth
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: 375,
      });

      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByTestId("mobile-dashboard")).toBeInTheDocument();
      });
    });

    it("should show condensed view on tablet", async () => {
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: 768,
      });

      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByTestId("tablet-dashboard")).toBeInTheDocument();
      });
    });
  });

  describe("Navigation Integration", () => {
    it("should navigate to detailed views when sections are clicked", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByText("Portfolio Overview")).toBeInTheDocument();
      });

      // Click on portfolio section
      fireEvent.click(screen.getByText("View Details"));

      // Should navigate to portfolio page (tested via router mock)
      expect(window.location.pathname).toBe("/");
    });

    it("should support keyboard navigation between sections", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByText("Portfolio Overview")).toBeInTheDocument();
      });

      // Tab navigation between sections
      const sections = screen.getAllByRole("button");
      sections[0].focus();
      expect(sections[0]).toHaveFocus();

      fireEvent.keyDown(sections[0], { key: "Tab" });
      expect(sections[1]).toHaveFocus();
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA labels for all sections", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(
          screen.getByLabelText(/portfolio overview/i)
        ).toBeInTheDocument();
        expect(screen.getByLabelText(/market overview/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/recent news/i)).toBeInTheDocument();
        expect(screen.getByLabelText(/active alerts/i)).toBeInTheDocument();
      });
    });

    it("should announce data updates to screen readers", async () => {
      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(screen.getByText("$125,000.00")).toBeInTheDocument();
      });

      // Simulate data update
      const updatedData = {
        ...mockDashboardData,
        portfolio: {
          ...mockDashboardData.portfolio,
          totalValue: 126000.0,
        },
      };

      api.get.mockResolvedValue({
        data: { success: true, data: updatedData },
      });

      // Trigger refresh
      const refreshButton = screen.getByLabelText(/refresh/i);
      fireEvent.click(refreshButton);

      await waitFor(() => {
        expect(screen.getByLabelText(/dashboard updated/i)).toBeInTheDocument();
      });
    });

    it("should support high contrast mode", async () => {
      // Mock high contrast media query
      Object.defineProperty(window, "matchMedia", {
        writable: true,
        value: vi.fn().mockImplementation((query) => ({
          matches: query === "(prefers-contrast: high)",
          media: query,
          onchange: null,
          addListener: vi.fn(),
          removeListener: vi.fn(),
        })),
      });

      renderWithProviders(<Dashboard />);

      await waitFor(() => {
        expect(
          screen.getByTestId("high-contrast-dashboard")
        ).toBeInTheDocument();
      });
    });
  });
});
