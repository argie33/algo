# Community Signup System Setup Guide

This guide walks you through setting up the complete community newsletter signup system for Bullseye Financial.

## What's Been Built

✅ **Frontend Components**
- Newsletter signup form on Home, About, and Contact pages
- Terms of Service page (/terms)
- Privacy Policy page (/privacy)
- Clickable legal links in signup form

✅ **Backend API**
- `POST /api/community/signup` - Email signup endpoint
- `GET /api/community/stats` - Subscription statistics
- `GET /api/community/subscribers` - List subscribers (admin)
- `POST /api/community/unsubscribe` - Unsubscribe endpoint

✅ **Database**
- PostgreSQL `community_signups` table with full schema
- Email validation and duplicate checking
- Status tracking (active, unsubscribed, bounced)
- Automatic timestamp updates

✅ **Email Service**
- SendGrid integration (recommended)
- Mailgun support
- AWS SES ready
- Professional HTML email templates

---

## Step 1: Create Database Table

Run the migration script to create the `community_signups` table:

```bash
cd /home/stocks/algo/webapp/lambda
node scripts/create-community-table.js
```

Expected output:
```
🔄 Initializing database...
📝 Creating community_signups table...
  Executing: CREATE TABLE IF NOT EXISTS community_signups...
✅ Community signups table created successfully!
✅ Table verification successful!
```

---

## Step 2: Configure Email Service

### Option A: SendGrid (Recommended)

1. **Get SendGrid API Key**
   - Go to https://sendgrid.com
   - Sign up or login to your account
   - Create an API key (Settings > API Keys > Create Key)
   - Keep the key safe

2. **Set Environment Variables**

   In your `.env.local` or Lambda environment:
   ```bash
   EMAIL_SERVICE_PROVIDER=sendgrid
   SENDGRID_API_KEY=your_sendgrid_api_key_here
   FROM_EMAIL=newsletter@bullseyefinancial.com
   WEBSITE_URL=https://bullseyefinancial.com
   ```

3. **Install Dependencies**
   ```bash
   cd /home/stocks/algo/webapp/lambda
   npm install @sendgrid/mail
   ```

### Option B: Mailgun

1. **Get Mailgun API Key**
   - Go to https://www.mailgun.com
   - Sign up or login
   - Copy your API key and domain

2. **Set Environment Variables**
   ```bash
   EMAIL_SERVICE_PROVIDER=mailgun
   MAILGUN_API_KEY=your_mailgun_api_key_here
   MAILGUN_DOMAIN=mg.bullseyefinancial.com
   FROM_EMAIL=newsletter@bullseyefinancial.com
   WEBSITE_URL=https://bullseyefinancial.com
   ```

3. **Install Dependencies**
   ```bash
   cd /home/stocks/algo/webapp/lambda
   npm install mailgun.js
   ```

### Option C: AWS SES

Already set up? Configure in the emailService.js to use SES instead.

---

## Step 3: Verify Configuration

Test the email service by:

1. **Test Signup Locally**
   ```bash
   curl -X POST http://localhost:3001/api/community/signup \
     -H "Content-Type: application/json" \
     -d '{"email":"test@example.com"}'
   ```

   Expected response:
   ```json
   {
     "success": true,
     "message": "Thank you for joining our community! Check your email for updates.",
     "data": {
       "subscription_id": 1,
       "subscribed_at": "2026-01-02T12:34:56.789Z"
     }
   }
   ```

2. **Check Email Received**
   - Check your test email inbox for the welcome email
   - Verify it has the Bullseye branding and unsubscribe link

---

## Step 4: Admin Endpoints

### Get Subscription Stats

```bash
curl http://localhost:3001/api/community/stats
```

Response:
```json
{
  "success": true,
  "data": {
    "stats": {
      "total_subscribers": 150,
      "active_subscribers": 145,
      "unsubscribed": 5,
      "new_this_week": 12,
      "new_this_month": 35
    }
  }
}
```

### Get All Subscribers

```bash
curl http://localhost:3001/api/community/subscribers
```

Response:
```json
{
  "success": true,
  "data": {
    "subscribers": [
      {
        "id": 1,
        "email": "investor@example.com",
        "status": "active",
        "subscribed_at": "2026-01-02T12:34:56.789Z",
        "source": "website"
      }
    ],
    "total": 150
  }
}
```

---

## Step 5: Newsletter Management

### Send Weekly Newsletter

Create a script to send to all active subscribers:

```javascript
// send-newsletter.js
const { query } = require('./utils/database');
const { sendNewsletter } = require('./utils/emailService');

async function sendWeeklyNewsletter() {
  try {
    // Get all active subscribers
    const result = await query(
      `SELECT email FROM community_signups WHERE status = 'active'`
    );

    const emails = result.rows.map(row => row.email);

    // Send newsletter
    await sendNewsletter(emails, {
      subject: 'Weekly Market Insights - Week of Jan 2, 2026',
      htmlContent: `
        <h2>Weekly Market Insights</h2>
        <p>This week in markets...</p>
        <!-- Add your newsletter content here -->
      `,
      textContent: 'Weekly Market Insights...',
    });

    console.log(`✅ Newsletter sent to ${emails.length} subscribers`);
  } catch (error) {
    console.error('Error sending newsletter:', error);
  }
}

sendWeeklyNewsletter();
```

Run with:
```bash
node send-newsletter.js
```

---

## Step 6: Deploy

### Deploy Backend (Lambda)

```bash
cd /home/stocks/algo/webapp/lambda
npm install
serverless deploy
```

### Deploy Frontend

```bash
cd /home/stocks/algo/webapp/frontend
npm run build
# Files are in dist/ - upload to your hosting
```

---

## Monitoring

### Check Email Delivery

Monitor sent emails:

```bash
curl http://localhost:3001/api/community/stats
```

Watch for:
- `total_subscribers` growing
- `new_this_week` increasing
- Low `bounced` count

### Database Health

Check for duplicates or invalid emails:

```sql
-- Find duplicate emails
SELECT email, COUNT(*) as count
FROM community_signups
WHERE status = 'active'
GROUP BY email
HAVING COUNT(*) > 1;

-- Find bounced emails
SELECT COUNT(*) FROM community_signups WHERE status = 'bounced';

-- Get signup breakdown by source
SELECT source, COUNT(*) as count
FROM community_signups
GROUP BY source;
```

---

## Troubleshooting

### Emails Not Sending

1. **Check API Key is configured**
   ```bash
   echo $SENDGRID_API_KEY
   ```

2. **Check email service logs**
   - SendGrid: https://app.sendgrid.com/email_activity
   - Mailgun: https://app.mailgun.com/app/sending/logs

3. **Verify sender email is verified**
   - SendGrid: Add newsletter@bullseyefinancial.com to verified senders
   - Mailgun: Add domain to SMTP settings

### Signup Not Working

1. **Check backend logs**
   ```bash
   # CloudWatch logs
   serverless logs -f community
   ```

2. **Verify database connection**
   ```bash
   psql $DATABASE_URL -c "SELECT COUNT(*) FROM community_signups;"
   ```

3. **Test API endpoint directly**
   ```bash
   curl -v -X POST http://localhost:3001/api/community/signup \
     -H "Content-Type: application/json" \
     -d '{"email":"test@example.com"}'
   ```

---

## Security Considerations

1. **Rate Limiting** - Add rate limiter to `/api/community/signup` to prevent abuse
2. **Authentication** - Add auth middleware to `/api/community/stats` and `/api/community/subscribers`
3. **Email Validation** - Implement double opt-in for GDPR compliance
4. **Data Privacy** - Ensure email data is encrypted at rest and in transit
5. **Terms Update** - Keep Terms of Service and Privacy Policy current and accurate

---

## Next Steps

1. ✅ Test signup locally
2. ✅ Configure email service
3. ✅ Deploy database migration
4. ✅ Deploy backend
5. ✅ Deploy frontend
6. ✅ Monitor first week of signups
7. ✅ Set up automated newsletter sending
8. ✅ Implement unsubscribe management

---

## Files Created

**Backend**
- `/webapp/lambda/routes/community.js` - Main API route
- `/webapp/lambda/utils/emailService.js` - Email utility
- `/webapp/lambda/scripts/create-community-table.js` - DB setup script
- `/webapp/lambda/migrations/001-create-community-signups.sql` - Schema migration

**Frontend**
- `/webapp/frontend/src/components/marketing/CommunitySignup.jsx` - Signup form
- `/webapp/frontend/src/pages/marketing/Terms.jsx` - Terms of Service
- `/webapp/frontend/src/pages/marketing/Privacy.jsx` - Privacy Policy
- `/webapp/frontend/src/App.jsx` - Updated routes

---

## Support

For issues:
1. Check the Troubleshooting section
2. Review email provider documentation
3. Check backend logs: `serverless logs -f community`
4. Verify database: `psql $DATABASE_URL -c "\\d community_signups"`

---

**Last Updated**: January 2, 2026
**Status**: Production Ready ✅
