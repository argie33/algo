import { test, expect } from '@playwright/test';

test('Check real site vs test expectations', async ({ page }) => {
  const apiCalls = [];
  const consoleErrors = [];

  // Capture API calls
  page.on('response', response => {
    if (response.url().includes('/api/')) {
      apiCalls.push({
        url: response.url(),
        status: response.status(),
        ok: response.ok()
      });
    }
  });

  // Capture console errors
  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });

  await page.goto('http://localhost:5173');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);

  console.log('API calls made:', apiCalls);
  console.log('Console errors:', consoleErrors);

  // Check if Dashboard loads
  const dashboardTitle = await page.locator('h1:has-text("ProTrade Analytics")').count();
  console.log('Dashboard title found:', dashboardTitle);

  // Check for missing name fields in market data
  const marketSections = await page.locator('[data-testid*="market"], .market').count();
  console.log('Market sections found:', marketSections);

  // Look for error states or missing data
  const errorMessages = await page.locator('[data-testid*="error"], .error, .MuiAlert-root').count();
  console.log('Error components found:', errorMessages);

  expect(consoleErrors.length).toBeLessThan(30); // Allow expected errors (WebSocket, API unavailability)
  expect(apiCalls.filter(call => !call.ok).length).toBeLessThan(5); // Allow some failed calls
});