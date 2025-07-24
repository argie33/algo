/**
 * API Key Functionality Integration Test
 * Tests the complete API key saving, retrieval, and validation workflow
 */

const request = require('supertest');
const express = require('express');
const { SimpleApiKeyService } = require('../../utils/simpleApiKeyService');

// Create test app with minimal setup
const app = express();
app.use(express.json());

// Mock authentication middleware
app.use((req, res, next) => {
  req.user = {
    sub: 'test-user-123',
    email: 'test@example.com',
    username: 'testuser'
  };
  next();
});

// Load the settings route
const settingsRoute = require('../../routes/settings');
app.use('/api/settings', settingsRoute);

describe('API Key Functionality Integration Tests', () => {
  const testUserId = 'test-user-123';
  const testProvider = 'alpaca';
  const testApiKey = 'PKTEST123456789012345678901234567890';
  const testSecret = 'test-secret-key-1234567890123456789012345678901234567890';

  beforeAll(async () => {
    // Clean up any existing test data
    try {
      const apiKeyService = new SimpleApiKeyService();
      await apiKeyService.deleteApiKey(testUserId, testProvider);
    } catch (error) {
      console.log('No existing test data to clean up');
    }
  });

  afterAll(async () => {
    // Clean up test data
    try {
      const apiKeyService = new SimpleApiKeyService();
      await apiKeyService.deleteApiKey(testUserId, testProvider);
    } catch (error) {
      console.log('Test cleanup completed');
    }
  });

  test('GET /api/settings/api-keys - should return empty list initially', async () => {
    const response = await request(app)
      .get('/api/settings/api-keys')
      .expect(200);

    expect(response.body.success).toBe(true);
    expect(Array.isArray(response.body.data)).toBe(true);
    expect(response.body.data.length).toBe(0);
  });

  test('POST /api/settings/api-keys - should save API key successfully', async () => {
    const response = await request(app)
      .post('/api/settings/api-keys')
      .send({
        provider: testProvider,
        apiKey: testApiKey,
        apiSecret: testSecret,
        isSandbox: true,
        description: 'Test API key'
      })
      .expect(200);

    expect(response.body.success).toBe(true);
    expect(response.body.message).toContain('API key added successfully');
    expect(response.body.apiKey.provider).toBe(testProvider);
    expect(response.body.apiKey.isSandbox).toBe(true);
  });

  test('GET /api/settings/api-keys - should return saved API key', async () => {
    const response = await request(app)
      .get('/api/settings/api-keys')
      .expect(200);

    expect(response.body.success).toBe(true);
    expect(Array.isArray(response.body.data)).toBe(true);
    expect(response.body.data.length).toBe(1);
    
    const apiKey = response.body.data[0];
    expect(apiKey.provider).toBe(testProvider);
    expect(apiKey.masked_api_key).toContain('***');
    expect(apiKey.is_active).toBe(true);
  });

  test('POST /api/settings/api-keys/:provider/validate - should validate saved API key', async () => {
    const response = await request(app)
      .post(`/api/settings/api-keys/${testProvider}/validate`)
      .expect(200);

    expect(response.body.success).toBe(true);
    expect(response.body.data.valid).toBe(true);
    expect(response.body.data.provider).toBe(testProvider);
    expect(response.body.data.hasApiKey).toBe(true);
    expect(response.body.data.hasSecret).toBe(true);
  });

  test('POST /api/settings/api-keys - should reject invalid provider', async () => {
    const response = await request(app)
      .post('/api/settings/api-keys')
      .send({
        provider: 'invalid-provider',
        apiKey: testApiKey,
        apiSecret: testSecret
      })
      .expect(400);

    expect(response.body.success).toBe(false);
    expect(response.body.error).toContain('Invalid provider');
  });

  test('POST /api/settings/api-keys - should reject short API key', async () => {
    const response = await request(app)
      .post('/api/settings/api-keys')
      .send({
        provider: testProvider,
        apiKey: 'short',
        apiSecret: testSecret
      })
      .expect(400);

    expect(response.body.success).toBe(false);
    expect(response.body.error).toContain('should be 20-50 characters');
  });

  test('POST /api/settings/api-keys - should reject missing required fields', async () => {
    const response = await request(app)
      .post('/api/settings/api-keys')
      .send({
        provider: testProvider
        // Missing apiKey and apiSecret
      })
      .expect(400);

    expect(response.body.success).toBe(false);
    expect(response.body.error).toContain('required');
  });

  test('DELETE /api/settings/api-keys/:provider - should delete API key', async () => {
    const response = await request(app)
      .delete(`/api/settings/api-keys/${testProvider}`)
      .expect(200);

    expect(response.body.success).toBe(true);
    expect(response.body.message).toContain('deleted successfully');
  });

  test('GET /api/settings/api-keys - should return empty list after deletion', async () => {
    const response = await request(app)
      .get('/api/settings/api-keys')
      .expect(200);

    expect(response.body.success).toBe(true);
    expect(Array.isArray(response.body.data)).toBe(true);
    expect(response.body.data.length).toBe(0);
  });

  test('POST /api/settings/api-keys/:provider/validate - should return false for non-existent key', async () => {
    const response = await request(app)
      .post(`/api/settings/api-keys/${testProvider}/validate`)
      .expect(200);

    expect(response.body.success).toBe(true);
    expect(response.body.data.valid).toBe(false);
    expect(response.body.data.error).toContain('not found');
  });
});