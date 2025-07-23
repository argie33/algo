const logger = require('./logger');
const { query } = require('./database');

/**
 * Institutional-Grade Risk Management and Position Sizing System
 * Implements sophisticated risk management algorithms for trading strategies
 */
class RiskManager {
  constructor() {
    this.riskModels = new Map();
    this.positionLimits = new Map();
    this.correlationMatrix = new Map();
    this.volatilityCache = new Map();
    this.portfolioRiskMetrics = new Map();
  }

  /**
   * Calculate position size based on risk management rules
   * @param {Object} params - Position sizing parameters
   * @returns {Object} Position sizing recommendation
   */
  async calculatePositionSize(params) {
    const startTime = Date.now();
    
    try {
      const {
        userId,
        symbol,
        signal,
        portfolioValue,
        riskPerTrade = 0.02,
        maxPositionSize = 0.1,
        volatilityAdjustment = true,
        correlationAdjustment = true
      } = params;

      logger.info('🎯 Calculating position size', {
        userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
        symbol: symbol,
        portfolioValue: portfolioValue,
        riskPerTrade: riskPerTrade,
        maxPositionSize: maxPositionSize,
        signalConfidence: signal?.confidence || 'unknown'
      });

      // Validate inputs
      if (!userId || typeof userId !== 'string' || userId.trim() === '') {
        throw new Error('Invalid userId: must be a non-empty string');
      }
      if (!symbol || typeof symbol !== 'string' || symbol.trim() === '') {
        throw new Error('Invalid symbol: must be a non-empty string');
      }
      if (!portfolioValue || typeof portfolioValue !== 'number' || portfolioValue <= 0) {
        throw new Error('Invalid portfolioValue: must be a positive number');
      }
      if (riskPerTrade && (typeof riskPerTrade !== 'number' || riskPerTrade <= 0 || riskPerTrade > 1)) {
        throw new Error('Invalid riskPerTrade: must be between 0 and 1');
      }
      if (maxPositionSize && (typeof maxPositionSize !== 'number' || maxPositionSize <= 0 || maxPositionSize > 1)) {
        throw new Error('Invalid maxPositionSize: must be between 0 and 1');
      }

      // Get current portfolio composition
      const portfolioComposition = await this.getPortfolioComposition(userId);
      
      // Calculate base position size
      const basePositionSize = await this.calculateBasePositionSize({
        portfolioValue,
        riskPerTrade,
        maxPositionSize,
        signal
      });

      // Apply volatility adjustment
      const volatilityAdjustedSize = volatilityAdjustment ? 
        await this.applyVolatilityAdjustment(symbol, basePositionSize) : 
        basePositionSize;

      // Apply correlation adjustment
      const correlationAdjustedSize = correlationAdjustment ? 
        await this.applyCorrelationAdjustment(symbol, portfolioComposition, volatilityAdjustedSize) : 
        volatilityAdjustedSize;

      // Apply concentration limits
      const concentrationAdjustedSize = await this.applyConcentrationLimits(
        symbol, 
        portfolioComposition, 
        correlationAdjustedSize, 
        portfolioValue
      );

      // Apply sector limits
      const sectorAdjustedSize = await this.applySectorLimits(
        symbol, 
        portfolioComposition, 
        concentrationAdjustedSize, 
        portfolioValue
      );

      // Calculate final position metrics - enforce max position size limit
      const finalPositionSize = Math.max(0, Math.min(sectorAdjustedSize, maxPositionSize));
      const positionValue = finalPositionSize * portfolioValue;
      const riskAmount = positionValue * riskPerTrade;

      // Generate risk assessment
      const riskAssessment = await this.assessPositionRisk({
        symbol,
        positionSize: finalPositionSize,
        portfolioValue,
        portfolioComposition,
        signal
      });

      const result = {
        symbol: symbol,
        recommendedSize: finalPositionSize,
        positionValue: positionValue,
        riskAmount: riskAmount,
        maxLoss: riskAmount,
        adjustments: {
          baseSize: basePositionSize,
          volatilityAdjusted: volatilityAdjustedSize,
          correlationAdjusted: correlationAdjustedSize,
          concentrationAdjusted: concentrationAdjustedSize,
          sectorAdjusted: sectorAdjustedSize
        },
        riskMetrics: {
          portfolioRisk: riskAssessment.portfolioRisk,
          positionRisk: riskAssessment.positionRisk,
          concentrationRisk: riskAssessment.concentrationRisk,
          correlationRisk: riskAssessment.correlationRisk,
          overallRiskScore: riskAssessment.overallRiskScore
        },
        limits: {
          maxPositionSize: maxPositionSize,
          riskPerTrade: riskPerTrade,
          sectorLimit: await this.getSectorLimit(symbol),
          concentrationLimit: 0.15 // 15% max concentration
        },
        recommendation: this.generateRiskRecommendation(riskAssessment, finalPositionSize),
        processingTime: Date.now() - startTime
      };

      logger.info('✅ Position size calculated', {
        symbol: symbol,
        recommendedSize: finalPositionSize,
        positionValue: positionValue,
        riskScore: riskAssessment.overallRiskScore,
        processingTime: result.processingTime
      });

      return result;

    } catch (error) {
      logger.error('❌ Position size calculation failed', {
        symbol: params.symbol,
        error: error.message,
        errorStack: error.stack,
        processingTime: Date.now() - startTime
      });
      
      throw new Error(`Position sizing failed: ${error.message}`);
    }
  }

  /**
   * Calculate base position size before adjustments
   * @param {Object} params - Base calculation parameters
   * @returns {number} Base position size
   */
  async calculateBasePositionSize({ portfolioValue, riskPerTrade, maxPositionSize, signal }) {
    // Start with risk-based position size
    let baseSize = riskPerTrade;

    // Adjust for signal confidence
    if (signal && signal.confidence) {
      const confidenceMultiplier = Math.min(signal.confidence * 1.5, 1.0);
      baseSize *= confidenceMultiplier;
    }

    // Adjust for signal strength
    if (signal && signal.strength) {
      const strengthMultipliers = {
        'weak': 0.5,
        'moderate': 1.0,
        'strong': 1.3
      };
      baseSize *= strengthMultipliers[signal.strength] || 1.0;
    }

    // Apply maximum position size limit
    return Math.min(baseSize, maxPositionSize);
  }

  /**
   * Apply volatility adjustment to position size
   * @param {string} symbol - Stock symbol
   * @param {number} baseSize - Base position size
   * @returns {number} Volatility-adjusted position size
   */
  async applyVolatilityAdjustment(symbol, baseSize) {
    try {
      const volatility = await this.getSymbolVolatility(symbol);
      
      // Adjust position size inversely to volatility
      // Higher volatility = smaller position size
      const volatilityAdjustment = Math.max(0.3, Math.min(1.5, 1.0 / Math.sqrt(volatility)));
      
      return baseSize * volatilityAdjustment;
      
    } catch (error) {
      logger.warn('⚠️ Volatility adjustment failed, using base size', {
        symbol: symbol,
        error: error.message
      });
      return baseSize;
    }
  }

  /**
   * Apply correlation adjustment to position size
   * @param {string} symbol - Stock symbol
   * @param {Object} portfolioComposition - Current portfolio
   * @param {number} currentSize - Current position size
   * @returns {number} Correlation-adjusted position size
   */
  async applyCorrelationAdjustment(symbol, portfolioComposition, currentSize) {
    try {
      const correlationRisk = await this.calculateCorrelationRisk(symbol, portfolioComposition);
      
      // Reduce position size if highly correlated with existing positions
      const correlationAdjustment = Math.max(0.5, 1.0 - (correlationRisk * 0.5));
      
      return currentSize * correlationAdjustment;
      
    } catch (error) {
      logger.warn('⚠️ Correlation adjustment failed, using current size', {
        symbol: symbol,
        error: error.message
      });
      return currentSize;
    }
  }

  /**
   * Apply concentration limits to position size
   * @param {string} symbol - Stock symbol
   * @param {Object} portfolioComposition - Current portfolio
   * @param {number} currentSize - Current position size
   * @param {number} portfolioValue - Total portfolio value
   * @returns {number} Concentration-adjusted position size
   */
  async applyConcentrationLimits(symbol, portfolioComposition, currentSize, portfolioValue) {
    const concentrationLimit = 0.15; // 15% maximum concentration
    
    // Check if position would exceed concentration limit
    const currentHolding = portfolioComposition[symbol] || 0;
    const proposedHolding = currentHolding + (currentSize * portfolioValue);
    const proposedConcentration = proposedHolding / portfolioValue;
    
    if (proposedConcentration > concentrationLimit) {
      const maxAllowedHolding = portfolioValue * concentrationLimit;
      const maxAdditionalHolding = maxAllowedHolding - currentHolding;
      const maxAdditionalSize = Math.max(0, maxAdditionalHolding / portfolioValue);
      
      logger.info('⚠️ Concentration limit applied', {
        symbol: symbol,
        originalSize: currentSize,
        adjustedSize: maxAdditionalSize,
        concentrationLimit: concentrationLimit,
        proposedConcentration: proposedConcentration
      });
      
      return maxAdditionalSize;
    }
    
    return currentSize;
  }

  /**
   * Apply sector limits to position size
   * @param {string} symbol - Stock symbol
   * @param {Object} portfolioComposition - Current portfolio
   * @param {number} currentSize - Current position size
   * @param {number} portfolioValue - Total portfolio value
   * @returns {number} Sector-adjusted position size
   */
  async applySectorLimits(symbol, portfolioComposition, currentSize, portfolioValue) {
    try {
      const sector = await this.getSymbolSector(symbol);
      const sectorLimit = await this.getSectorLimit(symbol);
      
      // Calculate current sector exposure
      const currentSectorExposure = await this.calculateSectorExposure(sector, portfolioComposition);
      const proposedSectorExposure = currentSectorExposure + (currentSize * portfolioValue);
      const proposedSectorConcentration = proposedSectorExposure / portfolioValue;
      
      if (proposedSectorConcentration > sectorLimit) {
        const maxAllowedSectorHolding = portfolioValue * sectorLimit;
        const maxAdditionalSectorHolding = maxAllowedSectorHolding - currentSectorExposure;
        const maxAdditionalSize = Math.max(0, maxAdditionalSectorHolding / portfolioValue);
        
        logger.info('⚠️ Sector limit applied', {
          symbol: symbol,
          sector: sector,
          originalSize: currentSize,
          adjustedSize: maxAdditionalSize,
          sectorLimit: sectorLimit,
          proposedSectorConcentration: proposedSectorConcentration
        });
        
        return maxAdditionalSize;
      }
      
      return currentSize;
      
    } catch (error) {
      logger.warn('⚠️ Sector limit adjustment failed, using current size', {
        symbol: symbol,
        error: error.message
      });
      return currentSize;
    }
  }

  /**
   * Assess overall position risk
   * @param {Object} params - Risk assessment parameters
   * @returns {Object} Risk assessment
   */
  async assessPositionRisk({ symbol, positionSize, portfolioValue, portfolioComposition, signal }) {
    try {
      const portfolioRisk = await this.calculatePortfolioRisk(portfolioComposition);
      const positionRisk = await this.calculatePositionRisk(symbol, positionSize);
      const concentrationRisk = await this.calculateConcentrationRisk(symbol, portfolioComposition);
      const correlationRisk = await this.calculateCorrelationRisk(symbol, portfolioComposition);
      
      // Calculate overall risk score (0-1, higher is riskier)
      const overallRiskScore = Math.min(1.0, 
        (portfolioRisk * 0.3) + 
        (positionRisk * 0.3) + 
        (concentrationRisk * 0.2) + 
        (correlationRisk * 0.2)
      );
      
      return {
        portfolioRisk,
        positionRisk,
        concentrationRisk,
        correlationRisk,
        overallRiskScore,
        riskLevel: this.categorizeRiskLevel(overallRiskScore),
        riskFactors: this.identifyRiskFactors({
          portfolioRisk,
          positionRisk,
          concentrationRisk,
          correlationRisk
        })
      };
      
    } catch (error) {
      logger.error('❌ Risk assessment failed', {
        symbol: symbol,
        error: error.message
      });
      
      // Return conservative risk assessment
      return {
        portfolioRisk: 0.8,
        positionRisk: 0.8,
        concentrationRisk: 0.8,
        correlationRisk: 0.8,
        overallRiskScore: 0.8,
        riskLevel: 'high',
        riskFactors: ['risk_calculation_error']
      };
    }
  }

  /**
   * Generate risk recommendation based on assessment
   * @param {Object} riskAssessment - Risk assessment results
   * @param {number} positionSize - Recommended position size
   * @returns {Object} Risk recommendation
   */
  generateRiskRecommendation(riskAssessment, positionSize) {
    const { overallRiskScore, riskLevel, riskFactors } = riskAssessment;
    
    let recommendation = 'proceed';
    let message = 'Position size is within acceptable risk limits';
    let actions = [];
    
    if (overallRiskScore >= 0.8) {
      recommendation = 'reject';
      message = 'Position exceeds risk tolerance - consider reducing size or avoiding trade';
      actions = ['reduce_position_size', 'wait_for_better_entry', 'diversify_portfolio'];
    } else if (overallRiskScore > 0.6) {
      recommendation = 'caution';
      message = 'Position has elevated risk - proceed with caution';
      actions = ['monitor_closely', 'consider_stop_loss', 'review_correlation'];
    } else if (positionSize === 0) {
      recommendation = 'reject';
      message = 'Position size reduced to zero due to risk limits';
      actions = ['improve_diversification', 'wait_for_better_opportunity'];
    }
    
    return {
      recommendation,
      message,
      actions,
      riskLevel,
      riskScore: overallRiskScore,
      keyRiskFactors: riskFactors.slice(0, 3)
    };
  }

  // Helper methods for risk calculations
  
  async getPortfolioComposition(userId) {
    try {
      const result = await query(`
        SELECT symbol, market_value, sector
        FROM portfolio_holdings ph
        LEFT JOIN symbols s ON ph.symbol = s.symbol
        WHERE ph.user_id = $1
      `, [userId]);
      
      const composition = {};
      result.rows.forEach(row => {
        composition[row.symbol] = row.market_value || 0;
      });
      
      return composition;
      
    } catch (error) {
      logger.error('❌ Failed to get portfolio composition', {
        userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
        error: error.message
      });
      return {};
    }
  }

  async getSymbolVolatility(symbol) {
    try {
      // Try to get from cache first
      const cached = this.volatilityCache.get(symbol);
      if (cached && (Date.now() - cached.timestamp) < 3600000) { // 1 hour cache
        return cached.volatility;
      }
      
      // Calculate volatility from recent price data
      const result = await query(`
        SELECT close, date 
        FROM price_daily 
        WHERE symbol = $1 
        ORDER BY date DESC 
        LIMIT 30
      `, [symbol]);
      
      if (result.rows.length < 20) {
        return 0.2; // Default volatility
      }
      
      const prices = result.rows.map(row => row.close);
      const returns = [];
      
      for (let i = 1; i < prices.length; i++) {
        const dailyReturn = (prices[i] - prices[i-1]) / prices[i-1];
        returns.push(dailyReturn);
      }
      
      const meanReturn = returns.reduce((sum, r) => sum + r, 0) / returns.length;
      const variance = returns.reduce((sum, r) => sum + Math.pow(r - meanReturn, 2), 0) / returns.length;
      const volatility = Math.sqrt(variance * 252); // Annualized volatility
      
      // Cache the result
      this.volatilityCache.set(symbol, {
        volatility: volatility,
        timestamp: Date.now()
      });
      
      return volatility;
      
    } catch (error) {
      logger.warn('⚠️ Volatility calculation failed, using default', {
        symbol: symbol,
        error: error.message
      });
      return 0.2; // Default volatility
    }
  }

  async getSymbolSector(symbol) {
    try {
      const result = await query(`
        SELECT sector 
        FROM symbols 
        WHERE symbol = $1
      `, [symbol]);
      
      return result.rows[0]?.sector || 'Other';
      
    } catch (error) {
      logger.warn('⚠️ Sector lookup failed', {
        symbol: symbol,
        error: error.message
      });
      return 'Other';
    }
  }

  async getSectorLimit(symbol) {
    const sector = await this.getSymbolSector(symbol);
    
    // Sector-specific limits
    const sectorLimits = {
      'Technology': 0.30,
      'Healthcare': 0.25,
      'Financial Services': 0.20,
      'Consumer Discretionary': 0.20,
      'Industrials': 0.15,
      'Energy': 0.10,
      'Materials': 0.10,
      'Real Estate': 0.10,
      'Utilities': 0.10,
      'Consumer Staples': 0.15,
      'Communication Services': 0.15,
      'Other': 0.05
    };
    
    return sectorLimits[sector] || 0.05;
  }

  async calculateSectorExposure(sector, portfolioComposition) {
    try {
      let sectorExposure = 0;
      const totalValue = Object.values(portfolioComposition).reduce((sum, value) => sum + value, 0);
      
      // For each symbol in portfolio, check if it's in the same sector
      for (const symbol of Object.keys(portfolioComposition)) {
        try {
          const symbolSector = await this.getSymbolSector(symbol);
          if (symbolSector === sector) {
            sectorExposure += portfolioComposition[symbol];
          }
        } catch (error) {
          // Skip symbols with sector lookup errors
          continue;
        }
      }
      
      return sectorExposure;
    } catch (error) {
      logger.warn('⚠️ Sector exposure calculation failed', {
        sector: sector,
        error: error.message
      });
      return 0;
    }
  }

  async calculatePortfolioRisk(portfolioComposition) {
    // Simplified portfolio risk calculation
    const positionCount = Object.keys(portfolioComposition).length;
    const diversificationScore = Math.min(1.0, positionCount / 20); // 20 positions = well diversified
    
    return Math.max(0.1, 1.0 - diversificationScore);
  }

  async calculatePositionRisk(symbol, positionSize) {
    const volatility = await this.getSymbolVolatility(symbol);
    return Math.min(1.0, (positionSize * volatility) / 0.1); // Risk increases with position size and volatility
  }

  async calculateConcentrationRisk(symbol, portfolioComposition) {
    const totalValue = Object.values(portfolioComposition).reduce((sum, value) => sum + value, 0);
    const symbolValue = portfolioComposition[symbol] || 0;
    const concentration = totalValue > 0 ? symbolValue / totalValue : 0;
    
    return Math.min(1.0, concentration / 0.05); // Risk increases with concentration
  }

  async calculateCorrelationRisk(symbol, portfolioComposition) {
    // Simplified correlation risk - would need correlation matrix in production
    const sector = await this.getSymbolSector(symbol);
    const sectorExposure = await this.calculateSectorExposure(sector, portfolioComposition);
    
    return Math.min(1.0, sectorExposure / 0.3); // Risk increases with sector concentration
  }

  categorizeRiskLevel(riskScore) {
    if (riskScore < 0.3) return 'low';
    if (riskScore < 0.6) return 'moderate';
    if (riskScore < 0.8) return 'high';
    return 'extreme';
  }

  identifyRiskFactors({ portfolioRisk, positionRisk, concentrationRisk, correlationRisk }) {
    const factors = [];
    
    if (portfolioRisk > 0.6) factors.push('insufficient_diversification');
    if (positionRisk > 0.6) factors.push('high_position_volatility');
    if (concentrationRisk > 0.6) factors.push('position_concentration');
    if (correlationRisk > 0.6) factors.push('sector_correlation');
    
    return factors;
  }

  /**
   * Calculate stop loss and take profit levels
   * @param {Object} params - Stop loss calculation parameters
   * @returns {Object} Stop loss and take profit levels
   */
  async calculateStopLossTakeProfit(params) {
    const {
      symbol,
      entryPrice,
      direction, // 'long' or 'short'
      volatility,
      signal,
      riskPerTrade = 0.02
    } = params;

    try {
      const symbolVolatility = volatility || await this.getSymbolVolatility(symbol);
      
      // Calculate ATR-based stop loss
      const atrMultiplier = signal?.strength === 'strong' ? 1.5 : 2.0;
      const stopLossDistance = symbolVolatility * atrMultiplier;
      
      // Calculate stop loss levels
      const stopLoss = direction === 'long' ? 
        entryPrice * (1 - stopLossDistance) : 
        entryPrice * (1 + stopLossDistance);
      
      // Calculate take profit (risk-reward ratio)
      const riskRewardRatio = signal?.confidence > 0.8 ? 2.5 : 2.0;
      const takeProfitDistance = stopLossDistance * riskRewardRatio;
      
      const takeProfit = direction === 'long' ? 
        entryPrice * (1 + takeProfitDistance) : 
        entryPrice * (1 - takeProfitDistance);
      
      return {
        stopLoss: parseFloat(stopLoss.toFixed(4)),
        takeProfit: parseFloat(takeProfit.toFixed(4)),
        stopLossDistance: parseFloat(stopLossDistance.toFixed(4)),
        takeProfitDistance: parseFloat(takeProfitDistance.toFixed(4)),
        riskRewardRatio: riskRewardRatio,
        maxRiskAmount: entryPrice * riskPerTrade
      };
      
    } catch (error) {
      logger.error('❌ Stop loss/take profit calculation failed', {
        symbol: symbol,
        error: error.message
      });
      
      // Return conservative levels
      const defaultStop = direction === 'long' ? 
        entryPrice * 0.95 : 
        entryPrice * 1.05;
      
      const defaultTarget = direction === 'long' ? 
        entryPrice * 1.10 : 
        entryPrice * 0.90;
      
      return {
        stopLoss: parseFloat(defaultStop.toFixed(4)),
        takeProfit: parseFloat(defaultTarget.toFixed(4)),
        stopLossDistance: 0.05,
        takeProfitDistance: 0.10,
        riskRewardRatio: 2.0,
        maxRiskAmount: entryPrice * riskPerTrade
      };
    }
  }
}

module.exports = RiskManager;