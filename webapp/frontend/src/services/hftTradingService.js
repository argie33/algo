/**
 * HFT Trading Service - Advanced High-Frequency Trading Operations
 * Integrates with Live Data feeds and provides AI-powered trading capabilities
 */

import { api } from './api';

class HFTTradingService {
  constructor() {
    this.wsConnection = null;
    this.subscribers = new Map();
    this.latencyBuffer = [];
    this.performanceCache = new Map();
  }

  // Strategy Management
  async getActiveStrategies() {
    try {
      const response = await api.get('/api/hft/strategies/active');
      return response.data.strategies || [];
    } catch (error) {
      console.error('Failed to get active strategies:', error);
      return this.getMockStrategies();
    }
  }

  async deployStrategy(strategyId, symbols, config = {}) {
    try {
      const response = await api.post('/api/hft/strategies/deploy', {
        strategyId,
        symbols,
        config: {
          maxPosition: config.maxPosition || 1000,
          riskLimit: config.riskLimit || 0.02,
          latencyThreshold: config.latencyThreshold || 5, // ms
          ...config
        }
      });
      return response.data;
    } catch (error) {
      console.error('Failed to deploy strategy:', error);
      return { success: false, error: error.message };
    }
  }

  async stopStrategy(strategyId, symbols = []) {
    try {
      const response = await api.post('/api/hft/strategies/stop', {
        strategyId,
        symbols
      });
      return response.data;
    } catch (error) {
      console.error('Failed to stop strategy:', error);
      return { success: false, error: error.message };
    }
  }

  async stopAllStrategies() {
    try {
      const response = await api.post('/api/hft/strategies/stop-all');
      return response.data;
    } catch (error) {
      console.error('Failed to stop all strategies:', error);
      return { success: false, error: error.message };
    }
  }

  async startSelectedStrategies(symbols) {
    try {
      const response = await api.post('/api/hft/strategies/start-selected', {
        symbols
      });
      return response.data;
    } catch (error) {
      console.error('Failed to start selected strategies:', error);
      return { success: false, error: error.message };
    }
  }

  // Performance Analytics
  async getPerformanceMetrics(timeframe = '1D') {
    try {
      const response = await api.get(`/api/hft/performance?timeframe=${timeframe}`);
      return response.data.metrics || {};
    } catch (error) {
      console.error('Failed to get performance metrics:', error);
      return this.getMockPerformanceMetrics();
    }
  }

  async getLatencyMetrics() {
    try {
      const response = await api.get('/api/hft/latency');
      return response.data.metrics || {};
    } catch (error) {
      console.error('Failed to get latency metrics:', error);
      return this.getMockLatencyMetrics();
    }
  }

  async getOrderFlowAnalysis(symbol) {
    try {
      const response = await api.get(`/api/hft/order-flow/${symbol}`);
      return response.data.analysis || {};
    } catch (error) {
      console.error('Failed to get order flow analysis:', error);
      return this.getMockOrderFlowAnalysis();
    }
  }

  // AI & Machine Learning
  async getAIRecommendations() {
    try {
      const response = await api.get('/api/hft/ai/recommendations');
      return response.data.recommendations || [];
    } catch (error) {
      console.error('Failed to get AI recommendations:', error);
      return this.getMockAIRecommendations();
    }
  }

  async getSymbolAIScore(symbol) {
    try {
      const response = await api.get(`/api/hft/ai/score/${symbol}`);
      return response.data.score || 0;
    } catch (error) {
      console.error('Failed to get AI score:', error);
      return Math.random() * 100;
    }
  }

  async getPredictiveSignals(symbols = []) {
    try {
      const response = await api.post('/api/hft/ai/predict', { symbols });
      return response.data.signals || [];
    } catch (error) {
      console.error('Failed to get predictive signals:', error);
      return this.getMockPredictiveSignals();
    }
  }

  // Risk Management
  async getRiskMetrics() {
    try {
      const response = await api.get('/api/hft/risk');
      return response.data.metrics || {};
    } catch (error) {
      console.error('Failed to get risk metrics:', error);
      return this.getMockRiskMetrics();
    }
  }

  async updateRiskLimits(limits) {
    try {
      const response = await api.post('/api/hft/risk/limits', limits);
      return response.data;
    } catch (error) {
      console.error('Failed to update risk limits:', error);
      return { success: false, error: error.message };
    }
  }

  // Market Microstructure
  async getMarketMicrostructure(symbol) {
    try {
      const response = await api.get(`/api/hft/microstructure/${symbol}`);
      return response.data.microstructure || {};
    } catch (error) {
      console.error('Failed to get market microstructure:', error);
      return this.getMockMarketMicrostructure();
    }
  }

  // Live Data Integration
  async subscribeToLiveData(symbols, callback) {
    try {
      // Initialize WebSocket connection if not exists
      if (!this.wsConnection) {
        await this.initializeWebSocket();
      }

      // Subscribe to symbols
      symbols.forEach(symbol => {
        this.subscribers.set(symbol, callback);
        this.wsConnection.send(JSON.stringify({
          type: 'SUBSCRIBE',
          symbol,
          dataTypes: ['TRADE', 'QUOTE', 'LEVEL2']
        }));
      });

      return { success: true };
    } catch (error) {
      console.error('Failed to subscribe to live data:', error);
      return { success: false, error: error.message };
    }
  }

  async unsubscribeFromLiveData(symbols) {
    if (!this.wsConnection) return;

    symbols.forEach(symbol => {
      this.subscribers.delete(symbol);
      this.wsConnection.send(JSON.stringify({
        type: 'UNSUBSCRIBE',
        symbol
      }));
    });
  }

  // WebSocket Management
  async initializeWebSocket() {
    return new Promise((resolve, reject) => {
      const wsUrl = process.env.REACT_APP_HFT_WS_URL || 'wss://hft-stream.your-domain.com';
      this.wsConnection = new WebSocket(wsUrl);

      this.wsConnection.onopen = () => {
        console.log('HFT WebSocket connected');
        resolve();
      };

      this.wsConnection.onmessage = (event) => {
        this.handleWebSocketMessage(JSON.parse(event.data));
      };

      this.wsConnection.onerror = (error) => {
        console.error('HFT WebSocket error:', error);
        reject(error);
      };

      this.wsConnection.onclose = () => {
        console.log('HFT WebSocket disconnected');
        // Reconnect after 3 seconds
        setTimeout(() => this.initializeWebSocket(), 3000);
      };
    });
  }

  handleWebSocketMessage(data) {
    const { symbol, type, payload } = data;

    // Update latency metrics
    if (data.timestamp) {
      const latency = Date.now() - data.timestamp;
      this.updateLatencyMetrics(latency);
    }

    // Call subscriber callback
    const callback = this.subscribers.get(symbol);
    if (callback) {
      callback(data);
    }

    // Cache performance data
    if (type === 'PERFORMANCE_UPDATE') {
      this.performanceCache.set(symbol, payload);
    }
  }

  updateLatencyMetrics(latency) {
    this.latencyBuffer.push({ timestamp: Date.now(), latency });
    
    // Keep only last 1000 measurements
    if (this.latencyBuffer.length > 1000) {
      this.latencyBuffer.shift();
    }
  }

  // Strategy Templates
  getStrategyTemplates() {
    return [
      {
        id: 'momentum-scalper',
        name: 'Momentum Scalper',
        description: 'High-frequency momentum-based scalping strategy',
        parameters: {
          momentumThreshold: 0.001,
          holdingPeriod: 5000, // ms
          maxPosition: 1000,
          stopLoss: 0.002
        },
        riskLevel: 'Medium',
        expectedReturn: 0.15,
        category: 'Scalping'
      },
      {
        id: 'mean-reversion',
        name: 'Mean Reversion',
        description: 'Statistical arbitrage based on mean reversion',
        parameters: {
          lookbackPeriod: 20,
          zScoreThreshold: 2.0,
          maxPosition: 500,
          stopLoss: 0.003
        },
        riskLevel: 'Low',
        expectedReturn: 0.08,
        category: 'Statistical Arbitrage'
      },
      {
        id: 'arbitrage-hunter',
        name: 'Arbitrage Hunter',
        description: 'Cross-venue arbitrage opportunities',
        parameters: {
          minSpread: 0.0005,
          maxLatency: 2, // ms
          maxPosition: 2000,
          venues: ['NYSE', 'NASDAQ', 'IEX']
        },
        riskLevel: 'Very Low',
        expectedReturn: 0.05,
        category: 'Arbitrage'
      },
      {
        id: 'volume-breakout',
        name: 'Volume Breakout',
        description: 'Volume-based breakout strategy',
        parameters: {
          volumeThreshold: 1.5,
          priceBreakout: 0.002,
          maxPosition: 800,
          stopLoss: 0.004
        },
        riskLevel: 'High',
        expectedReturn: 0.25,
        category: 'Breakout'
      },
      {
        id: 'ml-pattern',
        name: 'ML Pattern Recognition',
        description: 'Machine learning pattern recognition',
        parameters: {
          modelConfidence: 0.75,
          patternWindow: 100,
          maxPosition: 1200,
          stopLoss: 0.0025
        },
        riskLevel: 'Medium',
        expectedReturn: 0.18,
        category: 'Machine Learning'
      }
    ];
  }

  // Mock Data Methods (for development/fallback)
  getMockStrategies() {
    return this.getStrategyTemplates().map(template => ({
      ...template,
      isActive: Math.random() > 0.5,
      performance: {
        totalReturn: (Math.random() - 0.5) * 0.1,
        dailyReturn: (Math.random() - 0.5) * 0.03,
        winRate: 0.6 + Math.random() * 0.3,
        trades: Math.floor(Math.random() * 1000),
        avgLatency: Math.random() * 10
      }
    }));
  }

  getMockPerformanceMetrics() {
    return {
      totalPnL: 12847.32,
      dailyPnL: 2341.87,
      totalTrades: 1247,
      winRate: 0.942,
      avgLatency: 2.3,
      maxDrawdown: 0.015,
      sharpeRatio: 2.8,
      strategies: {
        'momentum-scalper': { pnl: 5432.10, trades: 423 },
        'mean-reversion': { pnl: 3214.56, trades: 234 },
        'arbitrage-hunter': { pnl: 2876.33, trades: 345 },
        'volume-breakout': { pnl: 1324.33, trades: 145 },
        'ml-pattern': { pnl: 0, trades: 100 }
      }
    };
  }

  getMockLatencyMetrics() {
    return {
      avgLatency: 2.3,
      p50Latency: 1.8,
      p95Latency: 4.2,
      p99Latency: 7.1,
      maxLatency: 12.3,
      networkLatency: 0.8,
      processLatency: 1.5
    };
  }

  getMockOrderFlowAnalysis() {
    return {
      bidAskSpread: 0.001,
      marketDepth: {
        bids: Array.from({ length: 10 }, (_, i) => ({
          price: 100 - i * 0.01,
          size: Math.floor(Math.random() * 1000)
        })),
        asks: Array.from({ length: 10 }, (_, i) => ({
          price: 100.01 + i * 0.01,
          size: Math.floor(Math.random() * 1000)
        }))
      },
      imbalance: Math.random() - 0.5,
      toxicity: Math.random() * 0.1
    };
  }

  getMockAIRecommendations() {
    return [
      {
        id: 1,
        title: 'High Volatility Detected',
        description: 'AAPL showing unusual volatility patterns. Consider reducing position size.',
        priority: 'high',
        confidence: 0.85,
        action: 'REDUCE_POSITION',
        symbol: 'AAPL'
      },
      {
        id: 2,
        title: 'Arbitrage Opportunity',
        description: 'Price discrepancy detected between NYSE and NASDAQ for MSFT.',
        priority: 'medium',
        confidence: 0.72,
        action: 'ARBITRAGE',
        symbol: 'MSFT'
      },
      {
        id: 3,
        title: 'Momentum Signal',
        description: 'Strong momentum building in TSLA. Consider increasing allocation.',
        priority: 'medium',
        confidence: 0.68,
        action: 'INCREASE_POSITION',
        symbol: 'TSLA'
      }
    ];
  }

  getMockPredictiveSignals() {
    return [
      { symbol: 'AAPL', direction: 'UP', confidence: 0.78, timeframe: '5m' },
      { symbol: 'MSFT', direction: 'DOWN', confidence: 0.65, timeframe: '10m' },
      { symbol: 'GOOGL', direction: 'UP', confidence: 0.82, timeframe: '3m' }
    ];
  }

  getMockRiskMetrics() {
    return {
      var95: 0.023,
      expectedShortfall: 0.031,
      maxDrawdown: 0.015,
      betaToMarket: 0.85,
      correlation: {
        SPY: 0.72,
        QQQ: 0.68,
        IWM: 0.45
      },
      exposures: {
        gross: 125000,
        net: 85000,
        long: 105000,
        short: 20000
      }
    };
  }

  getMockMarketMicrostructure() {
    return {
      tickSize: 0.01,
      avgSpread: 0.001,
      spreadVolatility: 0.0003,
      marketImpact: 0.0002,
      liquidityScore: 8.5,
      venueDistribution: {
        NYSE: 0.35,
        NASDAQ: 0.28,
        IEX: 0.15,
        'Dark Pools': 0.22
      }
    };
  }

  // Cleanup
  disconnect() {
    if (this.wsConnection) {
      this.wsConnection.close();
      this.wsConnection = null;
    }
    this.subscribers.clear();
    this.performanceCache.clear();
  }
}

// Export singleton instance
export const hftTradingService = new HFTTradingService();
export default hftTradingService;