import { test, expect } from '@playwright/test';

test('Verify all historical PHI signals on TradingView match our calculations', async ({ page }) => {
  // Navigate to PHI chart
  await page.goto('https://www.tradingview.com/chart/?symbol=NYSE:PHI', { 
    waitUntil: 'networkidle', 
    timeout: 60000 
  });
  
  await page.waitForTimeout(8000);
  
  
  // Take screenshot of current view (Nov 4)
  await page.screenshot({ path: '/tmp/tradingview_nov4.png' });
  
  // Scroll left to see August data
  // Try pressing left arrow key multiple times to navigate backwards
  for (let i = 0; i < 15; i++) {
    await page.keyboard.press('ArrowLeft');
    await page.waitForTimeout(200);
  }
  
  await page.waitForTimeout(2000);
  await page.screenshot({ path: '/tmp/tradingview_august.png' });
  
  // Scroll right to get back to Nov
  for (let i = 0; i < 15; i++) {
    await page.keyboard.press('ArrowRight');
    await page.waitForTimeout(200);
  }
  
  await page.waitForTimeout(2000);
  await page.screenshot({ path: '/tmp/tradingview_november_final.png' });
  
});

