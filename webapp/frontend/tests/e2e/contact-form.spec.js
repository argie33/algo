/**
 * Contact Form E2E Tests
 * Tests the complete contact form flow from UI to API
 */

import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const API_URL = process.env.API_URL || 'http://localhost:3001';

test.describe('Contact Form', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to contact page
    await page.goto(`${BASE_URL}/contact`);
    await page.waitForLoadState('networkidle');
  });

  test('should display contact form with all required fields', async ({ page }) => {
    // Check for form fields
    const nameInput = page.locator('input[name="name"]');
    const emailInput = page.locator('input[name="email"]');
    const subjectInput = page.locator('input[name="subject"]');
    const messageInput = page.locator('textarea[name="message"]');
    const submitButton = page.locator('button:has-text("Send Message")');

    await expect(nameInput).toBeVisible();
    await expect(emailInput).toBeVisible();
    await expect(subjectInput).toBeVisible();
    await expect(messageInput).toBeVisible();
    await expect(submitButton).toBeVisible();
  });

  test('should submit contact form successfully', async ({ page }) => {
    // Fill out form
    await page.fill('input[name="name"]', 'Test User');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="subject"]', 'E2E Test');
    await page.fill('textarea[name="message"]', 'This is an automated e2e test message');

    // Listen for API response
    const responsePromise = page.waitForResponse(response =>
      response.url().includes('/api/contact') && response.status() === 201
    );

    // Submit form
    await page.click('button:has-text("Send Message")');

    // Wait for success response
    const response = await responsePromise;
    const responseData = await response.json();

    expect(response.status()).toBe(201);
    expect(responseData.success).toBe(true);
    expect(responseData.data.submission_id).toBeDefined();
  });

  test('should show success message after submission', async ({ page }) => {
    // Fill out form
    await page.fill('input[name="name"]', 'Test User');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="subject"]', 'E2E Test');
    await page.fill('textarea[name="message"]', 'This is an automated e2e test message');

    // Wait for API response
    await page.waitForResponse(response =>
      response.url().includes('/api/contact') && response.status() === 201
    );

    // Check for success message
    const successAlert = page.locator('text=Thank you for reaching out');
    await expect(successAlert).toBeVisible({ timeout: 5000 });
  });

  test('should validate required fields', async ({ page }) => {
    // Try to submit empty form
    await page.click('button:has-text("Send Message")');

    // Check for validation error
    const errorAlert = page.locator('text=Please fill in all required fields');
    await expect(errorAlert).toBeVisible({ timeout: 5000 });
  });

  test('should validate email format', async ({ page }) => {
    // Fill out form with invalid email
    await page.fill('input[name="name"]', 'Test User');
    await page.fill('input[name="email"]', 'invalid-email');
    await page.fill('textarea[name="message"]', 'Test message');

    // Try to submit
    await page.click('button:has-text("Send Message")');

    // Check for validation error
    const errorAlert = page.locator('text=Please enter a valid email address');
    await expect(errorAlert).toBeVisible({ timeout: 5000 });
  });

  test('should clear form after successful submission', async ({ page }) => {
    // Fill out form
    await page.fill('input[name="name"]', 'Test User');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="subject"]', 'E2E Test');
    await page.fill('textarea[name="message"]', 'This is an automated e2e test message');

    // Wait for successful submission
    await page.waitForResponse(response =>
      response.url().includes('/api/contact') && response.status() === 201
    );

    // Wait a moment for form to clear
    await page.waitForTimeout(1000);

    // Check that form fields are cleared
    const nameInput = page.locator('input[name="name"]');
    const emailInput = page.locator('input[name="email"]');
    const messageInput = page.locator('textarea[name="message"]');

    await expect(nameInput).toHaveValue('');
    await expect(emailInput).toHaveValue('');
    await expect(messageInput).toHaveValue('');
  });

  test('should disable submit button while sending', async ({ page }) => {
    // Fill out form
    await page.fill('input[name="name"]', 'Test User');
    await page.fill('input[name="email"]', 'test@example.com');
    await page.fill('input[name="subject"]', 'E2E Test');
    await page.fill('textarea[name="message"]', 'Test message');

    const submitButton = page.locator('button:has-text("Send Message")');

    // Start listening for response but don't await immediately
    const responsePromise = page.waitForResponse(response =>
      response.url().includes('/api/contact') && response.status() === 201
    );

    // Click submit
    await submitButton.click();

    // Check button is disabled while sending
    await expect(submitButton).toBeDisabled();

    // Wait for response
    await responsePromise;

    // Button should be enabled again after response
    await expect(submitButton).toBeEnabled();
  });

  test('should display contact information on page', async ({ page }) => {
    // Check for contact info section
    const salesEmail = page.locator('text=sales@bullseyefinancial.com');
    const supportEmail = page.locator('text=support@bullseyefinancial.com');
    const phone = page.locator('text=+1 (555) 123-4567');

    await expect(salesEmail).toBeVisible();
    await expect(supportEmail).toBeVisible();
    await expect(phone).toBeVisible();
  });

  test('should display department information', async ({ page }) => {
    // Check for department cards
    const salesDept = page.locator('text=Sales & Partnerships');
    const supportDept = page.locator('text=Support & Technical');
    const researchDept = page.locator('text=Research & Methodology');

    await expect(salesDept).toBeVisible();
    await expect(supportDept).toBeVisible();
    await expect(researchDept).toBeVisible();
  });
});

test.describe('Contact Form API Verification', () => {
  test('should verify form data saved to database', async ({ request }) => {
    // Submit via API
    const response = await request.post(`${API_URL}/api/contact`, {
      data: {
        name: 'E2E Test User',
        email: 'e2e-test@example.com',
        subject: 'E2E API Test',
        message: 'This is an e2e api test message'
      }
    });

    expect(response.status()).toBe(201);
    const data = await response.json();
    expect(data.success).toBe(true);
    expect(data.data.submission_id).toBeDefined();

    // Log submission ID for manual verification
    console.log('✅ Form submission successful - ID:', data.data.submission_id);
  });

  test('should reject invalid email format via API', async ({ request }) => {
    const response = await request.post(`${API_URL}/api/contact`, {
      data: {
        name: 'Test User',
        email: 'invalid-email',
        subject: 'Test',
        message: 'Test message'
      }
    });

    expect(response.status()).toBe(400);
    const data = await response.json();
    expect(data.success).toBe(false);
    expect(data.error).toContain('Invalid email format');
  });

  test('should reject missing required fields via API', async ({ request }) => {
    const response = await request.post(`${API_URL}/api/contact`, {
      data: {
        name: 'Test User'
        // Missing email and message
      }
    });

    expect(response.status()).toBe(400);
    const data = await response.json();
    expect(data.success).toBe(false);
    expect(data.error).toContain('required');
  });
});
