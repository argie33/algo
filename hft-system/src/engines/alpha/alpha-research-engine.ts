import { EventEmitter } from 'events';
import { Config } from '../../config';
import { createLogger } from '../../utils/logger';
import { Logger } from 'pino';
import { Signal, Order, Position, MarketTick, Quote } from '../../types';

export interface AlphaModel {
  id: string;
  name: string;
  type: 'momentum' | 'mean_reversion' | 'arbitrage' | 'news' | 'fundamental';
  enabled: boolean;
  weight: number;
  parameters: Record<string, any>;
  performance: {
    sharpe: number;
    pnl: number;
    winRate: number;
    maxDrawdown: number;
    lastUpdate: number;
  };
}

export interface AlphaSignal {
  modelId: string;
  symbol: string;
  signal: number; // -1 to 1
  confidence: number; // 0 to 1
  expectedReturn: number;
  expectedHoldingPeriod: number; // milliseconds
  riskScore: number;
  timestamp: number;
  metadata: Record<string, any>;
}

export interface ModelPrediction {
  symbol: string;
  prediction: number;
  confidence: number;
  features: Record<string, number>;
  timestamp: number;
}

/**
 * Alpha Research Engine - Multi-Model Signal Generation
 * Similar to Citadel's alpha research platform
 */
export class AlphaResearchEngine extends EventEmitter {
  private config: Config;
  private logger: Logger;
  private isRunning: boolean = false;
  
  // Alpha models
  private models: Map<string, AlphaModel> = new Map();
  private modelPredictions: Map<string, ModelPrediction[]> = new Map();
  private combinedSignals: Map<string, AlphaSignal> = new Map();
  
  // Performance tracking
  private modelPerformance: Map<string, any> = new Map();
  private signalHistory: Map<string, AlphaSignal[]> = new Map();
  
  // Real-time data
  private marketData: Map<string, MarketTick[]> = new Map();
  private quotes: Map<string, Quote> = new Map();
  private positions: Map<string, Position> = new Map();
  
  constructor(config: Config) {
    super();
    this.config = config;
    this.logger = createLogger('alpha-research-engine');
    
    this.initializeModels();
  }
  
  async initialize(): Promise<void> {
    this.logger.info('Initializing Alpha Research Engine');
    
    // Load historical model performance
    await this.loadModelPerformance();
    
    // Initialize feature engineering
    await this.initializeFeatureEngineering();
    
    this.logger.info('Alpha Research Engine initialized with models:', 
      Array.from(this.models.keys()));
  }
  
  async start(): Promise<void> {
    if (this.isRunning) return;
    
    this.logger.info('Starting Alpha Research Engine');
    this.isRunning = true;
    
    // Start model inference loop
    this.startModelInference();
    
    // Start signal combination
    this.startSignalCombination();
    
    // Start performance monitoring
    this.startPerformanceMonitoring();
    
    this.logger.info('Alpha Research Engine started');
  }
  
  async stop(): Promise<void> {
    if (!this.isRunning) return;
    
    this.logger.info('Stopping Alpha Research Engine');
    this.isRunning = false;
    
    // Save model performance
    await this.saveModelPerformance();
    
    this.logger.info('Alpha Research Engine stopped');
  }
  
  // Add market data for processing
  addMarketData(tick: MarketTick): void {
    const symbol = tick.symbol;
    
    if (!this.marketData.has(symbol)) {
      this.marketData.set(symbol, []);
    }
    
    const ticks = this.marketData.get(symbol)!;
    ticks.push(tick);
    
    // Keep only recent data for performance
    if (ticks.length > 10000) {
      ticks.splice(0, ticks.length - 5000);
    }
    
    // Trigger model inference for this symbol
    this.runModelInference(symbol);
  }
  
  addQuote(quote: Quote): void {
    this.quotes.set(quote.symbol, quote);
    
    // Update spread-based models
    this.updateSpreadModels(quote);
  }
  
  updatePosition(position: Position): void {
    this.positions.set(position.symbol, position);
    
    // Update position-aware models
    this.updatePositionAwareModels(position);
  }
  
  // Initialize alpha models
  private initializeModels(): void {
    // 1. Momentum Models
    this.models.set('momentum_breakout', {
      id: 'momentum_breakout',
      name: 'Momentum Breakout',
      type: 'momentum',
      enabled: true,
      weight: 0.15,
      parameters: {
        lookbackPeriod: 20,
        volumeThreshold: 1.5,
        priceThreshold: 0.002
      },
      performance: {
        sharpe: 1.8,
        pnl: 0,
        winRate: 0.52,
        maxDrawdown: 0.03,
        lastUpdate: Date.now()
      }
    });
    
    this.models.set('momentum_continuation', {
      id: 'momentum_continuation',
      name: 'Momentum Continuation',
      type: 'momentum',
      enabled: true,
      weight: 0.12,
      parameters: {
        trendStrength: 0.7,
        volumeConfirmation: true,
        timeDecay: 0.95
      },
      performance: {
        sharpe: 1.6,
        pnl: 0,
        winRate: 0.48,
        maxDrawdown: 0.04,
        lastUpdate: Date.now()
      }
    });
    
    // 2. Mean Reversion Models
    this.models.set('mean_reversion_short', {
      id: 'mean_reversion_short',
      name: 'Short-Term Mean Reversion',
      type: 'mean_reversion',
      enabled: true,
      weight: 0.18,
      parameters: {
        lookbackPeriod: 10,
        deviationThreshold: 2.0,
        volumeFilter: true
      },
      performance: {
        sharpe: 2.1,
        pnl: 0,
        winRate: 0.58,
        maxDrawdown: 0.02,
        lastUpdate: Date.now()
      }
    });
    
    this.models.set('mean_reversion_pairs', {
      id: 'mean_reversion_pairs',
      name: 'Pairs Trading Mean Reversion',
      type: 'mean_reversion',
      enabled: true,
      weight: 0.14,
      parameters: {
        correlationThreshold: 0.8,
        spreadThreshold: 2.5,
        halfLife: 5
      },
      performance: {
        sharpe: 1.9,
        pnl: 0,
        winRate: 0.55,
        maxDrawdown: 0.025,
        lastUpdate: Date.now()
      }
    });
    
    // 3. Arbitrage Models
    this.models.set('stat_arb', {
      id: 'stat_arb',
      name: 'Statistical Arbitrage',
      type: 'arbitrage',
      enabled: true,
      weight: 0.16,
      parameters: {
        universeSize: 500,
        lookbackDays: 60,
        entryThreshold: 2.0,
        exitThreshold: 0.5
      },
      performance: {
        sharpe: 2.3,
        pnl: 0,
        winRate: 0.62,
        maxDrawdown: 0.015,
        lastUpdate: Date.now()
      }
    });
    
    // 4. News/Event Models
    this.models.set('earnings_reaction', {
      id: 'earnings_reaction',
      name: 'Earnings Reaction',
      type: 'news',
      enabled: true,
      weight: 0.13,
      parameters: {
        surpriseThreshold: 0.05,
        reactionWindow: 300000, // 5 minutes
        volumeMultiplier: 2.0
      },
      performance: {
        sharpe: 1.4,
        pnl: 0,
        winRate: 0.45,
        maxDrawdown: 0.05,
        lastUpdate: Date.now()
      }
    });
    
    // 5. Fundamental Models  
    this.models.set('fundamental_quality', {
      id: 'fundamental_quality',
      name: 'Fundamental Quality',
      type: 'fundamental',
      enabled: true,
      weight: 0.12,
      parameters: {
        roe_threshold: 0.15,
        debt_ratio_max: 0.4,
        growth_rate_min: 0.1
      },
      performance: {
        sharpe: 1.2,
        pnl: 0,
        winRate: 0.53,
        maxDrawdown: 0.035,
        lastUpdate: Date.now()
      }
    });
  }
  
  // Run inference for all models on a symbol
  private async runModelInference(symbol: string): Promise<void> {
    const features = await this.extractFeatures(symbol);
    if (!features) return;
    
    const predictions: ModelPrediction[] = [];
    
    for (const [modelId, model] of this.models) {
      if (!model.enabled) continue;
      
      try {
        const prediction = await this.runSingleModel(model, symbol, features);
        if (prediction) {
          predictions.push(prediction);
        }
      } catch (error) {
        this.logger.error(`Error running model ${modelId}:`, error);
      }
    }
    
    this.modelPredictions.set(symbol, predictions);
    
    // Combine predictions into final signal
    this.combineSignals(symbol, predictions);
  }
  
  // Extract features for model inference
  private async extractFeatures(symbol: string): Promise<Record<string, number> | null> {
    const ticks = this.marketData.get(symbol);
    const quote = this.quotes.get(symbol);
    
    if (!ticks || ticks.length < 50 || !quote) {
      return null;
    }
    
    const recentTicks = ticks.slice(-100);
    const prices = recentTicks.map(t => t.price);
    const volumes = recentTicks.map(t => t.size);
    const timestamps = recentTicks.map(t => t.timestamp);
    
    // Technical features
    const sma_5 = this.calculateSMA(prices.slice(-5));
    const sma_20 = this.calculateSMA(prices.slice(-20));
    const sma_50 = this.calculateSMA(prices.slice(-50));
    const rsi = this.calculateRSI(prices, 14);
    const volatility = this.calculateVolatility(prices);
    
    // Volume features
    const volumeSMA = this.calculateSMA(volumes.slice(-20));
    const volumeRatio = volumes[volumes.length - 1] / volumeSMA;
    
    // Price features
    const currentPrice = prices[prices.length - 1];
    const priceChange = (currentPrice - prices[prices.length - 2]) / prices[prices.length - 2];
    const priceRange = (Math.max(...prices.slice(-20)) - Math.min(...prices.slice(-20))) / currentPrice;
    
    // Spread features
    const spread = (quote.ask_price - quote.bid_price) / quote.bid_price;
    const midPrice = (quote.ask_price + quote.bid_price) / 2;
    const priceVsMid = (currentPrice - midPrice) / midPrice;
    
    // Time features
    const timeOfDay = new Date().getHours() + new Date().getMinutes() / 60;
    const timeSinceLastTick = Date.now() - timestamps[timestamps.length - 1];
    
    return {
      // Technical indicators
      sma_5,
      sma_20, 
      sma_50,
      rsi,
      volatility,
      
      // Price momentum
      price_change: priceChange,
      price_vs_sma5: (currentPrice - sma_5) / sma_5,
      price_vs_sma20: (currentPrice - sma_20) / sma_20,
      price_range: priceRange,
      
      // Volume
      volume_ratio: volumeRatio,
      volume_normalized: volumes[volumes.length - 1] / Math.max(...volumes),
      
      // Microstructure
      spread_bps: spread * 10000,
      price_vs_mid: priceVsMid,
      bid_size: quote.bid_size,
      ask_size: quote.ask_size,
      size_imbalance: (quote.bid_size - quote.ask_size) / (quote.bid_size + quote.ask_size),
      
      // Time
      time_of_day: timeOfDay,
      time_since_tick: timeSinceLastTick
    };
  }
  
  // Run a single model
  private async runSingleModel(
    model: AlphaModel, 
    symbol: string, 
    features: Record<string, number>
  ): Promise<ModelPrediction | null> {
    
    let prediction = 0;
    let confidence = 0;
    
    switch (model.type) {
      case 'momentum':
        ({ prediction, confidence } = this.runMomentumModel(model, features));
        break;
      case 'mean_reversion':
        ({ prediction, confidence } = this.runMeanReversionModel(model, features));
        break;
      case 'arbitrage':
        ({ prediction, confidence } = this.runArbitrageModel(model, features));
        break;
      case 'news':
        ({ prediction, confidence } = this.runNewsModel(model, features));
        break;
      case 'fundamental':
        ({ prediction, confidence } = this.runFundamentalModel(model, features));
        break;
    }
    
    if (Math.abs(prediction) < 0.01) {
      return null; // No signal
    }
    
    return {
      symbol,
      prediction: prediction * model.weight, // Apply model weight
      confidence,
      features,
      timestamp: Date.now()
    };
  }
  
  // Momentum model implementation
  private runMomentumModel(model: AlphaModel, features: Record<string, number>): 
    { prediction: number; confidence: number } {
    
    const params = model.parameters;
    let signal = 0;
    let confidence = 0;
    
    if (model.id === 'momentum_breakout') {
      // Breakout detection
      const priceVsSMA = features.price_vs_sma20;
      const volumeRatio = features.volume_ratio;
      const volatility = features.volatility;
      
      if (priceVsSMA > params.priceThreshold && volumeRatio > params.volumeThreshold) {
        signal = Math.tanh(priceVsSMA * 2) * Math.min(volumeRatio / 2, 1);
        confidence = Math.min(volatility * 10, 1);
      } else if (priceVsSMA < -params.priceThreshold && volumeRatio > params.volumeThreshold) {
        signal = Math.tanh(priceVsSMA * 2) * Math.min(volumeRatio / 2, 1);
        confidence = Math.min(volatility * 10, 1);
      }
    } else if (model.id === 'momentum_continuation') {
      // Trend continuation
      const shortTrend = features.price_vs_sma5;
      const longTrend = features.price_vs_sma20;
      const volumeConfirm = features.volume_ratio > 1.2;
      
      if (shortTrend > 0 && longTrend > 0 && volumeConfirm) {
        signal = Math.tanh((shortTrend + longTrend) * params.trendStrength);
        confidence = Math.min(Math.abs(shortTrend) + Math.abs(longTrend), 1);
      } else if (shortTrend < 0 && longTrend < 0 && volumeConfirm) {
        signal = Math.tanh((shortTrend + longTrend) * params.trendStrength);
        confidence = Math.min(Math.abs(shortTrend) + Math.abs(longTrend), 1);
      }
    }
    
    return { prediction: signal, confidence };
  }
  
  // Mean reversion model implementation
  private runMeanReversionModel(model: AlphaModel, features: Record<string, number>): 
    { prediction: number; confidence: number } {
    
    const params = model.parameters;
    let signal = 0;
    let confidence = 0;
    
    if (model.id === 'mean_reversion_short') {
      // Short-term mean reversion
      const rsi = features.rsi;
      const priceVsSMA = features.price_vs_sma5;
      const volumeFilter = !params.volumeFilter || features.volume_ratio > 0.8;
      
      if (rsi > 70 && priceVsSMA > 0.01 && volumeFilter) {
        signal = -Math.tanh((rsi - 70) / 10); // Sell signal
        confidence = Math.min((rsi - 70) / 30, 1);
      } else if (rsi < 30 && priceVsSMA < -0.01 && volumeFilter) {
        signal = -Math.tanh((rsi - 30) / 10); // Buy signal
        confidence = Math.min((30 - rsi) / 30, 1);
      }
    }
    
    return { prediction: signal, confidence };
  }
  
  // Arbitrage model implementation
  private runArbitrageModel(model: AlphaModel, features: Record<string, number>): 
    { prediction: number; confidence: number } {
    
    // Statistical arbitrage based on price vs moving averages and volatility
    const priceVsMA = features.price_vs_sma20;
    const volatility = features.volatility;
    const spread = features.spread_bps;
    
    let signal = 0;
    let confidence = 0;
    
    // Look for mean reversion opportunities with tight spreads
    if (Math.abs(priceVsMA) > 0.02 && spread < 5) { // 5 bps spread threshold
      signal = -Math.tanh(priceVsMA * 3); // Fade the move
      confidence = Math.min(Math.abs(priceVsMA) * 10, 1);
    }
    
    return { prediction: signal, confidence };
  }
  
  // News model implementation
  private runNewsModel(model: AlphaModel, features: Record<string, number>): 
    { prediction: number; confidence: number } {
    
    // Simplified news reaction model based on volume and volatility spikes
    const volumeRatio = features.volume_ratio;
    const volatility = features.volatility;
    const priceChange = features.price_change;
    
    let signal = 0;
    let confidence = 0;
    
    // Detect news events via volume/volatility spikes
    if (volumeRatio > 3 && volatility > 0.02) {
      // Momentum following news
      signal = Math.tanh(priceChange * 5);
      confidence = Math.min(volumeRatio / 5, 1);
    }
    
    return { prediction: signal, confidence };
  }
  
  // Fundamental model implementation
  private runFundamentalModel(model: AlphaModel, features: Record<string, number>): 
    { prediction: number; confidence: number } {
    
    // Basic technical proxy for fundamental signals
    const longTermTrend = features.price_vs_sma50;
    const volatility = features.volatility;
    
    let signal = 0;
    let confidence = 0;
    
    // Long-term trend following with low volatility preference
    if (volatility < 0.02) { // Low volatility
      signal = Math.tanh(longTermTrend * 0.5);
      confidence = Math.min(Math.abs(longTermTrend), 0.5);
    }
    
    return { prediction: signal, confidence };
  }
  
  // Combine multiple model predictions into final signal
  private combineSignals(symbol: string, predictions: ModelPrediction[]): void {
    if (predictions.length === 0) return;
    
    let weightedSignal = 0;
    let totalWeight = 0;
    let maxConfidence = 0;
    
    for (const pred of predictions) {
      const weight = this.models.get(pred.symbol.split('_')[0])?.weight || 0;
      weightedSignal += pred.prediction * pred.confidence;
      totalWeight += pred.confidence;
      maxConfidence = Math.max(maxConfidence, pred.confidence);
    }
    
    if (totalWeight === 0) return;
    
    const finalSignal = weightedSignal / totalWeight;
    
    const alphaSignal: AlphaSignal = {
      modelId: 'combined',
      symbol,
      signal: Math.max(-1, Math.min(1, finalSignal)), // Clamp to [-1, 1]
      confidence: maxConfidence,
      expectedReturn: Math.abs(finalSignal) * 0.001, // 0.1% per unit signal
      expectedHoldingPeriod: 60000, // 1 minute
      riskScore: Math.abs(finalSignal) * 0.5,
      timestamp: Date.now(),
      metadata: {
        modelCount: predictions.length,
        totalWeight
      }
    };
    
    this.combinedSignals.set(symbol, alphaSignal);
    
    // Add to history
    if (!this.signalHistory.has(symbol)) {
      this.signalHistory.set(symbol, []);
    }
    const history = this.signalHistory.get(symbol)!;
    history.push(alphaSignal);
    
    // Keep only recent signals
    if (history.length > 1000) {
      history.splice(0, history.length - 500);
    }
    
    // Emit signal
    this.emit('alpha_signal', alphaSignal);
  }
  
  // Utility functions
  private calculateSMA(prices: number[]): number {
    return prices.reduce((sum, price) => sum + price, 0) / prices.length;
  }
  
  private calculateRSI(prices: number[], period: number): number {
    if (prices.length < period + 1) return 50;
    
    const changes = [];
    for (let i = 1; i < prices.length; i++) {
      changes.push(prices[i] - prices[i - 1]);
    }
    
    const gains = changes.slice(-period).filter(c => c > 0);
    const losses = changes.slice(-period).filter(c => c < 0).map(c => Math.abs(c));
    
    const avgGain = gains.length > 0 ? gains.reduce((sum, g) => sum + g, 0) / period : 0;
    const avgLoss = losses.length > 0 ? losses.reduce((sum, l) => sum + l, 0) / period : 0;
    
    if (avgLoss === 0) return 100;
    
    const rs = avgGain / avgLoss;
    return 100 - (100 / (1 + rs));
  }
  
  private calculateVolatility(prices: number[]): number {
    if (prices.length < 2) return 0;
    
    const returns = [];
    for (let i = 1; i < prices.length; i++) {
      returns.push((prices[i] - prices[i - 1]) / prices[i - 1]);
    }
    
    const mean = returns.reduce((sum, r) => sum + r, 0) / returns.length;
    const variance = returns.reduce((sum, r) => sum + Math.pow(r - mean, 2), 0) / returns.length;
    
    return Math.sqrt(variance);
  }
  
  // Update models based on spread changes
  private updateSpreadModels(quote: Quote): void {
    // Update models that care about bid-ask spread
    // This would trigger recalculation of spread-sensitive models
  }
  
  // Update models based on position changes
  private updatePositionAwareModels(position: Position): void {
    // Update models that consider current positions
    // This would modify signals based on existing exposure
  }
  
  // Model performance monitoring and management
  private startModelInference(): void {
    // This would run continuous model inference as data comes in
  }
  
  private startSignalCombination(): void {
    // This would run signal combination logic
  }
  
  private startPerformanceMonitoring(): void {
    // This would track model performance and adjust weights
  }
  
  private async loadModelPerformance(): Promise<void> {
    // Load historical model performance from database
  }
  
  private async saveModelPerformance(): Promise<void> {
    // Save model performance to database
  }
  
  private async initializeFeatureEngineering(): Promise<void> {
    // Initialize feature calculation engines
  }
  
  // Public interface
  getActiveModels(): AlphaModel[] {
    return Array.from(this.models.values()).filter(m => m.enabled);
  }
  
  getCurrentSignal(symbol: string): AlphaSignal | undefined {
    return this.combinedSignals.get(symbol);
  }
  
  getModelPerformance(modelId: string): any {
    return this.modelPerformance.get(modelId);
  }
  
  updateModelWeight(modelId: string, weight: number): void {
    const model = this.models.get(modelId);
    if (model) {
      model.weight = weight;
      this.logger.info(`Updated model ${modelId} weight to ${weight}`);
    }
  }
  
  enableModel(modelId: string): void {
    const model = this.models.get(modelId);
    if (model) {
      model.enabled = true;
      this.logger.info(`Enabled model ${modelId}`);
    }
  }
  
  disableModel(modelId: string): void {
    const model = this.models.get(modelId);
    if (model) {
      model.enabled = false;
      this.logger.info(`Disabled model ${modelId}`);
    }
  }
}
