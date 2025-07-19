/**
 * Alpaca WebSocket Service Unit Tests
 * Testing the actual alpacaWebSocketService.js with real WebSocket functionality
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Mock WebSocket globally
global.WebSocket = vi.fn();

// Import the REAL AlpacaWebSocketService
const alpacaWebSocketServiceModule = await import('../../../services/alpacaWebSocketService');
const AlpacaWebSocketService = alpacaWebSocketServiceModule.default || alpacaWebSocketServiceModule.AlpacaWebSocketService;

describe('🔗 Alpaca WebSocket Service', () => {
  let alpacaService;
  let mockWebSocket;

  beforeEach(() => {
    // Create a mock WebSocket instance
    mockWebSocket = {
      readyState: 1, // OPEN
      send: vi.fn(),
      close: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      CONNECTING: 0,
      OPEN: 1,
      CLOSING: 2,
      CLOSED: 3
    };

    // Mock WebSocket constructor
    global.WebSocket.mockImplementation(() => mockWebSocket);

    // Create fresh service instance
    alpacaService = new AlpacaWebSocketService();

    // Mock console to avoid noise in tests
    vi.spyOn(console, 'log').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    // Cleanup service
    if (alpacaService) {
      alpacaService.disconnect();
      alpacaService.removeAllListeners();
    }
    
    vi.restoreAllMocks();
  });

  describe('Service Initialization', () => {
    it('should initialize with correct default state', () => {
      expect(alpacaService.ws).toBeNull();
      expect(alpacaService.connected).toBe(false);
      expect(alpacaService.authenticated).toBe(false);
      expect(alpacaService.subscriptions).toBeInstanceOf(Set);
      expect(alpacaService.subscriptions.size).toBe(0);
    });

    it('should have default configuration values', () => {
      expect(alpacaService.config).toEqual(
        expect.objectContaining({
          reconnectInterval: expect.any(Number),
          maxReconnectAttempts: expect.any(Number),
          heartbeatInterval: expect.any(Number)
        })
      );
    });

    it('should initialize empty event handlers', () => {
      expect(alpacaService.events).toEqual({});
    });

    it('should have proper EventEmitter methods', () => {
      expect(typeof alpacaService.on).toBe('function');
      expect(typeof alpacaService.off).toBe('function');
      expect(typeof alpacaService.emit).toBe('function');
      expect(typeof alpacaService.removeAllListeners).toBe('function');
    });
  });

  describe('EventEmitter Implementation', () => {
    it('should handle event subscription and emission', () => {
      const mockHandler = vi.fn();
      
      alpacaService.on('test-event', mockHandler);
      alpacaService.emit('test-event', 'test-data');
      
      expect(mockHandler).toHaveBeenCalledWith('test-data');
    });

    it('should handle multiple listeners for same event', () => {
      const handler1 = vi.fn();
      const handler2 = vi.fn();
      
      alpacaService.on('quote', handler1);
      alpacaService.on('quote', handler2);
      alpacaService.emit('quote', { symbol: 'AAPL', price: 185.50 });
      
      expect(handler1).toHaveBeenCalledWith({ symbol: 'AAPL', price: 185.50 });
      expect(handler2).toHaveBeenCalledWith({ symbol: 'AAPL', price: 185.50 });
    });

    it('should remove specific event listeners', () => {
      const handler = vi.fn();
      
      alpacaService.on('remove-test', handler);
      alpacaService.off('remove-test', handler);
      alpacaService.emit('remove-test', 'data');
      
      expect(handler).not.toHaveBeenCalled();
    });

    it('should remove all listeners for an event', () => {
      const handler1 = vi.fn();
      const handler2 = vi.fn();
      
      alpacaService.on('clear-all', handler1);
      alpacaService.on('clear-all', handler2);
      alpacaService.removeAllListeners('clear-all');
      alpacaService.emit('clear-all', 'data');
      
      expect(handler1).not.toHaveBeenCalled();
      expect(handler2).not.toHaveBeenCalled();
    });

    it('should remove all listeners when no event specified', () => {
      const handler1 = vi.fn();
      const handler2 = vi.fn();
      
      alpacaService.on('event1', handler1);
      alpacaService.on('event2', handler2);
      alpacaService.removeAllListeners();
      
      alpacaService.emit('event1', 'data');
      alpacaService.emit('event2', 'data');
      
      expect(handler1).not.toHaveBeenCalled();
      expect(handler2).not.toHaveBeenCalled();
    });
  });

  describe('WebSocket Connection Management', () => {
    it('should create WebSocket connection with correct URL', () => {
      const apiKey = 'test_api_key';
      const apiSecret = 'test_api_secret';
      
      alpacaService.connect(apiKey, apiSecret);
      
      expect(global.WebSocket).toHaveBeenCalledWith(
        expect.stringContaining('wss://stream.data.alpaca.markets/v2/')
      );
      expect(alpacaService.ws).toBe(mockWebSocket);
    });

    it('should set up WebSocket event listeners on connect', () => {
      alpacaService.connect('test_key', 'test_secret');
      
      expect(mockWebSocket.addEventListener).toHaveBeenCalledWith('open', expect.any(Function));
      expect(mockWebSocket.addEventListener).toHaveBeenCalledWith('message', expect.any(Function));
      expect(mockWebSocket.addEventListener).toHaveBeenCalledWith('close', expect.any(Function));
      expect(mockWebSocket.addEventListener).toHaveBeenCalledWith('error', expect.any(Function));
    });

    it('should handle WebSocket open event', () => {
      const connectHandler = vi.fn();
      alpacaService.on('connected', connectHandler);
      
      alpacaService.connect('test_key', 'test_secret');
      
      // Simulate WebSocket open event
      const openHandler = mockWebSocket.addEventListener.mock.calls.find(
        call => call[0] === 'open'
      )[1];
      openHandler();
      
      expect(alpacaService.connected).toBe(true);
      expect(connectHandler).toHaveBeenCalled();
    });

    it('should handle WebSocket close event', () => {
      const disconnectHandler = vi.fn();
      alpacaService.on('disconnected', disconnectHandler);
      
      alpacaService.connect('test_key', 'test_secret');
      alpacaService.connected = true; // Simulate connected state
      
      // Simulate WebSocket close event
      const closeHandler = mockWebSocket.addEventListener.mock.calls.find(
        call => call[0] === 'close'
      )[1];
      closeHandler({ code: 1000, reason: 'Normal closure' });
      
      expect(alpacaService.connected).toBe(false);
      expect(disconnectHandler).toHaveBeenCalledWith({ code: 1000, reason: 'Normal closure' });
    });

    it('should handle WebSocket error event', () => {
      const errorHandler = vi.fn();
      alpacaService.on('error', errorHandler);
      
      alpacaService.connect('test_key', 'test_secret');
      
      // Simulate WebSocket error event
      const wsErrorHandler = mockWebSocket.addEventListener.mock.calls.find(
        call => call[0] === 'error'
      )[1];
      const errorEvent = { type: 'error', message: 'Connection failed' };
      wsErrorHandler(errorEvent);
      
      expect(errorHandler).toHaveBeenCalledWith(errorEvent);
    });

    it('should disconnect WebSocket properly', () => {
      alpacaService.connect('test_key', 'test_secret');
      alpacaService.connected = true;
      
      alpacaService.disconnect();
      
      expect(mockWebSocket.close).toHaveBeenCalled();
      expect(alpacaService.connected).toBe(false);
      expect(alpacaService.authenticated).toBe(false);
    });

    it('should not disconnect if not connected', () => {
      alpacaService.disconnect();
      
      expect(mockWebSocket.close).not.toHaveBeenCalled();
    });
  });

  describe('Authentication Flow', () => {
    beforeEach(() => {
      alpacaService.connect('test_key', 'test_secret');
      alpacaService.connected = true;
    });

    it('should send authentication message on connection', () => {
      // Simulate WebSocket open event which should trigger auth
      const openHandler = mockWebSocket.addEventListener.mock.calls.find(
        call => call[0] === 'open'
      )[1];
      openHandler();
      
      expect(mockWebSocket.send).toHaveBeenCalledWith(
        expect.stringContaining('"action":"auth"')
      );
    });

    it('should handle successful authentication response', () => {
      const authHandler = vi.fn();
      alpacaService.on('authenticated', authHandler);
      
      // Simulate authentication success message
      const messageHandler = mockWebSocket.addEventListener.mock.calls.find(
        call => call[0] === 'message'
      )[1];
      
      const authSuccessMessage = {
        data: JSON.stringify([{
          "T": "success",
          "msg": "authenticated"
        }])
      };
      
      messageHandler(authSuccessMessage);
      
      expect(alpacaService.authenticated).toBe(true);
      expect(authHandler).toHaveBeenCalled();
    });

    it('should handle authentication failure', () => {
      const authErrorHandler = vi.fn();
      alpacaService.on('auth_error', authErrorHandler);
      
      const messageHandler = mockWebSocket.addEventListener.mock.calls.find(
        call => call[0] === 'message'
      )[1];
      
      const authFailMessage = {
        data: JSON.stringify([{
          "T": "error",
          "code": 401,
          "msg": "authentication failed"
        }])
      };
      
      messageHandler(authFailMessage);
      
      expect(alpacaService.authenticated).toBe(false);
      expect(authErrorHandler).toHaveBeenCalledWith(
        expect.objectContaining({ msg: "authentication failed" })
      );
    });
  });

  describe('Symbol Subscription Management', () => {
    beforeEach(() => {
      alpacaService.connect('test_key', 'test_secret');
      alpacaService.connected = true;
      alpacaService.authenticated = true;
    });

    it('should subscribe to symbols for quotes', () => {
      alpacaService.subscribeToQuotes(['AAPL', 'GOOGL']);
      
      expect(mockWebSocket.send).toHaveBeenCalledWith(
        expect.stringContaining('"action":"subscribe"')
      );
      expect(mockWebSocket.send).toHaveBeenCalledWith(
        expect.stringContaining('"quotes":["AAPL","GOOGL"]')
      );
    });

    it('should subscribe to symbols for trades', () => {
      alpacaService.subscribeToTrades(['AAPL', 'MSFT']);
      
      expect(mockWebSocket.send).toHaveBeenCalledWith(
        expect.stringContaining('"action":"subscribe"')
      );
      expect(mockWebSocket.send).toHaveBeenCalledWith(
        expect.stringContaining('"trades":["AAPL","MSFT"]')
      );
    });

    it('should subscribe to symbols for bars (OHLCV)', () => {
      alpacaService.subscribeToBars(['AAPL']);
      
      expect(mockWebSocket.send).toHaveBeenCalledWith(
        expect.stringContaining('"action":"subscribe"')
      );
      expect(mockWebSocket.send).toHaveBeenCalledWith(
        expect.stringContaining('"bars":["AAPL"]')
      );
    });

    it('should unsubscribe from symbols', () => {
      alpacaService.unsubscribe(['AAPL'], 'quotes');
      
      expect(mockWebSocket.send).toHaveBeenCalledWith(
        expect.stringContaining('"action":"unsubscribe"')
      );
      expect(mockWebSocket.send).toHaveBeenCalledWith(
        expect.stringContaining('"quotes":["AAPL"]')
      );
    });

    it('should track subscriptions locally', () => {
      alpacaService.subscribeToQuotes(['AAPL', 'GOOGL']);
      
      expect(alpacaService.subscriptions.has('AAPL')).toBe(true);
      expect(alpacaService.subscriptions.has('GOOGL')).toBe(true);
      expect(alpacaService.subscriptions.size).toBe(2);
    });

    it('should not subscribe when not authenticated', () => {
      alpacaService.authenticated = false;
      
      alpacaService.subscribeToQuotes(['AAPL']);
      
      // Should not send WebSocket message
      expect(mockWebSocket.send).not.toHaveBeenCalled();
    });
  });

  describe('Message Processing', () => {
    beforeEach(() => {
      alpacaService.connect('test_key', 'test_secret');
      alpacaService.connected = true;
      alpacaService.authenticated = true;
    });

    it('should process quote messages correctly', () => {
      const quoteHandler = vi.fn();
      alpacaService.on('quote', quoteHandler);
      
      const messageHandler = mockWebSocket.addEventListener.mock.calls.find(
        call => call[0] === 'message'
      )[1];
      
      const quoteMessage = {
        data: JSON.stringify([{
          "T": "q",
          "S": "AAPL",
          "bx": "V",
          "bp": 185.45,
          "bs": 100,
          "ax": "Q", 
          "ap": 185.50,
          "as": 200,
          "t": "2024-01-15T15:30:00.123456789Z"
        }])
      };
      
      messageHandler(quoteMessage);
      
      expect(quoteHandler).toHaveBeenCalledWith(
        expect.objectContaining({
          T: "q",
          S: "AAPL",
          bp: 185.45,
          ap: 185.50
        })
      );
    });

    it('should process trade messages correctly', () => {
      const tradeHandler = vi.fn();
      alpacaService.on('trade', tradeHandler);
      
      const messageHandler = mockWebSocket.addEventListener.mock.calls.find(
        call => call[0] === 'message'
      )[1];
      
      const tradeMessage = {
        data: JSON.stringify([{
          "T": "t",
          "S": "AAPL",
          "p": 185.50,
          "s": 100,
          "t": "2024-01-15T15:30:00.123456789Z",
          "x": "V"
        }])
      };
      
      messageHandler(tradeMessage);
      
      expect(tradeHandler).toHaveBeenCalledWith(
        expect.objectContaining({
          T: "t",
          S: "AAPL",
          p: 185.50,
          s: 100
        })
      );
    });

    it('should process bar (OHLCV) messages correctly', () => {
      const barHandler = vi.fn();
      alpacaService.on('bar', barHandler);
      
      const messageHandler = mockWebSocket.addEventListener.mock.calls.find(
        call => call[0] === 'message'
      )[1];
      
      const barMessage = {
        data: JSON.stringify([{
          "T": "b",
          "S": "AAPL",
          "o": 184.00,
          "h": 186.50,
          "l": 183.75,
          "c": 185.50,
          "v": 1250000,
          "t": "2024-01-15T15:30:00Z"
        }])
      };
      
      messageHandler(barMessage);
      
      expect(barHandler).toHaveBeenCalledWith(
        expect.objectContaining({
          T: "b",
          S: "AAPL",
          o: 184.00,
          h: 186.50,
          l: 183.75,
          c: 185.50,
          v: 1250000
        })
      );
    });

    it('should handle malformed JSON messages gracefully', () => {
      const errorHandler = vi.fn();
      alpacaService.on('error', errorHandler);
      
      const messageHandler = mockWebSocket.addEventListener.mock.calls.find(
        call => call[0] === 'message'
      )[1];
      
      const malformedMessage = {
        data: 'invalid json {'
      };
      
      messageHandler(malformedMessage);
      
      expect(errorHandler).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'parse_error'
        })
      );
    });

    it('should emit symbol-specific events', () => {
      const aaplHandler = vi.fn();
      alpacaService.on('AAPL', aaplHandler);
      
      const messageHandler = mockWebSocket.addEventListener.mock.calls.find(
        call => call[0] === 'message'
      )[1];
      
      const aaplQuote = {
        data: JSON.stringify([{
          "T": "q",
          "S": "AAPL",
          "bp": 185.45,
          "ap": 185.50
        }])
      };
      
      messageHandler(aaplQuote);
      
      expect(aaplHandler).toHaveBeenCalledWith(
        expect.objectContaining({
          S: "AAPL",
          bp: 185.45
        })
      );
    });
  });

  describe('Reconnection Logic', () => {
    it('should attempt reconnection on disconnect', async () => {
      vi.useFakeTimers();
      
      alpacaService.connect('test_key', 'test_secret');
      alpacaService.connected = true;
      
      // Simulate unexpected disconnect
      const closeHandler = mockWebSocket.addEventListener.mock.calls.find(
        call => call[0] === 'close'
      )[1];
      closeHandler({ code: 1006, reason: 'Abnormal closure' });
      
      expect(alpacaService.connected).toBe(false);
      
      // Should schedule reconnection
      vi.advanceTimersByTime(alpacaService.config.reconnectInterval);
      
      expect(global.WebSocket).toHaveBeenCalledTimes(2); // Initial + reconnect
      
      vi.useRealTimers();
    });

    it('should not reconnect on normal closure', () => {
      vi.useFakeTimers();
      
      alpacaService.connect('test_key', 'test_secret');
      alpacaService.connected = true;
      
      // Simulate normal disconnect
      const closeHandler = mockWebSocket.addEventListener.mock.calls.find(
        call => call[0] === 'close'
      )[1];
      closeHandler({ code: 1000, reason: 'Normal closure' });
      
      vi.advanceTimersByTime(alpacaService.config.reconnectInterval);
      
      expect(global.WebSocket).toHaveBeenCalledTimes(1); // Only initial
      
      vi.useRealTimers();
    });

    it('should stop reconnecting after max attempts', () => {
      vi.useFakeTimers();
      
      alpacaService.config.maxReconnectAttempts = 3;
      alpacaService.connect('test_key', 'test_secret');
      
      // Simulate multiple failed reconnections
      for (let i = 0; i < 5; i++) {
        const closeHandler = mockWebSocket.addEventListener.mock.calls.find(
          call => call[0] === 'close'
        )[1];
        closeHandler({ code: 1006, reason: 'Connection lost' });
        
        vi.advanceTimersByTime(alpacaService.config.reconnectInterval);
      }
      
      // Should not exceed max attempts + 1 (initial)
      expect(global.WebSocket).toHaveBeenCalledTimes(4);
      
      vi.useRealTimers();
    });
  });

  describe('Performance and Memory Management', () => {
    beforeEach(() => {
      alpacaService.connect('test_key', 'test_secret');
      alpacaService.connected = true;
      alpacaService.authenticated = true;
    });

    it('should handle high-frequency message processing', () => {
      const quoteHandler = vi.fn();
      alpacaService.on('quote', quoteHandler);
      
      const messageHandler = mockWebSocket.addEventListener.mock.calls.find(
        call => call[0] === 'message'
      )[1];
      
      const startTime = performance.now();
      
      // Process 1000 messages rapidly
      for (let i = 0; i < 1000; i++) {
        const message = {
          data: JSON.stringify([{
            "T": "q",
            "S": "AAPL",
            "bp": 185.45 + Math.random(),
            "ap": 185.50 + Math.random()
          }])
        };
        messageHandler(message);
      }
      
      const processingTime = performance.now() - startTime;
      expect(processingTime).toBeLessThan(1000); // Should process within 1 second
      expect(quoteHandler).toHaveBeenCalledTimes(1000);
    });

    it('should clean up resources on disconnect', () => {
      alpacaService.subscribeToQuotes(['AAPL', 'GOOGL']);
      expect(alpacaService.subscriptions.size).toBe(2);
      
      alpacaService.disconnect();
      
      expect(alpacaService.connected).toBe(false);
      expect(alpacaService.authenticated).toBe(false);
      expect(alpacaService.subscriptions.size).toBe(0);
    });

    it('should handle memory efficiently with many subscriptions', () => {
      const symbols = Array.from({ length: 1000 }, (_, i) => `STOCK${i}`);
      
      const startTime = performance.now();
      alpacaService.subscribeToQuotes(symbols);
      const subscriptionTime = performance.now() - startTime;
      
      expect(subscriptionTime).toBeLessThan(100); // Should be fast
      expect(alpacaService.subscriptions.size).toBe(1000);
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('should handle WebSocket creation failure', () => {
      global.WebSocket.mockImplementation(() => {
        throw new Error('WebSocket creation failed');
      });
      
      expect(() => {
        alpacaService.connect('test_key', 'test_secret');
      }).toThrow('WebSocket creation failed');
    });

    it('should handle send failures when WebSocket is closed', () => {
      alpacaService.connect('test_key', 'test_secret');
      mockWebSocket.readyState = 3; // CLOSED
      
      expect(() => {
        alpacaService.subscribeToQuotes(['AAPL']);
      }).not.toThrow();
    });

    it('should validate subscription parameters', () => {
      alpacaService.connect('test_key', 'test_secret');
      alpacaService.connected = true;
      alpacaService.authenticated = true;
      
      // Should handle empty arrays
      alpacaService.subscribeToQuotes([]);
      expect(mockWebSocket.send).not.toHaveBeenCalled();
      
      // Should handle null/undefined
      alpacaService.subscribeToQuotes(null);
      expect(mockWebSocket.send).not.toHaveBeenCalled();
    });

    it('should handle duplicate subscriptions gracefully', () => {
      alpacaService.connect('test_key', 'test_secret');
      alpacaService.connected = true;
      alpacaService.authenticated = true;
      
      alpacaService.subscribeToQuotes(['AAPL']);
      alpacaService.subscribeToQuotes(['AAPL']); // Duplicate
      
      expect(alpacaService.subscriptions.size).toBe(1);
    });
  });
});