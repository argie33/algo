const { chromium } = require('playwright');

async function checkPages() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const errors = [];

  page.on('console', msg => {
    if (msg.type() === 'error') {
      errors.push(msg.text());
    }
  });

  page.on('requestfailed', request => {
    errors.push(`Network failed: ${request.url()}`);
  });

  // List of pages to check
  const pages = [
    '/',
    '/login',
    '/dashboard',
    '/market-overview',
    '/stocks',
    '/portfolio',
    '/settings'
  ];

  const results = [];

  for (const route of pages) {
    try {
      console.log(`\n🔍 Checking ${route}...`);
      const response = await page.goto(`http://localhost:5173${route}`, {
        waitUntil: 'networkidle',
        timeout: 10000
      });

      if (!response) {
        console.log(`  ❌ No response`);
        results.push({ route, status: 'no-response', data: null });
        continue;
      }

      console.log(`  ✅ Status: ${response.status()}`);

      // Get page info
      const info = await page.evaluate(() => {
        return {
          title: document.title,
          h1s: Array.from(document.querySelectorAll('h1')).map(h => h.textContent.trim()).slice(0, 3),
          buttons: Array.from(document.querySelectorAll('button')).length,
          tables: Array.from(document.querySelectorAll('table')).length,
          textContent: document.body.textContent.substring(0, 200)
        };
      });

      console.log(`  📄 Title: ${info.title}`);
      console.log(`  📝 H1s: ${info.h1s.join(' | ')}`);
      console.log(`  🔘 Buttons: ${info.buttons}`);
      console.log(`  📊 Tables: ${info.tables}`);

      results.push({
        route,
        status: response.status(),
        title: info.title,
        data: info
      });

    } catch (error) {
      console.log(`  ❌ Error: ${error.message}`);
      results.push({ route, status: 'error', error: error.message });
    }
  }

  // Now try to navigate to the main app
  console.log('\n\n' + '='.repeat(60));
  console.log('🎯 TESTING MAIN APP NAVIGATION');
  console.log('='.repeat(60));

  try {
    console.log('\n📱 Navigating to /dashboard...');
    await page.goto('http://localhost:5173/dashboard', {
      waitUntil: 'networkidle',
      timeout: 15000
    });

    // Wait for any data to load
    await page.waitForTimeout(2000);

    // Check for API calls
    const requests = [];
    page.on('request', req => {
      if (req.url().includes('/api')) {
        requests.push(req.url());
      }
    });

    // Try to click on any navigation items
    const navItems = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('nav a, [role="navigation"] a, nav button')).map(el => ({
        text: el.textContent.trim(),
        href: el.getAttribute('href'),
        ariaLabel: el.getAttribute('aria-label')
      })).slice(0, 10);
    });

    console.log('\n🧭 Navigation Items Found:');
    navItems.forEach(item => {
      console.log(`  - ${item.text || item.ariaLabel} ${item.href ? `(${item.href})` : ''}`);
    });

  } catch (error) {
    console.log(`  ❌ Navigation error: ${error.message}`);
  }

  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('📊 SUMMARY');
  console.log('='.repeat(60));
  console.log('\nRoutes checked:');
  results.forEach(r => {
    const statusEmoji = r.status === 200 ? '✅' : '❌';
    console.log(`  ${statusEmoji} ${r.route} [${r.status}]`);
  });

  if (errors.length > 0) {
    console.log(`\n❌ Errors: ${errors.length}`);
    errors.slice(0, 5).forEach(e => console.log(`  - ${e}`));
  }

  await browser.close();
}

checkPages().catch(err => {
  console.error('Script error:', err);
  process.exit(1);
});
