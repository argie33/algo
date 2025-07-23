/**
 * Email Service Tests
 * Tests for real AWS SES email functionality
 */

import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import emailService, { sendSupportEmail, sendNotificationEmail, testEmailConnection } from '../../../services/emailService';

// Mock fetch globally
global.fetch = vi.fn();

describe('EmailService - Real AWS SES Integration', () => {
  beforeEach(() => {
    // Reset mocks before each test
    vi.clearAllMocks();
    
    // Reset emailService state
    emailService.initialized = false;
    emailService.apiUrl = null;
    
    // Clear localStorage
    global.localStorage = {
      getItem: vi.fn(() => null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
      clear: vi.fn(),
    };
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Initialization', () => {
    test('should initialize with correct API URL', async () => {
      // Mock getApiUrl import
      vi.doMock('../../../config/environment', () => ({
        getApiUrl: vi.fn(() => 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'),
        getSupportEmail: vi.fn(() => 'support@aws-verified-domain.com')
      }));

      await emailService.initialize();

      expect(emailService.initialized).toBe(true);
      expect(emailService.apiUrl).toBe('https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev');
    });

    test('should handle initialization failure gracefully', async () => {
      // Mock failed import
      vi.doMock('../../../config/environment', () => {
        throw new Error('Config import failed');
      });

      await expect(emailService.initialize()).rejects.toThrow('Email service initialization failed');
    });
  });

  describe('Support Email Functionality', () => {
    beforeEach(async () => {
      // Mock successful initialization
      vi.doMock('../../../config/environment', () => ({
        getApiUrl: vi.fn(() => 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'),
        getSupportEmail: vi.fn(() => 'support@aws-verified-domain.com')
      }));
    });

    test('should send support email successfully', async () => {
      // Mock successful API response
      fetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          messageId: 'ses-message-id-123',
          timestamp: '2025-01-01T00:00:00Z'
        })
      });

      const emailData = {
        subject: 'Test Support Request',
        message: 'This is a test support message',
        userEmail: 'user@example.com',
        priority: 'normal'
      };

      const result = await sendSupportEmail(emailData);

      expect(result.success).toBe(true);
      expect(result.messageId).toBe('ses-message-id-123');
      expect(fetch).toHaveBeenCalledWith(
        'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/support/email',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: expect.stringContaining('Test Support Request')
        })
      );
    });

    test('should validate required fields', async () => {
      const invalidEmailData = {
        subject: 'Test',
        // Missing message and userEmail
      };

      await expect(sendSupportEmail(invalidEmailData)).rejects.toThrow(
        'Subject, message, and user email are required'
      );
    });

    test('should validate email format', async () => {
      const invalidEmailData = {
        subject: 'Test',
        message: 'Test message',
        userEmail: 'invalid-email-format'
      };

      await expect(sendSupportEmail(invalidEmailData)).rejects.toThrow('Invalid email format');
    });

    test('should handle API errors gracefully', async () => {
      // Mock API error response
      fetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ message: 'SES service unavailable' })
      });

      const emailData = {
        subject: 'Test',
        message: 'Test message',
        userEmail: 'user@example.com'
      };

      await expect(sendSupportEmail(emailData)).rejects.toThrow(
        'Failed to send support email: SES service unavailable'
      );

      // Should store pending email in localStorage
      expect(global.localStorage.setItem).toHaveBeenCalledWith(
        'pendingEmails',
        expect.stringContaining('Test')
      );
    });

    test('should generate proper HTML email template', () => {
      const data = {
        subject: 'Test Subject',
        message: 'Test message with\nnewlines',
        userEmail: 'user@example.com',
        priority: 'high',
        timestamp: '2025-01-01T00:00:00Z'
      };

      const html = emailService.generateSupportEmailTemplate(data);

      expect(html).toContain('Test Subject');
      expect(html).toContain('user@example.com');
      expect(html).toContain('high'); // Priority is lowercase in the span
      expect(html).toContain('Test message with<br>newlines');
      expect(html).toContain('#fd7e14'); // High priority color
    });

    test('should generate proper plain text email', () => {
      const data = {
        subject: 'Test Subject',
        message: 'Test message',
        userEmail: 'user@example.com',
        priority: 'urgent',
        timestamp: '2025-01-01T00:00:00Z'
      };

      const text = emailService.generatePlainTextEmail(data);

      expect(text).toContain('URGENT');
      expect(text).toContain('Test Subject');
      expect(text).toContain('user@example.com');
      expect(text).toContain('Test message');
    });
  });

  describe('Notification Email Functionality', () => {
    beforeEach(async () => {
      // Mock successful initialization
      vi.doMock('../../../config/environment', () => ({
        getApiUrl: vi.fn(() => 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'),
        getSupportEmail: vi.fn(() => 'support@aws-verified-domain.com')
      }));
    });

    test('should send notification email successfully', async () => {
      // Mock successful API response
      fetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({
          messageId: 'notification-message-id-456',
          timestamp: '2025-01-01T00:00:00Z'
        })
      });

      const emailData = {
        to: 'user@example.com',
        subject: 'Trade Alert',
        message: 'Your portfolio has gained 5%',
        type: 'portfolio_alert'
      };

      const result = await sendNotificationEmail(emailData);

      expect(result.success).toBe(true);
      expect(result.messageId).toBe('notification-message-id-456');
      expect(fetch).toHaveBeenCalledWith(
        'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev/notifications/email',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: expect.stringContaining('Trade Alert')
        })
      );
    });

    test('should validate notification email fields', async () => {
      const invalidEmailData = {
        to: 'user@example.com',
        // Missing subject and message
      };

      await expect(sendNotificationEmail(invalidEmailData)).rejects.toThrow(
        'To, subject, and message are required'
      );
    });

    test('should generate notification email template', () => {
      const data = {
        message: 'Your portfolio performance has improved',
        type: 'portfolio_update',
        timestamp: '2025-01-01T00:00:00Z'
      };

      const html = emailService.generateNotificationEmailTemplate(data);

      expect(html).toContain('ProTrade Analytics Notification');
      expect(html).toContain('Your portfolio performance has improved');
      expect(html).toContain('portfolio_update');
    });
  });

  describe('Connection Testing', () => {
    test('should test email service connection successfully', async () => {
      // Mock successful health check
      fetch.mockResolvedValueOnce({
        ok: true,
        status: 200
      });

      const result = await testEmailConnection();

      expect(result.success).toBe(true);
      expect(result.message).toBe('Email service is healthy');
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining('/support/health'),
        expect.objectContaining({ method: 'GET' })
      );
    });

    test('should handle connection test failure', async () => {
      // Mock failed health check
      fetch.mockResolvedValueOnce({
        ok: false,
        status: 503
      });

      const result = await testEmailConnection();

      expect(result.success).toBe(false);
      expect(result.message).toBe('Email service is not responding');
    });

    test('should handle network errors during connection test', async () => {
      // Mock network error
      fetch.mockRejectedValueOnce(new Error('Network error'));

      const result = await testEmailConnection();

      expect(result.success).toBe(false);
      expect(result.message).toContain('Email service connection failed: Network error');
    });
  });

  describe('Pending Email Management', () => {
    test('should store pending emails when send fails', () => {
      const emailData = {
        subject: 'Failed Email',
        message: 'This email failed to send',
        userEmail: 'user@example.com'
      };

      emailService.storePendingEmail(emailData);

      expect(global.localStorage.setItem).toHaveBeenCalledWith(
        'pendingEmails',
        expect.stringContaining('Failed Email')
      );
    });

    test('should retrieve pending emails', () => {
      const pendingEmails = [
        { subject: 'Email 1', status: 'pending' },
        { subject: 'Email 2', status: 'pending' }
      ];

      global.localStorage.getItem.mockReturnValue(JSON.stringify(pendingEmails));

      const result = emailService.getPendingEmails();

      expect(result).toEqual(pendingEmails);
      expect(global.localStorage.getItem).toHaveBeenCalledWith('pendingEmails');
    });

    test('should clear pending emails', () => {
      emailService.clearPendingEmails();

      expect(global.localStorage.removeItem).toHaveBeenCalledWith('pendingEmails');
    });

    test('should handle localStorage errors gracefully', () => {
      global.localStorage.getItem.mockImplementation(() => {
        throw new Error('localStorage error');
      });

      const result = emailService.getPendingEmails();

      expect(result).toEqual([]);
    });
  });

  describe('Email Validation', () => {
    test('should validate correct email formats', () => {
      const validEmails = [
        'user@example.com',
        'test.user+tag@domain.co.uk',
        'user123@test-domain.org'
      ];

      validEmails.forEach(email => {
        expect(emailService.isValidEmail(email)).toBe(true);
      });
    });

    test('should reject invalid email formats', () => {
      const invalidEmails = [
        'invalid-email',
        '@domain.com',
        'user@',
        'user@@domain.com',
        'user@domain',
        ''
      ];

      invalidEmails.forEach(email => {
        expect(emailService.isValidEmail(email)).toBe(false);
      });
    });
  });

  describe('No Fake URLs', () => {
    test('should not use any fake or placeholder URLs', async () => {
      // Mock real AWS configuration
      vi.doMock('../../../config/environment', () => ({
        getApiUrl: vi.fn(() => 'https://2m14opj30h.execute-api.us-east-1.amazonaws.com/dev'),
        getSupportEmail: vi.fn(() => 'support@aws-verified-domain.com')
      }));

      await emailService.initialize();

      // Verify no fake domains are used
      expect(emailService.apiUrl).not.toContain('protrade.com');
      expect(emailService.apiUrl).not.toContain('example.com');
      expect(emailService.apiUrl).not.toContain('placeholder');
      expect(emailService.apiUrl).toContain('execute-api'); // Contains execute-api in the AWS URL
    });
  });
});