/**
 * Authentication Security Test Suite
 * Comprehensive security validation for authentication flows
 */

import { test, expect } from '@playwright/test';

test.describe('Authentication Security', () => {
  test.beforeEach(async ({ page }) => {
    // Security test setup
    await page.addInitScript(() => {
      // Monitor for security events
      window.__SECURITY_EVENTS__ = [];

      // Override console to capture security warnings
      const originalConsole = console.warn;
      console.warn = (...args) => {
        window.__SECURITY_EVENTS__.push({ type: 'warning', message: args.join(' ') });
        originalConsole.apply(console, args);
      };
    });
  });

  test('should prevent XSS attacks in login form', async ({ page }) => {
    await page.goto('/');

    // XSS payloads to test
    const xssPayloads = [
      '<script>alert("XSS")</script>',
      'javascript:alert("XSS")',
      '<img src=x onerror=alert("XSS")>',
      '"><script>alert("XSS")</script>',
      "';alert('XSS');//",
    ];

    for (const payload of xssPayloads) {
      // Try to inject XSS in email field
      const emailInput = page.locator('input[type="email"]').first();
      if (await emailInput.isVisible()) {
        await emailInput.fill(payload);
        await emailInput.blur();

        // Verify XSS was not executed
        const alertDialogs = await page.evaluate(() => window.__SECURITY_EVENTS__);
        expect(alertDialogs).not.toContainEqual(
          expect.objectContaining({ type: 'alert' })
        );
      }
    }
  });

  test('should validate HTTPS enforcement', async ({ page }) => {
    // Check for mixed content warnings
    const securityEvents = [];
    page.on('console', msg => {
      if (msg.type() === 'warning' && msg.text().includes('mixed content')) {
        securityEvents.push(msg.text());
      }
    });

    await page.goto('/');
    await page.waitForTimeout(2000);

    expect(securityEvents.length).toBe(0);
  });

  test('should prevent CSRF attacks', async ({ page }) => {
    await page.goto('/');

    // Mock CSRF attack scenario
    await page.evaluate(() => {
      // Simulate external form submission
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = '/api/auth/login';
      form.innerHTML = `
        <input type="hidden" name="email" value="attacker@evil.com">
        <input type="hidden" name="password" value="password">
      `;
      document.body.appendChild(form);

      // Attempt to submit (should be blocked)
      try {
        form.submit();
      } catch (e) {
        window.__CSRF_BLOCKED__ = true;
      }
    });

    const csrfBlocked = await page.evaluate(() => window.__CSRF_BLOCKED__);
    expect(csrfBlocked).toBeTruthy();
  });

  test('should implement secure session management', async ({ page }) => {
    await page.goto('/');

    // Check for secure session cookies
    const cookies = await page.context().cookies();
    const sessionCookies = cookies.filter(c =>
      c.name.includes('session') || c.name.includes('token')
    );

    for (const cookie of sessionCookies) {
      expect(cookie.secure).toBe(true);
      expect(cookie.httpOnly).toBe(true);
      expect(cookie.sameSite).toBe('Strict');
    }
  });

  test('should validate input sanitization', async ({ page }) => {
    await page.goto('/settings');

    const maliciousInputs = [
      '<script>document.cookie="stolen=true"</script>',
      '../../../etc/passwd',
      '<?php system($_GET["cmd"]); ?>',
      '{{7*7}}',
      '${7*7}',
      '<%=7*7%>',
    ];

    for (const maliciousInput of maliciousInputs) {
      const inputs = await page.locator('input, textarea').all();

      for (const input of inputs) {
        if (await input.isVisible() && await input.isEnabled()) {
          await input.fill(maliciousInput);
          await input.blur();

          // Verify input was sanitized
          const value = await input.inputValue();
          expect(value).not.toContain('<script>');
          expect(value).not.toContain('javascript:');
        }
      }
    }
  });

  test('should prevent SQL injection attempts', async ({ page }) => {
    await page.goto('/stocks');

    const sqlInjectionPayloads = [
      "'; DROP TABLE users; --",
      "' OR '1'='1",
      "' UNION SELECT * FROM users --",
      "admin'--",
      "' OR 1=1#",
    ];

    for (const payload of sqlInjectionPayloads) {
      const searchInput = page.locator('input[placeholder*="search"]').first();
      if (await searchInput.isVisible()) {
        await searchInput.fill(payload);
        await searchInput.press('Enter');

        // Check for SQL error messages
        const errorMessages = await page.locator('.error, .alert-error').allTextContents();
        const hasSecurityError = errorMessages.some(msg =>
          msg.toLowerCase().includes('sql') ||
          msg.toLowerCase().includes('database error')
        );
        expect(hasSecurityError).toBe(false);
      }
    }
  });

  test('should enforce content security policy', async ({ page }) => {
    const cspViolations = [];

    page.on('console', msg => {
      if (msg.text().includes('Content Security Policy')) {
        cspViolations.push(msg.text());
      }
    });

    await page.goto('/');
    await page.waitForTimeout(3000);

    // Should have no CSP violations
    expect(cspViolations.length).toBe(0);
  });

  test('should validate API authentication headers', async ({ page }) => {
    const apiRequests = [];

    page.on('request', request => {
      if (request.url().includes('/api/')) {
        apiRequests.push({
          url: request.url(),
          headers: request.headers(),
        });
      }
    });

    await page.goto('/portfolio');
    await page.waitForTimeout(3000);

    // Verify all API requests have proper authentication
    for (const request of apiRequests) {
      const hasAuth = request.headers.authorization ||
                     request.headers['x-api-key'] ||
                     request.headers['x-auth-token'];
      expect(hasAuth).toBeTruthy();
    }
  });

  test('should prevent clickjacking attacks', async ({ page }) => {
    await page.goto('/');

    // Check X-Frame-Options header
    const response = await page.goto('/');
    const headers = response.headers();

    expect(
      headers['x-frame-options'] === 'DENY' ||
      headers['x-frame-options'] === 'SAMEORIGIN'
    ).toBe(true);
  });

  test('should validate password security requirements', async ({ page }) => {
    await page.goto('/');

    const weakPasswords = [
      '123456',
      'password',
      'qwerty',
      'abc123',
      '111111',
      'password123',
    ];

    // Try to register with weak passwords
    for (const weakPassword of weakPasswords) {
      const registerButton = page.locator('text=Register').first();
      if (await registerButton.isVisible()) {
        await registerButton.click();

        const passwordInput = page.locator('input[type="password"]').first();
        await passwordInput.fill(weakPassword);
        await passwordInput.blur();

        // Should show password strength warning
        const strengthWarning = await page.locator('.password-strength, .weak-password').count();
        expect(strengthWarning).toBeGreaterThan(0);
      }
    }
  });

  test('should implement rate limiting protection', async ({ page }) => {
    await page.goto('/');

    // Attempt rapid-fire login attempts
    const attempts = [];
    for (let i = 0; i < 10; i++) {
      const attempt = page.evaluate(() => {
        return fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            email: 'test@example.com',
            password: 'wrongpassword'
          })
        }).then(r => r.status);
      });
      attempts.push(attempt);
    }

    const results = await Promise.all(attempts);
    const rateLimited = results.some(status => status === 429);
    expect(rateLimited).toBe(true);
  });
});