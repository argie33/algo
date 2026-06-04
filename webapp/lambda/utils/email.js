const { SESClient, SendEmailCommand } = require('@aws-sdk/client-ses');

let sesClient = null;
let emailConfigured = false;

const initEmailService = () => {
  try {
    if (process.env.AWS_REGION) {
      sesClient = new SESClient({ region: process.env.AWS_REGION });
      emailConfigured = true;
    } else {
    }
  } catch (error) {
    console.warn('⚠️  Failed to initialize email service:', error.message);
  }
};

const getEmailConfig = async () => {
  return {
    contactEmail: process.env.CONTACT_EMAIL,
    isConfigured: emailConfigured
  };
};

const sendEmail = async ({ to, subject, html, text }) => {
  if (!emailConfigured || !sesClient) {
    return { success: true, skipped: true };
  }

  const emailFrom = process.env.EMAIL_FROM;
  if (!emailFrom) {
    console.warn('⚠️  EMAIL_FROM not configured, email sending will fail');
    return { success: false, error: 'EMAIL_FROM not configured' };
  }

  try {
    const toAddresses = Array.isArray(to) ? to : [to];

    const command = new SendEmailCommand({
      Source: emailFrom,
      Destination: { ToAddresses: toAddresses },
      Message: {
        Subject: { Data: subject, Charset: 'UTF-8' },
        Body: html
          ? { Html: { Data: html, Charset: 'UTF-8' } }
          : { Text: { Data: text || subject, Charset: 'UTF-8' } }
      }
    });

    const result = await sesClient.send(command);
    return { success: true, messageId: result.MessageId };
  } catch (error) {
    console.error(' Failed to send email:', error.message);
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
