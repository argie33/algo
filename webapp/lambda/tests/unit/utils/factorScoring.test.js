/**
 * Unit tests for FactorScoring
 */

// Mock logger
const mockLogger = {
  error: jest.fn(),
  warn: jest.fn(),
  info: jest.fn()
};
jest.mock('../../../utils/logger', () => mockLogger);

const {
  FactorScoringEngine,
  calculateCompositeScore,
  scoreUniverse,
  getFactorExplanations,
  getFactorDefinitions,
  createCustomProfile,
  screenByFactors,
  FACTOR_DEFINITIONS
} = require('../../../utils/factorScoring');

describe('FactorScoringEngine', () => {
  let engine;
  
  beforeEach(() => {
    jest.clearAllMocks();
    engine = new FactorScoringEngine();
  });

  describe('constructor', () => {
    test('should initialize with default factors', () => {
      const defaultEngine = new FactorScoringEngine();
      expect(defaultEngine.factors).toBe(FACTOR_DEFINITIONS);
      expect(defaultEngine.universeStats).toBeInstanceOf(Map);
    });

    test('should initialize with custom factors', () => {
      const customFactors = {
        custom: {
          name: 'Custom',
          weight: 1.0,
          factors: {
            custom_metric: { weight: 1.0 }
          }
        }
      };
      
      const customEngine = new FactorScoringEngine(customFactors);
      expect(customEngine.factors).toBe(customFactors);
    });
  });

  describe('calculateCompositeScore', () => {
    const sampleStock = {
      symbol: 'AAPL',
      pe_ratio: 15.5,
      pb_ratio: 2.3,
      revenue_growth_1y: 0.15,
      roe: 0.25,
      debt_to_equity: 0.4
    };

    test('should calculate composite score for valid stock data', () => {
      const result = engine.calculateCompositeScore(sampleStock);

      expect(result).toEqual({
        compositeScore: expect.any(Number),
        categoryScores: expect.any(Object),
        rank: null,
        percentile: null
      });

      expect(result.compositeScore).toBeGreaterThanOrEqual(0);
      expect(result.compositeScore).toBeLessThanOrEqual(1);
    });

    test('should calculate score with universe data for percentile ranking', () => {
      const universeData = [
        sampleStock,
        { symbol: 'GOOGL', pe_ratio: 20.0, pb_ratio: 3.0, revenue_growth_1y: 0.20, roe: 0.18, debt_to_equity: 0.2 },
        { symbol: 'MSFT', pe_ratio: 25.0, pb_ratio: 4.0, revenue_growth_1y: 0.10, roe: 0.30, debt_to_equity: 0.3 }
      ];

      const result = engine.calculateCompositeScore(sampleStock, universeData);

      expect(result.compositeScore).toBeGreaterThan(0);
      expect(result.categoryScores).toHaveProperty('value');
      expect(result.categoryScores).toHaveProperty('growth');
      expect(result.categoryScores).toHaveProperty('profitability');
    });

    test('should handle missing data gracefully', () => {
      const incompleteStock = {
        symbol: 'TEST',
        pe_ratio: 15.0
        // Missing most metrics
      };

      const result = engine.calculateCompositeScore(incompleteStock);

      expect(result.compositeScore).toBeGreaterThanOrEqual(0);
      expect(result.categoryScores).toBeDefined();
    });

    test('should handle null stock data', () => {
      const result = engine.calculateCompositeScore(null);
      expect(result).toBeNull();
    });

    test('should handle errors gracefully', () => {
      // Create a stock with invalid data that might cause errors
      const invalidStock = {
        pe_ratio: 'invalid',
        pb_ratio: undefined,
        revenue_growth_1y: null
      };

      const result = engine.calculateCompositeScore(invalidStock);

      expect(result.compositeScore).toBeDefined();
      expect(mockLogger.error).not.toHaveBeenCalled(); // Should handle without erroring
    });

    test('should handle calculation errors', () => {
      // Mock calculateCategoryScore to throw an error
      const originalMethod = engine.calculateCategoryScore;
      engine.calculateCategoryScore = jest.fn(() => {
        throw new Error('Category calculation failed');
      });

      const result = engine.calculateCompositeScore(sampleStock);

      expect(result).toBeNull();
      expect(mockLogger.error).toHaveBeenCalledWith(
        'Composite score calculation error',
        expect.objectContaining({
          error: expect.any(Error),
          symbol: 'AAPL'
        })
      );

      // Restore
      engine.calculateCategoryScore = originalMethod;
    });
  });

  describe('calculateCategoryScore', () => {
    const categoryDef = {
      factors: {
        pe_ratio: { weight: 0.5, inverse: true },
        pb_ratio: { weight: 0.5, inverse: true }
      }
    };

    test('should calculate category score with valid factors', () => {
      const stockData = {
        pe_ratio: 15.0,
        pb_ratio: 2.0
      };

      const result = engine.calculateCategoryScore(stockData, categoryDef);

      expect(result).toBeGreaterThan(0);
      expect(result).toBeLessThanOrEqual(1);
    });

    test('should return null with no valid factors', () => {
      const stockData = {
        invalid_factor: 15.0
      };

      const result = engine.calculateCategoryScore(stockData, categoryDef);

      expect(result).toBeNull();
    });

    test('should handle null and undefined values', () => {
      const stockData = {
        pe_ratio: null,
        pb_ratio: undefined
      };

      const result = engine.calculateCategoryScore(stockData, categoryDef);

      expect(result).toBeNull();
    });

    test('should handle NaN values', () => {
      const stockData = {
        pe_ratio: NaN,
        pb_ratio: 2.0
      };

      const result = engine.calculateCategoryScore(stockData, categoryDef);

      expect(result).toBeGreaterThan(0); // Should use pb_ratio only
    });
  });

  describe('calculatePercentileScore', () => {
    const universeData = [
      { pe_ratio: 10.0 },
      { pe_ratio: 15.0 },
      { pe_ratio: 20.0 },
      { pe_ratio: 25.0 },
      { pe_ratio: 30.0 }
    ];

    test('should calculate percentile score correctly', () => {
      const result = engine.calculatePercentileScore(20.0, 'pe_ratio', universeData, false);

      expect(result).toBeGreaterThanOrEqual(0);
      expect(result).toBeLessThanOrEqual(1);
    });

    test('should invert percentile for inverse factors', () => {
      const normal = engine.calculatePercentileScore(20.0, 'pe_ratio', universeData, false);
      const inverse = engine.calculatePercentileScore(20.0, 'pe_ratio', universeData, true);

      expect(normal + inverse).toBeCloseTo(1.0, 5);
    });

    test('should fall back to absolute score with insufficient data', () => {
      const smallUniverse = [{ pe_ratio: 15.0 }];
      
      const result = engine.calculatePercentileScore(15.0, 'pe_ratio', smallUniverse);

      expect(result).toBeGreaterThanOrEqual(0);
      expect(result).toBeLessThanOrEqual(1);
    });

    test('should handle errors gracefully', () => {
      // Mock sort to throw an error
      const originalSort = Array.prototype.sort;
      Array.prototype.sort = jest.fn(() => {
        throw new Error('Sort failed');
      });

      const result = engine.calculatePercentileScore(20.0, 'pe_ratio', universeData);

      expect(result).toBeGreaterThanOrEqual(0);
      expect(mockLogger.warn).toHaveBeenCalledWith(
        'Percentile score calculation error',
        expect.objectContaining({
          error: expect.any(Error),
          factorName: 'pe_ratio',
          value: 20.0
        })
      );

      // Restore
      Array.prototype.sort = originalSort;
    });
  });

  describe('calculateAbsoluteScore', () => {
    test('should score using predefined ranges', () => {
      const peScore = engine.calculateAbsoluteScore(15.0, 'pe_ratio');
      expect(peScore).toBe(0.8); // 15 is in 10-15 range = 80 score

      const roeScore = engine.calculateAbsoluteScore(0.25, 'roe');
      expect(roeScore).toBe(1.0); // 25% ROE gets top score
    });

    test('should use linear score for unknown factors', () => {
      const result = engine.calculateAbsoluteScore(0.5, 'unknown_factor');

      expect(result).toBeGreaterThanOrEqual(0);
      expect(result).toBeLessThanOrEqual(1);
    });

    test('should return default score when no range matches', () => {
      const result = engine.calculateAbsoluteScore(-999, 'pe_ratio');
      expect(result).toBe(0.5);
    });
  });

  describe('getFactorScoringRanges', () => {
    test('should return ranges for known factors', () => {
      const peRanges = engine.getFactorScoringRanges('pe_ratio');
      expect(Array.isArray(peRanges)).toBe(true);
      expect(peRanges.length).toBeGreaterThan(0);
      expect(peRanges[0]).toHaveProperty('min');
      expect(peRanges[0]).toHaveProperty('max');
      expect(peRanges[0]).toHaveProperty('score');
    });

    test('should return null for unknown factors', () => {
      const result = engine.getFactorScoringRanges('unknown_factor');
      expect(result).toBeNull();
    });
  });

  describe('linearScore', () => {
    test('should calculate sigmoid-based score', () => {
      const result = engine.linearScore(5.0);

      expect(result).toBeGreaterThanOrEqual(0);
      expect(result).toBeLessThanOrEqual(1);
    });

    test('should invert score when inverse is true', () => {
      const normal = engine.linearScore(5.0, false);
      const inverse = engine.linearScore(5.0, true);

      expect(normal + inverse).toBeCloseTo(1.0, 10);
    });
  });

  describe('scoreUniverse', () => {
    const universeData = [
      { symbol: 'AAPL', pe_ratio: 15.0, roe: 0.25, revenue_growth_1y: 0.15 },
      { symbol: 'GOOGL', pe_ratio: 20.0, roe: 0.18, revenue_growth_1y: 0.20 },
      { symbol: 'MSFT', pe_ratio: 25.0, roe: 0.30, revenue_growth_1y: 0.10 }
    ];

    test('should score and rank universe', () => {
      const result = engine.scoreUniverse(universeData);

      expect(Array.isArray(result)).toBe(true);
      expect(result.length).toBe(3);

      // Check sorted by score (descending)
      for (let i = 1; i < result.length; i++) {
        expect(result[i-1].factorScore.compositeScore)
          .toBeGreaterThanOrEqual(result[i].factorScore.compositeScore);
      }

      // Check ranks assigned
      result.forEach((stock, index) => {
        expect(stock.factorScore.rank).toBe(index + 1);
        expect(stock.factorScore.percentile).toBeGreaterThan(0);
        expect(stock.factorScore.percentile).toBeLessThanOrEqual(100);
      });
    });

    test('should apply custom weights', () => {
      const customWeights = {
        value: 0.5,
        growth: 0.3,
        profitability: 0.2
      };

      const result = engine.scoreUniverse(universeData, customWeights);

      expect(result.length).toBe(3);
      // Weights are normalized, so check relative proportion instead
      expect(engine.factors.value.weight).toBeGreaterThan(engine.factors.growth.weight);
    });

    test('should handle empty universe', () => {
      const result = engine.scoreUniverse([]);
      expect(result).toEqual([]);
    });

    test('should handle null universe', () => {
      const result = engine.scoreUniverse(null);
      expect(result).toEqual([]);
    });

    test('should handle scoring errors', () => {
      // Mock calculateCompositeScore to throw error for first stock
      const originalMethod = engine.calculateCompositeScore;
      let callCount = 0;
      engine.calculateCompositeScore = jest.fn((stock, universe) => {
        if (callCount++ === 0) {
          throw new Error('Scoring failed');
        }
        return originalMethod.call(engine, stock, universe);
      });

      expect(() => engine.scoreUniverse(universeData)).toThrow();
      expect(mockLogger.error).toHaveBeenCalledWith(
        'Universe scoring error',
        expect.objectContaining({
          error: expect.any(Error)
        })
      );

      // Restore
      engine.calculateCompositeScore = originalMethod;
    });
  });

  describe('applyCustomWeights', () => {
    test('should apply and normalize custom weights', () => {
      const customWeights = {
        value: 0.6,
        growth: 0.4
      };

      engine.applyCustomWeights(customWeights);

      // Weights should be normalized to sum to 1
      const totalWeight = Object.values(engine.factors).reduce((sum, cat) => sum + cat.weight, 0);
      expect(totalWeight).toBeCloseTo(1.0, 5);
    });

    test('should ignore unknown categories', () => {
      const customWeights = {
        unknown_category: 0.5,
        value: 0.5
      };

      engine.applyCustomWeights(customWeights);

      expect(engine.factors.unknown_category).toBeUndefined();
      expect(engine.factors.value.weight).toBeGreaterThan(0);
    });

    test('should handle zero total weight', () => {
      // Set all weights to 0
      Object.values(engine.factors).forEach(cat => cat.weight = 0);
      
      engine.applyCustomWeights({ value: 0 });

      // Should not divide by zero
      Object.values(engine.factors).forEach(cat => {
        expect(isNaN(cat.weight)).toBe(false);
      });
    });
  });

  describe('getFactorExplanations', () => {
    const stockData = {
      pe_ratio: 15.0,
      roe: 0.25,
      revenue_growth_1y: 0.15
    };

    test('should provide detailed factor explanations', () => {
      const result = engine.getFactorExplanations(stockData);

      expect(result).toHaveProperty('value');
      expect(result).toHaveProperty('profitability');
      expect(result).toHaveProperty('growth');

      const valueExplanation = result.value;
      expect(valueExplanation).toHaveProperty('name');
      expect(valueExplanation).toHaveProperty('description');
      expect(valueExplanation).toHaveProperty('weight');
      expect(valueExplanation).toHaveProperty('factors');

      if (valueExplanation.factors.length > 0) {
        const factor = valueExplanation.factors[0];
        expect(factor).toHaveProperty('factor');
        expect(factor).toHaveProperty('value');
        expect(factor).toHaveProperty('score');
        expect(factor).toHaveProperty('weight');
        expect(factor).toHaveProperty('interpretation');
      }
    });

    test('should skip null and undefined values', () => {
      const stockWithNulls = {
        pe_ratio: null,
        roe: undefined,
        revenue_growth_1y: 0.15
      };

      const result = engine.getFactorExplanations(stockWithNulls);

      expect(result.growth.factors.length).toBe(1); // Only revenue_growth_1y
    });
  });

  describe('interpretFactorScore', () => {
    test('should provide correct interpretations', () => {
      expect(engine.interpretFactorScore('pe_ratio', 10, 90)).toBe('Excellent');
      expect(engine.interpretFactorScore('pe_ratio', 15, 75)).toBe('Good');
      expect(engine.interpretFactorScore('pe_ratio', 20, 65)).toBe('Above Average');
      expect(engine.interpretFactorScore('pe_ratio', 25, 45)).toBe('Average');
      expect(engine.interpretFactorScore('pe_ratio', 30, 35)).toBe('Below Average');
      expect(engine.interpretFactorScore('pe_ratio', 40, 20)).toBe('Poor');
    });
  });

  describe('getFactorDefinitions', () => {
    test('should return current factor definitions', () => {
      const result = engine.getFactorDefinitions();

      expect(result).toBe(engine.factors);
      expect(result).toHaveProperty('value');
      expect(result).toHaveProperty('growth');
      expect(result).toHaveProperty('profitability');
    });
  });

  describe('createCustomProfile', () => {
    test('should create custom profile with metadata', () => {
      const weights = { value: 0.5, growth: 0.5 };
      const result = engine.createCustomProfile('Growth Focus', weights, 'Emphasizes growth metrics');

      expect(result).toEqual({
        name: 'Growth Focus',
        description: 'Emphasizes growth metrics',
        weights: weights,
        created_at: expect.stringMatching(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/)
      });
    });

    test('should handle empty description', () => {
      const result = engine.createCustomProfile('Test Profile', { value: 1.0 });

      expect(result.name).toBe('Test Profile');
      expect(result.description).toBe('');
    });
  });

  describe('rankUniverse', () => {
    const universeData = [
      { symbol: 'AAPL', pe_ratio: 15.0, roe: 0.25 },
      { symbol: 'GOOGL', pe_ratio: 20.0, roe: 0.18 },
      { symbol: 'MSFT', pe_ratio: 25.0, roe: 0.30 }
    ];

    test('should rank universe with accessible properties', () => {
      const result = engine.rankUniverse(universeData);

      expect(result.length).toBe(3);
      
      result.forEach((stock, index) => {
        expect(stock.rank).toBe(index + 1);
        expect(stock.compositeScore).toBeDefined();
        expect(stock.percentile).toBeDefined();
        expect(stock.categoryScores).toBeDefined();
      });
    });

    test('should handle empty universe in rankUniverse', () => {
      const result = engine.rankUniverse([]);
      expect(result).toEqual([]);
    });
  });

  describe('calculateUniverseStats', () => {
    const universeData = [
      { pe_ratio: 10.0, roe: 0.20 },
      { pe_ratio: 15.0, roe: 0.25 },
      { pe_ratio: 20.0, roe: 0.30 }
    ];

    test('should calculate comprehensive statistics', () => {
      const result = engine.calculateUniverseStats(universeData);

      expect(result).toBeInstanceOf(Map);
      expect(result.has('pe_ratio')).toBe(true);
      expect(result.has('roe')).toBe(true);

      const peStats = result.get('pe_ratio');
      expect(peStats).toEqual({
        min: 10.0,
        max: 20.0,
        median: 15.0,
        mean: 15.0,
        std: expect.any(Number),
        count: 3
      });
    });

    test('should skip factors with no valid data', () => {
      const sparseData = [
        { pe_ratio: null, roe: 0.25 },
        { pe_ratio: undefined, roe: null }
      ];

      const result = engine.calculateUniverseStats(sparseData);

      expect(result.has('pe_ratio')).toBe(false);
      expect(result.has('roe')).toBe(true); // One valid value: 0.25
    });
  });

  describe('analyzeFactors', () => {
    const universeData = [
      { pe_ratio: 10.0, roe: 0.20, revenue_growth_1y: 0.10 },
      { pe_ratio: 15.0, roe: 0.25, revenue_growth_1y: 0.15 },
      { pe_ratio: 20.0, roe: 0.30, revenue_growth_1y: 0.20 }
    ];

    test('should provide comprehensive factor analysis', () => {
      const result = engine.analyzeFactors(universeData);

      expect(result).toHaveProperty('factorStats');
      expect(result).toHaveProperty('correlations');
      expect(result).toHaveProperty('distributions');
      expect(result).toHaveProperty('sampleSize', 3);

      expect(result.factorStats.pe_ratio).toBeDefined();
      expect(result.correlations.pe_ratio).toBeDefined();
      expect(result.distributions.pe_ratio).toHaveProperty('quartiles');
    });
  });

  describe('calculateFactorCorrelations', () => {
    const universeData = [
      { pe_ratio: 10.0, roe: 0.30 },
      { pe_ratio: 15.0, roe: 0.25 },
      { pe_ratio: 20.0, roe: 0.20 }
    ];

    test('should calculate correlation matrix', () => {
      const result = engine.calculateFactorCorrelations(universeData);

      expect(result).toHaveProperty('pe_ratio');
      expect(result.pe_ratio).toHaveProperty('roe');
      expect(typeof result.pe_ratio.roe).toBe('number');
    });
  });

  describe('calculateCorrelation', () => {
    const universeData = [
      { factor1: 1, factor2: 2 },
      { factor1: 2, factor2: 4 },
      { factor1: 3, factor2: 6 }
    ];

    test('should calculate perfect positive correlation', () => {
      const result = engine.calculateCorrelation(universeData, 'factor1', 'factor2');
      expect(result).toBeCloseTo(1.0, 5);
    });

    test('should handle insufficient data', () => {
      const smallData = [{ factor1: 1, factor2: 2 }];
      const result = engine.calculateCorrelation(smallData, 'factor1', 'factor2');
      expect(result).toBe(0);
    });

    test('should handle zero denominator', () => {
      const constantData = [
        { factor1: 5, factor2: 5 },
        { factor1: 5, factor2: 5 }
      ];
      const result = engine.calculateCorrelation(constantData, 'factor1', 'factor2');
      expect(result).toBe(0);
    });
  });

  describe('identifyTopFactors', () => {
    const universeData = [
      { pe_ratio: 10.0, roe: 0.20, revenue_growth_1y: 0.10 },
      { pe_ratio: 20.0, roe: 0.30, revenue_growth_1y: 0.20 },
      { pe_ratio: 30.0, roe: 0.40, revenue_growth_1y: 0.30 }
    ];

    test('should identify top performing factors', () => {
      const result = engine.identifyTopFactors(universeData, 3);

      expect(Array.isArray(result)).toBe(true);
      expect(result.length).toBeLessThanOrEqual(3);

      if (result.length > 0) {
        const topFactor = result[0];
        expect(topFactor).toHaveProperty('factor');
        expect(topFactor).toHaveProperty('name');
        expect(topFactor).toHaveProperty('category');
        expect(topFactor).toHaveProperty('impact');
        expect(topFactor).toHaveProperty('significance');
        expect(topFactor).toHaveProperty('discriminationPower');
        expect(topFactor).toHaveProperty('dataPoints');
      }
    });

    test('should handle single value factors', () => {
      const uniformData = [
        { pe_ratio: 15.0 },
        { pe_ratio: 15.0 }
      ];

      const result = engine.identifyTopFactors(uniformData);

      expect(Array.isArray(result)).toBe(true);
      // Factors with no variance should have discrimination power of 0
    });
  });

  describe('calculateVariance', () => {
    test('should calculate variance correctly', () => {
      const values = [1, 2, 3, 4, 5];
      const result = engine.calculateVariance(values);

      // Expected variance = 2
      expect(result).toBeCloseTo(2, 5);
    });

    test('should handle insufficient data', () => {
      expect(engine.calculateVariance([])).toBe(0);
      expect(engine.calculateVariance([5])).toBe(0);
    });
  });

  describe('normalizeFactors', () => {
    test('should normalize to 0-1 range', () => {
      const values = [10, 20, 30, 40, 50];
      const result = engine.normalizeFactors(values);

      expect(result[0]).toBe(0);
      expect(result[result.length - 1]).toBe(1);
      expect(result[2]).toBe(0.5); // Middle value
    });

    test('should invert when inverse is true', () => {
      const values = [10, 20, 30];
      const normal = engine.normalizeFactors(values, false);
      const inverse = engine.normalizeFactors(values, true);

      expect(normal[0] + inverse[0]).toBeCloseTo(1.0, 5);
      expect(normal[2] + inverse[2]).toBeCloseTo(1.0, 5);
    });

    test('should handle edge cases', () => {
      expect(engine.normalizeFactors([])).toEqual([]);
      expect(engine.normalizeFactors([5])).toEqual([0.5]);
      expect(engine.normalizeFactors([10, 10, 10])).toEqual([0.5, 0.5, 0.5]);
    });
  });

  describe('calculateQuartiles', () => {
    test('should calculate quartiles for sufficient data', () => {
      const universeData = [
        { pe_ratio: 10 },
        { pe_ratio: 20 },
        { pe_ratio: 30 },
        { pe_ratio: 40 },
        { pe_ratio: 50 }
      ];

      const result = engine.calculateQuartiles(universeData, 'pe_ratio');

      expect(result).toHaveProperty('q1');
      expect(result).toHaveProperty('q2');
      expect(result).toHaveProperty('q3');
      expect(result.q1).toBeLessThan(result.q2);
      expect(result.q2).toBeLessThan(result.q3);
    });

    test('should handle insufficient data', () => {
      const smallData = [{ pe_ratio: 15 }];
      const result = engine.calculateQuartiles(smallData, 'pe_ratio');

      expect(result.q1).toBe(15);
      expect(result.q2).toBe(15);
      expect(result.q3).toBe(15);
    });

    test('should filter out invalid values', () => {
      const dataWithNulls = [
        { pe_ratio: 10 },
        { pe_ratio: null },
        { pe_ratio: 20 },
        { pe_ratio: undefined },
        { pe_ratio: 30 }
      ];

      const result = engine.calculateQuartiles(dataWithNulls, 'pe_ratio');

      expect(result.q1).toBeDefined();
      expect(result.q2).toBeDefined();
      expect(result.q3).toBeDefined();
    });
  });

  describe('screenByFactors', () => {
    const scoredStocks = [
      {
        symbol: 'AAPL',
        factorScore: {
          compositeScore: 0.8,
          percentile: 90,
          categoryScores: { value: 0.7, growth: 0.9 }
        }
      },
      {
        symbol: 'GOOGL',
        factorScore: {
          compositeScore: 0.6,
          percentile: 70,
          categoryScores: { value: 0.5, growth: 0.7 }
        }
      }
    ];

    test('should filter by composite score', () => {
      const criteria = { minCompositeScore: 0.7 };
      const result = engine.screenByFactors(scoredStocks, criteria);

      expect(result.length).toBe(1);
      expect(result[0].symbol).toBe('AAPL');
    });

    test('should filter by max composite score', () => {
      const criteria = { maxCompositeScore: 0.7 };
      const result = engine.screenByFactors(scoredStocks, criteria);

      expect(result.length).toBe(1);
      expect(result[0].symbol).toBe('GOOGL');
    });

    test('should filter by percentile', () => {
      const criteria = { minPercentile: 80 };
      const result = engine.screenByFactors(scoredStocks, criteria);

      expect(result.length).toBe(1);
      expect(result[0].symbol).toBe('AAPL');
    });

    test('should filter by category scores', () => {
      const criteria = {
        categoryFilters: { value: 0.6, growth: 0.8 }
      };
      const result = engine.screenByFactors(scoredStocks, criteria);

      expect(result.length).toBe(1);
      expect(result[0].symbol).toBe('AAPL');
    });

    test('should filter out stocks without factor scores', () => {
      const stocksWithoutScores = [
        ...scoredStocks,
        { symbol: 'TSLA' } // No factorScore
      ];

      const criteria = { minCompositeScore: 0.1 };
      const result = engine.screenByFactors(stocksWithoutScores, criteria);

      expect(result.length).toBe(2);
      expect(result.every(stock => stock.factorScore)).toBe(true);
    });
  });

  describe('exported functions', () => {
    const sampleStock = {
      symbol: 'TEST',
      pe_ratio: 15.0,
      roe: 0.25
    };

    test('calculateCompositeScore should work', () => {
      const result = calculateCompositeScore(sampleStock);
      expect(result.compositeScore).toBeDefined();
    });

    test('scoreUniverse should work', () => {
      const result = scoreUniverse([sampleStock]);
      expect(Array.isArray(result)).toBe(true);
    });

    test('getFactorExplanations should work', () => {
      const result = getFactorExplanations(sampleStock);
      expect(result).toHaveProperty('value');
    });

    test('getFactorDefinitions should work', () => {
      const result = getFactorDefinitions();
      expect(result).toHaveProperty('value');
    });

    test('createCustomProfile should work', () => {
      const result = createCustomProfile('Test', { value: 1.0 });
      expect(result.name).toBe('Test');
    });

    test('screenByFactors should work', () => {
      const scoredStocks = [{
        factorScore: { compositeScore: 0.8 }
      }];
      const result = screenByFactors(scoredStocks, {});
      expect(Array.isArray(result)).toBe(true);
    });

    test('FACTOR_DEFINITIONS should be exported', () => {
      expect(FACTOR_DEFINITIONS).toBeDefined();
      expect(FACTOR_DEFINITIONS).toHaveProperty('value');
    });
  });
});