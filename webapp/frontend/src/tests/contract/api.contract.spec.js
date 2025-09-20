/**
 * API Contract Testing Suite
 * Comprehensive API contract validation and schema testing
 */

import { test, expect } from '@playwright/test';

test.describe('API Contract Validation', () => {
  test.beforeEach(async ({ page }) => {
    // Set up contract testing monitoring
    await page.addInitScript(() => {
      window.__CONTRACT_VIOLATIONS__ = [];
      window.__API_SCHEMAS__ = {};

      // Monitor API responses for contract validation
      const originalFetch = window.fetch;
      window.fetch = function(...args) {
        const url = args[0];
        const _options = args[1] || {};

        return originalFetch.apply(this, args).then(async response => {
          if (response.ok && response.headers.get('content-type')?.includes('application/json')) {
            try {
              const clonedResponse = response.clone();
              const data = await clonedResponse.json();

              window.__API_SCHEMAS__[url] = {
                status: response.status,
                headers: Object.fromEntries(response.headers),
                data: data,
                timestamp: Date.now()
              };
            } catch (e) {
              // Not valid JSON
            }
          }
          return response;
        });
      };
    });
  });

  test('should validate portfolio API contract', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    const apiSchemas = await page.evaluate(() => window.__API_SCHEMAS__);
    const portfolioApis = Object.entries(apiSchemas).filter(([url]) => url.includes('/api/portfolio'));

    for (const [_url, response] of portfolioApis) {
      // Validate response structure
      expect(response.status).toBe(200);
      expect(response.data).toBeTruthy();

      if (Array.isArray(response.data)) {
        // Portfolio items array validation
        for (const item of response.data.slice(0, 5)) {
          // Required fields
          expect(item).toHaveProperty('symbol');
          expect(typeof item.symbol).toBe('string');
          expect(item.symbol).toMatch(/^[A-Z0-9.-]{1,10}$/);

          if (item.quantity !== undefined) {
            expect(typeof item.quantity).toBe('number');
            expect(item.quantity).toBeGreaterThanOrEqual(0);
          }

          if (item.price !== undefined) {
            expect(typeof item.price).toBe('number');
            expect(item.price).toBeGreaterThan(0);
            expect(item.price).toBeLessThan(1000000);
          }

          if (item.value !== undefined) {
            expect(typeof item.value).toBe('number');
            expect(item.value).toBeGreaterThanOrEqual(0);
          }

          if (item.change !== undefined) {
            expect(typeof item.change).toBe('number');
            expect(Math.abs(item.change)).toBeLessThan(10000);
          }

          if (item.changePercent !== undefined) {
            expect(typeof item.changePercent).toBe('number');
            expect(Math.abs(item.changePercent)).toBeLessThan(1000);
          }

          if (item.lastUpdated !== undefined) {
            expect(typeof item.lastUpdated).toBe('string');
            const date = new Date(item.lastUpdated);
            expect(date.getTime()).not.toBeNaN();
          }
        }
      } else if (typeof response.data === 'object') {
        // Portfolio summary validation
        if (response.data.totalValue !== undefined) {
          expect(typeof response.data.totalValue).toBe('number');
          expect(response.data.totalValue).toBeGreaterThanOrEqual(0);
        }

        if (response.data.totalGainLoss !== undefined) {
          expect(typeof response.data.totalGainLoss).toBe('number');
        }

        if (response.data.totalGainLossPercent !== undefined) {
          expect(typeof response.data.totalGainLossPercent).toBe('number');
        }

        if (response.data.positions !== undefined) {
          expect(Array.isArray(response.data.positions)).toBe(true);
        }
      }

      // Validate response headers
      expect(response.headers['content-type']).toMatch(/application\/json/);

      if (response.headers['cache-control']) {
        expect(['no-cache', 'private', 'max-age']).toContain(
          response.headers['cache-control'].split(',')[0].trim()
        );
      }
    }
  });

  test('should validate market data API contract', async ({ page }) => {
    await page.goto('/market-overview');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    const apiSchemas = await page.evaluate(() => window.__API_SCHEMAS__);
    const marketApis = Object.entries(apiSchemas).filter(([url]) => url.includes('/api/market'));

    for (const [_url, response] of marketApis) {
      expect(response.status).toBe(200);
      expect(response.data).toBeTruthy();

      if (Array.isArray(response.data)) {
        // Market data items validation
        for (const item of response.data.slice(0, 5)) {
          // Symbol validation
          expect(item).toHaveProperty('symbol');
          expect(typeof item.symbol).toBe('string');
          expect(item.symbol).toMatch(/^[A-Z0-9.-]{1,10}$/);

          // Price validation
          if (item.price !== undefined) {
            expect(typeof item.price).toBe('number');
            expect(item.price).toBeGreaterThan(0);
            expect(item.price).toBeLessThan(1000000);
          }

          // Volume validation
          if (item.volume !== undefined) {
            expect(typeof item.volume).toBe('number');
            expect(item.volume).toBeGreaterThanOrEqual(0);
            expect(item.volume).toBeLessThan(1e12);
          }

          // Market cap validation
          if (item.marketCap !== undefined) {
            expect(typeof item.marketCap).toBe('number');
            expect(item.marketCap).toBeGreaterThan(0);
          }

          // Timestamp validation
          if (item.timestamp !== undefined) {
            expect(typeof item.timestamp).toBe('string');
            const date = new Date(item.timestamp);
            expect(date.getTime()).not.toBeNaN();

            // Should be recent (within last year)
            const yearAgo = Date.now() - (365 * 24 * 60 * 60 * 1000);
            expect(date.getTime()).toBeGreaterThan(yearAgo);
          }

          // OHLC data validation
          if (item.open !== undefined) {
            expect(typeof item.open).toBe('number');
            expect(item.open).toBeGreaterThan(0);
          }

          if (item.high !== undefined) {
            expect(typeof item.high).toBe('number');
            expect(item.high).toBeGreaterThan(0);
          }

          if (item.low !== undefined) {
            expect(typeof item.low).toBe('number');
            expect(item.low).toBeGreaterThan(0);
          }

          if (item.close !== undefined) {
            expect(typeof item.close).toBe('number');
            expect(item.close).toBeGreaterThan(0);
          }

          // OHLC consistency validation
          if (item.open && item.high && item.low && item.close) {
            expect(item.high).toBeGreaterThanOrEqual(Math.max(item.open, item.close));
            expect(item.low).toBeLessThanOrEqual(Math.min(item.open, item.close));
          }
        }
      }
    }
  });

  test('should validate user API contract', async ({ page }) => {
    await page.goto('/settings');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    const apiSchemas = await page.evaluate(() => window.__API_SCHEMAS__);
    const userApis = Object.entries(apiSchemas).filter(([url]) =>
      url.includes('/api/user') || url.includes('/api/profile')
    );

    for (const [_url, response] of userApis) {
      expect(response.status).toBe(200);
      expect(response.data).toBeTruthy();

      if (typeof response.data === 'object' && !Array.isArray(response.data)) {
        // User profile validation
        if (response.data.id !== undefined) {
          expect(typeof response.data.id).toBe('string');
          expect(response.data.id.length).toBeGreaterThan(0);
        }

        if (response.data.email !== undefined) {
          expect(typeof response.data.email).toBe('string');
          expect(response.data.email).toMatch(/^[^\s@]+@[^\s@]+\.[^\s@]+$/);
        }

        if (response.data.username !== undefined) {
          expect(typeof response.data.username).toBe('string');
          expect(response.data.username.length).toBeGreaterThan(0);
        }

        if (response.data.firstName !== undefined) {
          expect(typeof response.data.firstName).toBe('string');
        }

        if (response.data.lastName !== undefined) {
          expect(typeof response.data.lastName).toBe('string');
        }

        if (response.data.createdAt !== undefined) {
          expect(typeof response.data.createdAt).toBe('string');
          const date = new Date(response.data.createdAt);
          expect(date.getTime()).not.toBeNaN();
        }

        if (response.data.lastLogin !== undefined) {
          expect(typeof response.data.lastLogin).toBe('string');
          const date = new Date(response.data.lastLogin);
          expect(date.getTime()).not.toBeNaN();
        }

        // Sensitive fields should not be present
        expect(response.data.password).toBeUndefined();
        expect(response.data.passwordHash).toBeUndefined();
        expect(response.data.salt).toBeUndefined();
        expect(response.data.apiKey).toBeUndefined();
        expect(response.data.internalId).toBeUndefined();
      }
    }
  });

  test('should validate analytics API contract', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    const apiSchemas = await page.evaluate(() => window.__API_SCHEMAS__);
    const analyticsApis = Object.entries(apiSchemas).filter(([url]) =>
      url.includes('/api/analytics') || url.includes('/api/performance')
    );

    for (const [_url, response] of analyticsApis) {
      expect(response.status).toBe(200);
      expect(response.data).toBeTruthy();

      if (typeof response.data === 'object') {
        // Performance metrics validation
        if (response.data.totalReturn !== undefined) {
          expect(typeof response.data.totalReturn).toBe('number');
          expect(Math.abs(response.data.totalReturn)).toBeLessThan(10000);
        }

        if (response.data.dailyReturn !== undefined) {
          expect(typeof response.data.dailyReturn).toBe('number');
          expect(Math.abs(response.data.dailyReturn)).toBeLessThan(100);
        }

        if (response.data.sharpeRatio !== undefined) {
          expect(typeof response.data.sharpeRatio).toBe('number');
          expect(Math.abs(response.data.sharpeRatio)).toBeLessThan(100);
        }

        if (response.data.volatility !== undefined) {
          expect(typeof response.data.volatility).toBe('number');
          expect(response.data.volatility).toBeGreaterThanOrEqual(0);
          expect(response.data.volatility).toBeLessThan(1000);
        }

        if (response.data.maxDrawdown !== undefined) {
          expect(typeof response.data.maxDrawdown).toBe('number');
          expect(response.data.maxDrawdown).toBeLessThanOrEqual(0);
          expect(response.data.maxDrawdown).toBeGreaterThan(-100);
        }

        if (response.data.beta !== undefined) {
          expect(typeof response.data.beta).toBe('number');
          expect(Math.abs(response.data.beta)).toBeLessThan(10);
        }

        if (response.data.alpha !== undefined) {
          expect(typeof response.data.alpha).toBe('number');
          expect(Math.abs(response.data.alpha)).toBeLessThan(1000);
        }

        // Time series data validation
        if (response.data.timeSeries !== undefined) {
          expect(Array.isArray(response.data.timeSeries)).toBe(true);

          for (const point of response.data.timeSeries.slice(0, 5)) {
            expect(point).toHaveProperty('timestamp');
            expect(point).toHaveProperty('value');

            expect(typeof point.timestamp).toBe('string');
            const date = new Date(point.timestamp);
            expect(date.getTime()).not.toBeNaN();

            expect(typeof point.value).toBe('number');
            expect(isFinite(point.value)).toBe(true);
          }
        }
      }
    }
  });

  test('should validate error response contracts', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Test various error scenarios
    const errorTests = [
      { endpoint: '/api/nonexistent', expectedStatus: 404 },
      { endpoint: '/api/portfolio/invalid-id', expectedStatus: 400 },
      { endpoint: '/api/unauthorized', expectedStatus: 401 }
    ];

    for (const test of errorTests) {
      const errorResponse = await page.evaluate(async (testData) => {
        try {
          const response = await fetch(testData.endpoint);
          return {
            status: response.status,
            headers: Object.fromEntries(response.headers),
            data: await response.json().catch(() => response.text())
          };
        } catch (error) {
          return {
            error: error.message,
            networkError: true
          };
        }
      }, test);

      if (!errorResponse.networkError) {
        expect(errorResponse.status).toBe(test.expectedStatus);

        // Error response should have proper structure
        if (typeof errorResponse.data === 'object') {
          // Should have error message
          expect(
            errorResponse.data.error ||
            errorResponse.data.message ||
            errorResponse.data.detail
          ).toBeTruthy();

          // Should not expose sensitive information
          const errorString = JSON.stringify(errorResponse.data).toLowerCase();
          expect(errorString).not.toMatch(/password|secret|key|token|internal|stack|database/);

          // Should have proper error code if present
          if (errorResponse.data.code !== undefined) {
            expect(typeof errorResponse.data.code).toBe('string');
            expect(errorResponse.data.code.length).toBeGreaterThan(0);
          }

          // Should have timestamp if present
          if (errorResponse.data.timestamp !== undefined) {
            const date = new Date(errorResponse.data.timestamp);
            expect(date.getTime()).not.toBeNaN();
          }
        }

        // Error response headers should be appropriate
        expect(errorResponse.headers['content-type']).toMatch(/application\/json|text\/plain/);
      }
    }
  });

  test('should validate pagination contracts', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);

    // Look for pagination parameters in API calls
    const paginationTest = await page.evaluate(async () => {
      try {
        const response = await fetch('/api/portfolio?page=1&limit=10&offset=0');
        if (response.ok) {
          const data = await response.json();
          return {
            status: response.status,
            headers: Object.fromEntries(response.headers),
            data: data
          };
        }
        return null;
      } catch (error) {
        return null;
      }
    });

    if (paginationTest && paginationTest.data) {
      const data = paginationTest.data;

      // Pagination metadata validation
      if (data.pagination !== undefined) {
        expect(typeof data.pagination).toBe('object');

        if (data.pagination.page !== undefined) {
          expect(typeof data.pagination.page).toBe('number');
          expect(data.pagination.page).toBeGreaterThan(0);
        }

        if (data.pagination.limit !== undefined) {
          expect(typeof data.pagination.limit).toBe('number');
          expect(data.pagination.limit).toBeGreaterThan(0);
          expect(data.pagination.limit).toBeLessThanOrEqual(1000);
        }

        if (data.pagination.total !== undefined) {
          expect(typeof data.pagination.total).toBe('number');
          expect(data.pagination.total).toBeGreaterThanOrEqual(0);
        }

        if (data.pagination.totalPages !== undefined) {
          expect(typeof data.pagination.totalPages).toBe('number');
          expect(data.pagination.totalPages).toBeGreaterThanOrEqual(0);
        }

        if (data.pagination.hasNext !== undefined) {
          expect(typeof data.pagination.hasNext).toBe('boolean');
        }

        if (data.pagination.hasPrev !== undefined) {
          expect(typeof data.pagination.hasPrev).toBe('boolean');
        }
      }

      // Data array should respect limit
      if (Array.isArray(data.data || data.items || data.results)) {
        const items = data.data || data.items || data.results;
        expect(items.length).toBeLessThanOrEqual(10); // Requested limit
      }
    }
  });

  test('should validate rate limiting contracts', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Make rapid requests to test rate limiting
    const rateLimitTests = [];
    const endpoint = '/api/health';

    for (let i = 0; i < 10; i++) {
      const test = page.evaluate(async (url) => {
        try {
          const response = await fetch(url);
          return {
            status: response.status,
            headers: Object.fromEntries(response.headers),
            timestamp: Date.now()
          };
        } catch (error) {
          return {
            error: error.message,
            timestamp: Date.now()
          };
        }
      }, endpoint);

      rateLimitTests.push(test);
    }

    const results = await Promise.all(rateLimitTests);

    // Check for rate limiting responses
    const rateLimitedResponses = results.filter(r => r.status === 429);

    if (rateLimitedResponses.length > 0) {
      for (const response of rateLimitedResponses) {
        // Rate limit headers should be present
        expect(
          response.headers['x-ratelimit-limit'] ||
          response.headers['x-ratelimit-remaining'] ||
          response.headers['retry-after']
        ).toBeTruthy();

        // Retry-After header should be reasonable
        if (response.headers['retry-after']) {
          const retryAfter = parseInt(response.headers['retry-after']);
          expect(retryAfter).toBeGreaterThan(0);
          expect(retryAfter).toBeLessThan(3600); // Less than 1 hour
        }
      }
    }
  });

  test('should validate API versioning contracts', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    const apiSchemas = await page.evaluate(() => window.__API_SCHEMAS__);

    for (const [url, response] of Object.entries(apiSchemas)) {
      if (url.includes('/api/')) {
        // API version should be specified in URL or headers
        const hasVersionInUrl = /\/api\/v\d+\//.test(url) || /\/api\/\d+\//.test(url);
        const hasVersionHeader = response.headers['api-version'] || response.headers['x-api-version'];

        // At least one versioning method should be present for production APIs
        if (!url.includes('/health') && !url.includes('/status')) {
          expect(hasVersionInUrl || hasVersionHeader).toBe(true);
        }

        // Version header format validation
        if (hasVersionHeader) {
          const versionHeader = response.headers['api-version'] || response.headers['x-api-version'];
          expect(versionHeader).toMatch(/^\d+(\.\d+)*$/); // Semantic versioning
        }

        // Deprecated API warning
        if (response.headers['deprecated'] || response.headers['sunset']) {
          console.log(`Deprecated API detected: ${url}`);

          if (response.headers['sunset']) {
            const sunsetDate = new Date(response.headers['sunset']);
            expect(sunsetDate.getTime()).not.toBeNaN();
          }
        }
      }
    }
  });

  test('should validate data consistency across related APIs', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    const apiSchemas = await page.evaluate(() => window.__API_SCHEMAS__);

    // Extract portfolio data from different endpoints
    const portfolioSummary = Object.entries(apiSchemas).find(([url]) =>
      url.includes('/api/portfolio/summary') || url.includes('/api/portfolio/totals')
    );

    const portfolioItems = Object.entries(apiSchemas).find(([url]) =>
      url.includes('/api/portfolio') && !url.includes('summary') && !url.includes('totals')
    );

    if (portfolioSummary && portfolioItems) {
      const [, summaryResponse] = portfolioSummary;
      const [, itemsResponse] = portfolioItems;

      // Data consistency validation
      if (summaryResponse.data && itemsResponse.data && Array.isArray(itemsResponse.data)) {
        const items = itemsResponse.data;
        const summary = summaryResponse.data;

        // Calculate totals from items
        const calculatedTotal = items.reduce((sum, item) => {
          const value = (item.quantity || 0) * (item.price || 0);
          return sum + value;
        }, 0);

        // Compare with summary total (allow for reasonable variance due to timing)
        if (summary.totalValue !== undefined && calculatedTotal > 0) {
          const variance = Math.abs(summary.totalValue - calculatedTotal) / calculatedTotal;
          expect(variance).toBeLessThan(0.1); // 10% variance allowed
        }

        // Symbol consistency
        const itemSymbols = new Set(items.map(item => item.symbol).filter(Boolean));

        if (summary.positions && Array.isArray(summary.positions)) {
          const summarySymbols = new Set(summary.positions.map(pos => pos.symbol).filter(Boolean));

          // Summary should not have symbols not in items
          for (const symbol of summarySymbols) {
            expect(itemSymbols.has(symbol)).toBe(true);
          }
        }
      }
    }
  });
});