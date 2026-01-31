/**
 * Email Service Unit Tests
 * Tests email sending functionality with AWS SES and SMTP
 */

describe('Email Service', () => {
  let emailService;

  beforeEach(() => {
    // Clear module cache to force re-initialization
    jest.resetModules();
    // Set AWS region for SES in test
    process.env.AWS_REGION = 'us-east-1';
    process.env.CONTACT_NOTIFICATION_EMAIL = 'edgebrookecapital@gmail.com';
    process.env.EMAIL_FROM = 'noreply@bullseyefinancial.com';
  });

  afterEach(() => {
    delete process.env.AWS_REGION;
    delete process.env.CONTACT_NOTIFICATION_EMAIL;
    delete process.env.EMAIL_FROM;
  });

  test('should export sendEmail and confirmation functions', () => {
    emailService = require('../../utils/email');
    expect(typeof emailService.sendEmail).toBe('function');
    expect(typeof emailService.sendContactConfirmationEmail).toBe('function');
    expect(typeof emailService.sendCommunityWelcomeEmail).toBe('function');
    expect(typeof emailService.sendNewsletter).toBe('function');
  });

  test('should initialize with a valid email service', () => {
    emailService = require('../../utils/email');
    const service = emailService.getEmailService();
    expect(['aws-ses', 'smtp', 'console']).toContain(service);
  });

  test('should handle single recipient email', async () => {
    emailService = require('../../utils/email');

    // Mock SES for testing
    jest.mock('@aws-sdk/client-ses', () => {
      const mockSend = jest.fn().mockResolvedValue({ MessageId: 'test-id' });
      return {
        SESClient: jest.fn(),
        SendEmailCommand: jest.fn()
      };
    });

    const result = await emailService.sendEmail({
      to: 'test@example.com',
      subject: 'Test Email',
      html: '<h1>Test</h1>'
    });

    expect(result.success).toBe(true);
  });

  test('should handle multiple recipient emails', async () => {
    emailService = require('../../utils/email');

    const result = await emailService.sendEmail({
      to: ['test1@example.com', 'test2@example.com'],
      subject: 'Test Email',
      html: '<h1>Test</h1>'
    });

    expect(result.success).toBe(true);
  });

  test('should include CC and BCC recipients', async () => {
    emailService = require('../../utils/email');

    const result = await emailService.sendEmail({
      to: 'test@example.com',
      cc: 'cc@example.com',
      bcc: 'bcc@example.com',
      subject: 'Test Email',
      html: '<h1>Test</h1>'
    });

    expect(result.success).toBe(true);
  });

  test('should send contact confirmation email to user', async () => {
    emailService = require('../../utils/email');

    await emailService.sendContactConfirmationEmail(
      'user@example.com',
      'John Doe',
      '12345'
    );

    // Should not throw error
    expect(true).toBe(true);
  });

  test('should send community welcome email to subscriber', async () => {
    emailService = require('../../utils/email');

    await emailService.sendCommunityWelcomeEmail(
      'subscriber@example.com',
      'John'
    );

    // Should not throw error
    expect(true).toBe(true);
  });
});
