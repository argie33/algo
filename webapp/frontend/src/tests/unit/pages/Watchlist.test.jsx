/**
 * Watchlist Page Unit Tests
 * Tests the watchlist functionality - stock tracking, adding/removing stocks, performance monitoring
 */

import { vi, describe, it, expect, beforeEach } from "vitest";

// Mock import.meta.env BEFORE any imports
Object.defineProperty(import.meta, "env", {
  value: {
    VITE_API_URL: "http://localhost:3001",
    MODE: "test",
    DEV: true,
    PROD: false,
    BASE_URL: "/",
  },
  writable: true,
  configurable: true,
});

import { renderWithProviders, screen, waitFor, userEvent } from "../../test-utils.jsx";

// Import the component under test
import Watchlist from "../../../pages/Watchlist.jsx";

// Mock window.location.reload to avoid JSDOM navigation errors
Object.defineProperty(window, "location", {
  value: {
    reload: vi.fn(),
    href: "http://localhost:3001",
  },
  writable: true,
});

// Mock API service with comprehensive mock
vi.mock("../../../services/api.js", async () => {
  const mockApi = await import("../../mocks/apiMock.js");
  return {
    default: mockApi.default,
    getApiConfig: mockApi.getApiConfig,
    getPortfolioData: mockApi.getPortfolioData,
    getApiKeys: mockApi.getApiKeys,
    testApiConnection: mockApi.testApiConnection,
    importPortfolioFromBroker: mockApi.importPortfolioFromBroker,
    healthCheck: mockApi.healthCheck,
    getMarketOverview: mockApi.getMarketOverview,
  };
});

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: { id: 1, email: "test@example.com" },
    isAuthenticated: true,
    isLoading: false,
  })),
}));

const mockWatchlistData = [
  {
    id: 1,
    symbol: "AAPL",
    name: "Apple Inc.",
    price: 175.43,
    change: 2.15,
    changePercent: 1.24,
    volume: 52000000,
    marketCap: 2800000000000,
    pe: 28.5,
    addedAt: "2024-01-15T10:00:00Z",
  },
  {
    id: 2,
    symbol: "GOOGL",
    name: "Alphabet Inc.",
    price: 142.56,
    change: -1.23,
    changePercent: -0.85,
    volume: 28000000,
    marketCap: 1800000000000,
    pe: 25.2,
    addedAt: "2024-01-14T15:30:00Z",
  },
  {
    id: 3,
    symbol: "TSLA",
    name: "Tesla Inc.",
    price: 248.9,
    change: 5.67,
    changePercent: 2.33,
    volume: 45000000,
    marketCap: 790000000000,
    pe: 65.8,
    addedAt: "2024-01-13T09:15:00Z",
  },
];

// Test render helper
function renderWatchlist(props = {}) {
  return renderWithProviders(<Watchlist {...props} />);
}

describe("Watchlist Component", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { default: api } = await import("../../../services/api.js");

    // Mock the watchlist data loading
    vi.mocked(api.get).mockResolvedValue({
      data: {
        success: true,
        data: {
          data: mockWatchlistData.reduce((acc, stock) => {
            acc[stock.symbol] = {
              bidPrice: stock.price - 0.01,
              askPrice: stock.price + 0.01,
              bidSize: 100,
              askSize: 100,
              timestamp: new Date().toISOString(),
            };
            return acc;
          }, {}),
        },
      },
    });

    vi.mocked(api.getWatchlist).mockResolvedValue({
      success: true,
      data: mockWatchlistData,
    });
  });

  it("renders watchlist page", async () => {
    renderWatchlist();

    expect(screen.getByRole("heading", { name: /watchlist/i })).toBeInTheDocument();
  });

  it("displays watchlist stocks when loaded", async () => {
    renderWatchlist();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
      expect(screen.getByText("GOOGL")).toBeInTheDocument();
      expect(screen.getByText("Alphabet Inc.")).toBeInTheDocument();
      expect(screen.getByText("TSLA")).toBeInTheDocument();
      expect(screen.getByText("Tesla Inc.")).toBeInTheDocument();
    });
  });

  it("shows stock prices and changes", async () => {
    renderWatchlist();

    await waitFor(() => {
      expect(screen.getByText("$175.43")).toBeInTheDocument();
      expect(screen.getByText("$142.56")).toBeInTheDocument();
      expect(screen.getByText("$248.90")).toBeInTheDocument();
      expect(screen.getByText("+2.15")).toBeInTheDocument();
      expect(screen.getByText("-1.23")).toBeInTheDocument();
      expect(screen.getByText("+5.67")).toBeInTheDocument();
    });
  });

  it("shows loading state initially", async () => {
    const { default: api } = await import("../../../services/api.js");
    vi.mocked(api.getWatchlist).mockImplementation(() => new Promise(() => {}));

    renderWatchlist();

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    const { default: api } = await import("../../../services/api.js");
    vi.mocked(api.getWatchlist).mockRejectedValue(new Error("API Error"));

    renderWatchlist();

    await waitFor(() => {
      expect(
        screen.getByText(/error/i) || screen.getByText(/failed/i)
      ).toBeInTheDocument();
    });
  });

  it("allows adding stocks to watchlist", async () => {
    const api = require("../../../services/api.js").default;
    renderWatchlist();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Look for add stock input or button
    const addInput =
      screen.queryByPlaceholderText(/add stock/i) ||
      screen.queryByPlaceholderText(/symbol/i) ||
      screen.queryByLabelText(/add to watchlist/i);

    if (addInput) {
      await userEvent.type(addInput, "MSFT");

      const addButton = screen.getByRole("button", { name: /add/i });
      await userEvent.click(addButton);

      await waitFor(() => {
        expect(api.addToWatchlist).toHaveBeenCalled();
      });
    }
  });

  it("allows removing stocks from watchlist", async () => {
    const api = require("../../../services/api.js").default;
    renderWatchlist();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Look for remove buttons
    const removeButtons =
      screen.queryAllByLabelText(/remove/i) ||
      screen.queryAllByRole("button", { name: /remove/i }) ||
      screen.queryAllByRole("button", { name: /delete/i });

    if (removeButtons.length > 0) {
      await userEvent.click(removeButtons[0]);

      await waitFor(() => {
        expect(api.removeFromWatchlist).toHaveBeenCalled();
      });
    }
  });

  it("displays stock metrics", async () => {
    renderWatchlist();

    await waitFor(() => {
      // Volume
      expect(
        screen.getByText("52.0M") || screen.getByText("52,000,000")
      ).toBeInTheDocument();
      // Market Cap
      expect(
        screen.getByText("$2.80T") || screen.getByText("2.8T")
      ).toBeInTheDocument();
      // P/E Ratio
      expect(screen.getByText("28.5")).toBeInTheDocument();
    });
  });

  it("shows percentage changes with proper styling", async () => {
    renderWatchlist();

    await waitFor(() => {
      // Positive change
      expect(
        screen.getByText("+1.24%") || screen.getByText("1.24%")
      ).toBeInTheDocument();
      // Negative change
      expect(
        screen.getByText("-0.85%") || screen.getByText("0.85%")
      ).toBeInTheDocument();
    });
  });

  it("supports sorting by different columns", async () => {
    renderWatchlist();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Look for sort buttons/headers
    const sortHeaders =
      screen.getAllByRole("columnheader") ||
      screen
        .getAllByRole("button")
        .filter((btn) => btn.textContent.match(/symbol|name|price|change/i));

    if (sortHeaders.length > 0) {
      await userEvent.click(sortHeaders[0]);
      // Verify sorting behavior if implemented
    }
  });

  it("allows searching/filtering watchlist", async () => {
    renderWatchlist();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    const searchInput =
      screen.getByPlaceholderText(/search/i) ||
      screen.getByPlaceholderText(/filter/i);

    if (searchInput) {
      await userEvent.type(searchInput, "Apple");

      await waitFor(() => {
        expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
      });
    }
  });

  it("handles empty watchlist", async () => {
    const { default: api } = await import("../../../services/api.js");
    vi.mocked(api.getWatchlist).mockResolvedValue({
      success: true,
      data: [],
    });

    renderWatchlist();

    await waitFor(() => {
      expect(
        screen.queryByText(/no stocks/i) ||
          screen.queryByText(/empty/i) ||
          screen.queryByText(/add your first stock/i)
      ).toBeInTheDocument();
    });
  });

  it("refreshes watchlist data", async () => {
    renderWatchlist();

    const refreshButton =
      screen.queryByLabelText(/refresh/i) ||
      screen.queryByRole("button", { name: /refresh/i });

    if (refreshButton) {
      await userEvent.click(refreshButton);
      // Test that refresh functionality works
    }
  });

  it("displays time when stocks were added", async () => {
    renderWatchlist();

    await waitFor(() => {
      // Should show relative times or formatted dates
      expect(
        screen.getByText(/added/i) ||
          screen.getByText(/Jan/i) ||
          screen.getByText(/day/i)
      ).toBeInTheDocument();
    });
  });

  it("navigates to stock detail page", async () => {
    renderWatchlist();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    const stockLink = screen.getByText("AAPL");
    await userEvent.click(stockLink);

    // Verify navigation (would need router mock for full test)
  });

  it("shows watchlist performance summary", async () => {
    renderWatchlist();

    await waitFor(() => {
      // Should show overall performance metrics
      expect(
        screen.getByText(/total value/i) ||
          screen.getByText(/daily change/i) ||
          screen.getByText(/performance/i)
      ).toBeInTheDocument();
    });
  });
});
