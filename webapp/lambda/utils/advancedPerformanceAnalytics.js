/**
 * Advanced Performance Analytics Service
 * Institutional-grade performance metrics and analytics for portfolio and trading analysis
 */

const { createRequestLogger } = require('./logger');
const { getTimeout, withTradingTimeout } = require('./timeoutManager');

class AdvancedPerformanceAnalytics {
  constructor(dbClient) {
    this.db = dbClient;
    this.logger = createRequestLogger('performance-analytics');
  }

  /**
   * Calculate comprehensive portfolio performance metrics
   */
  async calculatePortfolioPerformance(userId, startDate, endDate, options = {}) {
    const startTime = Date.now();
    
    try {
      // Get portfolio value history
      const portfolioHistory = await this.getPortfolioHistory(userId, startDate, endDate);
      
      // Calculate base metrics
      const baseMetrics = await this.calculateBaseMetrics(portfolioHistory);
      
      // Calculate risk metrics
      const riskMetrics = await this.calculateRiskMetrics(portfolioHistory);
      
      // Calculate advanced metrics
      const advancedMetrics = await this.calculateAdvancedMetrics(portfolioHistory);
      
      // Calculate benchmark comparisons
      const benchmarkMetrics = await this.calculateBenchmarkMetrics(portfolioHistory, startDate, endDate);
      
      // Calculate attribution analysis
      const attributionAnalysis = await this.calculateAttributionAnalysis(userId, startDate, endDate);
      
      // Calculate sector and style analysis
      const sectorAnalysis = await this.calculateSectorAnalysis(userId, startDate, endDate);
      
      // Calculate factor exposure
      const factorExposure = await this.calculateFactorExposure(userId, startDate, endDate);
      
      const performanceMetrics = {
        period: {
          start: startDate,
          end: endDate,
          daysInPeriod: this.calculateDaysInPeriod(startDate, endDate)
        },
        baseMetrics,
        riskMetrics,
        advancedMetrics,
        benchmarkMetrics,
        attributionAnalysis,
        sectorAnalysis,
        factorExposure,
        metadata: {
          calculationTime: Date.now() - startTime,
          timestamp: new Date().toISOString(),
          dataPoints: portfolioHistory.length
        }
      };
      
      this.logger.info('Portfolio performance metrics calculated', {
        userId: `${userId.substring(0, 8)}...`,
        period: `${startDate} to ${endDate}`,
        calculationTime: Date.now() - startTime,
        dataPoints: portfolioHistory.length
      });
      
      return performanceMetrics;
      
    } catch (error) {
      this.logger.error('Error calculating portfolio performance', {
        userId: `${userId.substring(0, 8)}...`,
        error: error.message,
        stack: error.stack
      });
      throw error;
    }
  }

  /**
   * Get portfolio value history from database
   */
  async getPortfolioHistory(userId, startDate, endDate) {
    const query = `
      SELECT 
        DATE(created_at) as date,
        SUM(market_value) as total_value,
        SUM(unrealized_pl) as unrealized_pl,
        SUM(cost_basis) as cost_basis,
        COUNT(*) as position_count
      FROM portfolio_holdings 
      WHERE user_id = $1 
        AND created_at >= $2 
        AND created_at <= $3
        AND quantity > 0
      GROUP BY DATE(created_at)
      ORDER BY date ASC
    `;
    
    const result = await this.db.query(query, [userId, startDate, endDate]);
    return result.rows;
  }

  /**
   * Calculate base performance metrics
   */
  async calculateBaseMetrics(portfolioHistory) {
    if (portfolioHistory.length < 2) {
      return {
        totalReturn: 0,
        annualizedReturn: 0,
        totalReturnPercent: 0,
        averageDailyReturn: 0,
        compoundAnnualGrowthRate: 0
      };
    }
    
    const startValue = parseFloat(portfolioHistory[0].total_value);
    const endValue = parseFloat(portfolioHistory[portfolioHistory.length - 1].total_value);
    const totalReturn = endValue - startValue;
    const totalReturnPercent = (totalReturn / startValue) * 100;
    
    // Calculate daily returns
    const dailyReturns = [];
    for (let i = 1; i < portfolioHistory.length; i++) {
      const currentValue = parseFloat(portfolioHistory[i].total_value);
      const previousValue = parseFloat(portfolioHistory[i - 1].total_value);
      const dailyReturn = (currentValue - previousValue) / previousValue;
      dailyReturns.push(dailyReturn);
    }
    
    const averageDailyReturn = dailyReturns.reduce((sum, ret) => sum + ret, 0) / dailyReturns.length;
    const annualizedReturn = Math.pow(1 + averageDailyReturn, 252) - 1; // 252 trading days
    
    // Compound Annual Growth Rate (CAGR)
    const days = portfolioHistory.length;
    const years = days / 365.25;
    const compoundAnnualGrowthRate = years > 0 ? Math.pow(endValue / startValue, 1 / years) - 1 : 0;
    
    return {
      totalReturn,
      annualizedReturn: annualizedReturn * 100,
      totalReturnPercent,
      averageDailyReturn: averageDailyReturn * 100,
      compoundAnnualGrowthRate: compoundAnnualGrowthRate * 100,
      startValue,
      endValue,
      dailyReturns
    };
  }

  /**
   * Calculate risk metrics
   */
  async calculateRiskMetrics(portfolioHistory) {
    if (portfolioHistory.length < 2) {
      return {
        volatility: 0,
        downsideVolatility: 0,
        maxDrawdown: 0,
        valueAtRisk: 0,
        expectedShortfall: 0,
        calmarRatio: 0,
        sterlingRatio: 0
      };
    }
    
    // Calculate daily returns
    const dailyReturns = [];
    for (let i = 1; i < portfolioHistory.length; i++) {
      const currentValue = parseFloat(portfolioHistory[i].total_value);
      const previousValue = parseFloat(portfolioHistory[i - 1].total_value);
      const dailyReturn = (currentValue - previousValue) / previousValue;
      dailyReturns.push(dailyReturn);
    }
    
    // Volatility (standard deviation of returns)
    const meanReturn = dailyReturns.reduce((sum, ret) => sum + ret, 0) / dailyReturns.length;
    const variance = dailyReturns.reduce((sum, ret) => sum + Math.pow(ret - meanReturn, 2), 0) / dailyReturns.length;
    const volatility = Math.sqrt(variance) * Math.sqrt(252) * 100; // Annualized volatility
    
    // Downside volatility (only negative returns)
    const negativeReturns = dailyReturns.filter(ret => ret < 0);
    const downsideVariance = negativeReturns.length > 0 ? 
      negativeReturns.reduce((sum, ret) => sum + Math.pow(ret, 2), 0) / negativeReturns.length : 0;
    const downsideVolatility = Math.sqrt(downsideVariance) * Math.sqrt(252) * 100;
    
    // Maximum Drawdown
    const maxDrawdown = this.calculateMaxDrawdown(portfolioHistory);
    
    // Value at Risk (VaR) at 95% confidence level
    const sortedReturns = [...dailyReturns].sort((a, b) => a - b);
    const varIndex = Math.floor(sortedReturns.length * 0.05);
    const valueAtRisk = sortedReturns[varIndex] * 100;
    
    // Expected Shortfall (Conditional VaR)
    const expectedShortfall = sortedReturns.slice(0, varIndex).reduce((sum, ret) => sum + ret, 0) / varIndex * 100;
    
    // Calmar Ratio (CAGR / Max Drawdown)
    const annualizedReturn = Math.pow(1 + meanReturn, 252) - 1;
    const calmarRatio = maxDrawdown !== 0 ? (annualizedReturn * 100) / Math.abs(maxDrawdown) : 0;
    
    // Sterling Ratio (similar to Calmar but uses average drawdown)
    const sterlingRatio = maxDrawdown !== 0 ? (annualizedReturn * 100) / Math.abs(maxDrawdown * 0.1) : 0;
    
    return {
      volatility,
      downsideVolatility,
      maxDrawdown,
      valueAtRisk,
      expectedShortfall,
      calmarRatio,
      sterlingRatio,
      meanReturn: meanReturn * 100,
      variance: variance * 100
    };
  }

  /**
   * Calculate maximum drawdown
   */
  calculateMaxDrawdown(portfolioHistory) {
    let maxDrawdown = 0;
    let peak = -Infinity;
    
    for (const record of portfolioHistory) {
      const value = parseFloat(record.total_value);
      if (value > peak) {
        peak = value;
      }
      
      const drawdown = (peak - value) / peak;
      if (drawdown > maxDrawdown) {
        maxDrawdown = drawdown;
      }
    }
    
    return maxDrawdown * 100;
  }

  /**
   * Calculate advanced metrics
   */
  async calculateAdvancedMetrics(portfolioHistory) {
    if (portfolioHistory.length < 2) {
      return {
        informationRatio: 0,
        treynorRatio: 0,
        jensenAlpha: 0,
        trackingError: 0,
        uptureRatio: 0,
        gainLossRatio: 0,
        winRate: 0
      };
    }
    
    // Calculate daily returns
    const dailyReturns = [];
    for (let i = 1; i < portfolioHistory.length; i++) {
      const currentValue = parseFloat(portfolioHistory[i].total_value);
      const previousValue = parseFloat(portfolioHistory[i - 1].total_value);
      const dailyReturn = (currentValue - previousValue) / previousValue;
      dailyReturns.push(dailyReturn);
    }
    
    const meanReturn = dailyReturns.reduce((sum, ret) => sum + ret, 0) / dailyReturns.length;
    
    // Separate positive and negative returns
    const positiveReturns = dailyReturns.filter(ret => ret > 0);
    const negativeReturns = dailyReturns.filter(ret => ret < 0);
    
    // Win Rate
    const winRate = (positiveReturns.length / dailyReturns.length) * 100;
    
    // Gain/Loss Ratio
    const averageGain = positiveReturns.length > 0 ? 
      positiveReturns.reduce((sum, ret) => sum + ret, 0) / positiveReturns.length : 0;
    const averageLoss = negativeReturns.length > 0 ? 
      Math.abs(negativeReturns.reduce((sum, ret) => sum + ret, 0) / negativeReturns.length) : 0;
    const gainLossRatio = averageLoss !== 0 ? averageGain / averageLoss : 0;
    
    // Upture Ratio (capture of positive market moves)
    const uptureRatio = positiveReturns.length > 0 ? 
      (positiveReturns.reduce((sum, ret) => sum + ret, 0) / positiveReturns.length) * 100 : 0;
    
    // Placeholder values for metrics requiring benchmark data
    const informationRatio = 0; // Requires benchmark comparison
    const treynorRatio = 0; // Requires beta calculation
    const jensenAlpha = 0; // Requires benchmark comparison
    const trackingError = 0; // Requires benchmark comparison
    
    return {
      informationRatio,
      treynorRatio,
      jensenAlpha,
      trackingError,
      uptureRatio,
      gainLossRatio,
      winRate,
      averageGain: averageGain * 100,
      averageLoss: averageLoss * 100,
      positiveReturnsCount: positiveReturns.length,
      negativeReturnsCount: negativeReturns.length
    };
  }

  /**
   * Calculate benchmark comparison metrics
   */
  async calculateBenchmarkMetrics(portfolioHistory, startDate, endDate) {
    try {
      // Fetch SPY (S&P 500) benchmark data from our stock_prices table
      const benchmarkQuery = `
        SELECT 
          DATE(date) as date,
          close as close_price
        FROM stock_prices 
        WHERE symbol = 'SPY' 
          AND date >= $1 
          AND date <= $2
        ORDER BY date
      `;
      
      const benchmarkData = await this.db.query(benchmarkQuery, [startDate, endDate]);
      
      if (benchmarkData.rows.length < 2) {
        this.logger.warn('Insufficient benchmark data for metrics calculation', {
          availableDataPoints: benchmarkData.rows.length,
          startDate,
          endDate
        });
        return {
          benchmarkReturn: 0,
          alpha: 0,
          beta: 0,
          correlation: 0,
          sharpeRatio: 0,
          sortinoRatio: 0,
          informationRatio: 0,
          trackingError: 0,
          upCaptureRatio: 0,
          downCaptureRatio: 0,
          dataQuality: 'insufficient'
        };
      }

      // Calculate benchmark returns
      const benchmarkReturns = [];
      for (let i = 1; i < benchmarkData.rows.length; i++) {
        const currentPrice = parseFloat(benchmarkData.rows[i].close_price);
        const previousPrice = parseFloat(benchmarkData.rows[i - 1].close_price);
        const dailyReturn = (currentPrice - previousPrice) / previousPrice;
        benchmarkReturns.push(dailyReturn);
      }

      // Calculate portfolio returns aligned with benchmark dates
      const portfolioReturns = this.calculateAlignedPortfolioReturns(portfolioHistory, benchmarkData.rows);
      
      if (portfolioReturns.length < 2) {
        return {
          benchmarkReturn: 0,
          alpha: 0,
          beta: 0,
          correlation: 0,
          sharpeRatio: 0,
          sortinoRatio: 0,
          informationRatio: 0,
          trackingError: 0,
          upCaptureRatio: 0,
          downCaptureRatio: 0,
          dataQuality: 'insufficient_portfolio_data'
        };
      }

      // Calculate benchmark metrics
      const benchmarkReturn = benchmarkReturns.reduce((sum, ret) => sum + ret, 0) * 100;
      const { beta, alpha, correlation } = this.calculateBetaAndAlpha(portfolioReturns, benchmarkReturns);
      const trackingError = this.calculateTrackingError(portfolioReturns, benchmarkReturns);
      const { upCaptureRatio, downCaptureRatio } = this.calculateCaptureRatios(portfolioReturns, benchmarkReturns);
      
      // Calculate Sharpe and Sortino ratios (assuming risk-free rate of 0 for simplicity)
      const portfolioMeanReturn = portfolioReturns.reduce((sum, ret) => sum + ret, 0) / portfolioReturns.length;
      const portfolioVolatility = this.calculateVolatility(portfolioReturns);
      const sharpeRatio = portfolioVolatility > 0 ? (portfolioMeanReturn * 252) / (portfolioVolatility * Math.sqrt(252)) : 0;
      
      const negativeReturns = portfolioReturns.filter(ret => ret < 0);
      const downsideDeviation = this.calculateVolatility(negativeReturns);
      const sortinoRatio = downsideDeviation > 0 ? (portfolioMeanReturn * 252) / (downsideDeviation * Math.sqrt(252)) : 0;
      
      const informationRatio = trackingError > 0 ? alpha / trackingError : 0;

      return {
        benchmarkReturn,
        alpha: alpha * 100,
        beta,
        correlation,
        sharpeRatio,
        sortinoRatio,
        informationRatio,
        trackingError: trackingError * 100,
        upCaptureRatio: upCaptureRatio * 100,
        downCaptureRatio: downCaptureRatio * 100,
        dataQuality: 'complete'
      };

    } catch (error) {
      this.logger.error('Error calculating benchmark metrics', {
        error: error.message,
        startDate,
        endDate
      });
      return {
        benchmarkReturn: 0,
        alpha: 0,
        beta: 0,
        correlation: 0,
        sharpeRatio: 0,
        sortinoRatio: 0,
        informationRatio: 0,
        trackingError: 0,
        upCaptureRatio: 0,
        downCaptureRatio: 0,
        dataQuality: 'error',
        error: error.message
      };
    }
  }

  /**
   * Calculate attribution analysis
   */
  async calculateAttributionAnalysis(userId, startDate, endDate) {
    const query = `
      SELECT 
        symbol,
        sector,
        SUM(market_value) as total_value,
        SUM(unrealized_pl) as total_pnl,
        SUM(cost_basis) as total_cost_basis,
        AVG(quantity) as avg_quantity
      FROM portfolio_holdings 
      WHERE user_id = $1 
        AND created_at >= $2 
        AND created_at <= $3
        AND quantity > 0
      GROUP BY symbol, sector
      ORDER BY total_value DESC
    `;
    
    const result = await this.db.query(query, [userId, startDate, endDate]);
    const holdings = result.rows;
    
    const totalPortfolioValue = holdings.reduce((sum, holding) => sum + parseFloat(holding.total_value), 0);
    
    const attributionAnalysis = {
      securityAttribution: holdings.map(holding => ({
        symbol: holding.symbol,
        sector: holding.sector,
        weight: (parseFloat(holding.total_value) / totalPortfolioValue) * 100,
        contribution: (parseFloat(holding.total_pnl) / totalPortfolioValue) * 100,
        totalValue: parseFloat(holding.total_value),
        totalPnL: parseFloat(holding.total_pnl),
        returnContribution: (parseFloat(holding.total_pnl) / parseFloat(holding.total_cost_basis)) * 100
      })).slice(0, 20), // Top 20 contributors
      
      sectorAttribution: this.calculateSectorAttribution(holdings, totalPortfolioValue),
      
      totalPortfolioValue,
      numberOfHoldings: holdings.length
    };
    
    return attributionAnalysis;
  }

  /**
   * Calculate sector attribution
   */
  calculateSectorAttribution(holdings, totalPortfolioValue) {
    const sectorMap = new Map();
    
    holdings.forEach(holding => {
      const sector = holding.sector || 'Unknown';
      const value = parseFloat(holding.total_value);
      const pnl = parseFloat(holding.total_pnl);
      
      if (!sectorMap.has(sector)) {
        sectorMap.set(sector, { value: 0, pnl: 0, count: 0 });
      }
      
      const sectorData = sectorMap.get(sector);
      sectorData.value += value;
      sectorData.pnl += pnl;
      sectorData.count += 1;
    });
    
    return Array.from(sectorMap.entries()).map(([sector, data]) => ({
      sector,
      weight: (data.value / totalPortfolioValue) * 100,
      contribution: (data.pnl / totalPortfolioValue) * 100,
      totalValue: data.value,
      totalPnL: data.pnl,
      holdingCount: data.count
    })).sort((a, b) => b.weight - a.weight);
  }

  /**
   * Calculate sector analysis
   */
  async calculateSectorAnalysis(userId, startDate, endDate) {
    const query = `
      SELECT 
        sector,
        COUNT(*) as holding_count,
        SUM(market_value) as total_value,
        SUM(unrealized_pl) as total_pnl,
        AVG(unrealized_plpc) as avg_return,
        STDDEV(unrealized_plpc) as return_volatility
      FROM portfolio_holdings 
      WHERE user_id = $1 
        AND created_at >= $2 
        AND created_at <= $3
        AND quantity > 0
        AND sector IS NOT NULL
      GROUP BY sector
      ORDER BY total_value DESC
    `;
    
    const result = await this.db.query(query, [userId, startDate, endDate]);
    const sectors = result.rows;
    
    const totalPortfolioValue = sectors.reduce((sum, sector) => sum + parseFloat(sector.total_value), 0);
    
    return {
      sectorBreakdown: sectors.map(sector => ({
        sector: sector.sector,
        allocation: (parseFloat(sector.total_value) / totalPortfolioValue) * 100,
        holdingCount: parseInt(sector.holding_count),
        totalValue: parseFloat(sector.total_value),
        totalPnL: parseFloat(sector.total_pnl),
        averageReturn: parseFloat(sector.avg_return) || 0,
        returnVolatility: parseFloat(sector.return_volatility) || 0,
        contribution: (parseFloat(sector.total_pnl) / totalPortfolioValue) * 100
      })),
      diversificationScore: this.calculateDiversificationScore(sectors, totalPortfolioValue),
      sectorCount: sectors.length,
      totalPortfolioValue
    };
  }

  /**
   * Calculate diversification score
   */
  calculateDiversificationScore(sectors, totalPortfolioValue) {
    // Calculate Herfindahl-Hirschman Index (HHI) for sector concentration
    const hhi = sectors.reduce((sum, sector) => {
      const weight = parseFloat(sector.total_value) / totalPortfolioValue;
      return sum + (weight * weight);
    }, 0);
    
    // Convert to diversification score (0-100, higher is better)
    const diversificationScore = Math.max(0, (1 - hhi) * 100);
    
    return {
      diversificationScore,
      herfindahlIndex: hhi,
      interpretation: this.getDiversificationInterpretation(diversificationScore)
    };
  }

  /**
   * Get diversification interpretation
   */
  getDiversificationInterpretation(score) {
    if (score >= 80) return 'Highly Diversified';
    if (score >= 60) return 'Well Diversified';
    if (score >= 40) return 'Moderately Diversified';
    if (score >= 20) return 'Somewhat Concentrated';
    return 'Highly Concentrated';
  }

  /**
   * Calculate factor exposure
   */
  async calculateFactorExposure(userId, startDate, endDate) {
    // This would typically involve sophisticated factor analysis
    // For now, return a basic implementation
    
    const query = `
      SELECT 
        symbol,
        market_value,
        unrealized_plpc as return_pct,
        sector
      FROM portfolio_holdings 
      WHERE user_id = $1 
        AND created_at >= $2 
        AND created_at <= $3
        AND quantity > 0
        AND market_value > 0
      ORDER BY market_value DESC
    `;
    
    const result = await this.db.query(query, [userId, startDate, endDate]);
    const holdings = result.rows;
    
    if (holdings.length === 0) {
      return {
        factorExposures: {},
        riskFactors: {},
        styleFactors: {}
      };
    }
    
    const totalValue = holdings.reduce((sum, h) => sum + parseFloat(h.market_value), 0);
    
    // Calculate basic factor exposures
    const factorExposures = {
      size: this.calculateSizeFactor(holdings, totalValue),
      value: this.calculateValueFactor(holdings, totalValue),
      momentum: this.calculateMomentumFactor(holdings, totalValue),
      quality: this.calculateQualityFactor(holdings, totalValue)
    };
    
    const riskFactors = {
      concentration: this.calculateConcentrationRisk(holdings, totalValue),
      sectorConcentration: this.calculateSectorConcentrationRisk(holdings, totalValue),
      volatility: this.calculateVolatilityRisk(holdings)
    };
    
    const styleFactors = {
      growthTilt: this.calculateGrowthTilt(holdings, totalValue),
      valueTilt: this.calculateValueTilt(holdings, totalValue),
      qualityTilt: this.calculateQualityTilt(holdings, totalValue)
    };
    
    return {
      factorExposures,
      riskFactors,
      styleFactors,
      totalHoldings: holdings.length,
      totalValue
    };
  }

  /**
   * Calculate size factor (placeholder implementation)
   */
  calculateSizeFactor(holdings, totalValue) {
    // Simple proxy: weight of top 10 holdings (large cap bias)
    const top10Value = holdings.slice(0, 10).reduce((sum, h) => sum + parseFloat(h.market_value), 0);
    return (top10Value / totalValue) * 100;
  }

  /**
   * Calculate value factor using P/E and P/B ratios
   */
  calculateValueFactor(holdings, totalValue) {
    // Calculate weighted average P/E ratio as proxy for value tilt
    // Higher P/E = growth tilt (positive value), Lower P/E = value tilt (negative value)
    let weightedPE = 0;
    let totalWeightWithPE = 0;
    
    holdings.forEach(holding => {
      const weight = parseFloat(holding.market_value) / totalValue;
      // Use a proxy P/E based on return performance (high performers = high P/E)
      const proxyPE = 15 + (parseFloat(holding.return_pct || 0) * 0.5); // Base P/E of 15
      
      if (proxyPE > 0) {
        weightedPE += weight * proxyPE;
        totalWeightWithPE += weight;
      }
    });
    
    if (totalWeightWithPE === 0) return 0;
    
    const avgPE = weightedPE / totalWeightWithPE;
    
    // Convert to factor score: positive = growth, negative = value
    // Market average P/E ~20, so adjust relative to that
    return ((avgPE - 20) / 20) * 100;
  }

  /**
   * Calculate momentum factor (placeholder implementation)
   */
  calculateMomentumFactor(holdings, totalValue) {
    // Simple proxy: weighted average of returns
    const weightedReturn = holdings.reduce((sum, h) => {
      const weight = parseFloat(h.market_value) / totalValue;
      const returnPct = parseFloat(h.return_pct) || 0;
      return sum + (weight * returnPct);
    }, 0);
    return weightedReturn;
  }

  /**
   * Calculate quality factor using fundamental metrics
   */
  calculateQualityFactor(holdings, totalValue) {
    // Quality score based on diversification and position sizing
    const maxPositionWeight = Math.max(...holdings.map(h => parseFloat(h.market_value) / totalValue));
    const concentrationPenalty = Math.max(0, (maxPositionWeight - 0.1) * 100); // Penalty for positions > 10%
    const diversificationBonus = Math.min(25, holdings.length * 2); // Bonus for more holdings
    
    return Math.max(0, 75 + diversificationBonus - concentrationPenalty);
  }

  /**
   * Calculate concentration risk
   */
  calculateConcentrationRisk(holdings, totalValue) {
    const top1Weight = holdings.length > 0 ? (parseFloat(holdings[0].market_value) / totalValue) * 100 : 0;
    const top5Weight = holdings.slice(0, 5).reduce((sum, h) => sum + parseFloat(h.market_value), 0) / totalValue * 100;
    
    return {
      top1Weight,
      top5Weight,
      riskLevel: top1Weight > 20 ? 'High' : top1Weight > 10 ? 'Medium' : 'Low'
    };
  }

  /**
   * Calculate sector concentration risk
   */
  calculateSectorConcentrationRisk(holdings, totalValue) {
    const sectorMap = new Map();
    
    holdings.forEach(holding => {
      const sector = holding.sector || 'Unknown';
      const value = parseFloat(holding.market_value);
      
      if (!sectorMap.has(sector)) {
        sectorMap.set(sector, 0);
      }
      sectorMap.set(sector, sectorMap.get(sector) + value);
    });
    
    const sectorWeights = Array.from(sectorMap.values()).map(value => (value / totalValue) * 100);
    const maxSectorWeight = Math.max(...sectorWeights);
    
    return {
      maxSectorWeight,
      sectorCount: sectorMap.size,
      riskLevel: maxSectorWeight > 40 ? 'High' : maxSectorWeight > 25 ? 'Medium' : 'Low'
    };
  }

  /**
   * Calculate volatility risk
   */
  calculateVolatilityRisk(holdings) {
    const returns = holdings.map(h => parseFloat(h.return_pct) || 0);
    const meanReturn = returns.reduce((sum, ret) => sum + ret, 0) / returns.length;
    const variance = returns.reduce((sum, ret) => sum + Math.pow(ret - meanReturn, 2), 0) / returns.length;
    const volatility = Math.sqrt(variance);
    
    return {
      volatility,
      riskLevel: volatility > 25 ? 'High' : volatility > 15 ? 'Medium' : 'Low'
    };
  }

  /**
   * Calculate growth tilt
   */
  calculateGrowthTilt(holdings, totalValue) {
    // Placeholder: assume growth tilt based on sector distribution
    const techWeight = holdings.filter(h => h.sector === 'Technology').reduce((sum, h) => sum + parseFloat(h.market_value), 0);
    return (techWeight / totalValue) * 100;
  }

  /**
   * Calculate value tilt
   */
  calculateValueTilt(holdings, totalValue) {
    // Placeholder: assume value tilt based on sector distribution
    const valueWeight = holdings.filter(h => ['Finance', 'Energy', 'Utilities'].includes(h.sector)).reduce((sum, h) => sum + parseFloat(h.market_value), 0);
    return (valueWeight / totalValue) * 100;
  }

  /**
   * Calculate quality tilt
   */
  calculateQualityTilt(holdings, totalValue) {
    // Placeholder: assume quality based on diversification
    return Math.min(100, holdings.length * 1.5);
  }

  /**
   * Calculate days in period
   */
  calculateDaysInPeriod(startDate, endDate) {
    const start = new Date(startDate);
    const end = new Date(endDate);
    const timeDiff = end.getTime() - start.getTime();
    return Math.ceil(timeDiff / (1000 * 3600 * 24));
  }

  /**
   * Generate performance report
   */
  async generatePerformanceReport(userId, startDate, endDate, format = 'detailed') {
    const startTime = Date.now();
    
    try {
      const performanceMetrics = await this.calculatePortfolioPerformance(userId, startDate, endDate);
      
      const report = {
        reportId: `perf_${userId}_${Date.now()}`,
        userId,
        period: performanceMetrics.period,
        summary: this.generatePerformanceSummary(performanceMetrics),
        metrics: format === 'detailed' ? performanceMetrics : this.getBasicMetrics(performanceMetrics),
        recommendations: this.generateRecommendations(performanceMetrics),
        generatedAt: new Date().toISOString(),
        generationTime: Date.now() - startTime
      };
      
      this.logger.info('Performance report generated', {
        userId: `${userId.substring(0, 8)}...`,
        reportId: report.reportId,
        generationTime: report.generationTime
      });
      
      return report;
      
    } catch (error) {
      this.logger.error('Error generating performance report', {
        userId: `${userId.substring(0, 8)}...`,
        error: error.message
      });
      throw error;
    }
  }

  /**
   * Generate performance summary
   */
  generatePerformanceSummary(metrics) {
    const { baseMetrics, riskMetrics, sectorAnalysis } = metrics;
    
    return {
      overallPerformance: this.getPerformanceGrade(baseMetrics.totalReturnPercent),
      keyHighlights: [
        `Total Return: ${baseMetrics.totalReturnPercent.toFixed(2)}%`,
        `Annualized Return: ${baseMetrics.annualizedReturn.toFixed(2)}%`,
        `Volatility: ${riskMetrics.volatility.toFixed(2)}%`,
        `Max Drawdown: ${riskMetrics.maxDrawdown.toFixed(2)}%`,
        `Diversification: ${sectorAnalysis.diversificationScore.diversificationScore.toFixed(0)}/100`
      ],
      riskProfile: this.assessRiskProfile(riskMetrics),
      recommendation: this.getOverallRecommendation(metrics)
    };
  }

  /**
   * Get performance grade
   */
  getPerformanceGrade(returnPercent) {
    if (returnPercent >= 20) return 'A+';
    if (returnPercent >= 15) return 'A';
    if (returnPercent >= 10) return 'B+';
    if (returnPercent >= 5) return 'B';
    if (returnPercent >= 0) return 'C';
    if (returnPercent >= -5) return 'D';
    return 'F';
  }

  /**
   * Assess risk profile
   */
  assessRiskProfile(riskMetrics) {
    const { volatility, maxDrawdown } = riskMetrics;
    
    if (volatility > 25 || maxDrawdown > 20) return 'High Risk';
    if (volatility > 15 || maxDrawdown > 10) return 'Medium Risk';
    return 'Low Risk';
  }

  /**
   * Get overall recommendation
   */
  getOverallRecommendation(metrics) {
    const { baseMetrics, riskMetrics, sectorAnalysis } = metrics;
    
    if (baseMetrics.totalReturnPercent > 10 && riskMetrics.volatility < 20) {
      return 'Excellent performance with controlled risk. Continue current strategy.';
    } else if (baseMetrics.totalReturnPercent > 0 && riskMetrics.maxDrawdown < 15) {
      return 'Solid performance. Consider optimizing for better risk-adjusted returns.';
    } else if (riskMetrics.volatility > 25) {
      return 'High volatility detected. Consider diversification to reduce risk.';
    } else {
      return 'Performance needs improvement. Review strategy and consider rebalancing.';
    }
  }

  /**
   * Get basic metrics for simplified reports
   */
  getBasicMetrics(performanceMetrics) {
    return {
      totalReturn: performanceMetrics.baseMetrics.totalReturnPercent,
      annualizedReturn: performanceMetrics.baseMetrics.annualizedReturn,
      volatility: performanceMetrics.riskMetrics.volatility,
      maxDrawdown: performanceMetrics.riskMetrics.maxDrawdown,
      sharpeRatio: performanceMetrics.benchmarkMetrics.sharpeRatio,
      sectorCount: performanceMetrics.sectorAnalysis.sectorCount
    };
  }

  /**
   * Generate recommendations
   */
  generateRecommendations(metrics) {
    const recommendations = [];
    
    // Risk-based recommendations
    if (metrics.riskMetrics.volatility > 25) {
      recommendations.push({
        type: 'risk_management',
        priority: 'high',
        title: 'High Volatility Alert',
        description: 'Portfolio volatility is above 25%. Consider diversification or position sizing adjustments.',
        action: 'Reduce concentration in high-volatility positions'
      });
    }
    
    // Concentration recommendations
    if (metrics.factorExposures.riskFactors.concentration.top1Weight > 20) {
      recommendations.push({
        type: 'diversification',
        priority: 'medium',
        title: 'Position Concentration',
        description: 'Largest position exceeds 20% of portfolio. Consider reducing concentration.',
        action: 'Trim largest position or add diversifying holdings'
      });
    }
    
    // Performance recommendations
    if (metrics.baseMetrics.totalReturnPercent < 0) {
      recommendations.push({
        type: 'performance',
        priority: 'high',
        title: 'Negative Returns',
        description: 'Portfolio has negative returns. Review strategy and consider rebalancing.',
        action: 'Conduct thorough portfolio review and strategy reassessment'
      });
    }
    
    return recommendations;
  }
  /**
   * Calculate aligned portfolio returns for benchmark comparison
   */
  calculateAlignedPortfolioReturns(portfolioHistory, benchmarkDates) {
    const portfolioReturns = [];
    
    for (let i = 1; i < benchmarkDates.length; i++) {
      const benchmarkDate = benchmarkDates[i].date;
      const prevBenchmarkDate = benchmarkDates[i - 1].date;
      
      // Find portfolio values for these dates
      const currentPortfolio = portfolioHistory.find(p => p.date === benchmarkDate);
      const previousPortfolio = portfolioHistory.find(p => p.date === prevBenchmarkDate);
      
      if (currentPortfolio && previousPortfolio) {
        const currentValue = parseFloat(currentPortfolio.total_value);
        const previousValue = parseFloat(previousPortfolio.total_value);
        if (previousValue > 0) {
          const portfolioReturn = (currentValue - previousValue) / previousValue;
          portfolioReturns.push(portfolioReturn);
        }
      }
    }
    
    return portfolioReturns;
  }

  /**
   * Calculate beta, alpha, and correlation with benchmark
   */
  calculateBetaAndAlpha(portfolioReturns, benchmarkReturns) {
    if (portfolioReturns.length !== benchmarkReturns.length || portfolioReturns.length < 2) {
      return { beta: 0, alpha: 0, correlation: 0 };
    }

    const portfolioMean = portfolioReturns.reduce((sum, ret) => sum + ret, 0) / portfolioReturns.length;
    const benchmarkMean = benchmarkReturns.reduce((sum, ret) => sum + ret, 0) / benchmarkReturns.length;
    
    let covariance = 0;
    let portfolioVariance = 0;
    let benchmarkVariance = 0;
    
    for (let i = 0; i < portfolioReturns.length; i++) {
      const portfolioDiff = portfolioReturns[i] - portfolioMean;
      const benchmarkDiff = benchmarkReturns[i] - benchmarkMean;
      
      covariance += portfolioDiff * benchmarkDiff;
      portfolioVariance += portfolioDiff * portfolioDiff;
      benchmarkVariance += benchmarkDiff * benchmarkDiff;
    }
    
    covariance /= portfolioReturns.length;
    portfolioVariance /= portfolioReturns.length;
    benchmarkVariance /= benchmarkReturns.length;
    
    const beta = benchmarkVariance > 0 ? covariance / benchmarkVariance : 0;
    const correlation = (portfolioVariance > 0 && benchmarkVariance > 0) ? 
      covariance / (Math.sqrt(portfolioVariance) * Math.sqrt(benchmarkVariance)) : 0;
    const alpha = portfolioMean - (beta * benchmarkMean);
    
    return { beta, alpha, correlation };
  }

  /**
   * Calculate tracking error
   */
  calculateTrackingError(portfolioReturns, benchmarkReturns) {
    if (portfolioReturns.length !== benchmarkReturns.length || portfolioReturns.length < 2) {
      return 0;
    }

    const trackingDifferences = portfolioReturns.map((pRet, i) => pRet - benchmarkReturns[i]);
    const meanDifference = trackingDifferences.reduce((sum, diff) => sum + diff, 0) / trackingDifferences.length;
    const variance = trackingDifferences.reduce((sum, diff) => sum + Math.pow(diff - meanDifference, 2), 0) / trackingDifferences.length;
    
    return Math.sqrt(variance);
  }

  /**
   * Calculate up and down capture ratios
   */
  calculateCaptureRatios(portfolioReturns, benchmarkReturns) {
    if (portfolioReturns.length !== benchmarkReturns.length || portfolioReturns.length < 2) {
      return { upCaptureRatio: 0, downCaptureRatio: 0 };
    }

    const upPeriods = [];
    const downPeriods = [];
    
    for (let i = 0; i < benchmarkReturns.length; i++) {
      if (benchmarkReturns[i] > 0) {
        upPeriods.push({ portfolio: portfolioReturns[i], benchmark: benchmarkReturns[i] });
      } else if (benchmarkReturns[i] < 0) {
        downPeriods.push({ portfolio: portfolioReturns[i], benchmark: benchmarkReturns[i] });
      }
    }
    
    const upCaptureRatio = upPeriods.length > 0 ?
      (upPeriods.reduce((sum, p) => sum + p.portfolio, 0) / upPeriods.length) /
      (upPeriods.reduce((sum, p) => sum + p.benchmark, 0) / upPeriods.length) : 0;
      
    const downCaptureRatio = downPeriods.length > 0 ?
      (downPeriods.reduce((sum, p) => sum + p.portfolio, 0) / downPeriods.length) /
      (downPeriods.reduce((sum, p) => sum + p.benchmark, 0) / downPeriods.length) : 0;
    
    return { upCaptureRatio, downCaptureRatio };
  }

  /**
   * Calculate volatility (standard deviation)
   */
  calculateVolatility(returns) {
    if (returns.length < 2) return 0;
    
    const mean = returns.reduce((sum, ret) => sum + ret, 0) / returns.length;
    const variance = returns.reduce((sum, ret) => sum + Math.pow(ret - mean, 2), 0) / returns.length;
    
    return Math.sqrt(variance);
  }
}

module.exports = { AdvancedPerformanceAnalytics };