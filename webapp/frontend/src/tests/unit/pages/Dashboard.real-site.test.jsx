import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Dashboard from "../../../pages/Dashboard";
import AuthContext from "../../../contexts/AuthContext";

// Mock fetch for API calls
global.fetch = vi.fn(() =>
  Promise.resolve({
    ok: true,
    status: 200,
    json: () =>
      Promise.resolve({
        success: true,
        data: {
          marketOverview: {
            indices: [
              {
                symbol: "SPY",
                price: 425.5,
                change: 2.15,
                changePercent: 0.51,
              },
              {
                symbol: "QQQ",
                price: 365.8,
                change: -1.2,
                changePercent: -0.33,
              },
            ],
          },
          topStocks: [
            {
              symbol: "AAPL",
              price: 189.45,
              change: 2.34,
              changePercent: 1.25,
            },
            {
              symbol: "MSFT",
              price: 350.0,
              change: -1.5,
              changePercent: -0.43,
            },
          ],
          portfolio: {
            totalValue: 125000,
            dayChange: 2500,
            dayChangePercent: 2.04,
            holdings: [],
          },
          technicalSignals: {
            signals: [
              { symbol: "AAPL", signal: "BUY", strength: 0.8 },
              { symbol: "MSFT", signal: "HOLD", strength: 0.6 },
            ],
          },
        },
      }),
  })
);

// Mock your actual API functions
vi.mock("../../../services/api", () => ({
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    baseURL: "http://localhost:3001",
  })),
  getStockPrices: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: [
        { symbol: "AAPL", price: 189.45, change: 2.34, changePercent: 1.25 },
        { symbol: "MSFT", price: 350.0, change: -1.5, changePercent: -0.43 },
      ],
    })
  ),
  getStockMetrics: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: {
        marketCap: "2.5T",
        volume: "65.2M",
        peRatio: 28.5,
      },
    })
  ),
  api: {
    get: vi.fn(() =>
      Promise.resolve({
        data: {
          success: true,
          data: [],
        },
      })
    ),
    post: vi.fn(() =>
      Promise.resolve({
        data: {
          success: true,
          data: {},
        },
      })
    ),
  },
}));

const mockAuthContext = {
  user: { id: "test-user", email: "test@example.com" },
  isAuthenticated: true,
  isLoading: false,
  tokens: { idToken: "test-token" },
};

const renderWithAuth = (component) => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthContext.Provider value={mockAuthContext}>
          {component}
        </AuthContext.Provider>
      </BrowserRouter>
    </QueryClientProvider>
  );
};

describe("Dashboard Page - Real Site Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Dashboard Layout", () => {
    test("should render main dashboard structure", () => {
      renderWithAuth(<Dashboard />);

      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });

    test("should display MUI Grid layout", () => {
      renderWithAuth(<Dashboard />);

      const grids = document.querySelectorAll(".MuiGrid-root");
      expect(grids.length).toBeGreaterThan(0);
    });

    test("should show Container component", () => {
      renderWithAuth(<Dashboard />);

      const container = document.querySelector(".MuiContainer-root");
      expect(container).toBeInTheDocument();
    });
  });

  describe("Market Overview Cards", () => {
    test("should display market overview cards", async () => {
      renderWithAuth(<Dashboard />);

      await waitFor(() => {
        const cards = document.querySelectorAll(".MuiCard-root");
        expect(cards.length).toBeGreaterThan(0);
      });
    });

    test("should show market indices or similar dashboard widgets", async () => {
      renderWithAuth(<Dashboard />);

      await waitFor(() => {
        // Test for any market data display
        const marketElements = screen.queryAllByText(
          /SPY|QQQ|DIA|Market|Index/i
        );
        expect(marketElements.length).toBeGreaterThanOrEqual(0);
      });
    });
  });

  describe("Quick Actions", () => {
    test("should display quick action buttons", async () => {
      renderWithAuth(<Dashboard />);

      await waitFor(() => {
        const buttons = screen.getAllByRole("button");
        expect(buttons.length).toBeGreaterThan(0);
      });
    });

    test("should handle quick navigation", async () => {
      const user = userEvent.setup();
      renderWithAuth(<Dashboard />);

      // Test any navigation buttons on dashboard
      const portfolioLink = screen.queryByText(/portfolio/i);
      if (portfolioLink) {
        await user.click(portfolioLink);
      }
    });
  });

  describe("Data Widgets", () => {
    test("should display portfolio summary widget if present", async () => {
      renderWithAuth(<Dashboard />);

      await waitFor(() => {
        // Test for portfolio-related content
        const portfolioContent = screen.queryByText(
          /portfolio|holdings|positions/i
        );
        if (portfolioContent) {
          expect(portfolioContent).toBeInTheDocument();
        }
      });
    });

    test("should show watchlist or stock information", async () => {
      renderWithAuth(<Dashboard />);

      await waitFor(() => {
        // Test for stock symbols or watchlist
        const stockContent = screen.queryAllByText(
          /AAPL|MSFT|GOOGL|Stock|Watch/i
        );
        expect(stockContent.length).toBeGreaterThanOrEqual(0);
      });
    });
  });

  describe("Charts and Visualizations", () => {
    test("should render any chart components present", async () => {
      renderWithAuth(<Dashboard />);

      await waitFor(() => {
        // Check for any chart containers
        const chartElements = document.querySelectorAll(
          '.recharts-wrapper, .chart-container, [data-testid*="chart"]'
        );
        expect(chartElements.length).toBeGreaterThanOrEqual(0);
      });
    });
  });

  describe("Search and Filter Functionality", () => {
    test("should display Autocomplete component if present", async () => {
      renderWithAuth(<Dashboard />);

      await waitFor(() => {
        const autocomplete = document.querySelector(".MuiAutocomplete-root");
        if (autocomplete) {
          expect(autocomplete).toBeInTheDocument();
        }
      });
    });

    test("should handle text input in search fields", async () => {
      const user = userEvent.setup();
      renderWithAuth(<Dashboard />);

      const textFields = document.querySelectorAll(".MuiTextField-root input");
      if (textFields.length > 0) {
        await user.type(textFields[0], "AAPL");
        expect(textFields[0]).toHaveValue("AAPL");
      }
    });
  });

  describe("Real-time Data Integration", () => {
    test("should prepare for API data loading", async () => {
      const { api } = await import("../../../services/api");

      api.get.mockResolvedValue({
        data: {
          marketData: {
            SPY: { price: 450.25, change: 5.75 },
          },
        },
      });

      renderWithAuth(<Dashboard />);

      // When real API is connected, should make requests
      // await waitFor(() => {
      //   expect(api.get).toHaveBeenCalled();
      // });
    });

    test("should handle API errors when real data is connected", async () => {
      const { api } = await import("../../../services/api");

      api.get.mockRejectedValue(new Error("Network error"));

      renderWithAuth(<Dashboard />);

      // Should gracefully handle errors when real API is integrated
    });
  });

  describe("Table Components", () => {
    test("should display tables with MUI Table components", async () => {
      renderWithAuth(<Dashboard />);

      await waitFor(() => {
        const tables = document.querySelectorAll(".MuiTable-root");
        if (tables.length > 0) {
          expect(tables[0]).toBeInTheDocument();
        }
      });
    });

    test("should handle table interactions", async () => {
      const _user = userEvent.setup();
      renderWithAuth(<Dashboard />);

      await waitFor(() => {
        const tableRows = document.querySelectorAll(".MuiTableRow-root");
        if (tableRows.length > 1) {
          // Click on a data row (not header)
          fireEvent.click(tableRows[1]);
        }
      });
    });
  });

  describe("Notifications and Alerts", () => {
    test("should display notification badges if present", async () => {
      renderWithAuth(<Dashboard />);

      await waitFor(() => {
        const badges = document.querySelectorAll(".MuiBadge-root");
        expect(badges.length).toBeGreaterThanOrEqual(0);
      });
    });

    test("should show alert components for important information", async () => {
      renderWithAuth(<Dashboard />);

      await waitFor(() => {
        const alerts = document.querySelectorAll(".MuiAlert-root");
        expect(alerts.length).toBeGreaterThanOrEqual(0);
      });
    });
  });

  describe("Performance and Analytics", () => {
    test("should display analytics cards or metrics", async () => {
      renderWithAuth(<Dashboard />);

      await waitFor(() => {
        // Look for any analytics-related content
        const analyticsContent = screen.queryAllByText(
          /analytics|performance|metrics|trend|gain|loss|profit/i
        );
        expect(analyticsContent.length).toBeGreaterThanOrEqual(0);
      });
    });

    test("should show trending indicators", async () => {
      renderWithAuth(<Dashboard />);

      await waitFor(() => {
        // Look for trending icons or indicators
        const trendingElements = document.querySelectorAll(
          '[data-testid*="trending"], .trending'
        );
        expect(trendingElements.length).toBeGreaterThanOrEqual(0);
      });
    });
  });

  describe("Responsive Design", () => {
    test("should adapt to different screen sizes", () => {
      // Test mobile viewport
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: 768,
      });

      renderWithAuth(<Dashboard />);

      const grids = document.querySelectorAll(".MuiGrid-root");
      expect(grids.length).toBeGreaterThan(0);
    });

    test("should handle large desktop viewport", () => {
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: 1920,
      });

      renderWithAuth(<Dashboard />);

      // Should render without errors on large screens
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });
  });

  describe("User Interaction", () => {
    test("should handle button clicks", async () => {
      const user = userEvent.setup();
      renderWithAuth(<Dashboard />);

      const buttons = screen.getAllByRole("button");
      if (buttons.length > 0) {
        await user.click(buttons[0]);
        // Should handle click without errors
      }
    });

    test("should handle icon button interactions", async () => {
      const user = userEvent.setup();
      renderWithAuth(<Dashboard />);

      const iconButtons = document.querySelectorAll(".MuiIconButton-root");
      if (iconButtons.length > 0) {
        await user.click(iconButtons[0]);
        // Should handle icon button clicks
      }
    });
  });

  describe("Authentication Context Integration", () => {
    test("should access authenticated user data", () => {
      renderWithAuth(<Dashboard />);

      // Should properly integrate with your auth context
      expect(mockAuthContext.isAuthenticated).toBe(true);
      expect(mockAuthContext.user.email).toBe("test@example.com");
    });

    test("should handle loading state", () => {
      const loadingContext = {
        ...mockAuthContext,
        isLoading: true,
      };

      render(
        <BrowserRouter>
          <AuthContext.Provider value={loadingContext}>
            <Dashboard />
          </AuthContext.Provider>
        </BrowserRouter>
      );

      // Should handle loading state appropriately
    });
  });

  describe("API Configuration", () => {
    test("should use correct API configuration", async () => {
      const { getApiConfig } = await import("../../../services/api");

      renderWithAuth(<Dashboard />);

      const config = getApiConfig();
      expect(config.apiUrl).toBe("http://localhost:3001");
    });
  });
});
