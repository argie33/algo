/**
 * Real News Service Unit Tests
 * Testing the actual newsService.js with multiple news sources and sentiment analysis
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import axios from 'axios';

// Mock axios and cacheService
vi.mock('axios');
vi.mock('../../../services/cacheService', () => ({
  default: {
    get: vi.fn(),
    set: vi.fn(),
    invalidate: vi.fn()
  },
  CacheConfigs: {
    NEWS: {
      ttl: 300000 // 5 minutes
    }
  }
}));

// Import the REAL NewsService
const newsServiceModule = await import('../../../services/newsService');
const NewsService = newsServiceModule.default || newsServiceModule.NewsService;

// Import mocked dependencies
import cacheService from '../../../services/cacheService';

describe('📰 Real News Service', () => {
  let newsService;
  let mockAxios;

  beforeEach(() => {
    vi.clearAllMocks();
    
    // Setup axios mock
    mockAxios = axios;
    mockAxios.get = vi.fn();
    mockAxios.create = vi.fn(() => mockAxios);

    // Mock environment variables
    vi.stubGlobal('process', {
      env: {
        REACT_APP_ALPACA_API_KEY: 'test_alpaca_key',
        REACT_APP_FINNHUB_API_KEY: 'test_finnhub_key',
        REACT_APP_NEWSAPI_KEY: 'test_newsapi_key'
      }
    });

    // Create fresh service instance
    newsService = new NewsService();

    // Mock console to avoid noise
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Service Initialization', () => {
    it('should initialize with correct news sources configuration', () => {
      expect(newsService.sources).toEqual({
        alpaca: {
          enabled: true,
          name: 'Alpaca News',
          apiKey: 'test_alpaca_key',
          baseUrl: 'https://data.alpaca.markets/v1beta1/news'
        },
        finnhub: {
          enabled: false,
          name: 'Finnhub News',
          apiKey: 'test_finnhub_key',
          baseUrl: 'https://finnhub.io/api/v1/news'
        },
        newsapi: {
          enabled: false,
          name: 'NewsAPI',
          apiKey: 'test_newsapi_key',
          baseUrl: 'https://newsapi.org/v2'
        }
      });
    });

    it('should initialize with predefined categories', () => {
      expect(newsService.categories).toEqual([
        'general',
        'earnings',
        'mergers',
        'analyst',
        'economic',
        'crypto',
        'technology',
        'healthcare',
        'energy'
      ]);
    });

    it('should initialize with sentiment keywords', () => {
      expect(newsService.sentimentKeywords).toHaveProperty('positive');
      expect(newsService.sentimentKeywords).toHaveProperty('negative');
      expect(newsService.sentimentKeywords).toHaveProperty('neutral');
      
      expect(newsService.sentimentKeywords.positive).toContain('surge');
      expect(newsService.sentimentKeywords.negative).toContain('fall');
      expect(newsService.sentimentKeywords.neutral).toContain('stable');
    });

    it('should have alpaca source enabled by default', () => {
      expect(newsService.sources.alpaca.enabled).toBe(true);
      expect(newsService.sources.finnhub.enabled).toBe(false);
      expect(newsService.sources.newsapi.enabled).toBe(false);
    });
  });

  describe('News Fetching for Symbols', () => {
    const mockAlpacaResponse = {
      data: {
        news: [
          {
            id: 'news_1',
            headline: 'Apple Reports Strong Q4 Earnings',
            summary: 'Apple Inc. exceeded analyst expectations with record iPhone sales...',
            author: 'Tech Reporter',
            created_at: '2024-01-15T14:30:00Z',
            updated_at: '2024-01-15T14:30:00Z',
            url: 'https://example.com/news/1',
            symbols: ['AAPL'],
            content: 'Full article content here...',
            images: [
              { url: 'https://example.com/image1.jpg', size: 'thumb' }
            ]
          },
          {
            id: 'news_2',
            headline: 'Google Announces New AI Breakthrough',
            summary: 'Alphabet Inc. unveils revolutionary machine learning technology...',
            author: 'AI Reporter',
            created_at: '2024-01-15T13:45:00Z',
            updated_at: '2024-01-15T13:45:00Z',
            url: 'https://example.com/news/2',
            symbols: ['GOOGL'],
            content: 'Full article content about AI...',
            images: []
          }
        ],
        next_page_token: 'next_token_123'
      }
    };

    it('should fetch news for specific symbols', async () => {
      mockAxios.get.mockResolvedValue(mockAlpacaResponse);
      cacheService.get.mockReturnValue(null);

      const result = await newsService.getNewsForSymbols(['AAPL', 'GOOGL']);

      expect(mockAxios.get).toHaveBeenCalledWith(
        expect.stringContaining('https://data.alpaca.markets/v1beta1/news'),
        expect.objectContaining({
          params: expect.objectContaining({
            symbols: 'AAPL,GOOGL'
          }),
          headers: expect.objectContaining({
            'APCA-API-KEY-ID': 'test_alpaca_key'
          })
        })
      );

      expect(result.articles).toHaveLength(2);
      expect(result.articles[0].headline).toBe('Apple Reports Strong Q4 Earnings');
      expect(result.articles[1].headline).toBe('Google Announces New AI Breakthrough');
    });

    it('should use cached news when available', async () => {
      const cachedNews = {
        articles: [{ id: 'cached_1', headline: 'Cached News' }],
        total: 1,
        source: 'cache'
      };
      
      cacheService.get.mockReturnValue(cachedNews);

      const result = await newsService.getNewsForSymbols(['AAPL']);

      expect(mockAxios.get).not.toHaveBeenCalled();
      expect(result).toEqual(cachedNews);
      expect(cacheService.get).toHaveBeenCalledWith('news_AAPL_{}');
    });

    it('should handle API request errors gracefully', async () => {
      mockAxios.get.mockRejectedValue(new Error('API request failed'));
      cacheService.get.mockReturnValue(null);

      const result = await newsService.getNewsForSymbols(['AAPL']);

      expect(result.articles).toEqual([]);
      expect(result.error).toBe('Failed to fetch news: API request failed');
      expect(result.total).toBe(0);
    });

    it('should filter news by date range', async () => {
      mockAxios.get.mockResolvedValue(mockAlpacaResponse);
      cacheService.get.mockReturnValue(null);

      const options = {
        startDate: '2024-01-15',
        endDate: '2024-01-16',
        limit: 10
      };

      await newsService.getNewsForSymbols(['AAPL'], options);

      expect(mockAxios.get).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          params: expect.objectContaining({
            start: '2024-01-15',
            end: '2024-01-16',
            page_size: 10
          })
        })
      );
    });

    it('should handle pagination with next page token', async () => {
      mockAxios.get.mockResolvedValue(mockAlpacaResponse);
      cacheService.get.mockReturnValue(null);

      const result = await newsService.getNewsForSymbols(['AAPL']);

      expect(result.nextPageToken).toBe('next_token_123');
      expect(result.hasMore).toBe(true);
    });
  });

  describe('General Market News', () => {
    const mockGeneralNews = {
      data: {
        news: [
          {
            id: 'general_1',
            headline: 'Federal Reserve Announces Interest Rate Decision',
            summary: 'The Federal Reserve maintains current interest rates...',
            author: 'Economics Reporter',
            created_at: '2024-01-15T15:00:00Z',
            url: 'https://example.com/fed-news',
            symbols: [],
            content: 'Federal Reserve content...'
          },
          {
            id: 'general_2',
            headline: 'Market Opens Higher on Positive Economic Data',
            summary: 'Stock markets surge following strong employment report...',
            author: 'Market Reporter',
            created_at: '2024-01-15T09:30:00Z',
            url: 'https://example.com/market-news',
            symbols: [],
            content: 'Market analysis content...'
          }
        ]
      }
    };

    it('should fetch general market news', async () => {
      mockAxios.get.mockResolvedValue(mockGeneralNews);
      cacheService.get.mockReturnValue(null);

      const result = await newsService.getGeneralNews();

      expect(mockAxios.get).toHaveBeenCalledWith(
        expect.stringContaining('https://data.alpaca.markets/v1beta1/news'),
        expect.objectContaining({
          params: expect.objectContaining({
            symbols: undefined
          })
        })
      );

      expect(result.articles).toHaveLength(2);
      expect(result.articles[0].headline).toContain('Federal Reserve');
    });

    it('should filter general news by category', async () => {
      mockAxios.get.mockResolvedValue(mockGeneralNews);
      cacheService.get.mockReturnValue(null);

      await newsService.getGeneralNews({ category: 'economic' });

      expect(mockAxios.get).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          params: expect.objectContaining({
            include_content: true,
            sort: 'desc'
          })
        })
      );
    });

    it('should handle empty news response', async () => {
      mockAxios.get.mockResolvedValue({ data: { news: [] } });
      cacheService.get.mockReturnValue(null);

      const result = await newsService.getGeneralNews();

      expect(result.articles).toEqual([]);
      expect(result.total).toBe(0);
      expect(result.hasMore).toBe(false);
    });
  });

  describe('Sentiment Analysis', () => {
    it('should analyze positive sentiment correctly', () => {
      const positiveHeadline = 'Apple Stock Surges to Record High on Strong Earnings Beat';
      const sentiment = newsService.analyzeSentiment(positiveHeadline);

      expect(sentiment.sentiment).toBe('positive');
      expect(sentiment.score).toBeGreaterThan(0);
      expect(sentiment.keywords).toContain('surge');
      expect(sentiment.keywords).toContain('beat');
    });

    it('should analyze negative sentiment correctly', () => {
      const negativeHeadline = 'Tesla Stock Plunges After CEO Warning About Production Concerns';
      const sentiment = newsService.analyzeSentiment(negativeHeadline);

      expect(sentiment.sentiment).toBe('negative');
      expect(sentiment.score).toBeLessThan(0);
      expect(sentiment.keywords).toContain('plunge');
      expect(sentiment.keywords).toContain('warning');
      expect(sentiment.keywords).toContain('concern');
    });

    it('should analyze neutral sentiment correctly', () => {
      const neutralHeadline = 'Microsoft Maintains Steady Growth in Cloud Services Division';
      const sentiment = newsService.analyzeSentiment(neutralHeadline);

      expect(sentiment.sentiment).toBe('neutral');
      expect(sentiment.score).toBe(0);
      expect(sentiment.keywords).toContain('maintain');
      expect(sentiment.keywords).toContain('steady');
    });

    it('should handle empty or null text', () => {
      expect(newsService.analyzeSentiment('')).toEqual({
        sentiment: 'neutral',
        score: 0,
        keywords: []
      });

      expect(newsService.analyzeSentiment(null)).toEqual({
        sentiment: 'neutral',
        score: 0,
        keywords: []
      });
    });

    it('should calculate weighted sentiment scores', () => {
      const mixedHeadline = 'Apple Gains Despite Market Concerns About Economic Decline';
      const sentiment = newsService.analyzeSentiment(mixedHeadline);

      // Should have both positive and negative keywords
      expect(sentiment.keywords).toContain('gain');
      expect(sentiment.keywords).toContain('concern');
      expect(sentiment.keywords).toContain('decline');
      
      // Net sentiment should reflect the balance
      expect(typeof sentiment.score).toBe('number');
    });
  });

  describe('News Filtering and Search', () => {
    const mockSearchResponse = {
      data: {
        news: [
          {
            id: 'search_1',
            headline: 'AI Technology Breakthrough in Healthcare',
            summary: 'Revolutionary AI system improves medical diagnosis...',
            symbols: ['NVDA', 'GOOGL'],
            created_at: '2024-01-15T12:00:00Z'
          }
        ]
      }
    };

    it('should search news by keywords', async () => {
      mockAxios.get.mockResolvedValue(mockSearchResponse);
      cacheService.get.mockReturnValue(null);

      const result = await newsService.searchNews('AI technology healthcare');

      expect(mockAxios.get).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          params: expect.objectContaining({
            q: 'AI technology healthcare'
          })
        })
      );

      expect(result.articles).toHaveLength(1);
      expect(result.articles[0].headline).toContain('AI Technology');
    });

    it('should filter news by sentiment', async () => {
      const newsWithSentiment = {
        articles: [
          { headline: 'Stock Surges on Great News', sentiment: 'positive' },
          { headline: 'Market Crashes on Bad Data', sentiment: 'negative' },
          { headline: 'Trading Remains Steady', sentiment: 'neutral' }
        ]
      };

      const positiveNews = newsService.filterBySentiment(newsWithSentiment.articles, 'positive');
      const negativeNews = newsService.filterBySentiment(newsWithSentiment.articles, 'negative');

      expect(positiveNews).toHaveLength(1);
      expect(positiveNews[0].sentiment).toBe('positive');
      
      expect(negativeNews).toHaveLength(1);
      expect(negativeNews[0].sentiment).toBe('negative');
    });

    it('should sort news by relevance score', () => {
      const articles = [
        { headline: 'Low relevance', relevanceScore: 0.3 },
        { headline: 'High relevance', relevanceScore: 0.9 },
        { headline: 'Medium relevance', relevanceScore: 0.6 }
      ];

      const sortedNews = newsService.sortByRelevance(articles);

      expect(sortedNews[0].relevanceScore).toBe(0.9);
      expect(sortedNews[1].relevanceScore).toBe(0.6);
      expect(sortedNews[2].relevanceScore).toBe(0.3);
    });

    it('should remove duplicate news articles', () => {
      const articlesWithDuplicates = [
        { id: '1', headline: 'News Article 1', url: 'http://example.com/1' },
        { id: '2', headline: 'News Article 2', url: 'http://example.com/2' },
        { id: '1', headline: 'News Article 1', url: 'http://example.com/1' }, // Duplicate
        { id: '3', headline: 'Different Title', url: 'http://example.com/1' } // Same URL
      ];

      const uniqueArticles = newsService.removeDuplicates(articlesWithDuplicates);

      expect(uniqueArticles).toHaveLength(2);
      expect(uniqueArticles.map(a => a.id)).toEqual(['1', '2']);
    });
  });

  describe('Multiple News Sources', () => {
    it('should enable additional news sources', () => {
      newsService.enableSource('finnhub');
      
      expect(newsService.sources.finnhub.enabled).toBe(true);
    });

    it('should disable news sources', () => {
      newsService.disableSource('alpaca');
      
      expect(newsService.sources.alpaca.enabled).toBe(false);
    });

    it('should fetch from multiple enabled sources', async () => {
      newsService.enableSource('finnhub');
      
      // Mock responses from both sources
      mockAxios.get
        .mockResolvedValueOnce(mockAlpacaResponse) // Alpaca
        .mockResolvedValueOnce({ // Finnhub
          data: [
            {
              id: 'finnhub_1',
              headline: 'Finnhub News Article',
              summary: 'News from Finnhub...',
              datetime: 1642258800, // Unix timestamp
              source: 'Reuters',
              url: 'https://finnhub.com/news/1'
            }
          ]
        });

      cacheService.get.mockReturnValue(null);

      const result = await newsService.getNewsFromAllSources(['AAPL']);

      expect(mockAxios.get).toHaveBeenCalledTimes(2);
      expect(result.articles.length).toBeGreaterThan(2); // Combined from both sources
      expect(result.sources).toContain('alpaca');
      expect(result.sources).toContain('finnhub');
    });

    it('should handle source-specific API errors', async () => {
      newsService.enableSource('finnhub');
      
      mockAxios.get
        .mockResolvedValueOnce(mockAlpacaResponse) // Alpaca succeeds
        .mockRejectedValueOnce(new Error('Finnhub API error')); // Finnhub fails

      cacheService.get.mockReturnValue(null);

      const result = await newsService.getNewsFromAllSources(['AAPL']);

      expect(result.articles).toHaveLength(2); // Only from Alpaca
      expect(result.errors).toHaveProperty('finnhub');
      expect(result.errors.finnhub).toContain('Finnhub API error');
    });
  });

  describe('Caching Strategy', () => {
    it('should cache news results with appropriate TTL', async () => {
      mockAxios.get.mockResolvedValue(mockAlpacaResponse);
      cacheService.get.mockReturnValue(null);

      await newsService.getNewsForSymbols(['AAPL']);

      expect(cacheService.set).toHaveBeenCalledWith(
        expect.stringContaining('news_AAPL'),
        expect.any(Object),
        expect.any(Number)
      );
    });

    it('should invalidate cache for specific symbols', () => {
      newsService.invalidateCache(['AAPL', 'GOOGL']);

      expect(cacheService.invalidate).toHaveBeenCalledWith('news_AAPL_*');
      expect(cacheService.invalidate).toHaveBeenCalledWith('news_GOOGL_*');
    });

    it('should invalidate all news cache', () => {
      newsService.invalidateAllCache();

      expect(cacheService.invalidate).toHaveBeenCalledWith('news_*');
    });

    it('should generate appropriate cache keys', () => {
      const key1 = newsService.generateCacheKey(['AAPL'], {});
      const key2 = newsService.generateCacheKey(['AAPL'], { startDate: '2024-01-15' });
      const key3 = newsService.generateCacheKey(['GOOGL'], {});

      expect(key1).not.toBe(key2); // Different options
      expect(key1).not.toBe(key3); // Different symbols
      expect(key1).toContain('AAPL');
      expect(key2).toContain('AAPL');
      expect(key3).toContain('GOOGL');
    });
  });

  describe('Performance and Rate Limiting', () => {
    it('should handle rate limiting gracefully', async () => {
      mockAxios.get.mockRejectedValue({
        response: { status: 429, data: { message: 'Rate limit exceeded' } }
      });
      cacheService.get.mockReturnValue(null);

      const result = await newsService.getNewsForSymbols(['AAPL']);

      expect(result.error).toContain('Rate limit exceeded');
      expect(result.articles).toEqual([]);
    });

    it('should process large news datasets efficiently', async () => {
      const largeNewsResponse = {
        data: {
          news: Array.from({ length: 1000 }, (_, i) => ({
            id: `news_${i}`,
            headline: `News Article ${i}`,
            summary: `Summary for article ${i}`,
            created_at: new Date().toISOString(),
            symbols: ['AAPL']
          }))
        }
      };

      mockAxios.get.mockResolvedValue(largeNewsResponse);
      cacheService.get.mockReturnValue(null);

      const startTime = performance.now();
      
      const result = await newsService.getNewsForSymbols(['AAPL']);
      
      const processingTime = performance.now() - startTime;

      expect(processingTime).toBeLessThan(1000); // Should process within 1 second
      expect(result.articles).toHaveLength(1000);
    });

    it('should batch multiple symbol requests efficiently', async () => {
      mockAxios.get.mockResolvedValue(mockAlpacaResponse);
      cacheService.get.mockReturnValue(null);

      const symbols = Array.from({ length: 50 }, (_, i) => `STOCK${i}`);
      
      const startTime = performance.now();
      
      await newsService.getNewsForSymbols(symbols);
      
      const processingTime = performance.now() - startTime;

      expect(processingTime).toBeLessThan(500);
      expect(mockAxios.get).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          params: expect.objectContaining({
            symbols: symbols.join(',')
          })
        })
      );
    });
  });

  describe('Error Handling and Resilience', () => {
    it('should handle network timeouts', async () => {
      mockAxios.get.mockRejectedValue(new Error('Network timeout'));
      cacheService.get.mockReturnValue(null);

      const result = await newsService.getNewsForSymbols(['AAPL']);

      expect(result.error).toContain('Network timeout');
      expect(result.articles).toEqual([]);
      expect(result.total).toBe(0);
    });

    it('should handle malformed API responses', async () => {
      mockAxios.get.mockResolvedValue({ data: 'invalid response format' });
      cacheService.get.mockReturnValue(null);

      const result = await newsService.getNewsForSymbols(['AAPL']);

      expect(result.articles).toEqual([]);
      expect(result.error).toBeDefined();
    });

    it('should validate API keys before requests', async () => {
      // Remove API key
      newsService.sources.alpaca.apiKey = null;

      const result = await newsService.getNewsForSymbols(['AAPL']);

      expect(mockAxios.get).not.toHaveBeenCalled();
      expect(result.error).toContain('API key not configured');
    });

    it('should handle empty symbol arrays', async () => {
      const result = await newsService.getNewsForSymbols([]);

      expect(mockAxios.get).not.toHaveBeenCalled();
      expect(result.articles).toEqual([]);
      expect(result.total).toBe(0);
    });

    it('should sanitize user input', async () => {
      mockAxios.get.mockResolvedValue(mockAlpacaResponse);
      
      // Test with potentially problematic symbols
      const problematicSymbols = ['AAPL; DROP TABLE', 'GOOGL<script>', 'MSFT"injection'];
      
      await newsService.getNewsForSymbols(problematicSymbols);

      expect(mockAxios.get).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          params: expect.objectContaining({
            symbols: expect.stringMatching(/^[A-Z,]+$/) // Should be sanitized
          })
        })
      );
    });
  });
});