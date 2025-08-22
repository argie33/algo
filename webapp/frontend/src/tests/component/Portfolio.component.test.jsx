/**
 * Portfolio Component Integration Test
 * Critical: Tests portfolio component with real data interactions
 */

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Portfolio from "../../pages/Portfolio";
import { AuthProvider } from "../../contexts/AuthContext";
import { ApiKeyProvider } from "../../contexts/ApiKeyProvider";

// Mock API responses
const mockPortfolioData = {
  success: true,
  data: {
    holdings: [
      {
        symbol: "AAPL",
        quantity: 100,
        avgCost: 150.5,
        currentPrice: 175.25,
        currentValue: 17525.0,
        gainLoss: 2475.0,
        gainLossPercent: 16.44,
        sector: "Technology",
      },
      {
        symbol: "TSLA",
        quantity: 50,
        avgCost: 200.0,
        currentPrice: 180.5,
        currentValue: 9025.0,
        gainLoss: -975.0,
        gainLossPercent: -9.75,
        sector: "Consumer Discretionary",
      },
    ],
    totalValue: 26550.0,
    totalCost: 25525.0,
    totalGainLoss: 1025.0,
    totalGainLossPercent: 4.02,
    sectorAllocation: [
      { sector: "Technology", percentage: 65.98, value: 17525.0 },
      { sector: "Consumer Discretionary", percentage: 34.02, value: 9025.0 },
    ],
    dayChange: 125.5,
    dayChangePercent: 0.47,
  },
};

const mockRiskMetrics = {
  success: true,
  data: {
    beta: 1.15,
    var95: -1250.5,
    var99: -1875.25,
    sharpeRatio: 0.85,
    volatility: 18.5,
    correlation: 0.72,
  },
};

// Mock services
vi.mock("../../services/api", () => ({
  api: {
    get: vi.fn(),
    defaults: { headers: { common: {} } },
  },
  getApiConfig: vi.fn(() => ({
    baseURL: "https://test-api.example.com",
    isConfigured: true,
  })),
}));

vi.mock("../../contexts/AuthContext", () => ({
  AuthProvider: ({ children }) => children,
  useAuth: () => ({
    user: {
      username: "test@example.com",
      userId: "test-user-123",
    },
    isAuthenticated: true,
    isLoading: false,
    tokens: {
      accessToken: "mock-token",
    },
  }),
}));

vi.mock("../../contexts/ApiKeyProvider", () => ({
  ApiKeyProvider: ({ children }) => children,
  useApiKeys: () => ({
    apiKeys: {
      alpaca: {
        keyId: "test-alpaca-key",
        secret: "test-secret",
        isValid: true,
      },
    },
    isLoading: false,
    hasRequiredKeys: () => true,
    refreshApiKeys: vi.fn(),
  }),
}));

describe("Portfolio Component Integration", () => {
  let queryClient;
  let user;
  let mockApi;

  const TestWrapper = ({ children }) => (
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <ApiKeyProvider>{children}</ApiKeyProvider>
        </AuthProvider>
      </QueryClientProvider>
    </BrowserRouter>
  );

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          cacheTime: 0,
        },
        mutations: { retry: false },
      },
    });

    user = userEvent.setup();
    mockApi = require("../../services/api").api;
    vi.clearAllMocks();

    // Default API responses
    mockApi.get.mockImplementation((url) => {
      if (url.includes("/api/portfolio/analytics")) {
        return Promise.resolve({ data: mockPortfolioData });
      }
      if (url.includes("/api/portfolio/risk-metrics")) {
        return Promise.resolve({ data: mockRiskMetrics });
      }
      return Promise.reject(new Error("Unexpected API call"));
    });
  });

  afterEach(() => {
    queryClient.clear();
    vi.restoreAllMocks();
  });

  describe("Portfolio Data Loading", () => {
    it("should load and display portfolio holdings correctly", async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Wait for data to load
      await waitFor(() => {
        expect(mockApi.get).toHaveBeenCalledWith(
          expect.stringContaining("/api/portfolio/analytics"),
          expect.objectContaining({
            headers: expect.objectContaining({
              Authorization: "Bearer mock-token",
            }),
          })
        );
      });

      // Verify holdings are displayed
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText("TSLA")).toBeInTheDocument();

      // Verify financial data
      expect(screen.getByText("$26,550.00")).toBeInTheDocument(); // Total value
      expect(screen.getByText("$1,025.00")).toBeInTheDocument(); // Total gain/loss
      expect(screen.getByText("4.02%")).toBeInTheDocument(); // Gain/loss percentage
    });

    it("should display individual holding details correctly", async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      // Find AAPL row and verify details
      const aaplRow = screen.getByText("AAPL").closest("tr");
      expect(within(aaplRow).getByText("100")).toBeInTheDocument(); // Quantity
      expect(within(aaplRow).getByText("$150.50")).toBeInTheDocument(); // Avg cost
      expect(within(aaplRow).getByText("$175.25")).toBeInTheDocument(); // Current price
      expect(within(aaplRow).getByText("$17,525.00")).toBeInTheDocument(); // Current value
      expect(within(aaplRow).getByText("$2,475.00")).toBeInTheDocument(); // Gain/loss
      expect(within(aaplRow).getByText("16.44%")).toBeInTheDocument(); // Gain/loss %
    });

    it("should handle negative positions correctly", async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("TSLA")).toBeInTheDocument();
      });

      // Find TSLA row and verify negative values are displayed correctly
      const tslaRow = screen.getByText("TSLA").closest("tr");
      expect(within(tslaRow).getByText("-$975.00")).toBeInTheDocument(); // Negative gain/loss
      expect(within(tslaRow).getByText("-9.75%")).toBeInTheDocument(); // Negative percentage

      // Verify negative values have appropriate styling
      const negativeValue = within(tslaRow).getByText("-$975.00");
      expect(negativeValue).toHaveClass(/text-red|negative|loss/);
    });
  });

  describe("Portfolio Timeframe Selection", () => {
    it("should update data when timeframe is changed", async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Wait for initial load
      await waitFor(() => {
        expect(mockApi.get).toHaveBeenCalledTimes(1);
      });

      // Find and click timeframe selector
      const timeframeSelector = screen.getByRole("button", {
        name: /1D|1 Day/i,
      });
      await user.click(timeframeSelector);

      // Select different timeframe
      const oneWeekOption = screen.getByText("1W");
      await user.click(oneWeekOption);

      // Should trigger new API call
      await waitFor(() => {
        expect(mockApi.get).toHaveBeenCalledWith(
          expect.stringContaining("timeframe=1W"),
          expect.any(Object)
        );
      });
    });

    it("should display loading state during timeframe changes", async () => {
      // Mock delayed API response
      mockApi.get.mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(() => resolve({ data: mockPortfolioData }), 500)
          )
      );

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Change timeframe
      const timeframeSelector = screen.getByRole("button", {
        name: /timeframe|period/i,
      });
      await user.click(timeframeSelector);

      const oneMonthOption = screen.getByText("1M");
      await user.click(oneMonthOption);

      // Should show loading indicator
      expect(
        screen.getByTestId("loading-spinner") || screen.getByText(/loading/i)
      ).toBeInTheDocument();
    });
  });

  describe("Portfolio Metrics and Charts", () => {
    it("should display portfolio summary metrics", async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("$26,550.00")).toBeInTheDocument();
      });

      // Verify all key metrics are displayed
      expect(screen.getByText("Total Value")).toBeInTheDocument();
      expect(screen.getByText("Total Cost")).toBeInTheDocument();
      expect(screen.getByText("Day Change")).toBeInTheDocument();
      expect(screen.getByText("Gain/Loss")).toBeInTheDocument();
    });

    it("should display sector allocation chart", async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("Technology")).toBeInTheDocument();
      });

      // Verify sector allocation data
      expect(screen.getByText("Technology")).toBeInTheDocument();
      expect(screen.getByText("Consumer Discretionary")).toBeInTheDocument();
      expect(screen.getByText("65.98%")).toBeInTheDocument();
      expect(screen.getByText("34.02%")).toBeInTheDocument();
    });

    it("should load and display risk metrics", async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Click risk metrics tab or section
      const riskTab = screen.getByText(/risk|metrics/i);
      await user.click(riskTab);

      await waitFor(() => {
        expect(mockApi.get).toHaveBeenCalledWith(
          expect.stringContaining("/api/portfolio/risk-metrics"),
          expect.any(Object)
        );
      });

      // Verify risk metrics are displayed
      expect(screen.getByText("1.15")).toBeInTheDocument(); // Beta
      expect(screen.getByText("0.85")).toBeInTheDocument(); // Sharpe ratio
    });
  });

  describe("Interactive Features", () => {
    it("should allow sorting holdings by different columns", async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      // Click on gain/loss column header to sort
      const gainLossHeader = screen.getByText("Gain/Loss");
      await user.click(gainLossHeader);

      // Verify sorting (AAPL with positive gain should be first in descending order)
      const rows = screen.getAllByRole("row");
      const firstDataRow = rows[1]; // Skip header row
      expect(within(firstDataRow).getByText("AAPL")).toBeInTheDocument();
    });

    it("should allow filtering holdings by sector", async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
        expect(screen.getByText("TSLA")).toBeInTheDocument();
      });

      // Find and use sector filter
      const sectorFilter = screen.getByLabelText(/filter.*sector/i);
      await user.selectOptions(sectorFilter, "Technology");

      // Should only show Technology stocks
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.queryByText("TSLA")).not.toBeInTheDocument();
    });

    it("should show detailed view when clicking on a holding", async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      // Click on AAPL row
      const aaplSymbol = screen.getByText("AAPL");
      await user.click(aaplSymbol);

      // Should show detailed view or modal
      await waitFor(() => {
        expect(
          screen.getByText(/details|more info|expand/i)
        ).toBeInTheDocument();
      });
    });
  });

  describe("Error Handling", () => {
    it("should handle API errors gracefully", async () => {
      mockApi.get.mockRejectedValueOnce({
        response: { status: 500, data: { error: "Internal server error" } },
      });

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(
          screen.getByText(/error.*loading|failed.*load/i)
        ).toBeInTheDocument();
      });

      // Should provide retry option
      const retryButton = screen.getByRole("button", {
        name: /retry|try again/i,
      });
      expect(retryButton).toBeInTheDocument();
    });

    it("should handle empty portfolio gracefully", async () => {
      const emptyPortfolio = {
        success: true,
        data: {
          holdings: [],
          totalValue: 0,
          totalCost: 0,
          totalGainLoss: 0,
          totalGainLossPercent: 0,
          sectorAllocation: [],
        },
      };

      mockApi.get.mockResolvedValueOnce({ data: emptyPortfolio });

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(
          screen.getByText(/no holdings|empty portfolio|get started/i)
        ).toBeInTheDocument();
      });

      // Should show call-to-action for adding holdings
      expect(
        screen.getByText(/add.*position|start trading/i)
      ).toBeInTheDocument();
    });

    it("should handle missing API keys", async () => {
      const { useApiKeys } = require("../../contexts/ApiKeyProvider");
      vi.mocked(useApiKeys).mockReturnValue({
        apiKeys: {},
        isLoading: false,
        hasRequiredKeys: () => false,
        refreshApiKeys: vi.fn(),
      });

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Should show API key setup message
      await waitFor(() => {
        expect(
          screen.getByText(/api key.*required|setup.*api/i)
        ).toBeInTheDocument();
      });

      // Should provide link to API key setup
      const setupButton = screen.getByRole("button", {
        name: /setup.*api|configure/i,
      });
      expect(setupButton).toBeInTheDocument();
    });
  });

  describe("Real-time Updates", () => {
    it("should update prices when new data is received", async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("$175.25")).toBeInTheDocument(); // Initial AAPL price
      });

      // Simulate price update
      const updatedData = {
        ...mockPortfolioData,
        data: {
          ...mockPortfolioData.data,
          holdings: [
            {
              ...mockPortfolioData.data.holdings[0],
              currentPrice: 180.5,
              currentValue: 18050.0,
              gainLoss: 3000.0,
              gainLossPercent: 19.93,
            },
            mockPortfolioData.data.holdings[1],
          ],
        },
      };

      mockApi.get.mockResolvedValueOnce({ data: updatedData });

      // Trigger refresh (could be automatic or manual)
      const refreshButton = screen.queryByRole("button", {
        name: /refresh|update/i,
      });
      if (refreshButton) {
        await user.click(refreshButton);
      }

      await waitFor(() => {
        expect(screen.getByText("$180.50")).toBeInTheDocument(); // Updated price
        expect(screen.getByText("$3,000.00")).toBeInTheDocument(); // Updated gain/loss
      });
    });

    it("should maintain scroll position during updates", async () => {
      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      // Scroll to bottom of holdings table
      const holdingsTable = screen.getByRole("table");
      holdingsTable.scrollTop = holdingsTable.scrollHeight;

      const scrollPosition = holdingsTable.scrollTop;

      // Trigger data update
      mockApi.get.mockResolvedValueOnce({ data: mockPortfolioData });

      const refreshButton = screen.queryByRole("button", { name: /refresh/i });
      if (refreshButton) {
        await user.click(refreshButton);
      }

      // Should maintain scroll position
      await waitFor(() => {
        expect(holdingsTable.scrollTop).toBe(scrollPosition);
      });
    });
  });

  describe("Responsive Design", () => {
    it("should adapt layout for mobile screens", async () => {
      // Mock mobile viewport
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: 375,
      });

      window.dispatchEvent(new Event("resize"));

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      // Should show mobile-optimized layout
      expect(
        screen.queryByText("Mobile View") ||
          document.querySelector('[data-testid="mobile-layout"]')
      ).toBeTruthy();
    });
  });
});
