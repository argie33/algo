// Automated Testing Suite for Financial Services
// Tests for all major services and components

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import axios from 'axios';
import newsService from '../services/newsService';
import economicDataService from '../services/economicDataService';
import portfolioOptimizer from '../services/portfolioOptimizer';
import aiTradingSignals from '../services/aiTradingSignals';
import socialTradingService from '../services/socialTradingService';
import cacheService from '../services/cacheService';

// Mock axios
vi.mock('axios');
const mockedAxios = vi.mocked(axios);

describe('Financial Services Test Suite', () => {
  beforeEach(() => {
    // Clear all mocks before each test
    vi.clearAllMocks();
    cacheService.clear();
  });

  afterEach(() => {
    // Clean up after each test
    vi.restoreAllMocks();
  });

  describe('News Service', () => {
    it('should fetch news for symbols successfully', async () => {
      const mockNewsData = {
        news: [
          {
            id: '1',
            headline: 'Test News Headline',
            summary: 'Test news summary',
            symbols: ['AAPL'],
            created_at: new Date().toISOString(),
            url: 'https://example.com/news/1'
          }
        ]
      };

      mockedAxios.get.mockResolvedValueOnce({ data: mockNewsData });

      const result = await newsService.getNewsForSymbols(['AAPL'], { limit: 10 });

      expect(result).toHaveLength(1);
      expect(result[0]).toHaveProperty('headline', 'Test News Headline');
      expect(result[0]).toHaveProperty('sentiment');
      expect(result[0]).toHaveProperty('relevanceScore');
    });

    it('should handle API errors gracefully', async () => {
      mockedAxios.get.mockRejectedValueOnce(new Error('API Error'));

      const result = await newsService.getNewsForSymbols(['AAPL']);

      // Should return mock data when API fails
      expect(Array.isArray(result)).toBe(true);
      expect(result.length).toBeGreaterThan(0);
    });

    it('should analyze sentiment correctly', () => {
      const positiveArticle = {
        headline: 'Stock surges on strong earnings beat',
        summary: 'Company reports record profits and growth'
      };

      const sentiment = newsService.analyzeSentiment(positiveArticle);

      expect(sentiment).toHaveProperty('label');
      expect(sentiment).toHaveProperty('score');
      expect(sentiment).toHaveProperty('confidence');
      expect(['positive', 'negative', 'neutral']).toContain(sentiment.label);
    });

    it('should calculate relevance score for symbols', () => {
      const article = {
        headline: 'AAPL announces new iPhone',
        summary: 'Apple unveils latest smartphone',
        symbols: ['AAPL']
      };

      const relevance = newsService.calculateRelevance(article, ['AAPL']);

      expect(relevance).toBeGreaterThan(0);
      expect(relevance).toBeLessThanOrEqual(1);
    });

    it('should deduplicate similar articles', () => {
      const articles = [
        {
          id: '1',
          headline: 'Apple announces earnings',
          summary: 'Apple reports quarterly results',
          content: 'Full article content here'
        },
        {
          id: '2',
          headline: 'Apple announces earnings today',
          summary: 'Apple quarterly earnings announced',
          content: 'Different content'
        }
      ];

      const deduplicated = newsService.deduplicateNews(articles);

      expect(deduplicated).toHaveLength(1);
    });
  });

  describe('Economic Data Service', () => {
    it('should fetch economic indicators successfully', async () => {
      const mockData = {
        observations: [
          { date: '2024-01-01', value: '3.5' },
          { date: '2024-02-01', value: '3.7' }
        ]
      };

      mockedAxios.get.mockResolvedValueOnce({ data: mockData });

      const result = await economicDataService.getIndicator('gdpGrowth');

      expect(result).toHaveProperty('indicator', 'gdpGrowth');
      expect(result).toHaveProperty('data');
      expect(result.data).toHaveLength(2);
      expect(result.data[0]).toHaveProperty('value', 3.5);
    });

    it('should calculate trend correctly', () => {
      const increasingData = [
        { value: 1 }, { value: 2 }, { value: 3 }, { value: 4 }, { value: 5 }
      ];

      const trend = economicDataService.calculateTrend(increasingData);

      expect(trend).toBe('up');
    });

    it('should return dashboard data with all key indicators', async () => {
      const dashboard = await economicDataService.getDashboardData();

      expect(dashboard).toHaveProperty('gdpGrowth');
      expect(dashboard).toHaveProperty('cpiYoY');
      expect(dashboard).toHaveProperty('unemployment');
      expect(dashboard).toHaveProperty('fedFunds');
      expect(dashboard).toHaveProperty('treasury10Y');
      expect(dashboard).toHaveProperty('vix');

      // Each indicator should have required properties
      Object.values(dashboard).forEach(indicator => {
        expect(indicator).toHaveProperty('name');
        expect(indicator).toHaveProperty('value');
        expect(indicator).toHaveProperty('trend');
        expect(indicator).toHaveProperty('unit');
      });
    });

    it('should calculate yield curve with spread', async () => {
      const yieldCurve = await economicDataService.getYieldCurve();

      expect(yieldCurve).toHaveProperty('curve');
      expect(yieldCurve).toHaveProperty('spread');
      expect(yieldCurve).toHaveProperty('isInverted');
      expect(Array.isArray(yieldCurve.curve)).toBe(true);
      expect(yieldCurve.curve.length).toBeGreaterThan(0);
    });
  });

  describe('Portfolio Optimizer', () => {
    it('should optimize portfolio with valid symbols', async () => {
      const symbols = ['AAPL', 'MSFT', 'GOOGL'];
      
      const optimization = await portfolioOptimizer.optimizePortfolio(symbols, {
        method: 'maximum_sharpe'
      });

      expect(optimization).toHaveProperty('allocation');
      expect(optimization).toHaveProperty('metrics');
      expect(optimization).toHaveProperty('riskAnalysis');
      expect(optimization.allocation).toHaveLength(symbols.length);

      // Check that weights sum to approximately 1
      const totalWeight = optimization.allocation.reduce((sum, asset) => sum + asset.weight, 0);
      expect(totalWeight).toBeCloseTo(1.0, 2);

      // Check portfolio metrics
      expect(optimization.metrics).toHaveProperty('expectedReturn');
      expect(optimization.metrics).toHaveProperty('volatility');
      expect(optimization.metrics).toHaveProperty('sharpeRatio');
    });

    it('should apply portfolio constraints correctly', () => {
      const weights = [0.6, 0.3, 0.1]; // Violates max weight constraint
      const constraints = { maxWeight: 0.4, minWeight: 0.05 };

      const constrainedWeights = portfolioOptimizer.applyConstraints(weights, constraints);

      constrainedWeights.forEach(weight => {
        expect(weight).toBeLessThanOrEqual(constraints.maxWeight);
        expect(weight).toBeGreaterThanOrEqual(constraints.minWeight);
      });

      // Should still sum to 1
      const sum = constrainedWeights.reduce((a, b) => a + b, 0);
      expect(sum).toBeCloseTo(1.0, 2);
    });

    it('should calculate portfolio variance correctly', () => {
      const weights = [0.5, 0.3, 0.2];
      const covMatrix = [
        [0.04, 0.01, 0.02],
        [0.01, 0.09, 0.015],
        [0.02, 0.015, 0.16]
      ];

      const variance = portfolioOptimizer.calculatePortfolioVariance(weights, covMatrix);

      expect(variance).toBeGreaterThan(0);
      expect(typeof variance).toBe('number');
    });

    it('should calculate covariance between return series', () => {
      const returns1 = [0.01, 0.02, -0.01, 0.03, -0.02];
      const returns2 = [0.015, 0.025, -0.005, 0.02, -0.015];

      const covariance = portfolioOptimizer.covariance(returns1, returns2);

      expect(typeof covariance).toBe('number');
      expect(Math.abs(covariance)).toBeLessThan(1); // Reasonable bounds
    });

    it('should calculate efficient frontier', async () => {
      const symbols = ['AAPL', 'MSFT'];
      
      const frontier = await portfolioOptimizer.calculateEfficientFrontier(symbols, 5);

      expect(Array.isArray(frontier)).toBe(true);
      expect(frontier.length).toBeGreaterThan(0);
      
      frontier.forEach(point => {
        expect(point).toHaveProperty('return');
        expect(point).toHaveProperty('risk');
        expect(point).toHaveProperty('sharpe');
        expect(point).toHaveProperty('weights');
      });

      // Should be sorted by risk
      for (let i = 1; i < frontier.length; i++) {
        expect(frontier[i].risk).toBeGreaterThanOrEqual(frontier[i-1].risk);
      }
    });
  });

  describe('AI Trading Signals', () => {
    it('should generate trading signals for symbols', async () => {
      const symbols = ['AAPL', 'MSFT'];
      
      const result = await aiTradingSignals.generateSignals(symbols, {
        models: ['ensemble'],
        minConfidence: 0.5
      });

      expect(result).toHaveProperty('signals');
      expect(result).toHaveProperty('metadata');
      expect(Array.isArray(result.signals)).toBe(true);
      
      result.signals.forEach(signal => {
        expect(signal).toHaveProperty('symbol');
        expect(signal).toHaveProperty('signal');
        expect(signal).toHaveProperty('confidence');
        expect(signal).toHaveProperty('reasoning');
        expect(signal.confidence).toBeGreaterThanOrEqual(0.5);
        expect(['BUY', 'SELL', 'HOLD', 'STRONG_BUY', 'STRONG_SELL', 'NEUTRAL']).toContain(signal.signal);
      });
    });

    it('should convert signal to numerical value correctly', () => {
      expect(aiTradingSignals.signalToValue('STRONG_BUY')).toBe(2);
      expect(aiTradingSignals.signalToValue('BUY')).toBe(1);
      expect(aiTradingSignals.signalToValue('HOLD')).toBe(0);
      expect(aiTradingSignals.signalToValue('SELL')).toBe(-1);
      expect(aiTradingSignals.signalToValue('STRONG_SELL')).toBe(-2);
    });

    it('should convert value back to signal correctly', () => {
      expect(aiTradingSignals.valueToSignal(2)).toBe('STRONG_BUY');
      expect(aiTradingSignals.valueToSignal(1)).toBe('BUY');
      expect(aiTradingSignals.valueToSignal(0)).toBe('HOLD');
      expect(aiTradingSignals.valueToSignal(-1)).toBe('SELL');
      expect(aiTradingSignals.valueToSignal(-2)).toBe('STRONG_SELL');
    });

    it('should calculate RSI correctly', () => {
      const prices = [44, 44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.85, 47.25, 47.92, 46.23, 46.08, 46.03, 46.83, 47.69];
      
      const rsi = aiTradingSignals.calculateRSI(prices, 14);

      expect(Array.isArray(rsi)).toBe(true);
      expect(rsi.length).toBe(1); // Only one RSI value for 15 prices with 14-period
      expect(rsi[0]).toBeGreaterThan(0);
      expect(rsi[0]).toBeLessThan(100);
    });

    it('should calculate SMA correctly', () => {
      const prices = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
      
      const sma = aiTradingSignals.calculateSMA(prices, 3);

      expect(Array.isArray(sma)).toBe(true);
      expect(sma.length).toBe(8); // 10 - 3 + 1
      expect(sma[0]).toBe(2); // (1+2+3)/3
      expect(sma[1]).toBe(3); // (2+3+4)/3
    });

    it('should combine signals with proper weighting', () => {
      const signals = [
        { signal: 'BUY', confidence: 0.8 },
        { signal: 'STRONG_BUY', confidence: 0.9 },
        { signal: 'HOLD', confidence: 0.6 },
        { signal: 'BUY', confidence: 0.7 }
      ];

      const combined = aiTradingSignals.combineSignals(signals);

      expect(combined).toHaveProperty('final_signal');
      expect(combined).toHaveProperty('confidence');
      expect(combined).toHaveProperty('reasoning');
      expect(combined).toHaveProperty('consensus');
      expect(combined.confidence).toBeGreaterThan(0);
      expect(combined.confidence).toBeLessThanOrEqual(1);
    });
  });

  describe('Social Trading Service', () => {
    it('should fetch top traders leaderboard', async () => {
      const leaderboard = await socialTradingService.getTopTraders({ limit: 10 });

      expect(Array.isArray(leaderboard)).toBe(true);
      expect(leaderboard.length).toBeLessThanOrEqual(10);
      
      leaderboard.forEach(trader => {
        expect(trader).toHaveProperty('id');
        expect(trader).toHaveProperty('username');
        expect(trader).toHaveProperty('monthlyReturn');
        expect(trader).toHaveProperty('winRate');
        expect(trader).toHaveProperty('followers');
        expect(trader).toHaveProperty('rank');
        expect(trader.winRate).toBeGreaterThanOrEqual(0);
        expect(trader.winRate).toBeLessThanOrEqual(100);
      });

      // Should be sorted by monthly return
      for (let i = 1; i < leaderboard.length; i++) {
        expect(leaderboard[i].monthlyReturn).toBeLessThanOrEqual(leaderboard[i-1].monthlyReturn);
      }
    });

    it('should calculate trader rank correctly', () => {
      const rank1 = socialTradingService.calculateTraderRank(50);
      const rank2 = socialTradingService.calculateTraderRank(1000);
      const rank3 = socialTradingService.calculateTraderRank(10000);

      expect(rank1.rank).toBe('NOVICE');
      expect(rank2.rank).toBe('SILVER');
      expect(rank3.rank).toBe('DIAMOND');
    });

    it('should calculate risk score from trades', () => {
      const conservativeTrades = [
        { pnl: 10, entry_price: 100, return: 0.01 },
        { pnl: 5, entry_price: 100, return: 0.005 },
        { pnl: -2, entry_price: 100, return: -0.002 }
      ];

      const aggressiveTrades = [
        { pnl: 500, entry_price: 100, return: 0.5 },
        { pnl: -300, entry_price: 100, return: -0.3 },
        { pnl: 800, entry_price: 100, return: 0.8 }
      ];

      const conservativeRisk = socialTradingService.calculateRiskScore(conservativeTrades);
      const aggressiveRisk = socialTradingService.calculateRiskScore(aggressiveTrades);

      expect(conservativeRisk).toBeLessThan(aggressiveRisk);
      expect([1, 2, 3, 4]).toContain(conservativeRisk);
      expect([1, 2, 3, 4]).toContain(aggressiveRisk);
    });

    it('should get trader profile with complete information', async () => {
      const profile = await socialTradingService.getTraderProfile('trader_123');

      expect(profile).toHaveProperty('id', 'trader_123');
      expect(profile).toHaveProperty('username');
      expect(profile).toHaveProperty('bio');
      expect(profile).toHaveProperty('performanceHistory');
      expect(profile).toHaveProperty('sharpeRatio');
      expect(profile).toHaveProperty('maxDrawdown');
      expect(Array.isArray(profile.performanceHistory)).toBe(true);
      expect(profile.performanceHistory.length).toBe(12); // 12 months
    });

    it('should get community insights with sentiment data', async () => {
      const insights = await socialTradingService.getCommunityInsights('AAPL');

      expect(insights).toHaveProperty('symbol', 'AAPL');
      expect(insights).toHaveProperty('sentiment');
      expect(insights).toHaveProperty('trending');
      expect(insights).toHaveProperty('topTraders');
      expect(insights).toHaveProperty('priceTargets');

      // Sentiment percentages should sum to 100
      const { bullish, bearish, neutral } = insights.sentiment;
      const total = bullish + bearish + neutral;
      expect(total).toBeCloseTo(100, 1);
    });

    it('should get social trading statistics', async () => {
      const stats = await socialTradingService.getSocialStats();

      expect(stats).toHaveProperty('totalTraders');
      expect(stats).toHaveProperty('activeTraders');
      expect(stats).toHaveProperty('totalCopiers');
      expect(stats).toHaveProperty('totalVolume24h');
      expect(stats).toHaveProperty('topPerformers');
      expect(stats).toHaveProperty('trendingStrategies');
      expect(Array.isArray(stats.topPerformers)).toBe(true);
      expect(Array.isArray(stats.trendingStrategies)).toBe(true);
    });
  });

  describe('Cache Service', () => {
    it('should cache and retrieve data correctly', async () => {
      const testData = { message: 'test data' };
      const key = 'test_key';

      // Cache data
      const result1 = await cacheService.cacheApiCall(
        key,
        async () => testData,
        60000 // 1 minute TTL
      );

      expect(result1).toEqual(testData);

      // Should return cached data
      const result2 = await cacheService.cacheApiCall(
        key,
        async () => ({ message: 'new data' }), // Different data
        60000
      );

      expect(result2).toEqual(testData); // Should return cached version
    });

    it('should generate consistent cache keys', () => {
      const params1 = { symbol: 'AAPL', period: '1D' };
      const params2 = { period: '1D', symbol: 'AAPL' };

      const key1 = cacheService.generateKey('test', params1);
      const key2 = cacheService.generateKey('test', params2);

      expect(key1).toBe(key2); // Should be the same regardless of parameter order
    });

    it('should handle cache expiration', async () => {
      const key = 'expiring_key';
      let callCount = 0;

      const dataFetcher = async () => {
        callCount++;
        return { call: callCount };
      };

      // First call
      const result1 = await cacheService.cacheApiCall(key, dataFetcher, 10); // 10ms TTL

      expect(result1.call).toBe(1);

      // Wait for cache to expire
      await new Promise(resolve => setTimeout(resolve, 20));

      // Second call after expiration
      const result2 = await cacheService.cacheApiCall(key, dataFetcher, 10);

      expect(result2.call).toBe(2); // Should be a new call
    });
  });

  describe('Integration Tests', () => {
    it('should handle network failures gracefully across all services', async () => {
      // Mock network failure
      mockedAxios.get.mockRejectedValue(new Error('Network Error'));

      const services = [
        () => newsService.getNewsForSymbols(['AAPL']),
        () => economicDataService.getDashboardData(),
        () => portfolioOptimizer.optimizePortfolio(['AAPL', 'MSFT']),
        () => aiTradingSignals.generateSignals(['AAPL']),
        () => socialTradingService.getTopTraders()
      ];

      const results = await Promise.all(
        services.map(async (service) => {
          try {
            const result = await service();
            return { success: true, result };
          } catch (error) {
            return { success: false, error: error.message };
          }
        })
      );

      // All services should handle errors gracefully and return mock data
      results.forEach(({ success, result }) => {
        expect(success).toBe(true);
        expect(result).toBeDefined();
      });
    });

    it('should maintain consistent data formats across services', async () => {
      const newsData = await newsService.getNewsForSymbols(['AAPL']);
      const economicData = await economicDataService.getDashboardData();
      const portfolioData = await portfolioOptimizer.optimizePortfolio(['AAPL']);
      const signalsData = await aiTradingSignals.generateSignals(['AAPL']);
      const socialData = await socialTradingService.getTopTraders();

      // Check that all services return expected data structures
      expect(Array.isArray(newsData)).toBe(true);
      expect(typeof economicData).toBe('object');
      expect(portfolioData).toHaveProperty('allocation');
      expect(signalsData).toHaveProperty('signals');
      expect(Array.isArray(socialData)).toBe(true);

      // Check timestamp formats are consistent
      if (newsData.length > 0 && newsData[0].createdAt) {
        expect(newsData[0].createdAt).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/);
      }
    });

    it('should handle concurrent requests efficiently', async () => {
      const startTime = Date.now();

      // Make multiple concurrent requests
      const promises = [
        newsService.getNewsForSymbols(['AAPL']),
        economicDataService.getDashboardData(),
        portfolioOptimizer.optimizePortfolio(['AAPL', 'MSFT']),
        aiTradingSignals.generateSignals(['AAPL']),
        socialTradingService.getTopTraders()
      ];

      const results = await Promise.all(promises);

      const endTime = Date.now();
      const duration = endTime - startTime;

      // All requests should complete
      expect(results).toHaveLength(5);
      results.forEach(result => {
        expect(result).toBeDefined();
      });

      // Should complete in reasonable time (less than 5 seconds)
      expect(duration).toBeLessThan(5000);
    });
  });
});

// Performance benchmarks
describe('Performance Tests', () => {
  it('should complete portfolio optimization within time limit', async () => {
    const startTime = Date.now();
    
    await portfolioOptimizer.optimizePortfolio(['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA']);
    
    const duration = Date.now() - startTime;
    expect(duration).toBeLessThan(2000); // Should complete within 2 seconds
  });

  it('should handle large dataset efficiently', async () => {
    const symbols = Array.from({ length: 20 }, (_, i) => `STOCK${i + 1}`);
    const startTime = Date.now();
    
    const signals = await aiTradingSignals.generateSignals(symbols);
    
    const duration = Date.now() - startTime;
    expect(duration).toBeLessThan(3000); // Should complete within 3 seconds
    expect(signals.signals.length).toBeGreaterThan(0);
  });

  it('should cache results to improve performance', async () => {
    const key = 'performance_test';
    let fetchCount = 0;
    
    const fetcher = async () => {
      fetchCount++;
      await new Promise(resolve => setTimeout(resolve, 100)); // Simulate API delay
      return { data: 'test', fetchCount };
    };

    // First call (should hit API)
    const start1 = Date.now();
    const result1 = await cacheService.cacheApiCall(key, fetcher, 60000);
    const duration1 = Date.now() - start1;

    // Second call (should use cache)
    const start2 = Date.now();
    const result2 = await cacheService.cacheApiCall(key, fetcher, 60000);
    const duration2 = Date.now() - start2;

    expect(fetchCount).toBe(1); // Should only fetch once
    expect(result1).toEqual(result2); // Results should be identical
    expect(duration2).toBeLessThan(duration1); // Cached call should be faster
    expect(duration2).toBeLessThan(10); // Cached call should be very fast
  });
});