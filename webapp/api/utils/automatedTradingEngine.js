const { query } = require('./database');
const { createLogger } = require('./structuredLogger');
const AdvancedSignalProcessor = require('./advancedSignalProcessor');
const PortfolioOptimizationEngine = require('./portfolioOptimizationEngine');

class AutomatedTradingEngine {
  constructor() {
    this.logger = createLogger('financial-platform', 'automated-trading');
    this.correlationId = this.generateCorrelationId();
    this.signalProcessor = new AdvancedSignalProcessor();
    this.portfolioOptimizer = new PortfolioOptimizationEngine();
    
    // Trading parameters
    this.config = {
      maxPositions: 20,
      maxPositionSize: 0.1, // 10% max per position
      riskTolerance: 0.05, // 5% portfolio risk
      rebalanceThreshold: 0.05, // 5% drift threshold
      stopLossThreshold: 0.08, // 8% stop loss
      takeProfitThreshold: 0.15, // 15% take profit
      minSignalStrength: 0.6, // Minimum signal confidence
      maxDailyTrades: 5
    };
    
    this.tradingState = {
      dailyTradeCount: 0,
      lastRebalance: null,
      activeOrders: new Map(),
      riskMetrics: {}
    };
  }

  generateCorrelationId() {
    return `auto-trade-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Execute automated trading strategy
   */
  async executeAutomatedStrategy(userId, preferences = {}) {
    const startTime = Date.now();
    
    try {
      this.logger.info('Starting automated trading execution', {
        userId,
        preferences,
        correlationId: this.correlationId
      });

      // Get current portfolio
      const currentPortfolio = await this.getCurrentPortfolio(userId);
      
      // Get market signals
      const marketSignals = await this.getMarketSignals(userId);
      
      // Analyze portfolio health
      const portfolioAnalysis = await this.analyzePortfolioHealth(currentPortfolio, userId);
      
      // Generate trading decisions
      const tradingDecisions = await this.generateTradingDecisions(
        currentPortfolio,
        marketSignals,
        portfolioAnalysis,
        preferences
      );
      
      // Execute risk management
      const riskManagedDecisions = await this.applyRiskManagement(
        tradingDecisions,
        currentPortfolio,
        userId
      );
      
      // Generate execution plan
      const executionPlan = await this.generateExecutionPlan(
        riskManagedDecisions,
        currentPortfolio,
        userId
      );
      
      // Update trading state
      this.updateTradingState(executionPlan);
      
      const processingTime = Date.now() - startTime;
      
      this.logger.info('Automated trading execution completed', {
        userId,
        decisionsGenerated: tradingDecisions.length,
        riskManagedDecisions: riskManagedDecisions.length,
        executionPlan: executionPlan.orders.length,
        processingTime,
        correlationId: this.correlationId
      });

      return {
        success: true,
        portfolio: currentPortfolio,
        signals: marketSignals,
        analysis: portfolioAnalysis,
        decisions: riskManagedDecisions,
        executionPlan: executionPlan,
        riskMetrics: this.tradingState.riskMetrics,
        metadata: {
          processingTime,
          correlationId: this.correlationId,
          timestamp: new Date().toISOString()
        }
      };

    } catch (error) {
      this.logger.error('Automated trading execution failed', {
        userId,
        error: error.message,
        correlationId: this.correlationId,
        processingTime: Date.now() - startTime
      });
      
      return this.createEmptyTradingResponse(error.message);
    }
  }

  /**
   * Get current portfolio holdings
   */
  async getCurrentPortfolio(userId) {
    const portfolioQuery = `
      SELECT 
        symbol,
        quantity,
        avg_cost,
        current_price,
        market_value,
        unrealized_pnl,
        created_at,
        updated_at
      FROM portfolio_holdings
      WHERE user_id = $1
        AND quantity > 0
      ORDER BY market_value DESC
    `;

    try {
      const result = await query(portfolioQuery, [userId]);
      return result.rows.map(row => ({
        ...row,
        quantity: parseFloat(row.quantity),
        avgCost: parseFloat(row.avg_cost),
        currentPrice: parseFloat(row.current_price),
        marketValue: parseFloat(row.market_value),
        unrealizedPnl: parseFloat(row.unrealized_pnl)
      }));
    } catch (error) {
      this.logger.error('Failed to fetch current portfolio', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return [];
    }
  }

  /**
   * Get market signals for watchlist and portfolio
   */
  async getMarketSignals(userId) {
    try {
      // Get watchlist symbols
      const watchlistQuery = `
        SELECT DISTINCT symbol 
        FROM watchlist 
        WHERE user_id = $1
        UNION
        SELECT DISTINCT symbol 
        FROM portfolio_holdings 
        WHERE user_id = $1 AND quantity > 0
      `;
      
      const watchlistResult = await query(watchlistQuery, [userId]);
      const symbols = watchlistResult.rows.map(row => row.symbol);
      
      // Generate signals for each symbol
      const signals = await Promise.all(
        symbols.map(async (symbol) => {
          try {
            const signalData = await this.signalProcessor.generateAdvancedSignals(symbol);
            return {
              symbol,
              ...signalData
            };
          } catch (error) {
            this.logger.warn('Failed to generate signal for symbol', {
              symbol,
              error: error.message,
              correlationId: this.correlationId
            });
            return null;
          }
        })
      );
      
      return signals.filter(signal => signal !== null);
    } catch (error) {
      this.logger.error('Failed to get market signals', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return [];
    }
  }

  /**
   * Analyze portfolio health and risk metrics
   */
  async analyzePortfolioHealth(portfolio, userId) {
    if (!portfolio || portfolio.length === 0) {
      return {
        health: 'empty',
        riskLevel: 'low',
        recommendations: ['Start building your portfolio with diversified positions']
      };
    }

    try {
      // Calculate portfolio metrics
      const totalValue = portfolio.reduce((sum, holding) => sum + holding.marketValue, 0);
      const totalUnrealizedPnl = portfolio.reduce((sum, holding) => sum + holding.unrealizedPnl, 0);
      const portfolioReturn = totalValue > 0 ? totalUnrealizedPnl / totalValue : 0;
      
      // Calculate concentration risk
      const concentrationRisk = this.calculateConcentrationRisk(portfolio);
      
      // Calculate sector concentration
      const sectorConcentration = await this.calculateSectorConcentration(portfolio);
      
      // Risk assessment
      const riskLevel = this.assessRiskLevel(concentrationRisk, sectorConcentration, portfolioReturn);
      
      // Generate recommendations
      const recommendations = this.generatePortfolioRecommendations(
        portfolio,
        concentrationRisk,
        sectorConcentration,
        riskLevel
      );

      return {
        health: riskLevel,
        totalValue,
        totalUnrealizedPnl,
        portfolioReturn,
        concentrationRisk,
        sectorConcentration,
        riskLevel,
        recommendations,
        needsRebalancing: this.needsRebalancing(portfolio),
        stopLossAlerts: this.checkStopLossAlerts(portfolio),
        takeProfitAlerts: this.checkTakeProfitAlerts(portfolio)
      };
    } catch (error) {
      this.logger.error('Failed to analyze portfolio health', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return {
        health: 'unknown',
        riskLevel: 'unknown',
        recommendations: ['Unable to analyze portfolio health']
      };
    }
  }

  /**
   * Generate trading decisions based on signals and portfolio analysis
   */
  async generateTradingDecisions(portfolio, signals, portfolioAnalysis, preferences) {
    const decisions = [];
    
    try {
      // Process buy signals
      const buySignals = signals.filter(signal => 
        signal.recommendation?.action === 'buy' && 
        signal.recommendation?.confidence >= this.config.minSignalStrength
      );
      
      for (const signal of buySignals) {
        const decision = await this.evaluateBuyDecision(signal, portfolio, portfolioAnalysis);
        if (decision) {
          decisions.push(decision);
        }
      }
      
      // Process sell signals
      const sellSignals = signals.filter(signal => 
        signal.recommendation?.action === 'sell' && 
        signal.recommendation?.confidence >= this.config.minSignalStrength
      );
      
      for (const signal of sellSignals) {
        const decision = await this.evaluateSellDecision(signal, portfolio, portfolioAnalysis);
        if (decision) {
          decisions.push(decision);
        }
      }
      
      // Process rebalancing needs
      if (portfolioAnalysis.needsRebalancing) {
        const rebalanceDecisions = await this.generateRebalancingDecisions(portfolio, signals);
        decisions.push(...rebalanceDecisions);
      }
      
      // Process stop loss alerts
      if (portfolioAnalysis.stopLossAlerts?.length > 0) {
        const stopLossDecisions = this.generateStopLossDecisions(portfolioAnalysis.stopLossAlerts);
        decisions.push(...stopLossDecisions);
      }
      
      // Process take profit alerts
      if (portfolioAnalysis.takeProfitAlerts?.length > 0) {
        const takeProfitDecisions = this.generateTakeProfitDecisions(portfolioAnalysis.takeProfitAlerts);
        decisions.push(...takeProfitDecisions);
      }
      
      return decisions.sort((a, b) => b.priority - a.priority);
    } catch (error) {
      this.logger.error('Failed to generate trading decisions', {
        error: error.message,
        correlationId: this.correlationId
      });
      return [];
    }
  }

  /**
   * Apply risk management rules to trading decisions
   */
  async applyRiskManagement(decisions, portfolio, userId) {
    const riskManagedDecisions = [];
    
    try {
      const totalPortfolioValue = portfolio.reduce((sum, holding) => sum + holding.marketValue, 0);
      let dailyRiskBudget = totalPortfolioValue * this.config.riskTolerance;
      
      for (const decision of decisions) {
        // Check daily trade limit
        if (this.tradingState.dailyTradeCount >= this.config.maxDailyTrades) {
          this.logger.warn('Daily trade limit reached', {
            userId,
            dailyTradeCount: this.tradingState.dailyTradeCount,
            correlationId: this.correlationId
          });
          break;
        }
        
        // Check position size limits
        if (decision.action === 'buy') {
          const positionValue = decision.quantity * decision.price;
          const positionPercent = positionValue / totalPortfolioValue;
          
          if (positionPercent > this.config.maxPositionSize) {
            // Reduce position size
            const adjustedQuantity = Math.floor(
              (this.config.maxPositionSize * totalPortfolioValue) / decision.price
            );
            
            decision.quantity = adjustedQuantity;
            decision.rationale += ' (Position size reduced for risk management)';
          }
        }
        
        // Check portfolio risk budget
        const decisionRisk = this.calculateDecisionRisk(decision, portfolio);
        if (decisionRisk <= dailyRiskBudget) {
          riskManagedDecisions.push(decision);
          dailyRiskBudget -= decisionRisk;
        } else {
          this.logger.warn('Decision exceeds risk budget', {
            userId,
            symbol: decision.symbol,
            decisionRisk,
            remainingBudget: dailyRiskBudget,
            correlationId: this.correlationId
          });
        }
      }
      
      return riskManagedDecisions;
    } catch (error) {
      this.logger.error('Failed to apply risk management', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return decisions; // Return original decisions if risk management fails
    }
  }

  /**
   * Generate execution plan for approved trading decisions
   */
  async generateExecutionPlan(decisions, portfolio, userId) {
    const orders = [];
    const portfolioChanges = [];
    
    try {
      for (const decision of decisions) {
        const order = {
          symbol: decision.symbol,
          action: decision.action,
          quantity: decision.quantity,
          orderType: decision.orderType || 'market',
          price: decision.price,
          stopLoss: decision.stopLoss,
          takeProfit: decision.takeProfit,
          rationale: decision.rationale,
          confidence: decision.confidence,
          priority: decision.priority,
          correlationId: this.correlationId,
          timestamp: new Date().toISOString()
        };
        
        orders.push(order);
        
        // Calculate portfolio impact
        const portfolioChange = this.calculatePortfolioChange(decision, portfolio);
        portfolioChanges.push(portfolioChange);
      }
      
      return {
        orders,
        portfolioChanges,
        summary: {
          totalOrders: orders.length,
          buyOrders: orders.filter(o => o.action === 'buy').length,
          sellOrders: orders.filter(o => o.action === 'sell').length,
          estimatedValue: orders.reduce((sum, o) => sum + (o.quantity * o.price), 0),
          expectedRiskReduction: this.calculateExpectedRiskReduction(portfolioChanges),
          expectedReturn: this.calculateExpectedReturn(portfolioChanges)
        }
      };
    } catch (error) {
      this.logger.error('Failed to generate execution plan', {
        userId,
        error: error.message,
        correlationId: this.correlationId
      });
      return {
        orders: [],
        portfolioChanges: [],
        summary: { totalOrders: 0 }
      };
    }
  }

  // Helper methods (simplified implementations)
  calculateConcentrationRisk(portfolio) {
    const totalValue = portfolio.reduce((sum, holding) => sum + holding.marketValue, 0);
    const weights = portfolio.map(holding => holding.marketValue / totalValue);
    return weights.reduce((sum, w) => sum + w * w, 0); // Herfindahl index
  }

  async calculateSectorConcentration(portfolio) {
    // Simplified sector concentration calculation
    const sectors = {};
    const totalValue = portfolio.reduce((sum, holding) => sum + holding.marketValue, 0);
    
    for (const holding of portfolio) {
      const sector = 'Technology'; // Simplified - would lookup actual sector
      if (!sectors[sector]) sectors[sector] = 0;
      sectors[sector] += holding.marketValue / totalValue;
    }
    
    return sectors;
  }

  assessRiskLevel(concentrationRisk, sectorConcentration, portfolioReturn) {
    if (concentrationRisk > 0.4) return 'high';
    if (concentrationRisk > 0.2) return 'medium';
    return 'low';
  }

  generatePortfolioRecommendations(portfolio, concentrationRisk, sectorConcentration, riskLevel) {
    const recommendations = [];
    
    if (concentrationRisk > 0.3) {
      recommendations.push('Consider diversifying - portfolio is highly concentrated');
    }
    
    if (riskLevel === 'high') {
      recommendations.push('Reduce position sizes in largest holdings');
    }
    
    return recommendations;
  }

  needsRebalancing(portfolio) {
    // Simplified rebalancing check
    return Math.random() > 0.7; // 30% chance needs rebalancing
  }

  checkStopLossAlerts(portfolio) {
    return portfolio.filter(holding => {
      const loss = (holding.currentPrice - holding.avgCost) / holding.avgCost;
      return loss < -this.config.stopLossThreshold;
    });
  }

  checkTakeProfitAlerts(portfolio) {
    return portfolio.filter(holding => {
      const gain = (holding.currentPrice - holding.avgCost) / holding.avgCost;
      return gain > this.config.takeProfitThreshold;
    });
  }

  async evaluateBuyDecision(signal, portfolio, portfolioAnalysis) {
    // Check if we already have a position
    const existingPosition = portfolio.find(p => p.symbol === signal.symbol);
    if (existingPosition && existingPosition.quantity > 0) {
      return null; // Skip if already have position
    }
    
    return {
      symbol: signal.symbol,
      action: 'buy',
      quantity: 100, // Simplified quantity calculation
      price: signal.currentPrice,
      orderType: 'market',
      rationale: signal.recommendation.rationale,
      confidence: signal.recommendation.confidence,
      priority: signal.recommendation.confidence * 100,
      stopLoss: signal.currentPrice * (1 - this.config.stopLossThreshold),
      takeProfit: signal.currentPrice * (1 + this.config.takeProfitThreshold)
    };
  }

  async evaluateSellDecision(signal, portfolio, portfolioAnalysis) {
    // Check if we have a position to sell
    const existingPosition = portfolio.find(p => p.symbol === signal.symbol);
    if (!existingPosition || existingPosition.quantity <= 0) {
      return null; // Skip if no position
    }
    
    return {
      symbol: signal.symbol,
      action: 'sell',
      quantity: existingPosition.quantity,
      price: signal.currentPrice,
      orderType: 'market',
      rationale: signal.recommendation.rationale,
      confidence: signal.recommendation.confidence,
      priority: signal.recommendation.confidence * 100
    };
  }

  async generateRebalancingDecisions(portfolio, signals) {
    // Simplified rebalancing logic
    return [];
  }

  generateStopLossDecisions(stopLossAlerts) {
    return stopLossAlerts.map(holding => ({
      symbol: holding.symbol,
      action: 'sell',
      quantity: holding.quantity,
      price: holding.currentPrice,
      orderType: 'market',
      rationale: 'Stop loss triggered',
      confidence: 0.9,
      priority: 95
    }));
  }

  generateTakeProfitDecisions(takeProfitAlerts) {
    return takeProfitAlerts.map(holding => ({
      symbol: holding.symbol,
      action: 'sell',
      quantity: Math.floor(holding.quantity * 0.5), // Sell half
      price: holding.currentPrice,
      orderType: 'market',
      rationale: 'Take profit triggered',
      confidence: 0.8,
      priority: 80
    }));
  }

  calculateDecisionRisk(decision, portfolio) {
    const positionValue = decision.quantity * decision.price;
    return positionValue * 0.1; // Simplified risk calculation
  }

  calculatePortfolioChange(decision, portfolio) {
    return {
      symbol: decision.symbol,
      action: decision.action,
      quantity: decision.quantity,
      value: decision.quantity * decision.price,
      impact: decision.action === 'buy' ? 'increase' : 'decrease'
    };
  }

  calculateExpectedRiskReduction(portfolioChanges) {
    return Math.random() * 0.1; // Simplified
  }

  calculateExpectedReturn(portfolioChanges) {
    return Math.random() * 0.05 + 0.02; // Simplified
  }

  updateTradingState(executionPlan) {
    this.tradingState.dailyTradeCount += executionPlan.orders.length;
    this.tradingState.lastRebalance = new Date();
  }

  createEmptyTradingResponse(message) {
    return {
      success: false,
      message,
      portfolio: [],
      signals: [],
      analysis: null,
      decisions: [],
      executionPlan: { orders: [], portfolioChanges: [], summary: { totalOrders: 0 } },
      riskMetrics: {},
      metadata: {
        correlationId: this.correlationId,
        timestamp: new Date().toISOString()
      }
    };
  }
}

module.exports = AutomatedTradingEngine;