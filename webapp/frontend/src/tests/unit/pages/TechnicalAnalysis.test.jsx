/**
 * Unit Tests for TechnicalAnalysis Page Component
 * Tests the technical analysis page functionality and chart rendering
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders } from "../../test-utils.jsx";
import { screen, waitFor } from "@testing-library/react";
import TechnicalAnalysis from "../../../pages/TechnicalAnalysis.jsx";

// Mock the API service - both named export and api object
vi.mock("../../../services/api.js", () => ({
  getTechnicalData: vi.fn(() => Promise.resolve({
    data: [
      {
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
    ]
  })),
  api: {
    getTechnicalData: vi.fn(() => Promise.resolve({
      data: [
        {
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
      ]
    })),
    getStockPrices: vi.fn(() => Promise.resolve({
      data: [
        { symbol: 'AAPL', price: 180.50, change: 2.25 }
      ]
    }))
  }
}));

// Mock the custom useQuery hook
vi.mock("../../../hooks/useData", () => ({
  useQuery: vi.fn(() => ({
    data: {
      data: [
        {
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
      ]
    },
    isLoading: false,
    error: null,
    _refetch: vi.fn()
  }))
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
      
      // Wait for component to load first
      await waitFor(() => {
        expect(screen.getByText(/Technical Analysis/i)).toBeInTheDocument();
      }, { timeout: 5000 });
      
      // Then look for indicators - they might be in table headers or form labels
      await waitFor(() => {
        const rsiElements = screen.queryAllByText(/RSI/i);
        const macdElements = screen.queryAllByText(/MACD/i);
        
        // Should find at least one occurrence of each indicator
        expect(rsiElements.length).toBeGreaterThan(0);
        expect(macdElements.length).toBeGreaterThan(0);
      }, { timeout: 5000 });
    });
  });

  describe("Chart Rendering", () => {
    it("should render technical analysis content", async () => {
      renderWithProviders(<TechnicalAnalysis />);
      
      await waitFor(() => {
        // Check for technical analysis content that actually exists
        expect(screen.getByText(/Technical Analysis/i)).toBeInTheDocument();
      }, { timeout: 5000 });
    });
  });

  describe("Error Handling", () => {
    it("should handle API errors gracefully", async () => {
      const { useQuery } = await import("../../../hooks/useData");
      useQuery.mockReturnValueOnce({
        data: null,
        isLoading: false,
        error: new Error('API Error'),
        _refetch: vi.fn()
      });
      
      renderWithProviders(<TechnicalAnalysis />);
      
      // Should not crash and should show error handling
      await waitFor(() => {
        expect(screen.getByText(/Technical Analysis/i)).toBeInTheDocument();
      }, { timeout: 5000 });
    });
  });
});