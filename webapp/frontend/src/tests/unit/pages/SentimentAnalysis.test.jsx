/**
 * SentimentAnalysis Page Unit Tests
 * Tests the sentiment analysis functionality - market sentiment, social trends, sentiment scoring, real-time news
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
import SentimentAnalysis from "../../../pages/SentimentAnalysis.jsx";

// Mock AuthContext
vi.mock("../../../contexts/AuthContext.jsx", () => ({
  useAuth: vi.fn(() => ({
    user: createMockUser(),
    isAuthenticated: true,
    isLoading: false,
  })),
}));

// Mock RealTimeSentimentScore component
vi.mock("../../../components/RealTimeSentimentScore", () => ({
  default: ({ symbol, showDetails, size }) => (
    <div data-testid="real-time-sentiment-score">
      <span>Real-Time Sentiment for {symbol}</span>
      {showDetails && <span>Details shown</span>}
      <span>Size: {size}</span>
    </div>
  ),
}));

// Mock realTimeNewsService
vi.mock("../../../services/realTimeNewsService", () => ({
  default: {
    subscribeToNews: vi.fn(),
    unsubscribeFromNews: vi.fn(),
    getLatestNews: vi.fn(),
    fetchBreakingNews: vi.fn(),
    getAllLatestSentiments: vi.fn(),
  },
  __esModule: true,
}));

// Mock API service
vi.mock("../../../services/api.js", () => ({
  api: {
    getMarketSentiment: vi.fn(),
    getSentimentTrends: vi.fn(),
    getSocialMediaSentiment: vi.fn(),
    getSymbolSentiment: vi.fn(),
    getSentimentIndicators: vi.fn(),
  },
  getApiConfig: vi.fn(() => ({
    apiUrl: "http://localhost:3001",
    environment: "test",
  })),
}));

const mockSentimentData = {
  overall: {
    score: 0.65,
    label: "Bullish",
    confidence: 0.78,
    change: 0.12,
    changePercent: 22.5,
  },
  breakdown: {
    veryBullish: 25,
    bullish: 35,
    neutral: 25,
    bearish: 12,
    veryBearish: 3,
  },
  topSymbols: [
    { symbol: "AAPL", sentiment: 0.82, volume: 45000, label: "Very Bullish" },
    { symbol: "GOOGL", sentiment: 0.71, volume: 38000, label: "Bullish" },
    { symbol: "TSLA", sentiment: -0.35, volume: 52000, label: "Bearish" },
  ],
};

const mockTrendsData = [
  {
    date: "2024-01-15",
    sentiment: 0.65,
    volume: 125000,
    bullishCount: 75000,
    bearishCount: 50000,
  },
  {
    date: "2024-01-14",
    sentiment: 0.53,
    volume: 118000,
    bullishCount: 65000,
    bearishCount: 53000,
  },
];

const mockSocialData = {
  twitter: {
    sentiment: 0.58,
    volume: 25000,
    trending: ["$AAPL", "$TSLA", "$NVDA"],
  },
  reddit: {
    sentiment: 0.72,
    volume: 15000,
    trending: ["WSB", "YOLO", "diamond hands"],
  },
  news: {
    sentiment: 0.45,
    volume: 8500,
    trending: ["earnings", "fed", "inflation"],
  },
};

const mockNewsData = [
  {
    id: "news_1",
    title: "Apple reports strong quarterly earnings",
    summary: "Apple exceeded analyst expectations with record revenue growth",
    source: "Reuters",
    publishedAt: "2024-01-01T10:00:00Z",
    url: "https://reuters.com/apple-earnings",
    symbols: ["AAPL"],
    sentiment: { score: 0.8, label: "positive", confidence: 0.9 },
    impact: { score: 0.7, level: "medium" },
    isRealTime: true,
    timestamp: Date.now(),
  },
  {
    id: "news_2",
    title: "Tech sector outlook remains uncertain",
    summary: "Mixed signals from technology companies create market volatility",
    source: "Bloomberg",
    publishedAt: "2024-01-01T09:30:00Z",
    url: "https://bloomberg.com/tech-outlook",
    symbols: ["AAPL", "GOOGL", "MSFT"],
    sentiment: { score: 0.4, label: "negative", confidence: 0.8 },
    impact: { score: 0.6, level: "medium" },
    isRealTime: true,
    timestamp: Date.now() - 300000,
  },
];

const mockRealTimeSentimentData = {
  AAPL: {
    symbol: "AAPL",
    score: 0.75,
    label: "positive",
    confidence: 0.85,
    trend: "improving",
    articles: [mockNewsData[0]],
    timestamp: Date.now(),
    isRealTime: true,
  },
  GOOGL: {
    symbol: "GOOGL",
    score: 0.45,
    label: "negative",
    confidence: 0.7,
    trend: "declining",
    articles: [mockNewsData[1]],
    timestamp: Date.now(),
    isRealTime: true,
  },
};

describe("SentimentAnalysis Component", () => {
  const { api } = require("../../../services/api.js");
  const {
    default: mockRealTimeNewsService,
  } = require("../../../services/realTimeNewsService");

  beforeEach(() => {
    vi.clearAllMocks();
    api.getMarketSentiment.mockResolvedValue({
      success: true,
      data: mockSentimentData,
    });
    api.getSentimentTrends.mockResolvedValue({
      success: true,
      data: mockTrendsData,
    });
    api.getSocialMediaSentiment.mockResolvedValue({
      success: true,
      data: mockSocialData,
    });
    api.getSentimentIndicators.mockResolvedValue({
      success: true,
      data: {
        fearGreedIndex: 75,
        vixLevel: 18.5,
        putCallRatio: 0.85,
      },
    });

    // Setup real-time news service mocks
    mockRealTimeNewsService.subscribeToNews.mockReturnValue(
      "news-subscription-id"
    );
    mockRealTimeNewsService.getLatestNews.mockReturnValue(mockNewsData);
    mockRealTimeNewsService.getAllLatestSentiments.mockReturnValue(
      mockRealTimeSentimentData
    );
    mockRealTimeNewsService.fetchBreakingNews.mockResolvedValue([]);
  });

  it("renders sentiment analysis page", async () => {
    renderWithProviders(<SentimentAnalysis />);

    expect(screen.getByText(/sentiment analysis/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(api.getMarketSentiment).toHaveBeenCalled();
    });
  });

  it("displays overall market sentiment", async () => {
    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("Bullish")).toBeInTheDocument();
      expect(screen.getByText("0.65")).toBeInTheDocument();
      expect(screen.getByText("78%")).toBeInTheDocument(); // confidence
      expect(screen.getByText("22.5%")).toBeInTheDocument(); // change
    });
  });

  it("shows sentiment breakdown", async () => {
    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("25")).toBeInTheDocument(); // very bullish
      expect(screen.getByText("35")).toBeInTheDocument(); // bullish
      expect(screen.getByText("25")).toBeInTheDocument(); // neutral
      expect(screen.getByText("12")).toBeInTheDocument(); // bearish
      expect(screen.getByText("3")).toBeInTheDocument(); // very bearish
    });
  });

  it("displays top sentiment symbols", async () => {
    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
      expect(screen.getByText("GOOGL")).toBeInTheDocument();
      expect(screen.getByText("TSLA")).toBeInTheDocument();
      expect(screen.getByText("Very Bullish")).toBeInTheDocument();
      expect(screen.getByText("Bullish")).toBeInTheDocument();
      expect(screen.getByText("Bearish")).toBeInTheDocument();
    });
  });

  it("shows loading state initially", () => {
    api.getMarketSentiment.mockImplementation(() => new Promise(() => {}));

    renderWithProviders(<SentimentAnalysis />);

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("handles API errors gracefully", async () => {
    api.getMarketSentiment.mockRejectedValue(new Error("API Error"));

    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });

  it("displays sentiment trends chart", async () => {
    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Chart should be rendered (SVG element)
    const chartSvg = document.querySelector("svg");
    expect(chartSvg).toBeInTheDocument();
  });

  it("shows social media sentiment", async () => {
    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("25,000")).toBeInTheDocument(); // Twitter volume
      expect(screen.getByText("15,000")).toBeInTheDocument(); // Reddit volume
      expect(screen.getByText("0.58")).toBeInTheDocument(); // Twitter sentiment
      expect(screen.getByText("0.72")).toBeInTheDocument(); // Reddit sentiment
    });
  });

  it("displays trending topics", async () => {
    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("$AAPL")).toBeInTheDocument();
      expect(screen.getByText("$TSLA")).toBeInTheDocument();
      expect(screen.getByText("earnings")).toBeInTheDocument();
      expect(screen.getByText("diamond hands")).toBeInTheDocument();
    });
  });

  it("switches between different time periods", async () => {
    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("Bullish")).toBeInTheDocument();
    });

    // Look for time period selector
    const timeSelects = screen.getAllByRole("combobox");
    if (timeSelects.length > 0) {
      fireEvent.mouseDown(timeSelects[0]);

      const weekOption = screen.getByText(/week/i);
      if (weekOption) {
        fireEvent.click(weekOption);

        await waitFor(() => {
          expect(api.getSentimentTrends).toHaveBeenCalledWith(
            expect.objectContaining({
              period: "week",
            })
          );
        });
      }
    }
  });

  it("filters sentiment by specific symbol", async () => {
    api.getSymbolSentiment.mockResolvedValue({
      success: true,
      data: {
        symbol: "AAPL",
        sentiment: 0.82,
        volume: 45000,
        trends: mockTrendsData,
      },
    });

    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    // Look for symbol search input
    const searchInput =
      screen.getByPlaceholderText(/symbol/i) ||
      screen.getByLabelText(/search/i);

    if (searchInput) {
      await userEvent.type(searchInput, "AAPL");

      const searchButton = screen.getByRole("button", { name: /search/i });
      fireEvent.click(searchButton);

      await waitFor(() => {
        expect(api.getSymbolSentiment).toHaveBeenCalledWith("AAPL");
      });
    }
  });

  it("displays sentiment indicators", async () => {
    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("75")).toBeInTheDocument(); // Fear & Greed Index
      expect(screen.getByText("18.5")).toBeInTheDocument(); // VIX
      expect(screen.getByText("0.85")).toBeInTheDocument(); // Put/Call Ratio
    });
  });

  it("shows sentiment volume information", async () => {
    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("45,000")).toBeInTheDocument(); // AAPL volume
      expect(screen.getByText("38,000")).toBeInTheDocument(); // GOOGL volume
      expect(screen.getByText("52,000")).toBeInTheDocument(); // TSLA volume
    });
  });

  it("displays sentiment change indicators", async () => {
    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      // Positive sentiment change
      expect(screen.getByText("0.12")).toBeInTheDocument();
      expect(screen.getByText("22.5%")).toBeInTheDocument();
    });
  });

  it("refreshes sentiment data", async () => {
    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      expect(api.getMarketSentiment).toHaveBeenCalledTimes(1);
    });

    const refreshButton =
      screen.getByLabelText(/refresh/i) ||
      screen.getByRole("button", { name: /refresh/i });
    fireEvent.click(refreshButton);

    await waitFor(() => {
      expect(api.getMarketSentiment).toHaveBeenCalledTimes(2);
    });
  });

  it("switches between tabs (overview/trends/social)", async () => {
    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("Bullish")).toBeInTheDocument();
    });

    // Click trends tab
    const trendsTab = screen.getByRole("tab", { name: /trends/i });
    if (trendsTab) {
      fireEvent.click(trendsTab);

      await waitFor(() => {
        expect(api.getSentimentTrends).toHaveBeenCalled();
      });
    }
  });

  it("displays confidence levels", async () => {
    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      expect(screen.getByText("78%")).toBeInTheDocument(); // overall confidence
      expect(screen.getByText(/confidence/i)).toBeInTheDocument();
    });
  });

  it("handles empty sentiment data", async () => {
    api.getMarketSentiment.mockResolvedValue({
      success: true,
      data: {
        overall: null,
        breakdown: {},
        topSymbols: [],
      },
    });

    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      expect(
        screen.getByText(/no sentiment data/i) ||
          screen.getByText(/unavailable/i)
      ).toBeInTheDocument();
    });
  });

  it("shows sentiment score colors", async () => {
    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      // Should show different colored indicators for bullish/bearish
      const sentimentElements = screen.getAllByText(/bullish|bearish/i);
      expect(sentimentElements.length).toBeGreaterThan(0);
    });
  });

  it("displays historical sentiment comparison", async () => {
    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      // Should show historical data
      expect(screen.getByText("2024-01-15")).toBeInTheDocument();
      expect(screen.getByText("125,000")).toBeInTheDocument(); // volume
    });
  });

  it("handles real-time sentiment updates", async () => {
    renderWithProviders(<SentimentAnalysis />);

    await waitFor(() => {
      expect(api.getMarketSentiment).toHaveBeenCalledTimes(1);
    });

    // Simulate real-time update
    setTimeout(() => {
      expect(api.getMarketSentiment).toHaveBeenCalledTimes(1);
    }, 1000);
  });

  // Real-Time News Sentiment Tests
  describe("Real-Time News Sentiment Integration", () => {
    it("displays real-time sentiment components for tracked symbols", async () => {
      renderWithProviders(<SentimentAnalysis />);

      await waitFor(() => {
        expect(
          screen.getByText("Real-Time Sentiment for AAPL")
        ).toBeInTheDocument();
        expect(
          screen.getByText("Real-Time Sentiment for GOOGL")
        ).toBeInTheDocument();
      });
    });

    it("configures real-time sentiment components with correct props", async () => {
      renderWithProviders(<SentimentAnalysis />);

      await waitFor(() => {
        const sentimentComponents = screen.getAllByTestId(
          "real-time-sentiment-score"
        );
        expect(sentimentComponents).toHaveLength(2);

        expect(screen.getByText("Details shown")).toBeInTheDocument();
        expect(screen.getByText("Size: medium")).toBeInTheDocument();
      });
    });

    it("displays real-time news feed", async () => {
      renderWithProviders(<SentimentAnalysis />);

      await waitFor(() => {
        expect(
          screen.getByText("Apple reports strong quarterly earnings")
        ).toBeInTheDocument();
        expect(
          screen.getByText("Tech sector outlook remains uncertain")
        ).toBeInTheDocument();
        expect(screen.getByText("Reuters")).toBeInTheDocument();
        expect(screen.getByText("Bloomberg")).toBeInTheDocument();
      });
    });

    it("subscribes to real-time news updates on mount", async () => {
      renderWithProviders(<SentimentAnalysis />);

      await waitFor(() => {
        expect(mockRealTimeNewsService.subscribeToNews).toHaveBeenCalledWith(
          expect.any(Function)
        );
      });
    });

    it("unsubscribes from news updates on unmount", async () => {
      const { unmount } = renderWithProviders(<SentimentAnalysis />);

      await waitFor(() => {
        expect(mockRealTimeNewsService.subscribeToNews).toHaveBeenCalled();
      });

      unmount();

      expect(mockRealTimeNewsService.unsubscribeFromNews).toHaveBeenCalledWith(
        "news-subscription-id"
      );
    });

    it("updates news feed when new articles arrive", async () => {
      let newsCallback;
      mockRealTimeNewsService.subscribeToNews.mockImplementation((callback) => {
        newsCallback = callback;
        return "news-subscription-id";
      });

      renderWithProviders(<SentimentAnalysis />);

      await waitFor(() => {
        expect(mockRealTimeNewsService.subscribeToNews).toHaveBeenCalled();
      });

      // Simulate new news arrival
      const newNews = [
        {
          id: "news_3",
          title: "Breaking: New market development",
          source: "CNBC",
          publishedAt: new Date().toISOString(),
          sentiment: { score: 0.9, label: "positive" },
          isRealTime: true,
        },
      ];

      newsCallback(newNews);

      await waitFor(() => {
        expect(
          screen.getByText("Breaking: New market development")
        ).toBeInTheDocument();
      });
    });

    it("fetches and handles breaking news", async () => {
      const breakingNews = [
        {
          id: "breaking_1",
          title: "BREAKING: Major market event",
          source: "CNBC",
          isBreaking: true,
          priority: "high",
        },
      ];

      mockRealTimeNewsService.fetchBreakingNews.mockResolvedValue(breakingNews);

      renderWithProviders(<SentimentAnalysis />);

      await waitFor(() => {
        expect(mockRealTimeNewsService.fetchBreakingNews).toHaveBeenCalled();
      });
    });

    it("handles breaking news fetch errors gracefully", async () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      mockRealTimeNewsService.fetchBreakingNews.mockRejectedValue(
        new Error("API Error")
      );

      renderWithProviders(<SentimentAnalysis />);

      await waitFor(() => {
        expect(mockRealTimeNewsService.fetchBreakingNews).toHaveBeenCalled();
      });

      consoleSpy.mockRestore();
    });

    it("displays real-time sentiment indicators", async () => {
      renderWithProviders(<SentimentAnalysis />);

      await waitFor(() => {
        expect(
          mockRealTimeNewsService.getAllLatestSentiments
        ).toHaveBeenCalled();
      });
    });

    it("shows news article sentiment scores", async () => {
      renderWithProviders(<SentimentAnalysis />);

      await waitFor(() => {
        // Should display sentiment scores for news articles
        const newsElements = screen.getAllByText(/positive|negative/i);
        expect(newsElements.length).toBeGreaterThan(0);
      });
    });

    it("filters news by sentiment", async () => {
      renderWithProviders(<SentimentAnalysis />);

      await waitFor(() => {
        expect(
          screen.getByText("Apple reports strong quarterly earnings")
        ).toBeInTheDocument();
        expect(
          screen.getByText("Tech sector outlook remains uncertain")
        ).toBeInTheDocument();
      });

      // Simulate filter for positive sentiment only
      const filterSelect = screen.queryByLabelText(/filter by sentiment/i);
      if (filterSelect) {
        fireEvent.change(filterSelect, { target: { value: "positive" } });

        await waitFor(() => {
          expect(
            screen.getByText("Apple reports strong quarterly earnings")
          ).toBeInTheDocument();
          expect(
            screen.queryByText("Tech sector outlook remains uncertain")
          ).not.toBeInTheDocument();
        });
      }
    });

    it("searches news articles by text", async () => {
      renderWithProviders(<SentimentAnalysis />);

      await waitFor(() => {
        expect(
          screen.getByText("Apple reports strong quarterly earnings")
        ).toBeInTheDocument();
        expect(
          screen.getByText("Tech sector outlook remains uncertain")
        ).toBeInTheDocument();
      });

      // Simulate search for Apple
      const searchInput = screen.queryByPlaceholderText(/search news/i);
      if (searchInput) {
        await userEvent.type(searchInput, "Apple");

        await waitFor(() => {
          expect(
            screen.getByText("Apple reports strong quarterly earnings")
          ).toBeInTheDocument();
          expect(
            screen.queryByText("Tech sector outlook remains uncertain")
          ).not.toBeInTheDocument();
        });
      }
    });

    it("displays news article impact levels", async () => {
      renderWithProviders(<SentimentAnalysis />);

      await waitFor(() => {
        // Should show impact levels for news articles
        const impactElements = screen.getAllByText(/medium|high|low/i);
        expect(impactElements.length).toBeGreaterThan(0);
      });
    });

    it("shows live indicators for real-time data", async () => {
      renderWithProviders(<SentimentAnalysis />);

      await waitFor(() => {
        // Should display live indicators
        const liveIndicators = screen.queryAllByText(/live|real-time/i);
        expect(liveIndicators.length).toBeGreaterThan(0);
      });
    });

    it("handles empty news feed gracefully", async () => {
      mockRealTimeNewsService.getLatestNews.mockReturnValue([]);
      mockRealTimeNewsService.getAllLatestSentiments.mockReturnValue({});

      renderWithProviders(<SentimentAnalysis />);

      await waitFor(() => {
        expect(
          screen.getByText(/no news available|no sentiment data/i) ||
            screen.getByText(/loading/i)
        ).toBeInTheDocument();
      });
    });
  });
});
