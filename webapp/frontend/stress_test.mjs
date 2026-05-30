import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  const errors = { 429: 0, 401: 0, 403: 0, other: [] };
  let completed = 0;
  let failed = 0;
  
  page.on('response', response => {
    const status = response.status();
    if (status === 429) errors[429]++;
    if (status === 401) errors[401]++;
    if (status === 403) errors[403]++;
    if (status >= 400 && status !== 429 && status !== 401 && status !== 403) {
      errors.other.push(status);
    }
    completed++;
  });
  
  page.on('requestfailed', () => {
    failed++;
  });
  
  try {
    console.log('🔥 STRESS TEST: Loading app rapidly...\n');
    
    // Load the app 3 times to stress the backend
    const promises = [];
    for (let i = 0; i < 3; i++) {
      promises.push(
        page.goto('http://localhost:5175', { waitUntil: 'load', timeout: 30000 }).catch(() => {})
      );
    }
    
    await Promise.all(promises);
    await page.waitForTimeout(2000);
    
    console.log(`\n📊 STRESS TEST RESULTS:`);
    console.log(`  Total requests: ${completed}`);
    console.log(`  Failed: ${failed}`);
    console.log(`  429 errors: ${errors[429]}`);
    console.log(`  401 errors: ${errors[401]}`);
    console.log(`  403 errors: ${errors[403]}`);
    
    if (errors[429] === 0 && errors[401] === 0 && errors[403] === 0 && failed === 0) {
      console.log('\n✅ CLEAN - No auth or rate limit errors!');
    } else {
      console.log('\n⚠️ ISSUES FOUND!');
    }
    
  } finally {
    await browser.close();
  }
})();
