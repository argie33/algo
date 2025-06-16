import { BaseEngine, Signal, SignalType, SignalSource, MarketTick, Quote, Trade, Bar } from '../../types';
import { Config } from '../../config';
import { Logger } from 'pino';
import { v4 as uuidv4 } from 'uuid';

export interface SignalConfig {
  enabledStrategies: string[];
  signalThreshold: number;
  maxSignalsPerSecond: number;
  cooldownPeriod: number;
}

/**
 * Advanced signal generation engine integrating fundamental and technical analysis
 * Leverages existing fundamental data infrastructure for signal generation
 */
export class SignalEngine extends BaseEngine {
  private priceData: Map<string, number> = new Map();
  private quoteData: Map<string, Quote> = new Map();
  private signalHistory: Map<string, Signal[]> = new Map();
  private lastSignalTime: Map<string, number> = new Map();
  private fundamentalData: Map<string, any> = new Map();
  private technicalIndicators: Map<string, any> = new Map();
  
  private readonly signalConfig: SignalConfig = {
    enabledStrategies: ['momentum', 'mean_reversion', 'fundamental', 'technical'],
    signalThreshold: 0.6,
    maxSignalsPerSecond: 100,
    cooldownPeriod: 1000 // 1 seconds
  };

  constructor(config: Config, logger: Logger) {
    super('SignalEngine', config, logger);
  }

  async initialize(): Promise<void> {
    this.logger.info('Initializing Signal Engine...');
    
    try {
      // Initialize signal storage for each symbol
      const enabledSymbols = this.config.getEnabledSymbols();
      enabledSymbols.forEach(symbolConfig => {
        this.signalHistory.set(symbolConfig.symbol, []);
        this.lastSignalTime.set(symbolConfig.symbol, 0);
      });
      
      // Load fundamental data from existing infrastructure
      await this.loadFundamentalData();
      
      this.logger.info('Signal Engine initialized successfully');
      
    } catch (error) {
      this.logger.error({ error }, 'Failed to initialize Signal Engine');
      throw error;
    }
  }

  async start(): Promise<void> {
    if (this.isRunning) return;
    
    this.logger.info('Starting Signal Engine...');
    this.isRunning = true;
    
    // Start periodic fundamental data refresh
    setInterval(() => {
      this.refreshFundamentalData();
    }, 60000); // Refresh every minute
    
    this.logger.info('Signal Engine started successfully');
  }

  async stop(): Promise<void> {
    if (!this.isRunning) return;
    
    this.logger.info('Stopping Signal Engine...');
    this.isRunning = false;
    
    this.logger.info('Signal Engine stopped');
  }

  /**
   * Process market tick data for signal generation
   */
  processTick(tick: MarketTick): void {
    if (!this.isRunning) return;
    
    try {
      this.priceData.set(tick.symbol, tick.price);
      this.updateMetric(`${tick.symbol}_last_price`, tick.price);
      
      // Generate signals based on tick data
      this.generateTickSignals(tick);
      
      this.incrementMetric('ticks_processed');
      
    } catch (error) {
      this.logger.error({ error, tick }, 'Failed to process tick');
      this.incrementMetric('tick_processing_errors');
    }
  }

  /**
   * Process quote data for signal generation
   */
  processQuote(quote: Quote): void {
    if (!this.isRunning) return;
    
    try {
      this.quoteData.set(quote.symbol, quote);
      
      // Generate signals based on quote data
      this.generateQuoteSignals(quote);
      
      this.incrementMetric('quotes_processed');
      
    } catch (error) {
      this.logger.error({ error, quote }, 'Failed to process quote');
      this.incrementMetric('quote_processing_errors');
    }
  }

  /**
   * Process trade data for signal generation
   */
  processTrade(trade: Trade): void {
    if (!this.isRunning) return;
    
    try {
      // Update price data
      this.priceData.set(trade.symbol, trade.price);
      
      // Generate signals based on trade data
      this.generateTradeSignals(trade);
      
      this.incrementMetric('trades_processed');
      
    } catch (error) {
      this.logger.error({ error, trade }, 'Failed to process trade');
      this.incrementMetric('trade_processing_errors');
    }
  }

  /**
   * Generate signals from tick data
   */
  private generateTickSignals(tick: MarketTick): void {
    const strategies = ['momentum', 'volume_spike'];
    
    strategies.forEach(strategy => {
      const signal = this.generateSignal(tick.symbol, strategy, {
        price: tick.price,
        size: tick.size,
        timestamp: tick.timestamp
      });
      
      if (signal) {
        this.emitSignal(signal);
      }
    });
  }

  /**
   * Generate signals from quote data
   */
  private generateQuoteSignals(quote: Quote): void {
    const spread = quote.ask_price - quote.bid_price;
    const midPrice = (quote.ask_price + quote.bid_price) / 2;
    
    // Spread-based signals
    if (spread > 0) {
      const signal = this.generateSignal(quote.symbol, 'spread_analysis', {
        spread,
        midPrice,
        bidSize: quote.bid_size,
        askSize: quote.ask_size,
        timestamp: quote.timestamp
      });
      
      if (signal) {
        this.emitSignal(signal);
      }
    }
  }

  /**
   * Generate signals from trade data
   */
  private generateTradeSignals(trade: Trade): void {
    const strategies = ['volume_weighted', 'tape_reading'];
    
    strategies.forEach(strategy => {
      const signal = this.generateSignal(trade.symbol, strategy, {
        price: trade.price,
        size: trade.size,
        timestamp: trade.timestamp,
        exchange: trade.exchange
      });
      
      if (signal) {
        this.emitSignal(signal);
      }
    });
  }

  /**
   * Core signal generation logic
   */
  private generateSignal(symbol: string, strategy: string, data: any): Signal | null {
    // Check cooldown period
    const lastSignalTime = this.lastSignalTime.get(symbol) || 0;
    const now = Date.now();
    
    if (now - lastSignalTime < this.signalConfig.cooldownPeriod) {
      return null;
    }
    
    let signalType: SignalType = SignalType.HOLD;
    let strength = 0;
    let source: SignalSource = SignalSource.TECHNICAL;
    let metadata: any = { strategy, ...data };
    
    // Strategy-specific signal generation
    switch (strategy) {
      case 'momentum':
        ({ signalType, strength } = this.generateMomentumSignal(symbol, data));
        source = SignalSource.TECHNICAL;
        break;
        
      case 'mean_reversion':
        ({ signalType, strength } = this.generateMeanReversionSignal(symbol, data));
        source = SignalSource.TECHNICAL;
        break;
        
      case 'fundamental':
        ({ signalType, strength } = this.generateFundamentalSignal(symbol, data));
        source = SignalSource.FUNDAMENTAL;
        break;
        
      case 'volume_spike':
        ({ signalType, strength } = this.generateVolumeSpikeSignal(symbol, data));
        source = SignalSource.TECHNICAL;
        break;
        
      case 'spread_analysis':
        ({ signalType, strength } = this.generateSpreadSignal(symbol, data));
        source = SignalSource.TECHNICAL;
        break;
        
      default:
        return null;
    }
    
    // Check if signal meets threshold
    if (strength < this.signalConfig.signalThreshold) {
      return null;
    }
    
    const signal: Signal = {
      id: uuidv4(),
      symbol,
      type: signalType,
      source,
      strength,
      timestamp: now,
      metadata
    };
    
    return signal;
  }

  /**
   * Generate momentum signal
   */
  private generateMomentumSignal(symbol: string, data: any): { signalType: SignalType; strength: number } {
    const currentPrice = data.price;
    const previousPrice = this.getPreviousPrice(symbol);
    
    if (!previousPrice) {
      return { signalType: SignalType.HOLD, strength: 0 };
    }
    
    const priceChange = (currentPrice - previousPrice) / previousPrice;
    const absChange = Math.abs(priceChange);
    
    // Momentum threshold
    const momentumThreshold = 0.002; // 0.2%
    
    if (absChange > momentumThreshold) {
      const signalType = priceChange > 0 ? SignalType.BUY : SignalType.SELL;
      const strength = Math.min(absChange * 10, 1.0); // Scale to 0-1
      
      return { signalType, strength };
    }
    
    return { signalType: SignalType.HOLD, strength: 0 };
  }

  /**
   * Generate mean reversion signal
   */
  private generateMeanReversionSignal(symbol: string, data: any): { signalType: SignalType; strength: number } {
    // This would use historical price data to determine if price is extended
    // For now, simplified logic
    const currentPrice = data.price;
    const sma = this.getSimpleMovingAverage(symbol, 20);
    
    if (!sma) {
      return { signalType: SignalType.HOLD, strength: 0 };
    }
    
    const deviation = (currentPrice - sma) / sma;
    const absDeviation = Math.abs(deviation);
    
    // Mean reversion threshold
    const reversionThreshold = 0.01; // 1%
    
    if (absDeviation > reversionThreshold) {
      // Signal opposite to current deviation
      const signalType = deviation > 0 ? SignalType.SELL : SignalType.BUY;
      const strength = Math.min(absDeviation * 5, 1.0);
      
      return { signalType, strength };
    }
    
    return { signalType: SignalType.HOLD, strength: 0 };
  }

  /**
   * Generate fundamental signal using existing fundamental data
   */
  private generateFundamentalSignal(symbol: string, data: any): { signalType: SignalType; strength: number } {
    const fundamentalData = this.fundamentalData.get(symbol);
    
    if (!fundamentalData) {
      return { signalType: SignalType.HOLD, strength: 0 };
    }
    
    // Example: Use P/E ratio and earnings growth
    const peRatio = fundamentalData.pe_ratio;
    const earningsGrowth = fundamentalData.earnings_growth;
    const currentPrice = data.price;
    
    let score = 0;
    
    // P/E analysis
    if (peRatio && peRatio < 15) score += 0.3; // Undervalued
    if (peRatio && peRatio > 25) score -= 0.3; // Overvalued
    
    // Earnings growth analysis
    if (earningsGrowth && earningsGrowth > 0.1) score += 0.4; // Growing
    if (earningsGrowth && earningsGrowth < -0.1) score -= 0.4; // Declining
    
    const absScore = Math.abs(score);
    
    if (absScore > 0.5) {
      const signalType = score > 0 ? SignalType.BUY : SignalType.SELL;
      const strength = Math.min(absScore, 1.0);
      
      return { signalType, strength };
    }
    
    return { signalType: SignalType.HOLD, strength: 0 };
  }

  /**
   * Generate volume spike signal
   */
  private generateVolumeSpikeSignal(symbol: string, data: any): { signalType: SignalType; strength: number } {
    const currentVolume = data.size;
    const avgVolume = this.getAverageVolume(symbol);
    
    if (!avgVolume || avgVolume === 0) {
      return { signalType: SignalType.HOLD, strength: 0 };
    }
    
    const volumeRatio = currentVolume / avgVolume;
    
    if (volumeRatio > 2.0) { // Volume spike > 200% of average
      const strength = Math.min((volumeRatio - 1) / 5, 1.0); // Scale strength
      
      // Determine direction based on recent price movement
      const priceChange = this.getRecentPriceChange(symbol);
      const signalType = priceChange >= 0 ? SignalType.BUY : SignalType.SELL;
      
      return { signalType, strength };
    }
    
    return { signalType: SignalType.HOLD, strength: 0 };
  }

  /**
   * Generate spread signal
   */
  private generateSpreadSignal(symbol: string, data: any): { signalType: SignalType; strength: number } {
    const spread = data.spread;
    const avgSpread = this.getAverageSpread(symbol);
    
    if (!avgSpread || avgSpread === 0) {
      return { signalType: SignalType.HOLD, strength: 0 };
    }
    
    const spreadRatio = spread / avgSpread;
    
    // Tight spread might indicate good execution opportunity
    if (spreadRatio < 0.5) {
      const strength = (1 - spreadRatio) * 0.7; // Max strength 0.7
      
      // Use bid/ask imbalance to determine direction
      const imbalance = data.askSize - data.bidSize;
      const signalType = imbalance > 0 ? SignalType.SELL : SignalType.BUY;
      
      return { signalType, strength };
    }
    
    return { signalType: SignalType.HOLD, strength: 0 };
  }

  /**
   * Emit signal event
   */
  private emitSignal(signal: Signal): void {
    // Update signal history
    const history = this.signalHistory.get(signal.symbol) || [];
    history.push(signal);
    
    // Keep only last 100 signals per symbol
    if (history.length > 100) {
      history.shift();
    }
    
    this.signalHistory.set(signal.symbol, history);
    this.lastSignalTime.set(signal.symbol, signal.timestamp);
    
    // Update metrics
    this.incrementMetric('signals_generated');
    this.incrementMetric(`${signal.symbol}_signals`);
    this.updateMetric(`${signal.symbol}_last_signal_strength`, signal.strength);
    
    this.logger.debug({ signal }, 'Generated signal');
    
    // Emit signal event
    this.emit('signal', signal);
  }

  /**
   * Load fundamental data from existing infrastructure
   */
  private async loadFundamentalData(): Promise<void> {
    try {
      // This would integrate with your existing Python data loaders
      // For now, mock some fundamental data
      const enabledSymbols = this.config.getEnabledSymbols();
      
      enabledSymbols.forEach(symbolConfig => {
        this.fundamentalData.set(symbolConfig.symbol, {
          pe_ratio: Math.random() * 30 + 10, // Mock P/E ratio
          earnings_growth: (Math.random() - 0.5) * 0.4, // Mock earnings growth
          revenue_growth: (Math.random() - 0.5) * 0.3,
          debt_to_equity: Math.random() * 2,
          last_updated: Date.now()
        });
      });
      
      this.logger.info('Fundamental data loaded');
      
    } catch (error) {
      this.logger.error({ error }, 'Failed to load fundamental data');
    }
  }

  /**
   * Refresh fundamental data periodically
   */
  private async refreshFundamentalData(): Promise<void> {
    try {
      // This would query your existing database tables
      // populated by your Python loaders
      await this.loadFundamentalData();
      
      this.logger.debug('Fundamental data refreshed');
      
    } catch (error) {
      this.logger.error({ error }, 'Failed to refresh fundamental data');
    }
  }

  // Helper methods for technical analysis
  private getPreviousPrice(symbol: string): number | null {
    // This would maintain a price history buffer
    return this.priceData.get(symbol) || null;
  }

  private getSimpleMovingAverage(symbol: string, periods: number): number | null {
    // This would calculate SMA from price history
    return this.priceData.get(symbol) || null;
  }

  private getAverageVolume(symbol: string): number | null {
    // This would calculate average volume from trade history
    return 1000; // Mock value
  }

  private getRecentPriceChange(symbol: string): number {
    // This would calculate recent price change
    return 0; // Mock value
  }

  private getAverageSpread(symbol: string): number | null {
    // This would calculate average spread from quote history
    return 0.01; // Mock value
  }

  /**
   * Get signal history for a symbol
   */
  getSignalHistory(symbol: string): Signal[] {
    return this.signalHistory.get(symbol) || [];
  }

  /**
   * Get latest signal for a symbol
   */
  getLatestSignal(symbol: string): Signal | null {
    const history = this.signalHistory.get(symbol) || [];
    return history.length > 0 ? history[history.length - 1] : null;
  }
}
