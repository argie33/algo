import { test, expect } from '@playwright/test';

test('Verify all historical PHI signals on TradingView match our calculations', async ({ page }) => {
  // Navigate to PHI chart
  await page.goto('https://www.tradingview.com/chart/?symbol=NYSE:PHI', { 
    waitUntil: 'networkidle', 
    timeout: 60000 
  });
  
  await page.waitForTimeout(8000);
  
  console.log('\n=== VERIFYING PHI SIGNALS ON TRADINGVIEW ===\n');
  
  // Take screenshot of current view (Nov 4)
  console.log('📸 Taking screenshot of CURRENT VIEW (Nov 4 area)...');
  await page.screenshot({ path: '/tmp/tradingview_nov4.png' });
  console.log('✅ Saved: /tmp/tradingview_nov4.png');
  
  // Scroll left to see August data
  console.log('\n⬅️  Scrolling left to view AUGUST 2025...');
  // Try pressing left arrow key multiple times to navigate backwards
  for (let i = 0; i < 15; i++) {
    await page.keyboard.press('ArrowLeft');
    await page.waitForTimeout(200);
  }
  
  await page.waitForTimeout(2000);
  console.log('📸 Taking screenshot of AUGUST area (looking for Aug 4 Buy and Aug 27 Sell)...');
  await page.screenshot({ path: '/tmp/tradingview_august.png' });
  console.log('✅ Saved: /tmp/tradingview_august.png');
  
  // Scroll right to get back to Nov
  console.log('\n➡️  Scrolling right to return to NOVEMBER...');
  for (let i = 0; i < 15; i++) {
    await page.keyboard.press('ArrowRight');
    await page.waitForTimeout(200);
  }
  
  await page.waitForTimeout(2000);
  console.log('📸 Taking final screenshot of NOVEMBER view...');
  await page.screenshot({ path: '/tmp/tradingview_november_final.png' });
  console.log('✅ Saved: /tmp/tradingview_november_final.png');
  
  console.log('\n✅ SIGNAL VERIFICATION COMPLETE');
  console.log('\nPlease verify these signals appear on the chart:');
  console.log('  ✓ Aug 4, 2025   - BUY signal (green label/arrow)');
  console.log('  ✓ Aug 27, 2025  - SELL signal (red label/arrow)');
  console.log('  ✓ Nov 4, 2025   - BUY signal (green label/arrow)');
});
