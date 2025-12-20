import { test, expect } from '@playwright/test';

test.describe('Mobile Responsiveness - iPhone 12', () => {
  test.use({
    viewport: { width: 390, height: 844 },
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15'
  });

  test('Dashboard should be readable and functional on mobile', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Check if content overflows viewport
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);

    console.log(`Dashboard - Scroll width: ${scrollWidth}, Client width: ${clientWidth}`);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 10); // 10px tolerance

    // Check if text is readable (not too small)
    const textSizes = await page.evaluate(() => {
      const elements = Array.from(document.querySelectorAll('p, span, div'));
      return elements.slice(0, 20).map(el => {
        const fontSize = window.getComputedStyle(el).fontSize;
        return parseInt(fontSize);
      }).filter(size => size > 0);
    });

    // Most text should be readable
    const readableSizes = textSizes.filter(size => size >= 12);
    expect(readableSizes.length / textSizes.length).toBeGreaterThan(0.7);
  });

  test('Stock Detail page should not have horizontal scroll', async ({ page }) => {
    await page.goto('/stock/AAPL');
    await page.waitForLoadState('networkidle');

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);

    console.log(`Stock Detail - Scroll width: ${scrollWidth}, Client width: ${clientWidth}`);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 10);
  });

  test('Navigation should work on mobile', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    // Look for mobile menu button
    const menuButtonSelectors = [
      'button[aria-label*="menu"]',
      'button[aria-label*="Menu"]',
      '[data-testid*="menu"]',
      '.MuiIconButton-root'
    ];

    for (const selector of menuButtonSelectors) {
      const menuButton = page.locator(selector).first();
      if (await menuButton.isVisible()) {
        await menuButton.click();
        await page.waitForTimeout(500);
        break;
      }
    }
  });

  test('Market Overview should stack on mobile', async ({ page }) => {
    await page.goto('/market');
    await page.waitForLoadState('networkidle');

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);

    console.log(`Market - Scroll width: ${scrollWidth}, Client width: ${clientWidth}`);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 10);
  });

  test('Stock Explorer table should not cause horizontal scroll', async ({ page }) => {
    await page.goto('/explorer');
    await page.waitForLoadState('networkidle');

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);

    console.log(`Explorer - Scroll width: ${scrollWidth}, Client width: ${clientWidth}`);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 10);
  });

  test('Watchlist should not have layout issues', async ({ page }) => {
    await page.goto('/watchlist');
    await page.waitForLoadState('networkidle');

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);

    console.log(`Watchlist - Scroll width: ${scrollWidth}, Client width: ${clientWidth}`);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 10);
  });

  test('Portfolio page should not have layout issues', async ({ page }) => {
    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);

    console.log(`Portfolio - Scroll width: ${scrollWidth}, Client width: ${clientWidth}`);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 10);
  });

  test('Trading Signals should not have layout issues', async ({ page }) => {
    await page.goto('/signals');
    await page.waitForLoadState('networkidle');

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);

    console.log(`Signals - Scroll width: ${scrollWidth}, Client width: ${clientWidth}`);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 10);
  });

  test('Screener should not have layout issues', async ({ page }) => {
    await page.goto('/screener');
    await page.waitForLoadState('networkidle');

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);

    console.log(`Screener - Scroll width: ${scrollWidth}, Client width: ${clientWidth}`);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 10);
  });

  test('Take screenshots of critical pages', async ({ page }) => {
    const pages = [
      { path: '/', name: 'dashboard' },
      { path: '/stock/AAPL', name: 'stock-detail' },
      { path: '/portfolio', name: 'portfolio' },
      { path: '/screener', name: 'screener' },
      { path: '/signals', name: 'signals' }
    ];

    for (const { path, name } of pages) {
      await page.goto(path);
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(1000);

      await page.screenshot({
        path: `playwright-report/mobile-${name}.png`,
        fullPage: true
      });
    }
  });
});

test.describe('Tablet Responsiveness - iPad', () => {
  test.use({
    viewport: { width: 768, height: 1024 }
  });

  test('Dashboard should utilize tablet space effectively', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);

    console.log(`Tablet Dashboard - Scroll width: ${scrollWidth}, Client width: ${clientWidth}`);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 10);
  });

  test('Tables should be readable on tablet', async ({ page }) => {
    await page.goto('/stock/AAPL');
    await page.waitForLoadState('networkidle');

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);

    console.log(`Tablet Stock Detail - Scroll width: ${scrollWidth}, Client width: ${clientWidth}`);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 10);
  });
});

test.describe('Responsive Breakpoint Tests', () => {
  test('Should adapt layout at mobile breakpoint (375px)', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);

    console.log(`375px breakpoint - Scroll width: ${scrollWidth}, Client width: ${clientWidth}`);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 10);
  });

  test('Should adapt layout at tablet breakpoint (768px)', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);

    console.log(`768px breakpoint - Scroll width: ${scrollWidth}, Client width: ${clientWidth}`);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 10);
  });

  test('Should adapt layout at desktop breakpoint (1920px)', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);

    console.log(`1920px breakpoint - Scroll width: ${scrollWidth}, Client width: ${clientWidth}`);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth + 10);
  });
});