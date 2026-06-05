const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  const issues = [];
  const apiCalls = [];

  // Capture all API calls and responses
  page.on('response', async (response) => {
    const url = response.url();
    if (url.includes('/api/')) {
      const status = response.status();
      let data = null;
      try {
        data = await response.json();
      } catch (e) {
        try {
          data = await response.text();
        } catch {}
      }
      apiCalls.push({
        url: url.split('localhost:3001')[1] || url,
        status: status,
        error: status >= 400,
        dataKeys: data && typeof data === 'object' ? Object.keys(data) : null
      });
      if (status >= 400) {
        issues.push(`API ERROR: ${status} ${url.split('/api/')[1]}`);
      }
    }
  });

  page.on('console', msg => {
    if (msg.type() === 'error') {
      issues.push(`CONSOLE ERROR: ${msg.text()}`);
    }
  });

  page.on('pageerror', error => {
    issues.push(`PAGE ERROR: ${error.message}`);
  });

  try {
    console.log('Loading app...\n');
    await page.goto('http://localhost:5182/app/markets', { waitUntil: 'networkidle', timeout: 20000 });
    await page.waitForTimeout(2000);

    // Try to access different sections
    const testRoutes = ['/app/portfolio', '/app/trades', '/app/deep-value'];
    for (const route of testRoutes) {
      try {
        await page.goto(`http://localhost:5182${route}`, { timeout: 5000 });
        await page.waitForTimeout(500);
      } catch (e) {
        // Silent
      }
    }

  } catch (e) {
    issues.push(`NAV ERROR: ${e.message}`);
  }

  await page.close();
  await context.close();
  await browser.close();

  console.log('=== API CALLS MADE ===\n');
  const grouped = {};
  apiCalls.forEach(call => {
    const path = call.url.split('?')[0];
    if (!grouped[path]) grouped[path] = [];
    grouped[path].push(call.status);
  });

  Object.entries(grouped).sort().forEach(([path, statuses]) => {
    const errors = statuses.filter(s => s >= 400).length;
    const icon = errors > 0 ? '✗' : '✓';
    console.log(`${icon} ${path.padEnd(45)} [${statuses.join(',')}]${errors > 0 ? ` (${errors} errors)` : ''}`);
  });

  console.log('\n=== ISSUES FOUND ===\n');
  if (issues.length === 0) {
    console.log('No errors detected');
  } else {
    const unique = [...new Set(issues)];
    unique.forEach((issue, i) => {
      console.log(`${i + 1}. ${issue}`);
    });
  }

  console.log(`\nTotal API calls: ${apiCalls.length}`);
  console.log(`Failed API calls: ${apiCalls.filter(c => c.error).length}`);
})();
