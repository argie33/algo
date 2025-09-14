/**
 * Frontend News Analyzer Utility
 * Provides client-side news analysis and sentiment scoring
 */

class NewsAnalyzer {
  constructor() {
    this.sentimentKeywords = {
      positive: [
        'growth', 'profit', 'gain', 'up', 'strong', 'bullish', 'buy',
        'upgrade', 'beat', 'exceed', 'success', 'breakthrough', 'surge',
        'rally', 'boom', 'soar', 'climb', 'rise', 'advance', 'outperform'
      ],
      negative: [
        'loss', 'decline', 'down', 'weak', 'bearish', 'sell',
        'downgrade', 'miss', 'below', 'cut', 'crash', 'plunge',
        'tumble', 'fall', 'drop', 'slump', 'collapse', 'underperform'
      ],
      neutral: [
        'maintain', 'hold', 'stable', 'flat', 'unchanged', 'neutral',
        'steady', 'consistent', 'moderate'
      ]
    };

    this.impactWeights = {
      high: 1.0,
      medium: 0.6,
      low: 0.3
    };
  }

  /**
   * Analyze sentiment of news article
   * @param {Object} article - News article object
   * @returns {Object} Sentiment analysis result
   */
  analyzeSentiment(article) {
    try {
      if (!article || (!article.title && !article.headline)) {
        return {
          sentiment: 'neutral',
          score: 0.5,
          confidence: 0,
          keywords: []
        };
      }

      const text = `${article.title || article.headline || ''} ${article.summary || article.description || ''}`.toLowerCase();
      const words = text.split(/\s+/);

      let positiveScore = 0;
      let negativeScore = 0;
      let foundKeywords = [];

      // Count sentiment keywords
      words.forEach(word => {
        if (this.sentimentKeywords.positive.some(keyword => word.includes(keyword))) {
          positiveScore++;
          foundKeywords.push({ word, sentiment: 'positive' });
        } else if (this.sentimentKeywords.negative.some(keyword => word.includes(keyword))) {
          negativeScore++;
          foundKeywords.push({ word, sentiment: 'negative' });
        } else if (this.sentimentKeywords.neutral.some(keyword => word.includes(keyword))) {
          foundKeywords.push({ word, sentiment: 'neutral' });
        }
      });

      // Calculate sentiment
      const totalSentimentWords = positiveScore + negativeScore;
      let sentiment = 'neutral';
      let score = 0.5;

      if (totalSentimentWords > 0) {
        if (positiveScore > negativeScore) {
          sentiment = 'positive';
          score = 0.5 + (positiveScore / totalSentimentWords) * 0.5;
        } else if (negativeScore > positiveScore) {
          sentiment = 'negative';
          score = 0.5 - (negativeScore / totalSentimentWords) * 0.5;
        }
      }

      const confidence = Math.min(totalSentimentWords / 5, 1); // Max confidence with 5+ sentiment words

      return {
        sentiment,
        score: Math.round(score * 100) / 100,
        confidence: Math.round(confidence * 100) / 100,
        keywords: foundKeywords,
        wordCount: words.length,
        sentimentWordCount: totalSentimentWords
      };
    } catch (error) {
      console.error('NewsAnalyzer: Sentiment analysis failed:', error);
      return {
        sentiment: 'neutral',
        score: 0.5,
        confidence: 0,
        error: error.message
      };
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
        return { impact: 'low', score: 0.3 };
      }

      let score = 0.5; // Base score

      // Source credibility
      const credibleSources = [
        'reuters', 'bloomberg', 'cnbc', 'wsj', 'wall street journal',
        'financial times', 'ft', 'marketwatch', 'yahoo finance',
        'associated press', 'ap news'
      ];

      if (article.source) {
        const sourceLower = article.source.toLowerCase();
        if (credibleSources.some(src => sourceLower.includes(src))) {
          score += 0.2;
        }
      }

      // Recency bonus
      if (article.publishedAt || article.published_at) {
        const publishTime = new Date(article.publishedAt || article.published_at);
        const hoursAgo = (Date.now() - publishTime.getTime()) / (1000 * 60 * 60);
        
        if (hoursAgo < 1) score += 0.2;
        else if (hoursAgo < 6) score += 0.1;
        else if (hoursAgo < 24) score += 0.05;
      }

      // Content quality (length)
      const content = article.summary || article.description || '';
      if (content.length > 200) score += 0.1;
      if (content.length > 500) score += 0.05;

      // Symbol relevance
      if (article.symbols && article.symbols.length > 0) {
        score += 0.1;
      }

      // Determine impact level
      let impact = 'low';
      if (score >= 0.8) impact = 'high';
      else if (score >= 0.6) impact = 'medium';

      return {
        impact,
        score: Math.round(score * 100) / 100,
        factors: {
          source: article.source || 'unknown',
          recency: this.getRecencyDescription(article),
          contentLength: content.length,
          hasSymbols: !!(article.symbols && article.symbols.length > 0)
        }
      };
    } catch (error) {
      console.error('NewsAnalyzer: Impact calculation failed:', error);
      return {
        impact: 'low',
        score: 0.3,
        error: error.message
      };
    }
  }

  /**
   * Get recency description
   * @param {Object} article 
   * @returns {string}
   */
  getRecencyDescription(article) {
    try {
      if (!article.publishedAt && !article.published_at) return 'unknown';
      
      const publishTime = new Date(article.publishedAt || article.published_at);
      const hoursAgo = (Date.now() - publishTime.getTime()) / (1000 * 60 * 60);
      
      if (hoursAgo < 1) return 'very recent';
      if (hoursAgo < 6) return 'recent';
      if (hoursAgo < 24) return 'today';
      if (hoursAgo < 168) return 'this week';
      return 'older';
    } catch (error) {
      return 'unknown';
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
        'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of',
        'with', 'by', 'is', 'are', 'was', 'were', 'a', 'an', 'this',
        'that', 'will', 'have', 'has', 'had', 'stock', 'stocks',
        'market', 'markets', 'company', 'companies'
      ]);

      articles.forEach(article => {
        const title = article.title || article.headline || '';
        const words = title
          .toLowerCase()
          .replace(/[^\w\s]/g, '')
          .split(/\s+/)
          .filter(word => word.length > 3 && !commonWords.has(word));

        words.forEach(word => {
          topicCounts[word] = (topicCounts[word] || 0) + 1;
        });
      });

      return Object.entries(topicCounts)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 10)
        .map(([topic, count]) => ({
          topic,
          count,
          frequency: count / articles.length
        }));
    } catch (error) {
      console.error('NewsAnalyzer: Topic extraction failed:', error);
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
          overallSentiment: 'neutral',
          averageScore: 0.5,
          confidence: 0,
          articleCount: 0,
          distribution: { positive: 0, negative: 0, neutral: 0 }
        };
      }

      const results = articles.map(article => this.analyzeSentiment(article));
      const distribution = { positive: 0, negative: 0, neutral: 0 };
      let totalScore = 0;
      let totalConfidence = 0;

      results.forEach(result => {
        distribution[result.sentiment]++;
        totalScore += result.score;
        totalConfidence += result.confidence;
      });

      const averageScore = totalScore / articles.length;
      const averageConfidence = totalConfidence / articles.length;

      // Determine overall sentiment
      let overallSentiment = 'neutral';
      const maxCount = Math.max(...Object.values(distribution));
      
      if (distribution.positive === maxCount && distribution.positive > 0) {
        overallSentiment = 'positive';
      } else if (distribution.negative === maxCount && distribution.negative > 0) {
        overallSentiment = 'negative';
      }

      return {
        overallSentiment,
        averageScore: Math.round(averageScore * 100) / 100,
        confidence: Math.round(averageConfidence * 100) / 100,
        articleCount: articles.length,
        distribution,
        details: results
      };
    } catch (error) {
      console.error('NewsAnalyzer: Articles analysis failed:', error);
      return {
        overallSentiment: 'neutral',
        averageScore: 0.5,
        confidence: 0,
        articleCount: 0,
        distribution: { positive: 0, negative: 0, neutral: 0 },
        error: error.message
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
      if (!source || typeof source !== 'string') {
        return 0.5;
      }

      const sourceLower = source.toLowerCase();

      // Tier 1: Highest reliability (0.9+)
      const tier1Sources = [
        'reuters', 'bloomberg', 'associated press', 'ap news',
        'wall street journal', 'wsj', 'financial times', 'ft'
      ];

      // Tier 2: High reliability (0.7-0.8)
      const tier2Sources = [
        'cnbc', 'marketwatch', 'yahoo finance', 'cnn business',
        'bbc', 'npr', 'usa today', 'washington post'
      ];

      // Tier 3: Medium reliability (0.5-0.6)
      const tier3Sources = [
        'forbes', 'business insider', 'thestreet', 'seeking alpha',
        'motley fool', 'benzinga', 'zacks', 'morningstar'
      ];

      if (tier1Sources.some(src => sourceLower.includes(src))) return 0.9;
      if (tier2Sources.some(src => sourceLower.includes(src))) return 0.75;
      if (tier3Sources.some(src => sourceLower.includes(src))) return 0.55;

      // Check for unreliable patterns
      const unreliablePatterns = ['blog', 'forum', 'reddit', 'twitter', 'facebook'];
      if (unreliablePatterns.some(pattern => sourceLower.includes(pattern))) {
        return 0.3;
      }

      return 0.5; // Default for unknown sources
    } catch (error) {
      console.error('NewsAnalyzer: Reliability calculation failed:', error);
      return 0.5;
    }
  }
}

// Create and export singleton instance
export const newsAnalyzer = new NewsAnalyzer();
export default newsAnalyzer;