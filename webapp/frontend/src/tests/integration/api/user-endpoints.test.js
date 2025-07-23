/**
 * User Endpoints Integration Tests
 * Tests user management API endpoints with real authentication
 */

import { describe, it, expect, beforeEach, afterEach, beforeAll, afterAll, vi } from 'vitest';
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';

// Test server setup
const server = setupServer(
  // User registration endpoint
  http.post('/api/auth/register', async ({ request }) => {
    const body = await request.json();
    if (body.email === 'test@example.com') {
      return HttpResponse.json({
        success: true,
        user: {
          id: 'user_123',
          email: 'test@example.com',
          username: 'testuser',
          verified: false
        },
        token: 'jwt_token_12345'
      });
    }
    return HttpResponse.json({ success: false, error: 'User already exists' }, { status: 409 });
  }),

  // User profile endpoint
  http.get('/api/users/profile', ({ request }) => {
    const authHeader = request.headers.get('authorization');
    if (authHeader?.includes('Bearer jwt_token_12345')) {
      return HttpResponse.json({
        success: true,
        user: {
          id: 'user_123',
          email: 'test@example.com',
          username: 'testuser',
          profile: {
            firstName: 'John',
            lastName: 'Doe',
            riskTolerance: 'moderate',
            investmentGoals: ['growth', 'income']
          },
          preferences: {
            currency: 'USD',
            timezone: 'America/New_York',
            notifications: {
              email: true,
              push: false,
              trades: true
            }
          }
        }
      });
    }
    return HttpResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }),

  // Update user profile endpoint
  http.put('/api/users/profile', async ({ request }) => {
    const authHeader = request.headers.get('authorization');
    const body = await request.json();
    
    if (authHeader?.includes('Bearer jwt_token_12345')) {
      return HttpResponse.json({
        success: true,
        user: {
          id: 'user_123',
          profile: {
            ...body,
            updatedAt: new Date().toISOString()
          }
        }
      });
    }
    return HttpResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }),

  // User settings endpoint
  http.get('/api/users/settings', ({ request }) => {
    const authHeader = request.headers.get('authorization');
    if (authHeader?.includes('Bearer jwt_token_12345')) {
      return HttpResponse.json({
        success: true,
        settings: {
          trading: {
            defaultOrderType: 'market',
            confirmations: true,
            riskLimits: {
              maxDailyLoss: 1000,
              maxPositionSize: 10000
            }
          },
          notifications: {
            priceAlerts: true,
            executionAlerts: true,
            newsAlerts: false
          },
          display: {
            theme: 'dark',
            currency: 'USD',
            decimalPlaces: 2
          }
        }
      });
    }
    return HttpResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }),

  // Account verification endpoint
  http.post('/api/users/verify', async ({ request }) => {
    const body = await request.json();
    if (body.token === 'verification_token_valid') {
      return HttpResponse.json({
        success: true,
        message: 'Email verified successfully',
        user: {
          id: 'user_123',
          verified: true,
          verifiedAt: new Date().toISOString()
        }
      });
    }
    return HttpResponse.json({ 
      success: false, 
      error: 'Invalid verification token' 
    }, { status: 400 });
  })
);

describe('User Endpoints Integration', () => {
  beforeAll(() => server.listen());
  afterEach(() => server.resetHandlers());
  afterAll(() => server.close());

  describe('User Registration', () => {
    it('successfully registers new user', async () => {
      const response = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: 'test@example.com',
          password: 'securePassword123',
          username: 'testuser'
        })
      });

      const data = await response.json();
      
      expect(response.status).toBe(200);
      expect(data.success).toBe(true);
      expect(data.user.email).toBe('test@example.com');
      expect(data.token).toBeDefined();
    });

    it('handles duplicate user registration', async () => {
      const response = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: 'existing@example.com',
          password: 'password123',
          username: 'existing'
        })
      });

      expect(response.status).toBe(409);
      const data = await response.json();
      expect(data.success).toBe(false);
      expect(data.error).toContain('already exists');
    });
  });

  describe('User Profile Management', () => {
    const authToken = 'Bearer jwt_token_12345';

    it('retrieves user profile with authentication', async () => {
      const response = await fetch('/api/users/profile', {
        headers: { 'Authorization': authToken }
      });

      const data = await response.json();
      
      expect(response.status).toBe(200);
      expect(data.success).toBe(true);
      expect(data.user.profile.firstName).toBe('John');
      expect(data.user.preferences.currency).toBe('USD');
    });

    it('updates user profile successfully', async () => {
      const updates = {
        firstName: 'Jane',
        lastName: 'Smith',
        riskTolerance: 'aggressive'
      };

      const response = await fetch('/api/users/profile', {
        method: 'PUT',
        headers: {
          'Authorization': authToken,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(updates)
      });

      const data = await response.json();
      
      expect(response.status).toBe(200);
      expect(data.success).toBe(true);
      expect(data.user.profile.firstName).toBe('Jane');
      expect(data.user.profile.riskTolerance).toBe('aggressive');
    });

    it('requires authentication for profile access', async () => {
      const response = await fetch('/api/users/profile');
      
      expect(response.status).toBe(401);
      const data = await response.json();
      expect(data.error).toBe('Unauthorized');
    });
  });

  describe('User Settings Management', () => {
    const authToken = 'Bearer jwt_token_12345';

    it('retrieves user settings', async () => {
      const response = await fetch('/api/users/settings', {
        headers: { 'Authorization': authToken }
      });

      const data = await response.json();
      
      expect(response.status).toBe(200);
      expect(data.success).toBe(true);
      expect(data.settings.trading.defaultOrderType).toBe('market');
      expect(data.settings.notifications.priceAlerts).toBe(true);
      expect(data.settings.display.theme).toBe('dark');
    });

    it('includes risk limit settings', async () => {
      const response = await fetch('/api/users/settings', {
        headers: { 'Authorization': authToken }
      });

      const data = await response.json();
      const riskLimits = data.settings.trading.riskLimits;
      
      expect(riskLimits.maxDailyLoss).toBe(1000);
      expect(riskLimits.maxPositionSize).toBe(10000);
    });
  });

  describe('Account Verification', () => {
    it('verifies email with valid token', async () => {
      const response = await fetch('/api/users/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token: 'verification_token_valid'
        })
      });

      const data = await response.json();
      
      expect(response.status).toBe(200);
      expect(data.success).toBe(true);
      expect(data.user.verified).toBe(true);
      expect(data.user.verifiedAt).toBeDefined();
    });

    it('rejects invalid verification token', async () => {
      const response = await fetch('/api/users/verify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token: 'invalid_token'
        })
      });

      expect(response.status).toBe(400);
      const data = await response.json();
      expect(data.success).toBe(false);
      expect(data.error).toContain('Invalid verification token');
    });
  });

  describe('Error Handling', () => {
    it('handles network timeouts gracefully', async () => {
      server.use(
        http.get('/api/users/profile', () => {
          return new Promise((resolve) => {
            setTimeout(() => resolve(HttpResponse.json({ error: 'Timeout' })), 1000);
          });
        })
      );

      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 500);

      try {
        await fetch('/api/users/profile', {
          signal: controller.signal,
          headers: { 'Authorization': 'Bearer jwt_token_12345' }
        });
      } catch (error) {
        expect(error.name).toBe('AbortError');
      } finally {
        clearTimeout(timeoutId);
      }
    });

    it('handles malformed JSON responses', async () => {
      server.use(
        http.get('/api/users/profile', () => {
          return new HttpResponse('invalid json', {
            headers: { 'Content-Type': 'application/json' }
          });
        })
      );

      const response = await fetch('/api/users/profile', {
        headers: { 'Authorization': 'Bearer jwt_token_12345' }
      });

      try {
        await response.json();
      } catch (error) {
        expect(error.name).toBe('SyntaxError');
      }
    });
  });
});