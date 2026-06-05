const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  const results = {
    pages_tested: [],
    errors: [],
    console_errors: [],
    network_errors: [],
    pages_working: [],
  };

  page.on('console', msg => {
    if (msg.type() === 'error') {
      results.console_errors.push(msg.text());
    }
  });

  page.on('pageerror', error => {
    results.errors.push(`PAGE ERROR: ${error.message}`);
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
      console.log(`\n📄 Testing: ${route.name}`);
      console.log(`   Loading: ${route.path}`);
      
      await page.goto(`http://localhost:5182${route.path}`, {
        waitUntil: 'networkidle',
        timeout: 15000
      });

      await page.waitForTimeout(1000);

      // Check if page loaded
      const title = await page.title();
      const bodyText = await page.evaluate(() => document.body.innerText);
      const hasContent = bodyText.length > 50;

      if (title && hasContent) {
        results.pages_working.push(route.name);
        console.log(`   ✅ LOADED - Title: ${title.substring(0, 40)}`);
      } else {
        results.errors.push(`${route.name}: Page loaded but no content`);
        console.log(`   ⚠️ LOADED BUT NO CONTENT`);
      }

    } catch (e) {
      results.errors.push(`${route.name}: ${e.message.substring(0, 80)}`);
      console.log(`   ❌ ERROR: ${e.message.substring(0, 60)}`);
    }
  }

  await page.close();
  await context.close();
  await browser.close();

  console.log('\n' + '=' .repeat(60));
  console.log('\n📊 TEST RESULTS\n');
  console.log(`✅ Pages that loaded successfully: ${results.pages_working.length}/${routes.length}`);
  console.log(`❌ Errors encountered: ${results.errors.length}`);
  console.log(`🔴 Console errors: ${results.console_errors.length}`);

  if (results.pages_working.length > 0) {
    console.log('\n✅ WORKING PAGES:');
    results.pages_working.forEach(p => console.log(`   • ${p}`));
  }

  if (results.errors.length > 0) {
    console.log('\n⚠️ ERRORS:');
    results.errors.slice(0, 10).forEach((e, i) => console.log(`   ${i + 1}. ${e}`));
    if (results.errors.length > 10) console.log(`   ... and ${results.errors.length - 10} more`);
  }

  if (results.console_errors.length > 0) {
    console.log('\n🔴 CONSOLE ERRORS:');
    [...new Set(results.console_errors)].slice(0, 5).forEach(e => console.log(`   • ${e.substring(0, 80)}`));
  }

  const successRate = Math.round((results.pages_working.length / routes.length) * 100);
  console.log(`\n📈 SUCCESS RATE: ${successRate}%\n`);

  if (successRate >= 80) {
    console.log('🎉 SYSTEM APPEARS TO BE WORKING WELL!\n');
  }
})();
