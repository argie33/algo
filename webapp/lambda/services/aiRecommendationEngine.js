/**
 * AI Recommendation Engine for HFT Trading
 * Provides ML-powered trading signals and strategy recommendations
 */

const { createLogger } = require('../utils/structuredLogger');
const { query } = require('../utils/database');

class AIRecommendationEngine {
  constructor() {
    this.logger = createLogger('financial-platform', 'ai-recommendation-engine');
    this.correlationId = this.generateCorrelationId();
    
    // Technical indicators cache
    this.indicators = new Map();
    this.priceHistory = new Map();
    
    // AI model configurations
    this.models = {
      momentum: {
        name: 'Momentum Predictor',
        confidence: 0.75,
        lookbackPeriod: 20,
        signalThreshold: 0.02
      },
      meanReversion: {
        name: 'Mean Reversion Detector',
        confidence: 0.68,
        lookbackPeriod: 50,
        deviationThreshold: 2.0
      },
      volumeAnalysis: {
        name: 'Volume Pattern Analyzer',
        confidence: 0.72,
        lookbackPeriod: 30,
        volumeThreshold: 1.5
      },
      sentiment: {
        name: 'Market Sentiment Analyzer',
        confidence: 0.65,
        sources: ['news', 'social', 'options_flow']
      }
    };
    
    // Performance tracking
    this.metrics = {
      totalRecommendations: 0,
      successfulRecommendations: 0,
      averageAccuracy: 0,
      lastModelUpdate: null
    };
  }

  generateCorrelationId() {
    return `ai-rec-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Generate comprehensive trading recommendations
   */
  async generateRecommendations(userId, options = {}) {
    try {
      const {
        symbols = [],
        strategies = [],
        timeframe = '1h',
        maxRecommendations = 10,
        minConfidence = 0.6
      } = options;

      this.logger.info('Generating AI recommendations', {
        userId,
        symbols: symbols.length,
        strategies: strategies.length,
        timeframe,
        correlationId: this.correlationId
      });

      // Get user's trading history and preferences
      const userProfile = await this.getUserTradingProfile(userId);
      
      // Get market data for analysis
      const marketData = await this.getMarketData(symbols, timeframe);
      
      // Generate recommendations using different models
      const recommendations = [];
      
      // Momentum-based recommendations
      const momentumRecs = await this.generateMomentumRecommendations(
        marketData, userProfile, strategies
      );
      recommendations.push(...momentumRecs);
      
      // Mean reversion recommendations
      const reversionRecs = await this.generateMeanReversionRecommendations(
        marketData, userProfile, strategies
      );
      recommendations.push(...reversionRecs);
      
      // Volume analysis recommendations
      const volumeRecs = await this.generateVolumeRecommendations(
        marketData, userProfile, strategies
      );
      recommendations.push(...volumeRecs);
      
      // Sentiment-based recommendations
      const sentimentRecs = await this.generateSentimentRecommendations(
        symbols, userProfile, strategies
      );
      recommendations.push(...sentimentRecs);

      // Filter by confidence and rank
      const filteredRecs = recommendations
        .filter(rec => rec.confidence >= minConfidence)
        .sort((a, b) => b.confidence - a.confidence)
        .slice(0, maxRecommendations);

      // Log recommendations for performance tracking
      await this.logRecommendations(userId, filteredRecs);

      this.metrics.totalRecommendations += filteredRecs.length;

      return {
        success: true,
        recommendations: filteredRecs,
        metadata: {
          generatedAt: new Date().toISOString(),
          modelsUsed: Object.keys(this.models),
          totalAnalyzed: symbols.length,
          confidenceRange: {
            min: Math.min(...filteredRecs.map(r => r.confidence)),
            max: Math.max(...filteredRecs.map(r => r.confidence))
          }
        }
      };

    } catch (error) {
      this.logger.error('Failed to generate AI recommendations', {
        error: error.message,
        userId,
        correlationId: this.correlationId
      });
      
      return {
        success: false,
        error: error.message,
        recommendations: []
      };
    }
  }

  /**
   * Get user trading profile and preferences
   */
  async getUserTradingProfile(userId) {
    try {
      const sql = `
        SELECT 
          s.type as strategy_type,
          s.symbols,
          s.risk_parameters,
          COUNT(p.id) as position_count,
          AVG(p.unrealized_pnl) as avg_pnl,
          AVG(pm.win_rate) as avg_win_rate
        FROM hft_strategies s
        LEFT JOIN hft_positions p ON s.id = p.strategy_id
        LEFT JOIN hft_performance_metrics pm ON s.id = pm.strategy_id
        WHERE s.user_id = $1 AND s.enabled = true
        GROUP BY s.id, s.type, s.symbols, s.risk_parameters
      `;

      const result = await query(sql, [userId]);
      
      const profile = {
        preferredStrategies: result.rows.map(r => r.strategy_type),
        tradedSymbols: [...new Set(result.rows.flatMap(r => r.symbols || []))],
        riskTolerance: this.calculateRiskTolerance(result.rows),
        avgWinRate: result.rows.reduce((sum, r) => sum + (parseFloat(r.avg_win_rate) || 0), 0) / result.rows.length || 0,
        avgPnL: result.rows.reduce((sum, r) => sum + (parseFloat(r.avg_pnl) || 0), 0) / result.rows.length || 0
      };

      return profile;

    } catch (error) {
      this.logger.error('Failed to get user trading profile', {
        error: error.message,
        userId,
        correlationId: this.correlationId
      });
      
      return {
        preferredStrategies: ['momentum'],
        tradedSymbols: ['AAPL', 'TSLA'],
        riskTolerance: 'medium',
        avgWinRate: 0.5,
        avgPnL: 0
      };
    }
  }

  /**
   * Calculate user risk tolerance
   */
  calculateRiskTolerance(strategies) {
    const avgMaxLoss = strategies.reduce((sum, s) => {
      const riskParams = s.risk_parameters || {};
      return sum + (parseFloat(riskParams.maxDailyLoss) || 500);
    }, 0) / strategies.length || 500;

    if (avgMaxLoss > 1000) return 'high';
    if (avgMaxLoss > 300) return 'medium';
    return 'low';
  }

  /**
   * Get market data for analysis
   */
  async getMarketData(symbols, timeframe) {
    // In a real implementation, this would fetch from market data APIs
    // For now, we'll simulate market data
    
    const marketData = new Map();
    
    for (const symbol of symbols) {
      const basePrice = 100 + Math.random() * 200;
      const prices = [];
      const volumes = [];
      
      // Generate 100 data points
      for (let i = 0; i < 100; i++) {
        const price = basePrice * (0.95 + Math.random() * 0.1);
        const volume = Math.floor(1000000 + Math.random() * 10000000);
        
        prices.push(price);
        volumes.push(volume);
      }
      
      marketData.set(symbol, {
        symbol,
        prices,
        volumes,
        currentPrice: prices[prices.length - 1],
        change24h: (prices[prices.length - 1] - prices[0]) / prices[0],
        avgVolume: volumes.reduce((sum, v) => sum + v, 0) / volumes.length
      });
    }
    
    return marketData;
  }

  /**
   * Generate momentum-based recommendations
   */
  async generateMomentumRecommendations(marketData, userProfile, strategies) {
    const recommendations = [];
    const model = this.models.momentum;
    
    for (const [symbol, data] of marketData) {
      try {
        // Calculate momentum indicators
        const momentum = this.calculateMomentum(data.prices, model.lookbackPeriod);
        const rsi = this.calculateRSI(data.prices, 14);
        const macd = this.calculateMACD(data.prices);
        
        // Generate signal based on momentum
        if (Math.abs(momentum) > model.signalThreshold) {
          const action = momentum > 0 ? 'BUY' : 'SELL';
          const confidence = Math.min(0.95, model.confidence + Math.abs(momentum) * 0.1);
          
          // Adjust confidence based on user profile
          const profileAdjustment = this.getProfileAdjustment(symbol, userProfile);
          const adjustedConfidence = confidence * profileAdjustment;
          
          if (adjustedConfidence >= 0.6) {
            recommendations.push({
              id: `momentum_${symbol}_${Date.now()}`,
              symbol,
              action,
              confidence: Math.round(adjustedConfidence * 100) / 100,
              currentPrice: data.currentPrice,
              targetPrice: data.currentPrice * (1 + momentum * (action === 'BUY' ? 1 : -1)),
              stopLoss: data.currentPrice * (action === 'BUY' ? 0.98 : 1.02),
              timeHorizon: '4h',
              expectedReturn: Math.round(Math.abs(momentum) * 100 * 100) / 100,
              riskLevel: this.calculateRiskLevel(adjustedConfidence, Math.abs(momentum)),
              reasoning: `Strong ${momentum > 0 ? 'bullish' : 'bearish'} momentum detected. RSI: ${rsi.toFixed(2)}, MACD signal strength: ${Math.abs(macd.signal).toFixed(4)}`,
              model: model.name,
              indicators: {
                momentum: momentum.toFixed(4),
                rsi: rsi.toFixed(2),
                macd: macd.signal.toFixed(4)
              },
              generatedAt: new Date().toISOString()
            });
          }
        }
      } catch (error) {
        this.logger.error('Error generating momentum recommendation', {
          symbol,
          error: error.message,
          correlationId: this.correlationId
        });
      }
    }
    
    return recommendations;
  }

  /**
   * Generate mean reversion recommendations
   */
  async generateMeanReversionRecommendations(marketData, userProfile, strategies) {
    const recommendations = [];
    const model = this.models.meanReversion;
    
    for (const [symbol, data] of marketData) {
      try {
        // Calculate mean reversion indicators
        const bollingerBands = this.calculateBollingerBands(data.prices, 20, 2);
        const deviation = this.calculateStandardDeviation(data.prices, model.lookbackPeriod);
        const meanPrice = data.prices.slice(-model.lookbackPeriod).reduce((sum, p) => sum + p, 0) / model.lookbackPeriod;
        
        const currentDeviation = Math.abs(data.currentPrice - meanPrice) / deviation;
        
        // Generate signal for mean reversion
        if (currentDeviation > model.deviationThreshold) {
          const action = data.currentPrice > meanPrice ? 'SELL' : 'BUY';
          const confidence = Math.min(0.9, model.confidence + (currentDeviation - model.deviationThreshold) * 0.1);
          
          const profileAdjustment = this.getProfileAdjustment(symbol, userProfile);
          const adjustedConfidence = confidence * profileAdjustment;
          
          if (adjustedConfidence >= 0.6) {
            recommendations.push({
              id: `reversion_${symbol}_${Date.now()}`,
              symbol,
              action,
              confidence: Math.round(adjustedConfidence * 100) / 100,
              currentPrice: data.currentPrice,
              targetPrice: meanPrice,
              stopLoss: data.currentPrice * (action === 'BUY' ? 0.95 : 1.05),
              timeHorizon: '2h',
              expectedReturn: Math.round(Math.abs(data.currentPrice - meanPrice) / data.currentPrice * 100 * 100) / 100,
              riskLevel: this.calculateRiskLevel(adjustedConfidence, currentDeviation),
              reasoning: `Price deviation of ${currentDeviation.toFixed(2)} standard deviations from mean suggests reversion opportunity. Bollinger Band position indicates oversold/overbought condition.`,
              model: model.name,
              indicators: {
                deviation: currentDeviation.toFixed(2),
                meanPrice: meanPrice.toFixed(2),
                upperBand: bollingerBands.upper.toFixed(2),
                lowerBand: bollingerBands.lower.toFixed(2)
              },
              generatedAt: new Date().toISOString()
            });
          }
        }
      } catch (error) {
        this.logger.error('Error generating mean reversion recommendation', {
          symbol,
          error: error.message,
          correlationId: this.correlationId
        });
      }
    }
    
    return recommendations;
  }

  /**
   * Generate volume-based recommendations
   */
  async generateVolumeRecommendations(marketData, userProfile, strategies) {
    const recommendations = [];
    const model = this.models.volumeAnalysis;
    
    for (const [symbol, data] of marketData) {
      try {
        const recentVolumes = data.volumes.slice(-model.lookbackPeriod);
        const avgVolume = recentVolumes.reduce((sum, v) => sum + v, 0) / recentVolumes.length;
        const currentVolume = data.volumes[data.volumes.length - 1];
        const volumeRatio = currentVolume / avgVolume;
        
        // Check for volume spikes
        if (volumeRatio > model.volumeThreshold) {
          // Determine action based on price movement and volume
          const priceChange = data.change24h;
          const action = priceChange > 0 ? 'BUY' : 'SELL';
          const confidence = Math.min(0.85, model.confidence + (volumeRatio - model.volumeThreshold) * 0.05);
          
          const profileAdjustment = this.getProfileAdjustment(symbol, userProfile);
          const adjustedConfidence = confidence * profileAdjustment;
          
          if (adjustedConfidence >= 0.6) {
            recommendations.push({
              id: `volume_${symbol}_${Date.now()}`,
              symbol,
              action,
              confidence: Math.round(adjustedConfidence * 100) / 100,
              currentPrice: data.currentPrice,
              targetPrice: data.currentPrice * (1 + priceChange * 0.5),
              stopLoss: data.currentPrice * (action === 'BUY' ? 0.97 : 1.03),
              timeHorizon: '1h',
              expectedReturn: Math.round(Math.abs(priceChange) * 50 * 100) / 100,
              riskLevel: this.calculateRiskLevel(adjustedConfidence, volumeRatio),
              reasoning: `Unusual volume spike detected (${volumeRatio.toFixed(2)}x average). Combined with ${priceChange > 0 ? 'positive' : 'negative'} price movement suggests momentum continuation.`,
              model: model.name,
              indicators: {
                volumeRatio: volumeRatio.toFixed(2),
                avgVolume: Math.round(avgVolume).toLocaleString(),
                currentVolume: Math.round(currentVolume).toLocaleString(),
                priceChange24h: (priceChange * 100).toFixed(2) + '%'
              },
              generatedAt: new Date().toISOString()
            });
          }
        }
      } catch (error) {
        this.logger.error('Error generating volume recommendation', {
          symbol,
          error: error.message,
          correlationId: this.correlationId
        });
      }
    }
    
    return recommendations;
  }

  /**
   * Generate sentiment-based recommendations
   */
  async generateSentimentRecommendations(symbols, userProfile, strategies) {
    const recommendations = [];
    const model = this.models.sentiment;
    
    for (const symbol of symbols) {
      try {
        // Simulate sentiment analysis (in real implementation, this would call sentiment APIs)
        const sentiment = {
          news: -0.5 + Math.random(), // -0.5 to 0.5
          social: -0.5 + Math.random(),
          optionsFlow: -0.5 + Math.random()
        };
        
        const avgSentiment = (sentiment.news + sentiment.social + sentiment.optionsFlow) / 3;
        const sentimentStrength = Math.abs(avgSentiment);
        
        if (sentimentStrength > 0.3) {
          const action = avgSentiment > 0 ? 'BUY' : 'SELL';
          const confidence = Math.min(0.8, model.confidence + sentimentStrength * 0.2);
          
          const profileAdjustment = this.getProfileAdjustment(symbol, userProfile);
          const adjustedConfidence = confidence * profileAdjustment;
          
          if (adjustedConfidence >= 0.6) {
            const basePrice = 100 + Math.random() * 200; // Simulated current price
            
            recommendations.push({
              id: `sentiment_${symbol}_${Date.now()}`,
              symbol,
              action,
              confidence: Math.round(adjustedConfidence * 100) / 100,
              currentPrice: basePrice,
              targetPrice: basePrice * (1 + avgSentiment * 0.05),
              stopLoss: basePrice * (action === 'BUY' ? 0.96 : 1.04),
              timeHorizon: '6h',
              expectedReturn: Math.round(sentimentStrength * 5 * 100) / 100,
              riskLevel: this.calculateRiskLevel(adjustedConfidence, sentimentStrength),
              reasoning: `${avgSentiment > 0 ? 'Positive' : 'Negative'} sentiment across multiple sources. News sentiment: ${sentiment.news > 0 ? 'bullish' : 'bearish'}, Social sentiment: ${sentiment.social > 0 ? 'positive' : 'negative'}.`,
              model: model.name,
              indicators: {
                newsSentiment: sentiment.news.toFixed(3),
                socialSentiment: sentiment.social.toFixed(3),
                optionsFlow: sentiment.optionsFlow.toFixed(3),
                avgSentiment: avgSentiment.toFixed(3)
              },
              generatedAt: new Date().toISOString()
            });
          }
        }
      } catch (error) {
        this.logger.error('Error generating sentiment recommendation', {
          symbol,
          error: error.message,
          correlationId: this.correlationId
        });
      }
    }
    
    return recommendations;
  }

  /**
   * Calculate momentum indicator
   */
  calculateMomentum(prices, period) {
    if (prices.length < period + 1) return 0;
    
    const current = prices[prices.length - 1];
    const past = prices[prices.length - 1 - period];
    
    return (current - past) / past;
  }

  /**
   * Calculate RSI
   */
  calculateRSI(prices, period = 14) {
    if (prices.length < period + 1) return 50;
    
    let gains = 0;
    let losses = 0;
    
    for (let i = prices.length - period; i < prices.length; i++) {
      const change = prices[i] - prices[i - 1];
      if (change > 0) {
        gains += change;
      } else {
        losses += Math.abs(change);
      }
    }
    
    const avgGain = gains / period;
    const avgLoss = losses / period;
    const rs = avgGain / avgLoss;
    
    return 100 - (100 / (1 + rs));
  }

  /**
   * Calculate MACD
   */
  calculateMACD(prices) {
    if (prices.length < 26) return { signal: 0, histogram: 0 };
    
    const ema12 = this.calculateEMA(prices, 12);
    const ema26 = this.calculateEMA(prices, 26);
    const macdLine = ema12 - ema26;
    
    // Simplified signal line calculation
    const signal = macdLine * 0.8; // Approximation
    const histogram = macdLine - signal;
    
    return { signal, histogram };
  }

  /**
   * Calculate EMA
   */
  calculateEMA(prices, period) {
    if (prices.length === 0) return 0;
    
    const multiplier = 2 / (period + 1);
    let ema = prices[0];
    
    for (let i = 1; i < prices.length; i++) {
      ema = (prices[i] * multiplier) + (ema * (1 - multiplier));
    }
    
    return ema;
  }

  /**
   * Calculate Bollinger Bands
   */
  calculateBollingerBands(prices, period, stdDev) {
    if (prices.length < period) return { upper: 0, middle: 0, lower: 0 };
    
    const recentPrices = prices.slice(-period);
    const middle = recentPrices.reduce((sum, p) => sum + p, 0) / period;
    const deviation = this.calculateStandardDeviation(recentPrices, period);
    
    return {
      upper: middle + (deviation * stdDev),
      middle,
      lower: middle - (deviation * stdDev)
    };
  }

  /**
   * Calculate standard deviation
   */
  calculateStandardDeviation(prices, period) {
    const recentPrices = prices.slice(-period);
    const mean = recentPrices.reduce((sum, p) => sum + p, 0) / recentPrices.length;
    const squaredDiffs = recentPrices.map(p => Math.pow(p - mean, 2));
    const avgSquaredDiff = squaredDiffs.reduce((sum, d) => sum + d, 0) / squaredDiffs.length;
    
    return Math.sqrt(avgSquaredDiff);
  }

  /**
   * Get profile adjustment factor
   */
  getProfileAdjustment(symbol, userProfile) {
    let adjustment = 1.0;
    
    // Boost confidence for symbols user has traded before
    if (userProfile.tradedSymbols.includes(symbol)) {
      adjustment += 0.1;
    }
    
    // Risk tolerance adjustment
    if (userProfile.riskTolerance === 'high') {
      adjustment += 0.05;
    } else if (userProfile.riskTolerance === 'low') {
      adjustment -= 0.05;
    }
    
    // Performance-based adjustment
    if (userProfile.avgWinRate > 0.6) {
      adjustment += 0.05;
    }
    
    return Math.max(0.8, Math.min(1.2, adjustment));
  }

  /**
   * Calculate risk level
   */
  calculateRiskLevel(confidence, strength) {
    if (confidence > 0.8 && strength < 1.5) return 'LOW';
    if (confidence > 0.7 && strength < 2.0) return 'MEDIUM';
    return 'HIGH';
  }

  /**
   * Log recommendations for performance tracking
   */
  async logRecommendations(userId, recommendations) {
    try {
      for (const rec of recommendations) {
        // In a real implementation, this would store recommendations
        // for later performance analysis
        this.logger.info('AI recommendation generated', {
          userId,
          symbol: rec.symbol,
          action: rec.action,
          confidence: rec.confidence,
          model: rec.model,
          correlationId: this.correlationId
        });
      }
    } catch (error) {
      this.logger.error('Failed to log recommendations', {
        error: error.message,
        correlationId: this.correlationId
      });
    }
  }

  /**
   * Get engine metrics
   */
  getMetrics() {
    return {
      ...this.metrics,
      modelsAvailable: Object.keys(this.models).length,
      cacheSize: this.indicators.size,
      correlationId: this.correlationId
    };
  }
}

module.exports = AIRecommendationEngine;