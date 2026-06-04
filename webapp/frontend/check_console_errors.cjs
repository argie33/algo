const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  const consoleMessages = [];
  const pageErrors = [];
  const requestFailures = [];

  // Capture console messages
  page.on('console', (msg) => {
    consoleMessages.push({
      type: msg.type(),
      text: msg.text(),
      args: msg.args().length
    });
  });

  // Capture page errors/exceptions
  page.on('pageerror', (err) => {
    pageErrors.push({
      name: err.name,
      message: err.message,
      stack: err.stack.split('\n').slice(0, 3).join('\n')
    });
  });

  // Capture request failures
  page.on('requestfailed', (request) => {
    requestFailures.push({
      url: request.url(),
      failure: request.failure().errorText
    });
  });

  await page.setViewportSize({ width: 1920, height: 1080 });

  try {
    console.log('Opening http://localhost:5173 and checking for errors...\n');
    await page.goto('http://localhost:5173', { waitUntil: 'networkidle', timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(3000);

    // Also check a few key pages
    const pagesToCheck = [
      '/dashboard',
      '/portfolio',
      '/signals',
      '/sectors'
    ];

    for (const route of pagesToCheck) {
      console.log(`Navigating to ${route}...`);
      await page.goto(`http://localhost:5173${route}`, { waitUntil: 'networkidle', timeout: 10000 }).catch(() => {});
      await page.waitForTimeout(2000);
    }

    // Print all collected data
    console.log('\n' + '='.repeat(70));
    console.log('CONSOLE MESSAGES');
    console.log('='.repeat(70));

    if (consoleMessages.length === 0) {
      console.log('✓ No console messages');
    } else {
      // Group by type
      const byType = {};
      consoleMessages.forEach(msg => {
        if (!byType[msg.type]) byType[msg.type] = [];
        byType[msg.type].push(msg.text);
      });

      for (const [type, msgs] of Object.entries(byType)) {
        console.log(`\n${type.toUpperCase()} (${msgs.length}):`);
        msgs.forEach((text, i) => {
          if (i < 10) { // Show first 10 of each type
            console.log(`  ${i + 1}. ${text.substring(0, 120)}`);
          }
        });
        if (msgs.length > 10) {
          console.log(`  ... and ${msgs.length - 10} more`);
        }
      }
    }

    console.log('\n' + '='.repeat(70));
    console.log('PAGE ERRORS/EXCEPTIONS');
    console.log('='.repeat(70));

    if (pageErrors.length === 0) {
      console.log('✓ No page errors');
    } else {
      pageErrors.forEach((err, i) => {
        console.log(`\n${i + 1}. ${err.name}: ${err.message}`);
        console.log(`   ${err.stack}`);
      });
    }

    console.log('\n' + '='.repeat(70));
    console.log('REQUEST FAILURES');
    console.log('='.repeat(70));

    if (requestFailures.length === 0) {
      console.log('✓ No request failures');
    } else {
      requestFailures.forEach((req, i) => {
        console.log(`${i + 1}. ${req.url}`);
        console.log(`   ${req.failure}`);
      });
    }

    console.log('\n' + '='.repeat(70));
    console.log('SUMMARY');
    console.log('='.repeat(70));
    console.log(`Console messages: ${consoleMessages.length}`);
    console.log(`Page errors: ${pageErrors.length}`);
    console.log(`Request failures: ${requestFailures.length}`);

  } catch (e) {
    console.error('Fatal error:', e.message);
  }

  await browser.close();
})();
