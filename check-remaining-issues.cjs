const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const issues = {
    js_errors: [],
    js_warnings: [],
    failed_requests: [],
    timeout_requests: [],
    slow_endpoints: [],
  };

  page.on('console', msg => {
    if (msg.type() === 'error') {
      const text = msg.text();
      // Filter out ResizeObserver warnings and normal API errors
      if (!text.includes('ResizeObserver') && !text.includes('401')) {
        issues.js_errors.push(text.slice(0, 100));
      }
    } else if (msg.type() === 'warning' && !msg.text().includes('ResizeObserver')) {
      issues.js_warnings.push(msg.text().slice(0, 80));
    }
  });

  page.on('response', response => {
    const status = response.status();
    if (status >= 400 && status !== 401) {
      issues.failed_requests.push(`${response.url().replace('http://localhost:5181', '')} → ${status}`);
    }
  });

  console.log('[INFO] Loading app...');
  const start = Date.now();
  await page.goto('http://localhost:5181', { waitUntil: 'domcontentloaded' }).catch(e => {
    console.log(`[WARN] ${e.message}`);
  });

  await page.waitForTimeout(3000);
  const elapsed = Date.now() - start;

  const content = await page.textContent('body');
  const hasContent = content && content.trim().length > 500;

  // Check for error UI
  const hasErrorBanner = await page.evaluate(() => {
    const text = document.textContent || '';
    return text.includes('API Connection Issue') ||
           text.includes('Connection Error');
  }).catch(() => false);

  console.log('\n========== REMAINING ISSUES CHECK ==========\n');

  if (issues.js_errors.length > 0) {
    console.log(`⚠️  JavaScript Errors: ${issues.js_errors.length}`);
    issues.js_errors.forEach(e => console.log(`  - ${e}`));
  } else {
    console.log(`✅ JavaScript Errors: 0`);
  }

  if (issues.js_warnings.length > 0) {
    console.log(`⚠️  Warnings: ${issues.js_warnings.length}`);
    issues.js_warnings.slice(0, 3).forEach(w => console.log(`  - ${w}`));
  } else {
    console.log(`✅ Warnings: 0`);
  }

  if (issues.failed_requests.length > 0) {
    console.log(`⚠️  Failed Requests (4xx/5xx): ${issues.failed_requests.length}`);
    issues.failed_requests.forEach(r => console.log(`  - ${r}`));
  } else {
    console.log(`✅ Failed Requests: 0`);
  }

  console.log(`\n📊 Page Status:`);
  console.log(`  Load time: ${elapsed}ms`);
  console.log(`  Content loaded: ${hasContent ? 'YES' : 'BLANK'}`);
  console.log(`  Error banner shown: ${hasErrorBanner ? 'YES (API issues detected)' : 'NO'}`);

  const totalIssues = issues.js_errors.length + issues.js_warnings.length + issues.failed_requests.length;

  if (totalIssues === 0 && hasContent) {
    console.log(`\n✅ NO ISSUES FOUND - Site is clean!`);
  } else {
    console.log(`\n⚠️  ${totalIssues} issues detected`);
  }

  await browser.close();
})();
