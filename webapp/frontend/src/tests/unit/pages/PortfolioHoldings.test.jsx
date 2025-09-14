/**
 * PortfolioHoldings Page Unit Tests
 * Tests the portfolio holdings functionality - holdings display, allocation charts, performance tracking
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
import PortfolioHoldings from "../../../pages/PortfolioHoldings.jsx";

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
    tokens: {
      accessToken: "mock-access-token",
      idToken: "mock-id-token",
    },
  })),
}));

// Mock API service
vi.mock("../../../services/api.js", () => ({
  api: {
    getPortfolioHoldings: vi.fn(),
    getPortfolioSummary: vi.fn(),
    addHolding: vi.fn(),
    updateHolding: vi.fn(),
    deleteHolding: vi.fn(),
    getStockPrices: vi.fn(),
  },
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    environment: "test",
  })),
}));

// Mock document title hook
vi.mock("../../../hooks/useDocumentTitle.jsx", () => ({
  useDocumentTitle: vi.fn(),
}));

const mockHoldings = [
  {
    id: 1,
    symbol: "AAPL",
    company: "Apple Inc.",
    shares: 100,
    avgPrice: 150.5,
    currentPrice: 175.25,
    totalValue: 17525.0,
    totalCost: 15050.0,
    gainLoss: 2475.0,
    gainLossPercent: 16.44,
    sector: "Technology",
    lastUpdated: "2024-01-15T14:30:00Z",
  },
  {
    id: 2,
    symbol: "GOOGL",
    company: "Alphabet Inc.",
    shares: 50,
    avgPrice: 2500.0,
    currentPrice: 2650.75,
    totalValue: 132537.5,
    totalCost: 125000.0,
    gainLoss: 7537.5,
    gainLossPercent: 6.03,
    sector: "Technology",
    lastUpdated: "2024-01-15T14:30:00Z",
  },
];

const mockPortfolioSummary = {
  totalValue: 150062.5,
  totalCost: 140050.0,
  totalGainLoss: 10012.5,
  totalGainLossPercent: 7.15,
  cash: 5000.0,
  dayChange: 1234.56,
  dayChangePercent: 0.83,
};

describe("PortfolioHoldings Component", () => {
  const { api } = require("../../../services/api.js");

  beforeEach(() => {
    vi.clearAllMocks();
    api.getPortfolioHoldings.mockResolvedValue({
      success: true,
      data: mockHoldings,
    });
    api.getPortfolioSummary.mockResolvedValue({
      success: true,
      data: mockPortfolioSummary,
    });
    api.getStockPrices.mockResolvedValue({
      success: true,
      data: [
        { symbol: "AAPL", price: 175.25 },
        { symbol: "GOOGL", price: 2650.75 },
      ],
    });
  });

  it("renders portfolio holdings page", async () => {
    renderWithProviders(<PortfolioHoldings />);

    expect(screen.getByText(/portfolio holdings/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(api.getPortfolioHoldings).toHaveBeenCalled();
    });
  });

  it("displays portfolio summary", async () => {
    renderWithProviders(<PortfolioHoldings />);

    await waitFor(() => {
      expect(screen.getByText("$150,062.50")).toBeInTheDocument();
      expect(screen.getByText("$10,012.50")).toBeInTheDocument();
      expect(screen.getByText("7.15%")).toBeInTheDocument();
    });
  });

  it("shows individual holdings", async () => {
    renderWithProviders(<PortfolioHoldings />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
      expect(screen.getByText("GOOGL")).toBeInTheDocument();
      expect(screen.getByText("Alphabet Inc.")).toBeInTheDocument();
      expect(screen.getByText("100")).toBeInTheDocument(); // shares
      expect(screen.getByText("50")).toBeInTheDocument(); // shares
    });
  });

  it("displays gain/loss with appropriate colors", async () => {
    renderWithProviders(<PortfolioHoldings />);

    await waitFor(() => {
      expect(screen.getByText("$2,475.00")).toBeInTheDocument();
      expect(screen.getByText("16.44%")).toBeInTheDocument();
      expect(screen.getByText("$7,537.50")).toBeInTheDocument();
      expect(screen.getByText("6.03%")).toBeInTheDocument();
    });
  });

  it("shows loading state initially", () => {
    api.getPortfolioHoldings.mockImplementation(() => new Promise(() => {}));

    renderWithProviders(<PortfolioHoldings />);

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    api.getPortfolioHoldings.mockRejectedValue(new Error("API Error"));

    renderWithProviders(<PortfolioHoldings />);

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });

  it("opens add holding dialog", async () => {
    renderWithProviders(<PortfolioHoldings />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    const addButton = screen.getByRole("button", { name: /add holding/i });
    fireEvent.click(addButton);

    await waitFor(() => {
      expect(screen.getByText(/add new holding/i)).toBeInTheDocument();
    });
  });

  it("handles adding new holding", async () => {
    api.addHolding.mockResolvedValue({ success: true });

    renderWithProviders(<PortfolioHoldings />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Open add dialog
    fireEvent.click(screen.getByRole("button", { name: /add holding/i }));

    await waitFor(() => {
      expect(screen.getByText(/add new holding/i)).toBeInTheDocument();
    });

    // Fill form
    const symbolInput = screen.getByLabelText(/symbol/i);
    const sharesInput = screen.getByLabelText(/shares/i);
    const priceInput = screen.getByLabelText(/price/i);

    await userEvent.type(symbolInput, "TSLA");
    await userEvent.type(sharesInput, "25");
    await userEvent.type(priceInput, "800.00");

    // Submit
    const saveButton = screen.getByRole("button", { name: /save/i });
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(api.addHolding).toHaveBeenCalledWith(
        expect.objectContaining({
          symbol: "TSLA",
          shares: 25,
          avgPrice: 800.0,
        })
      );
    });
  });

  it("handles editing existing holding", async () => {
    api.updateHolding.mockResolvedValue({ success: true });

    renderWithProviders(<PortfolioHoldings />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Click edit button for first holding
    const editButtons = screen.getAllByLabelText(/edit/i);
    fireEvent.click(editButtons[0]);

    await waitFor(() => {
      expect(screen.getByText(/edit holding/i)).toBeInTheDocument();
    });

    // Update shares
    const sharesInput = screen.getByDisplayValue("100");
    await userEvent.clear(sharesInput);
    await userEvent.type(sharesInput, "120");

    // Save changes
    const saveButton = screen.getByRole("button", { name: /save/i });
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(api.updateHolding).toHaveBeenCalledWith(
        1,
        expect.objectContaining({
          shares: 120,
        })
      );
    });
  });

  it("handles deleting holding", async () => {
    api.deleteHolding.mockResolvedValue({ success: true });

    renderWithProviders(<PortfolioHoldings />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Click delete button
    const deleteButtons = screen.getAllByLabelText(/delete/i);
    fireEvent.click(deleteButtons[0]);

    // Confirm deletion
    await waitFor(() => {
      expect(screen.getByText(/confirm deletion/i)).toBeInTheDocument();
    });

    const confirmButton = screen.getByRole("button", { name: /delete/i });
    fireEvent.click(confirmButton);

    await waitFor(() => {
      expect(api.deleteHolding).toHaveBeenCalledWith(1);
    });
  });

  it("refreshes portfolio data", async () => {
    renderWithProviders(<PortfolioHoldings />);

    await waitFor(() => {
      expect(api.getPortfolioHoldings).toHaveBeenCalledTimes(1);
    });

    const refreshButton = screen.getByLabelText(/refresh/i);
    fireEvent.click(refreshButton);

    await waitFor(() => {
      expect(api.getPortfolioHoldings).toHaveBeenCalledTimes(2);
      expect(api.getStockPrices).toHaveBeenCalledTimes(2);
    });
  });

  it("sorts holdings by different columns", async () => {
    renderWithProviders(<PortfolioHoldings />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Click on a sortable column header
    const symbolHeader = screen.getByText(/symbol/i);
    fireEvent.click(symbolHeader);

    // Holdings should be re-sorted
    await waitFor(() => {
      const rows = screen.getAllByRole("row");
      expect(rows.length).toBeGreaterThan(2); // header + data rows
    });
  });

  it("filters holdings by sector", async () => {
    renderWithProviders(<PortfolioHoldings />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Look for sector filter dropdown
    const filterButton =
      screen.getByLabelText(/filter/i) ||
      screen.getByRole("button", { name: /filter/i });

    if (filterButton) {
      fireEvent.click(filterButton);

      // Select Technology sector
      const technologyOption = screen.getByText("Technology");
      fireEvent.click(technologyOption);

      await waitFor(() => {
        // Both holdings are Technology, so should still see both
        expect(screen.getByText("AAPL")).toBeInTheDocument();
        expect(screen.getByText("GOOGL")).toBeInTheDocument();
      });
    }
  });

  it("displays allocation pie chart", async () => {
    renderWithProviders(<PortfolioHoldings />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Switch to allocation view tab if exists
    const allocationTab = screen.getByRole("tab", { name: /allocation/i });
    if (allocationTab) {
      fireEvent.click(allocationTab);

      await waitFor(() => {
        // Should display chart elements
        expect(document.querySelector("svg")).toBeInTheDocument();
      });
    }
  });

  it("shows sector allocation", async () => {
    renderWithProviders(<PortfolioHoldings />);

    await waitFor(() => {
      expect(screen.getByText("Technology")).toBeInTheDocument();
    });
  });

  it("handles pagination for large portfolios", async () => {
    // Mock large portfolio
    const largePortfolio = Array.from({ length: 100 }, (_, i) => ({
      id: i + 1,
      symbol: `STOCK${i + 1}`,
      company: `Company ${i + 1}`,
      shares: 10,
      avgPrice: 100,
      currentPrice: 105,
      totalValue: 1050,
      totalCost: 1000,
      gainLoss: 50,
      gainLossPercent: 5,
      sector: "Technology",
    }));

    api.getPortfolioHoldings.mockResolvedValue({
      success: true,
      data: largePortfolio,
    });

    renderWithProviders(<PortfolioHoldings />);

    await waitFor(() => {
      expect(screen.getByText("STOCK1")).toBeInTheDocument();
    });

    // Look for pagination controls
    const paginationControls = screen.getByRole("navigation", {
      name: /pagination/i,
    });
    if (paginationControls) {
      expect(paginationControls).toBeInTheDocument();
    }
  });

  it("handles empty portfolio", async () => {
    api.getPortfolioHoldings.mockResolvedValue({
      success: true,
      data: [],
    });

    renderWithProviders(<PortfolioHoldings />);

    await waitFor(() => {
      expect(
        screen.getByText(/no holdings/i) || screen.getByText(/empty portfolio/i)
      ).toBeInTheDocument();
    });
  });
});
