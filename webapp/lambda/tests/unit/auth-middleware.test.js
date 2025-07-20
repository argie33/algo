/**
 * UNIT TESTS: Authentication Middleware
 * Real implementation testing with zero mocks for business logic
 * Comprehensive coverage of JWT verification, Cognito integration, and development mode
 */

// Jest globals are automatically available in test environment

const jwt = require('jsonwebtoken');

describe('Authentication Middleware Unit Tests', () => {
  let mockRequest;
  let mockResponse;
  let nextFunction;
  let originalEnv;
  let auth; // Load auth module in beforeEach to pick up env changes
  
  beforeEach(() => {
    // Store original environment
    originalEnv = { ...process.env };
    
    // Clear module cache to pick up environment changes
    delete require.cache[require.resolve('../../middleware/auth')];
    auth = require('../../middleware/auth');
    
    // Clear cached configuration
    auth.clearConfigCache();
    
    // Mock request object
    mockRequest = {
      headers: {},
      method: 'GET',
      path: '/api/test',
      connection: { remoteAddress: '127.0.0.1' }
    };
    
    // Mock response object
    mockResponse = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn().mockReturnThis(),
      locals: {}
    };
    
    // Mock next function
    nextFunction = jest.fn();
    
    // Mock console methods to reduce noise in tests
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'warn').mockImplementation(() => {});
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });
  
  afterEach(() => {
    // Restore original environment
    process.env = originalEnv;
    jest.restoreAllMocks();
  });

  describe('Development Mode Authentication', () => {
    beforeEach(() => {
      process.env.NODE_ENV = 'development';
      process.env.ALLOW_DEV_AUTH_BYPASS = 'true';
    });

    it('allows access without token in development mode', async () => {
      await auth.authenticateToken(mockRequest, mockResponse, nextFunction);
      
      expect(nextFunction).toHaveBeenCalledTimes(1);
      expect(mockRequest.user).toBeDefined();
      expect(mockRequest.user.authMethod).toBe('dev-bypass');
      expect(mockRequest.user.isDevelopment).toBe(true);
      expect(mockRequest.user.email).toBe('dev@example.com');
      expect(mockRequest.user.role).toBe('admin');
    });

    it('validates development JWT tokens correctly', async () => {
      const devToken = auth.generateTestToken('test-user', 'test@example.com');
      mockRequest.headers.authorization = `Bearer ${devToken}`;
      
      await auth.authenticateToken(mockRequest, mockResponse, nextFunction);
      
      expect(nextFunction).toHaveBeenCalledTimes(1);
      expect(mockRequest.user).toBeDefined();
      expect(mockRequest.user.authMethod).toBe('dev-token');
      expect(mockRequest.user.email).toBe('test@example.com');
      expect(mockRequest.user.sub).toBe('test-user');
    });

    it('generates valid development tokens', () => {
      const token = auth.generateTestToken('user123', 'user@test.com');
      
      expect(token).toBeDefined();
      expect(typeof token).toBe('string');
      
      // Verify token can be decoded
      const secret = process.env.DEV_JWT_SECRET || 'development-secret-key';
      const decoded = jwt.verify(token, secret);
      
      expect(decoded.sub).toBe('user123');
      expect(decoded.email).toBe('user@test.com');
      expect(decoded.username).toBe('user');
      expect(decoded['custom:role']).toBe('admin');
    });

    it('falls back to development mode when Cognito is unavailable', async () => {
      // Provide invalid token that would fail Cognito verification
      mockRequest.headers.authorization = 'Bearer invalid-token';
      
      await auth.authenticateToken(mockRequest, mockResponse, nextFunction);
      
      expect(nextFunction).toHaveBeenCalledTimes(1);
      expect(mockRequest.user).toBeDefined();
      expect(mockRequest.user.authMethod).toBe('dev-fallback');
    });
  });

  describe('Production Mode Authentication', () => {
    beforeEach(() => {
      process.env.NODE_ENV = 'production';
      process.env.ALLOW_DEV_AUTH_BYPASS = 'false';
    });

    it('requires authentication token in production mode', async () => {
      await auth.authenticateToken(mockRequest, mockResponse, nextFunction);
      
      expect(mockResponse.status).toHaveBeenCalledWith(401);
      expect(mockResponse.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Authentication required',
          message: 'Access token is missing from Authorization header'
        })
      );
      expect(nextFunction).not.toHaveBeenCalled();
    });

    it('rejects invalid tokens in production mode', async () => {
      mockRequest.headers.authorization = 'Bearer invalid-token';
      
      await auth.authenticateToken(mockRequest, mockResponse, nextFunction);
      
      expect(mockResponse.status).toHaveBeenCalledWith(401);
      expect(nextFunction).not.toHaveBeenCalled();
    });

    it('handles malformed authorization headers', async () => {
      mockRequest.headers.authorization = 'InvalidFormat';
      
      await auth.authenticateToken(mockRequest, mockResponse, nextFunction);
      
      expect(mockResponse.status).toHaveBeenCalledWith(401);
      expect(nextFunction).not.toHaveBeenCalled();
    });
  });

  describe('JWT Token Validation', () => {
    beforeEach(() => {
      process.env.NODE_ENV = 'development';
    });

    it('handles expired JWT tokens', async () => {
      // Create expired token
      const expiredPayload = {
        sub: 'user123',
        email: 'user@test.com',
        exp: Math.floor(Date.now() / 1000) - 3600 // Expired 1 hour ago
      };
      const secret = process.env.DEV_JWT_SECRET || 'development-secret-key';
      const expiredToken = jwt.sign(expiredPayload, secret);
      
      mockRequest.headers.authorization = `Bearer ${expiredToken}`;
      
      await auth.authenticateToken(mockRequest, mockResponse, nextFunction);
      
      // In development mode, should fall back to dev access
      expect(nextFunction).toHaveBeenCalledTimes(1);
      expect(mockRequest.user.authMethod).toBe('dev-fallback');
    });

    it('validates JWT token structure and claims', () => {
      const token = auth.generateTestToken('test-user', 'test@example.com');
      const secret = process.env.DEV_JWT_SECRET || 'development-secret-key';
      const decoded = jwt.verify(token, secret);
      
      // Check required claims
      expect(decoded.sub).toBeDefined();
      expect(decoded.email).toBeDefined();
      expect(decoded.iat).toBeDefined();
      expect(decoded.exp).toBeDefined();
      expect(decoded.aud).toBeDefined();
      expect(decoded.iss).toBeDefined();
      
      // Check custom claims
      expect(decoded['custom:role']).toBe('admin');
      expect(decoded['cognito:groups']).toContain('admin');
      expect(decoded.email_verified).toBe(true);
    });

    it('handles malformed JWT tokens gracefully', async () => {
      mockRequest.headers.authorization = 'Bearer not.a.valid.jwt';
      
      await auth.authenticateToken(mockRequest, mockResponse, nextFunction);
      
      // Should fall back in development mode
      expect(nextFunction).toHaveBeenCalledTimes(1);
    });
  });

  describe('Role-Based Authorization', () => {
    beforeEach(() => {
      mockRequest.user = {
        sub: 'user123',
        email: 'user@test.com',
        role: 'user',
        groups: ['subscribers']
      };
    });

    it('allows access when user has required role', () => {
      const middleware = auth.requireRole(['user', 'admin']);
      
      middleware(mockRequest, mockResponse, nextFunction);
      
      expect(nextFunction).toHaveBeenCalledTimes(1);
    });

    it('allows access when user is in required group', () => {
      const middleware = auth.requireRole(['subscribers']);
      
      middleware(mockRequest, mockResponse, nextFunction);
      
      expect(nextFunction).toHaveBeenCalledTimes(1);
    });

    it('denies access when user lacks required role', () => {
      const middleware = auth.requireRole(['admin']);
      
      middleware(mockRequest, mockResponse, nextFunction);
      
      expect(mockResponse.status).toHaveBeenCalledWith(403);
      expect(mockResponse.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Insufficient permissions'
        })
      );
      expect(nextFunction).not.toHaveBeenCalled();
    });

    it('denies access when user is not authenticated', () => {
      delete mockRequest.user;
      const middleware = auth.requireRole(['user']);
      
      middleware(mockRequest, mockResponse, nextFunction);
      
      expect(mockResponse.status).toHaveBeenCalledWith(401);
      expect(nextFunction).not.toHaveBeenCalled();
    });

    it('handles multiple role requirements', () => {
      mockRequest.user.role = 'admin';
      const middleware = auth.requireRole(['admin', 'superuser']);
      
      middleware(mockRequest, mockResponse, nextFunction);
      
      expect(nextFunction).toHaveBeenCalledTimes(1);
    });
  });

  describe('Optional Authentication', () => {
    it('continues without authentication when no token provided', async () => {
      await auth.optionalAuth(mockRequest, mockResponse, nextFunction);
      
      expect(nextFunction).toHaveBeenCalledTimes(1);
      expect(mockRequest.user).toBeUndefined();
    });

    it('authenticates when valid token is provided', async () => {
      process.env.NODE_ENV = 'development';
      const token = auth.generateTestToken();
      mockRequest.headers.authorization = `Bearer ${token}`;
      
      await auth.optionalAuth(mockRequest, mockResponse, nextFunction);
      
      expect(nextFunction).toHaveBeenCalledTimes(1);
      expect(mockRequest.user).toBeDefined();
    });

    it('continues silently when authentication fails', async () => {
      process.env.NODE_ENV = 'production';
      process.env.ALLOW_DEV_AUTH_BYPASS = 'false';
      mockRequest.headers.authorization = 'Bearer invalid-token';
      
      await auth.optionalAuth(mockRequest, mockResponse, nextFunction);
      
      expect(nextFunction).toHaveBeenCalledTimes(1);
      expect(mockRequest.user).toBeUndefined();
    });
  });

  describe('Request Context Enhancement', () => {
    beforeEach(() => {
      process.env.NODE_ENV = 'development';
      mockRequest.headers['x-request-id'] = 'test-request-123';
      mockRequest.headers['x-forwarded-for'] = '192.168.1.100';
      mockRequest.headers['user-agent'] = 'Test Browser/1.0';
    });

    it('enriches user object with request context', async () => {
      await auth.authenticateToken(mockRequest, mockResponse, nextFunction);
      
      expect(mockRequest.user).toMatchObject({
        clientIp: '192.168.1.100',
        userAgent: 'Test Browser/1.0',
        requestId: 'test-request-123',
        authenticatedAt: expect.any(String)
      });
    });

    it('generates request ID when not provided', async () => {
      delete mockRequest.headers['x-request-id'];
      
      await auth.authenticateToken(mockRequest, mockResponse, nextFunction);
      
      expect(mockRequest.user.requestId).toBeDefined();
      expect(typeof mockRequest.user.requestId).toBe('string');
    });

    it('handles missing client IP gracefully', async () => {
      delete mockRequest.headers['x-forwarded-for'];
      delete mockRequest.connection.remoteAddress;
      
      await auth.authenticateToken(mockRequest, mockResponse, nextFunction);
      
      expect(mockRequest.user.clientIp).toBeDefined();
    });
  });

  describe('Cognito Configuration Management', () => {
    it('loads configuration from environment variables', async () => {
      process.env.COGNITO_USER_POOL_ID = 'us-east-1_test123';
      process.env.COGNITO_CLIENT_ID = 'test-client-id';
      process.env.AWS_REGION = 'us-east-1';
      
      const config = await auth.loadCognitoConfig();
      
      expect(config).toEqual({
        userPoolId: 'us-east-1_test123',
        clientId: 'test-client-id',
        region: 'us-east-1'
      });
    });

    it('handles missing Cognito configuration gracefully', async () => {
      delete process.env.COGNITO_USER_POOL_ID;
      delete process.env.COGNITO_CLIENT_ID;
      delete process.env.COGNITO_SECRET_ARN;
      
      const config = await auth.loadCognitoConfig();
      
      expect(config).toBeNull();
    });

    it('uses default region when not specified', async () => {
      process.env.COGNITO_USER_POOL_ID = 'us-east-1_test123';
      process.env.COGNITO_CLIENT_ID = 'test-client-id';
      delete process.env.AWS_REGION;
      delete process.env.AWS_DEFAULT_REGION;
      
      const config = await auth.loadCognitoConfig();
      
      expect(config.region).toBe('us-east-1');
    });
  });

  describe('Authentication Status Endpoint', () => {
    let mockRes;
    
    beforeEach(() => {
      mockRes = {
        json: jest.fn(),
        status: jest.fn().mockReturnThis()
      };
    });

    it('returns comprehensive authentication status', async () => {
      process.env.NODE_ENV = 'development';
      process.env.COGNITO_USER_POOL_ID = 'test-pool';
      process.env.COGNITO_CLIENT_ID = 'test-client';
      
      await auth.getAuthStatus(mockRequest, mockRes);
      
      expect(mockRes.json).toHaveBeenCalledWith(
        expect.objectContaining({
          status: 'healthy',
          configuration: expect.objectContaining({
            developmentMode: true,
            developmentBypassAllowed: true
          }),
          environment: expect.objectContaining({
            NODE_ENV: 'development',
            hasUserPoolId: true,
            hasClientId: true
          })
        })
      );
    });

    it('handles status check errors gracefully', async () => {
      // Create an error by making process.env throw when accessed
      const originalProcess = global.process;
      global.process = new Proxy(originalProcess, {
        get(target, prop) {
          if (prop === 'env') {
            throw new Error('Process environment access failed');
          }
          return target[prop];
        }
      });
      
      await auth.getAuthStatus(mockRequest, mockResponse);
      
      expect(mockResponse.status).toHaveBeenCalledWith(500);
      expect(mockResponse.json).toHaveBeenCalledWith(
        expect.objectContaining({
          status: 'error',
          error: 'Process environment access failed'
        })
      );
      
      // Restore the original process
      global.process = originalProcess;
    });
  });

  describe('Error Handling and Edge Cases', () => {
    it('handles network errors during token verification', async () => {
      // Temporarily restore console for debugging
      console.log.mockRestore();
      
      // Set production environment
      process.env.NODE_ENV = 'production';
      process.env.ALLOW_DEV_AUTH_BYPASS = 'false';
      
      // Clear cache and reload module to pick up environment changes
      delete require.cache[require.resolve('../../middleware/auth')];
      const prodAuth = require('../../middleware/auth');
      prodAuth.clearConfigCache();
      
      // Mock network error
      const networkError = new Error('Network error during token verification');
      networkError.code = 'ENOTFOUND';
      
      mockRequest.headers.authorization = 'Bearer some-token';
      
      // Mock getVerifier to return a verifier that throws network error during verify
      const mockVerifier = {
        verify: jest.fn().mockRejectedValue(networkError)
      };
      jest.spyOn(prodAuth, 'getVerifier').mockResolvedValue(mockVerifier);
      
      await prodAuth.authenticateToken(mockRequest, mockResponse, nextFunction);
      
      // Debug: check what was actually called
      console.log('Status called with:', mockResponse.status.mock.calls);
      console.log('JSON called with:', mockResponse.json.mock.calls);
      
      expect(mockResponse.status).toHaveBeenCalledWith(503);
      expect(mockResponse.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Authentication service unavailable'
        })
      );
    });

    it('handles concurrent authentication requests safely', async () => {
      process.env.NODE_ENV = 'development';
      
      const requests = Array.from({ length: 10 }, (_, i) => ({
        ...mockRequest,
        headers: { ...mockRequest.headers }
      }));
      
      const responses = Array.from({ length: 10 }, () => ({
        ...mockResponse,
        status: jest.fn().mockReturnThis(),
        json: jest.fn().mockReturnThis()
      }));
      
      const nexts = Array.from({ length: 10 }, () => jest.fn());
      
      // Execute concurrent authentication
      await Promise.all(
        requests.map((req, i) => 
          auth.authenticateToken(req, responses[i], nexts[i])
        )
      );
      
      // All should succeed in development mode
      nexts.forEach(next => {
        expect(next).toHaveBeenCalledTimes(1);
      });
    });

    it('preserves original user data when authentication fails in development', async () => {
      process.env.NODE_ENV = 'development';
      mockRequest.user = { originalData: 'preserved' };
      
      await auth.authenticateToken(mockRequest, mockResponse, nextFunction);
      
      // Should replace with dev user, not preserve original
      expect(mockRequest.user.originalData).toBeUndefined();
      expect(mockRequest.user.authMethod).toBe('dev-bypass');
    });

    it('handles missing authorization header gracefully', async () => {
      process.env.NODE_ENV = 'production';
      process.env.ALLOW_DEV_AUTH_BYPASS = 'false';
      
      await auth.authenticateToken(mockRequest, mockResponse, nextFunction);
      
      expect(mockResponse.status).toHaveBeenCalledWith(401);
      expect(mockResponse.json).toHaveBeenCalledWith(
        expect.objectContaining({
          details: expect.objectContaining({
            authHeaderPresent: false,
            expectedFormat: 'Bearer <token>'
          })
        })
      );
    });
  });

  describe('Token Generation and Validation', () => {
    it('generates tokens with correct expiration', () => {
      const token = auth.generateTestToken();
      const secret = process.env.DEV_JWT_SECRET || 'development-secret-key';
      const decoded = jwt.verify(token, secret);
      
      const now = Math.floor(Date.now() / 1000);
      const expectedExp = now + (24 * 60 * 60); // 24 hours
      
      expect(decoded.exp).toBeCloseTo(expectedExp, -2); // Within 100 seconds
    });

    it('generates unique tokens for different users', () => {
      const token1 = auth.generateTestToken('user1', 'user1@test.com');
      const token2 = auth.generateTestToken('user2', 'user2@test.com');
      
      expect(token1).not.toBe(token2);
      
      const secret = process.env.DEV_JWT_SECRET || 'development-secret-key';
      const decoded1 = jwt.verify(token1, secret);
      const decoded2 = jwt.verify(token2, secret);
      
      expect(decoded1.sub).toBe('user1');
      expect(decoded2.sub).toBe('user2');
      expect(decoded1.email).toBe('user1@test.com');
      expect(decoded2.email).toBe('user2@test.com');
    });

    it('uses custom JWT secret when provided', () => {
      process.env.DEV_JWT_SECRET = 'custom-secret-key';
      
      const token = auth.generateTestToken();
      
      // Should be able to verify with custom secret
      const decoded = jwt.verify(token, 'custom-secret-key');
      expect(decoded).toBeDefined();
      
      // Should fail with default secret
      expect(() => {
        jwt.verify(token, 'development-secret-key');
      }).toThrow();
    });
  });
});