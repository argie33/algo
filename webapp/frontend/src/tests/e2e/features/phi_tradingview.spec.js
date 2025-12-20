import { test } from '@playwright/test';

test('Screenshot PHI on TradingView', async ({ page }) => {
  // Navigate to PHI chart  
  await page.goto('https://www.tradingview.com/chart/?symbol=NYSE:PHI', { waitUntil: 'networkidle', timeout: 60000 });
  
  // Wait for chart to load
  await page.waitForTimeout(10000);
  
  // Take screenshot
  await page.screenshot({ path: '/tmp/phi_tradingview.png', fullPage: true });
  console.log('Screenshot saved to /tmp/phi_tradingview.png');
});
