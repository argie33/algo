/**
 * Integration Tests for User API Endpoints
 * Tests real API endpoints with actual AWS services
 * Following TDD principles with comprehensive coverage
 */

const request = require('supertest');
const AWS = require('aws-sdk');
const jwt = require('jsonwebtoken');

describe('User API Endpoints - Integration Tests', () => {
  let testServer;
  let testUserId;
  let validToken;
  let validHeader;

  beforeAll(async () => {
    // Initialize test server
    const { app } = require('../../index');
    testServer = app;

    // Create test user and valid JWT token
    testUserId = 'test-user-' + Date.now();
    validToken = jwt.sign(
      {
        sub: testUserId,
        email: 'test@example.com',
        'cognito:username': 'testuser',
        exp: Math.floor(Date.now() / 1000) + (60 * 60), // 1 hour
        iat: Math.floor(Date.now() / 1000)
      },
      'test-secret'
    );
    validHeader = { 'Authorization': `Bearer ${validToken}` };

    // Ensure test database is clean
    await cleanupTestData();
  });

  afterAll(async () => {
    // Clean up test data
    await cleanupTestData();
  });

  afterEach(async () => {
    // Clean up after each test to prevent interference
    await cleanupTestUserData();
  });

  const cleanupTestData = async () => {
    try {
      const dbManager = require('../../utils/databaseConnectionManager');
      
      // Clean up test user data
      await dbManager.query(
        'DELETE FROM user_api_keys WHERE user_id LIKE $1',
        ['test-user-%']
      );
      await dbManager.query(
        'DELETE FROM user_notification_preferences WHERE user_id LIKE $1',
        ['test-user-%']
      );
      await dbManager.query(
        'DELETE FROM user_theme_preferences WHERE user_id LIKE $1',
        ['test-user-%']
      );
      await dbManager.query(
        'DELETE FROM user_profiles WHERE user_id LIKE $1',
        ['test-user-%']
      );
    } catch (error) {
      console.log('Cleanup error (expected in test environment):', error.message);
    }
  };

  const cleanupTestUserData = async () => {
    try {
      const dbManager = require('../../utils/databaseConnectionManager');
      
      await dbManager.query(
        'DELETE FROM user_api_keys WHERE user_id = $1',
        [testUserId]
      );
      await dbManager.query(
        'DELETE FROM user_notification_preferences WHERE user_id = $1',
        [testUserId]
      );
      await dbManager.query(
        'DELETE FROM user_theme_preferences WHERE user_id = $1',
        [testUserId]
      );
      await dbManager.query(
        'DELETE FROM user_profiles WHERE user_id = $1',
        [testUserId]
      );
    } catch (error) {
      console.log('User cleanup error (expected):', error.message);
    }
  };

  describe('Real Database Integration', () => {
    it('should connect to real AWS RDS database', async () => {
      const response = await request(testServer)
        .get('/api/health')
        .expect(200);

      expect(response.body.database).toBeDefined();
      expect(response.body.database.healthy).toBe(true);
    });

    it('should handle database connection timeouts gracefully', async () => {
      // Test with a very large result set that might timeout
      const response = await request(testServer)
        .get('/api/user/profile')
        .set(validHeader)
        .timeout(15000);

      // Should either succeed or fail gracefully with 503
      expect([200, 503]).toContain(response.status);
    });
  });

  describe('User Profile Integration', () => {
    it('should create and retrieve user profile in real database', async () => {
      // First, create a profile
      const profileData = {
        firstName: 'John',
        lastName: 'Doe',
        email: 'john.doe@test.com',
        phone: '+1234567890',
        timezone: 'America/New_York',
        currency: 'USD'
      };

      const createResponse = await request(testServer)
        .put('/api/user/profile')
        .set(validHeader)
        .send(profileData)
        .expect(200);

      expect(createResponse.body.success).toBe(true);

      // Then retrieve it
      const getResponse = await request(testServer)
        .get('/api/user/profile')
        .set(validHeader)
        .expect(200);

      expect(getResponse.body.data).toMatchObject(profileData);
    });

    it('should update existing profile without creating duplicates', async () => {
      const initialProfile = {
        firstName: 'Jane',
        lastName: 'Smith',
        email: 'jane@test.com',
        timezone: 'America/Los_Angeles',
        currency: 'USD'
      };

      // Create initial profile
      await request(testServer)
        .put('/api/user/profile')
        .set(validHeader)
        .send(initialProfile)
        .expect(200);

      // Update profile
      const updatedProfile = {
        ...initialProfile,
        firstName: 'Janet',
        timezone: 'Europe/London'
      };

      const updateResponse = await request(testServer)
        .put('/api/user/profile')
        .set(validHeader)
        .send(updatedProfile)
        .expect(200);

      expect(updateResponse.body.data.firstName).toBe('Janet');
      expect(updateResponse.body.data.timezone).toBe('Europe/London');

      // Verify only one record exists
      const dbManager = require('../../utils/databaseConnectionManager');
      const result = await dbManager.query(
        'SELECT COUNT(*) as count FROM user_profiles WHERE user_id = $1',
        [testUserId]
      );
      expect(parseInt(result.rows[0].count)).toBe(1);
    });
  });

  describe('Notification Preferences Integration', () => {
    it('should persist notification preferences to real database', async () => {
      const preferences = {
        email: true,
        push: false,
        priceAlerts: true,
        portfolioUpdates: false,
        marketNews: true,
        weeklyReports: false
      };

      const response = await request(testServer)
        .put('/api/user/notifications')
        .set(validHeader)
        .send(preferences)
        .expect(200);

      expect(response.body.success).toBe(true);

      // Verify data in database
      const dbManager = require('../../utils/databaseConnectionManager');
      const result = await dbManager.query(
        'SELECT * FROM user_notification_preferences WHERE user_id = $1',
        [testUserId]
      );

      expect(result.rows.length).toBe(1);
      expect(result.rows[0].email_notifications).toBe(preferences.email);
      expect(result.rows[0].push_notifications).toBe(preferences.push);
    });

    it('should return default preferences when none exist', async () => {
      const response = await request(testServer)
        .get('/api/user/notifications')
        .set(validHeader)
        .expect(200);

      expect(response.body.data).toMatchObject({
        email: true,
        push: true,
        priceAlerts: true,
        portfolioUpdates: true,
        marketNews: false,
        weeklyReports: true
      });
    });
  });

  describe('Theme Preferences Integration', () => {
    it('should persist theme preferences to real database', async () => {
      const themeData = {
        darkMode: true,
        primaryColor: '#2196f3',
        chartStyle: 'line',
        layout: 'compact'
      };

      const response = await request(testServer)
        .put('/api/user/theme')
        .set(validHeader)
        .send(themeData)
        .expect(200);

      expect(response.body.success).toBe(true);

      // Verify data in database
      const dbManager = require('../../utils/databaseConnectionManager');
      const result = await dbManager.query(
        'SELECT * FROM user_theme_preferences WHERE user_id = $1',
        [testUserId]
      );

      expect(result.rows.length).toBe(1);
      expect(result.rows[0].dark_mode).toBe(themeData.darkMode);
      expect(result.rows[0].primary_color).toBe(themeData.primaryColor);
    });
  });

  describe('API Keys Integration', () => {
    it('should securely store and retrieve API keys', async () => {
      const apiKeyData = {
        brokerName: 'alpaca',
        apiKey: 'test-api-key-12345',
        apiSecret: 'test-secret-67890',
        sandbox: true
      };

      // Store API key
      const storeResponse = await request(testServer)
        .post('/api/portfolio/api-keys')
        .set(validHeader)
        .send(apiKeyData)
        .expect(200);

      expect(storeResponse.body.success).toBe(true);

      // Retrieve API keys
      const getResponse = await request(testServer)
        .get('/api/portfolio/api-keys')
        .set(validHeader)
        .expect(200);

      expect(getResponse.body.apiKeys).toBeDefined();
      expect(getResponse.body.apiKeys.length).toBeGreaterThan(0);

      const storedKey = getResponse.body.apiKeys.find(k => k.provider === 'alpaca');
      expect(storedKey).toBeDefined();
      expect(storedKey.masked_api_key).toMatch(/\*{3,}/); // Should be masked
      expect(storedKey.api_key_encrypted).toBeUndefined(); // Should not expose encrypted value
    });

    it('should validate API key provider', async () => {
      const invalidApiKeyData = {
        brokerName: 'unsupported-broker',
        apiKey: 'test-key',
        apiSecret: 'test-secret',
        sandbox: true
      };

      const response = await request(testServer)
        .post('/api/portfolio/api-keys')
        .set(validHeader)
        .send(invalidApiKeyData)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('broker');
    });

    it('should delete API keys successfully', async () => {
      // First create an API key
      const apiKeyData = {
        brokerName: 'alpaca',
        apiKey: 'test-delete-key',
        apiSecret: 'test-delete-secret',
        sandbox: true
      };

      await request(testServer)
        .post('/api/portfolio/api-keys')
        .set(validHeader)
        .send(apiKeyData)
        .expect(200);

      // Then delete it
      const deleteResponse = await request(testServer)
        .delete('/api/portfolio/api-keys/alpaca')
        .set(validHeader)
        .expect(200);

      expect(deleteResponse.body.success).toBe(true);

      // Verify it's deleted
      const getResponse = await request(testServer)
        .get('/api/portfolio/api-keys')
        .set(validHeader)
        .expect(200);

      const deletedKey = getResponse.body.apiKeys.find(k => k.provider === 'alpaca');
      expect(deletedKey).toBeUndefined();
    });

    it('should handle API key encryption/decryption', async () => {
      const apiKeyData = {
        brokerName: 'alpaca',
        apiKey: 'test-encryption-key',
        apiSecret: 'test-encryption-secret',
        sandbox: true
      };

      const response = await request(testServer)
        .post('/api/portfolio/api-keys')
        .set(validHeader)
        .send(apiKeyData)
        .expect(200);

      // Verify the data is encrypted in the database
      const dbManager = require('../../utils/databaseConnectionManager');
      const result = await dbManager.query(
        'SELECT api_key_encrypted FROM user_api_keys WHERE user_id = $1 AND provider = $2',
        [testUserId, 'alpaca']
      );

      expect(result.rows.length).toBe(1);
      // Encrypted value should be different from original
      expect(result.rows[0].api_key_encrypted).not.toBe(apiKeyData.apiKey);
      expect(result.rows[0].api_key_encrypted).toBeDefined();
    });
  });

  describe('Authentication Integration', () => {
    it('should integrate with AWS Cognito JWT validation', async () => {
      // Test with a properly formatted JWT token (even if not real Cognito)
      const realFormatToken = jwt.sign(
        {
          sub: 'cognito-test-user',
          'cognito:username': 'testuser',
          email: 'test@example.com',
          token_use: 'access',
          scope: 'aws.cognito.signin.user.admin',
          auth_time: Math.floor(Date.now() / 1000),
          iss: 'https://cognito-idp.us-east-1.amazonaws.com/us-east-1_test',
          exp: Math.floor(Date.now() / 1000) + 3600,
          iat: Math.floor(Date.now() / 1000),
          client_id: 'test-client-id'
        },
        'test-secret'
      );

      const response = await request(testServer)
        .get('/api/user/profile')
        .set('Authorization', `Bearer ${realFormatToken}`)
        .expect(200);

      expect(response.body.success).toBe(true);
    });

    it('should reject expired tokens', async () => {
      const expiredToken = jwt.sign(
        {
          sub: 'test-user',
          exp: Math.floor(Date.now() / 1000) - 3600, // Expired 1 hour ago
          iat: Math.floor(Date.now() / 1000) - 7200  // Issued 2 hours ago
        },
        'test-secret'
      );

      const response = await request(testServer)
        .get('/api/user/profile')
        .set('Authorization', `Bearer ${expiredToken}`)
        .expect(401);

      expect(response.body.success).toBe(false);
    });

    it('should reject malformed tokens', async () => {
      const response = await request(testServer)
        .get('/api/user/profile')
        .set('Authorization', 'Bearer invalid.token.format')
        .expect(401);

      expect(response.body.success).toBe(false);
    });
  });

  describe('Error Handling and Resilience', () => {
    it('should handle database connection failures gracefully', async () => {
      // Simulate database connection issue by using invalid connection
      const originalEnv = process.env.DB_ENDPOINT;
      process.env.DB_ENDPOINT = 'invalid-endpoint.amazonaws.com';

      const response = await request(testServer)
        .get('/api/user/profile')
        .set(validHeader);

      // Should return service unavailable or use fallback behavior
      expect([200, 503]).toContain(response.status);

      // Restore original environment
      process.env.DB_ENDPOINT = originalEnv;
    });

    it('should handle high concurrent load', async () => {
      const concurrentRequests = 50;
      const promises = Array.from({ length: concurrentRequests }, (_, index) => {
        const userToken = jwt.sign(
          {
            sub: `concurrent-user-${index}`,
            email: `user${index}@test.com`,
            exp: Math.floor(Date.now() / 1000) + 3600,
            iat: Math.floor(Date.now() / 1000)
          },
          'test-secret'
        );

        return request(testServer)
          .get('/api/user/profile')
          .set('Authorization', `Bearer ${userToken}`)
          .timeout(10000);
      });

      const responses = await Promise.allSettled(promises);
      
      // At least 80% should succeed
      const successful = responses.filter(r => 
        r.status === 'fulfilled' && r.value.status < 500
      ).length;
      
      expect(successful / concurrentRequests).toBeGreaterThan(0.8);
    });

    it('should implement circuit breaker for failing services', async () => {
      // Make repeated requests to trigger circuit breaker if implemented
      const failurePromises = Array.from({ length: 10 }, () =>
        request(testServer)
          .get('/api/user/invalid-endpoint')
          .set(validHeader)
      );

      const responses = await Promise.allSettled(failurePromises);
      
      // Should get consistent error responses, not random failures
      const statusCodes = responses
        .filter(r => r.status === 'fulfilled')
        .map(r => r.value.status);
      
      expect(new Set(statusCodes).size).toBeLessThanOrEqual(2); // Should be consistent
    });
  });

  describe('Security Integration', () => {
    it('should prevent SQL injection in real database', async () => {
      const maliciousProfile = {
        firstName: "'; DROP TABLE user_profiles; --",
        lastName: 'Test',
        email: 'test@example.com'
      };

      const response = await request(testServer)
        .put('/api/user/profile')
        .set(validHeader)
        .send(maliciousProfile)
        .expect(400);

      expect(response.body.success).toBe(false);

      // Verify table still exists by making a normal request
      const normalResponse = await request(testServer)
        .get('/api/user/profile')
        .set(validHeader)
        .expect(200);

      expect(normalResponse.body.success).toBe(true);
    });

    it('should sanitize XSS attempts', async () => {
      const xssProfile = {
        firstName: '<script>alert("xss")</script>',
        lastName: '<img src="x" onerror="alert(1)">',
        email: 'test@example.com'
      };

      const response = await request(testServer)
        .put('/api/user/profile')
        .set(validHeader)
        .send(xssProfile)
        .expect(400);

      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain('Invalid');
    });

    it('should rate limit API requests', async () => {
      const rapidRequests = Array.from({ length: 100 }, () =>
        request(testServer)
          .get('/api/user/profile')
          .set(validHeader)
      );

      const responses = await Promise.allSettled(rapidRequests);
      const rateLimited = responses.some(r => 
        r.status === 'fulfilled' && r.value.status === 429
      );

      expect(rateLimited).toBe(true);
    });
  });

  describe('Performance Integration', () => {
    it('should meet response time requirements', async () => {
      const startTime = Date.now();
      
      const response = await request(testServer)
        .get('/api/user/profile')
        .set(validHeader)
        .expect(200);
      
      const responseTime = Date.now() - startTime;
      expect(responseTime).toBeLessThan(3000); // Should respond within 3 seconds
    });

    it('should handle large data sets efficiently', async () => {
      // Create multiple API keys to test list performance
      const createPromises = Array.from({ length: 5 }, (_, index) => 
        request(testServer)
          .post('/api/portfolio/api-keys')
          .set(validHeader)
          .send({
            brokerName: `test-broker-${index}`,
            apiKey: `test-key-${index}`,
            apiSecret: `test-secret-${index}`,
            sandbox: true
          })
      );

      await Promise.all(createPromises);

      const startTime = Date.now();
      const response = await request(testServer)
        .get('/api/portfolio/api-keys')
        .set(validHeader)
        .expect(200);
      
      const responseTime = Date.now() - startTime;
      expect(responseTime).toBeLessThan(2000); // Should handle list efficiently
      expect(response.body.apiKeys.length).toBeGreaterThanOrEqual(5);
    });
  });

  describe('Data Consistency', () => {
    it('should maintain data consistency across transactions', async () => {
      const profileData = {
        firstName: 'Consistency',
        lastName: 'Test',
        email: 'consistency@test.com',
        timezone: 'UTC',
        currency: 'USD'
      };

      // Create profile and preferences in sequence
      await request(testServer)
        .put('/api/user/profile')
        .set(validHeader)
        .send(profileData)
        .expect(200);

      await request(testServer)
        .put('/api/user/notifications')
        .set(validHeader)
        .send({ email: true, push: false })
        .expect(200);

      // Verify both are consistent
      const profileResponse = await request(testServer)
        .get('/api/user/profile')
        .set(validHeader)
        .expect(200);

      const notificationResponse = await request(testServer)
        .get('/api/user/notifications')
        .set(validHeader)
        .expect(200);

      expect(profileResponse.body.data.email).toBe(profileData.email);
      expect(notificationResponse.body.data.email).toBe(true);
    });
  });
});