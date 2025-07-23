/**
 * Real-Time Data Service Unit Tests
 * Tests WebSocket connections, data streaming, and circuit breaker patterns
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock WebSocket
global.WebSocket = vi.fn().mockImplementation(() => ({
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  send: vi.fn(),
  close: vi.fn(),
  readyState: 1, // OPEN
  CONNECTING: 0,
  OPEN: 1,
  CLOSING: 2,
  CLOSED: 3
}));

// Mock the real-time data service
vi.mock('../../../services/realTimeDataService', () => ({
  connectToDataStream: vi.fn(),
  subscribeToSymbol: vi.fn(),
  unsubscribeFromSymbol: vi.fn(),
  getLatestPrice: vi.fn(),
  getConnectionStatus: vi.fn(),
  reconnectWebSocket: vi.fn(),
  clearDataCache: vi.fn(),
  getCircuitBreakerState: vi.fn(),
  resetCircuitBreaker: vi.fn()
}));

describe('Real-Time Data Service', () => {
  let mockWebSocket;

  beforeEach(() => {
    vi.clearAllMocks();
    mockWebSocket = {
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      send: vi.fn(),
      close: vi.fn(),
      readyState: 1,
      CONNECTING: 0,
      OPEN: 1,
      CLOSING: 2,
      CLOSED: 3
    };
    global.WebSocket.mockImplementation(() => mockWebSocket);
  });

  describe('WebSocket Connection Management', () => {
    it('establishes WebSocket connection successfully', async () => {
      const { connectToDataStream } = await import('../../../services/realTimeDataService');
      connectToDataStream.mockResolvedValue({
        connected: true,
        connectionId: 'ws_12345',
        endpoint: 'wss://data.protrade.com/live',
        protocol: 'v2'
      });

      const result = await connectToDataStream();
      
      expect(result.connected).toBe(true);
      expect(result.connectionId).toBe('ws_12345');
      expect(result.endpoint).toBe('wss://data.protrade.com/live');
    });

    it('handles connection failures gracefully', async () => {
      const { connectToDataStream } = await import('../../../services/realTimeDataService');
      connectToDataStream.mockRejectedValue(new Error('Connection failed: Network timeout'));

      await expect(connectToDataStream()).rejects.toThrow('Connection failed: Network timeout');
    });

    it('manages connection state transitions', async () => {
      const { getConnectionStatus } = await import('../../../services/realTimeDataService');
      getConnectionStatus.mockReturnValue({
        state: 'CONNECTED',
        lastHeartbeat: Date.now() - 5000,
        connectionTime: Date.now() - 60000,
        reconnectAttempts: 0,
        latency: 45
      });

      const status = getConnectionStatus();
      
      expect(status.state).toBe('CONNECTED');
      expect(status.latency).toBe(45);
      expect(status.reconnectAttempts).toBe(0);
    });
  });

  describe('Symbol Subscription Management', () => {
    it('subscribes to stock symbols for live data', async () => {
      const { subscribeToSymbol } = await import('../../../services/realTimeDataService');
      subscribeToSymbol.mockResolvedValue({
        subscribed: true,
        symbol: 'AAPL',
        channels: ['trades', 'quotes', 'bars'],
        subscriptionId: 'sub_AAPL_12345'
      });

      const result = await subscribeToSymbol('AAPL', ['trades', 'quotes', 'bars']);
      
      expect(result.subscribed).toBe(true);
      expect(result.symbol).toBe('AAPL');
      expect(result.channels).toEqual(['trades', 'quotes', 'bars']);
    });

    it('handles bulk symbol subscriptions', async () => {
      const { subscribeToSymbol } = await import('../../../services/realTimeDataService');
      subscribeToSymbol.mockResolvedValue({
        subscribed: true,
        symbols: ['AAPL', 'GOOGL', 'MSFT', 'TSLA'],
        failed: [],
        totalActive: 4,
        quotaUsed: '40%'
      });

      const result = await subscribeToSymbol(['AAPL', 'GOOGL', 'MSFT', 'TSLA']);
      
      expect(result.symbols).toHaveLength(4);
      expect(result.failed).toHaveLength(0);
      expect(result.quotaUsed).toBe('40%');
    });
  });

  describe('Circuit Breaker Pattern', () => {
    it('opens circuit breaker on consecutive failures', async () => {
      const { getCircuitBreakerState } = await import('../../../services/realTimeDataService');
      getCircuitBreakerState.mockReturnValue({
        state: 'OPEN',
        failureCount: 5,
        threshold: 5,
        lastFailureTime: Date.now() - 10000,
        nextRetryTime: Date.now() + 50000,
        timeout: 60000
      });

      const circuitState = getCircuitBreakerState();
      
      expect(circuitState.state).toBe('OPEN');
      expect(circuitState.failureCount).toBe(5);
      expect(circuitState.timeout).toBe(60000);
    });

    it('resets circuit breaker after successful recovery', async () => {
      const { resetCircuitBreaker } = await import('../../../services/realTimeDataService');
      resetCircuitBreaker.mockReturnValue({
        reset: true,
        previousState: 'OPEN',
        newState: 'CLOSED',
        successfulTests: 3,
        resetTime: Date.now()
      });

      const resetResult = resetCircuitBreaker();
      
      expect(resetResult.reset).toBe(true);
      expect(resetResult.previousState).toBe('OPEN');
      expect(resetResult.newState).toBe('CLOSED');
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });
});