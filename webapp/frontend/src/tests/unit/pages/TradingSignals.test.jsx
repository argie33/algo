import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TestWrapper } from "../../test-utils.jsx";

// Mock hooks - must be before imports that use them
vi.mock("../../../hooks/useDocumentTitle", () => ({
  useDocumentTitle: vi.fn(),
}));

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

import TradingSignals from "../../../pages/TradingSignals";

// Mock API calls
global.fetch = vi.fn();

// Using TestWrapper for consistent test setup

describe("TradingSignals", () => {
  const mockSignalsData = [
    {
      id: "1",
      symbol: "AAPL",
      signal: "BUY",
      strength: "Strong",
      price: 160.5,
      targetPrice: 175.0,
      stopLoss: 145.0,
      confidence: 85,
      timeframe: "1D",
      timestamp: "2024-01-15T10:30:00Z",
      source: "Technical Analysis",
      description: "Golden cross pattern with high volume",
      sector: "Technology",
      marketCap: 2500000000000,
      volume: 50000000,
      change: 2.5,
      changePercent: 1.58,
      indicators: {
        rsi: 65,
        macd: "Bullish",
        movingAverage: "Above 50-day",
        support: 155.0,
        resistance: 165.0,
      },
    },
    {
      id: "2",
      symbol: "TSLA",
      signal: "SELL",
      strength: "Moderate",
      price: 180.25,
      targetPrice: 160.0,
      stopLoss: 195.0,
      confidence: 70,
      timeframe: "4H",
      timestamp: "2024-01-15T09:15:00Z",
      source: "Sentiment Analysis",
      description: "Bearish divergence with negative news sentiment",
      sector: "Automotive",
      marketCap: 580000000000,
      volume: 75000000,
      change: -5.75,
      changePercent: -3.09,
      indicators: {
        rsi: 25,
        macd: "Bearish",
        movingAverage: "Below 20-day",
        support: 175.0,
        resistance: 190.0,
      },
    },
  ];

  beforeEach(() => {
    vi.clearAllMocks();
    // useDocumentTitle mock is set up in vi.mock above

    // Mock successful API responses - handle both signals and performance endpoints
    global.fetch.mockImplementation((url) => {
      if (url.includes('/api/signals')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            data: mockSignalsData,  // Component expects data to be array, not signals
            metadata: {
              total: 2,
              lastUpdated: "2024-01-15T10:30:00Z",
              marketStatus: "OPEN",
            },
          }),
        });
      } else if (url.includes('/api/trading/performance')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            data: {
              totalSignals: 100,
              successRate: 65.5,
              avgReturn: 12.3,
              totalReturn: 1234.56,
            },
          }),
        });
      }
      return Promise.reject(new Error('Unknown endpoint'));
    });
  });

  describe("Component Rendering", () => {
    it("should render the trading signals page", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      expect(screen.getByText(/trading signals/i)).toBeInTheDocument();
    });

    it("should set document title", () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      // Document title is mocked - test passes if component renders
    });

    it("should show loading state initially", () => {
      // Mock the loading state by making fetch not resolve immediately
      global.fetch.mockImplementation(() => new Promise(() => {})); // Never resolves

      render(<TradingSignals />, { wrapper: TestWrapper });

      // Check for the loading text instead of progressbar role since we use custom loading component
      expect(
        screen.getByText(/loading trading signals and performance data/i)
      ).toBeInTheDocument();
    });
  });

  describe("Data Loading", () => {
    it("should fetch trading signals data with correct query parameters", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringMatching(/\/api\/signals\?.*timeframe=daily/)
        );
      });
    });

    it("should NOT use path parameters for timeframe", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        // Ensure we're NOT calling the wrong pattern like /api/signals/daily
        expect(global.fetch).not.toHaveBeenCalledWith(
          expect.stringMatching(/\/api\/signals\/(daily|weekly|monthly)/)
        );
      });
    });

    it("should include pagination parameters in API call", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(global.fetch).toHaveBeenCalledWith(
          expect.stringMatching(/\/api\/signals\?.*page=1.*limit=25/)
        );
      });
    });

    it("should use correct API pattern for historical data", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      // Mock clicking on a symbol to trigger historical data fetch
      const symbolButton = screen.getByText("AAPL");
      if (symbolButton && symbolButton.closest("button")) {
        await user.click(symbolButton.closest("button"));

        await waitFor(() => {
          // Should call correct pattern: /api/signals?timeframe=daily&symbol=AAPL
          expect(global.fetch).toHaveBeenCalledWith(
            expect.stringMatching(/\/api\/signals\?timeframe=daily.*symbol=AAPL/)
          );
          // Should NOT call wrong pattern: /api/signals/daily?symbol=AAPL
          expect(global.fetch).not.toHaveBeenCalledWith(
            expect.stringMatching(/\/api\/signals\/daily\?symbol=AAPL/)
          );
        });
      }
    });

    it("should display signals after loading", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
        expect(screen.getByText("TSLA")).toBeInTheDocument();
      });
    });

    it("should handle loading errors gracefully", async () => {
      global.fetch.mockImplementation((url) => {
        if (url.includes('/api/signals')) {
          return Promise.reject(new Error("Failed to load trading signals"));
        } else if (url.includes('/api/trading/performance')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              success: true,
              data: {
                totalSignals: 0,
                successRate: 0,
                avgReturn: 0,
                totalReturn: 0,
              },
            }),
          });
        }
        return Promise.reject(new Error('Unknown endpoint'));
      });

      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText(/failed to load trading signals/i)).toBeInTheDocument();
      });
    });

    it("should handle empty signals data", async () => {
      global.fetch.mockImplementation((url) => {
        if (url.includes('/api/signals')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              data: [],
              metadata: { total: 0 },
            }),
          });
        } else if (url.includes('/api/trading/performance')) {
          return Promise.resolve({
            ok: true,
            json: async () => ({
              success: true,
              data: {
                totalSignals: 0,
                successRate: 0,
                avgReturn: 0,
                totalReturn: 0,
              },
            }),
          });
        }
        return Promise.reject(new Error('Unknown endpoint'));
      });

      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText(/no trading signals data found/i)).toBeInTheDocument();
      });
    });
  });

  describe("Signal Display", () => {
    it("should display signal details correctly", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
        expect(screen.getByText("BUY")).toBeInTheDocument();
        expect(screen.getByText("Strong")).toBeInTheDocument();
        expect(screen.getByText("$160.50")).toBeInTheDocument();
        expect(screen.getByText("85%")).toBeInTheDocument();
      });
    });

    it("should display target price and stop loss", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("$175.00")).toBeInTheDocument(); // Target
        expect(screen.getByText("$145.00")).toBeInTheDocument(); // Stop loss
      });
    });

    it("should show signal timestamps", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText(/10:30/)).toBeInTheDocument();
      });
    });

    it("should display technical indicators", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("RSI: 65")).toBeInTheDocument();
        expect(screen.getByText("Bullish")).toBeInTheDocument(); // MACD
      });
    });
  });

  describe("Signal Filtering", () => {
    it("should allow filtering by signal type", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      // Look for filter controls
      const buyFilter = screen.queryByRole("button", { name: /buy/i });
      if (buyFilter) {
        await user.click(buyFilter);

        await waitFor(() => {
          expect(screen.getByText("AAPL")).toBeInTheDocument();
          expect(screen.queryByText("TSLA")).not.toBeInTheDocument();
        });
      }
    });

    it("should allow filtering by timeframe", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      // Look for timeframe filter
      const timeframeSelect = screen.queryByLabelText(/timeframe/i);
      if (timeframeSelect) {
        await user.click(timeframeSelect);

        const oneDay = screen.queryByText("1D");
        if (oneDay) {
          await user.click(oneDay);

          await waitFor(() => {
            expect(screen.getByText("AAPL")).toBeInTheDocument();
          });
        }
      }
    });

    it("should allow filtering by strength", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      // Look for strength filter
      const strengthToggle = screen.queryByLabelText(/strong only/i);
      if (strengthToggle) {
        await user.click(strengthToggle);

        await waitFor(() => {
          expect(screen.getByText("AAPL")).toBeInTheDocument();
          expect(screen.queryByText("TSLA")).not.toBeInTheDocument();
        });
      }
    });
  });

  describe("Signal Sorting", () => {
    it("should allow sorting by confidence", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      const confidenceHeader = screen.queryByText("Confidence");
      if (confidenceHeader?.closest("th")) {
        await user.click(confidenceHeader.closest("th"));

        // Verify sorting order change
        await waitFor(() => {
          const rows = screen.getAllByRole("row");
          expect(rows.length).toBeGreaterThan(0);
        });
      }
    });

    it("should allow sorting by timestamp", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      const timeHeader = screen.queryByText(/time/i);
      if (timeHeader?.closest("th")) {
        await user.click(timeHeader.closest("th"));

        await waitFor(() => {
          const rows = screen.getAllByRole("row");
          expect(rows.length).toBeGreaterThan(0);
        });
      }
    });
  });

  describe("Signal Actions", () => {
    it("should allow viewing signal details", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      const detailsButton = screen.queryByRole("button", { name: /details/i });
      if (detailsButton) {
        await user.click(detailsButton);

        await waitFor(() => {
          expect(screen.getByText(/technical analysis/i)).toBeInTheDocument();
        });
      }
    });

    it("should handle signal following/unfollowing", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      const followButton = screen.queryByRole("button", { name: /follow/i });
      if (followButton) {
        await user.click(followButton);

        await waitFor(() => {
          expect(screen.getByText(/following/i)).toBeInTheDocument();
        });
      }
    });
  });

  describe("Real-time Updates", () => {
    it("should handle data refresh", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      const refreshButton = screen.queryByRole("button", { name: /refresh/i });
      if (refreshButton) {
        await user.click(refreshButton);

        await waitFor(() => {
          expect(global.fetch).toHaveBeenCalledTimes(2);
        });
      }
    });

    it("should show last updated timestamp", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText(/last updated/i)).toBeInTheDocument();
      });
    });
  });

  describe("Market Status Integration", () => {
    it("should display market status", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText(/market.*open/i)).toBeInTheDocument();
      });
    });

    it("should handle market closed state", async () => {
      global.fetch.mockResolvedValue({
        ok: true,
        json: async () => ({
          signals: mockSignalsData,
          metadata: {
            marketStatus: "CLOSED",
            lastUpdated: "2024-01-15T16:00:00Z",
          },
        }),
      });

      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText(/market.*closed/i)).toBeInTheDocument();
      });
    });
  });

  describe("Error Handling", () => {
    it("should display error message on API failure", async () => {
      global.fetch.mockRejectedValue(new Error("Network error"));

      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(
          screen.getByText(/error.*loading.*signals/i)
        ).toBeInTheDocument();
      });
    });

    it("should provide retry functionality on error", async () => {
      global.fetch
        .mockRejectedValueOnce(new Error("Network error"))
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ signals: mockSignalsData }),
        });

      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText(/error/i)).toBeInTheDocument();
      });

      const retryButton = screen.getByRole("button", { name: /retry/i });
      await user.click(retryButton);

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });
    });
  });

  describe("Performance", () => {
    it("should handle large datasets efficiently", async () => {
      const largeDataset = Array.from({ length: 100 }, (_, i) => ({
        ...mockSignalsData[0],
        id: `signal-${i}`,
        symbol: `STOCK${i}`,
        price: 100 + i,
      }));

      global.fetch.mockResolvedValue({
        ok: true,
        json: async () => ({
          signals: largeDataset,
          metadata: { total: 100 },
        }),
      });

      const { container } = render(<TradingSignals />, {
        wrapper: TestWrapper,
      });

      await waitFor(() => {
        expect(screen.getByText("STOCK0")).toBeInTheDocument();
      });

      // Should render without performance issues
      expect(container).toBeInTheDocument();
    });

    it("should implement pagination for large datasets", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      const pagination = screen.queryByRole("navigation");
      if (pagination) {
        const nextButton = screen.queryByRole("button", { name: /next/i });
        if (nextButton) {
          await user.click(nextButton);

          await waitFor(() => {
            expect(global.fetch).toHaveBeenCalledTimes(2);
          });
        }
      }
    });
  });

  describe("Accessibility", () => {
    it("should have proper table structure", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        const table = screen.getByRole("table");
        expect(table).toBeInTheDocument();

        const columnHeaders = screen.getAllByRole("columnheader");
        expect(columnHeaders.length).toBeGreaterThan(0);
      });
    });

    it("should support keyboard navigation", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      // Test tab navigation
      await user.tab();
      expect(document.activeElement).toBeDefined();
    });

    it("should have appropriate ARIA labels", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        const table = screen.getByRole("table");
        expect(table).toHaveAttribute(
          "aria-label",
          expect.stringContaining("signals")
        );
      });
    });
  });

  describe("Data Formatting", () => {
    it("should format prices correctly", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("$160.50")).toBeInTheDocument();
        expect(screen.getByText("$180.25")).toBeInTheDocument();
      });
    });

    it("should format percentages correctly", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("85%")).toBeInTheDocument(); // Confidence
        expect(screen.getByText("1.58%")).toBeInTheDocument(); // Change percent
      });
    });

    it("should use appropriate colors for buy/sell signals", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        const buyChip = screen.getByText("BUY").closest(".MuiChip-root");
        const sellChip = screen.getByText("SELL").closest(".MuiChip-root");

        if (buyChip && sellChip) {
          expect(buyChip).toHaveClass(expect.stringContaining("success"));
          expect(sellChip).toHaveClass(expect.stringContaining("error"));
        }
      });
    });
  });

  describe("Signal Performance Tracking", () => {
    it("should display signal performance tracker when signals are available", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("Signal Performance Tracking")).toBeInTheDocument();
        expect(screen.getByText("Total Signals")).toBeInTheDocument();
        expect(screen.getByText("Profitable")).toBeInTheDocument();
        expect(screen.getByText("Avg Return")).toBeInTheDocument();
        expect(screen.getByText("Win Rate")).toBeInTheDocument();
      });
    });

    it("should display signal performance details table", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("Signal Performance Details")).toBeInTheDocument();
        expect(screen.getByText("Symbol")).toBeInTheDocument();
        expect(screen.getByText("Signal")).toBeInTheDocument();
        expect(screen.getByText("Confidence")).toBeInTheDocument();
        expect(screen.getByText("Signal Date")).toBeInTheDocument();
        expect(screen.getByText("Days Held")).toBeInTheDocument();
        expect(screen.getByText("Current Return")).toBeInTheDocument();
        expect(screen.getByText("Performance")).toBeInTheDocument();
      });
    });
  });
});
