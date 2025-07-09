const { query } = require('./database');

class FactorScoringEngine {
  constructor() {
    this.factors = {
      // Financial Health Factors
      debt_to_equity: { weight: 0.15, type: 'lower_better', optimal: 0.3 },
      current_ratio: { weight: 0.12, type: 'higher_better', optimal: 2.0 },
      quick_ratio: { weight: 0.10, type: 'higher_better', optimal: 1.5 },
      interest_coverage: { weight: 0.08, type: 'higher_better', optimal: 5.0 },
      
      // Profitability Factors
      roe: { weight: 0.18, type: 'higher_better', optimal: 0.15 },
      roa: { weight: 0.15, type: 'higher_better', optimal: 0.08 },
      gross_margin: { weight: 0.12, type: 'higher_better', optimal: 0.4 },
      operating_margin: { weight: 0.15, type: 'higher_better', optimal: 0.15 },
      net_margin: { weight: 0.12, type: 'higher_better', optimal: 0.10 },
      
      // Growth Factors
      revenue_growth: { weight: 0.20, type: 'higher_better', optimal: 0.15 },
      earnings_growth: { weight: 0.18, type: 'higher_better', optimal: 0.12 },
      eps_growth: { weight: 0.15, type: 'higher_better', optimal: 0.10 },
      
      // Valuation Factors
      pe_ratio: { weight: 0.15, type: 'optimal_range', optimal: 20, range: [10, 30] },
      pb_ratio: { weight: 0.12, type: 'lower_better', optimal: 1.5 },
      ps_ratio: { weight: 0.10, type: 'lower_better', optimal: 2.0 },
      peg_ratio: { weight: 0.18, type: 'optimal_range', optimal: 1.0, range: [0.5, 2.0] },
      
      // Efficiency Factors
      asset_turnover: { weight: 0.12, type: 'higher_better', optimal: 1.0 },
      inventory_turnover: { weight: 0.08, type: 'higher_better', optimal: 6.0 },
      
      // Market Factors
      market_cap: { weight: 0.05, type: 'neutral', optimal: null },
      beta: { weight: 0.08, type: 'optimal_range', optimal: 1.0, range: [0.5, 1.5] },
      
      // Technical Factors
      price_momentum_3m: { weight: 0.10, type: 'higher_better', optimal: 0.1 },
      price_momentum_12m: { weight: 0.12, type: 'higher_better', optimal: 0.2 },
      rsi: { weight: 0.08, type: 'optimal_range', optimal: 50, range: [30, 70] },
      
      // Dividend Factors
      dividend_yield: { weight: 0.10, type: 'higher_better', optimal: 0.03 },
      dividend_growth: { weight: 0.08, type: 'higher_better', optimal: 0.05 },
      payout_ratio: { weight: 0.06, type: 'optimal_range', optimal: 0.4, range: [0.2, 0.6] }
    };
  }

  // Calculate individual factor score (0-100)
  calculateFactorScore(value, factor) {
    if (value === null || value === undefined || isNaN(value)) {
      return 50; // Neutral score for missing data
    }

    const { type, optimal, range } = factor;

    switch (type) {
      case 'higher_better':
        return this.calculateHigherBetterScore(value, optimal);
      
      case 'lower_better':
        return this.calculateLowerBetterScore(value, optimal);
      
      case 'optimal_range':
        return this.calculateOptimalRangeScore(value, optimal, range);
      
      case 'neutral':
        return 50;
      
      default:
        return 50;
    }
  }

  calculateHigherBetterScore(value, optimal) {
    if (value >= optimal) {
      return Math.min(100, 50 + (value / optimal) * 25);
    } else {
      return Math.max(0, (value / optimal) * 50);
    }
  }

  calculateLowerBetterScore(value, optimal) {
    if (value <= optimal) {
      return Math.max(50, 100 - (value / optimal) * 25);
    } else {
      return Math.max(0, 100 - (value / optimal) * 50);
    }
  }

  calculateOptimalRangeScore(value, optimal, range) {
    const [min, max] = range;
    
    if (value >= min && value <= max) {
      const distanceFromOptimal = Math.abs(value - optimal);
      const maxDistance = Math.max(optimal - min, max - optimal);
      return Math.max(50, 100 - (distanceFromOptimal / maxDistance) * 50);
    } else if (value < min) {
      return Math.max(0, 50 - ((min - value) / min) * 50);
    } else {
      return Math.max(0, 50 - ((value - max) / max) * 50);
    }
  }

  // Calculate composite score for a stock
  async calculateCompositeScore(stockData) {
    let totalScore = 0;
    let totalWeight = 0;
    const factorScores = {};

    for (const [factorName, factorConfig] of Object.entries(this.factors)) {
      const value = stockData[factorName];
      const score = this.calculateFactorScore(value, factorConfig);
      
      factorScores[factorName] = {
        value: value,
        score: score,
        weight: factorConfig.weight
      };
      
      totalScore += score * factorConfig.weight;
      totalWeight += factorConfig.weight;
    }

    const compositeScore = totalWeight > 0 ? totalScore / totalWeight : 50;

    return {
      compositeScore: Math.round(compositeScore),
      factorScores: factorScores,
      grade: this.getGrade(compositeScore),
      riskLevel: this.getRiskLevel(stockData),
      recommendation: this.getRecommendation(compositeScore)
    };
  }

  getGrade(score) {
    if (score >= 90) return 'A+';
    if (score >= 85) return 'A';
    if (score >= 80) return 'A-';
    if (score >= 75) return 'B+';
    if (score >= 70) return 'B';
    if (score >= 65) return 'B-';
    if (score >= 60) return 'C+';
    if (score >= 55) return 'C';
    if (score >= 50) return 'C-';
    if (score >= 45) return 'D+';
    if (score >= 40) return 'D';
    return 'F';
  }

  getRiskLevel(stockData) {
    const beta = stockData.beta || 1.0;
    const debtToEquity = stockData.debt_to_equity || 0.5;
    const currentRatio = stockData.current_ratio || 1.5;
    
    let riskScore = 0;
    
    // Beta risk
    if (beta > 1.5) riskScore += 3;
    else if (beta > 1.2) riskScore += 2;
    else if (beta < 0.5) riskScore += 1;
    
    // Debt risk
    if (debtToEquity > 1.0) riskScore += 3;
    else if (debtToEquity > 0.6) riskScore += 2;
    else if (debtToEquity > 0.3) riskScore += 1;
    
    // Liquidity risk
    if (currentRatio < 1.0) riskScore += 3;
    else if (currentRatio < 1.5) riskScore += 2;
    
    if (riskScore >= 6) return 'High';
    if (riskScore >= 3) return 'Medium';
    return 'Low';
  }

  getRecommendation(score) {
    if (score >= 80) return 'Strong Buy';
    if (score >= 70) return 'Buy';
    if (score >= 60) return 'Hold';
    if (score >= 50) return 'Weak Hold';
    if (score >= 40) return 'Sell';
    return 'Strong Sell';
  }

  // Get stocks with factor scores from database
  async getStocksWithFactorScores(filters = {}) {
    try {
      let whereClause = 'WHERE 1=1';
      const params = [];
      let paramIndex = 1;

      // Add filters
      if (filters.minScore) {
        whereClause += ` AND factor_score >= $${paramIndex}`;
        params.push(filters.minScore);
        paramIndex++;
      }

      if (filters.maxScore) {
        whereClause += ` AND factor_score <= $${paramIndex}`;
        params.push(filters.maxScore);
        paramIndex++;
      }

      if (filters.sector) {
        whereClause += ` AND sector = $${paramIndex}`;
        params.push(filters.sector);
        paramIndex++;
      }

      if (filters.minMarketCap) {
        whereClause += ` AND market_cap >= $${paramIndex}`;
        params.push(filters.minMarketCap);
        paramIndex++;
      }

      if (filters.maxMarketCap) {
        whereClause += ` AND market_cap <= $${paramIndex}`;
        params.push(filters.maxMarketCap);
        paramIndex++;
      }

      const stocksQuery = `
        SELECT 
          symbol,
          company_name,
          sector,
          market_cap,
          price,
          
          -- Financial Health
          debt_to_equity,
          current_ratio,
          quick_ratio,
          interest_coverage,
          
          -- Profitability
          roe,
          roa,
          gross_margin,
          operating_margin,
          net_margin,
          
          -- Growth
          revenue_growth,
          earnings_growth,
          eps_growth,
          
          -- Valuation
          pe_ratio,
          pb_ratio,
          ps_ratio,
          peg_ratio,
          
          -- Efficiency
          asset_turnover,
          inventory_turnover,
          
          -- Market
          beta,
          
          -- Technical
          price_momentum_3m,
          price_momentum_12m,
          rsi,
          
          -- Dividend
          dividend_yield,
          dividend_growth,
          payout_ratio,
          
          -- Cached score if available
          factor_score,
          last_updated
          
        FROM stock_fundamentals sf
        JOIN stock_symbols_enhanced sse ON sf.symbol = sse.symbol
        ${whereClause}
        ORDER BY 
          CASE 
            WHEN factor_score IS NOT NULL THEN factor_score 
            ELSE 50 
          END DESC,
          market_cap DESC
        LIMIT ${filters.limit || 100}
      `;

      const result = await query(stocksQuery, params);
      
      // Calculate scores for stocks that don't have cached scores
      const stocksWithScores = await Promise.all(
        result.rows.map(async (stock) => {
          if (!stock.factor_score || this.isStaleScore(stock.last_updated)) {
            const scoreData = await this.calculateCompositeScore(stock);
            
            // Cache the score in database
            await this.cacheFactorScore(stock.symbol, scoreData.compositeScore);
            
            return {
              ...stock,
              factor_score: scoreData.compositeScore,
              grade: scoreData.grade,
              risk_level: scoreData.riskLevel,
              recommendation: scoreData.recommendation,
              factor_breakdown: scoreData.factorScores
            };
          }
          
          return {
            ...stock,
            grade: this.getGrade(stock.factor_score),
            risk_level: this.getRiskLevel(stock),
            recommendation: this.getRecommendation(stock.factor_score)
          };
        })
      );

      return stocksWithScores;
    } catch (error) {
      console.error('Error getting stocks with factor scores:', error);
      throw error;
    }
  }

  // Cache factor score in database
  async cacheFactorScore(symbol, score) {
    try {
      await query(`
        UPDATE stock_fundamentals 
        SET factor_score = $1, last_updated = NOW()
        WHERE symbol = $2
      `, [score, symbol]);
    } catch (error) {
      console.error('Error caching factor score:', error);
    }
  }

  // Check if cached score is stale (older than 1 day)
  isStaleScore(lastUpdated) {
    if (!lastUpdated) return true;
    const oneDayAgo = new Date(Date.now() - 24 * 60 * 60 * 1000);
    return new Date(lastUpdated) < oneDayAgo;
  }

  // Get top performers by factor
  async getTopPerformersByFactor(factorName, limit = 20) {
    try {
      const factor = this.factors[factorName];
      if (!factor) {
        throw new Error(`Unknown factor: ${factorName}`);
      }

      const orderBy = factor.type === 'lower_better' ? 'ASC' : 'DESC';
      
      const result = await query(`
        SELECT 
          symbol,
          company_name,
          sector,
          ${factorName} as factor_value,
          factor_score,
          market_cap,
          price
        FROM stock_fundamentals sf
        JOIN stock_symbols_enhanced sse ON sf.symbol = sse.symbol
        WHERE ${factorName} IS NOT NULL
        ORDER BY ${factorName} ${orderBy}
        LIMIT $1
      `, [limit]);

      return result.rows.map(stock => ({
        ...stock,
        factor_name: factorName,
        factor_score_individual: this.calculateFactorScore(stock.factor_value, factor)
      }));
    } catch (error) {
      console.error('Error getting top performers by factor:', error);
      throw error;
    }
  }

  // Get sector analysis with factor scores
  async getSectorAnalysis() {
    try {
      const result = await query(`
        SELECT 
          sector,
          COUNT(*) as stock_count,
          AVG(factor_score) as avg_factor_score,
          AVG(pe_ratio) as avg_pe,
          AVG(roe) as avg_roe,
          AVG(debt_to_equity) as avg_debt_to_equity,
          AVG(revenue_growth) as avg_revenue_growth,
          SUM(market_cap) as total_market_cap
        FROM stock_fundamentals sf
        JOIN stock_symbols_enhanced sse ON sf.symbol = sse.symbol
        WHERE sector IS NOT NULL
        GROUP BY sector
        ORDER BY avg_factor_score DESC
      `);

      return result.rows.map(sector => ({
        ...sector,
        grade: this.getGrade(sector.avg_factor_score || 50),
        relative_strength: this.calculateRelativeStrength(sector.avg_factor_score || 50)
      }));
    } catch (error) {
      console.error('Error getting sector analysis:', error);
      throw error;
    }
  }

  calculateRelativeStrength(score) {
    if (score >= 70) return 'Strong';
    if (score >= 60) return 'Above Average';
    if (score >= 50) return 'Average';
    if (score >= 40) return 'Below Average';
    return 'Weak';
  }
}

module.exports = FactorScoringEngine;