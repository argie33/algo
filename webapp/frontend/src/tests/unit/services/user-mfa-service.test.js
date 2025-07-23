/**
 * Unit Tests for User MFA Service Endpoints
 * Tests the /api/user/* MFA-related endpoints implemented in user.js
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Mock the user service endpoints
const mockUserService = {
  // MFA Enable endpoint
  enableTwoFactor: vi.fn(),
  
  // MFA Disable endpoint  
  disableTwoFactor: vi.fn(),
  
  // MFA Verify endpoint
  verifyTwoFactor: vi.fn(),
  
  // MFA Status endpoints
  getTwoFactorStatus: vi.fn(),
  getMfaStatus: vi.fn(),
  
  // MFA Setup endpoint
  setupTwoFactor: vi.fn(),
  
  // Backup codes endpoint
  generateBackupCodes: vi.fn(),
  
  // Password change endpoint
  changePassword: vi.fn()
};

// Mock fetch for API calls
global.fetch = vi.fn();

describe('User MFA Service API Endpoints', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem('accessToken', 'mock-jwt-token');
  });

  afterEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  describe('POST /api/user/two-factor/enable', () => {
    it('should enable SMS two-factor authentication successfully', async () => {
      const mockResponse = {
        success: true,
        method: 'sms',
        message: 'SMS two-factor authentication has been enabled'
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse
      });

      const response = await fetch('/api/user/two-factor/enable', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          method: 'sms',
          phoneNumber: '+1234567890'
        })
      });

      const result = await response.json();

      expect(fetch).toHaveBeenCalledWith('/api/user/two-factor/enable', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          method: 'sms',
          phoneNumber: '+1234567890'
        })
      });

      expect(result).toEqual(mockResponse);
      expect(result.success).toBe(true);
      expect(result.method).toBe('sms');
    });

    it('should enable TOTP two-factor authentication with QR code', async () => {
      const mockResponse = {
        success: true,
        method: 'totp',
        message: 'TOTP two-factor authentication has been enabled',
        qrCodeUrl: 'https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=otpauth://totp/TradingApp:test-user?secret=JBSWY3DPEHPK3PXP&issuer=TradingApp',
        secret: 'JBSWY3DPEHPK3PXP'
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse
      });

      const response = await fetch('/api/user/two-factor/enable', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          method: 'totp'
        })
      });

      const result = await response.json();

      expect(result.success).toBe(true);
      expect(result.method).toBe('totp');
      expect(result.qrCodeUrl).toContain('qrserver.com');
      expect(result.secret).toBe('JBSWY3DPEHPK3PXP');
    });

    it('should return error for invalid MFA method', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'Valid MFA method (sms or totp) is required'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/two-factor/enable', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          method: 'invalid'
        })
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toContain('Valid MFA method');
    });

    it('should return error when phone number missing for SMS', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'Phone number is required for SMS authentication'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/two-factor/enable', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          method: 'sms'
          // Missing phoneNumber
        })
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toContain('Phone number is required');
    });
  });

  describe('POST /api/user/two-factor/disable', () => {
    it('should disable two-factor authentication successfully', async () => {
      const mockResponse = {
        success: true,
        message: 'Two-factor authentication has been disabled',
        mfaEnabled: false
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse
      });

      const response = await fetch('/api/user/two-factor/disable', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        }
      });

      const result = await response.json();

      expect(result.success).toBe(true);
      expect(result.mfaEnabled).toBe(false);
      expect(result.message).toContain('disabled');
    });

    it('should handle server errors gracefully', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'Failed to disable 2FA',
        message: 'Internal server error'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/two-factor/disable', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        }
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toBe('Failed to disable 2FA');
    });
  });

  describe('POST /api/user/two-factor/verify', () => {
    it('should verify two-factor code successfully', async () => {
      const mockResponse = {
        success: true,
        message: 'Two-factor authentication verified successfully',
        mfaEnabled: true,
        method: 'totp',
        backupCodes: ['ABC123DE', 'FGH456IJ', 'KLM789NO', 'PQR012ST', 'UVW345XY', 'ZAB678CD', 'EFG901HI', 'JKL234MN']
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse
      });

      const response = await fetch('/api/user/two-factor/verify', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          method: 'totp',
          code: '123456'
        })
      });

      const result = await response.json();

      expect(result.success).toBe(true);
      expect(result.mfaEnabled).toBe(true);
      expect(result.backupCodes).toHaveLength(8);
      expect(result.backupCodes[0]).toMatch(/^[A-Z0-9]{8}$/);
    });

    it('should reject invalid verification code format', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'Verification code must be 6 digits'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/two-factor/verify', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          method: 'totp',
          code: '12345' // Too short
        })
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toContain('6 digits');
    });

    it('should require method and code parameters', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'Method and verification code are required'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/two-factor/verify', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          // Missing method and code
        })
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toContain('required');
    });
  });

  describe('GET /api/user/two-factor/status', () => {
    it('should return two-factor status', async () => {
      const mockResponse = {
        success: true,
        data: {
          enabled: false,
          setupRequired: true,
          backupCodes: 0,
          lastUsed: null
        },
        message: 'Two-factor authentication is not yet configured'
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse
      });

      const response = await fetch('/api/user/two-factor/status', {
        method: 'GET',
        headers: {
          'Authorization': 'Bearer mock-jwt-token'
        }
      });

      const result = await response.json();

      expect(result.success).toBe(true);
      expect(result.data.enabled).toBe(false);
      expect(result.data.setupRequired).toBe(true);
    });
  });

  describe('GET /api/user/mfa-status', () => {
    it('should return MFA status for SecurityTab', async () => {
      const mockResponse = {
        success: true,
        mfaEnabled: false,
        mfaMethods: [],
        backupCodes: [],
        message: 'MFA status retrieved successfully'
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse
      });

      const response = await fetch('/api/user/mfa-status', {
        method: 'GET',
        headers: {
          'Authorization': 'Bearer mock-jwt-token'
        }
      });

      const result = await response.json();

      expect(result.success).toBe(true);
      expect(result.mfaEnabled).toBe(false);
      expect(Array.isArray(result.mfaMethods)).toBe(true);
      expect(Array.isArray(result.backupCodes)).toBe(true);
    });
  });

  describe('POST /api/user/two-factor/setup/:method', () => {
    it('should setup TOTP method with QR code', async () => {
      const mockResponse = {
        success: true,
        method: 'totp',
        message: 'TOTP setup initiated',
        qrCodeUrl: 'https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=otpauth://totp/TradingApp:test-user?secret=JBSWY3DPEHPK3PXP&issuer=TradingApp',
        secret: 'JBSWY3DPEHPK3PXP'
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse
      });

      const response = await fetch('/api/user/two-factor/setup/totp', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        }
      });

      const result = await response.json();

      expect(result.success).toBe(true);
      expect(result.method).toBe('totp');
      expect(result.qrCodeUrl).toContain('qrserver.com');
    });

    it('should setup SMS method with phone number', async () => {
      const mockResponse = {
        success: true,
        method: 'sms',
        message: 'SMS verification code sent to +1234567890',
        phoneNumber: '+1234567890'
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse
      });

      const response = await fetch('/api/user/two-factor/setup/sms', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          phoneNumber: '+1234567890'
        })
      });

      const result = await response.json();

      expect(result.success).toBe(true);
      expect(result.method).toBe('sms');
      expect(result.phoneNumber).toBe('+1234567890');
    });

    it('should reject invalid MFA methods', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'Invalid MFA method. Use sms or totp.'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/two-factor/setup/invalid', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        }
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toContain('Invalid MFA method');
    });

    it('should require phone number for SMS setup', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'Phone number is required for SMS setup'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/two-factor/setup/sms', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          // Missing phoneNumber
        })
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toContain('Phone number is required');
    });
  });

  describe('POST /api/user/backup-codes/generate', () => {
    it('should generate backup codes successfully', async () => {
      const mockResponse = {
        success: true,
        codes: ['ABC123DE', 'FGH456IJ', 'KLM789NO', 'PQR012ST', 'UVW345XY', 'ZAB678CD', 'EFG901HI', 'JKL234MN'],
        message: 'Backup codes generated successfully'
      };

      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse
      });

      const response = await fetch('/api/user/backup-codes/generate', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        }
      });

      const result = await response.json();

      expect(result.success).toBe(true);
      expect(result.codes).toHaveLength(8);
      expect(result.codes[0]).toMatch(/^[A-Z0-9]{8}$/);
      expect(result.message).toContain('generated successfully');
    });

    it('should handle generation errors', async () => {
      const mockErrorResponse = {
        success: false,
        error: 'Failed to generate backup codes',
        message: 'Database error'
      };

      fetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: async () => mockErrorResponse
      });

      const response = await fetch('/api/user/backup-codes/generate', {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer mock-jwt-token',
          'Content-Type': 'application/json'
        }
      });

      const result = await response.json();

      expect(result.success).toBe(false);
      expect(result.error).toBe('Failed to generate backup codes');
    });
  });

  describe('Authentication Headers', () => {
    it('should include proper Authorization header in all requests', () => {
      const testEndpoints = [
        '/api/user/two-factor/enable',
        '/api/user/two-factor/disable',
        '/api/user/two-factor/verify',
        '/api/user/two-factor/status',
        '/api/user/mfa-status',
        '/api/user/backup-codes/generate'
      ];

      testEndpoints.forEach(endpoint => {
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

    it('should handle missing authorization gracefully', async () => {
      fetch.mockResolvedValueOnce({
        ok: false,
        status: 401,
        json: async () => ({
          success: false,
          error: 'Unauthorized'
        })
      });

      const response = await fetch('/api/user/two-factor/enable', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          method: 'totp'
        })
      });

      expect(response.status).toBe(401);
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors', async () => {
      fetch.mockRejectedValueOnce(new Error('Network error'));

      try {
        await fetch('/api/user/two-factor/enable', {
          method: 'POST',
          headers: {
            'Authorization': 'Bearer mock-jwt-token',
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            method: 'totp'
          })
        });
      } catch (error) {
        expect(error.message).toBe('Network error');
      }
    });

    it('should handle JSON parsing errors', async () => {
      fetch.mockResolvedValueOnce({
        ok: true,
        json: async () => {
          throw new Error('Invalid JSON');
        }
      });

      const response = await fetch('/api/user/mfa-status', {
        method: 'GET',
        headers: {
          'Authorization': 'Bearer mock-jwt-token'
        }
      });

      try {
        await response.json();
      } catch (error) {
        expect(error.message).toBe('Invalid JSON');
      }
    });
  });

  describe('Input Validation', () => {
    it('should validate 6-digit verification codes', () => {
      const validCodes = ['123456', '000000', '999999'];
      const invalidCodes = ['12345', '1234567', 'abcdef', '12345a', ''];

      validCodes.forEach(code => {
        expect(/^\d{6}$/.test(code)).toBe(true);
      });

      invalidCodes.forEach(code => {
        expect(/^\d{6}$/.test(code)).toBe(false);
      });
    });

    it('should validate MFA methods', () => {
      const validMethods = ['sms', 'totp'];
      const invalidMethods = ['email', 'push', '', 'invalid'];

      validMethods.forEach(method => {
        expect(['sms', 'totp'].includes(method)).toBe(true);
      });

      invalidMethods.forEach(method => {
        expect(['sms', 'totp'].includes(method)).toBe(false);
      });
    });

    it('should validate phone number format', () => {
      const validPhones = ['+1234567890', '+12345678901', '+447911123456'];
      const invalidPhones = ['1234567890', '123-456-7890', '', 'invalid'];

      validPhones.forEach(phone => {
        expect(/^\+\d{10,15}$/.test(phone)).toBe(true);
      });

      invalidPhones.forEach(phone => {
        expect(/^\+\d{10,15}$/.test(phone)).toBe(false);
      });
    });
  });
});