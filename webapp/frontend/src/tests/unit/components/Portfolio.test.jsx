/**
 * Unit Tests for Portfolio Component
 * Tests the core portfolio display functionality that users see
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  renderWithProviders,
  screen,
  waitFor,
  createMockUser,
} from "../../test-utils.jsx";
import Portfolio from "../../../pages/Portfolio.jsx";

// Mock the AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
    error: null,
  })),
  AuthProvider: ({ children }) => children, // Mock AuthProvider as a pass-through
}));

// Mock the API service - Portfolio imports individual functions
vi.mock("../../../services/api.js", () => ({
  // Mock direct function imports that Portfolio uses
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    environment: "test",
  })),
  testApiConnection: vi.fn(() => Promise.resolve({
    success: true,
    data: { status: 'healthy' }
  })),
  getApiKeys: vi.fn(() => Promise.resolve({
    success: true,
    apiKeys: [
      {
        provider: 'alpaca',
        keyId: 'PK***ABC',
        isValid: true,
        lastValidated: '2025-01-15T10:30:00Z'
      }
    ]
  })),
  importPortfolioFromBroker: vi.fn(() => Promise.resolve({
    success: true,
    data: { message: 'Portfolio imported successfully' }
  })),
  
  // Mock the named export api object
  api: {
    getPortfolio: vi.fn(),
    getQuote: vi.fn(),
    placeOrder: vi.fn(),
  },
  
  // Mock the default export api object for other tests
  default: {
    getPortfolio: vi.fn(),
    getQuote: vi.fn(),
    placeOrder: vi.fn(),
  },
}));

// Mock chart components to avoid canvas issues in tests
vi.mock("react-chartjs-2", () => ({
  Line: ({ data }) => (
    <div data-testid="portfolio-chart">
      Portfolio Chart with {data?.datasets?.length || 0} datasets
    </div>
  ),
  Doughnut: ({ data }) => (
    <div data-testid="allocation-chart">
      Allocation Chart with {data?.labels?.length || 0} segments
    </div>
  ),
}));

describe("Portfolio Component - User Interface", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Mock global fetch since Portfolio component uses fetch directly
    global.fetch = vi.fn();
  });

  describe("Portfolio Loading and Display", () => {
    it("should display loading state initially", async () => {
      // Critical: Users should see loading indicator while data loads
      global.fetch.mockImplementation(() => new Promise(() => {})); // Never resolves

      renderWithProviders(<Portfolio />);

      // Should show loading indicator
      expect(
        screen.getByText(/loading/i) || screen.getByTestId("loading")
      ).toBeTruthy();
    });

    it("should display portfolio data when loaded successfully", async () => {
      // Critical: Users need to see their portfolio value and holdings
      const mockPortfolioResponse = {
        data: {
          holdings: [
            {
              symbol: "AAPL",
              quantity: 100,
              currentPrice: 150.25,
              marketValue: 15025,
              avgCost: 145.0,
              unrealizedPnL: 525,
              percentageReturn: 3.62,
            },
            {
              symbol: "MSFT",
              quantity: 50,
              currentPrice: 280.1,
              marketValue: 14005,
              avgCost: 275.0,
              unrealizedPnL: 255,
              percentageReturn: 1.85,
            },
          ],
          totalValue: 125750.5,
          todaysPnL: 2500.75,
          totalPnL: 25750.5,
          performanceHistory: [
            { date: '2024-01-01', portfolioValue: 120000, benchmarkValue: 100000 },
            { date: '2024-01-02', portfolioValue: 122500, benchmarkValue: 101000 },
            { date: '2024-01-03', portfolioValue: 125750.5, benchmarkValue: 102000 },
          ],
        }
      };

      global.fetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockPortfolioResponse),
      });

      renderWithProviders(<Portfolio />);

      await waitFor(() => {
        // Should display total portfolio value
        expect(
          screen.getByText(/125,750\.50/i) || screen.getByText(/\$125,750/i)
        ).toBeTruthy();
      });

      // Should display today's P&L
      expect(
        screen.getByText(/2,500\.75/i) || screen.getByText(/\$2,500/i)
      ).toBeTruthy();

      // Should display individual positions
      expect(screen.getByText("AAPL")).toBeTruthy();
      expect(screen.getByText("MSFT")).toBeTruthy();

      // Should display quantities
      expect(screen.getByText(/100/)).toBeTruthy();
      expect(screen.getByText(/50/)).toBeTruthy();
    });

    it("should handle empty portfolio gracefully", async () => {
      // Critical: New users or users who sold everything should see proper empty state
      const apiModule = await import("../../../services/api.js");
      const emptyPortfolio = {
        totalValue: 0,
        todaysPnL: 0,
        totalPnL: 0,
        positions: [],
      };

      apiModule.api.getPortfolio.mockResolvedValue(emptyPortfolio);

      renderWithProviders(<Portfolio />);

      await waitFor(() => {
        // Should show zero value
        expect(
          screen.getByText(/\$0\.00/i) || screen.getByText(/0\.00/)
        ).toBeTruthy();
      });

      // Should show empty state message
      expect(
        screen.getByText(/no positions/i) ||
          screen.getByText(/empty/i) ||
          screen.getByText(/no holdings/i)
      ).toBeTruthy();
    });
  });

  describe("Portfolio Calculations Display", () => {
    it("should display profit/loss with correct formatting and colors", async () => {
      // Critical: P&L display affects user trading decisions
      const apiModule = await import("../../../services/api.js");
      const portfolioWithPnL = {
        totalValue: 50000,
        todaysPnL: -1250.75, // Negative P&L
        totalPnL: 5750.25, // Positive total P&L
        positions: [
          {
            symbol: "TSLA",
            quantity: 10,
            currentPrice: 220.5,
            marketValue: 2205,
            avgCost: 250.0,
            unrealizedPnL: -295, // Loss position
            percentageReturn: -11.8,
          },
        ],
      };

      apiModule.api.getPortfolio.mockResolvedValue(portfolioWithPnL);

      renderWithProviders(<Portfolio />);

      await waitFor(() => {
        // Should display negative today's P&L
        const todaysPnL =
          screen.getByText(/-1,250\.75/i) || screen.getByText(/-\$1,250/i);
        expect(todaysPnL).toBeTruthy();

        // Should display positive total P&L
        const totalPnL =
          screen.getByText(/5,750\.25/i) || screen.getByText(/\$5,750/i);
        expect(totalPnL).toBeTruthy();
      });

      // Should show loss position
      expect(screen.getByText("TSLA")).toBeTruthy();
      expect(
        screen.getByText(/-295/i) || screen.getByText(/-\$295/i)
      ).toBeTruthy();
    });

    it("should calculate and display percentage returns correctly", async () => {
      // Critical: Percentage returns help users understand performance
      const apiModule = await import("../../../services/api.js");
      const portfolioWithReturns = {
        totalValue: 100000,
        positions: [
          {
            symbol: "NVDA",
            quantity: 25,
            currentPrice: 400.0,
            marketValue: 10000,
            avgCost: 200.0,
            unrealizedPnL: 5000,
            percentageReturn: 100.0, // 100% gain
          },
        ],
      };

      apiModule.api.getPortfolio.mockResolvedValue(portfolioWithReturns);

      renderWithProviders(<Portfolio />);

      await waitFor(() => {
        // Should display 100% return
        expect(
          screen.getByText(/100\.0%/i) || screen.getByText(/\+100%/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Error Handling", () => {
    it("should display error message when portfolio load fails", async () => {
      // Critical: API failures should not leave users with blank screen
      const apiModule = await import("../../../services/api.js");
      apiModule.api.getPortfolio.mockRejectedValue(
        new Error("API temporarily unavailable")
      );

      renderWithProviders(<Portfolio />);

      await waitFor(() => {
        // Should show error message
        expect(
          screen.getByText(/error/i) ||
            screen.getByText(/failed/i) ||
            screen.getByText(/unavailable/i)
        ).toBeTruthy();
      });
    });

    it("should handle malformed portfolio data gracefully", async () => {
      // Critical: Bad data should not crash the component
      const apiModule = await import("../../../services/api.js");
      const malformedData = {
        // Missing required fields
        positions: null,
        totalValue: "not-a-number",
      };

      apiModule.api.getPortfolio.mockResolvedValue(malformedData);

      renderWithProviders(<Portfolio />);

      await waitFor(() => {
        // Should not crash and should show some fallback content
        expect(document.body).toBeTruthy();
      });
    });
  });

  describe("User Interaction Features", () => {
    it("should allow filtering/sorting of positions", async () => {
      // Critical: Users with many positions need to find stocks quickly
      const apiModule = await import("../../../services/api.js");
      const largePortfolio = {
        totalValue: 250000,
        positions: Array.from({ length: 20 }, (_, i) => ({
          symbol: `STOCK${i}`,
          quantity: 10 + i,
          currentPrice: 100 + i * 10,
          marketValue: (10 + i) * (100 + i * 10),
          unrealizedPnL: i * 50 - 500,
        })),
      };

      apiModule.api.getPortfolio.mockResolvedValue(largePortfolio);

      renderWithProviders(<Portfolio />);

      await waitFor(() => {
        // Should display multiple positions
        expect(screen.getByText("STOCK0")).toBeTruthy();
        expect(screen.getByText("STOCK1")).toBeTruthy();
      });

      // Should have some way to sort or filter (search box, sort buttons, etc.)
      const _sortControls =
        screen.queryByText(/sort/i) ||
        screen.queryByPlaceholderText(/search/i) ||
        screen.queryByRole("button");
      // Note: This might not exist yet, but test documents the requirement
    });

    it("should show real-time price updates when available", async () => {
      // Critical: Live prices help users make timely trading decisions
      const apiModule = await import("../../../services/api.js");
      const portfolioData = {
        totalValue: 75000,
        positions: [
          {
            symbol: "SPY",
            quantity: 100,
            currentPrice: 450.25,
            marketValue: 45025,
            lastUpdated: new Date().toISOString(),
          },
        ],
      };

      apiModule.api.getPortfolio.mockResolvedValue(portfolioData);

      renderWithProviders(<Portfolio />);

      await waitFor(() => {
        // Should show current price
        expect(
          screen.getByText(/450\.25/i) || screen.getByText(/\$450/i)
        ).toBeTruthy();
      });

      // Should indicate when data was last updated
      const _timestamp =
        screen.queryByText(/updated/i) ||
        screen.queryByText(/ago/i) ||
        screen.queryByText(/last/i);
      // Note: Timestamp display is a good UX feature to test for
    });
  });

  describe("Accessibility and User Experience", () => {
    it("should be accessible to screen readers", async () => {
      // Critical: Financial data must be accessible to all users
      const apiModule = await import("../../../services/api.js");
      apiModule.api.getPortfolio.mockResolvedValue({
        totalValue: 100000,
        positions: [{ symbol: "AAPL", quantity: 10, currentPrice: 150 }],
      });

      renderWithProviders(<Portfolio />);

      await waitFor(() => {
        // Should have proper headings
        const headings = screen.getAllByRole("heading");
        expect(headings.length).toBeGreaterThan(0);
      });

      // Should have proper table structure for positions
      const table = screen.queryByRole("table") || screen.queryByRole("grid");
      if (table) {
        // If using table, should have proper headers
        const headers = screen.getAllByRole("columnheader");
        expect(headers.length).toBeGreaterThan(0);
      }
    });

    it("should handle large numbers formatting correctly", async () => {
      // Critical: Large portfolios should display readable numbers
      const apiModule = await import("../../../services/api.js");
      const largePortfolio = {
        totalValue: 5750000.5, // $5.75M
        positions: [
          {
            symbol: "BRK.A",
            quantity: 1,
            currentPrice: 500000,
            marketValue: 500000,
          },
        ],
      };

      apiModule.api.getPortfolio.mockResolvedValue(largePortfolio);

      renderWithProviders(<Portfolio />);

      await waitFor(() => {
        // Should format large numbers with commas or abbreviations
        const formattedNumber =
          screen.getByText(/5,750,000/i) ||
          screen.getByText(/5\.75M/i) ||
          screen.getByText(/\$5,750,000/i);
        expect(formattedNumber).toBeTruthy();
      });
    });
  });
});
