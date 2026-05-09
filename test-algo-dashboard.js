const { chromium } = require('playwright');

async function testAlgoDashboard() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const errors = [];
  const apiCalls = [];

  page.on('console', msg => {
    if (msg.type() === 'error') {
      errors.push(msg.text());
    }
  });

  page.on('response', response => {
    if (response.url().includes('/api/')) {
      apiCalls.push({
        url: response.url().split('localhost:3001/')[1],
        status: response.status()
      });
    }
  });

  try {
    console.log('📱 Loading Algo Dashboard (/app/algo-dashboard)...\n');
    const response = await page.goto('http://localhost:5173/app/algo-dashboard', {
      waitUntil: 'networkidle',
      timeout: 20000
    });

    console.log(`✅ Page loaded - Status: ${response.status()}`);

    await page.waitForTimeout(2000);

    const content = await page.evaluate(() => {
      return {
        errorElements: Array.from(document.querySelectorAll('[role="alert"], .error, .MuiAlert-error')).length,
        hasContent: document.body.textContent.length > 100
      };
    });

    console.log(`\n📊 RESULTS:`);
    console.log(`  ✅ API calls: ${apiCalls.length}`);
    console.log(`  ❌ Console errors: ${errors.length}`);
    console.log(`  🔴 Page alerts: ${content.errorElements}`);
    console.log(`  📄 Has content: ${content.hasContent}`);

    if (errors.length > 0) {
      console.log(`\n❌ Console errors:`);
      errors.slice(0, 3).forEach((err, i) => {
        console.log(`  ${i + 1}. ${err.substring(0, 100)}`);
      });
    }

    const failedApis = apiCalls.filter(c => c.status >= 400);
    if (failedApis.length > 0) {
      console.log(`\n❌ Failed API calls:`);
      failedApis.forEach(api => {
        console.log(`  ${api.status} ${api.url}`);
      });
    }

  } catch (error) {
    console.log(`❌ Error: ${error.message}`);
    errors.push(error.message);
  }

  await browser.close();

  return {
    success: errors.length === 0 && failedApis.length === 0,
    errors: errors.length,
    failedApis: (apiCalls.filter(c => c.status >= 400)).length
  };
}

testAlgoDashboard().then(result => {
  const emoji = result.success ? '✅' : '❌';
  console.log(`\n${emoji} Test complete - Errors: ${result.errors}, Failed APIs: ${result.failedApis}`);
  process.exit(result.success ? 0 : 1);
}).catch(err => {
  console.error('Script error:', err);
  process.exit(1);
});
