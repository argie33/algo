import { BaseEngine, Signal, Order, OrderSide, OrderType, OrderStatus, TimeInForce, OrderFill, OrderRejectionError } from '../../types';
import { Config } from '../../config';
import { Logger } from 'pino';
import { AlpacaApi } from '@alpacahq/alpaca-trade-api';
import { v4 as uuidv4 } from 'uuid';

export interface OrderExecutionConfig {
  defaultOrderType: OrderType;
  defaultTimeInForce: TimeInForce;
  maxRetries: number;
  retryDelay: number;
  executionTimeout: number;
  slippageTolerance: number;
}

/**
 * High-performance order management and execution engine
 */
export class OrderEngine extends BaseEngine {
  private alpaca: AlpacaApi;
  private activeOrders: Map<string, Order> = new Map();
  private orderHistory: Order[] = [];
  private executionQueue: Signal[] = [];
  private isProcessingQueue: boolean = false;

  private readonly executionConfig: OrderExecutionConfig = {
    defaultOrderType: OrderType.MARKET,
    defaultTimeInForce: TimeInForce.DAY,
    maxRetries: 3,
    retryDelay: 100,
    executionTimeout: 5000,
    slippageTolerance: 0.002 // 0.2%
  };

  constructor(config: Config, logger: Logger) {
    super('OrderEngine', config, logger);
    
    this.alpaca = new AlpacaApi({
      credentials: {
        key: config.alpaca.keyId,
        secret: config.alpaca.secretKey,
        paper: config.alpaca.paper
      },
      baseUrl: config.alpaca.baseUrl
    });
  }

  async initialize(): Promise<void> {
    this.logger.info('Initializing Order Engine...');
    
    try {
      // Test connection
      const account = await this.alpaca.getAccount();
      this.logger.info({ accountId: account.id, buyingPower: account.buying_power }, 'Order Engine connected to Alpaca');
      
      // Start order processing
      this.startOrderProcessing();
      
      this.logger.info('Order Engine initialized successfully');
      
    } catch (error) {
      this.logger.error({ error }, 'Failed to initialize Order Engine');
      throw error;
    }
  }

  async start(): Promise<void> {
    if (this.isRunning) return;
    
    this.logger.info('Starting Order Engine...');
    this.isRunning = true;
    
    this.logger.info('Order Engine started successfully');
  }

  async stop(): Promise<void> {
    if (!this.isRunning) return;
    
    this.logger.info('Stopping Order Engine...');
    this.isRunning = false;
    
    // Cancel all active orders
    await this.cancelAllActiveOrders();
    
    this.logger.info('Order Engine stopped');
  }

  /**
   * Process a signal and create orders
   */
  async processSignal(signal: Signal): Promise<void> {
    if (!this.isRunning) {
      throw new OrderRejectionError('Order engine not running');
    }

    const startTime = performance.now();
    
    try {
      // Add to execution queue
      this.executionQueue.push(signal);
      
      // Update metrics
      this.incrementMetric('signals_received');
      this.updateMetric('queue_size', this.executionQueue.length);
      
      this.logger.debug({ signalId: signal.id, symbol: signal.symbol }, 'Signal queued for execution');
      
    } catch (error) {
      const latency = performance.now() - startTime;
      this.updateMetric('signal_processing_latency', latency);
      this.incrementMetric('signal_processing_errors');
      
      this.logger.error({ error, signal }, 'Failed to process signal');
      throw error;
    }
  }

  /**
   * Start order processing loop
   */
  private startOrderProcessing(): void {
    const processQueue = async () => {
      if (this.isProcessingQueue || this.executionQueue.length === 0) {
        setTimeout(processQueue, 10); // Check every 10ms for ultra-low latency
        return;
      }

      this.isProcessingQueue = true;

      try {
        const signal = this.executionQueue.shift();
        if (signal) {
          await this.executeSignal(signal);
        }
      } catch (error) {
        this.logger.error({ error }, 'Error processing order queue');
      } finally {
        this.isProcessingQueue = false;
      }

      // Immediate next processing
      setImmediate(processQueue);
    };

    processQueue();
  }

  /**
   * Execute a signal by creating and submitting orders
   */
  private async executeSignal(signal: Signal): Promise<void> {
    const startTime = performance.now();
    
    try {
      // Create order from signal
      const order = this.createOrderFromSignal(signal);
      
      if (!order) {
        this.logger.warn({ signal }, 'Failed to create order from signal');
        return;
      }

      // Submit order
      await this.submitOrder(order);
      
      const latency = performance.now() - startTime;
      this.updateMetric('order_execution_latency', latency);
      this.incrementMetric('orders_submitted');
      
      this.logger.info({ 
        orderId: order.id, 
        symbol: order.symbol, 
        side: order.side,
        quantity: order.quantity,
        latency 
      }, 'Order executed');
      
    } catch (error) {
      const latency = performance.now() - startTime;
      this.updateMetric('order_execution_latency', latency);
      this.incrementMetric('order_execution_errors');
      
      this.logger.error({ error, signal }, 'Failed to execute signal');
    }
  }

  /**
   * Create order from signal
   */
  private createOrderFromSignal(signal: Signal): Order | null {
    try {
      const symbolConfig = this.config.getSymbolConfig(signal.symbol);
      if (!symbolConfig) {
        this.logger.warn({ symbol: signal.symbol }, 'Symbol configuration not found');
        return null;
      }

      // Calculate order quantity based on signal strength and position sizing
      const orderQuantity = this.calculateOrderQuantity(signal, symbolConfig);
      
      if (orderQuantity <= 0) {
        this.logger.debug({ signal }, 'Order quantity too small, skipping');
        return null;
      }

      const order: Order = {
        id: uuidv4(),
        client_order_id: `signal-${signal.id}`,
        symbol: signal.symbol,
        side: signal.type === 'buy' ? OrderSide.BUY : OrderSide.SELL,
        type: this.selectOrderType(signal),
        time_in_force: this.executionConfig.defaultTimeInForce,
        quantity: orderQuantity,
        filled_quantity: 0,
        remaining_quantity: orderQuantity,
        status: OrderStatus.PENDING,
        timestamp: Date.now(),
        price: signal.target_price,
        stop_price: signal.stop_loss,
        limit_price: signal.target_price
      };

      return order;

    } catch (error) {
      this.logger.error({ error, signal }, 'Failed to create order from signal');
      return null;
    }
  }

  /**
   * Calculate order quantity based on signal and risk parameters
   */
  private calculateOrderQuantity(signal: Signal, symbolConfig: any): number {
    // Position sizing based on signal strength and risk limits
    const maxPositionSize = symbolConfig.maxPositionSize;
    const signalStrength = signal.strength;
    
    // Base quantity as percentage of max position size
    const baseQuantity = maxPositionSize * 0.1; // 10% of max position
    
    // Adjust by signal strength
    const adjustedQuantity = baseQuantity * signalStrength;
    
    // Ensure minimum order size
    const minOrderSize = 1;
    
    return Math.max(minOrderSize, Math.floor(adjustedQuantity));
  }

  /**
   * Select appropriate order type based on signal
   */
  private selectOrderType(signal: Signal): OrderType {
    // Use limit orders for better execution quality
    if (signal.target_price) {
      return OrderType.LIMIT;
    }
    
    // Use market orders for high-conviction signals
    if (signal.strength > 0.8) {
      return OrderType.MARKET;
    }
    
    return this.executionConfig.defaultOrderType;
  }

  /**
   * Submit order to Alpaca
   */
  private async submitOrder(order: Order): Promise<void> {
    try {
      // Update order status
      order.status = OrderStatus.NEW;
      order.submitted_at = Date.now();
      
      // Store in active orders
      this.activeOrders.set(order.id, order);
      
      // Prepare Alpaca order request
      const alpacaOrder: any = {
        symbol: order.symbol,
        qty: order.quantity,
        side: order.side,
        type: order.type,
        time_in_force: order.time_in_force,
        client_order_id: order.client_order_id
      };

      // Add price parameters based on order type
      if (order.type === OrderType.LIMIT && order.limit_price) {
        alpacaOrder.limit_price = order.limit_price;
      }
      
      if (order.type === OrderType.STOP && order.stop_price) {
        alpacaOrder.stop_price = order.stop_price;
      }
      
      if (order.type === OrderType.STOP_LIMIT && order.stop_price && order.limit_price) {
        alpacaOrder.stop_price = order.stop_price;
        alpacaOrder.limit_price = order.limit_price;
      }

      // Submit to Alpaca
      const alpacaResponse = await this.alpaca.createOrder(alpacaOrder);
      
      // Update order with Alpaca response
      order.id = alpacaResponse.id;
      order.status = this.mapAlpacaStatus(alpacaResponse.status);
      
      this.logger.info({ orderId: order.id, alpacaId: alpacaResponse.id }, 'Order submitted to Alpaca');
      
      // Emit order placed event
      this.emit('orderPlaced', order);
      
      // Start monitoring order status
      this.monitorOrder(order);
      
    } catch (error) {
      order.status = OrderStatus.REJECTED;
      order.rejected_reason = error.message;
      
      this.logger.error({ error, order }, 'Failed to submit order to Alpaca');
      this.incrementMetric('order_rejections');
      
      throw new OrderRejectionError('Failed to submit order', { order, error });
    }
  }

  /**
   * Monitor order status and handle fills
   */
  private async monitorOrder(order: Order): Promise<void> {
    const checkStatus = async () => {
      try {
        const alpacaOrder = await this.alpaca.getOrder({ order_id: order.id });
        
        const previousStatus = order.status;
        order.status = this.mapAlpacaStatus(alpacaOrder.status);
        order.filled_quantity = parseFloat(alpacaOrder.filled_qty || '0');
        order.remaining_quantity = order.quantity - order.filled_quantity;
        order.average_fill_price = parseFloat(alpacaOrder.filled_avg_price || '0');

        // Check for status changes
        if (order.status !== previousStatus) {
          this.handleOrderStatusChange(order, previousStatus);
        }

        // Continue monitoring if order is still active
        if (this.isOrderActive(order.status)) {
          setTimeout(checkStatus, 100); // Check every 100ms
        } else {
          this.activeOrders.delete(order.id);
          this.orderHistory.push(order);
        }

      } catch (error) {
        this.logger.error({ error, orderId: order.id }, 'Failed to check order status');
      }
    };

    // Start monitoring with small delay
    setTimeout(checkStatus, 50);
  }

  /**
   * Handle order status changes
   */
  private handleOrderStatusChange(order: Order, previousStatus: OrderStatus): void {
    this.logger.info({ 
      orderId: order.id, 
      symbol: order.symbol,
      previousStatus, 
      newStatus: order.status,
      filledQuantity: order.filled_quantity
    }, 'Order status changed');

    switch (order.status) {
      case OrderStatus.FILLED:
        this.handleOrderFilled(order);
        break;
      case OrderStatus.PARTIALLY_FILLED:
        this.handlePartialFill(order);
        break;
      case OrderStatus.CANCELED:
        this.handleOrderCanceled(order);
        break;
      case OrderStatus.REJECTED:
        this.handleOrderRejected(order);
        break;
    }
  }

  /**
   * Handle order filled
   */
  private handleOrderFilled(order: Order): void {
    order.filled_at = Date.now();
    
    const fill: OrderFill = {
      id: uuidv4(),
      order_id: order.id,
      symbol: order.symbol,
      side: order.side,
      quantity: order.filled_quantity,
      price: order.average_fill_price || 0,
      commission: 0, // Alpaca commission-free
      exchange: 'ALPACA',
      timestamp: order.filled_at
    };

    this.incrementMetric('orders_filled');
    this.updateMetric(`${order.symbol}_last_fill_price`, fill.price);
    
    // Emit order filled event
    this.emit('orderFilled', fill);
    
    this.logger.info({ fill }, 'Order filled');
  }

  /**
   * Handle partial fill
   */
  private handlePartialFill(order: Order): void {
    const partialFill: OrderFill = {
      id: uuidv4(),
      order_id: order.id,
      symbol: order.symbol,
      side: order.side,
      quantity: order.filled_quantity,
      price: order.average_fill_price || 0,
      commission: 0,
      exchange: 'ALPACA',
      timestamp: Date.now()
    };

    this.incrementMetric('partial_fills');
    
    // Emit partial fill event
    this.emit('partialFilled', partialFill);
  }

  /**
   * Handle order canceled
   */
  private handleOrderCanceled(order: Order): void {
    order.canceled_at = Date.now();
    this.incrementMetric('orders_canceled');
    
    this.logger.info({ orderId: order.id }, 'Order canceled');
  }

  /**
   * Handle order rejected
   */
  private handleOrderRejected(order: Order): void {
    this.incrementMetric('orders_rejected');
    
    this.logger.warn({ 
      orderId: order.id, 
      reason: order.rejected_reason 
    }, 'Order rejected');
  }

  /**
   * Cancel all active orders
   */
  private async cancelAllActiveOrders(): Promise<void> {
    const cancelPromises = Array.from(this.activeOrders.values()).map(order => 
      this.cancelOrder(order.id).catch(error => 
        this.logger.error({ error, orderId: order.id }, 'Failed to cancel order')
      )
    );

    await Promise.all(cancelPromises);
  }

  /**
   * Cancel specific order
   */
  async cancelOrder(orderId: string): Promise<void> {
    try {
      await this.alpaca.cancelOrder({ order_id: orderId });
      this.logger.info({ orderId }, 'Order cancellation requested');
    } catch (error) {
      this.logger.error({ error, orderId }, 'Failed to cancel order');
      throw error;
    }
  }

  /**
   * Map Alpaca order status to internal status
   */
  private mapAlpacaStatus(alpacaStatus: string): OrderStatus {
    switch (alpacaStatus?.toLowerCase()) {
      case 'new':
      case 'accepted':
        return OrderStatus.NEW;
      case 'partially_filled':
        return OrderStatus.PARTIALLY_FILLED;
      case 'filled':
        return OrderStatus.FILLED;
      case 'canceled':
        return OrderStatus.CANCELED;
      case 'rejected':
        return OrderStatus.REJECTED;
      case 'expired':
        return OrderStatus.EXPIRED;
      default:
        return OrderStatus.PENDING;
    }
  }

  /**
   * Check if order status is active
   */
  private isOrderActive(status: OrderStatus): boolean {
    return [
      OrderStatus.PENDING,
      OrderStatus.NEW,
      OrderStatus.PARTIALLY_FILLED
    ].includes(status);
  }

  /**
   * Get active orders
   */
  getActiveOrders(): Order[] {
    return Array.from(this.activeOrders.values());
  }

  /**
   * Get order history
   */
  getOrderHistory(): Order[] {
    return [...this.orderHistory];
  }

  /**
   * Get order by ID
   */
  getOrder(orderId: string): Order | undefined {
    return this.activeOrders.get(orderId) || 
           this.orderHistory.find(order => order.id === orderId);
  }
}
