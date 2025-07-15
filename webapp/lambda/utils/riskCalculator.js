const { query } = require('./database');

class RiskCalculator {
  constructor() {
    this.riskFactors = {
      // Market risk factors
      MARKET_RISK: { weight: 0.3, category: 'market' },
      SECTOR_CONCENTRATION: { weight: 0.2, category: 'concentration' },
      GEOGRAPHIC_CONCENTRATION: { weight: 0.1, category: 'concentration' },
      
      // Company-specific risk factors
      FINANCIAL_LEVERAGE: { weight: 0.15, category: 'financial' },
      LIQUIDITY_RISK: { weight: 0.1, category: 'financial' },
      PROFITABILITY_RISK: { weight: 0.15, category: 'financial' },
      
      // Technical risk factors
      VOLATILITY_RISK: { weight: 0.2, category: 'technical' },
      MOMENTUM_RISK: { weight: 0.1, category: 'technical' },
      
      // Other risk factors
      SIZE_RISK: { weight: 0.05, category: 'other' },
      CORRELATION_RISK: { weight: 0.1, category: 'other' }
    };
  }

  // Calculate portfolio-level risk metrics
  async calculatePortfolioRisk(positions) {
    try {
      if (!positions || positions.length === 0) {
        return this.getEmptyRiskProfile();
      }

      // Get market data for all positions
      const symbols = positions.map(p => p.symbol);
      const marketData = await this.getMarketDataForSymbols(symbols);
      const technicalData = await this.getTechnicalDataForSymbols(symbols);
      
      // Calculate individual position risks
      const positionRisks = await Promise.all(
        positions.map(position => this.calculatePositionRisk(position, marketData, technicalData))
      );

      // Calculate portfolio-level metrics
      const portfolioMetrics = this.calculatePortfolioMetrics(positions, positionRisks);
      
      // Calculate Value at Risk (VaR)
      const varCalculations = this.calculateVaR(positions, positionRisks);
      
      // Calculate stress test scenarios
      const stressTests = this.calculateStressTests(positions, positionRisks);
      
      // Generate risk recommendations
      const recommendations = this.generateRiskRecommendations(portfolioMetrics, positionRisks);

      return {
        portfolioMetrics,
        positionRisks,
        varCalculations,
        stressTests,
        recommendations,
        riskScore: portfolioMetrics.overallRiskScore,
        riskGrade: this.getRiskGrade(portfolioMetrics.overallRiskScore),
        lastUpdated: new Date().toISOString()
      };
    } catch (error) {
      console.error('Error calculating portfolio risk:', error);
      throw error;
    }
  }

  // Calculate risk for individual position
  async calculatePositionRisk(position, marketData, technicalData) {
    const symbol = position.symbol;
    const stockData = marketData[symbol] || {};
    const techData = technicalData[symbol] || {};
    
    const risks = {
      marketRisk: this.calculateMarketRisk(stockData, techData),
      financialRisk: this.calculateFinancialRisk(stockData),
      technicalRisk: this.calculateTechnicalRisk(techData),
      concentrationRisk: this.calculateConcentrationRisk(position),
      liquidityRisk: this.calculateLiquidityRisk(stockData),
      specificRisk: this.calculateSpecificRisk(stockData, techData)
    };

    const overallRisk = this.calculateOverallPositionRisk(risks);
    
    return {
      symbol,
      marketValue: position.marketValue || 0,
      weight: position.weight || 0,
      risks,
      overallRisk,
      riskContribution: overallRisk * (position.weight || 0),
      recommendations: this.getPositionRecommendations(risks, overallRisk)
    };
  }

  // Calculate market risk (Beta-based)
  calculateMarketRisk(stockData, techData) {
    const beta = stockData.beta || 1.0;
    const correlation = stockData.correlation_with_market || 0.7;
    
    // Market risk score based on beta and correlation
    let marketRiskScore = 0;
    
    if (beta > 1.5) marketRiskScore += 30;
    else if (beta > 1.2) marketRiskScore += 20;
    else if (beta > 0.8) marketRiskScore += 10;
    else if (beta < 0.5) marketRiskScore += 15; // Very low beta can be risky too
    
    if (correlation > 0.8) marketRiskScore += 15;
    else if (correlation < 0.3) marketRiskScore += 10;
    
    return Math.min(100, marketRiskScore);
  }

  // Calculate financial risk
  calculateFinancialRisk(stockData) {
    let financialRisk = 0;
    
    // Debt-to-equity risk
    const debtToEquity = stockData.debt_to_equity || 0;
    if (debtToEquity > 1.5) financialRisk += 30;
    else if (debtToEquity > 1.0) financialRisk += 20;
    else if (debtToEquity > 0.5) financialRisk += 10;
    
    // Current ratio risk
    const currentRatio = stockData.current_ratio || 1.5;
    if (currentRatio < 1.0) financialRisk += 25;
    else if (currentRatio < 1.5) financialRisk += 15;
    
    // Interest coverage risk
    const interestCoverage = stockData.interest_coverage || 5;
    if (interestCoverage < 2.0) financialRisk += 25;
    else if (interestCoverage < 3.0) financialRisk += 15;
    
    // ROE consistency risk
    const roe = stockData.roe || 0;
    if (roe < 0.05) financialRisk += 20;
    else if (roe < 0.10) financialRisk += 10;
    
    return Math.min(100, financialRisk);
  }

  // Calculate technical risk
  calculateTechnicalRisk(techData) {
    let technicalRisk = 0;
    
    // Volatility risk (using ATR as proxy)
    const atr = techData.atr || 0;
    const price = techData.close || techData.current_price || 100;
    const volatility = atr / price;
    
    if (volatility > 0.05) technicalRisk += 25;
    else if (volatility > 0.03) technicalRisk += 15;
    else if (volatility > 0.02) technicalRisk += 10;
    
    // Momentum risk
    const momentum3m = techData.price_momentum_3m || 0;
    const momentum12m = techData.price_momentum_12m || 0;
    
    if (momentum3m < -0.2) technicalRisk += 20;
    else if (momentum3m < -0.1) technicalRisk += 10;
    
    if (momentum12m < -0.3) technicalRisk += 15;
    
    // RSI extremes
    const rsi = techData.rsi || 50;
    if (rsi > 80 || rsi < 20) technicalRisk += 15;
    
    return Math.min(100, technicalRisk);
  }

  // Calculate concentration risk
  calculateConcentrationRisk(position) {
    const weight = position.weight || 0;
    
    if (weight > 0.3) return 40; // >30% concentration
    if (weight > 0.2) return 25; // >20% concentration
    if (weight > 0.1) return 15; // >10% concentration
    if (weight > 0.05) return 10; // >5% concentration
    
    return 5; // Minimal concentration risk
  }

  // Calculate liquidity risk
  calculateLiquidityRisk(stockData) {
    const marketCap = stockData.market_cap || 0;
    const avgVolume = stockData.average_volume || 0;
    
    let liquidityRisk = 0;
    
    // Market cap based liquidity
    if (marketCap < 300000000) liquidityRisk += 30; // <$300M
    else if (marketCap < 1000000000) liquidityRisk += 20; // <$1B
    else if (marketCap < 5000000000) liquidityRisk += 10; // <$5B
    
    // Volume based liquidity
    if (avgVolume < 100000) liquidityRisk += 25; // <100k shares
    else if (avgVolume < 500000) liquidityRisk += 15; // <500k shares
    else if (avgVolume < 1000000) liquidityRisk += 10; // <1M shares
    
    return Math.min(100, liquidityRisk);
  }

  // Calculate company-specific risk
  calculateSpecificRisk(stockData, techData) {
    let specificRisk = 0;
    
    // Earnings quality risk
    const operatingMargin = stockData.operating_margin || 0;
    const netMargin = stockData.net_margin || 0;
    
    if (operatingMargin < 0.05) specificRisk += 20;
    else if (operatingMargin < 0.10) specificRisk += 10;
    
    if (netMargin < 0.03) specificRisk += 15;
    else if (netMargin < 0.05) specificRisk += 10;
    
    // Growth sustainability risk
    const revenueGrowth = stockData.revenue_growth || 0;
    const earningsGrowth = stockData.earnings_growth || 0;
    
    if (revenueGrowth < -0.1) specificRisk += 20;
    if (earningsGrowth < -0.2) specificRisk += 25;
    
    return Math.min(100, specificRisk);
  }

  // Calculate overall position risk
  calculateOverallPositionRisk(risks) {
    const weights = {
      marketRisk: 0.25,
      financialRisk: 0.25,
      technicalRisk: 0.20,
      concentrationRisk: 0.15,
      liquidityRisk: 0.10,
      specificRisk: 0.05
    };
    
    let weightedRisk = 0;
    for (const [riskType, risk] of Object.entries(risks)) {
      weightedRisk += (risk * (weights[riskType] || 0));
    }
    
    return Math.min(100, weightedRisk);
  }

  // Calculate portfolio-level metrics
  calculatePortfolioMetrics(positions, positionRisks) {
    const totalValue = positions.reduce((sum, p) => sum + (p.marketValue || 0), 0);
    
    if (totalValue === 0) return this.getEmptyPortfolioMetrics();
    
    // Weighted average risk
    const weightedRisk = positionRisks.reduce((sum, risk) => {
      return sum + (risk.overallRisk * (risk.marketValue / totalValue));
    }, 0);
    
    // Diversification metrics
    const numPositions = positions.length;
    const maxWeight = Math.max(...positions.map(p => p.weight || 0));
    const herfindahlIndex = positions.reduce((sum, p) => sum + Math.pow(p.weight || 0, 2), 0);
    
    // Sector concentration
    const sectorWeights = {};
    positions.forEach(p => {
      const sector = p.sector || 'Unknown';
      sectorWeights[sector] = (sectorWeights[sector] || 0) + (p.weight || 0);
    });
    const maxSectorWeight = Math.max(...Object.values(sectorWeights));
    
    // Calculate diversification score
    const diversificationScore = this.calculateDiversificationScore(numPositions, maxWeight, herfindahlIndex);
    
    return {
      overallRiskScore: weightedRisk,
      diversificationScore,
      numPositions,
      maxPositionWeight: maxWeight,
      maxSectorWeight,
      herfindahlIndex,
      riskContributions: positionRisks.map(r => ({
        symbol: r.symbol,
        contribution: r.riskContribution
      })).sort((a, b) => b.contribution - a.contribution)
    };
  }

  // Calculate diversification score
  calculateDiversificationScore(numPositions, maxWeight, herfindahlIndex) {
    let score = 100;
    
    // Penalty for too few positions
    if (numPositions < 10) score -= (10 - numPositions) * 5;
    
    // Penalty for high concentration
    if (maxWeight > 0.2) score -= (maxWeight - 0.2) * 200;
    
    // Penalty for high Herfindahl index
    if (herfindahlIndex > 0.1) score -= (herfindahlIndex - 0.1) * 300;
    
    return Math.max(0, score);
  }

  // Calculate Value at Risk (VaR)
  calculateVaR(positions, positionRisks) {
    const totalValue = positions.reduce((sum, p) => sum + (p.marketValue || 0), 0);
    
    if (totalValue === 0) return { var95: 0, var99: 0, expectedShortfall: 0 };
    
    // Simplified VaR calculation using portfolio volatility
    const portfolioVolatility = this.calculatePortfolioVolatility(positions, positionRisks);
    
    // Assuming normal distribution (simplified)
    const var95 = totalValue * portfolioVolatility * 1.65; // 95% confidence
    const var99 = totalValue * portfolioVolatility * 2.33; // 99% confidence
    const expectedShortfall = totalValue * portfolioVolatility * 2.5; // Expected shortfall
    
    return {
      var95,
      var99,
      expectedShortfall,
      portfolioVolatility,
      confidence95: var95 / totalValue,
      confidence99: var99 / totalValue
    };
  }

  // Calculate portfolio volatility
  calculatePortfolioVolatility(positions, positionRisks) {
    // Simplified calculation using weighted average of individual volatilities
    const totalValue = positions.reduce((sum, p) => sum + (p.marketValue || 0), 0);
    
    if (totalValue === 0) return 0;
    
    const weightedVolatility = positionRisks.reduce((sum, risk) => {
      const weight = risk.marketValue / totalValue;
      const volatility = risk.risks.technicalRisk / 100; // Convert to decimal
      return sum + (weight * volatility);
    }, 0);
    
    return weightedVolatility;
  }

  // Calculate stress test scenarios
  calculateStressTests(positions, positionRisks) {
    const totalValue = positions.reduce((sum, p) => sum + (p.marketValue || 0), 0);
    
    const scenarios = {
      marketCrash: this.calculateMarketCrashScenario(positions, positionRisks, totalValue),
      sectorRotation: this.calculateSectorRotationScenario(positions, positionRisks, totalValue),
      interestRateShock: this.calculateInterestRateShockScenario(positions, positionRisks, totalValue),
      liquidityCrisis: this.calculateLiquidityCrisisScenario(positions, positionRisks, totalValue)
    };
    
    return scenarios;
  }

  // Market crash scenario (-30% market decline)
  calculateMarketCrashScenario(positions, positionRisks, totalValue) {
    const marketDecline = -0.30;
    
    let portfolioImpact = 0;
    positions.forEach((position, i) => {
      const beta = positionRisks[i].risks.marketRisk / 50 || 1.0; // Rough beta approximation
      const positionImpact = position.marketValue * marketDecline * beta;
      portfolioImpact += positionImpact;
    });
    
    return {
      name: 'Market Crash (-30%)',
      portfolioImpact,
      percentageImpact: portfolioImpact / totalValue,
      worstPositions: this.getWorstPositions(positions, positionRisks, 'marketRisk')
    };
  }

  // Sector rotation scenario
  calculateSectorRotationScenario(positions, positionRisks, totalValue) {
    // Simplified: assume tech sector down 20%, other sectors up 5%
    let portfolioImpact = 0;
    
    positions.forEach(position => {
      const sector = position.sector || 'Unknown';
      const impact = sector === 'Technology' ? -0.20 : 0.05;
      portfolioImpact += position.marketValue * impact;
    });
    
    return {
      name: 'Sector Rotation (Tech -20%, Others +5%)',
      portfolioImpact,
      percentageImpact: portfolioImpact / totalValue,
      affectedSectors: ['Technology']
    };
  }

  // Interest rate shock scenario
  calculateInterestRateShockScenario(positions, positionRisks, totalValue) {
    // Simplified: high debt companies more affected
    let portfolioImpact = 0;
    
    positions.forEach((position, i) => {
      const financialRisk = positionRisks[i].risks.financialRisk;
      const impact = -(financialRisk / 100) * 0.15; // Up to -15% for high debt companies
      portfolioImpact += position.marketValue * impact;
    });
    
    return {
      name: 'Interest Rate Shock (+200bps)',
      portfolioImpact,
      percentageImpact: portfolioImpact / totalValue,
      worstPositions: this.getWorstPositions(positions, positionRisks, 'financialRisk')
    };
  }

  // Liquidity crisis scenario
  calculateLiquidityCrisisScenario(positions, positionRisks, totalValue) {
    let portfolioImpact = 0;
    
    positions.forEach((position, i) => {
      const liquidityRisk = positionRisks[i].risks.liquidityRisk;
      const impact = -(liquidityRisk / 100) * 0.25; // Up to -25% for illiquid positions
      portfolioImpact += position.marketValue * impact;
    });
    
    return {
      name: 'Liquidity Crisis',
      portfolioImpact,
      percentageImpact: portfolioImpact / totalValue,
      worstPositions: this.getWorstPositions(positions, positionRisks, 'liquidityRisk')
    };
  }

  // Get worst positions by risk type
  getWorstPositions(positions, positionRisks, riskType) {
    return positions
      .map((position, i) => ({
        symbol: position.symbol,
        weight: position.weight,
        riskScore: positionRisks[i].risks[riskType]
      }))
      .sort((a, b) => b.riskScore - a.riskScore)
      .slice(0, 5);
  }

  // Generate risk recommendations
  generateRiskRecommendations(portfolioMetrics, positionRisks) {
    const recommendations = [];
    
    // Concentration recommendations
    if (portfolioMetrics.maxPositionWeight > 0.2) {
      recommendations.push({
        type: 'warning',
        category: 'concentration',
        title: 'High Position Concentration',
        message: `Consider reducing position size for holdings above 20% (currently ${(portfolioMetrics.maxPositionWeight * 100).toFixed(1)}%)`,
        priority: 'high'
      });
    }
    
    // Diversification recommendations
    if (portfolioMetrics.numPositions < 10) {
      recommendations.push({
        type: 'info',
        category: 'diversification',
        title: 'Increase Diversification',
        message: `Consider adding more positions to improve diversification (currently ${portfolioMetrics.numPositions} positions)`,
        priority: 'medium'
      });
    }
    
    // Risk recommendations for high-risk positions
    const highRiskPositions = positionRisks.filter(r => r.overallRisk > 70);
    if (highRiskPositions.length > 0) {
      recommendations.push({
        type: 'warning',
        category: 'position_risk',
        title: 'High Risk Positions',
        message: `Review positions with high risk scores: ${highRiskPositions.map(p => p.symbol).join(', ')}`,
        priority: 'high'
      });
    }
    
    return recommendations;
  }

  // Get risk grade
  getRiskGrade(riskScore) {
    if (riskScore <= 20) return 'A';
    if (riskScore <= 35) return 'B';
    if (riskScore <= 50) return 'C';
    if (riskScore <= 70) return 'D';
    return 'F';
  }

  // Get market data for symbols
  async getMarketDataForSymbols(symbols) {
    try {
      if (symbols.length === 0) return {};
      
      const placeholders = symbols.map((_, i) => `$${i + 1}`).join(',');
      const result = await query(`
        SELECT 
          sf.symbol,
          sf.beta,
          sf.debt_to_equity,
          sf.current_ratio,
          sf.interest_coverage,
          sf.roe,
          sf.operating_margin,
          sf.net_margin,
          sf.revenue_growth,
          sf.earnings_growth,
          sf.market_cap,
          sse.sector
        FROM stock_fundamentals sf
        JOIN stock_symbols_enhanced sse ON sf.symbol = sse.symbol
        WHERE sf.symbol IN (${placeholders})
      `, symbols);
      
      const dataMap = {};
      result.rows.forEach(row => {
        dataMap[row.symbol] = row;
      });
      
      return dataMap;
    } catch (error) {
      console.error('Error fetching market data:', error);
      return {};
    }
  }

  // Get technical data for symbols
  async getTechnicalDataForSymbols(symbols) {
    try {
      if (symbols.length === 0) return {};
      
      const placeholders = symbols.map((_, i) => `$${i + 1}`).join(',');
      const result = await query(`
        SELECT 
          symbol,
          rsi,
          atr,
          price_momentum_3m,
          price_momentum_12m,
          close as current_price
        FROM technical_data_daily
        WHERE symbol IN (${placeholders})
        AND date = (
          SELECT MAX(date) 
          FROM technical_data_daily 
          WHERE symbol = technical_data_daily.symbol
        )
      `, symbols);
      
      const dataMap = {};
      result.rows.forEach(row => {
        dataMap[row.symbol] = row;
      });
      
      return dataMap;
    } catch (error) {
      console.error('Error fetching technical data:', error);
      return {};
    }
  }

  // Get position recommendations
  getPositionRecommendations(risks, overallRisk) {
    const recommendations = [];
    
    if (risks.financialRisk > 60) {
      recommendations.push('Monitor debt levels and liquidity');
    }
    
    if (risks.technicalRisk > 70) {
      recommendations.push('High volatility - consider reducing position size');
    }
    
    if (risks.concentrationRisk > 30) {
      recommendations.push('Position size too large - consider trimming');
    }
    
    if (overallRisk > 80) {
      recommendations.push('High overall risk - review position thoroughly');
    }
    
    return recommendations;
  }

  // Get empty risk profile
  getEmptyRiskProfile() {
    return {
      portfolioMetrics: this.getEmptyPortfolioMetrics(),
      positionRisks: [],
      varCalculations: { var95: 0, var99: 0, expectedShortfall: 0 },
      stressTests: {},
      recommendations: [],
      riskScore: 0,
      riskGrade: 'N/A',
      lastUpdated: new Date().toISOString()
    };
  }

  // Get empty portfolio metrics
  getEmptyPortfolioMetrics() {
    return {
      overallRiskScore: 0,
      diversificationScore: 0,
      numPositions: 0,
      maxPositionWeight: 0,
      maxSectorWeight: 0,
      herfindahlIndex: 0,
      riskContributions: []
    };
  }

  /**
   * Calculate order-specific risk for trading verification
   * CRITICAL: This method is required for order execution safety
   */
  async calculateOrderRisk(orderData) {
    try {
      const { symbol, quantity, side, price, stopLossPrice } = orderData;
      
      // Validate input parameters
      if (!symbol || !quantity || !side || !price) {
        throw new Error('Missing required order parameters for risk calculation');
      }

      console.log(`🎯 Calculating order risk for ${side} ${quantity} ${symbol} at $${price}`);

      // Get current market data and portfolio context
      const [marketData, portfolioContext] = await Promise.all([
        this.getSymbolMarketData(symbol),
        this.getUserPortfolioContext(orderData.userId || 'unknown')
      ]);

      // Calculate order value and risk exposure
      const orderValue = Math.abs(quantity * price);
      const riskAmount = stopLossPrice ? 
        Math.abs((price - stopLossPrice) * quantity) : 
        orderValue * 0.1; // 10% default risk if no stop loss

      // Calculate order-specific risk factors
      const risks = {
        // Market Risk: Based on symbol volatility and market conditions
        marketRisk: this.calculateOrderMarketRisk(marketData),
        
        // Position Size Risk: Order size relative to portfolio
        positionSizeRisk: this.calculatePositionSizeRisk(orderValue, portfolioContext.totalValue),
        
        // Liquidity Risk: Based on volume and spread
        liquidityRisk: this.calculateOrderLiquidityRisk(marketData),
        
        // Concentration Risk: Symbol exposure relative to portfolio
        concentrationRisk: this.calculateOrderConcentrationRisk(symbol, portfolioContext),
        
        // Risk/Reward Ratio
        riskRewardRatio: stopLossPrice ? Math.abs(price - stopLossPrice) / (price * 0.05) : 5
      };

      // Calculate overall order risk score (0-100)
      const overallRisk = this.calculateOverallOrderRisk(risks);

      // Determine risk approval status
      const approval = this.determineOrderApproval(overallRisk, risks, orderData);

      const result = {
        orderRiskScore: overallRisk,
        riskAmount: riskAmount,
        orderValue: orderValue,
        risks: risks,
        approval: approval,
        recommendations: this.getOrderRecommendations(risks, approval),
        calculatedAt: new Date().toISOString()
      };

      console.log(`✅ Order risk calculated: Score=${overallRisk}, Approved=${approval.approved}`);
      return result;

    } catch (error) {
      console.error('❌ Order risk calculation failed:', error.message);
      
      // Return high-risk result to prevent dangerous orders
      return {
        orderRiskScore: 95,
        riskAmount: orderData.quantity * orderData.price,
        orderValue: orderData.quantity * orderData.price,
        risks: { calculationError: true },
        approval: { 
          approved: false, 
          reason: 'Risk calculation failed - order rejected for safety',
          requiresManualReview: true 
        },
        recommendations: ['Risk calculation failed - manual review required'],
        calculatedAt: new Date().toISOString(),
        error: error.message
      };
    }
  }

  /**
   * Calculate market risk for specific order
   */
  calculateOrderMarketRisk(marketData) {
    if (!marketData) return 75; // High risk if no data
    
    let risk = 0;
    
    // Volatility-based risk
    const volatility = marketData.volatility || 0.3;
    if (volatility > 0.5) risk += 30;
    else if (volatility > 0.3) risk += 20;
    else if (volatility > 0.2) risk += 10;
    
    // Spread-based risk
    const spread = marketData.spread || 0.05;
    if (spread > 0.05) risk += 20;
    else if (spread > 0.02) risk += 10;
    
    return Math.min(100, risk);
  }

  /**
   * Calculate position size risk relative to portfolio
   */
  calculatePositionSizeRisk(orderValue, portfolioValue) {
    if (!portfolioValue || portfolioValue === 0) return 50; // Medium risk if unknown
    
    const positionPercent = (orderValue / portfolioValue) * 100;
    
    if (positionPercent > 20) return 90;      // Very high risk
    else if (positionPercent > 10) return 60; // High risk
    else if (positionPercent > 5) return 30;  // Medium risk
    else return 10;                           // Low risk
  }

  /**
   * Calculate order liquidity risk
   */
  calculateOrderLiquidityRisk(marketData) {
    if (!marketData) return 60;
    
    const avgVolume = marketData.avgVolume || 0;
    const spread = marketData.spread || 0.05;
    
    let risk = 0;
    
    // Volume-based liquidity risk
    if (avgVolume < 50000) risk += 40;
    else if (avgVolume < 200000) risk += 25;
    else if (avgVolume < 500000) risk += 15;
    
    // Spread-based liquidity risk
    if (spread > 0.1) risk += 30;
    else if (spread > 0.05) risk += 20;
    else if (spread > 0.02) risk += 10;
    
    return Math.min(100, risk);
  }

  /**
   * Calculate concentration risk for order
   */
  calculateOrderConcentrationRisk(symbol, portfolioContext) {
    if (!portfolioContext.positions) return 20;
    
    const existingPosition = portfolioContext.positions.find(p => p.symbol === symbol);
    if (!existingPosition) return 10; // New position - lower concentration risk
    
    const currentWeight = (existingPosition.marketValue / portfolioContext.totalValue) * 100;
    
    if (currentWeight > 15) return 80;
    else if (currentWeight > 10) return 50;
    else if (currentWeight > 5) return 25;
    else return 10;
  }

  /**
   * Calculate overall order risk score
   */
  calculateOverallOrderRisk(risks) {
    const weights = {
      marketRisk: 0.25,
      positionSizeRisk: 0.30,
      liquidityRisk: 0.20,
      concentrationRisk: 0.25
    };

    let weightedRisk = 0;
    for (const [riskType, risk] of Object.entries(risks)) {
      if (weights[riskType]) {
        weightedRisk += risk * weights[riskType];
      }
    }

    return Math.min(100, Math.max(0, weightedRisk));
  }

  /**
   * Determine if order should be approved based on risk
   */
  determineOrderApproval(overallRisk, risks, orderData) {
    // Automatic rejection criteria
    if (overallRisk > 85) {
      return {
        approved: false,
        reason: 'Overall risk too high',
        requiresManualReview: true
      };
    }

    if (risks.positionSizeRisk > 80) {
      return {
        approved: false,
        reason: 'Position size too large relative to portfolio',
        requiresManualReview: true
      };
    }

    if (risks.liquidityRisk > 70) {
      return {
        approved: false,
        reason: 'Insufficient liquidity for safe execution',
        requiresManualReview: false
      };
    }

    // Conditional approval
    if (overallRisk > 60) {
      return {
        approved: true,
        reason: 'Approved with warnings - monitor closely',
        warnings: ['High risk order - consider reducing size', 'Monitor execution carefully']
      };
    }

    // Standard approval
    return {
      approved: true,
      reason: 'Risk within acceptable parameters',
      warnings: []
    };
  }

  /**
   * Get order recommendations based on risk analysis
   */
  getOrderRecommendations(risks, approval) {
    const recommendations = [];

    if (!approval.approved) {
      recommendations.push('Order rejected due to excessive risk');
      recommendations.push('Consider reducing position size or waiting for better market conditions');
      return recommendations;
    }

    if (risks.positionSizeRisk > 50) {
      recommendations.push('Consider reducing position size to manage risk');
    }

    if (risks.liquidityRisk > 40) {
      recommendations.push('Monitor order execution closely due to liquidity concerns');
    }

    if (risks.marketRisk > 50) {
      recommendations.push('High market volatility - consider using limit orders');
    }

    if (risks.concentrationRisk > 30) {
      recommendations.push('Adding to existing position - monitor concentration risk');
    }

    if (recommendations.length === 0) {
      recommendations.push('Order risk within normal parameters');
    }

    return recommendations;
  }

  /**
   * Get symbol market data (placeholder - integrate with real data source)
   */
  async getSymbolMarketData(symbol) {
    try {
      // In production, this would fetch real market data
      // For now, return reasonable defaults
      return {
        symbol: symbol,
        volatility: 0.25,
        avgVolume: 1000000,
        spread: 0.01,
        price: 100,
        lastUpdated: new Date().toISOString()
      };
    } catch (error) {
      console.error(`Failed to get market data for ${symbol}:`, error.message);
      return null;
    }
  }

  /**
   * Get user portfolio context (placeholder - integrate with portfolio service)
   */
  async getUserPortfolioContext(userId) {
    try {
      // In production, this would fetch user's current portfolio
      // For now, return safe defaults
      return {
        totalValue: 100000,
        positions: [],
        lastUpdated: new Date().toISOString()
      };
    } catch (error) {
      console.error(`Failed to get portfolio context for user ${userId}:`, error.message);
      return {
        totalValue: 0,
        positions: []
      };
    }
  }
}

module.exports = RiskCalculator;