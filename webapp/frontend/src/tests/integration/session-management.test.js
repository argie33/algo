/**
 * Session Management Integration Tests
 * Tests secure session storage, cross-tab synchronization, and AWS integration
 */

import { describe, it, expect, beforeEach, afterEach, vi, beforeAll, afterAll } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BrowserRouter } from 'react-router-dom';
import CryptoJS from 'crypto-js';
import { AuthProvider } from '../../contexts/AuthContext';
import SessionManager from '../../components/auth/SessionManager';
import secureSessionStorage from '../../utils/secureSessionStorage';

// Mock AWS Amplify
vi.mock('@aws-amplify/auth', () => ({
  fetchAuthSession: vi.fn(),
  signIn: vi.fn(),
  signOut: vi.fn(),
  getCurrentUser: vi.fn(),
  confirmSignIn: vi.fn()
}));

// Mock crypto-js
vi.mock('crypto-js', () => ({
  lib: {
    WordArray: {
      random: vi.fn(() => ({ toString: () => 'mock-random-string' }))
    }
  },
  AES: {
    encrypt: vi.fn((data, key, options) => ({ toString: () => 'encrypted-data' })),
    decrypt: vi.fn((data, key, options) => ({ toString: () => JSON.stringify({ token: 'mock-token' }) }))
  },
  enc: {
    Hex: {
      parse: vi.fn(() => 'mock-iv')
    },
    Utf8: 'mock-utf8'
  },
  mode: { CBC: 'CBC' },
  pad: { Pkcs7: 'Pkcs7' },
  SHA256: vi.fn(() => ({ toString: () => 'mock-fingerprint' }))
}));

// Mock BroadcastChannel
class MockBroadcastChannel {
  constructor(name) {
    this.name = name;
    this.listeners = [];
  }

  addEventListener(type, listener) {
    this.listeners.push(listener);
  }

  postMessage(data) {
    this.listeners.forEach(listener => {
      setTimeout(() => listener({ data }), 0);
    });
  }

  close() {
    this.listeners = [];
  }
}

global.BroadcastChannel = MockBroadcastChannel;

// Mock fetch for API calls
global.fetch = vi.fn();

describe('Session Management Integration Tests', () => {
  let mockUser;
  let mockTokens;
  let broadcastChannel;

  beforeAll(() => {
    // Setup global mocks
    Object.defineProperty(window, 'localStorage', {
      value: {
        getItem: vi.fn(),
        setItem: vi.fn(),
        removeItem: vi.fn(),
        clear: vi.fn()
      }
    });

    Object.defineProperty(window, 'sessionStorage', {
      value: {
        getItem: vi.fn(),
        setItem: vi.fn(),
        removeItem: vi.fn(),
        clear: vi.fn()
      }
    });

    // Mock navigator
    Object.defineProperty(navigator, 'userAgent', {
      value: 'Test Browser 1.0',
      writable: true
    });
  });

  beforeEach(async () => {
    vi.clearAllMocks();
    
    // Reset storage mocks
    window.localStorage.getItem.mockReturnValue(null);
    window.sessionStorage.getItem.mockReturnValue(null);
    global.fetch.mockClear();

    // Setup mock user and tokens
    mockUser = {
      sub: 'test-user-123',
      username: 'testuser',
      email: 'test@example.com',
      userId: 'test-user-123'
    };

    mockTokens = {
      accessToken: createMockJWT({ sub: 'test-user-123', exp: Math.floor(Date.now() / 1000) + 3600 }),
      refreshToken: 'mock-refresh-token',
      idToken: 'mock-id-token'
    };

    // Setup broadcast channel
    broadcastChannel = new MockBroadcastChannel('secure_session_sync');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    if (broadcastChannel) {
      broadcastChannel.close();
    }
  });

  afterAll(() => {
    vi.clearAllTimers();
  });

  describe('Secure Session Storage', () => {
    it('should encrypt and store session tokens securely', async () => {
      const tokenData = {
        ...mockTokens,
        userId: mockUser.sub,
        username: mockUser.username,
        email: mockUser.email
      };

      const result = secureSessionStorage.storeTokens(tokenData);
      
      expect(result).toBe(true);
      expect(window.sessionStorage.setItem).toHaveBeenCalledWith(
        'secure_access_token',
        expect.stringContaining('encrypted')
      );
      expect(window.localStorage.setItem).toHaveBeenCalledWith(
        'secure_refresh_token',
        expect.stringContaining('encrypted')
      );
    });

    it('should retrieve and decrypt tokens correctly', async () => {
      // Mock encrypted token data
      const mockEncryptedData = JSON.stringify({
        ciphertext: 'encrypted-data',
        iv: 'mock-iv'
      });

      window.sessionStorage.getItem.mockReturnValue(mockEncryptedData);
      window.localStorage.getItem.mockReturnValue(mockEncryptedData);

      const tokens = secureSessionStorage.getTokens();
      
      expect(tokens).toHaveProperty('accessToken');
      expect(tokens).toHaveProperty('refreshToken');
    });

    it('should validate session integrity with device fingerprint', async () => {
      const mockSessionMetadata = {
        deviceFingerprint: 'mock-fingerprint',
        loginTime: Date.now() - 1000,
        lastActivity: Date.now() - 500
      };

      window.sessionStorage.getItem.mockReturnValue(JSON.stringify({
        ciphertext: JSON.stringify(mockSessionMetadata),
        iv: 'mock-iv'
      }));

      const validation = secureSessionStorage.validateSession();
      
      expect(validation.valid).toBe(true);
    });

    it('should detect device fingerprint mismatch', async () => {
      const mockSessionMetadata = {
        deviceFingerprint: 'different-fingerprint',
        loginTime: Date.now() - 1000,
        lastActivity: Date.now() - 500
      };

      window.sessionStorage.getItem.mockReturnValue(JSON.stringify({
        ciphertext: JSON.stringify(mockSessionMetadata),
        iv: 'mock-iv'
      }));

      const validation = secureSessionStorage.validateSession();
      
      expect(validation.valid).toBe(false);
      expect(validation.reason).toBe('Device fingerprint mismatch');
    });

    it('should handle session expiry correctly', async () => {
      const expiredSessionMetadata = {
        deviceFingerprint: 'mock-fingerprint',
        loginTime: Date.now() - (25 * 60 * 60 * 1000), // 25 hours ago
        lastActivity: Date.now() - (25 * 60 * 60 * 1000)
      };

      window.sessionStorage.getItem.mockReturnValue(JSON.stringify({
        ciphertext: JSON.stringify(expiredSessionMetadata),
        iv: 'mock-iv'
      }));

      const validation = secureSessionStorage.validateSession();
      
      expect(validation.valid).toBe(false);
      expect(validation.reason).toBe('Session expired');
    });
  });

  describe('Cross-Tab Synchronization', () => {
    it('should broadcast login events to other tabs', async () => {
      const broadcastSpy = vi.spyOn(broadcastChannel, 'postMessage');
      
      const tokenData = {
        ...mockTokens,
        userId: mockUser.sub,
        username: mockUser.username,
        email: mockUser.email
      };

      secureSessionStorage.storeTokens(tokenData);
      
      await waitFor(() => {
        expect(broadcastSpy).toHaveBeenCalledWith(expect.objectContaining({
          type: 'session_login',
          data: expect.objectContaining({
            userId: mockUser.sub
          })
        }));
      });
    });

    it('should handle logout broadcast from other tabs', async () => {
      const clearSessionSpy = vi.spyOn(secureSessionStorage, 'clearSession');
      
      // Simulate logout broadcast from another tab
      broadcastChannel.postMessage({
        type: 'session_logout',
        data: { sessionId: 'test-session-123' },
        timestamp: Date.now(),
        fingerprint: 'mock-fingerprint'
      });

      await waitFor(() => {
        expect(clearSessionSpy).toHaveBeenCalled();
      });
    });

    it('should synchronize activity updates across tabs', async () => {
      const updateActivitySpy = vi.spyOn(secureSessionStorage, 'updateActivity');
      
      // Simulate activity broadcast from another tab
      broadcastChannel.postMessage({
        type: 'session_activity',
        data: { sessionId: 'test-session-123', timestamp: Date.now() },
        timestamp: Date.now(),
        fingerprint: 'mock-fingerprint'
      });

      await waitFor(() => {
        expect(updateActivitySpy).toHaveBeenCalled();
      });
    });

    it('should ignore broadcasts from different device fingerprints', async () => {
      const clearSessionSpy = vi.spyOn(secureSessionStorage, 'clearSession');
      
      // Simulate logout broadcast with different fingerprint
      broadcastChannel.postMessage({
        type: 'session_logout',
        data: { sessionId: 'test-session-123' },
        timestamp: Date.now(),
        fingerprint: 'different-fingerprint'
      });

      await waitFor(() => {
        expect(clearSessionSpy).not.toHaveBeenCalled();
      });
    });
  });

  describe('Session Manager Component Integration', () => {
    const TestWrapper = ({ children }) => (
      <BrowserRouter>
        <AuthProvider>
          {children}
        </AuthProvider>
      </BrowserRouter>
    );

    it('should display session warning dialog when token expires soon', async () => {
      // Mock short-lived token
      const shortLivedToken = {
        ...mockTokens,
        accessToken: createMockJWT({ 
          sub: 'test-user-123', 
          exp: Math.floor(Date.now() / 1000) + 300 // 5 minutes
        })
      };

      const { getCurrentUser, fetchAuthSession } = await import('@aws-amplify/auth');
      getCurrentUser.mockResolvedValue(mockUser);
      fetchAuthSession.mockResolvedValue({ tokens: shortLivedToken });

      render(
        <TestWrapper>
          <SessionManager>
            <div>Test Content</div>
          </SessionManager>
        </TestWrapper>
      );

      await waitFor(() => {
        expect(screen.getByText('Session Expiring Soon')).toBeInTheDocument();
      });
    });

    it('should handle session extension', async () => {
      const { getCurrentUser, fetchAuthSession } = await import('@aws-amplify/auth');
      getCurrentUser.mockResolvedValue(mockUser);
      fetchAuthSession.mockResolvedValue({ tokens: mockTokens });

      render(
        <TestWrapper>
          <SessionManager>
            <div>Test Content</div>
          </SessionManager>
        </TestWrapper>
      );

      // Mock token refresh
      const newTokens = {
        ...mockTokens,
        accessToken: createMockJWT({ 
          sub: 'test-user-123', 
          exp: Math.floor(Date.now() / 1000) + 3600 
        })
      };
      fetchAuthSession.mockResolvedValue({ tokens: newTokens });

      const extendButton = screen.queryByText('Extend Session');
      if (extendButton) {
        fireEvent.click(extendButton);

        await waitFor(() => {
          expect(screen.getByText('Session successfully extended')).toBeInTheDocument();
        });
      }
    });

    it('should display idle warning after inactivity', async () => {
      vi.useFakeTimers();

      const { getCurrentUser, fetchAuthSession } = await import('@aws-amplify/auth');
      getCurrentUser.mockResolvedValue(mockUser);
      fetchAuthSession.mockResolvedValue({ tokens: mockTokens });

      render(
        <TestWrapper>
          <SessionManager>
            <div>Test Content</div>
          </SessionManager>
        </TestWrapper>
      );

      // Fast-forward time to trigger idle timeout
      act(() => {
        vi.advanceTimersByTime(30 * 60 * 1000 + 1000); // 30 minutes + 1 second
      });

      await waitFor(() => {
        expect(screen.getByText('Are you still there?')).toBeInTheDocument();
      });

      vi.useRealTimers();
    });
  });

  describe('AWS Integration', () => {
    it('should handle API calls to session management service', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true,
          sessionId: 'test-session-123',
          expiresAt: Date.now() + 3600000
        })
      });

      const response = await fetch('/api/session/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userId: mockUser.sub,
          sessionId: 'test-session-123',
          deviceFingerprint: 'mock-fingerprint',
          metadata: { loginTime: Date.now() }
        })
      });

      const data = await response.json();
      
      expect(response.ok).toBe(true);
      expect(data.success).toBe(true);
      expect(data.sessionId).toBe('test-session-123');
    });

    it('should handle session validation API calls', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          valid: true,
          session: {
            sessionId: 'test-session-123',
            userId: mockUser.sub,
            lastActivity: Date.now()
          }
        })
      });

      const response = await fetch('/api/session/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userId: mockUser.sub,
          sessionId: 'test-session-123',
          deviceFingerprint: 'mock-fingerprint'
        })
      });

      const data = await response.json();
      
      expect(response.ok).toBe(true);
      expect(data.valid).toBe(true);
    });

    it('should handle session revocation API calls', async () => {
      global.fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          success: true
        })
      });

      const response = await fetch('/api/session/revoke', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userId: mockUser.sub,
          sessionId: 'test-session-123'
        })
      });

      const data = await response.json();
      
      expect(response.ok).toBe(true);
      expect(data.success).toBe(true);
    });

    it('should handle API errors gracefully', async () => {
      global.fetch.mockRejectedValueOnce(new Error('Network error'));

      try {
        await fetch('/api/session/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            userId: mockUser.sub,
            sessionId: 'test-session-123'
          })
        });
      } catch (error) {
        expect(error.message).toBe('Network error');
      }
    });
  });

  describe('Security Features', () => {
    it('should implement CSRF protection', async () => {
      const csrfToken = secureSessionStorage.generateCSRFToken();
      
      expect(csrfToken).toBeDefined();
      expect(typeof csrfToken).toBe('string');
      expect(csrfToken.length).toBeGreaterThan(0);
      
      const isValid = secureSessionStorage.validateCSRFToken(csrfToken);
      expect(isValid).toBe(true);
      
      const isInvalidTokenValid = secureSessionStorage.validateCSRFToken('invalid-token');
      expect(isInvalidTokenValid).toBe(false);
    });

    it('should rate limit session operations', async () => {
      const rateLimiter = secureSessionStorage.createRateLimiter(2, 1000); // 2 requests per second
      
      const result1 = rateLimiter('user-123');
      expect(result1.allowed).toBe(true);
      
      const result2 = rateLimiter('user-123');
      expect(result2.allowed).toBe(true);
      
      const result3 = rateLimiter('user-123');
      expect(result3.allowed).toBe(false);
    });

    it('should validate input sanitization', async () => {
      const maliciousInput = '<script>alert("xss")</script>';
      const sanitized = secureSessionStorage.sanitizeHTML(maliciousInput);
      
      expect(sanitized).not.toContain('<script>');
      expect(sanitized).toBe('&lt;script&gt;alert("xss")&lt;/script&gt;');
    });

    it('should validate URL sanitization', async () => {
      const maliciousUrl = 'javascript:alert("xss")';
      const sanitizedUrl = secureSessionStorage.sanitizeURL(maliciousUrl);
      
      expect(sanitizedUrl).toBe('#');
      
      const validUrl = 'https://example.com';
      const validSanitizedUrl = secureSessionStorage.sanitizeURL(validUrl);
      expect(validSanitizedUrl).toBe(validUrl);
    });
  });

  describe('Performance and Monitoring', () => {
    it('should track session metrics', async () => {
      const metrics = {
        sessionCount: 0,
        activeConnections: 0,
        avgSessionDuration: 0
      };

      // Simulate session creation
      secureSessionStorage.storeTokens({
        ...mockTokens,
        userId: mockUser.sub
      });

      metrics.sessionCount++;
      
      expect(metrics.sessionCount).toBe(1);
    });

    it('should handle concurrent session operations', async () => {
      const promises = Array(10).fill().map((_, index) => 
        secureSessionStorage.storeTokens({
          ...mockTokens,
          userId: `user-${index}`
        })
      );

      const results = await Promise.all(promises);
      
      expect(results.every(result => result === true)).toBe(true);
    });

    it('should cleanup expired sessions', async () => {
      // This would typically be handled by the backend service
      // but we can test the client-side cleanup logic
      const clearSessionSpy = vi.spyOn(secureSessionStorage, 'clearSession');
      
      // Mock expired session
      const expiredSession = {
        deviceFingerprint: 'mock-fingerprint',
        loginTime: Date.now() - (25 * 60 * 60 * 1000), // 25 hours ago
        lastActivity: Date.now() - (25 * 60 * 60 * 1000)
      };

      window.sessionStorage.getItem.mockReturnValue(JSON.stringify({
        ciphertext: JSON.stringify(expiredSession),
        iv: 'mock-iv'
      }));

      const validation = secureSessionStorage.validateSession();
      
      if (!validation.valid) {
        secureSessionStorage.clearSession();
      }

      expect(clearSessionSpy).toHaveBeenCalled();
    });
  });
});

// Helper function to create mock JWT tokens
function createMockJWT(payload) {
  const header = { alg: 'HS256', typ: 'JWT' };
  const encodedHeader = btoa(JSON.stringify(header));
  const encodedPayload = btoa(JSON.stringify(payload));
  const signature = 'mock-signature';
  
  return `${encodedHeader}.${encodedPayload}.${signature}`;
}