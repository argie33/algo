import { test } from '@playwright/test';

test('Capture PHI TradingView chart for verification', async ({ page }) => {
  console.log('Opening TradingView PHI chart...');
  await page.goto('https://www.tradingview.com/chart/?symbol=NYSE:PHI', { 
    waitUntil: 'networkidle', 
    timeout: 60000 
  });
  
  console.log('Waiting for chart to load completely...');
  await page.waitForTimeout(8000);
  
  // Get the current view
  console.log('Taking full page screenshot...');
  await page.screenshot({ 
    path: '/tmp/tradingview_phi_full.png', 
    fullPage: false 
  });
  
  console.log('✅ Screenshot saved to /tmp/tradingview_phi_full.png');
  console.log('\nPlease verify on the chart:');
  console.log('  - Aug 4, 2025: Look for BUY label (price crosses blue line UP)');
  console.log('  - Aug 27, 2025: Look for SELL label (price crosses red line DOWN)');
  console.log('  - Nov 4, 2025: Look for BUY label (price crosses blue line UP)');
  
  // Try to navigate using keyboard to ensure we can see different timeframes
  await page.waitForTimeout(3000);
});
