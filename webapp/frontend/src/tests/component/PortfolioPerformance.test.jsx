import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import { BrowserRouter } from "react-router-dom";
import PortfolioPerformance from "../../pages/PortfolioPerformance";

// Mock the API service
vi.mock("../../services/api", () => ({
  get: vi.fn(),
  post: vi.fn(),
}));

// Mock AuthContext
const mockAuthContext = {
  user: { sub: "test-user", email: "test@example.com" },
  token: "mock-jwt-token",
  isAuthenticated: true,
};

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => mockAuthContext,
}));

// Mock recharts components
vi.mock("recharts", () => ({
  LineChart: ({ children }) => <div data-testid="line-chart">{children}</div>,
  Line: () => <div data-testid="line" />,
  XAxis: () => <div data-testid="x-axis" />,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  ResponsiveContainer: ({ children }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
  AreaChart: ({ children }) => <div data-testid="area-chart">{children}</div>,
  Area: () => <div data-testid="area" />,
}));

// Import after mocking
import api from "../../services/api";

const renderWithRouter = (component) => {
  return render(<BrowserRouter>{component}</BrowserRouter>);
};

describe("PortfolioPerformance Component", () => {
  const mockPerformanceData = {
    overview: {
      totalValue: 125000.0,
      totalGainLoss: 25000.0,
      totalGainLossPercent: 25.0,
      dayGainLoss: 1250.0,
      dayGainLossPercent: 1.01,
    },
    holdings: [
      {
        symbol: "AAPL",
        quantity: 100,
        currentPrice: 150.0,
        marketValue: 15000.0,
        costBasis: 12000.0,
        gainLoss: 3000.0,
        gainLossPercent: 25.0,
      },
      {
        symbol: "GOOGL",
        quantity: 50,
        currentPrice: 2800.0,
        marketValue: 140000.0,
        costBasis: 125000.0,
        gainLoss: 15000.0,
        gainLossPercent: 12.0,
      },
    ],
    performance: {
      timeRange: "1Y",
      data: [
        { date: "2023-01-01", value: 100000, returns: 0 },
        { date: "2023-06-01", value: 110000, returns: 10.0 },
        { date: "2023-12-01", value: 125000, returns: 25.0 },
      ],
    },
    analytics: {
      sharpeRatio: 1.45,
      volatility: 18.5,
      maxDrawdown: -8.2,
      beta: 1.1,
    },
  };

  beforeEach(() => {
    vi.clearAllMocks();

    // Default API responses
    api.get.mockResolvedValue({
      data: {
        success: true,
        data: mockPerformanceData,
      },
    });
  });

  describe("Component Loading", () => {
    it("should render portfolio performance interface", async () => {
      renderWithRouter(<PortfolioPerformance />);

      expect(screen.getByText(/Portfolio Performance/i)).toBeInTheDocument();

      await waitFor(() => {
        expect(screen.getByText(/Total Value/i)).toBeInTheDocument();
        expect(screen.getByText(/Total Gain\/Loss/i)).toBeInTheDocument();
      });
    });

    it("should load performance data on mount", async () => {
      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledWith("/api/portfolio/performance");
      });

      await waitFor(() => {
        expect(screen.getByText("$125,000.00")).toBeInTheDocument();
        expect(screen.getByText("+$25,000.00")).toBeInTheDocument();
        expect(screen.getByText("+25.00%")).toBeInTheDocument();
      });
    });

    it("should show loading state initially", async () => {
      api.get.mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () =>
                resolve({
                  data: { success: true, data: mockPerformanceData },
                }),
              100
            )
          )
      );

      renderWithRouter(<PortfolioPerformance />);

      expect(
        screen.getByText(/Loading portfolio performance/i)
      ).toBeInTheDocument();

      await waitFor(
        () => {
          expect(
            screen.queryByText(/Loading portfolio performance/i)
          ).not.toBeInTheDocument();
        },
        { timeout: 200 }
      );
    });
  });

  describe("Performance Metrics Display", () => {
    it("should display key performance metrics", async () => {
      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByText("$125,000.00")).toBeInTheDocument();
        expect(screen.getByText("+$25,000.00")).toBeInTheDocument();
        expect(screen.getByText("+25.00%")).toBeInTheDocument();
        expect(screen.getByText("+$1,250.00")).toBeInTheDocument();
        expect(screen.getByText("+1.01%")).toBeInTheDocument();
      });
    });

    it("should display analytics metrics", async () => {
      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByText("1.45")).toBeInTheDocument(); // Sharpe Ratio
        expect(screen.getByText("18.5%")).toBeInTheDocument(); // Volatility
        expect(screen.getByText("-8.2%")).toBeInTheDocument(); // Max Drawdown
        expect(screen.getByText("1.1")).toBeInTheDocument(); // Beta
      });
    });

    it("should handle negative performance correctly", async () => {
      const negativePerformanceData = {
        ...mockPerformanceData,
        overview: {
          ...mockPerformanceData.overview,
          totalGainLoss: -5000.0,
          totalGainLossPercent: -5.0,
          dayGainLoss: -250.0,
          dayGainLossPercent: -0.25,
        },
      };

      api.get.mockResolvedValue({
        data: { success: true, data: negativePerformanceData },
      });

      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByText("-$5,000.00")).toBeInTheDocument();
        expect(screen.getByText("-5.00%")).toBeInTheDocument();
        expect(screen.getByText("-$250.00")).toBeInTheDocument();
        expect(screen.getByText("-0.25%")).toBeInTheDocument();
      });
    });
  });

  describe("Holdings Display", () => {
    it("should display portfolio holdings", async () => {
      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
        expect(screen.getByText("GOOGL")).toBeInTheDocument();
        expect(screen.getByText("100")).toBeInTheDocument(); // AAPL quantity
        expect(screen.getByText("50")).toBeInTheDocument(); // GOOGL quantity
      });
    });

    it("should display holding values and gains", async () => {
      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByText("$15,000.00")).toBeInTheDocument(); // AAPL market value
        expect(screen.getByText("$140,000.00")).toBeInTheDocument(); // GOOGL market value
        expect(screen.getByText("+$3,000.00")).toBeInTheDocument(); // AAPL gain
        expect(screen.getByText("+$15,000.00")).toBeInTheDocument(); // GOOGL gain
      });
    });

    it("should sort holdings by different criteria", async () => {
      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      // Click sort by value
      const sortByValueButton = screen.getByText(/Sort by Value/i);
      fireEvent.click(sortByValueButton);

      // GOOGL should appear first (higher value)
      const holdings = screen.getAllByTestId("holding-row");
      expect(holdings[0]).toHaveTextContent("GOOGL");
      expect(holdings[1]).toHaveTextContent("AAPL");
    });
  });

  describe("Performance Chart", () => {
    it("should render performance chart", async () => {
      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByTestId("line-chart")).toBeInTheDocument();
        expect(screen.getByTestId("responsive-container")).toBeInTheDocument();
      });
    });

    it("should switch between different time ranges", async () => {
      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByText("1Y")).toBeInTheDocument();
      });

      // Click 6M button
      fireEvent.click(screen.getByText("6M"));

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledWith(
          "/api/portfolio/performance?timeRange=6M"
        );
      });
    });

    it("should display different chart types", async () => {
      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByTestId("line-chart")).toBeInTheDocument();
      });

      // Switch to area chart
      fireEvent.click(screen.getByText(/Area Chart/i));

      await waitFor(() => {
        expect(screen.getByTestId("area-chart")).toBeInTheDocument();
      });
    });
  });

  describe("Time Range Filters", () => {
    it("should provide time range filter options", async () => {
      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByText("1D")).toBeInTheDocument();
        expect(screen.getByText("1W")).toBeInTheDocument();
        expect(screen.getByText("1M")).toBeInTheDocument();
        expect(screen.getByText("3M")).toBeInTheDocument();
        expect(screen.getByText("6M")).toBeInTheDocument();
        expect(screen.getByText("1Y")).toBeInTheDocument();
        expect(screen.getByText("ALL")).toBeInTheDocument();
      });
    });

    it("should update data when time range changes", async () => {
      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByText("1Y")).toBeInTheDocument();
      });

      // Click 3M button
      fireEvent.click(screen.getByText("3M"));

      await waitFor(() => {
        expect(api.get).toHaveBeenLastCalledWith(
          "/api/portfolio/performance?timeRange=3M"
        );
      });
    });

    it("should highlight active time range", async () => {
      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByText("1Y")).toHaveClass("active");
      });

      fireEvent.click(screen.getByText("6M"));

      await waitFor(() => {
        expect(screen.getByText("6M")).toHaveClass("active");
        expect(screen.getByText("1Y")).not.toHaveClass("active");
      });
    });
  });

  describe("Error Handling", () => {
    it("should handle API errors gracefully", async () => {
      api.get.mockRejectedValue({
        response: {
          data: {
            success: false,
            error: "Failed to load performance data",
          },
        },
      });

      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(
          screen.getByText(/Failed to load performance data/i)
        ).toBeInTheDocument();
      });
    });

    it("should handle network errors", async () => {
      api.get.mockRejectedValue(new Error("Network error"));

      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(
          screen.getByText(/Unable to load portfolio performance/i)
        ).toBeInTheDocument();
      });
    });

    it("should provide retry functionality", async () => {
      api.get
        .mockRejectedValueOnce(new Error("Network error"))
        .mockResolvedValue({
          data: { success: true, data: mockPerformanceData },
        });

      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(
          screen.getByText(/Unable to load portfolio performance/i)
        ).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText(/Retry/i));

      await waitFor(() => {
        expect(screen.getByText("$125,000.00")).toBeInTheDocument();
      });

      expect(api.get).toHaveBeenCalledTimes(2);
    });
  });

  describe("Data Refresh", () => {
    it("should refresh data when refresh button is clicked", async () => {
      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByText("$125,000.00")).toBeInTheDocument();
      });

      // Click refresh button
      fireEvent.click(screen.getByLabelText(/Refresh/i));

      await waitFor(() => {
        expect(api.get).toHaveBeenCalledTimes(2);
      });
    });

    it("should auto-refresh data periodically", async () => {
      vi.useFakeTimers();

      renderWithRouter(<PortfolioPerformance />);

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
  });

  describe("Responsive Design", () => {
    it("should handle mobile viewport", async () => {
      // Mock window.innerWidth
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: 375,
      });

      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByTestId("mobile-layout")).toBeInTheDocument();
      });
    });

    it("should handle tablet viewport", async () => {
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: 768,
      });

      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByTestId("tablet-layout")).toBeInTheDocument();
      });
    });
  });

  describe("Accessibility", () => {
    it("should have proper ARIA labels", async () => {
      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(
          screen.getByLabelText(/Portfolio total value/i)
        ).toBeInTheDocument();
        expect(
          screen.getByLabelText(/Portfolio gain loss/i)
        ).toBeInTheDocument();
      });
    });

    it("should be keyboard navigable", async () => {
      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByText("1Y")).toBeInTheDocument();
      });

      // Focus time range buttons
      const buttons = screen.getAllByRole("button");
      buttons[0].focus();
      expect(buttons[0]).toHaveFocus();

      // Tab navigation
      fireEvent.keyDown(buttons[0], { key: "Tab" });
      expect(buttons[1]).toHaveFocus();
    });

    it("should announce data updates to screen readers", async () => {
      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByText("$125,000.00")).toBeInTheDocument();
      });

      // Change time range
      fireEvent.click(screen.getByText("6M"));

      await waitFor(() => {
        expect(
          screen.getByLabelText(/Portfolio performance updated/i)
        ).toBeInTheDocument();
      });
    });
  });

  describe("Performance Optimization", () => {
    it("should memoize expensive calculations", async () => {
      const spy = vi.spyOn(React, "useMemo");

      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByText("$125,000.00")).toBeInTheDocument();
      });

      expect(spy).toHaveBeenCalled();

      spy.mockRestore();
    });

    it("should debounce rapid filter changes", async () => {
      vi.useFakeTimers();

      renderWithRouter(<PortfolioPerformance />);

      await waitFor(() => {
        expect(screen.getByText("1Y")).toBeInTheDocument();
      });

      // Rapid clicks
      fireEvent.click(screen.getByText("6M"));
      fireEvent.click(screen.getByText("3M"));
      fireEvent.click(screen.getByText("1M"));

      // Only the last call should be made after debounce
      vi.runAllTimers();

      await waitFor(() => {
        expect(api.get).toHaveBeenLastCalledWith(
          "/api/portfolio/performance?timeRange=1M"
        );
      });

      vi.useRealTimers();
    });
  });
});
