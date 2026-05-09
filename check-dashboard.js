const { chromium } = require('playwright');

async function checkDashboard() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const apiCalls = [];
  const errors = [];

  // Capture API calls
  page.on('response', response => {
    const url = response.url();
    if (url.includes('/api/')) {
      const status = response.status();
      apiCalls.push({
        url,
        status,
        ok: status < 400
      });
      const emoji = status < 400 ? '✅' : '❌';
      console.log(`${emoji} ${status} ${url.split('localhost:3001/')[1] || url}`);
    }
  });

  page.on('console', msg => {
    if (msg.type() === 'error') {
      errors.push(msg.text());
      console.log(`❌ CONSOLE ERROR: ${msg.text()}`);
    }
  });

  try {
    console.log('📱 Loading /app/market (Market Overview)...\n');
    await page.goto('http://localhost:5173/app/market', {
      waitUntil: 'networkidle',
      timeout: 15000
    });

    await page.waitForTimeout(2000);

    // Get page content
    const content = await page.evaluate(() => {
      return {
        title: document.title,
        headings: Array.from(document.querySelectorAll('h1, h2')).map(h => h.textContent.trim()).slice(0, 5),
        tables: document.querySelectorAll('table').length,
        charts: document.querySelectorAll('[class*="chart"]').length,
        dataElements: document.querySelectorAll('[data-testid], .data-table').length,
        errorMessages: Array.from(document.querySelectorAll('[role="alert"], .error, .error-message')).map(e => e.textContent.trim()).slice(0, 3)
      };
    });

    console.log('\n📊 Page Content:');
    console.log(`  📄 Title: ${content.title}`);
    console.log(`  📝 Headings: ${content.headings.join(' | ')}`);
    console.log(`  📊 Tables: ${content.tables}`);
    console.log(`  📈 Charts: ${content.charts}`);
    console.log(`  📋 Data Elements: ${content.dataElements}`);

    if (content.errorMessages.length > 0) {
      console.log(`  ⚠️  Error Messages:`);
      content.errorMessages.forEach(msg => console.log(`    - ${msg}`));
    }

  } catch (error) {
    console.log(`\n❌ Navigation error: ${error.message}`);
    errors.push(error.message);
  }

  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('📊 SUMMARY');
  console.log('='.repeat(60));

  const successful = apiCalls.filter(c => c.ok).length;
  const failed = apiCalls.filter(c => !c.ok).length;

  console.log(`✅ Successful API calls: ${successful}`);
  console.log(`❌ Failed API calls: ${failed}`);
  console.log(`❌ Console errors: ${errors.length}`);

  if (failed > 0) {
    console.log('\n❌ Failed endpoints:');
    apiCalls.filter(c => !c.ok).forEach(call => {
      console.log(`  ${call.status} ${call.url}`);
    });
  }

  if (errors.length > 0) {
    console.log('\n❌ Console errors:');
    errors.forEach(e => console.log(`  - ${e}`));
  }

  await browser.close();
  return { hasErrors: errors.length > 0 || failed > 0 };
}

checkDashboard().then(result => {
  process.exit(result.hasErrors ? 1 : 0);
}).catch(err => {
  console.error('Script error:', err);
  process.exit(1);
});
