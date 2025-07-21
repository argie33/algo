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
      start = null,
      end = null,
      sort = 'desc',
      includeContent = false,
      excludeContentless = true
    } = options;

    const cacheKey = cacheService.generateKey('news_symbols', { 
      symbols: Array.isArray(symbols) ? symbols.join(',') : symbols,
      limit,
      sort 
    });

    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        const allNews = [];
        
        // Alpaca News
        if (this.sources.alpaca.enabled && this.sources.alpaca.apiKey) {
          try {
            const alpacaNews = await this.fetchAlpacaNews(symbols, {
              limit,
              start,
              end,
              sort,
              includeContent,
              excludeContentless
            });
            allNews.push(...alpacaNews);
          } catch (error) {
            console.error('Alpaca news error:', error);
          }
        }

        // Add other news sources here as they become available

        // Sort and deduplicate
        const uniqueNews = this.deduplicateNews(allNews);
        const sortedNews = this.sortNews(uniqueNews, sort);
        
        // Add sentiment analysis
        const analyzedNews = sortedNews.map(article => ({
          ...article,
          sentiment: this.analyzeSentiment(article),
          relevanceScore: this.calculateRelevance(article, symbols)
        }));

        return analyzedNews.slice(0, limit);
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
        // For now, get news for major indices
        const marketSymbols = ['SPY', 'QQQ', 'DIA', 'IWM', 'VIX'];
        return this.getNewsForSymbols(marketSymbols, options);
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
        // Map categories to relevant symbols or keywords
        const categoryMap = {
          technology: ['AAPL', 'MSFT', 'GOOGL', 'META', 'NVDA', 'TSLA'],
          healthcare: ['JNJ', 'UNH', 'PFE', 'ABBV', 'TMO', 'CVS'],
          energy: ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'PXD'],
          finance: ['JPM', 'BAC', 'WFC', 'GS', 'MS', 'C'],
          crypto: ['BTC-USD', 'ETH-USD', 'BNB-USD', 'XRP-USD']
        };

        const symbols = categoryMap[category] || [];
        return this.getNewsForSymbols(symbols, options);
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

  // Mock news data for development
  getMockNews(symbols = [], limit = 10) {
    const mockArticles = [
      {
        id: '1',
        headline: 'Tech Giants Rally on Strong Earnings Reports',
        summary: 'Major technology companies see significant gains following better-than-expected quarterly results.',
        symbols: ['AAPL', 'MSFT', 'GOOGL'],
        createdAt: new Date().toISOString(),
        source: 'mock',
        sentiment: { score: 0.8, label: 'positive', confidence: 0.9 }
      },
      {
        id: '2',
        headline: 'Federal Reserve Signals Potential Rate Pause',
        summary: 'Fed officials suggest they may hold rates steady in upcoming meetings amid cooling inflation.',
        symbols: ['SPY', 'QQQ'],
        createdAt: new Date(Date.now() - 3600000).toISOString(),
        source: 'mock',
        sentiment: { score: 0.3, label: 'positive', confidence: 0.6 }
      },
      {
        id: '3',
        headline: 'Energy Sector Faces Headwinds as Oil Prices Decline',
        summary: 'Oil companies struggle as crude prices fall on increased supply concerns.',
        symbols: ['XOM', 'CVX'],
        createdAt: new Date(Date.now() - 7200000).toISOString(),
        source: 'mock',
        sentiment: { score: -0.6, label: 'negative', confidence: 0.8 }
      }
    ];
    
    // Filter by symbols if provided
    let filtered = mockArticles;
    if (symbols.length > 0) {
      filtered = mockArticles.filter(article => 
        article.symbols.some(sym => symbols.includes(sym))
      );
    }
    
    return filtered.slice(0, limit);
  }
}

// Create singleton instance
const newsService = new NewsService();

export default newsService;