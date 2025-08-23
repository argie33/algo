/**
 * News Analyzer Utility
 * Provides news analysis and sentiment scoring functionality
 */

const logger = require("./logger");

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
      ],
      neutral: ["maintain", "hold", "stable", "flat", "unchanged", "neutral"],
    };

    this.impactWeights = {
      high: 1.0,
      medium: 0.6,
      low: 0.3,
    };
  }

  /**
   * Analyze news article sentiment
   * @param {Object} article - News article object
   * @returns {Object} Sentiment analysis result
   */
  analyzeSentiment(article) {
    try {
      if (!article || !article.title) {
        return {
          sentiment: "neutral",
          score: 0,
          confidence: 0,
          keywords: [],
        };
      }

      const text =
        `${article.title} ${article.description || ""}`.toLowerCase();
      const words = text.split(/\s+/);

      let positiveScore = 0;
      let negativeScore = 0;
      let foundKeywords = [];

      // Count sentiment keywords
      words.forEach((word) => {
        if (this.sentimentKeywords.positive.includes(word)) {
          positiveScore++;
          foundKeywords.push({ word, sentiment: "positive" });
        } else if (this.sentimentKeywords.negative.includes(word)) {
          negativeScore++;
          foundKeywords.push({ word, sentiment: "negative" });
        } else if (this.sentimentKeywords.neutral.includes(word)) {
          foundKeywords.push({ word, sentiment: "neutral" });
        }
      });

      // Calculate overall sentiment
      const totalSentimentWords = positiveScore + negativeScore;
      let sentiment = "neutral";
      let score = 0;

      if (totalSentimentWords > 0) {
        if (positiveScore > negativeScore) {
          sentiment = "positive";
          score = positiveScore / totalSentimentWords;
        } else if (negativeScore > positiveScore) {
          sentiment = "negative";
          score = negativeScore / totalSentimentWords;
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
      logger.error("Sentiment analysis failed:", error);
      return {
        sentiment: "neutral",
        score: 0,
        confidence: 0,
        error: error.message,
      };
    }
  }

  /**
   * Analyze multiple news articles
   * @param {Array} articles - Array of news articles
   * @returns {Object} Aggregated sentiment analysis
   */
  analyzeArticles(articles = []) {
    try {
      if (!Array.isArray(articles) || articles.length === 0) {
        return {
          overallSentiment: "neutral",
          averageScore: 0,
          confidence: 0,
          articleCount: 0,
          sentimentDistribution: { positive: 0, negative: 0, neutral: 0 },
        };
      }

      const results = articles.map((article) => this.analyzeSentiment(article));

      const sentimentCounts = { positive: 0, negative: 0, neutral: 0 };
      let totalScore = 0;
      let totalConfidence = 0;

      results.forEach((result) => {
        sentimentCounts[result.sentiment]++;
        totalScore += result.score * (result.sentiment === "negative" ? -1 : 1);
        totalConfidence += result.confidence;
      });

      const averageScore = totalScore / articles.length;
      const averageConfidence = totalConfidence / articles.length;

      // Determine overall sentiment
      let overallSentiment = "neutral";
      if (
        sentimentCounts.positive > sentimentCounts.negative &&
        sentimentCounts.positive > sentimentCounts.neutral
      ) {
        overallSentiment = "positive";
      } else if (
        sentimentCounts.negative > sentimentCounts.positive &&
        sentimentCounts.negative > sentimentCounts.neutral
      ) {
        overallSentiment = "negative";
      }

      return {
        overallSentiment,
        averageScore: Math.round(averageScore * 100) / 100,
        confidence: Math.round(averageConfidence * 100) / 100,
        articleCount: articles.length,
        sentimentDistribution: sentimentCounts,
        details: results,
      };
    } catch (error) {
      logger.error("Articles analysis failed:", error);
      return {
        overallSentiment: "neutral",
        averageScore: 0,
        confidence: 0,
        articleCount: 0,
        error: error.message,
      };
    }
  }

  /**
   * Extract key topics from news articles
   * @param {Array} articles - Array of news articles
   * @returns {Array} Array of key topics
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
      ]);

      articles.forEach((article) => {
        if (article.title) {
          const words = article.title
            .toLowerCase()
            .replace(/[^\w\s]/g, "")
            .split(/\s+/)
            .filter((word) => word.length > 3 && !commonWords.has(word));

          words.forEach((word) => {
            topicCounts[word] = (topicCounts[word] || 0) + 1;
          });
        }
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
      logger.error("Topic extraction failed:", error);
      return [];
    }
  }

  /**
   * Calculate news impact score
   * @param {Object} article - News article
   * @returns {Object} Impact score result
   */
  calculateImpact(article) {
    try {
      if (!article) {
        return { impact: "low", score: 0 };
      }

      let score = 0.5; // Base score

      // Source credibility (simplified)
      const credibleSources = ["reuters", "bloomberg", "cnbc", "wsj", "ft"];
      if (
        article.source &&
        credibleSources.some((src) =>
          article.source.toLowerCase().includes(src)
        )
      ) {
        score += 0.2;
      }

      // Recency
      if (article.publishedAt) {
        const hoursAgo =
          (Date.now() - new Date(article.publishedAt).getTime()) /
          (1000 * 60 * 60);
        if (hoursAgo < 1) score += 0.2;
        else if (hoursAgo < 6) score += 0.1;
      }

      // Content length (longer articles often more impactful)
      if (article.description && article.description.length > 200) {
        score += 0.1;
      }

      // Determine impact level
      let impact = "low";
      if (score >= 0.8) impact = "high";
      else if (score >= 0.6) impact = "medium";

      return {
        impact,
        score: Math.round(score * 100) / 100,
        factors: {
          source: article.source || "unknown",
          recency: article.publishedAt ? "recent" : "unknown",
          contentLength: article.description ? article.description.length : 0,
        },
      };
    } catch (error) {
      logger.error("Impact calculation failed:", error);
      return {
        impact: "low",
        score: 0,
        error: error.message,
      };
    }
  }

  /**
   * Calculate reliability score for a news source
   * @param {string} source - News source name
   * @returns {number} Reliability score (0-1)
   */
  calculateReliabilityScore(source) {
    try {
      if (!source || typeof source !== "string") {
        return 0.5; // Default neutral score
      }

      const sourceLower = source.toLowerCase();

      // High reliability sources
      const highReliabilitySources = [
        "reuters",
        "bloomberg",
        "associated press",
        "ap news",
        "wall street journal",
        "wsj",
        "financial times",
        "ft",
        "cnbc",
        "marketwatch",
        "yahoo finance",
        "seeking alpha",
        "motley fool",
        "benzinga",
        "zacks",
        "morningstar",
      ];

      // Medium reliability sources
      const mediumReliabilitySources = [
        "cnn",
        "bbc",
        "npr",
        "usa today",
        "washington post",
        "new york times",
        "forbes",
        "business insider",
        "investopedia",
        "thestreet",
        "barrons",
      ];

      // Check for high reliability (0.8-1.0)
      for (const highSource of highReliabilitySources) {
        if (sourceLower.includes(highSource)) {
          return 0.9;
        }
      }

      // Check for medium reliability (0.6-0.8)
      for (const mediumSource of mediumReliabilitySources) {
        if (sourceLower.includes(mediumSource)) {
          return 0.7;
        }
      }

      // Check for known unreliable patterns
      const unreliablePatterns = [
        "blog",
        "forum",
        "reddit",
        "twitter",
        "facebook",
      ];
      for (const pattern of unreliablePatterns) {
        if (sourceLower.includes(pattern)) {
          return 0.3;
        }
      }

      // Default for unknown sources
      return 0.5;
    } catch (error) {
      logger.error("Reliability score calculation failed:", error);
      return 0.5;
    }
  }

  /**
   * Get sentiment keywords configuration
   * @returns {Object} Sentiment keywords
   */
  getSentimentKeywords() {
    return this.sentimentKeywords;
  }

  /**
   * Update sentiment keywords
   * @param {Object} keywords - New keywords configuration
   * @returns {boolean} Success status
   */
  updateSentimentKeywords(keywords) {
    try {
      if (keywords.positive && Array.isArray(keywords.positive)) {
        this.sentimentKeywords.positive = [
          ...this.sentimentKeywords.positive,
          ...keywords.positive,
        ];
      }
      if (keywords.negative && Array.isArray(keywords.negative)) {
        this.sentimentKeywords.negative = [
          ...this.sentimentKeywords.negative,
          ...keywords.negative,
        ];
      }
      if (keywords.neutral && Array.isArray(keywords.neutral)) {
        this.sentimentKeywords.neutral = [
          ...this.sentimentKeywords.neutral,
          ...keywords.neutral,
        ];
      }
      return true;
    } catch (error) {
      logger.error("Keywords update failed:", error);
      return false;
    }
  }
}

// Create singleton instance
const newsAnalyzer = new NewsAnalyzer();

module.exports = newsAnalyzer;
