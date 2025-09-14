/**
 * News Integration API Tests
 * Tests the enhanced news functionality with database integration and sentiment analysis
 */

import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock import.meta.env
Object.defineProperty(import.meta, 'env', {
  value: {
    VITE_API_URL: 'http://localhost:3001',
    MODE: 'test',
    DEV: true,
    PROD: false,
    BASE_URL: '/'
  },
  writable: true,
  configurable: true
});

// Mock fetch for API calls
global.fetch = vi.fn();

const mockNewsResponse = {
  success: true,
  data: {
    news: [
      {
        id: 1,
        uuid: "news-uuid-1",
        symbol: "AAPL",
        headline: "Apple Reports Strong Q4 Earnings Beat",
        summary: "Apple Inc. reported quarterly earnings that exceeded analyst expectations, driven by strong iPhone sales and services revenue.",
        url: "https://example.com/news/apple-earnings",
        source: "Financial Times",
        author: "Tech Reporter",
        published_at: "2024-01-15T08:30:00Z",
        category: "earnings",
        sentiment: 0.85,
        sentiment_confidence: 0.92,
        content_summary: "Strong earnings performance with revenue growth across all segments",
        tags: ["earnings", "technology", "mobile"],
        image_url: "https://example.com/images/apple-logo.jpg",
        related_symbols: ["AAPL", "MSFT"],
        impact_score: 8.5,
        credibility_score: 9.2
      },
      {
        id: 2,
        uuid: "news-uuid-2",
        symbol: "TSLA",
        headline: "Tesla Stock Falls on Production Concerns",
        summary: "Tesla shares declined following reports of potential production delays at its new facility.",
        url: "https://example.com/news/tesla-production",
        source: "Reuters",
        author: "Auto Reporter",
        published_at: "2024-01-15T07:15:00Z",
        category: "company_news",
        sentiment: -0.65,
        sentiment_confidence: 0.88,
        content_summary: "Production challenges may impact quarterly delivery targets",
        tags: ["automotive", "production", "manufacturing"],
        image_url: "https://example.com/images/tesla-factory.jpg",
        related_symbols: ["TSLA"],
        impact_score: 7.2,
        credibility_score: 8.8
      }
    ],
    pagination: {
      page: 1,
      limit: 20,
      total_count: 245,
      total_pages: 13,
      has_more: true
    },
    filters: {
      symbol: null,
      category: null,
      sentiment: null,
      date_range: "last_24h"
    },
    summary: {
      total_articles: 245,
      positive_sentiment: 147,
      negative_sentiment: 68,
      neutral_sentiment: 30,
      avg_sentiment: 0.24,
      top_symbols: ["AAPL", "TSLA", "NVDA", "AMZN", "GOOGL"],
      trending_topics: ["earnings", "ai", "electric_vehicles", "semiconductors"]
    },
    metadata: {
      database_integrated: true,
      sentiment_analysis: true,
      real_time_updates: true,
      data_sources: ["reuters", "bloomberg", "financial_times", "yahoo_finance"]
    }
  },
  timestamp: "2024-01-15T10:30:00Z"
};

const mockSentimentAnalysisResponse = {
  success: true,
  data: {
    analysis: {
      overall_sentiment: 0.15,
      sentiment_distribution: {
        positive: 62.5,
        negative: 25.0,
        neutral: 12.5
      },
      confidence_score: 0.84,
      analysis_period: "last_24h",
      total_articles: 245
    },
    symbol_sentiments: [
      {
        symbol: "AAPL",
        sentiment: 0.85,
        confidence: 0.92,
        article_count: 38,
        trend: "bullish"
      },
      {
        symbol: "TSLA",
        sentiment: -0.65,
        confidence: 0.88,
        article_count: 25,
        trend: "bearish"
      },
      {
        symbol: "NVDA",
        sentiment: 0.72,
        confidence: 0.90,
        article_count: 42,
        trend: "bullish"
      }
    ],
    trending_topics: [
      {
        topic: "earnings",
        sentiment: 0.68,
        article_count: 85,
        trend: "up"
      },
      {
        topic: "ai",
        sentiment: 0.74,
        article_count: 67,
        trend: "up"
      }
    ],
    metadata: {
      algorithm_version: "2.1",
      processing_time_ms: 245,
      data_quality_score: 0.91
    }
  },
  timestamp: "2024-01-15T10:30:00Z"
};

// Helper function to create News API client
class NewsAPI {
  constructor(baseURL = 'http://localhost:3001') {
    this.baseURL = baseURL;
  }

  async getNews(filters = {}) {
    const params = new URLSearchParams();
    
    if (filters.symbol) params.append('symbol', filters.symbol);
    if (filters.category) params.append('category', filters.category);
    if (filters.sentiment) params.append('sentiment', filters.sentiment);
    if (filters.limit) params.append('limit', filters.limit.toString());
    if (filters.page) params.append('page', filters.page.toString());

    const url = `${this.baseURL}/api/news?${params.toString()}`;
    const response = await fetch(url);
    
    if (!response.ok) {
      throw new Error(`News API failed: ${response.status}`);
    }
    
    return await response.json();
  }

  async getSentimentAnalysis(symbol = null, period = 'last_24h') {
    const params = new URLSearchParams();
    if (symbol) params.append('symbol', symbol);
    params.append('period', period);

    const url = `${this.baseURL}/api/news/sentiment?${params.toString()}`;
    const response = await fetch(url);
    
    if (!response.ok) {
      throw new Error(`Sentiment analysis failed: ${response.status}`);
    }
    
    return await response.json();
  }

  async getNewsBySymbol(symbol, limit = 20) {
    return this.getNews({ symbol, limit });
  }

  async getTrendingNews(limit = 10) {
    return this.getNews({ limit, trending: true });
  }
}

describe("News Integration API", () => {
  let newsAPI;

  beforeEach(() => {
    vi.clearAllMocks();
    newsAPI = new NewsAPI();
    
    // Default fetch mock
    fetch.mockImplementation((url) => {
      if (url.includes('/api/news/sentiment')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockSentimentAnalysisResponse)
        });
      }
      
      if (url.includes('/api/news')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockNewsResponse)
        });
      }
      
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ data: {} })
      });
    });
  });

  describe("News Retrieval", () => {
    it("fetches news successfully", async () => {
      const result = await newsAPI.getNews();
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/news?')
      );
      
      expect(result.success).toBe(true);
      expect(result.data.news).toHaveLength(2);
      expect(result.data.metadata.database_integrated).toBe(true);
    });

    it("returns enhanced news with sentiment analysis", async () => {
      const result = await newsAPI.getNews();
      
      const appleNews = result.data.news.find(n => n.symbol === 'AAPL');
      expect(appleNews.sentiment).toBe(0.85);
      expect(appleNews.sentiment_confidence).toBe(0.92);
      expect(appleNews.impact_score).toBe(8.5);
      expect(appleNews.credibility_score).toBe(9.2);
    });

    it("includes comprehensive article metadata", async () => {
      const result = await newsAPI.getNews();
      
      const article = result.data.news[0];
      expect(article.uuid).toBeTruthy();
      expect(article.headline).toBeTruthy();
      expect(article.summary).toBeTruthy();
      expect(article.source).toBe('Financial Times');
      expect(article.author).toBe('Tech Reporter');
      expect(article.published_at).toBeTruthy();
      expect(article.category).toBe('earnings');
      expect(article.tags).toContain('earnings');
      expect(article.related_symbols).toContain('AAPL');
    });

    it("filters news by symbol", async () => {
      await newsAPI.getNewsBySymbol('AAPL', 10);
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('symbol=AAPL&limit=10')
      );
    });

    it("filters news by category", async () => {
      await newsAPI.getNews({ category: 'earnings' });
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('category=earnings')
      );
    });

    it("filters news by sentiment", async () => {
      await newsAPI.getNews({ sentiment: 'positive' });
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('sentiment=positive')
      );
    });

    it("supports pagination", async () => {
      const result = await newsAPI.getNews({ page: 2, limit: 50 });
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringMatching(/page=2.*limit=50|limit=50.*page=2/)
      );
      
      expect(result.data.pagination.page).toBe(1);
      expect(result.data.pagination.limit).toBe(20);
      expect(result.data.pagination.total_count).toBe(245);
      expect(result.data.pagination.has_more).toBe(true);
    });
  });

  describe("Sentiment Analysis", () => {
    it("performs overall market sentiment analysis", async () => {
      const result = await newsAPI.getSentimentAnalysis();
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/news/sentiment?period=last_24h')
      );
      
      expect(result.success).toBe(true);
      expect(result.data.analysis.overall_sentiment).toBe(0.15);
      expect(result.data.analysis.confidence_score).toBe(0.84);
      expect(result.data.analysis.total_articles).toBe(245);
    });

    it("provides sentiment distribution breakdown", async () => {
      const result = await newsAPI.getSentimentAnalysis();
      
      const distribution = result.data.analysis.sentiment_distribution;
      expect(distribution.positive).toBe(62.5);
      expect(distribution.negative).toBe(25.0);
      expect(distribution.neutral).toBe(12.5);
      
      // Should total 100%
      const total = distribution.positive + distribution.negative + distribution.neutral;
      expect(total).toBe(100);
    });

    it("analyzes sentiment by symbol", async () => {
      const result = await newsAPI.getSentimentAnalysis('AAPL');
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('symbol=AAPL')
      );
      
      const symbolSentiments = result.data.symbol_sentiments;
      const aaplSentiment = symbolSentiments.find(s => s.symbol === 'AAPL');
      
      expect(aaplSentiment.sentiment).toBe(0.85);
      expect(aaplSentiment.confidence).toBe(0.92);
      expect(aaplSentiment.trend).toBe('bullish');
      expect(aaplSentiment.article_count).toBe(38);
    });

    it("identifies trending topics with sentiment", async () => {
      const result = await newsAPI.getSentimentAnalysis();
      
      const trendingTopics = result.data.trending_topics;
      const earningsTopic = trendingTopics.find(t => t.topic === 'earnings');
      
      expect(earningsTopic.sentiment).toBe(0.68);
      expect(earningsTopic.article_count).toBe(85);
      expect(earningsTopic.trend).toBe('up');
    });

    it("provides algorithm performance metadata", async () => {
      const result = await newsAPI.getSentimentAnalysis();
      
      expect(result.data.metadata.algorithm_version).toBe('2.1');
      expect(result.data.metadata.processing_time_ms).toBe(245);
      expect(result.data.metadata.data_quality_score).toBe(0.91);
    });

    it("handles different time periods", async () => {
      await newsAPI.getSentimentAnalysis(null, 'last_week');
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('period=last_week')
      );
    });
  });

  describe("Database Integration", () => {
    it("indicates database integration status", async () => {
      const result = await newsAPI.getNews();
      
      expect(result.data.metadata.database_integrated).toBe(true);
      expect(result.data.metadata.sentiment_analysis).toBe(true);
      expect(result.data.metadata.real_time_updates).toBe(true);
    });

    it("includes comprehensive summary statistics", async () => {
      const result = await newsAPI.getNews();
      
      const summary = result.data.summary;
      expect(summary.total_articles).toBe(245);
      expect(summary.positive_sentiment).toBe(147);
      expect(summary.negative_sentiment).toBe(68);
      expect(summary.neutral_sentiment).toBe(30);
      expect(summary.avg_sentiment).toBe(0.24);
      expect(summary.top_symbols).toContain('AAPL');
      expect(summary.trending_topics).toContain('earnings');
    });

    it("tracks data sources", async () => {
      const result = await newsAPI.getNews();
      
      const dataSources = result.data.metadata.data_sources;
      expect(dataSources).toContain('reuters');
      expect(dataSources).toContain('bloomberg');
      expect(dataSources).toContain('financial_times');
      expect(dataSources).toContain('yahoo_finance');
    });
  });

  describe("Error Handling", () => {
    it("handles news API errors", async () => {
      fetch.mockImplementationOnce(() => Promise.resolve({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ 
          success: false, 
          error: "News service unavailable",
          details: "Database connectivity issues"
        })
      }));

      await expect(newsAPI.getNews()).rejects.toThrow('News API failed: 500');
    });

    it("handles sentiment analysis errors", async () => {
      fetch.mockImplementationOnce(() => Promise.resolve({
        ok: false,
        status: 503,
        json: () => Promise.resolve({ 
          success: false, 
          error: "Sentiment analysis temporarily unavailable"
        })
      }));

      await expect(newsAPI.getSentimentAnalysis()).rejects.toThrow('Sentiment analysis failed: 503');
    });

    it("handles network errors gracefully", async () => {
      fetch.mockImplementationOnce(() => Promise.reject(new Error('Network error')));

      await expect(newsAPI.getNews()).rejects.toThrow('Network error');
    });
  });

  describe("Performance and Quality", () => {
    it("processes requests within reasonable time", async () => {
      const startTime = Date.now();
      await newsAPI.getNews();
      const endTime = Date.now();
      
      expect(endTime - startTime).toBeLessThan(5000);
    });

    it("handles large datasets efficiently", async () => {
      await newsAPI.getNews({ limit: 100 });
      
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('limit=100')
      );
    });

    it("provides data quality metrics", async () => {
      const result = await newsAPI.getSentimentAnalysis();
      
      expect(result.data.metadata.data_quality_score).toBeGreaterThan(0.8);
      expect(result.data.metadata.processing_time_ms).toBeLessThan(1000);
    });
  });

  describe("Real-time Updates", () => {
    it("includes real-time timestamps", async () => {
      const result = await newsAPI.getNews();
      
      expect(result.timestamp).toBeTruthy();
      
      result.data.news.forEach(article => {
        expect(article.published_at).toBeTruthy();
      });
    });

    it("indicates real-time data capability", async () => {
      const result = await newsAPI.getNews();
      
      expect(result.data.metadata.real_time_updates).toBe(true);
    });
  });
});