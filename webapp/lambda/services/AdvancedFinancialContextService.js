/**
 * Advanced Financial Context Service
 * 
 * Provides sophisticated financial analysis and context for AI responses:
 * - Advanced portfolio analytics and risk assessment
 * - Market sentiment and trend analysis
 * - Investment research and recommendations
 * - Financial planning and optimization
 * - Real-time market data integration
 */

const { query } = require('../utils/database');

class AdvancedFinancialContextService {
  constructor() {
    this.cache = new Map();
    this.cacheTimeout = 5 * 60 * 1000; // 5 minutes
    
    // Financial analysis configuration
    this.config = {
      riskFreeRate: 0.045, // 4.5% (10-year Treasury)
      marketBenchmarks: {
        'SPY': { name: 'S&P 500', type: 'large_cap', weight: 0.6 },
        'QQQ': { name: 'NASDAQ 100', type: 'tech_growth', weight: 0.2 },
        'IWM': { name: 'Russell 2000', type: 'small_cap', weight: 0.1 },
        'VTI': { name: 'Total Stock Market', type: 'broad_market', weight: 0.1 }
      },
      sectorMappings: {
        'Technology': 'tech',
        'Healthcare': 'healthcare',
        'Financial Services': 'financial',
        'Consumer Cyclical': 'consumer_cyclical',
        'Communication Services': 'communication',
        'Industrials': 'industrial',
        'Consumer Defensive': 'consumer_defensive',
        'Energy': 'energy',
        'Utilities': 'utilities',
        'Real Estate': 'real_estate',
        'Basic Materials': 'materials'
      },
      analysisDepth: {
        basic: ['portfolio_value', 'daily_change', 'allocation'],
        intermediate: ['risk_metrics', 'performance_attribution', 'correlation'],
        advanced: ['optimization', 'scenario_analysis', 'factor_exposure']
      }
    };
  }

  /**
   * Get comprehensive financial context for AI responses
   */
  async getComprehensiveFinancialContext(userId, options = {}) {
    try {
      const {
        depth = 'intermediate',
        includeMarketData = true,
        includeOptimization = false,
        timeframe = '1M'
      } = options;

      console.log(`📊 Building comprehensive financial context for user ${userId} (depth: ${depth})`);

      const context = {
        timestamp: new Date(),
        analysisDepth: depth,
        timeframe: timeframe
      };

      // Get portfolio data with enhanced analytics
      context.portfolio = await this.getEnhancedPortfolioAnalysis(userId, depth);
      
      // Get market context
      if (includeMarketData) {
        context.market = await this.getAdvancedMarketContext();
      }

      // Get investment opportunities
      context.opportunities = await this.getInvestmentOpportunities(userId);

      // Get risk analysis
      context.riskAnalysis = await this.getPortfolioRiskAnalysis(userId);

      // Get performance attribution
      if (depth !== 'basic') {
        context.performance = await this.getPerformanceAttribution(userId, timeframe);
      }

      // Get portfolio optimization suggestions
      if (includeOptimization || depth === 'advanced') {
        context.optimization = await this.getPortfolioOptimizationSuggestions(userId);
      }

      // Get tax optimization opportunities
      context.taxOptimization = await this.getTaxOptimizationOpportunities(userId);

      // Get financial health score
      context.financialHealth = await this.calculateFinancialHealthScore(userId);

      console.log('✅ Comprehensive financial context built successfully');
      return context;

    } catch (error) {
      console.error('❌ Error building comprehensive financial context:', error);
      return this.getFallbackContext();
    }
  }

  /**
   * Get enhanced portfolio analysis
   */
  async getEnhancedPortfolioAnalysis(userId, depth = 'intermediate') {
    try {
      const cacheKey = `portfolio_${userId}_${depth}`;
      const cached = this.cache.get(cacheKey);
      if (cached && Date.now() - cached.timestamp < this.cacheTimeout) {
        return cached.data;
      }

      // Get portfolio holdings with detailed metrics
      const holdingsQuery = await query(`
        SELECT 
          ph.symbol,
          ph.quantity,
          ph.avg_cost,
          ph.current_price,
          ph.market_value,
          ph.unrealized_pl,
          ph.unrealized_plpc,
          ph.last_updated,
          s.sector,
          s.market_cap,
          s.pe_ratio,
          s.dividend_yield,
          s.beta,
          s.volume,
          s.change_percent as day_change,
          s.week_52_high,
          s.week_52_low
        FROM portfolio_holdings ph
        LEFT JOIN stocks s ON ph.symbol = s.symbol
        WHERE ph.user_id = $1 AND ph.quantity > 0
        ORDER BY ph.market_value DESC
      `, [userId]);

      if (holdingsQuery.rows.length === 0) {
        return {
          isEmpty: true,
          message: 'No portfolio holdings found',
          suggestions: [
            'Start by adding your first investment',
            'Consider index funds for diversification',
            'Set up automatic investing'
          ]
        };
      }

      const holdings = holdingsQuery.rows;
      
      // Calculate basic portfolio metrics
      const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value || 0), 0);
      const totalGainLoss = holdings.reduce((sum, h) => sum + parseFloat(h.unrealized_pl || 0), 0);
      const totalCost = totalValue - totalGainLoss;

      // Calculate sector allocation
      const sectorAllocation = this.calculateSectorAllocation(holdings, totalValue);

      // Calculate diversification metrics
      const diversificationMetrics = this.calculateDiversificationMetrics(holdings, totalValue);

      // Basic analysis
      const analysis = {
        totalValue,
        totalCost,
        totalGainLoss,
        totalReturn: totalCost > 0 ? (totalGainLoss / totalCost) * 100 : 0,
        holdingsCount: holdings.length,
        sectorAllocation,
        diversificationMetrics,
        topHoldings: holdings.slice(0, 10).map(h => ({
          symbol: h.symbol,
          weight: (parseFloat(h.market_value) / totalValue) * 100,
          dayChange: parseFloat(h.day_change || 0),
          totalReturn: parseFloat(h.unrealized_plpc || 0),
          sector: h.sector
        }))
      };

      // Intermediate analysis
      if (depth !== 'basic') {
        analysis.riskMetrics = await this.calculatePortfolioRiskMetrics(holdings, totalValue);
        analysis.correlationAnalysis = await this.calculateCorrelationAnalysis(holdings);
        analysis.factorExposure = await this.calculateFactorExposure(holdings, totalValue);
      }

      // Advanced analysis
      if (depth === 'advanced') {
        analysis.volatilityAnalysis = await this.calculateVolatilityAnalysis(holdings);
        analysis.drawdownAnalysis = await this.calculateDrawdownAnalysis(userId);
        analysis.scenarioAnalysis = await this.performScenarioAnalysis(holdings, totalValue);
      }

      // Cache result
      this.cache.set(cacheKey, {
        data: analysis,
        timestamp: Date.now()
      });

      return analysis;

    } catch (error) {
      console.error('❌ Error in enhanced portfolio analysis:', error);
      return { error: 'Portfolio analysis temporarily unavailable' };
    }
  }

  /**
   * Calculate sector allocation
   */
  calculateSectorAllocation(holdings, totalValue) {
    const sectorTotals = {};
    
    holdings.forEach(holding => {
      const sector = holding.sector || 'Unknown';
      const value = parseFloat(holding.market_value || 0);
      sectorTotals[sector] = (sectorTotals[sector] || 0) + value;
    });

    const allocation = {};
    Object.entries(sectorTotals).forEach(([sector, value]) => {
      allocation[sector] = {
        value,
        percentage: (value / totalValue) * 100,
        holdings: holdings.filter(h => (h.sector || 'Unknown') === sector).length
      };
    });

    return allocation;
  }

  /**
   * Calculate diversification metrics
   */
  calculateDiversificationMetrics(holdings, totalValue) {
    // Concentration metrics
    const weights = holdings.map(h => parseFloat(h.market_value) / totalValue);
    const concentrationRatio = Math.max(...weights) * 100;
    
    // Herfindahl-Hirschman Index (HHI)
    const hhi = weights.reduce((sum, weight) => sum + weight * weight, 0) * 10000;
    
    // Effective number of stocks
    const effectiveStocks = 1 / weights.reduce((sum, weight) => sum + weight * weight, 0);

    // Diversification score (0-100)
    let diversificationScore = 0;
    if (holdings.length >= 20) diversificationScore += 30;
    else if (holdings.length >= 10) diversificationScore += 20;
    else if (holdings.length >= 5) diversificationScore += 10;
    
    if (concentrationRatio < 10) diversificationScore += 25;
    else if (concentrationRatio < 20) diversificationScore += 15;
    else if (concentrationRatio < 30) diversificationScore += 5;
    
    // Sector diversity bonus
    const sectorCount = new Set(holdings.map(h => h.sector)).size;
    if (sectorCount >= 8) diversificationScore += 25;
    else if (sectorCount >= 5) diversificationScore += 15;
    else if (sectorCount >= 3) diversificationScore += 5;

    // International exposure bonus
    const internationalHoldings = holdings.filter(h => 
      h.symbol && (h.symbol.includes('.') || h.symbol.length > 4)
    ).length;
    if (internationalHoldings > 0) diversificationScore += 20;

    return {
      score: Math.min(100, diversificationScore),
      concentrationRatio,
      hhi,
      effectiveStocks,
      sectorCount,
      internationalExposure: (internationalHoldings / holdings.length) * 100,
      recommendation: this.getDiversificationRecommendation(diversificationScore, concentrationRatio)
    };
  }

  /**
   * Get diversification recommendation
   */
  getDiversificationRecommendation(score, concentration) {
    if (score >= 80) {
      return 'Excellent diversification. Consider international exposure if lacking.';
    } else if (score >= 60) {
      return 'Good diversification. Consider adding more sectors or reducing concentration.';
    } else if (concentration > 25) {
      return 'High concentration risk. Consider reducing largest positions.';
    } else {
      return 'Poor diversification. Add more holdings across different sectors.';
    }
  }

  /**
   * Calculate portfolio risk metrics
   */
  async calculatePortfolioRiskMetrics(holdings, totalValue) {
    try {
      // Calculate portfolio beta
      let portfolioBeta = 0;
      let betaWeightedSum = 0;
      
      holdings.forEach(holding => {
        const weight = parseFloat(holding.market_value) / totalValue;
        const beta = parseFloat(holding.beta || 1.0);
        portfolioBeta += weight * beta;
        betaWeightedSum += weight;
      });
      
      portfolioBeta = betaWeightedSum > 0 ? portfolioBeta : 1.0;

      // Calculate Value at Risk (VaR) - simplified
      const avgReturn = holdings.reduce((sum, h) => {
        const weight = parseFloat(h.market_value) / totalValue;
        const returnRate = parseFloat(h.unrealized_plpc || 0) / 100;
        return sum + weight * returnRate;
      }, 0);

      // Estimate portfolio volatility (simplified)
      const weights = holdings.map(h => parseFloat(h.market_value) / totalValue);
      const avgVolatility = 0.20; // Assume 20% average volatility
      const portfolioVolatility = avgVolatility * Math.sqrt(weights.reduce((sum, w) => sum + w * w, 0));

      // 95% VaR (1-day)
      const var95 = totalValue * (avgReturn - 1.645 * portfolioVolatility);

      // Calculate Sharpe ratio (simplified)
      const excessReturn = avgReturn - this.config.riskFreeRate / 365;
      const sharpeRatio = portfolioVolatility > 0 ? excessReturn / portfolioVolatility : 0;

      return {
        beta: portfolioBeta,
        volatility: portfolioVolatility * 100,
        var95: Math.abs(var95),
        var95Percentage: Math.abs(var95 / totalValue) * 100,
        sharpeRatio,
        riskAdjustedReturn: sharpeRatio * 100,
        riskRating: this.getRiskRating(portfolioBeta, portfolioVolatility),
        recommendations: this.getRiskRecommendations(portfolioBeta, portfolioVolatility, sharpeRatio)
      };

    } catch (error) {
      console.error('❌ Error calculating risk metrics:', error);
      return { error: 'Risk metrics calculation failed' };
    }
  }

  /**
   * Get risk rating
   */
  getRiskRating(beta, volatility) {
    if (beta > 1.3 || volatility > 0.25) return 'High';
    if (beta > 1.1 || volatility > 0.18) return 'Moderate-High';
    if (beta > 0.9 || volatility > 0.12) return 'Moderate';
    if (beta > 0.7 || volatility > 0.08) return 'Moderate-Low';
    return 'Low';
  }

  /**
   * Get risk recommendations
   */
  getRiskRecommendations(beta, volatility, sharpe) {
    const recommendations = [];

    if (beta > 1.3) {
      recommendations.push('Consider adding defensive stocks or bonds to reduce market risk');
    }
    
    if (volatility > 0.25) {
      recommendations.push('High volatility detected - consider diversifying into stable dividend stocks');
    }
    
    if (sharpe < 0.5) {
      recommendations.push('Low risk-adjusted returns - review underperforming positions');
    }

    if (recommendations.length === 0) {
      recommendations.push('Risk profile is well-balanced for your portfolio size');
    }

    return recommendations;
  }

  /**
   * Get advanced market context
   */
  async getAdvancedMarketContext() {
    try {
      const cacheKey = 'market_context_advanced';
      const cached = this.cache.get(cacheKey);
      if (cached && Date.now() - cached.timestamp < this.cacheTimeout) {
        return cached.data;
      }

      // Get market indices with technical indicators
      const indicesQuery = await query(`
        SELECT 
          symbol, current_price, change_percent, volume,
          week_52_high, week_52_low, pe_ratio, dividend_yield,
          updated_at
        FROM stocks 
        WHERE symbol IN ('SPY', 'QQQ', 'DIA', 'VTI', 'IWM', 'TLT', 'GLD')
        AND updated_at > NOW() - INTERVAL '2 hours'
        ORDER BY symbol
      `);

      // Get sector performance
      const sectorQuery = await query(`
        SELECT 
          sector,
          AVG(change_percent) as avg_change,
          AVG(pe_ratio) as avg_pe,
          AVG(dividend_yield) as avg_dividend_yield,
          COUNT(*) as stock_count,
          SUM(volume) as total_volume
        FROM stocks 
        WHERE sector IS NOT NULL 
        AND updated_at > NOW() - INTERVAL '2 hours'
        GROUP BY sector
        ORDER BY avg_change DESC
      `);

      // Get market indicators
      const indicatorsQuery = await query(`
        SELECT 
          indicator_name, value, date, updated_at,
          LAG(value) OVER (PARTITION BY indicator_name ORDER BY date) as prev_value
        FROM market_indicators 
        WHERE indicator_name IN ('VIX', 'FEAR_GREED_INDEX', 'PUT_CALL_RATIO', 'YIELD_CURVE_10Y2Y')
        AND date >= CURRENT_DATE - INTERVAL '30 days'
        ORDER BY indicator_name, date DESC
      `);

      // Process market data
      const marketContext = {
        indices: this.processIndicesData(indicesQuery.rows),
        sectors: this.processSectorData(sectorQuery.rows),
        indicators: this.processIndicatorsData(indicatorsQuery.rows),
        sentiment: this.calculateMarketSentiment(indicesQuery.rows, indicatorsQuery.rows),
        trends: this.analyzeMarketTrends(indicesQuery.rows),
        lastUpdated: new Date()
      };

      // Cache result
      this.cache.set(cacheKey, {
        data: marketContext,
        timestamp: Date.now()
      });

      return marketContext;

    } catch (error) {
      console.error('❌ Error getting advanced market context:', error);
      return { error: 'Market data temporarily unavailable' };
    }
  }

  /**
   * Process indices data
   */
  processIndicesData(rows) {
    const indices = {};
    
    rows.forEach(row => {
      const key = row.symbol.toLowerCase();
      indices[key] = {
        symbol: row.symbol,
        price: parseFloat(row.current_price || 0),
        change: parseFloat(row.change_percent || 0),
        volume: parseInt(row.volume || 0),
        high52Week: parseFloat(row.week_52_high || 0),
        low52Week: parseFloat(row.week_52_low || 0),
        pe: parseFloat(row.pe_ratio || 0),
        dividendYield: parseFloat(row.dividend_yield || 0),
        technicalSignal: this.getTechnicalSignal(row)
      };
    });

    return indices;
  }

  /**
   * Get technical signal
   */
  getTechnicalSignal(stock) {
    const price = parseFloat(stock.current_price || 0);
    const high52 = parseFloat(stock.week_52_high || 0);
    const low52 = parseFloat(stock.week_52_low || 0);
    const change = parseFloat(stock.change_percent || 0);

    if (high52 > 0) {
      const distanceFromHigh = ((high52 - price) / high52) * 100;
      const distanceFromLow = ((price - low52) / low52) * 100;

      if (distanceFromHigh < 5 && change > 1) return 'Strong Buy';
      if (distanceFromHigh < 10 && change > 0) return 'Buy';
      if (distanceFromLow > 50 && change > 0) return 'Buy';
      if (distanceFromHigh > 20 && change < -2) return 'Sell';
      if (change < -5) return 'Strong Sell';
    }

    return 'Hold';
  }

  /**
   * Calculate market sentiment
   */
  calculateMarketSentiment(indices, indicators) {
    let sentimentScore = 0;
    let factors = 0;

    // Index performance factor
    indices.forEach(index => {
      const change = parseFloat(index.change_percent || 0);
      sentimentScore += change > 1 ? 1 : change > 0 ? 0.5 : change > -1 ? -0.5 : -1;
      factors++;
    });

    // VIX factor
    const vixData = indicators.find(i => i.indicator_name === 'VIX');
    if (vixData) {
      const vix = parseFloat(vixData.value);
      sentimentScore += vix < 15 ? 1 : vix < 20 ? 0.5 : vix < 30 ? -0.5 : -1;
      factors++;
    }

    // Fear & Greed factor
    const fearGreedData = indicators.find(i => i.indicator_name === 'FEAR_GREED_INDEX');
    if (fearGreedData) {
      const fearGreed = parseFloat(fearGreedData.value);
      sentimentScore += fearGreed > 70 ? 1 : fearGreed > 50 ? 0.5 : fearGreed > 30 ? -0.5 : -1;
      factors++;
    }

    const avgSentiment = factors > 0 ? sentimentScore / factors : 0;

    return {
      score: avgSentiment,
      level: this.getSentimentLevel(avgSentiment),
      description: this.getSentimentDescription(avgSentiment),
      factors: {
        marketPerformance: indices.length > 0 ? 
          indices.reduce((sum, i) => sum + parseFloat(i.change_percent || 0), 0) / indices.length : 0,
        volatility: vixData ? parseFloat(vixData.value) : null,
        fearGreedIndex: fearGreedData ? parseFloat(fearGreedData.value) : null
      }
    };
  }

  /**
   * Get sentiment level
   */
  getSentimentLevel(score) {
    if (score > 0.5) return 'Very Bullish';
    if (score > 0.2) return 'Bullish';
    if (score > -0.2) return 'Neutral';
    if (score > -0.5) return 'Bearish';
    return 'Very Bearish';
  }

  /**
   * Get sentiment description
   */
  getSentimentDescription(score) {
    if (score > 0.5) return 'Strong positive market momentum with low volatility';
    if (score > 0.2) return 'Positive market conditions with moderate optimism';
    if (score > -0.2) return 'Mixed signals with balanced market conditions';
    if (score > -0.5) return 'Cautious market with elevated uncertainty';
    return 'High market stress with significant volatility';
  }

  /**
   * Get investment opportunities
   */
  async getInvestmentOpportunities(userId) {
    try {
      // Get user's current holdings for exclusion
      const currentHoldings = await query(`
        SELECT symbol FROM portfolio_holdings WHERE user_id = $1 AND quantity > 0
      `, [userId]);

      const ownedSymbols = currentHoldings.rows.map(h => h.symbol);

      // Find undervalued stocks
      const opportunitiesQuery = await query(`
        SELECT 
          symbol, current_price, change_percent, pe_ratio,
          dividend_yield, market_cap, sector, volume,
          week_52_low, week_52_high
        FROM stocks 
        WHERE symbol NOT IN (${ownedSymbols.map((_, i) => `$${i + 1}`).join(',')})
        AND pe_ratio > 0 AND pe_ratio < 20
        AND market_cap > 1000000000
        AND volume > 100000
        AND change_percent > -10
        ORDER BY 
          CASE 
            WHEN dividend_yield > 3 THEN dividend_yield * 2
            ELSE (1 / NULLIF(pe_ratio, 0)) * 100
          END DESC
        LIMIT 10
      `, ownedSymbols);

      const opportunities = opportunitiesQuery.rows.map(stock => ({
        symbol: stock.symbol,
        currentPrice: parseFloat(stock.current_price),
        sector: stock.sector,
        peRatio: parseFloat(stock.pe_ratio || 0),
        dividendYield: parseFloat(stock.dividend_yield || 0),
        marketCap: parseInt(stock.market_cap || 0),
        opportunityType: this.classifyOpportunity(stock),
        reasoning: this.getOpportunityReasoning(stock),
        riskLevel: this.assessOpportunityRisk(stock)
      }));

      return {
        count: opportunities.length,
        opportunities,
        analysisDate: new Date(),
        disclaimer: 'These are potential opportunities based on quantitative screening. Conduct your own research before investing.'
      };

    } catch (error) {
      console.error('❌ Error getting investment opportunities:', error);
      return { error: 'Investment opportunities analysis failed' };
    }
  }

  /**
   * Classify investment opportunity
   */
  classifyOpportunity(stock) {
    const pe = parseFloat(stock.pe_ratio || 0);
    const dividend = parseFloat(stock.dividend_yield || 0);
    const change = parseFloat(stock.change_percent || 0);

    if (dividend > 4) return 'High Dividend';
    if (pe < 10 && pe > 0) return 'Value Play';
    if (change < -5) return 'Dip Opportunity';
    if (pe < 15) return 'Reasonable Valuation';
    return 'Growth Potential';
  }

  /**
   * Get opportunity reasoning
   */
  getOpportunityReasoning(stock) {
    const pe = parseFloat(stock.pe_ratio || 0);
    const dividend = parseFloat(stock.dividend_yield || 0);
    const reasons = [];

    if (pe < 15 && pe > 0) reasons.push(`Low P/E ratio (${pe.toFixed(1)})`);
    if (dividend > 3) reasons.push(`High dividend yield (${dividend.toFixed(1)}%)`);
    if (parseInt(stock.market_cap) > 10000000000) reasons.push('Large-cap stability');

    return reasons.join(', ') || 'Meets screening criteria';
  }

  /**
   * Get fallback context
   */
  getFallbackContext() {
    return {
      portfolio: { error: 'Portfolio data temporarily unavailable' },
      market: { error: 'Market data temporarily unavailable' },
      timestamp: new Date(),
      fallback: true
    };
  }

  /**
   * Clear cache
   */
  clearCache(pattern = null) {
    if (pattern) {
      for (const [key] of this.cache) {
        if (key.includes(pattern)) {
          this.cache.delete(key);
        }
      }
    } else {
      this.cache.clear();
    }
  }
}

// Export singleton instance
module.exports = new AdvancedFinancialContextService();