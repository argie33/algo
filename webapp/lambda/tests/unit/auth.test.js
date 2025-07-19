/**
 * Authentication Service Unit Tests
 * Comprehensive testing for JWT verification, token management, and user authentication
 */

// Jest globals are automatically available in test environment

// Mock AWS Cognito and JWT dependencies
jest.mock('aws-jwt-verify');
jest.mock('@aws-sdk/client-cognito-identity-provider');
jest.mock('../../utils/secureLogger', () => ({
  secureLogger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    security: jest.fn(),
    auditAuth: jest.fn()
  }
}));

const { CognitoJwtVerifier } = require('aws-jwt-verify');
const { CognitoIdentityProviderClient } = require('@aws-sdk/client-cognito-identity-provider');

describe('Authentication Service', () => {
  let mockVerifier;
  let mockCognitoClient;
  
  beforeEach(() => {
    jest.clearAllMocks();
    
    // Mock JWT verifier
    mockVerifier = {
      verify: jest.fn()
    };
    CognitoJwtVerifier.create.mockReturnValue(mockVerifier);
    
    // Mock Cognito client
    mockCognitoClient = {
      send: jest.fn()
    };
    CognitoIdentityProviderClient.mockImplementation(() => mockCognitoClient);
    
    // Set test environment variables
    process.env.COGNITO_USER_POOL_ID = 'us-east-1_TestPool';
    process.env.COGNITO_CLIENT_ID = 'test-client-id';
    process.env.JWT_SECRET = 'test-jwt-secret';
  });

  describe('JWT Token Verification', () => {
    test('should verify valid JWT tokens successfully', async () => {
      const { authenticateToken } = require('../../middleware/auth');
      
      const mockPayload = {
        sub: 'user-123',
        email: 'test@example.com',
        'cognito:username': 'testuser',
        exp: Math.floor(Date.now() / 1000) + 3600,
        iat: Math.floor(Date.now() / 1000)
      };
      
      mockVerifier.verify.mockResolvedValue(mockPayload);
      
      const req = {
        headers: {
          authorization: 'Bearer valid-jwt-token'
        }
      };
      const res = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      const next = jest.fn();
      
      await authenticateToken(req, res, next);
      
      expect(mockVerifier.verify).toHaveBeenCalledWith('valid-jwt-token');
      expect(req.user).toEqual(mockPayload);
      expect(next).toHaveBeenCalled();
      expect(res.status).not.toHaveBeenCalled();
    });

    test('should reject invalid JWT tokens', async () => {
      const { authenticateToken } = require('../../middleware/auth');
      
      mockVerifier.verify.mockRejectedValue(new Error('Invalid token'));
      
      const req = {
        headers: {
          authorization: 'Bearer invalid-token'
        }
      };
      const res = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      const next = jest.fn();
      
      await authenticateToken(req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Invalid or expired token'
        })
      );
      expect(next).not.toHaveBeenCalled();
    });

    test('should handle missing authorization header', async () => {
      const { authenticateToken } = require('../../middleware/auth');
      
      const req = { headers: {} };
      const res = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      const next = jest.fn();
      
      await authenticateToken(req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Access token is missing from Authorization header'
        })
      );
    });

    test('should handle malformed authorization header', async () => {
      const { authenticateToken } = require('../../middleware/auth');
      
      const req = {
        headers: {
          authorization: 'InvalidFormat token'
        }
      };
      const res = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      const next = jest.fn();
      
      await authenticateToken(req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Access token is missing from Authorization header'
        })
      );
    });

    test('should handle expired tokens', async () => {
      const { authenticateToken } = require('../../middleware/auth');
      
      const expiredError = new Error('Token expired');
      expiredError.name = 'TokenExpiredError';
      mockVerifier.verify.mockRejectedValue(expiredError);
      
      const req = {
        headers: {
          authorization: 'Bearer expired-token'
        }
      };
      const res = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      const next = jest.fn();
      
      await authenticateToken(req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Invalid or expired token'
        })
      );
    });
  });

  describe('Cognito Integration', () => {
    test('should initialize Cognito JWT verifier with correct configuration', () => {
      delete require.cache[require.resolve('../../middleware/auth')];
      require('../../middleware/auth');
      
      expect(CognitoJwtVerifier.create).toHaveBeenCalledWith({
        userPoolId: 'us-east-1_TestPool',
        tokenUse: 'access',
        clientId: 'test-client-id'
      });
    });

    test('should handle Cognito service errors gracefully', async () => {
      const { authenticateToken } = require('../../middleware/auth');
      
      const cognitoError = new Error('Cognito service unavailable');
      cognitoError.code = 'ServiceUnavailable';
      mockVerifier.verify.mockRejectedValue(cognitoError);
      
      const req = {
        headers: {
          authorization: 'Bearer valid-token'
        }
      };
      const res = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      const next = jest.fn();
      
      await authenticateToken(req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(401);
    });

    test('should validate token issuer and audience', async () => {
      const { authenticateToken } = require('../../middleware/auth');
      
      const invalidIssuerError = new Error('Invalid issuer');
      invalidIssuerError.name = 'JwtInvalidIssuerError';
      mockVerifier.verify.mockRejectedValue(invalidIssuerError);
      
      const req = {
        headers: {
          authorization: 'Bearer token-with-invalid-issuer'
        }
      };
      const res = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      const next = jest.fn();
      
      await authenticateToken(req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(401);
    });
  });

  describe('User Context Management', () => {
    test('should extract user information from valid tokens', async () => {
      const { authenticateToken } = require('../../middleware/auth');
      
      const mockPayload = {
        sub: 'user-456',
        email: 'john.doe@example.com',
        'cognito:username': 'johndoe',
        'cognito:groups': ['users', 'premium'],
        email_verified: true,
        exp: Math.floor(Date.now() / 1000) + 3600
      };
      
      mockVerifier.verify.mockResolvedValue(mockPayload);
      
      const req = {
        headers: {
          authorization: 'Bearer user-token'
        }
      };
      const res = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      const next = jest.fn();
      
      await authenticateToken(req, res, next);
      
      expect(req.user).toEqual(mockPayload);
      expect(req.user.sub).toBe('user-456');
      expect(req.user.email).toBe('john.doe@example.com');
      expect(req.user['cognito:username']).toBe('johndoe');
    });

    test('should handle tokens with minimal user information', async () => {
      const { authenticateToken } = require('../../middleware/auth');
      
      const minimalPayload = {
        sub: 'user-789',
        exp: Math.floor(Date.now() / 1000) + 3600
      };
      
      mockVerifier.verify.mockResolvedValue(minimalPayload);
      
      const req = {
        headers: {
          authorization: 'Bearer minimal-token'
        }
      };
      const res = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      const next = jest.fn();
      
      await authenticateToken(req, res, next);
      
      expect(req.user).toEqual(minimalPayload);
      expect(req.user.sub).toBe('user-789');
      expect(next).toHaveBeenCalled();
    });
  });

  describe('Security & Audit Logging', () => {
    test('should log successful authentication events', async () => {
      const { secureLogger } = require('../utils/secureLogger');
      const { authenticateToken } = require('../../middleware/auth');
      
      const mockPayload = {
        sub: 'user-123',
        email: 'test@example.com'
      };
      
      mockVerifier.verify.mockResolvedValue(mockPayload);
      
      const req = {
        headers: {
          authorization: 'Bearer valid-token'
        },
        ip: '192.168.1.100',
        get: jest.fn(() => 'Mozilla/5.0')
      };
      const res = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      const next = jest.fn();
      
      await authenticateToken(req, res, next);
      
      expect(secureLogger.auditAuth).toHaveBeenCalledWith(
        'token_verification_success',
        'user-123',
        expect.any(Object)
      );
    });

    test('should log failed authentication attempts', async () => {
      const { secureLogger } = require('../utils/secureLogger');
      const { authenticateToken } = require('../../middleware/auth');
      
      mockVerifier.verify.mockRejectedValue(new Error('Invalid token'));
      
      const req = {
        headers: {
          authorization: 'Bearer invalid-token'
        },
        ip: '192.168.1.100'
      };
      const res = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      const next = jest.fn();
      
      await authenticateToken(req, res, next);
      
      expect(secureLogger.auditAuth).toHaveBeenCalledWith(
        'token_verification_failure',
        null,
        expect.objectContaining({
          error: 'Invalid token',
          ip: '192.168.1.100'
        })
      );
    });

    test('should not log sensitive token data', async () => {
      const { secureLogger } = require('../utils/secureLogger');
      const { authenticateToken } = require('../../middleware/auth');
      
      mockVerifier.verify.mockRejectedValue(new Error('Invalid token'));
      
      const req = {
        headers: {
          authorization: 'Bearer secret-token-data'
        }
      };
      const res = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      const next = jest.fn();
      
      await authenticateToken(req, res, next);
      
      // Check that token data is not logged
      const logCalls = secureLogger.auditAuth.mock.calls.flat();
      const loggedData = JSON.stringify(logCalls);
      
      expect(loggedData).not.toContain('secret-token-data');
    });
  });

  describe('Performance & Rate Limiting', () => {
    test('should handle high volume token verification', async () => {
      const { authenticateToken } = require('../../middleware/auth');
      
      const mockPayload = { sub: 'user-123' };
      mockVerifier.verify.mockResolvedValue(mockPayload);
      
      const promises = [];
      for (let i = 0; i < 100; i++) {
        const req = {
          headers: {
            authorization: `Bearer token-${i}`
          }
        };
        const res = {
          status: jest.fn().mockReturnThis(),
          json: jest.fn()
        };
        const next = jest.fn();
        
        promises.push(authenticateToken(req, res, next));
      }
      
      await Promise.all(promises);
      
      expect(mockVerifier.verify).toHaveBeenCalledTimes(100);
    });

    test('should measure token verification performance', async () => {
      const { secureLogger } = require('../utils/secureLogger');
      const { authenticateToken } = require('../../middleware/auth');
      
      // Simulate slow verification
      mockVerifier.verify.mockImplementation(() => 
        new Promise(resolve => 
          setTimeout(() => resolve({ sub: 'user-123' }), 100)
        )
      );
      
      const req = {
        headers: {
          authorization: 'Bearer slow-token'
        }
      };
      const res = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      const next = jest.fn();
      
      const start = Date.now();
      await authenticateToken(req, res, next);
      const duration = Date.now() - start;
      
      expect(duration).toBeGreaterThan(90);
      expect(secureLogger.debug).toHaveBeenCalled();
    });
  });

  describe('Error Recovery & Resilience', () => {
    test('should handle Cognito service timeouts', async () => {
      const { authenticateToken } = require('../../middleware/auth');
      
      const timeoutError = new Error('Request timeout');
      timeoutError.code = 'TimeoutError';
      mockVerifier.verify.mockRejectedValue(timeoutError);
      
      const req = {
        headers: {
          authorization: 'Bearer timeout-token'
        }
      };
      const res = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      const next = jest.fn();
      
      await authenticateToken(req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: 'Invalid or expired token'
        })
      );
    });

    test('should handle network connectivity issues', async () => {
      const { authenticateToken } = require('../../middleware/auth');
      
      const networkError = new Error('Network unavailable');
      networkError.code = 'NetworkingError';
      mockVerifier.verify.mockRejectedValue(networkError);
      
      const req = {
        headers: {
          authorization: 'Bearer network-token'
        }
      };
      const res = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      const next = jest.fn();
      
      await authenticateToken(req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(401);
    });

    test('should gracefully degrade when Cognito is unavailable', async () => {
      const { authenticateToken } = require('../../middleware/auth');
      
      // Simulate complete service unavailability
      mockVerifier.verify.mockImplementation(() => {
        throw new Error('Service unavailable');
      });
      
      const req = {
        headers: {
          authorization: 'Bearer service-down-token'
        }
      };
      const res = {
        status: jest.fn().mockReturnThis(),
        json: jest.fn()
      };
      const next = jest.fn();
      
      await authenticateToken(req, res, next);
      
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith(
        expect.objectContaining({
          error: expect.stringContaining('Invalid or expired token')
        })
      );
    });
  });

  describe('Configuration & Environment', () => {
    test('should handle missing Cognito configuration', () => {
      delete process.env.COGNITO_USER_POOL_ID;
      delete process.env.COGNITO_CLIENT_ID;
      
      delete require.cache[require.resolve('../../middleware/auth')];
      
      expect(() => {
        require('../../middleware/auth');
      }).not.toThrow();
    });

    test('should validate environment configuration on startup', () => {
      process.env.COGNITO_USER_POOL_ID = 'invalid-pool-id';
      process.env.COGNITO_CLIENT_ID = '';
      
      delete require.cache[require.resolve('../../middleware/auth')];
      
      // Should handle invalid configuration gracefully
      expect(() => {
        require('../../middleware/auth');
      }).not.toThrow();
    });

    test('should support different environments', () => {
      const environments = ['development', 'staging', 'production'];
      
      environments.forEach(env => {
        process.env.NODE_ENV = env;
        process.env.COGNITO_USER_POOL_ID = `${env}-pool`;
        
        delete require.cache[require.resolve('../../middleware/auth')];
        
        expect(() => {
          require('../../middleware/auth');
        }).not.toThrow();
      });
    });
  });
});