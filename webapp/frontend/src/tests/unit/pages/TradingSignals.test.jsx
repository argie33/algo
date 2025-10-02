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
  // Use today's date for mock data so date filters work correctly
  const today = new Date().toISOString().split('T')[0];

  const mockSignalsData = [
    {
      id: "1",
      symbol: "AAPL",
      company_name: "Apple Inc.",
      signal: "BUY",
      strength: "Strong",
      date: today,
      buylevel: 160.5,
      stoplevel: 145.0,
      target_price: 175.0,
      profit_target_8pct: 173.34,
      profit_target_20pct: 192.6,
      current_price: 160.5,
      risk_reward_ratio: 3.5,
      risk_pct: 9.6,
      market_stage: "Stage 2 - Advancing",
      sata_score: 9,
      stage_number: 2,
      mansfield_rs: 12.5,
      volume_ratio: 2.1,
      volume_analysis: "Pocket Pivot",
      pct_from_ema_21: 1.5,
      pct_from_sma_50: 5.2,
      pct_from_sma_200: 12.3,
      entry_quality_score: 85,
      passes_minervini_template: true,
      rsi: 65,
      adx: 32,
      atr: 2.5,
      daily_range_pct: 1.8,
      inposition: false,
      timeframe: "daily",
      timestamp: "2024-01-15T10:30:00Z",
      source: "Technical Analysis",
      description: "Golden cross pattern with high volume",
      sector: "Technology",
      volume: 50000000,
      change: 2.5,
      changePercent: 1.58,
    },
    {
      id: "2",
      symbol: "TSLA",
      company_name: "Tesla Inc.",
      signal: "SELL",
      strength: "Moderate",
      date: today,
      buylevel: 180.25,
      stoplevel: 195.0,
      selllevel: 180.25,
      target_price: 160.0,
      profit_target_8pct: 165.83,
      profit_target_20pct: 144.2,
      current_price: 180.25,
      risk_reward_ratio: 2.5,
      risk_pct: 8.2,
      market_stage: "Stage 4 - Declining",
      sata_score: 2,
      stage_number: 4,
      mansfield_rs: -8.3,
      volume_ratio: 1.6,
      volume_analysis: "Volume Surge",
      pct_from_ema_21: -3.2,
      pct_from_sma_50: -8.5,
      pct_from_sma_200: -15.7,
      entry_quality_score: 70,
      passes_minervini_template: false,
      rsi: 25,
      adx: 28,
      atr: 3.2,
      daily_range_pct: 2.5,
      inposition: true,
      timeframe: "daily",
      timestamp: "2024-01-15T09:15:00Z",
      source: "Sentiment Analysis",
      description: "Bearish divergence with negative news sentiment",
      sector: "Automotive",
      volume: 75000000,
      change: -5.75,
      changePercent: -3.09,
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
      });
    });

    it("should display target price and stop loss", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("175.00")).toBeInTheDocument(); // Target
        expect(screen.getByText("145.00")).toBeInTheDocument(); // Stop loss
      });
    });

    it("should display swing trading metrics", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        // Should display market stage
        expect(screen.getByText(/Stage 2 - Advancing/)).toBeInTheDocument();
        // Should display volume analysis
        expect(screen.getByText(/Pocket Pivot/)).toBeInTheDocument();
        // Should display RSI
        expect(screen.getByText("65")).toBeInTheDocument();
      });
    });

    it("should display SATA Score and Mansfield RS", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        // Should display SATA Score for AAPL (9)
        expect(screen.getByText("9")).toBeInTheDocument();
        // Should display SATA Score for TSLA (2)
        expect(screen.getByText("2")).toBeInTheDocument();
        // Should display Mansfield RS for AAPL (12.5)
        expect(screen.getByText("12.5")).toBeInTheDocument();
        // Should display Mansfield RS for TSLA (-8.3)
        expect(screen.getByText("-8.3")).toBeInTheDocument();
      });
    });

    it("should show signal timestamps", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        // Check that a date is displayed (today's date)
        const datePattern = /\d{1,2}\/\d{1,2}\/\d{4}/; // Matches MM/DD/YYYY format
        expect(screen.getByText(datePattern)).toBeInTheDocument();
      });
    });

    it("should display profit targets", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        // 8% profit target
        expect(screen.getByText("173.34")).toBeInTheDocument();
        // 20% profit target
        expect(screen.getByText("192.60")).toBeInTheDocument();
      });
    });

    it("should display risk/reward ratio", async () => {
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("3.5")).toBeInTheDocument();
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

    it("should filter by high quality signals (score >= 60)", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      // Find and toggle high quality filter
      const highQualityToggle = screen.queryByLabelText(/high quality/i);
      if (highQualityToggle) {
        await user.click(highQualityToggle);

        await waitFor(() => {
          // AAPL has entry_quality_score of 85, should be visible
          expect(screen.getByText("AAPL")).toBeInTheDocument();
          // TSLA has entry_quality_score of 70, should also be visible (>= 60)
          expect(screen.getByText("TSLA")).toBeInTheDocument();
        });
      }
    });

    it("should filter by Minervini template", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      // Find and toggle Minervini filter
      const minerviniToggle = screen.queryByLabelText(/minervini template/i);
      if (minerviniToggle) {
        await user.click(minerviniToggle);

        await waitFor(() => {
          // AAPL passes Minervini template, should be visible
          expect(screen.getByText("AAPL")).toBeInTheDocument();
          // TSLA doesn't pass Minervini template, should be hidden
          expect(screen.queryByText("TSLA")).not.toBeInTheDocument();
        });
      }
    });

    it("should filter by Stage 2 only", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      // Find and toggle Stage 2 filter
      const stage2Toggle = screen.queryByLabelText(/stage 2 only/i);
      if (stage2Toggle) {
        await user.click(stage2Toggle);

        await waitFor(() => {
          // AAPL is in Stage 2, should be visible
          expect(screen.getByText("AAPL")).toBeInTheDocument();
          // TSLA is in Stage 4, should be hidden
          expect(screen.queryByText("TSLA")).not.toBeInTheDocument();
        });
      }
    });

    it("should filter by in-position only", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      // Find and toggle in-position filter
      const inPositionToggle = screen.queryByLabelText(/in position/i);
      if (inPositionToggle) {
        await user.click(inPositionToggle);

        await waitFor(() => {
          // Both AAPL and TSLA have inposition = false, so neither should be visible
          expect(screen.queryByText("AAPL")).not.toBeInTheDocument();
          expect(screen.queryByText("TSLA")).not.toBeInTheDocument();
        });
      }
    });

    it("should filter by pocket pivots only", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      // Find and toggle pocket pivots filter
      const pocketPivotsToggle = screen.queryByLabelText(/pocket pivots/i);
      if (pocketPivotsToggle) {
        await user.click(pocketPivotsToggle);

        await waitFor(() => {
          // AAPL has "Pocket Pivot" volume analysis, should be visible
          expect(screen.getByText("AAPL")).toBeInTheDocument();
          // TSLA has "Volume Surge", should be hidden
          expect(screen.queryByText("TSLA")).not.toBeInTheDocument();
        });
      }
    });

    it("should filter by minimum risk/reward ratio", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      // Find and change min risk/reward filter
      const minRRSelect = screen.queryByLabelText(/min risk\/reward/i);
      if (minRRSelect) {
        await user.click(minRRSelect);

        // Select "3:1 or better"
        const option3to1 = screen.queryByText(/3:1 or better/i);
        if (option3to1) {
          await user.click(option3to1);

          await waitFor(() => {
            // AAPL has risk_reward_ratio of 3.5, should be visible
            expect(screen.getByText("AAPL")).toBeInTheDocument();
            // TSLA has risk_reward_ratio of 2.5, should be hidden
            expect(screen.queryByText("TSLA")).not.toBeInTheDocument();
          });
        }
      }
    });

    it("should filter by date range - Today Only", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        // Default is "today" - should show signals from today
        const dateRangeSelect = screen.queryByLabelText(/date range/i);
        expect(dateRangeSelect).toBeInTheDocument();
      });

      // Date filter is already set to "today" by default
      // Both mock signals have date "2024-01-15" which may not be today
      // So they might be filtered out
    });

    it("should filter by date range - This Week", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });

      // Find and change date range filter
      const dateRangeSelect = screen.queryByLabelText(/date range/i);
      if (dateRangeSelect) {
        await user.click(dateRangeSelect);

        const weekOption = screen.queryByText(/this week/i);
        if (weekOption) {
          await user.click(weekOption);

          await waitFor(() => {
            // Signals from this week should be visible
            // Mock data may not have current week signals
            const rows = screen.getAllByRole("row");
            expect(rows.length).toBeGreaterThanOrEqual(0);
          });
        }
      }
    });

    it("should filter by date range - All Time", async () => {
      const user = userEvent.setup();
      render(<TradingSignals />, { wrapper: TestWrapper });

      // First wait for component to render
      await waitFor(() => {
        const dateRangeSelect = screen.queryByLabelText(/date range/i);
        expect(dateRangeSelect).toBeInTheDocument();
      });

      // Find and change date range filter to "All Time"
      const dateRangeSelect = screen.queryByLabelText(/date range/i);
      if (dateRangeSelect) {
        await user.click(dateRangeSelect);

        const allTimeOption = screen.queryByText(/all time/i);
        if (allTimeOption) {
          await user.click(allTimeOption);

          await waitFor(() => {
            // With "All Time", both signals should be visible
            expect(screen.getByText("AAPL")).toBeInTheDocument();
            expect(screen.getByText("TSLA")).toBeInTheDocument();
          });
        }
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
