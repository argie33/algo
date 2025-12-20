import { describe, it, expect, beforeEach } from 'vitest';
import NewsAnalyzer from '../../../utils/newsAnalyzer';

describe('NewsAnalyzer', () => {
  let analyzer;

  beforeEach(() => {
    analyzer = new NewsAnalyzer();
  });

  describe('sentiment analysis', () => {
    it('detects positive sentiment', () => {
      const positiveText = 'Strong growth and profits surge, stock rallies on breakthrough earnings beat';
      const result = analyzer.analyzeSentiment(positiveText);

      expect(result.score).toBeGreaterThan(0);
      expect(result.sentiment).toBe('positive');
    });

    it('detects negative sentiment', () => {
      const negativeText = 'Stock crashes, massive losses, company misses expectations badly';
      const result = analyzer.analyzeSentiment(negativeText);

      expect(result.score).toBeLessThan(0);
      expect(result.sentiment).toBe('negative');
    });

    it('detects neutral sentiment', () => {
      const neutralText = 'Company reports quarterly results, maintains guidance for next quarter';
      const result = analyzer.analyzeSentiment(neutralText);

      expect(Math.abs(result.score)).toBeLessThan(0.3);
      expect(result.sentiment).toBe('neutral');
    });

    it('handles empty text gracefully', () => {
      const result = analyzer.analyzeSentiment('');

      expect(result.score).toBe(0);
      expect(result.sentiment).toBe('neutral');
    });

    it('handles undefined input gracefully', () => {
      const result = analyzer.analyzeSentiment(undefined);

      expect(result.score).toBe(0);
      expect(result.sentiment).toBe('neutral');
    });
  });

  describe('keyword extraction', () => {
    it('extracts relevant financial keywords', () => {
      const text = 'Apple reports strong earnings, revenue up 15%, profit margins expanding';
      const keywords = analyzer.extractKeywords(text);

      expect(keywords).toContain('earnings');
      expect(keywords).toContain('revenue');
      expect(keywords).toContain('profit');
    });

    it('filters out common stop words', () => {
      const text = 'The company has been performing well in the market';
      const keywords = analyzer.extractKeywords(text);

      expect(keywords).not.toContain('the');
      expect(keywords).not.toContain('has');
      expect(keywords).not.toContain('been');
    });

    it('returns empty array for empty text', () => {
      const keywords = analyzer.extractKeywords('');
      expect(keywords).toEqual([]);
    });
  });

  describe('impact scoring', () => {
    it('assigns higher impact to major financial events', () => {
      const majorEvent = 'Apple announces stock split, revenue beats expectations by 20%';
      const minorEvent = 'Company schedules earnings call for next week';

      const majorImpact = analyzer.calculateImpact(majorEvent);
      const minorImpact = analyzer.calculateImpact(minorEvent);

      expect(majorImpact).toBeGreaterThan(minorImpact);
    });

    it('considers text length in impact calculation', () => {
      const longText = 'Detailed analysis of quarterly performance shows significant growth across all business segments with strong margin expansion and positive outlook for the remainder of the fiscal year';
      const shortText = 'Earnings beat';

      const longImpact = analyzer.calculateImpact(longText);
      const shortImpact = analyzer.calculateImpact(shortText);

      expect(longImpact).toBeGreaterThan(shortImpact);
    });
  });

  describe('symbol extraction', () => {
    it('extracts stock symbols from text', () => {
      const text = 'AAPL and MSFT both reported strong earnings, while TSLA missed expectations';
      const symbols = analyzer.extractSymbols(text);

      expect(symbols).toContain('AAPL');
      expect(symbols).toContain('MSFT');
      expect(symbols).toContain('TSLA');
    });

    it('handles mixed case symbols', () => {
      const text = 'aapl and Msft are performing well';
      const symbols = analyzer.extractSymbols(text);

      expect(symbols).toContain('AAPL');
      expect(symbols).toContain('MSFT');
    });

    it('returns empty array when no symbols found', () => {
      const text = 'General market commentary without specific companies';
      const symbols = analyzer.extractSymbols(text);

      expect(symbols).toEqual([]);
    });
  });

  describe('article categorization', () => {
    it('categorizes earnings-related articles', () => {
      const text = 'Quarterly earnings report shows revenue growth and profit margin expansion';
      const category = analyzer.categorizeArticle(text);

      expect(category).toBe('earnings');
    });

    it('categorizes market analysis articles', () => {
      const text = 'Technical analysis indicates potential breakout pattern in major indices';
      const category = analyzer.categorizeArticle(text);

      expect(category).toBe('analysis');
    });

    it('categorizes general news as default', () => {
      const text = 'Company announces new product launch in upcoming quarter';
      const category = analyzer.categorizeArticle(text);

      expect(category).toBe('general');
    });
  });
});