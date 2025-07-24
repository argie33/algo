/**
 * Frontend-Backend API Communication Test
 * Validates that the API endpoints called by the frontend are correctly implemented
 */

const request = require('supertest');
const express = require('express');

// Create minimal test app
const app = express();
app.use(express.json());

// Mock the auth middleware before loading routes
jest.mock('../../middleware/auth', () => ({
  authenticateToken: (req, res, next) => {
    req.user = {
      sub: 'test-user-123',
      email: 'test@example.com',
      username: 'testuser'
    };
    next();
  }
}));

// Load routes after mocking auth
const settingsRoute = require('../../routes/settings');
const portfolioRoute = require('../../routes/portfolio');

// Mount routes
app.use('/api/settings', settingsRoute);
app.use('/api/portfolio', portfolioRoute);

describe('Frontend-Backend API Communication', () => {
  
  test('Settings API key endpoints should be accessible', async () => {
    // Test GET /api/settings/api-keys (called by frontend)
    const response = await request(app)
      .get('/api/settings/api-keys')
      .expect(200);

    expect(response.body.success).toBe(true);
    expect(Array.isArray(response.body.data)).toBe(true);
  });

  test('Portfolio API key endpoints should be accessible', async () => {
    // Test GET /api/portfolio/api-keys (called by Settings.jsx)
    const response = await request(app)
      .get('/api/portfolio/api-keys')
      .expect(200);

    expect(response.body.success).toBe(true);
    expect(Array.isArray(response.body.apiKeys)).toBe(true);
  });

  test('Settings route should return correct response format', async () => {
    // This tests the fix where backend returned 'apiKeys' but frontend expected 'data'
    const response = await request(app)
      .get('/api/settings/api-keys')
      .expect(200);

    // Verify the response has the 'data' field (not 'apiKeys')
    expect(response.body).toHaveProperty('data');
    expect(response.body).not.toHaveProperty('apiKeys');
    expect(response.body.success).toBe(true);
  });

  test('Portfolio route should return correct response format', async () => {
    const response = await request(app)
      .get('/api/portfolio/api-keys')
      .expect(200);

    // Portfolio route should return 'apiKeys' field for backwards compatibility
    expect(response.body).toHaveProperty('apiKeys');
    expect(response.body.success).toBe(true);
  });

  test('API endpoints should handle authentication correctly', async () => {
    // Remove auth middleware temporarily to test auth requirement
    const noAuthApp = express();
    noAuthApp.use(express.json());
    noAuthApp.use('/api/settings', settingsRoute);

    // Should return 401 without authentication
    await request(noAuthApp)
      .get('/api/settings/api-keys')
      .expect(401);
  });

  test('Settings health endpoint should work', async () => {
    const response = await request(app)
      .get('/api/settings/')
      .expect(200);

    expect(response.body.success).toBe(true);
    expect(response.body.data.system).toBe('User Settings API');
  });

  test('Portfolio health endpoint should work', async () => {
    const response = await request(app)
      .get('/api/portfolio/')
      .expect(200);

    expect(response.body.status).toBe('ok');
    expect(response.body.endpoint).toBe('portfolio');
  });

  test('API key validation endpoints should be accessible', async () => {
    // Test validation endpoint that frontend might call
    const response = await request(app)
      .post('/api/settings/api-keys/alpaca/validate')
      .expect(200);

    expect(response.body.success).toBe(true);
    expect(response.body.data).toHaveProperty('valid');
    expect(response.body.data.valid).toBe(false); // No key stored, so should be false
  });

  test('Error responses should have consistent format', async () => {
    // Test with invalid provider to get error response
    const response = await request(app)
      .post('/api/settings/api-keys')
      .send({
        name: 'invalid-provider',
        key: 'test-key',
        secret: 'test-secret'
      })
      .expect(400);

    expect(response.body.success).toBe(false);
    expect(response.body.error).toBeTruthy();
  });

  test('Add API key with new format should work', async () => {
    // Test the new API format (name/key instead of provider/apiKey)
    const response = await request(app)
      .post('/api/settings/api-keys')
      .send({
        name: 'alpaca',
        key: 'PKTEST123456789012345678901234567890',
        secret: 'test-secret-key-1234567890123456789012345678901234567890',
        isSandbox: true,
        description: 'Test API key'
      })
      .expect(200);

    expect(response.body.success).toBe(true);
    expect(response.body.message).toBe('API key added successfully');
    expect(response.body.apiKey.provider).toBe('alpaca');
  });
});