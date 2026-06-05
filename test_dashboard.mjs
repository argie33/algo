import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();

// Listen for errors
let jsErrors = [];
page.on('console', msg => {
  if (msg.type() === 'error') {
    jsErrors.push(msg.text());
  }
});

page.on('pageerror', error => {
  jsErrors.push(error.toString());
});

try {
  console.log('Navigating to Economic Dashboard...');
  await page.goto('http://localhost:5173/dashboard/economic', { waitUntil: 'networkidle', timeout: 15000 });

  // Wait a bit for the page to settle
  await page.waitForTimeout(2000);

  // Check for the Error Boundary or error messages
  const errorBoundaryText = await page.evaluate(() => {
    const errorBoundary = document.querySelector('[class*="error"]');
    return errorBoundary ? errorBoundary.textContent : null;
  });

  // Check if the page loaded successfully
  const pageTitle = await page.title();
  const hasEconomicDashboard = await page.evaluate(() => {
    return document.body.textContent.includes('Economic Dashboard');
  });

  console.log('\n=== Test Results ===');
  console.log(`Page title: ${pageTitle}`);
  console.log(`Has Economic Dashboard title: ${hasEconomicDashboard}`);
  console.log(`JavaScript errors detected: ${jsErrors.length}`);

  if (jsErrors.length > 0) {
    console.log('\nErrors found:');
    jsErrors.forEach(err => console.log(`  - ${err}`));
  } else {
    console.log('\n✓ No JavaScript errors detected!');
  }

  // Check for the specific error we're fixing
  const hasChartDataError = jsErrors.some(err => err.includes('chartData.slice'));
  if (hasChartDataError) {
    console.log('\n✗ FAILED: chartData.slice error still present');
    process.exit(1);
  } else {
    console.log('✓ PASSED: No chartData.slice errors');
  }

  // Take a screenshot
  await page.screenshot({ path: 'economic-dashboard.png' });
  console.log('\nScreenshot saved: economic-dashboard.png');

} catch (error) {
  console.error('Test failed:', error);
  process.exit(1);
} finally {
  await browser.close();
}
