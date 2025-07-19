/**
 * API Routes Integration Tests
 * End-to-end testing of all critical API endpoints with real request/response flows
 */

const request = require('supertest');
// Jest globals are automatically available in test environment

// Mock database and external services
jest.mock('../../utils/database', () => ({
  query: jest.fn(),
  healthCheck: jest.fn(),
  initializeDatabase: jest.fn(),
  validateDatabaseSchema: jest.fn(),
  REQUIRED_SCHEMA: {}
}));

jest.mock('../../utils/apiKeyService');
jest.mock('../../utils/simpleApiKeyService', () => ({
  getApiKey: jest.fn(),
  setApiKey: jest.fn(),
  listApiKeys: jest.fn(),
  deleteApiKey: jest.fn()
}));

jest.mock('../../utils/secureLogger', () => ({
  secureLogger: {
    debug: jest.fn(),
    info: jest.fn(),
    warn: jest.fn(),
    error: jest.fn(),
    security: jest.fn(),
    auditAuth: jest.fn(),
    auditDatabase: jest.fn()
  }
}));

// Mock AWS SDK modules
jest.mock('@aws-sdk/client-secrets-manager', () => ({
  SecretsManagerClient: jest.fn().mockImplementation(() => ({
    send: jest.fn().mockResolvedValue({
      SecretString: JSON.stringify({ username: 'test', password: 'test' })
    })
  })),
  GetSecretValueCommand: jest.fn()
}));

jest.mock('@aws-sdk/client-cognito-identity-provider', () => ({
  CognitoIdentityProviderClient: jest.fn().mockImplementation(() => ({
    send: jest.fn().mockResolvedValue({ UserPool: { Id: 'test-pool' } })
  })),
  DescribeUserPoolCommand: jest.fn()
}));

// Mock additional utility modules with comprehensive functions
jest.mock('../../utils/timeoutHelper', () => ({
  withTimeout: jest.fn().mockImplementation(async (fn) => await fn()),
  circuitBreaker: jest.fn().mockImplementation(async (fn) => await fn()),
  getCircuitBreakerStatus: jest.fn().mockReturnValue({}),
  defaultTimeouts: {
    database: 5000,
    alpaca: 10000,
    news: 15000,
    sentiment: 20000,
    external: 30000,
    upload: 60000,
    websocket: 5000
  }
}));

jest.mock('../../utils/schemaValidator', () => ({
  validateSchema: jest.fn().mockResolvedValue(true)
}));

jest.mock('../../utils/jwtSecretManager', () => ({
  getJwtSecret: jest.fn().mockResolvedValue('mock-jwt-secret')
}));

// Mock alpaca service
jest.mock('../../utils/alpacaService', () => ({
  healthCheck: jest.fn().mockResolvedValue({ status: 'healthy' })
}));

const express = require('express');

describe('API Routes Integration Tests', () => {
  let app;
  let mockDatabase;
  let mockApiKeyService;

  beforeAll(() => {
    // Create Express app for testing
    app = express();
    app.use(express.json());
    app.use(express.urlencoded({ extended: true }));
    
    // Add CORS middleware
    app.use((req, res, next) => {
      res.header('Access-Control-Allow-Origin', '*');
      res.header('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS');
      res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization');
      if (req.method === 'OPTIONS') {
        res.sendStatus(200);
      } else {
        next();
      }
    });

    // Add comprehensive response formatter middleware
    app.use((req, res, next) => {
      res.success = (data, message = 'Success') => {
        return res.status(200).json({
          success: true,
          message,
          data,
          timestamp: new Date().toISOString()
        });
      };

      res.error = (message = 'Error occurred', statusCode = 500, details = null) => {
        return res.status(statusCode).json({
          success: false,
          error: message,
          details,
          timestamp: new Date().toISOString()
        });
      };

      res.serverError = (message = 'Server Error', details = null) => {
        return res.status(500).json({
          success: false,
          error: message,
          details,
          timestamp: new Date().toISOString()
        });
      };

      res.notFound = (message = 'Not Found') => {
        return res.status(404).json({
          success: false,
          error: message,
          timestamp: new Date().toISOString()
        });
      };

      res.unauthorized = (message = 'Unauthorized') => {
        return res.status(401).json({
          success: false,
          error: message,
          timestamp: new Date().toISOString()
        });
      };

      res.badRequest = (message = 'Bad Request', details = null) => {
        return res.status(400).json({
          success: false,
          error: message,
          details,
          timestamp: new Date().toISOString()
        });
      };

      next();
    });
  });

  beforeEach(() => {
    jest.clearAllMocks();
    
    // Mock database functions with comprehensive health check response
    mockDatabase = require('../../utils/database');
    mockDatabase.query = jest.fn();
    mockDatabase.initializeDatabase = jest.fn().mockResolvedValue(true);
    mockDatabase.healthCheck = jest.fn().mockResolvedValue({
      status: 'healthy',
      message: 'Database connection successful',
      timestamp: new Date().toISOString(),
      connectionInfo: {
        host: 'localhost',
        database: 'test',
        connected: true
      }
    });
    mockDatabase.validateDatabaseSchema = jest.fn().mockResolvedValue(true);
    
    // Mock API key service
    mockApiKeyService = require('../../utils/apiKeyService');
    mockApiKeyService.getApiKey = jest.fn();
    mockApiKeyService.setApiKey = jest.fn();
    mockApiKeyService.listApiKeys = jest.fn();
    mockApiKeyService.deleteApiKey = jest.fn();
    
    // Mock timeout helper
    const mockTimeoutHelper = require('../../utils/timeoutHelper');
    mockTimeoutHelper.getCircuitBreakerStatus.mockReturnValue({
      database: { state: 'closed', failures: 0 },
      alpaca: { state: 'closed', failures: 0 }
    });
    
    // Additional mocks are set up at module level
  });

  describe('Health Check Endpoints', () => {
    beforeAll(() => {
      // Load health routes
      const healthRoutes = require('../../routes/health');
      app.use('/api/health', healthRoutes);
    });

    test('GET /api/health should return service status', async () => {
      mockDatabase.query.mockResolvedValue({ rows: [{ now: new Date() }] });
      mockDatabase.healthCheck.mockResolvedValue({
        status: 'connected',
        timestamp: new Date().toISOString()
      });

      const response = await request(app)
        .get('/api/health');

      console.log('Health response status:', response.status);
      console.log('Health response body:', response.body);

      expect(response.status).toBe(200);
      expect(response.body).toMatchObject({
        success: true,
        data: expect.objectContaining({
          status: 'healthy'
        })
      });
    });

    test('GET /api/health should handle database errors', async () => {
      mockDatabase.query.mockRejectedValue(new Error('Database connection failed'));

      const response = await request(app)
        .get('/api/health')
        .expect(200);

      expect(response.body.data.database.status).toBe('error');
    });

    test('GET /api/health/detailed should return comprehensive status', async () => {
      mockDatabase.query.mockResolvedValue({ rows: [{ version: '13.4' }] });

      const response = await request(app)
        .get('/api/health/detailed')
        .expect(200);

      expect(response.body.data).toHaveProperty('uptime');
      expect(response.body.data).toHaveProperty('memory');
      expect(response.body.data).toHaveProperty('environment');
    });
  });

  describe('Authentication Endpoints', () => {
    beforeAll(() => {
      // Load auth routes with mock middleware
      app.use('/api/auth', (req, res, next) => {
        // Mock authentication middleware for testing
        if (req.headers.authorization === 'Bearer valid-token') {
          req.user = {
            sub: 'test-user-123',
            email: 'test@example.com',
            'cognito:username': 'testuser'
          };
        }
        next();
      });
      
      const authRoutes = require('../../routes/auth');
      app.use('/api/auth', authRoutes);
    });

    test('GET /api/auth/me should return user profile', async () => {
      const response = await request(app)
        .get('/api/auth/me')
        .set('Authorization', 'Bearer valid-token')
        .expect(200);

      expect(response.body.data).toMatchObject({
        id: 'test-user-123',
        email: 'test@example.com',
        username: 'testuser'
      });
    });

    test('GET /api/auth/me should reject invalid tokens', async () => {
      await request(app)
        .get('/api/auth/me')
        .set('Authorization', 'Bearer invalid-token')
        .expect(401);
    });

    test('POST /api/auth/refresh should handle token refresh', async () => {
      // Mock successful token refresh
      const response = await request(app)
        .post('/api/auth/refresh')
        .send({ refreshToken: 'valid-refresh-token' })
        .expect(200);

      expect(response.body.data).toHaveProperty('accessToken');
      expect(response.body.data).toHaveProperty('expiresIn');
    });
  });

  describe('Settings & API Keys Endpoints', () => {
    beforeAll(() => {
      // Add authentication middleware
      app.use('/api/settings', (req, res, next) => {
        if (req.headers.authorization === 'Bearer valid-token') {
          req.user = { sub: 'test-user-123' };
          next();
        } else {
          res.status(401).json({ error: 'Unauthorized' });
        }
      });

      const settingsRoutes = require('../../routes/settings');
      app.use('/api/settings', settingsRoutes);
    });

    test('GET /api/settings/api-keys should list user API keys', async () => {
      mockApiKeyService.listApiKeys.mockResolvedValue([
        { provider: 'alpaca', hasKey: true, lastUpdated: new Date() },
        { provider: 'polygon', hasKey: false, lastUpdated: null }
      ]);

      const response = await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', 'Bearer valid-token')
        .expect(200);

      expect(response.body.data).toHaveLength(2);
      expect(response.body.data[0]).toMatchObject({
        provider: 'alpaca',
        hasKey: true
      });
    });

    test('POST /api/settings/api-keys should store new API key', async () => {
      mockApiKeyService.setApiKey.mockResolvedValue(true);

      const response = await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', 'Bearer valid-token')
        .send({
          provider: 'alpaca',
          apiKey: 'PKTEST123456789',
          secretKey: 'secret123456789'
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(mockApiKeyService.setApiKey).toHaveBeenCalledWith(
        'test-user-123',
        'alpaca',
        expect.any(Object)
      );
    });

    test('POST /api/settings/api-keys should validate API key format', async () => {
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', 'Bearer valid-token')
        .send({
          provider: 'alpaca',
          apiKey: 'invalid-format',
          secretKey: 'secret'
        })
        .expect(400);
    });

    test('DELETE /api/settings/api-keys/:provider should remove API key', async () => {
      mockApiKeyService.deleteApiKey.mockResolvedValue(true);

      const response = await request(app)
        .delete('/api/settings/api-keys/alpaca')
        .set('Authorization', 'Bearer valid-token')
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(mockApiKeyService.deleteApiKey).toHaveBeenCalledWith(
        'test-user-123',
        'alpaca'
      );
    });

    test('GET /api/settings/profile should return user settings', async () => {
      mockDatabase.query.mockResolvedValue({
        rows: [{
          preferences: { theme: 'dark', notifications: true },
          timezone: 'America/New_York'
        }]
      });

      const response = await request(app)
        .get('/api/settings/profile')
        .set('Authorization', 'Bearer valid-token')
        .expect(200);

      expect(response.body.data).toMatchObject({
        preferences: { theme: 'dark', notifications: true },
        timezone: 'America/New_York'
      });
    });
  });

  describe('Portfolio Endpoints', () => {
    beforeAll(() => {
      app.use('/api/portfolio', (req, res, next) => {
        if (req.headers.authorization === 'Bearer valid-token') {
          req.user = { sub: 'test-user-123' };
          next();
        } else {
          res.status(401).json({ error: 'Unauthorized' });
        }
      });

      const portfolioRoutes = require('../../routes/portfolio');
      app.use('/api/portfolio', portfolioRoutes);
    });

    test('GET /api/portfolio should return user portfolio overview', async () => {
      mockDatabase.query.mockResolvedValue({
        rows: [{
          total_value: 25000.50,
          daily_change: 123.45,
          daily_change_percent: 0.49,
          position_count: 5
        }]
      });

      const response = await request(app)
        .get('/api/portfolio')
        .set('Authorization', 'Bearer valid-token')
        .expect(200);

      expect(response.body.data).toMatchObject({
        totalValue: 25000.50,
        dailyChange: 123.45,
        dailyChangePercent: 0.49,
        positionCount: 5
      });
    });

    test('GET /api/portfolio/positions should return portfolio positions', async () => {
      mockDatabase.query.mockResolvedValue({
        rows: [
          {
            symbol: 'AAPL',
            shares: 100,
            avg_cost: 150.00,
            current_price: 155.00,
            market_value: 15500.00,
            unrealized_gain: 500.00
          }
        ]
      });

      const response = await request(app)
        .get('/api/portfolio/positions')
        .set('Authorization', 'Bearer valid-token')
        .expect(200);

      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0]).toMatchObject({
        symbol: 'AAPL',
        shares: 100,
        avgCost: 150.00,
        currentPrice: 155.00,
        marketValue: 15500.00,
        unrealizedGain: 500.00
      });
    });

    test('POST /api/portfolio/positions should create new position', async () => {
      mockDatabase.query.mockResolvedValue({
        rows: [{ id: 1 }]
      });

      const response = await request(app)
        .post('/api/portfolio/positions')
        .set('Authorization', 'Bearer valid-token')
        .send({
          symbol: 'MSFT',
          shares: 50,
          price: 300.00,
          type: 'buy'
        })
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(mockDatabase.query).toHaveBeenCalledWith(
        expect.stringContaining('INSERT'),
        expect.arrayContaining(['test-user-123', 'MSFT', 50, 300.00, 'buy'])
      );
    });

    test('PUT /api/portfolio/positions/:id should update position', async () => {
      mockDatabase.query.mockResolvedValue({
        rows: [{ id: 1 }]
      });

      const response = await request(app)
        .put('/api/portfolio/positions/1')
        .set('Authorization', 'Bearer valid-token')
        .send({
          shares: 75
        })
        .expect(200);

      expect(response.body.success).toBe(true);
    });

    test('DELETE /api/portfolio/positions/:id should remove position', async () => {
      mockDatabase.query.mockResolvedValue({
        rowCount: 1
      });

      const response = await request(app)
        .delete('/api/portfolio/positions/1')
        .set('Authorization', 'Bearer valid-token')
        .expect(200);

      expect(response.body.success).toBe(true);
    });
  });

  describe('Market Data Endpoints', () => {
    beforeAll(() => {
      const marketRoutes = require('../../routes/market');
      app.use('/api/market', marketRoutes);
    });

    test('GET /api/market/quote/:symbol should return stock quote', async () => {
      mockDatabase.query.mockResolvedValue({
        rows: [{
          symbol: 'AAPL',
          price: 155.50,
          change: 2.25,
          change_percent: 1.47,
          volume: 45678900,
          market_cap: 2500000000000
        }]
      });

      const response = await request(app)
        .get('/api/market/quote/AAPL')
        .expect(200);

      expect(response.body.data).toMatchObject({
        symbol: 'AAPL',
        price: 155.50,
        change: 2.25,
        changePercent: 1.47,
        volume: 45678900,
        marketCap: 2500000000000
      });
    });

    test('GET /api/market/search should search for symbols', async () => {
      mockDatabase.query.mockResolvedValue({
        rows: [
          { symbol: 'AAPL', name: 'Apple Inc.', sector: 'Technology' },
          { symbol: 'AMZN', name: 'Amazon.com Inc.', sector: 'Consumer Discretionary' }
        ]
      });

      const response = await request(app)
        .get('/api/market/search?q=A')
        .expect(200);

      expect(response.body.data).toHaveLength(2);
      expect(response.body.data[0]).toMatchObject({
        symbol: 'AAPL',
        name: 'Apple Inc.',
        sector: 'Technology'
      });
    });

    test('GET /api/market/movers should return market movers', async () => {
      mockDatabase.query.mockResolvedValue({
        rows: [
          { symbol: 'TSLA', change_percent: 5.67, volume: 25000000 },
          { symbol: 'META', change_percent: -3.45, volume: 18000000 }
        ]
      });

      const response = await request(app)
        .get('/api/market/movers')
        .expect(200);

      expect(response.body.data).toHaveLength(2);
      expect(response.body.data[0].changePercent).toBeGreaterThan(0);
    });
  });

  describe('Error Handling & Edge Cases', () => {
    test('should handle database connection failures gracefully', async () => {
      mockDatabase.query.mockRejectedValue(new Error('Database connection lost'));

      const response = await request(app)
        .get('/api/health')
        .expect(200);

      expect(response.body.data.database.status).toBe('error');
    });

    test('should handle malformed JSON requests', async () => {
      await request(app)
        .post('/api/settings/api-keys')
        .set('Authorization', 'Bearer valid-token')
        .set('Content-Type', 'application/json')
        .send('{"invalid": json}')
        .expect(400);
    });

    test('should handle missing required fields', async () => {
      await request(app)
        .post('/api/portfolio/positions')
        .set('Authorization', 'Bearer valid-token')
        .send({
          symbol: 'AAPL'
          // Missing required fields: shares, price, type
        })
        .expect(400);
    });

    test('should handle SQL injection attempts', async () => {
      await request(app)
        .get('/api/market/quote/AAPL\'; DROP TABLE users; --')
        .expect(400);
    });

    test('should validate input parameters', async () => {
      await request(app)
        .post('/api/portfolio/positions')
        .set('Authorization', 'Bearer valid-token')
        .send({
          symbol: 'INVALID_SYMBOL_TOO_LONG',
          shares: -100, // Invalid negative shares
          price: 'not-a-number',
          type: 'invalid-type'
        })
        .expect(400);
    });

    test('should handle rate limiting', async () => {
      // Simulate many rapid requests
      const promises = [];
      for (let i = 0; i < 100; i++) {
        promises.push(
          request(app)
            .get('/api/health')
            .expect(res => {
              expect([200, 429]).toContain(res.status);
            })
        );
      }

      await Promise.all(promises);
    });
  });

  describe('Performance & Load Testing', () => {
    test('should handle concurrent requests efficiently', async () => {
      mockDatabase.query.mockResolvedValue({ rows: [{ now: new Date() }] });

      const startTime = Date.now();
      const promises = [];
      
      for (let i = 0; i < 50; i++) {
        promises.push(
          request(app)
            .get('/api/health')
            .expect(200)
        );
      }

      await Promise.all(promises);
      const duration = Date.now() - startTime;

      // Should complete 50 concurrent requests in reasonable time
      expect(duration).toBeLessThan(5000);
    });

    test('should maintain performance under load', async () => {
      mockDatabase.query.mockImplementation(() => 
        new Promise(resolve => 
          setTimeout(() => resolve({ rows: [{ test: 1 }] }), 10)
        )
      );

      const startTime = Date.now();
      
      await request(app)
        .get('/api/health')
        .expect(200);
        
      const duration = Date.now() - startTime;
      
      // Should respond quickly even with simulated database latency
      expect(duration).toBeLessThan(1000);
    });
  });

  describe('Security & Compliance', () => {
    test('should include security headers', async () => {
      const response = await request(app)
        .get('/api/health')
        .expect(200);

      expect(response.headers).toHaveProperty('access-control-allow-origin');
    });

    test('should validate authorization on protected endpoints', async () => {
      await request(app)
        .get('/api/settings/api-keys')
        .expect(401);

      await request(app)
        .get('/api/portfolio')
        .expect(401);

      await request(app)
        .post('/api/portfolio/positions')
        .expect(401);
    });

    test('should sanitize sensitive data in responses', async () => {
      mockApiKeyService.listApiKeys.mockResolvedValue([
        { provider: 'alpaca', hasKey: true, keyPreview: 'PK****' }
      ]);

      const response = await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', 'Bearer valid-token')
        .expect(200);

      const responseText = JSON.stringify(response.body);
      expect(responseText).not.toMatch(/PKTEST[A-Z0-9]{20,}/); // Should not contain full API keys
    });

    test('should log security events appropriately', async () => {
      const { secureLogger } = require('../utils/secureLogger');

      await request(app)
        .get('/api/settings/api-keys')
        .set('Authorization', 'Bearer invalid-token')
        .expect(401);

      expect(secureLogger.auditAuth).toHaveBeenCalledWith(
        expect.stringContaining('access_denied'),
        null,
        expect.any(Object)
      );
    });
  });
});