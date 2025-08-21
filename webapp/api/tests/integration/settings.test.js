const request = require('supertest');
const express = require('express');

// Create test app
const app = express();
app.use(express.json());

// Mock dependencies
const mockQuery = jest.fn();
const mockApiKeyService = {
  validateJwtToken: jest.fn(),
  getApiKeys: jest.fn(),
  storeApiKeys: jest.fn(),
  deleteApiKeys: jest.fn()
};

jest.mock('../../utils/database', () => ({
  query: mockQuery
}));

jest.mock('../../utils/apiKeyService', () => {
  return jest.fn().mockImplementation(() => mockApiKeyService);
});

// Mock auth middleware
const mockAuthMiddleware = (req, res, next) => {
  req.user = {
    sub: 'test-user-123',
    'cognito:username': 'testuser',
    email: 'test@example.com'
  };
  next();
};

app.use(mockAuthMiddleware);

// Import routes after mocking
const settingsRoutes = require('../../routes/settings');
app.use('/api/settings', settingsRoutes);

describe('Settings API Endpoints', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('GET /api/settings/api-keys', () => {
    it('should return user API keys', async () => {
      const mockApiKeys = {
        alpaca: 'alpaca-key-123',
        polygon: 'polygon-key-456'
      };

      mockApiKeyService.getApiKeys.mockResolvedValue(mockApiKeys);

      const response = await request(app)
        .get('/api/settings/api-keys')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: mockApiKeys
      });
      expect(mockApiKeyService.getApiKeys).toHaveBeenCalledWith('test-user-123');
    });

    it('should handle missing API keys', async () => {
      mockApiKeyService.getApiKeys.mockResolvedValue({});

      const response = await request(app)
        .get('/api/settings/api-keys')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: {}
      });
    });

    it('should handle API key service errors', async () => {
      mockApiKeyService.getApiKeys.mockRejectedValue(new Error('Service unavailable'));

      const response = await request(app)
        .get('/api/settings/api-keys')
        .expect(500);

      expect(response.body).toEqual({
        success: false,
        error: 'Failed to retrieve API keys'
      });
    });
  });

  describe('POST /api/settings/api-keys', () => {
    it('should store API keys successfully', async () => {
      const apiKeysData = {
        alpaca: 'new-alpaca-key',
        polygon: 'new-polygon-key'
      };

      mockApiKeyService.storeApiKeys.mockResolvedValue(true);

      const response = await request(app)
        .post('/api/settings/api-keys')
        .send(apiKeysData)
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        message: 'API keys stored successfully'
      });
      expect(mockApiKeyService.storeApiKeys).toHaveBeenCalledWith('test-user-123', apiKeysData);
    });

    it('should validate API key data', async () => {
      const invalidApiKeysData = {
        alpaca: '',
        polygon: 'valid-key'
      };

      const response = await request(app)
        .post('/api/settings/api-keys')
        .send(invalidApiKeysData)
        .expect(400);

      expect(response.body).toEqual({
        success: false,
        error: 'Invalid API key data'
      });
    });

    it('should handle storage errors', async () => {
      const apiKeysData = {
        alpaca: 'new-alpaca-key'
      };

      mockApiKeyService.storeApiKeys.mockRejectedValue(new Error('Storage failed'));

      const response = await request(app)
        .post('/api/settings/api-keys')
        .send(apiKeysData)
        .expect(500);

      expect(response.body).toEqual({
        success: false,
        error: 'Failed to store API keys'
      });
    });
  });

  describe('DELETE /api/settings/api-keys/:provider', () => {
    it('should delete specific API key provider', async () => {
      mockApiKeyService.deleteApiKeys.mockResolvedValue(true);

      const response = await request(app)
        .delete('/api/settings/api-keys/alpaca')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        message: 'API key deleted successfully'
      });
      expect(mockApiKeyService.deleteApiKeys).toHaveBeenCalledWith('test-user-123', 'alpaca');
    });

    it('should validate provider parameter', async () => {
      const response = await request(app)
        .delete('/api/settings/api-keys/invalid-provider')
        .expect(400);

      expect(response.body).toEqual({
        success: false,
        error: 'Invalid provider'
      });
    });

    it('should handle deletion errors', async () => {
      mockApiKeyService.deleteApiKeys.mockRejectedValue(new Error('Deletion failed'));

      const response = await request(app)
        .delete('/api/settings/api-keys/alpaca')
        .expect(500);

      expect(response.body).toEqual({
        success: false,
        error: 'Failed to delete API key'
      });
    });
  });

  describe('GET /api/settings/preferences', () => {
    it('should return user preferences', async () => {
      const mockPreferences = {
        theme: 'dark',
        notifications: true,
        defaultTimeframe: '1D'
      };

      mockQuery.mockResolvedValue({
        rows: [mockPreferences]
      });

      const response = await request(app)
        .get('/api/settings/preferences')
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        data: mockPreferences
      });
    });

    it('should return default preferences for new users', async () => {
      mockQuery.mockResolvedValue({ rows: [] });

      const response = await request(app)
        .get('/api/settings/preferences')
        .expect(200);

      expect(response.body.data).toEqual({
        theme: 'light',
        notifications: true,
        defaultTimeframe: '1D'
      });
    });
  });

  describe('POST /api/settings/preferences', () => {
    it('should update user preferences', async () => {
      const preferences = {
        theme: 'dark',
        notifications: false,
        defaultTimeframe: '4H'
      };

      mockQuery.mockResolvedValue({ rowCount: 1 });

      const response = await request(app)
        .post('/api/settings/preferences')
        .send(preferences)
        .expect(200);

      expect(response.body).toEqual({
        success: true,
        message: 'Preferences updated successfully'
      });
    });

    it('should validate preference values', async () => {
      const invalidPreferences = {
        theme: 'invalid-theme',
        notifications: 'not-boolean'
      };

      const response = await request(app)
        .post('/api/settings/preferences')
        .send(invalidPreferences)
        .expect(400);

      expect(response.body).toEqual({
        success: false,
        error: 'Invalid preference values'
      });
    });
  });

  describe('Authentication and Authorization', () => {
    it('should require authentication for all endpoints', async () => {
      // Create app without auth middleware
      const unauthenticatedApp = express();
      unauthenticatedApp.use(express.json());
      unauthenticatedApp.use('/api/settings', settingsRoutes);

      await request(unauthenticatedApp)
        .get('/api/settings/api-keys')
        .expect(401);
    });

    it('should handle invalid JWT tokens', async () => {
      mockApiKeyService.validateJwtToken.mockRejectedValue(new Error('Invalid token'));

      // Test with auth middleware that validates tokens
      const tokenValidatingApp = express();
      tokenValidatingApp.use(express.json());
      
      const validatingAuthMiddleware = async (req, res, next) => {
        try {
          const token = req.headers.authorization?.replace('Bearer ', '');
          await mockApiKeyService.validateJwtToken(token);
          req.user = { sub: 'test-user-123' };
          next();
        } catch (error) {
          res.status(401).json({ success: false, error: 'Unauthorized' });
        }
      };

      tokenValidatingApp.use(validatingAuthMiddleware);
      tokenValidatingApp.use('/api/settings', settingsRoutes);

      await request(tokenValidatingApp)
        .get('/api/settings/api-keys')
        .set('Authorization', 'Bearer invalid-token')
        .expect(401);
    });
  });

  describe('Rate Limiting and Security', () => {
    it('should handle concurrent requests safely', async () => {
      mockApiKeyService.getApiKeys.mockResolvedValue({ alpaca: 'test-key' });

      const requests = Array.from({ length: 10 }, () =>
        request(app).get('/api/settings/api-keys')
      );

      const responses = await Promise.all(requests);
      
      responses.forEach(response => {
        expect(response.status).toBe(200);
        expect(response.body.success).toBe(true);
      });
    });

    it('should sanitize input data', async () => {
      const maliciousData = {
        alpaca: '<script>alert("xss")</script>',
        polygon: 'SELECT * FROM users; DROP TABLE users;'
      };

      mockApiKeyService.storeApiKeys.mockResolvedValue(true);

      const response = await request(app)
        .post('/api/settings/api-keys')
        .send(maliciousData)
        .expect(200);

      // Verify that malicious input is handled properly
      const [userId, apiKeys] = mockApiKeyService.storeApiKeys.mock.calls[0];
      expect(apiKeys.alpaca).not.toContain('<script>');
      expect(apiKeys.polygon).not.toContain('DROP TABLE');
    });
  });
});