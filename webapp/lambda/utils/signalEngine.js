const { query } = require('./database');
const FactorScoringEngine = require('./factorScoring');

class SignalEngine {
  constructor() {
    this.factorEngine = new FactorScoringEngine();
    
    // Signal types and their configurations
    this.signalTypes = {
      // Technical signals
      MOMENTUM_BREAKOUT: {
        name: 'Momentum Breakout',
        type: 'technical',
        strength: 0.8,
        timeframe: 'short',
        description: 'Stock breaking above resistance with strong momentum'
      },
      MEAN_REVERSION: {
        name: 'Mean Reversion',
        type: 'technical',
        strength: 0.6,
        timeframe: 'short',
        description: 'Oversold stock showing signs of reversal'
      },
      GOLDEN_CROSS: {
        name: 'Golden Cross',
        type: 'technical',
        strength: 0.7,
        timeframe: 'medium',
        description: 'Short-term MA crossing above long-term MA'
      },
      
      // Fundamental signals
      EARNINGS_SURPRISE: {
        name: 'Earnings Surprise',
        type: 'fundamental',
        strength: 0.9,
        timeframe: 'medium',
        description: 'Company beating earnings expectations significantly'
      },
      VALUE_OPPORTUNITY: {
        name: 'Value Opportunity',
        type: 'fundamental',
        strength: 0.7,
        timeframe: 'long',
        description: 'Undervalued stock with strong fundamentals'
      },
      GROWTH_ACCELERATION: {
        name: 'Growth Acceleration',
        type: 'fundamental',
        strength: 0.8,
        timeframe: 'long',
        description: 'Company showing accelerating growth metrics'
      },
      
      // Sentiment signals
      ANALYST_UPGRADE: {
        name: 'Analyst Upgrade',
        type: 'sentiment',
        strength: 0.6,
        timeframe: 'short',
        description: 'Recent analyst rating upgrades'
      },
      INSTITUTIONAL_BUYING: {
        name: 'Institutional Buying',
        type: 'sentiment',
        strength: 0.7,
        timeframe: 'medium',
        description: 'Increased institutional ownership'
      },
      
      // Risk signals
      RISK_ALERT: {
        name: 'Risk Alert',
        type: 'risk',
        strength: -0.8,
        timeframe: 'short',
        description: 'Elevated risk indicators detected'
      },
      LIQUIDITY_CONCERN: {
        name: 'Liquidity Concern',
        type: 'risk',
        strength: -0.6,
        timeframe: 'short',
        description: 'Decreasing liquidity or increasing debt concerns'
      }
    };
  }

  // Generate signals for a single stock
  async generateSignalsForStock(symbol) {
    try {
      // Get comprehensive stock data
      const stockData = await this.getStockData(symbol);
      const technicalData = await this.getTechnicalData(symbol);
      
      if (!stockData) {
        throw new Error(`No data found for symbol: ${symbol}`);
      }

      const signals = [];

      // Generate technical signals
      signals.push(...await this.generateTechnicalSignals(symbol, technicalData));
      
      // Generate fundamental signals
      signals.push(...await this.generateFundamentalSignals(symbol, stockData));
      
      // Generate sentiment signals
      signals.push(...await this.generateSentimentSignals(symbol, stockData));
      
      // Generate risk signals
      signals.push(...await this.generateRiskSignals(symbol, stockData));

      // Calculate aggregate signal strength
      const aggregateSignal = this.calculateAggregateSignal(signals);

      return {
        symbol,
        signals: signals.sort((a, b) => Math.abs(b.strength) - Math.abs(a.strength)),
        aggregateSignal,
        recommendation: this.getRecommendation(aggregateSignal),
        confidence: this.calculateConfidence(signals),
        lastUpdated: new Date().toISOString()
      };
    } catch (error) {
      console.error(`Error generating signals for ${symbol}:`, error);
      throw error;
    }
  }

  // Generate technical signals
  async generateTechnicalSignals(symbol, technicalData) {
    const signals = [];
    
    if (!technicalData) return signals;

    // Momentum Breakout Signal
    if (technicalData.rsi > 60 && technicalData.rsi < 80 && 
        technicalData.macd > technicalData.macd_signal && 
        technicalData.price_momentum_3m > 0.05) {
      signals.push({
        type: 'MOMENTUM_BREAKOUT',
        strength: 0.8,
        confidence: 0.75,
        description: 'Strong momentum with RSI in bullish range',
        triggers: ['RSI > 60', 'MACD > Signal', 'Positive 3M momentum'],
        timestamp: new Date().toISOString()
      });
    }

    // Mean Reversion Signal
    if (technicalData.rsi < 30 && technicalData.rsi > 20 && 
        technicalData.price_momentum_3m < -0.1) {
      signals.push({
        type: 'MEAN_REVERSION',
        strength: 0.6,
        confidence: 0.65,
        description: 'Oversold conditions with reversal potential',
        triggers: ['RSI < 30', 'Negative 3M momentum'],
        timestamp: new Date().toISOString()
      });
    }

    // Golden Cross Signal
    if (technicalData.sma_20 > technicalData.sma_50 && 
        technicalData.sma_50 > technicalData.sma_200) {
      signals.push({
        type: 'GOLDEN_CROSS',
        strength: 0.7,
        confidence: 0.7,
        description: 'Bullish moving average alignment',
        triggers: ['SMA20 > SMA50', 'SMA50 > SMA200'],
        timestamp: new Date().toISOString()
      });
    }

    // Bollinger Band Squeeze
    if (technicalData.bbands_upper && technicalData.bbands_lower) {
      const bandWidth = (technicalData.bbands_upper - technicalData.bbands_lower) / technicalData.bbands_middle;
      if (bandWidth < 0.1) {
        signals.push({
          type: 'MOMENTUM_BREAKOUT',
          strength: 0.5,
          confidence: 0.6,
          description: 'Bollinger Band squeeze indicating potential breakout',
          triggers: ['Narrow Bollinger Bands'],
          timestamp: new Date().toISOString()
        });
      }
    }

    return signals;
  }

  // Generate fundamental signals
  async generateFundamentalSignals(symbol, stockData) {
    const signals = [];

    // Value Opportunity Signal
    if (stockData.pe_ratio && stockData.pe_ratio < 15 && 
        stockData.pb_ratio && stockData.pb_ratio < 1.5 && 
        stockData.roe && stockData.roe > 0.1) {
      signals.push({
        type: 'VALUE_OPPORTUNITY',
        strength: 0.7,
        confidence: 0.8,
        description: 'Undervalued stock with strong ROE',
        triggers: ['PE < 15', 'PB < 1.5', 'ROE > 10%'],
        timestamp: new Date().toISOString()
      });
    }

    // Growth Acceleration Signal
    if (stockData.revenue_growth && stockData.revenue_growth > 0.15 && 
        stockData.earnings_growth && stockData.earnings_growth > 0.2 && 
        stockData.roe && stockData.roe > 0.15) {
      signals.push({
        type: 'GROWTH_ACCELERATION',
        strength: 0.8,
        confidence: 0.85,
        description: 'Strong revenue and earnings growth',
        triggers: ['Revenue Growth > 15%', 'Earnings Growth > 20%', 'ROE > 15%'],
        timestamp: new Date().toISOString()
      });
    }

    // Earnings Quality Signal
    if (stockData.operating_margin && stockData.operating_margin > 0.15 && 
        stockData.net_margin && stockData.net_margin > 0.1 && 
        stockData.current_ratio && stockData.current_ratio > 1.5) {
      signals.push({
        type: 'EARNINGS_SURPRISE',
        strength: 0.6,
        confidence: 0.7,
        description: 'High-quality earnings with strong margins',
        triggers: ['Operating Margin > 15%', 'Net Margin > 10%', 'Current Ratio > 1.5'],
        timestamp: new Date().toISOString()
      });
    }

    return signals;
  }

  // Generate sentiment signals
  async generateSentimentSignals(symbol, stockData) {
    const signals = [];

    // This would typically integrate with analyst data, news sentiment, etc.
    // For now, we'll use proxy indicators

    // Institutional Interest (using market cap as proxy)
    if (stockData.market_cap && stockData.market_cap > 10000000000) { // $10B+
      signals.push({
        type: 'INSTITUTIONAL_BUYING',
        strength: 0.4,
        confidence: 0.5,
        description: 'Large cap stock with institutional interest',
        triggers: ['Market Cap > $10B'],
        timestamp: new Date().toISOString()
      });
    }

    return signals;
  }

  // Generate risk signals
  async generateRiskSignals(symbol, stockData) {
    const signals = [];

    // High Debt Signal
    if (stockData.debt_to_equity && stockData.debt_to_equity > 1.0) {
      signals.push({
        type: 'RISK_ALERT',
        strength: -0.6,
        confidence: 0.8,
        description: 'High debt-to-equity ratio',
        triggers: ['Debt/Equity > 1.0'],
        timestamp: new Date().toISOString()
      });
    }

    // Liquidity Concern Signal
    if (stockData.current_ratio && stockData.current_ratio < 1.0) {
      signals.push({
        type: 'LIQUIDITY_CONCERN',
        strength: -0.7,
        confidence: 0.85,
        description: 'Low current ratio indicating liquidity issues',
        triggers: ['Current Ratio < 1.0'],
        timestamp: new Date().toISOString()
      });
    }

    // High Volatility Signal
    if (stockData.beta && stockData.beta > 2.0) {
      signals.push({
        type: 'RISK_ALERT',
        strength: -0.4,
        confidence: 0.6,
        description: 'High beta indicating increased volatility',
        triggers: ['Beta > 2.0'],
        timestamp: new Date().toISOString()
      });
    }

    return signals;
  }

  // Calculate aggregate signal strength
  calculateAggregateSignal(signals) {
    if (signals.length === 0) return 0;

    const weightedSum = signals.reduce((sum, signal) => {
      return sum + (signal.strength * signal.confidence);
    }, 0);

    const totalWeight = signals.reduce((sum, signal) => sum + signal.confidence, 0);

    return totalWeight > 0 ? weightedSum / totalWeight : 0;
  }

  // Calculate overall confidence
  calculateConfidence(signals) {
    if (signals.length === 0) return 0;
    
    const avgConfidence = signals.reduce((sum, signal) => sum + signal.confidence, 0) / signals.length;
    const signalDiversity = new Set(signals.map(s => s.type)).size;
    const diversityBonus = Math.min(0.2, signalDiversity * 0.05);
    
    return Math.min(1.0, avgConfidence + diversityBonus);
  }

  // Get recommendation based on aggregate signal
  getRecommendation(aggregateSignal) {
    if (aggregateSignal >= 0.6) return 'Strong Buy';
    if (aggregateSignal >= 0.3) return 'Buy';
    if (aggregateSignal >= 0.1) return 'Weak Buy';
    if (aggregateSignal >= -0.1) return 'Hold';
    if (aggregateSignal >= -0.3) return 'Weak Sell';
    if (aggregateSignal >= -0.6) return 'Sell';
    return 'Strong Sell';
  }

  // Get stock data from database
  async getStockData(symbol) {
    try {
      const result = await query(`
        SELECT 
          sf.*,
          sse.company_name,
          sse.sector,
          sse.exchange
        FROM stock_fundamentals sf
        JOIN stock_symbols_enhanced sse ON sf.symbol = sse.symbol
        WHERE sf.symbol = $1
      `, [symbol]);

      return result.rows[0] || null;
    } catch (error) {
      console.error('Error fetching stock data:', error);
      return null;
    }
  }

  // Get technical data from database
  async getTechnicalData(symbol) {
    try {
      const result = await query(`
        SELECT *
        FROM technical_data_daily
        WHERE symbol = $1
        ORDER BY date DESC
        LIMIT 1
      `, [symbol]);

      return result.rows[0] || null;
    } catch (error) {
      console.error('Error fetching technical data:', error);
      return null;
    }
  }

  // Generate signals for multiple stocks
  async generateSignalsForPortfolio(symbols) {
    const results = [];
    
    for (const symbol of symbols) {
      try {
        const signals = await this.generateSignalsForStock(symbol);
        results.push(signals);
      } catch (error) {
        console.error(`Error generating signals for ${symbol}:`, error);
        results.push({
          symbol,
          signals: [],
          aggregateSignal: 0,
          recommendation: 'Hold',
          confidence: 0,
          error: error.message
        });
      }
    }

    return results;
  }

  // Get market-wide signals
  async getMarketSignals() {
    try {
      // Get top stocks by market cap for market analysis
      const result = await query(`
        SELECT symbol
        FROM stock_fundamentals sf
        JOIN stock_symbols_enhanced sse ON sf.symbol = sse.symbol
        WHERE market_cap > 1000000000
        ORDER BY market_cap DESC
        LIMIT 50
      `);

      const symbols = result.rows.map(row => row.symbol);
      const portfolioSignals = await this.generateSignalsForPortfolio(symbols);
      
      // Calculate market sentiment
      const marketSentiment = this.calculateMarketSentiment(portfolioSignals);
      
      return {
        marketSentiment,
        topSignals: portfolioSignals
          .filter(s => Math.abs(s.aggregateSignal) > 0.3)
          .sort((a, b) => Math.abs(b.aggregateSignal) - Math.abs(a.aggregateSignal))
          .slice(0, 20),
        lastUpdated: new Date().toISOString()
      };
    } catch (error) {
      console.error('Error getting market signals:', error);
      throw error;
    }
  }

  // Calculate overall market sentiment
  calculateMarketSentiment(portfolioSignals) {
    const validSignals = portfolioSignals.filter(s => !s.error);
    
    if (validSignals.length === 0) {
      return {
        overall: 'Neutral',
        score: 0,
        bullishCount: 0,
        bearishCount: 0,
        neutralCount: 0
      };
    }

    const totalScore = validSignals.reduce((sum, s) => sum + s.aggregateSignal, 0);
    const avgScore = totalScore / validSignals.length;
    
    const bullishCount = validSignals.filter(s => s.aggregateSignal > 0.1).length;
    const bearishCount = validSignals.filter(s => s.aggregateSignal < -0.1).length;
    const neutralCount = validSignals.length - bullishCount - bearishCount;

    let overall = 'Neutral';
    if (avgScore > 0.2) overall = 'Bullish';
    else if (avgScore < -0.2) overall = 'Bearish';

    return {
      overall,
      score: avgScore,
      bullishCount,
      bearishCount,
      neutralCount,
      totalStocks: validSignals.length
    };
  }

  // Get signals by type
  async getSignalsByType(signalType, limit = 20) {
    try {
      // This would typically query a signals cache table
      // For now, we'll generate signals for top stocks and filter
      
      const result = await query(`
        SELECT symbol
        FROM stock_fundamentals sf
        JOIN stock_symbols_enhanced sse ON sf.symbol = sse.symbol
        WHERE market_cap > 100000000
        ORDER BY market_cap DESC
        LIMIT 100
      `);

      const symbols = result.rows.map(row => row.symbol);
      const portfolioSignals = await this.generateSignalsForPortfolio(symbols);
      
      const filteredSignals = portfolioSignals
        .filter(stock => stock.signals.some(signal => signal.type === signalType))
        .map(stock => ({
          symbol: stock.symbol,
          signal: stock.signals.find(signal => signal.type === signalType),
          aggregateSignal: stock.aggregateSignal,
          recommendation: stock.recommendation
        }))
        .sort((a, b) => Math.abs(b.signal.strength) - Math.abs(a.signal.strength))
        .slice(0, limit);

      return filteredSignals;
    } catch (error) {
      console.error('Error getting signals by type:', error);
      throw error;
    }
  }
}

module.exports = SignalEngine;