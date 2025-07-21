// Technical Analysis Service
// Implements RSI, MACD, Bollinger Bands, and other technical indicators
// Integrated with market data service for real-time analysis

const logger = require('../utils/logger');
const marketDataService = require('./marketDataService');

class TechnicalAnalysisService {
  constructor() {
    this.indicators = {
      'RSI': this.calculateRSI.bind(this),
      'MACD': this.calculateMACD.bind(this),
      'BOLLINGER_BANDS': this.calculateBollingerBands.bind(this),
      'SMA': this.calculateSMA.bind(this),
      'EMA': this.calculateEMA.bind(this),
      'STOCHASTIC': this.calculateStochastic.bind(this),
      'WILLIAMS_R': this.calculateWilliamsR.bind(this)
      // Note: CCI, ATR, and VWAP indicators not implemented yet
    };
  }

  // Calculate multiple indicators for a dataset
  calculateIndicators(data, indicators = ['RSI', 'MACD', 'BOLLINGER_BANDS']) {
    if (!Array.isArray(data) || data.length === 0) {
      throw new Error('Invalid data: expected non-empty array');
    }

    const results = {};
    
    indicators.forEach(indicator => {
      if (this.indicators[indicator]) {
        try {
          results[indicator] = this.indicators[indicator](data);
        } catch (error) {
          console.error(`Failed to calculate ${indicator}:`, error.message);
          results[indicator] = { error: error.message };
        }
      } else {
        results[indicator] = { error: `Unknown indicator: ${indicator}` };
      }
    });

    return results;
  }

  // RSI (Relative Strength Index)
  calculateRSI(data, period = 14) {
    if (data.length < period + 1) {
      throw new Error(`Insufficient data for RSI: need at least ${period + 1} points`);
    }

    const prices = data.map(d => d.close || d.price);
    const changes = [];
    
    // Calculate price changes
    for (let i = 1; i < prices.length; i++) {
      changes.push(prices[i] - prices[i - 1]);
    }

    const rsiValues = [];
    let gains = [];
    let losses = [];

    // Initial calculation
    for (let i = 0; i < period; i++) {
      if (changes[i] > 0) {
        gains.push(changes[i]);
        losses.push(0);
      } else {
        gains.push(0);
        losses.push(Math.abs(changes[i]));
      }
    }

    let avgGain = gains.reduce((sum, gain) => sum + gain, 0) / period;
    let avgLoss = losses.reduce((sum, loss) => sum + loss, 0) / period;

    // Calculate initial RSI
    let rs = avgGain / (avgLoss || 0.001); // Prevent division by zero
    let rsi = 100 - (100 / (1 + rs));
    rsiValues.push({
      index: period,
      value: rsi,
      timestamp: data[period].timestamp || null
    });

    // Rolling calculation
    for (let i = period; i < changes.length; i++) {
      const change = changes[i];
      const gain = change > 0 ? change : 0;
      const loss = change < 0 ? Math.abs(change) : 0;

      // Smoothed moving averages
      avgGain = ((avgGain * (period - 1)) + gain) / period;
      avgLoss = ((avgLoss * (period - 1)) + loss) / period;

      rs = avgGain / (avgLoss || 0.001);
      rsi = 100 - (100 / (1 + rs));

      rsiValues.push({
        index: i + 1,
        value: rsi,
        timestamp: data[i + 1].timestamp || null,
        signal: rsi > 70 ? 'OVERBOUGHT' : rsi < 30 ? 'OVERSOLD' : 'NEUTRAL'
      });
    }

    return {
      values: rsiValues,
      current: rsiValues[rsiValues.length - 1],
      period,
      interpretation: this.interpretRSI(rsiValues[rsiValues.length - 1].value)
    };
  }

  // MACD (Moving Average Convergence Divergence)
  calculateMACD(data, fastPeriod = 12, slowPeriod = 26, signalPeriod = 9) {
    if (data.length < slowPeriod) {
      throw new Error(`Insufficient data for MACD: need at least ${slowPeriod} points`);
    }

    const prices = data.map(d => d.close || d.price);
    
    // Calculate EMAs
    const fastEMA = this.calculateEMAValues(prices, fastPeriod);
    const slowEMA = this.calculateEMAValues(prices, slowPeriod);
    
    const macdLine = [];
    const startIndex = slowPeriod - 1;

    // Calculate MACD line
    for (let i = startIndex; i < prices.length; i++) {
      const macdValue = fastEMA[i] - slowEMA[i];
      macdLine.push(macdValue);
    }

    // Calculate Signal line (EMA of MACD)
    const signalLine = this.calculateEMAValues(macdLine, signalPeriod);
    
    // Calculate Histogram
    const histogram = [];
    const signalStartIndex = signalPeriod - 1;
    
    for (let i = signalStartIndex; i < macdLine.length; i++) {
      histogram.push(macdLine[i] - signalLine[i]);
    }

    const results = [];
    const finalStartIndex = startIndex + signalStartIndex;

    for (let i = 0; i < histogram.length; i++) {
      const dataIndex = finalStartIndex + i;
      results.push({
        index: dataIndex,
        timestamp: data[dataIndex].timestamp || null,
        macd: macdLine[signalStartIndex + i],
        signal: signalLine[signalStartIndex + i],
        histogram: histogram[i],
        crossover: i > 0 ? this.detectMACDCrossover(
          macdLine[signalStartIndex + i - 1], 
          signalLine[signalStartIndex + i - 1],
          macdLine[signalStartIndex + i], 
          signalLine[signalStartIndex + i]
        ) : null
      });
    }

    return {
      values: results,
      current: results[results.length - 1],
      parameters: { fastPeriod, slowPeriod, signalPeriod },
      interpretation: this.interpretMACD(results[results.length - 1])
    };
  }

  // Bollinger Bands
  calculateBollingerBands(data, period = 20, stdDev = 2) {
    if (data.length < period) {
      throw new Error(`Insufficient data for Bollinger Bands: need at least ${period} points`);
    }

    const prices = data.map(d => d.close || d.price);
    const results = [];

    for (let i = period - 1; i < prices.length; i++) {
      const slice = prices.slice(i - period + 1, i + 1);
      
      // Calculate SMA
      const sma = slice.reduce((sum, price) => sum + price, 0) / period;
      
      // Calculate standard deviation
      const variance = slice.reduce((sum, price) => sum + Math.pow(price - sma, 2), 0) / period;
      const standardDeviation = Math.sqrt(variance);
      
      // Calculate bands
      const upperBand = sma + (stdDev * standardDeviation);
      const lowerBand = sma - (stdDev * standardDeviation);
      
      const currentPrice = prices[i];
      const bandWidth = (upperBand - lowerBand) / sma * 100;
      const percentB = (currentPrice - lowerBand) / (upperBand - lowerBand);

      results.push({
        index: i,
        timestamp: data[i].timestamp || null,
        upperBand,
        middleBand: sma,
        lowerBand,
        price: currentPrice,
        bandWidth,
        percentB,
        position: currentPrice > upperBand ? 'ABOVE_UPPER' : 
                 currentPrice < lowerBand ? 'BELOW_LOWER' : 'WITHIN_BANDS',
        squeeze: bandWidth < 10 // Bollinger Band squeeze indicator
      });
    }

    return {
      values: results,
      current: results[results.length - 1],
      parameters: { period, stdDev },
      interpretation: this.interpretBollingerBands(results[results.length - 1])
    };
  }

  // Simple Moving Average
  calculateSMA(data, period = 20) {
    if (data.length < period) {
      throw new Error(`Insufficient data for SMA: need at least ${period} points`);
    }

    const prices = data.map(d => d.close || d.price);
    const results = [];

    for (let i = period - 1; i < prices.length; i++) {
      const slice = prices.slice(i - period + 1, i + 1);
      const sma = slice.reduce((sum, price) => sum + price, 0) / period;
      
      results.push({
        index: i,
        timestamp: data[i].timestamp || null,
        value: sma,
        price: prices[i],
        trend: i > period - 1 ? (sma > results[results.length - 1].value ? 'UP' : 'DOWN') : 'NEUTRAL'
      });
    }

    return {
      values: results,
      current: results[results.length - 1],
      period
    };
  }

  // Exponential Moving Average
  calculateEMA(data, period = 20) {
    if (data.length < period) {
      throw new Error(`Insufficient data for EMA: need at least ${period} points`);
    }

    const prices = data.map(d => d.close || d.price);
    const emaValues = this.calculateEMAValues(prices, period);
    const results = [];

    for (let i = period - 1; i < prices.length; i++) {
      results.push({
        index: i,
        timestamp: data[i].timestamp || null,
        value: emaValues[i],
        price: prices[i],
        trend: i > period - 1 ? (emaValues[i] > emaValues[i - 1] ? 'UP' : 'DOWN') : 'NEUTRAL'
      });
    }

    return {
      values: results,
      current: results[results.length - 1],
      period
    };
  }

  // Stochastic Oscillator
  calculateStochastic(data, kPeriod = 14, dPeriod = 3) {
    if (data.length < kPeriod) {
      throw new Error(`Insufficient data for Stochastic: need at least ${kPeriod} points`);
    }

    const results = [];

    for (let i = kPeriod - 1; i < data.length; i++) {
      const slice = data.slice(i - kPeriod + 1, i + 1);
      const highestHigh = Math.max(...slice.map(d => d.high));
      const lowestLow = Math.min(...slice.map(d => d.low));
      const currentClose = data[i].close;

      const kPercent = ((currentClose - lowestLow) / (highestHigh - lowestLow)) * 100;
      
      results.push({
        index: i,
        timestamp: data[i].timestamp || null,
        kPercent,
        highestHigh,
        lowestLow
      });
    }

    // Calculate %D (SMA of %K)
    for (let i = dPeriod - 1; i < results.length; i++) {
      const slice = results.slice(i - dPeriod + 1, i + 1);
      const dPercent = slice.reduce((sum, item) => sum + item.kPercent, 0) / dPeriod;
      
      results[i].dPercent = dPercent;
      results[i].signal = results[i].kPercent > 80 ? 'OVERBOUGHT' : 
                         results[i].kPercent < 20 ? 'OVERSOLD' : 'NEUTRAL';
    }

    return {
      values: results.slice(dPeriod - 1),
      current: results[results.length - 1],
      parameters: { kPeriod, dPeriod }
    };
  }

  // Williams %R
  calculateWilliamsR(data, period = 14) {
    if (data.length < period) {
      throw new Error(`Insufficient data for Williams %R: need at least ${period} points`);
    }

    const results = [];

    for (let i = period - 1; i < data.length; i++) {
      const slice = data.slice(i - period + 1, i + 1);
      const highestHigh = Math.max(...slice.map(d => d.high));
      const lowestLow = Math.min(...slice.map(d => d.low));
      const currentClose = data[i].close;

      const williamsR = ((highestHigh - currentClose) / (highestHigh - lowestLow)) * -100;
      
      results.push({
        index: i,
        timestamp: data[i].timestamp || null,
        value: williamsR,
        signal: williamsR > -20 ? 'OVERBOUGHT' : williamsR < -80 ? 'OVERSOLD' : 'NEUTRAL'
      });
    }

    return {
      values: results,
      current: results[results.length - 1],
      period
    };
  }

  // Helper method to calculate EMA values
  calculateEMAValues(prices, period) {
    const multiplier = 2 / (period + 1);
    const emaValues = [];
    
    // Start with SMA for first value
    const firstSMA = prices.slice(0, period).reduce((sum, price) => sum + price, 0) / period;
    emaValues[period - 1] = firstSMA;
    
    // Calculate EMA for remaining values
    for (let i = period; i < prices.length; i++) {
      const ema = (prices[i] * multiplier) + (emaValues[i - 1] * (1 - multiplier));
      emaValues[i] = ema;
    }
    
    return emaValues;
  }

  // Detect MACD crossover
  detectMACDCrossover(prevMACD, prevSignal, currentMACD, currentSignal) {
    if (prevMACD <= prevSignal && currentMACD > currentSignal) {
      return 'BULLISH_CROSSOVER';
    } else if (prevMACD >= prevSignal && currentMACD < currentSignal) {
      return 'BEARISH_CROSSOVER';
    }
    return null;
  }

  // Interpretation methods
  interpretRSI(rsi) {
    if (rsi > 70) {
      return {
        signal: 'SELL',
        strength: 'STRONG',
        description: 'Overbought conditions - potential sell signal'
      };
    } else if (rsi < 30) {
      return {
        signal: 'BUY',
        strength: 'STRONG',
        description: 'Oversold conditions - potential buy signal'
      };
    } else if (rsi > 60) {
      return {
        signal: 'SELL',
        strength: 'WEAK',
        description: 'Approaching overbought territory'
      };
    } else if (rsi < 40) {
      return {
        signal: 'BUY',
        strength: 'WEAK',
        description: 'Approaching oversold territory'
      };
    }
    return {
      signal: 'HOLD',
      strength: 'NEUTRAL',
      description: 'RSI in neutral territory'
    };
  }

  interpretMACD(macdData) {
    const { macd, signal, histogram, crossover } = macdData;
    
    if (crossover === 'BULLISH_CROSSOVER') {
      return {
        signal: 'BUY',
        strength: 'STRONG',
        description: 'MACD bullish crossover - potential buy signal'
      };
    } else if (crossover === 'BEARISH_CROSSOVER') {
      return {
        signal: 'SELL',
        strength: 'STRONG',
        description: 'MACD bearish crossover - potential sell signal'
      };
    } else if (macd > signal && histogram > 0) {
      return {
        signal: 'BUY',
        strength: 'MODERATE',
        description: 'MACD above signal line with positive histogram'
      };
    } else if (macd < signal && histogram < 0) {
      return {
        signal: 'SELL',
        strength: 'MODERATE',
        description: 'MACD below signal line with negative histogram'
      };
    }
    
    return {
      signal: 'HOLD',
      strength: 'NEUTRAL',
      description: 'MACD signals are mixed'
    };
  }

  interpretBollingerBands(bandData) {
    const { position, percentB, squeeze } = bandData;
    
    if (squeeze) {
      return {
        signal: 'WATCH',
        strength: 'HIGH',
        description: 'Bollinger Band squeeze - expect breakout'
      };
    } else if (position === 'ABOVE_UPPER') {
      return {
        signal: 'SELL',
        strength: 'MODERATE',
        description: 'Price above upper band - potentially overbought'
      };
    } else if (position === 'BELOW_LOWER') {
      return {
        signal: 'BUY',
        strength: 'MODERATE',
        description: 'Price below lower band - potentially oversold'
      };
    } else if (percentB > 0.8) {
      return {
        signal: 'SELL',
        strength: 'WEAK',
        description: 'Price in upper portion of bands'
      };
    } else if (percentB < 0.2) {
      return {
        signal: 'BUY',
        strength: 'WEAK',
        description: 'Price in lower portion of bands'
      };
    }
    
    return {
      signal: 'HOLD',
      strength: 'NEUTRAL',
      description: 'Price within normal band range'
    };
  }

  // Generate trading signals based on multiple indicators
  generateTradingSignal(data, indicators = ['RSI', 'MACD', 'BOLLINGER_BANDS']) {
    const analysis = this.calculateIndicators(data, indicators);
    const signals = [];
    let totalScore = 0;
    let maxScore = 0;

    Object.keys(analysis).forEach(indicator => {
      if (analysis[indicator].interpretation) {
        const interpretation = analysis[indicator].interpretation;
        let score = 0;

        // Score the signals
        if (interpretation.signal === 'BUY') {
          score = interpretation.strength === 'STRONG' ? 3 : 
                 interpretation.strength === 'MODERATE' ? 2 : 1;
        } else if (interpretation.signal === 'SELL') {
          score = interpretation.strength === 'STRONG' ? -3 : 
                 interpretation.strength === 'MODERATE' ? -2 : -1;
        }

        signals.push({
          indicator,
          signal: interpretation.signal,
          strength: interpretation.strength,
          score,
          description: interpretation.description
        });

        totalScore += score;
        maxScore += 3; // Maximum possible score per indicator
      }
    });

    // Calculate overall signal
    const scoreRatio = totalScore / maxScore;
    let overallSignal, confidence;

    if (scoreRatio > 0.3) {
      overallSignal = 'BUY';
      confidence = Math.min(scoreRatio * 100, 100);
    } else if (scoreRatio < -0.3) {
      overallSignal = 'SELL';
      confidence = Math.min(Math.abs(scoreRatio) * 100, 100);
    } else {
      overallSignal = 'HOLD';
      confidence = 100 - Math.abs(scoreRatio) * 100;
    }

    return {
      timestamp: new Date().toISOString(),
      symbol: data[0]?.symbol || 'UNKNOWN',
      overallSignal,
      confidence: Math.round(confidence),
      totalScore,
      maxScore,
      signals,
      analysis,
      recommendation: this.generateRecommendation(overallSignal, confidence, signals)
    };
  }

  generateRecommendation(signal, confidence, signals) {
    const strongSignals = signals.filter(s => s.strength === 'STRONG').length;
    const consensusSignals = signals.filter(s => s.signal === signal).length;
    
    let recommendation = '';
    
    if (signal === 'BUY' && confidence > 70) {
      recommendation = `Strong BUY signal with ${confidence}% confidence. `;
    } else if (signal === 'SELL' && confidence > 70) {
      recommendation = `Strong SELL signal with ${confidence}% confidence. `;
    } else if (signal === 'BUY' && confidence > 50) {
      recommendation = `Moderate BUY signal with ${confidence}% confidence. `;
    } else if (signal === 'SELL' && confidence > 50) {
      recommendation = `Moderate SELL signal with ${confidence}% confidence. `;
    } else {
      recommendation = `HOLD position. Signals are mixed with ${confidence}% confidence. `;
    }
    
    if (strongSignals > 0) {
      recommendation += `${strongSignals} strong indicator(s) support this signal. `;
    }
    
    if (consensusSignals === signals.length) {
      recommendation += 'All indicators agree. ';
    } else {
      recommendation += `${consensusSignals}/${signals.length} indicators agree. `;
    }
    
    recommendation += 'Consider risk management and position sizing.';
    
    return recommendation;
  }

  // Market Data Integration Methods

  /**
   * Analyze symbol using real market data
   */
  async analyzeSymbol(symbol, indicators = ['RSI', 'MACD', 'BOLLINGER_BANDS'], period = '3mo') {
    try {
      logger.info(`Analyzing ${symbol} with indicators: ${indicators.join(', ')}`);
      
      // Get historical data from market data service
      const historicalData = await marketDataService.getHistoricalData(symbol, {
        period,
        interval: '1d'
      });

      if (!historicalData || historicalData.length === 0) {
        throw new Error(`No historical data available for ${symbol}`);
      }

      // Convert to format expected by technical analysis
      const analysisData = historicalData.map(d => ({
        close: d.close,
        high: d.high,
        low: d.low,
        open: d.open,
        volume: d.volume,
        date: d.date
      }));

      const analysis = this.calculateIndicators(analysisData, indicators);
      const tradingSignal = this.generateTradingSignal(analysisData, indicators);

      return {
        symbol,
        period,
        dataPoints: analysisData.length,
        analysis,
        tradingSignal,
        marketData: {
          currentPrice: analysisData[analysisData.length - 1].close,
          priceChange: analysisData[analysisData.length - 1].close - analysisData[analysisData.length - 2].close,
          volume: analysisData[analysisData.length - 1].volume
        },
        analyzedAt: new Date().toISOString()
      };

    } catch (error) {
      logger.error('Error analyzing symbol:', {
        symbol,
        indicators,
        error: error.message
      });
      throw new Error(`Failed to analyze ${symbol}: ${error.message}`);
    }
  }

  /**
   * Get technical analysis for multiple symbols
   */
  async analyzePortfolio(symbols, indicators = ['RSI', 'MACD']) {
    try {
      logger.info(`Analyzing portfolio: ${symbols.length} symbols`);
      
      const results = {};
      const promises = symbols.map(async (symbol) => {
        try {
          results[symbol] = await this.analyzeSymbol(symbol, indicators);
        } catch (error) {
          logger.warn(`Failed to analyze ${symbol}:`, error.message);
          results[symbol] = {
            error: error.message,
            symbol,
            analyzedAt: new Date().toISOString()
          };
        }
      });

      await Promise.allSettled(promises);

      const summary = {
        totalSymbols: symbols.length,
        successful: Object.values(results).filter(r => !r.error).length,
        failed: Object.values(results).filter(r => r.error).length,
        strongBuySignals: Object.values(results).filter(r => !r.error && r.tradingSignal?.signal === 'STRONG_BUY').length,
        strongSellSignals: Object.values(results).filter(r => !r.error && r.tradingSignal?.signal === 'STRONG_SELL').length
      };

      return {
        summary,
        analysis: results,
        analyzedAt: new Date().toISOString()
      };

    } catch (error) {
      logger.error('Error analyzing portfolio:', {
        symbolCount: symbols.length,
        error: error.message
      });
      throw new Error(`Failed to analyze portfolio: ${error.message}`);
    }
  }

  /**
   * Get real-time trading signals with market data
   */
  async getRealtimeSignals(symbol) {
    try {
      logger.info(`Getting real-time signals for ${symbol}`);
      
      // Get both current quote and historical data
      const [quote, analysis] = await Promise.all([
        marketDataService.getQuote(symbol),
        this.analyzeSymbol(symbol, ['RSI', 'MACD', 'BOLLINGER_BANDS'], '1mo')
      ]);

      // Combine real-time price with technical analysis
      const signals = {
        symbol,
        currentPrice: quote.price,
        priceChange: quote.change,
        changePercent: quote.changePercent,
        volume: quote.volume,
        technicalAnalysis: analysis.tradingSignal,
        indicators: {
          rsi: analysis.analysis.RSI?.current || null,
          macd: analysis.analysis.MACD?.current || null,
          bollingerBands: analysis.analysis.BOLLINGER_BANDS?.current || null
        },
        recommendation: this.generateRecommendation(analysis.tradingSignal),
        timestamp: new Date().toISOString()
      };

      logger.info(`Real-time signals for ${symbol}: ${signals.recommendation}`);
      return signals;

    } catch (error) {
      logger.error('Error getting real-time signals:', {
        symbol,
        error: error.message
      });
      throw new Error(`Failed to get real-time signals: ${error.message}`);
    }
  }

  /**
   * Health check for technical analysis service
   */
  async healthCheck() {
    try {
      // Test with real market data
      const testResult = await this.analyzeSymbol('AAPL', ['RSI'], '1mo');
      
      return {
        status: 'healthy',
        service: 'technical-analysis',
        availableIndicators: Object.keys(this.indicators),
        marketDataIntegration: true,
        testAnalysis: {
          symbol: testResult.symbol,
          dataPoints: testResult.dataPoints,
          hasSignals: !!testResult.tradingSignal
        },
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      return {
        status: 'unhealthy',
        service: 'technical-analysis',
        error: error.message,
        timestamp: new Date().toISOString()
      };
    }
  }
}

module.exports = TechnicalAnalysisService;