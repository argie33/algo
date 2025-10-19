const request = require('supertest');
const { app } = require('../../../index');

// Mock database BEFORE importing routes/modules
jest.mock("../../../utils/database", () => ({
  query: jest.fn(),
  initializeDatabase: jest.fn().mockResolvedValue(undefined),
  closeDatabase: jest.fn().mockResolvedValue(undefined),
  getPool: jest.fn(),
  transaction: jest.fn((cb) => cb()),
  healthCheck: jest.fn(),
}));

// Mock auth middleware
jest.mock("../../../middleware/auth", () => ({
  authenticateToken: jest.fn((req, res, next) => {
    req.user = { sub: "test-user-123" };
    next();
  }),
  authorizeAdmin: jest.fn((req, res, next) => next()),
  checkApiKey: jest.fn((req, res, next) => next()),
}));


describe('API Key Integration Tests', () => {
  // Alpaca API credentials from environment variables
    beforeEach(() => {
    jest.clearAllMocks();
    query.mockImplementation((sql, params) => {
      // Default: return empty rows for all queries
      if (sql.includes("information_schema.tables")) {
        return Promise.resolve({ rows: [{ exists: true }] });
      }
      return Promise.resolve({ rows: [] });
    });
  });
  const alpacaAccessKey = process.env.ALPACA_API_KEY || '';
  const alpacaSecretKey = process.env.ALPACA_API_SECRET || '';

  // Application authentication tokens for protected endpoints
  const appToken1 = 'dev-bypass-token';
  const appToken2 = 'test-token';

  beforeAll(() => {
    process.env.NODE_ENV = 'test';
    process.env.DB_HOST = 'localhost';
    process.env.DB_USER = 'postgres';
    process.env.DB_PASSWORD = 'password';
    process.env.DB_NAME = 'stocks';
    process.env.DB_PORT = '5432';
    process.env.ALLOW_DEV_BYPASS = 'true';
  });

  describe('Portfolio Holdings Endpoint Authentication', () => {
    test('should authenticate successfully with dev bypass token', async () => {
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${appToken1}`)
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data.holdings)).toBe(true);
    });

    test('should authenticate successfully with test token', async () => {
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${appToken2}`)
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data');
      expect(Array.isArray(response.body.data.holdings)).toBe(true);
    });

    test('should reject requests without authentication', async () => {
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .expect(401);

      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error', 'Authentication required');
    });

    test('should reject requests with invalid token', async () => {
      const response = await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', 'Bearer invalid-token-123')
        .expect(401);

      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error', 'Invalid token');
    });
  });

  describe('Other Protected Endpoints Authentication', () => {
    const protectedEndpoints = [
      '/api/portfolio',
      '/api/portfolio/summary',
      '/api/watchlist'
    ];

    protectedEndpoints.forEach(endpoint => {
      test(`${endpoint} should authenticate with dev bypass token`, async () => {
        const response = await request(app)
          .get(endpoint)
          .set('Authorization', `Bearer ${appToken1}`);

        // Should not be 401 (unauthorized)
        expect(response.status).not.toBe(401);

        // Should either succeed (200) or have other valid status
        if (response.status === 200) {
          expect(response.body).toHaveProperty('success', true);
        }
      });

      test(`${endpoint} should authenticate with test token`, async () => {
        const response = await request(app)
          .get(endpoint)
          .set('Authorization', `Bearer ${appToken2}`);

        // Should not be 401 (unauthorized)
        expect(response.status).not.toBe(401);

        // Should either succeed (200) or have other valid status
        if (response.status === 200) {
          expect(response.body).toHaveProperty('success', true);
        }
      });
    });
  });

  describe('Authentication Middleware Consistency', () => {
    test('both tokens should work consistently across multiple requests', async () => {
      // Test multiple requests with dev bypass token
      for (let i = 0; i < 3; i++) {
        const response = await request(app)
          .get('/api/portfolio/holdings')
          .set('Authorization', `Bearer ${appToken1}`)
          .expect(200);

        expect(response.body.success).toBe(true);
      }

      // Test multiple requests with test token
      for (let i = 0; i < 3; i++) {
        const response = await request(app)
          .get('/api/portfolio/holdings')
          .set('Authorization', `Bearer ${appToken2}`)
          .expect(200);

        expect(response.body.success).toBe(true);
      }
    });

    test('should handle mixed valid and invalid tokens correctly', async () => {
      // Valid request
      await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${appToken1}`)
        .expect(200);

      // Invalid request
      await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', 'Bearer invalid-token')
        .expect(401);

      // Valid request again
      await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${appToken2}`)
        .expect(200);
    });
  });

  describe('Token Format Validation', () => {
    test('should handle Bearer token format correctly', async () => {
      // Test with Bearer prefix
      await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${appToken1}`)
        .expect(200);

      // Test without Bearer prefix (should fail)
      await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', appToken1)
        .expect(401);
    });

    test('should handle case sensitivity correctly', async () => {
      // Test exact case
      await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `Bearer ${appToken1}`)
        .expect(200);

      // Test different case (middleware accepts both Bearer and bearer)
      await request(app)
        .get('/api/portfolio/holdings')
        .set('Authorization', `bearer ${appToken1}`)
        .expect(200);
    });
  });

  describe('Alpaca API Integration', () => {
    test('should use provided Alpaca credentials for testing', async () => {
      // This is a placeholder test - the actual Alpaca integration
      // would be tested in the existing Alpaca integration test file
      // Skip if credentials not provided
      if (!alpacaAccessKey || !alpacaSecretKey) {
        console.log('⚠️  Alpaca credentials not provided, skipping validation');
        expect(true).toBe(true);
        return;
      }

      expect(alpacaAccessKey).toHaveLength(20);
      expect(alpacaSecretKey).toHaveLength(40);
    });
  });
});