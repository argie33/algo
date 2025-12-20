/**
 * EarningsCalendar Page Unit Tests
 * Tests the earnings calendar functionality - weekly calendar, symbol drill-down, earnings details
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

import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import EarningsCalendar from "../../../pages/EarningsCalendar.jsx";

// Mock createMockUser function
const createMockUser = () => ({
  id: 1,
  email: "test@example.com",
  name: "Test User",
});

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
  })),
  AuthProvider: vi.fn(({ children }) => children),
}));

// Mock API service with standardized pattern
vi.mock("../../../services/api.js", () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: {} }),
    post: vi.fn().mockResolvedValue({ data: {} }),
    getEarningsCalendar: vi.fn().mockResolvedValue({ success: true, data: [] }),
    getEarningsEstimates: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getEarningsHistory: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getTradingSignalsDaily: vi.fn().mockResolvedValue({ success: true, data: [] }),
    getPortfolioAnalytics: vi.fn().mockResolvedValue({ success: true, data: {} }),
    getStockMetrics: vi.fn().mockResolvedValue({ success: true, data: {} }),
  },
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    environment: "test",
  })),
}));

// Mock fetch for direct API calls
global.fetch = vi.fn();

const mockCalendarData = {
  data: {
    data: [
      {
        symbol: "AAPL",
        company: "Apple Inc.",
        start_date: "2024-01-25",
        end_date: "2024-01-25",
        event_type: "Earnings",
        title: "Q1 2024 Earnings",
        fetched_at: "2024-01-20T10:00:00Z",
      },
      {
        symbol: "GOOGL",
        company: "Alphabet Inc.",
        start_date: "2024-01-24",
        end_date: "2024-01-24",
        event_type: "Earnings",
        title: "Q4 2023 Earnings",
        fetched_at: "2024-01-20T10:00:00Z",
      },
    ],
  },
  summary: {
    upcoming_events: 12,
    this_week: 2,
    database_integrated: true,
    real_time_data: true,
  },
};

const mockEstimatesData = {
  data: {
    AAPL: {
      company_name: "Apple Inc.",
      estimates: [
        {
          period: "Q1 2024",
          avg_estimate: 2.11,
          low_estimate: 1.95,
          high_estimate: 2.25,
          number_of_analysts: 24,
          growth: 5.2,
        },
      ],
    },
    GOOGL: {
      company_name: "Alphabet Inc.",
      estimates: [
        {
          period: "Q4 2023",
          avg_estimate: 1.34,
          low_estimate: 1.2,
          high_estimate: 1.5,
          number_of_analysts: 18,
          growth: 8.5,
        },
      ],
    },
  },
  pagination: {
    total: 2,
  },
  summary: {
    recent_updates: 15,
  },
};

const mockHistoryData = {
  data: {
    AAPL: {
      company_name: "Apple Inc.",
      history: [
        {
          quarter: "2023-12-31",
          eps_actual: 2.18,
          eps_estimate: 2.11,
          eps_difference: 0.07,
          surprise_percent: 3.32,
        },
      ],
    },
    GOOGL: {
      company_name: "Alphabet Inc.",
      history: [
        {
          quarter: "2023-09-30",
          eps_actual: 1.55,
          eps_estimate: 1.45,
          eps_difference: 0.1,
          surprise_percent: 6.9,
        },
      ],
    },
  },
  summary: {
    positive_surprises: 5,
  },
};

const mockEpsRevisions = {
  data: [
    {
      period: "Q1 2024",
      avg_estimate: 2.11,
      low_estimate: 1.95,
      high_estimate: 2.25,
      number_of_analysts: 24,
    },
  ],
};

const mockEpsTrend = {
  data: [
    {
      period: "Q1 2024",
      avg_estimate: 2.11,
      year_ago_eps: 2.00,
      growth: 5.5,
      number_of_analysts: 24,
    },
  ],
};

const mockMetrics = {
  data: {
    AAPL: {
      metrics: [
        {
          report_date: "2024-01-25",
          eps_yoy_growth: 8.2,
          revenue_yoy_growth: 6.5,
        },
      ],
    },
    GOOGL: {
      metrics: [
        {
          report_date: "2024-01-24",
          eps_yoy_growth: 6.5,
          revenue_yoy_growth: 5.8,
        },
      ],
    },
  },
};

// Test render helper
function renderEarningsCalendar(props = {}) {
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
        <EarningsCalendar {...props} />
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("EarningsCalendar Component", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Setup fetch mocks for different endpoints
    fetch.mockImplementation((url) => {
      if (url.includes("/api/earnings/events")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockCalendarData),
        });
      }

      if (url.includes("/api/earnings/estimates")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockEstimatesData),
        });
      }

      if (url.includes("/api/earnings/history")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockHistoryData),
        });
      }

      if (url.includes("/api/analysts/") && url.includes("/eps-revisions")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockEpsRevisions),
        });
      }

      if (url.includes("/api/analysts/") && url.includes("/eps-trend")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockEpsTrend),
        });
      }

      if (url.includes("/api/earnings/data")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockMetrics),
        });
      }

      // Default mock
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: {} }),
      });
    });
  });

  it("renders earnings calendar page", async () => {
    renderEarningsCalendar();

    // Wait for the initial fetch to complete and the page to load
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/earnings/events")
      );
    }, { timeout: 3000 });

    // Wait for the loading to complete and the title to appear
    await waitFor(() => {
      expect(
        screen.getByText(/earnings calendar/i)
      ).toBeInTheDocument();
    }, { timeout: 5000 });
  });

  it("displays weekly earnings calendar section", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText(/this week's earnings/i)).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it("displays earnings data table when loaded", async () => {
    renderEarningsCalendar();

    // Wait for the fetch call first
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/earnings/events")
      );
    }, { timeout: 3000 });

    // Wait for the data to be rendered
    await waitFor(() => {
      const tables = screen.getAllByRole("table");
      expect(tables.length).toBeGreaterThan(0);
    }, { timeout: 8000 });

    // Check for table headers
    await waitFor(() => {
      expect(screen.getByRole("columnheader", { name: /symbol/i })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: /company/i })).toBeInTheDocument();
      expect(screen.getByRole("columnheader", { name: /quality score/i })).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it("shows loading state initially", async () => {
    // Mock a hanging promise to keep loading state
    fetch.mockImplementationOnce(() => new Promise(() => {}));

    renderEarningsCalendar();

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    fetch.mockRejectedValueOnce(new Error("API Error"));

    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it("displays stock symbols when data loaded", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    }, { timeout: 3000 });

    expect(screen.getByText("GOOGL")).toBeInTheDocument();
  });

  it("displays company names", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
      expect(screen.getByText("Alphabet Inc.")).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it("displays summary statistics cards", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText(/upcoming events/i)).toBeInTheDocument();
      expect(screen.getByText(/this week/i)).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it("shows search functionality", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/search symbol/i)).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it("handles empty earnings data", async () => {
    fetch.mockImplementation((url) => {
      if (url.includes("/api/earnings/events")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              data: { data: [] },
              summary: { upcoming_events: 0, this_week: 0 },
            }),
        });
      }
      if (url.includes("/api/earnings/estimates")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ data: {}, pagination: { total: 0 } }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: {} }),
      });
    });

    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText(/no earnings data found/i) || screen.getByText(/no earnings scheduled/i)).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it("displays EPS estimates with range", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    }, { timeout: 3000 });

    // Should show estimates data
    await waitFor(() => {
      expect(screen.getByText(/Q1 2024/)).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it("shows analyst counts", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText("24")).toBeInTheDocument();
      expect(screen.getByText("18")).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it("displays growth percentages", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    }, { timeout: 3000 });

    // Should show growth data (5.2% and 8.5%)
    await waitFor(() => {
      const growthElements = screen.getAllByText(/\d+\.\d+%/);
      expect(growthElements.length).toBeGreaterThan(0);
    }, { timeout: 3000 });
  });

  it("handles database connectivity issues gracefully", async () => {
    fetch.mockImplementation((url) => {
      if (url.includes("/api/earnings/events")) {
        return Promise.resolve({
          ok: false,
          status: 503,
          json: () =>
            Promise.resolve({
              success: false,
              error: "Database temporarily unavailable",
              message: "Unable to retrieve earnings calendar data",
            }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: {} }),
      });
    });

    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it("shows pagination controls", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    }, { timeout: 3000 });

    // Check for pagination component
    await waitFor(() => {
      const paginationText = screen.getByText(/1.*2.*of.*2/i) || screen.getByText(/rows per page/i);
      expect(paginationText).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it("displays Earnings Estimates & Details heading", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText(/earnings estimates & details/i)).toBeInTheDocument();
    }, { timeout: 3000 });
  });
});
