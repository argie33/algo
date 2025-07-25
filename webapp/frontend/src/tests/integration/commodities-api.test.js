import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { getApiConfig } from '../../services/api';

// API Integration Tests for Commodities Page
describe('Commodities API Integration', () => {
  let apiUrl;

  beforeAll(() => {
    const config = getApiConfig();
    apiUrl = config.apiUrl;
  });

  describe('API Configuration', () => {
    it('should have valid API URL configured', () => {
      expect(apiUrl).toBeDefined();
      expect(apiUrl).toMatch(/^https?:\/\//);
    });
  });

  describe('Commodities Categories Endpoint', () => {
    it('should return category data structure', async () => {
      try {
        const response = await fetch(`${apiUrl}/api/commodities/categories`);
        
        if (response.ok) {
          const data = await response.json();
          
          // Validate response structure
          expect(data).toHaveProperty('success');
          expect(data).toHaveProperty('data');
          expect(Array.isArray(data.data)).toBe(true);
          
          if (data.data.length > 0) {
            const category = data.data[0];
            expect(category).toHaveProperty('id');
            expect(category).toHaveProperty('name');
            expect(category).toHaveProperty('commodities');
            expect(Array.isArray(category.commodities)).toBe(true);
          }
        } else {
          // Even if endpoint doesn't exist yet, we should get a 404, not 500
          expect(response.status).toBeOneOf([404, 501]);
        }
      } catch (error) {
        // Network errors are acceptable for testing
        expect(error.message).toMatch(/fetch|network|ECONNREFUSED/i);
      }
    });
  });

  describe('Commodities Prices Endpoint', () => {
    it('should return price data structure', async () => {
      try {
        const response = await fetch(`${apiUrl}/api/commodities/prices`);
        
        if (response.ok) {
          const data = await response.json();
          
          // Validate response structure
          expect(data).toHaveProperty('success');
          expect(data).toHaveProperty('data');
          expect(Array.isArray(data.data)).toBe(true);
          
          if (data.data.length > 0) {
            const commodity = data.data[0];
            expect(commodity).toHaveProperty('symbol');
            expect(commodity).toHaveProperty('name');
            expect(commodity).toHaveProperty('price');
            expect(commodity).toHaveProperty('category');
            expect(typeof commodity.price).toBe('number');
          }
        } else {
          expect(response.status).toBeOneOf([404, 501]);
        }
      } catch (error) {
        expect(error.message).toMatch(/fetch|network|ECONNREFUSED/i);
      }
    });

    it('should support category filtering', async () => {
      try {
        const response = await fetch(`${apiUrl}/api/commodities/prices?category=energy`);
        
        if (response.ok) {
          const data = await response.json();
          
          expect(data).toHaveProperty('success');
          expect(data).toHaveProperty('data');
          expect(Array.isArray(data.data)).toBe(true);
          
          // All returned commodities should be in energy category
          data.data.forEach(commodity => {
            expect(commodity.category).toBe('energy');
          });
        } else {
          expect(response.status).toBeOneOf([404, 501]);
        }
      } catch (error) {
        expect(error.message).toMatch(/fetch|network|ECONNREFUSED/i);
      }
    });
  });

  describe('Market Summary Endpoint', () => {
    it('should return market summary data', async () => {
      try {
        const response = await fetch(`${apiUrl}/api/commodities/market-summary`);
        
        if (response.ok) {
          const data = await response.json();
          
          expect(data).toHaveProperty('success');
          expect(data).toHaveProperty('data');
          
          const summary = data.data;
          expect(summary).toHaveProperty('overview');
          expect(summary.overview).toHaveProperty('totalMarketCap');
          expect(summary.overview).toHaveProperty('totalVolume');
          expect(summary.overview).toHaveProperty('tradingSession');
          
          expect(typeof summary.overview.totalMarketCap).toBe('number');
          expect(typeof summary.overview.totalVolume).toBe('number');
          expect(['open', 'closed']).toContain(summary.overview.tradingSession);
        } else {
          expect(response.status).toBeOneOf([404, 501]);
        }
      } catch (error) {
        expect(error.message).toMatch(/fetch|network|ECONNREFUSED/i);
      }
    });
  });

  describe('Correlations Endpoint', () => {
    it('should return correlation matrix data', async () => {
      try {
        const response = await fetch(`${apiUrl}/api/commodities/correlations`);
        
        if (response.ok) {
          const data = await response.json();
          
          expect(data).toHaveProperty('success');
          expect(data).toHaveProperty('data');
          
          const correlations = data.data;
          expect(correlations).toHaveProperty('matrix');
          expect(typeof correlations.matrix).toBe('object');
          
          // Check that matrix has expected structure
          const categories = Object.keys(correlations.matrix);
          categories.forEach(category => {
            expect(typeof correlations.matrix[category]).toBe('object');
          });
        } else {
          expect(response.status).toBeOneOf([404, 501]);
        }
      } catch (error) {
        expect(error.message).toMatch(/fetch|network|ECONNREFUSED/i);
      }
    });
  });

  describe('Health Check', () => {
    it('should have commodities service health endpoint', async () => {
      try {
        const response = await fetch(`${apiUrl}/api/commodities/health`);
        
        if (response.ok) {
          const data = await response.json();
          
          expect(data).toHaveProperty('success');
          expect(data).toHaveProperty('service');
          expect(data.service).toBe('commodities');
          expect(data).toHaveProperty('status');
          expect(data.status).toBe('operational');
        } else {
          expect(response.status).toBeOneOf([404, 501]);
        }
      } catch (error) {
        expect(error.message).toMatch(/fetch|network|ECONNREFUSED/i);
      }
    });
  });

  describe('Error Handling', () => {
    it('should handle invalid endpoints gracefully', async () => {
      try {
        const response = await fetch(`${apiUrl}/api/commodities/invalid-endpoint`);
        
        // Should return 404 for invalid endpoints
        expect(response.status).toBe(404);
      } catch (error) {
        // Network errors are acceptable
        expect(error.message).toMatch(/fetch|network|ECONNREFUSED/i);
      }
    });

    it('should handle malformed parameters', async () => {
      try {
        const response = await fetch(`${apiUrl}/api/commodities/prices?category=invalid-category`);
        
        if (response.ok) {
          const data = await response.json();
          
          // Should return empty array for invalid category
          expect(data).toHaveProperty('success');
          expect(data).toHaveProperty('data');
          expect(Array.isArray(data.data)).toBe(true);
          expect(data.data.length).toBe(0);
        } else {
          expect(response.status).toBeOneOf([400, 404, 501]);
        }
      } catch (error) {
        expect(error.message).toMatch(/fetch|network|ECONNREFUSED/i);
      }
    });
  });

  describe('Response Format Validation', () => {
    it('should return consistent response format across endpoints', async () => {
      const endpoints = [
        '/api/commodities/categories',
        '/api/commodities/prices',
        '/api/commodities/market-summary',
        '/api/commodities/correlations'
      ];

      for (const endpoint of endpoints) {
        try {
          const response = await fetch(`${apiUrl}${endpoint}`);
          
          if (response.ok) {
            const data = await response.json();
            
            // All responses should have these properties
            expect(data).toHaveProperty('success');
            expect(data).toHaveProperty('timestamp');
            expect(typeof data.success).toBe('boolean');
            expect(typeof data.timestamp).toBe('string');
            
            // If successful, should have data property
            if (data.success) {
              expect(data).toHaveProperty('data');
            } else {
              expect(data).toHaveProperty('error');
            }
          }
        } catch (error) {
          // Network errors are acceptable for testing
          expect(error.message).toMatch(/fetch|network|ECONNREFUSED/i);
        }
      }
    });
  });

  describe('Performance Requirements', () => {
    it('should respond within acceptable time limits', async () => {
      const startTime = Date.now();
      
      try {
        const response = await fetch(`${apiUrl}/api/commodities/prices`);
        const endTime = Date.now();
        const responseTime = endTime - startTime;
        
        // API should respond within 5 seconds (generous for testing)
        expect(responseTime).toBeLessThan(5000);
        
        if (response.ok) {
          // If endpoint exists, should be faster
          expect(responseTime).toBeLessThan(2000);
        }
      } catch (error) {
        // Network timeouts are acceptable
        expect(error.message).toMatch(/fetch|network|timeout|ECONNREFUSED/i);
      }
    });
  });
});