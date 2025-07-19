/**
 * Trading Service Unit Tests
 * Comprehensive testing of order management and trade execution functionality
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Real Trading Service - Import actual production service
import socialTradingService from '../../../services/socialTradingService';
import aiTradingSignals from '../../../services/aiTradingSignals';
import api from '../../../services/api';
import realTimeDataService from '../../../services/realTimeDataService';

// Mock external dependencies but use real service
vi.mock('../../../services/api');
vi.mock('../../../services/realTimeDataService');

describe('📈 Trading Service', () => {
  let mockApi;
  let mockRealTimeData;

  beforeEach(() => {
    mockApi = {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn()
    };

    mockWebSocket = {
      connect: vi.fn(),
      subscribe: vi.fn(),
      unsubscribe: vi.fn(),
      on: vi.fn(),
      emit: vi.fn()
    };

    mockValidation = {
      validateOrder: vi.fn(),
      validateBuyingPower: vi.fn(),
      validateMarketHours: vi.fn(),
      validateRiskLimits: vi.fn()
    };

    apiClient.mockReturnValue(mockApi);
    webSocketService.mockReturnValue(mockWebSocket);
    validationService.mockReturnValue(mockValidation);

    tradingService = new TradingService();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  describe('Order Management', () => {
    const mockOrderData = {
      symbol: 'AAPL',
      side: 'buy',
      quantity: 100,
      orderType: 'market',
      timeInForce: 'day'
    };

    const mockOrder = {
      id: 'order_123',
      ...mockOrderData,
      status: 'pending',
      submittedAt: '2024-01-15T10:30:00Z',
      estimatedValue: 18550
    };

    it('should place market order successfully', async () => {
      mockValidation.validateOrder.mockReturnValue({ valid: true });
      mockValidation.validateBuyingPower.mockReturnValue({ sufficient: true });
      mockValidation.validateMarketHours.mockReturnValue({ open: true });
      mockApi.post.mockResolvedValue({ data: { order: mockOrder } });

      const result = await tradingService.placeOrder(mockOrderData);

      expect(mockValidation.validateOrder).toHaveBeenCalledWith(mockOrderData);
      expect(mockValidation.validateBuyingPower).toHaveBeenCalled();
      expect(mockApi.post).toHaveBeenCalledWith('/orders', mockOrderData);
      expect(result.order.id).toBe('order_123');
      expect(result.order.status).toBe('pending');
    });

    it('should place limit order with price', async () => {
      const limitOrderData = {
        ...mockOrderData,
        orderType: 'limit',
        limitPrice: 185.50
      };

      mockValidation.validateOrder.mockReturnValue({ valid: true });
      mockValidation.validateBuyingPower.mockReturnValue({ sufficient: true });
      mockValidation.validateMarketHours.mockReturnValue({ open: true });
      mockApi.post.mockResolvedValue({ data: { order: { ...mockOrder, orderType: 'limit', limitPrice: 185.50 } } });

      const result = await tradingService.placeOrder(limitOrderData);

      expect(result.order.orderType).toBe('limit');
      expect(result.order.limitPrice).toBe(185.50);
    });

    it('should place stop-loss order', async () => {
      const stopOrderData = {
        ...mockOrderData,
        orderType: 'stop',
        stopPrice: 175.00,
        side: 'sell'
      };

      mockValidation.validateOrder.mockReturnValue({ valid: true });
      mockApi.post.mockResolvedValue({ data: { order: { ...mockOrder, ...stopOrderData } } });

      const result = await tradingService.placeOrder(stopOrderData);

      expect(result.order.orderType).toBe('stop');
      expect(result.order.stopPrice).toBe(175.00);
      expect(result.order.side).toBe('sell');
    });

    it('should handle order validation failures', async () => {
      mockValidation.validateOrder.mockReturnValue({ 
        valid: false, 
        errors: ['Invalid quantity'] 
      });

      await expect(tradingService.placeOrder(mockOrderData))
        .rejects.toThrow('Order validation failed: Invalid quantity');

      expect(mockApi.post).not.toHaveBeenCalled();
    });

    it('should handle insufficient buying power', async () => {
      mockValidation.validateOrder.mockReturnValue({ valid: true });
      mockValidation.validateBuyingPower.mockReturnValue({ 
        sufficient: false, 
        required: 18550, 
        available: 15000 
      });

      await expect(tradingService.placeOrder(mockOrderData))
        .rejects.toThrow('Insufficient buying power');

      expect(mockApi.post).not.toHaveBeenCalled();
    });

    it('should handle market closed scenarios', async () => {
      mockValidation.validateOrder.mockReturnValue({ valid: true });
      mockValidation.validateBuyingPower.mockReturnValue({ sufficient: true });
      mockValidation.validateMarketHours.mockReturnValue({ 
        open: false, 
        nextOpen: '2024-01-16T09:30:00Z' 
      });

      // Should still allow order placement but warn about extended hours
      mockApi.post.mockResolvedValue({ data: { order: { ...mockOrder, status: 'queued' } } });

      const result = await tradingService.placeOrder(mockOrderData);

      expect(result.order.status).toBe('queued');
    });
  });

  describe('Order Status and Management', () => {
    it('should get order by ID', async () => {
      const mockOrderDetail = {
        id: 'order_123',
        symbol: 'AAPL',
        status: 'filled',
        filledQuantity: 100,
        filledPrice: 185.75,
        fills: [
          { quantity: 50, price: 185.50, timestamp: '2024-01-15T10:30:15Z' },
          { quantity: 50, price: 186.00, timestamp: '2024-01-15T10:30:17Z' }
        ]
      };

      mockApi.get.mockResolvedValue({ data: { order: mockOrderDetail } });

      const order = await tradingService.getOrder('order_123');

      expect(mockApi.get).toHaveBeenCalledWith('/orders/order_123');
      expect(order.status).toBe('filled');
      expect(order.fills).toHaveLength(2);
    });

    it('should get order history with filters', async () => {
      const filters = {
        symbol: 'AAPL',
        status: 'filled',
        startDate: '2024-01-01',
        endDate: '2024-01-31'
      };

      const mockOrderHistory = [
        { id: 'order_1', symbol: 'AAPL', status: 'filled' },
        { id: 'order_2', symbol: 'AAPL', status: 'filled' }
      ];

      mockApi.get.mockResolvedValue({ data: { orders: mockOrderHistory } });

      const orders = await tradingService.getOrderHistory(filters);

      expect(mockApi.get).toHaveBeenCalledWith('/orders', { params: filters });
      expect(orders).toHaveLength(2);
    });

    it('should cancel pending order', async () => {
      mockApi.delete.mockResolvedValue({ 
        data: { 
          order: { id: 'order_123', status: 'cancelled' },
          message: 'Order cancelled successfully'
        } 
      });

      const result = await tradingService.cancelOrder('order_123');

      expect(mockApi.delete).toHaveBeenCalledWith('/orders/order_123');
      expect(result.order.status).toBe('cancelled');
    });

    it('should modify existing order', async () => {
      const modifications = {
        quantity: 150,
        limitPrice: 180.00
      };

      mockApi.put.mockResolvedValue({ 
        data: { 
          order: { id: 'order_123', ...modifications, status: 'modified' }
        } 
      });

      const result = await tradingService.modifyOrder('order_123', modifications);

      expect(mockApi.put).toHaveBeenCalledWith('/orders/order_123', modifications);
      expect(result.order.quantity).toBe(150);
      expect(result.order.limitPrice).toBe(180.00);
    });
  });

  describe('Position Management', () => {
    it('should get current positions', async () => {
      const mockPositions = [
        {
          symbol: 'AAPL',
          quantity: 100,
          averagePrice: 175.25,
          currentPrice: 185.50,
          marketValue: 18550,
          unrealizedPnL: 1025
        },
        {
          symbol: 'GOOGL',
          quantity: 25,
          averagePrice: 2800.00,
          currentPrice: 2850.00,
          marketValue: 71250,
          unrealizedPnL: 1250
        }
      ];

      mockApi.get.mockResolvedValue({ data: { positions: mockPositions } });

      const positions = await tradingService.getPositions();

      expect(mockApi.get).toHaveBeenCalledWith('/positions');
      expect(positions).toHaveLength(2);
      expect(positions[0].unrealizedPnL).toBe(1025);
    });

    it('should close position completely', async () => {
      const closeOrderData = {
        symbol: 'AAPL',
        quantity: 100,
        orderType: 'market'
      };

      mockApi.post.mockResolvedValue({ 
        data: { 
          order: { id: 'order_456', symbol: 'AAPL', side: 'sell', quantity: 100 }
        } 
      });

      const result = await tradingService.closePosition('AAPL', 100);

      expect(mockApi.post).toHaveBeenCalledWith('/positions/AAPL/close', { quantity: 100 });
      expect(result.order.side).toBe('sell');
    });

    it('should partially close position', async () => {
      mockApi.post.mockResolvedValue({ 
        data: { 
          order: { id: 'order_789', symbol: 'AAPL', side: 'sell', quantity: 50 }
        } 
      });

      const result = await tradingService.closePosition('AAPL', 50);

      expect(result.order.quantity).toBe(50);
    });
  });

  describe('Account Information', () => {
    it('should get account summary', async () => {
      const mockAccountSummary = {
        totalValue: 125000,
        buyingPower: 50000,
        cashBalance: 25000,
        marginUsed: 75000,
        dayTradingBuyingPower: 200000,
        maintenanceMargin: 15000
      };

      mockApi.get.mockResolvedValue({ data: { account: mockAccountSummary } });

      const account = await tradingService.getAccountSummary();

      expect(mockApi.get).toHaveBeenCalledWith('/account');
      expect(account.totalValue).toBe(125000);
      expect(account.buyingPower).toBe(50000);
    });

    it('should get buying power details', async () => {
      const mockBuyingPower = {
        cash: 25000,
        marginBuyingPower: 50000,
        dayTradingBuyingPower: 200000,
        maintenanceMargin: 15000,
        availableForTrading: 50000
      };

      mockApi.get.mockResolvedValue({ data: { buyingPower: mockBuyingPower } });

      const buyingPower = await tradingService.getBuyingPower();

      expect(mockApi.get).toHaveBeenCalledWith('/account/buying-power');
      expect(buyingPower.availableForTrading).toBe(50000);
    });

    it('should get trading restrictions', async () => {
      const mockRestrictions = {
        dayTradeCount: 2,
        dayTradeLimit: 3,
        isPatternDayTrader: false,
        marginCallAmount: 0,
        restrictions: []
      };

      mockApi.get.mockResolvedValue({ data: { restrictions: mockRestrictions } });

      const restrictions = await tradingService.getTradingRestrictions();

      expect(mockApi.get).toHaveBeenCalledWith('/account/restrictions');
      expect(restrictions.dayTradeCount).toBe(2);
      expect(restrictions.isPatternDayTrader).toBe(false);
    });
  });

  describe('Real-time Order Updates', () => {
    it('should subscribe to order updates', () => {
      const callback = vi.fn();

      tradingService.subscribeToOrderUpdates(callback);

      expect(mockWebSocket.subscribe).toHaveBeenCalledWith('order_updates');
      expect(mockWebSocket.on).toHaveBeenCalledWith('order_update', expect.any(Function));
    });

    it('should handle order status updates', () => {
      const callback = vi.fn();
      const orderUpdate = {
        orderId: 'order_123',
        status: 'filled',
        filledQuantity: 100,
        filledPrice: 185.75
      };

      tradingService.subscribeToOrderUpdates(callback);
      
      // Simulate WebSocket message
      const updateHandler = mockWebSocket.on.mock.calls.find(call => call[0] === 'order_update')[1];
      updateHandler(orderUpdate);

      expect(callback).toHaveBeenCalledWith(orderUpdate);
    });

    it('should unsubscribe from order updates', () => {
      tradingService.unsubscribeFromOrderUpdates();

      expect(mockWebSocket.unsubscribe).toHaveBeenCalledWith('order_updates');
    });
  });

  describe('Risk Management', () => {
    it('should validate position size limits', async () => {
      const orderData = {
        symbol: 'AAPL',
        quantity: 1000, // Large quantity
        orderType: 'market',
        side: 'buy'
      };

      mockValidation.validateRiskLimits.mockReturnValue({
        valid: false,
        violations: ['Position size exceeds maximum allowed']
      });

      await expect(tradingService.placeOrder(orderData))
        .rejects.toThrow('Risk limit violation: Position size exceeds maximum allowed');
    });

    it('should calculate order impact on portfolio', async () => {
      const orderData = {
        symbol: 'AAPL',
        quantity: 100,
        estimatedPrice: 185.50
      };

      const mockImpactAnalysis = {
        portfolioValueChange: 18550,
        newPortfolioValue: 143550,
        positionConcentration: 0.129, // 12.9%
        sectorConcentration: 0.45, // 45% in tech
        riskImpact: {
          volatilityChange: 0.02,
          betaChange: 0.05
        }
      };

      mockApi.post.mockResolvedValue({ data: { impact: mockImpactAnalysis } });

      const impact = await tradingService.analyzeOrderImpact(orderData);

      expect(mockApi.post).toHaveBeenCalledWith('/orders/analyze-impact', orderData);
      expect(impact.positionConcentration).toBe(0.129);
      expect(impact.riskImpact.volatilityChange).toBe(0.02);
    });

    it('should handle day trading rules', async () => {
      const orderData = {
        symbol: 'AAPL',
        quantity: 100,
        orderType: 'market',
        side: 'buy'
      };

      // Mock already having a day trade for this symbol
      mockApi.get.mockResolvedValue({ 
        data: { 
          restrictions: { 
            dayTradeCount: 3, 
            dayTradeLimit: 3,
            wouldExceedLimit: true
          } 
        } 
      });

      await expect(tradingService.placeOrder(orderData))
        .rejects.toThrow('Day trading limit would be exceeded');
    });
  });

  describe('Order Presets and Templates', () => {
    it('should save order preset', async () => {
      const presetData = {
        name: 'AAPL Buy Strategy',
        symbol: 'AAPL',
        orderType: 'limit',
        timeInForce: 'gtc',
        percentBelow: 2.0 // 2% below current price
      };

      mockApi.post.mockResolvedValue({ 
        data: { 
          preset: { id: 'preset_123', ...presetData }
        } 
      });

      const result = await tradingService.saveOrderPreset(presetData);

      expect(mockApi.post).toHaveBeenCalledWith('/order-presets', presetData);
      expect(result.preset.name).toBe('AAPL Buy Strategy');
    });

    it('should execute order from preset', async () => {
      const presetId = 'preset_123';
      const executionParams = {
        quantity: 100,
        currentPrice: 185.50
      };

      mockApi.post.mockResolvedValue({ 
        data: { 
          order: { 
            id: 'order_789',
            symbol: 'AAPL',
            quantity: 100,
            limitPrice: 181.79 // 2% below current price
          }
        } 
      });

      const result = await tradingService.executePreset(presetId, executionParams);

      expect(mockApi.post).toHaveBeenCalledWith(`/order-presets/${presetId}/execute`, executionParams);
      expect(result.order.limitPrice).toBe(181.79);
    });
  });

  describe('Trading Analytics', () => {
    it('should get trading performance metrics', async () => {
      const timeframe = '30d';
      const mockMetrics = {
        totalTrades: 45,
        winRate: 0.67,
        averageReturn: 0.035,
        bestTrade: { symbol: 'AAPL', return: 0.12 },
        worstTrade: { symbol: 'TSLA', return: -0.08 },
        sharpeRatio: 1.25,
        maxDrawdown: -0.15
      };

      mockApi.get.mockResolvedValue({ data: { metrics: mockMetrics } });

      const metrics = await tradingService.getTradingMetrics(timeframe);

      expect(mockApi.get).toHaveBeenCalledWith('/trading/metrics', { params: { timeframe } });
      expect(metrics.winRate).toBe(0.67);
      expect(metrics.totalTrades).toBe(45);
    });

    it('should generate trading report', async () => {
      const reportConfig = {
        period: 'quarterly',
        includeCharts: true,
        metrics: ['performance', 'risk', 'allocation']
      };

      const mockReport = {
        reportId: 'trading_report_123',
        generatedAt: '2024-01-15T15:30:00Z',
        summary: {
          totalReturn: 0.18,
          trades: 127,
          winRate: 0.69
        }
      };

      mockApi.post.mockResolvedValue({ data: { report: mockReport } });

      const result = await tradingService.generateTradingReport(reportConfig);

      expect(mockApi.post).toHaveBeenCalledWith('/trading/reports', reportConfig);
      expect(result.report.summary.winRate).toBe(0.69);
    });
  });

  describe('Error Handling', () => {
    it('should handle order rejection', async () => {
      mockValidation.validateOrder.mockReturnValue({ valid: true });
      mockValidation.validateBuyingPower.mockReturnValue({ sufficient: true });
      mockApi.post.mockRejectedValue({
        response: {
          status: 400,
          data: { message: 'Order rejected by exchange', code: 'REJECT_INVALID_SYMBOL' }
        }
      });

      await expect(tradingService.placeOrder({ symbol: 'INVALID', quantity: 100 }))
        .rejects.toMatchObject({
          response: { status: 400 }
        });
    });

    it('should handle market closed scenarios', async () => {
      mockValidation.validateMarketHours.mockReturnValue({
        open: false,
        message: 'Market is closed'
      });

      const orderData = { symbol: 'AAPL', quantity: 100, orderType: 'market' };

      // Should queue order for next market open
      mockApi.post.mockResolvedValue({ 
        data: { 
          order: { ...orderData, status: 'queued', scheduledFor: '2024-01-16T09:30:00Z' }
        } 
      });

      const result = await tradingService.placeOrder(orderData);

      expect(result.order.status).toBe('queued');
    });

    it('should retry failed order submissions', async () => {
      mockValidation.validateOrder.mockReturnValue({ valid: true });
      mockValidation.validateBuyingPower.mockReturnValue({ sufficient: true });
      
      mockApi.post
        .mockRejectedValueOnce(new Error('Network timeout'))
        .mockResolvedValue({ data: { order: { id: 'order_retry', status: 'pending' } } });

      const result = await tradingService.placeOrder({ symbol: 'AAPL', quantity: 100 });

      expect(mockApi.post).toHaveBeenCalledTimes(2);
      expect(result.order.id).toBe('order_retry');
    });
  });

  describe('Performance Optimization', () => {
    it('should batch order status requests', async () => {
      const orderIds = ['order_1', 'order_2', 'order_3'];
      const mockBatchResponse = {
        orders: orderIds.map(id => ({ id, status: 'filled' }))
      };

      mockApi.post.mockResolvedValue({ data: mockBatchResponse });

      const result = await tradingService.getOrdersBatch(orderIds);

      expect(mockApi.post).toHaveBeenCalledWith('/orders/batch', { orderIds });
      expect(result.orders).toHaveLength(3);
    });

    it('should perform order operations efficiently', async () => {
      const startTime = performance.now();
      
      mockValidation.validateOrder.mockReturnValue({ valid: true });
      mockValidation.validateBuyingPower.mockReturnValue({ sufficient: true });
      mockApi.post.mockResolvedValue({ 
        data: { order: { id: 'order_perf', status: 'pending' } } 
      });

      await tradingService.placeOrder({ symbol: 'AAPL', quantity: 100 });
      
      const executionTime = performance.now() - startTime;
      expect(executionTime).toBeLessThan(200); // Should complete within 200ms
    });
  });
});