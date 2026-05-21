import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  let consoleErrors = [];
  let apiCalls = [];

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });

  page.on('response', (response) => {
    if (response.url().includes('/api/')) {
      apiCalls.push({ url: response.url(), status: response.status() });
    }
  });

  try {
    console.log('Testing /sectors page...');
    await page.goto('http://localhost:5173/sectors', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(2000);

    console.log(`\n✅ Page loaded`);
    console.log(`Console Errors: ${consoleErrors.length}`);
    console.log(`API Calls: ${apiCalls.length}`);
    
    apiCalls.forEach((call) => {
      const status = call.status >= 200 && call.status < 400 ? '✅' : '❌';
      console.log(`  ${status} [${call.status}] ${call.url.split('/api/')[1]}`);
    });

    const hasErrors = consoleErrors.length > 0;
    const apiWorking = apiCalls.length > 0 && apiCalls.every(c => c.status < 400);

    console.log('');
    if (!hasErrors && apiWorking) {
      console.log('✅ ✅ ✅ SYSTEM WORKING - No errors, APIs responding! ✅ ✅ ✅');
      process.exit(0);
    } else if (hasErrors) {
      console.log('❌ Console errors found:');
      consoleErrors.forEach(err => console.log(`   ${err}`));
      process.exit(1);
    } else {
      console.log('⚠️  Page working but APIs not called yet');
      process.exit(0);
    }

  } catch (error) {
    console.error(`Error: ${error.message}`);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
