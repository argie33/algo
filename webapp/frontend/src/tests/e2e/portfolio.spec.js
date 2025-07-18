import { test, expect } from '@playwright/test';

test.describe('Portfolio Management', () => {
  test.beforeEach(async ({ page }) => {
    // Login before each test
    await page.goto('/');
    await page.click('text=Login');
    await page.fill('input[type="email"]', 'test@example.com');
    await page.fill('input[type="password"]', 'testpass123');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/dashboard');
  });

  test('should display portfolio overview', async ({ page }) => {
    await page.click('text=Portfolio');
    await expect(page.locator('text=Portfolio Overview')).toBeVisible();
    await expect(page.locator('[data-testid="portfolio-value"]')).toBeVisible();
    await expect(page.locator('[data-testid="portfolio-performance"]')).toBeVisible();
  });

  test('should create new portfolio', async ({ page }) => {
    await page.click('text=Portfolio');
    await page.click('text=New Portfolio');
    
    await page.fill('input[name="name"]', 'Test Portfolio');
    await page.fill('textarea[name="description"]', 'Test portfolio description');
    await page.click('button[type="submit"]');
    
    await expect(page.locator('text=Portfolio created successfully')).toBeVisible();
    await expect(page.locator('text=Test Portfolio')).toBeVisible();
  });

  test('should add position to portfolio', async ({ page }) => {
    await page.click('text=Portfolio');
    await page.click('text=Add Position');
    
    await page.fill('input[name="symbol"]', 'AAPL');
    await page.fill('input[name="shares"]', '100');
    await page.fill('input[name="price"]', '150.00');
    await page.click('button[type="submit"]');
    
    await expect(page.locator('text=Position added successfully')).toBeVisible();
    await expect(page.locator('text=AAPL')).toBeVisible();
    await expect(page.locator('text=100')).toBeVisible();
  });

  test('should calculate portfolio metrics', async ({ page }) => {
    await page.click('text=Portfolio');
    
    // Wait for portfolio data to load
    await page.waitForSelector('[data-testid="portfolio-value"]');
    
    const portfolioValue = await page.locator('[data-testid="portfolio-value"]').textContent();
    const dailyChange = await page.locator('[data-testid="daily-change"]').textContent();
    const totalReturn = await page.locator('[data-testid="total-return"]').textContent();
    
    expect(portfolioValue).toMatch(/\$[\d,]+\.\d{2}/);
    expect(dailyChange).toMatch(/[+-]\$[\d,]+\.\d{2}/);
    expect(totalReturn).toMatch(/[+-]\d+\.\d{2}%/);
  });

  test('should update position in portfolio', async ({ page }) => {
    await page.click('text=Portfolio');
    
    // Click edit on first position
    await page.click('[data-testid="edit-position"]:first-child');
    
    await page.fill('input[name="shares"]', '200');
    await page.click('button[type="submit"]');
    
    await expect(page.locator('text=Position updated successfully')).toBeVisible();
    await expect(page.locator('text=200')).toBeVisible();
  });

  test('should delete position from portfolio', async ({ page }) => {
    await page.click('text=Portfolio');
    
    // Click delete on first position
    await page.click('[data-testid="delete-position"]:first-child');
    
    // Confirm deletion
    await page.click('text=Confirm Delete');
    
    await expect(page.locator('text=Position deleted successfully')).toBeVisible();
  });

  test('should display portfolio chart', async ({ page }) => {
    await page.click('text=Portfolio');
    
    // Wait for chart to load
    await page.waitForSelector('[data-testid="portfolio-chart"]');
    
    // Check if chart is visible
    await expect(page.locator('[data-testid="portfolio-chart"]')).toBeVisible();
    
    // Check chart controls
    await expect(page.locator('text=1D')).toBeVisible();
    await expect(page.locator('text=1W')).toBeVisible();
    await expect(page.locator('text=1M')).toBeVisible();
    await expect(page.locator('text=1Y')).toBeVisible();
  });

  test('should handle portfolio errors gracefully', async ({ page }) => {
    // Mock API error
    await page.route('**/api/portfolio', route => {
      route.fulfill({
        status: 500,
        body: JSON.stringify({ error: 'Internal Server Error' })
      });
    });

    await page.click('text=Portfolio');
    
    // Check for error handling
    await expect(page.locator('text=Failed to load portfolio')).toBeVisible();
    await expect(page.locator('text=Try again')).toBeVisible();
  });

  test('should export portfolio data', async ({ page }) => {
    await page.click('text=Portfolio');
    
    // Set up download listener
    const downloadPromise = page.waitForEvent('download');
    
    await page.click('text=Export');
    await page.click('text=Export to CSV');
    
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/portfolio.*\.csv$/);
  });
});