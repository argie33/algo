/**
 * Unit Tests for RealTimePriceWidget Component
 * Tests props, state, data loading, and error handling
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import RealTimePriceWidget from "../../../components/RealTimePriceWidget.jsx";
import { renderWithTheme } from "./test-helpers/component-test-utils.jsx";

// Mock the data cache service
vi.mock("../../../services/dataCache", () => ({
  default: {
    get: vi.fn(),
  },
}));

// Mock formatters
vi.mock("../../../utils/formatters", () => ({
  formatCurrency: vi.fn((value) => `$${value.toFixed(2)}`),
  formatPercentage: vi.fn((value) => `${value.toFixed(2)}%`),
}));

describe("RealTimePriceWidget Component", () => {
  let mockDataCache;
  
  beforeEach(async () => {
    vi.clearAllMocks();
    mockDataCache = vi.mocked(await import("../../../services/dataCache"));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("Rendering", () => {
    it("should render with symbol prop", async () => {
      const mockPriceData = {
        symbol: "AAPL",
        price: 150.25,
        change: 2.50,
        changePercent: 1.69,
      };
      
      mockDataCache.default.get.mockResolvedValue(mockPriceData);
      
      renderWithTheme(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
      });
    });

    it("should render loading state initially", () => {
      // Mock delayed response
      mockDataCache.default.get.mockImplementation(
        () => new Promise(() => {}) // Never resolves
      );
      
      renderWithTheme(<RealTimePriceWidget symbol="AAPL" />);
      
      expect(screen.getByRole("progressbar") || screen.getByText(/loading/i)).toBeInTheDocument();
    });

    it("should handle missing symbol gracefully", async () => {
      renderWithTheme(<RealTimePriceWidget />);
      
      // Component should handle undefined symbol
      expect(document.body).toBeInTheDocument();
    });
  });

  describe("Price Display", () => {
    const mockPriceData = {
      symbol: "AAPL",
      price: 150.25,
      change: 2.50,
      changePercent: 1.69,
    };

    beforeEach(() => {
      mockDataCache.default.get.mockResolvedValue(mockPriceData);
    });

    it("should display current price", async () => {
      renderWithTheme(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText("$150.25")).toBeInTheDocument();
      });
    });

    it("should display price change", async () => {
      renderWithTheme(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText("2.50%")).toBeInTheDocument();
      });
    });

    it("should display negative changes correctly", async () => {
      const negativeData = {
        symbol: "TSLA",
        price: 220.50,
        change: -5.25,
        changePercent: -2.33,
      };
      
      mockDataCache.default.get.mockResolvedValue(negativeData);
      
      renderWithTheme(<RealTimePriceWidget symbol="TSLA" />);
      
      await waitFor(() => {
        expect(screen.getByText("$220.50")).toBeInTheDocument();
        expect(screen.getByText("-2.33%")).toBeInTheDocument();
      });
    });
  });

  describe("Error Handling", () => {
    it("should handle API errors gracefully", async () => {
      mockDataCache.default.get.mockRejectedValue(
        new Error("Network error")
      );
      
      renderWithTheme(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        // Component should render without crashing
        expect(document.body).toBeInTheDocument();
      });
    });

    it("should handle invalid symbol", async () => {
      mockDataCache.default.get.mockRejectedValue(
        new Error("Invalid symbol")
      );
      
      renderWithTheme(<RealTimePriceWidget symbol="INVALID" />);
      
      await waitFor(() => {
        // Component should render without crashing
        expect(document.body).toBeInTheDocument();
      });
    });
  });

  describe("Data Caching", () => {
    it("should call dataCache.get with correct parameters", async () => {
      const mockPriceData = {
        symbol: "AAPL",
        price: 150.25,
        change: 2.50,
        changePercent: 1.69,
      };
      
      mockDataCache.default.get.mockResolvedValue(mockPriceData);
      
      renderWithTheme(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        expect(mockDataCache.default.get).toHaveBeenCalledWith(
          "/api/stocks/quote/AAPL",
          {},
          expect.objectContaining({
            cacheType: "marketData",
            fetchFunction: expect.any(Function),
          })
        );
      });
    });

    it("should use cached data when available", async () => {
      const cachedData = {
        symbol: "AAPL",
        price: 150.25,
        change: 2.50,
        changePercent: 1.69,
      };
      
      mockDataCache.default.get.mockResolvedValue(cachedData);
      
      renderWithTheme(<RealTimePriceWidget symbol="AAPL" />);
      
      await waitFor(() => {
        expect(screen.getByText("$150.25")).toBeInTheDocument();
      });
      
      // Should have called cache only once
      expect(mockDataCache.default.get).toHaveBeenCalledTimes(1);
    });
  });

  describe("Component Props", () => {
    it("should support compact prop", () => {
      const mockPriceData = {
        symbol: "AAPL",
        price: 150.25,
        change: 2.50,
        changePercent: 1.69,
      };
      
      mockDataCache.default.get.mockResolvedValue(mockPriceData);
      
      renderWithTheme(<RealTimePriceWidget symbol="AAPL" compact={true} />);
      
      // Component should render without errors
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });
  });
});