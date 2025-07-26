/**
 * Streaming Service Unit Tests
 * 
 * Comprehensive testing for WebSocket streaming functionality
 */

// Mock WebSocket server
jest.mock('ws', () => ({
  Server: jest.fn().mockImplementation(() => ({
    on: jest.fn(),
    clients: new Set(),
    close: jest.fn()
  }))
}));

// Mock enhanced bedrock service
jest.mock('../../../services/EnhancedBedrockService', () => {
  return jest.fn().mockImplementation(() => ({
    generateStreamingResponse: jest.fn(),
    generateResponse: jest.fn()
  }));
});

const StreamingService = require('../../../services/StreamingService');

describe('StreamingService', () => {
  let service;
  let mockWSServer;

  beforeEach(() => {
    jest.clearAllMocks();
    service = new StreamingService();
    mockWSServer = {
      on: jest.fn(),
      clients: new Set(),
      close: jest.fn()
    };
    service.wsServer = mockWSServer;
  });

  describe('Service Initialization', () => {
    test('should initialize with correct default configuration', () => {
      expect(service.config).toEqual({
        heartbeatInterval: 30000,
        maxConnections: 1000,
        streamTimeout: 120000,
        rateLimitWindow: 60000,
        rateLimitRequests: 30
      });
    });

    test('should initialize empty connections and streams maps', () => {
      expect(service.connections.size).toBe(0);
      expect(service.activeStreams.size).toBe(0);
    });

    test('should initialize statistics tracking', () => {
      expect(service.stats).toEqual({
        totalConnections: 0,
        activeConnections: 0,
        totalStreams: 0,
        activeStreams: 0,
        messagesSent: 0,
        errors: 0
      });
    });
  });

  describe('Connection Management', () => {
    test('should handle new WebSocket connections', () => {
      const mockWS = {
        id: 'test-connection-1',
        readyState: 1,
        send: jest.fn(),
        on: jest.fn(),
        ping: jest.fn(),
        terminate: jest.fn()
      };

      service.handleConnection(mockWS);

      expect(service.connections.has('test-connection-1')).toBe(true);
      expect(service.stats.totalConnections).toBe(1);
      expect(service.stats.activeConnections).toBe(1);
    });

    test('should reject connections when at max capacity', () => {
      // Set connections to max capacity
      for (let i = 0; i < service.config.maxConnections; i++) {
        service.connections.set(`connection-${i}`, {});
      }
      service.stats.activeConnections = service.config.maxConnections;

      const mockWS = {
        id: 'test-connection-overflow',
        readyState: 1,
        send: jest.fn(),
        close: jest.fn()
      };

      service.handleConnection(mockWS);

      expect(mockWS.close).toHaveBeenCalledWith(1008, 'Server at capacity');
      expect(service.connections.has('test-connection-overflow')).toBe(false);
    });

    test('should handle connection disconnection', () => {
      const connectionId = 'test-connection-1';
      service.connections.set(connectionId, {
        id: connectionId,
        connected: true
      });
      service.stats.activeConnections = 1;

      service.handleDisconnection(connectionId);

      expect(service.connections.has(connectionId)).toBe(false);
      expect(service.stats.activeConnections).toBe(0);
    });

    test('should cleanup active streams on disconnection', () => {
      const connectionId = 'test-connection-1';
      const streamId = 'test-stream-1';

      service.connections.set(connectionId, { id: connectionId });
      service.activeStreams.set(streamId, { 
        connectionId, 
        id: streamId 
      });
      service.stats.activeConnections = 1;
      service.stats.activeStreams = 1;

      service.handleDisconnection(connectionId);

      expect(service.activeStreams.has(streamId)).toBe(false);
      expect(service.stats.activeStreams).toBe(0);
    });
  });

  describe('Rate Limiting', () => {
    test('should allow requests within rate limit', () => {
      const connectionId = 'test-connection-1';
      
      // First request should be allowed
      const isAllowed1 = service.checkRateLimit(connectionId);
      expect(isAllowed1).toBe(true);
      
      // Additional requests within limit should be allowed
      for (let i = 0; i < 25; i++) {
        const isAllowed = service.checkRateLimit(connectionId);
        expect(isAllowed).toBe(true);
      }
    });

    test('should block requests exceeding rate limit', () => {
      const connectionId = 'test-connection-1';
      
      // Exceed rate limit
      for (let i = 0; i < service.config.rateLimitRequests + 5; i++) {
        service.checkRateLimit(connectionId);
      }
      
      // Next request should be blocked
      const isAllowed = service.checkRateLimit(connectionId);
      expect(isAllowed).toBe(false);
    });

    test('should reset rate limit after time window', () => {
      const connectionId = 'test-connection-1';
      
      // Exceed rate limit
      for (let i = 0; i < service.config.rateLimitRequests + 1; i++) {
        service.checkRateLimit(connectionId);
      }
      
      // Mock time advancement
      const originalNow = Date.now;
      Date.now = jest.fn(() => originalNow() + service.config.rateLimitWindow + 1000);
      
      // Should be allowed after window reset
      const isAllowed = service.checkRateLimit(connectionId);
      expect(isAllowed).toBe(true);
      
      // Restore original Date.now
      Date.now = originalNow;
    });
  });

  describe('Message Handling', () => {
    test('should handle AI chat messages', async () => {
      const connectionId = 'test-connection-1';
      const mockWS = {
        id: connectionId,
        send: jest.fn(),
        readyState: 1
      };

      service.connections.set(connectionId, {
        id: connectionId,
        ws: mockWS,
        userId: 'test-user'
      });

      const message = {
        type: 'ai_chat_request',
        data: {
          message: 'Hello AI',
          conversationId: 'test-conversation'
        }
      };

      await service.handleMessage(connectionId, message);

      expect(service.stats.totalStreams).toBe(1);
    });

    test('should handle invalid message format', async () => {
      const connectionId = 'test-connection-1';
      const mockWS = {
        id: connectionId,
        send: jest.fn(),
        readyState: 1
      };

      service.connections.set(connectionId, {
        id: connectionId,
        ws: mockWS
      });

      const invalidMessage = {
        type: 'invalid_type'
      };

      await service.handleMessage(connectionId, invalidMessage);

      expect(mockWS.send).toHaveBeenCalledWith(
        expect.stringContaining('error')
      );
    });

    test('should handle stream stop requests', async () => {
      const connectionId = 'test-connection-1';
      const streamId = 'test-stream-1';

      service.activeStreams.set(streamId, {
        id: streamId,
        connectionId,
        status: 'active'
      });

      const message = {
        type: 'stream_stop',
        data: { streamId }
      };

      await service.handleMessage(connectionId, message);

      const stream = service.activeStreams.get(streamId);
      expect(stream.status).toBe('stopped');
    });
  });

  describe('Streaming Functionality', () => {
    test('should initiate AI streaming response', async () => {
      const connectionId = 'test-connection-1';
      const mockWS = {
        id: connectionId,
        send: jest.fn(),
        readyState: 1
      };

      service.connections.set(connectionId, {
        id: connectionId,
        ws: mockWS,
        userId: 'test-user'
      });

      const request = {
        message: 'Analyze my portfolio',
        conversationId: 'test-conversation',
        streaming: true
      };

      await service.initiateAIStream(connectionId, request);

      expect(service.stats.activeStreams).toBe(1);
      expect(mockWS.send).toHaveBeenCalledWith(
        expect.stringContaining('stream_started')
      );
    });

    test('should handle streaming chunks', () => {
      const connectionId = 'test-connection-1';
      const streamId = 'test-stream-1';
      const mockWS = {
        send: jest.fn(),
        readyState: 1
      };

      service.connections.set(connectionId, {
        ws: mockWS
      });

      service.activeStreams.set(streamId, {
        id: streamId,
        connectionId,
        status: 'active'
      });

      const chunk = {
        type: 'content',
        text: 'This is a streaming response chunk'
      };

      service.sendStreamChunk(streamId, chunk);

      expect(mockWS.send).toHaveBeenCalledWith(
        expect.stringContaining('stream_chunk')
      );
      expect(service.stats.messagesSent).toBe(1);
    });

    test('should complete streaming session', () => {
      const connectionId = 'test-connection-1';
      const streamId = 'test-stream-1';
      const mockWS = {
        send: jest.fn(),
        readyState: 1
      };

      service.connections.set(connectionId, {
        ws: mockWS
      });

      service.activeStreams.set(streamId, {
        id: streamId,
        connectionId,
        status: 'active'
      });
      service.stats.activeStreams = 1;

      const metadata = {
        tokensUsed: 150,
        cost: 0.00075,
        duration: 2500
      };

      service.completeStream(streamId, metadata);

      expect(mockWS.send).toHaveBeenCalledWith(
        expect.stringContaining('stream_complete')
      );
      expect(service.activeStreams.has(streamId)).toBe(false);
      expect(service.stats.activeStreams).toBe(0);
    });
  });

  describe('Error Handling', () => {
    test('should handle streaming errors gracefully', () => {
      const connectionId = 'test-connection-1';
      const streamId = 'test-stream-1';
      const mockWS = {
        send: jest.fn(),
        readyState: 1
      };

      service.connections.set(connectionId, {
        ws: mockWS
      });

      service.activeStreams.set(streamId, {
        id: streamId,
        connectionId,
        status: 'active'
      });

      const error = new Error('Bedrock service error');

      service.handleStreamError(streamId, error);

      expect(mockWS.send).toHaveBeenCalledWith(
        expect.stringContaining('stream_error')
      );
      expect(service.stats.errors).toBe(1);
    });

    test('should handle WebSocket send errors', () => {
      const connectionId = 'test-connection-1';
      const mockWS = {
        send: jest.fn().mockImplementation(() => {
          throw new Error('WebSocket error');
        }),
        readyState: 1
      };

      service.connections.set(connectionId, {
        ws: mockWS
      });

      // Should not throw error
      expect(() => {
        service.sendMessage(connectionId, { type: 'test' });
      }).not.toThrow();

      expect(service.stats.errors).toBe(1);
    });

    test('should handle connection cleanup on error', () => {
      const connectionId = 'test-connection-1';
      service.connections.set(connectionId, {
        id: connectionId
      });
      service.stats.activeConnections = 1;

      service.handleConnectionError(connectionId, new Error('Connection error'));

      expect(service.connections.has(connectionId)).toBe(false);
      expect(service.stats.activeConnections).toBe(0);
      expect(service.stats.errors).toBe(1);
    });
  });

  describe('Health Monitoring', () => {
    test('should implement heartbeat mechanism', () => {
      const connectionId = 'test-connection-1';
      const mockWS = {
        ping: jest.fn(),
        readyState: 1
      };

      service.connections.set(connectionId, {
        id: connectionId,
        ws: mockWS,
        lastHeartbeat: Date.now()
      });

      service.sendHeartbeat();

      expect(mockWS.ping).toHaveBeenCalled();
    });

    test('should detect and cleanup stale connections', () => {
      const connectionId = 'test-connection-1';
      const staleTimestamp = Date.now() - (service.config.heartbeatInterval * 3);

      service.connections.set(connectionId, {
        id: connectionId,
        lastHeartbeat: staleTimestamp,
        ws: { terminate: jest.fn() }
      });
      service.stats.activeConnections = 1;

      service.cleanupStaleConnections();

      expect(service.connections.has(connectionId)).toBe(false);
      expect(service.stats.activeConnections).toBe(0);
    });

    test('should provide service statistics', () => {
      const stats = service.getStatistics();

      expect(stats).toHaveProperty('totalConnections');
      expect(stats).toHaveProperty('activeConnections');
      expect(stats).toHaveProperty('totalStreams');
      expect(stats).toHaveProperty('activeStreams');
      expect(stats).toHaveProperty('messagesSent');
      expect(stats).toHaveProperty('errors');
      expect(stats).toHaveProperty('uptime');
    });
  });

  describe('Resource Management', () => {
    test('should timeout long-running streams', () => {
      const streamId = 'test-stream-1';
      const connectionId = 'test-connection-1';
      const pastTimeout = Date.now() - (service.config.streamTimeout + 1000);

      service.activeStreams.set(streamId, {
        id: streamId,
        connectionId,
        startTime: pastTimeout,
        status: 'active'
      });

      service.cleanupTimeoutStreams();

      const stream = service.activeStreams.get(streamId);
      expect(stream.status).toBe('timeout');
    });

    test('should handle graceful shutdown', async () => {
      const connectionId = 'test-connection-1';
      const mockWS = {
        close: jest.fn(),
        readyState: 1
      };

      service.connections.set(connectionId, {
        id: connectionId,
        ws: mockWS
      });

      await service.shutdown();

      expect(mockWS.close).toHaveBeenCalled();
      expect(mockWSServer.close).toHaveBeenCalled();
    });
  });

  describe('Integration with EnhancedBedrockService', () => {
    test('should handle successful Bedrock streaming response', async () => {
      const mockBedrockService = require('../../../services/EnhancedBedrockService');
      const mockInstance = new mockBedrockService();
      
      mockInstance.generateStreamingResponse.mockImplementation(async ({ onChunk, onComplete }) => {
        // Simulate streaming chunks
        onChunk({ type: 'content', text: 'Hello' });
        onChunk({ type: 'content', text: ' world' });
        onComplete({ tokensUsed: 10, cost: 0.001 });
      });

      service.bedrockService = mockInstance;

      const connectionId = 'test-connection-1';
      const mockWS = {
        send: jest.fn(),
        readyState: 1
      };

      service.connections.set(connectionId, {
        id: connectionId,
        ws: mockWS,
        userId: 'test-user'
      });

      await service.initiateAIStream(connectionId, {
        message: 'Test message',
        conversationId: 'test-conversation'
      });

      // Verify chunks were sent
      expect(mockWS.send).toHaveBeenCalledWith(
        expect.stringContaining('Hello')
      );
      expect(mockWS.send).toHaveBeenCalledWith(
        expect.stringContaining('world')
      );
    });
  });
});