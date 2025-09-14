/**
 * Financial Features Integration Tests
 * Tests financial analysis, trading, and data visualization features
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { TestWrapper } from "../test-utils.jsx";

// Import financial feature pages
import EarningsCalendar from "../../pages/EarningsCalendar.jsx";
import FinancialData from "../../pages/FinancialData.jsx";
import SectorAnalysis from "../../pages/SectorAnalysis.jsx";
import SentimentAnalysis from "../../pages/SentimentAnalysis.jsx";
import MetricsDashboard from "../../pages/MetricsDashboard.jsx";
import ScoresDashboard from "../../pages/ScoresDashboard.jsx";
import OrderManagement from "../../pages/OrderManagement.jsx";
import TradeHistory from "../../pages/TradeHistory.jsx";
import EconomicModeling from "../../pages/EconomicModeling.jsx";
import PatternRecognition from "../../pages/PatternRecognition.jsx";
import Backtest from "../../pages/Backtest.jsx";
import RealTimeDashboard from "../../pages/RealTimeDashboard.jsx";
import PortfolioPerformance from "../../pages/PortfolioPerformance.jsx";
import PortfolioOptimization from "../../pages/PortfolioOptimization.jsx";

// Import chart components
import HistoricalPriceChart from "../../components/HistoricalPriceChart.jsx";
import ProfessionalChart from "../../components/ProfessionalChart.jsx";

// Mock services
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

vi.mock("../../services/dataService.js", () => ({
  default: {
    fetchData: vi.fn(),
    clearCache: vi.fn(),
    invalidateCache: vi.fn()
  }
}));

describe("Financial Features Integration Tests", () => {
  let mockApi, mockDataService;

  beforeEach(async () => {
    vi.clearAllMocks();
    
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

  describe("Financial Analysis Pages", () => {

    it("should render EarningsCalendar with earnings data", async () => {
      mockDataService.fetchData.mockResolvedValue({
        earnings: [
          {
            symbol: "AAPL",
            company: "Apple Inc.",
            date: "2024-01-25",
            time: "after-market",
            estimate: 2.15,
            actual: null
          },
          {
            symbol: "MSFT",
            company: "Microsoft Corp.",
            date: "2024-01-26",
            time: "before-market",
            estimate: 3.25,
            actual: null
          }
        ]
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <EarningsCalendar />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });

    it("should render FinancialData with financial metrics", async () => {
      mockDataService.fetchData.mockResolvedValue({
        financials: {
          symbol: "AAPL",
          revenue: 394328000000,
          netIncome: 99803000000,
          eps: 6.16,
          peRatio: 28.5,
          marketCap: 2800000000000,
          bookValue: 4.40,
          debtToEquity: 2.12
        }
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <FinancialData />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });

    it("should render SectorAnalysis with sector performance", async () => {
      mockDataService.fetchData.mockResolvedValue({
        sectors: [
          { name: "Technology", performance: 15.2, marketCap: 12500000000000 },
          { name: "Healthcare", performance: 8.5, marketCap: 7200000000000 },
          { name: "Finance", performance: 12.1, marketCap: 8900000000000 }
        ]
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <SectorAnalysis />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });

    it("should render SentimentAnalysis with sentiment data", async () => {
      mockDataService.fetchData.mockResolvedValue({
        sentiment: {
          overall: "positive",
          score: 0.75,
          sources: {
            news: 0.8,
            social: 0.7,
            analyst: 0.85
          },
          trends: [
            { date: "2024-01-01", sentiment: 0.6 },
            { date: "2024-01-02", sentiment: 0.75 }
          ]
        }
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <SentimentAnalysis />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });
  });

  describe("Dashboard and Metrics Pages", () => {
    it("should render MetricsDashboard with key metrics", async () => {
      mockDataService.fetchData.mockResolvedValue({
        metrics: {
          portfolioValue: 250000,
          dayChange: 3500,
          weekChange: 8200,
          monthChange: 15600,
          yearChange: 45000,
          topGainer: { symbol: "AAPL", change: 5.2 },
          topLoser: { symbol: "MSFT", change: -2.1 }
        }
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <MetricsDashboard />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });

    it("should render ScoresDashboard with scoring data", async () => {
      mockDataService.fetchData.mockResolvedValue({
        scores: [
          { symbol: "AAPL", score: 8.5, factors: { growth: 9, value: 7, momentum: 9 } },
          { symbol: "MSFT", score: 8.2, factors: { growth: 8, value: 8, momentum: 9 } },
          { symbol: "GOOGL", score: 7.8, factors: { growth: 9, value: 6, momentum: 8 } }
        ]
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <ScoresDashboard />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });

    it("should render RealTimeDashboard with live data", async () => {
      mockDataService.fetchData.mockResolvedValue({
        realTimeData: {
          marketStatus: "open",
          activeTickers: ["AAPL", "MSFT", "GOOGL"],
          priceUpdates: [
            { symbol: "AAPL", price: 175.50, change: 2.15 },
            { symbol: "MSFT", price: 385.25, change: -1.25 }
          ]
        }
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <RealTimeDashboard />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });
  });

  describe("Trading and Portfolio Pages", () => {
    it("should render OrderManagement with order data", async () => {
      mockDataService.fetchData.mockResolvedValue({
        orders: [
          {
            id: "ORD001",
            symbol: "AAPL",
            type: "BUY",
            quantity: 100,
            price: 175.50,
            status: "PENDING",
            timestamp: "2024-01-15T10:30:00Z"
          },
          {
            id: "ORD002",
            symbol: "MSFT",
            type: "SELL",
            quantity: 50,
            price: 385.25,
            status: "FILLED",
            timestamp: "2024-01-15T09:45:00Z"
          }
        ]
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <OrderManagement />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });

    it("should render TradeHistory with trade records", async () => {
      mockDataService.fetchData.mockResolvedValue({
        trades: [
          {
            id: "TRD001",
            symbol: "AAPL",
            type: "BUY",
            quantity: 100,
            price: 170.00,
            commission: 0.99,
            date: "2024-01-10T14:30:00Z",
            profit: 550.00
          },
          {
            id: "TRD002",
            symbol: "MSFT",
            type: "SELL",
            quantity: 50,
            price: 380.00,
            commission: 0.99,
            date: "2024-01-12T11:15:00Z",
            profit: -125.00
          }
        ]
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <TradeHistory />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });

    it("should render PortfolioPerformance with performance metrics", async () => {
      mockDataService.fetchData.mockResolvedValue({
        performance: {
          totalReturn: 0.18,
          annualizedReturn: 0.22,
          sharpeRatio: 1.35,
          maxDrawdown: -0.08,
          volatility: 0.16,
          beta: 1.12,
          alpha: 0.05,
          performanceHistory: [
            { date: "2024-01-01", value: 200000 },
            { date: "2024-01-15", value: 250000 }
          ]
        }
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <PortfolioPerformance />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });

    it("should render PortfolioOptimization with optimization data", async () => {
      mockDataService.fetchData.mockResolvedValue({
        optimization: {
          currentAllocation: [
            { symbol: "AAPL", allocation: 0.4 },
            { symbol: "MSFT", allocation: 0.3 },
            { symbol: "GOOGL", allocation: 0.3 }
          ],
          recommendedAllocation: [
            { symbol: "AAPL", allocation: 0.35 },
            { symbol: "MSFT", allocation: 0.35 },
            { symbol: "GOOGL", allocation: 0.3 }
          ],
          expectedReturn: 0.12,
          expectedRisk: 0.15
        }
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <PortfolioOptimization />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });
  });

  describe("Advanced Analysis Pages", () => {
    it("should render EconomicModeling with economic data", async () => {
      mockDataService.fetchData.mockResolvedValue({
        economicIndicators: {
          gdp: { current: 2.1, forecast: 2.3 },
          inflation: { current: 3.2, forecast: 2.8 },
          unemployment: { current: 3.7, forecast: 3.5 },
          interestRates: { current: 5.25, forecast: 5.0 }
        },
        correlations: [
          { indicator: "GDP", correlation: 0.65 },
          { indicator: "Inflation", correlation: -0.45 }
        ]
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <EconomicModeling />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });

    it("should render PatternRecognition with pattern data", async () => {
      mockDataService.fetchData.mockResolvedValue({
        patterns: [
          {
            symbol: "AAPL",
            pattern: "Head and Shoulders",
            confidence: 0.85,
            prediction: "bearish",
            targetPrice: 165.00
          },
          {
            symbol: "MSFT",
            pattern: "Bull Flag",
            confidence: 0.72,
            prediction: "bullish",
            targetPrice: 410.00
          }
        ]
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <PatternRecognition />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });

    it("should render Backtest with backtesting results", async () => {
      mockDataService.fetchData.mockResolvedValue({
        backtestResults: {
          strategy: "Mean Reversion",
          startDate: "2023-01-01",
          endDate: "2024-01-01",
          totalReturn: 0.25,
          annualizedReturn: 0.25,
          maxDrawdown: -0.12,
          sharpeRatio: 1.45,
          winRate: 0.68,
          trades: 156,
          avgWin: 0.024,
          avgLoss: -0.018
        }
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <Backtest />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });
    });
  });

  describe("Chart Component Integration", () => {
    it("should render HistoricalPriceChart with price data", async () => {
      const chartData = [
        { date: "2024-01-01", open: 170, high: 175, low: 168, close: 174, volume: 50000000 },
        { date: "2024-01-02", open: 174, high: 178, low: 172, close: 176, volume: 45000000 },
        { date: "2024-01-03", open: 176, high: 180, low: 175, close: 179, volume: 55000000 }
      ];

      render(
        <TestWrapper>
          <HistoricalPriceChart 
            symbol="AAPL" 
            data={chartData}
            timeframe="1D"
          />
        </TestWrapper>
      );

      // Chart should render without crashing
      expect(screen.getByRole("main") || document.querySelector('svg')).toBeInTheDocument();
    });

    it("should render ProfessionalChart with technical indicators", async () => {
      const chartData = {
        prices: [
          { date: "2024-01-01", price: 174 },
          { date: "2024-01-02", price: 176 },
          { date: "2024-01-03", price: 179 }
        ],
        indicators: {
          sma20: [172, 174, 176],
          sma50: [170, 171, 173],
          rsi: [65, 68, 72],
          macd: [1.2, 1.5, 1.8]
        }
      };

      render(
        <TestWrapper>
          <ProfessionalChart 
            symbol="AAPL" 
            data={chartData}
            indicators={["SMA", "RSI", "MACD"]}
          />
        </TestWrapper>
      );

      // Chart should render without crashing
      expect(screen.getByRole("main") || document.querySelector('svg')).toBeInTheDocument();
    });
  });

  describe("User Interaction with Financial Features", () => {
    it("should handle order placement", async () => {
      const user = userEvent.setup();
      
      mockApi.post.mockResolvedValue({
        data: { 
          orderId: "ORD003",
          status: "submitted",
          message: "Order placed successfully"
        }
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <OrderManagement />
          </BrowserRouter>
        </TestWrapper>
      );

      // Look for order form elements
      const _buyButton = screen.queryByRole("button", { name: /buy/i });
      const _sellButton = screen.queryByRole("button", { name: /sell/i });
      const submitButton = screen.queryByRole("button", { name: /submit/i }) ||
                          screen.queryByRole("button", { name: /place order/i });

      if (submitButton) {
        await user.click(submitButton);
        
        await waitFor(() => {
          expect(mockApi.post).toHaveBeenCalled();
        }, { timeout: 5000 });
      }
    });

    it("should handle portfolio rebalancing", async () => {
      const user = userEvent.setup();
      
      mockApi.post.mockResolvedValue({
        data: { 
          success: true,
          message: "Portfolio rebalancing initiated"
        }
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <PortfolioOptimization />
          </BrowserRouter>
        </TestWrapper>
      );

      const rebalanceButton = screen.queryByRole("button", { name: /rebalance/i }) ||
                             screen.queryByRole("button", { name: /optimize/i });

      if (rebalanceButton) {
        await user.click(rebalanceButton);
        
        await waitFor(() => {
          expect(mockApi.post).toHaveBeenCalled();
        }, { timeout: 5000 });
      }
    });

    it("should handle backtest execution", async () => {
      const user = userEvent.setup();
      
      mockApi.post.mockResolvedValue({
        data: { 
          backtestId: "BT001",
          status: "running",
          estimatedTime: 300
        }
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <Backtest />
          </BrowserRouter>
        </TestWrapper>
      );

      const runButton = screen.queryByRole("button", { name: /run/i }) ||
                       screen.queryByRole("button", { name: /start/i });

      if (runButton) {
        await user.click(runButton);
        
        await waitFor(() => {
          expect(mockApi.post).toHaveBeenCalled();
        }, { timeout: 5000 });
      }
    });
  });

  describe("Data Validation and Error Handling", () => {
    it("should handle invalid financial data gracefully", async () => {
      mockDataService.fetchData.mockResolvedValue({
        financials: {
          symbol: "INVALID",
          revenue: null,
          netIncome: undefined,
          eps: "N/A"
        }
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <FinancialData />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });

      // Should handle invalid data without crashing
      expect(screen.getByRole("main") || screen.getByTestId("error-boundary")).toBeInTheDocument();
    });

    it("should handle API timeout scenarios", async () => {
      mockDataService.fetchData.mockImplementation(() => {
        return new Promise((_, reject) => {
          setTimeout(() => reject(new Error("Request timeout")), 100);
        });
      });

      render(
        <TestWrapper>
          <BrowserRouter>
            <MetricsDashboard />
          </BrowserRouter>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(mockDataService.fetchData).toHaveBeenCalled();
      }, { timeout: 5000 });

      // Should handle timeout gracefully
      expect(screen.getByRole("main") || screen.getByTestId("error-boundary")).toBeInTheDocument();
    });
  });
});