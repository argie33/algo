import { chromium } from 'playwright';

async function testDashboard() {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.setViewportSize({ width: 1920, height: 1080 });

    console.log('Navigating to dashboard...');
    await page.goto('http://localhost:5173', { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(3000);

    // Check for error messages
    const errorText = await page.evaluate(() => {
      const errorElements = document.querySelectorAll('[class*="error"], [class*="unavailable"]');
      return Array.from(errorElements)
        .map(el => el.textContent?.trim())
        .filter(text => text && text.length > 10)
        .slice(0, 5);
    });

    console.log('\nError messages found:');
    if (errorText.length === 0) {
      console.log('  ✓ No error messages detected!');
    } else {
      errorText.forEach((text, i) => {
        console.log(`  ${i + 1}. ${text.substring(0, 80)}`);
      });
    }

    // Check for "healthy" or "API Connection Issue" messages
    const pageText = await page.textContent();
    const hasAPIIssue = pageText.includes('API Connection Issue');
    const hasHealthy = pageText.includes('healthy');

    console.log(`\nDashboard Status:`);
    console.log(`  API Connection Issue: ${hasAPIIssue ? 'YES (bad)' : 'NO (good)'}`);
    console.log(`  "Healthy" text found: ${hasHealthy ? 'YES' : 'NO'}`);

    // Count panels with data
    const panelCount = await page.evaluate(() => {
      const panels = document.querySelectorAll('[class*="panel"], [class*="card"]');
      return panels.length;
    });

    console.log(`\nPanels detected: ${panelCount}`);

    // Take screenshot
    await page.screenshot({ path: 'dashboard_after_fix.png', fullPage: true });
    console.log('\nScreenshot saved: dashboard_after_fix.png');

  } finally {
    await browser.close();
  }
}

testDashboard().catch(console.error);
