const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  const errors = [];
  const apiErrors = [];
  const failedRequests = [];

  page.on('console', msg => {
    const text = msg.text();
    const type = msg.type();
    if (type === 'error') {
      errors.push(text);
    }
  });

  page.on('pageerror', error => {
    errors.push(`PAGE ERROR: ${error.message}`);
  });

  page.on('response', response => {
    const status = response.status();
    const url = response.url();
    if (status >= 400 && status < 600) {
      if (url.includes('/api/')) {
        apiErrors.push(`${status} ${url.split('/api/')[1]}`);
      } else {
        failedRequests.push(`${status} ${url}`);
      }
    }
  });

  const routes = ['/app/markets', '/app/deep-value', '/app/economic', '/app/portfolio'];

  for (const route of routes) {
    try {
      console.log(`\nChecking route: ${route}...`);
      await page.goto(`http://localhost:5182${route}`, { waitUntil: 'networkidle', timeout: 20000 });
      await page.waitForTimeout(1000);
      const content = await page.content();
      const hasError = content.includes('error') || content.includes('Error');
      console.log(`✓ Loaded (has error text: ${hasError})`);
    } catch (e) {
      console.log(`✗ Failed: ${e.message}`);
      errors.push(`Navigation to ${route} failed: ${e.message}`);
    }
  }

  await page.close();
  await context.close();
  await browser.close();

  console.log('\n\n=== SUMMARY ===');
  console.log(`Console Errors: ${errors.length}`);
  if (errors.length > 0) {
    errors.slice(0, 10).forEach((e, i) => console.log(`  ${i + 1}. ${e}`));
    if (errors.length > 10) console.log(`  ... and ${errors.length - 10} more`);
  }

  console.log(`\nAPI Errors (5xx): ${apiErrors.length}`);
  if (apiErrors.length > 0) {
    apiErrors.slice(0, 10).forEach((e, i) => console.log(`  ${i + 1}. ${e}`));
  }

  console.log(`\nFailed Requests: ${failedRequests.length}`);
  if (failedRequests.length > 0) {
    failedRequests.slice(0, 10).forEach((e, i) => console.log(`  ${i + 1}. ${e}`));
  }
})();
