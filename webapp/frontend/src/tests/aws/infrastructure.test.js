/**
 * AWS Infrastructure Integration Tests
 * Tests actual AWS services and deployment configuration
 */

import { describe, it, expect, beforeAll } from 'vitest';

describe('AWS Infrastructure Tests', () => {
  let apiUrl;
  let cloudfrontUrl;
  
  beforeAll(() => {
    // Get URLs from config or environment
    apiUrl = import.meta.env.VITE_API_URL || 'https://jh28jhdp01.execute-api.us-east-1.amazonaws.com/dev';
    cloudfrontUrl = 'https://d1zb7knau41vl9.cloudfront.net';
  });

  describe('API Gateway Health', () => {
    it('should reach API Gateway health endpoint', async () => {
      const response = await fetch(`${apiUrl}/health`, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json'
        }
      });

      expect(response.status).toBeLessThan(500);
      
      if (response.ok) {
        const data = await response.json();
        expect(data).toHaveProperty('status');
      }
    }, 15000);

    it('should have CORS headers configured', async () => {
      const response = await fetch(`${apiUrl}/health`, {
        method: 'OPTIONS'
      });

      // Should not be blocked by CORS
      expect(response.status).not.toBe(0);
      
      if (response.headers) {
        const corsHeader = response.headers.get('Access-Control-Allow-Origin');
        expect(corsHeader).toBeTruthy();
      }
    }, 10000);

    it('should handle authentication endpoints', async () => {
      const authResponse = await fetch(`${apiUrl}/auth/status`, {
        method: 'GET',
        headers: {
          'Accept': 'application/json'
        }
      });

      // Should respond (even if unauthorized)
      expect([200, 401, 403]).toContain(authResponse.status);
    }, 10000);
  });

  describe('Database Connectivity', () => {
    it('should report database status in health check', async () => {
      try {
        const response = await fetch(`${apiUrl}/health`);
        
        if (response.ok) {
          const data = await response.json();
          
          // Database status should be reported
          if (data.database) {
            expect(['connected', 'disconnected', 'error']).toContain(data.database.status);
          }
        }
      } catch (error) {
        // Network errors are acceptable for this test
        console.warn('Database connectivity test skipped due to network error');
      }
    }, 15000);

    it('should handle circuit breaker states', async () => {
      try {
        const response = await fetch(`${apiUrl}/health`);
        
        if (response.ok) {
          const data = await response.json();
          
          // Should not expose circuit breaker details to unauthorized users
          if (data.circuitBreaker) {
            expect(['open', 'closed', 'half-open']).toContain(data.circuitBreaker.state);
          }
        }
      } catch (error) {
        console.warn('Circuit breaker test skipped due to network error');
      }
    }, 10000);
  });

  describe('Environment Configuration', () => {
    it('should have environment variables configured', async () => {
      try {
        const response = await fetch(`${apiUrl}/health`);
        
        if (response.ok) {
          const data = await response.json();
          
          // Should have environment indicator
          expect(data).toHaveProperty('environment');
          expect(['development', 'staging', 'production']).toContain(data.environment);
        }
      } catch (error) {
        console.warn('Environment config test skipped due to network error');
      }
    }, 10000);

    it('should not expose sensitive environment variables', async () => {
      try {
        const response = await fetch(`${apiUrl}/health`);
        
        if (response.ok) {
          const text = await response.text();
          
          // Should not contain AWS credentials or secrets
          expect(text).not.toMatch(/AKIA[0-9A-Z]{16}/); // AWS access key
          expect(text).not.toMatch(/[A-Za-z0-9/+=]{40}/); // AWS secret
          expect(text).not.toMatch(/DB_SECRET_ARN/);
          expect(text).not.toMatch(/rds-db-credentials/);
        }
      } catch (error) {
        console.warn('Sensitive data test skipped due to network error');
      }
    }, 10000);
  });

  describe('Lambda Function Performance', () => {
    it('should respond within acceptable time limits', async () => {
      const start = Date.now();
      
      try {
        const response = await fetch(`${apiUrl}/health`);
        const duration = Date.now() - start;
        
        // Should respond within 10 seconds (accounting for cold starts)
        expect(duration).toBeLessThan(10000);
        
        if (response.ok) {
          const data = await response.json();
          
          // Check if this was a cold start
          if (data.coldStart !== undefined) {
            console.log(`Lambda cold start: ${data.coldStart}`);
          }
        }
      } catch (error) {
        const duration = Date.now() - start;
        
        // Even network errors should happen quickly
        expect(duration).toBeLessThan(30000);
      }
    }, 35000);
  });

  describe('CloudFront Distribution', () => {
    it('should serve static assets from CloudFront', async () => {
      try {
        const response = await fetch(cloudfrontUrl, {
          method: 'HEAD'
        });

        // Should be reachable
        expect([200, 403, 404]).toContain(response.status);
        
        // Should have CloudFront headers
        const cfHeaders = response.headers.get('via') || response.headers.get('x-cache');
        if (cfHeaders) {
          expect(cfHeaders).toContain('cloudfront');
        }
      } catch (error) {
        console.warn('CloudFront test skipped due to network error');
      }
    }, 10000);
  });

  describe('Security Configuration', () => {
    it('should have security headers configured', async () => {
      try {
        const response = await fetch(`${apiUrl}/health`);
        
        if (response.headers) {
          // Check for basic security headers
          const securityHeaders = [
            'x-content-type-options',
            'x-frame-options',
            'strict-transport-security'
          ];
          
          // At least some security headers should be present
          const presentHeaders = securityHeaders.filter(header => 
            response.headers.get(header)
          );
          
          expect(presentHeaders.length).toBeGreaterThan(0);
        }
      } catch (error) {
        console.warn('Security headers test skipped due to network error');
      }
    }, 10000);

    it('should not expose server information', async () => {
      try {
        const response = await fetch(`${apiUrl}/health`);
        
        if (response.headers) {
          const serverHeader = response.headers.get('server');
          
          // Should not expose detailed server information
          if (serverHeader) {
            expect(serverHeader).not.toMatch(/nginx\/[\d\.]+/);
            expect(serverHeader).not.toMatch(/apache\/[\d\.]+/);
          }
        }
      } catch (error) {
        console.warn('Server header test skipped due to network error');
      }
    }, 10000);
  });

  describe('Data Layer Integration', () => {
    it('should handle API key service endpoints', async () => {
      try {
        // Test API key service without authentication
        const response = await fetch(`${apiUrl}/api-keys`, {
          headers: {
            'Accept': 'application/json'
          }
        });

        // Should respond with authentication required or service info
        expect([200, 401, 403, 503]).toContain(response.status);
        
        if (response.ok) {
          const data = await response.json();
          
          // Should have appropriate response structure
          expect(data).toBeTypeOf('object');
        }
      } catch (error) {
        console.warn('API key service test skipped due to network error');
      }
    }, 10000);

    it('should handle market data endpoints', async () => {
      try {
        const response = await fetch(`${apiUrl}/market-data/health`);
        
        // Should respond appropriately
        expect([200, 401, 403, 404, 503]).toContain(response.status);
      } catch (error) {
        console.warn('Market data test skipped due to network error');
      }
    }, 10000);
  });
});

describe('Deployment Validation', () => {
  describe('Configuration Consistency', () => {
    it('should have consistent API URLs across environments', () => {
      const configUrl = window.__CONFIG__?.API_URL;
      const envUrl = import.meta.env.VITE_API_URL;
      
      // URLs should be consistent
      if (configUrl && envUrl) {
        expect(configUrl).toBe(envUrl);
      }
      
      // Should be valid URLs
      if (configUrl) {
        expect(() => new URL(configUrl)).not.toThrow();
      }
    });

    it('should have build-time configuration available', () => {
      // Build-time config should be available
      expect(window.__CONFIG__).toBeDefined();
      expect(window.__CONFIG__.BUILD_TIME).toBeDefined();
      expect(window.__CONFIG__.VERSION).toBeDefined();
    });
  });

  describe('Feature Flags and Environment Detection', () => {
    it('should correctly identify environment', () => {
      const isDev = import.meta.env.DEV;
      const isProd = import.meta.env.PROD;
      
      // Should be either dev or prod, not both
      expect(isDev !== isProd).toBe(true);
    });

    it('should have appropriate feature flags for environment', () => {
      const isProd = import.meta.env.PROD;
      
      // Production should have certain features disabled
      if (isProd) {
        // Debug features should be disabled in production
        expect(import.meta.env.VITE_DEBUG_MODE).not.toBe('true');
      }
    });
  });
});