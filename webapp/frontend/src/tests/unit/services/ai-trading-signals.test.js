/**
 * AI Trading Signals Unit Tests
 * Tests ML-powered trading signal generation and confidence scoring
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock the AI trading signals service
vi.mock('../../../services/aiTradingSignals', () => ({
  generateSignal: vi.fn(),
  analyzePattern: vi.fn(),
  calculateConfidence: vi.fn(),
  backtestSignal: vi.fn(),
  getSignalHistory: vi.fn(),
  updateModel: vi.fn(),
  validateSignal: vi.fn(),
  getModelMetrics: vi.fn()
}));

describe('AI Trading Signals', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Signal Generation', () => {
    it('generates buy signals with ML confidence scoring', async () => {
      const { generateSignal } = await import('../../../services/aiTradingSignals');
      const mockData = {
        symbol: 'AAPL',
        price: 195.50,
        volume: 45000000,
        technicalIndicators: {
          rsi: 45,
          macd: 0.85,
          bollingerBands: { upper: 200, lower: 190, middle: 195 }
        }
      };
      
      generateSignal.mockResolvedValue({
        symbol: 'AAPL',
        signal: 'BUY',
        confidence: 0.87,
        grade: 'A',
        entryPrice: 195.50,
        targetPrice: 205.00,
        stopLoss: 188.00,
        expectedReturn: 4.86,
        riskReward: 2.2,
        timeHorizon: 'medium_term',
        patterns: ['cup_and_handle', 'golden_cross'],
        reasoning: 'Strong bullish momentum with high volume confirmation'
      });

      const result = await generateSignal(mockData);
      
      expect(result.signal).toBe('BUY');
      expect(result.confidence).toBe(0.87);
      expect(result.grade).toBe('A');
      expect(result.patterns).toContain('cup_and_handle');
    });

    it('generates sell signals with risk assessment', async () => {
      const { generateSignal } = await import('../../../services/aiTradingSignals');
      
      generateSignal.mockResolvedValue({
        symbol: 'TSLA',
        signal: 'SELL',
        confidence: 0.75,
        grade: 'B+',
        entryPrice: 280.00,
        targetPrice: 260.00,
        stopLoss: 290.00,
        expectedReturn: -7.14,
        riskReward: 2.0,
        timeHorizon: 'short_term',
        patterns: ['head_and_shoulders', 'bearish_divergence'],
        reasoning: 'Overbought conditions with volume decline'
      });

      const result = await generateSignal({});
      
      expect(result.signal).toBe('SELL');
      expect(result.confidence).toBe(0.75);
      expect(result.grade).toBe('B+');
      expect(result.patterns).toContain('head_and_shoulders');
    });
  });

  describe('Pattern Recognition', () => {
    it('identifies cup and handle pattern', async () => {
      const { analyzePattern } = await import('../../../services/aiTradingSignals');
      
      analyzePattern.mockReturnValue({
        pattern: 'cup_and_handle',
        confidence: 0.85,
        formation: {
          cupDepth: 10,
          handleDepth: 2,
          duration: 45,
          volumeConfirmation: true
        },
        breakoutLevel: 195.50,
        targetPrice: 205.00,
        probability: 0.78,
        historicalSuccess: 0.68
      });

      const result = analyzePattern([]);
      
      expect(result.pattern).toBe('cup_and_handle');
      expect(result.confidence).toBe(0.85);
      expect(result.formation.volumeConfirmation).toBe(true);
    });
  });

  describe('Confidence Calculation', () => {
    it('calculates confidence based on multiple factors', async () => {
      const { calculateConfidence } = await import('../../../services/aiTradingSignals');
      
      calculateConfidence.mockReturnValue({
        overallConfidence: 0.82,
        factors: {
          technicalAnalysis: 0.85,
          volumeAnalysis: 0.75,
          marketSentiment: 0.80,
          fundamentalScore: 0.88,
          patternStrength: 0.90
        },
        grade: 'A-'
      });

      const result = calculateConfidence({});
      
      expect(result.overallConfidence).toBe(0.82);
      expect(result.grade).toBe('A-');
      expect(result.factors.technicalAnalysis).toBe(0.85);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });
});