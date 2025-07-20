// Portfolio Optimization Service
// Implements automated rebalancing, tax optimization, and advanced analytics

class PortfolioOptimizationService {
  constructor() {
    this.rebalancingStrategies = {
      'THRESHOLD': this.thresholdRebalancing.bind(this),
      'TIME_BASED': this.timeBasedRebalancing.bind(this),
      'RISK_PARITY': this.riskParityRebalancing.bind(this)
      // Note: VOLATILITY_BASED, MOMENTUM, and MEAN_REVERSION strategies not implemented yet
    };
  }

  // Main portfolio optimization method
  async optimizePortfolio(portfolio, marketData, options = {}) {
    const {
      strategy = 'THRESHOLD',
      targetAllocations = {},
      rebalanceThreshold = 0.05, // 5%
      maxTurnover = 0.25, // 25%
      minTradeSize = 100,
      taxOptimization = true,
      riskTolerance = 'MODERATE'
    } = options;

    // Validate inputs
    if (!portfolio || !portfolio.holdings) {
      throw new Error('Invalid portfolio data');
    }

    if (!marketData || Object.keys(marketData).length === 0) {
      throw new Error('Market data required for optimization');
    }

    // Calculate current portfolio metrics
    const currentMetrics = this.calculatePortfolioMetrics(portfolio, marketData);
    
    // Generate rebalancing recommendations
    const rebalanceRecommendations = await this.generateRebalancingRecommendations(
      portfolio, 
      marketData, 
      targetAllocations, 
      strategy,
      options
    );

    // Apply tax optimization if enabled
    let optimizedRecommendations = rebalanceRecommendations;
    if (taxOptimization) {
      optimizedRecommendations = this.applyTaxOptimization(
        rebalanceRecommendations,
        portfolio,
        marketData
      );
    }

    // Risk analysis
    const riskAnalysis = this.analyzePortfolioRisk(portfolio, marketData, riskTolerance);

    // Performance attribution
    const performanceAttribution = this.calculatePerformanceAttribution(
      portfolio,
      marketData
    );

    return {
      currentMetrics,
      rebalanceRecommendations: optimizedRecommendations,
      riskAnalysis,
      performanceAttribution,
      optimization: {
        strategy,
        taxOptimized: taxOptimization,
        estimatedTaxImpact: this.estimateTaxImpact(optimizedRecommendations, portfolio),
        turnover: this.calculateTurnover(optimizedRecommendations, portfolio),
        implementationCost: this.estimateImplementationCost(optimizedRecommendations)
      },
      timestamp: new Date().toISOString()
    };
  }

  // Calculate comprehensive portfolio metrics
  calculatePortfolioMetrics(portfolio, marketData) {
    const holdings = portfolio.holdings || [];
    let totalValue = 0;
    const positions = [];

    // Calculate individual position metrics
    holdings.forEach(holding => {
      const symbol = holding.symbol;
      const shares = holding.shares || 0;
      const currentPrice = marketData[symbol]?.price || holding.averagePrice || 0;
      const positionValue = shares * currentPrice;
      
      totalValue += positionValue;
      
      positions.push({
        symbol,
        shares,
        currentPrice,
        positionValue,
        averagePrice: holding.averagePrice || 0,
        unrealizedPnL: shares * (currentPrice - (holding.averagePrice || 0)),
        unrealizedPnLPercent: holding.averagePrice ? 
          ((currentPrice - holding.averagePrice) / holding.averagePrice) * 100 : 0,
        sector: marketData[symbol]?.sector || 'Unknown',
        marketCap: marketData[symbol]?.marketCap || 0
      });
    });

    // Calculate allocations
    const allocations = positions.map(pos => ({
      ...pos,
      allocation: totalValue > 0 ? (pos.positionValue / totalValue) * 100 : 0
    }));

    // Sector allocation
    const sectorAllocations = this.calculateSectorAllocations(allocations);

    // Risk metrics
    const riskMetrics = this.calculateRiskMetrics(positions, marketData);

    // Diversification metrics
    const diversificationMetrics = this.calculateDiversificationMetrics(allocations);

    return {
      totalValue,
      positionCount: positions.length,
      positions: allocations,
      sectorAllocations,
      riskMetrics,
      diversificationMetrics,
      cashPosition: portfolio.cash || 0,
      totalPortfolioValue: totalValue + (portfolio.cash || 0)
    };
  }

  // Threshold-based rebalancing
  async thresholdRebalancing(portfolio, marketData, targetAllocations, options) {
    const { rebalanceThreshold = 0.05 } = options;
    const currentMetrics = this.calculatePortfolioMetrics(portfolio, marketData);
    const recommendations = [];

    Object.entries(targetAllocations).forEach(([symbol, targetPercent]) => {
      const currentPosition = currentMetrics.positions.find(p => p.symbol === symbol);
      const currentPercent = currentPosition ? currentPosition.allocation : 0;
      const deviation = Math.abs(currentPercent - targetPercent);

      if (deviation > rebalanceThreshold * 100) {
        const targetValue = (targetPercent / 100) * currentMetrics.totalPortfolioValue;
        const currentValue = currentPosition ? currentPosition.positionValue : 0;
        const adjustmentNeeded = targetValue - currentValue;
        const currentPrice = marketData[symbol]?.price || 0;

        if (currentPrice > 0) {
          const sharesAdjustment = Math.round(adjustmentNeeded / currentPrice);
          
          recommendations.push({
            symbol,
            action: sharesAdjustment > 0 ? 'BUY' : 'SELL',
            shares: Math.abs(sharesAdjustment),
            currentPrice,
            estimatedCost: Math.abs(adjustmentNeeded),
            reason: `Rebalance: ${currentPercent.toFixed(1)}% → ${targetPercent.toFixed(1)}%`,
            priority: deviation > rebalanceThreshold * 200 ? 'HIGH' : 'MEDIUM',
            deviation: deviation
          });
        }
      }
    });

    return recommendations.sort((a, b) => b.deviation - a.deviation);
  }

  // Time-based rebalancing
  async timeBasedRebalancing(portfolio, marketData, targetAllocations, options) {
    const { rebalanceFrequency = 'QUARTERLY' } = options;
    const lastRebalanceDate = portfolio.lastRebalanceDate || 0;
    const now = Date.now();
    
    const intervals = {
      'MONTHLY': 30 * 24 * 60 * 60 * 1000,
      'QUARTERLY': 90 * 24 * 60 * 60 * 1000,
      'SEMI_ANNUALLY': 180 * 24 * 60 * 60 * 1000,
      'ANNUALLY': 365 * 24 * 60 * 60 * 1000
    };

    const interval = intervals[rebalanceFrequency] || intervals.QUARTERLY;
    
    if (now - lastRebalanceDate >= interval) {
      // Force rebalance regardless of threshold
      return this.thresholdRebalancing(portfolio, marketData, targetAllocations, {
        ...options,
        rebalanceThreshold: 0 // Force all positions to rebalance
      });
    }

    return [];
  }

  // Risk parity rebalancing
  async riskParityRebalancing(portfolio, marketData, targetAllocations, options) {
    const positions = portfolio.holdings || [];
    const recommendations = [];

    // Calculate risk contribution for each position
    const riskContributions = positions.map(holding => {
      const symbol = holding.symbol;
      const volatility = this.calculateVolatility(symbol, marketData);
      const positionValue = holding.shares * (marketData[symbol]?.price || 0);
      
      return {
        symbol,
        volatility,
        positionValue,
        riskContribution: positionValue * volatility
      };
    });

    const totalRisk = riskContributions.reduce((sum, rc) => sum + rc.riskContribution, 0);
    const targetRiskPerPosition = totalRisk / riskContributions.length;

    riskContributions.forEach(rc => {
      const currentRiskPercent = totalRisk > 0 ? (rc.riskContribution / totalRisk) * 100 : 0;
      const targetRiskPercent = (targetRiskPerPosition / totalRisk) * 100;
      const deviation = Math.abs(currentRiskPercent - targetRiskPercent);

      if (deviation > 5) { // 5% risk allocation deviation
        const adjustmentFactor = targetRiskPercent / currentRiskPercent;
        const currentShares = positions.find(p => p.symbol === rc.symbol)?.shares || 0;
        const targetShares = Math.round(currentShares * adjustmentFactor);
        const sharesAdjustment = targetShares - currentShares;

        if (Math.abs(sharesAdjustment) > 0) {
          recommendations.push({
            symbol: rc.symbol,
            action: sharesAdjustment > 0 ? 'BUY' : 'SELL',
            shares: Math.abs(sharesAdjustment),
            currentPrice: marketData[rc.symbol]?.price || 0,
            estimatedCost: Math.abs(sharesAdjustment) * (marketData[rc.symbol]?.price || 0),
            reason: `Risk parity: ${currentRiskPercent.toFixed(1)}% → ${targetRiskPercent.toFixed(1)}% risk`,
            priority: 'MEDIUM',
            riskAdjustment: true
          });
        }
      }
    });

    return recommendations;
  }

  // Tax-loss harvesting
  applyTaxOptimization(recommendations, portfolio, marketData) {
    const optimizedRecommendations = [...recommendations];
    const holdings = portfolio.holdings || [];

    // Identify positions with unrealized losses
    const lossPositions = holdings.filter(holding => {
      const currentPrice = marketData[holding.symbol]?.price || 0;
      const unrealizedPnL = holding.shares * (currentPrice - (holding.averagePrice || 0));
      return unrealizedPnL < 0;
    });

    // Add tax-loss harvesting opportunities
    lossPositions.forEach(position => {
      const currentPrice = marketData[position.symbol]?.price || 0;
      const unrealizedLoss = position.shares * (currentPrice - (position.averagePrice || 0));
      
      // Only harvest if loss is significant
      if (unrealizedLoss < -500) { // $500 minimum loss
        const existingRecommendation = optimizedRecommendations.find(r => r.symbol === position.symbol);
        
        if (!existingRecommendation) {
          optimizedRecommendations.push({
            symbol: position.symbol,
            action: 'SELL',
            shares: position.shares,
            currentPrice,
            estimatedCost: position.shares * currentPrice,
            reason: `Tax-loss harvesting: Realize $${Math.abs(unrealizedLoss).toFixed(2)} loss`,
            priority: 'LOW',
            taxOptimization: true,
            estimatedTaxSavings: Math.abs(unrealizedLoss) * 0.25 // Assume 25% tax rate
          });
        }
      }
    });

    // Optimize order of execution for tax efficiency
    return this.optimizeExecutionOrder(optimizedRecommendations, portfolio);
  }

  // Optimize execution order for tax efficiency
  optimizeExecutionOrder(recommendations, portfolio) {
    // Sort recommendations to minimize tax impact
    return recommendations.sort((a, b) => {
      // Prioritize tax-loss harvesting
      if (a.taxOptimization && !b.taxOptimization) return -1;
      if (!a.taxOptimization && b.taxOptimization) return 1;
      
      // Then by priority
      const priorityOrder = { 'HIGH': 3, 'MEDIUM': 2, 'LOW': 1 };
      return (priorityOrder[b.priority] || 0) - (priorityOrder[a.priority] || 0);
    });
  }

  // Calculate portfolio risk metrics
  calculateRiskMetrics(positions, marketData) {
    if (positions.length === 0) {
      return {
        beta: 1.0,
        volatility: 0,
        sharpeRatio: 0,
        var95: 0,
        maxDrawdown: 0
      };
    }

    // Calculate weighted average beta
    let totalValue = positions.reduce((sum, pos) => sum + pos.positionValue, 0);
    let weightedBeta = 0;
    let weightedVolatility = 0;

    positions.forEach(position => {
      const weight = position.positionValue / totalValue;
      const beta = marketData[position.symbol]?.beta || 1.0;
      const volatility = this.calculateVolatility(position.symbol, marketData);
      
      weightedBeta += weight * beta;
      weightedVolatility += weight * volatility;
    });

    // Calculate Value at Risk (simplified)
    const var95 = totalValue * 0.05 * weightedVolatility; // 5% probability of loss

    return {
      beta: weightedBeta,
      volatility: weightedVolatility,
      sharpeRatio: this.calculateSharpeRatio(positions, marketData),
      var95,
      maxDrawdown: this.calculateMaxDrawdown(positions, marketData),
      concentration: this.calculateConcentrationRisk(positions)
    };
  }

  // Calculate Sharpe ratio
  calculateSharpeRatio(positions, marketData) {
    // Simplified calculation - would need historical returns for accurate calculation
    const totalValue = positions.reduce((sum, pos) => sum + pos.positionValue, 0);
    const totalReturn = positions.reduce((sum, pos) => sum + pos.unrealizedPnL, 0);
    const returnPercent = totalValue > 0 ? (totalReturn / totalValue) * 100 : 0;
    const riskFreeRate = 2.5; // Assume 2.5% risk-free rate
    const volatility = this.calculateRiskMetrics(positions, marketData).volatility;
    
    return volatility > 0 ? (returnPercent - riskFreeRate) / volatility : 0;
  }

  // Calculate volatility for a symbol
  calculateVolatility(symbol, marketData) {
    // Simplified volatility calculation
    // In production, this would use historical price data
    return marketData[symbol]?.volatility || 0.2; // Default 20% volatility
  }

  // Calculate sector allocations
  calculateSectorAllocations(positions) {
    const sectorMap = new Map();
    
    positions.forEach(position => {
      const sector = position.sector || 'Unknown';
      const currentAllocation = sectorMap.get(sector) || 0;
      sectorMap.set(sector, currentAllocation + position.allocation);
    });

    return Array.from(sectorMap.entries()).map(([sector, allocation]) => ({
      sector,
      allocation: allocation,
      count: positions.filter(p => p.sector === sector).length
    })).sort((a, b) => b.allocation - a.allocation);
  }

  // Calculate diversification metrics
  calculateDiversificationMetrics(positions) {
    if (positions.length === 0) {
      return {
        herfindahlIndex: 1,
        effectivePositions: 0,
        concentrationRatio: 100,
        diversificationScore: 0
      };
    }

    // Herfindahl-Hirschman Index
    const herfindahlIndex = positions.reduce((sum, pos) => {
      const weight = pos.allocation / 100;
      return sum + (weight * weight);
    }, 0);

    // Effective number of positions
    const effectivePositions = 1 / herfindahlIndex;

    // Concentration ratio (top 5 positions)
    const sortedPositions = [...positions].sort((a, b) => b.allocation - a.allocation);
    const top5Allocation = sortedPositions.slice(0, 5).reduce((sum, pos) => sum + pos.allocation, 0);

    // Diversification score (0-100, higher is better)
    const diversificationScore = Math.max(0, 100 - (herfindahlIndex * 100));

    return {
      herfindahlIndex,
      effectivePositions,
      concentrationRatio: top5Allocation,
      diversificationScore,
      positionCount: positions.length
    };
  }

  // Calculate concentration risk
  calculateConcentrationRisk(positions) {
    if (positions.length === 0) return 100;
    
    const maxAllocation = Math.max(...positions.map(p => p.allocation));
    return maxAllocation;
  }

  // Calculate maximum drawdown
  calculateMaxDrawdown(positions, marketData) {
    // Simplified calculation
    // In production, this would use historical portfolio values
    const totalUnrealizedPnL = positions.reduce((sum, pos) => sum + pos.unrealizedPnL, 0);
    const totalValue = positions.reduce((sum, pos) => sum + pos.positionValue, 0);
    
    return totalValue > 0 ? Math.min(0, (totalUnrealizedPnL / totalValue) * 100) : 0;
  }

  // Performance attribution analysis
  calculatePerformanceAttribution(portfolio, marketData) {
    const holdings = portfolio.holdings || [];
    const attributions = [];

    holdings.forEach(holding => {
      const currentPrice = marketData[holding.symbol]?.price || 0;
      const unrealizedPnL = holding.shares * (currentPrice - (holding.averagePrice || 0));
      const marketReturn = marketData[holding.symbol]?.marketReturn || 0;
      const sectorReturn = marketData[holding.symbol]?.sectorReturn || 0;
      
      // Attribution breakdown
      const marketContribution = holding.shares * holding.averagePrice * (marketReturn / 100);
      const sectorContribution = holding.shares * holding.averagePrice * ((sectorReturn - marketReturn) / 100);
      const stockSpecific = unrealizedPnL - marketContribution - sectorContribution;

      attributions.push({
        symbol: holding.symbol,
        totalReturn: unrealizedPnL,
        marketContribution,
        sectorContribution,
        stockSpecific,
        allocation: (holding.shares * currentPrice) / portfolio.totalValue * 100
      });
    });

    const totals = attributions.reduce((acc, attr) => ({
      totalReturn: acc.totalReturn + attr.totalReturn,
      marketContribution: acc.marketContribution + attr.marketContribution,
      sectorContribution: acc.sectorContribution + attr.sectorContribution,
      stockSpecific: acc.stockSpecific + attr.stockSpecific
    }), { totalReturn: 0, marketContribution: 0, sectorContribution: 0, stockSpecific: 0 });

    return {
      byPosition: attributions,
      totals,
      summary: {
        marketEffect: totals.marketContribution,
        sectorEffect: totals.sectorContribution,
        selectionEffect: totals.stockSpecific,
        totalEffect: totals.totalReturn
      }
    };
  }

  // Estimate tax impact
  estimateTaxImpact(recommendations, portfolio) {
    const shortTermTaxRate = 0.37; // 37% for short-term gains
    const longTermTaxRate = 0.20;  // 20% for long-term gains
    let estimatedTaxLiability = 0;

    recommendations.forEach(rec => {
      if (rec.action === 'SELL') {
        const holding = portfolio.holdings?.find(h => h.symbol === rec.symbol);
        if (holding) {
          const costBasis = holding.averagePrice * rec.shares;
          const proceeds = rec.currentPrice * rec.shares;
          const gain = proceeds - costBasis;
          
          if (gain > 0) {
            // Assume long-term for simplicity
            estimatedTaxLiability += gain * longTermTaxRate;
          }
        }
      }
    });

    return {
      estimatedTaxLiability,
      shortTermRate: shortTermTaxRate * 100,
      longTermRate: longTermTaxRate * 100,
      taxOptimizationSavings: recommendations
        .filter(r => r.taxOptimization)
        .reduce((sum, r) => sum + (r.estimatedTaxSavings || 0), 0)
    };
  }

  // Calculate turnover
  calculateTurnover(recommendations, portfolio) {
    const totalPortfolioValue = portfolio.totalValue || 0;
    const totalTradeValue = recommendations.reduce((sum, rec) => {
      return sum + (rec.shares * rec.currentPrice);
    }, 0);

    return totalPortfolioValue > 0 ? (totalTradeValue / totalPortfolioValue) * 100 : 0;
  }

  // Estimate implementation cost
  estimateImplementationCost(recommendations) {
    const commissionPerTrade = 0; // Assume commission-free trading
    const spreadCost = 0.001; // 0.1% spread cost
    
    let totalCost = recommendations.length * commissionPerTrade;
    
    recommendations.forEach(rec => {
      const tradeValue = rec.shares * rec.currentPrice;
      totalCost += tradeValue * spreadCost;
    });

    return {
      commissionCost: recommendations.length * commissionPerTrade,
      spreadCost: totalCost - (recommendations.length * commissionPerTrade),
      totalCost
    };
  }

  // Analyze portfolio risk
  analyzePortfolioRisk(portfolio, marketData, riskTolerance) {
    const metrics = this.calculatePortfolioMetrics(portfolio, marketData);
    const riskLevels = {
      'CONSERVATIVE': { maxVolatility: 0.1, maxConcentration: 10, maxBeta: 0.8 },
      'MODERATE': { maxVolatility: 0.15, maxConcentration: 15, maxBeta: 1.0 },
      'AGGRESSIVE': { maxVolatility: 0.25, maxConcentration: 25, maxBeta: 1.3 }
    };

    const targetRisk = riskLevels[riskTolerance] || riskLevels.MODERATE;
    const currentRisk = metrics.riskMetrics;
    
    const riskAlerts = [];
    
    if (currentRisk.volatility > targetRisk.maxVolatility) {
      riskAlerts.push({
        type: 'HIGH_VOLATILITY',
        severity: 'HIGH',
        message: `Portfolio volatility (${(currentRisk.volatility * 100).toFixed(1)}%) exceeds target (${(targetRisk.maxVolatility * 100).toFixed(1)}%)`,
        recommendation: 'Consider reducing exposure to volatile assets'
      });
    }

    if (currentRisk.concentration > targetRisk.maxConcentration) {
      riskAlerts.push({
        type: 'HIGH_CONCENTRATION',
        severity: 'MEDIUM',
        message: `Highest position concentration (${currentRisk.concentration.toFixed(1)}%) exceeds target (${targetRisk.maxConcentration}%)`,
        recommendation: 'Consider diversifying concentrated positions'
      });
    }

    if (Math.abs(currentRisk.beta) > targetRisk.maxBeta) {
      riskAlerts.push({
        type: 'HIGH_BETA',
        severity: 'MEDIUM',
        message: `Portfolio beta (${currentRisk.beta.toFixed(2)}) exceeds target (${targetRisk.maxBeta})`,
        recommendation: 'Consider adding defensive positions to reduce market sensitivity'
      });
    }

    return {
      riskTolerance,
      targetRisk,
      currentRisk,
      riskAlerts,
      riskScore: this.calculateRiskScore(currentRisk, targetRisk),
      recommendations: this.generateRiskRecommendations(riskAlerts)
    };
  }

  // Calculate overall risk score
  calculateRiskScore(currentRisk, targetRisk) {
    const volatilityScore = Math.min(1, currentRisk.volatility / targetRisk.maxVolatility);
    const concentrationScore = Math.min(1, currentRisk.concentration / targetRisk.maxConcentration);
    const betaScore = Math.min(1, Math.abs(currentRisk.beta) / targetRisk.maxBeta);
    
    const overallScore = (volatilityScore + concentrationScore + betaScore) / 3;
    
    return {
      overall: Math.round(overallScore * 100),
      volatility: Math.round(volatilityScore * 100),
      concentration: Math.round(concentrationScore * 100),
      beta: Math.round(betaScore * 100),
      rating: overallScore < 0.7 ? 'LOW' : overallScore < 1.0 ? 'MODERATE' : 'HIGH'
    };
  }

  // Generate risk-based recommendations
  generateRiskRecommendations(riskAlerts) {
    const recommendations = [];
    
    riskAlerts.forEach(alert => {
      switch (alert.type) {
        case 'HIGH_VOLATILITY':
          recommendations.push({
            action: 'DIVERSIFY',
            description: 'Add low-volatility assets (bonds, utilities, REITs)',
            priority: 'HIGH'
          });
          break;
        case 'HIGH_CONCENTRATION':
          recommendations.push({
            action: 'REBALANCE',
            description: 'Reduce position sizes in concentrated holdings',
            priority: 'MEDIUM'
          });
          break;
        case 'HIGH_BETA':
          recommendations.push({
            action: 'HEDGE',
            description: 'Add defensive positions or consider market hedging',
            priority: 'MEDIUM'
          });
          break;
      }
    });

    return recommendations;
  }

  // Get available rebalancing strategies
  getAvailableStrategies() {
    return Object.keys(this.rebalancingStrategies).map(key => ({
      id: key,
      name: key.replace(/_/g, ' ').toLowerCase().replace(/\b\w/g, l => l.toUpperCase()),
      description: this.getStrategyDescription(key)
    }));
  }

  getStrategyDescription(strategy) {
    const descriptions = {
      'THRESHOLD': 'Rebalances when allocations deviate beyond specified threshold',
      'TIME_BASED': 'Rebalances at regular time intervals regardless of drift',
      'VOLATILITY_BASED': 'Adjusts allocations based on changing market volatility',
      'RISK_PARITY': 'Maintains equal risk contribution from all positions',
      'MOMENTUM': 'Increases allocation to outperforming assets',
      'MEAN_REVERSION': 'Increases allocation to underperforming assets'
    };
    return descriptions[strategy] || 'Custom rebalancing strategy';
  }
}

module.exports = PortfolioOptimizationService;