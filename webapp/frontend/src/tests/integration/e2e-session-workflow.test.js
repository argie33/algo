/**
 * End-to-End Session Workflow Integration Tests
 * Tests complete user authentication and session management flows
 */

import { test, expect } from '@playwright/test';

// Test configuration
const TEST_CONFIG = {
  baseURL: process.env.VITE_API_URL || 'http://localhost:3000',
  timeout: 30000,
  retries: 2
};

test.describe('E2E Session Management Workflow', () => {
  let page;
  let context;

  test.beforeEach(async ({ browser }) => {
    // Create isolated context for each test
    context = await browser.newContext({
      viewport: { width: 1280, height: 720 },
      permissions: ['clipboard-read', 'clipboard-write'],
      httpCredentials: {
        username: process.env.TEST_USERNAME || 'testuser',
        password: process.env.TEST_PASSWORD || 'testpass'
      }
    });

    page = await context.newPage();

    // Set up request/response monitoring
    page.on('request', request => {
      if (request.url().includes('session')) {
        console.log(`📤 Request: ${request.method()} ${request.url()}`);
      }
    });

    page.on('response', response => {
      if (response.url().includes('session')) {
        console.log(`📥 Response: ${response.status()} ${response.url()}`);
      }
    });

    // Navigate to application
    await page.goto(TEST_CONFIG.baseURL);
  });

  test.afterEach(async () => {
    await context.close();
  });

  test.describe('Authentication Flow', () => {
    test('should complete full login workflow with session creation', async () => {
      // Navigate to login page
      await page.click('[data-testid="login-button"]');
      await expect(page.locator('[data-testid="login-form"]')).toBeVisible();

      // Fill login form
      await page.fill('[data-testid="username-input"]', 'testuser@example.com');
      await page.fill('[data-testid="password-input"]', 'TestPassword123!');

      // Mock successful authentication response
      await page.route('**/api/auth/login', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            user: {
              sub: 'test-user-123',
              username: 'testuser',
              email: 'testuser@example.com'
            },
            tokens: {
              accessToken: createMockJWT({ sub: 'test-user-123', exp: Math.floor(Date.now() / 1000) + 3600 }),
              refreshToken: 'mock-refresh-token',
              idToken: 'mock-id-token'
            }
          })
        });
      });

      // Mock session creation API
      await page.route('**/api/session/create', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            sessionId: 'test-session-123',
            expiresAt: Date.now() + 3600000
          })
        });
      });

      // Submit login form
      await page.click('[data-testid="login-submit"]');

      // Wait for authentication to complete
      await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });

      // Verify session indicators
      await expect(page.locator('[data-testid="user-menu"]')).toBeVisible();
      await expect(page.locator('[data-testid="session-status"]')).toContainText('Active');

      // Check local storage for secure tokens
      const hasSecureTokens = await page.evaluate(() => {
        return sessionStorage.getItem('secure_access_token') !== null;
      });
      expect(hasSecureTokens).toBe(true);
    });

    test('should handle MFA challenge during login', async () => {
      await page.click('[data-testid="login-button"]');
      await page.fill('[data-testid="username-input"]', 'mfauser@example.com');
      await page.fill('[data-testid="password-input"]', 'TestPassword123!');

      // Mock MFA challenge response
      await page.route('**/api/auth/login', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: false,
            nextStep: 'MFA_CHALLENGE',
            challengeType: 'SMS_MFA',
            message: 'Enter the code sent to your phone'
          })
        });
      });

      await page.click('[data-testid="login-submit"]');

      // Verify MFA challenge dialog appears
      await expect(page.locator('[data-testid="mfa-challenge-dialog"]')).toBeVisible();
      await expect(page.locator('[data-testid="mfa-code-input"]')).toBeVisible();

      // Fill MFA code
      await page.fill('[data-testid="mfa-code-input"]', '123456');

      // Mock successful MFA verification
      await page.route('**/api/auth/mfa/verify', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            user: {
              sub: 'mfa-user-123',
              username: 'mfauser',
              email: 'mfauser@example.com'
            },
            tokens: {
              accessToken: createMockJWT({ sub: 'mfa-user-123', exp: Math.floor(Date.now() / 1000) + 3600 }),
              refreshToken: 'mock-refresh-token',
              idToken: 'mock-id-token'
            }
          })
        });
      });

      await page.click('[data-testid="mfa-verify-button"]');

      // Verify successful authentication
      await expect(page.locator('[data-testid="dashboard"]')).toBeVisible({ timeout: 10000 });
    });

    test('should handle authentication errors gracefully', async () => {
      await page.click('[data-testid="login-button"]');
      await page.fill('[data-testid="username-input"]', 'invalid@example.com');
      await page.fill('[data-testid="password-input"]', 'wrongpassword');

      // Mock authentication failure
      await page.route('**/api/auth/login', (route) => {
        route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({
            success: false,
            error: 'Invalid credentials',
            message: 'Username or password is incorrect'
          })
        });
      });

      await page.click('[data-testid="login-submit"]');

      // Verify error message is displayed
      await expect(page.locator('[data-testid="login-error"]')).toBeVisible();
      await expect(page.locator('[data-testid="login-error"]')).toContainText('Invalid credentials');

      // Verify user stays on login page
      await expect(page.locator('[data-testid="login-form"]')).toBeVisible();
    });
  });

  test.describe('Session Management', () => {
    test.beforeEach(async () => {
      // Set up authenticated session
      await setupAuthenticatedSession(page);
    });

    test('should display session warning when token expires soon', async () => {
      // Mock session with short-lived token
      await page.route('**/api/session/validate', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            valid: true,
            session: {
              sessionId: 'test-session-123',
              expiresAt: Date.now() + 300000 // 5 minutes from now
            }
          })
        });
      });

      // Trigger session check
      await page.reload();

      // Wait for session warning dialog
      await expect(page.locator('[data-testid="session-warning-dialog"]')).toBeVisible({ timeout: 15000 });
      await expect(page.locator('[data-testid="session-warning-title"]')).toContainText('Session Expiring Soon');

      // Verify extension options are available
      await expect(page.locator('[data-testid="extend-session-button"]')).toBeVisible();
      await expect(page.locator('[data-testid="logout-button"]')).toBeVisible();
    });

    test('should extend session successfully', async () => {
      // Navigate to session warning
      await triggerSessionWarning(page);

      // Mock successful token refresh
      await page.route('**/api/auth/refresh', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            tokens: {
              accessToken: createMockJWT({ sub: 'test-user-123', exp: Math.floor(Date.now() / 1000) + 3600 }),
              refreshToken: 'new-refresh-token'
            }
          })
        });
      });

      // Mock session update
      await page.route('**/api/session/update', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true
          })
        });
      });

      // Click extend session
      await page.click('[data-testid="extend-session-button"]');

      // Verify success notification
      await expect(page.locator('[data-testid="session-extended-notification"]')).toBeVisible();
      await expect(page.locator('[data-testid="session-extended-notification"]')).toContainText('Session successfully extended');

      // Verify dialog is closed
      await expect(page.locator('[data-testid="session-warning-dialog"]')).not.toBeVisible();
    });

    test('should handle idle timeout warning', async () => {
      // Mock idle session detection
      await page.evaluate(() => {
        // Simulate no user activity for 30 minutes
        const idleEvent = new CustomEvent('sessionIdle', {
          detail: { idleTime: 30 * 60 * 1000 }
        });
        window.dispatchEvent(idleEvent);
      });

      // Wait for idle warning dialog
      await expect(page.locator('[data-testid="idle-warning-dialog"]')).toBeVisible();
      await expect(page.locator('[data-testid="idle-warning-title"]')).toContainText('Are you still there?');

      // Verify continue and logout options
      await expect(page.locator('[data-testid="continue-session-button"]')).toBeVisible();
      await expect(page.locator('[data-testid="idle-logout-button"]')).toBeVisible();
    });

    test('should continue session after idle warning', async () => {
      await triggerIdleWarning(page);

      // Mock activity update
      await page.route('**/api/session/activity', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true
          })
        });
      });

      // Click continue session
      await page.click('[data-testid="continue-session-button"]');

      // Verify dialog is closed and session continues
      await expect(page.locator('[data-testid="idle-warning-dialog"]')).not.toBeVisible();
      await expect(page.locator('[data-testid="dashboard"]')).toBeVisible();
    });

    test('should logout from idle warning', async () => {
      await triggerIdleWarning(page);

      // Mock logout
      await page.route('**/api/auth/logout', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true
          })
        });
      });

      // Mock session revocation
      await page.route('**/api/session/revoke', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true
          })
        });
      });

      // Click logout
      await page.click('[data-testid="idle-logout-button"]');

      // Verify redirect to login
      await expect(page.locator('[data-testid="login-form"]')).toBeVisible();
    });
  });

  test.describe('Cross-Tab Synchronization', () => {
    test('should synchronize logout across multiple tabs', async () => {
      // Set up first tab with authenticated session
      await setupAuthenticatedSession(page);

      // Open second tab
      const secondPage = await context.newPage();
      await secondPage.goto(TEST_CONFIG.baseURL);
      await setupAuthenticatedSession(secondPage);

      // Verify both tabs are authenticated
      await expect(page.locator('[data-testid="dashboard"]')).toBeVisible();
      await expect(secondPage.locator('[data-testid="dashboard"]')).toBeVisible();

      // Mock logout API
      await page.route('**/api/auth/logout', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true })
        });
      });

      // Mock session revocation
      await page.route('**/api/session/revoke', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ success: true })
        });
      });

      // Logout from first tab
      await page.click('[data-testid="user-menu"]');
      await page.click('[data-testid="logout-button"]');

      // Verify first tab redirects to login
      await expect(page.locator('[data-testid="login-form"]')).toBeVisible();

      // Verify second tab also redirects to login (cross-tab sync)
      await expect(secondPage.locator('[data-testid="login-form"]')).toBeVisible({ timeout: 5000 });

      await secondPage.close();
    });

    test('should synchronize session extension across tabs', async () => {
      // Set up multiple tabs
      await setupAuthenticatedSession(page);
      const secondPage = await context.newPage();
      await secondPage.goto(TEST_CONFIG.baseURL);
      await setupAuthenticatedSession(secondPage);

      // Trigger session warning on both tabs
      await triggerSessionWarning(page);
      await triggerSessionWarning(secondPage);

      // Extend session from first tab
      await page.route('**/api/auth/refresh', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            success: true,
            tokens: {
              accessToken: createMockJWT({ sub: 'test-user-123', exp: Math.floor(Date.now() / 1000) + 3600 }),
              refreshToken: 'new-refresh-token'
            }
          })
        });
      });

      await page.click('[data-testid="extend-session-button"]');

      // Verify extension notification appears on both tabs
      await expect(page.locator('[data-testid="session-extended-notification"]')).toBeVisible();
      await expect(secondPage.locator('[data-testid="session-extended-notification"]')).toBeVisible({ timeout: 5000 });

      await secondPage.close();
    });
  });

  test.describe('Security Features', () => {
    test('should detect and handle concurrent session limit', async () => {
      // Set up multiple sessions
      const sessions = [];
      
      for (let i = 0; i < 6; i++) { // Exceed limit of 5
        const newPage = await context.newPage();
        await newPage.goto(TEST_CONFIG.baseURL);
        await setupAuthenticatedSession(newPage, `user-session-${i}`);
        sessions.push(newPage);
      }

      // Mock concurrent session limit response
      await page.route('**/api/session/create', (route) => {
        route.fulfill({
          status: 429,
          contentType: 'application/json',
          body: JSON.stringify({
            success: false,
            error: 'Concurrent session limit exceeded',
            maxSessions: 5
          })
        });
      });

      // Try to create another session
      const extraPage = await context.newPage();
      await extraPage.goto(TEST_CONFIG.baseURL);

      // Should show session limit warning
      await expect(extraPage.locator('[data-testid="session-limit-warning"]')).toBeVisible();

      // Cleanup
      for (const sessionPage of sessions) {
        await sessionPage.close();
      }
      await extraPage.close();
    });

    test('should handle session hijacking detection', async () => {
      await setupAuthenticatedSession(page);

      // Mock session validation with device fingerprint mismatch
      await page.route('**/api/session/validate', (route) => {
        route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({
            valid: false,
            reason: 'Device fingerprint mismatch',
            securityAlert: true
          })
        });
      });

      // Trigger session validation
      await page.reload();

      // Should show security alert
      await expect(page.locator('[data-testid="security-alert"]')).toBeVisible();
      await expect(page.locator('[data-testid="security-alert"]')).toContainText('Security Alert');

      // Should force logout
      await expect(page.locator('[data-testid="login-form"]')).toBeVisible({ timeout: 5000 });
    });

    test('should implement proper CSRF protection', async () => {
      await setupAuthenticatedSession(page);

      // Try to make request without CSRF token
      const response = await page.evaluate(async () => {
        try {
          const response = await fetch('/api/session/update', {
            method: 'PUT',
            headers: {
              'Content-Type': 'application/json'
            },
            body: JSON.stringify({
              userId: 'test-user-123',
              sessionId: 'test-session',
              metadata: { action: 'test' }
            })
          });
          return { status: response.status, ok: response.ok };
        } catch (error) {
          return { error: error.message };
        }
      });

      // Should be rejected due to missing CSRF token
      expect(response.status).toBe(403);
    });
  });

  test.describe('Performance and Monitoring', () => {
    test('should track session metrics', async () => {
      await setupAuthenticatedSession(page);

      // Perform various session activities
      await page.click('[data-testid="user-menu"]');
      await page.click('[data-testid="profile-link"]');
      await page.click('[data-testid="settings-link"]');
      await page.click('[data-testid="dashboard-link"]');

      // Mock metrics collection
      await page.route('**/api/session/metrics', (route) => {
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            sessionId: 'test-session-123',
            pageViews: 4,
            duration: 300000, // 5 minutes
            actions: ['login', 'profile_view', 'settings_view', 'dashboard_view']
          })
        });
      });

      // Verify metrics are being tracked
      const metricsResponse = await page.evaluate(async () => {
        const response = await fetch('/api/session/metrics?sessionId=test-session-123');
        return response.json();
      });

      expect(metricsResponse.pageViews).toBeGreaterThan(0);
      expect(metricsResponse.duration).toBeGreaterThan(0);
    });

    test('should handle session recovery after network failure', async () => {
      await setupAuthenticatedSession(page);

      // Simulate network failure
      await page.context().setOffline(true);

      // Try to perform action
      await page.click('[data-testid="user-menu"]');

      // Should show offline indicator
      await expect(page.locator('[data-testid="offline-indicator"]')).toBeVisible();

      // Restore network
      await page.context().setOffline(false);

      // Should automatically recover session
      await expect(page.locator('[data-testid="offline-indicator"]')).not.toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="dashboard"]')).toBeVisible();
    });
  });
});

// Helper functions
async function setupAuthenticatedSession(page, sessionId = 'test-session-123') {
  // Mock authentication
  await page.route('**/api/auth/login', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        user: {
          sub: 'test-user-123',
          username: 'testuser',
          email: 'testuser@example.com'
        },
        tokens: {
          accessToken: createMockJWT({ sub: 'test-user-123', exp: Math.floor(Date.now() / 1000) + 3600 }),
          refreshToken: 'mock-refresh-token'
        }
      })
    });
  });

  // Mock session creation
  await page.route('**/api/session/create', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        sessionId: sessionId,
        expiresAt: Date.now() + 3600000
      })
    });
  });

  // Set up authenticated state
  await page.evaluate((sessionId) => {
    localStorage.setItem('accessToken', 'mock-access-token');
    sessionStorage.setItem('secure_session_meta', JSON.stringify({
      sessionId: sessionId,
      userId: 'test-user-123',
      loginTime: Date.now(),
      lastActivity: Date.now()
    }));
  }, sessionId);

  await page.reload();
  await expect(page.locator('[data-testid="dashboard"]')).toBeVisible();
}

async function triggerSessionWarning(page) {
  await page.route('**/api/session/validate', (route) => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        valid: true,
        session: {
          sessionId: 'test-session-123',
          expiresAt: Date.now() + 300000 // 5 minutes
        }
      })
    });
  });

  await page.evaluate(() => {
    const warningEvent = new CustomEvent('sessionWarning', {
      detail: { timeToExpiry: 300000 }
    });
    window.dispatchEvent(warningEvent);
  });

  await expect(page.locator('[data-testid="session-warning-dialog"]')).toBeVisible();
}

async function triggerIdleWarning(page) {
  await page.evaluate(() => {
    const idleEvent = new CustomEvent('sessionIdle', {
      detail: { idleTime: 30 * 60 * 1000 }
    });
    window.dispatchEvent(idleEvent);
  });

  await expect(page.locator('[data-testid="idle-warning-dialog"]')).toBeVisible();
}

function createMockJWT(payload) {
  const header = { alg: 'HS256', typ: 'JWT' };
  const encodedHeader = btoa(JSON.stringify(header));
  const encodedPayload = btoa(JSON.stringify(payload));
  const signature = 'mock-signature';
  
  return `${encodedHeader}.${encodedPayload}.${signature}`;
}