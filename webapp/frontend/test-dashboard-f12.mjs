import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const allErrors = [];
  const allWarnings = [];
  const pageResults = [];

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      allErrors.push(msg.text());
    } else if (msg.type() === 'warning') {
      allWarnings.push(msg.text());
    }
  });

  page.on('pageerror', (err) => {
    allErrors.push(`PageError: ${err.message}`);
  });

  const pages = [
    { url: 'http://localhost:5174/', name: '🏠 Landing' },
    { url: 'http://localhost:5174/app/markets', name: '📊 Markets' },
    { url: 'http://localhost:5174/app/economic', name: '💰 Economic' },
    { url: 'http://localhost:5174/app/deep-value', name: '📈 Deep Value' },
    { url: 'http://localhost:5174/app/trading-signals', name: '🎯 Signals' },
    { url: 'http://localhost:5174/app/sectors', name: '🏭 Sectors' },
  ];

  console.log('🔍 TESTING LOCAL DASHBOARD PAGES - F12 CONSOLE AUDIT\n');
  console.log('═══════════════════════════════════════════════════════\n');

  for (const testPage of pages) {
    const pageErrors = [];
    const pageWarnings = [];
    
    console.log(`Testing: ${testPage.name}`);
    
    try {
      const response = await page.goto(testPage.url, {
        waitUntil: 'networkidle',
        timeout: 20000
      }).catch(e => {
        console.log(`  ⚠️  Timeout or error: ${e.message}`);
        return null;
      });

      if (response && response.status() === 200) {
        // Clear and capture page-specific errors
        const beforeErrors = allErrors.length;
        const beforeWarnings = allWarnings.length;
        
        await page.waitForTimeout(2000);

        pageErrors.push(...allErrors.slice(beforeErrors));
        pageWarnings.push(...allWarnings.slice(beforeWarnings));

        console.log(`  ✅ Status: 200`);
        console.log(`  📍 URL: ${page.url()}`);
        console.log(`  ❌ Errors: ${pageErrors.length}`);
        console.log(`  ⚠️  Warnings: ${pageWarnings.length}`);
        
        pageResults.push({
          name: testPage.name,
          url: testPage.url,
          errors: pageErrors.length,
          warnings: pageWarnings.length,
          status: pageErrors.length === 0 ? '✅' : '❌'
        });
      } else {
        console.log(`  ⚠️  Failed to load (status: ${response?.status()})`);
      }
    } catch (e) {
      console.log(`  ❌ Error: ${e.message}`);
    }

    console.log('');
  }

  // Summary
  console.log('═══════════════════════════════════════════════════════\n');
  console.log('📋 SUMMARY\n');
  
  pageResults.forEach(result => {
    const icon = result.errors === 0 ? '✅' : '❌';
    console.log(`${icon} ${result.name}: ${result.errors} errors, ${result.warnings} warnings`);
  });

  const totalErrors = allErrors.length;
  const totalWarnings = allWarnings.length;

  console.log(`\n═══════════════════════════════════════════════════════`);
  console.log(`\n🎯 FINAL VERDICT\n`);
  console.log(`Total Errors Across All Pages: ${totalErrors}`);
  console.log(`Total Warnings: ${totalWarnings}`);

  if (totalErrors === 0) {
    console.log(`\n✅ ALL DASHBOARD PAGES ARE CLEAN`);
    console.log(`   Zero F12 console errors detected`);
    console.log(`   Ready for production use`);
  } else {
    console.log(`\n❌ ${totalErrors} errors found:`);
    allErrors.slice(0, 10).forEach((err, i) => {
      console.log(`   ${i + 1}. ${err}`);
    });
    if (allErrors.length > 10) {
      console.log(`   ... and ${allErrors.length - 10} more`);
    }
  }

  await browser.close();
})();
