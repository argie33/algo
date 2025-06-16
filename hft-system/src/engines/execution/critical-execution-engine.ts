import { EventEmitter } from 'events';
import { Config } from '../../config';
import { createLogger } from '../../utils/logger';
import { Order, OrderStatus, AlphaSignal } from '../../types';

export interface ExecutionVenue {
  id: string;
  name: string;
  enabled: boolean;
  latency: number; // milliseconds
  fillRate: number; // 0-1
  costPerShare: number;
  maxOrderSize: number;
  supportedOrderTypes: string[];
  marketHours: {
    open: string;
    close: string;
  };
}

export interface ExecutionMetrics {
  avgLatency: number;
  fillRate: number;
  slippage: number;
  rejectRate: number;
  profitability: number;
  timestamp: number;
}

export interface SmartRoutingDecision {
  venue: string;
  orderType: string;
  quantity: number;
  price?: number;
  timeInForce: string;
  expectedLatency: number;
  expectedFillProbability: number;
  reasoning: string;
}

/**
 * Critical Execution Engine - Ultra-Fast Order Execution
 * Handles smart order routing, execution optimization, and latency minimization
 */
export class CriticalExecutionEngine extends EventEmitter {
  private config: Config;
  private logger: any;
  private isRunning: boolean = false;
  
  // Execution venues
  private venues: Map<string, ExecutionVenue> = new Map();
  private venueMetrics: Map<string, ExecutionMetrics> = new Map();
  
  // Active orders
  private activeOrders: Map<string, Order> = new Map();
  private orderHistory: Map<string, Order[]> = new Map();
  
  // Execution metrics
  private executionLatency: number[] = [];
  private slippageTracking: number[] = [];
  private fillRates: Map<string, number> = new Map();
  
  constructor(config: Config) {
    super();
    this.config = config;
    this.logger = createLogger('critical-execution-engine');
    
    this.initializeVenues();
  }
  
  async initialize(): Promise<void> {
    this.logger.info('Initializing Critical Execution Engine');
    
    // Initialize venue connections
    await this.initializeVenueConnections();
    
    // Load historical execution metrics
    await this.loadExecutionMetrics();
    
    this.logger.info('Critical Execution Engine initialized');
  }
  
  async start(): Promise<void> {
    if (this.isRunning) return;
    
    this.logger.info('Starting Critical Execution Engine');
    this.isRunning = true;
    
    // Start venue monitoring
    this.startVenueMonitoring();
    
    // Start execution optimization
    this.startExecutionOptimization();
    
    this.logger.info('Critical Execution Engine started');
  }
  
  async stop(): Promise<void> {
    if (!this.isRunning) return;
    
    this.logger.info('Stopping Critical Execution Engine');
    this.isRunning = false;
    
    // Cancel all active orders
    await this.cancelAllOrders();
    
    this.logger.info('Critical Execution Engine stopped');
  }
  
  // Main execution method - Convert alpha signal to orders
  async executeSignal(signal: AlphaSignal): Promise<Order[]> {
    const startTime = performance.now();
    
    try {
      // 1. Determine order parameters
      const orderParams = this.calculateOrderParameters(signal);
      
      // 2. Smart routing decision
      const routingDecision = await this.smartOrderRouting(orderParams);
      
      // 3. Create and submit orders
      const orders = await this.submitOrders(routingDecision, signal);
      
      // 4. Track execution latency
      const latency = performance.now() - startTime;
      this.executionLatency.push(latency);
      
      this.logger.info(`Executed signal for ${signal.symbol} in ${latency.toFixed(2)}ms`);
      
      return orders;
      
    } catch (error) {
      this.logger.error('Error executing signal:', error);
      return [];
    }
  }
  
  // Calculate order parameters from alpha signal
  private calculateOrderParameters(signal: AlphaSignal): any {
    const direction = signal.signal > 0 ? 'buy' : 'sell';
    const signalStrength = Math.abs(signal.signal);
    
    // Position sizing based on signal strength and risk
    const basePositionSize = 1000; // Base $1000 position
    const riskAdjustment = 1 - signal.riskScore;
    const confidenceAdjustment = signal.confidence;
    
    const dollarAmount = basePositionSize * signalStrength * riskAdjustment * confidenceAdjustment;
    
    // Estimate current price (would use real market data)
    const estimatedPrice = 100; // Placeholder
    const shareQuantity = Math.floor(dollarAmount / estimatedPrice);
    
    return {
      symbol: signal.symbol,
      direction,
      quantity: shareQuantity,
      expectedReturn: signal.expectedReturn,
      holdingPeriod: signal.expectedHoldingPeriod,
      urgency: signalStrength > 0.7 ? 'high' : 'normal'
    };
  }
  
  // Smart order routing algorithm
  private async smartOrderRouting(orderParams: any): Promise<SmartRoutingDecision> {
    const { symbol, direction, quantity, urgency } = orderParams;
    
    // Get available venues for this symbol
    const availableVenues = this.getAvailableVenues(symbol);
    
    if (availableVenues.length === 0) {
      throw new Error(`No available venues for ${symbol}`);
    }
    
    // Score each venue
    const venueScores = await Promise.all(
      availableVenues.map(venue => this.scoreVenue(venue, orderParams))
    );
    
    // Select best venue
    const bestVenueIndex = venueScores.reduce((bestIdx, score, idx) => 
      score > venueScores[bestIdx] ? idx : bestIdx, 0);
    
    const selectedVenue = availableVenues[bestVenueIndex];
    
    // Determine order type based on urgency and market conditions
    let orderType = 'limit';
    let timeInForce = 'IOC'; // Immediate or Cancel for speed
    
    if (urgency === 'high') {
      orderType = 'market';
      timeInForce = 'IOC';
    }
    
    return {
      venue: selectedVenue.id,
      orderType,
      quantity,
      timeInForce,
      expectedLatency: selectedVenue.latency,
      expectedFillProbability: selectedVenue.fillRate,
      reasoning: `Selected ${selectedVenue.name} for ${urgency} urgency order`
    };
  }
  
  // Score venue for order execution
  private async scoreVenue(venue: ExecutionVenue, orderParams: any): Promise<number> {
    const metrics = this.venueMetrics.get(venue.id);
    if (!metrics) return 0;
    
    let score = 0;
    
    // Latency score (lower is better)
    const latencyScore = Math.max(0, 1 - (venue.latency / 100)); // Normalize to 100ms
    score += latencyScore * 0.4;
    
    // Fill rate score
    score += venue.fillRate * 0.3;
    
    // Cost score (lower is better)
    const costScore = Math.max(0, 1 - (venue.costPerShare / 0.01)); // Normalize to 1 cent
    score += costScore * 0.2;
    
    // Historical performance
    score += (metrics.profitability + 1) / 2 * 0.1; // Normalize to 0-1
    
    return score;
  }
  
  // Submit orders to selected venue
  private async submitOrders(routing: SmartRoutingDecision, signal: AlphaSignal): Promise<Order[]> {
    const orderId = this.generateOrderId();
    
    const order: Order = {
      id: orderId,
      client_order_id: orderId,
      symbol: signal.symbol,
      side: signal.signal > 0 ? 'buy' : 'sell',
      type: routing.orderType as any,
      time_in_force: routing.timeInForce as any,
      quantity: routing.quantity,
      filled_quantity: 0,
      remaining_quantity: routing.quantity,
      status: 'new',
      timestamp: Date.now(),
      submitted_at: Date.now()
    };
    
    // Add to active orders
    this.activeOrders.set(orderId, order);
    
    // Submit to venue (placeholder - would integrate with actual broker API)
    await this.submitToVenue(routing.venue, order);
    
    // Emit order event
    this.emit('order_submitted', order);
    
    return [order];
  }
  
  // Initialize execution venues
  private initializeVenues(): void {
    // Alpaca (primary venue)
    this.venues.set('alpaca', {
      id: 'alpaca',
      name: 'Alpaca Markets',
      enabled: true,
      latency: 50, // ms
      fillRate: 0.95,
      costPerShare: 0.0,
      maxOrderSize: 1000000,
      supportedOrderTypes: ['market', 'limit', 'stop', 'stop_limit'],
      marketHours: {
        open: '09:30',
        close: '16:00'
      }
    });
    
    // IEX (backup venue)
    this.venues.set('iex', {
      id: 'iex',
      name: 'IEX Exchange',
      enabled: true,
      latency: 75,
      fillRate: 0.92,
      costPerShare: 0.0009,
      maxOrderSize: 500000,
      supportedOrderTypes: ['market', 'limit'],
      marketHours: {
        open: '09:30',
        close: '16:00'
      }
    });
    
    // Initialize metrics
    for (const venue of this.venues.values()) {
      this.venueMetrics.set(venue.id, {
        avgLatency: venue.latency,
        fillRate: venue.fillRate,
        slippage: 0.0005, // 0.5 bps
        rejectRate: 0.02,
        profitability: 0.0,
        timestamp: Date.now()
      });
    }
  }
  
  // Get available venues for symbol
  private getAvailableVenues(symbol: string): ExecutionVenue[] {
    // Filter venues based on symbol, market hours, etc.
    return Array.from(this.venues.values()).filter(venue => {
      if (!venue.enabled) return false;
      
      // Check market hours (simplified)
      const now = new Date();
      const currentHour = now.getHours();
      const currentMinute = now.getMinutes();
      const currentTime = currentHour + currentMinute / 60;
      
      const openTime = parseFloat(venue.marketHours.open.replace(':', '.'));
      const closeTime = parseFloat(venue.marketHours.close.replace(':', '.'));
      
      return currentTime >= openTime && currentTime <= closeTime;
    });
  }
  
  // Submit order to specific venue
  private async submitToVenue(venueId: string, order: Order): Promise<void> {
    // This would integrate with actual broker/venue APIs
    // For now, simulate order submission
    
    const venue = this.venues.get(venueId);
    if (!venue) {
      throw new Error(`Unknown venue: ${venueId}`);
    }
    
    // Simulate network latency
    await new Promise(resolve => setTimeout(resolve, venue.latency));
    
    // Simulate order acceptance (95% success rate)
    if (Math.random() > 0.95) {
      order.status = 'rejected';
      order.rejected_reason = 'Venue rejected order';
      this.emit('order_rejected', order);
      return;
    }
    
    order.status = 'new';
    this.emit('order_accepted', order);
    
    // Simulate fill (would be real-time in production)
    setTimeout(() => {
      this.simulateOrderFill(order);
    }, venue.latency + Math.random() * 100);
  }
  
  // Simulate order fill (for testing)
  private simulateOrderFill(order: Order): void {
    const venue = Array.from(this.venues.values())[0]; // Use first venue for simulation
    
    // Simulate partial or full fill
    const fillProbability = venue.fillRate;
    
    if (Math.random() < fillProbability) {
      // Full fill
      order.filled_quantity = order.quantity;
      order.remaining_quantity = 0;
      order.status = 'filled';
      order.filled_at = Date.now();
      order.average_fill_price = 100 + (Math.random() - 0.5) * 0.1; // Simulate price
      
      this.emit('order_filled', order);
      
      // Remove from active orders
      this.activeOrders.delete(order.id);
      
      // Add to history
      if (!this.orderHistory.has(order.symbol)) {
        this.orderHistory.set(order.symbol, []);
      }
      this.orderHistory.get(order.symbol)!.push(order);
      
    } else {
      // Partial fill or no fill
      order.status = 'partially_filled';
      order.filled_quantity = Math.floor(order.quantity * Math.random() * 0.5);
      order.remaining_quantity = order.quantity - order.filled_quantity;
      
      this.emit('order_partially_filled', order);
    }
  }
  
  // Cancel all active orders
  private async cancelAllOrders(): Promise<void> {
    const cancelPromises = Array.from(this.activeOrders.values()).map(order => 
      this.cancelOrder(order.id)
    );
    
    await Promise.all(cancelPromises);
  }
  
  // Cancel specific order
  async cancelOrder(orderId: string): Promise<boolean> {
    const order = this.activeOrders.get(orderId);
    if (!order) return false;
    
    order.status = 'canceled';
    order.canceled_at = Date.now();
    
    this.activeOrders.delete(orderId);
    this.emit('order_canceled', order);
    
    return true;
  }
  
  // Performance monitoring
  private startVenueMonitoring(): void {
    setInterval(() => {
      this.updateVenueMetrics();
    }, 5000); // Update every 5 seconds
  }
  
  private startExecutionOptimization(): void {
    setInterval(() => {
      this.optimizeExecution();
    }, 30000); // Optimize every 30 seconds
  }
  
  private updateVenueMetrics(): void {
    // Update venue performance metrics based on recent orders
    for (const [venueId, venue] of this.venues) {
      const metrics = this.venueMetrics.get(venueId);
      if (!metrics) continue;
      
      // Calculate recent performance
      const recentOrders = this.getRecentOrdersForVenue(venueId);
      
      if (recentOrders.length > 0) {
        const filledOrders = recentOrders.filter(o => o.status === 'filled');
        metrics.fillRate = filledOrders.length / recentOrders.length;
        
        // Calculate average slippage
        const slippages = filledOrders
          .filter(o => o.average_fill_price)
          .map(o => Math.abs((o.average_fill_price! - 100) / 100)); // Placeholder price
        
        if (slippages.length > 0) {
          metrics.slippage = slippages.reduce((sum, s) => sum + s, 0) / slippages.length;
        }
        
        metrics.timestamp = Date.now();
      }
    }
  }
  
  private optimizeExecution(): void {
    // Analyze recent execution performance and adjust venue weights
    const recentLatencies = this.executionLatency.slice(-100);
    if (recentLatencies.length > 0) {
      const avgLatency = recentLatencies.reduce((sum, l) => sum + l, 0) / recentLatencies.length;
      
      if (avgLatency > 100) { // If average latency > 100ms
        this.logger.warn(`High execution latency detected: ${avgLatency.toFixed(2)}ms`);
        // Could trigger venue rebalancing or optimization
      }
    }
  }
  
  private getRecentOrdersForVenue(venueId: string): Order[] {
    // Get orders from last 5 minutes for this venue
    const fiveMinutesAgo = Date.now() - 5 * 60 * 1000;
    const allOrders = Array.from(this.orderHistory.values()).flat();
    
    return allOrders.filter(order => 
      order.timestamp > fiveMinutesAgo && 
      order.id.includes(venueId) // Simplified venue tracking
    );
  }
  
  private generateOrderId(): string {
    return `ORD_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }
  
  private async initializeVenueConnections(): Promise<void> {
    // Initialize connections to execution venues
    this.logger.info('Initializing venue connections...');
  }
  
  private async loadExecutionMetrics(): Promise<void> {
    // Load historical execution metrics from database
    this.logger.info('Loading execution metrics...');
  }
  
  // Public interface
  getExecutionMetrics(): ExecutionMetrics {
    const recentLatencies = this.executionLatency.slice(-100);
    const avgLatency = recentLatencies.length > 0 ? 
      recentLatencies.reduce((sum, l) => sum + l, 0) / recentLatencies.length : 0;
    
    const recentSlippage = this.slippageTracking.slice(-100);
    const avgSlippage = recentSlippage.length > 0 ?
      recentSlippage.reduce((sum, s) => sum + s, 0) / recentSlippage.length : 0;
    
    return {
      avgLatency,
      fillRate: 0.95, // Placeholder
      slippage: avgSlippage,
      rejectRate: 0.02, // Placeholder
      profitability: 0.0, // Placeholder
      timestamp: Date.now()
    };
  }
  
  getActiveOrders(): Order[] {
    return Array.from(this.activeOrders.values());
  }
  
  getOrderHistory(symbol?: string): Order[] {
    if (symbol) {
      return this.orderHistory.get(symbol) || [];
    }
    
    return Array.from(this.orderHistory.values()).flat();
  }
  
  getVenueStatus(): Map<string, ExecutionVenue> {
    return new Map(this.venues);
  }
}
