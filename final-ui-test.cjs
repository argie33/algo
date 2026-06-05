const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  const results = {
    pages_working: [],
    pages_failed: [],
    errors: [],
    console_errors: [],
  };

  page.on('console', msg => {
    if (msg.type() === 'error') {
      const text = msg.text();
      if (!text.includes('dev_tools_migrator') && !text.includes('[webpack]')) {
        results.console_errors.push(text);
      }
    }
  });

  page.on('pageerror', error => {
    results.errors.push(`${error.message}`);
  });

  const routes = [
    { path: '/app/markets', name: 'Market Health (public)' },
    { path: '/app/economic', name: 'Economic Dashboard (public)' },
    { path: '/app/sectors', name: 'Sector Analysis (public)' },
    { path: '/app/deep-value', name: 'Deep Value Stocks (public)' },
    { path: '/app/portfolio', name: 'Portfolio Dashboard (auth)' },
    { path: '/app/trades', name: 'Trade Tracker (auth)' },
    { path: '/app/algo-dashboard', name: 'Algo Trading Dashboard (auth)' },
    { path: '/app/trading-signals', name: 'Trading Signals (auth)' },
    { path: '/app/swing', name: 'Swing Candidates (auth)' },
    { path: '/app/scores', name: 'Stock Scores (auth)' },
  ];

  console.log('🌐 TESTING FRONTEND UI\n');
  console.log('=' .repeat(60));

  for (const route of routes) {
    try {
      await page.goto(`http://localhost:5173${route.path}`, {
        waitUntil: 'domcontentloaded',
        timeout: 20000
      });

      await page.waitForTimeout(2000);

      const bodyText = await page.evaluate(() => document.body.innerText);
      const hasErrorMessage = bodyText.includes('error') && 
                            (bodyText.includes('failed') || bodyText.includes('unauthorized'));
      const hasContent = bodyText.length > 50 && !hasErrorMessage;

      if (hasContent) {
        results.pages_working.push(route.name);
        console.log(`✅ ${route.name}`);
      } else {
        results.pages_failed.push(route.name);
        console.log(`❌ ${route.name} - No content or error shown`);
      }

    } catch (e) {
      results.pages_failed.push(route.name);
      console.log(`❌ ${route.name} - ${e.message.substring(0, 50)}`);
    }
  }

  await page.close();
  await context.close();
  await browser.close();

  console.log('\n' + '=' .repeat(60));
  console.log('\n📊 FINAL TEST RESULTS\n');
  console.log(`✅ Pages working: ${results.pages_working.length}/${routes.length}`);
  console.log(`❌ Pages failed: ${results.pages_failed.length}/${routes.length}`);
  console.log(`🔴 Console errors: ${results.console_errors.length}`);
  console.log(`⚠️ Page errors: ${results.errors.length}`);

  if (results.pages_working.length > 0) {
    console.log('\n✅ WORKING PAGES:');
    results.pages_working.forEach(p => console.log(`   ✓ ${p}`));
  }

  if (results.pages_failed.length > 0) {
    console.log('\n❌ FAILED PAGES:');
    results.pages_failed.forEach(p => console.log(`   ✗ ${p}`));
  }

  const successRate = Math.round((results.pages_working.length / routes.length) * 100);
  console.log(`\n📈 SUCCESS RATE: ${successRate}%`);

  if (successRate >= 70) {
    console.log('\n🎉 SYSTEM IS MOSTLY WORKING!\n');
    process.exit(0);
  } else {
    console.log('\n⚠️ MORE WORK NEEDED\n');
    process.exit(1);
  }
})();
