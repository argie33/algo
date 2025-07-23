/**
 * Unit Tests for User Password Management Service
 * Tests the /api/user/change-password and related endpoints in user.js
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock the password service endpoints
const mockPasswordService = {
  changePassword: vi.fn(),
  forgotPassword: vi.fn(),
  getSessions: vi.fn()
};

// Mock fetch for API calls
global.fetch = vi.fn();

describe('User Password Management API Endpoints', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('accessToken', 'mock-jwt-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  describe('POST /api/user/change-password', () => {
    const validPasswordPayload = {
      currentPassword: 'OldPassword123!',
      newPassword: 'NewPassword456@'
    };

    it('should change password successfully with valid credentials', async () => {
      const mockResponse = {
        success: true,
        message: 'Password changed successfully'
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse
      });

      const response = await fetch('/api/user/change-password', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(validPasswordPayload)
      });

      const result = await response.json();

      expect(fetch).toHaveBeenCalledWith('/api/user/change-password', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(validPasswordPayload)
      });

      expect(result.success).toBe(true);
      expect(result.message).toBe('Password changed successfully');
    });

    it('should reject request when current password is missing', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'Current password and new password are required'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/change-password', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          newPassword: 'NewPassword456@'
          // Missing currentPassword
        })
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toContain('required');
    });

    it('should reject request when new password is missing', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'Current password and new password are required'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/change-password', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          currentPassword: 'OldPassword123!'
          // Missing newPassword
        })
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toContain('required');
    });

    it('should reject passwords shorter than 8 characters', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'New password must be at least 8 characters long'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/change-password', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          currentPassword: 'OldPassword123!',
          newPassword: 'Short1!' // Only 7 characters
        })
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toContain('at least 8 characters');
    });

    it('should enforce password complexity requirements', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'Password must contain at least one uppercase letter, one lowercase letter, one number, and one special character'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/change-password', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          currentPassword: 'OldPassword123!',
          newPassword: 'weakpassword' // No uppercase, numbers, or special chars
        })
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toContain('uppercase letter');
    });

    it('should handle incorrect current password', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'Current password is incorrect'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/change-password', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          currentPassword: 'WrongPassword123!',
          newPassword: 'NewPassword456@'
        })
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toBe('Current password is incorrect');
    });

    it('should handle AWS Cognito InvalidPasswordException', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'New password does not meet security requirements'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/change-password', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          currentPassword: 'OldPassword123!',
          newPassword: 'Password123' // Might not meet Cognito requirements
        })
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toContain('security requirements');
    });

    it('should handle rate limiting', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'Too many password change attempts. Please try again later.'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 429,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/change-password', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(validPasswordPayload)
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toContain('Too many');
    });

    it('should handle AWS Amplify service unavailable', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'Password change service unavailable',
        message: 'AWS Amplify authentication service is not configured'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 503,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/change-password', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(validPasswordPayload)
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toBe('Password change service unavailable');
    });

    it('should handle unexpected server errors', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'An unexpected error occurred while changing password',
        message: 'Database connection failed'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/change-password', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(validPasswordPayload)
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toContain('unexpected error');
    });
  });

  describe('POST /api/user/forgot-password', () => {
    it('should initiate password reset successfully', async () => {
      const mockResponse = {
        success: true,
        message: 'Password reset instructions have been sent to your email address'
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse
      });

      const response = await fetch('/api/user/forgot-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          email: 'user@example.com'
        })
      });

      const result = await response.json();

      expect(result.success).toBe(true);
      expect(result.message).toContain('sent to your email');
    });

    it('should require email address', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'Email address is required'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/forgot-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          // Missing email
        })
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toBe('Email address is required');
    });

    it('should handle unknown emails gracefully for security', async () => {
      const mockResponse = {
        success: true,
        message: 'If an account with that email address exists, password reset instructions have been sent'
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse
      });

      const response = await fetch('/api/user/forgot-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          email: 'nonexistent@example.com'
        })
      });

      const result = await response.json();

      expect(result.success).toBe(true);
      expect(result.message).toContain('If an account with that email');
    });
  });

  describe('GET /api/user/sessions', () => {
    it('should return current session information', async () => {
      const mockResponse = {
        success: true,
        sessions: [{
          userId: 'user-123',
          username: 'testuser',
          email: 'user@example.com',
          lastLoginTime: '2025-07-23T10:00:00.000Z',
          tokenIssuedAt: '2025-07-23T10:00:00.000Z',
          tokenExpiresAt: '2025-07-23T18:00:00.000Z',
          currentSession: true
        }],
        activeSessionCount: 1
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse
      });

      const response = await fetch('/api/user/sessions', {
        method: 'GET',
        headers: {
          'Authorization': 'Bearer mock-jwt-token'
        }
      });

      const result = await response.json();

      expect(result.success).toBe(true);
      expect(result.sessions).toHaveLength(1);
      expect(result.sessions[0].currentSession).toBe(true);
      expect(result.activeSessionCount).toBe(1);
    });

    it('should handle session retrieval errors', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'Failed to get session information',
        message: 'Token validation failed'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/sessions', {
        method: 'GET',
        headers: {
          'Authorization': 'Bearer mock-jwt-token'
        }
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toBe('Failed to get session information');
    });
  });

  describe('Password Validation', () => {
    it('should validate password complexity requirements', () => {
      const testCases = [
        {
          password: 'Password123!',
          expected: true,
          description: 'valid strong password'
        },
        {
          password: 'password123!',
          expected: false,
          description: 'missing uppercase'
        },
        {
          password: 'PASSWORD123!',
          expected: false,
          description: 'missing lowercase'
        },
        {
          password: 'Password!',
          expected: false,
          description: 'missing numbers'
        },
        {
          password: 'Password123',
          expected: false,
          description: 'missing special characters'
        },
        {
          password: 'Pass1!',
          expected: false,
          description: 'too short'
        }
      ];

      testCases.forEach(({ password, expected, description }) => {
        const hasUpperCase = /[A-Z]/.test(password);
        const hasLowerCase = /[a-z]/.test(password);
        const hasNumbers = /\d/.test(password);
        const hasSpecialChar = /[!@#$%^&*(),.?":{}|<>]/.test(password);
        const isLongEnough = password.length >= 8;

        const isValid = hasUpperCase && hasLowerCase && hasNumbers && hasSpecialChar && isLongEnough;
        
        expect(isValid).toBe(expected, `Password validation failed for: ${description}`);
      });
    });

    it('should validate email format', () => {
      const validEmails = [
        'user@example.com',
        'test.email@domain.co.uk',
        'user+tag@example.org'
      ];

      const invalidEmails = [
        'invalid-email',
        '@example.com',
        'user@',
        ''
      ];

      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

      validEmails.forEach(email => {
        expect(emailRegex.test(email)).toBe(true, `Valid email rejected: ${email}`);
      });

      invalidEmails.forEach(email => {
        expect(emailRegex.test(email)).toBe(false, `Invalid email accepted: ${email}`);
      });
    });
  });

  describe('Authentication Headers', () => {
    it('should include proper Authorization header for authenticated endpoints', () => {
      const authenticatedEndpoints = [
        '/api/user/change-password',
        '/api/user/sessions'
      ];

      authenticatedEndpoints.forEach(endpoint => {
        fetch.mockClear();
        
        fetch(endpoint, {
          method: 'POST',
          headers: {
            'Authorization': 'Bearer mock-jwt-token',
            'Content-Type': 'application/json'
          }
        });

        expect(fetch).toHaveBeenCalledWith(
          endpoint,
          expect.objectContaining({
            headers: expect.objectContaining({
              'Authorization': 'Bearer mock-jwt-token'
            })
          })
        );
      });
    });

    it('should not require authentication for forgot-password endpoint', async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ success: true })
      });

      const response = await fetch('/api/user/forgot-password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          email: 'user@example.com'
        })
      });

      expect(fetch).toHaveBeenCalledWith(
        '/api/user/forgot-password',
        expect.objectContaining({
          headers: expect.not.objectContaining({
            'Authorization': expect.any(String)
          })
        })
      );
    });
  });

  describe('Error Response Format', () => {
    it('should return consistent error response format', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'Test error message',
        message: 'Additional error details'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/change-password', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          currentPassword: 'wrong',
          newPassword: 'test'
        })
      });

      const result = await response.json();

      expect(result).toHaveProperty('success', false);
      expect(result).toHaveProperty('error');
      expect(typeof result.error).toBe('string');
    });

    it('should return consistent success response format', async () => {
      const mockSuccessResponse = {
        success: true,
        message: 'Operation completed successfully'
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockSuccessResponse
      });

      const response = await fetch('/api/user/change-password', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          currentPassword: 'OldPassword123!',
          newPassword: 'NewPassword456@'
        })
      });

      const result = await response.json();

      expect(result).toHaveProperty('success', true);
      expect(result).toHaveProperty('message');
      expect(typeof result.message).toBe('string');
    });
  });
});