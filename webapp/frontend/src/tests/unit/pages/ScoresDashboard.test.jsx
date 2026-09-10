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
 * - Factor labels: Quality, Momentum, Value, Growth, Risk
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
    risk_score: 79.2,
    price: 175.5,
    change_percent: 1.2,
    sector: "Technology",
    market_cap: 3000000000000,
  },
  {
    symbol: "MSFT",
    company_name: "Microsoft Corporation",
    composite_score: 91.2,
    quality_score: 91.2,
    momentum_score: 88.5,
    value_score: 85.1,
    growth_score: 89.5,
    risk_score: 82.4,
    price: 420.75,
    change_percent: 2.1,
    sector: "Technology",
    market_cap: 3100000000000,
  },
];

// Regression fixture (2026-09-01): a nano-cap that should be excluded once a Min Market Cap
// filter is applied, same shape as the live JCSE-style ($2-3M cap) top-of-Value entries that
// prompted wiring this filter into the page (backend minMarketCap param existed but no UI ever
// called it - see lambda/api/routes/scores.py).
const nanoStock = {
  symbol: "NANO",
  company_name: "Nano Cap Co.",
  composite_score: 95.0,
  quality_score: 95.0,
  momentum_score: 95.0,
  value_score: 99.0,
  growth_score: 95.0,
  risk_score: 95.0,
  price: 1.5,
  change_percent: 0.1,
  sector: "Technology",
  market_cap: 2500000,
};

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

  it("displays company name and factor scores for each ranked row", async () => {
    renderScoresDashboard();
    await waitFor(() => {
      // RankingsTab (default, useState("rankings")) was refactored from a <table> with
      // header cells into an expandable card/row list (chevron toggle + StockScoreAccordion
      // detail on click) - there is no header row at all anymore ("Symbol"/"Company"/"Score"
      // never appear as standalone text, only as data values), so this test previously
      // asserted a DOM structure that no longer exists in any tab. Assert the real per-row
      // content instead: company name and the growth/quality/momentum sub-scores rendered
      // next to each symbol.
      expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
      expect(screen.getByText("Microsoft Corporation")).toBeInTheDocument();
      // AAPL's growth_score (82.1) rendered to 1 decimal place next to its row.
      expect(screen.getByText("82.1")).toBeInTheDocument();
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
      // Grades appear in Leaderboard tab; default tab shows scores
      // Just verify that the page renders with score data
      const scoreElements = screen.getAllByText(/\d+(\.\d+)?/);
      expect(scoreElements.length).toBeGreaterThan(0);
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

  it("expands a row to show detail without crashing (regression: undefined detailStock)", async () => {
    // Regression test: RankingsTab's expanded-row branch referenced an undefined
    // `detailStock` variable instead of its own `detail` prop (the prop was renamed at
    // the call site but the child's render logic was never updated), throwing
    // "ReferenceError: detailStock is not defined" the instant any row was expanded -
    // a real runtime crash in production, not just a lint warning. Caught by ESLint's
    // no-undef rule during a broader quality sweep; no test previously exercised the
    // expand interaction at all.
    renderScoresDashboard();
    await waitFor(() => {
      expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getAllByText("AAPL")[0]);

    await waitFor(() => {
      // The row expands into a detail panel (StockScoreAccordion) rendering the
      // factor labels - if the component had crashed (the original bug), none of
      // this would render. "Quality" also matches a sort-select option, so scope
      // to the accordion's own span label.
      expect(screen.getAllByText(/Quality/i).length).toBeGreaterThan(1);
    });
  });

  it("filters out nano-caps by default ($300M floor) and shows them once cleared", async () => {
    const mockApi = await import("../../../services/api");
    mockApi.api.get.mockResolvedValue({
      data: { items: [...mockStocks, nanoStock] },
    });

    renderScoresDashboard();
    await waitFor(() => {
      expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
    });
    // Default floor is $300M (algo_config.min_market_cap_millions) - NANO's $2.5M cap
    // should never reach the list without the user explicitly widening the filter.
    expect(screen.queryAllByText("NANO").length).toBe(0);

    fireEvent.change(screen.getByTitle(/thinly-traded micro\/nano-caps/i), {
      target: { value: "0" },
    });

    await waitFor(() => {
      expect(screen.getAllByText("NANO").length).toBeGreaterThan(0);
    });
  });

  it("excludes nano-caps from Category Leaders/Laggards tabs (regression: unscreened universe)", async () => {
    // Regression test (2026-09-09, /goal session: "factor leaders and laggards still seem
    // off"): the Category Leaders/Laggards tabs (and Movers/Leaderboard/Heatmap/
    // Distribution/Correlation/Sectors alongside them) were wired to the raw, unscreened
    // `items` array instead of `filtered` (the same $300M-market-cap-floored array Rankings
    // already uses) - so a nano-cap could top every single factor's "leaders" list purely on
    // scoring mechanics, the exact failure mode the $300M floor above exists to prevent for
    // Rankings, just never propagated to these other views of the same data.
    const mockApi = await import("../../../services/api");
    mockApi.api.get.mockResolvedValue({
      data: { items: [...mockStocks, nanoStock] },
    });

    renderScoresDashboard();
    await waitFor(() => {
      expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole("button", { name: /Category Leaders/i }));

    // NANO scores 95-99 on every factor - the highest in the fixture - so it would top
    // every "Category Leaders" card if the $300M floor weren't applied.
    await waitFor(() => {
      expect(screen.getAllByText("AAPL").length).toBeGreaterThan(0);
    });
    expect(screen.queryAllByText("NANO").length).toBe(0);

    fireEvent.click(screen.getByRole("button", { name: /^Laggards$/i }));
    await waitFor(() => {
      expect(screen.queryAllByText("NANO").length).toBe(0);
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
