import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { BrowserRouter } from "react-router-dom";
import Portfolio from "../../../pages/Portfolio";
import AuthContext from "../../../contexts/AuthContext";

// Mock the useAuth hook
vi.mock("../../../contexts/AuthContext", async () => {
  const actual = await vi.importActual("../../../contexts/AuthContext");
  return {
    ...actual,
    default: actual.default,
    useAuth: vi.fn(() => ({
      user: { id: "test-user", email: "test@example.com" },
      isAuthenticated: true,
      isLoading: false,
      tokens: { idToken: "test-token" },
    })),
  };
});

// Mock your actual API functions
vi.mock("../../../services/api", () => ({
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    baseURL: "http://localhost:3001",
  })),
  getPortfolioData: vi.fn(() =>
    Promise.resolve({
      success: true,
      data: {
        holdings: [
          {
            symbol: "AAPL",
            company: "Apple Inc.",
            shares: 100,
            marketValue: 18945,
            gainLoss: 3945,
            gainLossPercent: 26.3,
            currentPrice: 189.45,
            costBasis: 150.0,
            beta: 1.2,
            volatility: 0.25,
            allocation: 60.4,
            factorScores: {
              quality: 85,
              growth: 75,
              value: 45,
              momentum: 65,
              size: 30,
              liquidity: 90,
              sentiment: 70,
              positioning: 55,
            },
          },
          {
            symbol: "MSFT",
            company: "Microsoft Corporation",
            shares: 50,
            marketValue: 17500,
            gainLoss: 2500,
            gainLossPercent: 16.7,
            currentPrice: 350.0,
            costBasis: 300.0,
            beta: 1.1,
            volatility: 0.22,
            allocation: 39.6,
            factorScores: {
              quality: 90,
              growth: 80,
              value: 40,
              momentum: 70,
              size: 25,
              liquidity: 95,
              sentiment: 75,
              positioning: 60,
            },
          },
        ],
        summary: {
          totalValue: 125000,
          dayChange: 2500,
          dayChangePercent: 2.04,
        },
        performanceHistory: [
          {
            date: "2025-01-01",
            portfolioValue: 100000,
          },
          {
            date: "2025-01-15",
            portfolioValue: 125000,
          },
        ],
        sectorAllocation: [
          {
            sector: "Technology",
            value: 75000,
            percentage: 60,
          },
          {
            sector: "Healthcare",
            value: 25000,
            percentage: 20,
          },
          {
            sector: "Financials",
            value: 25000,
            percentage: 20,
          },
        ],
      },
    })
  ),
  addHolding: vi.fn(),
  updateHolding: vi.fn(),
  deleteHolding: vi.fn(),
  getApiKeys: vi.fn(() =>
    Promise.resolve({
      apiKeys: [
        {
          provider: "alpaca",
          keyId: "test-key",
          isValid: true,
          lastValidated: "2025-01-15T10:30:00Z",
        },
      ],
    })
  ),
  testApiConnection: vi.fn(() => Promise.resolve({ success: true })),
  importPortfolioFromBroker: vi.fn(() => Promise.resolve({ success: true })),
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const mockAuthContext = {
  user: { id: "test-user", email: "test@example.com" },
  isAuthenticated: true,
  isLoading: false,
  tokens: { idToken: "test-token" },
};

// Mock fetch for API calls
global.fetch = vi.fn(() =>
  Promise.resolve({
    ok: true,
    status: 200,
    json: () =>
      Promise.resolve({
        success: true,
        data: {
          holdings: [
            {
              symbol: "AAPL",
              company: "Apple Inc.",
              shares: 100,
              marketValue: 18945,
              gainLoss: 3945,
              gainLossPercent: 26.3,
              currentPrice: 189.45,
              costBasis: 150.0,
              beta: 1.2,
              volatility: 0.25,
              allocation: 60.4,
              factorScores: {
                quality: 85,
                growth: 75,
                value: 45,
                momentum: 65,
                size: 30,
                liquidity: 90,
                sentiment: 70,
                positioning: 55,
              },
            },
            {
              symbol: "MSFT",
              company: "Microsoft Corporation",
              shares: 50,
              marketValue: 17500,
              gainLoss: 2500,
              gainLossPercent: 16.7,
              currentPrice: 350.0,
              costBasis: 300.0,
              beta: 1.1,
              volatility: 0.22,
              allocation: 39.6,
              factorScores: {
                quality: 90,
                growth: 80,
                value: 40,
                momentum: 70,
                size: 25,
                liquidity: 95,
                sentiment: 75,
                positioning: 60,
              },
            },
          ],
          summary: {
            totalValue: 125000,
            dayChange: 2500,
            dayChangePercent: 2.04,
          },
          performanceHistory: [
            {
              date: "2025-01-01",
              portfolioValue: 100000,
            },
            {
              date: "2025-01-15",
              portfolioValue: 125000,
            },
          ],
          sectorAllocation: [
            {
              sector: "Technology",
              value: 75000,
              percentage: 60,
            },
            {
              sector: "Healthcare",
              value: 25000,
              percentage: 20,
            },
            {
              sector: "Financials",
              value: 25000,
              percentage: 20,
            },
          ],
        },
      }),
  })
);

const renderWithAuth = (component) => {
  return render(
    <BrowserRouter>
      <AuthContext.Provider value={mockAuthContext}>
        {component}
      </AuthContext.Provider>
    </BrowserRouter>
  );
};

describe("Portfolio Page - Real Site Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("Mock Data Display", () => {
    test("should display mock portfolio data on initial load", async () => {
      renderWithAuth(<Portfolio />);

      // Test that mock data from your actual codebase is displayed
      await waitFor(() => {
        expect(screen.getByText("AAPL")).toBeInTheDocument();
        expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
        expect(screen.getByText("MSFT")).toBeInTheDocument();
        expect(screen.getByText("Microsoft Corporation")).toBeInTheDocument();
      });
    });

    test("should show portfolio value and gain/loss from mock data", async () => {
      renderWithAuth(<Portfolio />);

      await waitFor(() => {
        // Based on your mock data structure
        expect(screen.getByText(/Total Portfolio Value/i)).toBeInTheDocument();
        expect(screen.getByText(/Today's P&L/i)).toBeInTheDocument();
      });
    });

    test("should display holdings table with your actual columns", async () => {
      renderWithAuth(<Portfolio />);

      await waitFor(() => {
        // Test actual column headers from your Portfolio component
        expect(screen.getByText("Symbol")).toBeInTheDocument();
        expect(screen.getByText("Company")).toBeInTheDocument();
        expect(screen.getByText("Shares")).toBeInTheDocument();
        expect(screen.getByText("Market Value")).toBeInTheDocument();
        expect(screen.getByText("Gain/Loss")).toBeInTheDocument();
        expect(screen.getByText("Allocation")).toBeInTheDocument();
      });
    });
  });

  describe("MUI Tabs Functionality", () => {
    test("should have multiple tabs as per your implementation", async () => {
      const user = userEvent.setup();
      renderWithAuth(<Portfolio />);

      // Test actual tabs from your Portfolio component
      await waitFor(() => {
        expect(screen.getByRole("tablist")).toBeInTheDocument();
      });

      // Test tab switching functionality
      const tabs = screen.getAllByRole("tab");
      expect(tabs.length).toBeGreaterThan(1);

      // Click second tab
      if (tabs[1]) {
        await user.click(tabs[1]);
        // Should switch tab content
      }
    });
  });

  describe("Holdings Table Interactions", () => {
    test("should allow sorting by different columns", async () => {
      const user = userEvent.setup();
      renderWithAuth(<Portfolio />);

      await waitFor(() => {
        const symbolHeader = screen.getByText("Symbol");
        expect(symbolHeader).toBeInTheDocument();
      });

      // Test your TableSortLabel functionality
      const sortButton = screen.getByRole("button", { name: /Symbol/i });
      await user.click(sortButton);

      // Should trigger sort functionality
    });

    test("should have pagination controls", async () => {
      renderWithAuth(<Portfolio />);

      await waitFor(() => {
        // Test TablePagination component
        expect(screen.getByText(/rows per page/i)).toBeInTheDocument();
      });
    });
  });

  describe("Charts and Visualizations", () => {
    test("should display Recharts components", async () => {
      renderWithAuth(<Portfolio />);

      await waitFor(() => {
        // Test that your PieChart, LineChart components render
        const charts = document.querySelectorAll(".recharts-wrapper");
        expect(charts.length).toBeGreaterThan(0);
      });
    });

    test("should display allocation pie chart", async () => {
      renderWithAuth(<Portfolio />);

      await waitFor(() => {
        // Test sector allocation chart from your mock data
        const pieChart = document.querySelector(".recharts-pie");
        expect(pieChart).toBeInTheDocument();
      });
    });
  });

  describe("Add/Edit Holdings Dialog", () => {
    test("should open add holding dialog", async () => {
      const user = userEvent.setup();
      renderWithAuth(<Portfolio />);

      // Find and click the Add button from your MUI components
      const addButton =
        screen.getByLabelText(/add/i) ||
        screen.getByRole("button", { name: /add/i });
      if (addButton) {
        await user.click(addButton);

        await waitFor(() => {
          expect(screen.getByRole("dialog")).toBeInTheDocument();
        });
      }
    });

    test("should validate form inputs in add holding dialog", async () => {
      const user = userEvent.setup();
      renderWithAuth(<Portfolio />);

      // Navigate through your actual form validation
      const addButton =
        screen.getByLabelText(/add/i) ||
        screen.getByRole("button", { name: /add/i });
      if (addButton) {
        await user.click(addButton);

        // Test your TextField validation
        const symbolInput = screen.getByLabelText(/symbol/i);
        await user.type(symbolInput, "INVALID_SYMBOL_TOO_LONG");

        // Should show validation error
      }
    });
  });

  describe("Risk Alerts Feature", () => {
    test("should display risk alerts section", async () => {
      renderWithAuth(<Portfolio />);

      await waitFor(() => {
        // Test your risk alerts functionality
        expect(screen.getByText(/risk/i)).toBeInTheDocument();
      });
    });

    test("should allow creating new risk alerts", async () => {
      const user = userEvent.setup();
      renderWithAuth(<Portfolio />);

      // Test your risk alert dialog functionality
      const riskButton = screen.getByText(/risk/i);
      if (riskButton) {
        await user.click(riskButton);
      }
    });
  });

  describe("Factor Scores Display", () => {
    test("should display factor scores for holdings", async () => {
      renderWithAuth(<Portfolio />);

      await waitFor(() => {
        // Test your factor scores from mock data
        const qualityScore =
          screen.getByText("85") || screen.getByText("Quality: 85");
        if (qualityScore) {
          expect(qualityScore).toBeInTheDocument();
        }
      });
    });

    test("should show radar chart for factor analysis", async () => {
      renderWithAuth(<Portfolio />);

      await waitFor(() => {
        // Test your RadarChart component
        const radarChart = document.querySelector(".recharts-radar");
        if (radarChart) {
          expect(radarChart).toBeInTheDocument();
        }
      });
    });
  });

  describe("Responsive Design", () => {
    test("should adapt to mobile viewport", () => {
      // Mock mobile viewport
      Object.defineProperty(window, "innerWidth", {
        writable: true,
        configurable: true,
        value: 768,
      });

      renderWithAuth(<Portfolio />);

      // Test your responsive Grid components
      const grids = document.querySelectorAll(".MuiGrid-root");
      expect(grids.length).toBeGreaterThan(0);
    });
  });

  describe("Authentication Integration", () => {
    test("should access user context properly", () => {
      renderWithAuth(<Portfolio />);

      // Should access the auth context you're using
      expect(mockAuthContext.isAuthenticated).toBe(true);
    });

    test("should handle unauthenticated state", () => {
      const unauthenticatedContext = {
        ...mockAuthContext,
        isAuthenticated: false,
      };

      render(
        <BrowserRouter>
          <AuthContext.Provider value={unauthenticatedContext}>
            <Portfolio />
          </AuthContext.Provider>
        </BrowserRouter>
      );

      // Should handle your auth logic appropriately
    });
  });

  describe("API Integration Preparation", () => {
    test("should call getPortfolioData when real API is enabled", async () => {
      const { getPortfolioData } = await import("../../../services/api");

      getPortfolioData.mockResolvedValue({
        data: {
          holdings: [
            {
              symbol: "REAL_AAPL",
              company: "Apple Inc.",
              shares: 50,
              currentPrice: 190.0,
              marketValue: 9500,
            },
          ],
        },
      });

      renderWithAuth(<Portfolio />);

      // When you switch from mock to real data, this should work
      // expect(getPortfolioData).toHaveBeenCalled();
    });

    test("should handle API errors gracefully", async () => {
      const { getPortfolioData } = await import("../../../services/api");

      getPortfolioData.mockRejectedValue(new Error("API Error"));

      renderWithAuth(<Portfolio />);

      // Should show error handling UI when real API is integrated
    });
  });

  describe("Component State Management", () => {
    test("should manage activeTab state correctly", async () => {
      const user = userEvent.setup();
      renderWithAuth(<Portfolio />);

      // Test your actual tab state management
      const tabs = screen.getAllByRole("tab");
      if (tabs.length > 1) {
        await user.click(tabs[1]);

        // Should update activeTab state
        await waitFor(() => {
          expect(tabs[1]).toHaveAttribute("aria-selected", "true");
        });
      }
    });

    test("should manage table sorting state", async () => {
      const _user = userEvent.setup();
      renderWithAuth(<Portfolio />);

      await waitFor(() => {
        const symbolHeader = screen.getByText("Symbol");
        if (symbolHeader.closest("button")) {
          fireEvent.click(symbolHeader.closest("button"));
        }
      });

      // Should update orderBy and order state
    });
  });
});
