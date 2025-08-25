/**
 * Factor Scoring Engine for Stock Screening
 * Provides comprehensive scoring and ranking algorithms for stock selection
 */

const logger = require("./logger");

/**
 * Factor definitions and weights
 */
const FACTOR_DEFINITIONS = {
  value: {
    name: "Value",
    description: "Price relative to fundamental metrics",
    weight: 0.2,
    factors: {
      pe_ratio: { weight: 0.3, inverse: true },
      pb_ratio: { weight: 0.2, inverse: true },
      ps_ratio: { weight: 0.2, inverse: true },
      price_to_cash_flow: { weight: 0.15, inverse: true },
      enterprise_value_ebitda: { weight: 0.15, inverse: true },
    },
  },

  growth: {
    name: "Growth",
    description: "Revenue and earnings growth metrics",
    weight: 0.25,
    factors: {
      revenue_growth_1y: { weight: 0.25 },
      revenue_growth_3y: { weight: 0.2 },
      earnings_growth_1y: { weight: 0.25 },
      earnings_growth_3y: { weight: 0.2 },
      eps_growth_estimate: { weight: 0.1 },
    },
  },

  profitability: {
    name: "Profitability",
    description: "Company efficiency and profit margins",
    weight: 0.2,
    factors: {
      roe: { weight: 0.3 },
      roa: { weight: 0.25 },
      gross_margin: { weight: 0.2 },
      operating_margin: { weight: 0.15 },
      net_margin: { weight: 0.1 },
    },
  },

  financial_health: {
    name: "Financial Health",
    description: "Balance sheet strength and stability",
    weight: 0.15,
    factors: {
      debt_to_equity: { weight: 0.3, inverse: true },
      current_ratio: { weight: 0.25 },
      quick_ratio: { weight: 0.2 },
      interest_coverage: { weight: 0.15 },
      free_cash_flow_yield: { weight: 0.1 },
    },
  },

  momentum: {
    name: "Momentum",
    description: "Price and earnings momentum indicators",
    weight: 0.1,
    factors: {
      price_momentum_3m: { weight: 0.3 },
      price_momentum_6m: { weight: 0.25 },
      price_momentum_12m: { weight: 0.2 },
      earnings_revision_trend: { weight: 0.15 },
      relative_strength: { weight: 0.1 },
    },
  },

  quality: {
    name: "Quality",
    description: "Business quality and competitive advantages",
    weight: 0.1,
    factors: {
      revenue_stability: { weight: 0.25 },
      earnings_stability: { weight: 0.25 },
      dividend_consistency: { weight: 0.2 },
      market_share_trend: { weight: 0.15 },
      management_efficiency: { weight: 0.15 },
    },
  },
};

class FactorScoringEngine {
  constructor(customFactors = null) {
    this.factors = customFactors || FACTOR_DEFINITIONS;
    this.universeStats = new Map(); // Cache for universe statistics
  }

  /**
   * Calculate composite score for a stock
   */
  calculateCompositeScore(stockData, universeData = null) {
    try {
      const scores = {};
      let totalScore = 0;
      let totalWeight = 0;

      // Calculate score for each factor category
      for (const [categoryName, categoryDef] of Object.entries(this.factors)) {
        const categoryScore = this.calculateCategoryScore(
          stockData,
          categoryDef,
          universeData
        );

        if (categoryScore !== null) {
          scores[categoryName] = categoryScore;
          totalScore += categoryScore * categoryDef.weight;
          totalWeight += categoryDef.weight;
        }
      }

      // Normalize final score
      const finalScore = totalWeight > 0 ? totalScore / totalWeight : 0;

      return {
        compositeScore: Math.round(finalScore * 100) / 100,
        categoryScores: scores,
        rank: null, // Will be set during universe ranking
        percentile: null, // Will be set during universe ranking
      };
    } catch (error) {
      logger.error("Composite score calculation error", {
        error,
        symbol: stockData && stockData.symbol ? stockData.symbol : 'unknown',
      });
      return null;
    }
  }

  /**
   * Calculate score for a factor category
   */
  calculateCategoryScore(stockData, categoryDef, universeData) {
    let categoryScore = 0;
    let totalWeight = 0;
    let validFactors = 0;

    for (const [factorName, factorDef] of Object.entries(categoryDef.factors)) {
      const rawValue = stockData[factorName];

      if (rawValue !== null && rawValue !== undefined && !isNaN(rawValue)) {
        let normalizedScore;

        if (universeData && universeData.length > 1) {
          // Percentile-based scoring using universe data
          normalizedScore = this.calculatePercentileScore(
            rawValue,
            factorName,
            universeData,
            factorDef.inverse
          );
        } else {
          // Absolute scoring when no universe data available
          normalizedScore = this.calculateAbsoluteScore(
            rawValue,
            factorName,
            factorDef.inverse
          );
        }

        if (normalizedScore !== null) {
          categoryScore += normalizedScore * factorDef.weight;
          totalWeight += factorDef.weight;
          validFactors++;
        }
      }
    }

    // Return null if we don't have enough valid factors
    return validFactors > 0 && totalWeight > 0
      ? categoryScore / totalWeight
      : null;
  }

  /**
   * Calculate percentile-based score within universe
   */
  calculatePercentileScore(value, factorName, universeData, inverse = false) {
    try {
      // Extract values for this factor from universe
      const factorValues = universeData
        .map((stock) => stock[factorName])
        .filter((val) => val !== null && val !== undefined && !isNaN(val))
        .sort((a, b) => a - b);

      if (factorValues.length < 2) {
        return this.calculateAbsoluteScore(value, factorName, inverse);
      }

      // Find percentile rank
      const rank = factorValues.findIndex((val) => val >= value);
      let percentile = rank / factorValues.length;

      // Invert percentile for inverse factors (lower is better)
      if (inverse) {
        percentile = 1 - percentile;
      }

      // Convert to 0-1 score
      return Math.max(0, Math.min(1, percentile));
    } catch (error) {
      logger.warn("Percentile score calculation error", {
        error,
        factorName,
        value,
      });
      return this.calculateAbsoluteScore(value, factorName, inverse);
    }
  }

  /**
   * Calculate absolute score using predefined ranges
   */
  calculateAbsoluteScore(value, factorName, inverse = false) {
    const scoringRanges = this.getFactorScoringRanges(factorName);

    if (!scoringRanges) {
      // Default linear scoring for unknown factors
      return this.linearScore(value, inverse);
    }

    // Find appropriate range and calculate score
    for (const range of scoringRanges) {
      if (value >= range.min && (range.max === null || value <= range.max)) {
        // The ranges are already designed with correct scoring direction for each factor
        // For PE ratio: lower values get higher scores (already inverse-friendly)
        // For growth factors: higher values get higher scores (regular)
        return range.score / 100; // Normalize to 0-1 range
      }
    }

    // Default score if no range matches
    return 0.5; // Normalized to 0-1 range
  }

  /**
   * Get predefined scoring ranges for factors
   */
  getFactorScoringRanges(factorName) {
    const ranges = {
      pe_ratio: [
        { min: 0, max: 10, score: 90 },
        { min: 10, max: 15, score: 80 },
        { min: 15, max: 20, score: 70 },
        { min: 20, max: 25, score: 60 },
        { min: 25, max: 30, score: 50 },
        { min: 30, max: 40, score: 40 },
        { min: 40, max: null, score: 20 },
      ],

      revenue_growth_1y: [
        { min: 0.3, max: null, score: 100 }, // 30%+ growth
        { min: 0.2, max: 0.3, score: 90 },
        { min: 0.15, max: 0.2, score: 80 },
        { min: 0.1, max: 0.15, score: 70 },
        { min: 0.05, max: 0.1, score: 60 },
        { min: 0, max: 0.05, score: 50 },
        { min: -0.05, max: 0, score: 40 },
        { min: -0.1, max: -0.05, score: 30 },
        { min: null, max: -0.1, score: 10 },
      ],

      roe: [
        { min: 0.25, max: null, score: 100 }, // 25%+ ROE
        { min: 0.2, max: 0.25, score: 90 },
        { min: 0.15, max: 0.2, score: 80 },
        { min: 0.1, max: 0.15, score: 70 },
        { min: 0.05, max: 0.1, score: 60 },
        { min: 0, max: 0.05, score: 40 },
        { min: null, max: 0, score: 10 },
      ],

      debt_to_equity: [
        { min: 0, max: 0.3, score: 100 },
        { min: 0.3, max: 0.5, score: 80 },
        { min: 0.5, max: 0.7, score: 60 },
        { min: 0.7, max: 1.0, score: 40 },
        { min: 1.0, max: 1.5, score: 20 },
        { min: 1.5, max: null, score: 10 },
      ],
    };

    return ranges[factorName] || null;
  }

  /**
   * Simple linear scoring fallback
   */
  linearScore(value, inverse = false) {
    // Normalize to 0-1 range using sigmoid function
    const normalized = 1 / (1 + Math.exp(-value * 0.1));
    return inverse ? 1 - normalized : normalized;
  }

  /**
   * Score and rank a universe of stocks
   */
  scoreUniverse(stockData, customWeights = null) {
    try {
      if (!stockData || stockData.length === 0) {
        return [];
      }
      
      logger.info("Starting universe scoring", {
        stockCount: stockData.length,
      });

      if (customWeights) {
        this.applyCustomWeights(customWeights);
      }

      // Calculate scores for all stocks
      const scoredStocks = stockData
        .map((stock) => {
          const score = this.calculateCompositeScore(stock, stockData);
          return {
            ...stock,
            factorScore: score,
          };
        })
        .filter((stock) => stock.factorScore !== null);

      // Sort by composite score
      scoredStocks.sort(
        (a, b) => b.factorScore.compositeScore - a.factorScore.compositeScore
      );

      // Assign ranks and percentiles
      scoredStocks.forEach((stock, index) => {
        stock.factorScore.rank = index + 1;
        stock.factorScore.percentile =
          ((scoredStocks.length - index) / scoredStocks.length) * 100;
      });

      logger.info("Universe scoring completed", {
        scoredStocks: scoredStocks.length,
        topScore: scoredStocks[0]?.factorScore?.compositeScore,
        averageScore:
          scoredStocks.reduce(
            (sum, s) => sum + s.factorScore.compositeScore,
            0
          ) / scoredStocks.length,
      });

      return scoredStocks;
    } catch (error) {
      logger.error("Universe scoring error", { error });
      throw error;
    }
  }

  /**
   * Apply custom factor weights
   */
  applyCustomWeights(customWeights) {
    for (const [categoryName, weight] of Object.entries(customWeights)) {
      if (this.factors[categoryName]) {
        this.factors[categoryName].weight = weight;
      }
    }

    // Normalize weights to sum to 1
    const totalWeight = Object.values(this.factors).reduce(
      (sum, cat) => sum + cat.weight,
      0
    );
    if (totalWeight > 0) {
      for (const category of Object.values(this.factors)) {
        category.weight = category.weight / totalWeight;
      }
    }
  }

  /**
   * Get factor explanations for a stock
   */
  getFactorExplanations(stockData) {
    const explanations = {};

    for (const [categoryName, categoryDef] of Object.entries(this.factors)) {
      const categoryExplanations = [];

      for (const [factorName, factorDef] of Object.entries(
        categoryDef.factors
      )) {
        const value = stockData[factorName];

        if (value !== null && value !== undefined) {
          const score = this.calculateAbsoluteScore(
            value,
            factorName,
            factorDef.inverse
          );

          categoryExplanations.push({
            factor: factorName,
            value: value,
            score: Math.round(score * 100) / 100,
            weight: factorDef.weight,
            interpretation: this.interpretFactorScore(factorName, value, score),
          });
        }
      }

      explanations[categoryName] = {
        name: categoryDef.name,
        description: categoryDef.description,
        weight: categoryDef.weight,
        factors: categoryExplanations,
      };
    }

    return explanations;
  }

  /**
   * Interpret factor score with human-readable description
   */
  interpretFactorScore(factorName, value, score) {
    if (score >= 80) return "Excellent";
    if (score >= 70) return "Good";
    if (score >= 60) return "Above Average";
    if (score >= 40) return "Average";
    if (score >= 30) return "Below Average";
    return "Poor";
  }

  /**
   * Get factor definitions
   */
  getFactorDefinitions() {
    return this.factors;
  }

  /**
   * Create custom scoring profile
   */
  createCustomProfile(name, categoryWeights, description = "") {
    return {
      name: name,
      description: description,
      weights: categoryWeights,
      created_at: new Date().toISOString(),
    };
  }

  /**
   * Rank stocks in universe by composite score
   */
  rankUniverse(stockData) {
    if (!stockData || stockData.length === 0) {
      return [];
    }
    
    const scoredStocks = this.scoreUniverse(stockData);
    return scoredStocks.map((stock, index) => {
      // Ensure the factorScore properties are available at the top level for tests
      const result = {
        ...stock,
        rank: index + 1,
      };
      
      if (stock.factorScore) {
        result.compositeScore = stock.factorScore.compositeScore;
        result.percentile = stock.factorScore.percentile;
        result.categoryScores = stock.factorScore.categoryScores;
      }
      
      return result;
    });
  }

  /**
   * Calculate universe statistics for caching
   */
  calculateUniverseStats(universeData) {
    const stats = new Map();
    
    // Calculate statistics for each factor
    const allFactors = Object.values(this.factors).flatMap(cat => 
      Object.keys(cat.factors)
    );
    
    for (const factorName of allFactors) {
      const values = universeData
        .map(stock => stock[factorName])
        .filter(val => val !== null && val !== undefined && !isNaN(val));
      
      if (values.length > 0) {
        values.sort((a, b) => a - b);
        const mean = values.reduce((sum, val) => sum + val, 0) / values.length;
        const variance = this.calculateVariance(values);
        const std = Math.sqrt(variance);
        
        stats.set(factorName, {
          min: values[0],
          max: values[values.length - 1],
          median: values[Math.floor(values.length / 2)],
          mean: mean,
          std: std,
          count: values.length
        });
      }
    }
    
    this.universeStats = stats;
    return stats;
  }

  /**
   * Analyze factors across universe
   */
  analyzeFactors(universeData) {
    const stats = this.calculateUniverseStats(universeData);
    const correlations = this.calculateFactorCorrelations(universeData);
    
    // Calculate distributions for each factor
    const distributions = {};
    for (const [factorName, factorStats] of stats.entries()) {
      distributions[factorName] = {
        min: factorStats.min,
        max: factorStats.max,
        mean: factorStats.mean,
        median: factorStats.median,
        quartiles: this.calculateQuartiles(universeData, factorName)
      };
    }
    
    return {
      factorStats: Object.fromEntries(stats),
      correlations: correlations,
      distributions: distributions,
      sampleSize: universeData.length
    };
  }

  /**
   * Calculate correlations between factors
   */
  calculateFactorCorrelations(universeData) {
    const correlations = {};
    const allFactors = Object.values(this.factors).flatMap(cat => 
      Object.keys(cat.factors)
    );
    
    for (const factor1 of allFactors) {
      correlations[factor1] = {};
      for (const factor2 of allFactors) {
        if (factor1 !== factor2) {
          correlations[factor1][factor2] = this.calculateCorrelation(
            universeData, factor1, factor2
          );
        }
      }
    }
    
    return correlations;
  }

  /**
   * Calculate correlation between two factors
   */
  calculateCorrelation(universeData, factor1, factor2) {
    const pairs = universeData
      .map(stock => [stock[factor1], stock[factor2]])
      .filter(([val1, val2]) => 
        val1 !== null && val1 !== undefined && !isNaN(val1) &&
        val2 !== null && val2 !== undefined && !isNaN(val2)
      );
    
    if (pairs.length < 2) return 0;
    
    const n = pairs.length;
    const sum1 = pairs.reduce((sum, [val1]) => sum + val1, 0);
    const sum2 = pairs.reduce((sum, [, val2]) => sum + val2, 0);
    const sum1Sq = pairs.reduce((sum, [val1]) => sum + val1 * val1, 0);
    const sum2Sq = pairs.reduce((sum, [, val2]) => sum + val2 * val2, 0);
    const sumProd = pairs.reduce((sum, [val1, val2]) => sum + val1 * val2, 0);
    
    const numerator = n * sumProd - sum1 * sum2;
    const denominator = Math.sqrt(
      (n * sum1Sq - sum1 * sum1) * (n * sum2Sq - sum2 * sum2)
    );
    
    return denominator === 0 ? 0 : numerator / denominator;
  }

  /**
   * Identify top performing factors
   */
  identifyTopFactors(universeData, topN = 5) {
    const factorPerformance = [];
    const allFactors = Object.values(this.factors).flatMap(cat => 
      Object.keys(cat.factors)
    );
    
    for (const factorName of allFactors) {
      const values = universeData
        .map(stock => stock[factorName])
        .filter(val => val !== null && val !== undefined && !isNaN(val));
      
      if (values.length > 1) {
        const variance = this.calculateVariance(values);
        const range = Math.max(...values) - Math.min(...values);
        
        // Find the category and weight for this factor
        let category = 'unknown';
        let weight = 0;
        for (const [catName, catDef] of Object.entries(this.factors)) {
          if (catDef.factors[factorName]) {
            category = catName;
            weight = catDef.factors[factorName].weight || 0;
            break;
          }
        }
        
        factorPerformance.push({
          factor: factorName,
          name: factorName.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
          category: category,
          impact: variance,
          significance: range,
          variance: variance,
          range: range,
          discriminationPower: variance * range, // Combined metric
          dataPoints: values.length,
          weight: weight
        });
      }
    }
    
    return factorPerformance
      .sort((a, b) => b.discriminationPower - a.discriminationPower)
      .slice(0, topN);
  }

  /**
   * Calculate variance of an array of values
   */
  calculateVariance(values) {
    if (values.length < 2) return 0;
    
    const mean = values.reduce((sum, val) => sum + val, 0) / values.length;
    const squaredDiffs = values.map(val => Math.pow(val - mean, 2));
    return squaredDiffs.reduce((sum, diff) => sum + diff, 0) / values.length;
  }

  /**
   * Normalize an array of factor values to 0-1 range
   */
  normalizeFactors(values, inverse = false) {
    if (!values || values.length === 0) {
      return [];
    }
    
    if (values.length === 1) {
      return [0.5]; // Single value normalizes to middle
    }
    
    const min = Math.min(...values);
    const max = Math.max(...values);
    
    // Handle identical values
    if (min === max) {
      return values.map(() => 0.5);
    }
    
    const range = max - min;
    return values.map(value => {
      const normalized = (value - min) / range;
      return inverse ? 1 - normalized : normalized;
    });
  }

  /**
   * Calculate quartiles for a factor in the universe
   */
  calculateQuartiles(universeData, factorName) {
    const values = universeData
      .map(stock => stock[factorName])
      .filter(val => val !== null && val !== undefined && !isNaN(val))
      .sort((a, b) => a - b);
    
    if (values.length < 4) {
      return {
        q1: values[0] || 0,
        q2: values[Math.floor(values.length / 2)] || 0,
        q3: values[values.length - 1] || 0
      };
    }
    
    const q1Index = Math.floor(values.length * 0.25);
    const q2Index = Math.floor(values.length * 0.5);
    const q3Index = Math.floor(values.length * 0.75);
    
    return {
      q1: values[q1Index],
      q2: values[q2Index],
      q3: values[q3Index]
    };
  }

  /**
   * Screen stocks using factor scores
   */
  screenByFactors(scoredStocks, criteria) {
    return scoredStocks.filter((stock) => {
      const score = stock.factorScore;

      if (!score) return false;

      // Overall score filter
      if (
        criteria.minCompositeScore &&
        score.compositeScore < criteria.minCompositeScore
      ) {
        return false;
      }

      if (
        criteria.maxCompositeScore &&
        score.compositeScore > criteria.maxCompositeScore
      ) {
        return false;
      }

      // Percentile filter
      if (criteria.minPercentile && score.percentile < criteria.minPercentile) {
        return false;
      }

      // Category score filters
      if (criteria.categoryFilters) {
        for (const [category, minScore] of Object.entries(
          criteria.categoryFilters
        )) {
          if (
            score.categoryScores[category] &&
            score.categoryScores[category] < minScore
          ) {
            return false;
          }
        }
      }

      return true;
    });
  }
}

// Export singleton instance and class
const factorScoringEngine = new FactorScoringEngine();

module.exports = {
  FactorScoringEngine,
  calculateCompositeScore: (stockData, universeData) =>
    factorScoringEngine.calculateCompositeScore(stockData, universeData),
  scoreUniverse: (stockData, customWeights) =>
    factorScoringEngine.scoreUniverse(stockData, customWeights),
  getFactorExplanations: (stockData) =>
    factorScoringEngine.getFactorExplanations(stockData),
  getFactorDefinitions: () => factorScoringEngine.getFactorDefinitions(),
  createCustomProfile: (name, weights, description) =>
    factorScoringEngine.createCustomProfile(name, weights, description),
  screenByFactors: (scoredStocks, criteria) =>
    factorScoringEngine.screenByFactors(scoredStocks, criteria),
  FACTOR_DEFINITIONS,
};
