const request = require("supertest");
const express = require("express");

const newsRouter = require("../../../routes/news");

// Mock dependencies
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
  initializeDatabase: jest.fn().mockResolvedValue({}),
  healthCheck: jest.fn(),
  getPool: jest.fn(),
  closeDatabase: jest.fn(),
  transaction: jest.fn(),
}));

jest.mock("../../../middleware/auth", () => ({
  authenticateToken: (req, res, next) => {
    req.user = { sub: "test-user-123", email: "test@example.com" };
    next();
  },
}));

jest.mock("../../../utils/newsAnalyzer", () => ({
  calculateReliabilityScore: jest.fn((source) => {
    const scores = {
      Reuters: 0.95,
      Bloomberg: 0.92,
      CNBC: 0.85,
      MarketWatch: 0.8,
    };
    return scores[source] || 0.75;
  }),
}));

jest.mock("../../../utils/sentimentEngine", () => ({
  scoreToLabel: jest.fn((score) => {
    if (score > 0.1) return "positive";
    if (score < -0.1) return "negative";
    return "neutral";
  }),
  analyzeSentiment: jest.fn().mockResolvedValue({
    score: 0.75,
    label: "positive",
    confidence: 0.85,
    keywords: ["growth", "profit", "success"],
    impact_score: 0.8,
  }),
}));

const { query } = require("../../../utils/database");
const newsAnalyzer = require("../../../utils/newsAnalyzer");
const sentimentEngine = require("../../../utils/sentimentEngine");

describe("News Routes", () => {
  let app;

  beforeEach(() => {
    app = express();
    app.use(express.json());

    // Add response formatter middleware
    app.use((req, res, next) => {
      res.success = (data, status = 200) => {
        res.status(status).json({
          success: true,
          data: data,
        });
      };

      res.error = (message, status = 500) => {
        res.status(status).json({
          success: false,
          error: message,
        });
      };

      next();
    });

    app.use("/news", newsRouter);
    jest.clearAllMocks();
  });

  describe("GET /news/health", () => {
    test("should return health status", async () => {
      const response = await request(app).get("/news/health").expect(200);

      expect(response.body).toEqual({
        success: true,
        status: "operational",
        service: "news",
        timestamp: expect.any(String),
        message: "News service is running",
      });
    });
  });

  describe("GET /news/", () => {
    test("should return API status", async () => {
      const response = await request(app).get("/news/").expect(200);

      expect(response.body).toEqual({
        success: true,
        message: "News API - Ready",
        timestamp: expect.any(String),
        status: "operational",
      });
    });
  });

  describe("GET /news/articles", () => {
    test("should return news articles with sentiment analysis", async () => {
      const mockArticles = {
        rows: [
          {
            id: 1,
            title: "Tech Stocks Rally on Strong Earnings",
            content:
              "Technology companies showed strong earnings growth this quarter...",
            source: "Reuters",
            author: "John Smith",
            published_at: new Date().toISOString(),
            url: "https://reuters.com/article/1",
            category: "technology",
            symbol: "AAPL",
            sentiment_score: "0.75",
            sentiment_label: "positive",
            sentiment_confidence: "0.85",
            keywords: ["tech", "earnings", "growth"],
            summary: "Strong tech earnings drive market optimism",
            impact_score: "0.8",
            relevance_score: "0.9",
            created_at: new Date().toISOString(),
          },
        ],
      };

      const mockCount = { rows: [{ total: "1" }] };

      query
        .mockResolvedValueOnce(mockArticles)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/news/articles")
        .query({ symbol: "AAPL", limit: 10, timeframe: "24h" })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          articles: expect.arrayContaining([
            expect.objectContaining({
              id: 1,
              title: "Tech Stocks Rally on Strong Earnings",
              source: "Reuters",
              author: "John Smith",
              category: "technology",
              symbol: "AAPL",
              sentiment: {
                score: 0.75,
                label: "positive",
                confidence: 0.85,
              },
              keywords: ["tech", "earnings", "growth"],
              impact_score: 0.8,
              relevance_score: 0.9,
            }),
          ]),
          total: 1,
          limit: 10,
          offset: 0,
          filters: {
            symbol: "AAPL",
            timeframe: "24h",
          },
        },
      });
      expect(query).toHaveBeenCalledTimes(2);
    });

    test("should handle filtering by category and sentiment", async () => {
      const mockArticles = { rows: [] };
      const mockCount = { rows: [{ total: "0" }] };

      query
        .mockResolvedValueOnce(mockArticles)
        .mockResolvedValueOnce(mockCount);

      const response = await request(app)
        .get("/news/articles")
        .query({
          category: "technology",
          sentiment: "positive",
          timeframe: "1w",
        })
        .expect(200);

      expect(response.body.data.filters).toEqual({
        symbol: undefined,
        category: "technology",
        sentiment: "positive",
        timeframe: "1w",
      });
    });

    test("should handle database errors", async () => {
      query.mockRejectedValue(new Error("Database connection failed"));

      const response = await request(app).get("/news/articles").expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to fetch news articles",
        message: "Database connection failed",
      });
    });
  });

  describe("GET /news/sentiment/:symbol", () => {
    test("should return sentiment analysis for symbol", async () => {
      const mockSentimentData = {
        rows: [
          {
            avg_sentiment: "0.65",
            total_articles: "25",
            positive_count: "15",
            negative_count: "5",
            neutral_count: "5",
            avg_impact: "0.75",
            avg_relevance: "0.80",
          },
        ],
      };

      const mockTrendData = {
        rows: [
          {
            hour: "2024-01-01T10:00:00.000Z",
            avg_sentiment: "0.70",
            article_count: "5",
          },
        ],
      };

      const mockKeywordData = {
        rows: [
          { keyword: "growth", frequency: "10" },
          { keyword: "earnings", frequency: "8" },
        ],
      };

      query
        .mockResolvedValueOnce(mockSentimentData)
        .mockResolvedValueOnce(mockTrendData)
        .mockResolvedValueOnce(mockKeywordData);

      const response = await request(app)
        .get("/news/sentiment/AAPL")
        .query({ timeframe: "24h" })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          symbol: "AAPL",
          timeframe: "24h",
          overall_sentiment: {
            score: 0.65,
            label: "positive",
            distribution: {
              positive: 15,
              negative: 5,
              neutral: 5,
            },
            total_articles: 25,
            avg_impact: 0.75,
            avg_relevance: 0.8,
          },
          trend: expect.arrayContaining([
            expect.objectContaining({
              hour: "2024-01-01T10:00:00.000Z",
              sentiment: 0.7,
              article_count: 5,
            }),
          ]),
          keywords: expect.arrayContaining([
            { keyword: "growth", frequency: 10 },
            { keyword: "earnings", frequency: 8 },
          ]),
        },
      });
      expect(query).toHaveBeenCalledTimes(3);
      expect(sentimentEngine.scoreToLabel).toHaveBeenCalledWith(0.65);
    });

    test("should handle database errors", async () => {
      query.mockRejectedValue(new Error("Database query failed"));

      const response = await request(app)
        .get("/news/sentiment/AAPL")
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to fetch sentiment analysis",
        message: "Database query failed",
      });
    });
  });

  describe("GET /news/market-sentiment", () => {
    test("should return market sentiment overview", async () => {
      const mockMarketData = {
        rows: [
          {
            avg_sentiment: "0.55",
            total_articles: "100",
            positive_count: "60",
            negative_count: "25",
            neutral_count: "15",
          },
        ],
      };

      const mockCategoryData = {
        rows: [
          {
            category: "technology",
            avg_sentiment: "0.70",
            article_count: "30",
          },
          {
            category: "finance",
            avg_sentiment: "0.40",
            article_count: "25",
          },
        ],
      };

      const mockSymbolData = {
        rows: [
          {
            symbol: "AAPL",
            avg_sentiment: "0.80",
            article_count: "15",
            avg_impact: "0.85",
          },
        ],
      };

      const mockTrendData = {
        rows: [
          {
            hour: "2024-01-01T10:00:00.000Z",
            avg_sentiment: "0.60",
            article_count: "20",
          },
        ],
      };

      query
        .mockResolvedValueOnce(mockMarketData)
        .mockResolvedValueOnce(mockCategoryData)
        .mockResolvedValueOnce(mockSymbolData)
        .mockResolvedValueOnce(mockTrendData);

      const response = await request(app)
        .get("/news/market-sentiment")
        .query({ timeframe: "24h" })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          timeframe: "24h",
          overall_sentiment: {
            score: 0.55,
            label: "positive",
            distribution: {
              positive: 60,
              negative: 25,
              neutral: 15,
            },
            total_articles: 100,
          },
          by_category: expect.arrayContaining([
            expect.objectContaining({
              category: "technology",
              sentiment: 0.7,
              article_count: 30,
              label: "positive",
            }),
            expect.objectContaining({
              category: "finance",
              sentiment: 0.4,
              article_count: 25,
              label: "positive",
            }),
          ]),
          top_symbols: expect.arrayContaining([
            expect.objectContaining({
              symbol: "AAPL",
              sentiment: 0.8,
              article_count: 15,
              impact: 0.85,
              label: "positive",
            }),
          ]),
          trend: expect.arrayContaining([
            expect.objectContaining({
              hour: "2024-01-01T10:00:00.000Z",
              sentiment: 0.6,
              article_count: 20,
            }),
          ]),
        },
      });
      expect(query).toHaveBeenCalledTimes(4);
    });
  });

  describe("POST /news/analyze-sentiment", () => {
    test("should analyze sentiment for custom text", async () => {
      const response = await request(app)
        .post("/news/analyze-sentiment")
        .send({
          text: "The company reported excellent quarterly results with strong growth",
          symbol: "AAPL",
        })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          score: 0.75,
          label: "positive",
          confidence: 0.85,
          keywords: ["growth", "profit", "success"],
          impact_score: 0.8,
        },
      });
      expect(sentimentEngine.analyzeSentiment).toHaveBeenCalledWith(
        "The company reported excellent quarterly results with strong growth",
        "AAPL"
      );
    });

    test("should require text parameter", async () => {
      const response = await request(app)
        .post("/news/analyze-sentiment")
        .send({ symbol: "AAPL" })
        .expect(400);

      expect(response.body).toMatchObject({
        success: false,
        error: "Text is required for sentiment analysis",
      });
    });

    test("should handle sentiment analysis errors", async () => {
      sentimentEngine.analyzeSentiment.mockRejectedValue(
        new Error("Analysis failed")
      );

      const response = await request(app)
        .post("/news/analyze-sentiment")
        .send({ text: "Test text", symbol: "AAPL" })
        .expect(500);

      expect(response.body).toMatchObject({
        success: false,
        error: "Failed to analyze sentiment",
        message: "Analysis failed",
      });
    });
  });

  describe("GET /news/sources", () => {
    test("should return news sources with reliability scores", async () => {
      const mockSourcesData = {
        rows: [
          {
            source: "Reuters",
            article_count: "150",
            avg_relevance: "0.85",
            avg_impact: "0.75",
            positive_count: "90",
            negative_count: "30",
            neutral_count: "30",
          },
          {
            source: "Bloomberg",
            article_count: "120",
            avg_relevance: "0.80",
            avg_impact: "0.70",
            positive_count: "70",
            negative_count: "25",
            neutral_count: "25",
          },
        ],
      };

      query.mockResolvedValue(mockSourcesData);

      const response = await request(app).get("/news/sources").expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          sources: expect.arrayContaining([
            expect.objectContaining({
              source: "Reuters",
              article_count: 150,
              avg_relevance: 0.85,
              avg_impact: 0.75,
              sentiment_distribution: {
                positive: 90,
                negative: 30,
                neutral: 30,
              },
              reliability_score: 0.95,
            }),
            expect.objectContaining({
              source: "Bloomberg",
              article_count: 120,
              reliability_score: 0.92,
            }),
          ]),
          total: 2,
        },
      });
      expect(newsAnalyzer.calculateReliabilityScore).toHaveBeenCalledWith(
        "Reuters"
      );
      expect(newsAnalyzer.calculateReliabilityScore).toHaveBeenCalledWith(
        "Bloomberg"
      );
    });
  });

  describe("GET /news/categories", () => {
    test("should return news categories with sentiment data", async () => {
      const mockCategoriesData = {
        rows: [
          {
            category: "technology",
            article_count: "75",
            avg_sentiment: "0.65",
            avg_impact: "0.80",
          },
          {
            category: "finance",
            article_count: "60",
            avg_sentiment: "0.45",
            avg_impact: "0.70",
          },
        ],
      };

      query.mockResolvedValue(mockCategoriesData);

      const response = await request(app).get("/news/categories").expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          categories: expect.arrayContaining([
            expect.objectContaining({
              category: "technology",
              article_count: 75,
              avg_sentiment: 0.65,
              avg_impact: 0.8,
              sentiment_label: "positive",
            }),
            expect.objectContaining({
              category: "finance",
              article_count: 60,
              avg_sentiment: 0.45,
              avg_impact: 0.7,
              sentiment_label: "positive",
            }),
          ]),
          total: 2,
        },
      });
    });
  });

  describe("GET /news/trending", () => {
    test("should return trending topics", async () => {
      const mockKeywordData = {
        rows: [
          {
            keyword: "earnings",
            frequency: "25",
            avg_sentiment: "0.70",
            avg_impact: "0.85",
          },
          {
            keyword: "federal reserve",
            frequency: "20",
            avg_sentiment: "0.30",
            avg_impact: "0.90",
          },
        ],
      };

      const mockSymbolData = {
        rows: [
          {
            symbol: "AAPL",
            mention_count: "15",
            avg_sentiment: "0.75",
            avg_impact: "0.80",
          },
          {
            symbol: "TSLA",
            mention_count: "12",
            avg_sentiment: "-0.20",
            avg_impact: "0.75",
          },
        ],
      };

      query
        .mockResolvedValueOnce(mockKeywordData)
        .mockResolvedValueOnce(mockSymbolData);

      const response = await request(app)
        .get("/news/trending")
        .query({ timeframe: "24h", limit: 10 })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: {
          timeframe: "24h",
          keywords: expect.arrayContaining([
            expect.objectContaining({
              keyword: "earnings",
              frequency: 25,
              avg_sentiment: 0.7,
              avg_impact: 0.85,
              sentiment_label: "positive",
            }),
            expect.objectContaining({
              keyword: "federal reserve",
              frequency: 20,
              avg_sentiment: 0.3,
              avg_impact: 0.9,
              sentiment_label: "positive",
            }),
          ]),
          symbols: expect.arrayContaining([
            expect.objectContaining({
              symbol: "AAPL",
              mention_count: 15,
              avg_sentiment: 0.75,
              avg_impact: 0.8,
              sentiment_label: "positive",
            }),
            expect.objectContaining({
              symbol: "TSLA",
              mention_count: 12,
              avg_sentiment: -0.2,
              avg_impact: 0.75,
              sentiment_label: "negative",
            }),
          ]),
        },
      });
      expect(query).toHaveBeenCalledTimes(2);
    });
  });

  describe("GET /news/feed", () => {
    test("should return enhanced news feed", async () => {
      const response = await request(app)
        .get("/news/feed")
        .query({ category: "technology", limit: 5, time_range: "24h" })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          articles: expect.any(Array),
          summary: expect.objectContaining({
            total_articles: expect.any(Number),
            sentiment_distribution: expect.objectContaining({
              positive: expect.any(Number),
              neutral: expect.any(Number),
              negative: expect.any(Number),
            }),
            avg_impact_score: expect.any(Number),
          }),
        }),
        filters: {
          category: "technology",
          symbol: "ALL",
          sentiment_filter: "ALL",
          source_filter: "ALL",
          time_range: "24h",
        },
        last_updated: expect.any(String),
      });

      expect(response.body.data.articles.length).toBeLessThanOrEqual(5);
    });

    test("should return fallback data on error", async () => {
      // Force an error by causing the route to fail
      const originalConsole = console.error;
      console.error = jest.fn();

      // Since generateEnhancedNewsFeed doesn't use database,
      // we need to temporarily break something in the route itself
      // Let's mock Math.random to cause an error
      const originalMathRandom = Math.random;
      Math.random = () => {
        throw new Error("Forced error for testing");
      };

      const response = await request(app)
        .get("/news/feed")
        .query({ category: "technology" })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.any(Object),
        fallback: true,
        error: expect.any(String),
        last_updated: expect.any(String),
      });

      // Restore original functions
      Math.random = originalMathRandom;
      console.error = originalConsole;
    });
  });

  describe("GET /news/economic-calendar", () => {
    test("should return economic calendar data", async () => {
      const response = await request(app)
        .get("/news/economic-calendar")
        .query({ importance: "high", country: "US", limit: 10 })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          events: expect.any(Array),
          summary: expect.objectContaining({
            total_events: expect.any(Number),
            high_impact_events: expect.any(Number),
            countries_covered: expect.any(Array),
            next_major_event: expect.any(Object),
          }),
        }),
        filters: {
          importance: "high",
          country: "US",
          date_range: "7d",
        },
        last_updated: expect.any(String),
      });

      expect(response.body.data.events.length).toBeLessThanOrEqual(10);
    });
  });

  describe("GET /news/sentiment-dashboard", () => {
    test("should return sentiment dashboard data", async () => {
      const response = await request(app)
        .get("/news/sentiment-dashboard")
        .query({ timeframe: "24h" })
        .expect(200);

      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          overall_sentiment: expect.objectContaining({
            score: expect.any(Number),
            label: expect.stringMatching(/^(bullish|bearish|neutral)$/),
            confidence: expect.any(Number),
            change_24h: expect.any(Number),
          }),
          sentiment_by_sector: expect.any(Array),
          trending_topics: expect.any(Array),
          fear_greed_index: expect.objectContaining({
            value: expect.any(Number),
            label: expect.any(String),
            change_24h: expect.any(Number),
          }),
          social_sentiment: expect.any(Object),
          news_sentiment: expect.objectContaining({
            positive_articles: expect.any(Number),
            negative_articles: expect.any(Number),
            neutral_articles: expect.any(Number),
          }),
        }),
        timeframe: "24h",
        last_updated: expect.any(String),
      });
    });
  });
});
