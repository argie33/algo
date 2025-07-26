/**
 * HFT Real-Time Execution Engine
 * Handles order execution, risk management, and strategy coordination
 */

const { createLogger } = require('../utils/structuredLogger');
const { sendServiceUnavailable, sendNotImplemented } = require('../utils/standardErrorResponses');

class HFTExecutionEngine {
  constructor(alpacaService, riskManager) {
    this.logger = createLogger('hft-execution-engine');
    this.alpacaService = alpacaService;
    this.riskManager = riskManager;
    
    // Execution state
    this.isActive = false;
    this.executionQueue = [];
    this.activeOrders = new Map();
    this.completedOrders = new Map();
    this.executionMetrics = {
      ordersExecuted: 0,
      successfulExecutions: 0,
      failedExecutions: 0,
      averageExecutionTime: 0,
      totalVolume: 0,
      totalPnL: 0,
      executionTimes: []
    };
    
    // Risk controls
    this.dailyLimits = {
      maxDailyTrades: 100,
      maxDailyLoss: 1000,
      maxPositionSize: 500,
      dailyTradeCount: 0,
      dailyPnL: 0
    };
    
    // Initialize execution loop
    this.executionInterval = null;
  }

  /**
   * Start the execution engine
   */
  async start() {
    if (this.isActive) {
      this.logger.warn('Execution engine already active');
      return { success: false, message: 'Engine already running' };
    }

    try {
      // Validate broker connection
      if (!this.alpacaService) {
        throw new Error('Alpaca service not configured');
      }

      // Test API connection
      const account = await this.alpacaService.getAccount();
      if (!account) {
        throw new Error('Unable to connect to Alpaca API');
      }

      this.isActive = true;
      this.startExecutionLoop();
      
      this.logger.info('HFT Execution Engine started', {
        accountStatus: account.account_blocked ? 'blocked' : 'active',
        buyingPower: account.buying_power,
        daytradeCount: account.daytrade_count
      });

      return {
        success: true,
        message: 'HFT Execution Engine started successfully',
        accountInfo: {
          accountId: account.id,
          status: account.status,
          buyingPower: parseFloat(account.buying_power),
          daytradeCount: account.daytrade_count,
          accountBlocked: account.account_blocked
        }
      };

    } catch (error) {
      this.logger.error('Failed to start execution engine', { error: error.message });
      return {
        success: false,
        message: 'Failed to start execution engine',
        error: error.message
      };
    }
  }

  /**
   * Stop the execution engine
   */
  async stop() {
    if (!this.isActive) {
      return { success: false, message: 'Engine not running' };
    }

    this.isActive = false;
    
    if (this.executionInterval) {
      clearInterval(this.executionInterval);
      this.executionInterval = null;
    }

    // Cancel all pending orders
    await this.cancelAllPendingOrders();

    this.logger.info('HFT Execution Engine stopped');
    return { success: true, message: 'Execution engine stopped successfully' };
  }

  /**
   * Start the main execution loop
   */
  startExecutionLoop() {
    this.executionInterval = setInterval(async () => {
      if (this.executionQueue.length > 0) {
        await this.processExecutionQueue();
      }
    }, 100); // Process every 100ms for high frequency
  }

  /**
   * Add order to execution queue
   */
  async queueOrder(orderRequest) {
    const orderId = `order-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    
    // Pre-execution risk checks
    const riskCheck = await this.performRiskCheck(orderRequest);
    if (!riskCheck.approved) {
      this.logger.warn('Order rejected by risk management', {
        orderId,
        reason: riskCheck.reason,
        orderRequest
      });
      return {
        success: false,
        orderId,
        status: 'rejected',
        reason: riskCheck.reason
      };
    }

    const orderWithMetadata = {
      ...orderRequest,
      orderId,
      timestamp: Date.now(),
      status: 'queued',
      riskApproved: true,
      priority: orderRequest.priority || 'normal'
    };

    // Add to queue with priority handling
    if (orderRequest.priority === 'urgent') {
      this.executionQueue.unshift(orderWithMetadata);
    } else {
      this.executionQueue.push(orderWithMetadata);
    }

    this.logger.info('Order queued for execution', {
      orderId,
      symbol: orderRequest.symbol,
      side: orderRequest.side,
      quantity: orderRequest.qty,
      orderType: orderRequest.type,
      queueLength: this.executionQueue.length
    });

    return {
      success: true,
      orderId,
      status: 'queued',
      queuePosition: this.executionQueue.length
    };
  }

  /**
   * Process the execution queue
   */
  async processExecutionQueue() {
    if (this.executionQueue.length === 0) return;

    const order = this.executionQueue.shift();
    await this.executeOrder(order);
  }

  /**
   * Execute a single order
   */
  async executeOrder(order) {
    const startTime = Date.now();
    
    try {
      this.logger.info('Executing order', {
        orderId: order.orderId,
        symbol: order.symbol,
        side: order.side,
        quantity: order.qty
      });

      // Update order status
      order.status = 'executing';
      this.activeOrders.set(order.orderId, order);

      // Execute order through Alpaca
      const alpacaOrder = await this.alpacaService.createOrder({
        symbol: order.symbol,
        qty: order.qty,
        side: order.side,
        type: order.type || 'market',
        time_in_force: order.time_in_force || 'day',
        limit_price: order.limit_price,
        stop_price: order.stop_price
      });

      // Track execution metrics
      const executionTime = Date.now() - startTime;
      this.executionMetrics.executionTimes.push(executionTime);
      this.executionMetrics.averageExecutionTime = 
        this.executionMetrics.executionTimes.reduce((a, b) => a + b, 0) / 
        this.executionMetrics.executionTimes.length;

      // Update order with Alpaca response
      order.alpacaOrderId = alpacaOrder.id;
      order.status = alpacaOrder.status;
      order.executionTime = executionTime;
      order.completedAt = Date.now();

      // Move to completed orders
      this.activeOrders.delete(order.orderId);
      this.completedOrders.set(order.orderId, order);

      // Update metrics
      this.executionMetrics.ordersExecuted++;
      this.dailyLimits.dailyTradeCount++;
      
      if (alpacaOrder.status === 'filled') {
        this.executionMetrics.successfulExecutions++;
        this.logger.info('Order executed successfully', {
          orderId: order.orderId,
          alpacaOrderId: alpacaOrder.id,
          executionTime,
          fillPrice: alpacaOrder.filled_avg_price
        });
      } else {
        this.logger.warn('Order execution pending', {
          orderId: order.orderId,
          alpacaOrderId: alpacaOrder.id,
          status: alpacaOrder.status
        });
      }

      return {
        success: true,
        orderId: order.orderId,
        alpacaOrderId: alpacaOrder.id,
        status: alpacaOrder.status,
        executionTime
      };

    } catch (error) {
      this.logger.error('Order execution failed', {
        orderId: order.orderId,
        error: error.message,
        executionTime: Date.now() - startTime
      });

      // Update failed order
      order.status = 'failed';
      order.error = error.message;
      order.completedAt = Date.now();
      
      this.activeOrders.delete(order.orderId);
      this.completedOrders.set(order.orderId, order);
      
      this.executionMetrics.failedExecutions++;

      return {
        success: false,
        orderId: order.orderId,
        error: error.message,
        status: 'failed'
      };
    }
  }

  /**
   * Perform risk management checks
   */
  async performRiskCheck(orderRequest) {
    // Daily trade limit check
    if (this.dailyLimits.dailyTradeCount >= this.dailyLimits.maxDailyTrades) {
      return {
        approved: false,
        reason: 'Daily trade limit exceeded'
      };
    }

    // Position size check
    const orderValue = orderRequest.qty * (orderRequest.limit_price || 100); // Estimate
    if (orderValue > this.dailyLimits.maxPositionSize) {
      return {
        approved: false,
        reason: 'Position size exceeds limit'
      };
    }

    // Daily loss limit check
    if (this.dailyLimits.dailyPnL < -this.dailyLimits.maxDailyLoss) {
      return {
        approved: false,
        reason: 'Daily loss limit reached'
      };
    }

    // Additional risk checks through risk manager
    if (this.riskManager) {
      const riskAssessment = await this.riskManager.assessOrderRisk(orderRequest);
      if (!riskAssessment.approved) {
        return riskAssessment;
      }
    }

    return { approved: true };
  }

  /**
   * Cancel all pending orders
   */
  async cancelAllPendingOrders() {
    const cancelPromises = [];
    
    for (const [orderId, order] of this.activeOrders) {
      if (order.alpacaOrderId && order.status !== 'filled') {
        cancelPromises.push(
          this.alpacaService.cancelOrder(order.alpacaOrderId)
            .catch(error => {
              this.logger.error('Failed to cancel order', {
                orderId,
                alpacaOrderId: order.alpacaOrderId,
                error: error.message
              });
            })
        );
      }
    }

    await Promise.all(cancelPromises);
    this.executionQueue = [];
    this.activeOrders.clear();
  }

  /**
   * Get execution metrics
   */
  getMetrics() {
    return {
      ...this.executionMetrics,
      queueLength: this.executionQueue.length,
      activeOrders: this.activeOrders.size,
      completedOrders: this.completedOrders.size,
      dailyLimits: this.dailyLimits,
      isActive: this.isActive,
      uptime: this.isActive ? Date.now() - this.startTime : 0
    };
  }

  /**
   * Get order status
   */
  getOrderStatus(orderId) {
    if (this.activeOrders.has(orderId)) {
      return this.activeOrders.get(orderId);
    }
    
    if (this.completedOrders.has(orderId)) {
      return this.completedOrders.get(orderId);
    }

    // Check queue
    const queuedOrder = this.executionQueue.find(order => order.orderId === orderId);
    if (queuedOrder) {
      return queuedOrder;
    }

    return null;
  }
}

module.exports = HFTExecutionEngine;