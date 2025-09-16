/**
 * TradeHistory Page Unit Tests
 * Tests the trade history functionality - trade listing, filtering, performance analysis
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  renderWithProviders,
  screen,
  waitFor,
  createMockUser,
  fireEvent,
  userEvent,
} from "../../test-utils.jsx";
import TradeHistory from "../../../pages/TradeHistory.jsx";

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
  })),
}));

// Mock React Router
vi.mock("react-router-dom", () => ({
  useNavigate: vi.fn(() => vi.fn()),
}));

// Mock API service
vi.mock("../../../services/api.js", () => ({
  api: {
    getTradeHistory: vi.fn(),
    getTradePerformance: vi.fn(),
    getTradingSummary: vi.fn(),
    exportTrades: vi.fn(),
    uploadTrades: vi.fn(),
  },
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    environment: "test",
  })),
}));

const mockTrades = [
  {
    id: 1,
    symbol: "AAPL",
    type: "buy",
    quantity: 100,
    price: 150.5,
    date: "2024-01-15T10:30:00Z",
    amount: 15050.0,
    commission: 1.0,
    status: "filled",
    strategy: "Value Investing",
  },
  {
    id: 2,
    symbol: "AAPL",
    type: "sell",
    quantity: 50,
    price: 175.25,
    date: "2024-01-20T14:15:00Z",
    amount: 8762.5,
    commission: 1.0,
    status: "filled",
    strategy: "Profit Taking",
  },
  {
    id: 3,
    symbol: "GOOGL",
    type: "buy",
    quantity: 25,
    price: 2500.0,
    date: "2024-01-10T09:45:00Z",
    amount: 62500.0,
    commission: 2.5,
    status: "filled",
    strategy: "Growth Investing",
  },
];

const mockPerformance = {
  totalTrades: 50,
  winningTrades: 32,
  losingTrades: 18,
  winRate: 64.0,
  totalProfit: 12500.75,
  totalLoss: -3250.25,
  netProfit: 9250.5,
  averageWin: 390.65,
  averageLoss: -180.57,
  profitFactor: 3.85,
  sharpeRatio: 1.42,
};

describe("TradeHistory Component", () => {
  const { api } = require("../../../services/api.js");

  beforeEach(() => {
    vi.clearAllMocks();
    api.getTradeHistory.mockResolvedValue({
      success: true,
      data: mockTrades,
    });
    api.getTradePerformance.mockResolvedValue({
      success: true,
      data: mockPerformance,
    });
    api.getTradingSummary.mockResolvedValue({
      success: true,
      data: {
        todayTrades: 3,
        weekTrades: 12,
        monthTrades: 45,
      },
    });
  });

  it("renders trade history page", async () => {
    renderWithProviders(<TradeHistory />);

    expect(screen.getByText(/trade history/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(api.getTradeHistory).toHaveBeenCalled();
    });
  });

  it("displays trade list", async () => {
    renderWithProviders(<TradeHistory />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText("GOOGL")).toBeInTheDocument();
      expect(screen.getByText("100")).toBeInTheDocument(); // quantity
      expect(screen.getByText("$150.50")).toBeInTheDocument(); // price
    });
  });

  it("shows buy/sell indicators", async () => {
    renderWithProviders(<TradeHistory />);

    await waitFor(() => {
      expect(screen.getAllByText(/buy/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/sell/i).length).toBeGreaterThan(0);
    });
  });

  it("displays performance metrics", async () => {
    renderWithProviders(<TradeHistory />);

    await waitFor(() => {
      expect(screen.getByText("64.0%")).toBeInTheDocument(); // win rate
      expect(screen.getByText("$9,250.50")).toBeInTheDocument(); // net profit
      expect(screen.getByText("50")).toBeInTheDocument(); // total trades
    });
  });

  it("shows loading state initially", () => {
    api.getTradeHistory.mockImplementation(() => new Promise(() => {}));

    renderWithProviders(<TradeHistory />);

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    api.getTradeHistory.mockRejectedValue(new Error("API Error"));

    renderWithProviders(<TradeHistory />);

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });

  it("filters trades by symbol", async () => {
    renderWithProviders(<TradeHistory />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Look for search/filter input
    const searchInput =
      screen.getByPlaceholderText(/search/i) ||
      screen.getByLabelText(/filter/i);

    if (searchInput) {
      await userEvent.type(searchInput, "AAPL");

      await waitFor(() => {
        // Should filter to show only AAPL trades
        expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
      });
    }
  });

  it("filters trades by date range", async () => {
    renderWithProviders(<TradeHistory />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Look for date filters
    const dateInputs = screen.getAllByDisplayValue(/2024/);
    if (dateInputs.length > 0) {
      // Change date filter
      await userEvent.clear(dateInputs[0]);
      await userEvent.type(dateInputs[0], "2024-01-15");

      await waitFor(() => {
        expect(api.getTradeHistory).toHaveBeenCalledTimes(2);
      });
    }
  });

  it("filters trades by type (buy/sell)", async () => {
    renderWithProviders(<TradeHistory />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Look for type filter dropdown
    const typeSelects = screen.getAllByRole("combobox");
    if (typeSelects.length > 0) {
      fireEvent.mouseDown(typeSelects[0]);

      const buyOption = screen.getByText(/buy/i);
      fireEvent.click(buyOption);

      await waitFor(() => {
        // Should show filtered results
        expect(screen.getAllByText(/buy/i).length).toBeGreaterThan(0);
      });
    }
  });

  it("sorts trades by different columns", async () => {
    renderWithProviders(<TradeHistory />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Click on a sortable column header
    const dateHeader = screen.getByText(/date/i);
    fireEvent.click(dateHeader);

    // Trades should be re-sorted
    await waitFor(() => {
      const rows = screen.getAllByRole("row");
      expect(rows.length).toBeGreaterThan(2);
    });
  });

  it("handles pagination", async () => {
    // Mock large trade history
    const largeTrades = Array.from({ length: 100 }, (_, i) => ({
      id: i + 1,
      symbol: `STOCK${i + 1}`,
      type: i % 2 === 0 ? "buy" : "sell",
      quantity: 10,
      price: 100 + i,
      date: "2024-01-15T10:30:00Z",
      amount: (100 + i) * 10,
      commission: 1.0,
      status: "filled",
    }));

    api.getTradeHistory.mockResolvedValue({
      success: true,
      data: largeTrades,
    });

    renderWithProviders(<TradeHistory />);

    await waitFor(() => {
      expect(screen.getByText("STOCK1")).toBeInTheDocument();
    });

    // Look for pagination controls
    const nextButton = screen.getByLabelText(/next page/i);
    if (nextButton) {
      fireEvent.click(nextButton);

      await waitFor(() => {
        // Should show next page
        expect(screen.getByText("STOCK26")).toBeInTheDocument();
      });
    }
  });

  it("exports trade data", async () => {
    api.exportTrades.mockResolvedValue({
      success: true,
      data: "csv,data,here",
    });

    renderWithProviders(<TradeHistory />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    const exportButton =
      screen.getByLabelText(/export/i) ||
      screen.getByRole("button", { name: /export/i });
    fireEvent.click(exportButton);

    await waitFor(() => {
      expect(api.exportTrades).toHaveBeenCalled();
    });
  });

  it("uploads trade data", async () => {
    api.uploadTrades.mockResolvedValue({
      success: true,
      message: "Trades uploaded successfully",
    });

    renderWithProviders(<TradeHistory />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    const uploadButton =
      screen.getByLabelText(/upload/i) ||
      screen.getByRole("button", { name: /upload/i });
    fireEvent.click(uploadButton);

    // Mock file upload dialog
    await waitFor(() => {
      expect(screen.getByText(/upload/i)).toBeInTheDocument();
    });
  });

  it("refreshes trade data", async () => {
    renderWithProviders(<TradeHistory />);

    await waitFor(() => {
      expect(api.getTradeHistory).toHaveBeenCalledTimes(1);
    });

    const refreshButton = screen.getByLabelText(/refresh/i);
    fireEvent.click(refreshButton);

    await waitFor(() => {
      expect(api.getTradeHistory).toHaveBeenCalledTimes(2);
    });
  });

  it("switches between tabs (trades/performance)", async () => {
    renderWithProviders(<TradeHistory />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Click performance tab
    const performanceTab = screen.getByRole("tab", { name: /performance/i });
    fireEvent.click(performanceTab);

    await waitFor(() => {
      expect(screen.getByText("64.0%")).toBeInTheDocument();
      expect(screen.getByText("Profit Factor")).toBeInTheDocument();
    });
  });

  it("displays trade details in dialog", async () => {
    renderWithProviders(<TradeHistory />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Click on first trade row
    const tradeRows = screen.getAllByRole("row");
    if (tradeRows.length > 1) {
      fireEvent.click(tradeRows[1]); // Skip header row

      await waitFor(() => {
        expect(screen.getByText(/trade details/i)).toBeInTheDocument();
      });
    }
  });

  it("handles empty trade history", async () => {
    api.getTradeHistory.mockResolvedValue({
      success: true,
      data: [],
    });

    renderWithProviders(<TradeHistory />);

    await waitFor(() => {
      expect(
        screen.getByText(/no trades/i) ||
          screen.getByText(/no trading history/i)
      ).toBeInTheDocument();
    });
  });

  it("displays strategy information", async () => {
    renderWithProviders(<TradeHistory />);

    await waitFor(() => {
      expect(screen.getByText("Value Investing")).toBeInTheDocument();
      expect(screen.getByText("Profit Taking")).toBeInTheDocument();
      expect(screen.getByText("Growth Investing")).toBeInTheDocument();
    });
  });

  it("shows commission and fees", async () => {
    renderWithProviders(<TradeHistory />);

    await waitFor(() => {
      expect(screen.getByText("$1.00")).toBeInTheDocument(); // commission
      expect(screen.getByText("$2.50")).toBeInTheDocument(); // commission
    });
  });
});
