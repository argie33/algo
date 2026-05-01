const { SESClient, SendEmailCommand } = require('@aws-sdk/client-ses');

let sesClient = null;
let emailConfigured = false;

const initEmailService = () => {
  try {
    if (process.env.AWS_REGION) {
      sesClient = new SESClient({ region: process.env.AWS_REGION });
      emailConfigured = true;
      console.log('✅ AWS SES email service initialized (AWS SDK v3)');
    } else {
      console.log('⚠️  AWS_REGION not configured - email sending disabled');
    }
  } catch (error) {
    console.warn('⚠️  Failed to initialize email service:', error.message);
  }
};

const getEmailConfig = async () => {
  return {
    contactEmail: process.env.CONTACT_EMAIL || 'edgebrookecapital@gmail.com',
    isConfigured: emailConfigured
  };
};

const sendEmail = async ({ to, subject, html, text }) => {
  if (!emailConfigured || !sesClient) {
    console.log('📧 Email service not configured - skipping email send');
    return { success: true, skipped: true };
  }

  try {
    const toAddresses = Array.isArray(to) ? to : [to];

    const command = new SendEmailCommand({
      Source: process.env.EMAIL_FROM || 'noreply@edgebrooke.com',
      Destination: { ToAddresses: toAddresses },
      Message: {
        Subject: { Data: subject, Charset: 'UTF-8' },
        Body: html
          ? { Html: { Data: html, Charset: 'UTF-8' } }
          : { Text: { Data: text || subject, Charset: 'UTF-8' } }
      }
    });

    const result = await sesClient.send(command);
    console.log(`📧 Email sent successfully - MessageId: ${result.MessageId}`);
    return { success: true, messageId: result.MessageId };
  } catch (error) {
    console.error('❌ Failed to send email:', error.message);
    throw error;
  }
};

// Initialize on module load
initEmailService();

module.exports = {
  sendEmail,
  getEmailConfig,
  initEmailService
};
