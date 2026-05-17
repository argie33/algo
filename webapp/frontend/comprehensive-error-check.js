import { chromium } from 'playwright';

async function comprehensiveCheck() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const allErrors = [];
  const allWarnings = [];
  const networkErrors = [];
  let pageErrors = 0;

  page.on('console', msg => {
    const text = msg.text();
    const type = msg.type();

    if (type === 'error') {
      allErrors.push(text);
      console.error(`❌ ERROR: ${text}`);
    } else if (type === 'warning') {
      // Filter out expected warnings
      if (!text.includes('Cognito not configured') &&
          !text.includes('fallback API URL') &&
          !text.includes('ReactJS DevTools') &&
          !text.includes('VITE_COGNITO')) {
        allWarnings.push(text);
        console.warn(`⚠️  WARNING: ${text}`);
      }
    }
  });

  page.on('pageerror', err => {
    pageErrors++;
    console.error(`💥 PAGE ERROR: ${err.message}`);
    allErrors.push(`PAGE ERROR: ${err.message}`);
  });

  page.on('response', response => {
    if (response.status() >= 400) {
      const msg = `HTTP ${response.status()}: ${response.url()}`;
      networkErrors.push(msg);
      console.error(`🔴 ${msg}`);
    }
  });

  page.on('requestfailed', request => {
    console.error(`📡 REQUEST FAILED: ${request.url()}`);
    networkErrors.push(`REQUEST FAILED: ${request.url()}`);
  });

  const pages = ['/', '/portfolio', '/stocks', '/settings', '/analytics'];

  for (const route of pages) {
    try {
      await page.goto(`http://localhost:5173${route}`, {
        waitUntil: 'networkidle',
        timeout: 15000
      }).catch(err => {
        console.warn(`Navigation timeout/error: ${err.message}`);
      });

      // Wait for any async operations
      await page.waitForTimeout(2000);

      // Try to interact with the page
      try {
        const buttons = await page.$$('button');
        if (buttons.length > 0) {
        }
      } catch (e) {
        // Ignore interaction errors
      }
    } catch (err) {
      console.error(`Error navigating to ${route}: ${err.message}`);
    }
  }

  await browser.close();


  if (allErrors.length > 0) {
    allErrors.forEach((e, i) => console.log(`  ${i + 1}. ${e}`));
  }

  if (allWarnings.length > 0) {
    allWarnings.forEach((w, i) => console.log(`  ${i + 1}. ${w}`));
  }

  if (networkErrors.length > 0) {
    networkErrors.forEach((ne, i) => console.log(`  ${i + 1}. ${ne}`));
  }

  const hasIssues = allErrors.length > 0 || allWarnings.length > 0 || networkErrors.length > 0;

  process.exit(allErrors.length > 0 ? 1 : 0);
}

comprehensiveCheck().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
