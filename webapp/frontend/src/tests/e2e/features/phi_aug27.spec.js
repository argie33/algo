import { test } from '@playwright/test';

test('Screenshot PHI Aug 27 on TradingView', async ({ page }) => {
  // Navigate to PHI chart
  await page.goto('https://www.tradingview.com/chart/?symbol=NYSE:PHI', { waitUntil: 'networkidle', timeout: 60000 });
  
  // Wait for chart to fully load
  await page.waitForTimeout(10000);
  
  // Try to navigate to Aug 27 by scrolling or using keyboard
  // First, let's just take a screenshot of the current view
  await page.screenshot({ path: '/tmp/phi_full_chart.png', fullPage: true });
  console.log('Full chart screenshot saved');
});
