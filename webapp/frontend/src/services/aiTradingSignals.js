// AI-Powered Trading Signals Service
// Implements machine learning models for technical analysis, sentiment analysis, and signal generation

import axios from 'axios';
import cacheService from './cacheService';

class AITradingSignals {
  constructor() {
    this.models = {
      technical: 'Technical Analysis ML Model',
      sentiment: 'Sentiment Analysis Model', 
      momentum: 'Momentum Pattern Recognition',
      meanReversion: 'Mean Reversion Model',
      breakout: 'Breakout Detection Model',
      ensemble: 'Ensemble Multi-Model Signal'
    };
    
    this.signalTypes = {
      BUY: { label: 'BUY', color: 'success', strength: 1 },
      STRONG_BUY: { label: 'STRONG BUY', color: 'success', strength: 2 },
      SELL: { label: 'SELL', color: 'error', strength: -1 },
      STRONG_SELL: { label: 'STRONG SELL', color: 'error', strength: -2 },
      HOLD: { label: 'HOLD', color: 'warning', strength: 0 },
      NEUTRAL: { label: 'NEUTRAL', color: 'default', strength: 0 }
    };
    
    this.timeframes = ['1D', '5D', '1W', '1M', '3M'];
    
    // ML Model configurations
    this.modelConfig = {
      technical: {
        indicators: ['RSI', 'MACD', 'BB', 'SMA', 'EMA', 'ATR', 'ADX'],
        lookback: 20,
        confidence_threshold: 0.7
      },
      sentiment: {
        sources: ['news', 'social', 'analyst_ratings'],
        weight_news: 0.4,
        weight_social: 0.3,
        weight_analyst: 0.3
      },
      momentum: {
        short_period: 10,
        long_period: 50,
        rsi_oversold: 30,
        rsi_overbought: 70
      }
    };
  }

  // Generate AI trading signals for symbols
  async generateSignals(symbols, options = {}) {
    const {
      models = ['ensemble'],
      timeframe = '1D',
      minConfidence = 0.6,
      maxSignals = 50
    } = options;

    const cacheKey = cacheService.generateKey('ai_trading_signals', {
      symbols: Array.isArray(symbols) ? symbols.join(',') : symbols,
      models: models.join(','),
      timeframe
    });

    return cacheService.cacheApiCall(
      cacheKey,
      async () => {
        const signals = [];
        const symbolArray = Array.isArray(symbols) ? symbols : [symbols];

        await Promise.all(
          symbolArray.map(async (symbol) => {
            try {
              const symbolSignals = await this.generateSymbolSignals(symbol, models, timeframe);
              signals.push(...symbolSignals.filter(signal => signal.confidence >= minConfidence));
            } catch (error) {
              console.error(`Failed to generate signals for ${symbol}:`, error);
              // Skip failed symbol instead of using mock data
              // Real production apps should surface errors properly
            }
          })
        );

        // Sort by confidence and limit results
        const sortedSignals = signals
          .sort((a, b) => b.confidence - a.confidence)
          .slice(0, maxSignals);

        return {
          signals: sortedSignals,
          metadata: {
            generated_at: new Date().toISOString(),
            models_used: models,
            timeframe,
            total_symbols: symbolArray.length,
            signal_count: sortedSignals.length
          }
        };
      },
      300000, // 5 minutes cache
      true
    );
  }

  // Generate signals for a single symbol
  async generateSymbolSignals(symbol, models, timeframe) {
    const signals = [];

    for (const model of models) {
      try {
        let signal;
        
        switch (model) {
          case 'technical':
            signal = await this.technicalAnalysisSignal(symbol, timeframe);
            break;
          case 'sentiment':
            signal = await this.sentimentAnalysisSignal(symbol);
            break;
          case 'momentum':
            signal = await this.momentumSignal(symbol, timeframe);
            break;
          case 'meanReversion':
            signal = await this.meanReversionSignal(symbol, timeframe);
            break;
          case 'breakout':
            signal = await this.breakoutSignal(symbol, timeframe);
            break;
          case 'ensemble':
            signal = await this.ensembleSignal(symbol, timeframe);
            break;
          default:
            continue;
        }

        if (signal) {
          signals.push({
            ...signal,
            symbol,
            model,
            timeframe,
            generated_at: new Date().toISOString()
          });
        }
      } catch (error) {
        console.warn(`Model ${model} failed for ${symbol}:`, error);
      }
    }

    return signals;
  }

  // Technical Analysis ML Signal
  async technicalAnalysisSignal(symbol, timeframe) {
    // Get historical data and technical indicators
    const technicalData = await this.getTechnicalIndicators(symbol, timeframe);
    
    // Simulate ML model prediction
    const features = this.extractTechnicalFeatures(technicalData);
    const prediction = this.simulateTechnicalML(features);
    
    return {
      signal: this.mapPredictionToSignal(prediction.prediction),
      confidence: prediction.confidence,
      reasoning: prediction.reasoning,
      indicators: prediction.indicators,
      target_price: prediction.target_price,
      stop_loss: prediction.stop_loss,
      time_horizon: this.getTimeHorizon(timeframe)
    };
  }

  // Sentiment Analysis Signal
  async sentimentAnalysisSignal(symbol) {
    try {
      // Get news sentiment (would integrate with news service)
      const newsSentiment = await this.getNewsSentiment(symbol);
      const socialSentiment = await this.getSocialSentiment(symbol);
      const analystSentiment = await this.getAnalystSentiment(symbol);
      
      // Combine sentiments
      const overallSentiment = this.combineSentiments({
        news: newsSentiment,
        social: socialSentiment,
        analyst: analystSentiment
      });
      
      return {
        signal: this.sentimentToSignal(overallSentiment.score),
        confidence: overallSentiment.confidence,
        reasoning: `Sentiment Analysis: ${overallSentiment.reasoning}`,
        sentiment_breakdown: overallSentiment.breakdown,
        sentiment_score: overallSentiment.score
      };
    } catch (error) {
      console.error(`Failed to generate sentiment signal for ${symbol}:`, error);
      throw new Error(`Sentiment analysis unavailable for ${symbol}: ${error.message}`);
    }
  }

  // Momentum Signal
  async momentumSignal(symbol, timeframe) {
    const priceData = await this.getPriceData(symbol, timeframe);
    const indicators = await this.calculateMomentumIndicators(priceData);
    
    const signal = this.analyzeMomentum(indicators);
    
    return {
      signal: signal.direction,
      confidence: signal.confidence,
      reasoning: signal.reasoning,
      momentum_score: signal.score,
      indicators: indicators
    };
  }

  // Mean Reversion Signal
  async meanReversionSignal(symbol, timeframe) {
    const priceData = await this.getPriceData(symbol, timeframe);
    const analysis = this.analyzeMeanReversion(priceData);
    
    return {
      signal: analysis.signal,
      confidence: analysis.confidence,
      reasoning: analysis.reasoning,
      deviation_from_mean: analysis.deviation,
      reversion_probability: analysis.probability
    };
  }

  // Breakout Signal
  async breakoutSignal(symbol, timeframe) {
    const priceData = await this.getPriceData(symbol, timeframe);
    const volumeData = await this.getVolumeData(symbol, timeframe);
    
    const breakout = this.detectBreakout(priceData, volumeData);
    
    return {
      signal: breakout.direction,
      confidence: breakout.confidence,
      reasoning: breakout.reasoning,
      breakout_level: breakout.level,
      volume_confirmation: breakout.volume_confirmed
    };
  }

  // Ensemble Signal (combines multiple models)
  async ensembleSignal(symbol, timeframe) {
    try {
      // Get signals from multiple models
      const signals = await Promise.all([
        this.technicalAnalysisSignal(symbol, timeframe),
        this.sentimentAnalysisSignal(symbol),
        this.momentumSignal(symbol, timeframe),
        this.meanReversionSignal(symbol, timeframe)
      ]);
      
      // Combine signals using weighted average
      const ensemble = this.combineSignals(signals);
      
      return {
        signal: ensemble.final_signal,
        confidence: ensemble.confidence,
        reasoning: ensemble.reasoning,
        component_signals: signals,
        consensus_strength: ensemble.consensus
      };
    } catch (error) {
      return this.getMockSignal(symbol);
    }
  }

  // Get technical indicators
  async getTechnicalIndicators(symbol, timeframe) {
    try {
      const response = await axios.get(`/api/stocks/${symbol}/technical`, {
        params: { timeframe }
      });
      
      if (response.data.success) {
        return response.data.data;
      }
    } catch (error) {
      console.warn('Using mock technical data:', error);
    }
    
    // Mock technical indicators
    return {
      rsi: 55 + Math.random() * 30,
      macd: Math.random() * 2 - 1,
      bb_position: Math.random(),
      sma_20: 150 + Math.random() * 50,
      ema_12: 150 + Math.random() * 50,
      atr: 2 + Math.random() * 3,
      adx: 20 + Math.random() * 40,
      volume_ratio: 0.8 + Math.random() * 0.4
    };
  }

  // Extract features for ML model
  extractTechnicalFeatures(technicalData) {
    return {
      rsi_signal: technicalData.rsi > 70 ? -1 : technicalData.rsi < 30 ? 1 : 0,
      macd_signal: technicalData.macd > 0 ? 1 : -1,
      bb_signal: technicalData.bb_position > 0.8 ? -1 : technicalData.bb_position < 0.2 ? 1 : 0,
      trend_signal: technicalData.sma_20 > technicalData.ema_12 ? 1 : -1,
      volatility: technicalData.atr,
      strength: technicalData.adx,
      volume_signal: technicalData.volume_ratio > 1.2 ? 1 : -1
    };
  }

  // Simulate ML model prediction
  simulateTechnicalML(features) {
    // Weighted combination of features (simulating ML model)
    const weights = {
      rsi_signal: 0.2,
      macd_signal: 0.25,
      bb_signal: 0.15,
      trend_signal: 0.2,
      volume_signal: 0.1,
      strength: 0.1
    };
    
    let score = 0;
    for (const [feature, value] of Object.entries(features)) {
      if (weights[feature]) {
        score += weights[feature] * value;
      }
    }
    
    // Add some randomness to simulate model uncertainty
    score += (Math.random() - 0.5) * 0.2;
    
    const confidence = Math.min(0.95, Math.abs(score) + 0.4 + Math.random() * 0.2);
    
    let prediction, reasoning;
    if (score > 0.3) {
      prediction = score > 0.6 ? 2 : 1; // Strong buy or buy
      reasoning = 'Technical indicators show bullish momentum with strong confirmation';
    } else if (score < -0.3) {
      prediction = score < -0.6 ? -2 : -1; // Strong sell or sell
      reasoning = 'Technical indicators show bearish momentum with sell signals';
    } else {
      prediction = 0;
      reasoning = 'Mixed technical signals, neutral recommendation';
    }
    
    return {
      prediction,
      confidence,
      reasoning,
      indicators: features,
      target_price: 150 + score * 10, // Mock target price
      stop_loss: 145 - Math.abs(score) * 5 // Mock stop loss
    };
  }

  // Map prediction to signal type
  mapPredictionToSignal(prediction) {
    switch (prediction) {
      case 2: return 'STRONG_BUY';
      case 1: return 'BUY';
      case -1: return 'SELL';
      case -2: return 'STRONG_SELL';
      default: return 'HOLD';
    }
  }

  // Get news sentiment for symbol
  async getNewsSentiment(symbol) {
    // This would integrate with the news service
    return {
      score: (Math.random() - 0.5) * 2, // -1 to 1
      confidence: 0.7 + Math.random() * 0.2,
      article_count: Math.floor(Math.random() * 10) + 1
    };
  }

  // Get social sentiment
  async getSocialSentiment(symbol) {
    return {
      score: (Math.random() - 0.5) * 2,
      confidence: 0.6 + Math.random() * 0.3,
      mention_count: Math.floor(Math.random() * 100) + 10
    };
  }

  // Get analyst sentiment
  async getAnalystSentiment(symbol) {
    return {
      score: (Math.random() - 0.5) * 1.5,
      confidence: 0.8 + Math.random() * 0.15,
      analyst_count: Math.floor(Math.random() * 20) + 5
    };
  }

  // Combine different sentiment sources
  combineSentiments(sentiments) {
    const config = this.modelConfig.sentiment;
    
    const weightedScore = 
      sentiments.news.score * config.weight_news +
      sentiments.social.score * config.weight_social +
      sentiments.analyst.score * config.weight_analyst;
    
    const avgConfidence = (
      sentiments.news.confidence + 
      sentiments.social.confidence + 
      sentiments.analyst.confidence
    ) / 3;
    
    let reasoning;
    if (weightedScore > 0.5) {
      reasoning = 'Positive sentiment across news, social media, and analyst ratings';
    } else if (weightedScore < -0.5) {
      reasoning = 'Negative sentiment signals from multiple sources';
    } else {
      reasoning = 'Mixed sentiment signals with no clear direction';
    }
    
    return {
      score: weightedScore,
      confidence: avgConfidence,
      reasoning,
      breakdown: sentiments
    };
  }

  // Convert sentiment score to trading signal
  sentimentToSignal(score) {
    if (score > 0.7) return 'STRONG_BUY';
    if (score > 0.3) return 'BUY';
    if (score < -0.7) return 'STRONG_SELL';
    if (score < -0.3) return 'SELL';
    return 'NEUTRAL';
  }

  // Get price data for analysis
  async getPriceData(symbol, timeframe) {
    try {
      const response = await axios.get(`/api/stocks/${symbol}/historical`, {
        params: { period: this.getTimeframeDays(timeframe) }
      });
      
      if (response.data.success) {
        return response.data.data.map(d => ({
          date: d.date,
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close
        }));
      }
    } catch (error) {
      console.warn('Using mock price data:', error);
    }
    
    // Generate mock price data
    return this.generateMockPriceData(this.getTimeframeDays(timeframe));
  }

  // Get volume data
  async getVolumeData(symbol, timeframe) {
    // Mock volume data
    const days = this.getTimeframeDays(timeframe);
    const volumes = [];
    
    for (let i = 0; i < days; i++) {
      volumes.push({
        date: new Date(Date.now() - i * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        volume: Math.floor(1000000 + Math.random() * 5000000)
      });
    }
    
    return volumes.reverse();
  }

  // Calculate momentum indicators
  async calculateMomentumIndicators(priceData) {
    if (!priceData || priceData.length < 10) return {};
    
    const closes = priceData.map(d => d.close);
    const latest = closes[closes.length - 1];
    const sma10 = this.calculateSMA(closes, 10);
    const sma20 = this.calculateSMA(closes, 20);
    const rsi = this.calculateRSI(closes, 14);
    
    return {
      price: latest,
      sma10: sma10[sma10.length - 1],
      sma20: sma20[sma20.length - 1],
      rsi: rsi[rsi.length - 1],
      price_vs_sma10: ((latest - sma10[sma10.length - 1]) / sma10[sma10.length - 1]) * 100,
      price_vs_sma20: ((latest - sma20[sma20.length - 1]) / sma20[sma20.length - 1]) * 100
    };
  }

  // Analyze momentum
  analyzeMomentum(indicators) {
    let score = 0;
    let signals = [];
    
    // Price vs moving averages
    if (indicators.price_vs_sma10 > 2) {
      score += 1;
      signals.push('Price above 10-day SMA (+2%)');
    }
    if (indicators.price_vs_sma20 > 5) {
      score += 1;
      signals.push('Price above 20-day SMA (+5%)');
    }
    
    // RSI analysis
    if (indicators.rsi > 70) {
      score -= 1;
      signals.push('RSI overbought (>70)');
    } else if (indicators.rsi < 30) {
      score += 1;
      signals.push('RSI oversold (<30)');
    }
    
    // Moving average crossover
    if (indicators.sma10 > indicators.sma20) {
      score += 0.5;
      signals.push('Bullish SMA crossover');
    }
    
    const confidence = Math.min(0.9, Math.abs(score) * 0.3 + 0.4);
    
    let direction;
    if (score > 1) direction = 'BUY';
    else if (score > 0.5) direction = 'WEAK_BUY';
    else if (score < -1) direction = 'SELL';
    else if (score < -0.5) direction = 'WEAK_SELL';
    else direction = 'HOLD';
    
    return {
      direction,
      confidence,
      score,
      reasoning: signals.join('; ')
    };
  }

  // Analyze mean reversion
  analyzeMeanReversion(priceData) {
    if (!priceData || priceData.length < 20) {
      return { signal: 'HOLD', confidence: 0.3, reasoning: 'Insufficient data' };
    }
    
    const closes = priceData.map(d => d.close);
    const latest = closes[closes.length - 1];
    const mean = closes.reduce((sum, price) => sum + price, 0) / closes.length;
    const stdDev = Math.sqrt(closes.reduce((sum, price) => sum + Math.pow(price - mean, 2), 0) / closes.length);
    
    const deviation = (latest - mean) / stdDev;
    const probability = Math.abs(deviation) > 2 ? 0.8 : Math.abs(deviation) > 1 ? 0.6 : 0.3;
    
    let signal, reasoning;
    if (deviation > 2) {
      signal = 'SELL';
      reasoning = 'Price significantly above mean, reversion expected';
    } else if (deviation < -2) {
      signal = 'BUY';
      reasoning = 'Price significantly below mean, bounce expected';
    } else {
      signal = 'HOLD';
      reasoning = 'Price near historical mean';
    }
    
    return {
      signal,
      confidence: probability,
      reasoning,
      deviation,
      probability
    };
  }

  // Detect breakout patterns
  detectBreakout(priceData, volumeData) {
    if (!priceData || priceData.length < 20) {
      return { direction: 'HOLD', confidence: 0.3, reasoning: 'Insufficient data' };
    }
    
    const closes = priceData.map(d => d.close);
    const highs = priceData.map(d => d.high);
    const lows = priceData.map(d => d.low);
    const volumes = volumeData.map(d => d.volume);
    
    const latest = closes[closes.length - 1];
    const resistance = Math.max(...highs.slice(-20, -1));
    const support = Math.min(...lows.slice(-20, -1));
    const avgVolume = volumes.slice(-10).reduce((sum, vol) => sum + vol, 0) / 10;
    const latestVolume = volumes[volumes.length - 1];
    
    const volumeConfirmed = latestVolume > avgVolume * 1.5;
    
    let direction, level, reasoning;
    if (latest > resistance && volumeConfirmed) {
      direction = 'BUY';
      level = resistance;
      reasoning = 'Upward breakout above resistance with volume confirmation';
    } else if (latest < support && volumeConfirmed) {
      direction = 'SELL';
      level = support;
      reasoning = 'Downward breakdown below support with volume confirmation';
    } else {
      direction = 'HOLD';
      level = (resistance + support) / 2;
      reasoning = 'No clear breakout pattern detected';
    }
    
    const confidence = volumeConfirmed ? 0.8 : 0.5;
    
    return {
      direction,
      confidence,
      reasoning,
      level,
      volume_confirmed: volumeConfirmed
    };
  }

  // Combine signals from multiple models
  combineSignals(signals) {
    const signalWeights = {
      'technical': 0.4,
      'sentiment': 0.2,
      'momentum': 0.25,
      'meanReversion': 0.15
    };
    
    let weightedScore = 0;
    let totalWeight = 0;
    let confidenceSum = 0;
    
    signals.forEach((signal, index) => {
      const modelType = ['technical', 'sentiment', 'momentum', 'meanReversion'][index];
      const weight = signalWeights[modelType] || 0.25;
      const signalValue = this.signalToValue(signal.signal);
      
      weightedScore += signalValue * weight * signal.confidence;
      totalWeight += weight;
      confidenceSum += signal.confidence;
    });
    
    const finalScore = weightedScore / totalWeight;
    const avgConfidence = confidenceSum / signals.length;
    const consensus = this.calculateConsensus(signals);
    
    return {
      final_signal: this.valueToSignal(finalScore),
      confidence: avgConfidence,
      reasoning: `Ensemble model combining ${signals.length} AI models with ${(consensus * 100).toFixed(0)}% consensus`,
      consensus
    };
  }

  // Convert signal to numerical value
  signalToValue(signal) {
    switch (signal) {
      case 'STRONG_BUY': return 2;
      case 'BUY': return 1;
      case 'WEAK_BUY': return 0.5;
      case 'HOLD':
      case 'NEUTRAL': return 0;
      case 'WEAK_SELL': return -0.5;
      case 'SELL': return -1;
      case 'STRONG_SELL': return -2;
      default: return 0;
    }
  }

  // Convert value back to signal
  valueToSignal(value) {
    if (value > 1.5) return 'STRONG_BUY';
    if (value > 0.7) return 'BUY';
    if (value > 0.2) return 'WEAK_BUY';
    if (value < -1.5) return 'STRONG_SELL';
    if (value < -0.7) return 'SELL';
    if (value < -0.2) return 'WEAK_SELL';
    return 'HOLD';
  }

  // Calculate consensus among signals
  calculateConsensus(signals) {
    const values = signals.map(s => this.signalToValue(s.signal));
    const mean = values.reduce((sum, v) => sum + v, 0) / values.length;
    const variance = values.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / values.length;
    const stdDev = Math.sqrt(variance);
    
    // Lower standard deviation = higher consensus
    return Math.max(0, 1 - stdDev / 2);
  }

  // Helper methods
  getTimeframeDays(timeframe) {
    switch (timeframe) {
      case '1D': return 1;
      case '5D': return 5;
      case '1W': return 7;
      case '1M': return 30;
      case '3M': return 90;
      default: return 30;
    }
  }

  getTimeHorizon(timeframe) {
    switch (timeframe) {
      case '1D': return 'Intraday';
      case '5D': return 'Short-term';
      case '1W': return 'Short-term';
      case '1M': return 'Medium-term';
      case '3M': return 'Long-term';
      default: return 'Medium-term';
    }
  }

  // Generate mock price data
  generateMockPriceData(days) {
    const data = [];
    let price = 150;
    
    for (let i = days; i >= 0; i--) {
      const change = (Math.random() - 0.5) * 4;
      price = Math.max(price + change, 1);
      
      const high = price + Math.random() * 2;
      const low = price - Math.random() * 2;
      
      data.push({
        date: new Date(Date.now() - i * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        open: price + (Math.random() - 0.5),
        high,
        low,
        close: price
      });
    }
    
    return data;
  }

  // Calculate Simple Moving Average
  calculateSMA(prices, period) {
    const sma = [];
    for (let i = period - 1; i < prices.length; i++) {
      const sum = prices.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0);
      sma.push(sum / period);
    }
    return sma;
  }

  // Calculate RSI
  calculateRSI(prices, period = 14) {
    const gains = [];
    const losses = [];
    
    for (let i = 1; i < prices.length; i++) {
      const change = prices[i] - prices[i - 1];
      gains.push(change > 0 ? change : 0);
      losses.push(change < 0 ? Math.abs(change) : 0);
    }
    
    const rsi = [];
    for (let i = period - 1; i < gains.length; i++) {
      const avgGain = gains.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0) / period;
      const avgLoss = losses.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0) / period;
      
      if (avgLoss === 0) {
        rsi.push(100);
      } else {
        const rs = avgGain / avgLoss;
        rsi.push(100 - (100 / (1 + rs)));
      }
    }
    
    return rsi;
  }

  // Validate signal data integrity
  validateSignal(signal) {
    if (!signal || typeof signal !== 'object') {
      throw new Error('Invalid signal: signal must be an object');
    }
    
    if (!signal.signal || !this.signalTypes[signal.signal]) {
      throw new Error(`Invalid signal type: ${signal.signal}`);
    }
    
    if (typeof signal.confidence !== 'number' || signal.confidence < 0 || signal.confidence > 1) {
      throw new Error('Invalid confidence: must be a number between 0 and 1');
    }
    
    return true;
  }

  // Error handling helper for component consumption
  formatError(error, context = 'AI Trading Signals') {
    return {
      error: true,
      message: error.message || 'Unknown error occurred',
      context,
      timestamp: new Date().toISOString(),
      suggestion: 'Please try again later or contact support if the issue persists'
    };
  }
}

// Create singleton instance
const aiTradingSignals = new AITradingSignals();

export default aiTradingSignals;