/**
 * Advanced Market Making Strategy
 * 
 * Institutional-grade market making with:
 * - Dynamic spread adjustments
 * - Inventory management
 * - Adverse selection protection
 * - Multi-level order book management
 * - Cross-correlation hedging
 */

import { EventEmitter } from 'events';
import { timeSeriesManager } from '../core/timeseries/timeseries-engine';
import { fastSignalGenerator } from '../core/signals/fast-signal-generator';
import type { Logger } from 'pino';
import type { 
  Order, 
  Position, 
  MarketData, 
  OrderBookLevel,
  StrategyConfig,
  RiskParameters 
} from '../types';

export interface MarketMakingConfig extends StrategyConfig {
  // Spread management
  baseSpread: number;           // Base spread in bps
  minSpread: number;           // Minimum spread in bps
  maxSpread: number;           // Maximum spread in bps
  spreadMultiplier: number;    // Volatility-based spread multiplier
  
  // Position management
  maxInventory: number;        // Maximum inventory in shares
  inventoryLimit: number;      // Inventory limit as % of max
  skewFactor: number;          // Inventory skew adjustment factor
  
  // Order management
  orderLevels: number;         // Number of order levels per side
  orderSizeBase: number;       // Base order size
  orderSizeDecay: number;      // Size decay per level (0.8 = 80% of prev level)
  refreshThreshold: number;    // Price movement threshold for refresh (bps)
  
  // Risk parameters
  maxNotional: number;         // Maximum notional exposure per symbol
  maxDailyLoss: number;        // Maximum daily loss per symbol
  adverseSelectionLimit: number; // Adverse selection threshold
  
  // Timing
  quoteLifetime: number;       // Quote lifetime in ms
  refreshInterval: number;     // Minimum refresh interval in ms
  pauseAfterFill: number;      // Pause after fill in ms
}

export interface MarketState {
  bid: number;
  ask: number;
  bidSize: number;
  askSize: number;
  spread: number;
  mid: number;
  lastPrice: number;
  volume: number;
  timestamp: bigint;
  volatility: number;
  microPrice: number;          // Weighted mid price
}

export interface InventoryState {
  position: number;            // Net position
  avgPrice: number;           // Average price
  unrealizedPnL: number;      // Unrealized P&L
  exposure: number;           // Notional exposure
  maxExposure: number;        // Maximum allowed exposure
  skew: number;              // Inventory skew factor
}

export interface QuoteLevel {
  price: number;
  size: number;
  orderId?: string;
  timestamp: bigint;
}

export interface QuoteBook {
  bids: QuoteLevel[];
  asks: QuoteLevel[];
  symbol: string;
  timestamp: bigint;
}

export class MarketMakingStrategy extends EventEmitter {
  private config: MarketMakingConfig;
  private logger: Logger;
  private enabled: boolean = false;
  
  // Market state tracking
  private marketStates: Map<string, MarketState> = new Map();
  private inventoryStates: Map<string, InventoryState> = new Map();
  private activeQuotes: Map<string, QuoteBook> = new Map();
  
  // Performance tracking
  private metrics = {
    totalQuotes: 0,
    activeQuotes: 0,
    fills: 0,
    totalVolume: 0,
    totalPnL: 0,
    adverseSelections: 0,
    skippedQuotes: 0,
    refreshes: 0
  };
  
  // Timing and throttling
  private lastRefresh: Map<string, bigint> = new Map();
  private pausedUntil: Map<string, bigint> = new Map();
  
  constructor(config: MarketMakingConfig, logger: Logger) {
    super();
    this.config = config;
    this.logger = logger.child({ component: 'MarketMakingStrategy' });
    
    // Initialize inventory states for all symbols
    for (const symbol of config.symbols) {
      this.inventoryStates.set(symbol, {
        position: 0,
        avgPrice: 0,
        unrealizedPnL: 0,
        exposure: 0,
        maxExposure: config.maxNotional,
        skew: 0
      });
    }
    
    this.logger.info('Market making strategy initialized', {
      symbols: config.symbols.length,
      baseSpread: config.baseSpread,
      orderLevels: config.orderLevels
    });
  }
  
  /**
   * Start the market making strategy
   */
  public start(): void {
    this.enabled = true;
    this.logger.info('Market making strategy started');
    this.emit('strategy_started');
  }
  
  /**
   * Stop the market making strategy
   */
  public stop(): void {
    this.enabled = false;
    
    // Cancel all active quotes
    for (const [symbol, quoteBook] of this.activeQuotes) {
      this.cancelAllQuotes(symbol);
    }
    
    this.logger.info('Market making strategy stopped');
    this.emit('strategy_stopped');
  }
  
  /**
   * Process market data update
   */
  public async processMarketData(symbol: string, timestamp: bigint): Promise<void> {
    if (!this.enabled) return;
    
    try {
      // Check if symbol is paused
      const pausedUntil = this.pausedUntil.get(symbol);
      if (pausedUntil && timestamp < pausedUntil) {
        return;
      }
      
      // Update market state
      const marketState = await this.updateMarketState(symbol, timestamp);
      if (!marketState) return;
      
      // Check if we should refresh quotes
      const shouldRefresh = await this.shouldRefreshQuotes(symbol, timestamp);
      if (!shouldRefresh) return;
      
      // Calculate optimal quotes
      const quoteBook = await this.calculateOptimalQuotes(symbol, marketState, timestamp);
      if (!quoteBook) return;
      
      // Submit quotes
      await this.submitQuotes(symbol, quoteBook);
      
      this.lastRefresh.set(symbol, timestamp);
      this.metrics.refreshes++;
      
    } catch (error) {
      this.logger.error(`Error processing market data for ${symbol}:`, error);
    }
  }
  
  /**
   * Update market state from latest data
   */
  private async updateMarketState(symbol: string, timestamp: bigint): Promise<MarketState | null> {
    try {
      // Get latest market data from time series
      const latestTick = timeSeriesManager.getLatestTick(symbol);
      const orderBook = timeSeriesManager.getOrderBook(symbol);
      const volatility = await fastSignalGenerator.calculateVolatility(symbol, 100); // 100 periods
      
      if (!latestTick || !orderBook.bid || !orderBook.ask) {
        return null;
      }
      
      // Calculate micro price (volume-weighted mid)
      const totalBidVolume = orderBook.bid.size;
      const totalAskVolume = orderBook.ask.size;
      const totalVolume = totalBidVolume + totalAskVolume;
      
      const microPrice = totalVolume > 0 
        ? (orderBook.bid.price * totalAskVolume + orderBook.ask.price * totalBidVolume) / totalVolume
        : (orderBook.bid.price + orderBook.ask.price) / 2;
      
      const marketState: MarketState = {
        bid: orderBook.bid.price,
        ask: orderBook.ask.price,
        bidSize: orderBook.bid.size,
        askSize: orderBook.ask.size,
        spread: orderBook.ask.price - orderBook.bid.price,
        mid: (orderBook.bid.price + orderBook.ask.price) / 2,
        lastPrice: latestTick.price,
        volume: latestTick.size,
        timestamp,
        volatility: volatility || 0,
        microPrice
      };
      
      this.marketStates.set(symbol, marketState);
      return marketState;
      
    } catch (error) {
      this.logger.error(`Error updating market state for ${symbol}:`, error);
      return null;
    }
  }
  
  /**
   * Determine if quotes should be refreshed
   */
  private async shouldRefreshQuotes(symbol: string, timestamp: bigint): Promise<boolean> {
    const lastRefresh = this.lastRefresh.get(symbol) || 0n;
    const timeSinceRefresh = Number(timestamp - lastRefresh) / 1000000; // ms
    
    // Minimum refresh interval
    if (timeSinceRefresh < this.config.refreshInterval) {
      return false;
    }
    
    const marketState = this.marketStates.get(symbol);
    const activeQuotes = this.activeQuotes.get(symbol);
    
    // Always refresh if no active quotes
    if (!activeQuotes || !marketState) {
      return true;
    }
    
    // Check if market has moved significantly
    const bestBid = activeQuotes.bids[0]?.price || 0;
    const bestAsk = activeQuotes.asks[0]?.price || 0;
    
    const bidMoveThreshold = marketState.mid * (this.config.refreshThreshold / 10000);
    const askMoveThreshold = marketState.mid * (this.config.refreshThreshold / 10000);
    
    const bidMoved = Math.abs(marketState.bid - bestBid) > bidMoveThreshold;
    const askMoved = Math.abs(marketState.ask - bestAsk) > askMoveThreshold;
    
    if (bidMoved || askMoved) {
      this.logger.debug(`Market moved significantly for ${symbol}, refreshing quotes`);
      return true;
    }
    
    // Check quote lifetime
    const oldestQuoteAge = Number(timestamp - (activeQuotes.timestamp || 0n)) / 1000000;
    if (oldestQuoteAge > this.config.quoteLifetime) {
      this.logger.debug(`Quotes expired for ${symbol}, refreshing`);
      return true;
    }
    
    return false;
  }
  
  /**
   * Calculate optimal quotes based on market conditions and inventory
   */
  private async calculateOptimalQuotes(
    symbol: string, 
    marketState: MarketState, 
    timestamp: bigint
  ): Promise<QuoteBook | null> {
    try {
      const inventoryState = this.inventoryStates.get(symbol);
      if (!inventoryState) return null;
      
      // Calculate dynamic spread
      const spread = this.calculateDynamicSpread(symbol, marketState);
      const halfSpread = spread / 2;
      
      // Calculate inventory skew
      const skew = this.calculateInventorySkew(inventoryState);
      
      // Calculate fair value (using micro price + alpha signal)
      const fairValue = await this.calculateFairValue(symbol, marketState);
      
      // Calculate quote prices with skew
      const bidPrice = fairValue - halfSpread + skew;
      const askPrice = fairValue + halfSpread + skew;
      
      // Generate multi-level quotes
      const bids: QuoteLevel[] = [];
      const asks: QuoteLevel[] = [];
      
      for (let level = 0; level < this.config.orderLevels; level++) {
        const levelSpread = spread * (1 + level * 0.1); // 10% wider per level
        const levelHalfSpread = levelSpread / 2;
        
        const levelBidPrice = fairValue - levelHalfSpread + skew;
        const levelAskPrice = fairValue + levelHalfSpread + skew;
        
        // Calculate order size with decay
        const baseSize = this.config.orderSizeBase;
        const levelSize = Math.round(baseSize * Math.pow(this.config.orderSizeDecay, level));
        
        // Check if we should quote at this level based on inventory
        const shouldQuoteBid = this.shouldQuoteSide(symbol, 'bid', inventoryState, level);
        const shouldQuoteAsk = this.shouldQuoteSide(symbol, 'ask', inventoryState, level);
        
        if (shouldQuoteBid && levelBidPrice > 0) {
          bids.push({
            price: this.roundPrice(levelBidPrice),
            size: levelSize,
            timestamp
          });
        }
        
        if (shouldQuoteAsk && levelAskPrice > 0) {
          asks.push({
            price: this.roundPrice(levelAskPrice),
            size: levelSize,
            timestamp
          });
        }
      }
      
      // Sort levels
      bids.sort((a, b) => b.price - a.price); // Highest bid first
      asks.sort((a, b) => a.price - b.price); // Lowest ask first
      
      return {
        bids,
        asks,
        symbol,
        timestamp
      };
      
    } catch (error) {
      this.logger.error(`Error calculating optimal quotes for ${symbol}:`, error);
      return null;
    }
  }
  
  /**
   * Calculate dynamic spread based on market conditions
   */
  private calculateDynamicSpread(symbol: string, marketState: MarketState): number {
    const baseSpread = this.config.baseSpread;
    const volatilityAdjustment = marketState.volatility * this.config.spreadMultiplier;
    const marketSpread = marketState.spread;
    
    // Spread = max(base_spread, market_spread * 1.1, base_spread + volatility_adjustment)
    const dynamicSpread = Math.max(
      this.config.minSpread,
      Math.min(
        this.config.maxSpread,
        Math.max(
          baseSpread,
          marketSpread * 1.1, // 10% wider than market
          baseSpread + volatilityAdjustment
        )
      )
    );
    
    return dynamicSpread / 10000; // Convert bps to decimal
  }
  
  /**
   * Calculate inventory skew adjustment
   */
  private calculateInventorySkew(inventoryState: InventoryState): number {
    const inventoryRatio = inventoryState.position / this.config.maxInventory;
    const skew = inventoryRatio * this.config.skewFactor;
    
    // Skew quotes away from the direction of inventory
    // If long inventory, skew quotes lower to encourage selling
    return -skew;
  }
  
  /**
   * Calculate fair value using multiple signals
   */
  private async calculateFairValue(symbol: string, marketState: MarketState): Promise<number> {
    try {
      // Base fair value on micro price
      let fairValue = marketState.microPrice;
      
      // Add alpha signals from fast signal generator
      const momentum = await fastSignalGenerator.calculateMomentum(symbol, 20);
      const meanReversion = await fastSignalGenerator.calculateMeanReversion(symbol, 50);
      
      // Apply signal-based adjustments (small for market making)
      const momentumAdjustment = (momentum || 0) * 0.0001; // 1 bps per momentum unit
      const meanReversionAdjustment = (meanReversion || 0) * 0.0001;
      
      fairValue += momentumAdjustment + meanReversionAdjustment;
      
      return fairValue;
      
    } catch (error) {
      this.logger.error(`Error calculating fair value for ${symbol}:`, error);
      return marketState.microPrice;
    }
  }
  
  /**
   * Determine if we should quote on a specific side and level
   */
  private shouldQuoteSide(
    symbol: string, 
    side: 'bid' | 'ask', 
    inventoryState: InventoryState, 
    level: number
  ): boolean {
    // Check exposure limits
    if (Math.abs(inventoryState.exposure) >= inventoryState.maxExposure) {
      // Only quote to reduce inventory
      if (side === 'bid' && inventoryState.position >= 0) return false;
      if (side === 'ask' && inventoryState.position <= 0) return false;
    }
    
    // Check inventory limits
    const inventoryRatio = Math.abs(inventoryState.position) / this.config.maxInventory;
    
    if (inventoryRatio > this.config.inventoryLimit) {
      // Aggressive inventory reduction
      if (side === 'bid' && inventoryState.position > 0) return false;
      if (side === 'ask' && inventoryState.position < 0) return false;
    }
    
    // Reduce quote levels as inventory grows
    const maxLevels = Math.max(1, this.config.orderLevels - Math.floor(inventoryRatio * this.config.orderLevels));
    if (level >= maxLevels) return false;
    
    return true;
  }
  
  /**
   * Submit quotes to order engine
   */
  private async submitQuotes(symbol: string, quoteBook: QuoteBook): Promise<void> {
    try {
      // Cancel existing quotes first
      await this.cancelAllQuotes(symbol);
      
      // Submit new quotes
      const orders: Order[] = [];
      
      // Submit bid orders
      for (const bid of quoteBook.bids) {
        const order: Order = {
          id: `${symbol}_bid_${Date.now()}_${Math.random()}`,
          symbol,
          side: 'buy',
          type: 'limit',
          quantity: bid.size,
          price: bid.price,
          time_in_force: 'ioc', // Immediate or cancel for market making
          timestamp: bid.timestamp,
          strategy: 'market_making'
        };
        
        orders.push(order);
        bid.orderId = order.id;
      }
      
      // Submit ask orders
      for (const ask of quoteBook.asks) {
        const order: Order = {
          id: `${symbol}_ask_${Date.now()}_${Math.random()}`,
          symbol,
          side: 'sell',
          type: 'limit',
          quantity: ask.size,
          price: ask.price,
          time_in_force: 'ioc',
          timestamp: ask.timestamp,
          strategy: 'market_making'
        };
        
        orders.push(order);
        ask.orderId = order.id;
      }
      
      // Emit orders for execution
      for (const order of orders) {
        this.emit('order_created', order);
      }
      
      // Store active quotes
      this.activeQuotes.set(symbol, quoteBook);
      this.metrics.totalQuotes += orders.length;
      this.metrics.activeQuotes = this.activeQuotes.size;
      
      this.logger.debug(`Submitted ${orders.length} quotes for ${symbol}`);
      
    } catch (error) {
      this.logger.error(`Error submitting quotes for ${symbol}:`, error);
    }
  }
  
  /**
   * Cancel all active quotes for a symbol
   */
  private async cancelAllQuotes(symbol: string): Promise<void> {
    const activeQuotes = this.activeQuotes.get(symbol);
    if (!activeQuotes) return;
    
    const orderIds: string[] = [];
    
    // Collect all order IDs
    for (const bid of activeQuotes.bids) {
      if (bid.orderId) orderIds.push(bid.orderId);
    }
    
    for (const ask of activeQuotes.asks) {
      if (ask.orderId) orderIds.push(ask.orderId);
    }
    
    // Emit cancellation events
    for (const orderId of orderIds) {
      this.emit('order_cancelled', { id: orderId, symbol });
    }
    
    // Remove from active quotes
    this.activeQuotes.delete(symbol);
  }
  
  /**
   * Process order fill
   */
  public processOrderFill(order: Order): void {
    try {
      const inventoryState = this.inventoryStates.get(order.symbol);
      if (!inventoryState) return;
      
      // Update inventory
      const positionChange = order.side === 'buy' ? order.filled_quantity! : -order.filled_quantity!;
      const oldPosition = inventoryState.position;
      const newPosition = oldPosition + positionChange;
      
      // Update average price
      if (newPosition !== 0) {
        const oldNotional = oldPosition * inventoryState.avgPrice;
        const newNotional = positionChange * order.price!;
        inventoryState.avgPrice = (oldNotional + newNotional) / newPosition;
      } else {
        inventoryState.avgPrice = 0;
      }
      
      inventoryState.position = newPosition;
      inventoryState.exposure = Math.abs(newPosition * order.price!);
      
      // Calculate realized P&L if reducing position
      let realizedPnL = 0;
      if (Math.sign(oldPosition) !== Math.sign(newPosition) && oldPosition !== 0) {
        realizedPnL = Math.abs(positionChange) * (order.price! - inventoryState.avgPrice);
        if (oldPosition < 0) realizedPnL = -realizedPnL; // Short position
      }
      
      // Update metrics
      this.metrics.fills++;
      this.metrics.totalVolume += order.filled_quantity!;
      this.metrics.totalPnL += realizedPnL;
      
      // Pause quoting briefly after fill
      const pauseUntil = BigInt(Date.now() * 1000000) + BigInt(this.config.pauseAfterFill * 1000000);
      this.pausedUntil.set(order.symbol, pauseUntil);
      
      this.logger.info(`Order filled: ${order.id}`, {
        symbol: order.symbol,
        side: order.side,
        quantity: order.filled_quantity,
        price: order.price,
        newPosition: newPosition,
        realizedPnL
      });
      
      this.emit('position_updated', {
        symbol: order.symbol,
        position: newPosition,
        avgPrice: inventoryState.avgPrice,
        realizedPnL
      });
      
    } catch (error) {
      this.logger.error(`Error processing order fill:`, error);
    }
  }
  
  /**
   * Round price to appropriate tick size
   */
  private roundPrice(price: number): number {
    // Simple tick size rounding - can be enhanced for specific symbols
    if (price >= 1) {
      return Math.round(price * 100) / 100; // 1 cent
    } else {
      return Math.round(price * 10000) / 10000; // 0.01 cent
    }
  }
  
  /**
   * Get current strategy metrics
   */
  public getMetrics() {
    return {
      ...this.metrics,
      activeSymbols: this.marketStates.size,
      totalInventoryValue: Array.from(this.inventoryStates.values()).reduce(
        (sum, inv) => sum + Math.abs(inv.exposure), 0
      )
    };
  }
  
  /**
   * Get inventory state for a symbol
   */
  public getInventoryState(symbol: string): InventoryState | undefined {
    return this.inventoryStates.get(symbol);
  }
  
  /**
   * Emergency stop - cancel all quotes
   */
  public async emergencyStop(): Promise<void> {
    this.logger.warn('Emergency stop triggered - cancelling all quotes');
    
    for (const symbol of this.activeQuotes.keys()) {
      await this.cancelAllQuotes(symbol);
    }
    
    this.enabled = false;
    this.emit('emergency_stop');
  }
}
