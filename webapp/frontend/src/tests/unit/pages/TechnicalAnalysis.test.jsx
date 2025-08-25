/**
 * Unit Tests for TechnicalAnalysis Page Component
 * Tests the technical analysis page functionality and chart rendering
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders } from "../../test-utils.jsx";
import { screen, waitFor } from "@testing-library/react";
import TechnicalAnalysis from "../../../pages/TechnicalAnalysis.jsx";

// Mock the API service
vi.mock("../../../services/api.js", () => ({
  api: {
    getTechnicalData: vi.fn(() => Promise.resolve({
      data: {
        symbol: 'AAPL',
        indicators: {
          rsi: 65.5,
          macd: 2.15,
          bb_upper: 185.50,
          bb_lower: 175.25,
          sma_20: 180.75,
          sma_50: 178.25
        },
        history: [
          { date: '2024-01-01', close: 180.50, rsi: 60.0 },
          { date: '2024-01-02', close: 182.25, rsi: 65.5 }
        ]
      }
    })),
    getStockPrices: vi.fn(() => Promise.resolve({
      data: [
        { symbol: 'AAPL', price: 180.50, change: 2.25 }
      ]
    }))
  }
}));

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
      
      await waitFor(() => {
        expect(screen.getByText(/RSI/i)).toBeInTheDocument();
        expect(screen.getByText(/MACD/i)).toBeInTheDocument();
      }, { timeout: 10000 });
    });
  });

  describe("Chart Rendering", () => {
    it("should render technical charts", async () => {
      renderWithProviders(<TechnicalAnalysis />);
      
      await waitFor(() => {
        // Check for chart components (mocked in setup)
        expect(screen.getByTestId('line-chart')).toBeInTheDocument();
      }, { timeout: 10000 });
    });
  });

  describe("Error Handling", () => {
    it("should handle API errors gracefully", async () => {
      const { api } = await import("../../../services/api.js");
      api.getTechnicalData.mockRejectedValueOnce(new Error('API Error'));
      
      renderWithProviders(<TechnicalAnalysis />);
      
      // Should not crash and should show error handling
      await waitFor(() => {
        expect(screen.getByText(/Technical Analysis/i)).toBeInTheDocument();
      }, { timeout: 5000 });
    });
  });
});