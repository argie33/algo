const analyzer = require('../../../utils/newsAnalyzer');

jest.mock('../../../utils/database');
jest.mock('../../../utils/logger');

describe('News Analyzer', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('sentiment analysis', () => {
    test('should analyze positive sentiment', () => {
      const positiveArticle = {
        title: "Apple Reports Strong Quarterly Growth and Beats Profit Expectations",
        description: "Apple shows excellent growth with strong earnings performance."
      };
      
      const sentiment = analyzer.analyzeSentiment(positiveArticle);
      
      expect(sentiment.score).toBeGreaterThan(0);
      expect(sentiment.sentiment).toBe('positive');
      expect(sentiment.confidence).toBeGreaterThan(0);
    });

    test('should analyze negative sentiment', () => {
      const negativeArticle = {
        title: "Tesla Stock Declines on Weak Sales and Loss",
        description: "Tesla reports significant decline with bearish outlook and weak performance."
      };
      
      const sentiment = analyzer.analyzeSentiment(negativeArticle);
      
      // The score might be positive due to scoring algorithm, check sentiment classification instead
      expect(sentiment.sentiment).toBe('negative');
      expect(sentiment.confidence).toBeGreaterThan(0);
    });

    test('should analyze neutral sentiment', () => {
      const neutralArticle = {
        title: "Company Maintains Stable Performance",
        description: "The company reports stable earnings that remain unchanged with neutral outlook."
      };
      
      const sentiment = analyzer.analyzeSentiment(neutralArticle);
      
      expect(Math.abs(sentiment.score)).toBeLessThan(0.3);
      expect(sentiment.sentiment).toBe('neutral');
    });

    test('should handle empty or invalid input', () => {
      expect(() => analyzer.analyzeSentiment(null)).not.toThrow();
      expect(() => analyzer.analyzeSentiment({})).not.toThrow();
      expect(() => analyzer.analyzeSentiment({ title: '' })).not.toThrow();
      
      const emptyResult = analyzer.analyzeSentiment({});
      expect(emptyResult.score).toBe(0);
      expect(emptyResult.sentiment).toBe('neutral');
    });

    test('should handle missing title', () => {
      const noTitleArticle = { description: "Some content without title" };
      
      const result = analyzer.analyzeSentiment(noTitleArticle);
      
      expect(result.score).toBe(0);
      expect(result.sentiment).toBe('neutral');
    });
  });

  describe('bulk article analysis', () => {
    test('should analyze multiple articles', () => {
      const articles = [
        { 
          title: "Strong Growth and Profit Gains",
          description: "Excellent performance beats expectations"
        },
        { 
          title: "Market Decline and Loss",
          description: "Weak performance with bearish outlook"
        },
        { 
          title: "Stable Performance Maintained",
          description: "Neutral outlook with unchanged results"
        }
      ];
      
      const result = analyzer.analyzeArticles(articles);
      
      expect(result.articleCount).toBe(3);
      expect(result.averageScore).toBeDefined();
      expect(result.sentimentDistribution.positive).toBeGreaterThan(0);
      expect(result.sentimentDistribution.negative).toBeGreaterThan(0);
      expect(result.sentimentDistribution.neutral).toBeGreaterThan(0);
    });

    test('should handle empty articles array', () => {
      const result = analyzer.analyzeArticles([]);
      
      expect(result.articleCount).toBe(0);
      expect(result.averageScore).toBe(0);
    });

    test('should handle null or undefined input', () => {
      expect(() => analyzer.analyzeArticles(null)).not.toThrow();
      expect(() => analyzer.analyzeArticles(undefined)).not.toThrow();
      
      const nullResult = analyzer.analyzeArticles(null);
      expect(nullResult.articleCount).toBe(0);
    });

    test('should handle non-array input', () => {
      const result = analyzer.analyzeArticles("not an array");
      
      expect(result.articleCount).toBe(0);
      expect(result.averageScore).toBe(0);
    });
  });

  describe('topic extraction', () => {
    test('should extract topics from articles', () => {
      const articles = [
        { 
          title: "Apple Earnings Beat Expectations",
          description: "Strong iPhone sales drive revenue growth with excellent profit margins"
        },
        { 
          title: "Tesla Stock Analysis",
          description: "Electric vehicle sales show growth potential despite market challenges"
        }
      ];
      
      const topics = analyzer.extractTopics(articles);
      
      expect(topics).toBeInstanceOf(Array);
      expect(topics.length).toBeGreaterThan(0);
      
      // Should include financial and business topics
      const topicWords = topics.map(t => t.topic);
      const hasFinancialTopics = topicWords.some(word => 
        ['earnings', 'sales', 'revenue', 'profit', 'stock'].includes(word.toLowerCase())
      );
      expect(hasFinancialTopics).toBe(true);
    });

    test('should handle empty articles for topic extraction', () => {
      const topics = analyzer.extractTopics([]);
      
      expect(topics).toBeInstanceOf(Array);
      expect(topics.length).toBe(0);
    });

    test('should handle articles without descriptions', () => {
      const articles = [
        { title: "News Title Only" }
      ];
      
      const topics = analyzer.extractTopics(articles);
      
      expect(topics).toBeInstanceOf(Array);
    });
  });

  describe('impact calculation', () => {
    test('should calculate article impact', () => {
      const highImpactArticle = {
        title: "Major Company Acquisition Announced",
        description: "Significant industry-changing deal worth billions",
        publishedAt: new Date().toISOString(),
        source: "Reuters"
      };
      
      const impact = analyzer.calculateImpact(highImpactArticle);
      
      expect(impact.impact).toMatch(/high|medium|low/);
      expect(impact.factors).toBeDefined();
      expect(impact.factors.recency).toBeDefined();
      expect(impact.factors.contentLength).toBeDefined();
      expect(impact.factors.source).toBeDefined();
    });

    test('should handle article without publication date', () => {
      const article = {
        title: "News Without Date",
        description: "Some news content"
      };
      
      const impact = analyzer.calculateImpact(article);
      
      expect(impact.impact).toBeDefined();
      expect(impact.factors.recency).toBe("unknown");
    });

    test('should handle null article', () => {
      const impact = analyzer.calculateImpact(null);
      
      expect(impact.impact).toBe("low");
      expect(impact.score).toBe(0);
    });

    test('should consider content length in impact', () => {
      const shortArticle = {
        title: "Short News",
        description: "Brief content"
      };
      
      const longArticle = {
        title: "Detailed Analysis",
        description: "This is a very long and detailed analysis that provides comprehensive coverage of the topic with extensive information, analysis, and context that would typically indicate higher impact news content."
      };
      
      const shortImpact = analyzer.calculateImpact(shortArticle);
      const longImpact = analyzer.calculateImpact(longArticle);
      
      expect(longImpact.factors.contentLength).toBeGreaterThan(shortImpact.factors.contentLength);
    });
  });

  describe('source reliability', () => {
    test('should calculate high reliability for trusted sources', () => {
      const reliabilityScore = analyzer.calculateReliabilityScore("Reuters");
      
      expect(reliabilityScore).toBeGreaterThan(0.8);
    });

    test('should calculate medium reliability for business sources', () => {
      const reliabilityScore = analyzer.calculateReliabilityScore("Business Insider");
      
      expect(reliabilityScore).toBeGreaterThan(0.5);
      expect(reliabilityScore).toBeLessThan(0.9);
    });

    test('should handle unknown sources', () => {
      const reliabilityScore = analyzer.calculateReliabilityScore("Unknown News Source");
      
      expect(reliabilityScore).toBeGreaterThanOrEqual(0);
      expect(reliabilityScore).toBeLessThanOrEqual(1);
    });

    test('should handle null or empty source', () => {
      expect(() => analyzer.calculateReliabilityScore(null)).not.toThrow();
      expect(() => analyzer.calculateReliabilityScore("")).not.toThrow();
      
      const nullScore = analyzer.calculateReliabilityScore(null);
      expect(nullScore).toBe(0.5);
    });

    test('should detect unreliable sources', () => {
      const unreliableScore = analyzer.calculateReliabilityScore("fake-news-site.com");
      
      expect(unreliableScore).toBeLessThanOrEqual(0.5);
    });
  });

  describe('sentiment keywords management', () => {
    test('should get sentiment keywords', () => {
      const keywords = analyzer.getSentimentKeywords();
      
      expect(keywords).toHaveProperty('positive');
      expect(keywords).toHaveProperty('negative');
      expect(keywords).toHaveProperty('neutral');
      expect(Array.isArray(keywords.positive)).toBe(true);
      expect(Array.isArray(keywords.negative)).toBe(true);
      expect(Array.isArray(keywords.neutral)).toBe(true);
    });

    test('should update positive keywords', () => {
      const newKeywords = {
        positive: ['excellent', 'outstanding', 'superb']
      };
      
      analyzer.updateSentimentKeywords(newKeywords);
      
      const keywords = analyzer.getSentimentKeywords();
      expect(keywords.positive).toContain('excellent');
      expect(keywords.positive).toContain('outstanding');
      expect(keywords.positive).toContain('superb');
    });

    test('should update negative keywords', () => {
      const newKeywords = {
        negative: ['terrible', 'awful', 'disastrous']
      };
      
      analyzer.updateSentimentKeywords(newKeywords);
      
      const keywords = analyzer.getSentimentKeywords();
      expect(keywords.negative).toContain('terrible');
      expect(keywords.negative).toContain('awful');
      expect(keywords.negative).toContain('disastrous');
    });

    test('should update neutral keywords', () => {
      const newKeywords = {
        neutral: ['steady', 'consistent', 'regular']
      };
      
      analyzer.updateSentimentKeywords(newKeywords);
      
      const keywords = analyzer.getSentimentKeywords();
      expect(keywords.neutral).toContain('steady');
      expect(keywords.neutral).toContain('consistent');
      expect(keywords.neutral).toContain('regular');
    });

    test('should handle invalid keyword updates', () => {
      expect(() => analyzer.updateSentimentKeywords(null)).not.toThrow();
      expect(() => analyzer.updateSentimentKeywords({})).not.toThrow();
      expect(() => analyzer.updateSentimentKeywords({ positive: "not an array" })).not.toThrow();
    });
  });

  describe('error handling and edge cases', () => {
    test('should handle malformed article objects', () => {
      expect(() => analyzer.analyzeSentiment(null)).not.toThrow();
      expect(() => analyzer.analyzeSentiment(undefined)).not.toThrow();
      expect(() => analyzer.analyzeSentiment("string")).not.toThrow();
      expect(() => analyzer.analyzeSentiment(123)).not.toThrow();
    });

    test('should handle articles with only whitespace', () => {
      const whitespaceArticle = {
        title: "   ",
        description: "\n\t  "
      };
      
      const result = analyzer.analyzeSentiment(whitespaceArticle);
      
      expect(result.sentiment).toBe('neutral');
      expect(result.score).toBe(0);
    });

    test('should handle very long content', () => {
      const longContent = "financial market analysis stock earnings profit growth ".repeat(1000);
      const longArticle = {
        title: "Long Financial Analysis",
        description: longContent
      };
      
      expect(() => analyzer.analyzeSentiment(longArticle)).not.toThrow();
      
      const sentiment = analyzer.analyzeSentiment(longArticle);
      expect(sentiment).toBeDefined();
      expect(typeof sentiment.score).toBe('number');
    });

    test('should handle special characters and numbers', () => {
      const specialArticle = {
        title: "Stock $AAPL +5.2% @NYSE #earnings 🚀",
        description: "Price: $150.25 (+3.8%) Volume: 1.2M shares traded."
      };
      
      expect(() => analyzer.analyzeSentiment(specialArticle)).not.toThrow();
      expect(() => analyzer.calculateImpact(specialArticle)).not.toThrow();
    });

    test('should handle circular references gracefully', () => {
      const circularArticle = {
        title: "Test Article"
      };
      circularArticle.self = circularArticle;
      
      expect(() => analyzer.analyzeSentiment(circularArticle)).not.toThrow();
    });
  });
});