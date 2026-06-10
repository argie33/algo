import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  try {
    console.log('Loading dashboard...');
    await page.goto('http://localhost:5173/', { waitUntil: 'domcontentloaded' });

    // Wait for content
    await page.waitForTimeout(3000);

    // Get page title and main content
    const title = await page.title();
    console.log(`\nPage title: "${title}"`);

    // Check what routes exist
    const currentUrl = page.url();
    console.log(`Current URL: ${currentUrl}`);

    // Get body HTML preview
    const bodyText = await page.evaluate(() => {
      return document.body.innerText.substring(0, 500);
    });
    console.log(`\nPage content preview:\n${bodyText}`);

    // Check for main app element
    const hasApp = await page.locator('[id="app"]').count() > 0 ||
                  await page.locator('[class*="app"]').count() > 0 ||
                  await page.locator('[class*="main"]').count() > 0;
    console.log(`\nApp element found: ${hasApp}`);

    // Look for any dashboard-related elements
    const dashboardElements = await page.locator('[class*="dashboard"]').count();
    console.log(`Dashboard elements: ${dashboardElements}`);

    // Check for navigation/routing
    const navElements = await page.locator('[class*="nav"], [class*="menu"], [class*="sidebar"]').count();
    console.log(`Navigation elements: ${navElements}`);

    // Check for error messages
    const errorText = await page.evaluate(() => {
      const errors = [];
      document.querySelectorAll('[class*="error"], [class*="alert"]').forEach(el => {
        if (el.innerText) errors.push(el.innerText);
      });
      return errors;
    });
    if (errorText.length > 0) {
      console.log(`\nErrors detected:\n${errorText.join('\n')}`);
    }

    // Try to navigate to /app/dashboard directly
    console.log('\n\nTrying /app/dashboard route...');
    await page.goto('http://localhost:5173/app/dashboard', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);

    const dashboardTitle = await page.evaluate(() => document.body.innerText.substring(0, 200));
    console.log(`Dashboard page content:\n${dashboardTitle}`);

  } catch (error) {
    console.error('Error:', error.message);
  } finally {
    await browser.close();
  }
})();
