/**
 * Email Service Utility - AWS SES
 * Sends emails via AWS Simple Email Service
 */

const AWS = require('aws-sdk');

const ses = new AWS.SES({ region: process.env.AWS_REGION || 'us-east-1' });

/**
 * Send confirmation email to new subscriber
 * @param {string} email - Recipient email address
 * @param {object} options - Configuration options
 * @returns {Promise<object>} - Response from SES
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

    const params = {
      Source: `${fromName} <${fromEmail}>`,
      Destination: {
        ToAddresses: [email],
      },
      Message: {
        Subject: {
          Data: 'Welcome to Bullseye Financial Community',
        },
        Body: {
          Html: {
            Data: emailContent.html,
          },
          Text: {
            Data: emailContent.text,
          },
        },
      },
    };

    const result = await ses.sendEmail(params).promise();
    console.log(`✅ Email sent via AWS SES to ${email}`);
    return { success: true, provider: 'ses', messageId: result.MessageId };

  } catch (error) {
    console.error('SES error:', error.message);
    throw error;
  }
}

/**
 * Send weekly newsletter
 * @param {string[]} emails - Array of recipient emails
 * @param {object} newsletter - Newsletter content
 * @returns {Promise<object>} - Response from SES
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

    const params = {
      Source: `${fromName} <${fromEmail}>`,
      Destination: {
        ToAddresses: emails,
      },
      Message: {
        Subject: {
          Data: subject,
        },
        Body: {
          Html: {
            Data: htmlContent,
          },
          Text: {
            Data: textContent,
          },
        },
      },
    };

    const result = await ses.sendEmail(params).promise();
    console.log(`✅ Newsletter sent via AWS SES to ${emails.length} recipients`);
    return { success: true, provider: 'ses', messageId: result.MessageId };

  } catch (error) {
    console.error('SES error:', error.message);
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
