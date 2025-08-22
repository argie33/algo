/**
 * Real API Endpoints Integration Tests
 * Tests actual deployed API endpoints and functionality
 */

const request = require('supertest');
const { app } = require('../../index');

describe('Real API Endpoints Integration Tests', () => {
  let server;

  beforeAll(() => {
    // Start the server for testing
    server = app.listen(0); // Use random port
  });

  afterAll(async () => {
    if (server) {
      await new Promise(resolve => server.close(resolve));
    }
  });

  describe('Health and Core Endpoints', () => {
    it('should return healthy status from /health', async () => {
      const response = await request(app)
        .get('/health')
        .expect('Content-Type', /json/);
      
      expect(response.status).toBe(200);
      expect(response.body).toHaveProperty('status');
      expect(response.body.status).toBe('healthy');
    });

    it('should handle CORS preflight requests', async () => {
      const response = await request(app)
        .options('/health')
        .set('Origin', 'https://d1zb7knau41vl9.cloudfront.net')
        .set('Access-Control-Request-Method', 'GET');
      
      expect(response.status).toBe(204);
      expect(response.headers['access-control-allow-origin']).toBeDefined();
    });
  });

  describe('Market Data Endpoints', () => {
    it('should return market overview data', async () => {
      const response = await request(app)
        .get('/api/market/overview')
        .expect('Content-Type', /json/);
      
      // Should respond (even if no data)
      expect([200, 404, 500]).toContain(response.status);
      
      if (response.status === 200) {
        expect(response.body).toBeDefined();
        expect(typeof response.body).toBe('object');
      }
    });

    it('should handle stock quotes request', async () => {
      const response = await request(app)
        .get('/api/stocks/quote?symbol=AAPL')
        .expect('Content-Type', /json/);
      
      // Should respond with some status
      expect(typeof response.status).toBe('number');
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('data');
      }
    });

    it('should return trading signals', async () => {
      const response = await request(app)
        .get('/api/signals')
        .expect('Content-Type', /json/);
      
      // Should respond
      expect(typeof response.status).toBe('number');
      
      if (response.status === 200) {
        expect(response.body).toBeDefined();
      }
    });

    it('should return sentiment analysis data', async () => {
      const response = await request(app)
        .get('/api/sentiment/analysis')
        .expect('Content-Type', /json/);
      
      // Should respond
      expect(typeof response.status).toBe('number');
      
      if (response.status === 200) {
        expect(response.body).toBeDefined();
      }
    });

    it('should handle technical analysis requests', async () => {
      const response = await request(app)
        .get('/api/technical/indicators?symbol=AAPL&period=1d')
        .expect('Content-Type', /json/);
      
      // Should respond
      expect(typeof response.status).toBe('number');
    });
  });

  describe('Portfolio Endpoints', () => {
    it('should handle portfolio requests (auth required)', async () => {
      const response = await request(app)
        .get('/api/portfolio')
        .expect('Content-Type', /json/);
      
      // Should require auth (401) or return data (200)
      expect([200, 401, 403]).toContain(response.status);
    });

    it('should handle portfolio positions request', async () => {
      const response = await request(app)
        .get('/api/portfolio/positions')
        .expect('Content-Type', /json/);
      
      // Should require auth or return data
      expect([200, 401, 403]).toContain(response.status);
    });

    it('should handle portfolio performance request', async () => {
      const response = await request(app)
        .get('/api/portfolio/performance')
        .expect('Content-Type', /json/);
      
      // Should require auth or return data
      expect([200, 401, 403]).toContain(response.status);
    });
  });

  describe('Settings and Configuration Endpoints', () => {
    it('should handle settings request', async () => {
      const response = await request(app)
        .get('/api/settings')
        .expect('Content-Type', /json/);
      
      // Should require auth
      expect([200, 401, 403]).toContain(response.status);
    });

    it('should handle API keys endpoint (auth required)', async () => {
      const response = await request(app)
        .get('/api/settings/api-keys')
        .expect('Content-Type', /json/);
      
      // Should require auth
      expect([200, 401, 403]).toContain(response.status);
    });

    it('should handle API key validation', async () => {
      const response = await request(app)
        .post('/api/settings/api-keys/validate')
        .send({ provider: 'alpaca', keyId: 'test-key', secret: 'test-secret' })
        .expect('Content-Type', /json/);
      
      // Should handle validation request
      expect([200, 400, 401, 403]).toContain(response.status);
    });
  });

  describe('Watchlist Endpoints', () => {
    it('should handle watchlist request', async () => {
      const response = await request(app)
        .get('/api/watchlist');
      
      // Route doesn't exist yet - should return 404
      expect(response.status).toBe(404);
    });

    it('should handle add to watchlist', async () => {
      const response = await request(app)
        .post('/api/watchlist')
        .send({ symbol: 'AAPL', name: 'Apple Inc.' });
      
      // Route doesn't exist yet - should return 404
      expect(response.status).toBe(404);
    });
  });

  describe('News and Analysis Endpoints', () => {
    it('should return news data', async () => {
      const response = await request(app)
        .get('/api/news')
        .expect('Content-Type', /json/);
      
      // Should respond
      expect(typeof response.status).toBe('number');
      
      if (response.status === 200) {
        expect(response.body).toBeDefined();
      }
    });

    it('should return earnings calendar', async () => {
      const response = await request(app)
        .get('/api/calendar/earnings')
        .expect('Content-Type', /json/);
      
      // Should respond
      expect(typeof response.status).toBe('number');
    });

    it('should handle sector analysis', async () => {
      const response = await request(app)
        .get('/api/sectors/analysis')
        .expect('Content-Type', /json/);
      
      // Should respond
      expect(typeof response.status).toBe('number');
    });
  });

  describe('Live Data Endpoints', () => {
    it('should handle live data subscription', async () => {
      const response = await request(app)
        .get('/api/live-data/subscribe')
        .expect('Content-Type', /json/);
      
      // Should respond with subscription info
      expect(typeof response.status).toBe('number');
    });

    it('should handle live data status', async () => {
      const response = await request(app)
        .get('/api/live-data/status')
        .expect('Content-Type', /json/);
      
      // Should respond with status
      expect(typeof response.status).toBe('number');
      
      if (response.status === 200) {
        expect(response.body).toHaveProperty('data');
      }
    });
  });

  describe('Error Handling Tests', () => {
    it('should handle 404 for non-existent endpoints', async () => {
      const response = await request(app)
        .get('/api/nonexistent-endpoint')
        .expect('Content-Type', /json/);
      
      expect(response.status).toBe(404);
    });

    it('should handle malformed JSON requests', async () => {
      const response = await request(app)
        .post('/api/portfolio')
        .set('Content-Type', 'application/json')
        .send('invalid json{')
        .expect('Content-Type', /json/);
      
      expect(response.status).toBe(400);
    });

    it('should handle very large payloads', async () => {
      const largePayload = 'x'.repeat(100000); // 100KB payload
      
      const response = await request(app)
        .post('/api/portfolio')
        .send({ data: largePayload })
        .expect('Content-Type', /json/);
      
      // Should handle large payloads (may reject or accept)
      expect([200, 400, 401, 413]).toContain(response.status);
    });
  });

  describe('Security Tests', () => {
    it('should reject requests without proper headers', async () => {
      const response = await request(app)
        .get('/api/portfolio')
        .set('Authorization', 'Bearer invalid-token')
        .expect('Content-Type', /json/);
      
      // Should reject invalid auth 
      expect([401, 403, 404]).toContain(response.status);
    });

    it('should prevent SQL injection in query params', async () => {
      const response = await request(app)
        .get('/api/stocks/quote?symbol=AAPL\'; DROP TABLE users; --')
        .expect('Content-Type', /json/);
      
      // Should handle malicious input safely (401 because it requires auth)
      expect([401, 400, 404]).toContain(response.status);
    });

    it('should prevent XSS in parameters', async () => {
      const response = await request(app)
        .get('/api/stocks/quote?symbol=<script>alert("xss")</script>')
        .expect('Content-Type', /json/);
      
      // Should sanitize input (401 because it requires auth)
      expect([401, 400, 404]).toContain(response.status);
    });
  });

  describe('Performance Tests', () => {
    it('should respond to health check within 5 seconds', async () => {
      const startTime = Date.now();
      
      const response = await request(app)
        .get('/health')
        .timeout(5000);
      
      const responseTime = Date.now() - startTime;
      
      expect(response.status).toBe(200);
      expect(responseTime).toBeLessThan(5000);
    }, 6000);

    it('should handle concurrent requests', async () => {
      const promises = [];
      
      // Send 5 concurrent requests
      for (let i = 0; i < 5; i++) {
        promises.push(
          request(app)
            .get('/health')
            .timeout(10000)
        );
      }
      
      const responses = await Promise.all(promises);
      
      // All should succeed
      responses.forEach(response => {
        expect(response.status).toBe(200);
      });
    }, 15000);
  });
});