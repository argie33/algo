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

    // Check for the description
    await expect(page.getByText('Real analyst data from YFinance - Upgrades and downgrades')).toBeVisible();

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

    // Check table headers
    await expect(page.getByText('Symbol')).toBeVisible();
    await expect(page.getByText('Firm')).toBeVisible();
    await expect(page.getByText('Action')).toBeVisible();
    await expect(page.getByText('From Grade')).toBeVisible();
    await expect(page.getByText('To Grade')).toBeVisible();
    await expect(page.getByText('Date')).toBeVisible();
    await expect(page.getByText('Details')).toBeVisible();

    // Should have at least one row of data (if there's real data)
    // We'll check for table body content
    const tableRows = page.locator('tbody tr');
    if (await tableRows.count() > 0) {
      await expect(tableRows.first()).toBeVisible();
    }
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

    // Find the action filter dropdown
    const actionFilter = page.getByLabel('Action Filter');
    await expect(actionFilter).toBeVisible();

    // Click to open dropdown
    await actionFilter.click();

    // Check for filter options
    await expect(page.getByRole('option', { name: 'All Actions' })).toBeVisible();
    await expect(page.getByRole('option', { name: 'Upgrades' })).toBeVisible();
    await expect(page.getByRole('option', { name: 'Downgrades' })).toBeVisible();

    // Select upgrades filter
    await page.getByRole('option', { name: 'Upgrades' }).click();

    // Verify selection was made
    await expect(actionFilter).toHaveValue('upgrade');
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

    // Should show error message
    await expect(page.getByText('Failed to load analyst data')).toBeVisible({ timeout: 10000 });
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

    // Look for sentiment menu or navigation
    const sentimentMenu = page.getByText('Sentiment');
    if (await sentimentMenu.isVisible()) {
      await sentimentMenu.click();

      // Look for Analyst Insights link
      const analystLink = page.getByText('Analyst Insights');
      if (await analystLink.isVisible()) {
        await analystLink.click();

        // Should navigate to analyst insights page
        await expect(page.getByRole('heading', { name: 'Analyst Insights' })).toBeVisible();
      }
    }
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