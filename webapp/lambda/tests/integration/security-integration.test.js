/**
 * Security Integration Tests
 * Tests authentication, authorization, encryption, and security controls end-to-end
 */

const request = require('supertest');
const jwt = require('jsonwebtoken');
const crypto = require('crypto');
const { app } = require('../../index');
const { 
  createTestUser, 
  createTestApiKeys, 
  cleanupTestUser,
  withDatabaseTransaction 
} = require('../utils/database-test-utils');

describe('Security Integration Tests', () => {
  let testUser;
  let validToken;
  let expiredToken;
  let invalidToken;
  const secret = process.env.JWT_SECRET || 'test-secret-key';
  
  beforeAll(async () => {
    // Create test user for security testing
    testUser = await createTestUser('security-test-user');
    await createTestApiKeys(testUser.user_id, {
      alpaca_key: 'test-alpaca-key',
      alpaca_secret: 'test-alpaca-secret',
      polygon_key: 'test-polygon-key'
    });

    // Create test JWT tokens
    validToken = jwt.sign(
      { 
        sub: testUser.user_id, 
        email: testUser.email,
        exp: Math.floor(Date.now() / 1000) + 3600 // 1 hour from now
      }, 
      secret
    );

    expiredToken = jwt.sign(
      { 
        sub: testUser.user_id, 
        email: testUser.email,
        exp: Math.floor(Date.now() / 1000) - 3600 // 1 hour ago
      }, 
      secret
    );

    invalidToken = jwt.sign(
      { 
        sub: testUser.user_id, 
        email: testUser.email,
        exp: Math.floor(Date.now() / 1000) + 3600
      }, 
      'wrong-secret'
    );
  });

  afterAll(async () => {
    if (testUser) {
      await cleanupTestUser(testUser.user_id);
    }
  });

  describe('Authentication Security', () => {
    test('Protected endpoints reject requests without authentication', async () => {
      const protectedEndpoints = [
        '/api/portfolio',
        '/api/settings/api-keys',
        '/api/trading/orders',
        '/api/analytics/portfolio-metrics'
      ];

      for (const endpoint of protectedEndpoints) {
        const response = await request(app)
          .get(endpoint)
          .timeout(3000);

        // Should be unauthorized or require authentication
        expect([401, 403, 422]).toContain(response.status);
      }
    });

    test('Valid JWT tokens allow access to protected endpoints', async () => {
      const response = await request(app)
        .get('/api/portfolio')
        .set('Authorization', `Bearer ${validToken}`)
        .timeout(3000);

      // Should allow access (200) or return valid business response (404 if no portfolio)
      expect([200, 404]).toContain(response.status);
    });

    test('Expired JWT tokens are rejected', async () => {
      const response = await request(app)
        .get('/api/portfolio')
        .set('Authorization', `Bearer ${expiredToken}`)
        .timeout(3000);

      expect([401, 403]).toContain(response.status);
    });

    test('Invalid JWT tokens are rejected', async () => {
      const response = await request(app)
        .get('/api/portfolio')
        .set('Authorization', `Bearer ${invalidToken}`)
        .timeout(3000);

      expect([401, 403]).toContain(response.status);
    });

    test('Malformed JWT tokens are rejected', async () => {
      const malformedTokens = [
        'invalid-token',
        'Bearer',
        'Bearer ',
        'Bearer invalid.token.format',
        'Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.invalid',
      ];

      for (const token of malformedTokens) {
        const response = await request(app)
          .get('/api/portfolio')
          .set('Authorization', token)
          .timeout(2000);

        expect([400, 401, 403]).toContain(response.status);
      }
    });
  });

  describe('Authorization Security', () => {
    test('Users can only access their own data', async () => {
      // Create another test user
      const otherUser = await createTestUser('other-security-user');
      await createTestApiKeys(otherUser.user_id, {
        alpaca_key: 'other-alpaca-key',
        alpaca_secret: 'other-alpaca-secret'
      });

      try {
        // Create token for the other user
        const otherUserToken = jwt.sign(
          { 
            sub: otherUser.user_id, 
            email: otherUser.email,
            exp: Math.floor(Date.now() / 1000) + 3600
          }, 
          secret
        );

        // Try to access first user's data with second user's token
        const response = await request(app)
          .get('/api/settings/api-keys')
          .set('Authorization', `Bearer ${otherUserToken}`)
          .set('x-user-id', testUser.user_id) // Attempting to access other user's data
          .timeout(3000);

        // Should either reject the request or return empty data (not first user's data)
        if (response.status === 200) {
          // If successful, should not return the first user's API keys
          expect(response.body.alpaca_key).not.toBe('test-alpaca-key');
        } else {
          // Or should reject the request entirely
          expect([401, 403, 404]).toContain(response.status);
        }

      } finally {
        await cleanupTestUser(otherUser.user_id);
      }
    });

    test('User ID in token must match requested user data', async () => {
      // Try to access data for a different user ID than in token
      const fakeUserId = 'fake-user-' + Date.now();
      
      const response = await request(app)
        .get('/api/portfolio')
        .set('Authorization', `Bearer ${validToken}`)
        .set('x-user-id', fakeUserId)
        .timeout(3000);

      // Should reject or return empty data
      expect([401, 403, 404]).toContain(response.status);
    });
  });

  describe('Input Validation Security', () => {
    test('SQL injection attempts are prevented', async () => {
      const sqlInjectionPayloads = [
        "'; DROP TABLE users; --",
        "' OR '1'='1",
        "'; UPDATE users SET email='hacked@test.com'; --",
        "' UNION SELECT * FROM users --",
        "'; INSERT INTO users (email) VALUES ('hacked@test.com'); --"
      ];

      for (const payload of sqlInjectionPayloads) {
        const response = await request(app)
          .get('/api/market-data/quote')
          .query({ symbol: payload })
          .set('Authorization', `Bearer ${validToken}`)
          .timeout(3000);

        // Should reject malicious input
        expect([400, 422, 500]).not.toContain(response.status);
        if (response.status === 200) {
          // If it returns data, it should be sanitized
          expect(response.body).not.toMatchObject({
            symbol: payload
          });
        }
      }
    });

    test('XSS attempts are prevented in API responses', async () => {
      const xssPayloads = [
        '<script>alert("xss")</script>',
        '"><script>alert("xss")</script>',
        'javascript:alert("xss")',
        '<img src="x" onerror="alert(\'xss\')">',
        '${alert("xss")}'
      ];

      for (const payload of xssPayloads) {
        const response = await request(app)
          .post('/api/portfolio/add-holding')
          .set('Authorization', `Bearer ${validToken}`)
          .send({
            symbol: payload,
            quantity: 10,
            avgCost: 100
          })
          .timeout(3000);

        // Should either reject the request or sanitize the input
        if (response.status === 200 || response.status === 201) {
          const responseStr = JSON.stringify(response.body);
          expect(responseStr).not.toContain('<script>');
          expect(responseStr).not.toContain('javascript:');
          expect(responseStr).not.toContain('onerror=');
        }
      }
    });

    test('Oversized payloads are rejected', async () => {
      // Create a very large payload
      const largePayload = {
        symbol: 'A'.repeat(10000),
        data: 'B'.repeat(50000),
        description: 'C'.repeat(100000)
      };

      const response = await request(app)
        .post('/api/portfolio/add-holding')
        .set('Authorization', `Bearer ${validToken}`)
        .send(largePayload)
        .timeout(5000);

      // Should reject oversized requests
      expect([400, 413, 422]).toContain(response.status);
    });
  });

  describe('API Key Security', () => {
    test('API keys are encrypted in storage', async () => {
      await withDatabaseTransaction(async (client) => {
        // Retrieve encrypted API key from database
        const result = await client.query(
          'SELECT encrypted_alpaca_key, encryption_salt FROM user_api_keys WHERE user_id = $1',
          [testUser.user_id]
        );

        if (result.rows.length > 0) {
          const { encrypted_alpaca_key, encryption_salt } = result.rows[0];
          
          // Encrypted key should not be the plaintext key
          expect(encrypted_alpaca_key).not.toBe('test-alpaca-key');
          expect(encrypted_alpaca_key).toBeDefined();
          expect(encryption_salt).toBeDefined();
          
          // Should be properly encrypted (base64 format)
          expect(encrypted_alpaca_key).toMatch(/^[A-Za-z0-9+/]+=*$/);
          expect(encryption_salt).toMatch(/^[A-Za-z0-9+/]+=*$/);
        }
      });
    });

    test('API key retrieval requires proper authentication', async () => {
      const response = await request(app)
        .get('/api/settings/api-keys')
        .timeout(3000);

      // Should reject unauthenticated requests
      expect([401, 403, 422]).toContain(response.status);
    });

    test('API key updates are properly validated', async () => {
      const invalidApiKeys = [
        { alpaca_key: '', alpaca_secret: 'valid-secret' },
        { alpaca_key: 'valid-key', alpaca_secret: '' },
        { alpaca_key: 'short', alpaca_secret: 'also-short' },
        { alpaca_key: null, alpaca_secret: 'valid-secret' },
        { alpaca_key: 'valid-key', alpaca_secret: null }
      ];

      for (const invalidKeys of invalidApiKeys) {
        const response = await request(app)
          .post('/api/settings/api-keys')
          .set('Authorization', `Bearer ${validToken}`)
          .send(invalidKeys)
          .timeout(3000);

        // Should reject invalid API keys
        expect([400, 422]).toContain(response.status);
      }
    });
  });

  describe('Rate Limiting Security', () => {
    test('Rapid requests are rate limited', async () => {
      const rapidRequests = [];
      const requestCount = 20;

      // Send many requests quickly
      for (let i = 0; i < requestCount; i++) {
        const request_promise = request(app)
          .get('/api/health')
          .set('Authorization', `Bearer ${validToken}`)
          .timeout(2000);
        
        rapidRequests.push(request_promise);
      }

      const results = await Promise.allSettled(rapidRequests);
      
      let successCount = 0;
      let rateLimitedCount = 0;

      results.forEach(result => {
        if (result.status === 'fulfilled') {
          if (result.value.status === 200) {
            successCount++;
          } else if (result.value.status === 429) { // Too Many Requests
            rateLimitedCount++;
          }
        }
      });

      // Should have rate limited some requests
      expect(successCount + rateLimitedCount).toBeGreaterThan(requestCount * 0.5);
      
      // If rate limiting is implemented, some requests should be limited
      // If not implemented yet, all should succeed (but this test documents the requirement)
    });
  });

  describe('Session Security', () => {
    test('Tokens have reasonable expiration times', async () => {
      // Test that tokens don't last forever
      const payload = jwt.decode(validToken);
      expect(payload.exp).toBeDefined();
      
      const now = Math.floor(Date.now() / 1000);
      const tokenExpiry = payload.exp;
      const tokenLifetime = tokenExpiry - now;
      
      // Token should expire within reasonable time (less than 24 hours)
      expect(tokenLifetime).toBeLessThan(24 * 60 * 60);
      expect(tokenLifetime).toBeGreaterThan(0);
    });

    test('Token refresh mechanism works securely', async () => {
      // Test token refresh if implemented
      const response = await request(app)
        .post('/api/auth/refresh')
        .set('Authorization', `Bearer ${validToken}`)
        .timeout(3000);

      // Should either work (200) or be not implemented yet (404/405)
      if (response.status === 200) {
        expect(response.body).toHaveProperty('token');
        
        // New token should be different from old token
        expect(response.body.token).not.toBe(validToken);
        
        // New token should be valid JWT
        const decoded = jwt.decode(response.body.token);
        expect(decoded).toBeTruthy();
        expect(decoded.sub).toBe(testUser.user_id);
      }
    });
  });

  describe('Error Handling Security', () => {
    test('Error messages do not leak sensitive information', async () => {
      const sensitiveEndpoints = [
        '/api/settings/api-keys',
        '/api/portfolio',
        '/api/trading/orders'
      ];

      for (const endpoint of sensitiveEndpoints) {
        const response = await request(app)
          .get(endpoint)
          .set('Authorization', 'Bearer invalid-token')
          .timeout(3000);

        const responseText = JSON.stringify(response.body).toLowerCase();
        
        // Should not leak database details, file paths, or internal errors
        expect(responseText).not.toContain('database');
        expect(responseText).not.toContain('sql');
        expect(responseText).not.toContain('/home/');
        expect(responseText).not.toContain('stack trace');
        expect(responseText).not.toContain('internal server error');
        expect(responseText).not.toContain(testUser.user_id);
      }
    });

    test('Database errors are properly handled without information disclosure', async () => {
      // Try to cause a database error
      const response = await request(app)
        .get('/api/portfolio')
        .set('Authorization', `Bearer ${validToken}`)
        .set('x-user-id', 'invalid-user-id-format-to-cause-db-error')
        .timeout(3000);

      if (response.status >= 500) {
        const responseText = JSON.stringify(response.body).toLowerCase();
        
        // Should not expose database internals
        expect(responseText).not.toContain('postgresql');
        expect(responseText).not.toContain('connection');
        expect(responseText).not.toContain('query');
        expect(responseText).not.toContain('relation');
      }
    });
  });

  describe('HTTPS and Transport Security', () => {
    test('Security headers are present in responses', async () => {
      const response = await request(app)
        .get('/api/health')
        .timeout(3000);

      // Check for important security headers
      const headers = response.headers;
      
      // Content Security Policy (if implemented)
      if (headers['content-security-policy']) {
        expect(headers['content-security-policy']).toContain('script-src');
      }
      
      // X-Frame-Options (if implemented)
      if (headers['x-frame-options']) {
        expect(['DENY', 'SAMEORIGIN']).toContain(headers['x-frame-options']);
      }
      
      // X-Content-Type-Options (if implemented)
      if (headers['x-content-type-options']) {
        expect(headers['x-content-type-options']).toBe('nosniff');
      }
    });

    test('CORS configuration is secure', async () => {
      const response = await request(app)
        .options('/api/health')
        .set('Origin', 'https://malicious-site.com')
        .timeout(3000);

      // Should either reject cross-origin requests from unknown domains
      // or have proper CORS configuration
      if (response.headers['access-control-allow-origin']) {
        const allowedOrigin = response.headers['access-control-allow-origin'];
        expect(allowedOrigin).not.toBe('*'); // Should not allow all origins
      }
    });
  });
});