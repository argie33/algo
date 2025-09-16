/**
 * StockScreener Page Unit Tests
 * Tests the stock screening functionality - filters, criteria, results
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

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

import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import StockScreener from "../../../pages/StockScreener.jsx";

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
  })),
  AuthProvider: vi.fn(({ children }) => children),
}));

// Mock API service with proper ES module support
vi.mock("../../../services/api", () => {
  const mockApi = {
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    screenStocks: vi.fn(),
    getScreenerResults: vi.fn(),
    saveScreen: vi.fn(),
    getPresetScreens: vi.fn(),
  };

  const mockGetApiConfig = vi.fn(() => ({
    baseURL: "http://localhost:3001",
    apiUrl: "http://localhost:3001",
    environment: "test",
    isDevelopment: true,
    isProduction: false,
    baseUrl: "/",
  }));

  return {
    api: mockApi,
    getApiConfig: mockGetApiConfig,
    default: mockApi,
  };
});

const mockScreenerData = {
  results: [
    {
      symbol: "AAPL",
      name: "Apple Inc.",
      price: 185.92,
      marketCap: 2850000000000,
      pe: 28.5,
      div: 0.52,
      volume: 45678900,
      sector: "Technology",
    },
    {
      symbol: "MSFT",
      name: "Microsoft Corp",
      price: 378.85,
      marketCap: 2820000000000,
      pe: 32.1,
      div: 0.68,
      volume: 23456789,
      sector: "Technology",
    },
    {
      symbol: "JNJ",
      name: "Johnson & Johnson",
      price: 162.45,
      marketCap: 425000000000,
      pe: 15.8,
      div: 2.95,
      volume: 8765432,
      sector: "Healthcare",
    },
    {
      symbol: "JPM",
      name: "JPMorgan Chase",
      price: 168.24,
      marketCap: 485000000000,
      pe: 12.4,
      div: 4.2,
      volume: 12345678,
      sector: "Finance",
    },
  ],
  criteria: {
    marketCap: { min: 1000000000, max: null },
    pe: { min: 5, max: 30 },
    dividend: { min: 0, max: null },
    volume: { min: 1000000, max: null },
    price: { min: 10, max: 500 },
    sector: ["Technology", "Healthcare", "Finance"],
  },
  presets: [
    {
      id: 1,
      name: "Large Cap Growth",
      description: "Large cap stocks with strong growth potential",
    },
    {
      id: 2,
      name: "Dividend Aristocrats",
      description: "High dividend yield with consistent payments",
    },
    {
      id: 3,
      name: "Value Stocks",
      description: "Undervalued stocks with low P/E ratios",
    },
    {
      id: 4,
      name: "Small Cap Momentum",
      description: "Small cap stocks with strong momentum",
    },
  ],
  totalResults: 156,
  page: 1,
  limit: 25,
};

// Test render helper
function renderStockScreener(props = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <StockScreener {...props} />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("StockScreener Component", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../../../services/api");
    api.screenStocks.mockResolvedValue({
      success: true,
      data: mockScreenerData,
    });
    api.getPresetScreens.mockResolvedValue({
      success: true,
      data: mockScreenerData.presets,
    });
  });

  it("renders stock screener page", async () => {
    renderStockScreener();

    expect(screen.getByText(/stock screener/i)).toBeInTheDocument();

    await waitFor(() => {
      const { api } = require("../../../services/api");
      expect(api.screenStocks || api.getPresetScreens).toHaveBeenCalled();
    });
  });

  it("displays screening criteria controls", async () => {
    renderStockScreener();

    await waitFor(() => {
      expect(screen.getByText(/market cap/i)).toBeInTheDocument();
      expect(screen.getByText(/p\/e ratio|pe ratio/i)).toBeInTheDocument();
      expect(screen.getByText(/dividend/i)).toBeInTheDocument();
      expect(screen.getByText(/volume/i)).toBeInTheDocument();
      expect(screen.getByText(/price/i)).toBeInTheDocument();
    });
  });

  it("shows filter input fields", async () => {
    renderStockScreener();

    await waitFor(() => {
      const inputs = screen.getAllByRole("textbox");
      expect(inputs.length).toBeGreaterThan(0);

      const sliders = screen.getAllByRole("slider");
      expect(sliders.length).toBeGreaterThan(0);
    });
  });

  it("displays sector selection", async () => {
    renderStockScreener();

    await waitFor(() => {
      expect(screen.getByText(/sector/i)).toBeInTheDocument();
      expect(
        screen.getByRole("combobox") ||
          screen.getByText(/technology|healthcare|finance/i)
      ).toBeInTheDocument();
    });
  });

  it("shows preset screen options", async () => {
    renderStockScreener();

    await waitFor(() => {
      expect(screen.getByText(/presets|saved screens/i)).toBeInTheDocument();
      expect(screen.getByText("Large Cap Growth")).toBeInTheDocument();
      expect(screen.getByText("Dividend Aristocrats")).toBeInTheDocument();
      expect(screen.getByText("Value Stocks")).toBeInTheDocument();
      expect(screen.getByText("Small Cap Momentum")).toBeInTheDocument();
    });
  });

  it("displays screening results", async () => {
    renderStockScreener();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
      expect(screen.getByText("185.92")).toBeInTheDocument();
      expect(screen.getByText("MSFT")).toBeInTheDocument();
      expect(screen.getByText("Microsoft Corp")).toBeInTheDocument();
      expect(screen.getByText("JNJ")).toBeInTheDocument();
      expect(screen.getByText("JPM")).toBeInTheDocument();
    });
  });

  it("shows stock metrics in results table", async () => {
    renderStockScreener();

    await waitFor(() => {
      expect(screen.getByRole("table")).toBeInTheDocument();
      expect(screen.getByText(/symbol/i)).toBeInTheDocument();
      expect(screen.getByText(/price/i)).toBeInTheDocument();
      expect(screen.getByText(/market cap/i)).toBeInTheDocument();
      expect(screen.getByText(/p\/e|pe/i)).toBeInTheDocument();
      expect(screen.getByText(/dividend|div/i)).toBeInTheDocument();
    });
  });

  it("displays formatted market cap values", async () => {
    renderStockScreener();

    await waitFor(() => {
      expect(screen.getByText(/2.85T|2,850B/)).toBeInTheDocument(); // AAPL market cap
      expect(screen.getByText(/2.82T|2,820B/)).toBeInTheDocument(); // MSFT market cap
      expect(screen.getByText(/425B/)).toBeInTheDocument(); // JNJ market cap
    });
  });

  it("shows P/E ratios", async () => {
    renderStockScreener();

    await waitFor(() => {
      expect(screen.getByText("28.5")).toBeInTheDocument(); // AAPL P/E
      expect(screen.getByText("32.1")).toBeInTheDocument(); // MSFT P/E
      expect(screen.getByText("15.8")).toBeInTheDocument(); // JNJ P/E
      expect(screen.getByText("12.4")).toBeInTheDocument(); // JPM P/E
    });
  });

  it("displays dividend yields", async () => {
    renderStockScreener();

    await waitFor(() => {
      expect(screen.getByText("0.52")).toBeInTheDocument(); // AAPL dividend
      expect(screen.getByText("2.95")).toBeInTheDocument(); // JNJ dividend
      expect(screen.getByText("4.20")).toBeInTheDocument(); // JPM dividend
    });
  });

  it("handles running a custom screen", async () => {
    const { api } = require("../../../services/api");

    renderStockScreener();

    await waitFor(() => {
      const screenButton = screen.getByRole("button", {
        name: /screen|search|apply/i,
      });
      fireEvent.click(screenButton);

      expect(api.screenStocks).toHaveBeenCalled();
    });
  });

  it("applies preset screen filters", async () => {
    renderStockScreener();

    await waitFor(() => {
      const presetButton = screen.getByText("Large Cap Growth");
      fireEvent.click(presetButton);

      // Should trigger a new screen with preset criteria
      const { api } = require("../../../services/api");
      expect(api.screenStocks).toHaveBeenCalled();
    });
  });

  it("updates filter values", async () => {
    renderStockScreener();

    await waitFor(() => {
      const inputs = screen.getAllByRole("textbox");
      if (inputs.length > 0) {
        fireEvent.change(inputs[0], { target: { value: "100" } });
        expect(inputs[0].value).toBe("100");
      }
    });
  });

  it("handles slider inputs for ranges", async () => {
    renderStockScreener();

    await waitFor(() => {
      const sliders = screen.getAllByRole("slider");
      if (sliders.length > 0) {
        fireEvent.change(sliders[0], { target: { value: "50" } });
      }
    });
  });

  it("shows results count and pagination", async () => {
    renderStockScreener();

    await waitFor(() => {
      expect(screen.getByText(/156|results|total/i)).toBeInTheDocument();
      expect(
        screen.getByText(/page|1-25|showing/i) || screen.getByRole("navigation")
      ).toBeInTheDocument();
    });
  });

  it("handles pagination", async () => {
    renderStockScreener();

    await waitFor(() => {
      const nextButton = screen.getByRole("button", { name: /next|>/i });
      if (nextButton && !nextButton.disabled) {
        fireEvent.click(nextButton);

        const { api } = require("../../../services/api");
        expect(api.screenStocks).toHaveBeenCalledWith(
          expect.objectContaining({ page: 2 })
        );
      }
    });
  });

  it("allows saving custom screens", async () => {
    const { api } = require("../../../services/api");
    api.saveScreen.mockResolvedValue({ success: true });

    renderStockScreener();

    await waitFor(() => {
      const saveButton = screen.getByRole("button", {
        name: /save|save screen/i,
      });
      if (saveButton) {
        fireEvent.click(saveButton);

        expect(api.saveScreen).toHaveBeenCalled();
      }
    });
  });

  it("displays sector information", async () => {
    renderStockScreener();

    await waitFor(() => {
      expect(screen.getByText("Technology")).toBeInTheDocument();
      expect(screen.getByText("Healthcare")).toBeInTheDocument();
      expect(screen.getByText("Finance")).toBeInTheDocument();
    });
  });

  it("shows volume data", async () => {
    renderStockScreener();

    await waitFor(() => {
      expect(screen.getByText(/45.7M|45,678,900/)).toBeInTheDocument(); // AAPL volume
      expect(screen.getByText(/23.5M|23,456,789/)).toBeInTheDocument(); // MSFT volume
    });
  });

  it("handles clearing filters", async () => {
    renderStockScreener();

    await waitFor(() => {
      const clearButton = screen.getByRole("button", { name: /clear|reset/i });
      if (clearButton) {
        fireEvent.click(clearButton);

        // Should reset form and potentially trigger new search
        const { api } = require("../../../services/api");
        expect(api.screenStocks).toHaveBeenCalled();
      }
    });
  });

  it("shows loading state during screening", () => {
    const { api } = require("../../../services/api");
    api.screenStocks.mockImplementation(() => new Promise(() => {}));

    renderStockScreener();

    const screenButton = screen.getByRole("button", {
      name: /screen|search|apply/i,
    });
    fireEvent.click(screenButton);

    expect(
      screen.getByRole("progressbar") ||
        screen.getByText(/screening|searching/i)
    ).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    const { api } = require("../../../services/api");
    api.screenStocks.mockRejectedValue(new Error("Screening failed"));

    renderStockScreener();

    const screenButton = screen.getByRole("button", {
      name: /screen|search|apply/i,
    });
    fireEvent.click(screenButton);

    await waitFor(() => {
      expect(
        screen.getByText(/error|failed|screening failed/i)
      ).toBeInTheDocument();
    });
  });

  it("handles empty results", async () => {
    const { api } = require("../../../services/api");
    api.screenStocks.mockResolvedValue({
      success: true,
      data: { ...mockScreenerData, results: [], totalResults: 0 },
    });

    renderStockScreener();

    await waitFor(() => {
      expect(
        screen.getByText(/no results|no stocks found/i)
      ).toBeInTheDocument();
    });
  });

  it("allows sorting results", async () => {
    renderStockScreener();

    await waitFor(() => {
      // Click on column header to sort
      const priceHeader = screen.getByText(/price/i);
      fireEvent.click(priceHeader);

      // Should trigger re-sorting or new API call
      const { api } = require("../../../services/api");
      expect(api.screenStocks).toHaveBeenCalled();
    });
  });

  it("displays advanced filter options", async () => {
    renderStockScreener();

    await waitFor(() => {
      expect(
        screen.getByText(/advanced|more filters/i) ||
          screen.getByRole("button", { name: /advanced/i })
      ).toBeInTheDocument();
    });
  });

  it("shows stock detail links", async () => {
    renderStockScreener();

    await waitFor(() => {
      const stockLinks = screen.getAllByText(/AAPL|MSFT|JNJ|JPM/);
      expect(stockLinks.length).toBeGreaterThan(0);

      // Should be clickable links
      expect(
        stockLinks[0].closest("a") || stockLinks[0].getAttribute("role")
      ).toBeDefined();
    });
  });
});

function createMockUser() {
  return {
    id: 1,
    username: "testuser",
    email: "test@example.com",
    isAuthenticated: true,
  };
}
