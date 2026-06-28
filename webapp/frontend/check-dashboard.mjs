#!/usr/bin/env node
import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    console.log('📱 Opening dashboard at http://localhost:5173/');
    await page.goto('http://localhost:5173/', { waitUntil: 'networkidle', timeout: 30000 });

    console.log('✅ Dashboard loaded\n');

    // Wait for React rendering
    await page.waitForTimeout(1500);

    // Take screenshot
    await page.screenshot({ path: 'dashboard-screenshot.png', fullPage: true });
    console.log('📸 Screenshot saved: dashboard-screenshot.png\n');

    // Check for error messages
    const errors = await page.locator('text=/unavailable|unable|error|failed|not available/i').all();
    console.log(`Found ${errors.length} error/unavailable messages\n`);

    if (errors.length > 0) {
      console.log('⚠️ Panels with issues:\n');
      for (const error of errors.slice(0, 10)) {
        const text = await error.textContent();
        console.log(`  • ${text?.substring(0, 80)}`);
      }
    } else {
      console.log('✅ No error messages found on dashboard\n');
    }

    // Get page content to analyze
    const bodyText = await page.textContent('body');

    // Check if main dashboard content is present
    const hasAlgoStatus = bodyText.includes('Algo') || bodyText.includes('Status') || bodyText.includes('Portfolio');
    const hasPositions = bodyText.includes('Position') || bodyText.includes('Holdings');
    const hasPerformance = bodyText.includes('Performance') || bodyText.includes('Return');

    console.log('Dashboard Content Check:');
    console.log(`  ${hasAlgoStatus ? '✅' : '❌'} Algo/Status content visible`);
    console.log(`  ${hasPositions ? '✅' : '❌'} Positions/Holdings content visible`);
    console.log(`  ${hasPerformance ? '✅' : '❌'} Performance content visible`);

    console.log('\n✨ Dashboard check complete!');

  } catch (error) {
    console.error('Error:', error.message);
  } finally {
    await browser.close();
  }
})();
