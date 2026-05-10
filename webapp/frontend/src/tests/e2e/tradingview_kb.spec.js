import { test } from '@playwright/test';

test('Capture KB Financial Group on TradingView', async ({ page }) => {
  await page.goto('https://www.tradingview.com/chart/?symbol=NYSE:KB', { 
    waitUntil: 'networkidle', 
    timeout: 60000 
  });
  
  await page.waitForTimeout(8000);
  
  await page.screenshot({ path: '/tmp/tradingview_kb_full.png' });
  console.log('✅ KB screenshot saved');
});
