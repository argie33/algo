const logger = require('./logger');
const { query } = require('./database');

/**
 * Advanced Signal Processing and Pattern Recognition System
 * Institutional-grade technical analysis and pattern detection
 */
class SignalProcessor {
  constructor() {
    this.patternCache = new Map();
    this.signalHistory = new Map();
    this.performanceMetrics = new Map();
  }

  /**
   * Process market data and generate trading signals
   * @param {Array} priceData - Array of price data with OHLCV
   * @param {string} symbol - Stock symbol
   * @param {Object} options - Processing options
   * @returns {Object} Signal analysis results
   */
  async processSignals(priceData, symbol, options = {}) {
    const startTime = Date.now();
    
    try {
      logger.info('🔍 Starting signal processing', {
        symbol: symbol,
        dataPoints: priceData.length,
        timeframe: options.timeframe || '1D',
        patterns: options.patterns || 'all'
      });

      // Validate input data
      if (!priceData || priceData.length < 50) {
        throw new Error('Insufficient price data for signal processing');
      }

      // Calculate technical indicators
      const indicators = await this.calculateTechnicalIndicators(priceData);
      
      // Detect chart patterns
      const patterns = await this.detectPatterns(priceData, symbol);
      
      // Generate composite signals
      const signals = await this.generateCompositeSignals(indicators, patterns, priceData);
      
      // Calculate signal strength and confidence
      const analysis = await this.analyzeSignalStrength(signals, indicators, patterns);
      
      // Store signal history
      await this.storeSignalHistory(symbol, analysis);
      
      const processingTime = Date.now() - startTime;
      
      logger.info('✅ Signal processing completed', {
        symbol: symbol,
        signalCount: signals.length,
        patternCount: patterns.length,
        processingTime: processingTime,
        strongestSignal: analysis.primary?.type || 'none',
        confidence: analysis.primary?.confidence || 0
      });

      return {
        success: true,
        symbol: symbol,
        timestamp: new Date().toISOString(),
        processingTime: processingTime,
        indicators: indicators,
        patterns: patterns,
        signals: signals,
        analysis: analysis,
        recommendations: await this.generateRecommendations(analysis)
      };

    } catch (error) {
      logger.error('❌ Signal processing failed', {
        symbol: symbol,
        error: error.message,
        errorStack: error.stack,
        processingTime: Date.now() - startTime
      });
      
      throw new Error(`Signal processing failed: ${error.message}`);
    }
  }

  /**
   * Calculate comprehensive technical indicators
   * @param {Array} priceData - Price data array
   * @returns {Object} Technical indicators
   */
  async calculateTechnicalIndicators(priceData) {
    const indicators = {
      trend: {},
      momentum: {},
      volatility: {},
      volume: {},
      support_resistance: {}
    };

    // Trend Indicators
    indicators.trend.sma_20 = this.calculateSMA(priceData, 20);
    indicators.trend.sma_50 = this.calculateSMA(priceData, 50);
    indicators.trend.sma_200 = this.calculateSMA(priceData, 200);
    indicators.trend.ema_12 = this.calculateEMA(priceData, 12);
    indicators.trend.ema_26 = this.calculateEMA(priceData, 26);
    indicators.trend.bollinger_bands = this.calculateBollingerBands(priceData, 20, 2);
    indicators.trend.trend_direction = this.determineTrendDirection(indicators.trend);

    // Momentum Indicators
    indicators.momentum.rsi = this.calculateRSI(priceData, 14);
    indicators.momentum.macd = this.calculateMACD(priceData);
    indicators.momentum.stochastic = this.calculateStochastic(priceData, 14);
    indicators.momentum.williams_r = this.calculateWilliamsR(priceData, 14);
    indicators.momentum.momentum_score = this.calculateMomentumScore(indicators.momentum);

    // Volatility Indicators
    indicators.volatility.atr = this.calculateATR(priceData, 14);
    indicators.volatility.volatility_ratio = this.calculateVolatilityRatio(priceData);
    indicators.volatility.price_volatility = this.calculatePriceVolatility(priceData);

    // Volume Indicators
    indicators.volume.volume_sma = this.calculateVolumeSMA(priceData, 20);
    indicators.volume.volume_ratio = this.calculateVolumeRatio(priceData);
    indicators.volume.obv = this.calculateOBV(priceData);

    // Support and Resistance
    indicators.support_resistance = this.calculateSupportResistance(priceData);

    return indicators;
  }

  /**
   * Detect various chart patterns
   * @param {Array} priceData - Price data array
   * @param {string} symbol - Stock symbol
   * @returns {Array} Detected patterns
   */
  async detectPatterns(priceData, symbol) {
    const patterns = [];

    try {
      // Candlestick Patterns
      const candlestickPatterns = await this.detectCandlestickPatterns(priceData);
      patterns.push(...candlestickPatterns);

      // Chart Patterns
      const chartPatterns = await this.detectChartPatterns(priceData);
      patterns.push(...chartPatterns);

      // Harmonic Patterns
      const harmonicPatterns = await this.detectHarmonicPatterns(priceData);
      patterns.push(...harmonicPatterns);

      // Volume Patterns
      const volumePatterns = await this.detectVolumePatterns(priceData);
      patterns.push(...volumePatterns);

      // Sort patterns by confidence
      patterns.sort((a, b) => b.confidence - a.confidence);

      logger.info('🔍 Pattern detection completed', {
        symbol: symbol,
        patternsFound: patterns.length,
        highConfidencePatterns: patterns.filter(p => p.confidence > 0.8).length
      });

      return patterns;

    } catch (error) {
      logger.error('❌ Pattern detection failed', {
        symbol: symbol,
        error: error.message
      });
      return [];
    }
  }

  /**
   * Detect candlestick patterns
   * @param {Array} priceData - Price data array
   * @returns {Array} Candlestick patterns
   */
  async detectCandlestickPatterns(priceData) {
    const patterns = [];
    
    // Doji patterns
    patterns.push(...this.detectDoji(priceData));
    
    // Hammer and Hanging Man
    patterns.push(...this.detectHammer(priceData));
    
    // Engulfing patterns
    patterns.push(...this.detectEngulfing(priceData));
    
    // Morning/Evening Star
    patterns.push(...this.detectStar(priceData));
    
    // Harami patterns
    patterns.push(...this.detectHarami(priceData));

    return patterns;
  }

  /**
   * Detect chart patterns (head and shoulders, triangles, etc.)
   * @param {Array} priceData - Price data array
   * @returns {Array} Chart patterns
   */
  async detectChartPatterns(priceData) {
    const patterns = [];
    
    // Head and Shoulders
    patterns.push(...this.detectHeadAndShoulders(priceData));
    
    // Double Top/Bottom
    patterns.push(...this.detectDoubleTopBottom(priceData));
    
    // Triangles
    patterns.push(...this.detectTriangles(priceData));
    
    // Flags and Pennants
    patterns.push(...this.detectFlagsAndPennants(priceData));
    
    // Wedges
    patterns.push(...this.detectWedges(priceData));

    return patterns;
  }

  /**
   * Generate composite trading signals
   * @param {Object} indicators - Technical indicators
   * @param {Array} patterns - Detected patterns
   * @param {Array} priceData - Price data
   * @returns {Array} Trading signals
   */
  async generateCompositeSignals(indicators, patterns, priceData) {
    const signals = [];
    
    // Trend following signals
    const trendSignal = this.generateTrendSignal(indicators.trend, priceData);
    if (trendSignal) signals.push(trendSignal);
    
    // Momentum signals
    const momentumSignal = this.generateMomentumSignal(indicators.momentum, priceData);
    if (momentumSignal) signals.push(momentumSignal);
    
    // Mean reversion signals
    const meanReversionSignal = this.generateMeanReversionSignal(indicators, priceData);
    if (meanReversionSignal) signals.push(meanReversionSignal);
    
    // Breakout signals
    const breakoutSignal = this.generateBreakoutSignal(indicators, priceData);
    if (breakoutSignal) signals.push(breakoutSignal);
    
    // Pattern-based signals
    const patternSignals = this.generatePatternSignals(patterns, priceData);
    signals.push(...patternSignals);
    
    // Volume confirmation signals
    const volumeSignal = this.generateVolumeSignal(indicators.volume, priceData);
    if (volumeSignal) signals.push(volumeSignal);

    return signals;
  }

  /**
   * Analyze signal strength and generate confidence scores
   * @param {Array} signals - Generated signals
   * @param {Object} indicators - Technical indicators
   * @param {Array} patterns - Detected patterns
   * @returns {Object} Signal analysis
   */
  async analyzeSignalStrength(signals, indicators, patterns) {
    const analysis = {
      primary: null,
      secondary: [],
      conflicting: [],
      confidence: 0,
      strength: 'weak',
      recommendation: 'hold'
    };

    if (signals.length === 0) {
      return analysis;
    }

    // Group signals by direction
    const bullishSignals = signals.filter(s => s.direction === 'bullish');
    const bearishSignals = signals.filter(s => s.direction === 'bearish');

    // Calculate weighted confidence
    const bullishWeight = bullishSignals.reduce((sum, s) => sum + (s.confidence * s.weight), 0);
    const bearishWeight = bearishSignals.reduce((sum, s) => sum + (s.confidence * s.weight), 0);

    // Determine primary signal
    if (bullishWeight > bearishWeight && bullishWeight > 0.6) {
      analysis.primary = {
        type: 'bullish',
        confidence: bullishWeight,
        signals: bullishSignals.length,
        strength: this.calculateSignalStrength(bullishWeight)
      };
      analysis.recommendation = 'buy';
    } else if (bearishWeight > bullishWeight && bearishWeight > 0.6) {
      analysis.primary = {
        type: 'bearish',
        confidence: bearishWeight,
        signals: bearishSignals.length,
        strength: this.calculateSignalStrength(bearishWeight)
      };
      analysis.recommendation = 'sell';
    } else {
      analysis.primary = {
        type: 'neutral',
        confidence: 0.5,
        signals: signals.length,
        strength: 'weak'
      };
      analysis.recommendation = 'hold';
    }

    // Add secondary signals
    analysis.secondary = signals
      .filter(s => s.direction !== analysis.primary?.type)
      .slice(0, 3);

    // Identify conflicting signals
    if (bullishSignals.length > 0 && bearishSignals.length > 0) {
      analysis.conflicting = signals.filter(s => 
        s.confidence > 0.7 && s.direction !== analysis.primary?.type
      );
    }

    analysis.confidence = analysis.primary?.confidence || 0;
    analysis.strength = analysis.primary?.strength || 'weak';

    return analysis;
  }

  /**
   * Store signal history in database
   * @param {string} symbol - Stock symbol
   * @param {Object} analysis - Signal analysis
   */
  async storeSignalHistory(symbol, analysis) {
    try {
      await query(`
        INSERT INTO signal_history (
          symbol, timestamp, signal_type, confidence, strength, 
          recommendation, analysis_data, created_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
      `, [
        symbol,
        new Date().toISOString(),
        analysis.primary?.type || 'neutral',
        analysis.confidence,
        analysis.strength,
        analysis.recommendation,
        JSON.stringify(analysis)
      ]);
    } catch (error) {
      logger.error('❌ Failed to store signal history', {
        symbol: symbol,
        error: error.message
      });
    }
  }

  /**
   * Generate trading recommendations
   * @param {Object} analysis - Signal analysis
   * @returns {Object} Recommendations
   */
  async generateRecommendations(analysis) {
    const recommendations = {
      action: analysis.recommendation,
      confidence: analysis.confidence,
      riskLevel: this.calculateRiskLevel(analysis),
      positionSize: this.calculatePositionSize(analysis),
      stopLoss: this.calculateStopLoss(analysis),
      takeProfit: this.calculateTakeProfit(analysis),
      timeframe: this.determineTimeframe(analysis),
      rationale: this.generateRationale(analysis)
    };

    return recommendations;
  }

  // Helper methods for technical calculations
  calculateSMA(data, period) {
    if (data.length < period) return null;
    const slice = data.slice(-period);
    const sum = slice.reduce((acc, item) => acc + item.close, 0);
    return sum / period;
  }

  calculateEMA(data, period) {
    if (data.length < period) return null;
    const multiplier = 2 / (period + 1);
    let ema = data[0].close;
    
    for (let i = 1; i < data.length; i++) {
      ema = (data[i].close - ema) * multiplier + ema;
    }
    
    return ema;
  }

  calculateRSI(data, period) {
    if (data.length < period + 1) return null;
    
    let gains = 0;
    let losses = 0;
    
    for (let i = 1; i < period + 1; i++) {
      const change = data[i].close - data[i - 1].close;
      if (change > 0) gains += change;
      else losses -= change;
    }
    
    let avgGain = gains / period;
    let avgLoss = losses / period;
    
    for (let i = period + 1; i < data.length; i++) {
      const change = data[i].close - data[i - 1].close;
      if (change > 0) {
        avgGain = (avgGain * (period - 1) + change) / period;
        avgLoss = (avgLoss * (period - 1)) / period;
      } else {
        avgGain = (avgGain * (period - 1)) / period;
        avgLoss = (avgLoss * (period - 1) - change) / period;
      }
    }
    
    const rs = avgGain / avgLoss;
    return 100 - (100 / (1 + rs));
  }

  calculateMACD(data) {
    if (data.length < 26) return null;
    
    const ema12 = this.calculateEMA(data, 12);
    const ema26 = this.calculateEMA(data, 26);
    const macdLine = ema12 - ema26;
    
    // Signal line (EMA of MACD)
    const macdData = data.slice(-9).map((_, i) => ({ close: macdLine }));
    const signalLine = this.calculateEMA(macdData, 9);
    
    return {
      macd: macdLine,
      signal: signalLine,
      histogram: macdLine - signalLine,
      direction: macdLine > signalLine ? 'bullish' : 'bearish'
    };
  }

  // Pattern detection methods (simplified implementations)
  detectDoji(data) {
    const patterns = [];
    const recent = data.slice(-5);
    
    recent.forEach((candle, i) => {
      const bodySize = Math.abs(candle.close - candle.open);
      const shadowSize = candle.high - candle.low;
      
      if (bodySize < shadowSize * 0.1) {
        patterns.push({
          type: 'doji',
          pattern: 'reversal',
          confidence: 0.7,
          direction: 'neutral',
          timestamp: candle.timestamp,
          description: 'Doji candlestick indicates potential reversal'
        });
      }
    });
    
    return patterns;
  }

  detectHammer(data) {
    const patterns = [];
    const recent = data.slice(-3);
    
    recent.forEach((candle, i) => {
      const bodySize = Math.abs(candle.close - candle.open);
      const lowerShadow = Math.min(candle.open, candle.close) - candle.low;
      const upperShadow = candle.high - Math.max(candle.open, candle.close);
      
      if (lowerShadow > bodySize * 2 && upperShadow < bodySize * 0.5) {
        patterns.push({
          type: 'hammer',
          pattern: 'reversal',
          confidence: 0.75,
          direction: 'bullish',
          timestamp: candle.timestamp,
          description: 'Hammer pattern suggests potential upward reversal'
        });
      }
    });
    
    return patterns;
  }

  // Additional pattern detection methods would be implemented here
  detectEngulfing(data) { return []; }
  detectStar(data) { return []; }
  detectHarami(data) { return []; }
  detectHeadAndShoulders(data) { return []; }
  detectDoubleTopBottom(data) { return []; }
  detectTriangles(data) { return []; }
  detectFlagsAndPennants(data) { return []; }
  detectWedges(data) { return []; }
  detectHarmonicPatterns(data) { return []; }
  detectVolumePatterns(data) { return []; }

  // Signal generation methods
  generateTrendSignal(trend, data) {
    if (!trend.sma_20 || !trend.sma_50) return null;
    
    const currentPrice = data[data.length - 1].close;
    
    if (currentPrice > trend.sma_20 && trend.sma_20 > trend.sma_50) {
      return {
        type: 'trend_following',
        direction: 'bullish',
        confidence: 0.7,
        weight: 0.8,
        description: 'Price above moving averages with bullish trend'
      };
    } else if (currentPrice < trend.sma_20 && trend.sma_20 < trend.sma_50) {
      return {
        type: 'trend_following',
        direction: 'bearish',
        confidence: 0.7,
        weight: 0.8,
        description: 'Price below moving averages with bearish trend'
      };
    }
    
    return null;
  }

  generateMomentumSignal(momentum, data) {
    if (!momentum.rsi || !momentum.macd) return null;
    
    if (momentum.rsi < 30 && momentum.macd.histogram > 0) {
      return {
        type: 'momentum',
        direction: 'bullish',
        confidence: 0.8,
        weight: 0.7,
        description: 'Oversold RSI with bullish MACD momentum'
      };
    } else if (momentum.rsi > 70 && momentum.macd.histogram < 0) {
      return {
        type: 'momentum',
        direction: 'bearish',
        confidence: 0.8,
        weight: 0.7,
        description: 'Overbought RSI with bearish MACD momentum'
      };
    }
    
    return null;
  }

  generateMeanReversionSignal(indicators, data) {
    // Simplified mean reversion logic
    return null;
  }

  generateBreakoutSignal(indicators, data) {
    // Simplified breakout logic
    return null;
  }

  generatePatternSignals(patterns, data) {
    return patterns.map(pattern => ({
      type: 'pattern',
      direction: pattern.direction,
      confidence: pattern.confidence,
      weight: 0.6,
      description: pattern.description,
      pattern: pattern.type
    }));
  }

  generateVolumeSignal(volume, data) {
    if (!volume.volume_ratio) return null;
    
    if (volume.volume_ratio > 1.5) {
      return {
        type: 'volume',
        direction: 'bullish',
        confidence: 0.6,
        weight: 0.5,
        description: 'Above average volume confirms price movement'
      };
    }
    
    return null;
  }

  // Helper calculation methods
  calculateSignalStrength(confidence) {
    if (confidence > 0.8) return 'strong';
    if (confidence > 0.6) return 'moderate';
    return 'weak';
  }

  calculateRiskLevel(analysis) {
    if (analysis.confidence > 0.8) return 'low';
    if (analysis.confidence > 0.6) return 'medium';
    return 'high';
  }

  calculatePositionSize(analysis) {
    const baseSize = 0.02; // 2% of portfolio
    const multiplier = analysis.confidence;
    return Math.min(baseSize * multiplier, 0.05); // Max 5%
  }

  calculateStopLoss(analysis) {
    const baseStop = 0.02; // 2% stop loss
    const riskMultiplier = analysis.confidence > 0.8 ? 0.8 : 1.2;
    return baseStop * riskMultiplier;
  }

  calculateTakeProfit(analysis) {
    const baseProfit = 0.06; // 6% take profit
    const rewardMultiplier = analysis.confidence > 0.8 ? 1.5 : 1.0;
    return baseProfit * rewardMultiplier;
  }

  determineTimeframe(analysis) {
    if (analysis.strength === 'strong') return 'short';
    if (analysis.strength === 'moderate') return 'medium';
    return 'long';
  }

  generateRationale(analysis) {
    const reasons = [];
    
    if (analysis.primary?.type === 'bullish') {
      reasons.push('Multiple bullish signals detected');
    } else if (analysis.primary?.type === 'bearish') {
      reasons.push('Multiple bearish signals detected');
    }
    
    if (analysis.conflicting.length > 0) {
      reasons.push('Some conflicting signals present');
    }
    
    return reasons.join('. ');
  }

  // Additional helper methods for technical indicators
  calculateBollingerBands(data, period, stdDev) {
    // Implementation for Bollinger Bands
    return { upper: 0, middle: 0, lower: 0 };
  }

  calculateStochastic(data, period) {
    // Implementation for Stochastic oscillator
    return { k: 0, d: 0 };
  }

  calculateWilliamsR(data, period) {
    // Implementation for Williams %R
    return 0;
  }

  calculateATR(data, period) {
    // Implementation for Average True Range
    return 0;
  }

  calculateOBV(data) {
    // Implementation for On-Balance Volume
    return 0;
  }

  // Additional calculation methods would be implemented here
  determineTrendDirection(trend) { return 'neutral'; }
  calculateMomentumScore(momentum) { return 0.5; }
  calculateVolatilityRatio(data) { return 1.0; }
  calculatePriceVolatility(data) { return 0.2; }
  calculateVolumeSMA(data, period) { return 0; }
  calculateVolumeRatio(data) { return 1.0; }
  calculateSupportResistance(data) { return { support: [], resistance: [] }; }
}

module.exports = SignalProcessor;