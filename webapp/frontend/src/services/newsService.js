// News Service - Integrates multiple news sources for financial news
// Supports real-time news updates, sentiment analysis, and filtering

import axios from 'axios';
import cacheService, { CacheConfigs } from './cacheService';

class NewsService {
  constructor() {
    this.sources = {
      alpaca: {
        enabled: true,
        name: 'Alpaca News',
        apiKey: process.env.REACT_APP_ALPACA_API_KEY,
        baseUrl: 'https://data.alpaca.markets/v1beta1/news'
      }
    };
    
    this.categories = [
      'general',
      'earnings',
      'mergers',
      'analyst',
      'economic',
      'crypto',
      'technology',
      'healthcare',
      'energy'
    ];
    
    this.sentimentKeywords = {
      positive: ['surge', 'rally', 'gain', 'profit', 'growth', 'beat', 'upgrade', 'bullish', 'record', 'breakthrough'],
      negative: ['fall', 'drop', 'loss', 'decline', 'bear', 'downgrade', 'crash', 'plunge', 'warning', 'concern'],
      neutral: ['stable', 'unchanged', 'steady', 'maintain', 'hold', 'flat', 'sideways']
    };
  }

  // Get news for specific symbols
  async getNewsForSymbols(symbols, options = {}) {
    const {
      limit = 50,
      timeframe = '24h'
    } = options;

    const cacheKey = cacheService.generateKey('news_symbols', { 
      symbols: Array.isArray(symbols) ? symbols.join(',') : symbols,
      limit,
      timeframe
    });

    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        // Try backend API first
        const params = {
          limit,
          timeframe,
          ...(symbols && symbols.length > 0 && { symbol: Array.isArray(symbols) ? symbols[0] : symbols })
        };
        
        const backendResult = await this.getApiNews('/api/news/articles', params);
        
        // If backend returns articles array, use it
        if (Array.isArray(backendResult)) {
          return backendResult;
        }
        
        // If backend returns structured response with articles
        if (backendResult?.articles && Array.isArray(backendResult.articles)) {
          return backendResult.articles;
        }
        
        // Return the full response structure for NewsWidget to handle
        return backendResult;
      },
      CacheConfigs.NEWS.ttl,
      CacheConfigs.NEWS.persist
    );
  }

  // Fetch news from Alpaca
  async fetchAlpacaNews(symbols, options) {
    const params = new URLSearchParams();
    
    if (Array.isArray(symbols)) {
      params.append('symbols', symbols.join(','));
    } else if (symbols) {
      params.append('symbols', symbols);
    }
    
    if (options.limit) params.append('limit', options.limit);
    if (options.start) params.append('start', options.start);
    if (options.end) params.append('end', options.end);
    if (options.sort) params.append('sort', options.sort);
    if (options.includeContent) params.append('include_content', 'true');
    if (options.excludeContentless) params.append('exclude_contentless', 'true');

    const response = await axios.get(`${this.sources.alpaca.baseUrl}?${params}`, {
      headers: {
        'APCA-API-KEY-ID': this.sources.alpaca.apiKey,
        'APCA-API-SECRET-KEY': process.env.REACT_APP_ALPACA_API_SECRET
      }
    });

    return response.data.news.map(article => ({
      id: article.id,
      headline: article.headline,
      summary: article.summary,
      content: article.content,
      symbols: article.symbols,
      url: article.url,
      author: article.author,
      createdAt: article.created_at,
      updatedAt: article.updated_at,
      source: 'alpaca',
      images: article.images || []
    }));
  }

  // Get market-wide news
  async getMarketNews(options = {}) {
    const cacheKey = cacheService.generateKey('news_market', options);
    
    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        // Try backend API for general market news
        const params = {
          limit: options.limit || 50,
          timeframe: options.timeframe || '24h'
        };
        
        return this.getApiNews('/api/news/articles', params);
      },
      CacheConfigs.NEWS.ttl
    );
  }

  // Get news by category
  async getNewsByCategory(category, options = {}) {
    const cacheKey = cacheService.generateKey('news_category', { category, ...options });
    
    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        // Try backend API with category filter
        const params = {
          category,
          limit: options.limit || 50,
          timeframe: options.timeframe || '24h'
        };
        
        return this.getApiNews('/api/news/articles', params);
      },
      CacheConfigs.NEWS.ttl
    );
  }

  // Analyze sentiment of news article
  analyzeSentiment(article) {
    const text = `${article.headline} ${article.summary}`.toLowerCase();
    
    let positiveScore = 0;
    let negativeScore = 0;
    
    // Count sentiment keywords
    this.sentimentKeywords.positive.forEach(word => {
      if (text.includes(word)) positiveScore++;
    });
    
    this.sentimentKeywords.negative.forEach(word => {
      if (text.includes(word)) negativeScore++;
    });
    
    // Calculate sentiment
    if (positiveScore > negativeScore) {
      return {
        score: positiveScore / (positiveScore + negativeScore),
        label: 'positive',
        confidence: (positiveScore - negativeScore) / (positiveScore + negativeScore + 1)
      };
    } else if (negativeScore > positiveScore) {
      return {
        score: -negativeScore / (positiveScore + negativeScore),
        label: 'negative',
        confidence: (negativeScore - positiveScore) / (positiveScore + negativeScore + 1)
      };
    } else {
      return {
        score: 0,
        label: 'neutral',
        confidence: 0.5
      };
    }
  }

  // Calculate relevance score for symbols
  calculateRelevance(article, symbols) {
    if (!symbols || symbols.length === 0) return 1;
    
    const symbolArray = Array.isArray(symbols) ? symbols : [symbols];
    const text = `${article.headline} ${article.summary} ${article.content || ''}`.toLowerCase();
    
    let relevanceScore = 0;
    let maxPossibleScore = symbolArray.length * 3; // headline=2, summary=1
    
    symbolArray.forEach(symbol => {
      const sym = symbol.toLowerCase();
      // Higher weight for headline mentions
      if (article.headline.toLowerCase().includes(sym)) relevanceScore += 2;
      // Medium weight for summary mentions
      if (article.summary.toLowerCase().includes(sym)) relevanceScore += 1;
      // Check if symbol is in the article's symbol list
      if (article.symbols && article.symbols.includes(symbol.toUpperCase())) relevanceScore += 3;
    });
    
    return Math.min(relevanceScore / maxPossibleScore, 1);
  }

  // Deduplicate news articles
  deduplicateNews(articles) {
    const seen = new Map();
    
    return articles.filter(article => {
      // Create a unique key based on headline similarity
      const key = this.createArticleKey(article);
      
      if (seen.has(key)) {
        // Keep the one with more content
        const existing = seen.get(key);
        if ((article.content?.length || 0) > (existing.content?.length || 0)) {
          seen.set(key, article);
          return true;
        }
        return false;
      }
      
      seen.set(key, article);
      return true;
    });
  }

  // Create a unique key for article deduplication
  createArticleKey(article) {
    // Simple approach: use first 50 chars of headline
    return article.headline.toLowerCase().substring(0, 50).replace(/[^a-z0-9]/g, '');
  }

  // Sort news articles
  sortNews(articles, sort = 'desc') {
    return articles.sort((a, b) => {
      const dateA = new Date(a.createdAt || a.publishedAt);
      const dateB = new Date(b.createdAt || b.publishedAt);
      
      if (sort === 'desc') {
        return dateB - dateA;
      } else {
        return dateA - dateB;
      }
    });
  }

  // Search news
  async searchNews(query, options = {}) {
    const cacheKey = cacheService.generateKey('news_search', { query, ...options });
    
    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        // For now, implement basic search through cached news
        const allNews = await this.getMarketNews({ limit: 200 });
        
        const searchTerms = query.toLowerCase().split(' ');
        const filtered = allNews.filter(article => {
          const text = `${article.headline} ${article.summary}`.toLowerCase();
          return searchTerms.every(term => text.includes(term));
        });
        
        return filtered.slice(0, options.limit || 50);
      },
      CacheConfigs.NEWS.ttl
    );
  }

  // Get trending news topics
  async getTrendingTopics(limit = 10) {
    const cacheKey = cacheService.generateKey('news_trending', { limit });
    
    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        const recentNews = await this.getMarketNews({ limit: 100 });
        
        // Extract keywords and count frequency
        const keywordCounts = new Map();
        
        recentNews.forEach(article => {
          const words = `${article.headline} ${article.summary}`
            .toLowerCase()
            .split(/\s+/)
            .filter(word => word.length > 4 && !this.isCommonWord(word));
          
          words.forEach(word => {
            keywordCounts.set(word, (keywordCounts.get(word) || 0) + 1);
          });
        });
        
        // Sort by frequency and return top keywords
        const sorted = Array.from(keywordCounts.entries())
          .sort((a, b) => b[1] - a[1])
          .slice(0, limit)
          .map(([keyword, count]) => ({ keyword, count }));
        
        return sorted;
      },
      300000 // 5 minutes
    );
  }

  // Check if word is common (to filter out)
  isCommonWord(word) {
    const common = ['stock', 'market', 'share', 'price', 'today', 'report', 'announces', 'company'];
    return common.includes(word);
  }

  // Fetch news from backend API
  async getApiNews(endpoint = '/api/news/articles', params = {}) {
    try {
      const queryParams = new URLSearchParams(params);
      const response = await axios.get(`${endpoint}?${queryParams}`);
      
      if (response.data?.success) {
        // Handle both array format (legacy) and object format (new)
        if (Array.isArray(response.data.data)) {
          return response.data.data;
        } else if (response.data.data?.articles) {
          return response.data.data;
        } else {
          // Return empty format that matches expected structure
          return {
            articles: [],
            total: 0,
            message: response.data.data?.message || 'No news available',
            available_when_configured: response.data.data?.available_when_configured || [],
            data_sources: response.data.data?.data_sources || {}
          };
        }
      }
      
      return { articles: [], total: 0, message: 'News service unavailable' };
    } catch (error) {
      console.warn('Backend news API unavailable, using Alpaca fallback:', error.message);
      
      // Fallback to direct Alpaca API if backend is not available
      return this.getMockNews([], 5);
    }
  }

  // Mock news data for development fallback
  getMockNews(symbols = [], limit = 10) {
    const mockArticles = [
      {
        id: '1',
        headline: 'News API Configuration Required',
        summary: 'Connect your news data feeds to see real-time financial news with sentiment analysis.',
        symbols: symbols.length > 0 ? symbols.slice(0, 2) : ['SPY', 'QQQ'],
        createdAt: new Date().toISOString(),
        source: 'system',
        sentiment: { score: 0, label: 'neutral', confidence: 0.5 }
      },
      {
        id: '2', 
        headline: 'Professional News Feeds Available',
        summary: 'Enable comprehensive market news with source tracking, sentiment analysis, and impact scoring.',
        symbols: symbols.length > 0 ? symbols.slice(0, 2) : ['AAPL', 'MSFT'],
        createdAt: new Date(Date.now() - 3600000).toISOString(),
        source: 'system',
        sentiment: { score: 0, label: 'neutral', confidence: 0.5 }
      }
    ];
    
    return mockArticles.slice(0, limit);
  }
}

// Create singleton instance
const newsService = new NewsService();

export default newsService;