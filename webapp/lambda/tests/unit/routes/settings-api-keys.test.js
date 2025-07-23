/**
 * Unit Tests for Settings API Keys Route
 * Tests the API key response format and authentication handling
 */

const request = require('supertest');
const express = require('express');
const jwt = require('jsonwebtoken');

// Mock dependencies
jest.mock('../../../utils/simpleApiKeyService');
jest.mock('../../../middleware/auth');

const mockApiKeyService = require('../../../utils/simpleApiKeyService');
const { authenticateToken } = require('../../../middleware/auth');

// Create test app
const app = express();
app.use(express.json());

// Mock authentication middleware
authenticateToken.mockImplementation((req, res, next) => {
  req.user = {
    sub: 'test-user-123',
    email: 'test@example.com',
    username: 'testuser'
  };
  next();
});

// Load the settings route
const settingsRouter = require('../../../routes/settings');
app.use('/api/settings', settingsRouter);

describe('Settings API Keys Route', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    
    // Default mock for enabled service
    mockApiKeyService.isEnabled = true;
    mockApiKeyService.listApiKeys = jest.fn();
  });

  describe('GET /api/settings/api-keys', () => {
    test('should return data in correct format expected by frontend', async () => {
      // Mock API key service to return test keys
      const mockApiKeys = [
        {
          provider: 'alpaca',
          keyId: 'PK***MASKED***123',
          created: '2024-01-15T10:30:00Z'
        },
        {
          provider: 'polygon',
          keyId: 'pk_***MASKED***456',
          created: '2024-01-16T10:30:00Z'
        }
      ];
      
      mockApiKeyService.listApiKeys.mockResolvedValue(mockApiKeys);

      const response = await request(app)
        .get('/api/settings/api-keys')
        .expect(200);

      // Test the response structure matches frontend expectations
      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data'); // Frontend expects 'data', not 'apiKeys'
      expect(Array.isArray(response.body.data)).toBe(true);
      
      // Test the structure of each API key object
      expect(response.body.data).toHaveLength(2);
      
      const firstKey = response.body.data[0];
      expect(firstKey).toHaveProperty('id');
      expect(firstKey).toHaveProperty('provider', 'alpaca');
      expect(firstKey).toHaveProperty('is_active');
      expect(firstKey).toHaveProperty('masked_api_key');
      expect(firstKey).toHaveProperty('created_at');
    });

    test('should handle API key service disabled gracefully', async () => {
      mockApiKeyService.isEnabled = false;

      const response = await request(app)
        .get('/api/settings/api-keys')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data', []); // Should still use 'data' field
      expect(response.body).toHaveProperty('setupRequired', true);
    });

    test('should handle API key service errors gracefully', async () => {
      mockApiKeyService.listApiKeys.mockRejectedValue(new Error('Service unavailable'));

      const response = await request(app)
        .get('/api/settings/api-keys')
        .expect(200);

      expect(response.body).toHaveProperty('success', true);
      expect(response.body).toHaveProperty('data', []); // Should fallback with 'data' field
      expect(response.body).toHaveProperty('note');
    });

    test('should require authentication', async () => {
      // Override auth middleware to simulate no authentication
      authenticateToken.mockImplementationOnce((req, res, next) => {
        // Don't set req.user to simulate missing authentication
        next();
      });

      const response = await request(app)
        .get('/api/settings/api-keys')
        .expect(401);

      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error', 'Authentication required');
    });

    test('should validate user ID from token', async () => {
      // Override auth middleware to simulate missing user ID
      authenticateToken.mockImplementationOnce((req, res, next) => {
        req.user = { email: 'test@example.com' }; // Missing 'sub' field
        next();
      });

      const response = await request(app)
        .get('/api/settings/api-keys')
        .expect(401);

      expect(response.body).toHaveProperty('success', false);
      expect(response.body).toHaveProperty('error', 'Invalid authentication token');
    });

    test('should call API key service with correct user ID', async () => {
      mockApiKeyService.listApiKeys.mockResolvedValue([]);

      await request(app)
        .get('/api/settings/api-keys')
        .expect(200);

      expect(mockApiKeyService.listApiKeys).toHaveBeenCalledWith('test-user-123');
    });
  });
});