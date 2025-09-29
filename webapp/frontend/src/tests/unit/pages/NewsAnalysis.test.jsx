/**
 * NewsAnalysis Page Unit Tests
 * Tests the news analysis functionality - news feed, sentiment analysis, filtering
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  renderWithProviders,
  screen,
  waitFor,
  createMockUser,
  fireEvent,
  userEvent,
} from "../../test-utils.jsx";
import NewsAnalysis from "../../../pages/NewsAnalysis.jsx";

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
  })),
}));

// Mock API service
vi.mock("../../../services/api.js", () => ({
  default: {
    get: vi.fn().mockImplementation((url) => {
      if (url.includes('/api/news/articles')) {
        return Promise.resolve({
          data: {
            success: true,
            data: mockNewsData
          }
        });
      }
      if (url.includes('/api/news/market-sentiment')) {
        return Promise.resolve({
          data: {
            success: true,
            data: mockSentimentData
          }
        });
      }
      if (url.includes('/api/news/sentiment-dashboard')) {
        return Promise.resolve({
          data: {
            success: true,
            data: mockDashboardData
          }
        });
      }
      return Promise.resolve({ data: { success: true, data: [] } });
    }),
    post: vi.fn().mockResolvedValue({ data: {} }),
  },
  getNewsAnalysis: vi.fn().mockResolvedValue({ success: true, data: [] }),
  getNewsSentiment: vi.fn().mockResolvedValue({ success: true, data: {} }),
  getNewsKeywords: vi.fn().mockResolvedValue({ success: true, data: [] }),
  searchNews: vi.fn().mockResolvedValue({ success: true, data: [] }),
  getTradingSignalsDaily: vi.fn().mockResolvedValue({ success: true, data: [] }),
  getPortfolioAnalytics: vi.fn().mockResolvedValue({ success: true, data: {} }),
  getStockPrices: vi.fn().mockResolvedValue({ success: true, data: [] }),
  getStockMetrics: vi.fn().mockResolvedValue({ success: true, data: {} }),
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    environment: "test",
  })),
}));

const mockNewsData = [
  {
    id: 1,
    title: "Apple Reports Strong Q4 Earnings",
    summary: "Apple Inc. reported better-than-expected quarterly earnings...",
    url: "https://example.com/news/1",
    source: "Reuters",
    publishedAt: "2024-01-15T10:30:00Z",
    sentiment: "positive",
    sentimentScore: 0.75,
    symbols: ["AAPL"],
    keywords: ["earnings", "revenue", "iPhone"],
  },
  {
    id: 2,
    title: "Market Volatility Continues",
    summary:
      "Stock market faces continued volatility amid economic uncertainty...",
    url: "https://example.com/news/2",
    source: "Bloomberg",
    publishedAt: "2024-01-15T08:15:00Z",
    sentiment: "negative",
    sentimentScore: -0.45,
    symbols: ["SPY", "QQQ"],
    keywords: ["volatility", "market", "uncertainty"],
  },
];

const mockSentimentData = {
  overall: "neutral",
  score: 0.15,
  positive: 45,
  negative: 30,
  neutral: 25,
  trending: [
    { keyword: "earnings", sentiment: "positive", count: 25 },
    { keyword: "inflation", sentiment: "negative", count: 18 },
  ],
};

const mockDashboardData = {
  summary: {
    totalArticles: 150,
    overallSentiment: "neutral",
    sentimentScore: 0.15,
  },
  topSources: [
    { source: "Reuters", count: 25 },
    { source: "Bloomberg", count: 20 },
  ],
  topKeywords: [
    { keyword: "earnings", count: 15 },
    { keyword: "market", count: 12 },
  ],
};

describe("NewsAnalysis Component", () => {
  let api;

  beforeEach(async () => {
    vi.clearAllMocks();
    // The api object is already mocked at the module level, no need to reassign
  });

  it("renders news analysis page", async () => {
    renderWithProviders(<NewsAnalysis />);

    expect(screen.getByText(/news analysis/i)).toBeInTheDocument();
    await waitFor(() => {
      const api = require("../../../services/api.js").default;
      expect(api.getNewsAnalysis).toHaveBeenCalled();
    });
  });

  it("displays news articles", async () => {
    renderWithProviders(<NewsAnalysis />);

    await waitFor(() => {
      expect(
        screen.getByText("Apple Reports Strong Q4 Earnings")
      ).toBeInTheDocument();
      expect(
        screen.getByText("Market Volatility Continues")
      ).toBeInTheDocument();
      expect(screen.getByText("Reuters")).toBeInTheDocument();
      expect(screen.getByText("Bloomberg")).toBeInTheDocument();
    });
  });

  it("shows sentiment indicators", async () => {
    renderWithProviders(<NewsAnalysis />);

    await waitFor(() => {
      expect(screen.getByText(/positive/i)).toBeInTheDocument();
      expect(screen.getByText(/negative/i)).toBeInTheDocument();
      expect(screen.getByText("0.75")).toBeInTheDocument();
      expect(screen.getByText("-0.45")).toBeInTheDocument();
    });
  });

  it("displays overall sentiment summary", async () => {
    renderWithProviders(<NewsAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("neutral")).toBeInTheDocument();
      expect(screen.getByText("45")).toBeInTheDocument(); // positive count
      expect(screen.getByText("30")).toBeInTheDocument(); // negative count
    });
  });

  it("shows loading state initially", () => {
    api.getNewsAnalysis.mockImplementation(() => new Promise(() => {}));

    renderWithProviders(<NewsAnalysis />);

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    api.getNewsAnalysis.mockRejectedValue(new Error("API Error"));

    renderWithProviders(<NewsAnalysis />);

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });

  it("filters news by symbol", async () => {
    api.searchNews.mockResolvedValue({
      success: true,
      data: [mockNewsData[0]], // Only AAPL news
    });

    renderWithProviders(<NewsAnalysis />);

    await waitFor(() => {
      expect(
        screen.getByText("Apple Reports Strong Q4 Earnings")
      ).toBeInTheDocument();
    });

    // Look for symbol filter
    const searchInput =
      screen.getByPlaceholderText(/search/i) ||
      screen.getByLabelText(/filter/i);

    if (searchInput) {
      await userEvent.type(searchInput, "AAPL");

      await waitFor(() => {
        expect(api.searchNews).toHaveBeenCalledWith(
          expect.objectContaining({
            symbol: "AAPL",
          })
        );
      });
    }
  });

  it("filters news by sentiment", async () => {
    renderWithProviders(<NewsAnalysis />);

    await waitFor(() => {
      expect(
        screen.getByText("Apple Reports Strong Q4 Earnings")
      ).toBeInTheDocument();
    });

    // Look for sentiment filter dropdown
    const sentimentFilter = screen.getByRole("combobox", {
      name: /sentiment/i,
    });
    if (sentimentFilter) {
      fireEvent.mouseDown(sentimentFilter);

      const positiveOption = screen.getByText(/positive/i);
      fireEvent.click(positiveOption);

      await waitFor(() => {
        // Should show filtered results
        expect(
          screen.getByText("Apple Reports Strong Q4 Earnings")
        ).toBeInTheDocument();
      });
    }
  });

  it("displays trending keywords", async () => {
    renderWithProviders(<NewsAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("earnings")).toBeInTheDocument();
      expect(screen.getByText("inflation")).toBeInTheDocument();
    });
  });

  it("shows news timestamps", async () => {
    renderWithProviders(<NewsAnalysis />);

    await waitFor(() => {
      // Should display formatted timestamps
      expect(
        screen.getByText(/Jan/i) || screen.getByText(/2024/i)
      ).toBeInTheDocument();
    });
  });

  it("displays news sources", async () => {
    renderWithProviders(<NewsAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("Reuters")).toBeInTheDocument();
      expect(screen.getByText("Bloomberg")).toBeInTheDocument();
    });
  });

  it("shows article summaries", async () => {
    renderWithProviders(<NewsAnalysis />);

    await waitFor(() => {
      expect(
        screen.getByText(/Apple Inc. reported better-than-expected/)
      ).toBeInTheDocument();
      expect(
        screen.getByText(/Stock market faces continued volatility/)
      ).toBeInTheDocument();
    });
  });

  it("handles clicking on news articles", async () => {
    renderWithProviders(<NewsAnalysis />);

    await waitFor(() => {
      expect(
        screen.getByText("Apple Reports Strong Q4 Earnings")
      ).toBeInTheDocument();
    });

    // Click on news title (should open in new tab or show details)
    const newsTitle = screen.getByText("Apple Reports Strong Q4 Earnings");
    fireEvent.click(newsTitle);

    // Since it's a link, check if it has proper attributes
    const linkElement = newsTitle.closest("a");
    if (linkElement) {
      expect(linkElement).toHaveAttribute("href", "https://example.com/news/1");
    }
  });

  it("refreshes news data", async () => {
    renderWithProviders(<NewsAnalysis />);

    await waitFor(() => {
      expect(api.getNewsAnalysis).toHaveBeenCalledTimes(1);
    });

    const refreshButton =
      screen.getByLabelText(/refresh/i) ||
      screen.getByRole("button", { name: /refresh/i });
    fireEvent.click(refreshButton);

    await waitFor(() => {
      expect(api.getNewsAnalysis).toHaveBeenCalledTimes(2);
    });
  });

  it("displays related symbols for each article", async () => {
    renderWithProviders(<NewsAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText("SPY")).toBeInTheDocument();
      expect(screen.getByText("QQQ")).toBeInTheDocument();
    });
  });

  it("handles empty news feed", async () => {
    api.getNewsAnalysis.mockResolvedValue({
      success: true,
      data: [],
    });

    renderWithProviders(<NewsAnalysis />);

    await waitFor(() => {
      expect(
        screen.getByText(/no news/i) || screen.getByText(/no articles/i)
      ).toBeInTheDocument();
    });
  });

  it("displays keyword tags", async () => {
    renderWithProviders(<NewsAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("earnings")).toBeInTheDocument();
      expect(screen.getByText("market")).toBeInTheDocument();
      expect(screen.getByText("volatility")).toBeInTheDocument();
    });
  });

  it("filters by date range", async () => {
    renderWithProviders(<NewsAnalysis />);

    await waitFor(() => {
      expect(
        screen.getByText("Apple Reports Strong Q4 Earnings")
      ).toBeInTheDocument();
    });

    // Look for date filter inputs
    const dateInputs = screen.getAllByDisplayValue(/2024/);
    if (dateInputs.length > 0) {
      await userEvent.clear(dateInputs[0]);
      await userEvent.type(dateInputs[0], "2024-01-15");

      await waitFor(() => {
        expect(api.getNewsAnalysis).toHaveBeenCalledWith(
          expect.objectContaining({
            startDate: "2024-01-15",
          })
        );
      });
    }
  });
});
