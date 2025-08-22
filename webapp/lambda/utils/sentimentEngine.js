const logger = require("./logger");

class SentimentEngine {
  calculateMarketSentiment(_data = {}) {
    try {
      return {
        overallSentiment: "neutral",
        score: 0.5,
        confidence: 0.7,
        timestamp: new Date().toISOString(),
      };
    } catch (error) {
      logger.error("Market sentiment calculation failed:", error);
      return {
        overallSentiment: "neutral",
        score: 0.5,
        confidence: 0,
        error: error.message,
      };
    }
  }

  /**
   * Convert numeric sentiment score to text label
   * @param {number} score - Sentiment score (typically -1 to 1 or 0 to 1)
   * @returns {string} - Text label (positive, negative, neutral)
   */
  scoreToLabel(score) {
    try {
      if (typeof score !== 'number' || isNaN(score)) {
        return 'neutral';
      }

      // Handle different score ranges
      if (score >= 0.6) {
        return 'positive';
      } else if (score <= 0.4) {
        return 'negative';
      } else {
        return 'neutral';
      }
    } catch (error) {
      logger.error("Score to label conversion failed:", error);
      return 'neutral';
    }
  }

  /**
   * Analyze sentiment of text for a specific symbol
   * @param {string} text - Text to analyze
   * @param {string} symbol - Stock symbol for context
   * @returns {Object} - Sentiment analysis result
   */
  async analyzeSentiment(text, symbol = null) {
    try {
      if (!text || typeof text !== 'string') {
        throw new Error("Text is required for sentiment analysis");
      }

      // Simple keyword-based sentiment analysis (placeholder for real NLP)
      const positiveWords = ['good', 'great', 'excellent', 'positive', 'bullish', 'up', 'gain', 'profit', 'success'];
      const negativeWords = ['bad', 'terrible', 'negative', 'bearish', 'down', 'loss', 'decline', 'fail', 'poor'];
      
      const words = text.toLowerCase().split(/\s+/);
      let positiveCount = 0;
      let negativeCount = 0;

      words.forEach(word => {
        if (positiveWords.some(pw => word.includes(pw))) {
          positiveCount++;
        }
        if (negativeWords.some(nw => word.includes(nw))) {
          negativeCount++;
        }
      });

      const totalSentimentWords = positiveCount + negativeCount;
      let score = 0.5; // neutral default
      let confidence = 0.3; // low confidence for simple analysis

      if (totalSentimentWords > 0) {
        score = positiveCount / (positiveCount + negativeCount);
        confidence = Math.min(0.8, totalSentimentWords / words.length * 5); // higher confidence with more sentiment words
      }

      const label = this.scoreToLabel(score);

      return {
        score: Math.round(score * 100) / 100,
        label,
        confidence: Math.round(confidence * 100) / 100,
        symbol: symbol || null,
        wordCount: words.length,
        positiveWords: positiveCount,
        negativeWords: negativeCount,
        timestamp: new Date().toISOString(),
      };
    } catch (error) {
      logger.error("Sentiment analysis failed:", error);
      return {
        score: 0.5,
        label: 'neutral',
        confidence: 0,
        symbol: symbol || null,
        error: error.message,
        timestamp: new Date().toISOString(),
      };
    }
  }
}

module.exports = new SentimentEngine();
