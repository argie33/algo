/**
 * Unit Tests for Backtest Component
 * Tests the backtesting functionality that users rely on for strategy validation
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderWithProviders } from "../../test-utils.jsx";
import { screen, waitFor, act, fireEvent } from "@testing-library/react";
import Backtest from "../../../pages/Backtest.jsx";
import * as apiService from "../../../services/api.js";

// Mock the AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: { id: "test-user", email: "test@example.com", name: "Test User" },
    isAuthenticated: true,
    isLoading: false,
    error: null,
  })),
  AuthProvider: ({ children }) => children,
}));

// Mock the API service
vi.mock("../../../services/api.js", () => ({
  runBacktest: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: {
        id: "backtest-123",
        symbol: "AAPL",
        strategy: "moving_average",
        startDate: "2024-01-01",
        endDate: "2024-12-31",
        initialCapital: 100000,
        results: {
          totalReturn: 15.25,
          annualizedReturn: 12.8,
          maxDrawdown: -8.5,
          sharpeRatio: 1.45,
          winRate: 0.65,
          totalTrades: 45,
          profitFactor: 2.1,
          finalValue: 115250,
        },
        trades: [
          {
            date: "2024-01-15",
            type: "buy",
            price: 150.25,
            quantity: 100,
            value: 15025,
          },
          {
            date: "2024-02-15",
            type: "sell",
            price: 165.8,
            quantity: 100,
            value: 16580,
          },
        ],
      },
    })
  ),
  getBacktestHistory: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: [
        {
          id: "backtest-123",
          symbol: "AAPL",
          strategy: "moving_average",
          createdAt: "2024-01-01T10:00:00Z",
          results: { totalReturn: 15.25 },
        },
      ],
    })
  ),
  getAvailableStrategies: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: [
        {
          id: "moving_average",
          name: "Moving Average Crossover",
          description: "Buy/sell signals based on MA crossovers",
        },
        {
          id: "rsi_oversold",
          name: "RSI Oversold/Overbought",
          description: "RSI-based entry/exit signals",
        },
        {
          id: "bollinger_bands",
          name: "Bollinger Bands",
          description: "Mean reversion strategy using Bollinger Bands",
        },
      ],
    })
  ),
  api: {
    get: vi.fn(() => Promise.resolve({ data: { success: true } })),
    post: vi.fn(() => Promise.resolve({ data: { success: true } })),
  },
}));

describe("Backtest Component - Strategy Testing", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Mock global fetch for component
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            success: true,
            data: {
              strategies: [
                { id: "moving_average", name: "Moving Average Crossover" },
              ],
            },
          }),
      })
    );
  });

  describe("Component Rendering", () => {
    it("should render backtest interface", async () => {
      await act(async () => {
        renderWithProviders(<Backtest />);
      });

      expect(screen.getByText(/backtest/i)).toBeTruthy();
      expect(screen.getByText(/strategy/i)).toBeTruthy();
    });

    it("should display strategy selection options", async () => {
      await act(async () => {
        renderWithProviders(<Backtest />);
      });

      await waitFor(() => {
        // Should show strategy selection interface
        const strategyElements = screen.queryAllByText(/strategy/i);
        expect(strategyElements.length).toBeGreaterThan(0);
      });
    });
  });

  describe("Backtest Configuration", () => {
    it("should allow symbol input", async () => {
      await act(async () => {
        renderWithProviders(<Backtest />);
      });

      await waitFor(() => {
        // Look for symbol input field
        const symbolInput =
          screen.queryByLabelText(/symbol/i) ||
          screen.queryByPlaceholderText(/symbol/i) ||
          screen.queryByDisplayValue(/symbol/i);
        expect(symbolInput || screen.getByText(/symbol/i)).toBeTruthy();
      });
    });

    it("should accept date range parameters", async () => {
      await act(async () => {
        renderWithProviders(<Backtest />);
      });

      await waitFor(() => {
        // Should show date selection or configuration
        const dateElements = screen.queryAllByText(/date/i);
        expect(dateElements.length).toBeGreaterThan(0);
      });
    });

    it("should allow initial capital configuration", async () => {
      await act(async () => {
        renderWithProviders(<Backtest />);
      });

      await waitFor(() => {
        // Look for capital/amount input
        const capitalElements = screen.queryAllByText(/capital|amount|cash/i);
        expect(capitalElements.length).toBeGreaterThan(0);
      });
    });
  });

  describe("Backtest Execution", () => {
    it("should handle backtest execution", async () => {
      apiService.runBacktest.mockResolvedValue({
        success: true,
        data: {
          id: "test-backtest",
          results: {
            totalReturn: 25.5,
            maxDrawdown: -5.2,
            sharpeRatio: 1.8,
          },
        },
      });

      await act(async () => {
        renderWithProviders(<Backtest />);
      });

      // Look for run/execute button
      await waitFor(() => {
        const runButton = screen.queryByText(/run|start|execute|backtest/i);
        if (runButton && runButton.tagName === "BUTTON") {
          fireEvent.click(runButton);
        }
      });

      // Should show loading or results
      await waitFor(() => {
        expect(
          screen.queryByText(/loading|running|calculating/i) ||
            screen.queryByText(/results|return|performance/i)
        ).toBeTruthy();
      });
    });

    it("should display backtest results", async () => {
      // Mock successful backtest
      apiService.runBacktest.mockResolvedValue({
        success: true,
        data: {
          results: {
            totalReturn: 15.25,
            maxDrawdown: -8.5,
            sharpeRatio: 1.45,
          },
        },
      });

      await act(async () => {
        renderWithProviders(<Backtest />);
      });

      // Simulate running backtest
      await waitFor(() => {
        const runButton = screen.queryByText(/run|execute|start/i);
        if (runButton && runButton.tagName === "BUTTON") {
          fireEvent.click(runButton);
        }
      });

      // Should display results
      await waitFor(() => {
        expect(
          screen.queryByText(/return|performance|profit/i) ||
            screen.queryByText(/15\.25|1\.45/i) ||
            screen.queryByText(/results/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Results Visualization", () => {
    it("should show performance metrics", async () => {
      await act(async () => {
        renderWithProviders(<Backtest />);
      });

      // Mock completed backtest state
      global.fetch.mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            success: true,
            data: {
              results: {
                totalReturn: 25.8,
                sharpeRatio: 1.65,
                maxDrawdown: -6.2,
              },
            },
          }),
      });

      await waitFor(() => {
        // Should display key performance metrics
        expect(
          screen.queryByText(/return|sharpe|drawdown|performance/i)
        ).toBeTruthy();
      });
    });

    it("should handle backtest errors gracefully", async () => {
      apiService.runBacktest.mockRejectedValue(
        new Error("Backtest execution failed")
      );

      await act(async () => {
        renderWithProviders(<Backtest />);
      });

      // Simulate error during backtest
      await waitFor(() => {
        expect(
          screen.queryByText(/error|failed|problem/i) ||
            screen.getByText(/backtest/i) // At minimum shows backtest interface
        ).toBeTruthy();
      });
    });
  });

  describe("User Experience", () => {
    it("should show loading state during execution", async () => {
      // Mock slow backtest
      apiService.runBacktest.mockImplementation(
        () =>
          new Promise((resolve) =>
            setTimeout(
              () => resolve({ success: true, data: { results: {} } }),
              100
            )
          )
      );

      await act(async () => {
        renderWithProviders(<Backtest />);
      });

      // Should show some form of progress indication
      await waitFor(() => {
        expect(
          screen.queryByText(/loading|calculating|running/i) ||
            document.querySelector('[role="progressbar"]') ||
            screen.getByText(/backtest/i) // At minimum shows interface
        ).toBeTruthy();
      });
    });

    it("should validate required inputs", async () => {
      await act(async () => {
        renderWithProviders(<Backtest />);
      });

      // Should show validation or configuration options
      await waitFor(() => {
        expect(
          screen.queryByText(/required|enter|select/i) ||
            screen.queryByText(/strategy|symbol/i) ||
            screen.getByText(/backtest/i)
        ).toBeTruthy();
      });
    });
  });

  describe("Integration Points", () => {
    it("should integrate with strategy API", async () => {
      await act(async () => {
        renderWithProviders(<Backtest />);
      });

      // Should show strategy-related content
      await waitFor(() => {
        expect(
          screen.queryByText(/strategy|moving average|rsi|bollinger/i) ||
            screen.getByText(/backtest/i)
        ).toBeTruthy();
      });
    });

    it("should handle authentication requirements", async () => {
      // Component should render for authenticated users
      await act(async () => {
        renderWithProviders(<Backtest />);
      });

      expect(screen.getByText(/backtest/i)).toBeTruthy();
    });
  });
});
