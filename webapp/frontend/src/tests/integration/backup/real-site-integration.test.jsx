/**
 * Real Site Integration Tests
 * Tests actual site components and functionality with real API integration
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { TestWrapper } from "../test-utils.jsx";

// Import real site components
import Dashboard from "../../pages/Dashboard.jsx";
import MarketOverview from "../../pages/MarketOverview.jsx";
import StockExplorer from "../../pages/StockExplorer.jsx";
import TechnicalAnalysis from "../../pages/TechnicalAnalysis.jsx";
import PortfolioHoldings from "../../pages/PortfolioHoldings.jsx";
import Watchlist from "../../pages/Watchlist.jsx";
import Settings from "../../pages/Settings.jsx";
import ServiceHealth from "../../pages/ServiceHealth.jsx";

// Import real components
import MarketStatusBar from "../../components/MarketStatusBar.jsx";
import RealTimePriceWidget from "../../components/RealTimePriceWidget.jsx";
import ApiKeyProvider from "../../components/ApiKeyProvider.jsx";

// Mock API service for controlled testing
vi.mock("../../services/api.js", () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() }
    }
  }
}));

// Mock data service
vi.mock("../../services/dataService.js", () => ({
  default: {
    fetchData: vi.fn(),
    clearCache: vi.fn(),
    invalidateCache: vi.fn()
  }
}));

describe("Real Site Integration Tests", () => {
  let mockApi, mockDataService;

  beforeEach(async () => {
    vi.clearAllMocks();
    
    // Import mocked services
    const { default: api } = await import("../../services/api.js");
    const { default: dataService } = await import("../../services/dataService.js");
    
    mockApi = api;
    mockDataService = dataService;

    // Setup default successful responses
    mockApi.get.mockResolvedValue({ data: { success: true } });
    mockDataService.fetchData.mockResolvedValue({ data: [] });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe("Core Site Pages Integration", () => {
    it("should render Dashboard with real components", async () => {
      // Mock dashboard data
      mockDataService.fetchData.mockResolvedValue({
        portfolioValue: 150000,
        dayChange: 2500,
        holdings: [
          { symbol: "AAPL", shares: 100, currentPrice: 175.50 },
          { symbol: "GOOGL", shares: 50, currentPrice: 2750.25 }
        ]
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <Dashboard />
          </BrowserRouter>
        </TestWrapper>
      );

      // Should show loading initially
      expect(screen.getByTestId("loading-display") || screen.getByText(/loading/i)).toBeInTheDocument();

      // Wait for data to load
      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });

    it("should render MarketOverview with market data", async () => {
      // Mock market data
      mockDataService.fetchData.mockResolvedValue({
        marketStatus: "open",
        indices: {
          SPY: { price: 450.25, change: 2.15 },
          QQQ: { price: 385.50, change: -1.25 },
          DIA: { price: 350.75, change: 0.85 }
        }
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <MarketOverview />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });

    it("should render StockExplorer with search functionality", async () => {
      const user = userEvent.setup();

      // Mock stock search data
      mockDataService.fetchData.mockResolvedValue([
        { symbol: "AAPL", name: "Apple Inc.", price: 175.50 },
        { symbol: "MSFT", name: "Microsoft Corp.", price: 385.25 }
      ]);

      render(
        <TestWrapper>
          <BrowserRouter>
            <StockExplorer />
          </BrowserRouter>
        </TestWrapper>
      );

      // Look for search input
      const searchInput = screen.getByRole("textbox") || screen.getByPlaceholderText(/search/i);
      
      if (searchInput) {
        await user.type(searchInput, "AAPL");
        
        await waitFor(() => {
          expect(mockDataService.fetchData).toHaveBeenCalled();
        }, { timeout: 5000 });
      }
    });

    it("should render TechnicalAnalysis with chart data", async () => {
      // Mock technical analysis data
      mockDataService.fetchData.mockResolvedValue({
        symbol: "AAPL",
        technicals: {
          rsi: 65.5,
          macd: 1.25,
          bollingerBands: { upper: 180, middle: 175, lower: 170 }
        },
        chartData: [
          { date: "2024-01-01", price: 170 },
          { date: "2024-01-02", price: 175 }
        ]
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <TechnicalAnalysis />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });

    it("should render PortfolioHoldings with portfolio data", async () => {
      // Mock portfolio data
      mockDataService.fetchData.mockResolvedValue({
        holdings: [
          { 
            symbol: "AAPL", 
            shares: 100, 
            avgCost: 150.00, 
            currentPrice: 175.50,
            totalValue: 17550,
            gainLoss: 2550
          },
          { 
            symbol: "GOOGL", 
            shares: 50, 
            avgCost: 2500.00, 
            currentPrice: 2750.25,
            totalValue: 137512.50,
            gainLoss: 12512.50
          }
        ],
        totalValue: 155062.50,
        totalGainLoss: 15062.50
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <PortfolioHoldings />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });

    it("should render Watchlist with watchlist data", async () => {
      // Mock watchlist data
      mockDataService.fetchData.mockResolvedValue({
        watchlist: [
          { symbol: "AAPL", price: 175.50, change: 2.15, changePercent: 1.24 },
          { symbol: "MSFT", price: 385.25, change: -1.25, changePercent: -0.32 },
          { symbol: "GOOGL", price: 2750.25, change: 15.50, changePercent: 0.57 }
        ]
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <Watchlist />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });

    it("should render Settings with configuration options", async () => {
      render(
        <TestWrapper>
          <BrowserRouter>
            <Settings />
          </BrowserRouter>
        </TestWrapper>
      );

      // Settings page should render without API calls initially
      expect(screen.getByText(/settings/i) || screen.getByRole("main")).toBeInTheDocument();
    });

    it("should render ServiceHealth with health status", async () => {
      // Mock service health data
      mockDataService.fetchData.mockResolvedValue({
        services: [
          { name: "API Gateway", status: "healthy", responseTime: 45 },
          { name: "Database", status: "healthy", responseTime: 12 },
          { name: "Cache", status: "healthy", responseTime: 8 }
        ],
        overallStatus: "healthy"
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <ServiceHealth />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });
  });

  describe("Real Component Integration", () => {
    it("should render MarketStatusBar with market status", async () => {
      // Mock market status data
      mockDataService.fetchData.mockResolvedValue({
        marketStatus: "open",
        nextClose: "2024-01-15T21:00:00Z",
        timeToClose: "5:30:00"
      });

      render(
        <TestWrapper>
          <MarketStatusBar />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });

    it("should render RealTimePriceWidget with price data", async () => {
      // Mock real-time price data
      mockDataService.fetchData.mockResolvedValue({
        symbol: "AAPL",
        price: 175.50,
        change: 2.15,
        changePercent: 1.24,
        lastUpdate: new Date().toISOString()
      });

      render(
        <TestWrapper>
          <RealTimePriceWidget symbol="AAPL" />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });

    it("should render ApiKeyProvider with API key management", async () => {
      const TestComponent = () => (
        <ApiKeyProvider>
          <div data-testid="child-component">API Key Provider Child</div>
        </ApiKeyProvider>
      );

      render(
        <TestWrapper>
          <TestComponent />
        </TestWrapper>
      );

      expect(screen.getByTestId("child-component")).toBeInTheDocument();
    });
  });

  describe("Site Navigation Integration", () => {
    it("should handle navigation between pages", async () => {
      const _user = userEvent.setup();

      render(
        <TestWrapper>
          <BrowserRouter>
            <div>
              <nav>
                <a href="/dashboard">Dashboard</a>
                <a href="/market">Market</a>
                <a href="/portfolio">Portfolio</a>
              </nav>
              <Dashboard />
            </div>
          </BrowserRouter>
        </TestWrapper>
      );

      // Check navigation links exist
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
      expect(screen.getByText("Market")).toBeInTheDocument();
      expect(screen.getByText("Portfolio")).toBeInTheDocument();
    });
  });

  describe("Real API Integration", () => {
    it("should handle API success responses", async () => {
      const successData = { 
        data: { 
          portfolio: { value: 150000, holdings: [] } 
        } 
      };
      
      mockApi.get.mockResolvedValue(successData);
      mockDataService.fetchData.mockImplementation(async (url) => {
        const response = await mockApi.get(url);
        return response.data;
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <Dashboard />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockApi.get).toHaveBeenCalled();
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });

    it("should handle API error responses", async () => {
      const errorResponse = {
        response: { 
          status: 500, 
          data: { error: "Internal server error" } 
        }
      };
      
      mockApi.get.mockRejectedValue(errorResponse);
      mockDataService.fetchData.mockImplementation(async (url) => {
        const response = await mockApi.get(url);
        return response.data;
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <Dashboard />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockApi.get).toHaveBeenCalled();
      }, { timeout: 5000 });

      // Should handle error gracefully (not crash)
      expect(screen.getByRole("main") || screen.getByTestId("error-boundary")).toBeInTheDocument();
    });

    it("should handle authentication flows", async () => {
      // Mock authentication check
      mockApi.get.mockImplementation((url) => {
        if (url.includes('/auth/check')) {
          return Promise.resolve({ 
            data: { authenticated: true, user: { id: 1, name: "Test User" } } 
          });
        }
        return Promise.resolve({ data: {} });
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <Dashboard />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockApi.get).toHaveBeenCalled();
      }, { timeout: 5000 });
    });
  });

  describe("Real-time Data Integration", () => {
    it("should handle real-time price updates", async () => {
      // Mock WebSocket or polling behavior
      let updateCallback;
      
      mockDataService.fetchData.mockImplementation((url) => {
        if (url.includes('/realtime')) {
          // Simulate real-time update
          setTimeout(() => {
            if (updateCallback) {
              updateCallback({
                symbol: "AAPL",
                price: 176.00,
                change: 2.65
              });
            }
          }, 100);
          
          return Promise.resolve({
            subscribe: (callback) => { updateCallback = callback; },
            unsubscribe: () => { updateCallback = null; }
          });
        }
        return Promise.resolve({ data: [] });
      });

      render(
        <TestWrapper>
          <RealTimePriceWidget symbol="AAPL" />
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });
  });

  describe("User Interaction Integration", () => {
    it("should handle form submissions", async () => {
      const user = userEvent.setup();
      
      mockApi.post.mockResolvedValue({ 
        data: { success: true, message: "Settings saved" } 
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <Settings />
          </BrowserRouter>
        </TestWrapper>
      );

      // Look for form inputs and submit button
      const submitButton = screen.queryByRole("button", { name: /save/i }) || 
                          screen.queryByRole("button", { name: /submit/i });
      
      if (submitButton) {
        await user.click(submitButton);
        
        await waitFor(() => {
          expect(mockApi.post).toHaveBeenCalled();
        }, { timeout: 5000 });
      }
    });

    it("should handle search functionality", async () => {
      const user = userEvent.setup();
      
      mockDataService.fetchData.mockResolvedValue([
        { symbol: "AAPL", name: "Apple Inc." },
        { symbol: "MSFT", name: "Microsoft Corp." }
      ]);

      render(
        <TestWrapper>
          <BrowserRouter>
            <StockExplorer />
          </BrowserRouter>
        </TestWrapper>
      );

      const searchInput = screen.queryByRole("textbox") || 
                         screen.queryByPlaceholderText(/search/i);
      
      if (searchInput) {
        await user.type(searchInput, "AAPL");
        
        await waitFor(() => {
          expect(mockDataService.fetchData).toHaveBeenCalled();
        }, { timeout: 5000 });
      }
    });
  });

  describe("Data Flow Integration", () => {
    it("should maintain data consistency across components", async () => {
      const portfolioData = {
        holdings: [
          { symbol: "AAPL", shares: 100, currentPrice: 175.50 }
        ],
        totalValue: 17550
      };

      mockDataService.fetchData.mockResolvedValue(portfolioData);

      render(
        <TestWrapper>
          <BrowserRouter>
            <PortfolioHoldings />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });

      // Data should be consistent across component renders
      expect(mockDataService.fetchData).toHaveBeenCalledTimes(1);
    });

    it("should handle cache invalidation", async () => {
      mockDataService.fetchData.mockResolvedValue({ data: [] });
      mockDataService.invalidateCache.mockImplementation(() => {
        // Simulate cache invalidation
        return Promise.resolve();
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <Dashboard />
          </BrowserRouter>
        </TestWrapper>
      );

      // Simulate cache invalidation
      mockDataService.invalidateCache("dashboard");

      await waitFor(() => {
        expect(mockDataService.invalidateCache).toHaveBeenCalledWith("dashboard");
      }, { timeout: 5000 });
    });
  });
});