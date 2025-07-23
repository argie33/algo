/**
 * Real Email Service using AWS SES
 * Replaces fake email functionality with actual AWS SES integration
 */

import { getSupportEmail } from '../config/environment';

class EmailService {
  constructor() {
    this.apiUrl = null;
    this.sesRegion = 'us-east-1';
    this.initialized = false;
  }

  async initialize() {
    if (this.initialized) return;

    try {
      // Get API URL from configuration
      const { getApiUrl } = await import('../config/environment');
      this.apiUrl = getApiUrl();
      this.initialized = true;
    } catch (error) {
      console.error('Failed to initialize Email Service:', error);
      throw new Error('Email service initialization failed');
    }
  }

  /**
   * Send support email via AWS SES through API Gateway
   * @param {Object} emailData - Email data
   * @param {string} emailData.subject - Email subject
   * @param {string} emailData.message - Email message
   * @param {string} emailData.userEmail - User's email for reply-to
   * @param {string} emailData.priority - Priority level (low, normal, high, urgent)
   * @returns {Promise<Object>} Send result
   */
  async sendSupportEmail(emailData) {
    await this.initialize();

    const { subject, message, userEmail, priority = 'normal' } = emailData;

    if (!subject || !message || !userEmail) {
      throw new Error('Subject, message, and user email are required');
    }

    // Validate email format
    if (!this.isValidEmail(userEmail)) {
      throw new Error('Invalid email format');
    }

    try {
      const response = await fetch(`${this.apiUrl}/support/email`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          to: getSupportEmail(),
          replyTo: userEmail,
          subject: `[Support] ${subject}`,
          htmlBody: this.generateSupportEmailTemplate({
            subject,
            message,
            userEmail,
            priority,
            timestamp: new Date().toISOString()
          }),
          textBody: this.generatePlainTextEmail({
            subject,
            message,
            userEmail,
            priority,
            timestamp: new Date().toISOString()
          }),
          priority,
          tags: [
            { Name: 'Source', Value: 'WebApp' },
            { Name: 'Type', Value: 'Support' },
            { Name: 'Priority', Value: priority }
          ]
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || `Email send failed: ${response.status}`);
      }

      const result = await response.json();
      
      console.log('✅ Support email sent successfully', {
        messageId: result.messageId,
        to: getSupportEmail(),
        replyTo: userEmail
      });

      return {
        success: true,
        messageId: result.messageId,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('❌ Failed to send support email:', error);
      
      // Fallback: Store in local storage for manual processing
      this.storePendingEmail(emailData);
      
      throw new Error(`Failed to send support email: ${error.message}`);
    }
  }

  /**
   * Send notification email to user via AWS SES
   * @param {Object} emailData - Email data
   * @returns {Promise<Object>} Send result
   */
  async sendNotificationEmail(emailData) {
    await this.initialize();

    const { to, subject, message, type = 'notification' } = emailData;

    if (!to || !subject || !message) {
      throw new Error('To, subject, and message are required');
    }

    if (!this.isValidEmail(to)) {
      throw new Error('Invalid recipient email format');
    }

    try {
      const response = await fetch(`${this.apiUrl}/notifications/email`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          to,
          from: getSupportEmail(),
          subject,
          htmlBody: this.generateNotificationEmailTemplate({
            message,
            type,
            timestamp: new Date().toISOString()
          }),
          textBody: message,
          tags: [
            { Name: 'Source', Value: 'WebApp' },
            { Name: 'Type', Value: type }
          ]
        })
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || `Notification email send failed: ${response.status}`);
      }

      const result = await response.json();
      
      return {
        success: true,
        messageId: result.messageId,
        timestamp: new Date().toISOString()
      };

    } catch (error) {
      console.error('❌ Failed to send notification email:', error);
      throw new Error(`Failed to send notification email: ${error.message}`);
    }
  }

  /**
   * Generate HTML email template for support emails
   */
  generateSupportEmailTemplate(data) {
    const { subject, message, userEmail, priority, timestamp } = data;
    
    const priorityColor = {
      low: '#28a745',
      normal: '#007bff',
      high: '#fd7e14',
      urgent: '#dc3545'
    }[priority] || '#007bff';

    return `
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Support Request</title>
      </head>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="border: 1px solid #ddd; border-radius: 8px; padding: 30px; background-color: #f9f9f9;">
          <h2 style="color: #2c3e50; margin-bottom: 20px; border-bottom: 2px solid ${priorityColor}; padding-bottom: 10px;">
            📧 New Support Request
          </h2>
          
          <div style="background: white; padding: 20px; border-radius: 6px; margin-bottom: 20px;">
            <p><strong>Priority:</strong> <span style="color: ${priorityColor}; font-weight: bold; text-transform: uppercase;">${priority}</span></p>
            <p><strong>From:</strong> ${userEmail}</p>
            <p><strong>Subject:</strong> ${subject}</p>
            <p><strong>Timestamp:</strong> ${new Date(timestamp).toLocaleString()}</p>
          </div>
          
          <div style="background: white; padding: 20px; border-radius: 6px; border-left: 4px solid ${priorityColor};">
            <h3 style="margin-top: 0; color: #2c3e50;">Message:</h3>
            <div style="white-space: pre-wrap; background: #f8f9fa; padding: 15px; border-radius: 4px; border: 1px solid #e9ecef;">
              ${message.replace(/\n/g, '<br>')}
            </div>
          </div>
          
          <div style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666;">
            <p>This email was sent from the ProTrade Analytics web application.</p>
            <p>Reply directly to this email to respond to the user.</p>
          </div>
        </div>
      </body>
      </html>
    `;
  }

  /**
   * Generate plain text email for support
   */
  generatePlainTextEmail(data) {
    const { subject, message, userEmail, priority, timestamp } = data;
    
    return `
NEW SUPPORT REQUEST

Priority: ${priority.toUpperCase()}
From: ${userEmail}
Subject: ${subject}
Timestamp: ${new Date(timestamp).toLocaleString()}

Message:
${message}

---
This email was sent from the ProTrade Analytics web application.
Reply directly to this email to respond to the user.
    `.trim();
  }

  /**
   * Generate HTML template for notification emails
   */
  generateNotificationEmailTemplate(data) {
    const { message, type, timestamp } = data;
    
    return `
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>ProTrade Analytics Notification</title>
      </head>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="border: 1px solid #ddd; border-radius: 8px; padding: 30px; background-color: #f9f9f9;">
          <h2 style="color: #2c3e50; margin-bottom: 20px;">
            🔔 ProTrade Analytics Notification
          </h2>
          
          <div style="background: white; padding: 20px; border-radius: 6px; border-left: 4px solid #007bff;">
            ${message.replace(/\n/g, '<br>')}
          </div>
          
          <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #666;">
            <p>Sent: ${new Date(timestamp).toLocaleString()}</p>
            <p>Type: ${type}</p>
            <p>From: ProTrade Analytics Platform</p>
          </div>
        </div>
      </body>
      </html>
    `;
  }

  /**
   * Store pending email for manual processing if send fails
   */
  storePendingEmail(emailData) {
    try {
      const pendingEmails = JSON.parse(localStorage.getItem('pendingEmails') || '[]');
      pendingEmails.push({
        ...emailData,
        timestamp: new Date().toISOString(),
        status: 'pending'
      });
      localStorage.setItem('pendingEmails', JSON.stringify(pendingEmails));
      
      console.warn('📮 Email stored locally for manual processing');
    } catch (error) {
      console.error('Failed to store pending email:', error);
    }
  }

  /**
   * Get pending emails that failed to send
   */
  getPendingEmails() {
    try {
      return JSON.parse(localStorage.getItem('pendingEmails') || '[]');
    } catch (error) {
      console.error('Failed to get pending emails:', error);
      return [];
    }
  }

  /**
   * Clear pending emails
   */
  clearPendingEmails() {
    try {
      localStorage.removeItem('pendingEmails');
    } catch (error) {
      console.error('Failed to clear pending emails:', error);
    }
  }

  /**
   * Validate email format
   */
  isValidEmail(email) {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  }

  /**
   * Test email service connectivity
   */
  async testConnection() {
    await this.initialize();
    
    try {
      const response = await fetch(`${this.apiUrl}/support/health`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        }
      });

      return {
        success: response.ok,
        status: response.status,
        message: response.ok ? 'Email service is healthy' : 'Email service is not responding'
      };
    } catch (error) {
      return {
        success: false,
        message: `Email service connection failed: ${error.message}`
      };
    }
  }
}

// Export singleton instance
const emailService = new EmailService();
export default emailService;

// Named exports for convenience
export const sendSupportEmail = (emailData) => emailService.sendSupportEmail(emailData);
export const sendNotificationEmail = (emailData) => emailService.sendNotificationEmail(emailData);
export const testEmailConnection = () => emailService.testConnection();