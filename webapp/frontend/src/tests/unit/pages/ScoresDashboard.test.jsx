/**
 * ScoresDashboard Page Unit Tests
 * Tests the scores dashboard functionality - stock list with accordion details
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

// Mock API service with proper ES module support
vi.mock("../../../services/api", () => {
  const mockApi = {
    get: vi.fn((url) => {
      // Handle signals API requests
      if (url.includes('/signals/AAPL')) {
        return Promise.resolve({
          data: {
            success: true,
            data: [
              {
                symbol: 'AAPL',
                signal: 'BUY',
                confidence: 0.85,
                date: '2024-01-15',
                current_price: 175.5
              }
            ]
          }
        });
      }
      if (url.includes('/signals/MSFT')) {
        return Promise.resolve({
          data: {
            success: true,
            data: [
              {
                symbol: 'MSFT',
                signal: 'HOLD',
                confidence: 0.72,
                date: '2024-01-15',
                current_price: 420.75
              }
            ]
          }
        });
      }
      // Handle scores API requests
      return Promise.resolve({
        data: {
          success: true,
          data: {
            stocks: [
              {
                symbol: "AAPL",
                compositeScore: 88.7,
                currentPrice: 175.5,
                priceChange1d: 1.2,
                volume: 45000000,
                marketCap: 3400000000000,
                factors: {
                  momentum: {
                    score: 85.2,
                    rsi: 65.4,
                    description: "Momentum measures price velocity and market sentiment"
                  },
                  trend: {
                    score: 90.1,
                    sma20: 174.5,
                    sma50: 170.2,
                    description: "Trend analyzes price direction relative to moving averages"
                  },
                  value: {
                    score: 78.3,
                    peRatio: 28.5,
                    description: "Value assessment based on fundamental metrics"
                  },
                  quality: {
                    score: 88.7,
                    volatility: 18.5,
                    description: "Quality measures stability and consistency"
                  },
                  technical: {
                    priceChange5d: 3.5,
                    priceChange30d: 8.2,
                    description: "Technical indicators and price momentum"
                  },
                  risk: {
                    volatility30d: 18.5,
                    description: "Risk assessment based on volatility measures"
                  }
                },
                lastUpdated: "2025-09-27T07:59:12.033Z"
              },
              {
                symbol: "MSFT",
                compositeScore: 91.2,
                currentPrice: 420.75,
                priceChange1d: 2.1,
                volume: 25000000,
                marketCap: 3200000000000,
                factors: {
                  momentum: {
                    score: 88.5,
                    rsi: 72.1,
                    description: "Momentum measures price velocity and market sentiment"
                  },
                  trend: {
                    score: 92.8,
                    sma20: 418.3,
                    sma50: 415.8,
                    description: "Trend analyzes price direction relative to moving averages"
                  },
                  value: {
                    score: 85.1,
                    peRatio: 35.8,
                    description: "Value assessment based on fundamental metrics"
                  },
                  quality: {
                    score: 91.2,
                    volatility: 22.3,
                    description: "Quality measures stability and consistency"
                  },
                  technical: {
                    priceChange5d: 5.2,
                    priceChange30d: 12.1,
                    description: "Technical indicators and price momentum"
                  },
                  risk: {
                    volatility30d: 22.3,
                    description: "Risk assessment based on volatility measures"
                  }
                },
                lastUpdated: "2025-09-27T07:59:12.033Z"
              }
            ]
          }
        }
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

describe("ScoresDashboard Page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the dashboard title and description", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(
        screen.getByText(/Stock Scores Dashboard/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Comprehensive six-factor scoring system for all stocks/i)
      ).toBeInTheDocument();
    });
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
      expect(screen.getByText("Total Stocks")).toBeInTheDocument();
      expect(screen.getByText("Top Score")).toBeInTheDocument();
      expect(screen.getByText("Average Score")).toBeInTheDocument();
      expect(screen.getByText("High Quality (80+)")).toBeInTheDocument();
    });
  });

  it("displays stocks list with accordion format", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      // Check for stock symbols
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText("MSFT")).toBeInTheDocument();

      // Check for scores (composite scores appear in prominent score display and factor chips)
      expect(screen.getAllByText("88.7").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("91.2").length).toBeGreaterThanOrEqual(1);

      // Check for prices
      expect(screen.getByText("$175.50")).toBeInTheDocument();
      expect(screen.getByText("$420.75")).toBeInTheDocument();
    });
  });

  it("shows prominent score display for each stock", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText("Score: 88.7")).toBeInTheDocument();
      expect(screen.getByText("Score: 91.2")).toBeInTheDocument();
    }, { timeout: 10000 });
  });

  it("shows factor chips for each stock", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText("Quality: 88.7")).toBeInTheDocument();
      expect(screen.getByText("Momentum: 85.2")).toBeInTheDocument();
      expect(screen.getByText("Trend: 90.1")).toBeInTheDocument();
      expect(screen.getByText("Value: 78.3")).toBeInTheDocument();
      expect(screen.getAllByText(/Technical:/).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText(/Risk:/).length).toBeGreaterThanOrEqual(1);
    }, { timeout: 10000 });
  });

  it("expands accordion to show detailed factor analysis", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    }, { timeout: 10000 });

    // Find and click the first accordion
    const appleAccordion = screen.getByText("AAPL").closest('[role="button"]');
    fireEvent.click(appleAccordion);

    await waitFor(() => {
      expect(screen.getByText("Factor Analysis for AAPL")).toBeInTheDocument();
      expect(screen.getAllByText("Momentum").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Trend").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Value").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Quality").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Technical").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Risk").length).toBeGreaterThanOrEqual(1);
    }, { timeout: 5000 });
  });

  it("displays individual factor details in expanded view", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    }, { timeout: 10000 });

    const appleAccordion = screen.getByText("AAPL").closest('[role="button"]');
    fireEvent.click(appleAccordion);

    await waitFor(() => {
      // Check for factor descriptions (use getAllByText since descriptions appear for both stocks)
      expect(screen.getAllByText("Momentum measures price velocity and market sentiment").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Trend analyzes price direction relative to moving averages").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Value assessment based on fundamental metrics").length).toBeGreaterThanOrEqual(1);
    }, { timeout: 5000 });
  });

  it("filters stocks based on search input", async () => {
    renderScoresDashboard();

    // Wait for initial load
    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText("MSFT")).toBeInTheDocument();
    });

    // Enter search term
    const searchInput = screen.getByPlaceholderText(/Search stocks by symbol.../i);
    fireEvent.change(searchInput, { target: { value: "AAPL" } });

    // Check that only AAPL is shown
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.queryByText("MSFT")).not.toBeInTheDocument();
  });

  it("shows correct count in All Stocks header", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText("All Stocks (2)")).toBeInTheDocument();
    });
  });

  it("displays no stocks found when search has no results", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText(/Search stocks by symbol.../i);
    fireEvent.change(searchInput, { target: { value: "NONEXISTENT" } });

    await waitFor(() => {
      expect(screen.getByText("No stocks found")).toBeInTheDocument();
      expect(screen.getByText("All Stocks (0)")).toBeInTheDocument();
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
      expect(screen.getByText("No stocks found")).toBeInTheDocument();
    });
  });

  // Trading Signal Tests
  it("displays trading signals for stocks", async () => {
    renderScoresDashboard();

    // Wait for stocks to load first
    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText("MSFT")).toBeInTheDocument();
    });

    // Wait for signals to load (they load after stocks)
    await waitFor(() => {
      expect(screen.getByText("BUY")).toBeInTheDocument();
      expect(screen.getByText("HOLD")).toBeInTheDocument();
    }, { timeout: 5000 });
  });

  it("shows signal date information", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Wait for signals to load and check for signal date
    await waitFor(() => {
      const signalDate = screen.getAllByText(/Signal:/);
      expect(signalDate.length).toBeGreaterThan(0);
    }, { timeout: 5000 });
  });

  it("handles missing signal data gracefully", async () => {
    // Mock API to return empty signals
    const mockApi = await import("../../../services/api");
    mockApi.default.get.mockImplementation((url) => {
      if (url.includes('/signals/')) {
        return Promise.resolve({
          data: {
            success: true,
            data: []
          }
        });
      }
      // Return normal scores data
      return Promise.resolve({
        data: {
          success: true,
          data: {
            stocks: [
              {
                symbol: "AAPL",
                compositeScore: 88.7,
                currentPrice: 175.5,
                priceChange1d: 1.2,
                volume: 45000000,
                marketCap: 3400000000000,
                factors: {
                  momentum: { score: 85.2, rsi: 65.4, description: "Test momentum" },
                  trend: { score: 90.1, sma20: 174.5, sma50: 170.2, description: "Test trend" },
                  value: { score: 78.3, peRatio: 28.5, description: "Test value" },
                  quality: { score: 88.7, volatility: 18.5, description: "Test quality" },
                  technical: { priceChange5d: 3.5, priceChange30d: 8.2, description: "Test technical" },
                  risk: { volatility30d: 18.5, description: "Test risk" }
                },
                lastUpdated: "2025-09-27T07:59:12.033Z"
              }
            ]
          }
        }
      });
    });

    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Signals should not be displayed if no signal data
    expect(screen.queryByText("BUY")).not.toBeInTheDocument();
    expect(screen.queryByText("SELL")).not.toBeInTheDocument();
    expect(screen.queryByText("HOLD")).not.toBeInTheDocument();
  });

  it("loads signals only for visible stocks", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Verify that signals API is called for the visible stocks
    const mockApi = await import("../../../services/api");
    await waitFor(() => {
      const signalCalls = mockApi.default.get.mock.calls.filter(call =>
        call[0].includes('/signals/')
      );
      expect(signalCalls.length).toBeGreaterThan(0);
    }, { timeout: 3000 });
  });
});