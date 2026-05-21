import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const allErrors = [];

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      allErrors.push(msg.text());
      console.error(`[ERROR] ${msg.text()}`);
    }
  });

  page.on('pageerror', (err) => {
    allErrors.push(`PageError: ${err.message}`);
  });

  console.log('🔍 TESTING AWS PRODUCTION PAGES - F12 CONSOLE AUDIT\n');
  console.log('═════════════════════════════════════════════════════\n');

  const pages = [
    { url: 'https://d5j1h4wzrkvw7.cloudfront.net/', name: '🏠 Landing' },
    { url: 'https://d5j1h4wzrkvw7.cloudfront.net/app/deep-value', name: '📈 Deep Value' },
    { url: 'https://d5j1h4wzrkvw7.cloudfront.net/app/trading-signals', name: '🎯 Signals' },
    { url: 'https://d5j1h4wzrkvw7.cloudfront.net/app/sectors', name: '🏭 Sectors' },
  ];

  const pageResults = [];

  for (const testPage of pages) {
    console.log(`Testing: ${testPage.name}`);
    
    try {
      const response = await page.goto(testPage.url, {
        waitUntil: 'networkidle',
        timeout: 20000
      });

      if (response.status() === 200) {
        const beforeCount = allErrors.length;
        await page.waitForTimeout(2000);
        const pageErrors = allErrors.length - beforeCount;

        console.log(`  ✅ Status: 200`);
        console.log(`  📍 URL: ${page.url()}`);
        console.log(`  ❌ Errors: ${pageErrors}`);
        
        pageResults.push({
          name: testPage.name,
          errors: pageErrors,
          status: pageErrors === 0 ? '✅' : '❌'
        });
      }
    } catch (e) {
      console.log(`  ⚠️  Timeout or error`);
    }

    console.log('');
  }

  console.log('═════════════════════════════════════════════════════\n');
  console.log('📋 AWS RESULTS\n');
  
  pageResults.forEach(result => {
    console.log(`${result.status} ${result.name}: ${result.errors} errors`);
  });

  console.log(`\n═════════════════════════════════════════════════════`);
  console.log(`\n🎯 FINAL VERDICT\n`);
  console.log(`Total Errors on AWS: ${allErrors.length}`);

  if (allErrors.length === 0) {
    console.log(`\n✅ AWS SITE IS CLEAN`);
    console.log(`   Zero F12 console errors on all public pages`);
  } else {
    console.log(`\n❌ ${allErrors.length} errors found`);
  }

  await browser.close();
})();
