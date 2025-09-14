/**
 * End-to-End Data Flow Integration Tests
 * Tests complete data flow from API through services to UI components
 * Focuses on full integration workflows and user scenarios
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";

// Complete pages for E2E testing
import Dashboard from "../../pages/Dashboard.jsx";
import Portfolio from "../../pages/Portfolio.jsx";
import MarketOverview from "../../pages/MarketOverview.jsx";
import StockDetail from "../../pages/StockDetail.jsx";

// Test wrapper
import { TestWrapper } from "../test-utils.jsx";

// Mock all services for E2E integration
vi.mock("../../services/api.js");
vi.mock("../../services/dataService.js");
vi.mock("../../services/devAuth.js");
vi.mock("../../services/realTimeDataService.js");

describe("End-to-End Data Flow Integration", () => {
  let mockApiService;
  let mockDataService;
  let mockAuthService;
  let mockRealTimeService;

  beforeEach(() => {
    vi.clearAllMocks();

    // Setup comprehensive API mocks
    mockApiService = {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() }
      }
    };

    // Setup data service mocks
    mockDataService = {
      fetchData: vi.fn(),
      getCachedData: vi.fn(),
      invalidateCache: vi.fn(),
      subscribeToRealTimeData: vi.fn()
    };

    // Setup auth service mocks
    mockAuthService = {
      isAuthenticated: vi.fn(() => true),
      getCurrentSession: vi.fn(() => ({
        user: { username: "testuser", email: "test@example.com" },
        tokens: { accessToken: "mock-token" }
      })),
      signIn: vi.fn(),
      signOut: vi.fn()
    };

    // Setup real-time service mocks
    mockRealTimeService = {
      connect: vi.fn(() => Promise.resolve()),
      subscribe: vi.fn(),
      unsubscribe: vi.fn(),
      isConnected: vi.fn(() => true)
    };

    // Apply mocks
    require("../../services/api.js").default = mockApiService;
    require("../../services/dataService.js").default = mockDataService;
    require("../../services/devAuth.js").default = mockAuthService;
    require("../../services/realTimeDataService.js").default = mockRealTimeService;
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe("Portfolio Data Flow", () => {
    it("should complete full portfolio data flow from API to UI", async () => {
      // Mock portfolio API responses
      const mockPortfolioData = {
        data: {
          holdings: [
            { symbol: "AAPL", shares: 10, avgPrice: 150.00, currentPrice: 155.00 },
            { symbol: "GOOGL", shares: 5, avgPrice: 2800.00, currentPrice: 2850.00 }
          ],
          totalValue: 15800,
          dayChange: 300,
          dayChangePercent: 1.94
        }
      };

      mockApiService.get.mockImplementation((url) => {
        if (url.includes('/portfolio')) {
          return Promise.resolve(mockPortfolioData);
        }
        return Promise.reject(new Error(`Unexpected URL: ${url}`));
      });

      mockDataService.fetchData.mockImplementation((url) => {
        if (url.includes('/portfolio')) {
          return Promise.resolve(mockPortfolioData.data);
        }
        return Promise.reject(new Error(`Unexpected URL: ${url}`));
      });

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Should load and display portfolio data
      await waitFor(() => {
        expect(screen.getByText(/AAPL/)).toBeInTheDocument();
        expect(screen.getByText(/GOOGL/)).toBeInTheDocument();
        expect(screen.getByText(/15,?800/)).toBeInTheDocument(); // Total value
        expect(screen.getByText(/\+1\.94%/)).toBeInTheDocument(); // Day change percent
      }, { timeout: 3000 });

      // Verify API and service calls
      expect(mockApiService.get).toHaveBeenCalledWith(expect.stringContaining('/portfolio'));
      expect(mockDataService.fetchData).toHaveBeenCalledWith(expect.stringContaining('/portfolio'));
    });

    it("should handle portfolio updates with real-time data", async () => {
      const initialData = {
        data: {
          holdings: [{ symbol: "AAPL", shares: 10, avgPrice: 150.00, currentPrice: 150.00 }],
          totalValue: 1500,
          dayChange: 0
        }
      };

      const updatedData = {
        symbol: "AAPL",
        currentPrice: 155.00,
        change: 5.00,
        changePercent: 3.33
      };

      mockApiService.get.mockResolvedValue(initialData);
      mockDataService.fetchData.mockResolvedValue(initialData.data);

      // Mock real-time subscription
      let realtimeCallback;
      mockRealTimeService.subscribe.mockImplementation((symbol, callback) => {
        realtimeCallback = callback;
      });

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Wait for initial load
      await waitFor(() => {
        expect(screen.getByText(/AAPL/)).toBeInTheDocument();
        expect(screen.getByText(/1,?500/)).toBeInTheDocument();
      });

      // Simulate real-time update
      act(() => {
        if (realtimeCallback) {
          realtimeCallback(updatedData);
        }
      });

      // Should reflect updated price
      await waitFor(() => {
        expect(screen.getByText(/155\.00/)).toBeInTheDocument();
        expect(screen.getByText(/1,?550/)).toBeInTheDocument(); // Updated total
      });
    });
  });

  describe("Market Data Flow", () => {
    it("should integrate market data across multiple components", async () => {
      const mockMarketData = {
        data: {
          indices: [
            { symbol: "SPX", name: "S&P 500", value: 4500.25, change: 15.75 },
            { symbol: "NASDAQ", name: "NASDAQ", value: 14200.50, change: -25.30 }
          ],
          sectors: [
            { name: "Technology", performance: 2.1, change: "up" },
            { name: "Healthcare", performance: -0.8, change: "down" }
          ]
        }
      };

      mockApiService.get.mockImplementation((url) => {
        if (url.includes('/market')) {
          return Promise.resolve(mockMarketData);
        }
        return Promise.resolve({ data: {} });
      });

      mockDataService.fetchData.mockImplementation((url) => {
        if (url.includes('/market')) {
          return Promise.resolve(mockMarketData.data);
        }
        return Promise.resolve({});
      });

      render(
        <TestWrapper>
          <MarketOverview />
        </TestWrapper>
      );

      // Should display market indices
      await waitFor(() => {
        expect(screen.getByText(/S&P 500/)).toBeInTheDocument();
        expect(screen.getByText(/4,?500\.25/)).toBeInTheDocument();
        expect(screen.getByText(/NASDAQ/)).toBeInTheDocument();
        expect(screen.getByText(/14,?200\.50/)).toBeInTheDocument();
      });

      // Should display sector performance
      await waitFor(() => {
        expect(screen.getByText(/Technology/)).toBeInTheDocument();
        expect(screen.getByText(/2\.1%/)).toBeInTheDocument();
        expect(screen.getByText(/Healthcare/)).toBeInTheDocument();
      });
    });
  });

  describe("Stock Detail Data Flow", () => {
    it("should load comprehensive stock data from multiple endpoints", async () => {
      const symbol = "AAPL";
      
      // Mock multiple API responses for stock detail
      const mockStockPrice = {
        data: { symbol, price: 155.25, change: 2.15, changePercent: 1.41 }
      };

      const mockStockInfo = {
        data: { 
          symbol, 
          name: "Apple Inc.", 
          marketCap: "2.5T",
          peRatio: 28.5,
          dividend: "0.96"
        }
      };

      const mockTechnicalData = {
        data: {
          rsi: 65.2,
          macd: { signal: "bullish", value: 0.85 },
          movingAverages: { sma50: 152.30, sma200: 148.75 }
        }
      };

      mockApiService.get.mockImplementation((url) => {
        if (url.includes('/price')) return Promise.resolve(mockStockPrice);
        if (url.includes('/stock-info')) return Promise.resolve(mockStockInfo);
        if (url.includes('/technical')) return Promise.resolve(mockTechnicalData);
        return Promise.resolve({ data: {} });
      });

      mockDataService.fetchData.mockImplementation((url) => {
        if (url.includes('/price')) return Promise.resolve(mockStockPrice.data);
        if (url.includes('/stock-info')) return Promise.resolve(mockStockInfo.data);
        if (url.includes('/technical')) return Promise.resolve(mockTechnicalData.data);
        return Promise.resolve({});
      });

      render(
        <TestWrapper>
          <StockDetail symbol={symbol} />
        </TestWrapper>
      );

      // Should load and display all stock data
      await waitFor(() => {
        expect(screen.getByText(/Apple Inc\./)).toBeInTheDocument();
        expect(screen.getByText(/155\.25/)).toBeInTheDocument();
        expect(screen.getByText(/\+2\.15/)).toBeInTheDocument();
        expect(screen.getByText(/2\.5T/)).toBeInTheDocument(); // Market cap
        expect(screen.getByText(/28\.5/)).toBeInTheDocument(); // PE ratio
      }, { timeout: 3000 });

      // Verify multiple API calls were made
      expect(mockApiService.get).toHaveBeenCalledWith(expect.stringContaining('/price'));
      expect(mockApiService.get).toHaveBeenCalledWith(expect.stringContaining('/stock-info'));
      expect(mockApiService.get).toHaveBeenCalledWith(expect.stringContaining('/technical'));
    });
  });

  describe("Dashboard Integration Flow", () => {
    it("should coordinate data from multiple sources on dashboard", async () => {
      // Mock all dashboard data sources
      const mockDashboardData = {
        portfolio: { totalValue: 50000, dayChange: 1250 },
        market: { status: "open", indices: [{ symbol: "SPX", value: 4500 }] },
        watchlist: [{ symbol: "AAPL", price: 155.25 }],
        news: [{ headline: "Market Update", summary: "Stocks rise today" }]
      };

      mockApiService.get.mockImplementation((url) => {
        if (url.includes('/portfolio')) {
          return Promise.resolve({ data: mockDashboardData.portfolio });
        }
        if (url.includes('/market')) {
          return Promise.resolve({ data: mockDashboardData.market });
        }
        if (url.includes('/watchlist')) {
          return Promise.resolve({ data: mockDashboardData.watchlist });
        }
        if (url.includes('/news')) {
          return Promise.resolve({ data: mockDashboardData.news });
        }
        return Promise.resolve({ data: {} });
      });

      mockDataService.fetchData.mockImplementation((url) => {
        if (url.includes('/portfolio')) return Promise.resolve(mockDashboardData.portfolio);
        if (url.includes('/market')) return Promise.resolve(mockDashboardData.market);
        if (url.includes('/watchlist')) return Promise.resolve(mockDashboardData.watchlist);
        if (url.includes('/news')) return Promise.resolve(mockDashboardData.news);
        return Promise.resolve({});
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should display data from all sources
      await waitFor(() => {
        // Portfolio data
        expect(screen.getByText(/50,?000/)).toBeInTheDocument();
        expect(screen.getByText(/1,?250/)).toBeInTheDocument();
        
        // Market data
        expect(screen.getByText(/4,?500/)).toBeInTheDocument();
        
        // Watchlist
        expect(screen.getByText(/AAPL/)).toBeInTheDocument();
        expect(screen.getByText(/155\.25/)).toBeInTheDocument();
        
        // News
        expect(screen.getByText(/Market Update/)).toBeInTheDocument();
      }, { timeout: 5000 });
    });
  });

  describe("Error Handling Integration", () => {
    it("should handle API failures gracefully across components", async () => {
      // Mock API failures
      mockApiService.get.mockRejectedValue(new Error("Network error"));
      mockDataService.fetchData.mockRejectedValue(new Error("Service unavailable"));

      render(
        <TestWrapper>
          <Portfolio />
        </TestWrapper>
      );

      // Should show error states
      await waitFor(() => {
        expect(
          screen.getByText(/error loading/i) ||
          screen.getByText(/service unavailable/i) ||
          screen.getByText(/network error/i) ||
          screen.getByTestId("error-message")
        ).toBeInTheDocument();
      });
    });

    it("should recover from partial failures", async () => {
      // Mock partial failures
      mockApiService.get.mockImplementation((url) => {
        if (url.includes('/portfolio')) {
          return Promise.resolve({ data: { holdings: [], totalValue: 0 } });
        }
        if (url.includes('/market')) {
          return Promise.reject(new Error("Market service down"));
        }
        return Promise.resolve({ data: {} });
      });

      mockDataService.fetchData.mockImplementation((url) => {
        if (url.includes('/portfolio')) {
          return Promise.resolve({ holdings: [], totalValue: 0 });
        }
        if (url.includes('/market')) {
          return Promise.reject(new Error("Market service down"));
        }
        return Promise.resolve({});
      });

      render(
        <TestWrapper>
          <Dashboard />
        </TestWrapper>
      );

      // Should show successful data where available
      await waitFor(() => {
        // Portfolio section should work
        expect(screen.getByText(/portfolio/i)).toBeInTheDocument();
        
        // Market section should show error
        expect(
          screen.getByText(/market.*error/i) ||
          screen.getByText(/service down/i) ||
          screen.getByTestId("market-error")
        ).toBeInTheDocument();
      });
    });
  });
});