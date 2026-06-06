/**
 * News Analyzer — NLP utilities for news/article sentiment and impact analysis
 * Used by news dashboard, market sentiment, and trading signals
 */

class NewsAnalyzer {
  constructor() {
    // Positive financial keywords
    this.positiveKeywords = [
      'beat', 'rally', 'surge', 'gains', 'profit', 'profitability', 'growth',
      'upgrade', 'bullish', 'strong', 'excellent', 'outperform', 'upbeat',
      'advance', 'jump', 'boom', 'accelerate', 'expand', 'earnings',
    ];

    // Negative financial keywords
    this.negativeKeywords = [
      'crash', 'plunge', 'decline', 'loss', 'miss', 'downgrade', 'bearish',
      'weak', 'poor', 'downside', 'slump', 'tumble', 'fall', 'drop',
      'contract', 'shrink', 'bearish', 'cautious', 'disappointing',
    ];

    // Stop words to filter out
    this.stopWords = new Set([
      'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
      'of', 'with', 'by', 'from', 'up', 'about', 'is', 'are', 'was', 'were',
      'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
      'will', 'would', 'could', 'should', 'may', 'might', 'can', 'this',
      'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they',
    ]);

    // Major financial event keywords
    this.majorEventKeywords = [
      'bankruptcy', 'acquisition', 'merger', 'ipo', 'split', 'dividend',
      'earnings', 'guidance', 'restructure', 'ceo', 'cto', 'sec',
    ];
  }

  analyzeSentiment(text) {
    if (!text || typeof text !== 'string' || text.trim().length === 0) {
      return { score: 0, sentiment: 'neutral' };
    }

    const lowerText = text.toLowerCase();
    let score = 0;

    // Count positive and negative keywords
    this.positiveKeywords.forEach(keyword => {
      const regex = new RegExp(`\\b${keyword}\\b`, 'gi');
      const matches = lowerText.match(regex);
      score += (matches?.length || 0) * 1.0;
    });

    this.negativeKeywords.forEach(keyword => {
      const regex = new RegExp(`\\b${keyword}\\b`, 'gi');
      const matches = lowerText.match(regex);
      score -= (matches?.length || 0) * 1.0;
    });

    // Normalize by text length
    score = score / Math.sqrt(text.split(/\s+/).length || 1);

    // Determine sentiment
    let sentiment = 'neutral';
    if (score > 0.3) sentiment = 'positive';
    else if (score < -0.3) sentiment = 'negative';

    return { score, sentiment };
  }

  extractKeywords(text) {
    if (!text || typeof text !== 'string') return [];

    // Tokenize and filter
    const words = text
      .toLowerCase()
      .replace(/[^a-z0-9\s]/g, '') // Remove punctuation
      .split(/\s+/)
      .filter(word => word.length > 3 && !this.stopWords.has(word));

    // Remove duplicates and return
    return [...new Set(words)];
  }

  calculateImpact(text) {
    if (!text || typeof text !== 'string') return 0;

    let impact = 0;

    // Major events have high impact
    this.majorEventKeywords.forEach(keyword => {
      const regex = new RegExp(`\\b${keyword}\\b`, 'gi');
      const matches = text.match(regex);
      impact += (matches?.length || 0) * 5.0;
    });

    // Text length contributes to impact
    impact += (text.split(/\s+/).length / 10);

    // Sentiment contributes
    const { score } = this.analyzeSentiment(text);
    impact += Math.abs(score) * 2;

    return impact;
  }

  extractSymbols(text) {
    if (!text || typeof text !== 'string') return [];

    // Match common stock symbols (1-5 capital letters)
    const symbolRegex = /\b([A-Z]{1,5})\b/g;
    const symbols = text.match(symbolRegex) || [];

    // Filter out common words that aren't symbols
    const commonWords = new Set(['THE', 'AND', 'FOR', 'BUT', 'WITH', 'FROM', 'THAT', 'THIS', 'HAVE', 'WILL', 'SAID', 'THAN', 'ONLY', 'OVER', 'ALSO']);
    return [...new Set(symbols)].filter(sym => !commonWords.has(sym));
  }

  categorizeNews(text) {
    if (!text || typeof text !== 'string') return 'general';

    const lowerText = text.toLowerCase();

    if (
      lowerText.includes('earnings') ||
      lowerText.includes('revenue') ||
      lowerText.includes('profit') ||
      lowerText.includes('eps') ||
      lowerText.includes('guidance')
    ) {
      return 'earnings';
    }

    if (
      lowerText.includes('analysis') ||
      lowerText.includes('technical') ||
      lowerText.includes('chart') ||
      lowerText.includes('trend') ||
      lowerText.includes('momentum')
    ) {
      return 'analysis';
    }

    return 'general';
  }
}

export default NewsAnalyzer;
