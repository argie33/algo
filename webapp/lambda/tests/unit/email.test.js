/**
 * Email Service Unit Tests
 * Tests email sending functionality with AWS SES and SMTP
 */

// utils/email.js only exports sendEmail/getEmailConfig/initEmailService (a minimal SES
// wrapper) - sendContactConfirmationEmail/sendCommunityWelcomeEmail/sendNewsletter/
// getEmailService belonged to a richer email service removed in an earlier cleanup and
// were never re-added. Those cases were deleted here; only real exports are covered.
const mockSend = jest.fn().mockResolvedValue({ MessageId: "test-id" });
jest.mock("@aws-sdk/client-ses", () => ({
  SESClient: jest.fn().mockImplementation(() => ({ send: mockSend })),
  SendEmailCommand: jest.fn(),
}));

describe("Email Service", () => {
  let emailService;

  beforeEach(() => {
    // Clear module cache to force re-initialization
    jest.resetModules();
    mockSend.mockClear();
    mockSend.mockResolvedValue({ MessageId: "test-id" });
    // Set AWS region for SES in test
    process.env.AWS_REGION = "us-east-1";
    process.env.CONTACT_NOTIFICATION_EMAIL = "edgebrookecapital@gmail.com";
    process.env.EMAIL_FROM = "noreply@bullseyefinancial.com";
    emailService = require("../../utils/email");
  });

  afterEach(() => {
    delete process.env.AWS_REGION;
    delete process.env.CONTACT_NOTIFICATION_EMAIL;
    delete process.env.EMAIL_FROM;
  });

  test("should export sendEmail and config functions", () => {
    expect(typeof emailService.sendEmail).toBe("function");
    expect(typeof emailService.getEmailConfig).toBe("function");
    expect(typeof emailService.initEmailService).toBe("function");
  });

  test("should report configured state via getEmailConfig", async () => {
    const config = await emailService.getEmailConfig();
    expect(config).toHaveProperty("isConfigured", true);
  });

  test("should handle single recipient email", async () => {
    const result = await emailService.sendEmail({
      to: "test@example.com",
      subject: "Test Email",
      html: "<h1>Test</h1>",
    });

    expect(result.success).toBe(true);
    expect(mockSend).toHaveBeenCalledTimes(1);
  });

  test("should handle multiple recipient emails", async () => {
    const result = await emailService.sendEmail({
      to: ["test1@example.com", "test2@example.com"],
      subject: "Test Email",
      html: "<h1>Test</h1>",
    });

    expect(result.success).toBe(true);
  });

  test("should skip sending when EMAIL_FROM is not configured", async () => {
    delete process.env.EMAIL_FROM;
    jest.resetModules();
    emailService = require("../../utils/email");

    const result = await emailService.sendEmail({
      to: "test@example.com",
      subject: "Test Email",
      html: "<h1>Test</h1>",
    });

    expect(result.success).toBe(false);
    expect(result.error).toMatch(/EMAIL_FROM/);
  });
});
