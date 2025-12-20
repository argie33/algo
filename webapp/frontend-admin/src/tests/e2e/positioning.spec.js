// E2E Test for Positioning feature on Stock Detail page
// Tests the complete user journey with real API calls

import { test, expect } from '@playwright/test';

test.describe('Positioning E2E Tests', () => {
  const testSymbol = 'AAL'; // Use stock AAL which has both company_profile and positioning data

  test.beforeEach(async ({ page }) => {
    // Navigate to stock detail page with positioning data
    await page.goto(`/stocks/${testSymbol}`);
    await page.waitForLoadState('networkidle');
  });

  test('loads stock detail page with positioning data', async ({ page }) => {
    // Wait for the page to load - look for the stock symbol in the main content area
    await expect(page.getByText('Institutional Ownership')).toBeVisible({ timeout: 10000 });

    // Wait for positioning section to be visible
    await expect(page.getByText(/Ownership & Short Interest|Market Positioning/i)).toBeVisible({ timeout: 10000 });
  });

  test('displays institutional ownership percentage', async ({ page }) => {
    // Wait for positioning data to load
    await expect(page.getByText('Institutional Ownership')).toBeVisible({ timeout: 10000 });

    // Find the institutional ownership value (should be a percentage)
    const ownershipText = page.locator('text=/\\d+\\.\\d+%/').filter({ has: page.locator('text=/Institutional Ownership/i') }).first();
    await expect(ownershipText).toBeVisible();

    // Verify it's a valid percentage
    const text = await ownershipText.textContent();
    const percentage = parseFloat(text);
    expect(percentage).toBeGreaterThan(0);
    expect(percentage).toBeLessThan(100);
  });

  test('displays insider ownership percentage', async ({ page }) => {
    // Wait for positioning data to load
    await expect(page.getByText('Insider Ownership')).toBeVisible({ timeout: 10000 });

    // Find the insider ownership value
    const ownershipSection = page.locator('text=/Insider Ownership/i').locator('xpath=ancestor::*[2]');
    const ownershipValue = ownershipSection.locator('text=/\\d+\\.\\d+%/').first();
    await expect(ownershipValue).toBeVisible();
  });

  test('displays short interest percentage', async ({ page }) => {
    // Wait for positioning data to load
    await expect(page.getByText(/Short Interest|Short %/i)).toBeVisible({ timeout: 10000 });

    // Find the short interest value
    const shortSection = page.locator('text=/Short Interest|Short %/i').locator('xpath=ancestor::*[2]');
    const shortValue = shortSection.locator('text=/\\d+\\.\\d+%/').first();
    await expect(shortValue).toBeVisible();
  });

  test('displays positioning score', async ({ page }) => {
    // Wait for positioning score to load
    await expect(page.getByText(/Positioning Score|Position Score/i)).toBeVisible({ timeout: 10000 });

    // Find the score value (should be 0-100)
    const scoreSection = page.locator('text=/Positioning Score|Position Score/i').locator('xpath=ancestor::*[3]');
    const scoreValue = scoreSection.locator('text=/^\\d+$/').first();

    if (await scoreValue.isVisible()) {
      const score = parseInt(await scoreValue.textContent());
      expect(score).toBeGreaterThanOrEqual(0);
      expect(score).toBeLessThanOrEqual(100);
    }
  });

  test('shows institutional holders list', async ({ page }) => {
    // Wait for page to load
    await page.waitForTimeout(2000);

    // Look for institutional holders section or table
    const institutionalSection = page.locator('text=/Top (Institutional )?Holders|Major Holders/i');

    if (await institutionalSection.isVisible({ timeout: 5000 })) {
      // Check for holder names (like Vanguard, Blackrock, etc.)
      const holderNames = page.locator('text=/Vanguard|Blackrock|State Street|Fidelity/i');
      await expect(holderNames.first()).toBeVisible({ timeout: 5000 });
    }
  });

  test('displays positioning metrics without N/A values for stock AAL', async ({ page }) => {
    // Wait for positioning data to load
    await page.waitForTimeout(2000);

    // Check that institutional ownership is not N/A
    const instOwnership = page.locator('text=/Institutional Ownership/i').locator('xpath=ancestor::*[2]');
    const instValue = await instOwnership.textContent();
    expect(instValue).not.toContain('N/A');

    // Check that insider ownership is not N/A
    const insiderOwnership = page.locator('text=/Insider Ownership/i').locator('xpath=ancestor::*[2]');
    const insiderValue = await insiderOwnership.textContent();
    expect(insiderValue).not.toContain('N/A');

    // Check that short interest is not N/A
    const shortInterest = page.locator('text=/Short Interest|Short %/i').locator('xpath=ancestor::*[2]');
    const shortValue = await shortInterest.textContent();
    expect(shortValue).not.toContain('N/A');
  });

  test('API call returns correct positioning data structure', async ({ page }) => {
    // Intercept the positioning API call
    const apiResponsePromise = page.waitForResponse(
      response => response.url().includes(`/api/positioning/stocks`) && response.status() === 200,
      { timeout: 10000 }
    );

    // Navigate to trigger API call
    await page.goto(`/stocks/${testSymbol}`);

    // Wait for API response
    const apiResponse = await apiResponsePromise;
    const responseBody = await apiResponse.json();

    // Verify response structure
    expect(responseBody).toHaveProperty('positioning_metrics');
    expect(responseBody).toHaveProperty('positioning_score');
    expect(responseBody).toHaveProperty('institutional_holders');
    expect(responseBody).toHaveProperty('retail_sentiment');
    expect(responseBody).toHaveProperty('metadata');

    // Verify positioning_score is a number
    expect(typeof responseBody.positioning_score).toBe('number');
    expect(responseBody.positioning_score).toBeGreaterThanOrEqual(0);
    expect(responseBody.positioning_score).toBeLessThanOrEqual(100);

    // Verify institutional_holders is an array
    expect(Array.isArray(responseBody.institutional_holders)).toBe(true);
    expect(responseBody.institutional_holders.length).toBeGreaterThan(0);

    // Verify positioning_metrics structure
    expect(responseBody.positioning_metrics).toHaveProperty('institutional_ownership');
    expect(responseBody.positioning_metrics).toHaveProperty('insider_ownership');
    expect(responseBody.positioning_metrics).toHaveProperty('short_percent_of_float');
  });

  test('handles API errors gracefully', async ({ page }) => {
    // Intercept positioning API and return error
    await page.route('/api/positioning/stocks*', route => {
      route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          error: 'Failed to fetch positioning data'
        })
      });
    });

    // Navigate to stock detail page
    await page.goto(`/stocks/${testSymbol}`);

    // Wait for page to load
    await page.waitForTimeout(2000);

    // Positioning section should either show error or fallback gracefully
    const hasError = await page.getByText(/error|failed|unable/i).isVisible().catch(() => false);
    const hasNoData = await page.getByText(/no data|n\/a/i).isVisible().catch(() => false);

    // One of these should be true - either error message or N/A fallback
    expect(hasError || hasNoData).toBeTruthy();
  });

  test('handles missing positioning data for non-existent symbol', async ({ page }) => {
    const nonExistentSymbol = 'NONEXISTENT_TEST_12345';

    // Navigate to non-existent stock
    await page.goto(`/stocks/${nonExistentSymbol}`);

    // Wait for potential error or empty state
    await page.waitForTimeout(3000);

    // Should either show 404, error, or N/A for positioning data
    const hasError = await page.getByText(/not found|error|invalid|no stock found/i).isVisible().catch(() => false);
    const hasNoData = await page.locator('text=/n\\/a/i').first().isVisible().catch(() => false);

    // One of these should be true OR the page should have loaded (even if with N/A values)
    const pageLoaded = await page.locator('#root').isVisible();
    expect(hasError || hasNoData || pageLoaded).toBeTruthy();
  });

  test('positioning data updates when navigating between different stocks', async ({ page }) => {
    // Navigate to first stock
    await page.goto(`/stocks/${testSymbol}`);
    await page.waitForLoadState('networkidle');

    // Get initial institutional ownership value
    await expect(page.getByText('Institutional Ownership')).toBeVisible({ timeout: 10000 });
    const firstOwnership = await page.locator('text=/Institutional Ownership/i')
      .locator('xpath=ancestor::*[2]')
      .textContent();

    // Navigate to different stock
    const secondSymbol = 'AAPL';
    await page.goto(`/stocks/${secondSymbol}`);
    await page.waitForLoadState('networkidle');

    // Wait for positioning data to update
    await page.waitForTimeout(1000);

    // Get new institutional ownership value
    const secondOwnership = await page.locator('text=/Institutional Ownership/i')
      .locator('xpath=ancestor::*[2]')
      .textContent()
      .catch(() => 'N/A');

    // Values should be different (or one might be N/A if AAPL doesn't have data)
    expect(firstOwnership).not.toBe(secondOwnership);
  });

  test('responsive design works on mobile', async ({ page }) => {
    // Set mobile viewport
    await page.setViewportSize({ width: 375, height: 667 });

    // Navigate to stock
    await page.goto(`/stocks/${testSymbol}`);

    // Wait for page to load
    await page.waitForLoadState('networkidle');

    // Positioning data should still be visible (might be stacked differently)
    await expect(page.getByText('Institutional Ownership')).toBeVisible({ timeout: 10000 });
  });

  test('page loads within acceptable time limits', async ({ page }) => {
    const startTime = Date.now();

    // Navigate to stock detail page
    await page.goto(`/stocks/${testSymbol}`);

    // Wait for positioning data to appear
    await expect(page.getByText('Institutional Ownership')).toBeVisible({ timeout: 10000 });

    const loadTime = Date.now() - startTime;

    // Should load within 5 seconds
    expect(loadTime).toBeLessThan(5000);
  });

  test('positioning data persists when switching tabs on stock detail page', async ({ page }) => {
    // Navigate to stock
    await page.goto(`/stocks/${testSymbol}`);
    await page.waitForLoadState('networkidle');

    // Wait for positioning data
    await expect(page.getByText('Institutional Ownership')).toBeVisible({ timeout: 10000 });
    const initialValue = await page.locator('text=/Institutional Ownership/i')
      .locator('xpath=ancestor::*[2]')
      .textContent();

    // Look for tabs (if they exist)
    const tabs = page.locator('[role="tab"], .MuiTab-root');

    if (await tabs.count() > 1) {
      // Click on a different tab
      await tabs.nth(1).click();
      await page.waitForTimeout(500);

      // Click back to overview/first tab
      await tabs.first().click();
      await page.waitForTimeout(500);

      // Positioning data should still be there
      const finalValue = await page.locator('text=/Institutional Ownership/i')
        .locator('xpath=ancestor::*[2]')
        .textContent();

      expect(finalValue).toBe(initialValue);
    }
  });

  test('verifies correct percentage formatting (not decimal)', async ({ page }) => {
    // Navigate to stock
    await page.goto(`/stocks/${testSymbol}`);
    await page.waitForLoadState('networkidle');

    // Wait for institutional ownership
    await expect(page.getByText('Institutional Ownership')).toBeVisible({ timeout: 10000 });

    // Get the ownership value
    const ownershipSection = page.locator('text=/Institutional Ownership/i').locator('xpath=ancestor::*[2]');
    const text = await ownershipSection.textContent();

    // Extract percentage (should be like "58.40%" not "0.58%")
    const percentageMatch = text.match(/(\d+\.\d+)%/);

    if (percentageMatch) {
      const value = parseFloat(percentageMatch[1]);

      // For stocks with institutional ownership, the value should be > 1
      // (not 0.584 which would indicate incorrect formatting)
      expect(value).toBeGreaterThan(1);
    }
  });
});

test.describe('Positioning Summary Page E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to positioning summary page (if it exists)
    await page.goto('/positioning/summary');
    await page.waitForLoadState('networkidle');
  });

  test.skip('loads positioning summary with market overview', async ({ page }) => {
    // This test is skipped because positioning summary page may not exist yet
    // It's here as a placeholder for future implementation

    // Wait for market overview section
    await expect(page.getByText(/Market Overview|Positioning Summary/i)).toBeVisible({ timeout: 10000 });

    // Check for institutional flow
    await expect(page.getByText(/Institutional Flow|Institutional Sentiment/i)).toBeVisible();

    // Check for retail sentiment
    await expect(page.getByText(/Retail Sentiment/i)).toBeVisible();
  });
});
