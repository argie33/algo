/**
 * API Security Test Suite
 * Comprehensive validation for API security measures
 */

import { test, expect } from '@playwright/test';

test.describe('API Security', () => {
  test.beforeEach(async ({ page }) => {
    // Set up API monitoring
    await page.addInitScript(() => {
      window.__API_REQUESTS__ = [];
      window.__SECURITY_VIOLATIONS__ = [];

      // Monitor fetch requests
      const originalFetch = window.fetch;
      window.fetch = function(...args) {
        const url = args[0];
        const options = args[1] || {};

        window.__API_REQUESTS__.push({
          url,
          method: options.method || 'GET',
          headers: options.headers || {},
          body: options.body,
          timestamp: Date.now()
        });

        return originalFetch.apply(this, args);
      };
    });
  });

  test('should enforce API authentication on all endpoints', async ({ page }) => {
    const securedEndpoints = [
      '/api/portfolio',
      '/api/user/profile',
      '/api/orders',
      '/api/positions',
      '/api/trades',
      '/api/alerts',
      '/api/watchlist',
      '/api/analytics',
      '/api/settings'
    ];

    await page.goto('/');

    for (const endpoint of securedEndpoints) {
      // Test without authentication
      const response = await page.evaluate(async (url) => {
        try {
          const res = await fetch(url, {
            headers: {
              'Content-Type': 'application/json'
            }
          });
          return { status: res.status, headers: Object.fromEntries(res.headers) };
        } catch (e) {
          return { error: e.message };
        }
      }, endpoint);

      // Should return 401 Unauthorized or 403 Forbidden
      expect([401, 403]).toContain(response.status);
    }
  });

  test('should validate API input parameters', async ({ page }) => {
    await page.goto('/portfolio');

    const maliciousPayloads = [
      // SQL Injection
      { field: 'symbol', value: "'; DROP TABLE positions; --" },
      { field: 'quantity', value: '1 OR 1=1' },

      // NoSQL Injection
      { field: 'filter', value: '{"$ne": null}' },
      { field: 'query', value: '{"$where": "function() { return true; }"}' },

      // XSS Payloads
      { field: 'notes', value: '<script>alert("xss")</script>' },
      { field: 'name', value: 'javascript:alert(1)' },

      // Path Traversal
      { field: 'file', value: '../../etc/passwd' },
      { field: 'path', value: '../../../windows/system32/config/sam' },

      // Command Injection
      { field: 'command', value: '; ls -la' },
      { field: 'input', value: '| cat /etc/hosts' }
    ];

    for (const payload of maliciousPayloads) {
      const response = await page.evaluate(async (testPayload) => {
        try {
          const body = { [testPayload.field]: testPayload.value };
          const res = await fetch('/api/portfolio/update', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': 'Bearer test-token'
            },
            body: JSON.stringify(body)
          });
          return { status: res.status, body: await res.text() };
        } catch (e) {
          return { error: e.message };
        }
      }, payload);

      // Should reject malicious input with 400 Bad Request
      expect(response.status).toBe(400);

      // Should not expose internal error details
      expect(response.body).not.toMatch(/database|sql|mongodb|mysql|postgres/i);
      expect(response.body).not.toMatch(/stack trace|internal server error/i);
    }
  });

  test('should implement proper API rate limiting', async ({ page }) => {
    await page.goto('/');

    const endpoint = '/api/portfolio/summary';
    const requests = [];

    // Make rapid requests to trigger rate limiting
    for (let i = 0; i < 20; i++) {
      const request = page.evaluate(async (url) => {
        try {
          const res = await fetch(url, {
            headers: { 'Authorization': 'Bearer test-token' }
          });
          return { status: res.status, headers: Object.fromEntries(res.headers) };
        } catch (e) {
          return { error: e.message };
        }
      }, endpoint);
      requests.push(request);
    }

    const responses = await Promise.all(requests);

    // Should have some 429 Too Many Requests responses
    const rateLimited = responses.filter(r => r.status === 429);
    expect(rateLimited.length).toBeGreaterThan(0);

    // Rate limit headers should be present
    const rateLimitResponse = rateLimited[0];
    expect(rateLimitResponse.headers['x-ratelimit-limit']).toBeTruthy();
    expect(rateLimitResponse.headers['x-ratelimit-remaining']).toBeTruthy();
  });

  test('should sanitize API responses', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForTimeout(3000);

    const apiRequests = await page.evaluate(() => window.__API_REQUESTS__);

    for (const request of apiRequests) {
      if (request.url.includes('/api/')) {
        // Test the actual response
        const response = await page.evaluate(async (url) => {
          try {
            const res = await fetch(url, {
              headers: { 'Authorization': 'Bearer test-token' }
            });
            return await res.text();
          } catch (e) {
            return null;
          }
        }, request.url);

        if (response) {
          // Responses should not contain sensitive internal information
          expect(response).not.toMatch(/password|secret|private.*key|connection.*string/i);
          expect(response).not.toMatch(/database.*host|db.*password|api.*secret/i);
          expect(response).not.toMatch(/internal.*error|stack.*trace|debug.*info/i);
        }
      }
    }
  });

  test('should validate CORS configuration', async ({ page }) => {
    await page.goto('/');

    // Test CORS with various origins
    const corsTests = [
      { origin: 'https://evil.com', shouldAllow: false },
      { origin: 'http://localhost:3000', shouldAllow: true },
      { origin: 'https://app.yourfinancialplatform.com', shouldAllow: true },
      { origin: null, shouldAllow: false }
    ];

    for (const test of corsTests) {
      const response = await page.evaluate(async (corsTest) => {
        try {
          const res = await fetch('/api/health', {
            method: 'GET',
            headers: {
              'Origin': corsTest.origin,
              'Content-Type': 'application/json'
            }
          });
          return {
            status: res.status,
            headers: Object.fromEntries(res.headers),
            corsAllowed: res.headers.get('Access-Control-Allow-Origin') !== null
          };
        } catch (e) {
          return { error: e.message };
        }
      }, test);

      if (test.shouldAllow) {
        expect(response.corsAllowed).toBe(true);
      } else {
        expect(response.corsAllowed).toBe(false);
      }
    }
  });

  test('should implement secure error handling', async ({ page }) => {
    await page.goto('/');

    const errorTriggers = [
      { endpoint: '/api/nonexistent', expectedStatus: 404 },
      { endpoint: '/api/portfolio/invalid-id', expectedStatus: 400 },
      { endpoint: '/api/orders', method: 'POST', body: 'invalid-json', expectedStatus: 400 }
    ];

    for (const trigger of errorTriggers) {
      const response = await page.evaluate(async (errorTrigger) => {
        try {
          const options = {
            method: errorTrigger.method || 'GET',
            headers: { 'Content-Type': 'application/json' }
          };

          if (errorTrigger.body) {
            options.body = errorTrigger.body;
          }

          const res = await fetch(errorTrigger.endpoint, options);
          return {
            status: res.status,
            body: await res.text(),
            headers: Object.fromEntries(res.headers)
          };
        } catch (e) {
          return { error: e.message };
        }
      }, trigger);

      expect(response.status).toBe(trigger.expectedStatus);

      // Error responses should not expose sensitive information
      expect(response.body).not.toMatch(/database|sql|internal|stack|debug/i);
      expect(response.body).not.toMatch(/password|secret|key|token/i);

      // Should have proper error format
      if (response.body && response.body.includes('{')) {
        const errorBody = JSON.parse(response.body);
        expect(errorBody.error || errorBody.message).toBeTruthy();
      }
    }
  });

  test('should validate API versioning security', async ({ page }) => {
    await page.goto('/');

    const versionTests = [
      '/api/v1/portfolio',
      '/api/v2/portfolio',
      '/api/portfolio', // Current version
      '/api/legacy/portfolio'
    ];

    for (const endpoint of versionTests) {
      const response = await page.evaluate(async (url) => {
        try {
          const res = await fetch(url, {
            headers: { 'Authorization': 'Bearer test-token' }
          });
          return {
            status: res.status,
            headers: Object.fromEntries(res.headers),
            deprecated: res.headers.get('Deprecated') !== null
          };
        } catch (e) {
          return { error: e.message };
        }
      }, endpoint);

      // Deprecated versions should be marked
      if (endpoint.includes('v1') || endpoint.includes('legacy')) {
        expect(response.deprecated || response.status === 410).toBe(true);
      }

      // All versions should require authentication
      if (response.status !== 404 && response.status !== 410) {
        expect([200, 401, 403]).toContain(response.status);
      }
    }
  });

  test('should protect against API enumeration attacks', async ({ page }) => {
    await page.goto('/');

    // Test user enumeration
    const userTests = [
      'user@example.com',
      'nonexistent@example.com',
      'admin@example.com'
    ];

    const timings = [];

    for (const email of userTests) {
      const startTime = Date.now();

      await page.evaluate(async (testEmail) => {
        try {
          await fetch('/api/auth/forgot-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: testEmail })
          });
        } catch (e) {
          // Ignore errors, we're testing timing
        }
      }, email);

      const endTime = Date.now();
      timings.push(endTime - startTime);
    }

    // Response times should be consistent (within 200ms)
    const avgTiming = timings.reduce((a, b) => a + b) / timings.length;
    const maxDeviation = Math.max(...timings.map(t => Math.abs(t - avgTiming)));
    expect(maxDeviation).toBeLessThan(200);
  });

  test('should implement proper API logging without sensitive data', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForTimeout(2000);

    // Check for log information in responses
    const response = await page.evaluate(async () => {
      try {
        const res = await fetch('/api/portfolio/summary', {
          headers: { 'Authorization': 'Bearer test-token' }
        });
        return {
          status: res.status,
          headers: Object.fromEntries(res.headers),
          body: await res.text()
        };
      } catch (e) {
        return { error: e.message };
      }
    });

    // Should not expose request IDs, trace IDs, or debug info in production
    expect(response.headers['x-request-id']).toBeFalsy();
    expect(response.headers['x-trace-id']).toBeFalsy();
    expect(response.body).not.toMatch(/debug|trace|log.*level/i);
  });

  test('should validate API content type restrictions', async ({ page }) => {
    await page.goto('/');

    const contentTypeTests = [
      { contentType: 'application/json', shouldAccept: true },
      { contentType: 'application/xml', shouldAccept: false },
      { contentType: 'text/plain', shouldAccept: false },
      { contentType: 'multipart/form-data', shouldAccept: false },
      { contentType: 'application/x-www-form-urlencoded', shouldAccept: false }
    ];

    for (const test of contentTypeTests) {
      const response = await page.evaluate(async (contentTest) => {
        try {
          const res = await fetch('/api/portfolio/update', {
            method: 'POST',
            headers: {
              'Content-Type': contentTest.contentType,
              'Authorization': 'Bearer test-token'
            },
            body: JSON.stringify({ symbol: 'AAPL', quantity: 10 })
          });
          return { status: res.status };
        } catch (e) {
          return { error: e.message };
        }
      }, test);

      if (test.shouldAccept) {
        expect([200, 400]).toContain(response.status); // 400 for validation errors is OK
      } else {
        expect(response.status).toBe(415); // Unsupported Media Type
      }
    }
  });
});