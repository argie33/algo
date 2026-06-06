/**
 * Frontend News Analyzer Utility
 * Provides client-side news analysis and sentiment scoring
 */

class NewsAnalyzer {
  constructor() {
    this.sentimentKeywords = {
      positive: [
        "growth",
        "profit",
        "gain",
        "up",
        "strong",
        "bullish",
        "buy",
        "upgrade",
        "beat",
        "exceed",
        "success",
        "breakthrough",
        "surge",
        "rally",
        "boom",
        "soar",
        "climb",
        "rise",
        "advance",
        "outperform",
      ],
      negative: [
        "loss",
        "decline",
        "down",
        "weak",
        "bearish",
        "sell",
        "downgrade",
        "miss",
        "below",
        "cut",
        "crash",
        "plunge",
        "tumble",
        "fall",
        "drop",
        "slump",
        "collapse",
        "underperform",
      ],
      neutral: [
        "maintain",
        "hold",
        "stable",
        "flat",
        "unchanged",
        "neutral",
        "steady",
        "consistent",
        "moderate",
      ],
    };

    this.impactWeights = {
      high: 1.0,
      medium: 0.6,
      low: 0.3,
    };
  }

  /**
   * Analyze sentiment of news article
   * @param {Object} article - News article object
   * @returns {Object} Sentiment analysis result
   */
  analyzeSentiment(article) {
    try {
      // Handle both string input and article object
      let text;
      if (typeof article === 'string') {
        text = article.toLowerCase();
      } else if (article && (article.title || article.headline)) {
        text =
          `${article.title || article.headline || ""} ${article.summary || article.description || ""}`.toLowerCase();
      } else {
        return {
          sentiment: 'neutral',
          score: 0,
          confidence: 0,
          keywords: [],
        };
      }

      // Handle empty text
      if (!text || text.trim().length === 0) {
        return {
          sentiment: 'neutral',
          score: 0,
          confidence: 0,
          keywords: [],
        };
      }

      const words = text.split(/\s+/);

      let positiveScore = 0;
      let negativeScore = 0;
      let foundKeywords = [];

      // Count sentiment keywords
      words.forEach((word) => {
        if (
          this.sentimentKeywords.positive.some((keyword) =>
            word.includes(keyword)
          )
        ) {
          positiveScore++;
          foundKeywords.push({ word, sentiment: "positive" });
        } else if (
          this.sentimentKeywords.negative.some((keyword) =>
            word.includes(keyword)
          )
        ) {
          negativeScore++;
          foundKeywords.push({ word, sentiment: "negative" });
        } else if (
          this.sentimentKeywords.neutral.some((keyword) =>
            word.includes(keyword)
          )
        ) {
          foundKeywords.push({ word, sentiment: "neutral" });
        }
      });

      // Calculate sentiment
      const totalSentimentWords = positiveScore + negativeScore;
      let sentiment = 'neutral';
      let score = 0;

      if (totalSentimentWords > 0) {
        if (positiveScore > negativeScore) {
          sentiment = "positive";
          score = positiveScore / totalSentimentWords;
        } else if (negativeScore > positiveScore) {
          sentiment = "negative";
          score = -(negativeScore / totalSentimentWords);
        } else {
          sentiment = "neutral";
          score = 0;
        }
      }

      const confidence = Math.min(totalSentimentWords / 5, 1); // Max confidence with 5+ sentiment words

      return {
        sentiment,
        score: Math.round(score * 100) / 100,
        confidence: Math.round(confidence * 100) / 100,
        keywords: foundKeywords,
        wordCount: words.length,
        sentimentWordCount: totalSentimentWords,
      };
    } catch (error) {
      console.error("NewsAnalyzer: Sentiment analysis failed:", error);
      return {
        sentiment: 'neutral',
        score: 0,
        confidence: 0,
        error: error.message,
      };
    }
  }

  /**
   * Extract keywords from text
   * @param {string} text - Text to extract keywords from
   * @returns {Array} Array of keywords
   */
  extractKeywords(text = '') {
    try {
      if (!text || typeof text !== 'string') {
        return [];
      }

      const commonStopwords = new Set([
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these',
        'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what', 'which',
        'who', 'when', 'where', 'why', 'how', 'as', 'if', 'because', 'while',
        'after', 'before', 'during', 'between', 'through', 'about', 'over',
        'under', 'above', 'below', 'up', 'down', 'out', 'in', 'off', 'into',
        'onto', 'etc', 'am', 'pm'
      ]);

      const financialKeywords = new Set([
        'earnings', 'revenue', 'profit', 'loss', 'margin', 'growth', 'decline',
        'beat', 'miss', 'guidance', 'forecast', 'analyst', 'upgrade', 'downgrade',
        'buyback', 'dividend', 'acquisition', 'merger', 'ipo', 'stock', 'shares',
        'trading', 'sector', 'market', 'price', 'volume', 'volatility', 'bullish',
        'bearish', 'support', 'resistance', 'breakout', 'momentum', 'technical',
        'fundamental', 'valuation', 'pe', 'eps', 'roe', 'fcf', 'cash', 'debt'
      ]);

      const words = text.toLowerCase()
        .replace(/[^\w\s]/g, ' ')
        .split(/\s+/)
        .filter(word => word.length > 0);

      const keywords = [];
      const seen = new Set();

      words.forEach(word => {
        if (!seen.has(word) &&
            !commonStopwords.has(word) &&
            word.length > 2 &&
            financialKeywords.has(word)) {
          keywords.push(word);
          seen.add(word);
        }
      });

      return keywords;
    } catch (error) {
      console.error("NewsAnalyzer: Keyword extraction failed:", error);
      return [];
    }
  }

  /**
   * Extract stock symbols from text
   * @param {string} text - Text to extract symbols from
   * @returns {Array} Array of stock symbols
   */
  extractSymbols(text = '') {
    try {
      if (!text || typeof text !== 'string') {
        return [];
      }

      const commonWords = new Set([
        'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'her',
        'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how',
        'its', 'may', 'new', 'now', 'old', 'see', 'two', 'way', 'who', 'boy',
        'did', 'let', 'put', 'say', 'she', 'too', 'use', 'own', 'ate', 'yes',
        'got', 'in', 'on', 'to', 'is', 'by', 'at', 'it', 'or', 'an', 'be',
        'we', 'as', 'up', 'so', 'do', 'go', 'no', 'if', 'of', 'a', 'be', 'me'
      ]);

      const symbolPattern = /\b([a-zA-Z]{1,5})\b/g;
      const symbols = [];
      const seen = new Set();
      let match;

      while ((match = symbolPattern.exec(text)) !== null) {
        const symbol = match[1].toUpperCase();
        const symbolLower = match[1].toLowerCase();
        if (!seen.has(symbol) &&
            symbol.length >= 2 &&
            symbol.length <= 5 &&
            !commonWords.has(symbolLower)) {
          symbols.push(symbol);
          seen.add(symbol);
        }
      }

      return symbols;
    } catch (error) {
      console.error("NewsAnalyzer: Symbol extraction failed:", error);
      return [];
    }
  }

  /**
   * Categorize article by type
   * @param {string} text - Article text
   * @returns {string} Category: 'earnings', 'analysis', 'general'
   */
  categorizeArticle(text = '') {
    try {
      if (!text || typeof text !== 'string') {
        return 'general';
      }

      const textLower = text.toLowerCase();

      const earningsKeywords = ['earnings', 'earnings report', 'earnings beat', 'earnings call', 'quarterly earnings', 'revenue beat', 'profit margin'];
      const analysisKeywords = ['technical analysis', 'breakout', 'support level', 'resistance level', 'moving average', 'rsi', 'macd', 'chart pattern'];

      const hasEarnings = earningsKeywords.some(keyword => textLower.includes(keyword));
      const hasAnalysis = analysisKeywords.some(keyword => textLower.includes(keyword));

      if (hasEarnings) return 'earnings';
      if (hasAnalysis) return 'analysis';
      return 'general';
    } catch (error) {
      console.error("NewsAnalyzer: Article categorization failed:", error);
      return 'general';
    }
  }

  /**
   * Calculate news impact score
   * @param {string|Object} article - News article or text
   * @returns {number|Object} Impact score result
   */
  calculateImpact(article) {
    try {
      if (!article) {
        return 0;
      }

      // Handle string input - use text length as impact
      if (typeof article === 'string') {
        const text = article.trim();
        const length = text.length;

        // Calculate impact based on text length and keywords
        const majorEventKeywords = ['announces', 'breakthrough', 'record', 'surge', 'crash', 'plunge', 'stock split', 'beats', 'misses'];
        const hasMajorEvent = majorEventKeywords.some(keyword => text.toLowerCase().includes(keyword));

        let score = 0;
        if (length > 500) score = 0.8;
        else if (length > 200) score = 0.6;
        else if (length > 50) score = 0.4;
        else if (length > 0) score = 0.2;

        if (hasMajorEvent) score += 0.2;

        return Math.min(score, 1);
      }

      // Handle object input
      let score = 0;

      // Source credibility
      const credibleSources = [
        "reuters",
        "bloomberg",
        "cnbc",
        "wsj",
        "wall street journal",
        "financial times",
        "ft",
        "marketwatch",
        "yahoo finance",
        "associated press",
        "ap news",
      ];

      if (article.source) {
        const sourceLower = article.source.toLowerCase();
        if (credibleSources.some((src) => sourceLower.includes(src))) {
          score += 0.2;
        }
      }

      // Recency bonus
      if (article.publishedAt || article.published_at) {
        const publishTime = new Date(
          article.publishedAt || article.published_at
        );
        const hoursAgo =
          (Date.now() - publishTime.getTime()) / (1000 * 60 * 60);

        if (hoursAgo < 1) score += 0.2;
        else if (hoursAgo < 6) score += 0.1;
        else if (hoursAgo < 24) score += 0.05;
      }

      // Content quality (length)
      const content = article.summary || article.description || "";
      if (content.length > 200) score += 0.1;
      if (content.length > 500) score += 0.05;

      // Symbol relevance
      if (article.symbols && article.symbols.length > 0) {
        score += 0.1;
      }

      // Determine impact level
      let impact = null;
      if (score >= 0.8) impact = "high";
      else if (score >= 0.6) impact = "medium";
      else if (score > 0) impact = "low";

      return {
        impact,
        score: Math.round(score * 100) / 100,
        factors: {
          source: article.source || "unknown",
          recency: this.getRecencyDescription(article),
          contentLength: content.length,
          hasSymbols: !!(article.symbols && article.symbols.length > 0),
        },
      };
    } catch (error) {
      console.error("NewsAnalyzer: Impact calculation failed:", error);
      return 0;
    }
  }

  /**
   * Get recency description
   * @param {Object} article
   * @returns {string}
   */
  getRecencyDescription(article) {
    try {
      if (!article.publishedAt && !article.published_at) return "unknown";

      const publishTime = new Date(article.publishedAt || article.published_at);
      const hoursAgo = (Date.now() - publishTime.getTime()) / (1000 * 60 * 60);

      if (hoursAgo < 1) return "very recent";
      if (hoursAgo < 6) return "recent";
      if (hoursAgo < 24) return "today";
      if (hoursAgo < 168) return "this week";
      return "older";
    } catch (error) {
      return "unknown";
    }
  }

  /**
   * Extract key topics from news articles
   * @param {Array} articles - Array of articles
   * @returns {Array} Key topics
   */
  extractTopics(articles = []) {
    try {
      if (!Array.isArray(articles) || articles.length === 0) {
        return [];
      }

      const topicCounts = {};
      const commonWords = new Set([
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
        "a",
        "an",
        "this",
        "that",
        "will",
        "have",
        "has",
        "had",
        "stock",
        "stocks",
        "market",
        "markets",
        "company",
        "companies",
      ]);

      articles.forEach((article) => {
        const title = article.title || article.headline || "";
        const words = title
          .toLowerCase()
          .replace(/[^\w\s]/g, "")
          .split(/\s+/)
          .filter((word) => word.length > 3 && !commonWords.has(word));

        words.forEach((word) => {
          topicCounts[word] = (topicCounts[word] || 0) + 1;
        });
      });

      return Object.entries(topicCounts)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 10)
        .map(([topic, count]) => ({
          topic,
          count,
          frequency: count / articles.length,
        }));
    } catch (error) {
      console.error("NewsAnalyzer: Topic extraction failed:", error);
      return [];
    }
  }

  /**
   * Analyze multiple articles for aggregate sentiment
   * @param {Array} articles - Articles to analyze
   * @returns {Object} Aggregate analysis
   */
  analyzeArticles(articles = []) {
    try {
      if (!Array.isArray(articles) || articles.length === 0) {
        return {
          overallSentiment: null,
          averageScore: null,
          confidence: 0,
          articleCount: 0,
          distribution: { positive: 0, negative: 0, neutral: 0 },
        };
      }

      const results = articles.map((article) => this.analyzeSentiment(article));
      const distribution = { positive: 0, negative: 0, neutral: 0 };
      let totalScore = 0;
      let totalConfidence = 0;

      results.forEach((result) => {
        distribution[result.sentiment]++;
        totalScore += result.score;
        totalConfidence += result.confidence;
      });

      const averageScore = totalScore / articles.length;
      const averageConfidence = totalConfidence / articles.length;

      // Determine overall sentiment
      let overallSentiment = null;
      const maxCount = Math.max(...Object.values(distribution));

      if (distribution.positive === maxCount && distribution.positive > 0) {
        overallSentiment = "positive";
      } else if (
        distribution.negative === maxCount &&
        distribution.negative > 0
      ) {
        overallSentiment = "negative";
      } else if (distribution.neutral > 0) {
        overallSentiment = "neutral";
      }

      return {
        overallSentiment,
        averageScore: Math.round(averageScore * 100) / 100,
        confidence: Math.round(averageConfidence * 100) / 100,
        articleCount: articles.length,
        distribution,
        details: results,
      };
    } catch (error) {
      console.error("NewsAnalyzer: Articles analysis failed:", error);
      return {
        overallSentiment: null,
        averageScore: null,
        confidence: 0,
        articleCount: 0,
        distribution: { positive: 0, negative: 0, neutral: 0 },
        error: error.message,
      };
    }
  }

  /**
   * Calculate reliability score for news source
   * @param {string} source - News source
   * @returns {number} Reliability score (0-1)
   */
  calculateReliabilityScore(source) {
    try {
      if (!source || typeof source !== "string") {
        return null;
      }

      const sourceLower = source.toLowerCase();

      // Tier 1: Highest reliability (0.9+)
      const tier1Sources = [
        "reuters",
        "bloomberg",
        "associated press",
        "ap news",
        "wall street journal",
        "wsj",
        "financial times",
        "ft",
      ];

      // Tier 2: High reliability (0.7-0.8)
      const tier2Sources = [
        "cnbc",
        "marketwatch",
        "yahoo finance",
        "cnn business",
        "bbc",
        "npr",
        "usa today",
        "washington post",
      ];

      // Tier 3: Medium reliability (0.5-0.6)
      const tier3Sources = [
        "forbes",
        "business insider",
        "thestreet",
        "seeking alpha",
        "motley fool",
        "benzinga",
        "zacks",
        "morningstar",
      ];

      if (tier1Sources.some((src) => sourceLower.includes(src))) return 0.9;
      if (tier2Sources.some((src) => sourceLower.includes(src))) return 0.75;
      if (tier3Sources.some((src) => sourceLower.includes(src))) return 0.55;

      // Check for unreliable patterns
      const unreliablePatterns = [
        "blog",
        "forum",
        "reddit",
        "twitter",
        "facebook",
      ];
      if (unreliablePatterns.some((pattern) => sourceLower.includes(pattern))) {
        return 0.3;
      }

      return null; // No default for unknown sources - let caller handle it
    } catch (error) {
      console.error("NewsAnalyzer: Reliability calculation failed:", error);
      return null;
    }
  }
}

export default NewsAnalyzer;

// Create and export singleton instance for use in the app
export const newsAnalyzer = new NewsAnalyzer();

