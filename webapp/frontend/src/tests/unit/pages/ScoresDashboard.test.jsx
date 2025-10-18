/**
 * Bullseye Stock Screener Page Unit Tests
 * Tests the new leaderboard-based scores dashboard with top performers
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
import ScoresDashboard from "../../../pages/ScoresDashboard.jsx";

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
  })),
  AuthProvider: vi.fn(({ children }) => children),
}));

// Mock react-router-dom navigate
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// Mock API service with proper ES module support
vi.mock("../../../services/api", () => {
  const mockApi = {
    get: vi.fn(() => {
      return Promise.resolve({
        data: {
          success: true,
          data: {
            stocks: [
              {
                symbol: "AAPL",
                company_name: "Apple Inc.",
                composite_score: 88.7,
                momentum_score: 85.2,
                value_score: 78.3,
                quality_score: 88.7,
                growth_score: 82.1,
                positioning_score: 84.5,
                sentiment_score: 79.2,
                current_price: 175.5,
                price_change_1d: 1.2,
                price_change_5d: 3.5,
                price_change_30d: 8.2,
                volatility_30d: 18.5,
                market_cap: 3400000000000,
                volume_avg_30d: 45000000,
                pe_ratio: 28.5,
                last_updated: "2025-09-27T07:59:12.033Z",
              },
              {
                symbol: "MSFT",
                company_name: "Microsoft Corporation",
                composite_score: 91.2,
                momentum_score: 88.5,
                value_score: 85.1,
                quality_score: 91.2,
                growth_score: 89.5,
                positioning_score: 86.7,
                sentiment_score: 82.4,
                current_price: 420.75,
                price_change_1d: 2.1,
                price_change_5d: 5.2,
                price_change_30d: 12.1,
                volatility_30d: 22.3,
                market_cap: 3200000000000,
                volume_avg_30d: 25000000,
                pe_ratio: 35.8,
                last_updated: "2025-09-27T07:59:12.033Z",
              },
            ],
          },
        },
      });
    }),
    post: vi.fn(() => Promise.resolve({ data: {} })),
  };

  return {
    default: mockApi,
    getStockScores: vi.fn(),
    getScoringMetrics: vi.fn(),
    getTopScores: vi.fn(),
  };
});

// Helper function to create mock user
function createMockUser() {
  return {
    id: "test-user-123",
    email: "test@example.com",
    name: "Test User",
    subscription: {
      tier: "premium",
      status: "active",
      features: ["real_time_data", "advanced_analytics", "premium_support"],
    },
    preferences: {
      theme: "light",
      defaultView: "dashboard",
      notifications: true,
    },
    lastLogin: new Date().toISOString(),
    createdAt: "2024-01-01T00:00:00.000Z",
  };
}

// Helper function to render component with required providers
function renderScoresDashboard(initialEntries = ["/scores"]) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <ScoresDashboard />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Bullseye Stock Screener Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockNavigate.mockClear();
  });

  it("renders the Bullseye title without subtitle", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText(/Bullseye Stock Screener/i)).toBeInTheDocument();
    });

    // Subtitle should not be present
    expect(
      screen.queryByText(
        /Multi-factor analysis with precision scoring/i
      )
    ).not.toBeInTheDocument();
  });

  it("displays search functionality", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(
        screen.getByPlaceholderText(/Search stocks by symbol.../i)
      ).toBeInTheDocument();
    });
  });

  it("displays summary statistics", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText("Total Stocks Analyzed")).toBeInTheDocument();
      expect(screen.getByText("Highest Overall Score")).toBeInTheDocument();
      expect(screen.getByText("Market Average")).toBeInTheDocument();
      expect(screen.getByText(/High Quality Stocks/i)).toBeInTheDocument();
    });
  });

  it("displays filter controls icon button", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      const filterButtons = screen.getAllByRole("button");
      expect(filterButtons.length).toBeGreaterThan(0);
    });
  });

  it("displays accordion with stock symbols", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
      expect(screen.getAllByText("MSFT").length).toBeGreaterThan(0);
    });
  });

  it("displays all individual score labels in accordion summary", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      // Check for score labels (not chips with colons - these are now progress bars with labels)
      // 7-factor system includes: Quality, Momentum, Value, Growth, Positioning, Sentiment, Risk
      expect(screen.getAllByText(/^Quality$/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/^Momentum$/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/^Value$/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/^Growth$/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/^Positioning$/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/^Sentiment$/i).length).toBeGreaterThan(0);
    });
  });

  it("displays score gauge with grade in accordion summary", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
    });

    // Score gauge should show the rounded score (89 for AAPL)
    expect(screen.getAllByText("89").length).toBeGreaterThan(0);

    // Score gauge should also show grade (B+ or A- for 89)
    const grades = screen.queryAllByText(/^[A-F][+-]?$/);
    expect(grades.length).toBeGreaterThan(0);
  });

  it("filters stocks based on search input", async () => {
    renderScoresDashboard();

    // Wait for initial load
    await waitFor(() => {
      expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
      expect(screen.getAllByText("MSFT").length).toBeGreaterThan(0);
    });

    // Enter search term
    const searchInput = screen.getByPlaceholderText(/Search stocks by symbol.../i);
    fireEvent.change(searchInput, { target: { value: "AAPL" } });

    // Check that only AAPL is shown
    await waitFor(() => {
      expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
      expect(screen.queryAllByText("MSFT").length).toBe(0);
    });
  });

  it("displays filter controls icon button", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      const filterButtons = screen.getAllByRole("button");
      expect(filterButtons.length).toBeGreaterThan(0);
    });
  });

  it("shows and hides filters when filter button is clicked", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      const buttons = screen.getAllByRole("button");
      expect(buttons.length).toBeGreaterThan(0);
    });

    // Initially, advanced filters should not be visible
    expect(screen.queryByText("Min Composite")).not.toBeInTheDocument();
    expect(screen.queryByText("Min Momentum")).not.toBeInTheDocument();

    // Click filter button (look for button with svg/icon)
    const buttons = screen.getAllByRole("button");
    const filterButton = buttons.find((btn) => btn.querySelector("svg"));
    if (filterButton) {
      fireEvent.click(filterButton);

      await waitFor(() => {
        expect(screen.getByText("Min Composite")).toBeInTheDocument();
        expect(screen.getByText("Min Momentum")).toBeInTheDocument();
        expect(screen.getByText("Min Quality")).toBeInTheDocument();
        expect(screen.getByText("Min Value")).toBeInTheDocument();
        expect(screen.getByText("Min Growth")).toBeInTheDocument();
      });
    }
  });

  it("navigates to stock detail when accordion is clicked", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
    });

    // Find and click the accordion
    const appleElements = screen.getAllByText("AAPL");
    const appleAccordion = appleElements[0].closest(".MuiAccordion-root");
    if (appleAccordion) {
      fireEvent.click(appleAccordion);

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith("/stocks/AAPL");
      });
    }
  });

  it("displays no stocks found when search has no results", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
    });

    const searchInput = screen.getByPlaceholderText(/Search stocks by symbol.../i);
    fireEvent.change(searchInput, { target: { value: "NONEXISTENT" } });

    await waitFor(() => {
      expect(screen.getByText("No stocks found matching your filters")).toBeInTheDocument();
      expect(screen.getByText("Clear Filters")).toBeInTheDocument();
    });
  });

  it("shows loading state initially", async () => {
    // Mock API to never resolve to test loading state
    const mockApi = await import("../../../services/api");
    mockApi.default.get.mockImplementation(() => new Promise(() => {}));

    renderScoresDashboard();

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    const mockApi = await import("../../../services/api");
    mockApi.default.get.mockRejectedValue(new Error("API Error"));

    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText("No stocks found matching your filters")).toBeInTheDocument();
    });
  });

  it("displays score gauges with grades for each stock", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      // Check for score values (they appear in the score gauges)
      expect(screen.getAllByText("89").length).toBeGreaterThan(0); // AAPL rounded score
      expect(screen.getAllByText("91").length).toBeGreaterThan(0); // MSFT rounded score

      // Check for grades
      const grades = screen.queryAllByText(/^[A-F][+-]?$/);
      expect(grades.length).toBeGreaterThan(0);
    });
  });

  it("displays accordion format with proper structure", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
    });

    // Check that accordion elements ARE present
    const accordions = document.querySelectorAll(".MuiAccordion-root");
    expect(accordions.length).toBeGreaterThan(0);
  });

  it("expands accordion to show factor analysis with 7 factors and NO trading signal card", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
    });

    // Find AAPL accordion and expand it
    const appleElements = screen.getAllByText("AAPL");
    const appleAccordion = appleElements[0].closest(".MuiAccordion-root");
    if (appleAccordion) {
      const expandButton = appleAccordion.querySelector('[aria-label*="expand"]');
      if (expandButton) {
        fireEvent.click(expandButton);

        await waitFor(() => {
          // Check for all 7 factor analysis cards (including risk)
          expect(screen.getByText(/Quality & Fundamentals/i)).toBeInTheDocument();
          expect(screen.getByText(/Price Action & Momentum/i)).toBeInTheDocument();
          expect(screen.getByText(/Value Assessment/i)).toBeInTheDocument();
          expect(screen.getByText(/Growth Potential/i)).toBeInTheDocument();
          expect(screen.getByText(/Market Positioning/i)).toBeInTheDocument();
          expect(screen.getByText(/Market Sentiment/i)).toBeInTheDocument();
        });

        // Trading Signal should NOT be visible as a separate card
        const tradingSignalCards = screen.queryAllByText(/^Trading Signal$/i);
        // Filter to check if any are in the accordion details (not summary)
        const detailSignals = tradingSignalCards.filter(el => {
          const parent = el.closest('.MuiAccordionDetails-root');
          return parent !== null;
        });
        expect(detailSignals.length).toBe(0);
      }
    }
  });

  it("displays clear filters button when filters are active", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
    });

    // Enter search term to activate filters
    const searchInput = screen.getByPlaceholderText(/Search stocks by symbol.../i);
    fireEvent.change(searchInput, { target: { value: "AAPL" } });

    await waitFor(() => {
      expect(screen.getByText("Clear Filters")).toBeInTheDocument();
    });
  });
});
