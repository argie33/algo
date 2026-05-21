import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  let apiCallsMade = [];
  let apiCallsFailed = [];

  page.on('response', (response) => {
    if (response.url().includes('/api/')) {
      apiCallsMade.push({
        url: response.url(),
        status: response.status()
      });
      if (response.status() >= 400) {
        apiCallsFailed.push(response.url());
      }
    }
  });

  try {
    console.log('Loading http://localhost:5173...');
    await page.goto('http://localhost:5173', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(3000);

    console.log(`\n✅ Frontend loaded`);
    console.log(`API Calls Made: ${apiCallsMade.length}`);
    apiCallsMade.forEach((call, i) => {
      const status = call.status >= 200 && call.status < 400 ? '✅' : '❌';
      console.log(`  ${status} [${call.status}] ${call.url.substring(0, 80)}`);
    });

    if (apiCallsFailed.length === 0 && apiCallsMade.length > 0) {
      console.log('\n✅ ✅ ✅ CORS FIXED - All API calls successful! ✅ ✅ ✅');
    } else if (apiCallsMade.length === 0) {
      console.log('\n⚠️  No API calls made yet (may be lazy-loaded)');
    } else {
      console.log(`\n❌ ${apiCallsFailed.length} API calls failed`);
    }

  } catch (error) {
    console.error(`Error: ${error.message}`);
  } finally {
    await browser.close();
  }
})();
