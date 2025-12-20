import { test } from '@playwright/test';

test('Capture PHI on TradingView', async ({ page }) => {
  await page.goto('https://www.tradingview.com/chart/?symbol=NYSE:PHI', { 
    waitUntil: 'networkidle', 
    timeout: 60000 
  });
  
  await page.waitForTimeout(8000);
  
  await page.screenshot({ path: '/tmp/tradingview_phi.png' });
  console.log('✅ Screenshot saved');
});
