/**
 * Email Service - Sends emails using AWS SES or local SMTP
 * Supports both AWS Lambda and local development environments
 */

const os = require('os');
const { SESClient, SendEmailCommand } = require('@aws-sdk/client-ses');

// Load environment variables from .env.local in development
if (process.env.NODE_ENV !== 'production' && !process.env.AWS_LAMBDA_FUNCTION_NAME) {
  try {
    require('dotenv').config({ path: '/home/stocks/algo/.env.local' });
  } catch (e) {
    // dotenv not available or .env.local not found - that's ok
  }
}

// Optional dependency - nodemailer for SMTP support
let nodemailer;
try {
  nodemailer = require('nodemailer');
} catch (error) {
  nodemailer = null;
}

let sesClient = null;
let smtpTransporter = null;
let emailService = 'none';

// Initialize email service
function initializeEmailService() {
  // Check if running in AWS Lambda or with AWS credentials
  if (process.env.AWS_REGION || process.env.AWS_ACCESS_KEY_ID) {
    try {
      sesClient = new SESClient({
        region: process.env.AWS_REGION || 'us-east-1'
      });
      emailService = 'aws-ses';
      console.log('✅ Email service initialized: AWS SES');
      return;
    } catch (error) {
      console.warn('⚠️  Failed to initialize AWS SES:', error.message);
    }
  }

  // Fall back to local SMTP (for development)
  if (process.env.SMTP_HOST && process.env.SMTP_PORT && nodemailer) {
    try {
      smtpTransporter = nodemailer.createTransport({
        host: process.env.SMTP_HOST,
        port: parseInt(process.env.SMTP_PORT),
        secure: process.env.SMTP_SECURE === 'true',
        auth: process.env.SMTP_USER && process.env.SMTP_PASS ? {
          user: process.env.SMTP_USER,
          pass: process.env.SMTP_PASS
        } : undefined
      });
      emailService = 'smtp';
      console.log(`✅ Email service initialized: SMTP (${process.env.SMTP_HOST})`);
      return;
    } catch (error) {
      console.warn('⚠️  Failed to initialize SMTP:', error.message);
    }
  }

  // Fallback: console logging for development
  emailService = 'console';
  console.log('⚠️  No email service configured. Emails will be logged to console.');
}

/**
 * Get email config from AWS Secrets Manager or environment
 */
async function getEmailConfig() {
  if (process.env.CONTACT_NOTIFICATION_EMAIL && process.env.EMAIL_FROM) {
    return {
      contactEmail: process.env.CONTACT_NOTIFICATION_EMAIL,
      emailFrom: process.env.EMAIL_FROM
    };
  }

  // Try to get from AWS Secrets Manager (Lambda/ECS)
  if (process.env.EMAIL_CONFIG_SECRET_NAME) {
    try {
      const SecretsManager = require('@aws-sdk/client-secrets-manager');
      const client = new SecretsManager.SecretsManagerClient({
        region: process.env.AWS_REGION || 'us-east-1'
      });

      const result = await client.send(new SecretsManager.GetSecretValueCommand({
        SecretId: process.env.EMAIL_CONFIG_SECRET_NAME
      }));

      const secret = JSON.parse(result.SecretString || '{}');
      return {
        contactEmail: secret.contact_notification_email || 'edgebrookecapital@gmail.com',
        emailFrom: secret.email_from || 'noreply@bullseyefinancial.com'
      };
    } catch (error) {
      console.warn('⚠️  Could not fetch email config from Secrets Manager:', error.message);
    }
  }

  // Default values
  return {
    contactEmail: 'edgebrookecapital@gmail.com',
    emailFrom: 'noreply@bullseyefinancial.com'
  };
}

/**
 * Send email using configured service
 * @param {Object} options - Email options
 * @param {Array|String} options.to - Recipient email(s)
 * @param {Array|String} options.cc - CC email(s) (optional)
 * @param {Array|String} options.bcc - BCC email(s) (optional)
 * @param {String} options.subject - Email subject
 * @param {String} options.text - Plain text body
 * @param {String} options.html - HTML body
 * @param {String} options.from - Sender email (optional, uses default)
 * @returns {Promise}
 */
async function sendEmail(options) {
  // Initialize service on first use
  if (emailService === 'none') {
    initializeEmailService();
  }

  if (emailService === 'console') {
    console.log('📧 EMAIL (Console Mode):', {
      to: Array.isArray(options.to) ? options.to.join(', ') : options.to,
      subject: options.subject,
      body: options.html || options.text
    });
    return { success: true, service: 'console' };
  }

  const emailConfig = await getEmailConfig();
  const from = options.from || emailConfig.emailFrom;

  try {
    if (emailService === 'aws-ses') {
      return await sendViaSES(from, options);
    } else if (emailService === 'smtp') {
      return await sendViaSMTP(from, options);
    }
  } catch (error) {
    console.error(`❌ Failed to send email via ${emailService}:`, error.message);
    throw error;
  }
}

/**
 * Send email via AWS SES
 */
async function sendViaSES(from, options) {
  const recipients = Array.isArray(options.to) ? options.to : [options.to];

  const command = new SendEmailCommand({
    Source: from,
    Destination: {
      ToAddresses: recipients,
      CcAddresses: options.cc ? (Array.isArray(options.cc) ? options.cc : [options.cc]) : [],
      BccAddresses: options.bcc ? (Array.isArray(options.bcc) ? options.bcc : [options.bcc]) : []
    },
    Message: {
      Subject: {
        Data: options.subject,
        Charset: 'UTF-8'
      },
      Body: {
        Html: {
          Data: options.html || options.text,
          Charset: 'UTF-8'
        },
        ...(options.text && {
          Text: {
            Data: options.text,
            Charset: 'UTF-8'
          }
        })
      }
    }
  });

  const response = await sesClient.send(command);
  console.log(`✅ Email sent via AWS SES - MessageId: ${response.MessageId}`);

  return {
    success: true,
    service: 'aws-ses',
    messageId: response.MessageId,
    recipients
  };
}

/**
 * Send email via SMTP
 */
async function sendViaSMTP(from, options) {
  const recipients = Array.isArray(options.to) ? options.to : [options.to];

  const result = await smtpTransporter.sendMail({
    from,
    to: recipients.join(', '),
    cc: options.cc ? (Array.isArray(options.cc) ? options.cc.join(', ') : options.cc) : undefined,
    bcc: options.bcc ? (Array.isArray(options.bcc) ? options.bcc.join(', ') : options.bcc) : undefined,
    subject: options.subject,
    html: options.html,
    text: options.text
  });

  console.log(`✅ Email sent via SMTP - MessageId: ${result.messageId}`);

  return {
    success: true,
    service: 'smtp',
    messageId: result.messageId,
    recipients
  };
}

/**
 * Send transactional email (form confirmation to user)
 */
async function sendConfirmationEmail(userEmail, userName, submissionId) {
  const subject = 'We received your message - Bullseye Financial';
  const html = `
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
      <h2 style="color: #1976d2;">Thank you for reaching out!</h2>
      <p>Hi ${userName},</p>
      <p>We've received your message and will review it shortly. Our team will get back to you within 24 business hours.</p>
      <p style="background: #f5f5f5; padding: 15px; border-radius: 5px;">
        <strong>Submission ID:</strong> #${submissionId}<br>
        <strong>Time:</strong> ${new Date().toLocaleString()}
      </p>
      <p>If you have any urgent matters, please contact us directly:</p>
      <ul>
        <li><strong>Phone:</strong> +1 (555) 123-4567</li>
        <li><strong>Email:</strong> support@bullseyefinancial.com</li>
      </ul>
      <p style="color: #666; font-size: 12px; margin-top: 30px; border-top: 1px solid #ddd; padding-top: 15px;">
        This is an automated message. Please do not reply to this email.
      </p>
    </div>
  `;

  try {
    await sendEmail({
      to: userEmail,
      subject,
      html
    });
    console.log(`✅ Confirmation email sent to ${userEmail}`);
  } catch (error) {
    console.error(`⚠️  Failed to send confirmation email to ${userEmail}:`, error.message);
    // Don't throw - this is optional
  }
}

// Initialize on module load
initializeEmailService();

module.exports = {
  sendEmail,
  sendConfirmationEmail,
  getEmailConfig,
  getEmailService: () => emailService
};
