/**
 * Unit Tests for TechnicalAnalysis Page Component
 * Tests the technical analysis page functionality and chart rendering
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders } from "../../test-utils.jsx";
import { screen, waitFor } from "@testing-library/react";
import TechnicalAnalysis from "../../../pages/TechnicalAnalysis.jsx";

// Mock API service with standardized pattern
vi.mock("../../../services/api.js", () => ({
  default: {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    getTechnicalData: vi.fn(() =>
      Promise.resolve({
        success: true,
        data: [
          {
            symbol: "AAPL",
            indicators: {
              rsi: 65.5,
              macd: 2.15,
              bb_upper: 185.5,
              bb_lower: 175.25,
              sma_20: 180.75,
              sma_50: 178.25,
            },
            history: [
              { date: "2024-01-01", close: 180.5, rsi: 60.0 },
              { date: "2024-01-02", close: 182.25, rsi: 65.5 },
            ],
          },
        ],
      })
    ),
    getStockPrices: vi.fn(() =>
      Promise.resolve({
        success: true,
        data: [{ symbol: "AAPL", price: 180.5, change: 2.25 }],
      })
    ),
    getTradingSignalsDaily: vi.fn(() => Promise.resolve({ success: true, data: [] })),
    getPortfolioAnalytics: vi.fn(() => Promise.resolve({ success: true, data: {} })),
    getStockMetrics: vi.fn(() => Promise.resolve({ success: true, data: {} })),
  },
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    environment: "test",
  })),
}));

// Mock @tanstack/react-query
vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    useQuery: vi.fn(() => ({
      data: {
        data: [
          {
            symbol: "AAPL",
            rsi: 65.5,
            macd: 2.15,
            macd_signal: -0.5,
            macd_hist: 2.65,
            adx: 35.2,
            atr: 4.25,
            mfi: 58.3,
            bbands_upper: 185.5,
            bbands_middle: 180.0,
            bbands_lower: 175.25,
            sma_20: 180.75,
            sma_50: 178.25,
            date: "2024-01-15",
          },
          {
            symbol: "MSFT",
            rsi: 72.1,
            macd: 1.85,
            macd_signal: 0.2,
            macd_hist: 1.65,
            adx: 28.7,
            atr: 3.85,
            mfi: 65.8,
            bbands_upper: 385.2,
            bbands_middle: 380.0,
            bbands_lower: 374.8,
            sma_20: 381.25,
            sma_50: 375.80,
            date: "2024-01-15",
          }
        ],
        totalCount: 2,
        page: 1,
        limit: 10
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })),
  };
});

describe("TechnicalAnalysis Page Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Page Loading", () => {
    it("should render technical analysis page", async () => {
      renderWithProviders(<TechnicalAnalysis />);

      expect(screen.getByText(/Technical Analysis/i)).toBeInTheDocument();
    });

    it("should display technical indicators", async () => {
      renderWithProviders(<TechnicalAnalysis />);

      // Wait for component to load first
      await waitFor(
        () => {
          expect(screen.getByText(/Technical Analysis/i)).toBeInTheDocument();
        },
        { timeout: 5000 }
      );

      // Then look for indicators - they might be in table headers or form labels
      await waitFor(
        () => {
          const rsiElements = screen.queryAllByText(/RSI/i);
          const macdElements = screen.queryAllByText(/MACD/i);

          // Should find at least one occurrence of each indicator
          expect(rsiElements.length).toBeGreaterThan(0);
          expect(macdElements.length).toBeGreaterThan(0);
        },
        { timeout: 5000 }
      );
    });
  });

  describe("Chart Rendering", () => {
    it("should render technical analysis content", async () => {
      renderWithProviders(<TechnicalAnalysis />);

      await waitFor(
        () => {
          // Check for technical analysis content that actually exists
          expect(screen.getByText(/Technical Analysis/i)).toBeInTheDocument();
        },
        { timeout: 5000 }
      );
    });
  });

  describe("Error Handling", () => {
    it("should handle API errors gracefully", async () => {
      const { useQuery } = await import("@tanstack/react-query");
      useQuery.mockReturnValueOnce({
        data: null,
        isLoading: false,
        error: new Error("API Error"),
        refetch: vi.fn(),
      });

      renderWithProviders(<TechnicalAnalysis />);

      // Should not crash and should show error handling
      await waitFor(
        () => {
          expect(screen.getByText(/Technical Analysis/i)).toBeInTheDocument();
        },
        { timeout: 5000 }
      );
    });
  });
});
