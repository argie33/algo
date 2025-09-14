/**
 * Real-Time News Sentiment Service
 * Handles live news and sentiment data streams
 */

import realTimeDataService from './realTimeDataService.js';
import api from './api.js';

class RealTimeNewsService {
  constructor() {
    this.newsSubscribers = new Map();
    this.sentimentSubscribers = new Map();
    this.latestNews = [];
    this.latestSentiment = {};
    this.isProcessingNews = false;
    this.newsBuffer = [];
    this.bufferProcessInterval = null;
  }

  initialize() {
    // Subscribe to news updates via WebSocket
    realTimeDataService.subscribe('news_updates', this.handleNewsUpdate.bind(this));
    realTimeDataService.subscribe('sentiment_updates', this.handleSentimentUpdate.bind(this));
    realTimeDataService.subscribe('breaking_news', this.handleBreakingNews.bind(this));
    
    // Start buffer processing
    this.startBufferProcessing();
    
    if (import.meta.env.DEV) {
      console.log('📰 RealTimeNewsService: Initialized');
    }
  }

  // News subscriptions
  subscribeToNews(callback) {
    const id = Symbol('newsSubscriber');
    this.newsSubscribers.set(id, callback);
    
    // Send latest news to new subscriber
    if (this.latestNews.length > 0) {
      callback(this.latestNews);
    }
    
    return id;
  }

  unsubscribeFromNews(id) {
    return this.newsSubscribers.delete(id);
  }

  // Sentiment subscriptions
  subscribeToSentiment(symbol, callback) {
    if (!this.sentimentSubscribers.has(symbol)) {
      this.sentimentSubscribers.set(symbol, new Map());
    }
    
    const id = Symbol('sentimentSubscriber');
    this.sentimentSubscribers.get(symbol).set(id, callback);
    
    // Send latest sentiment to new subscriber
    if (this.latestSentiment[symbol]) {
      callback(this.latestSentiment[symbol]);
    }
    
    return id;
  }

  unsubscribeFromSentiment(symbol, id) {
    if (this.sentimentSubscribers.has(symbol)) {
      const result = this.sentimentSubscribers.get(symbol).delete(id);
      if (this.sentimentSubscribers.get(symbol).size === 0) {
        this.sentimentSubscribers.delete(symbol);
      }
      return result;
    }
    return false;
  }

  // Handle incoming news updates
  handleNewsUpdate(newsData) {
    try {
      if (!newsData || !Array.isArray(newsData.articles)) {
        return;
      }

      // Process each article
      const processedArticles = newsData.articles.map(article => ({
        id: article.id || `news_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        title: article.title || article.headline,
        summary: article.summary || article.description,
        source: article.source,
        publishedAt: article.publishedAt || article.published_at,
        url: article.url,
        symbols: article.symbols || [],
        sentiment: article.sentiment || this.analyzeSentiment(article),
        impact: article.impact || this.calculateImpact(article),
        isRealTime: true,
        timestamp: Date.now()
      }));

      // Add to buffer for processing
      this.newsBuffer.push(...processedArticles);

      if (import.meta.env.DEV) {
        console.log(`📰 RealTimeNewsService: Received ${processedArticles.length} news articles`);
      }

    } catch (error) {
      console.error('❌ RealTimeNewsService: Error handling news update:', error);
    }
  }

  // Handle sentiment updates
  handleSentimentUpdate(sentimentData) {
    try {
      if (!sentimentData || !sentimentData.symbol) {
        return;
      }

      const { symbol, sentiment, timestamp } = sentimentData;
      
      // Store latest sentiment
      this.latestSentiment[symbol] = {
        symbol,
        score: sentiment.score,
        label: sentiment.label,
        confidence: sentiment.confidence,
        trend: sentiment.trend,
        sources: sentiment.sources || [],
        newsImpact: sentiment.newsImpact || [],
        timestamp: timestamp || Date.now(),
        isRealTime: true
      };

      // Notify sentiment subscribers
      if (this.sentimentSubscribers.has(symbol)) {
        this.sentimentSubscribers.get(symbol).forEach(callback => {
          try {
            callback(this.latestSentiment[symbol]);
          } catch (error) {
            console.error('❌ RealTimeNewsService: Error in sentiment callback:', error);
          }
        });
      }

      if (import.meta.env.DEV) {
        console.log(`📊 RealTimeNewsService: Updated sentiment for ${symbol}:`, sentiment);
      }

    } catch (error) {
      console.error('❌ RealTimeNewsService: Error handling sentiment update:', error);
    }
  }

  // Handle breaking news alerts
  handleBreakingNews(breakingNewsData) {
    try {
      if (!breakingNewsData || !breakingNewsData.article) {
        return;
      }

      const article = {
        ...breakingNewsData.article,
        isBreaking: true,
        priority: 'high',
        timestamp: Date.now()
      };

      // Immediately notify all news subscribers of breaking news
      this.notifyNewsSubscribers([article]);

      if (import.meta.env.DEV) {
        console.log('🚨 RealTimeNewsService: Breaking news received:', article.title);
      }

    } catch (error) {
      console.error('❌ RealTimeNewsService: Error handling breaking news:', error);
    }
  }

  // Process news buffer periodically
  startBufferProcessing() {
    this.bufferProcessInterval = setInterval(() => {
      if (this.newsBuffer.length > 0 && !this.isProcessingNews) {
        this.processNewsBuffer();
      }
    }, 2000); // Process every 2 seconds
  }

  stopBufferProcessing() {
    if (this.bufferProcessInterval) {
      clearInterval(this.bufferProcessInterval);
      this.bufferProcessInterval = null;
    }
  }

  async processNewsBuffer() {
    if (this.isProcessingNews || this.newsBuffer.length === 0) {
      return;
    }

    this.isProcessingNews = true;
    
    try {
      // Get articles to process
      const articlesToProcess = this.newsBuffer.splice(0, 10); // Process up to 10 at a time
      
      // Enhance articles with sentiment analysis
      const enhancedArticles = await Promise.all(
        articlesToProcess.map(async (article) => {
          try {
            // Analyze sentiment if not already provided
            if (!article.sentiment || typeof article.sentiment !== 'object') {
              article.sentiment = await this.analyzeSentiment(article);
            }
            
            // Calculate impact score
            article.impact = this.calculateImpact(article);
            
            return article;
          } catch (error) {
            console.error('❌ RealTimeNewsService: Error processing article:', error);
            return article; // Return original article if processing fails
          }
        })
      );

      // Update latest news (keep last 100 articles)
      this.latestNews = [...enhancedArticles, ...this.latestNews].slice(0, 100);

      // Notify subscribers
      this.notifyNewsSubscribers(enhancedArticles);

      // Update symbol sentiment aggregates
      this.updateSymbolSentiments(enhancedArticles);

    } catch (error) {
      console.error('❌ RealTimeNewsService: Error processing news buffer:', error);
    } finally {
      this.isProcessingNews = false;
    }
  }

  // Notify all news subscribers
  notifyNewsSubscribers(articles) {
    this.newsSubscribers.forEach(callback => {
      try {
        callback(articles);
      } catch (error) {
        console.error('❌ RealTimeNewsService: Error in news callback:', error);
      }
    });
  }

  // Update sentiment for symbols mentioned in news
  updateSymbolSentiments(articles) {
    const symbolSentiments = {};

    // Aggregate sentiment by symbol
    articles.forEach(article => {
      if (article.symbols && article.symbols.length > 0) {
        article.symbols.forEach(symbol => {
          if (!symbolSentiments[symbol]) {
            symbolSentiments[symbol] = {
              articles: [],
              totalScore: 0,
              count: 0
            };
          }

          symbolSentiments[symbol].articles.push(article);
          symbolSentiments[symbol].totalScore += article.sentiment.score || 0;
          symbolSentiments[symbol].count++;
        });
      }
    });

    // Calculate and update aggregate sentiment for each symbol
    Object.entries(symbolSentiments).forEach(([symbol, data]) => {
      const avgScore = data.totalScore / data.count;
      const sentiment = {
        symbol,
        score: avgScore,
        label: this.scoreToLabel(avgScore),
        confidence: Math.min(1, data.count / 5), // Higher confidence with more articles
        articles: data.articles,
        timestamp: Date.now(),
        isRealTime: true
      };

      // Update stored sentiment
      this.latestSentiment[symbol] = sentiment;

      // Notify subscribers
      if (this.sentimentSubscribers.has(symbol)) {
        this.sentimentSubscribers.get(symbol).forEach(callback => {
          try {
            callback(sentiment);
          } catch (error) {
            console.error('❌ RealTimeNewsService: Error in sentiment callback:', error);
          }
        });
      }
    });
  }

  // Analyze sentiment for an article
  analyzeSentiment(article) {
    try {
      const text = `${article.title || ''} ${article.summary || ''}`;
      
      // Simple keyword-based sentiment analysis
      const positiveWords = ['bullish', 'gain', 'profit', 'growth', 'strong', 'beat', 'exceed', 'buy', 'upgrade'];
      const negativeWords = ['bearish', 'loss', 'decline', 'weak', 'miss', 'below', 'sell', 'downgrade', 'cut'];
      
      const words = text.toLowerCase().split(/\s+/);
      let positiveCount = 0;
      let negativeCount = 0;
      
      words.forEach(word => {
        if (positiveWords.some(pw => word.includes(pw))) positiveCount++;
        if (negativeWords.some(nw => word.includes(nw))) negativeCount++;
      });
      
      const totalSentimentWords = positiveCount + negativeCount;
      let score = 0.5; // neutral
      
      if (totalSentimentWords > 0) {
        score = positiveCount / totalSentimentWords;
      }
      
      return {
        score: Math.round(score * 100) / 100,
        label: this.scoreToLabel(score),
        confidence: Math.min(0.8, totalSentimentWords / words.length * 5),
        positiveWords: positiveCount,
        negativeWords: negativeCount,
        wordCount: words.length
      };
    } catch (error) {
      console.error('❌ RealTimeNewsService: Sentiment analysis error:', error);
      return {
        score: 0.5,
        label: 'neutral',
        confidence: 0
      };
    }
  }

  // Calculate article impact score
  calculateImpact(article) {
    let score = 0.5;
    
    // Source credibility
    const highCredibilitySources = ['reuters', 'bloomberg', 'wsj', 'cnbc', 'marketwatch'];
    if (article.source && highCredibilitySources.some(src => 
      article.source.toLowerCase().includes(src))) {
      score += 0.2;
    }
    
    // Recency
    if (article.publishedAt) {
      const hoursAgo = (Date.now() - new Date(article.publishedAt).getTime()) / (1000 * 60 * 60);
      if (hoursAgo < 1) score += 0.2;
      else if (hoursAgo < 6) score += 0.1;
    }
    
    // Content length
    if (article.summary && article.summary.length > 200) {
      score += 0.1;
    }
    
    return {
      score: Math.min(1, score),
      level: score >= 0.8 ? 'high' : score >= 0.6 ? 'medium' : 'low'
    };
  }

  // Convert sentiment score to label
  scoreToLabel(score) {
    if (score >= 0.6) return 'positive';
    if (score <= 0.4) return 'negative';
    return 'neutral';
  }

  // Get latest news
  getLatestNews(limit = 20) {
    return this.latestNews.slice(0, limit);
  }

  // Get sentiment for symbol
  getLatestSentiment(symbol) {
    return this.latestSentiment[symbol] || null;
  }

  // Get all latest sentiments
  getAllLatestSentiments() {
    return { ...this.latestSentiment };
  }

  // Fetch news sentiment analysis from API
  async fetchNewsSentiment(symbol, timeframe = '24h') {
    try {
      const response = await api.get(`/api/news/sentiment/${symbol}?timeframe=${timeframe}`);
      return response.data;
    } catch (error) {
      console.error(`❌ RealTimeNewsService: Failed to fetch sentiment for ${symbol}:`, error);
      throw error;
    }
  }

  // Fetch breaking news
  async fetchBreakingNews() {
    try {
      const response = await api.get('/api/news/breaking');
      return response.data;
    } catch (error) {
      console.error('❌ RealTimeNewsService: Failed to fetch breaking news:', error);
      throw error;
    }
  }

  // Cleanup
  destroy() {
    this.stopBufferProcessing();
    this.newsSubscribers.clear();
    this.sentimentSubscribers.clear();
    this.latestNews = [];
    this.latestSentiment = {};
    this.newsBuffer = [];
    
    if (import.meta.env.DEV) {
      console.log('📰 RealTimeNewsService: Destroyed');
    }
  }
}

// Create singleton instance
const realTimeNewsService = new RealTimeNewsService();

// Initialize on import
realTimeNewsService.initialize();

export default realTimeNewsService;