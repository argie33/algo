import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import RealTimePriceWidget from "../../../components/RealTimePriceWidget";

vi.mock("../../../services/dataCache", () => ({
  default: {
    get: vi.fn(),
    isMarketHours: vi.fn(() => true),
  },
  __esModule: true,
}));

vi.mock("../../../utils/formatters", () => ({
  formatCurrency: vi.fn((value) => value != null ? `$${value.toFixed(2)}` : 'N/A'),
  formatPercentage: vi.fn((value) => value != null ? `${value.toFixed(2)}%` : 'N/A'),
}));

const mockPriceData = {
  symbol: "AAPL",
  price: 150.25,
  previousClose: 148.5,
  dayChange: 1.75,
  dayChangePercent: 1.18,
  volume: 45000000,
  marketCap: 2400000000000,
  dayHigh: 152.10,
  dayLow: 147.80,
  lastUpdated: new Date().toISOString(),
};

const { default: mockDataCache } = await import("../../../services/dataCache");

describe("RealTimePriceWidget", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockDataCache.get.mockResolvedValue(mockPriceData);
  });

  describe("Rendering", () => {
    test("renders without crashing", async () => {
      render(<RealTimePriceWidget symbol="AAPL" />);

      await waitFor(() => {
        expect(screen.getByText("$150.25")).toBeInTheDocument();
      });
    });

    test("displays loading skeleton initially", () => {
      mockDataCache.get.mockImplementation(() => new Promise(() => {})); // Never resolves
      render(<RealTimePriceWidget symbol="AAPL" />);

      expect(
        screen.getByTestId("loading-skeleton") ||
          screen.getByRole("progressbar")
      ).toBeInTheDocument();
    });

    test("displays price data when loaded", async () => {
      render(<RealTimePriceWidget symbol="AAPL" />);

      await waitFor(() => {
        expect(screen.getByText("$150.25")).toBeInTheDocument();
        expect(screen.getByText(/1.18%/)).toBeInTheDocument();
      });
    });

    test("shows trending up icon for positive change", async () => {
      render(<RealTimePriceWidget symbol="AAPL" />);

      await waitFor(() => {
        expect(screen.getByTestId("trendingup-icon")).toBeInTheDocument();
      });
    });

    test("shows trending down icon for negative change", async () => {
      const negativeData = {
        ...mockPriceData,
        dayChange: -2.5,
        dayChangePercent: -1.68,
      };

      mockDataCache.get.mockResolvedValue(negativeData);
      render(<RealTimePriceWidget symbol="AAPL" />);

      await waitFor(() => {
        expect(screen.getByTestId("trendingdown-icon")).toBeInTheDocument();
      });
    });

    test("shows flat icon for zero change", async () => {
      const flatData = {
        ...mockPriceData,
        dayChange: 0,
        dayChangePercent: 0,
      };

      mockDataCache.get.mockResolvedValue(flatData);
      render(<RealTimePriceWidget symbol="AAPL" />);

      await waitFor(() => {
        expect(screen.getByTestId("trendingflat-icon")).toBeInTheDocument();
      });
    });
  });

  describe("Compact Mode", () => {
    test("renders in compact mode", async () => {
      render(<RealTimePriceWidget symbol="AAPL" compact={true} />);

      await waitFor(() => {
        expect(screen.getByText("$150.25")).toBeInTheDocument();
      });
    });

    test("shows essential information in compact mode", async () => {
      render(<RealTimePriceWidget symbol="AAPL" compact={true} />);

      await waitFor(() => {
        expect(screen.getByText("$150.25")).toBeInTheDocument();
        expect(screen.getByText(/1.18%/)).toBeInTheDocument();
      });
    });
  });

  describe("Data Updates", () => {
    test("fetches data on mount", async () => {
      render(<RealTimePriceWidget symbol="AAPL" />);

      await waitFor(() => {
        expect(mockDataCache.get).toHaveBeenCalledWith(
          "/api/stocks/quote/AAPL",
          {},
          expect.any(Object)
        );
      });
    });

    test("updates data periodically", async () => {
      vi.useFakeTimers();
      render(<RealTimePriceWidget symbol="AAPL" />);

      await waitFor(() => {
        expect(mockDataCache.get).toHaveBeenCalledTimes(1);
      });

      // Fast forward 30 seconds (typical refresh interval)
      vi.advanceTimersByTime(30000);

      await waitFor(() => {
        expect(mockDataCache.get).toHaveBeenCalledTimes(2);
      });

      vi.useRealTimers();
    });

    test("clears interval on unmount", async () => {
      vi.useFakeTimers();
      const { unmount } = render(<RealTimePriceWidget symbol="AAPL" />);

      await waitFor(() => {
        expect(mockDataCache.get).toHaveBeenCalled();
      });

      unmount();

      // Advance timers and verify no additional calls
      vi.advanceTimersByTime(60000);
      expect(mockDataCache.get).toHaveBeenCalledTimes(1);

      vi.useRealTimers();
    });
  });

  describe("Error Handling", () => {
    test("displays error message when fetch fails", async () => {
      const consoleErrorSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      mockDataCache.get.mockRejectedValue(new Error("API Error"));

      render(<RealTimePriceWidget symbol="AAPL" />);

      await waitFor(() => {
        expect(
          screen.getByText(/Unable to load price data/i) ||
            screen.getByText(/error/i) ||
            screen.getByRole("alert")
        ).toBeInTheDocument();
      });

      consoleErrorSpy.mockRestore();
    });

    test("handles invalid symbol gracefully", async () => {
      mockDataCache.get.mockRejectedValue(new Error("Symbol not found"));

      render(<RealTimePriceWidget symbol="INVALID" />);

      await waitFor(() => {
        expect(
          screen.getByText(/error/i) || screen.getByRole("alert")
        ).toBeInTheDocument();
      });
    });
  });

  describe("Data Staleness", () => {
    test("indicates stale data", async () => {
      const staleData = {
        ...mockPriceData,
        lastUpdated: new Date(Date.now() - 600000).toISOString(), // 10 minutes ago
      };

      mockDataCache.get.mockResolvedValue(staleData);
      render(<RealTimePriceWidget symbol="AAPL" />);

      await waitFor(() => {
        expect(
          screen.getByText(/stale/i) || screen.getByText(/delayed/i)
        ).toBeInTheDocument();
      });
    });

    test("shows fresh data indicator", async () => {
      render(<RealTimePriceWidget symbol="AAPL" />);

      await waitFor(() => {
        expect(screen.getByText("$150.25")).toBeInTheDocument();
        // Fresh data shouldn't show stale indicator
        expect(screen.queryByText(/stale/i)).not.toBeInTheDocument();
      });
    });
  });

  describe("Volume and Market Cap", () => {
    test("displays volume information", async () => {
      render(<RealTimePriceWidget symbol="AAPL" />);

      await waitFor(() => {
        // Look for volume display - exact format may vary
        expect(screen.getByText(/45,000,000|45M|Volume/i)).toBeInTheDocument();
      });
    });

    test("displays market cap information", async () => {
      render(<RealTimePriceWidget symbol="AAPL" />);

      await waitFor(() => {
        // Look for market cap display - exact format may vary
        expect(screen.getByText(/2.4T|Market Cap|2,400B/i)).toBeInTheDocument();
      });
    });
  });

  describe("Symbol Updates", () => {
    test("refetches data when symbol changes", async () => {
      const { rerender } = render(<RealTimePriceWidget symbol="AAPL" />);

      await waitFor(() => {
        expect(mockDataCache.get).toHaveBeenCalledWith(
          "/api/stocks/quote/AAPL",
          {},
          expect.any(Object)
        );
      });

      mockDataCache.get.mockClear();
      rerender(<RealTimePriceWidget symbol="TSLA" />);

      await waitFor(() => {
        expect(mockDataCache.get).toHaveBeenCalledWith(
          "/api/stocks/quote/TSLA",
          {},
          expect.any(Object)
        );
      });
    });
  });

  describe("Edge Cases", () => {
    test("handles null/undefined price data", async () => {
      mockDataCache.get.mockResolvedValue(null);
      render(<RealTimePriceWidget symbol="AAPL" />);

      await waitFor(() => {
        expect(
          screen.getByText(/error/i) || screen.getByRole("alert")
        ).toBeInTheDocument();
      });
    });

    test("handles missing symbol prop", () => {
      render(<RealTimePriceWidget />);

      // Should handle gracefully without crashing
      expect(
        screen.getByRole("progressbar") || screen.getByText(/error/i)
      ).toBeInTheDocument();
    });

    test("handles zero price values", async () => {
      const zeroData = {
        ...mockPriceData,
        price: 0,
        dayChange: 0,
        dayChangePercent: 0,
      };

      mockDataCache.get.mockResolvedValue(zeroData);
      render(<RealTimePriceWidget symbol="AAPL" />);

      await waitFor(() => {
        expect(screen.getByText("$0.00")).toBeInTheDocument();
        expect(screen.getByText("0.00%")).toBeInTheDocument();
      });
    });
  });
});
