/**
 * News Analyzer Integration Tests
 * Tests news sentiment analysis with real news data processing
 */

const { initializeDatabase, closeDatabase } = require("../../../utils/database");
const newsAnalyzer = require("../../../utils/newsAnalyzer");

describe("News Analyzer Integration Tests", () => {
  beforeAll(async () => {
    await initializeDatabase();
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("News Data Processing", () => {
    test("should analyze news sentiment", async () => {
      const testArticle = {
        title: "Apple Reports Strong Quarterly Earnings Beat",
        content: "Apple Inc. reported strong quarterly earnings that beat analyst expectations, driven by robust iPhone sales and growing services revenue.",
        source: "test_source",
        publishedAt: new Date().toISOString(),
        symbol: "AAPL"
      };

      const sentiment = await newsAnalyzer.analyzeSentiment(testArticle);

      expect(sentiment).toBeDefined();
      expect(sentiment.score).toBeDefined();
      expect(sentiment.magnitude).toBeDefined();
      expect(sentiment.label).toBeDefined();
      
      expect(typeof sentiment.score).toBe('number');
      expect(sentiment.score).toBeGreaterThanOrEqual(-1);
      expect(sentiment.score).toBeLessThanOrEqual(1);
      expect(['positive', 'negative', 'neutral']).toContain(sentiment.label);
    });

    test("should extract key topics from news", async () => {
      const testArticle = {
        title: "Tesla Announces New Manufacturing Facility",
        content: "Tesla announced plans for a new electric vehicle manufacturing facility that will increase production capacity and create thousands of jobs.",
        symbol: "TSLA"
      };

      const topics = await newsAnalyzer.extractTopics(testArticle);

      expect(Array.isArray(topics)).toBe(true);
      expect(topics.length).toBeGreaterThan(0);
      
      topics.forEach(topic => {
        expect(topic.keyword).toBeDefined();
        expect(topic.relevance).toBeDefined();
        expect(typeof topic.relevance).toBe('number');
        expect(topic.relevance).toBeGreaterThan(0);
        expect(topic.relevance).toBeLessThanOrEqual(1);
      });
    });
  });

  describe("Real-time News Processing", () => {
    test("should process news feed", async () => {
      const newsFeed = [
        {
          title: "Market Opens Higher on Positive Economic Data",
          content: "Stock markets opened higher today following positive economic indicators...",
          symbol: "SPY"
        },
        {
          title: "Tech Stocks Rally on AI News",
          content: "Technology stocks surged on artificial intelligence development announcements...",
          symbol: "QQQ"
        }
      ];

      const processedFeed = await newsAnalyzer.processNewsFeed(newsFeed);

      expect(Array.isArray(processedFeed)).toBe(true);
      expect(processedFeed.length).toBe(newsFeed.length);

      processedFeed.forEach(article => {
        expect(article.sentiment).toBeDefined();
        expect(article.topics).toBeDefined();
        expect(article.processedAt).toBeDefined();
      });
    });

    test("should handle high-volume news processing", async () => {
      const largeNewsFeed = Array.from({ length: 100 }, (_, i) => ({
        title: `Test Article ${i}`,
        content: `This is test content for article ${i} about market movements and stock performance.`,
        symbol: i % 2 === 0 ? "AAPL" : "GOOGL"
      }));

      const startTime = Date.now();
      const processed = await newsAnalyzer.processBulkNews(largeNewsFeed);
      const duration = Date.now() - startTime;

      expect(processed.length).toBe(100);
      expect(duration).toBeLessThan(30000); // Should complete within 30 seconds

      processed.forEach(article => {
        expect(article.sentiment).toBeDefined();
        expect(article.topics).toBeDefined();
      });
    });
  });

  describe("Symbol-Specific Analysis", () => {
    test("should analyze news for specific symbols", async () => {
      const symbol = "AAPL";
      const symbolNews = await newsAnalyzer.getSymbolNews(symbol, { limit: 10 });

      expect(Array.isArray(symbolNews)).toBe(true);
      symbolNews.forEach(article => {
        expect(article.symbol).toBe(symbol);
        expect(article.sentiment).toBeDefined();
        expect(article.relevanceScore).toBeDefined();
      });
    });

    test("should calculate symbol sentiment score", async () => {
      const symbol = "AAPL";
      const sentimentScore = await newsAnalyzer.getSymbolSentimentScore(symbol);

      expect(sentimentScore).toBeDefined();
      expect(sentimentScore.composite).toBeDefined();
      expect(sentimentScore.trend).toBeDefined();
      expect(sentimentScore.articleCount).toBeDefined();
      expect(sentimentScore.timeframe).toBeDefined();

      expect(typeof sentimentScore.composite).toBe('number');
      expect(sentimentScore.composite).toBeGreaterThanOrEqual(-1);
      expect(sentimentScore.composite).toBeLessThanOrEqual(1);
    });
  });

  describe("Trend Analysis", () => {
    test("should identify trending topics", async () => {
      const trendingTopics = await newsAnalyzer.getTrendingTopics({ period: "24h" });

      expect(Array.isArray(trendingTopics)).toBe(true);
      trendingTopics.forEach(topic => {
        expect(topic.keyword).toBeDefined();
        expect(topic.frequency).toBeDefined();
        expect(topic.sentiment).toBeDefined();
        expect(topic.growth).toBeDefined();

        expect(typeof topic.frequency).toBe('number');
        expect(topic.frequency).toBeGreaterThan(0);
      });
    });

    test("should analyze sentiment trends over time", async () => {
      const symbol = "AAPL";
      const trendAnalysis = await newsAnalyzer.analyzeSentimentTrends(symbol, {
        period: "7days",
        granularity: "1hour"
      });

      expect(trendAnalysis).toBeDefined();
      expect(Array.isArray(trendAnalysis.timeline)).toBe(true);
      expect(trendAnalysis.overall).toBeDefined();
      expect(trendAnalysis.volatility).toBeDefined();

      trendAnalysis.timeline.forEach(point => {
        expect(point.timestamp).toBeDefined();
        expect(point.sentiment).toBeDefined();
        expect(point.volume).toBeDefined();
      });
    });
  });

  describe("News Source Quality", () => {
    test("should evaluate news source credibility", async () => {
      const sources = ["Reuters", "Bloomberg", "Unknown Source"];
      
      for (const source of sources) {
        const credibility = await newsAnalyzer.evaluateSourceCredibility(source);
        
        expect(credibility).toBeDefined();
        expect(credibility.score).toBeDefined();
        expect(credibility.tier).toBeDefined();
        expect(credibility.factors).toBeDefined();

        expect(typeof credibility.score).toBe('number');
        expect(credibility.score).toBeGreaterThanOrEqual(0);
        expect(credibility.score).toBeLessThanOrEqual(1);
      }
    });

    test("should weight analysis by source quality", async () => {
      const highQualityArticle = {
        title: "Market Analysis",
        content: "Professional market analysis content...",
        source: "Bloomberg",
        symbol: "AAPL"
      };

      const lowQualityArticle = {
        title: "Market Analysis",
        content: "Professional market analysis content...",
        source: "Unknown Blog",
        symbol: "AAPL"
      };

      const highQualitySentiment = await newsAnalyzer.analyzeSentiment(highQualityArticle);
      const lowQualitySentiment = await newsAnalyzer.analyzeSentiment(lowQualityArticle);

      expect(highQualitySentiment.confidence).toBeGreaterThan(lowQualitySentiment.confidence);
      expect(highQualitySentiment.weight).toBeGreaterThan(lowQualitySentiment.weight);
    });
  });

  describe("Language Processing", () => {
    test("should handle multiple languages", async () => {
      const articles = [
        {
          title: "Apple Reports Strong Earnings",
          content: "Apple reported strong quarterly earnings...",
          language: "en"
        },
        {
          title: "Apple reporta ganancias sólidas",
          content: "Apple reportó ganancias trimestrales sólidas...",
          language: "es"
        }
      ];

      for (const article of articles) {
        const analysis = await newsAnalyzer.analyzeSentiment(article);
        
        expect(analysis).toBeDefined();
        expect(analysis.language).toBe(article.language);
        expect(analysis.sentiment).toBeDefined();
      }
    });

    test("should detect article language automatically", async () => {
      const article = {
        title: "Apple annonce des résultats solides",
        content: "Apple a annoncé des résultats trimestriels solides qui dépassent les attentes des analystes..."
      };

      const analysis = await newsAnalyzer.detectLanguageAndAnalyze(article);
      
      expect(analysis).toBeDefined();
      expect(analysis.detectedLanguage).toBe("fr");
      expect(analysis.sentiment).toBeDefined();
    });
  });

  describe("Market Impact Analysis", () => {
    test("should predict market impact from news", async () => {
      const breakingNews = {
        title: "Apple Announces Record Breaking Quarterly Revenue",
        content: "Apple announced record-breaking quarterly revenue driven by strong iPhone sales and services growth...",
        symbol: "AAPL",
        publishedAt: new Date().toISOString()
      };

      const marketImpact = await newsAnalyzer.predictMarketImpact(breakingNews);

      expect(marketImpact).toBeDefined();
      expect(marketImpact.impactScore).toBeDefined();
      expect(marketImpact.direction).toBeDefined();
      expect(marketImpact.confidence).toBeDefined();
      expect(marketImpact.timeframe).toBeDefined();

      expect(typeof marketImpact.impactScore).toBe('number');
      expect(['positive', 'negative', 'neutral']).toContain(marketImpact.direction);
    });

    test("should correlate news with price movements", async () => {
      const symbol = "AAPL";
      const correlation = await newsAnalyzer.correlateSentimentWithPrice(symbol, {
        period: "30days",
        lag: "1hour"
      });

      expect(correlation).toBeDefined();
      expect(correlation.coefficient).toBeDefined();
      expect(correlation.significance).toBeDefined();
      expect(correlation.strength).toBeDefined();

      expect(typeof correlation.coefficient).toBe('number');
      expect(correlation.coefficient).toBeGreaterThanOrEqual(-1);
      expect(correlation.coefficient).toBeLessThanOrEqual(1);
    });
  });

  describe("Alert Integration", () => {
    test("should trigger news-based alerts", async () => {
      const alertConfig = {
        symbol: "AAPL",
        sentimentThreshold: 0.7,
        keywords: ["earnings", "revenue", "breakthrough"],
        urgency: "high"
      };

      const newsAlert = await newsAnalyzer.setupNewsAlert(alertConfig);

      expect(newsAlert).toBeDefined();
      expect(newsAlert.alertId).toBeDefined();
      expect(newsAlert.active).toBe(true);
      expect(newsAlert.criteria).toEqual(alertConfig);
    });

    test("should process real-time news alerts", async () => {
      const urgentNews = {
        title: "Apple CEO Announces Major Product Launch",
        content: "Apple CEO announced a revolutionary new product that could transform the industry...",
        symbol: "AAPL",
        publishedAt: new Date().toISOString(),
        urgency: "breaking"
      };

      const alertTriggered = await newsAnalyzer.processNewsAlert(urgentNews);

      expect(alertTriggered).toBeDefined();
      expect(typeof alertTriggered.triggered).toBe('boolean');
      if (alertTriggered.triggered) {
        expect(alertTriggered.alertId).toBeDefined();
        expect(alertTriggered.reason).toBeDefined();
      }
    });
  });

  describe("Performance and Scalability", () => {
    test("should process news articles efficiently", async () => {
      const testArticles = Array.from({ length: 50 }, (_, i) => ({
        title: `Performance Test Article ${i}`,
        content: `This is test content for performance testing article ${i} with various market-related keywords and sentiment indicators.`,
        symbol: "AAPL"
      }));

      const startTime = Date.now();
      const results = await newsAnalyzer.processBulkNews(testArticles);
      const duration = Date.now() - startTime;

      expect(results.length).toBe(50);
      expect(duration).toBeLessThan(15000); // 15 seconds for 50 articles

      results.forEach(result => {
        expect(result.sentiment).toBeDefined();
        expect(result.processingTime).toBeDefined();
        expect(result.processingTime).toBeLessThan(1000); // Each article < 1 second
      });
    });

    test("should handle memory efficiently with large datasets", async () => {
      const initialMemory = process.memoryUsage().heapUsed;
      
      // Process large amount of news data
      const largeDataset = Array.from({ length: 200 }, (_, i) => ({
        title: `Memory Test Article ${i}`,
        content: `Large content for memory testing ${"x".repeat(1000)}`,
        symbol: "TEST"
      }));

      await newsAnalyzer.processBulkNews(largeDataset);
      
      const finalMemory = process.memoryUsage().heapUsed;
      const memoryIncrease = finalMemory - initialMemory;
      const maxAcceptableIncrease = 100 * 1024 * 1024; // 100MB

      expect(memoryIncrease).toBeLessThan(maxAcceptableIncrease);
    });
  });
});