# Contact Form Email Testing Guide

## Overview
The contact form now sends email notifications to `edgebrookecapital@gmail.com` when someone submits the form.

## How It Works

1. **Frontend**: User fills out contact form and submits
2. **Backend**: Form data is saved to `contact_submissions` database table
3. **Email**: Notification email is sent to configured recipient(s)
4. **User**: Receives confirmation that form was submitted

## Testing Locally

### Prerequisites
- Node.js running locally
- API server running (`npm start` in `/home/stocks/algo/webapp/lambda`)
- Database configured and running

### Test 1: Direct API Test (Curl)

```bash
curl -X POST http://localhost:3001/api/contact \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test User",
    "email": "test@example.com",
    "subject": "Testing Contact Form",
    "message": "This is a test message to verify email functionality."
  }'
```

**Expected Response:**
```json
{
  "success": true,
  "message": "Thank you for your message! We'll get back to you soon.",
  "data": {
    "submission_id": 3,
    "submitted_at": "2026-01-31T18:30:45.123Z"
  }
}
```

### Test 2: Via Web Form

1. Navigate to: `http://localhost:3000/contact` (or your frontend URL)
2. Fill out the form:
   - Name: "Test User"
   - Email: "test@example.com"
   - Subject: "Testing Contact Form"
   - Message: "This is a test message"
3. Click "Send Message"
4. You should see success confirmation
5. **Check email**: `edgebrookecapital@gmail.com` should receive notification

### Test 3: Check Console Output

When testing locally, if email service is not configured, you'll see:
```
📧 EMAIL (Console Mode): {
  to: 'edgebrookecapital@gmail.com',
  subject: 'New Contact Form Submission: Testing Contact Form',
  body: '...'
}
```

This means emails are being logged to console (development mode).

### Test 4: Check Database

```bash
# Verify form was saved
sqlite3 stocks.db "SELECT * FROM contact_submissions ORDER BY submitted_at DESC LIMIT 1;"
```

## Testing in AWS

### Prerequisites
- AWS Lambda function deployed
- AWS SES verified sender domain or email address
- IAM role has SES permissions

### Configuration

1. **Verify Sender Email in AWS SES:**
   ```
   AWS Console > SES > Email Addresses > Verify New Email Address
   - Verify: noreply@bullseyefinancial.com
   ```

2. **Set Environment Variables in Lambda:**
   ```
   CONTACT_NOTIFICATION_EMAIL=edgebrookecapital@gmail.com
   EMAIL_FROM=noreply@bullseyefinancial.com
   AWS_REGION=us-east-1
   ```

3. **Add SES Permissions to Lambda IAM Role:**
   ```json
   {
     "Effect": "Allow",
     "Action": [
       "ses:SendEmail",
       "ses:SendRawEmail"
     ],
     "Resource": "*"
   }
   ```

### Test AWS Deployment

1. Submit form through website (production URL)
2. Check CloudWatch Logs for Lambda function:
   ```
   ✅ Email sent via AWS SES - MessageId: xxxx
   ```
3. Verify email received at `edgebrookecapital@gmail.com`

## Troubleshooting

### Email Not Received

1. **Check Lambda Logs:**
   ```bash
   aws logs tail /aws/lambda/financial-dashboard-api --follow
   ```

2. **Verify SES Configuration:**
   - Is sender email verified in AWS SES?
   - Is recipient email in verified recipients list (if in sandbox)?
   - Check SES Send Quota and max send rate

3. **Check Database:**
   ```bash
   # Verify form was saved
   SELECT * FROM contact_submissions WHERE email = 'test@example.com';
   ```

4. **Gmail Spam Folder:**
   - Check spam/promotions folder
   - Add sender email to contacts to improve delivery

### Email Service Not Initialized

**Console Output:**
```
⚠️  No email service configured. Emails will be logged to console.
```

**Solution:**
1. For local testing: Set `AWS_REGION` or configure `SMTP_*` env vars
2. For AWS Lambda: Ensure IAM role has SES permissions

## Email Templates

### Admin Notification Email
Recipients: `CONTACT_NOTIFICATION_EMAIL`
Contains: User details, message content, submission ID

### User Confirmation Email
Recipients: User email (optional - not yet implemented)
Contains: Confirmation that message was received

## Configuration Options

### Environment Variables

```
# Required
CONTACT_NOTIFICATION_EMAIL=email@example.com

# Optional
EMAIL_FROM=noreply@bullseyefinancial.com         # Default: noreply@bullseyefinancial.com
AWS_REGION=us-east-1                              # For AWS SES
SMTP_HOST=smtp.example.com                        # For SMTP fallback
SMTP_PORT=587
SMTP_SECURE=false
SMTP_USER=username
SMTP_PASS=password
```

## Multiple Recipients

To send to multiple emails:
```bash
CONTACT_NOTIFICATION_EMAIL=email1@example.com,email2@example.com,email3@example.com
```

## API Response Codes

| Code | Meaning | Cause |
|------|---------|-------|
| 201 | Success | Form submitted and saved |
| 400 | Bad Request | Missing required fields or invalid email |
| 500 | Server Error | Database or email service error |

**Note:** Form is saved even if email fails to send. You can always check the database.

## Next Steps

1. ✅ Test locally with curl
2. ✅ Test locally with web form
3. ✅ Deploy to AWS Lambda
4. ✅ Test AWS deployment
5. ✅ Monitor incoming emails at edgebrookecapital@gmail.com
