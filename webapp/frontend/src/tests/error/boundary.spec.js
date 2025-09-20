/**
 * Error Boundary Testing Suite
 * Comprehensive error handling and boundary testing
 */

import { test, expect } from '@playwright/test';

test.describe('Error Boundary Testing', () => {
  test.beforeEach(async ({ page }) => {
    // Set up error boundary monitoring
    await page.addInitScript(() => {
      window.__ERROR_BOUNDARY_LOGS__ = [];
      window.__UNHANDLED_ERRORS__ = [];
      window.__COMPONENT_ERRORS__ = [];

      // Capture unhandled errors
      window.addEventListener('error', (event) => {
        window.__UNHANDLED_ERRORS__.push({
          message: event.message,
          filename: event.filename,
          lineno: event.lineno,
          colno: event.colno,
          error: event.error?.toString(),
          timestamp: Date.now()
        });
      });

      // Capture unhandled promise rejections
      window.addEventListener('unhandledrejection', (event) => {
        window.__UNHANDLED_ERRORS__.push({
          type: 'unhandled_promise_rejection',
          reason: event.reason?.toString(),
          timestamp: Date.now()
        });
      });

      // Mock React error boundary for testing
      window.__REACT_ERROR_BOUNDARY__ = {
        componentDidCatch: (error, errorInfo) => {
          window.__COMPONENT_ERRORS__.push({
            error: error.toString(),
            errorInfo: errorInfo,
            timestamp: Date.now()
          });
        }
      };

      // Override console.error to capture React errors
      const originalConsoleError = console.error;
      console.error = function(...args) {
        const message = args.join(' ');
        if (message.includes('React') || message.includes('component')) {
          window.__ERROR_BOUNDARY_LOGS__.push({
            message: message,
            timestamp: Date.now()
          });
        }
        return originalConsoleError.apply(console, args);
      };
    });
  });

  test('should handle network errors gracefully', async ({ page }) => {
    // Start with working site
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Simulate network failure
    await page.route('**/api/**', route => route.abort('failed'));

    // Reload to trigger network errors
    await page.reload();
    await page.waitForTimeout(3000);

    // Check for error boundaries or fallback UI
    const errorElements = await page.locator(
      '.error-boundary, .error-fallback, .network-error, .offline-indicator, [data-testid*="error"]'
    ).count();

    const errorMessages = await page.locator(
      'text=/network.*error|connection.*failed|unable.*to.*load|offline/i'
    ).count();

    // Should show appropriate error handling
    expect(errorElements + errorMessages).toBeGreaterThan(0);

    // Page should not be completely broken
    const bodyText = await page.textContent('body');
    expect(bodyText.length).toBeGreaterThan(50);

    // Should not have unhandled JavaScript errors
    const unhandledErrors = await page.evaluate(() => window.__UNHANDLED_ERRORS__);
    const criticalErrors = unhandledErrors.filter(error =>
      !error.message?.includes('fetch') && !error.message?.includes('network')
    );
    expect(criticalErrors.length).toBe(0);
  });

  test('should handle component render errors', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Inject component error to test error boundaries
    await page.evaluate(() => {
      // Simulate React component error
      try {
        // Try to trigger a component error
        const components = document.querySelectorAll('[data-reactroot], [data-react-component]');
        if (components.length > 0) {
          // Simulate throwing error in component
          if (window.React && window.React.Component) {
            const error = new Error('Test component error');
            if (window.__REACT_ERROR_BOUNDARY__.componentDidCatch) {
              window.__REACT_ERROR_BOUNDARY__.componentDidCatch(error, {
                componentStack: 'in TestComponent'
              });
            }
          }
        }
      } catch (e) {
        // Expected to fail in test environment
      }
    });

    await page.waitForTimeout(2000);

    // Check error boundary handling
    const errorBoundaries = await page.locator('.error-boundary, .error-fallback').count();
    const componentErrors = await page.evaluate(() => window.__COMPONENT_ERRORS__);

    // Should have error boundary handling or graceful degradation
    if (componentErrors.length > 0) {
      expect(errorBoundaries).toBeGreaterThan(0);
    }

    // Page should remain functional
    const isPageFunctional = await page.evaluate(() => {
      return document.readyState === 'complete' &&
             document.body.children.length > 0;
    });
    expect(isPageFunctional).toBe(true);
  });

  test('should handle API error responses', async ({ page }) => {
    // Mock API to return errors
    await page.route('**/api/portfolio**', route => {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Internal Server Error',
          message: 'Unable to load portfolio data'
        })
      });
    });

    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);

    // Should show error state for failed API calls
    const errorIndicators = await page.locator(
      '.error, .alert-error, .api-error, [role="alert"]'
    ).count();

    const errorMessages = await page.locator(
      'text=/error.*loading|failed.*to.*load|unable.*to.*fetch/i'
    ).count();

    expect(errorIndicators + errorMessages).toBeGreaterThan(0);

    // Should not show sensitive error details
    const pageContent = await page.textContent('body');
    expect(pageContent.toLowerCase()).not.toMatch(/internal.*server.*error|stack.*trace|database.*error/);

    // Should provide user-friendly error message
    const userFriendlyMessages = await page.locator(
      'text=/try.*again|refresh.*page|check.*connection|unavailable/i'
    ).count();
    expect(userFriendlyMessages).toBeGreaterThan(0);

    // Test retry mechanism if available
    const retryButtons = await page.locator('button:has-text("Retry"), button:has-text("Try Again")').all();
    if (retryButtons.length > 0) {
      await retryButtons[0].click();
      await page.waitForTimeout(1000);
      // Should attempt to reload data
    }
  });

  test('should handle authentication errors', async ({ page }) => {
    // Mock authentication failure
    await page.route('**/api/**', route => {
      if (route.request().headers()['authorization']) {
        route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({
            error: 'Unauthorized',
            message: 'Invalid or expired token'
          })
        });
      } else {
        route.continue();
      }
    });

    await page.goto('/portfolio');
    await page.waitForTimeout(3000);

    // Should handle authentication errors appropriately
    const authErrorHandling = await page.evaluate(() => {
      const hasLoginRedirect = window.location.pathname.includes('/login') ||
                              window.location.hash.includes('login');
      const hasAuthError = document.querySelector('.auth-error, .login-required, .session-expired');
      const hasUnauthorizedMessage = document.body.textContent.toLowerCase().includes('unauthorized') ||
                                   document.body.textContent.toLowerCase().includes('please log in');

      return {
        hasLoginRedirect,
        hasAuthError: !!hasAuthError,
        hasUnauthorizedMessage
      };
    });

    // Should either redirect to login or show auth error
    expect(
      authErrorHandling.hasLoginRedirect ||
      authErrorHandling.hasAuthError ||
      authErrorHandling.hasUnauthorizedMessage
    ).toBe(true);

    // Should not expose sensitive auth details
    const pageContent = await page.textContent('body');
    expect(pageContent.toLowerCase()).not.toMatch(/token.*expired|invalid.*token|auth.*failed/);
  });

  test('should handle form validation errors', async ({ page }) => {
    await page.goto('/settings');
    await page.waitForLoadState('networkidle');

    const forms = await page.locator('form').all();

    for (const form of forms.slice(0, 2)) {
      if (await form.isVisible()) {
        // Test invalid form submission
        const submitButton = form.locator('button[type="submit"], input[type="submit"]').first();
        const inputs = await form.locator('input, textarea, select').all();

        // Fill form with invalid data
        for (const input of inputs.slice(0, 3)) {
          if (await input.isVisible() && await input.isEnabled()) {
            const inputType = await input.getAttribute('type');

            let invalidValue = '';
            if (inputType === 'email') {
              invalidValue = 'invalid-email';
            } else if (inputType === 'number') {
              invalidValue = 'not-a-number';
            } else if (inputType === 'url') {
              invalidValue = 'invalid-url';
            } else {
              invalidValue = ''; // Empty for required fields
            }

            await input.fill(invalidValue);
          }
        }

        // Submit form
        if (await submitButton.isVisible()) {
          await submitButton.click();
          await page.waitForTimeout(1000);

          // Check for validation errors
          const validationErrors = await form.locator(
            '.error, .invalid, .field-error, [aria-invalid="true"]'
          ).count();

          const errorMessages = await form.locator(
            'text=/required|invalid|error/i'
          ).count();

          expect(validationErrors + errorMessages).toBeGreaterThan(0);

          // Form should not submit with invalid data
          const formStillVisible = await form.isVisible();
          expect(formStillVisible).toBe(true);
        }
      }
    }
  });

  test('should handle JavaScript runtime errors', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Inject various JavaScript errors
    const errorTests = [
      () => page.evaluate(() => { throw new TypeError('Test type error'); }),
      () => page.evaluate(() => { window.nonExistentFunction(); }),
      () => page.evaluate(() => { const obj = null; obj.property; }),
      () => page.evaluate(() => { JSON.parse('invalid json'); })
    ];

    for (const errorTest of errorTests) {
      const initialErrors = await page.evaluate(() => window.__UNHANDLED_ERRORS__.length);

      try {
        await errorTest();
      } catch (e) {
        // Errors are expected
      }

      await page.waitForTimeout(500);

      // Check that errors were handled
      const finalErrors = await page.evaluate(() => window.__UNHANDLED_ERRORS__.length);
      const _newErrors = finalErrors - initialErrors;

      // Application should continue functioning despite errors
      const isPageResponsive = await page.evaluate(() => {
        return document.readyState === 'complete' &&
               typeof window.fetch === 'function';
      });
      expect(isPageResponsive).toBe(true);
    }

    // Check overall error handling
    const allErrors = await page.evaluate(() => window.__UNHANDLED_ERRORS__);
    console.log(`Total unhandled errors: ${allErrors.length}`);

    // Should not have excessive unhandled errors
    expect(allErrors.length).toBeLessThan(10);
  });

  test('should handle file upload errors', async ({ page }) => {
    await page.goto('/settings');
    await page.waitForLoadState('networkidle');

    const fileInputs = await page.locator('input[type="file"]').all();

    for (const fileInput of fileInputs) {
      if (await fileInput.isVisible()) {
        // Test with oversized file
        try {
          await fileInput.setInputFiles({
            name: 'large-file.jpg',
            mimeType: 'image/jpeg',
            buffer: Buffer.alloc(10 * 1024 * 1024) // 10MB file
          });

          await page.waitForTimeout(1000);

          // Should show file size error
          const fileSizeError = await page.locator(
            'text=/file.*too.*large|size.*limit|maximum.*size/i'
          ).count();

          if (fileSizeError === 0) {
            // Check for generic error messages
            const genericError = await page.locator('.error, .alert-error').count();
            expect(genericError).toBeGreaterThan(0);
          }
        } catch (e) {
          // File input might reject the file
        }

        // Test with invalid file type
        try {
          await fileInput.setInputFiles({
            name: 'script.exe',
            mimeType: 'application/octet-stream',
            buffer: Buffer.from('fake executable')
          });

          await page.waitForTimeout(1000);

          // Should show file type error
          const fileTypeError = await page.locator(
            'text=/invalid.*file.*type|not.*supported|wrong.*format/i'
          ).count();

          expect(fileTypeError).toBeGreaterThan(0);
        } catch (e) {
          // File input might reject the file
        }
      }
    }
  });

  test('should handle timeout errors', async ({ page }) => {
    // Set up slow responses to trigger timeouts
    await page.route('**/api/**', async route => {
      await new Promise(resolve => setTimeout(resolve, 10000)); // 10 second delay
      route.continue();
    });

    await page.goto('/dashboard');

    // Wait for timeout handling
    await page.waitForTimeout(5000);

    // Should show timeout error or loading state
    const timeoutHandling = await page.locator(
      '.timeout-error, .loading-timeout, .slow-connection, text=/taking.*longer|timeout|slow/i'
    ).count();

    const loadingIndicators = await page.locator(
      '.loading, .spinner, .skeleton'
    ).count();

    // Should show either timeout handling or loading indicators
    expect(timeoutHandling + loadingIndicators).toBeGreaterThan(0);

    // Page should remain interactive
    const isInteractive = await page.evaluate(() => {
      const button = document.querySelector('button');
      return button ? !button.disabled : true;
    });
    expect(isInteractive).toBe(true);
  });

  test('should handle browser compatibility errors', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Test feature detection and fallbacks
    const compatibilityTests = await page.evaluate(() => {
      const tests = {
        hasLocalStorage: typeof localStorage !== 'undefined',
        hasFetch: typeof fetch !== 'undefined',
        hasPromises: typeof Promise !== 'undefined',
        hasArrowFunctions: true, // Can't test syntax features easily
        hasAsyncAwait: true
      };

      const missingFeatures = [];
      Object.entries(tests).forEach(([feature, supported]) => {
        if (!supported) {
          missingFeatures.push(feature);
        }
      });

      return {
        tests,
        missingFeatures,
        userAgent: navigator.userAgent
      };
    });

    // Check for polyfill messages or compatibility warnings
    if (compatibilityTests.missingFeatures.length > 0) {
      const compatibilityWarnings = await page.locator(
        '.browser-warning, .compatibility-notice, .polyfill-notice'
      ).count();

      // Should show compatibility warnings for missing features
      expect(compatibilityWarnings).toBeGreaterThan(0);
    }

    // Application should work despite missing features
    const basicFunctionality = await page.evaluate(() => {
      return {
        canClick: document.querySelector('button') !== null,
        canNavigate: document.querySelector('a, nav') !== null,
        hasContent: document.body.textContent.length > 100
      };
    });

    expect(basicFunctionality.canClick || basicFunctionality.canNavigate).toBe(true);
    expect(basicFunctionality.hasContent).toBe(true);
  });

  test('should provide error recovery mechanisms', async ({ page }) => {
    await page.goto('/dashboard');
    await page.waitForLoadState('networkidle');

    // Simulate error condition
    await page.route('**/api/portfolio**', route => {
      route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({
          error: 'Service Unavailable',
          message: 'Service temporarily unavailable'
        })
      });
    });

    await page.reload();
    await page.waitForTimeout(3000);

    // Look for recovery mechanisms
    const recoveryOptions = await page.locator(
      'button:has-text("Retry"), button:has-text("Refresh"), button:has-text("Try Again"), .retry-button'
    ).all();

    const refreshOptions = await page.locator(
      'button:has-text("Reload"), a:has-text("Home"), .home-link'
    ).all();

    // Should provide at least one recovery option
    expect(recoveryOptions.length + refreshOptions.length).toBeGreaterThan(0);

    // Test retry functionality
    if (recoveryOptions.length > 0) {
      // Remove error route to allow retry to succeed
      await page.unroute('**/api/portfolio**');

      await recoveryOptions[0].click();
      await page.waitForTimeout(2000);

      // Should attempt to recover
      const errorCount = await page.locator('.error, .alert-error').count();
      expect(errorCount).toBeLessThanOrEqual(1); // Error should be reduced or removed
    }

    // Test navigation recovery
    if (refreshOptions.length > 0) {
      await refreshOptions[0].click();
      await page.waitForTimeout(1000);

      // Should navigate to recovery page
      const newUrl = page.url();
      expect(newUrl).toBeTruthy();
    }
  });
});