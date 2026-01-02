/**
 * Email Service Utility
 * Supports SendGrid, Mailgun, or SES
 * Configure EMAIL_SERVICE_PROVIDER environment variable
 */

const sgMail = process.env.EMAIL_SERVICE_PROVIDER === 'sendgrid'
  ? require('@sendgrid/mail')
  : null;

let emailServiceProvider = process.env.EMAIL_SERVICE_PROVIDER || 'sendgrid';

// Initialize SendGrid if configured
if (emailServiceProvider === 'sendgrid' && sgMail) {
  sgMail.setApiKey(process.env.SENDGRID_API_KEY);
}

/**
 * Send confirmation email to new subscriber
 * @param {string} email - Recipient email address
 * @param {object} options - Configuration options
 * @returns {Promise<object>} - Response from email service
 */
async function sendConfirmationEmail(email, options = {}) {
  try {
    const {
      firstName = 'Investor',
      unsubscribeLink = `${process.env.WEBSITE_URL || 'https://bullseyefinancial.com'}/api/community/unsubscribe?email=${email}`,
      fromEmail = process.env.FROM_EMAIL || 'newsletter@bullseyefinancial.com',
      fromName = 'Bullseye Financial',
    } = options;

    const emailContent = generateWelcomeEmail(firstName, unsubscribeLink);

    if (emailServiceProvider === 'sendgrid') {
      return await sendWithSendGrid(email, fromEmail, fromName, emailContent);
    } else if (emailServiceProvider === 'mailgun') {
      return await sendWithMailgun(email, fromEmail, fromName, emailContent);
    } else {
      console.warn(`Email service provider '${emailServiceProvider}' not configured. Email would be sent to: ${email}`);
      return { success: true, provider: 'none', message: 'Email service not configured - no email sent' };
    }

  } catch (error) {
    console.error('Error sending confirmation email:', error);
    throw error;
  }
}

/**
 * Send weekly newsletter
 * @param {string[]} emails - Array of recipient emails
 * @param {object} newsletter - Newsletter content
 * @returns {Promise<object>} - Response from email service
 */
async function sendNewsletter(emails, newsletter) {
  try {
    const {
      subject = 'Weekly Market Insights from Bullseye Financial',
      htmlContent,
      textContent,
      fromEmail = process.env.FROM_EMAIL || 'newsletter@bullseyefinancial.com',
      fromName = 'Bullseye Financial',
    } = newsletter;

    if (emailServiceProvider === 'sendgrid') {
      return await sendWithSendGrid(emails, fromEmail, fromName, { html: htmlContent, text: textContent }, subject);
    } else if (emailServiceProvider === 'mailgun') {
      return await sendWithMailgun(emails, fromEmail, fromName, { html: htmlContent, text: textContent }, subject);
    } else {
      console.warn(`Email service provider '${emailServiceProvider}' not configured. Newsletter would be sent to ${emails.length} recipients`);
      return { success: true, provider: 'none', recipientCount: emails.length };
    }

  } catch (error) {
    console.error('Error sending newsletter:', error);
    throw error;
  }
}

/**
 * Send with SendGrid
 */
async function sendWithSendGrid(to, fromEmail, fromName, content, subject = 'Welcome to Bullseye Financial Community') {
  try {
    if (!process.env.SENDGRID_API_KEY) {
      throw new Error('SENDGRID_API_KEY is not configured');
    }

    const msg = {
      to: Array.isArray(to) ? to : [to],
      from: {
        email: fromEmail,
        name: fromName,
      },
      subject,
      html: content.html || content,
      text: content.text || '',
      trackingSettings: {
        clickTracking: { enable: true },
        openTracking: { enable: true },
      },
    };

    const response = await sgMail.send(msg);
    console.log(`✅ Email sent via SendGrid to ${Array.isArray(to) ? to.length : 1} recipient(s)`);
    return { success: true, provider: 'sendgrid', response };

  } catch (error) {
    console.error('SendGrid error:', error.message);
    throw error;
  }
}

/**
 * Send with Mailgun
 */
async function sendWithMailgun(to, fromEmail, fromName, content, subject = 'Welcome to Bullseye Financial Community') {
  try {
    if (!process.env.MAILGUN_API_KEY || !process.env.MAILGUN_DOMAIN) {
      throw new Error('MAILGUN_API_KEY or MAILGUN_DOMAIN is not configured');
    }

    const mailgun = require('mailgun.js');
    const client = new mailgun.default({ key: process.env.MAILGUN_API_KEY });
    const mg = client.messages;

    const messageData = {
      from: `${fromName} <${fromEmail}>`,
      to: Array.isArray(to) ? to.join(',') : to,
      subject,
      html: content.html || content,
      text: content.text || '',
      'o:tracking': true,
      'o:tracking-clicks': true,
      'o:tracking-opens': true,
    };

    const response = await mg.create(process.env.MAILGUN_DOMAIN, messageData);
    console.log(`✅ Email sent via Mailgun to ${Array.isArray(to) ? to.length : 1} recipient(s)`);
    return { success: true, provider: 'mailgun', response };

  } catch (error) {
    console.error('Mailgun error:', error.message);
    throw error;
  }
}

/**
 * Generate welcome email HTML
 */
function generateWelcomeEmail(firstName, unsubscribeLink) {
  return {
    html: `
      <!DOCTYPE html>
      <html>
      <head>
        <style>
          body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
          .container { max-width: 600px; margin: 0 auto; padding: 20px; }
          .header { background: linear-gradient(135deg, #1976d2 0%, #1565c0 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }
          .content { padding: 30px; border: 1px solid #e0e0e0; border-radius: 0 0 8px 8px; }
          .cta { display: inline-block; background: #1976d2; color: white; padding: 12px 30px; text-decoration: none; border-radius: 4px; margin: 20px 0; }
          .footer { font-size: 0.9rem; color: #999; margin-top: 20px; text-align: center; }
          .unsubscribe { font-size: 0.85rem; color: #999; }
        </style>
      </head>
      <body>
        <div class="container">
          <div class="header">
            <h1>Welcome to Bullseye Financial Community, ${firstName}!</h1>
          </div>

          <div class="content">
            <p>Thank you for joining our community of professional investors and traders.</p>

            <p>You'll now receive:</p>
            <ul>
              <li>📊 Weekly market insights and analysis</li>
              <li>🎯 AI-powered stock opportunities</li>
              <li>📅 Invitations to events and webinars</li>
              <li>🔍 Exclusive research updates</li>
            </ul>

            <p><a href="https://bullseyefinancial.com/app/market" class="cta">Explore the Platform</a></p>

            <p>Questions? Check out our <a href="https://bullseyefinancial.com/contact">contact page</a> or reply to this email.</p>

            <p>Best regards,<br/>The Bullseye Financial Team</p>
          </div>

          <div class="footer">
            <p class="unsubscribe">You're receiving this email because you subscribed to our community. <a href="${unsubscribeLink}">Unsubscribe</a></p>
          </div>
        </div>
      </body>
      </html>
    `,
    text: `Welcome to Bullseye Financial Community, ${firstName}!\n\nThank you for joining our community. You'll now receive weekly market insights, AI-powered opportunities, and exclusive updates.\n\nExplore the platform: https://bullseyefinancial.com/app/market\n\nUnsubscribe: ${unsubscribeLink}`
  };
}

module.exports = {
  sendConfirmationEmail,
  sendNewsletter,
};
