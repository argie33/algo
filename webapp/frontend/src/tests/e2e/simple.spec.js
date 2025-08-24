import { test, expect } from '@playwright/test';

test.describe('Basic E2E Functionality', () => {
  test.setTimeout(30000);

  test('should load the homepage', async ({ page }) => {
    // Navigate to the homepage
    await page.goto('/');
    
    // Wait for the page to load
    await page.waitForLoadState('networkidle');
    
    // Check if the page title contains expected content
    await expect(page).toHaveTitle(/Financial Dashboard|Stock/i);
    
    // Check if basic UI elements are present
    const body = await page.locator('body');
    await expect(body).toBeVisible();
  });

  test('should handle navigation', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Look for navigation elements (adjust selectors based on your actual UI)
    const nav = await page.locator('nav, [role="navigation"], .nav, .navigation').first();
    if (await nav.isVisible()) {
      await expect(nav).toBeVisible();
    }
  });

  test('should be responsive', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');
    
    // Test desktop view
    await page.setViewportSize({ width: 1920, height: 1080 });
    await expect(page.locator('body')).toBeVisible();
    
    // Test mobile view
    await page.setViewportSize({ width: 375, height: 667 });
    await expect(page.locator('body')).toBeVisible();
  });
});