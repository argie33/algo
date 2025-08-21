const request = require('supertest');
const express = require('express');

// Create test app
const app = express();
app.use(express.json());

// Mock database health check
const mockHealthCheck = jest.fn();
jest.mock('../../utils/database', () => ({
  healthCheck: mockHealthCheck
}));

// Import routes after mocking
const healthRoutes = require('../../routes/health');
app.use('/api/health', healthRoutes);

describe('Health API Endpoints', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('GET /api/health', () => {
    it('should return healthy status when all services are up', async () => {
      mockHealthCheck.mockResolvedValue({
        healthy: true,
        message: 'Database connection successful',
        responseTime: 50
      });

      const response = await request(app)
        .get('/api/health')
        .expect(200);

      expect(response.body).toEqual({
        status: 'healthy',
        timestamp: expect.any(String),
        services: {
          database: {
            healthy: true,
            message: 'Database connection successful',
            responseTime: 50
          }
        }
      });
    });

    it('should return unhealthy status when database is down', async () => {
      mockHealthCheck.mockResolvedValue({
        healthy: false,
        message: 'Database connection failed',
        error: 'Connection refused'
      });

      const response = await request(app)
        .get('/api/health')
        .expect(503);

      expect(response.body).toEqual({
        status: 'unhealthy',
        timestamp: expect.any(String),
        services: {
          database: {
            healthy: false,
            message: 'Database connection failed',
            error: 'Connection refused'
          }
        }
      });
    });

    it('should handle database health check errors', async () => {
      mockHealthCheck.mockRejectedValue(new Error('Health check failed'));

      const response = await request(app)
        .get('/api/health')
        .expect(503);

      expect(response.body).toEqual({
        status: 'unhealthy',
        timestamp: expect.any(String),
        services: {
          database: {
            healthy: false,
            message: 'Health check failed',
            error: 'Health check failed'
          }
        }
      });
    });
  });

  describe('GET /api/health/detailed', () => {
    it('should return detailed health information', async () => {
      mockHealthCheck.mockResolvedValue({
        healthy: true,
        message: 'Database connection successful',
        responseTime: 45,
        details: {
          poolSize: 5,
          activeConnections: 2,
          idleConnections: 3
        }
      });

      const response = await request(app)
        .get('/api/health/detailed')
        .expect(200);

      expect(response.body).toEqual({
        status: 'healthy',
        timestamp: expect.any(String),
        uptime: expect.any(Number),
        version: expect.any(String),
        environment: 'test',
        services: {
          database: {
            healthy: true,
            message: 'Database connection successful',
            responseTime: 45,
            details: {
              poolSize: 5,
              activeConnections: 2,
              idleConnections: 3
            }
          }
        }
      });
    });
  });

  describe('Health Check Performance', () => {
    it('should respond within acceptable time limits', async () => {
      mockHealthCheck.mockResolvedValue({
        healthy: true,
        message: 'Database connection successful',
        responseTime: 30
      });

      const startTime = Date.now();
      await request(app)
        .get('/api/health')
        .expect(200);
      const responseTime = Date.now() - startTime;

      expect(responseTime).toBeLessThan(1000); // Should respond within 1 second
    });

    it('should handle slow database responses', async () => {
      // Simulate slow database response
      mockHealthCheck.mockImplementation(() => 
        new Promise(resolve => 
          setTimeout(() => resolve({
            healthy: true,
            message: 'Database connection successful',
            responseTime: 800
          }), 100)
        )
      );

      const response = await request(app)
        .get('/api/health')
        .expect(200);

      expect(response.body.services.database.responseTime).toBeGreaterThan(50);
    });
  });
});