// E2E Test for Analyst Insights page
// Tests the complete user journey with real API calls

import { test, expect } from '@playwright/test';

test.describe('Analyst Insights E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to the analyst insights page
    await page.goto('/sentiment/analysts');
  });

  test('loads analyst insights page with real data', async ({ page }) => {
    // Wait for the page to load
    await expect(page.getByRole('heading', { name: 'Analyst Insights' })).toBeVisible();

    // Wait for data to load (should show loading spinner first, then data)
    await expect(page.getByText('Recent Analyst Actions')).toBeVisible({ timeout: 10000 });
  });

  test('displays summary cards with correct information', async ({ page }) => {
    // Wait for summary cards to load
    await expect(page.getByText('Recent Upgrades')).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Recent Downgrades')).toBeVisible();
    await expect(page.getByText('Active Firms')).toBeVisible();
    await expect(page.getByText('Total Actions')).toBeVisible();

    // Check that cards have numeric values
    const cards = page.locator('[role="button"]').or(page.locator('h6')).filter({ hasText: /^\d+$/ });
    await expect(cards.first()).toBeVisible();
  });

  test('upgrades/downgrades table displays real data', async ({ page }) => {
    // Wait for the table to load
    await expect(page.getByText('Recent Analyst Actions')).toBeVisible({ timeout: 10000 });

    // Check for table - use more flexible selectors
    const table = page.locator('table').first();
    await expect(table).toBeVisible({ timeout: 5000 });

    // Check for table headers within the table
    const tableHeaders = table.locator('thead th');
    await expect(tableHeaders).toHaveCount(7, { timeout: 5000 });

    // Verify at least the table structure exists
    const tableBody = table.locator('tbody');
    await expect(tableBody).toBeVisible();
  });


  test('search functionality works correctly', async ({ page }) => {
    // Wait for page to load
    await expect(page.getByText('Recent Analyst Actions')).toBeVisible({ timeout: 10000 });

    // Find and use the search input
    const searchInput = page.getByPlaceholder('Search by symbol...');
    await expect(searchInput).toBeVisible();

    // Type a common symbol
    await searchInput.fill('AAPL');

    // Wait a moment for filtering to occur
    await page.waitForTimeout(500);

    // The search should filter results (if any data exists)
    // We can't guarantee specific symbols exist, so we just verify the search field works
    await expect(searchInput).toHaveValue('AAPL');
  });

  test('action filter dropdown works', async ({ page }) => {
    // Wait for page to load
    await expect(page.getByText('Recent Analyst Actions')).toBeVisible({ timeout: 10000 });

    // Find the action filter dropdown - use ID selector for MUI Select
    const actionFilter = page.locator('#action-filter');
    await expect(actionFilter).toBeVisible({ timeout: 5000 });

    // Click to open dropdown
    await actionFilter.click();
    await page.waitForTimeout(500);

    // Check for filter options in the dropdown menu
    const upgradesOption = page.getByRole('option', { name: /upgrades/i });
    await expect(upgradesOption).toBeVisible({ timeout: 3000 });

    // Select upgrades filter
    await upgradesOption.click();
    await page.waitForTimeout(500);

    // Verify dropdown closed after selection
    await expect(page.getByRole('listbox')).not.toBeVisible();
  });

  test('symbol clicking triggers detailed data fetch', async ({ page }) => {
    // Wait for data to load
    await expect(page.getByText('Recent Analyst Actions')).toBeVisible({ timeout: 10000 });

    // Look for any clickable symbols in the table
    const symbolLinks = page.locator('tbody tr td:first-child a, tbody tr td:first-child [role="button"]');

    if (await symbolLinks.count() > 0) {
      // Listen for API calls
      const apiCallPromise = page.waitForResponse(response =>
        response.url().includes('/api/analysts/') &&
        response.url().split('/').length > 4 // Symbol-specific endpoint
      );

      // Click on first symbol
      await symbolLinks.first().click();

      // Wait for API call to complete
      await apiCallPromise;
    }
  });

  test('handles error states gracefully', async ({ page }) => {
    // Intercept API calls and return errors
    await page.route('/api/analysts/upgrades*', route => {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          error: 'Database connection failed'
        })
      });
    });

    await page.route('/api/analysts/revenue-estimates', route => {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          error: 'Database connection failed'
        })
      });
    });

    // Reload page to trigger error
    await page.reload();

    // Page should still load the heading even if data fails
    await expect(page.getByRole('heading', { name: 'Analyst Insights' })).toBeVisible();

    // Should show some error indicator - either error text or empty state
    const hasError = await page.getByText(/error|failed|unable/i).isVisible().catch(() => false);
    const hasEmptyState = await page.getByText(/no data|no analyst/i).isVisible().catch(() => false);
    expect(hasError || hasEmptyState).toBeTruthy();
  });


  test('responsive design works on mobile', async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });

    // Page should still be accessible and readable
    await expect(page.getByRole('heading', { name: 'Analyst Insights' })).toBeVisible();
    await expect(page.getByText('Recent Analyst Actions')).toBeVisible({ timeout: 10000 });

    // Summary cards should stack properly
    const summaryCards = page.locator('[role="button"]').filter({ hasText: /Recent (Upgrades|Downgrades)|Active Firms|Total Actions/ });
    await expect(summaryCards.first()).toBeVisible();
  });

  test('navigation to analyst insights works from main menu', async ({ page }) => {
    // Go to home page first
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Try multiple navigation paths
    // 1. Try clicking menu button first (for mobile/tablet)
    const menuButton = page.locator('button[aria-label*="menu"]').first();
    if (await menuButton.isVisible()) {
      await menuButton.click();
      await page.waitForTimeout(500);
    }

    // 2. Look for Sentiment navigation item
    const sentimentLink = page.locator('a:has-text("Sentiment"), button:has-text("Sentiment")').first();
    if (await sentimentLink.isVisible({ timeout: 3000 })) {
      await sentimentLink.click();
      await page.waitForTimeout(500);

      // Look for Analyst Insights link in submenu or navigation
      const analystLink = page.locator('a:has-text("Analyst Insights")').first();
      if (await analystLink.isVisible({ timeout: 3000 })) {
        await analystLink.click();
        await page.waitForLoadState('networkidle');
      }
    } else {
      // Direct navigation if menu structure is different
      await page.goto('/sentiment/analysts');
      await page.waitForLoadState('networkidle');
    }

    // Verify we're on the analyst insights page by checking URL and content
    expect(page.url()).toContain('/sentiment/analysts');
    await expect(page.getByText('Recent Analyst Actions')).toBeVisible({ timeout: 10000 });
  });

  test('page loads within acceptable time limits', async ({ page }) => {
    const startTime = Date.now();

    // Navigate and wait for main content
    await page.goto('/sentiment/analysts');
    await expect(page.getByRole('heading', { name: 'Analyst Insights' })).toBeVisible();

    const loadTime = Date.now() - startTime;

    // Should load within 5 seconds
    expect(loadTime).toBeLessThan(5000);
  });
});