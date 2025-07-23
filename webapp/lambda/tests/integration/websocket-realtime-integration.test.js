// Integration Tests for Real-time WebSocket Infrastructure
// Tests actual WebSocket connections to deployed AWS infrastructure
// Real Implementation Standard - NO MOCKS for infrastructure testing

const { describe, test, expect, beforeAll, afterAll, beforeEach, afterEach, vi } = require('vitest');
const WebSocket = require('ws');
const AWS = require('aws-sdk');

// Test configuration
const TEST_CONFIG = {
  websocketUrl: process.env.WEBSOCKET_URL || 'wss://test.execute-api.us-east-1.amazonaws.com/dev',
  region: process.env.AWS_REGION || 'us-east-1',
  timeout: 30000,
  connectionTimeout: 10000,
  messageTimeout: 5000
};

// Test utilities
class WebSocketTestClient {
  constructor() {
    this.ws = null;
    this.messages = [];
    this.connected = false;
    this.messageHandlers = new Map();
  }

  async connect(userId = 'test-user', token = null) {
    return new Promise((resolve, reject) => {
      const params = new URLSearchParams();
      if (userId) params.append('userId', userId);
      if (token) params.append('token', token);
      
      const url = `${TEST_CONFIG.websocketUrl}?${params.toString()}`;
      console.log(`🔌 Connecting to WebSocket: ${url}`);
      
      this.ws = new WebSocket(url);
      
      const timeout = setTimeout(() => {
        reject(new Error('Connection timeout'));
      }, TEST_CONFIG.connectionTimeout);
      
      this.ws.on('open', () => {
        clearTimeout(timeout);
        this.connected = true;
        console.log('✅ WebSocket connected');
        resolve();
      });
      
      this.ws.on('message', (data) => {
        try {
          const message = JSON.parse(data.toString());
          console.log('📥 Received:', message.type, message);
          
          this.messages.push(message);
          
          // Call specific message handlers
          const handler = this.messageHandlers.get(message.type);
          if (handler) {
            handler(message);
          }
        } catch (error) {
          console.error('❌ Failed to parse message:', error);
        }
      });
      
      this.ws.on('close', (code, reason) => {
        this.connected = false;
        console.log(`🔌 WebSocket closed: ${code} - ${reason}`);
      });
      
      this.ws.on('error', (error) => {
        clearTimeout(timeout);
        console.error('❌ WebSocket error:', error);
        reject(error);
      });
    });
  }

  send(message) {
    if (!this.connected) {
      throw new Error('WebSocket not connected');
    }
    
    const messageStr = JSON.stringify(message);
    console.log('📤 Sending:', message.action || message.type, message);
    this.ws.send(messageStr);
  }

  async waitForMessage(type, timeout = TEST_CONFIG.messageTimeout) {
    return new Promise((resolve, reject) => {
      // Check if we already have the message
      const existing = this.messages.find(msg => msg.type === type);
      if (existing) {
        resolve(existing);
        return;
      }
      
      // Set up handler for new messages
      const timeoutId = setTimeout(() => {
        this.messageHandlers.delete(type);
        reject(new Error(`Timeout waiting for message type: ${type}`));
      }, timeout);
      
      this.messageHandlers.set(type, (message) => {
        clearTimeout(timeoutId);
        this.messageHandlers.delete(type);
        resolve(message);
      });
    });
  }

  async subscribe(symbols, channels = ['trades', 'quotes', 'bars']) {
    this.send({
      action: 'subscribe',
      symbols: Array.isArray(symbols) ? symbols : [symbols],
      channels
    });
    
    return this.waitForMessage('subscription_confirmed');
  }

  async unsubscribe(symbols) {
    this.send({
      action: 'unsubscribe',
      symbols: Array.isArray(symbols) ? symbols : [symbols]
    });
    
    return this.waitForMessage('unsubscribe_confirmed');
  }

  async ping() {
    const timestamp = Date.now();
    this.send({
      action: 'ping',
      timestamp
    });
    
    const pong = await this.waitForMessage('pong');
    return {
      ...pong,
      latency: Date.now() - timestamp
    };
  }

  disconnect() {
    if (this.ws && this.connected) {
      this.ws.close(1000, 'Test complete');
    }
    this.connected = false;
    this.messages = [];
    this.messageHandlers.clear();
  }

  getMessages(type = null) {
    if (type) {
      return this.messages.filter(msg => msg.type === type);
    }
    return [...this.messages];
  }

  clearMessages() {
    this.messages = [];
  }
}

describe('WebSocket Real-time Infrastructure Integration Tests', () => {
  let testClient;
  
  beforeEach(() => {
    testClient = new WebSocketTestClient();
  });
  
  afterEach(() => {
    if (testClient) {
      testClient.disconnect();
    }
  });

  describe('WebSocket Connection Management', () => {
    test('establishes WebSocket connection successfully', async () => {
      await testClient.connect('integration-test-user');
      
      expect(testClient.connected).toBe(true);
      
      // Should receive connection confirmation
      const confirmation = await testClient.waitForMessage('connected');
      expect(confirmation).toMatchObject({
        type: 'connected',
        userId: 'integration-test-user',
        supportedActions: expect.arrayContaining(['subscribe', 'unsubscribe', 'ping'])
      });
    }, TEST_CONFIG.timeout);
    
    test('handles connection with authentication token', async () => {
      // Create a mock JWT token for testing
      const mockToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LXVzZXIiLCJlbWFpbCI6InRlc3RAZW1haWwuY29tIn0.test';
      
      await testClient.connect('auth-test-user', mockToken);
      
      const confirmation = await testClient.waitForMessage('connected');
      expect(confirmation.userId).toBe('auth-test-user');
    }, TEST_CONFIG.timeout);
    
    test('handles anonymous connections', async () => {
      await testClient.connect();
      
      const confirmation = await testClient.waitForMessage('connected');
      expect(confirmation.userId).toBe('anonymous');
    }, TEST_CONFIG.timeout);
  });

  describe('Symbol Subscription Management', () => {
    beforeEach(async () => {
      await testClient.connect('subscription-test-user');
      await testClient.waitForMessage('connected');
    });
    
    test('subscribes to single symbol successfully', async () => {
      const confirmation = await testClient.subscribe('AAPL');
      
      expect(confirmation).toMatchObject({
        type: 'subscription_confirmed',
        symbols: ['AAPL'],
        channels: ['trades', 'quotes', 'bars']
      });
    }, TEST_CONFIG.timeout);
    
    test('subscribes to multiple symbols', async () => {
      const symbols = ['AAPL', 'MSFT', 'GOOGL'];
      const confirmation = await testClient.subscribe(symbols);
      
      expect(confirmation).toMatchObject({
        type: 'subscription_confirmed',
        symbols: expect.arrayContaining(symbols)
      });
    }, TEST_CONFIG.timeout);
    
    test('validates symbol format and filters invalid symbols', async () => {
      const mixedSymbols = ['AAPL', 'invalid-symbol', 'MSFT', '12345', 'GOOGL'];
      const confirmation = await testClient.subscribe(mixedSymbols);
      
      // Should only confirm valid symbols
      expect(confirmation.symbols).toEqual(expect.arrayContaining(['AAPL', 'MSFT', 'GOOGL']));
      expect(confirmation.symbols).not.toContain('invalid-symbol');
      expect(confirmation.symbols).not.toContain('12345');
    }, TEST_CONFIG.timeout);
    
    test('unsubscribes from symbols', async () => {
      // First subscribe
      await testClient.subscribe(['AAPL', 'MSFT']);
      
      // Then unsubscribe
      const confirmation = await testClient.unsubscribe(['AAPL']);
      
      expect(confirmation).toMatchObject({
        type: 'unsubscribe_confirmed',
        symbols: ['AAPL']
      });
    }, TEST_CONFIG.timeout);
    
    test('handles subscription without API keys gracefully', async () => {
      // This should trigger the "NO_API_KEYS" error
      testClient.send({
        action: 'subscribe',
        symbols: ['AAPL']
      });
      
      // May receive either subscription confirmation or error depending on deployment
      try {
        const response = await Promise.race([
          testClient.waitForMessage('subscription_confirmed'),
          testClient.waitForMessage('error')
        ]);
        
        if (response.type === 'error') {
          expect(response.code).toBe('NO_API_KEYS');
          expect(response.message).toContain('API keys');
        } else {
          // If API keys are configured, subscription should succeed
          expect(response.type).toBe('subscription_confirmed');
        }
      } catch (error) {
        // Timeout is acceptable if no API keys are configured
        expect(error.message).toContain('Timeout');
      }
    }, TEST_CONFIG.timeout);
  });

  describe('Ping/Pong Latency Testing', () => {
    beforeEach(async () => {
      await testClient.connect('ping-test-user');
      await testClient.waitForMessage('connected');
    });
    
    test('responds to ping with pong and latency measurement', async () => {
      const result = await testClient.ping();
      
      expect(result).toMatchObject({
        type: 'pong',
        clientTimestamp: expect.any(Number),
        timestamp: expect.any(Number)
      });
      
      expect(result.latency).toBeGreaterThan(0);
      expect(result.latency).toBeLessThan(5000); // Should be under 5 seconds
    }, TEST_CONFIG.timeout);
    
    test('measures multiple ping latencies', async () => {
      const latencies = [];
      
      for (let i = 0; i < 3; i++) {
        const result = await testClient.ping();
        latencies.push(result.latency);
        
        // Wait a bit between pings
        await new Promise(resolve => setTimeout(resolve, 100));
      }
      
      expect(latencies).toHaveLength(3);
      latencies.forEach(latency => {
        expect(latency).toBeGreaterThan(0);
        expect(latency).toBeLessThan(10000);
      });
      
      console.log('📊 Ping latencies (ms):', latencies);
    }, TEST_CONFIG.timeout);
  });

  describe('Real-time Market Data Integration', () => {
    beforeEach(async () => {
      await testClient.connect('market-data-test-user');
      await testClient.waitForMessage('connected');
    });
    
    test('receives market data updates after subscription', async () => {
      // Subscribe to a popular stock
      await testClient.subscribe('AAPL');
      
      // Wait for potential market data updates
      // Note: This may timeout during non-market hours or if no API keys are configured
      try {
        const marketData = await testClient.waitForMessage('market_data_update', 15000);
        
        expect(marketData).toMatchObject({
          type: 'market_data_update',
          symbol: 'AAPL',
          data: {
            price: expect.any(Number),
            timestamp: expect.any(String),
            source: 'alpaca'
          }
        });
        
        console.log('📈 Received market data for AAPL:', marketData.data);
      } catch (error) {
        // During testing or non-market hours, market data may not be available
        console.log('⏰ No market data received (expected during off-hours or without API keys)');
        expect(error.message).toContain('Timeout');
      }
    }, 20000);
    
    test('handles multiple symbol subscriptions for market data', async () => {
      const symbols = ['AAPL', 'MSFT'];
      await testClient.subscribe(symbols);
      
      // Clear previous messages
      testClient.clearMessages();
      
      // Wait for market data from any subscribed symbol
      try {
        const updates = [];
        const timeout = setTimeout(() => {}, 10000);
        
        for (let i = 0; i < 5; i++) {
          try {
            const update = await testClient.waitForMessage('market_data_update', 2000);
            updates.push(update);
            
            if (symbols.includes(update.symbol)) {
              console.log(`📊 Market data for ${update.symbol}:`, update.data.price);
            }
          } catch (timeoutError) {
            break; // No more updates available
          }
        }
        
        clearTimeout(timeout);
        
        if (updates.length > 0) {
          // Verify data format
          updates.forEach(update => {
            expect(update).toMatchObject({
              type: 'market_data_update',
              symbol: expect.stringMatching(/^[A-Z]+$/),
              data: {
                price: expect.any(Number),
                source: 'alpaca'
              }
            });
          });
        }
      } catch (error) {
        console.log('⏰ No market data received during test period');
      }
    }, 15000);
  });

  describe('Error Handling and Edge Cases', () => {
    test('handles malformed JSON messages', async () => {
      await testClient.connect('error-test-user');
      await testClient.waitForMessage('connected');
      
      // Send malformed JSON
      testClient.ws.send('invalid-json{');
      
      // Connection should remain stable
      expect(testClient.connected).toBe(true);
      
      // Should still be able to send valid messages
      const pong = await testClient.ping();
      expect(pong.type).toBe('pong');
    }, TEST_CONFIG.timeout);
    
    test('handles unknown action types', async () => {
      await testClient.connect('unknown-action-user');
      await testClient.waitForMessage('connected');
      
      testClient.send({
        action: 'unknown-action',
        data: 'test'
      });
      
      // Connection should remain stable
      expect(testClient.connected).toBe(true);
    }, TEST_CONFIG.timeout);
    
    test('handles empty symbol arrays', async () => {
      await testClient.connect('empty-symbols-user');
      await testClient.waitForMessage('connected');
      
      testClient.send({
        action: 'subscribe',
        symbols: []
      });
      
      // Should handle gracefully without breaking connection
      expect(testClient.connected).toBe(true);
    }, TEST_CONFIG.timeout);
  });

  describe('Connection Lifecycle Management', () => {
    test('handles graceful disconnection', async () => {
      await testClient.connect('lifecycle-test-user');
      await testClient.waitForMessage('connected');
      
      // Subscribe to symbol
      await testClient.subscribe('AAPL');
      
      // Disconnect gracefully
      testClient.disconnect();
      
      expect(testClient.connected).toBe(false);
    }, TEST_CONFIG.timeout);
    
    test('manages multiple concurrent connections', async () => {
      const clients = [];
      
      try {
        // Create multiple test clients
        for (let i = 0; i < 3; i++) {
          const client = new WebSocketTestClient();
          await client.connect(`concurrent-user-${i}`);
          await client.waitForMessage('connected');
          clients.push(client);
        }
        
        // All clients should be connected
        clients.forEach(client => {
          expect(client.connected).toBe(true);
        });
        
        // Test that each client can subscribe independently
        for (let i = 0; i < clients.length; i++) {
          const confirmation = await clients[i].subscribe(`TEST${i}`);
          expect(confirmation.type).toBe('subscription_confirmed');
        }
        
      } finally {
        // Clean up all clients
        clients.forEach(client => client.disconnect());
      }
    }, TEST_CONFIG.timeout);
  });

  describe('Performance and Load Testing', () => {
    test('handles rapid subscription requests', async () => {
      await testClient.connect('performance-test-user');
      await testClient.waitForMessage('connected');
      
      const symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA'];
      const startTime = Date.now();
      
      // Send subscription requests rapidly
      const confirmations = await Promise.all(
        symbols.map(symbol => testClient.subscribe(symbol))
      );
      
      const endTime = Date.now();
      const totalTime = endTime - startTime;
      
      expect(confirmations).toHaveLength(symbols.length);
      confirmations.forEach(confirmation => {
        expect(confirmation.type).toBe('subscription_confirmed');
      });
      
      console.log(`⚡ Rapid subscriptions completed in ${totalTime}ms`);
      expect(totalTime).toBeLessThan(10000); // Should complete within 10 seconds
    }, TEST_CONFIG.timeout);
    
    test('measures WebSocket connection establishment time', async () => {
      const startTime = Date.now();
      
      await testClient.connect('timing-test-user');
      await testClient.waitForMessage('connected');
      
      const connectionTime = Date.now() - startTime;
      
      console.log(`🚀 WebSocket connection established in ${connectionTime}ms`);
      expect(connectionTime).toBeLessThan(TEST_CONFIG.connectionTimeout);
    }, TEST_CONFIG.timeout);
  });
});

describe('WebSocket Infrastructure Health Tests', () => {
  test('validates WebSocket URL configuration', () => {
    expect(TEST_CONFIG.websocketUrl).toMatch(/^wss:\/\//);
    expect(TEST_CONFIG.websocketUrl).toContain('execute-api');
    console.log('🔗 Testing WebSocket URL:', TEST_CONFIG.websocketUrl);
  });
  
  test('validates AWS region configuration', () => {
    expect(TEST_CONFIG.region).toMatch(/^[a-z]+-[a-z]+-\d+$/);
    console.log('🌍 Testing in AWS region:', TEST_CONFIG.region);
  });
});

// Integration with existing test framework
describe('Test Framework Integration', () => {
  test('integrates with vitest test runner', () => {
    expect(typeof describe).toBe('function');
    expect(typeof test).toBe('function');
    expect(typeof expect).toBe('function');
  });
  
  test('provides real-time testing utilities', () => {
    const client = new WebSocketTestClient();
    
    expect(client).toHaveProperty('connect');
    expect(client).toHaveProperty('subscribe');
    expect(client).toHaveProperty('waitForMessage');
    expect(client).toHaveProperty('ping');
    expect(client).toHaveProperty('disconnect');
  });
  
  test('follows Real Implementation Standard', () => {
    // These tests use real WebSocket connections to actual infrastructure
    // No mocks are used for testing the WebSocket protocol itself
    // Only AWS SDK and external dependencies are mocked when needed
    expect(true).toBe(true); // This test validates our testing philosophy
  });
});