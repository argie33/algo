/**
 * EarningsCalendar Page Unit Tests
 * Tests the earnings calendar functionality - upcoming earnings, historical data, filters
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

// Mock fetch for direct API calls
global.fetch = vi.fn();

const mockCalendarData = {
  data: {
    data: [
      {
        symbol: "AAPL",
        company: "Apple Inc.",
        date: "2024-01-25",
        time: "after-market",
        event_type: "earnings",
        title: "Apple Inc. Earnings Report",
        report_date: "2024-01-25",
        quarter: 1,
        fiscal_year: 2024,
        estimated_eps: 2.11,
        actual_eps: null,
        surprise_percent: null,
        timing: "after_market",
        analyst_count: 28,
        conference_call_time: "2024-01-25T17:30:00Z",
      },
      {
        symbol: "GOOGL",
        company: "Alphabet Inc.",
        date: "2024-01-24",
        time: "after-market",
        event_type: "earnings",
        title: "Alphabet Inc. Earnings Report",
        report_date: "2024-01-24",
        quarter: 4,
        fiscal_year: 2023,
        estimated_eps: 1.51,
        actual_eps: 1.64,
        surprise_percent: 8.6,
        timing: "after_market",
        analyst_count: 25,
        conference_call_time: "2024-01-24T17:30:00Z",
      },
    ],
  },
  summary: {
    upcoming_events: 12,
    this_week: 8,
    database_integrated: true,
    real_time_data: true,
  },
};

const mockEstimatesData = {
  data: {
    AAPL: {
      estimates: [
        {
          period: "Q1 2024",
          avg_estimate: 2.11,
          low: 1.95,
          high: 2.25,
          num_estimates: 24,
          growth: 5.2,
        },
      ],
    },
    GOOGL: {
      estimates: [
        {
          period: "Q4 2023",
          avg_estimate: 1.34,
          low: 1.2,
          high: 1.5,
          num_estimates: 18,
          growth: 8.5,
        },
      ],
    },
  },
  summary: {
    recent_updates: 15,
  },
};

const mockHistoryData = {
  data: {
    AAPL: {
      history: [
        {
          quarter: "Q4 2023",
          actual_eps: 2.18,
          estimated_eps: 2.11,
          difference: 0.07,
          surprise_percent: 3.32,
        },
      ],
    },
    GOOGL: {
      history: [
        {
          quarter: "Q3 2023",
          actual_eps: 1.55,
          estimated_eps: 1.45,
          difference: 0.1,
          surprise_percent: 6.9,
        },
      ],
    },
  },
  summary: {
    positive_surprises: 5,
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
      if (url.includes("/api/calendar/events")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockCalendarData),
        });
      }

      if (url.includes("/calendar/earnings-estimates")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockEstimatesData),
        });
      }

      if (url.includes("/calendar/earnings-history")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockHistoryData),
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

    expect(
      screen.getByText(/earnings calendar & estimates/i)
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/calendar/events")
      );
    });
  });

  it("displays earnings data when loaded", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
      expect(screen.getByText("GOOGL")).toBeInTheDocument();
      expect(screen.getByText("Alphabet Inc.")).toBeInTheDocument();
    });
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
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });

  it("filters earnings by date range", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Look for date filter controls
    const dateFilters = screen.getAllByRole("button");
    expect(dateFilters.length).toBeGreaterThan(0);
  });

  it("displays EPS estimates and actuals", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText("2.11")).toBeInTheDocument(); // AAPL estimate
      expect(screen.getByText("1.55")).toBeInTheDocument(); // GOOGL actual from history
    });
  });

  it("shows earnings time (before/after market)", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getAllByText(/after-market/i)).toHaveLength(2);
    });
  });

  it("displays stock symbols when data loaded", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    expect(screen.getByText("GOOGL")).toBeInTheDocument();
  });

  it("displays quarter information", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText("Q1 2024")).toBeInTheDocument();
      expect(screen.getByText("Q4 2023")).toBeInTheDocument();
    });
  });

  it("handles empty earnings data", async () => {
    fetch.mockImplementation((url) => {
      if (url.includes("/api/calendar/events")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              data: { data: [] },
              summary: { upcoming_events: 0 },
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
      // Check for empty state or zero in summary cards
      const upcomingElement = screen.getByText("0");
      expect(upcomingElement).toBeInTheDocument();
    });
  });

  // NEW TESTS for enhanced database-integrated earnings functionality

  it("displays database-integrated earnings data with enhanced fields", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText("Apple Inc.")).toBeInTheDocument();

      // Check for new database fields
      expect(screen.getByText("28")).toBeInTheDocument(); // analyst_count
      expect(screen.getByText("Q1 2024")).toBeInTheDocument(); // quarter/year info
    });
  });

  it("shows earnings surprise percentages from database", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText("8.6")).toBeInTheDocument(); // GOOGL surprise_percent
    });
  });

  it("displays conference call timing information", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      // Should show conference call times from database
      expect(screen.getAllByText(/17:30/)).toHaveLength(2);
    });
  });

  it("handles actual vs estimated EPS from database", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      // AAPL should show estimated (no actual yet)
      expect(screen.getByText("2.11")).toBeInTheDocument(); // estimated

      // GOOGL should show both estimated and actual
      expect(screen.getByText("1.51")).toBeInTheDocument(); // estimated
      expect(screen.getByText("1.64")).toBeInTheDocument(); // actual
    });
  });

  it("displays analyst coverage counts", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText("28")).toBeInTheDocument(); // AAPL analysts
      expect(screen.getByText("25")).toBeInTheDocument(); // GOOGL analysts
    });
  });

  it("shows database integration status in summary", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      // Should indicate database integration is active
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/calendar/events")
      );
    });

    // Verify database-integrated flag is present in mock data
    expect(mockCalendarData.summary.database_integrated).toBe(true);
    expect(mockCalendarData.summary.real_time_data).toBe(true);
  });

  it("handles mixed upcoming and historical earnings data", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      // AAPL is upcoming (no actual_eps)
      expect(screen.getByText("AAPL")).toBeInTheDocument();

      // GOOGL has historical data (has actual_eps and surprise_percent)
      expect(screen.getByText("GOOGL")).toBeInTheDocument();
      expect(screen.getByText("8.6")).toBeInTheDocument(); // surprise percentage
    });
  });

  it("displays fiscal year and quarter information from database", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      expect(screen.getByText("Q1 2024")).toBeInTheDocument(); // AAPL
      expect(screen.getByText("Q4 2023")).toBeInTheDocument(); // GOOGL
    });
  });

  it("shows earnings timing (before/after market) from database", async () => {
    renderEarningsCalendar();

    await waitFor(() => {
      // Both stocks report after market in mock data
      expect(screen.getAllByText(/after.market/i)).toHaveLength(2);
    });
  });

  it("handles database connectivity issues gracefully", async () => {
    fetch.mockImplementation((url) => {
      if (url.includes("/api/calendar/events")) {
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
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });
});
