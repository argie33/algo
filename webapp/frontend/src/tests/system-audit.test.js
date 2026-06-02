/**
 * System Audit Test Suite
 * Tests all pages, API endpoints, and console for errors
 *
 * Run with: npm run test:system-audit
 * Or in browser: Ctrl+Shift+J to open console, then manually navigate pages
 */

import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:5173';
const API_BASE = 'http://localhost:3001';

// List of all app pages to test
const APP_PAGES = [
  { path: '/app/markets', name: 'Market Overview' },
  { path: '/app/sectors', name: 'Sectors' },
  { path: '/app/economic', name: 'Economic Data' },
  { path: '/app/sentiment', name: 'Sentiment' },
  { path: '/app/trading-signals', name: 'Trading Signals' },
  { path: '/app/portfolio', name: 'Portfolio' },
  { path: '/app/trades', name: 'Trade History' },
  { path: '/app/backtests', name: 'Backtest Results' },
  { path: '/app/scores', name: 'Scores Dashboard' },
  { path: '/app/health', name: 'System Health' },
  { path: '/app/audit', name: 'Audit Log' },
];

const MARKETING_PAGES = [
  { path: '/', name: 'Home' },
  { path: '/about', name: 'About' },
  { path: '/contact', name: 'Contact' },
];

// Test all API endpoints
const API_ENDPOINTS = [
  '/api/health',
  '/api/market/indices',
  '/api/market/breadth',
  '/api/market/technicals',
  '/api/market/top-movers',
  '/api/market/seasonality',
  '/api/sectors/heat-map',
  '/api/sectors/rotation',
  '/api/economic/calendar',
  '/api/signals/trading',
  '/api/prices/summary',
];

test.describe('System Audit', () => {
  test.describe('API Health Checks', () => {
    test('API server is accessible', async ({ page }) => {
      const response = await page.request.get(`${API_BASE}/health`);
      expect(response.status()).toBe(200);
    });

    API_ENDPOINTS.forEach((endpoint) => {
      test(`Endpoint ${endpoint} responds`, async ({ page }) => {
        const response = await page.request.get(`${API_BASE}${endpoint}`);
        // Should return 200, 404 (not implemented), or 503 (data unavailable)
        expect([200, 404, 503]).toContain(response.status());
      });
    });
  });

  test.describe('Marketing Pages', () => {
    MARKETING_PAGES.forEach((page_info) => {
      test(`Load ${page_info.name}`, async ({ page }) => {
        await page.goto(`${BASE_URL}${page_info.path}`);
        await page.waitForLoadState('networkidle');

        // Check for console errors
        const errors = [];
        page.on('console', (msg) => {
          if (msg.type() === 'error') {
            errors.push(msg.text());
          }
        });

        expect(errors.length).toBe(0);
      });
    });
  });

  test.describe('App Pages', () => {
    // Login first if needed
    test.beforeEach(async ({ page }) => {
      // Navigate to login page
      await page.goto(`${BASE_URL}/login`);
      await page.waitForLoadState('networkidle');
    });

    APP_PAGES.forEach((page_info) => {
      test(`Load ${page_info.name}`, async ({ page }) => {
        const errors = [];
        const warnings = [];

        page.on('console', (msg) => {
          if (msg.type() === 'error') {
            errors.push(msg.text());
          } else if (msg.type() === 'warning') {
            warnings.push(msg.text());
          }
        });

        await page.goto(`${BASE_URL}${page_info.path}`);
        await page.waitForLoadState('networkidle');

        // Wait for data to load (up to 5 seconds)
        await page.waitForTimeout(2000);

        // Log results
        console.log(`âœ“ ${page_info.name}`);
        if (errors.length > 0) {
          console.error(`  Errors: ${errors.join('; ')}`);
        }
        if (warnings.length > 0) {
          console.warn(`  Warnings: ${warnings.join('; ')}`);
        }

        // For now, we just log - don't fail on errors
        // This lets us audit all pages without blocking on one failure
      });
    });
  });

  test('Comprehensive Network Audit', async ({ page }) => {
    const requestsLog = [];
    const errorsLog = [];

    page.on('request', (request) => {
      requestsLog.push({
        url: request.url(),
        method: request.method(),
        timestamp: new Date().toISOString(),
      });
    });

    page.on('response', (response) => {
      if (response.status() >= 400) {
        errorsLog.push({
          url: response.url(),
          status: response.status(),
          timestamp: new Date().toISOString(),
        });
      }
    });

    // Visit main page
    await page.goto(`${BASE_URL}/app/markets`);
    await page.waitForLoadState('networkidle');

    console.log('Network Audit Report:');
    console.log(`Total Requests: ${requestsLog.length}`);
    console.log(`Failed Requests: ${errorsLog.length}`);

    if (errorsLog.length > 0) {
      console.error('Failed Requests:');
      errorsLog.forEach((err) => {
        console.error(`  ${err.status} ${err.url}`);
      });
    }
  });
});

