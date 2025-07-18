import { test, expect } from '@playwright/test';

test.describe('Authentication Flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('should display login form', async ({ page }) => {
    await page.click('text=Login');
    await expect(page.locator('form')).toBeVisible();
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('should login with valid credentials', async ({ page }) => {
    await page.click('text=Login');
    
    await page.fill('input[type="email"]', 'test@example.com');
    await page.fill('input[type="password"]', 'testpass123');
    await page.click('button[type="submit"]');
    
    // Wait for navigation after login
    await page.waitForURL('**/dashboard');
    
    // Check if dashboard is loaded
    await expect(page.locator('text=Dashboard')).toBeVisible();
    await expect(page.locator('text=Welcome')).toBeVisible();
  });

  test('should show error for invalid credentials', async ({ page }) => {
    await page.click('text=Login');
    
    await page.fill('input[type="email"]', 'invalid@example.com');
    await page.fill('input[type="password"]', 'wrongpass');
    await page.click('button[type="submit"]');
    
    // Check for error message
    await expect(page.locator('text=Invalid credentials')).toBeVisible();
  });

  test('should logout successfully', async ({ page }) => {
    // Login first
    await page.click('text=Login');
    await page.fill('input[type="email"]', 'test@example.com');
    await page.fill('input[type="password"]', 'testpass123');
    await page.click('button[type="submit"]');
    
    await page.waitForURL('**/dashboard');
    
    // Logout
    await page.click('text=Logout');
    
    // Check if redirected to login
    await expect(page.locator('text=Login')).toBeVisible();
  });

  test('should handle authentication errors gracefully', async ({ page }) => {
    // Mock network failure
    await page.route('**/api/auth/login', route => {
      route.fulfill({
        status: 500,
        body: JSON.stringify({ error: 'Internal Server Error' })
      });
    });

    await page.click('text=Login');
    await page.fill('input[type="email"]', 'test@example.com');
    await page.fill('input[type="password"]', 'testpass123');
    await page.click('button[type="submit"]');
    
    // Check for error handling
    await expect(page.locator('text=Login failed')).toBeVisible();
  });
});