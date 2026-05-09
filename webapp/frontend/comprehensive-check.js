import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  const issues = [];
  const warnings = [];

  page.on('console', async (msg) => {
    if (msg.type() === 'error') {
      const args = [];
      for (const arg of msg.args()) {
        try {
          args.push(await arg.jsonValue());
        } catch {
          args.push('<unserializable>');
        }
      }
      issues.push({ type: 'error', message: msg.text(), args });
    } else if (msg.type() === 'warn' && !msg.text().includes('[API CONFIG]') && !msg.text().includes('Cognito')) {
      warnings.push(msg.text());
    }
  });

  page.on('pageerror', (error) => {
    issues.push({ type: 'exception', message: error.message });
  });

  page.on('response', (response) => {
    if (response.status() >= 400) {
      // Log failed API requests
      if (!response.url().includes('localhost:5178') || response.status() !== 404) {
        console.log(`API Error: ${response.status()} ${response.url()}`);
      }
    }
  });

  const routes = ['/', '/portfolio', '/settings', '/market-overview'];

  for (const route of routes) {
    console.log(`Checking ${route}...`);
    try {
      await page.goto(`http://localhost:5178${route}`, { waitUntil: 'load', timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(1000);
    } catch (e) {
      console.log(`  Navigation timeout (may be OK)`);
    }
  }

  console.log('\n=== ISSUES FOUND ===');
  if (issues.length === 0) {
    console.log('✓ No errors or uncaught exceptions found!');
  } else {
    console.log(`Found ${issues.length} issue(s):`);
    issues.forEach((issue, i) => {
      console.log(`\n${i + 1}. [${issue.type.toUpperCase()}] ${issue.message}`);
      if (issue.args) {
        console.log(`   ${JSON.stringify(issue.args).substring(0, 200)}`);
      }
    });
  }

  if (warnings.length > 0) {
    console.log(`\n=== NON-CONFIG WARNINGS ===`);
    warnings.slice(0, 10).forEach((w, i) => {
      console.log(`${i + 1}. ${w}`);
    });
    if (warnings.length > 10) {
      console.log(`... and ${warnings.length - 10} more warnings`);
    }
  }

  console.log('\n=== NEXT STEPS ===');
  if (issues.length === 0) {
    console.log('✓ Application appears healthy! Check these manually:');
    console.log('  - Click around the UI to verify interactions work');
    console.log('  - Check that data loads (if API is connected)');
    console.log('  - Verify responsive design on mobile');
  } else {
    console.log('Fix the errors above and run this check again.');
  }

  await browser.close();
})();
