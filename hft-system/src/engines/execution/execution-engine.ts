import { EventEmitter } from 'events';
import { Config } from '../../config';
import { createLogger } from '../../utils/logger';
import { Logger } from 'pino';
import { 
  Order, 
  OrderStatus, 
  OrderSide, 
  OrderType, 
  Position,
  MarketTick,
  Quote,
  ExecutionReport,
  VenueConfig,
  ExecutionAlgorithm,
  OrderSlice,
  ExecutionMetrics
} from '../../types';

export interface ExecutionEngineConfig {
  enabled: boolean;
  venues: VenueConfig[];
  algorithms: {
    twap: boolean;
    vwap: boolean;
    implementation_shortfall: boolean;
    smart_routing: boolean;
  };
  darkPools: {
    enabled: boolean;
    minSize: number;
    venues: string[];
  };
  slicing: {
    enabled: boolean;
    maxSliceSize: number;
    minSliceSize: number;
    timeSliceMs: number;
  };
  latencyTargets: {
    orderAck: number; // ms
    fill: number; // ms
    cancel: number; // ms
  };
}

/**
 * Institutional-Grade Execution Engine
 * - Smart Order Routing across multiple venues
 * - TWAP/VWAP execution algorithms
 * - Dark pool access and execution
 * - Order slicing and iceberg orders
 * - Real-time execution cost analysis
 * - Latency optimization
 */
export class ExecutionEngine extends EventEmitter {
  private config: Config;
  private logger: Logger;
  private isRunning: boolean = false;
  
  // Order management
  private activeOrders: Map<string, Order> = new Map();
  private orderSlices: Map<string, OrderSlice[]> = new Map();
  private executionQueue: Order[] = [];
  
  // Venue connections and routing
  private venues: Map<string, any> = new Map(); // Venue connections
  private venueLatency: Map<string, number> = new Map();
  private venueLiquidity: Map<string, number> = new Map();
  
  // Market data for execution decisions
  private currentQuotes: Map<string, Quote> = new Map();
  private currentTrades: Map<string, MarketTick> = new Map();
  private volumeProfiles: Map<string, number[]> = new Map();
  
  // Execution algorithms
  private twapEngine: TWAPEngine;
  private vwapEngine: VWAPEngine;
  private smartRouter: SmartRouter;
  private darkPoolRouter: DarkPoolRouter;
  
  // Performance tracking
  private executionMetrics: ExecutionMetrics = {
    totalOrders: 0,
    totalVolume: 0,
    averageLatency: 0,
    fillRate: 0,
    implementationShortfall: 0,
    venueStats: {},
    algorithmStats: {},
    timestamp: Date.now()
  };
  
  constructor(config: Config, logger: Logger) {
    super();
    this.config = config;
    this.logger = logger;
    
    // Initialize execution algorithms
    this.twapEngine = new TWAPEngine(config, logger);
    this.vwapEngine = new VWAPEngine(config, logger);
    this.smartRouter = new SmartRouter(config, logger);
    this.darkPoolRouter = new DarkPoolRouter(config, logger);
  }
  
  async initialize(): Promise<void> {
    this.logger.info('Initializing Execution Engine');
    
    // Initialize venue connections
    await this.initializeVenues();
    
    // Initialize execution algorithms
    await this.twapEngine.initialize();
    await this.vwapEngine.initialize();
    await this.smartRouter.initialize();
    await this.darkPoolRouter.initialize();
    
    // Set up event handlers
    this.setupEventHandlers();
    
    this.logger.info('Execution Engine initialized');
  }
  
  async start(): Promise<void> {
    if (this.isRunning) {
      this.logger.warn('Execution Engine already running');
      return;
    }
    
    this.logger.info('Starting Execution Engine');
    this.isRunning = true;
    
    // Start processing execution queue
    this.startExecutionProcessor();
    
    // Start performance monitoring
    this.startPerformanceMonitoring();
    
    this.logger.info('Execution Engine started');
  }
  
  async stop(): Promise<void> {
    if (!this.isRunning) return;
    
    this.logger.info('Stopping Execution Engine');
    this.isRunning = false;
    
    // Cancel all active orders
    await this.cancelAllOrders();
    
    // Stop algorithms
    await this.twapEngine.stop();
    await this.vwapEngine.stop();
    await this.smartRouter.stop();
    await this.darkPoolRouter.stop();
    
    this.logger.info('Execution Engine stopped');
  }
  
  // Core execution methods
  async executeOrder(order: Order): Promise<string> {
    const startTime = Date.now();
    
    this.logger.info(`Executing order: ${order.id} ${order.side} ${order.quantity} ${order.symbol}`);
    
    // Validate order
    const validation = await this.validateOrder(order);
    if (!validation.valid) {
      throw new Error(`Order validation failed: ${validation.reason}`);
    }
    
    // Determine execution strategy
    const strategy = await this.selectExecutionStrategy(order);
    
    // Execute based on strategy
    let executionResult: string;
    
    switch (strategy.algorithm) {
      case 'TWAP':
        executionResult = await this.executeTWAP(order, strategy.params);
        break;
      case 'VWAP':
        executionResult = await this.executeVWAP(order, strategy.params);
        break;
      case 'SMART_ROUTING':
        executionResult = await this.executeSmartRouting(order, strategy.params);
        break;
      case 'DARK_POOL':
        executionResult = await this.executeDarkPool(order, strategy.params);
        break;
      case 'IMMEDIATE':
        executionResult = await this.executeImmediate(order);
        break;
      default:
        executionResult = await this.executeDefault(order);
    }
    
    // Record execution metrics
    const latency = Date.now() - startTime;
    this.recordExecutionMetrics(order, latency, strategy.algorithm);
    
    this.emit('order_executed', {
      orderId: order.id,
      executionId: executionResult,
      latency,
      strategy: strategy.algorithm
    });
    
    return executionResult;
  }
  
  async cancelOrder(orderId: string): Promise<boolean> {
    const order = this.activeOrders.get(orderId);
    if (!order) {
      this.logger.warn(`Cannot cancel order ${orderId}: not found`);
      return false;
    }
    
    // Cancel on all venues
    const cancelResults = await Promise.allSettled(
      Array.from(this.venues.keys()).map(venue => 
        this.cancelOrderOnVenue(orderId, venue)
      )
    );
    
    // Update order status
    order.status = OrderStatus.CANCELED;
    order.canceled_at = Date.now();
    
    this.activeOrders.delete(orderId);
    
    this.emit('order_cancelled', { orderId, timestamp: Date.now() });
    
    return true;
  }
  
  // Execution algorithms
  private async executeTWAP(order: Order, params: any): Promise<string> {
    const slices = await this.twapEngine.calculateSlices(order, params);
    const executionId = `twap_${order.id}_${Date.now()}`;
    
    // Store slices for tracking
    this.orderSlices.set(order.id, slices);
    
    // Execute slices sequentially
    for (const slice of slices) {
      await this.executeSlice(slice);
      
      // Wait for next execution time
      if (slice.delayMs > 0) {
        await this.delay(slice.delayMs);
      }
    }
    
    return executionId;
  }
  
  private async executeVWAP(order: Order, params: any): Promise<string> {
    const volumeProfile = this.volumeProfiles.get(order.symbol) || [];
    const slices = await this.vwapEngine.calculateSlices(order, volumeProfile, params);
    const executionId = `vwap_${order.id}_${Date.now()}`;
    
    this.orderSlices.set(order.id, slices);
    
    // Execute slices based on volume profile
    for (const slice of slices) {
      await this.executeSlice(slice);
      await this.delay(slice.delayMs);
    }
    
    return executionId;
  }
  
  private async executeSmartRouting(order: Order, params: any): Promise<string> {
    const routing = await this.smartRouter.calculateRouting(order, {
      venues: Array.from(this.venues.keys()),
      latency: this.venueLatency,
      liquidity: this.venueLiquidity,
      currentQuotes: this.currentQuotes.get(order.symbol)
    });
    
    const executionId = `smart_${order.id}_${Date.now()}`;
    
    // Execute across multiple venues simultaneously
    const executions = await Promise.allSettled(
      routing.allocations.map(allocation => 
        this.executeOnVenue(allocation.venue, allocation.slice)
      )
    );
    
    return executionId;
  }
  
  private async executeDarkPool(order: Order, params: any): Promise<string> {
    const darkPools = this.config.execution.darkPools.venues;
    const allocation = await this.darkPoolRouter.allocate(order, darkPools);
    
    const executionId = `dark_${order.id}_${Date.now()}`;
    
    // Try dark pools first, then lit markets for remainder
    for (const pool of allocation.pools) {
      const result = await this.executeOnVenue(pool.venue, pool.slice);
      if (result.filled === pool.slice.quantity) {
        return executionId; // Fully filled in dark pool
      }
    }
    
    // Execute remainder on lit markets
    if (allocation.remainder && allocation.remainder.quantity > 0) {
      await this.executeSmartRouting(allocation.remainder, {});
    }
    
    return executionId;
  }
  
  private async executeImmediate(order: Order): Promise<string> {
    // Find best venue for immediate execution
    const bestVenue = await this.findBestVenue(order);
    return await this.executeOnVenue(bestVenue, {
      orderId: order.id,
      venue: bestVenue,
      quantity: order.quantity,
      price: order.price,
      delayMs: 0
    });
  }
  
  private async executeDefault(order: Order): Promise<string> {
    // Default to primary venue (e.g., Alpaca)
    return await this.executeOnVenue('alpaca', {
      orderId: order.id,
      venue: 'alpaca',
      quantity: order.quantity,
      price: order.price,
      delayMs: 0
    });
  }
  
  // Venue management
  private async initializeVenues(): Promise<void> {
    const venueConfigs = this.config.execution.venues;
    
    for (const venueConfig of venueConfigs) {
      try {
        const venue = await this.createVenueConnection(venueConfig);
        this.venues.set(venueConfig.name, venue);
        this.venueLatency.set(venueConfig.name, venueConfig.avgLatencyMs || 50);
        this.venueLiquidity.set(venueConfig.name, venueConfig.liquidityScore || 0.5);
        
        this.logger.info(`Connected to venue: ${venueConfig.name}`);
      } catch (error) {
        this.logger.error(`Failed to connect to venue ${venueConfig.name}:`, error);
      }
    }
  }
  
  private async createVenueConnection(config: VenueConfig): Promise<any> {
    // This would create actual venue connections
    // For now, return a mock connection
    return {
      name: config.name,
      submit: async (order: Order) => ({ orderId: `${config.name}_${Date.now()}` }),
      cancel: async (orderId: string) => ({ cancelled: true }),
      status: async (orderId: string) => ({ status: 'ACTIVE' })
    };
  }
  
  private async executeOnVenue(venueName: string, slice: OrderSlice): Promise<any> {
    const venue = this.venues.get(venueName);
    if (!venue) {
      throw new Error(`Venue ${venueName} not available`);
    }
    
    const startTime = Date.now();
    
    try {
      const result = await venue.submit({
        id: slice.orderId,
        symbol: slice.symbol || '',
        quantity: slice.quantity,
        price: slice.price,
        side: slice.side || OrderSide.BUY,
        type: slice.type || OrderType.LIMIT
      });
      
      const latency = Date.now() - startTime;
      this.venueLatency.set(venueName, latency);
      
      return result;
    } catch (error) {
      this.logger.error(`Execution failed on ${venueName}:`, error);
      throw error;
    }
  }
  
  private async executeSlice(slice: OrderSlice): Promise<void> {
    await this.executeOnVenue(slice.venue, slice);
  }
  
  private async cancelOrderOnVenue(orderId: string, venueName: string): Promise<boolean> {
    const venue = this.venues.get(venueName);
    if (!venue) return false;
    
    try {
      await venue.cancel(orderId);
      return true;
    } catch (error) {
      this.logger.error(`Cancel failed on ${venueName}:`, error);
      return false;
    }
  }
  
  // Strategy selection
  private async selectExecutionStrategy(order: Order): Promise<{ algorithm: string; params: any }> {
    const quote = this.currentQuotes.get(order.symbol);
    const volume = this.volumeProfiles.get(order.symbol);
    
    // Determine optimal strategy based on order characteristics
    const orderValue = order.quantity * (order.price || quote?.ask_price || 0);
    const spread = quote ? quote.ask_price - quote.bid_price : 0;
    const relativeSize = volume ? order.quantity / volume[0] : 0;
    
    // Large orders use TWAP/VWAP
    if (orderValue > 100000 || relativeSize > 0.1) {
      return {
        algorithm: volume && volume.length > 0 ? 'VWAP' : 'TWAP',
        params: { duration: 300000, maxSliceSize: order.quantity * 0.1 }
      };
    }
    
    // Medium orders use smart routing
    if (orderValue > 10000) {
      return {
        algorithm: 'SMART_ROUTING',
        params: { maxVenues: 3, latencyWeight: 0.7 }
      };
    }
    
    // Small orders try dark pools first
    if (this.config.execution.darkPools.enabled && orderValue > this.config.execution.darkPools.minSize) {
      return {
        algorithm: 'DARK_POOL',
        params: { maxDarkRatio: 0.8 }
      };
    }
    
    // Default to immediate execution
    return {
      algorithm: 'IMMEDIATE',
      params: {}
    };
  }
  
  private async validateOrder(order: Order): Promise<{ valid: boolean; reason?: string }> {
    // Basic validation
    if (!order.symbol || !order.quantity || order.quantity <= 0) {
      return { valid: false, reason: 'Invalid order parameters' };
    }
    
    // Check if symbol is tradeable
    const quote = this.currentQuotes.get(order.symbol);
    if (!quote) {
      return { valid: false, reason: 'No market data available' };
    }
    
    // Check spread
    const spread = quote.ask_price - quote.bid_price;
    const midPrice = (quote.ask_price + quote.bid_price) / 2;
    if (spread / midPrice > 0.05) { // 5% spread limit
      return { valid: false, reason: 'Spread too wide' };
    }
    
    return { valid: true };
  }
  
  private async findBestVenue(order: Order): Promise<string> {
    let bestVenue = 'alpaca';
    let bestScore = 0;
    
    for (const [venueName, venue] of this.venues.entries()) {
      const latency = this.venueLatency.get(venueName) || 100;
      const liquidity = this.venueLiquidity.get(venueName) || 0.5;
      
      // Score based on latency and liquidity
      const score = liquidity * 0.7 + (100 - latency) / 100 * 0.3;
      
      if (score > bestScore) {
        bestScore = score;
        bestVenue = venueName;
      }
    }
    
    return bestVenue;
  }
  
  // Market data updates
  updateQuote(quote: Quote): void {
    this.currentQuotes.set(quote.symbol, quote);
  }
  
  updateTrade(trade: MarketTick): void {
    this.currentTrades.set(trade.symbol, trade);
    
    // Update volume profile
    const profile = this.volumeProfiles.get(trade.symbol) || [];
    profile.push(trade.size);
    if (profile.length > 1000) { // Keep last 1000 trades
      profile.shift();
    }
    this.volumeProfiles.set(trade.symbol, profile);
  }
  
  // Performance monitoring
  private startPerformanceMonitoring(): void {
    setInterval(() => {
      this.calculateExecutionMetrics();
    }, 5000); // Update every 5 seconds
  }
  
  private calculateExecutionMetrics(): void {
    // Update real-time execution metrics
    const now = Date.now();
    
    // Calculate average latency across venues
    const latencies = Array.from(this.venueLatency.values());
    this.executionMetrics.averageLatency = latencies.reduce((sum, lat) => sum + lat, 0) / latencies.length;
    
    // Update timestamp
    this.executionMetrics.timestamp = now;
    
    this.emit('execution_metrics_updated', this.executionMetrics);
  }
  
  private recordExecutionMetrics(order: Order, latency: number, algorithm: string): void {
    this.executionMetrics.totalOrders++;
    this.executionMetrics.totalVolume += order.quantity;
    
    // Update algorithm stats
    if (!this.executionMetrics.algorithmStats[algorithm]) {
      this.executionMetrics.algorithmStats[algorithm] = {
        orders: 0,
        volume: 0,
        averageLatency: 0
      };
    }
    
    const stats = this.executionMetrics.algorithmStats[algorithm];
    stats.orders++;
    stats.volume += order.quantity;
    stats.averageLatency = (stats.averageLatency * (stats.orders - 1) + latency) / stats.orders;
  }
  
  // Event handlers
  private setupEventHandlers(): void {
    this.twapEngine.on('slice_executed', (data) => {
      this.emit('execution_slice_completed', data);
    });
    
    this.vwapEngine.on('slice_executed', (data) => {
      this.emit('execution_slice_completed', data);
    });
    
    this.smartRouter.on('routing_calculated', (data) => {
      this.emit('routing_updated', data);
    });
  }
  
  private startExecutionProcessor(): void {
    // Process execution queue
    setInterval(() => {
      this.processExecutionQueue();
    }, 1); // Process every 1ms for ultra-low latency
  }
  
  private async processExecutionQueue(): Promise<void> {
    while (this.executionQueue.length > 0 && this.isRunning) {
      const order = this.executionQueue.shift();
      if (order) {
        try {
          await this.executeOrder(order);
        } catch (error) {
          this.logger.error('Execution queue processing error:', error);
          this.emit('execution_error', { order, error });
        }
      }
    }
  }
  
  private async cancelAllOrders(): Promise<void> {
    const cancelPromises = Array.from(this.activeOrders.keys()).map(orderId => 
      this.cancelOrder(orderId)
    );
    
    await Promise.allSettled(cancelPromises);
  }
  
  private delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
  
  // Getters
  getExecutionMetrics(): ExecutionMetrics {
    return { ...this.executionMetrics };
  }
  
  getActiveOrderCount(): number {
    return this.activeOrders.size;
  }
  
  getVenueStatus(): Map<string, any> {
    const status = new Map();
    
    for (const [venueName, venue] of this.venues.entries()) {
      status.set(venueName, {
        connected: !!venue,
        latency: this.venueLatency.get(venueName),
        liquidity: this.venueLiquidity.get(venueName)
      });
    }
    
    return status;
  }
}

// Supporting algorithm classes (simplified implementations)
class TWAPEngine extends EventEmitter {
  constructor(private config: Config, private logger: Logger) {
    super();
  }
  
  async initialize(): Promise<void> {}
  async stop(): Promise<void> {}
  
  async calculateSlices(order: Order, params: any): Promise<OrderSlice[]> {
    const { duration = 300000, maxSliceSize = order.quantity * 0.1 } = params;
    const numSlices = Math.ceil(order.quantity / maxSliceSize);
    const sliceSize = order.quantity / numSlices;
    const timeInterval = duration / numSlices;
    
    const slices: OrderSlice[] = [];
    
    for (let i = 0; i < numSlices; i++) {
      slices.push({
        orderId: `${order.id}_slice_${i}`,
        venue: 'alpaca', // Default venue
        quantity: i === numSlices - 1 ? order.quantity - (sliceSize * i) : sliceSize,
        price: order.price,
        delayMs: i * timeInterval,
        symbol: order.symbol,
        side: order.side,
        type: order.type
      });
    }
    
    return slices;
  }
}

class VWAPEngine extends EventEmitter {
  constructor(private config: Config, private logger: Logger) {
    super();
  }
  
  async initialize(): Promise<void> {}
  async stop(): Promise<void> {}
  
  async calculateSlices(order: Order, volumeProfile: number[], params: any): Promise<OrderSlice[]> {
    // Simplified VWAP calculation
    const totalVolume = volumeProfile.reduce((sum, vol) => sum + vol, 0);
    const slices: OrderSlice[] = [];
    
    if (totalVolume === 0) {
      // Fallback to TWAP if no volume data
      const twap = new TWAPEngine(this.config, this.logger);
      return twap.calculateSlices(order, params);
    }
    
    let remainingQuantity = order.quantity;
    
    for (let i = 0; i < Math.min(volumeProfile.length, 10); i++) {
      const volumeWeight = volumeProfile[i] / totalVolume;
      const sliceQuantity = Math.min(order.quantity * volumeWeight, remainingQuantity);
      
      if (sliceQuantity > 0) {
        slices.push({
          orderId: `${order.id}_vwap_${i}`,
          venue: 'alpaca',
          quantity: sliceQuantity,
          price: order.price,
          delayMs: i * 30000, // 30 second intervals
          symbol: order.symbol,
          side: order.side,
          type: order.type
        });
        
        remainingQuantity -= sliceQuantity;
      }
    }
    
    return slices;
  }
}

class SmartRouter extends EventEmitter {
  constructor(private config: Config, private logger: Logger) {
    super();
  }
  
  async initialize(): Promise<void> {}
  async stop(): Promise<void> {}
  
  async calculateRouting(order: Order, context: any): Promise<any> {
    const { venues, latency, liquidity } = context;
    const allocations: any[] = [];
    
    // Simplified smart routing - allocate across top venues
    const sortedVenues = venues.sort((a: string, b: string) => {
      const scoreA = (liquidity.get(a) || 0.5) * 0.7 + (100 - (latency.get(a) || 50)) / 100 * 0.3;
      const scoreB = (liquidity.get(b) || 0.5) * 0.7 + (100 - (latency.get(b) || 50)) / 100 * 0.3;
      return scoreB - scoreA;
    });
    
    let remainingQuantity = order.quantity;
    
    for (let i = 0; i < Math.min(3, sortedVenues.length) && remainingQuantity > 0; i++) {
      const venue = sortedVenues[i];
      const allocation = remainingQuantity * (i === 0 ? 0.6 : i === 1 ? 0.3 : 0.1);
      const quantity = Math.min(allocation, remainingQuantity);
      
      allocations.push({
        venue,
        slice: {
          orderId: `${order.id}_${venue}`,
          venue,
          quantity,
          price: order.price,
          delayMs: 0,
          symbol: order.symbol,
          side: order.side,
          type: order.type
        }
      });
      
      remainingQuantity -= quantity;
    }
    
    return { allocations };
  }
}

class DarkPoolRouter extends EventEmitter {
  constructor(private config: Config, private logger: Logger) {
    super();
  }
  
  async initialize(): Promise<void> {}
  async stop(): Promise<void> {}
  
  async allocate(order: Order, darkPools: string[]): Promise<any> {
    const pools: any[] = [];
    let remainingQuantity = order.quantity;
    
    // Try to fill in dark pools first
    const darkQuantity = Math.min(order.quantity * 0.8, remainingQuantity);
    
    if (darkQuantity > 0) {
      pools.push({
        venue: darkPools[0] || 'dark_pool_1',
        slice: {
          orderId: `${order.id}_dark`,
          venue: darkPools[0] || 'dark_pool_1',
          quantity: darkQuantity,
          price: order.price,
          delayMs: 0,
          symbol: order.symbol,
          side: order.side,
          type: order.type
        }
      });
      
      remainingQuantity -= darkQuantity;
    }
    
    // Return remainder for lit market execution
    const remainder = remainingQuantity > 0 ? {
      ...order,
      quantity: remainingQuantity
    } : null;
    
    return { pools, remainder };
  }
}
