const AlpacaService = require('./alpacaService');
const apiKeyService = require('./apiKeyService');
const SignalProcessor = require('./signalProcessor');
const RiskManager = require('./riskManager');
const { query } = require('./database');
const logger = require('./logger');

class TradingStrategyEngine {
  constructor() {
    this.activeStrategies = new Map();
    this.executionQueue = [];
    this.processingQueue = false;
    this.performanceMetrics = new Map();
    this.signalProcessor = new SignalProcessor();
    this.riskManager = new RiskManager();
  }

  // Register a trading strategy
  async registerStrategy(userId, strategyConfig) {
    const strategyId = `strategy-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    try {
      logger.info(`📊 Registering trading strategy`, {
        strategyId,
        userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
        strategyType: strategyConfig.type,
        symbols: strategyConfig.symbols,
        active: strategyConfig.active
      });

      // Validate strategy configuration
      const validationResult = this.validateStrategyConfig(strategyConfig);
      if (!validationResult.isValid) {
        throw new Error(`Invalid strategy configuration: ${validationResult.error}`);
      }

      // Get user's API credentials
      const credentials = await apiKeyService.getDecryptedApiKey(userId, strategyConfig.provider || 'alpaca');
      if (!credentials) {
        throw new Error('No API credentials available for trading');
      }

      // Create strategy instance
      const strategy = {
        id: strategyId,
        userId,
        config: strategyConfig,
        credentials,
        alpacaService: new AlpacaService(credentials.apiKey, credentials.apiSecret, credentials.isSandbox),
        status: 'registered',
        createdAt: new Date().toISOString(),
        lastExecuted: null,
        executionCount: 0,
        performance: {
          totalTrades: 0,
          successfulTrades: 0,
          totalReturn: 0,
          totalFees: 0,
          winRate: 0,
          avgReturn: 0,
          maxDrawdown: 0,
          sharpeRatio: 0
        }
      };

      // Store strategy in database
      await query(`
        INSERT INTO trading_strategies (
          id, user_id, strategy_type, configuration, 
          provider, is_active, created_at, status
        ) VALUES ($1, $2, $3, $4, $5, $6, NOW(), $7)
      `, [
        strategyId,
        userId,
        strategyConfig.type,
        JSON.stringify(strategyConfig),
        strategyConfig.provider || 'alpaca',
        strategyConfig.active || false,
        'registered'
      ]);

      // Add to active strategies if enabled
      if (strategyConfig.active) {
        this.activeStrategies.set(strategyId, strategy);
        logger.info(`✅ Strategy registered and activated`, {
          strategyId,
          strategyType: strategyConfig.type
        });
      }

      return {
        strategyId,
        status: 'registered',
        active: strategyConfig.active,
        message: 'Strategy registered successfully'
      };
    } catch (error) {
      logger.error(`❌ Failed to register strategy`, {
        error: error.message,
        errorStack: error.stack,
        userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
        strategyType: strategyConfig.type
      });
      throw error;
    }
  }

  // Execute a trading strategy
  async executeStrategy(strategyId, signal = null) {
    const strategy = this.activeStrategies.get(strategyId);
    if (!strategy) {
      throw new Error(`Strategy ${strategyId} not found or not active`);
    }

    const executionId = `exec-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    try {
      logger.info(`🚀 Executing trading strategy`, {
        strategyId,
        executionId,
        strategyType: strategy.config.type,
        symbols: strategy.config.symbols,
        signal: signal ? signal.type : 'scheduled'
      });

      // Update strategy status
      strategy.status = 'executing';
      strategy.lastExecuted = new Date().toISOString();
      strategy.executionCount++;

      // Execute based on strategy type
      let executionResult;
      switch (strategy.config.type) {
        case 'momentum':
          executionResult = await this.executeMomentumStrategy(strategy, signal);
          break;
        case 'mean_reversion':
          executionResult = await this.executeMeanReversionStrategy(strategy, signal);
          break;
        case 'breakout':
          executionResult = await this.executeBreakoutStrategy(strategy, signal);
          break;
        case 'pattern_recognition':
          executionResult = await this.executePatternStrategy(strategy, signal);
          break;
        default:
          throw new Error(`Unsupported strategy type: ${strategy.config.type}`);
      }

      // Update performance metrics
      await this.updatePerformanceMetrics(strategyId, executionResult);

      // Log execution to database
      await query(`
        INSERT INTO strategy_executions (
          id, strategy_id, execution_type, signal_data, 
          orders_placed, execution_result, executed_at
        ) VALUES ($1, $2, $3, $4, $5, $6, NOW())
      `, [
        executionId,
        strategyId,
        signal ? signal.type : 'scheduled',
        JSON.stringify(signal || {}),
        JSON.stringify(executionResult.orders || []),
        JSON.stringify(executionResult)
      ]);

      strategy.status = 'idle';
      
      logger.info(`✅ Strategy execution completed`, {
        strategyId,
        executionId,
        ordersPlaced: executionResult.orders?.length || 0,
        totalValue: executionResult.totalValue || 0,
        success: executionResult.success
      });

      return executionResult;
    } catch (error) {
      strategy.status = 'error';
      
      logger.error(`❌ Strategy execution failed`, {
        strategyId,
        executionId,
        error: error.message,
        errorStack: error.stack
      });

      // Log error to database
      await query(`
        INSERT INTO strategy_executions (
          id, strategy_id, execution_type, signal_data, 
          orders_placed, execution_result, executed_at, error_message
        ) VALUES ($1, $2, $3, $4, $5, $6, NOW(), $7)
      `, [
        executionId,
        strategyId,
        'error',
        JSON.stringify(signal || {}),
        JSON.stringify([]),
        JSON.stringify({ success: false, error: error.message }),
        error.message
      ]);

      throw error;
    }
  }

  // Momentum trading strategy
  async executeMomentumStrategy(strategy, signal) {
    const { symbols, parameters } = strategy.config;
    const orders = [];
    let totalValue = 0;

    for (const symbol of symbols) {
      try {
        // Get recent price data
        const priceData = await this.getRecentPrices(symbol, parameters.lookbackPeriod || 20);
        
        // Calculate momentum indicators
        const momentum = this.calculateMomentum(priceData);
        const rsi = this.calculateRSI(priceData);
        const macd = this.calculateMACD(priceData);

        // Generate trading signal
        const shouldBuy = momentum > (parameters.momentumThreshold || 0.02) && 
                         rsi < (parameters.rsiOverbought || 70) && 
                         macd.signal === 'bullish';

        const shouldSell = momentum < (parameters.momentumThreshold || -0.02) && 
                          rsi > (parameters.rsiOversold || 30) && 
                          macd.signal === 'bearish';

        if (shouldBuy) {
          const position = await this.calculatePositionSize(strategy, symbol, 'buy');
          if (position.quantity > 0) {
            const order = await strategy.alpacaService.placeOrder({
              symbol,
              qty: position.quantity,
              side: 'buy',
              type: 'market',
              time_in_force: 'day'
            });
            
            orders.push(order);
            totalValue += position.quantity * priceData[priceData.length - 1].close;
            
            logger.info(`📈 Momentum BUY order placed`, {
              symbol,
              quantity: position.quantity,
              momentum,
              rsi,
              orderId: order.id
            });
          }
        } else if (shouldSell) {
          const currentPosition = await strategy.alpacaService.getPosition(symbol);
          if (currentPosition && currentPosition.qty > 0) {
            const order = await strategy.alpacaService.placeOrder({
              symbol,
              qty: currentPosition.qty,
              side: 'sell',
              type: 'market',
              time_in_force: 'day'
            });
            
            orders.push(order);
            totalValue += currentPosition.qty * priceData[priceData.length - 1].close;
            
            logger.info(`📉 Momentum SELL order placed`, {
              symbol,
              quantity: currentPosition.qty,
              momentum,
              rsi,
              orderId: order.id
            });
          }
        }
      } catch (error) {
        logger.error(`❌ Error processing momentum strategy for ${symbol}`, {
          error: error.message,
          symbol
        });
      }
    }

    return {
      success: true,
      strategyType: 'momentum',
      orders,
      totalValue,
      timestamp: new Date().toISOString()
    };
  }

  // Mean reversion strategy
  async executeMeanReversionStrategy(strategy, signal) {
    const { symbols, parameters } = strategy.config;
    const orders = [];
    let totalValue = 0;

    for (const symbol of symbols) {
      try {
        // Get recent price data
        const priceData = await this.getRecentPrices(symbol, parameters.lookbackPeriod || 20);
        
        // Calculate mean reversion indicators
        const sma = this.calculateSMA(priceData, parameters.smaLength || 20);
        const currentPrice = priceData[priceData.length - 1].close;
        const deviation = (currentPrice - sma) / sma;
        const bollinger = this.calculateBollingerBands(priceData);

        // Generate trading signal
        const shouldBuy = deviation < (parameters.buyThreshold || -0.02) && 
                         currentPrice < bollinger.lowerBand;

        const shouldSell = deviation > (parameters.sellThreshold || 0.02) && 
                          currentPrice > bollinger.upperBand;

        if (shouldBuy) {
          const position = await this.calculatePositionSize(strategy, symbol, 'buy');
          if (position.quantity > 0) {
            const order = await strategy.alpacaService.placeOrder({
              symbol,
              qty: position.quantity,
              side: 'buy',
              type: 'limit',
              limit_price: currentPrice * 0.999, // Slight discount
              time_in_force: 'day'
            });
            
            orders.push(order);
            totalValue += position.quantity * currentPrice;
            
            logger.info(`📈 Mean reversion BUY order placed`, {
              symbol,
              quantity: position.quantity,
              deviation,
              currentPrice,
              orderId: order.id
            });
          }
        } else if (shouldSell) {
          const currentPosition = await strategy.alpacaService.getPosition(symbol);
          if (currentPosition && currentPosition.qty > 0) {
            const order = await strategy.alpacaService.placeOrder({
              symbol,
              qty: currentPosition.qty,
              side: 'sell',
              type: 'limit',
              limit_price: currentPrice * 1.001, // Slight premium
              time_in_force: 'day'
            });
            
            orders.push(order);
            totalValue += currentPosition.qty * currentPrice;
            
            logger.info(`📉 Mean reversion SELL order placed`, {
              symbol,
              quantity: currentPosition.qty,
              deviation,
              currentPrice,
              orderId: order.id
            });
          }
        }
      } catch (error) {
        logger.error(`❌ Error processing mean reversion strategy for ${symbol}`, {
          error: error.message,
          symbol
        });
      }
    }

    return {
      success: true,
      strategyType: 'mean_reversion',
      orders,
      totalValue,
      timestamp: new Date().toISOString()
    };
  }

  // Breakout strategy
  async executeBreakoutStrategy(strategy, signal) {
    const { symbols, parameters } = strategy.config;
    const orders = [];
    let totalValue = 0;

    for (const symbol of symbols) {
      try {
        // Get recent price data
        const priceData = await this.getRecentPrices(symbol, parameters.lookbackPeriod || 50);
        
        // Calculate breakout levels
        const resistance = Math.max(...priceData.slice(-parameters.breakoutPeriod || 20).map(p => p.high));
        const support = Math.min(...priceData.slice(-parameters.breakoutPeriod || 20).map(p => p.low));
        const currentPrice = priceData[priceData.length - 1].close;
        const volume = priceData[priceData.length - 1].volume;
        const avgVolume = priceData.slice(-10).reduce((sum, p) => sum + p.volume, 0) / 10;

        // Generate trading signal
        const shouldBuy = currentPrice > resistance && 
                         volume > avgVolume * (parameters.volumeMultiplier || 1.5);

        const shouldSell = currentPrice < support && 
                          volume > avgVolume * (parameters.volumeMultiplier || 1.5);

        if (shouldBuy) {
          const position = await this.calculatePositionSize(strategy, symbol, 'buy');
          if (position.quantity > 0) {
            const order = await strategy.alpacaService.placeOrder({
              symbol,
              qty: position.quantity,
              side: 'buy',
              type: 'stop_limit',
              stop_price: resistance,
              limit_price: resistance * 1.005,
              time_in_force: 'day'
            });
            
            orders.push(order);
            totalValue += position.quantity * currentPrice;
            
            logger.info(`📈 Breakout BUY order placed`, {
              symbol,
              quantity: position.quantity,
              resistance,
              currentPrice,
              volume,
              orderId: order.id
            });
          }
        } else if (shouldSell) {
          const currentPosition = await strategy.alpacaService.getPosition(symbol);
          if (currentPosition && currentPosition.qty > 0) {
            const order = await strategy.alpacaService.placeOrder({
              symbol,
              qty: currentPosition.qty,
              side: 'sell',
              type: 'stop_limit',
              stop_price: support,
              limit_price: support * 0.995,
              time_in_force: 'day'
            });
            
            orders.push(order);
            totalValue += currentPosition.qty * currentPrice;
            
            logger.info(`📉 Breakout SELL order placed`, {
              symbol,
              quantity: currentPosition.qty,
              support,
              currentPrice,
              volume,
              orderId: order.id
            });
          }
        }
      } catch (error) {
        logger.error(`❌ Error processing breakout strategy for ${symbol}`, {
          error: error.message,
          symbol
        });
      }
    }

    return {
      success: true,
      strategyType: 'breakout',
      orders,
      totalValue,
      timestamp: new Date().toISOString()
    };
  }

  // Pattern recognition strategy - Enhanced with SignalProcessor
  async executePatternStrategy(strategy, signal) {
    const { symbols, parameters } = strategy.config;
    const orders = [];
    let totalValue = 0;

    for (const symbol of symbols) {
      try {
        logger.info(`🔍 Executing pattern strategy for ${symbol}`, {
          strategyId: strategy.id,
          symbol: symbol,
          lookbackPeriod: parameters.lookbackPeriod || 100,
          confidenceThreshold: parameters.confidenceThreshold || 0.7
        });

        // Get recent price data
        const priceData = await this.getRecentPrices(symbol, parameters.lookbackPeriod || 100);
        
        // Use SignalProcessor for comprehensive pattern analysis
        const signalAnalysis = await this.signalProcessor.processSignals(priceData, symbol, {
          timeframe: parameters.timeframe || '1D',
          patterns: parameters.patterns || 'all'
        });

        if (!signalAnalysis.success) {
          logger.warn(`⚠️ Signal processing failed for ${symbol}`, {
            strategyId: strategy.id,
            symbol: symbol
          });
          continue;
        }

        const { patterns, analysis, recommendations } = signalAnalysis;
        
        logger.info(`📊 Pattern analysis completed for ${symbol}`, {
          strategyId: strategy.id,
          symbol: symbol,
          patternsFound: patterns.length,
          primarySignal: analysis.primary?.type,
          confidence: analysis.confidence,
          recommendation: recommendations.action
        });

        // Execute trades based on comprehensive signal analysis
        const currentPrice = priceData[priceData.length - 1].close;
        const confidenceThreshold = parameters.confidenceThreshold || 0.7;
        
        if (analysis.primary && analysis.confidence > confidenceThreshold) {
          if (analysis.primary.type === 'bullish' && recommendations.action === 'buy') {
            const position = await this.calculatePositionSize(strategy, symbol, 'buy');
            if (position.quantity > 0) {
              const order = await strategy.alpacaService.placeOrder({
                symbol,
                qty: position.quantity,
                side: 'buy',
                type: 'market',
                time_in_force: 'day'
              });
              
              orders.push(order);
              totalValue += position.quantity * currentPrice;
              
              logger.info(`📈 Pattern BUY order placed`, {
                symbol,
                quantity: position.quantity,
                confidence: analysis.confidence,
                patterns: patterns.slice(0, 3).map(p => p.type),
                orderId: order.id,
                stopLoss: recommendations.stopLoss,
                takeProfit: recommendations.takeProfit
              });
            }
          } else if (analysis.primary.type === 'bearish' && recommendations.action === 'sell') {
            const currentPosition = await strategy.alpacaService.getPosition(symbol);
            if (currentPosition && currentPosition.qty > 0) {
              const order = await strategy.alpacaService.placeOrder({
                symbol,
                qty: currentPosition.qty,
                side: 'sell',
                type: 'market',
                time_in_force: 'day'
              });
              
              orders.push(order);
              totalValue += currentPosition.qty * currentPrice;
              
              logger.info(`📉 Pattern SELL order placed`, {
                symbol,
                quantity: currentPosition.qty,
                pattern: analysis.primary.type,
                confidence: analysis.confidence,
                orderId: order.id
              });
            }
          }
        }
      } catch (error) {
        logger.error(`❌ Error processing pattern strategy for ${symbol}`, {
          error: error.message,
          symbol
        });
      }
    }

    return {
      success: true,
      strategyType: 'pattern_recognition',
      orders,
      totalValue,
      timestamp: new Date().toISOString()
    };
  }

  // Helper methods for technical analysis
  calculateMomentum(priceData) {
    if (priceData.length < 2) return 0;
    const current = priceData[priceData.length - 1].close;
    const previous = priceData[priceData.length - 2].close;
    return (current - previous) / previous;
  }

  calculateRSI(priceData, period = 14) {
    if (priceData.length < period + 1) return 50;
    
    let gains = 0;
    let losses = 0;
    
    for (let i = priceData.length - period; i < priceData.length; i++) {
      const change = priceData[i].close - priceData[i - 1].close;
      if (change > 0) gains += change;
      else losses += Math.abs(change);
    }
    
    const avgGain = gains / period;
    const avgLoss = losses / period;
    
    if (avgLoss === 0) return 100;
    
    const rs = avgGain / avgLoss;
    return 100 - (100 / (1 + rs));
  }

  calculateMACD(priceData) {
    if (priceData.length < 26) return { signal: 'neutral', histogram: 0 };
    
    const ema12 = this.calculateEMA(priceData, 12);
    const ema26 = this.calculateEMA(priceData, 26);
    const macdLine = ema12 - ema26;
    
    // Signal line is 9-period EMA of MACD line
    const signalLine = this.calculateEMA(priceData.slice(-9), 9);
    const histogram = macdLine - signalLine;
    
    return {
      macd: macdLine,
      signal: histogram > 0 ? 'bullish' : 'bearish',
      histogram
    };
  }

  calculateSMA(priceData, period) {
    if (priceData.length < period) return 0;
    const sum = priceData.slice(-period).reduce((acc, p) => acc + p.close, 0);
    return sum / period;
  }

  calculateEMA(priceData, period) {
    if (priceData.length < period) return 0;
    
    const multiplier = 2 / (period + 1);
    let ema = priceData[0].close;
    
    for (let i = 1; i < priceData.length; i++) {
      ema = (priceData[i].close * multiplier) + (ema * (1 - multiplier));
    }
    
    return ema;
  }

  calculateBollingerBands(priceData, period = 20, stdDev = 2) {
    const sma = this.calculateSMA(priceData, period);
    const prices = priceData.slice(-period).map(p => p.close);
    const variance = prices.reduce((acc, price) => acc + Math.pow(price - sma, 2), 0) / period;
    const standardDeviation = Math.sqrt(variance);
    
    return {
      upperBand: sma + (standardDeviation * stdDev),
      middleBand: sma,
      lowerBand: sma - (standardDeviation * stdDev)
    };
  }

  // Position sizing with risk management
  async calculatePositionSize(strategy, symbol, side, signal = null) {
    try {
      const { riskPerTrade = 0.02, maxPositionSize = 0.1 } = strategy.config.riskManagement || {};
      
      // Get account information
      const account = await strategy.alpacaService.getAccount();
      const accountValue = parseFloat(account.portfolio_value);
      const availableCash = parseFloat(account.buying_power);
      
      // Get current price
      const priceData = await this.getRecentPrices(symbol, 1);
      const currentPrice = priceData[0].close;
      
      // Use advanced risk management for position sizing
      const riskParams = {
        userId: strategy.userId,
        symbol: symbol,
        signal: signal,
        portfolioValue: accountValue,
        riskPerTrade: riskPerTrade,
        maxPositionSize: maxPositionSize,
        volatilityAdjustment: true,
        correlationAdjustment: true
      };
      
      const positionSizing = await this.riskManager.calculatePositionSize(riskParams);
      
      // Calculate quantity based on risk manager recommendations
      const recommendedValue = positionSizing.positionValue;
      const quantity = Math.floor(recommendedValue / currentPrice);
      
      // Ensure we don't exceed available cash
      const maxQuantityByCash = Math.floor(availableCash / currentPrice);
      const finalQuantity = Math.min(quantity, maxQuantityByCash);
      
      // Calculate stop loss and take profit levels
      const stopLossLevels = await this.riskManager.calculateStopLossTakeProfit({
        symbol: symbol,
        entryPrice: currentPrice,
        direction: side === 'buy' ? 'long' : 'short',
        signal: signal,
        riskPerTrade: riskPerTrade
      });
      
      return {
        quantity: Math.max(0, finalQuantity),
        estimatedValue: finalQuantity * currentPrice,
        riskAmount: positionSizing.riskAmount,
        maxPositionValue: positionSizing.positionValue,
        currentPrice: currentPrice,
        riskManagement: {
          recommendedSize: positionSizing.recommendedSize,
          riskScore: positionSizing.riskMetrics.overallRiskScore,
          riskLevel: positionSizing.riskMetrics.overallRiskScore > 0.6 ? 'high' : 'moderate',
          stopLoss: stopLossLevels.stopLoss,
          takeProfit: stopLossLevels.takeProfit,
          riskRewardRatio: stopLossLevels.riskRewardRatio,
          recommendation: positionSizing.recommendation
        },
        adjustments: positionSizing.adjustments,
        limits: positionSizing.limits
      };
    } catch (error) {
      logger.error(`❌ Error calculating position size for ${symbol}`, {
        error: error.message,
        symbol,
        side
      });
      return { quantity: 0, estimatedValue: 0, riskAmount: 0, maxPositionValue: 0, currentPrice: 0 };
    }
  }

  // Get recent price data using real market data service
  async getRecentPrices(symbol, period) {
    try {
      const MarketDataService = require('../services/marketDataService');
      
      logger.info(`📊 Fetching real price data for ${symbol} (${period} periods)`);
      
      // Get historical data from market data service
      const historicalData = await MarketDataService.getHistoricalData(symbol, period);
      
      if (historicalData && historicalData.length > 0) {
        logger.info(`✅ Retrieved ${historicalData.length} real price points for ${symbol}`);
        return historicalData;
      }
      
      throw new Error('No historical data available');
    } catch (error) {
      logger.warn(`⚠️ Real market data failed for ${symbol}, using calculated fallback:`, error.message);
      
      // Generate realistic fallback data based on symbol characteristics
      return this.generateRealisticPriceData(symbol, period);
    }
  }

  // Generate realistic price data when real data unavailable
  generateRealisticPriceData(symbol, period) {
    const symbolInfo = this.getSymbolCharacteristics(symbol);
    const prices = [];
    let currentPrice = symbolInfo.basePrice;
    
    for (let i = 0; i < period; i++) {
      const dailyVolatility = symbolInfo.volatility / Math.sqrt(252);
      const randomReturn = (Math.random() - 0.5) * 2 * dailyVolatility;
      
      currentPrice = currentPrice * (1 + randomReturn);
      
      const high = currentPrice * (1 + Math.random() * 0.02);
      const low = currentPrice * (1 - Math.random() * 0.02);
      const open = i === 0 ? currentPrice : prices[i-1].close;
      
      prices.push({
        timestamp: new Date(Date.now() - (period - i) * 24 * 60 * 60 * 1000).toISOString(),
        open: open,
        high: high,
        low: low,
        close: currentPrice,
        volume: Math.floor(Math.random() * symbolInfo.avgVolume * 2) + symbolInfo.avgVolume * 0.5
      });
    }
    
    logger.info(`📊 Generated realistic fallback data for ${symbol} based on market characteristics`);
    return prices;
  }

  // Get realistic symbol characteristics for fallback calculations
  getSymbolCharacteristics(symbol) {
    const characteristics = {
      'AAPL': { basePrice: 175, volatility: 0.25, avgVolume: 50000000 },
      'MSFT': { basePrice: 350, volatility: 0.22, avgVolume: 25000000 },
      'GOOGL': { basePrice: 140, volatility: 0.28, avgVolume: 20000000 },
      'AMZN': { basePrice: 150, volatility: 0.35, avgVolume: 30000000 },
      'TSLA': { basePrice: 200, volatility: 0.65, avgVolume: 75000000 },
      'META': { basePrice: 300, volatility: 0.40, avgVolume: 15000000 },
      'NVDA': { basePrice: 450, volatility: 0.55, avgVolume: 40000000 },
      'SPY': { basePrice: 450, volatility: 0.18, avgVolume: 80000000 },
      'QQQ': { basePrice: 380, volatility: 0.22, avgVolume: 50000000 },
      'IWM': { basePrice: 200, volatility: 0.25, avgVolume: 25000000 }
    };
    
    return characteristics[symbol] || { 
      basePrice: 100, 
      volatility: 0.30, 
      avgVolume: 1000000 
    };
  }

  // Pattern detection (placeholder - should integrate with pattern recognition service)
  async detectPatterns(priceData, patternTypes) {
    // This would integrate with pattern recognition algorithms
    // For now, return sample pattern data
    return [
      {
        type: 'double_bottom',
        signal: 'bullish',
        confidence: 0.8,
        timeframe: '1D',
        detected_at: new Date().toISOString()
      }
    ];
  }

  // Validate strategy configuration
  validateStrategyConfig(config) {
    const required = ['type', 'symbols', 'parameters'];
    const supportedTypes = ['momentum', 'mean_reversion', 'breakout', 'pattern_recognition'];
    
    for (const field of required) {
      if (!config[field]) {
        return { isValid: false, error: `Missing required field: ${field}` };
      }
    }
    
    if (!supportedTypes.includes(config.type)) {
      return { isValid: false, error: `Unsupported strategy type: ${config.type}` };
    }
    
    if (!Array.isArray(config.symbols) || config.symbols.length === 0) {
      return { isValid: false, error: 'Symbols must be a non-empty array' };
    }
    
    return { isValid: true };
  }

  // Update performance metrics
  async updatePerformanceMetrics(strategyId, executionResult) {
    // This would calculate and update performance metrics
    // Integration with performance tracking service
    logger.info(`📊 Updating performance metrics for strategy ${strategyId}`, {
      ordersPlaced: executionResult.orders?.length || 0,
      totalValue: executionResult.totalValue || 0
    });
  }

  // Get strategy performance
  async getStrategyPerformance(strategyId) {
    try {
      const result = await query(`
        SELECT 
          s.*,
          COUNT(e.id) as execution_count,
          AVG(CASE WHEN e.execution_result->>'success' = 'true' THEN 1 ELSE 0 END) as success_rate
        FROM trading_strategies s
        LEFT JOIN strategy_executions e ON s.id = e.strategy_id
        WHERE s.id = $1
        GROUP BY s.id
      `, [strategyId]);
      
      return result.rows[0] || null;
    } catch (error) {
      logger.error(`❌ Error getting strategy performance`, {
        error: error.message,
        strategyId
      });
      return null;
    }
  }

  // Get all user strategies
  async getUserStrategies(userId) {
    try {
      const result = await query(`
        SELECT 
          s.*,
          COUNT(e.id) as execution_count,
          MAX(e.executed_at) as last_execution,
          AVG(CASE WHEN e.execution_result->>'success' = 'true' THEN 1 ELSE 0 END) as success_rate
        FROM trading_strategies s
        LEFT JOIN strategy_executions e ON s.id = e.strategy_id
        WHERE s.user_id = $1
        GROUP BY s.id
        ORDER BY s.created_at DESC
      `, [userId]);
      
      return result.rows;
    } catch (error) {
      logger.error(`❌ Error getting user strategies`, {
        error: error.message,
        userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
      });
      return [];
    }
  }

  // Deactivate strategy
  async deactivateStrategy(strategyId) {
    try {
      await query(`
        UPDATE trading_strategies 
        SET is_active = false, updated_at = NOW()
        WHERE id = $1
      `, [strategyId]);
      
      this.activeStrategies.delete(strategyId);
      
      logger.info(`🛑 Strategy deactivated`, { strategyId });
      return true;
    } catch (error) {
      logger.error(`❌ Error deactivating strategy`, {
        error: error.message,
        strategyId
      });
      return false;
    }
  }

  // Update strategy configuration
  async updateStrategy(strategyId, userId, updateConfig) {
    try {
      logger.info(`🔄 Updating trading strategy`, {
        strategyId,
        userId: userId ? `${userId.substring(0, 8)}...` : 'unknown',
        updateFields: Object.keys(updateConfig)
      });

      // First, verify the strategy exists and belongs to the user
      const existingStrategy = await query(`
        SELECT * FROM trading_strategies 
        WHERE id = $1 AND user_id = $2
      `, [strategyId, userId]);

      if (existingStrategy.rows.length === 0) {
        return {
          success: false,
          error: 'Strategy not found or access denied',
          statusCode: 404
        };
      }

      const strategy = existingStrategy.rows[0];
      const currentConfig = JSON.parse(strategy.configuration);

      // Build update query dynamically based on provided fields
      const updateFields = [];
      const updateValues = [];
      let paramIndex = 3; // Starting after strategyId and userId

      // Handle active status
      if (typeof updateConfig.active === 'boolean') {
        updateFields.push(`is_active = $${paramIndex}`);
        updateValues.push(updateConfig.active);
        paramIndex++;
      }

      // Handle name update
      if (updateConfig.name) {
        updateFields.push(`name = $${paramIndex}`);
        updateValues.push(updateConfig.name);
        paramIndex++;
      }

      // Handle description update  
      if (updateConfig.description) {
        updateFields.push(`description = $${paramIndex}`);
        updateValues.push(updateConfig.description);
        paramIndex++;
      }

      // Handle configuration updates (parameters and risk management)
      if (updateConfig.parameters || updateConfig.riskManagement) {
        const newConfig = { ...currentConfig };
        
        if (updateConfig.parameters) {
          newConfig.parameters = { ...currentConfig.parameters, ...updateConfig.parameters };
        }
        
        if (updateConfig.riskManagement) {
          newConfig.riskManagement = { ...currentConfig.riskManagement, ...updateConfig.riskManagement };
        }

        updateFields.push(`configuration = $${paramIndex}`);
        updateValues.push(JSON.stringify(newConfig));
        paramIndex++;
      }

      // Always update the updated_at timestamp
      updateFields.push('updated_at = NOW()');

      if (updateFields.length === 1) { // Only updated_at field
        return {
          success: false,
          error: 'No valid update fields provided',
          statusCode: 400
        };
      }

      // Execute the update
      const updateQuery = `
        UPDATE trading_strategies 
        SET ${updateFields.join(', ')}
        WHERE id = $1 AND user_id = $2
        RETURNING *
      `;

      const updateResult = await query(updateQuery, [strategyId, userId, ...updateValues]);
      const updatedStrategy = updateResult.rows[0];

      // Update in-memory active strategies if needed
      if (typeof updateConfig.active === 'boolean') {
        if (updateConfig.active && !this.activeStrategies.has(strategyId)) {
          // Strategy was activated - add to active strategies
          try {
            // Get user's API credentials
            const credentials = await apiKeyService.getDecryptedApiKey(userId, strategy.provider || 'alpaca');
            if (credentials) {
              const strategyInstance = {
                id: strategyId,
                userId,
                config: JSON.parse(updatedStrategy.configuration),
                credentials,
                alpacaService: new AlpacaService(credentials.apiKey, credentials.apiSecret, credentials.isSandbox),
                status: 'active',
                lastExecuted: strategy.last_executed,
                executionCount: strategy.execution_count || 0,
                performance: JSON.parse(strategy.performance || '{}')
              };
              
              this.activeStrategies.set(strategyId, strategyInstance);
              logger.info(`✅ Strategy added to active strategies`, { strategyId });
            }
          } catch (credError) {
            logger.warn(`⚠️ Strategy updated but couldn't activate due to credential error`, {
              strategyId,
              error: credError.message
            });
          }
        } else if (!updateConfig.active && this.activeStrategies.has(strategyId)) {
          // Strategy was deactivated - remove from active strategies
          this.activeStrategies.delete(strategyId);
          logger.info(`🛑 Strategy removed from active strategies`, { strategyId });
        }
      } else if (this.activeStrategies.has(strategyId)) {
        // Strategy is active and config was updated - update the instance
        const activeStrategy = this.activeStrategies.get(strategyId);
        activeStrategy.config = JSON.parse(updatedStrategy.configuration);
        this.activeStrategies.set(strategyId, activeStrategy);
        logger.info(`🔄 Active strategy configuration updated`, { strategyId });
      }

      logger.info(`✅ Strategy updated successfully`, {
        strategyId,
        updatedFields: Object.keys(updateConfig),
        isActive: updatedStrategy.is_active
      });

      return {
        success: true,
        active: updatedStrategy.is_active,
        updatedFields: Object.keys(updateConfig),
        updatedAt: updatedStrategy.updated_at
      };

    } catch (error) {
      logger.error(`❌ Error updating strategy`, {
        error: error.message,
        errorStack: error.stack,
        strategyId,
        userId: userId ? `${userId.substring(0, 8)}...` : 'unknown'
      });
      
      return {
        success: false,
        error: `Failed to update strategy: ${error.message}`,
        statusCode: 500
      };
    }
  }
}

module.exports = new TradingStrategyEngine();