import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  // Intercept all network requests
  let apiResponses = [];
  page.on('response', async resp => {
    if (resp.url().includes('/api/signals')) {
      const status = resp.status();
      const body = await resp.text();
      apiResponses.push({
        url: resp.url(),
        status,
        bodyLength: body.length,
        hasItems: body.includes('"items"'),
        bodySample: body.substring(0, 200)
      });
    }
  });
  
  await page.goto('http://localhost:5174/app/trading-signals', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);
  
  console.log('API Responses Captured:');
  apiResponses.forEach((r, i) => {
    console.log(`\n${i+1}. ${r.url}`);
    console.log(`   Status: ${r.status}`);
    console.log(`   Has 'items': ${r.hasItems}`);
    console.log(`   Body length: ${r.bodyLength}`);
    console.log(`   Sample: ${r.bodySample}`);
  });

  await browser.close();
})();
