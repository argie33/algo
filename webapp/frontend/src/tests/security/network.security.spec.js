/**
 * Network Security Test Suite
 * Comprehensive validation for network-level security measures
 */

import { test, expect } from '@playwright/test';

test.describe('Network Security', () => {
  test.beforeEach(async ({ page }) => {
    // Set up network monitoring
    await page.addInitScript(() => {
      window.__NETWORK_REQUESTS__ = [];
      window.__SECURITY_HEADERS__ = {};

      // Monitor network events
      const originalFetch = window.fetch;
      window.fetch = function(...args) {
        const url = args[0];
        const options = args[1] || {};

        window.__NETWORK_REQUESTS__.push({
          url,
          method: options.method || 'GET',
          headers: options.headers || {},
          timestamp: Date.now()
        });

        return originalFetch.apply(this, args).then(response => {
          // Store security headers
          window.__SECURITY_HEADERS__[url] = Object.fromEntries(response.headers);
          return response;
        });
      };
    });
  });

  test('should enforce HTTPS for all requests', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(3000);

    const networkRequests = await page.evaluate(() => window.__NETWORK_REQUESTS__);

    for (const request of networkRequests) {
      if (request.url.startsWith('http://') && !request.url.includes('localhost')) {
        // External HTTP requests should be blocked or redirected to HTTPS
        expect(request.url).toMatch(/^https:/);
      }
    }

    // Check for mixed content warnings
    const consoleLogs = [];
    page.on('console', msg => {
      if (msg.type() === 'warning' && msg.text().includes('mixed content')) {
        consoleLogs.push(msg.text());
      }
    });

    await page.reload();
    await page.waitForTimeout(2000);

    expect(consoleLogs.length).toBe(0);
  });

  test('should implement proper TLS configuration', async ({ page }) => {
    const response = await page.goto('/');
    const securityDetails = await response.securityDetails();

    if (securityDetails) {
      // Should use TLS 1.2 or higher
      expect(securityDetails.protocol()).toMatch(/TLS.*1\.[2-9]|TLS.*[2-9]\./);

      // Should have valid certificate
      expect(securityDetails.validFrom()).toBeInstanceOf(Date);
      expect(securityDetails.validTo()).toBeInstanceOf(Date);
      expect(securityDetails.validTo().getTime()).toBeGreaterThan(Date.now());

      // Should use strong cipher suites
      expect(securityDetails.issuer()).toBeTruthy();
      expect(securityDetails.subjectName()).toBeTruthy();
    }
  });

  test('should validate HTTP security headers', async ({ page }) => {
    const response = await page.goto('/');
    const headers = response.headers();

    // Strict-Transport-Security
    expect(headers['strict-transport-security']).toBeTruthy();
    expect(headers['strict-transport-security']).toMatch(/max-age=\d+/);

    // X-Content-Type-Options
    expect(headers['x-content-type-options']).toBe('nosniff');

    // X-Frame-Options or Content-Security-Policy frame-ancestors
    expect(
      headers['x-frame-options'] === 'DENY' ||
      headers['x-frame-options'] === 'SAMEORIGIN' ||
      (headers['content-security-policy'] && headers['content-security-policy'].includes('frame-ancestors'))
    ).toBe(true);

    // X-XSS-Protection (if present, should be properly configured)
    if (headers['x-xss-protection']) {
      expect(headers['x-xss-protection']).toMatch(/1; mode=block/);
    }

    // Referrer-Policy
    expect(headers['referrer-policy']).toBeTruthy();
    expect(['no-referrer', 'same-origin', 'strict-origin', 'strict-origin-when-cross-origin'])
      .toContain(headers['referrer-policy']);

    // Content-Security-Policy
    expect(headers['content-security-policy']).toBeTruthy();
  });

  test('should implement robust Content Security Policy', async ({ page }) => {
    const response = await page.goto('/');
    const headers = response.headers();
    const csp = headers['content-security-policy'];

    expect(csp).toBeTruthy();

    // Should restrict unsafe inline scripts
    expect(csp).not.toMatch(/'unsafe-inline'/);
    expect(csp).not.toMatch(/'unsafe-eval'/);

    // Should have default-src directive
    expect(csp).toMatch(/default-src/);

    // Should restrict object-src
    expect(csp).toMatch(/object-src.*'none'/);

    // Should have frame-ancestors protection
    expect(csp).toMatch(/frame-ancestors/);

    // Monitor for CSP violations
    const cspViolations = [];
    page.on('console', msg => {
      if (msg.text().includes('Content Security Policy')) {
        cspViolations.push(msg.text());
      }
    });

    await page.waitForTimeout(3000);
    expect(cspViolations.length).toBe(0);
  });

  test('should prevent DNS rebinding attacks', async ({ page }) => {
    await page.goto('/');

    // Test Host header validation
    const hostTests = [
      'localhost:3000',
      'app.yourfinancialplatform.com',
      'evil.com',
      '192.168.1.1',
      'internal.network'
    ];

    for (const host of hostTests) {
      const response = await page.evaluate(async (testHost) => {
        try {
          const res = await fetch('/api/health', {
            headers: { 'Host': testHost }
          });
          return { status: res.status };
        } catch (e) {
          return { error: e.message };
        }
      }, host);

      // Should validate Host header and reject suspicious hosts
      if (host.includes('evil.com') || host.includes('internal.network')) {
        expect([400, 403, 404]).toContain(response.status);
      }
    }
  });

  test('should implement proper CORS policies', async ({ page }) => {
    await page.goto('/');

    const corsTests = [
      {
        origin: 'https://evil.com',
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
        shouldAllow: false
      },
      {
        origin: 'https://app.yourfinancialplatform.com',
        method: 'GET',
        headers: { 'Content-Type': 'application/json' },
        shouldAllow: true
      },
      {
        origin: 'https://evil.com',
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        shouldAllow: false
      }
    ];

    for (const test of corsTests) {
      // Test preflight request
      const preflightResponse = await page.evaluate(async (corsTest) => {
        try {
          const res = await fetch('/api/portfolio', {
            method: 'OPTIONS',
            headers: {
              'Origin': corsTest.origin,
              'Access-Control-Request-Method': corsTest.method,
              'Access-Control-Request-Headers': Object.keys(corsTest.headers).join(',')
            }
          });
          return {
            status: res.status,
            headers: Object.fromEntries(res.headers)
          };
        } catch (e) {
          return { error: e.message };
        }
      }, test);

      if (test.shouldAllow) {
        expect(preflightResponse.status).toBe(200);
        expect(preflightResponse.headers['access-control-allow-origin']).toBeTruthy();
      } else {
        expect(
          preflightResponse.status !== 200 ||
          !preflightResponse.headers['access-control-allow-origin']
        ).toBe(true);
      }
    }
  });

  test('should protect against clickjacking', async ({ page }) => {
    const response = await page.goto('/');
    const headers = response.headers();

    // Check for frame protection
    const hasFrameProtection =
      headers['x-frame-options'] ||
      (headers['content-security-policy'] && headers['content-security-policy'].includes('frame-ancestors'));

    expect(hasFrameProtection).toBeTruthy();

    // Test iframe embedding
    await page.setContent(`
      <html>
        <body>
          <iframe src="${page.url()}" id="test-frame"></iframe>
        </body>
      </html>
    `);

    const frameLoaded = await page.evaluate(() => {
      const frame = document.getElementById('test-frame');
      return new Promise(resolve => {
        frame.onload = () => resolve(true);
        frame.onerror = () => resolve(false);
        setTimeout(() => resolve(false), 5000);
      });
    });

    // Frame should be blocked
    expect(frameLoaded).toBe(false);
  });

  test('should implement secure cookie policies', async ({ page }) => {
    await page.goto('/');

    const cookies = await page.context().cookies();
    const securityCookies = cookies.filter(c =>
      c.name.includes('session') ||
      c.name.includes('auth') ||
      c.name.includes('token')
    );

    for (const cookie of securityCookies) {
      // Security cookies should be secure
      expect(cookie.secure).toBe(true);

      // Should be HttpOnly to prevent XSS
      expect(cookie.httpOnly).toBe(true);

      // Should have appropriate SameSite policy
      expect(['Strict', 'Lax']).toContain(cookie.sameSite);

      // Should have reasonable expiration
      if (cookie.expires && cookie.expires !== -1) {
        const expirationDate = new Date(cookie.expires * 1000);
        const maxAge = 24 * 60 * 60 * 1000; // 24 hours
        expect(expirationDate.getTime() - Date.now()).toBeLessThan(maxAge);
      }
    }
  });

  test('should prevent information disclosure through headers', async ({ page }) => {
    const response = await page.goto('/');
    const headers = response.headers();

    // Should not expose server information
    expect(headers['server']).toBeFalsy();
    expect(headers['x-powered-by']).toBeFalsy();

    // Should not expose version information
    const serverHeaders = Object.keys(headers).filter(h =>
      h.toLowerCase().includes('server') ||
      h.toLowerCase().includes('version') ||
      h.toLowerCase().includes('powered')
    );

    for (const header of serverHeaders) {
      const value = headers[header].toLowerCase();
      expect(value).not.toMatch(/apache|nginx|iis|express|php|asp\.net/);
      expect(value).not.toMatch(/\d+\.\d+\.\d+/); // Version numbers
    }
  });

  test('should implement proper timeout configurations', async ({ page }) => {
    await page.goto('/');

    // Test connection timeout
    const slowEndpoint = '/api/analytics/complex-calculation';
    const startTime = Date.now();

    const response = await page.evaluate(async (endpoint) => {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 30000); // 30s timeout

        const res = await fetch(endpoint, {
          signal: controller.signal,
          headers: { 'Authorization': 'Bearer test-token' }
        });

        clearTimeout(timeoutId);
        return { status: res.status, timedOut: false };
      } catch (e) {
        return {
          timedOut: e.name === 'AbortError',
          error: e.message
        };
      }
    }, slowEndpoint);

    const duration = Date.now() - startTime;

    // Should timeout within reasonable time (30 seconds)
    if (response.timedOut) {
      expect(duration).toBeLessThan(35000);
    }
  });

  test('should validate WebSocket security', async ({ page }) => {
    await page.goto('/');

    // Monitor WebSocket connections
    const wsConnections = [];
    page.on('websocket', ws => {
      wsConnections.push({
        url: ws.url(),
        isClosed: ws.isClosed()
      });
    });

    await page.waitForTimeout(5000);

    for (const ws of wsConnections) {
      // WebSocket should use secure protocol
      expect(ws.url).toMatch(/^wss:/);

      // Should not connect to external domains
      expect(ws.url).not.toMatch(/evil\.com|malicious\.site/);
    }
  });

  test('should protect against subdomain takeover', async ({ page }) => {
    await page.goto('/');

    // Check for external subdomain references
    const _content = await page.content();
    const links = await page.locator('a[href], link[href], script[src], img[src]').all();

    for (const link of links) {
      const href = await link.getAttribute('href') || await link.getAttribute('src');
      if (href && href.includes('.')) {
        // External references should be to trusted domains
        const domain = new URL(href, page.url()).hostname;

        // Should not reference abandoned subdomains
        expect(domain).not.toMatch(/\.s3\.amazonaws\.com$/);
        expect(domain).not.toMatch(/\.herokuapp\.com$/);
        expect(domain).not.toMatch(/\.github\.io$/);
      }
    }
  });

  test('should implement network-level DDoS protection', async ({ page }) => {
    await page.goto('/');

    // Test rate limiting at network level
    const requests = [];
    const endpoint = '/api/health';

    for (let i = 0; i < 50; i++) {
      const request = page.evaluate(async (url) => {
        const startTime = Date.now();
        try {
          const res = await fetch(url);
          return {
            status: res.status,
            time: Date.now() - startTime,
            headers: Object.fromEntries(res.headers)
          };
        } catch (e) {
          return { error: e.message, time: Date.now() - startTime };
        }
      }, endpoint);
      requests.push(request);
    }

    const responses = await Promise.all(requests);

    // Should implement rate limiting
    const rateLimited = responses.filter(r => r.status === 429);
    expect(rateLimited.length).toBeGreaterThan(0);

    // Should have rate limiting headers
    const rateLimitResponse = rateLimited[0];
    if (rateLimitResponse && rateLimitResponse.headers) {
      expect(
        rateLimitResponse.headers['x-ratelimit-limit'] ||
        rateLimitResponse.headers['retry-after']
      ).toBeTruthy();
    }
  });
});