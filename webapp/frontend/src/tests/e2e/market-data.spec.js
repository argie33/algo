import { test, expect } from '@playwright/test';

test.describe('Market Data', () => {
  test.beforeEach(async ({ page }) => {
    // Login before each test
    await page.goto('/');
    await page.click('text=Login');
    await page.fill('input[type="email"]', 'test@example.com');
    await page.fill('input[type="password"]', 'testpass123');
    await page.click('button[type="submit"]');
    await page.waitForURL('**/dashboard');
  });

  test('should display market overview', async ({ page }) => {
    await page.click('text=Market');
    await expect(page.locator('text=Market Overview')).toBeVisible();
    await expect(page.locator('[data-testid="market-indices"]')).toBeVisible();
    await expect(page.locator('[data-testid="top-gainers"]')).toBeVisible();
    await expect(page.locator('[data-testid="top-losers"]')).toBeVisible();
  });

  test('should search for stocks', async ({ page }) => {
    await page.click('text=Market');
    
    await page.fill('input[placeholder="Search stocks..."]', 'AAPL');
    await page.press('input[placeholder="Search stocks..."]', 'Enter');
    
    await expect(page.locator('text=Apple Inc.')).toBeVisible();
    await expect(page.locator('text=AAPL')).toBeVisible();
    await expect(page.locator('[data-testid="stock-price"]')).toBeVisible();
  });

  test('should display stock details', async ({ page }) => {
    await page.click('text=Market');
    
    await page.fill('input[placeholder="Search stocks..."]', 'AAPL');
    await page.press('input[placeholder="Search stocks..."]', 'Enter');
    
    await page.click('text=AAPL');
    
    await expect(page.locator('[data-testid="stock-chart"]')).toBeVisible();
    await expect(page.locator('[data-testid="stock-fundamentals"]')).toBeVisible();
    await expect(page.locator('[data-testid="stock-news"]')).toBeVisible();
  });

  test('should display real-time quotes', async ({ page }) => {
    await page.click('text=Live Data');
    
    await expect(page.locator('[data-testid="live-quotes"]')).toBeVisible();
    
    // Check if quotes are updating
    const initialPrice = await page.locator('[data-testid="stock-price"]:first-child').textContent();
    
    // Wait for potential update
    await page.waitForTimeout(5000);
    
    const updatedPrice = await page.locator('[data-testid="stock-price"]:first-child').textContent();
    
    // Price should be present (may or may not have changed)
    expect(initialPrice).toMatch(/\$[\d,]+\.\d{2}/);
    expect(updatedPrice).toMatch(/\$[\d,]+\.\d{2}/);
  });

  test('should display market charts', async ({ page }) => {
    await page.click('text=Market');
    
    // Wait for charts to load
    await page.waitForSelector('[data-testid="market-chart"]');
    
    await expect(page.locator('[data-testid="market-chart"]')).toBeVisible();
    
    // Test chart time period controls
    await page.click('text=1D');
    await page.waitForTimeout(1000);
    
    await page.click('text=1W');
    await page.waitForTimeout(1000);
    
    await page.click('text=1M');
    await page.waitForTimeout(1000);
  });

  test('should add stock to watchlist', async ({ page }) => {
    await page.click('text=Market');
    
    await page.fill('input[placeholder="Search stocks..."]', 'AAPL');
    await page.press('input[placeholder="Search stocks..."]', 'Enter');
    
    await page.click('[data-testid="add-to-watchlist"]');
    
    await expect(page.locator('text=Added to watchlist')).toBeVisible();
    
    // Check watchlist
    await page.click('text=Watchlist');
    await expect(page.locator('text=AAPL')).toBeVisible();
  });

  test('should display technical indicators', async ({ page }) => {
    await page.click('text=Market');
    
    await page.fill('input[placeholder="Search stocks..."]', 'AAPL');
    await page.press('input[placeholder="Search stocks..."]', 'Enter');
    
    await page.click('text=AAPL');
    await page.click('text=Technical Analysis');
    
    await expect(page.locator('[data-testid="rsi-indicator"]')).toBeVisible();
    await expect(page.locator('[data-testid="macd-indicator"]')).toBeVisible();
    await expect(page.locator('[data-testid="moving-averages"]')).toBeVisible();
  });

  test('should handle market data errors gracefully', async ({ page }) => {
    // Mock API error
    await page.route('**/api/market-data/**', route => {
      route.fulfill({
        status: 500,
        body: JSON.stringify({ error: 'Market data unavailable' })
      });
    });

    await page.click('text=Market');
    
    // Check for error handling
    await expect(page.locator('text=Market data unavailable')).toBeVisible();
    await expect(page.locator('text=Retry')).toBeVisible();
  });

  test('should filter stocks by criteria', async ({ page }) => {
    await page.click('text=Screener');
    
    // Set filter criteria
    await page.selectOption('select[name="marketCap"]', 'large');
    await page.selectOption('select[name="sector"]', 'technology');
    await page.fill('input[name="minPrice"]', '100');
    await page.fill('input[name="maxPrice"]', '500');
    
    await page.click('text=Apply Filters');
    
    // Check results
    await expect(page.locator('[data-testid="screener-results"]')).toBeVisible();
    await expect(page.locator('[data-testid="stock-result"]')).toHaveCount({ min: 1 });
  });

  test('should display news and events', async ({ page }) => {
    await page.click('text=News');
    
    await expect(page.locator('[data-testid="news-articles"]')).toBeVisible();
    await expect(page.locator('[data-testid="news-article"]')).toHaveCount({ min: 1 });
    
    // Check news article details
    const firstArticle = page.locator('[data-testid="news-article"]').first();
    await expect(firstArticle.locator('[data-testid="news-title"]')).toBeVisible();
    await expect(firstArticle.locator('[data-testid="news-date"]')).toBeVisible();
    await expect(firstArticle.locator('[data-testid="news-source"]')).toBeVisible();
  });
});