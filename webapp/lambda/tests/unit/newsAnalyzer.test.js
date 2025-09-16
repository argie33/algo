/**
 * News Analyzer Tests
 * Tests news sentiment analysis, topic extraction, and reliability scoring
 */

const newsAnalyzer = require("../../utils/newsAnalyzer");

// Mock logger to avoid test output noise
jest.mock("../../utils/logger", () => ({
  error: jest.fn(),
  info: jest.fn(),
  warn: jest.fn(),
  debug: jest.fn(),
}));

describe("News Analyzer", () => {
  // Sample articles for testing
  const sampleArticles = [
    {
      title: "Company Reports Strong Growth and Record Profits",
      description:
        "The technology company exceeded expectations with bullish quarterly results",
      source: "Reuters",
      publishedAt: new Date().toISOString(),
    },
    {
      title: "Market Decline Continues with Weak Performance",
      description:
        "Bearish sentiment drives down stock prices amid economic concerns",
      source: "Bloomberg",
      publishedAt: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(), // 2 hours ago
    },
    {
      title: "Company Maintains Stable Operations",
      description: "Neutral outlook as business holds steady position",
      source: "CNBC",
      publishedAt: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(), // 24 hours ago
    },
  ];

  describe("Sentiment Analysis", () => {
    describe("analyzeSentiment", () => {
      test("should analyze positive sentiment correctly", () => {
        const article = {
          title: "Stock soars with strong growth and bullish outlook",
          description: "Company beats expectations with excellent profits",
        };

        const result = newsAnalyzer.analyzeSentiment(article);

        expect(result.sentiment).toBe("positive");
        expect(result.score).toBeGreaterThan(0);
        expect(result.confidence).toBeGreaterThan(0);
        expect(result.keywords).toEqual(
          expect.arrayContaining([
            expect.objectContaining({ sentiment: "positive" }),
          ])
        );
        expect(result.wordCount).toBeGreaterThan(0);
        expect(result.sentimentWordCount).toBeGreaterThan(0);
      });

      test("should analyze negative sentiment correctly", () => {
        const article = {
          title: "Stock plummets with weak earnings and bearish forecast",
          description: "Company misses targets with declining profits and loss",
        };

        const result = newsAnalyzer.analyzeSentiment(article);

        expect(result.sentiment).toBe("negative");
        expect(result.score).toBeGreaterThan(0);
        expect(result.confidence).toBeGreaterThan(0);
        expect(result.keywords).toEqual(
          expect.arrayContaining([
            expect.objectContaining({ sentiment: "negative" }),
          ])
        );
      });

      test("should analyze neutral sentiment correctly", () => {
        const article = {
          title: "Company maintains stable operations",
          description: "Business holds steady with neutral outlook",
        };

        const result = newsAnalyzer.analyzeSentiment(article);

        expect(result.sentiment).toBe("neutral");
        expect(result.score).toBe(0);
        expect(result.confidence).toBe(0);
        expect(result.keywords).toEqual(
          expect.arrayContaining([
            expect.objectContaining({ sentiment: "neutral" }),
          ])
        );
      });

      test("should handle missing article data", () => {
        expect(newsAnalyzer.analyzeSentiment(null)).toEqual({
          sentiment: "neutral",
          score: 0,
          confidence: 0,
          keywords: [],
        });

        expect(newsAnalyzer.analyzeSentiment({})).toEqual({
          sentiment: "neutral",
          score: 0,
          confidence: 0,
          keywords: [],
        });

        expect(newsAnalyzer.analyzeSentiment({ title: "" })).toEqual({
          sentiment: "neutral",
          score: 0,
          confidence: 0,
          keywords: [],
        });
      });

      test("should handle mixed sentiment", () => {
        const article = {
          title: "Company shows growth but faces decline in some areas",
          description: "Strong profits offset by weak market performance",
        };

        const result = newsAnalyzer.analyzeSentiment(article);

        expect(result.sentiment).toMatch(/positive|negative|neutral/);
        expect(result.keywords.length).toBeGreaterThan(0);
        expect(result.sentimentWordCount).toBeGreaterThan(1);
      });

      test("should calculate confidence based on sentiment word density", () => {
        const highDensityArticle = {
          title: "bullish growth profit strong",
          description: "",
        };
        const lowDensityArticle = {
          title:
            "company announces quarterly earnings results today with growth",
          description: "",
        };

        const highResult = newsAnalyzer.analyzeSentiment(highDensityArticle);
        const lowResult = newsAnalyzer.analyzeSentiment(lowDensityArticle);

        expect(highResult.confidence).toBeGreaterThan(lowResult.confidence);
      });

      test("should handle error gracefully", () => {
        // Mock an error by breaking the article structure in a way that causes an exception
        const originalSplit = String.prototype.split;
        String.prototype.split = jest.fn(() => {
          throw new Error("Test error");
        });

        const result = newsAnalyzer.analyzeSentiment({ title: "test" });

        expect(result.sentiment).toBe("neutral");
        expect(result.score).toBe(0);
        expect(result.confidence).toBe(0);
        expect(result.error).toBe("Test error");

        // Restore original method
        String.prototype.split = originalSplit;
      });
    });

    describe("analyzeArticles", () => {
      test("should analyze multiple articles correctly", () => {
        const result = newsAnalyzer.analyzeArticles(sampleArticles);

        expect(result.overallSentiment).toMatch(/positive|negative|neutral/);
        expect(result.averageScore).toBeDefined();
        expect(result.confidence).toBeGreaterThan(0);
        expect(result.articleCount).toBe(3);
        expect(result.sentimentDistribution).toEqual({
          positive: expect.any(Number),
          negative: expect.any(Number),
          neutral: expect.any(Number),
        });
        expect(result.details).toHaveLength(3);
      });

      test("should handle empty article array", () => {
        const result = newsAnalyzer.analyzeArticles([]);

        expect(result).toEqual({
          overallSentiment: "neutral",
          averageScore: 0,
          confidence: 0,
          articleCount: 0,
          sentimentDistribution: { positive: 0, negative: 0, neutral: 0 },
        });
      });

      test("should handle non-array input", () => {
        expect(newsAnalyzer.analyzeArticles(null)).toEqual({
          overallSentiment: "neutral",
          averageScore: 0,
          confidence: 0,
          articleCount: 0,
          sentimentDistribution: { positive: 0, negative: 0, neutral: 0 },
        });

        expect(newsAnalyzer.analyzeArticles("not an array")).toEqual({
          overallSentiment: "neutral",
          averageScore: 0,
          confidence: 0,
          articleCount: 0,
          sentimentDistribution: { positive: 0, negative: 0, neutral: 0 },
        });
      });

      test("should determine overall sentiment from distribution", () => {
        const positiveArticles = [
          { title: "bullish growth profit strong excellent" },
          { title: "gain up beat exceed upgrade" },
          { title: "positive outlook with growth" },
        ];

        const result = newsAnalyzer.analyzeArticles(positiveArticles);
        expect(result.overallSentiment).toBe("positive");
        expect(result.sentimentDistribution.positive).toBeGreaterThan(
          result.sentimentDistribution.negative
        );
      });

      test("should determine negative overall sentiment when negative articles dominate", () => {
        const negativeArticles = [
          { title: "bearish decline loss weak downgrade" },
          { title: "sell down miss below cut" },
          { title: "negative outlook with decline" },
        ];

        const result = newsAnalyzer.analyzeArticles(negativeArticles);
        expect(result.overallSentiment).toBe("negative");
        expect(result.sentimentDistribution.negative).toBeGreaterThan(
          result.sentimentDistribution.positive
        );
        expect(result.sentimentDistribution.negative).toBeGreaterThan(
          result.sentimentDistribution.neutral
        );
      });

      test("should handle analysis errors gracefully", () => {
        // Mock analyzeSentiment to throw error
        const originalAnalyzeSentiment = newsAnalyzer.analyzeSentiment;
        newsAnalyzer.analyzeSentiment = jest.fn(() => {
          throw new Error("Analysis error");
        });

        const result = newsAnalyzer.analyzeArticles([{ title: "test" }]);

        expect(result.overallSentiment).toBe("neutral");
        expect(result.averageScore).toBe(0);
        expect(result.confidence).toBe(0);
        expect(result.error).toBe("Analysis error");

        // Restore original method
        newsAnalyzer.analyzeSentiment = originalAnalyzeSentiment;
      });
    });
  });

  describe("Topic Extraction", () => {
    describe("extractTopics", () => {
      test("should extract topics from articles", () => {
        const articles = [
          { title: "Technology company reports quarterly earnings growth" },
          { title: "Technology sector shows strong performance this quarter" },
          { title: "Earnings beat expectations across technology industry" },
        ];

        const topics = newsAnalyzer.extractTopics(articles);

        expect(topics).toBeInstanceOf(Array);
        expect(topics.length).toBeGreaterThan(0);
        expect(topics[0]).toEqual({
          topic: expect.any(String),
          count: expect.any(Number),
          frequency: expect.any(Number),
        });

        // Should find "technology" and "earnings" as top topics
        const topicWords = topics.map((t) => t.topic);
        expect(topicWords).toContain("technology");
      });

      test("should filter out common words", () => {
        const articles = [
          { title: "The company and the industry are showing growth" },
        ];

        const topics = newsAnalyzer.extractTopics(articles);

        const topicWords = topics.map((t) => t.topic);
        expect(topicWords).not.toContain("the");
        expect(topicWords).not.toContain("and");
        expect(topicWords).not.toContain("are");
      });

      test("should filter out short words", () => {
        const articles = [{ title: "Company is up on big news" }];

        const topics = newsAnalyzer.extractTopics(articles);

        const topicWords = topics.map((t) => t.topic);
        expect(topicWords).not.toContain("is");
        expect(topicWords).not.toContain("up");
        expect(topicWords).not.toContain("on");
      });

      test("should handle empty array", () => {
        expect(newsAnalyzer.extractTopics([])).toEqual([]);
      });

      test("should handle non-array input", () => {
        expect(newsAnalyzer.extractTopics(null)).toEqual([]);
        expect(newsAnalyzer.extractTopics("not array")).toEqual([]);
      });

      test("should handle articles without titles", () => {
        const articles = [
          { description: "Some description" },
          { title: "Valid title with technology" },
        ];

        const topics = newsAnalyzer.extractTopics(articles);
        expect(topics.length).toBeGreaterThan(0);
      });

      test("should sort topics by frequency", () => {
        const articles = [
          { title: "Apple reports quarterly earnings" },
          { title: "Apple stock performance analysis" },
          { title: "Technology earnings this quarter" },
        ];

        const topics = newsAnalyzer.extractTopics(articles);

        // "apple" should be first (appears 2 times)
        expect(topics[0].topic).toBe("apple");
        expect(topics[0].count).toBe(2);
        expect(topics[0].frequency).toBeCloseTo(2 / 3);
      });

      test("should limit to top 10 topics", () => {
        const articles = Array.from({ length: 20 }, (_, i) => ({
          title: `Topic${i} unique word${i} content${i} information${i}`,
        }));

        const topics = newsAnalyzer.extractTopics(articles);
        expect(topics.length).toBeLessThanOrEqual(10);
      });

      test("should handle extraction errors gracefully", () => {
        // Mock String.prototype.toLowerCase to throw error
        const originalToLowerCase = String.prototype.toLowerCase;
        String.prototype.toLowerCase = jest.fn(() => {
          throw new Error("Test error");
        });

        const result = newsAnalyzer.extractTopics([{ title: "test" }]);
        expect(result).toEqual([]);

        // Restore original method
        String.prototype.toLowerCase = originalToLowerCase;
      });
    });
  });

  describe("Impact Calculation", () => {
    describe("calculateImpact", () => {
      test("should calculate high impact for credible recent sources", () => {
        const article = {
          source: "Reuters Financial News",
          publishedAt: new Date().toISOString(), // Now
          description:
            "Detailed article with comprehensive analysis that provides extensive coverage of the financial markets and economic indicators with in-depth research and thorough examination of market trends and investment opportunities",
        };

        const result = newsAnalyzer.calculateImpact(article);

        expect(result.impact).toBe("high");
        expect(result.score).toBeGreaterThan(0.8);
        expect(result.factors.source).toBe("Reuters Financial News");
        expect(result.factors.recency).toBe("recent");
        expect(result.factors.contentLength).toBeGreaterThanOrEqual(200);
      });

      test("should calculate medium impact", () => {
        const article = {
          source: "Some News Source",
          publishedAt: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(), // 3 hours ago
          description: "Moderately detailed article with some analysis",
        };

        const result = newsAnalyzer.calculateImpact(article);

        expect(result.impact).toBe("medium");
        expect(result.score).toBeGreaterThanOrEqual(0.6);
        expect(result.score).toBeLessThan(0.8);
      });

      test("should calculate low impact for basic articles", () => {
        const article = {
          source: "Unknown Source",
          publishedAt: new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString(), // 48 hours ago
          description: "Short description",
        };

        const result = newsAnalyzer.calculateImpact(article);

        expect(result.impact).toBe("low");
        expect(result.score).toBeLessThan(0.6);
      });

      test("should handle missing article data", () => {
        expect(newsAnalyzer.calculateImpact(null)).toEqual({
          impact: "low",
          score: 0,
        });

        expect(newsAnalyzer.calculateImpact({})).toEqual({
          impact: "low",
          score: 0.5,
          factors: {
            source: "unknown",
            recency: "unknown",
            contentLength: 0,
          },
        });
      });

      test("should boost score for credible sources", () => {
        const credibleSources = [
          "Reuters",
          "Bloomberg News",
          "CNBC Financial",
          "WSJ Markets",
          "FT Business",
        ];

        credibleSources.forEach((source) => {
          const article = { source };
          const result = newsAnalyzer.calculateImpact(article);
          expect(result.score).toBeGreaterThanOrEqual(0.7); // Base score (0.5) + credibility boost (0.2)
        });
      });

      test("should boost score for recent articles", () => {
        const recentArticle = {
          publishedAt: new Date(Date.now() - 30 * 60 * 1000).toISOString(), // 30 minutes ago
        };
        const olderArticle = {
          publishedAt: new Date(Date.now() - 12 * 60 * 60 * 1000).toISOString(), // 12 hours ago
        };

        const recentResult = newsAnalyzer.calculateImpact(recentArticle);
        const olderResult = newsAnalyzer.calculateImpact(olderArticle);

        expect(recentResult.score).toBeGreaterThan(olderResult.score);
      });

      test("should boost score for longer content", () => {
        const longArticle = {
          description: "A".repeat(250), // 250 characters
        };
        const shortArticle = {
          description: "Short description",
        };

        const longResult = newsAnalyzer.calculateImpact(longArticle);
        const shortResult = newsAnalyzer.calculateImpact(shortArticle);

        expect(longResult.score).toBeGreaterThan(shortResult.score);
      });

      test("should handle calculation errors gracefully", () => {
        // Mock Date.now to throw error
        const originalDateNow = Date.now;
        Date.now = jest.fn(() => {
          throw new Error("Date error");
        });

        const result = newsAnalyzer.calculateImpact({
          publishedAt: "2024-01-01T00:00:00Z",
        });

        expect(result.impact).toBe("low");
        expect(result.score).toBe(0);
        expect(result.error).toBe("Date error");

        // Restore original method
        Date.now = originalDateNow;
      });
    });
  });

  describe("Reliability Scoring", () => {
    describe("calculateReliabilityScore", () => {
      test("should assign high scores to reliable sources", () => {
        const reliableSources = [
          "Reuters",
          "Bloomberg",
          "Wall Street Journal",
          "Financial Times",
          "CNBC",
          "MarketWatch",
        ];

        reliableSources.forEach((source) => {
          const score = newsAnalyzer.calculateReliabilityScore(source);
          expect(score).toBe(0.9);
        });
      });

      test("should assign medium scores to medium reliability sources", () => {
        const mediumSources = [
          "CNN",
          "BBC",
          "Forbes",
          "Business Insider",
          "Washington Post",
        ];

        mediumSources.forEach((source) => {
          const score = newsAnalyzer.calculateReliabilityScore(source);
          expect(score).toBe(0.7);
        });
      });

      test("should assign low scores to unreliable sources", () => {
        const unreliableSources = [
          "Random Blog",
          "Twitter Feed",
          "Reddit Post",
          "Facebook News",
          "Some Forum",
        ];

        unreliableSources.forEach((source) => {
          const score = newsAnalyzer.calculateReliabilityScore(source);
          expect(score).toBe(0.3);
        });
      });

      test("should handle case insensitive matching", () => {
        expect(newsAnalyzer.calculateReliabilityScore("REUTERS")).toBe(0.9);
        expect(newsAnalyzer.calculateReliabilityScore("bloomberg")).toBe(0.9);
        expect(
          newsAnalyzer.calculateReliabilityScore("Wall Street Journal")
        ).toBe(0.9);
      });

      test("should handle partial matching", () => {
        expect(
          newsAnalyzer.calculateReliabilityScore("Reuters Financial News")
        ).toBe(0.9);
        expect(newsAnalyzer.calculateReliabilityScore("Bloomberg TV")).toBe(
          0.9
        );
        expect(newsAnalyzer.calculateReliabilityScore("CNN Business")).toBe(
          0.7
        );
      });

      test("should return default score for unknown sources", () => {
        expect(
          newsAnalyzer.calculateReliabilityScore("Unknown News Source")
        ).toBe(0.5);
        expect(newsAnalyzer.calculateReliabilityScore("Some Random Site")).toBe(
          0.5
        );
      });

      test("should handle invalid inputs", () => {
        expect(newsAnalyzer.calculateReliabilityScore(null)).toBe(0.5);
        expect(newsAnalyzer.calculateReliabilityScore(undefined)).toBe(0.5);
        expect(newsAnalyzer.calculateReliabilityScore("")).toBe(0.5);
        expect(newsAnalyzer.calculateReliabilityScore(123)).toBe(0.5);
      });

      test("should handle errors gracefully", () => {
        // Mock toLowerCase to throw error
        const originalToLowerCase = String.prototype.toLowerCase;
        String.prototype.toLowerCase = jest.fn(() => {
          throw new Error("Test error");
        });

        const result = newsAnalyzer.calculateReliabilityScore("test");
        expect(result).toBe(0.5);

        // Restore original method
        String.prototype.toLowerCase = originalToLowerCase;
      });
    });
  });

  describe("Configuration Management", () => {
    describe("getSentimentKeywords", () => {
      test("should return sentiment keywords configuration", () => {
        const keywords = newsAnalyzer.getSentimentKeywords();

        expect(keywords).toHaveProperty("positive");
        expect(keywords).toHaveProperty("negative");
        expect(keywords).toHaveProperty("neutral");
        expect(Array.isArray(keywords.positive)).toBe(true);
        expect(Array.isArray(keywords.negative)).toBe(true);
        expect(Array.isArray(keywords.neutral)).toBe(true);
      });

      test("should contain expected keywords", () => {
        const keywords = newsAnalyzer.getSentimentKeywords();

        expect(keywords.positive).toContain("growth");
        expect(keywords.positive).toContain("profit");
        expect(keywords.negative).toContain("loss");
        expect(keywords.negative).toContain("decline");
        expect(keywords.neutral).toContain("maintain");
      });
    });

    describe("updateSentimentKeywords", () => {
      beforeEach(() => {
        // Reset keywords to original state
        const original = newsAnalyzer.getSentimentKeywords();
        newsAnalyzer.sentimentKeywords = {
          positive: [...original.positive],
          negative: [...original.negative],
          neutral: [...original.neutral],
        };
      });

      test("should add new positive keywords", () => {
        const result = newsAnalyzer.updateSentimentKeywords({
          positive: ["excellent", "amazing"],
        });

        expect(result).toBe(true);
        const keywords = newsAnalyzer.getSentimentKeywords();
        expect(keywords.positive).toContain("excellent");
        expect(keywords.positive).toContain("amazing");
      });

      test("should add new negative keywords", () => {
        const result = newsAnalyzer.updateSentimentKeywords({
          negative: ["terrible", "awful"],
        });

        expect(result).toBe(true);
        const keywords = newsAnalyzer.getSentimentKeywords();
        expect(keywords.negative).toContain("terrible");
        expect(keywords.negative).toContain("awful");
      });

      test("should add new neutral keywords", () => {
        const result = newsAnalyzer.updateSentimentKeywords({
          neutral: ["steady", "consistent"],
        });

        expect(result).toBe(true);
        const keywords = newsAnalyzer.getSentimentKeywords();
        expect(keywords.neutral).toContain("steady");
        expect(keywords.neutral).toContain("consistent");
      });

      test("should handle partial updates", () => {
        const result = newsAnalyzer.updateSentimentKeywords({
          positive: ["fantastic"],
          // No negative or neutral
        });

        expect(result).toBe(true);
        const keywords = newsAnalyzer.getSentimentKeywords();
        expect(keywords.positive).toContain("fantastic");
      });

      test("should ignore non-array values", () => {
        const originalKeywords = newsAnalyzer.getSentimentKeywords();
        const originalPositiveLength = originalKeywords.positive.length;

        const result = newsAnalyzer.updateSentimentKeywords({
          positive: "not an array",
          negative: 123,
          neutral: { key: "value" },
        });

        expect(result).toBe(true);
        const keywords = newsAnalyzer.getSentimentKeywords();
        expect(keywords.positive.length).toBe(originalPositiveLength);
      });

      test("should handle update errors gracefully", () => {
        // Mock the logger error to simulate an internal error
        const mockLogger = require("../../utils/logger");

        // Force an error by corrupting the sentimentKeywords object
        const originalKeywords = newsAnalyzer.sentimentKeywords;
        newsAnalyzer.sentimentKeywords = null;

        const result = newsAnalyzer.updateSentimentKeywords({
          positive: ["test"],
        });

        expect(result).toBe(false);
        expect(mockLogger.error).toHaveBeenCalledWith(
          "Keywords update failed:",
          expect.any(Error)
        );

        // Restore original keywords
        newsAnalyzer.sentimentKeywords = originalKeywords;
      });
    });
  });

  describe("Integration Tests", () => {
    test("should work with real news data structure", () => {
      const realNewsArticle = {
        title: "Apple Inc. Reports Strong Q4 Earnings Beat",
        description:
          "Technology giant Apple exceeded analyst expectations with bullish quarterly results showing significant growth in iPhone sales and services revenue.",
        source: "Reuters Business News",
        publishedAt: new Date().toISOString(),
        url: "https://example.com/news",
        urlToImage: "https://example.com/image.jpg",
      };

      const sentiment = newsAnalyzer.analyzeSentiment(realNewsArticle);
      const impact = newsAnalyzer.calculateImpact(realNewsArticle);
      const reliability = newsAnalyzer.calculateReliabilityScore(
        realNewsArticle.source
      );

      expect(sentiment.sentiment).toBe("positive");
      expect(sentiment.confidence).toBeGreaterThan(0);
      expect(impact.impact).toMatch(/high|medium/);
      expect(reliability).toBe(0.9);
    });

    test("should analyze news feed with mixed sentiments", () => {
      const newsFeed = [
        {
          title: "Market surges on excellent earnings reports",
          source: "Bloomberg",
        },
        {
          title: "Economic decline worries investors",
          source: "Reuters",
        },
        {
          title: "Company maintains steady performance",
          source: "CNBC",
        },
      ];

      const analysis = newsAnalyzer.analyzeArticles(newsFeed);
      const topics = newsAnalyzer.extractTopics(newsFeed);

      expect(analysis.articleCount).toBe(3);
      expect(analysis.sentimentDistribution.positive).toBeGreaterThan(0);
      expect(analysis.sentimentDistribution.negative).toBeGreaterThan(0);
      expect(analysis.sentimentDistribution.neutral).toBeGreaterThan(0);
      expect(topics.length).toBeGreaterThan(0);
    });

    test("should maintain consistency across multiple analyses", () => {
      const article = {
        title: "Consistent test article with bullish growth",
        description: "Strong performance continues",
      };

      const result1 = newsAnalyzer.analyzeSentiment(article);
      const result2 = newsAnalyzer.analyzeSentiment(article);

      expect(result1.sentiment).toBe(result2.sentiment);
      expect(result1.score).toBe(result2.score);
      expect(result1.confidence).toBe(result2.confidence);
    });
  });
});
