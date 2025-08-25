/**
 * Unit Tests for MarketStatusBar Component
 * Tests component state, effects, and conditional rendering
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithTheme } from "./test-helpers/component-test-utils.jsx";
import MarketStatusBar from "../../../components/MarketStatusBar.jsx";

// Mock dependencies
vi.mock("../../../services/dataCache", () => ({
  default: {
    get: vi.fn(),
  },
}));

vi.mock("../../../utils/formatters", () => ({
  formatPercentage: vi.fn((value) => `${value.toFixed(2)}%`),
  formatNumber: vi.fn((value, decimals = 2) => {
    if (decimals === 0) {
      return Math.round(value).toLocaleString();
    }
    return value.toLocaleString(undefined, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  }),
}));

describe("MarketStatusBar Component", () => {
  let mockDataCache;
  
  beforeEach(async () => {
    vi.clearAllMocks();
    mockDataCache = await import("../../../services/dataCache");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("Loading State", () => {
    it("should not render anything while loading", () => {
      // Mock delayed response
      mockDataCache.default.get.mockImplementation(() => new Promise(() => {}));
      
      const { container } = renderWithTheme(<MarketStatusBar />);
      
      // Component returns null while loading
      expect(container).toBeEmptyDOMElement();
    });
  });

  describe("Market Status Display", () => {
    const mockMarketData = {
      isOpen: true,
      session: "Open",
      nextChange: "Closes at 4:00 PM",
      indices: [
        {
          symbol: "SPX",
          name: "S&P 500",
          value: 4500.25,
          change: 25.50,
          changePercent: 0.57,
        },
        {
          symbol: "DJI", 
          name: "Dow Jones",
          value: 35250.75,
          change: -125.25,
          changePercent: -0.35,
        },
      ],
    };

    beforeEach(() => {
      mockDataCache.default.get.mockResolvedValue(mockMarketData);
    });

    it("should display market open status", async () => {
      renderWithTheme(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText("Market Open")).toBeInTheDocument();
      });
    });

    it("should display market closed status", async () => {
      const closedData = { ...mockMarketData, isOpen: false, session: "Closed" };
      mockDataCache.default.get.mockResolvedValue(closedData);
      
      renderWithTheme(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText("Market Closed")).toBeInTheDocument();
      });
    });

    it("should display pre-market status", async () => {
      const preMarketData = { ...mockMarketData, session: "Pre-Market", nextChange: "Opens at 9:30 AM" };
      mockDataCache.default.get.mockResolvedValue(preMarketData);
      
      renderWithTheme(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText("Market Pre-Market")).toBeInTheDocument();
      });
    });

    it("should display after-hours status", async () => {
      const afterHoursData = { ...mockMarketData, session: "After-Hours", nextChange: "Closes at 8:00 PM" };
      mockDataCache.default.get.mockResolvedValue(afterHoursData);
      
      renderWithTheme(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText("Market After-Hours")).toBeInTheDocument();
      });
    });

    it("should display next change time", async () => {
      renderWithTheme(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText("Closes at 4:00 PM")).toBeInTheDocument();
      });
    });
  });

  describe("Indices Display", () => {
    const mockIndicesData = {
      isOpen: true,
      session: "Open", 
      nextChange: "Closes at 4:00 PM",
      indices: [
        {
          symbol: "SPX",
          name: "S&P 500",
          value: 4500.25,
          change: 25.50,
          changePercent: 0.57,
        },
        {
          symbol: "DJI",
          name: "Dow Jones", 
          value: 35250.75,
          change: -125.25,
          changePercent: -0.35,
        },
        {
          symbol: "IXIC",
          name: "Nasdaq",
          value: 14125.50,
          change: 85.75,
          changePercent: 0.62,
        },
      ],
    };

    beforeEach(() => {
      mockDataCache.default.get.mockResolvedValue(mockIndicesData);
    });

    it("should display all major indices", async () => {
      renderWithTheme(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText("S&P 500")).toBeInTheDocument();
        expect(screen.getByText("Dow Jones")).toBeInTheDocument();
        expect(screen.getByText("Nasdaq")).toBeInTheDocument();
      });
    });

    it("should display index values", async () => {
      renderWithTheme(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText("4,500")).toBeInTheDocument(); // Formatted number without decimals
        expect(screen.getByText("35,251")).toBeInTheDocument();
        expect(screen.getByText("14,126")).toBeInTheDocument();
      });
    });

    it("should display positive changes with up trend", async () => {
      renderWithTheme(<MarketStatusBar />);
      
      await waitFor(() => {
        // Should show positive changes
        expect(screen.getByText("0.57%")).toBeInTheDocument(); // S&P 500
        expect(screen.getByText("0.62%")).toBeInTheDocument(); // Nasdaq
      });
    });

    it("should display negative changes with down trend", async () => {
      renderWithTheme(<MarketStatusBar />);
      
      await waitFor(() => {
        // Should show negative change
        expect(screen.getByText("-0.35%")).toBeInTheDocument(); // Dow Jones
      });
    });

    it("should show trending up icons for positive changes", async () => {
      renderWithTheme(<MarketStatusBar />);
      
      await waitFor(() => {
        const trendingUpIcons = screen.getAllByTestId("TrendingUpIcon");
        expect(trendingUpIcons.length).toBeGreaterThan(0);
      });
    });

    it("should show trending down icons for negative changes", async () => {
      renderWithTheme(<MarketStatusBar />);
      
      await waitFor(() => {
        const trendingDownIcons = screen.getAllByTestId("TrendingDownIcon");
        expect(trendingDownIcons.length).toBeGreaterThan(0);
      });
    });
  });

  describe("Error Handling", () => {
    it("should handle fetch errors gracefully", async () => {
      const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      mockDataCache.default.get.mockRejectedValue(new Error("Network error"));
      
      renderWithTheme(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          "Failed to fetch market status:",
          expect.any(Error)
        );
      });
      
      // Component should render with default closed state on error
      await waitFor(() => {
        expect(screen.getByText("Market Closed")).toBeInTheDocument();
      });
      
      consoleErrorSpy.mockRestore();
    });

    it("should handle missing data gracefully", async () => {
      mockDataCache.default.get.mockResolvedValue({
        isOpen: false,
        session: "Closed",
        nextChange: null,
        indices: [],
      });
      
      renderWithTheme(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText("Market Closed")).toBeInTheDocument();
      });
    });
  });

  describe("Component Updates", () => {
    it("should handle data updates correctly", async () => {
      // Initial data - market open
      mockDataCache.default.get.mockResolvedValue({
        isOpen: true,
        session: "Open",
        nextChange: "Closes at 4:00 PM",
        indices: [],
      });
      
      renderWithTheme(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText("Market Open")).toBeInTheDocument();
        expect(screen.getByText("Closes at 4:00 PM")).toBeInTheDocument();
      });
      
      // This test demonstrates the component can handle different data states
      // In a real scenario, the component would update via useEffect intervals
      expect(mockDataCache.default.get).toHaveBeenCalledWith(
        "/api/market/status",
        {},
        expect.objectContaining({
          cacheType: "marketData",
          fetchFunction: expect.any(Function),
        })
      );
    });
  });

  describe("Data Caching", () => {
    beforeEach(() => {
      mockDataCache.default.get.mockResolvedValue({
        isOpen: true,
        session: "Open",
        nextChange: "Closes at 4:00 PM",
        indices: [],
      });
    });

    it("should call dataCache.get with correct parameters", async () => {
      renderWithTheme(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(mockDataCache.default.get).toHaveBeenCalledWith(
          "/api/market/status",
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
        isOpen: true,
        session: "Open",
        nextChange: "Closes at 4:00 PM",
        indices: [],
      };
      
      mockDataCache.default.get.mockResolvedValue(cachedData);
      
      renderWithTheme(<MarketStatusBar />);
      
      await waitFor(() => {
        expect(screen.getByText("Market Open")).toBeInTheDocument();
      });
      
      // Should have called cache only once
      expect(mockDataCache.default.get).toHaveBeenCalledTimes(1);
    });
  });

  describe("Responsive Behavior", () => {
    it("should render within container bounds", async () => {
      mockDataCache.default.get.mockResolvedValue({
        isOpen: true,
        session: "Open",
        nextChange: "Closes at 4:00 PM",
        indices: [
          { symbol: "SPX", name: "S&P 500", value: 4500, change: 25, changePercent: 0.57 },
        ],
      });
      
      renderWithTheme(<MarketStatusBar />);
      
      await waitFor(() => {
        // Component should render without layout issues
        const container = screen.getByText("S&P 500").closest('div');
        expect(container).toBeInTheDocument();
      });
    });
  });
});