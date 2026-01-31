# Running Contact Form E2E Tests with Playwright

## What These Tests Do

The Playwright e2e tests will:
1. ✅ Navigate to the contact form page
2. ✅ Fill out the form with test data
3. ✅ Submit the form
4. ✅ Verify the API response (201 status)
5. ✅ Check success message displays
6. ✅ Validate form validation (required fields, email format)
7. ✅ Verify form data is saved to database
8. ✅ Test API endpoints directly

**This tests the COMPLETE flow - frontend UI → API → Database**

---

## Prerequisites

1. **Start the backend API:**
   ```bash
   cd /home/stocks/algo/webapp/lambda
   npm start
   # Should be running on http://localhost:3001
   ```

2. **Start the frontend dev server:**
   ```bash
   cd /home/stocks/algo/webapp/frontend
   npm run dev
   # Should be running on http://localhost:3000 (or Vite default port)
   ```

3. **Ensure database is running:**
   - PostgreSQL should be accessible
   - `contact_submissions` table exists

---

## Run the E2E Tests

### Option 1: Run All Contact Form Tests

```bash
cd /home/stocks/algo/webapp/frontend

npx playwright test tests/e2e/contact-form.spec.js
```

### Option 2: Run Tests in UI Mode (Watch Mode)

```bash
npx playwright test tests/e2e/contact-form.spec.js --ui
```

This opens an interactive dashboard where you can:
- Watch tests run
- Inspect each step
- Replay failed tests
- View screenshots/videos

### Option 3: Run Specific Test

```bash
# Run only the submission test
npx playwright test tests/e2e/contact-form.spec.js -g "submit contact form successfully"

# Run only API tests
npx playwright test tests/e2e/contact-form.spec.js -g "API Verification"
```

### Option 4: Run with Debug Mode

```bash
# Opens Playwright Inspector
npx playwright test tests/e2e/contact-form.spec.js --debug
```

---

## Test Output Example

```
✓ Contact Form
  ✓ should display contact form with all required fields (1.2s)
  ✓ should submit contact form successfully (2.1s)
  ✓ should show success message after submission (2.3s)
  ✓ should validate required fields (1.5s)
  ✓ should validate email format (1.4s)
  ✓ should clear form after successful submission (1.8s)
  ✓ should disable submit button while sending (1.6s)
  ✓ should display contact information on page (1.1s)
  ✓ should display department information (1.0s)

✓ Contact Form API Verification
  ✓ should verify form data saved to database (0.9s)
  ✓ should reject invalid email format via API (0.8s)
  ✓ should reject missing required fields via API (0.7s)

12 passed (15s)
```

---

## What Gets Tested

### Frontend Tests (UI)
- ✅ Form fields are visible
- ✅ Form submission works
- ✅ Success message displays
- ✅ Form validation works
- ✅ Form clears after submission
- ✅ Submit button shows loading state
- ✅ Contact info displays

### API Tests
- ✅ Form data is saved to database
- ✅ Invalid emails are rejected
- ✅ Missing fields are rejected
- ✅ Response includes submission ID
- ✅ Success response returned (201)

---

## Verifying Email Was "Sent"

Since we're in development mode, emails go to console. To see if email was triggered:

1. **Check API Server Console:**
   ```
   ✅ Contact form received from test@example.com (Test User) - ID: 123
   📧 EMAIL (Console Mode): {
     to: 'edgebrookecapital@gmail.com',
     subject: 'New Contact Form Submission: E2E Test',
     ...
   }
   ```

2. **Check Database for Submission:**
   ```bash
   psql -U stocks -d stocks -c "SELECT * FROM contact_submissions ORDER BY submitted_at DESC LIMIT 1;"
   ```

3. **Expected Output:**
   ```
   id | name           | email                | subject    | message              | status | submitted_at
   ---+----------------+----------------------+------------+----------------------+--------+---
   3  | E2E Test User  | e2e-test@example.com | E2E API Test | This is an e2e api... | new    | 2026-01-31...
   ```

---

## Environment Variables

If you need custom URLs, set:

```bash
# For custom base URLs
export BASE_URL=http://localhost:3000
export API_URL=http://localhost:3001

# Then run tests
npx playwright test tests/e2e/contact-form.spec.js
```

---

## Troubleshooting

### Tests Fail with "Page Not Found"
- Check frontend is running: `http://localhost:3000/contact`
- Check API is running: `http://localhost:3001/api/contact`

### Tests Fail with "Database Error"
- Verify PostgreSQL is running
- Check `contact_submissions` table exists

### Tests Pass but Form Doesn't Look Right
- Check network tab in browser
- Verify API response status is 201
- Check console for errors

### API Tests Fail
- Verify API is accessible from command line:
  ```bash
  curl http://localhost:3001/api/contact -X POST \
    -H "Content-Type: application/json" \
    -d '{"name":"Test","email":"test@example.com","message":"test"}'
  ```

---

## Next Steps: Testing Real Email

Once you're ready to test actual email sending:

1. **Configure SMTP or AWS SES** in `.env.local`
2. **Run tests again** - emails will actually be sent
3. **Check your inbox** at `edgebrookecapital@gmail.com`

---

## CI/CD Integration

To add to your CI pipeline:

```bash
# Install dependencies
npm ci

# Run e2e tests
npx playwright test tests/e2e/contact-form.spec.js

# Generate report
npx playwright show-report
```

---

## Test Report

After running tests, view the HTML report:

```bash
npx playwright show-report
```

This opens a detailed report with:
- Test duration
- Screenshots of each step
- Videos of failures
- Trace files for debugging
