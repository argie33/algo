import { test } from '@playwright/test';

test('Capture PHI TradingView chart for verification', async ({ page }) => {
  await page.goto('https://www.tradingview.com/chart/?symbol=NYSE:PHI', { 
    waitUntil: 'networkidle', 
    timeout: 60000 
  });
  
  await page.waitForTimeout(8000);
  
  // Get the current view
  await page.screenshot({ 
    path: '/tmp/tradingview_phi_full.png', 
    fullPage: false 
  });
  
  
  // Try to navigate using keyboard to ensure we can see different timeframes
  await page.waitForTimeout(3000);
});
