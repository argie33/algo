/**
 * Factor Scoring Integration Tests
 * Tests factor scoring algorithms with mock financial data
 */

const { initializeDatabase, closeDatabase } = require("../../../utils/database");
const factorScoring = require("../../../utils/factorScoring");
const { FactorScoringEngine } = factorScoring;

describe("Factor Scoring Integration Tests", () => {
  let mockStockData;

  beforeAll(async () => {
    await initializeDatabase();
    
    // Create mock stock data for testing
    mockStockData = [
      {
        symbol: "AAPL",
        pe_ratio: 15.2,
        pb_ratio: 3.1,
        ps_ratio: 2.8,
        revenue_growth_1y: 0.15,
        earnings_growth_1y: 0.12,
        roe: 0.28,
        roa: 0.15,
        debt_to_equity: 0.45,
        current_ratio: 1.2,
        price_momentum_3m: 0.08,
        price_momentum_6m: 0.15,
        gross_margin: 0.42,
        operating_margin: 0.28,
        net_margin: 0.21
      },
      {
        symbol: "GOOGL",
        pe_ratio: 18.5,
        pb_ratio: 2.9,
        ps_ratio: 3.2,
        revenue_growth_1y: 0.18,
        earnings_growth_1y: 0.20,
        roe: 0.22,
        roa: 0.12,
        debt_to_equity: 0.25,
        current_ratio: 2.1,
        price_momentum_3m: 0.05,
        price_momentum_6m: 0.12,
        gross_margin: 0.58,
        operating_margin: 0.25,
        net_margin: 0.19
      },
      {
        symbol: "MSFT",
        pe_ratio: 22.1,
        pb_ratio: 4.2,
        ps_ratio: 5.1,
        revenue_growth_1y: 0.12,
        earnings_growth_1y: 0.18,
        roe: 0.35,
        roa: 0.18,
        debt_to_equity: 0.38,
        current_ratio: 1.8,
        price_momentum_3m: 0.12,
        price_momentum_6m: 0.18,
        gross_margin: 0.68,
        operating_margin: 0.42,
        net_margin: 0.31
      },
      {
        symbol: "TSLA",
        pe_ratio: 45.8,
        pb_ratio: 8.9,
        ps_ratio: 6.2,
        revenue_growth_1y: 0.35,
        earnings_growth_1y: 0.28,
        roe: 0.18,
        roa: 0.08,
        debt_to_equity: 0.65,
        current_ratio: 1.4,
        price_momentum_3m: 0.25,
        price_momentum_6m: 0.38,
        gross_margin: 0.18,
        operating_margin: 0.08,
        net_margin: 0.06
      }
    ];
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("Composite Score Calculation", () => {
    test("should calculate composite score for individual stock", () => {
      const stockData = mockStockData[0]; // AAPL
      const score = factorScoring.calculateCompositeScore(stockData, mockStockData);

      expect(score).toBeDefined();
      expect(score.compositeScore).toBeDefined();
      expect(score.categoryScores).toBeDefined();
      expect(typeof score.compositeScore).toBe('number');
      expect(score.compositeScore).toBeGreaterThanOrEqual(0);
      expect(score.compositeScore).toBeLessThanOrEqual(1);

      // Check category scores
      expect(score.categoryScores.value).toBeDefined();
      expect(score.categoryScores.growth).toBeDefined();
      expect(score.categoryScores.profitability).toBeDefined();
      expect(score.categoryScores.financial_health).toBeDefined();
    });

    test("should handle stock data without universe comparison", () => {
      const stockData = mockStockData[0];
      const score = factorScoring.calculateCompositeScore(stockData);

      expect(score).toBeDefined();
      expect(score.compositeScore).toBeDefined();
      expect(typeof score.compositeScore).toBe('number');
    });

    test("should handle missing factor data gracefully", () => {
      const incompleteStock = {
        symbol: "INCOMPLETE",
        pe_ratio: 15.2,
        // Missing other factors
      };

      const score = factorScoring.calculateCompositeScore(incompleteStock);
      expect(score).toBeDefined();
      expect(score.compositeScore).toBeDefined();
    });
  });

  describe("Universe Scoring", () => {
    test("should score entire universe of stocks", () => {
      const scoredUniverse = factorScoring.scoreUniverse(mockStockData);

      expect(Array.isArray(scoredUniverse)).toBe(true);
      expect(scoredUniverse.length).toBe(mockStockData.length);

      scoredUniverse.forEach((stock, index) => {
        expect(stock.symbol).toBeDefined();
        expect(stock.factorScore).toBeDefined();
        expect(stock.factorScore.compositeScore).toBeDefined();
        expect(stock.factorScore.rank).toBe(index + 1);
        expect(stock.factorScore.percentile).toBeDefined();
        
        if (index > 0) {
          // Verify sorting (higher scores first)
          expect(stock.factorScore.compositeScore)
            .toBeLessThanOrEqual(scoredUniverse[index - 1].factorScore.compositeScore);
        }
      });
    });

    test("should handle custom factor weights", () => {
      const customWeights = {
        value: 0.4,
        growth: 0.3,
        profitability: 0.2,
        financial_health: 0.1
      };

      const scoredUniverse = factorScoring.scoreUniverse(mockStockData, customWeights);

      expect(Array.isArray(scoredUniverse)).toBe(true);
      expect(scoredUniverse.length).toBe(mockStockData.length);
      
      scoredUniverse.forEach(stock => {
        expect(stock.factorScore.compositeScore).toBeDefined();
      });
    });

    test("should handle empty universe gracefully", () => {
      const emptyUniverse = factorScoring.scoreUniverse([]);
      expect(Array.isArray(emptyUniverse)).toBe(true);
      expect(emptyUniverse.length).toBe(0);
    });
  });

  describe("Factor Explanations", () => {
    test("should provide detailed factor explanations", () => {
      const stockData = mockStockData[0]; // AAPL
      const explanations = factorScoring.getFactorExplanations(stockData);

      expect(explanations).toBeDefined();
      expect(explanations.value).toBeDefined();
      expect(explanations.growth).toBeDefined();
      expect(explanations.profitability).toBeDefined();

      // Check value category explanation
      const valueExplanation = explanations.value;
      expect(valueExplanation.name).toBe("Value");
      expect(valueExplanation.description).toBeDefined();
      expect(valueExplanation.weight).toBeDefined();
      expect(Array.isArray(valueExplanation.factors)).toBe(true);

      // Check individual factor explanations
      valueExplanation.factors.forEach(factor => {
        expect(factor.factor).toBeDefined();
        expect(factor.value).toBeDefined();
        expect(factor.score).toBeDefined();
        expect(factor.weight).toBeDefined();
        expect(factor.interpretation).toBeDefined();
      });
    });

    test("should handle stocks with limited factor data", () => {
      const limitedStock = {
        symbol: "LIMITED",
        pe_ratio: 20.5,
        roe: 0.15
      };

      const explanations = factorScoring.getFactorExplanations(limitedStock);
      expect(explanations).toBeDefined();
      expect(explanations.value).toBeDefined();
      expect(explanations.profitability).toBeDefined();
    });
  });

  describe("Factor Definitions", () => {
    test("should return factor definitions", () => {
      const definitions = factorScoring.getFactorDefinitions();

      expect(definitions).toBeDefined();
      expect(definitions.value).toBeDefined();
      expect(definitions.growth).toBeDefined();
      expect(definitions.profitability).toBeDefined();
      expect(definitions.financial_health).toBeDefined();
      expect(definitions.momentum).toBeDefined();
      expect(definitions.quality).toBeDefined();

      // Check structure of value category
      const value = definitions.value;
      expect(value.name).toBe("Value");
      expect(value.description).toBeDefined();
      expect(value.weight).toBeDefined();
      expect(value.factors).toBeDefined();
      expect(value.factors.pe_ratio).toBeDefined();
      expect(value.factors.pe_ratio.weight).toBeDefined();
      expect(value.factors.pe_ratio.inverse).toBe(true);
    });
  });

  describe("Custom Profile Creation", () => {
    test("should create custom scoring profile", () => {
      const categoryWeights = {
        value: 0.3,
        growth: 0.25,
        profitability: 0.25,
        financial_health: 0.2
      };

      const profile = factorScoring.createCustomProfile(
        "Growth-Value Mix",
        categoryWeights,
        "Balanced approach focusing on growth and value"
      );

      expect(profile).toBeDefined();
      expect(profile.name).toBe("Growth-Value Mix");
      expect(profile.description).toBeDefined();
      expect(profile.weights).toEqual(categoryWeights);
      expect(profile.created_at).toBeDefined();
      expect(new Date(profile.created_at)).toBeInstanceOf(Date);
    });
  });

  describe("Stock Screening", () => {
    test("should screen stocks by factor criteria", () => {
      const scoredStocks = factorScoring.scoreUniverse(mockStockData);
      
      const criteria = {
        minCompositeScore: 0.3,
        minPercentile: 25,
        categoryFilters: {
          value: 0.2,
          profitability: 0.3
        }
      };

      const screenedStocks = factorScoring.screenByFactors(scoredStocks, criteria);

      expect(Array.isArray(screenedStocks)).toBe(true);
      
      screenedStocks.forEach(stock => {
        expect(stock.factorScore.compositeScore).toBeGreaterThanOrEqual(criteria.minCompositeScore);
        expect(stock.factorScore.percentile).toBeGreaterThanOrEqual(criteria.minPercentile);
        
        if (stock.factorScore.categoryScores.value) {
          expect(stock.factorScore.categoryScores.value).toBeGreaterThanOrEqual(0.2);
        }
        if (stock.factorScore.categoryScores.profitability) {
          expect(stock.factorScore.categoryScores.profitability).toBeGreaterThanOrEqual(0.3);
        }
      });
    });

    test("should handle restrictive screening criteria", () => {
      const scoredStocks = factorScoring.scoreUniverse(mockStockData);
      
      const restrictiveCriteria = {
        minCompositeScore: 0.9, // Very high threshold
        minPercentile: 95
      };

      const screenedStocks = factorScoring.screenByFactors(scoredStocks, restrictiveCriteria);
      
      expect(Array.isArray(screenedStocks)).toBe(true);
      // May result in empty array due to restrictive criteria
      screenedStocks.forEach(stock => {
        expect(stock.factorScore.compositeScore).toBeGreaterThanOrEqual(0.9);
      });
    });
  });

  describe("FactorScoringEngine Class", () => {
    test("should create new engine with custom factors", () => {
      const customFactors = {
        test_factor: {
          name: "Test Factor",
          description: "Custom test factor",
          weight: 1.0,
          factors: {
            test_metric: { weight: 1.0 }
          }
        }
      };

      const engine = new FactorScoringEngine(customFactors);
      expect(engine).toBeDefined();
      
      const definitions = engine.getFactorDefinitions();
      expect(definitions.test_factor).toBeDefined();
      expect(definitions.test_factor.name).toBe("Test Factor");
    });

    test("should analyze factors across universe", () => {
      const engine = new FactorScoringEngine();
      const analysis = engine.analyzeFactors(mockStockData);

      expect(analysis).toBeDefined();
      expect(analysis.factorStats).toBeDefined();
      expect(analysis.correlations).toBeDefined();
      expect(analysis.distributions).toBeDefined();
      expect(analysis.sampleSize).toBe(mockStockData.length);

      // Check factor statistics
      expect(analysis.factorStats.pe_ratio).toBeDefined();
      expect(analysis.factorStats.pe_ratio.min).toBeDefined();
      expect(analysis.factorStats.pe_ratio.max).toBeDefined();
      expect(analysis.factorStats.pe_ratio.mean).toBeDefined();
      expect(analysis.factorStats.pe_ratio.std).toBeDefined();
    });

    test("should identify top performing factors", () => {
      const engine = new FactorScoringEngine();
      const topFactors = engine.identifyTopFactors(mockStockData, 3);

      expect(Array.isArray(topFactors)).toBe(true);
      expect(topFactors.length).toBeLessThanOrEqual(3);

      topFactors.forEach(factor => {
        expect(factor.factor).toBeDefined();
        expect(factor.name).toBeDefined();
        expect(factor.category).toBeDefined();
        expect(factor.discriminationPower).toBeDefined();
        expect(factor.variance).toBeDefined();
        expect(factor.range).toBeDefined();
      });

      // Should be sorted by discrimination power
      for (let i = 1; i < topFactors.length; i++) {
        expect(topFactors[i].discriminationPower)
          .toBeLessThanOrEqual(topFactors[i - 1].discriminationPower);
      }
    });

    test("should rank universe correctly", () => {
      const engine = new FactorScoringEngine();
      const rankings = engine.rankUniverse(mockStockData);

      expect(Array.isArray(rankings)).toBe(true);
      expect(rankings.length).toBe(mockStockData.length);

      rankings.forEach((stock, index) => {
        expect(stock.rank).toBe(index + 1);
        expect(stock.compositeScore).toBeDefined();
        expect(stock.percentile).toBeDefined();
        expect(stock.categoryScores).toBeDefined();

        if (index > 0) {
          expect(stock.compositeScore)
            .toBeLessThanOrEqual(rankings[index - 1].compositeScore);
        }
      });
    });

    test("should normalize factors correctly", () => {
      const engine = new FactorScoringEngine();
      
      const values = [10, 20, 30, 40, 50];
      const normalized = engine.normalizeFactors(values);
      
      expect(Array.isArray(normalized)).toBe(true);
      expect(normalized.length).toBe(values.length);
      expect(normalized[0]).toBe(0); // Min value
      expect(normalized[normalized.length - 1]).toBe(1); // Max value
      
      // Test inverse normalization
      const inverseNormalized = engine.normalizeFactors(values, true);
      expect(inverseNormalized[0]).toBe(1); // Min value becomes max
      expect(inverseNormalized[inverseNormalized.length - 1]).toBe(0); // Max value becomes min
    });

    test("should handle edge cases in normalization", () => {
      const engine = new FactorScoringEngine();
      
      // Single value
      const singleValue = engine.normalizeFactors([42]);
      expect(singleValue).toEqual([0.5]);
      
      // Identical values
      const identicalValues = engine.normalizeFactors([10, 10, 10]);
      expect(identicalValues).toEqual([0.5, 0.5, 0.5]);
      
      // Empty array
      const emptyArray = engine.normalizeFactors([]);
      expect(emptyArray).toEqual([]);
    });
  });

  describe("Performance and Error Handling", () => {
    test("should handle large datasets efficiently", () => {
      // Create larger dataset
      const largeDataset = [];
      for (let i = 0; i < 100; i++) {
        largeDataset.push({
          symbol: `STOCK_${i}`,
          pe_ratio: 10 + (i % 30), // deterministic values
          pb_ratio: 1 + (i % 5),
          revenue_growth_1y: -0.1 + (i % 50) * 0.01,
          roe: (i % 30) * 0.01,
          debt_to_equity: (i % 20) * 0.1,
        });
      }

      const startTime = Date.now();
      const scoredUniverse = factorScoring.scoreUniverse(largeDataset);
      const duration = Date.now() - startTime;

      expect(scoredUniverse.length).toBe(100);
      expect(duration).toBeLessThan(5000); // Should complete within 5 seconds
    });

    test("should handle null and undefined values gracefully", () => {
      const stockWithNulls = {
        symbol: "NULL_TEST",
        pe_ratio: null,
        pb_ratio: undefined,
        revenue_growth_1y: 0.15,
        roe: 0.20
      };

      const score = factorScoring.calculateCompositeScore(stockWithNulls);
      expect(score).toBeDefined();
      expect(score.compositeScore).toBeDefined();
    });

    test("should handle invalid input gracefully", () => {
      expect(() => factorScoring.calculateCompositeScore(null)).not.toThrow();
      expect(() => factorScoring.calculateCompositeScore({})).not.toThrow();
      expect(() => factorScoring.scoreUniverse(null)).not.toThrow();
    });
  });
});