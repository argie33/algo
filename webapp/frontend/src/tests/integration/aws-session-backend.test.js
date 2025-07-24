/**
 * AWS Session Backend Integration Tests
 * Tests AWS Lambda session management, Redis integration, and API Gateway
 */

import { describe, it, expect, beforeEach, afterEach, vi, beforeAll, afterAll } from 'vitest';

// Mock AWS SDK
vi.mock('aws-sdk', () => ({
  SecretsManager: vi.fn(() => ({
    getSecretValue: vi.fn().mockReturnValue({
      promise: vi.fn().mockResolvedValue({
        SecretString: JSON.stringify({
          redis_endpoint: 'mock-redis-endpoint',
          encryption_key: 'mock-encryption-key',
          environment: 'test',
          project_name: 'stocks-webapp'
        })
      })
    })
  })),
  CognitoIdentityServiceProvider: vi.fn(() => ({
    adminGetUser: vi.fn().mockReturnValue({
      promise: vi.fn().mockResolvedValue({
        Username: 'testuser',
        UserAttributes: [
          { Name: 'email', Value: 'test@example.com' },
          { Name: 'given_name', Value: 'Test' },
          { Name: 'family_name', Value: 'User' }
        ]
      })
    })
  }))
}));

// Mock ioredis
vi.mock('ioredis', () => {
  const mockRedisInstance = {
    setex: vi.fn().mockResolvedValue('OK'),
    get: vi.fn().mockResolvedValue(null),
    del: vi.fn().mockResolvedValue(1),
    sadd: vi.fn().mockResolvedValue(1),
    srem: vi.fn().mockResolvedValue(1),
    smembers: vi.fn().mockResolvedValue([]),
    expire: vi.fn().mockResolvedValue(1),
    ping: vi.fn().mockResolvedValue('PONG'),
    pipeline: vi.fn(() => ({
      del: vi.fn(),
      exec: vi.fn().mockResolvedValue([])
    })),
    on: vi.fn()
  };

  return vi.fn(() => mockRedisInstance);
});

// Import the Lambda handler after mocking dependencies
let handler;

beforeAll(async () => {
  // Set environment variables
  process.env.REDIS_ENDPOINT = 'mock-redis-endpoint';
  process.env.SESSION_SECRETS_ARN = 'arn:aws:secretsmanager:us-east-1:123456789012:secret:test-session-secrets';
  
  // Import handler after mocks are set up
  const sessionManagement = await import('../../infrastructure/terraform/lambda/session-management.js');
  handler = sessionManagement.handler;
});

describe('AWS Session Backend Integration Tests', () => {
  let mockEvent;
  let mockContext;

  beforeEach(() => {
    vi.clearAllMocks();
    
    mockContext = {
      awsRequestId: 'test-request-id',
      functionName: 'test-session-management',
      getRemainingTimeInMillis: () => 30000
    };

    // Default event structure
    mockEvent = {
      httpMethod: 'POST',
      pathParameters: { proxy: 'create' },
      body: JSON.stringify({
        userId: 'test-user-123',
        sessionId: 'test-session-456',
        deviceFingerprint: 'mock-fingerprint',
        metadata: {
          userAgent: 'Test Browser',
          ipAddress: '192.168.1.1',
          loginTime: Date.now()
        }
      }),
      headers: {
        'Content-Type': 'application/json',
        'Origin': 'https://example.com'
      },
      requestContext: {
        requestId: 'test-request-id'
      }
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Session Creation', () => {
    it('should create a new session successfully', async () => {
      const Redis = await import('ioredis');
      const mockRedis = new Redis();
      
      mockRedis.setex.mockResolvedValue('OK');
      mockRedis.sadd.mockResolvedValue(1);
      mockRedis.expire.mockResolvedValue(1);
      mockRedis.smembers.mockResolvedValue([]); // No existing sessions

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(200);
      
      const body = JSON.parse(response.body);
      expect(body.success).toBe(true);
      expect(body.sessionId).toBe('test-session-456');
      expect(body.expiresAt).toBeDefined();
      
      // Verify Redis calls
      expect(mockRedis.setex).toHaveBeenCalledWith(
        expect.stringContaining('session:test-user-123:test-session-456'),
        86400,
        expect.stringMatching(/^\{.*\}$/) // JSON string
      );
      expect(mockRedis.sadd).toHaveBeenCalledWith(
        expect.stringContaining('user:test-user-123:sessions'),
        'test-session-456'
      );
    });

    it('should enforce concurrent session limits', async () => {
      const Redis = await import('ioredis');
      const mockRedis = new Redis();
      
      // Mock 6 existing sessions (exceeds limit of 5)
      const existingSessions = Array(6).fill().map((_, i) => `session-${i}`);
      mockRedis.smembers.mockResolvedValue(existingSessions);
      
      // Mock session data for cleanup
      mockRedis.get.mockImplementation((key) => {
        if (key.includes('session:')) {
          return JSON.stringify({
            sessionId: 'old-session',
            lastActivity: Date.now() - 1000,
            createdAt: Date.now() - 10000
          });
        }
        return null;
      });

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(200);
      
      // Should have cleaned up old sessions
      expect(mockRedis.del).toHaveBeenCalled();
      expect(mockRedis.srem).toHaveBeenCalled();
    });

    it('should handle invalid request data', async () => {
      mockEvent.body = JSON.stringify({
        // Missing required fields
        sessionId: 'test-session-456'
      });

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(400);
      
      const body = JSON.parse(response.body);
      expect(body.error).toBe('userId and sessionId are required');
    });

    it('should handle Redis connection errors', async () => {
      const Redis = await import('ioredis');
      const mockRedis = new Redis();
      
      mockRedis.setex.mockRejectedValue(new Error('Redis connection failed'));

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(500);
      
      const body = JSON.parse(response.body);
      expect(body.error).toBe('Failed to create session');
    });
  });

  describe('Session Validation', () => {
    beforeEach(() => {
      mockEvent.pathParameters.proxy = 'validate';
      mockEvent.body = JSON.stringify({
        userId: 'test-user-123',
        sessionId: 'test-session-456',
        deviceFingerprint: 'mock-fingerprint'
      });
    });

    it('should validate a valid session', async () => {
      const Redis = await import('ioredis');
      const mockRedis = new Redis();
      
      const sessionData = {
        userId: 'test-user-123',
        sessionId: 'test-session-456',
        deviceFingerprint: 'mock-fingerprint',
        createdAt: Date.now() - 3600000, // 1 hour ago
        lastActivity: Date.now() - 300000, // 5 minutes ago
        expiresAt: Date.now() + 3600000 // 1 hour from now
      };
      
      mockRedis.get.mockResolvedValue(JSON.stringify(sessionData));
      mockRedis.setex.mockResolvedValue('OK'); // For activity update

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(200);
      
      const body = JSON.parse(response.body);
      expect(body.valid).toBe(true);
      expect(body.session).toBeDefined();
      expect(body.session.userId).toBe('test-user-123');
      
      // Should update last activity
      expect(mockRedis.setex).toHaveBeenCalledWith(
        expect.stringContaining('session:test-user-123:test-session-456'),
        86400,
        expect.stringMatching(/lastActivity/)
      );
    });

    it('should reject expired sessions', async () => {
      const Redis = await import('ioredis');
      const mockRedis = new Redis();
      
      const expiredSessionData = {
        userId: 'test-user-123',
        sessionId: 'test-session-456',
        deviceFingerprint: 'mock-fingerprint',
        createdAt: Date.now() - 86400000, // 24 hours ago
        lastActivity: Date.now() - 86400000,
        expiresAt: Date.now() - 3600000 // 1 hour ago (expired)
      };
      
      mockRedis.get.mockResolvedValue(JSON.stringify(expiredSessionData));
      mockRedis.del.mockResolvedValue(1);

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(401);
      
      const body = JSON.parse(response.body);
      expect(body.valid).toBe(false);
      expect(body.reason).toBe('Session expired');
      
      // Should clean up expired session
      expect(mockRedis.del).toHaveBeenCalledWith(
        expect.stringContaining('session:test-user-123:test-session-456')
      );
    });

    it('should reject sessions with idle timeout', async () => {
      const Redis = await import('ioredis');
      const mockRedis = new Redis();
      
      const idleSessionData = {
        userId: 'test-user-123',
        sessionId: 'test-session-456',
        deviceFingerprint: 'mock-fingerprint',
        createdAt: Date.now() - 3600000,
        lastActivity: Date.now() - 1800000, // 30 minutes ago (idle timeout)
        expiresAt: Date.now() + 3600000
      };
      
      mockRedis.get.mockResolvedValue(JSON.stringify(idleSessionData));
      mockRedis.del.mockResolvedValue(1);

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(401);
      
      const body = JSON.parse(response.body);
      expect(body.valid).toBe(false);
      expect(body.reason).toBe('Session idle timeout');
    });

    it('should reject sessions with device fingerprint mismatch', async () => {
      const Redis = await import('ioredis');
      const mockRedis = new Redis();
      
      const sessionData = {
        userId: 'test-user-123',
        sessionId: 'test-session-456',
        deviceFingerprint: 'different-fingerprint', // Mismatch
        createdAt: Date.now() - 3600000,
        lastActivity: Date.now() - 300000,
        expiresAt: Date.now() + 3600000
      };
      
      mockRedis.get.mockResolvedValue(JSON.stringify(sessionData));

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(401);
      
      const body = JSON.parse(response.body);
      expect(body.valid).toBe(false);
      expect(body.reason).toBe('Device fingerprint mismatch');
    });

    it('should handle non-existent sessions', async () => {
      const Redis = await import('ioredis');
      const mockRedis = new Redis();
      
      mockRedis.get.mockResolvedValue(null); // Session not found

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(401);
      
      const body = JSON.parse(response.body);
      expect(body.valid).toBe(false);
      expect(body.reason).toBe('Session not found');
    });
  });

  describe('Session Updates', () => {
    beforeEach(() => {
      mockEvent.httpMethod = 'PUT';
      mockEvent.pathParameters.proxy = 'update';
      mockEvent.body = JSON.stringify({
        userId: 'test-user-123',
        sessionId: 'test-session-456',
        metadata: {
          userAgent: 'Updated Browser',
          lastAction: 'page_view'
        }
      });
    });

    it('should update session metadata', async () => {
      const Redis = await import('ioredis');
      const mockRedis = new Redis();
      
      const existingSessionData = {
        userId: 'test-user-123',
        sessionId: 'test-session-456',
        deviceFingerprint: 'mock-fingerprint',
        createdAt: Date.now() - 3600000,
        lastActivity: Date.now() - 300000,
        expiresAt: Date.now() + 3600000,
        version: 1
      };
      
      mockRedis.get.mockResolvedValue(JSON.stringify(existingSessionData));
      mockRedis.setex.mockResolvedValue('OK');

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(200);
      
      const body = JSON.parse(response.body);
      expect(body.success).toBe(true);
      
      // Verify the session was updated with new metadata
      expect(mockRedis.setex).toHaveBeenCalledWith(
        expect.stringContaining('session:test-user-123:test-session-456'),
        86400,
        expect.stringMatching(/userAgent.*Updated Browser/)
      );
    });

    it('should handle updates to non-existent sessions', async () => {
      const Redis = await import('ioredis');
      const mockRedis = new Redis();
      
      mockRedis.get.mockResolvedValue(null); // Session not found

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(404);
      
      const body = JSON.parse(response.body);
      expect(body.error).toBe('Session not found');
    });
  });

  describe('Session Activity Updates', () => {
    beforeEach(() => {
      mockEvent.httpMethod = 'PUT';
      mockEvent.pathParameters.proxy = 'activity';
      mockEvent.body = JSON.stringify({
        userId: 'test-user-123',
        sessionId: 'test-session-456'
      });
    });

    it('should update session activity timestamp', async () => {
      const Redis = await import('ioredis');
      const mockRedis = new Redis();
      
      const sessionData = {
        userId: 'test-user-123',
        sessionId: 'test-session-456',
        deviceFingerprint: 'mock-fingerprint',
        createdAt: Date.now() - 3600000,
        lastActivity: Date.now() - 300000,
        expiresAt: Date.now() + 3600000
      };
      
      mockRedis.get.mockResolvedValue(JSON.stringify(sessionData));
      mockRedis.setex.mockResolvedValue('OK');

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(200);
      
      const body = JSON.parse(response.body);
      expect(body.success).toBe(true);
      
      // Verify activity timestamp was updated
      expect(mockRedis.setex).toHaveBeenCalledWith(
        expect.stringContaining('session:test-user-123:test-session-456'),
        86400,
        expect.stringMatching(/lastActivity.*\d{13}/) // Recent timestamp
      );
    });
  });

  describe('Session Revocation', () => {
    beforeEach(() => {
      mockEvent.httpMethod = 'DELETE';
      mockEvent.pathParameters.proxy = 'revoke';
    });

    it('should revoke a specific session', async () => {
      mockEvent.body = JSON.stringify({
        userId: 'test-user-123',
        sessionId: 'test-session-456'
      });

      const Redis = await import('ioredis');
      const mockRedis = new Redis();
      
      mockRedis.del.mockResolvedValue(1);
      mockRedis.srem.mockResolvedValue(1);

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(200);
      
      const body = JSON.parse(response.body);
      expect(body.success).toBe(true);
      
      // Verify session was deleted
      expect(mockRedis.del).toHaveBeenCalledWith(
        expect.stringContaining('session:test-user-123:test-session-456')
      );
      expect(mockRedis.srem).toHaveBeenCalledWith(
        expect.stringContaining('user:test-user-123:sessions'),
        'test-session-456'
      );
    });

    it('should revoke all sessions for a user', async () => {
      mockEvent.body = JSON.stringify({
        userId: 'test-user-123',
        revokeAll: true
      });

      const Redis = await import('ioredis');
      const mockRedis = new Redis();
      
      const existingSessions = ['session-1', 'session-2', 'session-3'];
      mockRedis.smembers.mockResolvedValue(existingSessions);
      
      const mockPipeline = {
        del: vi.fn(),
        exec: vi.fn().mockResolvedValue([])
      };
      mockRedis.pipeline.mockReturnValue(mockPipeline);
      mockRedis.del.mockResolvedValue(1);

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(200);
      
      const body = JSON.parse(response.body);
      expect(body.success).toBe(true);
      expect(body.revokedSessions).toBe(3);
      
      // Verify pipeline was used to delete all sessions
      expect(mockPipeline.del).toHaveBeenCalledTimes(3);
      expect(mockPipeline.exec).toHaveBeenCalled();
    });
  });

  describe('Session Status and Listing', () => {
    beforeEach(() => {
      mockEvent.httpMethod = 'GET';
    });

    it('should get session status', async () => {
      mockEvent.pathParameters.proxy = 'status';
      mockEvent.queryStringParameters = {
        userId: 'test-user-123',
        sessionId: 'test-session-456'
      };

      const Redis = await import('ioredis');
      const mockRedis = new Redis();
      
      const sessionData = {
        userId: 'test-user-123',
        sessionId: 'test-session-456',
        createdAt: Date.now() - 3600000,
        lastActivity: Date.now() - 300000,
        expiresAt: Date.now() + 3600000
      };
      
      mockRedis.get.mockResolvedValue(JSON.stringify(sessionData));

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(200);
      
      const body = JSON.parse(response.body);
      expect(body.sessionId).toBe('test-session-456');
      expect(body.userId).toBe('test-user-123');
      expect(body.isValid).toBe(true);
      expect(body.timeToExpiry).toBeGreaterThan(0);
    });

    it('should list user sessions', async () => {
      mockEvent.pathParameters.proxy = 'list';
      mockEvent.queryStringParameters = {
        userId: 'test-user-123'
      };

      const Redis = await import('ioredis');
      const mockRedis = new Redis();
      
      const sessionIds = ['session-1', 'session-2'];
      mockRedis.smembers.mockResolvedValue(sessionIds);
      
      mockRedis.get.mockImplementation((key) => {
        if (key.includes('session-1')) {
          return JSON.stringify({
            sessionId: 'session-1',
            createdAt: Date.now() - 7200000,
            lastActivity: Date.now() - 300000,
            expiresAt: Date.now() + 3600000,
            deviceFingerprint: 'fingerprint-1'
          });
        } else if (key.includes('session-2')) {
          return JSON.stringify({
            sessionId: 'session-2',
            createdAt: Date.now() - 3600000,
            lastActivity: Date.now() - 600000,
            expiresAt: Date.now() + 7200000,
            deviceFingerprint: 'fingerprint-2'
          });
        }
        return null;
      });

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(200);
      
      const body = JSON.parse(response.body);
      expect(body.userId).toBe('test-user-123');
      expect(body.sessionCount).toBe(2);
      expect(body.sessions).toHaveLength(2);
      expect(body.sessions[0].sessionId).toBe('session-1');
      expect(body.sessions[1].sessionId).toBe('session-2');
    });
  });

  describe('CORS and Error Handling', () => {
    it('should handle CORS preflight requests', async () => {
      mockEvent.httpMethod = 'OPTIONS';

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(200);
      expect(response.headers['Access-Control-Allow-Origin']).toBe('*');
      expect(response.headers['Access-Control-Allow-Methods']).toContain('POST');
      expect(response.body).toBe('');
    });

    it('should handle unsupported HTTP methods', async () => {
      mockEvent.httpMethod = 'PATCH';
      mockEvent.pathParameters.proxy = 'unsupported';

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(404);
      
      const body = JSON.parse(response.body);
      expect(body.error).toBe('Endpoint not found');
    });

    it('should handle malformed JSON in request body', async () => {
      mockEvent.body = 'invalid json';

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(500);
      
      const body = JSON.parse(response.body);
      expect(body.error).toBe('Internal server error');
    });

    it('should include CORS headers in error responses', async () => {
      mockEvent.body = 'invalid json';

      const response = await handler(mockEvent, mockContext);
      
      expect(response.headers['Access-Control-Allow-Origin']).toBe('*');
      expect(response.headers['Content-Type']).toBe('application/json');
    });
  });

  describe('Session Cleanup', () => {
    beforeEach(() => {
      mockEvent.httpMethod = 'DELETE';
      mockEvent.pathParameters.proxy = 'cleanup';
      mockEvent.body = JSON.stringify({
        userId: 'test-user-123'
      });
    });

    it('should clean up expired and idle sessions', async () => {
      const Redis = await import('ioredis');
      const mockRedis = new Redis();
      
      const sessionIds = ['session-1', 'session-2', 'session-3'];
      mockRedis.smembers.mockResolvedValue(sessionIds);
      
      // Mock different session states
      mockRedis.get.mockImplementation((key) => {
        if (key.includes('session-1')) {
          // Expired session
          return JSON.stringify({
            sessionId: 'session-1',
            expiresAt: Date.now() - 3600000, // 1 hour ago
            lastActivity: Date.now() - 3600000
          });
        } else if (key.includes('session-2')) {
          // Idle session
          return JSON.stringify({
            sessionId: 'session-2',
            expiresAt: Date.now() + 3600000,
            lastActivity: Date.now() - 1800000 // 30 minutes ago
          });
        } else if (key.includes('session-3')) {
          // Valid session
          return JSON.stringify({
            sessionId: 'session-3',
            expiresAt: Date.now() + 3600000,
            lastActivity: Date.now() - 300000 // 5 minutes ago
          });
        }
        return null;
      });
      
      mockRedis.del.mockResolvedValue(1);
      mockRedis.srem.mockResolvedValue(1);

      const response = await handler(mockEvent, mockContext);
      
      expect(response.statusCode).toBe(200);
      
      const body = JSON.parse(response.body);
      expect(body.success).toBe(true);
      expect(body.cleanedSessions).toBe(2); // expired + idle sessions
      
      // Verify cleanup calls
      expect(mockRedis.del).toHaveBeenCalledTimes(2);
      expect(mockRedis.srem).toHaveBeenCalledTimes(2);
    });
  });
});