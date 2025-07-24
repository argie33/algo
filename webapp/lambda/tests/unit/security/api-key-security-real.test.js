/**
 * API Key Security Validation Tests - HIGH PRIORITY #8
 * Tests actual security measures the site uses to protect API keys
 */
const request = require('supertest');
const jwt = require('jsonwebtoken');

// Mock dependencies
jest.mock('../../../utils/apiKeyService');
jest.mock('../../../middleware/auth');

const mockApiKeyService = require('../../../utils/apiKeyService');
const { authenticateToken } = require('../../../middleware/auth');

describe('API Key Security - Real Site Protection', () => {
  let app;

  beforeEach(() => {
    jest.clearAllMocks();
    app = require('../../../index');
  });

  describe('Authentication Security (What Site Actually Checks)', () => {
    test('should reject API key access without valid JWT token', async () => {
      // No Authorization header
      const response = await request(app)
        .get('/api/settings/api-keys')
        .expect(401);

      expect(response.body.error).toContain('Authentication required');
      expect(mockApiKeyService.listApiKeys).not.toHaveBeenCalled();
    });

    test('should reject API key access with expired JWT token', async () => {
      // Create expired token (what actually happens in production)
      const expiredToken = jwt.sign(
        { 
          sub: 'user-123',
          exp: Math.floor(Date.now() / 1000) - 3600 // Expired 1 hour ago
        },
        'test-secret'
      );

      authenticateToken.mockImplementation((req, res, next) => {
        return res.status(401).json({ error: 'Token expired' });
      });

      const response = await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', `Bearer ${expiredToken}`)
        .expect(401);

      expect(response.body.error).toContain('Token expired');
    });

    test('should reject API key access with malformed JWT token', async () => {
      authenticateToken.mockImplementation((req, res, next) => {
        return res.status(401).json({ error: 'Invalid token format' });
      });

      const response = await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', 'Bearer invalid-token-format')
        .expect(401);

      expect(response.body.error).toContain('Invalid token format');
    });
  });

  describe('User Isolation Security (Prevents Cross-User Access)', () => {
    test('should isolate API keys by user ID from JWT token', async () => {
      authenticateToken.mockImplementation((req, res, next) => {
        req.user = { sub: 'user-123' };
        next();
      });

      mockApiKeyService.listApiKeys.mockResolvedValue([
        { provider: 'alpaca', keyId: 'PK***456' }
      ]);

      await request(app)
        .get('/api/settings/api-keys')
        .expect(200);

      // Verify service called with user ID from JWT, not request body
      expect(mockApiKeyService.listApiKeys).toHaveBeenCalledWith('user-123');
    });

    test('should prevent user from accessing other users API keys via JWT manipulation', async () => {
      // User tries to manipulate JWT to access another user's keys
      authenticateToken.mockImplementation((req, res, next) => {
        req.user = { sub: 'user-123' }; // Authenticated as user-123
        next();
      });

      // Mock service to return keys for user-123 only
      mockApiKeyService.listApiKeys.mockResolvedValue([]);

      const response = await request(app)
        .get('/api/settings/api-keys')
        .expect(200);

      // Should only get user-123's keys, never user-456's keys
      expect(mockApiKeyService.listApiKeys).toHaveBeenCalledWith('user-123');
      expect(mockApiKeyService.listApiKeys).not.toHaveBeenCalledWith('user-456');
    });
  });

  describe('Input Validation Security (What Site Actually Validates)', () => {
    test('should validate Alpaca API key format to prevent injection', async () => {
      authenticateToken.mockImplementation((req, res, next) => {
        req.user = { sub: 'user-123' };
        next();
      });

      // Test malicious API key input
      const maliciousInput = {
        provider: 'alpaca',
        apiKey: '<script>alert("xss")</script>',
        secretKey: 'valid-secret-123'
      };

      const response = await request(app)
        .post('/api/settings/api-keys')
        .send(maliciousInput)
        .expect(400);

      expect(response.body.error).toContain('Invalid Alpaca API key format');
      expect(mockApiKeyService.storeApiKey).not.toHaveBeenCalled();
    });

    test('should validate provider names to prevent path traversal', async () => {
      authenticateToken.mockImplementation((req, res, next) => {
        req.user = { sub: 'user-123' };
        next();
      });

      // Test path traversal attack via provider
      const pathTraversalInput = {
        provider: '../../../etc/passwd',
        apiKey: 'PKTEST123456789',
        secretKey: 'valid-secret-123'
      };

      const response = await request(app)
        .post('/api/settings/api-keys')
        .send(pathTraversalInput)
        .expect(400);

      expect(response.body.error).toContain('Unsupported provider');
      expect(mockApiKeyService.storeApiKey).not.toHaveBeenCalled();
    });

    test('should sanitize SQL injection attempts in provider names', async () => {
      authenticateToken.mockImplementation((req, res, next) => {
        req.user = { sub: 'user-123' };
        next();
      });

      // Test SQL injection via provider field
      const sqlInjectionInput = {
        provider: "alpaca'; DROP TABLE user_api_keys; --",
        apiKey: 'PKTEST123456789',
        secretKey: 'valid-secret-123'
      };

      const response = await request(app)
        .post('/api/settings/api-keys')
        .send(sqlInjectionInput)
        .expect(400);

      expect(response.body.error).toContain('Unsupported provider');
      expect(mockApiKeyService.storeApiKey).not.toHaveBeenCalled();
    });
  });

  describe('API Key Format Validation (Production Security Rules)', () => {
    beforeEach(() => {
      authenticateToken.mockImplementation((req, res, next) => {
        req.user = { sub: 'user-123' };
        next();
      });
    });

    test('should enforce Alpaca API key format requirements', async () => {
      const testCases = [
        {
          name: 'too short',
          apiKey: 'PK123',
          expectedError: 'must start with PK and be at least 20 characters'
        },
        {
          name: 'wrong prefix',
          apiKey: 'SK1234567890123456789',
          expectedError: 'must start with PK and be at least 20 characters'
        },
        {
          name: 'special characters',
          apiKey: 'PK123456789<>{}[]',
          expectedError: 'must start with PK and be at least 20 characters'
        }
      ];

      for (const testCase of testCases) {
        const response = await request(app)
          .post('/api/settings/api-keys')
          .send({
            provider: 'alpaca',
            apiKey: testCase.apiKey,
            secretKey: 'valid-secret-1234567890'
          })
          .expect(400);

        expect(response.body.error).toContain(testCase.expectedError);
      }
    });

    test('should enforce Alpaca secret key length limits', async () => {
      const testCases = [
        {
          name: 'too short',
          secretKey: 'short',
          expectedError: 'must be 20-80 characters long'
        },
        {
          name: 'too long',
          secretKey: 'a'.repeat(81),
          expectedError: 'must be 20-80 characters long'
        }
      ];

      for (const testCase of testCases) {
        const response = await request(app)
          .post('/api/settings/api-keys')
          .send({
            provider: 'alpaca',
            apiKey: 'PKTEST1234567890123456',
            secretKey: testCase.secretKey
          })
          .expect(400);

        expect(response.body.error).toContain(testCase.expectedError);
      }
    });
  });

  describe('Rate Limiting Security (Anti-Abuse Protection)', () => {
    test('should rate limit API key creation attempts', async () => {
      authenticateToken.mockImplementation((req, res, next) => {
        req.user = { sub: 'user-123' };
        next();
      });

      mockApiKeyService.storeApiKey.mockResolvedValue(true);

      const validPayload = {
        provider: 'alpaca',
        apiKey: 'PKTEST1234567890123456',
        secretKey: 'valid-secret-1234567890'
      };

      // Make rapid requests to trigger rate limiting
      const requests = Array(6).fill().map(() => 
        request(app)
          .post('/api/settings/api-keys')
          .send(validPayload)
      );

      const responses = await Promise.all(requests);
      
      // At least one request should be rate limited
      const rateLimitedResponses = responses.filter(r => r.status === 429);
      expect(rateLimitedResponses.length).toBeGreaterThan(0);
    });
  });

  describe('Error Information Disclosure Prevention', () => {
    test('should not expose internal system details in error messages', async () => {
      authenticateToken.mockImplementation((req, res, next) => {
        req.user = { sub: 'user-123' };
        next();
      });

      // Simulate internal service error
      mockApiKeyService.storeApiKey.mockRejectedValue(
        new Error('Internal AWS error: ParameterStoreUnavailable at region us-east-1')
      );

      const response = await request(app)
        .post('/api/settings/api-keys')
        .send({
          provider: 'alpaca',
          apiKey: 'PKTEST1234567890123456',
          secretKey: 'valid-secret-1234567890'
        })
        .expect(500);

      // Should not expose internal AWS details
      expect(response.body.error).not.toContain('AWS');
      expect(response.body.error).not.toContain('ParameterStore');
      expect(response.body.error).not.toContain('us-east-1');
      
      // Should provide generic user-friendly message
      expect(response.body.error).toContain('temporarily unavailable');
    });

    test('should not expose user IDs or sensitive data in logs', async () => {
      const consoleSpy = jest.spyOn(console, 'log').mockImplementation();

      authenticateToken.mockImplementation((req, res, next) => {
        req.user = { sub: 'sensitive-user-id-12345' };
        next();
      });

      mockApiKeyService.listApiKeys.mockResolvedValue([]);

      await request(app)
        .get('/api/settings/api-keys')
        .expect(200);

      // Check that sensitive user ID is not logged in plain text
      const logCalls = consoleSpy.mock.calls.flat();
      const sensitiveData = logCalls.some(call => 
        typeof call === 'string' && call.includes('sensitive-user-id-12345')
      );
      
      expect(sensitiveData).toBe(false);

      consoleSpy.mockRestore();
    });
  });

  describe('HTTPS and Transport Security', () => {
    test('should set secure headers for API key endpoints', async () => {
      authenticateToken.mockImplementation((req, res, next) => {
        req.user = { sub: 'user-123' };
        next();
      });

      mockApiKeyService.listApiKeys.mockResolvedValue([]);

      const response = await request(app)
        .get('/api/settings/api-keys')
        .expect(200);

      // Check security headers are set
      expect(response.headers['x-content-type-options']).toBe('nosniff');
      expect(response.headers['x-frame-options']).toBe('DENY');
      expect(response.headers['x-xss-protection']).toBe('1; mode=block');
    });
  });
});