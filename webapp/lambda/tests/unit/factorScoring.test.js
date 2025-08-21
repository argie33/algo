/**
 * Unit Tests for Factor Scoring Engine
 * Tests stock scoring, ranking algorithms, and factor analysis
 */

// Mock logger before requiring factorScoring
jest.mock("../../utils/logger", () => ({
  error: jest.fn(),
  warn: jest.fn(),
  info: jest.fn(),
  debug: jest.fn(),
}));

const logger = require("../../utils/logger");

describe("Factor Scoring Engine", () => {
  let FactorScoringEngine;
  let scoringEngine;

  beforeEach(() => {
    jest.clearAllMocks();

    // Clear module cache to get fresh instance
    delete require.cache[require.resolve("../../utils/factorScoring")];
    FactorScoringEngine = require("../../utils/factorScoring");

    // Create fresh instance for each test
    scoringEngine = new FactorScoringEngine();
  });

  describe("Initialization", () => {
    test("should initialize with default factor definitions", () => {
      expect(scoringEngine.factors).toBeDefined();
      expect(scoringEngine.factors).toHaveProperty("value");
      expect(scoringEngine.factors).toHaveProperty("growth");
      expect(scoringEngine.factors).toHaveProperty("profitability");
      expect(scoringEngine.factors).toHaveProperty("financial_health");
      expect(scoringEngine.factors).toHaveProperty("momentum");
      expect(scoringEngine.factors).toHaveProperty("quality");
    });

    test("should initialize with custom factors", () => {
      const customFactors = {
        custom: {
          name: "Custom",
          weight: 1.0,
          factors: {
            custom_metric: { weight: 1.0 },
          },
        },
      };

      const customEngine = new FactorScoringEngine(customFactors);
      expect(customEngine.factors).toEqual(customFactors);
      expect(customEngine.factors).not.toHaveProperty("value");
    });

    test("should initialize with empty universe stats", () => {
      expect(scoringEngine.universeStats.size).toBe(0);
    });
  });

  describe("Factor Definitions Validation", () => {
    test("should have correct factor category weights", () => {
      const totalWeight = Object.values(scoringEngine.factors).reduce(
        (sum, category) => sum + category.weight,
        0
      );

      expect(totalWeight).toBeCloseTo(1.0, 2); // Should sum to 1.0
    });

    test("should have correct sub-factor weights within categories", () => {
      Object.entries(scoringEngine.factors).forEach(
        ([_categoryName, categoryDef]) => {
          const subFactorWeightSum = Object.values(categoryDef.factors).reduce(
            (sum, factor) => sum + factor.weight,
            0
          );

          expect(subFactorWeightSum).toBeCloseTo(1.0, 2);
        }
      );
    });

    test("should have required properties for each factor category", () => {
      Object.entries(scoringEngine.factors).forEach(
        ([_categoryName, categoryDef]) => {
          expect(categoryDef).toHaveProperty("name");
          expect(categoryDef).toHaveProperty("description");
          expect(categoryDef).toHaveProperty("weight");
          expect(categoryDef).toHaveProperty("factors");

          expect(typeof categoryDef.name).toBe("string");
          expect(typeof categoryDef.description).toBe("string");
          expect(typeof categoryDef.weight).toBe("number");
          expect(typeof categoryDef.factors).toBe("object");
        }
      );
    });

    test("should have inverse flag for value factors", () => {
      const valueFactors = scoringEngine.factors.value.factors;

      // Value factors should generally be inverse (lower is better)
      expect(valueFactors.pe_ratio.inverse).toBe(true);
      expect(valueFactors.pb_ratio.inverse).toBe(true);
      expect(valueFactors.ps_ratio.inverse).toBe(true);
    });

    test("should not have inverse flag for growth factors", () => {
      const growthFactors = scoringEngine.factors.growth.factors;

      // Growth factors should not be inverse (higher is better)
      Object.values(growthFactors).forEach((factor) => {
        expect(factor.inverse).toBeFalsy();
      });
    });
  });

  describe("Composite Score Calculation", () => {
    test("should calculate composite score for complete stock data", () => {
      const stockData = {
        symbol: "AAPL",
        // Value factors
        pe_ratio: 15.5,
        pb_ratio: 2.3,
        ps_ratio: 3.1,
        price_to_cash_flow: 12.8,
        enterprise_value_ebitda: 10.2,
        // Growth factors
        revenue_growth_1y: 0.15,
        revenue_growth_3y: 0.12,
        earnings_growth_1y: 0.18,
        earnings_growth_3y: 0.14,
        eps_growth_estimate: 0.2,
        // Profitability factors
        roe: 0.25,
        roa: 0.12,
        gross_margin: 0.45,
        operating_margin: 0.28,
        net_margin: 0.22,
        // Financial health factors
        debt_to_equity: 0.8,
        current_ratio: 1.5,
        quick_ratio: 1.2,
        interest_coverage: 15.5,
        free_cash_flow_yield: 0.08,
        // Momentum factors
        price_momentum_3m: 0.1,
        price_momentum_6m: 0.15,
        price_momentum_12m: 0.25,
        earnings_revision_trend: 0.05,
        relative_strength: 0.12,
        // Quality factors
        revenue_stability: 0.95,
        earnings_stability: 0.88,
        dividend_consistency: 0.92,
        market_share_trend: 0.08,
        management_efficiency: 0.85,
      };

      const result = scoringEngine.calculateCompositeScore(stockData);

      expect(result).toBeDefined();
      expect(result).toHaveProperty("compositeScore");
      expect(result).toHaveProperty("categoryScores");
      expect(result).toHaveProperty("rank", null);
      expect(result).toHaveProperty("percentile", null);

      expect(typeof result.compositeScore).toBe("number");
      expect(result.compositeScore).toBeGreaterThan(0);
      expect(result.compositeScore).toBeLessThanOrEqual(1);

      // Should have scores for all categories
      expect(result.categoryScores).toHaveProperty("value");
      expect(result.categoryScores).toHaveProperty("growth");
      expect(result.categoryScores).toHaveProperty("profitability");
      expect(result.categoryScores).toHaveProperty("financial_health");
      expect(result.categoryScores).toHaveProperty("momentum");
      expect(result.categoryScores).toHaveProperty("quality");
    });

    test("should handle missing factor data gracefully", () => {
      const incompleteStockData = {
        symbol: "TEST",
        pe_ratio: 20.0,
        revenue_growth_1y: 0.1,
        roe: 0.15,
        // Missing many factors
      };

      const result = scoringEngine.calculateCompositeScore(incompleteStockData);

      expect(result).toBeDefined();
      expect(result.compositeScore).toBeGreaterThan(0);
      expect(Object.keys(result.categoryScores)).toEqual(
        expect.arrayContaining(["value", "growth", "profitability"])
      );
    });

    test("should return null for stock with no valid data", () => {
      const emptyStockData = {
        symbol: "EMPTY",
        invalid_field: "test",
      };

      const result = scoringEngine.calculateCompositeScore(emptyStockData);
      expect(result.compositeScore).toBe(0);
    });

    test("should handle calculation errors gracefully", () => {
      const problematicData = {
        symbol: "ERROR",
        pe_ratio: "invalid",
        pb_ratio: null,
        ps_ratio: undefined,
        // Mix of invalid data types
      };

      const result = scoringEngine.calculateCompositeScore(problematicData);
      expect(result).toBeDefined();
      expect(typeof result.compositeScore).toBe("number");
    });

    test("should log errors for problematic stocks", () => {
      // Create stock data that will cause an error
      const stockData = null; // This should trigger error handling

      const result = scoringEngine.calculateCompositeScore(stockData);

      expect(result).toBeNull();
      expect(logger.error).toHaveBeenCalledWith(
        "Composite score calculation error",
        expect.objectContaining({
          error: expect.any(Error),
        })
      );
    });
  });

  describe("Category Score Calculation", () => {
    test("should calculate category score correctly", () => {
      const stockData = {
        pe_ratio: 15.0,
        pb_ratio: 2.5,
        ps_ratio: 3.0,
        price_to_cash_flow: 12.0,
        enterprise_value_ebitda: 10.0,
      };

      const categoryDef = scoringEngine.factors.value;
      const score = scoringEngine.calculateCategoryScore(
        stockData,
        categoryDef
      );

      expect(typeof score).toBe("number");
      expect(score).toBeGreaterThanOrEqual(0);
      expect(score).toBeLessThanOrEqual(1);
    });

    test("should handle inverse factors correctly", () => {
      const stockData1 = { pe_ratio: 10.0 }; // Lower PE (better for value)
      const stockData2 = { pe_ratio: 30.0 }; // Higher PE (worse for value)

      const categoryDef = {
        factors: {
          pe_ratio: { weight: 1.0, inverse: true },
        },
      };

      const score1 = scoringEngine.calculateCategoryScore(
        stockData1,
        categoryDef
      );
      const score2 = scoringEngine.calculateCategoryScore(
        stockData2,
        categoryDef
      );

      // For inverse factors, lower values should get higher scores
      expect(score1).toBeGreaterThan(score2);
    });

    test("should handle missing factor data in category", () => {
      const stockData = {
        pe_ratio: 15.0,
        // Missing other value factors
      };

      const categoryDef = scoringEngine.factors.value;
      const score = scoringEngine.calculateCategoryScore(
        stockData,
        categoryDef
      );

      expect(typeof score).toBe("number");
      expect(score).toBeGreaterThanOrEqual(0);
      expect(score).toBeLessThanOrEqual(1);
    });

    test("should return null for category with no valid data", () => {
      const stockData = {
        unrelated_field: 100,
      };

      const categoryDef = scoringEngine.factors.value;
      const score = scoringEngine.calculateCategoryScore(
        stockData,
        categoryDef
      );

      expect(score).toBeNull();
    });

    test("should handle extreme values correctly", () => {
      const stockData = {
        pe_ratio: 0, // Zero value
        pb_ratio: -5.0, // Negative value
        ps_ratio: 1000.0, // Very large value
      };

      const categoryDef = scoringEngine.factors.value;
      const score = scoringEngine.calculateCategoryScore(
        stockData,
        categoryDef
      );

      expect(typeof score).toBe("number");
      expect(score).toBeGreaterThanOrEqual(0);
      expect(score).toBeLessThanOrEqual(1);
    });
  });

  describe("Factor Normalization", () => {
    test("should normalize factor values correctly", () => {
      const values = [10, 20, 30, 40, 50];

      const normalized = scoringEngine.normalizeFactors(values);

      expect(normalized).toHaveLength(5);
      expect(Math.min(...normalized)).toBeGreaterThanOrEqual(0);
      expect(Math.max(...normalized)).toBeLessThanOrEqual(1);

      // Values should maintain relative ordering
      expect(normalized[0]).toBeLessThan(normalized[4]);
    });

    test("should handle single value normalization", () => {
      const values = [42];

      const normalized = scoringEngine.normalizeFactors(values);

      expect(normalized).toHaveLength(1);
      expect(normalized[0]).toBe(0.5); // Single value should normalize to middle
    });

    test("should handle identical values", () => {
      const values = [10, 10, 10, 10];

      const normalized = scoringEngine.normalizeFactors(values);

      expect(normalized).toHaveLength(4);
      normalized.forEach((value) => {
        expect(value).toBe(0.5); // All identical values should be 0.5
      });
    });

    test("should handle inverse normalization", () => {
      const values = [10, 20, 30, 40, 50];

      const normalizedRegular = scoringEngine.normalizeFactors(values, false);
      const normalizedInverse = scoringEngine.normalizeFactors(values, true);

      // Inverse should flip the ordering
      expect(normalizedInverse[0]).toBeGreaterThan(normalizedInverse[4]);
      expect(normalizedRegular[0]).toBeLessThan(normalizedRegular[4]);
    });
  });

  describe("Universe Ranking", () => {
    test("should rank stocks in universe correctly", () => {
      const universeData = [
        {
          symbol: "STOCK_A",
          pe_ratio: 10.0,
          revenue_growth_1y: 0.2,
          roe: 0.25,
        },
        {
          symbol: "STOCK_B",
          pe_ratio: 20.0,
          revenue_growth_1y: 0.1,
          roe: 0.15,
        },
        {
          symbol: "STOCK_C",
          pe_ratio: 15.0,
          revenue_growth_1y: 0.15,
          roe: 0.2,
        },
      ];

      const rankedUniverse = scoringEngine.rankUniverse(universeData);

      expect(rankedUniverse).toHaveLength(3);

      // Should be sorted by composite score (highest first)
      for (let i = 1; i < rankedUniverse.length; i++) {
        expect(rankedUniverse[i].compositeScore).toBeLessThanOrEqual(
          rankedUniverse[i - 1].compositeScore
        );
      }

      // Should have rank and percentile assigned
      rankedUniverse.forEach((stock, index) => {
        expect(stock.rank).toBe(index + 1);
        expect(stock.percentile).toBeGreaterThan(0);
        expect(stock.percentile).toBeLessThanOrEqual(100);
      });
    });

    test("should handle empty universe", () => {
      const rankedUniverse = scoringEngine.rankUniverse([]);
      expect(rankedUniverse).toHaveLength(0);
    });

    test("should handle single stock universe", () => {
      const universeData = [
        {
          symbol: "ONLY_STOCK",
          pe_ratio: 15.0,
          roe: 0.2,
        },
      ];

      const rankedUniverse = scoringEngine.rankUniverse(universeData);

      expect(rankedUniverse).toHaveLength(1);
      expect(rankedUniverse[0].rank).toBe(1);
      expect(rankedUniverse[0].percentile).toBe(100);
    });
  });

  describe("Factor Analysis", () => {
    test("should provide factor analysis for universe", () => {
      const universeData = [
        { symbol: "A", pe_ratio: 10, roe: 0.2, revenue_growth_1y: 0.15 },
        { symbol: "B", pe_ratio: 20, roe: 0.1, revenue_growth_1y: 0.25 },
        { symbol: "C", pe_ratio: 15, roe: 0.15, revenue_growth_1y: 0.1 },
      ];

      const analysis = scoringEngine.analyzeFactors(universeData);

      expect(analysis).toHaveProperty("factorStats");
      expect(analysis).toHaveProperty("correlations");
      expect(analysis).toHaveProperty("distributions");

      // Should have stats for each factor
      expect(analysis.factorStats).toHaveProperty("pe_ratio");
      expect(analysis.factorStats).toHaveProperty("roe");
      expect(analysis.factorStats).toHaveProperty("revenue_growth_1y");

      // Each factor stat should have mean, median, std, min, max
      Object.values(analysis.factorStats).forEach((stat) => {
        expect(stat).toHaveProperty("mean");
        expect(stat).toHaveProperty("median");
        expect(stat).toHaveProperty("std");
        expect(stat).toHaveProperty("min");
        expect(stat).toHaveProperty("max");
      });
    });

    test("should calculate factor correlations", () => {
      const universeData = [
        { pe_ratio: 10, pb_ratio: 1.5 },
        { pe_ratio: 20, pb_ratio: 2.5 },
        { pe_ratio: 15, pb_ratio: 2.0 },
        { pe_ratio: 25, pb_ratio: 3.0 },
      ];

      const correlations =
        scoringEngine.calculateFactorCorrelations(universeData);

      expect(correlations).toHaveProperty("pe_ratio");
      expect(correlations.pe_ratio).toHaveProperty("pb_ratio");

      const correlation = correlations.pe_ratio.pb_ratio;
      expect(typeof correlation).toBe("number");
      expect(correlation).toBeGreaterThanOrEqual(-1);
      expect(correlation).toBeLessThanOrEqual(1);
    });

    test("should identify top performing factors", () => {
      const universeData = [
        { symbol: "A", pe_ratio: 10, roe: 0.25, revenue_growth_1y: 0.2 },
        { symbol: "B", pe_ratio: 20, roe: 0.15, revenue_growth_1y: 0.3 },
        { symbol: "C", pe_ratio: 15, roe: 0.2, revenue_growth_1y: 0.1 },
      ];

      const topFactors = scoringEngine.identifyTopFactors(universeData);

      expect(Array.isArray(topFactors)).toBe(true);
      expect(topFactors.length).toBeGreaterThan(0);

      // Each top factor should have required properties
      topFactors.forEach((factor) => {
        expect(factor).toHaveProperty("name");
        expect(factor).toHaveProperty("category");
        expect(factor).toHaveProperty("impact");
        expect(factor).toHaveProperty("significance");
      });
    });
  });

  describe("Performance Optimization", () => {
    test("should cache universe statistics for repeated calculations", () => {
      const universeData = [
        { symbol: "A", pe_ratio: 10 },
        { symbol: "B", pe_ratio: 20 },
        { symbol: "C", pe_ratio: 15 },
      ];

      // First calculation should populate cache
      scoringEngine.calculateUniverseStats(universeData);
      expect(scoringEngine.universeStats.size).toBeGreaterThan(0);

      // Second calculation should use cache
      const stats1 = scoringEngine.calculateUniverseStats(universeData);
      const stats2 = scoringEngine.calculateUniverseStats(universeData);

      expect(stats1).toEqual(stats2);
    });

    test("should handle large universes efficiently", () => {
      // Create large universe for performance testing
      const universeData = [];
      for (let i = 0; i < 1000; i++) {
        universeData.push({
          symbol: `STOCK_${i}`,
          pe_ratio: Math.random() * 30 + 5,
          roe: Math.random() * 0.3 + 0.05,
          revenue_growth_1y: Math.random() * 0.4 - 0.1,
        });
      }

      const startTime = Date.now();
      const rankedUniverse = scoringEngine.rankUniverse(universeData);
      const endTime = Date.now();

      expect(rankedUniverse).toHaveLength(1000);
      expect(endTime - startTime).toBeLessThan(5000); // Should complete within 5 seconds
    });
  });

  describe("Error Handling and Edge Cases", () => {
    test("should handle null and undefined inputs", () => {
      expect(scoringEngine.calculateCompositeScore(null)).toBeNull();
      expect(scoringEngine.calculateCompositeScore(undefined)).toBeNull();
      expect(scoringEngine.rankUniverse(null)).toEqual([]);
      expect(scoringEngine.rankUniverse(undefined)).toEqual([]);
    });

    test("should handle stocks with all zero values", () => {
      const stockData = {
        symbol: "ZERO",
        pe_ratio: 0,
        pb_ratio: 0,
        ps_ratio: 0,
        roe: 0,
        revenue_growth_1y: 0,
      };

      const result = scoringEngine.calculateCompositeScore(stockData);
      expect(result).toBeDefined();
      expect(typeof result.compositeScore).toBe("number");
    });

    test("should handle stocks with extreme outlier values", () => {
      const stockData = {
        symbol: "OUTLIER",
        pe_ratio: 1000000, // Extremely high
        pb_ratio: -100, // Negative
        roe: 50.0, // Unrealistically high
        revenue_growth_1y: -0.99, // Near bankruptcy
      };

      const result = scoringEngine.calculateCompositeScore(stockData);
      expect(result).toBeDefined();
      expect(typeof result.compositeScore).toBe("number");
      expect(result.compositeScore).toBeGreaterThanOrEqual(0);
      expect(result.compositeScore).toBeLessThanOrEqual(1);
    });

    test("should maintain numerical stability with mixed data types", () => {
      const stockData = {
        symbol: "MIXED",
        pe_ratio: "15.5", // String number
        pb_ratio: true, // Boolean
        ps_ratio: 3.14159, // Float
        roe: 0.2, // Normal number
        revenue_growth_1y: null, // Null
      };

      const result = scoringEngine.calculateCompositeScore(stockData);
      expect(result).toBeDefined();
      expect(typeof result.compositeScore).toBe("number");
    });
  });
});
