import { vi, beforeEach, afterEach, describe, test, expect } from "vitest";
import realTimeNewsService from "../../../services/realTimeNewsService.js";

// Mock the realTimeDataService
vi.mock("../../../services/realTimeDataService.js", () => ({
  default: {
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
  },
  __esModule: true,
}));

// Mock the api service
vi.mock("../../../services/api.js", () => ({
  default: {
    get: vi.fn(),
  },
  __esModule: true,
}));

const { default: mockRealTimeDataService } = await import(
  "../../../services/realTimeDataService.js"
);
const { default: mockApi } = await import("../../../services/api.js");

const mockNewsData = {
  articles: [
    {
      id: "news_1",
      title: "Apple reports strong earnings",
      summary: "Apple exceeded expectations in Q4 earnings",
      source: "Reuters",
      publishedAt: "2024-01-01T10:00:00Z",
      url: "https://reuters.com/apple-earnings",
      symbols: ["AAPL"],
      sentiment: { score: 0.8, label: "positive", confidence: 0.9 },
      impact: { score: 0.7, level: "medium" },
    },
    {
      id: "news_2",
      title: "Tech sector outlook remains bullish",
      summary: "Analysts remain optimistic about tech growth",
      source: "Bloomberg",
      publishedAt: "2024-01-01T09:30:00Z",
      url: "https://bloomberg.com/tech-outlook",
      symbols: ["AAPL", "GOOGL", "MSFT"],
      sentiment: { score: 0.75, label: "positive", confidence: 0.8 },
      impact: { score: 0.8, level: "high" },
    },
  ],
};

const mockSentimentData = {
  symbol: "AAPL",
  sentiment: {
    score: 0.75,
    label: "positive",
    confidence: 0.85,
    trend: "improving",
    sources: [
      { source: "Reuters", score: 0.8 },
      { source: "Bloomberg", score: 0.7 },
    ],
    newsImpact: [{ title: "Apple earnings beat", impact: 0.8 }],
  },
  timestamp: Date.now(),
};

const mockBreakingNewsData = {
  article: {
    id: "breaking_1",
    title: "BREAKING: Apple announces major acquisition",
    summary: "Apple to acquire AI startup for $2B",
    source: "CNBC",
    publishedAt: new Date().toISOString(),
    url: "https://cnbc.com/apple-acquisition",
    symbols: ["AAPL"],
    priority: "high",
  },
};

describe("RealTimeNewsService", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();

    // Reset service state
    realTimeNewsService.newsSubscribers.clear();
    realTimeNewsService.sentimentSubscribers.clear();
    realTimeNewsService.latestNews = [];
    realTimeNewsService.latestSentiment = {};
    realTimeNewsService.newsBuffer = [];
    realTimeNewsService.isProcessingNews = false;
  });

  afterEach(() => {
    vi.useRealTimers();
    realTimeNewsService.stopBufferProcessing();
  });

  describe("Initialization", () => {
    test("initializes with empty state", () => {
      expect(realTimeNewsService.newsSubscribers.size).toBe(0);
      expect(realTimeNewsService.sentimentSubscribers.size).toBe(0);
      expect(realTimeNewsService.latestNews).toEqual([]);
      expect(realTimeNewsService.latestSentiment).toEqual({});
      expect(realTimeNewsService.newsBuffer).toEqual([]);
      expect(realTimeNewsService.isProcessingNews).toBe(false);
    });

    test("initializes WebSocket subscriptions", () => {
      realTimeNewsService.initialize();

      expect(mockRealTimeDataService.subscribe).toHaveBeenCalledWith(
        "news_updates",
        expect.any(Function)
      );
      expect(mockRealTimeDataService.subscribe).toHaveBeenCalledWith(
        "sentiment_updates",
        expect.any(Function)
      );
      expect(mockRealTimeDataService.subscribe).toHaveBeenCalledWith(
        "breaking_news",
        expect.any(Function)
      );
    });
  });

  describe("News Subscriptions", () => {
    test("allows subscribing to news updates", () => {
      const callback = vi.fn();
      const subscriptionId = realTimeNewsService.subscribeToNews(callback);

      expect(subscriptionId).toEqual(expect.any(Symbol));
      expect(realTimeNewsService.newsSubscribers.has(subscriptionId)).toBe(
        true
      );
    });

    test("sends latest news to new subscribers", () => {
      realTimeNewsService.latestNews = [mockNewsData.articles[0]];
      const callback = vi.fn();

      realTimeNewsService.subscribeToNews(callback);

      expect(callback).toHaveBeenCalledWith([mockNewsData.articles[0]]);
    });

    test("allows unsubscribing from news updates", () => {
      const callback = vi.fn();
      const subscriptionId = realTimeNewsService.subscribeToNews(callback);

      const result = realTimeNewsService.unsubscribeFromNews(subscriptionId);

      expect(result).toBe(true);
      expect(realTimeNewsService.newsSubscribers.has(subscriptionId)).toBe(
        false
      );
    });
  });

  describe("Sentiment Subscriptions", () => {
    test("allows subscribing to sentiment updates", () => {
      const callback = vi.fn();
      const subscriptionId = realTimeNewsService.subscribeToSentiment(
        "AAPL",
        callback
      );

      expect(subscriptionId).toEqual(expect.any(Symbol));
      expect(realTimeNewsService.sentimentSubscribers.has("AAPL")).toBe(true);
      expect(
        realTimeNewsService.sentimentSubscribers.get("AAPL").has(subscriptionId)
      ).toBe(true);
    });

    test("sends latest sentiment to new subscribers", () => {
      realTimeNewsService.latestSentiment["AAPL"] = {
        score: 0.8,
        label: "positive",
      };
      const callback = vi.fn();

      realTimeNewsService.subscribeToSentiment("AAPL", callback);

      expect(callback).toHaveBeenCalledWith({ score: 0.8, label: "positive" });
    });

    test("allows unsubscribing from sentiment updates", () => {
      const callback = vi.fn();
      const subscriptionId = realTimeNewsService.subscribeToSentiment(
        "AAPL",
        callback
      );

      const result = realTimeNewsService.unsubscribeFromSentiment(
        "AAPL",
        subscriptionId
      );

      expect(result).toBe(true);
      expect(
        realTimeNewsService.sentimentSubscribers
          .get("AAPL")
          ?.has(subscriptionId)
      ).toBe(false);
    });

    test("cleans up empty symbol maps when last subscriber unsubscribes", () => {
      const callback = vi.fn();
      const subscriptionId = realTimeNewsService.subscribeToSentiment(
        "AAPL",
        callback
      );

      realTimeNewsService.unsubscribeFromSentiment("AAPL", subscriptionId);

      expect(realTimeNewsService.sentimentSubscribers.has("AAPL")).toBe(false);
    });
  });

  describe("News Update Handling", () => {
    test("processes incoming news updates correctly", () => {
      realTimeNewsService.handleNewsUpdate(mockNewsData);

      expect(realTimeNewsService.newsBuffer.length).toBe(2);
      expect(realTimeNewsService.newsBuffer[0]).toMatchObject({
        title: "Apple reports strong earnings",
        source: "Reuters",
        symbols: ["AAPL"],
        isRealTime: true,
      });
    });

    test("handles malformed news data gracefully", () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});

      realTimeNewsService.handleNewsUpdate({ invalid: "data" });
      realTimeNewsService.handleNewsUpdate(null);
      realTimeNewsService.handleNewsUpdate({ articles: null });

      expect(realTimeNewsService.newsBuffer.length).toBe(0);
      consoleSpy.mockRestore();
    });

    test("assigns unique IDs to articles without IDs", () => {
      const newsDataWithoutIds = {
        articles: [
          {
            title: "Test article",
            source: "Test Source",
          },
        ],
      };

      realTimeNewsService.handleNewsUpdate(newsDataWithoutIds);

      expect(realTimeNewsService.newsBuffer[0].id).toMatch(/^news_\d+_/);
    });
  });

  describe("Sentiment Update Handling", () => {
    test("processes incoming sentiment updates correctly", () => {
      const callback = vi.fn();
      realTimeNewsService.subscribeToSentiment("AAPL", callback);

      realTimeNewsService.handleSentimentUpdate(mockSentimentData);

      expect(realTimeNewsService.latestSentiment["AAPL"]).toMatchObject({
        symbol: "AAPL",
        score: 0.75,
        label: "positive",
        confidence: 0.85,
        isRealTime: true,
      });
      expect(callback).toHaveBeenCalledWith(
        realTimeNewsService.latestSentiment["AAPL"]
      );
    });

    test("handles malformed sentiment data gracefully", () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});

      realTimeNewsService.handleSentimentUpdate({ invalid: "data" });
      realTimeNewsService.handleSentimentUpdate(null);

      expect(Object.keys(realTimeNewsService.latestSentiment)).toHaveLength(0);
      consoleSpy.mockRestore();
    });

    test("handles callback errors gracefully", () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      const failingCallback = vi.fn().mockImplementation(() => {
        throw new Error("Callback error");
      });

      realTimeNewsService.subscribeToSentiment("AAPL", failingCallback);
      realTimeNewsService.handleSentimentUpdate(mockSentimentData);

      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining("Error in sentiment callback"),
        expect.any(Error)
      );
      consoleSpy.mockRestore();
    });
  });

  describe("Breaking News Handling", () => {
    test("processes breaking news alerts correctly", () => {
      const callback = vi.fn();
      realTimeNewsService.subscribeToNews(callback);

      realTimeNewsService.handleBreakingNews(mockBreakingNewsData);

      expect(callback).toHaveBeenCalledWith([
        expect.objectContaining({
          title: "BREAKING: Apple announces major acquisition",
          isBreaking: true,
          priority: "high",
        }),
      ]);
    });

    test("handles malformed breaking news gracefully", () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});

      realTimeNewsService.handleBreakingNews({ invalid: "data" });
      realTimeNewsService.handleBreakingNews(null);

      consoleSpy.mockRestore();
    });
  });

  describe("News Buffer Processing", () => {
    test("processes news buffer periodically", async () => {
      realTimeNewsService.newsBuffer = [mockNewsData.articles[0]];
      realTimeNewsService.startBufferProcessing();

      vi.advanceTimersByTime(2000);

      await vi.runAllTimersAsync();

      expect(realTimeNewsService.latestNews.length).toBeGreaterThan(0);
      expect(realTimeNewsService.newsBuffer.length).toBe(0);
    });

    test("processes up to 10 articles at a time", async () => {
      // Add 15 articles to buffer
      realTimeNewsService.newsBuffer = Array(15)
        .fill()
        .map((_, i) => ({
          ...mockNewsData.articles[0],
          id: `news_${i}`,
          title: `Article ${i}`,
        }));

      await realTimeNewsService.processNewsBuffer();

      expect(realTimeNewsService.latestNews.length).toBe(10);
      expect(realTimeNewsService.newsBuffer.length).toBe(5);
    });

    test("handles processing errors gracefully", async () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});

      // Mock analyzeSentiment to throw error
      realTimeNewsService.analyzeSentiment = vi.fn().mockImplementation(() => {
        throw new Error("Analysis error");
      });

      realTimeNewsService.newsBuffer = [mockNewsData.articles[0]];
      await realTimeNewsService.processNewsBuffer();

      expect(consoleSpy).toHaveBeenCalled();
      expect(realTimeNewsService.isProcessingNews).toBe(false);
      consoleSpy.mockRestore();
    });

    test("prevents concurrent processing", async () => {
      realTimeNewsService.newsBuffer = [mockNewsData.articles[0]];
      realTimeNewsService.isProcessingNews = true;

      await realTimeNewsService.processNewsBuffer();

      // Should not process when already processing
      expect(realTimeNewsService.latestNews.length).toBe(0);
    });
  });

  describe("Sentiment Analysis", () => {
    test("analyzes article sentiment correctly", () => {
      const article = {
        title: "Apple stock surges on strong earnings beat",
        summary: "Company reports profit growth and bullish outlook",
      };

      const sentiment = realTimeNewsService.analyzeSentiment(article);

      expect(sentiment.score).toBeGreaterThan(0.5); // Positive sentiment
      expect(sentiment.label).toBe("positive");
      expect(sentiment.confidence).toBeGreaterThan(0);
      expect(sentiment.positiveWords).toBeGreaterThan(0);
    });

    test("handles negative sentiment correctly", () => {
      const article = {
        title: "Apple stock declines on weak earnings miss",
        summary: "Company reports losses and bearish outlook",
      };

      const sentiment = realTimeNewsService.analyzeSentiment(article);

      expect(sentiment.score).toBeLessThan(0.5); // Negative sentiment
      expect(sentiment.label).toBe("negative");
      expect(sentiment.negativeWords).toBeGreaterThan(0);
    });

    test("handles neutral sentiment correctly", () => {
      const article = {
        title: "Apple announces board meeting",
        summary: "Routine quarterly meeting scheduled",
      };

      const sentiment = realTimeNewsService.analyzeSentiment(article);

      expect(sentiment.score).toBeCloseTo(0.5, 1); // Neutral sentiment
      expect(sentiment.label).toBe("neutral");
    });

    test("handles analysis errors gracefully", () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});

      const sentiment = realTimeNewsService.analyzeSentiment(null);

      expect(sentiment.score).toBe(0.5);
      expect(sentiment.label).toBe("neutral");
      expect(sentiment.confidence).toBe(0);
      consoleSpy.mockRestore();
    });
  });

  describe("Impact Calculation", () => {
    test("calculates impact based on source credibility", () => {
      const article = {
        source: "Reuters",
        publishedAt: new Date().toISOString(),
        summary:
          "A detailed analysis of market conditions with comprehensive data",
      };

      const impact = realTimeNewsService.calculateImpact(article);

      expect(impact.score).toBeGreaterThan(0.5);
      expect(impact.level).toBe("high");
    });

    test("factors in article recency", () => {
      const recentArticle = {
        source: "Unknown Source",
        publishedAt: new Date().toISOString(), // Very recent
      };

      const oldArticle = {
        source: "Unknown Source",
        publishedAt: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(), // 24 hours ago
      };

      const recentImpact = realTimeNewsService.calculateImpact(recentArticle);
      const oldImpact = realTimeNewsService.calculateImpact(oldArticle);

      expect(recentImpact.score).toBeGreaterThan(oldImpact.score);
    });

    test("considers content length", () => {
      const shortArticle = {
        source: "Test",
        summary: "Short summary",
      };

      const longArticle = {
        source: "Test",
        summary:
          "A" +
          "very ".repeat(50) +
          "long summary with comprehensive details and analysis",
      };

      const shortImpact = realTimeNewsService.calculateImpact(shortArticle);
      const longImpact = realTimeNewsService.calculateImpact(longArticle);

      expect(longImpact.score).toBeGreaterThan(shortImpact.score);
    });
  });

  describe("Symbol Sentiment Aggregation", () => {
    test("updates symbol sentiments from articles", () => {
      const callback = vi.fn();
      realTimeNewsService.subscribeToSentiment("AAPL", callback);

      const articles = [
        {
          symbols: ["AAPL"],
          sentiment: { score: 0.8 },
        },
        {
          symbols: ["AAPL"],
          sentiment: { score: 0.6 },
        },
      ];

      realTimeNewsService.updateSymbolSentiments(articles);

      expect(realTimeNewsService.latestSentiment["AAPL"].score).toBe(0.7); // Average
      expect(callback).toHaveBeenCalledWith(
        expect.objectContaining({
          symbol: "AAPL",
          score: 0.7,
          label: "positive",
        })
      );
    });

    test("handles multiple symbols in single article", () => {
      const callback1 = vi.fn();
      const callback2 = vi.fn();
      realTimeNewsService.subscribeToSentiment("AAPL", callback1);
      realTimeNewsService.subscribeToSentiment("GOOGL", callback2);

      const articles = [
        {
          symbols: ["AAPL", "GOOGL"],
          sentiment: { score: 0.8 },
        },
      ];

      realTimeNewsService.updateSymbolSentiments(articles);

      expect(callback1).toHaveBeenCalled();
      expect(callback2).toHaveBeenCalled();
      expect(realTimeNewsService.latestSentiment["AAPL"].score).toBe(0.8);
      expect(realTimeNewsService.latestSentiment["GOOGL"].score).toBe(0.8);
    });
  });

  describe("API Methods", () => {
    test("fetches news sentiment from API", async () => {
      const mockResponse = {
        data: {
          symbol: "AAPL",
          score: 0.75,
          articles: 10,
        },
      };
      mockApi.get.mockResolvedValue(mockResponse);

      const result = await realTimeNewsService.fetchNewsSentiment("AAPL", "1h");

      expect(mockApi.get).toHaveBeenCalledWith(
        "/api/news/sentiment/AAPL?timeframe=1h"
      );
      expect(result).toEqual(mockResponse.data);
    });

    test("handles API errors for sentiment fetch", async () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      mockApi.get.mockRejectedValue(new Error("API Error"));

      await expect(
        realTimeNewsService.fetchNewsSentiment("AAPL")
      ).rejects.toThrow("API Error");

      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining("Failed to fetch sentiment for AAPL"),
        expect.any(Error)
      );
      consoleSpy.mockRestore();
    });

    test("fetches breaking news from API", async () => {
      const mockResponse = {
        data: [mockBreakingNewsData.article],
      };
      mockApi.get.mockResolvedValue(mockResponse);

      const result = await realTimeNewsService.fetchBreakingNews();

      expect(mockApi.get).toHaveBeenCalledWith("/api/news/breaking");
      expect(result).toEqual(mockResponse.data);
    });

    test("handles API errors for breaking news fetch", async () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      mockApi.get.mockRejectedValue(new Error("API Error"));

      await expect(realTimeNewsService.fetchBreakingNews()).rejects.toThrow(
        "API Error"
      );
      consoleSpy.mockRestore();
    });
  });

  describe("Data Access Methods", () => {
    test("returns latest news with limit", () => {
      realTimeNewsService.latestNews = Array(30)
        .fill()
        .map((_, i) => ({
          id: `news_${i}`,
          title: `Article ${i}`,
        }));

      const result = realTimeNewsService.getLatestNews(10);

      expect(result).toHaveLength(10);
      expect(result[0].title).toBe("Article 0");
    });

    test("returns sentiment for specific symbol", () => {
      realTimeNewsService.latestSentiment["AAPL"] = {
        score: 0.8,
        label: "positive",
      };

      const result = realTimeNewsService.getLatestSentiment("AAPL");

      expect(result).toEqual({ score: 0.8, label: "positive" });
    });

    test("returns null for non-existent symbol sentiment", () => {
      const result = realTimeNewsService.getLatestSentiment("NONEXISTENT");

      expect(result).toBeNull();
    });

    test("returns all latest sentiments", () => {
      realTimeNewsService.latestSentiment = {
        AAPL: { score: 0.8 },
        GOOGL: { score: 0.6 },
      };

      const result = realTimeNewsService.getAllLatestSentiments();

      expect(result).toEqual({
        AAPL: { score: 0.8 },
        GOOGL: { score: 0.6 },
      });
    });
  });

  describe("Cleanup", () => {
    test("destroys service and clears all state", () => {
      realTimeNewsService.newsSubscribers.set(Symbol(), vi.fn());
      realTimeNewsService.sentimentSubscribers.set("AAPL", new Map());
      realTimeNewsService.latestNews = [mockNewsData.articles[0]];
      realTimeNewsService.latestSentiment = { AAPL: { score: 0.8 } };
      realTimeNewsService.newsBuffer = [mockNewsData.articles[1]];
      realTimeNewsService.bufferProcessInterval = setInterval(() => {}, 1000);

      realTimeNewsService.destroy();

      expect(realTimeNewsService.newsSubscribers.size).toBe(0);
      expect(realTimeNewsService.sentimentSubscribers.size).toBe(0);
      expect(realTimeNewsService.latestNews).toEqual([]);
      expect(realTimeNewsService.latestSentiment).toEqual({});
      expect(realTimeNewsService.newsBuffer).toEqual([]);
      expect(realTimeNewsService.bufferProcessInterval).toBeNull();
    });

    test("stops buffer processing on destroy", () => {
      const clearIntervalSpy = vi.spyOn(global, "clearInterval");
      realTimeNewsService.bufferProcessInterval = setInterval(() => {}, 1000);

      realTimeNewsService.destroy();

      expect(clearIntervalSpy).toHaveBeenCalled();
    });
  });

  describe("Score to Label Conversion", () => {
    test("converts scores to correct labels", () => {
      expect(realTimeNewsService.scoreToLabel(0.8)).toBe("positive");
      expect(realTimeNewsService.scoreToLabel(0.6)).toBe("positive");
      expect(realTimeNewsService.scoreToLabel(0.5)).toBe("neutral");
      expect(realTimeNewsService.scoreToLabel(0.4)).toBe("negative");
      expect(realTimeNewsService.scoreToLabel(0.2)).toBe("negative");
    });
  });

  describe("Edge Cases and Error Handling", () => {
    test("handles empty news buffer gracefully", async () => {
      realTimeNewsService.newsBuffer = [];

      await realTimeNewsService.processNewsBuffer();

      expect(realTimeNewsService.latestNews).toEqual([]);
      expect(realTimeNewsService.isProcessingNews).toBe(false);
    });

    test("handles callback errors in news notifications", () => {
      const consoleSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      const failingCallback = vi.fn().mockImplementation(() => {
        throw new Error("Callback error");
      });

      realTimeNewsService.subscribeToNews(failingCallback);
      realTimeNewsService.notifyNewsSubscribers([mockNewsData.articles[0]]);

      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining("Error in news callback"),
        expect.any(Error)
      );
      consoleSpy.mockRestore();
    });

    test("maintains news history limit of 100 articles", async () => {
      // Fill with 95 existing articles
      realTimeNewsService.latestNews = Array(95)
        .fill()
        .map((_, i) => ({
          id: `existing_${i}`,
          title: `Existing ${i}`,
        }));

      // Process 10 new articles
      realTimeNewsService.newsBuffer = Array(10)
        .fill()
        .map((_, i) => ({
          id: `new_${i}`,
          title: `New ${i}`,
          symbols: [],
        }));

      await realTimeNewsService.processNewsBuffer();

      expect(realTimeNewsService.latestNews).toHaveLength(100);
      expect(realTimeNewsService.latestNews[0].title).toBe("New 0"); // New articles first
      expect(realTimeNewsService.latestNews[99].title).toBe("Existing 89"); // Trimmed old articles
    });
  });
});
