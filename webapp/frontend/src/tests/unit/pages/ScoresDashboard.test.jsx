/**
 * ScoresDashboard Page Unit Tests
 *
 * Component facts (from ScoresDashboard.jsx):
 * - Title: "Bullseye Stock Screener"
 * - Subtitle: "Multi-factor stock scoring..."
 * - Uses useApiQuery wrapping api.get("/api/scores/stockscores?...")
 * - KPI cards: "Universe", "Composite >= 80", "Market Avg", "Top Decile"
 * - Search input: placeholder "Search symbol..."
 * - Filter button (Clear), score/grade display
 * - Table-based layout (not MUI accordion)
 * - Factor labels: Quality, Momentum, Value, Growth, Positioning, Stability
 * - On error: shows alert-danger div
 * - Loading: shows "Loading scores..."
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ScoresDashboard from "../../../pages/ScoresDashboard.jsx";

vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: { id: "test-user-123", email: "test@example.com", name: "Test User" },
    isAuthenticated: true,
    isLoading: false,
  })),
  AuthProvider: vi.fn(({ children }) => children),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return { ...actual, useNavigate: () => mockNavigate };
});

// Two mock stocks for the /api/scores/stockscores endpoint
const mockStocks = [
  {
    symbol: "AAPL",
    company_name: "Apple Inc.",
    composite_score: 88.7,
    quality_score: 88.7,
    momentum_score: 85.2,
    value_score: 78.3,
    growth_score: 82.1,
    positioning_score: 84.5,
    stability_score: 79.2,
    price: 175.5,
    change_percent: 1.2,
    sector: "Technology",
  },
  {
    symbol: "MSFT",
    company_name: "Microsoft Corporation",
    composite_score: 91.2,
    quality_score: 91.2,
    momentum_score: 88.5,
    value_score: 85.1,
    growth_score: 89.5,
    positioning_score: 86.7,
    stability_score: 82.4,
    price: 420.75,
    change_percent: 2.1,
    sector: "Technology",
  },
];

vi.mock("../../../services/api", () => {
  const mockApi = {
    get: vi.fn(() =>
      Promise.resolve({
        data: { items: mockStocks },
      })
    ),
    post: vi.fn(() => Promise.resolve({ data: {} })),
  };
  return {
    default: mockApi,
    api: mockApi,
  };
});

function renderScoresDashboard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/scores"]}>
        <ScoresDashboard />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const defaultMockResponse = {
  data: { items: mockStocks },
};

describe("ScoresDashboard Page", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    mockNavigate.mockClear();
    // Restore default mock after each test (some tests override with error/never-resolve)
    const mockApi = await import("../../../services/api");
    mockApi.api.get.mockResolvedValue(defaultMockResponse);
  });

  it("renders the Bullseye Stock Screener title", async () => {
    renderScoresDashboard();
    await waitFor(() => {
      expect(screen.getByText(/Bullseye Stock Screener/i)).toBeInTheDocument();
    });
  });

  it("displays KPI cards with labels", async () => {
    renderScoresDashboard();
    await waitFor(() => {
      expect(screen.getByText("Universe")).toBeInTheDocument();
    });
  });

  it("displays search input", async () => {
    renderScoresDashboard();
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/Search symbol/i)).toBeInTheDocument();
    });
  });

  it("displays stock symbols after data loads", async () => {
    renderScoresDashboard();
    await waitFor(() => {
      expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
      expect(screen.getAllByText("MSFT").length).toBeGreaterThan(0);
    });
  });

  it("displays table headers for score factors", async () => {
    renderScoresDashboard();
    await waitFor(() => {
      // Table shows column headers Symbol, Composite, Grade, Quality, Mom, Value, Growth, Pos, Stab
      expect(screen.getByText("Symbol")).toBeInTheDocument();
      expect(screen.getByText("Composite")).toBeInTheDocument();
      expect(screen.getByText("Grade")).toBeInTheDocument();
    });
  });

  it("displays filter controls", async () => {
    renderScoresDashboard();
    await waitFor(() => {
      // Clear button and sort selects are present
      expect(
        screen.getByRole("button", { name: /Clear/i })
      ).toBeInTheDocument();
    });
  });

  it("filters stocks based on search input", async () => {
    renderScoresDashboard();
    await waitFor(() => {
      expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
    });

    const searchInput = screen.getByPlaceholderText(/Search symbol/i);
    fireEvent.change(searchInput, { target: { value: "AAPL" } });

    await waitFor(() => {
      expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
      expect(screen.queryAllByText("MSFT").length).toBe(0);
    });
  });

  it("shows empty state when search has no results", async () => {
    renderScoresDashboard();
    await waitFor(() => {
      expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
    });

    const searchInput = screen.getByPlaceholderText(/Search symbol/i);
    fireEvent.change(searchInput, { target: { value: "NONEXISTENT" } });

    await waitFor(() => {
      expect(screen.getByText(/No stocks match/i)).toBeInTheDocument();
    });
  });

  it("shows loading state initially when API never resolves", async () => {
    const mockApi = await import("../../../services/api");
    mockApi.api.get.mockImplementation(() => new Promise(() => {}));
    renderScoresDashboard();
    await waitFor(() => {
      expect(screen.getByText(/Loading scores/i)).toBeInTheDocument();
    });
  });

  it("handles API errors by showing error state", async () => {
    const mockApi = await import("../../../services/api");
    mockApi.api.get.mockRejectedValue(new Error("API Error"));
    renderScoresDashboard();
    await waitFor(() => {
      // On error, component shows alert-danger or empty/no-stocks state
      const errorEl = document.querySelector(".alert-danger");
      const emptyEl = screen.queryByText(/No stocks match/i);
      expect(errorEl || emptyEl).toBeTruthy();
    });
  });

  it("displays grades next to composite scores", async () => {
    renderScoresDashboard();
    await waitFor(() => {
      // AAPL at 88.7 => A, MSFT at 91.2 => A+
      const grades = document.querySelectorAll("td");
      const gradeTexts = Array.from(grades).map((el) => el.textContent?.trim());
      const hasGrade = gradeTexts.some((t) => /^[A-F][+-]?$/.test(t));
      expect(hasGrade).toBeTruthy();
    });
  });

  it("renders tab navigation buttons", async () => {
    renderScoresDashboard();
    await waitFor(() => {
      // Component renders tab buttons: Rankings, Top Movers, A-Grade >= 80, etc.
      expect(
        screen.getByRole("button", { name: /Rankings/i })
      ).toBeInTheDocument();
    });
  });

  it("renders Refresh button", async () => {
    renderScoresDashboard();
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Refresh/i })
      ).toBeInTheDocument();
    });
  });

  it("clears search when Clear button is clicked", async () => {
    renderScoresDashboard();
    await waitFor(() => {
      expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
    });

    const searchInput = screen.getByPlaceholderText(/Search symbol/i);
    fireEvent.change(searchInput, { target: { value: "AAPL" } });

    await waitFor(() => {
      expect(screen.queryAllByText("MSFT").length).toBe(0);
    });

    fireEvent.click(screen.getByRole("button", { name: /Clear/i }));

    await waitFor(() => {
      expect(screen.getAllByText("MSFT").length).toBeGreaterThan(0);
    });
  });
});
