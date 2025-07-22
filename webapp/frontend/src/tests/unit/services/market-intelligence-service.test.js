/**
 * Market Intelligence Service Tests
 * Tests real market intelligence data fetching and fallback logic
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import marketIntelligenceService from '../../../services/marketIntelligenceService';

// Mock the API service
vi.mock('../../../services/api', () => ({
  apiRequest: vi.fn()
}));

describe('MarketIntelligenceService', () => {
  beforeEach(() => {
    // Clear cache before each test
    marketIntelligenceService.clearCache();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('getMarketIntelligence', () => {
    it('should fetch real market intelligence data successfully', async () => {
      const { apiRequest } = await import('../../../services/api');
      
      // Mock successful API responses
      apiRequest
        .mockResolvedValueOnce({
          success: true,
          data: { sentimentScore: 75, confidence: 0.8, trend: 'positive' }
        })
        .mockResolvedValueOnce({
          success: true,
          data: { momentumScore: 65, rsi: 60, macd: { signal: 'bullish' } }
        })
        .mockResolvedValueOnce({
          success: true,
          data: { positioningScore: 55, institutionalFlow: 0.2 }
        });

      const result = await marketIntelligenceService.getMarketIntelligence('AAPL');

      expect(result).toMatchObject({
        sentiment: {
          score: 75,
          confidence: 0.8,
          trend: 'positive'
        },
        momentum: {
          score: 65,
          rsi: 60,
          macd: { signal: 'bullish' }
        },
        positioning: {
          score: 55,
          institutionalFlow: 0.2
        },
        isMockData: false
      });

      expect(apiRequest).toHaveBeenCalledTimes(3);
      expect(apiRequest).toHaveBeenCalledWith('/market/sentiment/AAPL');
      expect(apiRequest).toHaveBeenCalledWith('/market/momentum/AAPL');
      expect(apiRequest).toHaveBeenCalledWith('/market/positioning/AAPL');
    });

    it('should use cached data when available', async () => {
      const { apiRequest } = await import('../../../services/api');
      
      // Mock successful API responses for first call
      apiRequest
        .mockResolvedValue({
          success: true,
          data: { sentimentScore: 75, confidence: 0.8 }
        });

      // First call
      const result1 = await marketIntelligenceService.getMarketIntelligence('AAPL');
      
      // Second call should use cache
      const result2 = await marketIntelligenceService.getMarketIntelligence('AAPL');

      expect(result1).toEqual(result2);
      expect(apiRequest).toHaveBeenCalledTimes(3); // Only called once for first request
    });

    it('should fallback to calculated scores when API fails', async () => {
      const { apiRequest } = await import('../../../services/api');
      
      // Mock API failure
      apiRequest.mockRejectedValue(new Error('API Error'));

      const result = await marketIntelligenceService.getMarketIntelligence('AAPL');

      expect(result).toMatchObject({
        sentiment: {
          score: 50,
          confidence: 0.3,
          sources: ['fallback'],
          trend: 'neutral'
        },
        momentum: {
          score: 50,
          rsi: 50,
          macd: { signal: 'neutral' }
        },
        positioning: {
          score: 50,
          institutionalFlow: 0
        },
        isMockData: false,
        isCalculated: true
      });
    });

    it('should calculate technical sentiment from price data', async () => {
      const { apiRequest } = await import('../../../services/api');
      
      // Mock sentiment API failure but quotes API success
      apiRequest
        .mockRejectedValueOnce(new Error('Sentiment API Error'))
        .mockRejectedValueOnce(new Error('Momentum API Error'))
        .mockRejectedValueOnce(new Error('Positioning API Error'))
        .mockResolvedValueOnce({
          success: true,
          data: {
            current_price: 150,
            previous_close: 145,
            volume: 1000000,
            avg_volume: 800000
          }
        });

      const result = await marketIntelligenceService.getMarketIntelligence('AAPL');

      expect(result.sentiment.score).toBeGreaterThan(50); // Should be positive due to price increase
      expect(result.sentiment.calculation).toBe('price_volume_based');
    });

    it('should calculate technical momentum from price history', async () => {
      const { apiRequest } = await import('../../../services/api');
      
      // Mock all APIs to fail except history
      apiRequest
        .mockRejectedValue(new Error('API Error'))
        .mockResolvedValueOnce({
          success: true,
          data: Array.from({ length: 20 }, (_, i) => ({
            close: 100 + i // Upward trend
          }))
        });

      const result = await marketIntelligenceService.getMarketIntelligence('AAPL');

      expect(result.momentum.score).toBeGreaterThan(50); // Should be positive due to upward trend
      expect(result.momentum.calculation).toBe('technical_analysis');
    });

    it('should handle invalid or missing data gracefully', async () => {
      const { apiRequest } = await import('../../../services/api');
      
      // Mock API returning invalid data
      apiRequest.mockResolvedValue({
        success: true,
        data: null
      });

      const result = await marketIntelligenceService.getMarketIntelligence('AAPL');

      expect(result).toMatchObject({
        sentiment: expect.objectContaining({ score: expect.any(Number) }),
        momentum: expect.objectContaining({ score: expect.any(Number) }),
        positioning: expect.objectContaining({ score: expect.any(Number) })
      });

      expect(result.sentiment.score).toBeGreaterThanOrEqual(0);
      expect(result.sentiment.score).toBeLessThanOrEqual(100);
    });

    it('should validate score ranges', async () => {
      const { apiRequest } = await import('../../../services/api');
      
      // Mock API returning extreme values
      apiRequest
        .mockResolvedValueOnce({
          success: true,
          data: { sentimentScore: 150 } // Over 100
        })
        .mockResolvedValueOnce({
          success: true,
          data: { momentumScore: -50 } // Under 0
        })
        .mockResolvedValueOnce({
          success: true,
          data: { positioningScore: 75 }
        });

      const result = await marketIntelligenceService.getMarketIntelligence('AAPL');

      // Scores should be clamped to 0-100 range
      expect(result.sentiment.score).toBe(100);
      expect(result.momentum.score).toBe(0);
      expect(result.positioning.score).toBe(75);
    });
  });

  describe('RSI calculation', () => {
    it('should calculate RSI correctly', () => {
      const prices = [100, 102, 101, 103, 104, 102, 105, 107, 106, 108, 110, 109, 111, 112, 110, 113];
      const rsi = marketIntelligenceService.calculateRSI(prices, 14);
      
      expect(rsi).toBeGreaterThan(0);
      expect(rsi).toBeLessThan(100);
      expect(rsi).toBeGreaterThan(50); // Should be above 50 for upward trend
    });

    it('should return 50 for insufficient data', () => {
      const prices = [100, 102];
      const rsi = marketIntelligenceService.calculateRSI(prices, 14);
      
      expect(rsi).toBe(50);
    });
  });

  describe('Price momentum calculation', () => {
    it('should calculate positive momentum for upward trend', () => {
      const prices = [100, 105, 110, 115];
      const momentum = marketIntelligenceService.calculatePriceMomentum(prices);
      
      expect(momentum).toBeGreaterThan(0);
      expect(momentum).toBe(0.15); // 15% gain
    });

    it('should calculate negative momentum for downward trend', () => {
      const prices = [100, 95, 90, 85];
      const momentum = marketIntelligenceService.calculatePriceMomentum(prices);
      
      expect(momentum).toBeLessThan(0);
      expect(momentum).toBe(-0.15); // 15% loss
    });

    it('should return 0 for insufficient data', () => {
      const prices = [100];
      const momentum = marketIntelligenceService.calculatePriceMomentum(prices);
      
      expect(momentum).toBe(0);
    });
  });

  describe('Cache management', () => {
    it('should clear cache successfully', async () => {
      const { apiRequest } = await import('../../../services/api');
      
      apiRequest.mockResolvedValue({
        success: true,
        data: { sentimentScore: 75 }
      });

      // First call
      await marketIntelligenceService.getMarketIntelligence('AAPL');
      
      // Clear cache
      marketIntelligenceService.clearCache();
      
      // Second call should hit API again
      await marketIntelligenceService.getMarketIntelligence('AAPL');
      
      expect(apiRequest).toHaveBeenCalledTimes(6); // 3 calls each time
    });
  });
});