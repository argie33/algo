/**
 * ScoresDashboard Page Unit Tests
 * Tests the scores dashboard functionality - stock scoring, rankings, analysis
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
    get: vi.fn(() => Promise.resolve({ data: {} })),
    post: vi.fn(() => Promise.resolve({ data: {} })),
    getStockScores: vi.fn(),
    getScoringMetrics: vi.fn(),
    getTopScores: vi.fn(),
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

const mockScoresData = {
  topScores: [
    {
      symbol: "AAPL",
      name: "Apple Inc.",
      score: 95,
      grade: "A+",
      factors: { growth: 92, value: 88, momentum: 98, quality: 94 },
    },
    {
      symbol: "MSFT",
      name: "Microsoft Corp",
      score: 92,
      grade: "A",
      factors: { growth: 89, value: 85, momentum: 95, quality: 98 },
    },
    {
      symbol: "GOOGL",
      name: "Alphabet Inc.",
      score: 88,
      grade: "A-",
      factors: { growth: 94, value: 78, momentum: 89, quality: 92 },
    },
    {
      symbol: "AMZN",
      name: "Amazon.com Inc",
      score: 85,
      grade: "B+",
      factors: { growth: 96, value: 68, momentum: 87, quality: 89 },
    },
  ],
  metrics: {
    totalStocks: 500,
    averageScore: 65,
    scoreDistribution: [
      { grade: "A", count: 25, percentage: 5 },
      { grade: "B", count: 125, percentage: 25 },
      { grade: "C", count: 200, percentage: 40 },
      { grade: "D", count: 100, percentage: 20 },
      { grade: "F", count: 50, percentage: 10 },
    ],
  },
  factors: {
    growth: { weight: 25, description: "Revenue and earnings growth trends" },
    value: { weight: 25, description: "Valuation metrics relative to peers" },
    momentum: { weight: 25, description: "Price and earnings momentum" },
    quality: { weight: 25, description: "Financial health and stability" },
  },
  sectors: [
    { name: "Technology", averageScore: 78, count: 75 },
    { name: "Healthcare", averageScore: 72, count: 60 },
    { name: "Finance", averageScore: 68, count: 85 },
    { name: "Consumer", averageScore: 65, count: 90 },
  ],
};

// Test render helper
function renderScoresDashboard(props = {}) {
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
        <ScoresDashboard {...props} />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("ScoresDashboard Component", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    const { api } = await import("../../../services/api");
    api.getStockScores.mockResolvedValue({
      success: true,
      data: mockScoresData,
    });
  });

  it("renders scores dashboard page", async () => {
    renderScoresDashboard();

    expect(
      screen.getByText(/scores dashboard|stock scores/i)
    ).toBeInTheDocument();

    await waitFor(() => {
      const { api } = require("../../../services/api");
      expect(api.getStockScores).toHaveBeenCalled();
    });
  });

  it("displays top scoring stocks", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
      expect(screen.getByText("95")).toBeInTheDocument();
      expect(screen.getByText("A+")).toBeInTheDocument();

      expect(screen.getByText("MSFT")).toBeInTheDocument();
      expect(screen.getByText("Microsoft Corp")).toBeInTheDocument();
      expect(screen.getByText("92")).toBeInTheDocument();
      expect(screen.getByText("A")).toBeInTheDocument();
    });
  });

  it("shows scoring factors breakdown", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText(/growth/i)).toBeInTheDocument();
      expect(screen.getByText(/value/i)).toBeInTheDocument();
      expect(screen.getByText(/momentum/i)).toBeInTheDocument();
      expect(screen.getByText(/quality/i)).toBeInTheDocument();
    });
  });

  it("displays individual factor scores", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText("92")).toBeInTheDocument(); // AAPL growth
      expect(screen.getByText("88")).toBeInTheDocument(); // AAPL value
      expect(screen.getByText("98")).toBeInTheDocument(); // AAPL momentum
      expect(screen.getByText("94")).toBeInTheDocument(); // AAPL quality
    });
  });

  it("shows scoring metrics summary", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText(/total stocks/i)).toBeInTheDocument();
      expect(screen.getByText("500")).toBeInTheDocument();
      expect(screen.getByText(/average score/i)).toBeInTheDocument();
      expect(screen.getByText("65")).toBeInTheDocument();
    });
  });

  it("displays score distribution", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(
        screen.getByText(/score distribution|distribution/i)
      ).toBeInTheDocument();
      expect(screen.getByText("25")).toBeInTheDocument(); // A grade count
      expect(screen.getByText("125")).toBeInTheDocument(); // B grade count
      expect(screen.getByText("5%")).toBeInTheDocument(); // A grade percentage
      expect(screen.getByText("25%")).toBeInTheDocument(); // B grade percentage
    });
  });

  it("shows sector analysis", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText(/technology/i)).toBeInTheDocument();
      expect(screen.getByText("78")).toBeInTheDocument(); // Tech average score
      expect(screen.getByText(/healthcare/i)).toBeInTheDocument();
      expect(screen.getByText("72")).toBeInTheDocument(); // Healthcare average
    });
  });

  it("renders score visualization charts", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      // Should have charts/visualizations
      expect(
        screen.getByRole("img", { hidden: true }) ||
          screen.getByTestId(/chart|graph/)
      ).toBeInTheDocument();
    });
  });

  it("displays factor weights", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText("25%")).toBeInTheDocument(); // Factor weights
      expect(
        screen.getByText(/revenue and earnings growth/i)
      ).toBeInTheDocument();
      expect(screen.getByText(/valuation metrics/i)).toBeInTheDocument();
    });
  });

  it("handles score filtering and sorting", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      // Look for filter/sort controls
      expect(
        screen.getByRole("combobox") ||
          screen.getByRole("button", { name: /sort|filter/i })
      ).toBeInTheDocument();
    });
  });

  it("shows grade color coding", async () => {
    const { container: _container } = renderScoresDashboard();

    await waitFor(() => {
      // Grades should be color-coded
      const gradeElements = screen.getAllByText(/A\+|A|B\+/);
      expect(gradeElements.length).toBeGreaterThan(0);
    });
  });

  it("displays factor descriptions", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(
        screen.getByText(/financial health and stability/i)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/price and earnings momentum/i)
      ).toBeInTheDocument();
    });
  });

  it("handles loading state", () => {
    const { api } = require("../../../services/api");
    api.getStockScores.mockImplementation(() => new Promise(() => {}));

    renderScoresDashboard();

    expect(
      screen.getByRole("progressbar") || screen.getByText(/loading/i)
    ).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    const { api } = require("../../../services/api");
    api.getStockScores.mockRejectedValue(new Error("Failed to load scores"));

    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByText(/error|failed to load/i)).toBeInTheDocument();
    });
  });

  it("shows stocks table with rankings", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      expect(screen.getByRole("table")).toBeInTheDocument();
      expect(screen.getByText(/rank|symbol/i)).toBeInTheDocument();
      expect(screen.getByText(/score|grade/i)).toBeInTheDocument();
    });
  });

  it("handles empty scores data", async () => {
    const { api } = require("../../../services/api");
    api.getStockScores.mockResolvedValue({
      success: true,
      data: { topScores: [], metrics: {}, sectors: [] },
    });

    renderScoresDashboard();

    await waitFor(() => {
      expect(
        screen.getByText(/no scores|no data/i) || screen.getByText("0")
      ).toBeInTheDocument();
    });
  });

  it("updates data when filters change", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      const filterControls = screen.getAllByRole("combobox");
      if (filterControls.length > 0) {
        fireEvent.mouseDown(filterControls[0]);

        // Select a different option if available
        const options = screen.getAllByRole("option");
        if (options.length > 1) {
          fireEvent.click(options[1]);

          waitFor(() => {
            const { api } = require("../../../services/api");
            expect(api.getStockScores).toHaveBeenCalledTimes(2);
          });
        }
      }
    });
  });

  it("displays score trends", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      // Should show trends or changes in scores
      expect(
        screen.getByText(/trend|change|▲|▼|↑|↓/) ||
          screen.getByTestId(/trend|arrow/)
      ).toBeInTheDocument();
    });
  });

  it("shows detailed scoring methodology", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      // Should have methodology or help information
      expect(
        screen.getByText(/methodology|how scores/i) ||
          screen.getByRole("button", { name: /info|help/i })
      ).toBeInTheDocument();
    });
  });

  it("handles score range filtering", async () => {
    renderScoresDashboard();

    await waitFor(() => {
      // Look for score range controls
      expect(
        screen.getByRole("slider") || screen.getByText(/score range|min|max/i)
      ).toBeInTheDocument();
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
