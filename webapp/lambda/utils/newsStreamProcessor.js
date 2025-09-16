/**
 * Real-Time News Stream Processor
 * Handles incoming news data and processes it for sentiment analysis
 */

const newsAnalyzer = require("./newsAnalyzer");
const sentimentEngine = require("./sentimentEngine");
const { query } = require("./database");
const logger = require("./logger");

class NewsStreamProcessor {
  constructor() {
    this.subscribers = new Map();
    this.processingQueue = [];
    this.isProcessing = false;
    this.batchSize = 10;
    this.processingInterval = 2000; // 2 seconds
    this.sentimentCache = new Map();
    this.cacheTimeout = 300000; // 5 minutes

    this.startProcessing();
    this.startCacheCleanup();
  }

  /**
   * Subscribe to processed news updates
   * @param {string} type - Type of updates (news_updates, sentiment_updates, breaking_news)
   * @param {Function} callback - Callback function
   * @returns {symbol} Subscription ID
   */
  subscribe(type, callback) {
    if (!this.subscribers.has(type)) {
      this.subscribers.set(type, new Map());
    }

    const subscriptionId = Symbol("newsStreamSubscription");
    this.subscribers.get(type).set(subscriptionId, callback);

    logger.info(`NewsStreamProcessor: New subscription for ${type}`);
    return subscriptionId;
  }

  /**
   * Unsubscribe from updates
   * @param {string} type - Type of updates
   * @param {symbol} subscriptionId - Subscription ID
   */
  unsubscribe(type, subscriptionId) {
    if (this.subscribers.has(type)) {
      const result = this.subscribers.get(type).delete(subscriptionId);
      if (this.subscribers.get(type).size === 0) {
        this.subscribers.delete(type);
      }
      return result;
    }
    return false;
  }

  /**
   * Emit updates to subscribers
   * @param {string} type - Update type
   * @param {Object} data - Update data
   */
  emit(type, data) {
    if (this.subscribers.has(type)) {
      this.subscribers.get(type).forEach((callback) => {
        try {
          callback(data);
        } catch (error) {
          logger.error(
            `NewsStreamProcessor: Error in ${type} callback:`,
            error
          );
        }
      });
    }
  }

  /**
   * Add news articles to processing queue
   * @param {Array} articles - Array of news articles
   */
  addToQueue(articles) {
    if (!Array.isArray(articles)) {
      articles = [articles];
    }

    const validArticles = articles.filter(
      (article) =>
        article && (article.title || article.headline) && article.source
    );

    this.processingQueue.push(...validArticles);

    logger.info(
      `NewsStreamProcessor: Added ${validArticles.length} articles to processing queue`
    );
  }

  /**
   * Start the processing loop
   */
  startProcessing() {
    this.processingLoop = setInterval(() => {
      if (this.processingQueue.length > 0 && !this.isProcessing) {
        this.processBatch();
      }
    }, this.processingInterval);
  }

  /**
   * Stop the processing loop
   */
  stopProcessing() {
    if (this.processingLoop) {
      clearInterval(this.processingLoop);
      this.processingLoop = null;
    }
  }

  /**
   * Process a batch of articles
   */
  async processBatch() {
    if (this.isProcessing) return;

    this.isProcessing = true;

    try {
      const batch = this.processingQueue.splice(0, this.batchSize);
      if (batch.length === 0) {
        this.isProcessing = false;
        return;
      }

      logger.info(
        `NewsStreamProcessor: Processing batch of ${batch.length} articles`
      );

      // Process articles in parallel
      const processedArticles = await Promise.all(
        batch.map((article) => this.processArticle(article))
      );

      // Filter successful processing results
      const validResults = processedArticles.filter(
        (result) => result !== null
      );

      if (validResults.length > 0) {
        // Save to database
        await this.saveToDatabase(validResults);

        // Emit to subscribers
        this.emit("news_updates", {
          articles: validResults,
          timestamp: Date.now(),
        });

        // Process sentiment aggregates
        await this.processSentimentAggregates(validResults);
      }
    } catch (error) {
      logger.error("NewsStreamProcessor: Error processing batch:", error);
    } finally {
      this.isProcessing = false;
    }
  }

  /**
   * Process individual article
   * @param {Object} article - Raw article data
   * @returns {Object|null} Processed article or null if processing failed
   */
  async processArticle(article) {
    try {
      // Normalize article structure
      const normalizedArticle = {
        id:
          article.id ||
          `news_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        title: article.title || article.headline,
        summary: article.summary || article.description || "",
        content:
          article.content || article.summary || article.description || "",
        source: article.source,
        author: article.author || null,
        published_at: new Date(
          article.publishedAt || article.published_at || Date.now()
        ),
        url: article.url || null,
        symbols: this.extractSymbols(article),
        category: article.category || "general",
        created_at: new Date(),
      };

      // Analyze sentiment
      const sentimentAnalysis = await sentimentEngine.analyzeSentiment(
        normalizedArticle.title + " " + normalizedArticle.summary,
        normalizedArticle.symbols[0] // Primary symbol for context
      );

      // Calculate impact and relevance
      const impactAnalysis = newsAnalyzer.calculateImpact(normalizedArticle);
      const reliabilityScore = newsAnalyzer.calculateReliabilityScore(
        normalizedArticle.source
      );

      // Enhance article with analysis
      const enhancedArticle = {
        ...normalizedArticle,
        sentiment: sentimentAnalysis.label || "neutral",
        sentiment_score: sentimentAnalysis.score || 0.5,
        sentiment_confidence: sentimentAnalysis.confidence || 0,
        impact_score: impactAnalysis.score || 0.5,
        relevance_score: reliabilityScore || 0.5,
        keywords: this.extractKeywords(normalizedArticle),
        is_breaking: this.isBreakingNews(normalizedArticle),
        processing_timestamp: new Date(),
      };

      // Check for breaking news
      if (enhancedArticle.is_breaking) {
        this.emit("breaking_news", {
          article: enhancedArticle,
          timestamp: Date.now(),
        });
      }

      return enhancedArticle;
    } catch (error) {
      logger.error("NewsStreamProcessor: Error processing article:", error);
      return null;
    }
  }

  /**
   * Extract stock symbols from article
   * @param {Object} article - Article data
   * @returns {Array} Array of symbols
   */
  extractSymbols(article) {
    const symbols = [];

    // Check if symbols are explicitly provided
    if (article.symbols && Array.isArray(article.symbols)) {
      symbols.push(...article.symbols);
    }

    // Extract from title and content
    const text = `${article.title || article.headline || ""} ${article.summary || article.description || ""}`;
    const symbolPattern = /\b([A-Z]{1,5})\b/g;
    const matches = text.match(symbolPattern) || [];

    // Filter common words that might match the pattern
    const commonWords = new Set([
      "THE",
      "AND",
      "FOR",
      "ARE",
      "BUT",
      "NOT",
      "YOU",
      "ALL",
      "CAN",
      "HER",
      "WAS",
      "ONE",
      "OUR",
      "HAD",
      "BY",
      "WORD",
      "BUT",
      "WHAT",
      "SOME",
      "WE",
      "IS",
      "IT",
      "SAID",
      "EACH",
      "WHICH",
      "SHE",
      "DO",
      "HOW",
      "THEIR",
      "IF",
      "WILL",
      "UP",
      "OTHER",
      "ABOUT",
      "OUT",
      "MANY",
      "THEN",
      "THEM",
      "THESE",
      "SO",
      "SOME",
      "HER",
      "WOULD",
      "MAKE",
      "LIKE",
      "INTO",
      "HIM",
      "HAS",
      "TWO",
      "MORE",
      "GO",
      "NO",
      "WAY",
      "COULD",
      "MY",
      "THAN",
      "FIRST",
      "BEEN",
      "CALL",
      "WHO",
      "OIL",
      "ITS",
      "NOW",
      "FIND",
      "LONG",
      "DOWN",
      "DAY",
      "DID",
      "GET",
      "COME",
      "MADE",
      "MAY",
      "NEW",
    ]);

    matches.forEach((symbol) => {
      if (!commonWords.has(symbol) && !symbols.includes(symbol)) {
        symbols.push(symbol);
      }
    });

    return symbols.slice(0, 5); // Limit to 5 symbols
  }

  /**
   * Extract keywords from article
   * @param {Object} article - Article data
   * @returns {Array} Array of keywords
   */
  extractKeywords(article) {
    const text = `${article.title} ${article.summary}`.toLowerCase();
    const words = text.split(/\s+/);

    const stopWords = new Set([
      "the",
      "and",
      "or",
      "but",
      "in",
      "on",
      "at",
      "to",
      "for",
      "of",
      "with",
      "by",
      "is",
      "are",
      "was",
      "were",
      "been",
      "be",
      "have",
      "has",
      "had",
      "will",
      "would",
      "could",
      "should",
      "may",
      "might",
      "can",
      "must",
      "shall",
      "a",
      "an",
      "this",
      "that",
      "these",
      "those",
    ]);

    const keywords = words
      .filter((word) => word.length > 3 && !stopWords.has(word))
      .filter((word, index, arr) => arr.indexOf(word) === index) // Remove duplicates
      .slice(0, 10); // Limit to 10 keywords

    return keywords;
  }

  /**
   * Check if article is breaking news
   * @param {Object} article - Article data
   * @returns {boolean}
   */
  isBreakingNews(article) {
    const breakingKeywords = [
      "breaking",
      "urgent",
      "alert",
      "just in",
      "developing",
    ];
    const text = `${article.title} ${article.summary}`.toLowerCase();

    // Check for breaking keywords
    const hasBreakingKeywords = breakingKeywords.some((keyword) =>
      text.includes(keyword)
    );

    // Check recency (within last hour)
    const publishTime = new Date(article.published_at);
    const hourAgo = new Date(Date.now() - 60 * 60 * 1000);
    const isRecent = publishTime > hourAgo;

    // Check for high impact indicators
    const highImpactKeywords = [
      "earnings",
      "merger",
      "acquisition",
      "ceo",
      "bankruptcy",
      "lawsuit",
    ];
    const hasHighImpact = highImpactKeywords.some((keyword) =>
      text.includes(keyword)
    );

    return hasBreakingKeywords || (isRecent && hasHighImpact);
  }

  /**
   * Save processed articles to database
   * @param {Array} articles - Processed articles
   */
  async saveToDatabase(articles) {
    try {
      for (const article of articles) {
        // Check if article already exists
        const existingResult = await query(
          "SELECT id FROM news WHERE url = $1 OR (title = $2 AND source = $3)",
          [article.url, article.title, article.source]
        );

        if (existingResult.rows.length === 0) {
          // Insert new article
          await query(
            `
            INSERT INTO news (
              id, title, summary, content, source, author, published_at, url,
              symbols, category, sentiment, sentiment_score, sentiment_confidence,
              impact_score, relevance_score, keywords, is_breaking, created_at
            ) VALUES (
              $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18
            )
          `,
            [
              article.id,
              article.title,
              article.summary,
              article.content,
              article.source,
              article.author,
              article.published_at,
              article.url,
              article.symbols,
              article.category,
              article.sentiment,
              article.sentiment_score,
              article.sentiment_confidence,
              article.impact_score,
              article.relevance_score,
              article.keywords,
              article.is_breaking,
              article.created_at,
            ]
          );

          logger.info(
            `NewsStreamProcessor: Saved article ${article.id} to database`
          );
        }
      }
    } catch (error) {
      logger.error("NewsStreamProcessor: Error saving to database:", error);
    }
  }

  /**
   * Process sentiment aggregates for symbols
   * @param {Array} articles - Processed articles
   */
  async processSentimentAggregates(articles) {
    const symbolSentiments = {};

    // Group by symbols
    articles.forEach((article) => {
      if (article.symbols && article.symbols.length > 0) {
        article.symbols.forEach((symbol) => {
          if (!symbolSentiments[symbol]) {
            symbolSentiments[symbol] = {
              articles: [],
              totalScore: 0,
              count: 0,
            };
          }

          symbolSentiments[symbol].articles.push(article);
          symbolSentiments[symbol].totalScore += article.sentiment_score;
          symbolSentiments[symbol].count++;
        });
      }
    });

    // Calculate aggregates and emit updates
    for (const [symbol, data] of Object.entries(symbolSentiments)) {
      const avgScore = data.totalScore / data.count;
      const confidence = Math.min(1, data.count / 5);

      const sentimentData = {
        symbol,
        sentiment: {
          score: avgScore,
          label:
            avgScore >= 0.6
              ? "positive"
              : avgScore <= 0.4
                ? "negative"
                : "neutral",
          confidence,
          trend: this.calculateTrend(symbol, avgScore),
          sources: data.articles.map((a) => ({
            source: a.source,
            score: a.sentiment_score,
          })),
          newsImpact: data.articles.slice(0, 5),
        },
        timestamp: Date.now(),
      };

      // Cache sentiment
      this.sentimentCache.set(symbol, {
        data: sentimentData,
        timestamp: Date.now(),
      });

      // Emit sentiment update
      this.emit("sentiment_updates", sentimentData);
    }
  }

  /**
   * Calculate sentiment trend for symbol
   * @param {string} symbol - Stock symbol
   * @param {number} currentScore - Current sentiment score
   * @returns {string} Trend direction
   */
  calculateTrend(symbol, currentScore) {
    const cached = this.sentimentCache.get(symbol);
    if (!cached || !cached.data) return "flat";

    const previousScore = cached.data.sentiment.score;
    const difference = currentScore - previousScore;

    if (Math.abs(difference) < 0.05) return "flat";
    return difference > 0 ? "improving" : "declining";
  }

  /**
   * Start cache cleanup process
   */
  startCacheCleanup() {
    this.cacheCleanupInterval = setInterval(() => {
      const now = Date.now();
      for (const [key, value] of this.sentimentCache.entries()) {
        if (now - value.timestamp > this.cacheTimeout) {
          this.sentimentCache.delete(key);
        }
      }
    }, 60000); // Clean every minute
  }

  /**
   * Stop cache cleanup process
   */
  stopCacheCleanup() {
    if (this.cacheCleanupInterval) {
      clearInterval(this.cacheCleanupInterval);
      this.cacheCleanupInterval = null;
    }
  }

  /**
   * Get cached sentiment for symbol
   * @param {string} symbol - Stock symbol
   * @returns {Object|null} Cached sentiment data
   */
  getCachedSentiment(symbol) {
    const cached = this.sentimentCache.get(symbol);
    return cached ? cached.data : null;
  }

  /**
   * Get processing statistics
   * @returns {Object} Processing stats
   */
  getStats() {
    return {
      queueSize: this.processingQueue.length,
      isProcessing: this.isProcessing,
      cacheSize: this.sentimentCache.size,
      subscriberTypes: Array.from(this.subscribers.keys()),
      totalSubscribers: Array.from(this.subscribers.values()).reduce(
        (total, map) => total + map.size,
        0
      ),
    };
  }

  /**
   * Clean up and destroy processor
   */
  destroy() {
    this.stopProcessing();
    this.stopCacheCleanup();
    this.subscribers.clear();
    this.sentimentCache.clear();
    this.processingQueue = [];

    logger.info("NewsStreamProcessor: Destroyed");
  }
}

// Create singleton instance
const newsStreamProcessor = new NewsStreamProcessor();

module.exports = newsStreamProcessor;
