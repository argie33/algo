/**
 * Data Protection Security Test Suite
 * Comprehensive validation for data security and privacy
 */

import { test, expect } from '@playwright/test';

test.describe('Data Protection Security', () => {
  test.beforeEach(async ({ page }) => {
    // Set up security monitoring
    await page.addInitScript(() => {
      window.__DATA_LEAKS__ = [];
      window.__SENSITIVE_DATA__ = [];

      // Monitor for sensitive data exposure
      const originalFetch = window.fetch;
      window.fetch = function(...args) {
        const url = args[0];
        const options = args[1] || {};

        // Check for sensitive data in requests
        if (options.body) {
          const body = typeof options.body === 'string' ? options.body : JSON.stringify(options.body);
          if (body.includes('password') || body.includes('ssn') || body.includes('credit')) {
            window.__SENSITIVE_DATA__.push({ url, body });
          }
        }

        return originalFetch.apply(this, args);
      };
    });
  });

  test('should not expose sensitive data in client-side storage', async ({ page }) => {
    await page.goto('/settings');

    // Check localStorage for sensitive data
    const localStorageData = await page.evaluate(() => {
      const data = {};
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        data[key] = localStorage.getItem(key);
      }
      return data;
    });

    // Check sessionStorage for sensitive data
    const sessionStorageData = await page.evaluate(() => {
      const data = {};
      for (let i = 0; i < sessionStorage.length; i++) {
        const key = sessionStorage.key(i);
        data[key] = sessionStorage.getItem(key);
      }
      return data;
    });

    const sensitivePatterns = [
      /password/i,
      /credit.*card/i,
      /social.*security/i,
      /ssn/i,
      /secret.*key/i,
      /private.*key/i,
    ];

    // Verify no sensitive data in storage
    for (const [key, value] of Object.entries({ ...localStorageData, ...sessionStorageData })) {
      for (const pattern of sensitivePatterns) {
        expect(value).not.toMatch(pattern);
        expect(key).not.toMatch(pattern);
      }
    }
  });

  test('should encrypt sensitive data in transit', async ({ page }) => {
    const apiRequests = [];

    page.on('request', request => {
      if (request.url().includes('/api/')) {
        apiRequests.push({
          url: request.url(),
          method: request.method(),
          postData: request.postData(),
          headers: request.headers(),
        });
      }
    });

    await page.goto('/portfolio');
    await page.waitForTimeout(3000);

    // Verify all API requests use HTTPS
    for (const request of apiRequests) {
      expect(request.url).toMatch(/^https:/);
    }

    // Verify sensitive data is not in plain text
    for (const request of apiRequests) {
      if (request.postData) {
        expect(request.postData).not.toMatch(/password.*:/);
        expect(request.postData).not.toMatch(/creditCard.*:/);
      }
    }
  });

  test('should sanitize user input to prevent data injection', async ({ page }) => {
    await page.goto('/settings');

    const maliciousData = [
      'user@example.com<script>steal()</script>',
      'John<iframe src="evil.com"></iframe>Doe',
      'Company"onload="alert(1)',
      'Description\\x00\\x01\\x02malicious',
      'Name\r\n\r\nX-Injected-Header: evil',
    ];

    for (const maliciousInput of maliciousData) {
      const textInputs = await page.locator('input[type="text"], input[type="email"], textarea').all();

      for (const input of textInputs) {
        if (await input.isVisible() && await input.isEnabled()) {
          await input.fill(maliciousInput);
          await input.blur();

          // Verify input was sanitized
          const value = await input.inputValue();
          expect(value).not.toContain('<script>');
          expect(value).not.toContain('<iframe>');
          expect(value).not.toContain('onload=');
          expect(value).not.toContain('\\x00');
        }
      }
    }
  });

  test('should implement proper data masking for sensitive fields', async ({ page }) => {
    await page.goto('/portfolio');

    // Check for properly masked sensitive data
    const textContent = await page.textContent('body');

    // Should not expose full account numbers
    expect(textContent).not.toMatch(/\d{16}/); // Full credit card
    expect(textContent).not.toMatch(/\d{9}/);  // Full SSN

    // Should show masked versions if any
    const maskedPatterns = [
      /\*{4,}/,           // Masked with asterisks
      /X{4,}/,            // Masked with X's
      /\d{4}$/,           // Last 4 digits only
    ];

    // If sensitive data is shown, it should be masked
    const hasMaskedData = maskedPatterns.some(pattern => pattern.test(textContent));
    if (textContent.includes('account') || textContent.includes('card')) {
      expect(hasMaskedData).toBe(true);
    }
  });

  test('should prevent data exposure through error messages', async ({ page }) => {
    await page.goto('/');

    // Trigger various error conditions
    const errorTriggers = [
      () => page.evaluate(() => fetch('/api/nonexistent')),
      () => page.evaluate(() => fetch('/api/users/invalid-id')),
      () => page.fill('input[type="email"]', 'invalid-email'),
    ];

    for (const trigger of errorTriggers) {
      await trigger();
      await page.waitForTimeout(1000);

      // Check for exposed sensitive information in error messages
      const errorMessages = await page.locator('.error, .alert, [role="alert"]').allTextContents();

      for (const message of errorMessages) {
        expect(message).not.toMatch(/database/i);
        expect(message).not.toMatch(/sql/i);
        expect(message).not.toMatch(/stack trace/i);
        expect(message).not.toMatch(/internal server/i);
        expect(message).not.toMatch(/connection string/i);
      }
    }
  });

  test('should implement secure file upload validation', async ({ page }) => {
    await page.goto('/settings');

    // Look for file upload inputs
    const fileInputs = await page.locator('input[type="file"]').all();

    for (const fileInput of fileInputs) {
      if (await fileInput.isVisible()) {
        // Test malicious file types
        const maliciousFiles = [
          { name: 'evil.exe', content: 'MZ\x90\x00' }, // Executable
          { name: 'script.js', content: 'alert("xss")' }, // JavaScript
          { name: 'shell.php', content: '<?php system($_GET["cmd"]); ?>' }, // PHP
          { name: 'bomb.zip', content: 'PK\x03\x04' }, // ZIP bomb potential
        ];

        for (const file of maliciousFiles) {
          await fileInput.setInputFiles({
            name: file.name,
            mimeType: 'application/octet-stream',
            buffer: Buffer.from(file.content),
          });

          await page.waitForTimeout(1000);

          // Should show validation error
          const validationError = await page.locator('.file-error, .upload-error').count();
          expect(validationError).toBeGreaterThan(0);
        }
      }
    }
  });

  test('should prevent information disclosure through timing attacks', async ({ page }) => {
    await page.goto('/');

    const timings = [];

    // Test timing for valid vs invalid users
    const testCredentials = [
      { email: 'valid@example.com', password: 'wrongpassword' },
      { email: 'invalid@nonexistent.com', password: 'wrongpassword' },
    ];

    for (const creds of testCredentials) {
      const startTime = Date.now();

      await page.evaluate(async (credentials) => {
        try {
          await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(credentials),
          });
        } catch (e) {
          // Ignore errors, we're measuring timing
        }
      }, creds);

      const endTime = Date.now();
      timings.push(endTime - startTime);
    }

    // Timing difference should be minimal (< 100ms)
    const timingDifference = Math.abs(timings[0] - timings[1]);
    expect(timingDifference).toBeLessThan(100);
  });

  test('should validate API response security headers', async ({ page }) => {
    const responses = [];

    page.on('response', response => {
      if (response.url().includes('/api/')) {
        responses.push(response);
      }
    });

    await page.goto('/portfolio');
    await page.waitForTimeout(3000);

    for (const response of responses) {
      const headers = response.headers();

      // Check for security headers
      expect(headers['x-content-type-options']).toBe('nosniff');
      expect(headers['x-frame-options']).toBeTruthy();
      expect(headers['strict-transport-security']).toBeTruthy();

      // Ensure no sensitive headers are exposed
      expect(headers['server']).not.toMatch(/apache|nginx|iis/i);
      expect(headers['x-powered-by']).toBeFalsy();
    }
  });

  test('should prevent data leakage through browser caching', async ({ page }) => {
    await page.goto('/portfolio');

    // Check cache control headers for sensitive pages
    const response = await page.reload();
    const headers = response.headers();

    // Sensitive pages should not be cached
    if (page.url().includes('/portfolio') || page.url().includes('/settings')) {
      expect(headers['cache-control']).toMatch(/no-cache|no-store|private/);
    }
  });

  test('should implement proper session timeout', async ({ page }) => {
    await page.goto('/portfolio');

    // Mock session expiration
    await page.evaluate(() => {
      // Set session to expire immediately
      localStorage.setItem('sessionExpiry', Date.now() - 1000);
    });

    await page.reload();
    await page.waitForTimeout(2000);

    // Should redirect to login or show session expired message
    const url = page.url();
    const sessionExpiredMessage = await page.locator('text=session expired, text=please log in').count();

    expect(url.includes('/login') || sessionExpiredMessage > 0).toBe(true);
  });

  test('should validate data retention policies', async ({ page }) => {
    await page.goto('/settings');

    // Check for data retention information
    const privacyInfo = await page.locator('text=data retention, text=privacy policy').count();
    expect(privacyInfo).toBeGreaterThan(0);

    // Check for data deletion options
    const deleteOptions = await page.locator('text=delete account, text=remove data').count();
    expect(deleteOptions).toBeGreaterThan(0);
  });
});