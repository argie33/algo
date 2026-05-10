import { chromium } from 'playwright';

async function detailedApiTest() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const apiErrors = [];
  const apiResponses = [];
  const consoleMessages = [];

  page.on('console', msg => {
    consoleMessages.push({
      type: msg.type(),
      text: msg.text()
    });
    if (msg.type() === 'error') {
      console.error(`❌ CONSOLE ERROR: ${msg.text()}`);
    }
  });

  page.on('response', response => {
    const url = response.url();
    const status = response.status();

    if (url.includes('/api/')) {
      apiResponses.push({
        url,
        status,
        statusText: response.statusText()
      });

      if (status >= 400) {
        apiErrors.push({
          url,
          status,
          statusText: response.statusText()
        });
        console.error(`🔴 API ERROR: ${status} ${response.statusText()} - ${url}`);
      }
    }
  });

  page.on('pageerror', err => {
    console.error(`💥 PAGE ERROR: ${err.message}`);
    console.error(`   Stack: ${err.stack}`);
  });

  console.log('\n🧪 Testing API endpoints on each page...\n');

  const pages = ['/', '/portfolio', '/stocks', '/settings', '/analytics', '/algo-dashboard', '/market-overview'];

  for (const route of pages) {
    try {
      console.log(`📄 Loading: ${route}`);
      await page.goto(`http://localhost:5173${route}`, {
        waitUntil: 'networkidle',
        timeout: 20000
      }).catch(err => {
        console.warn(`  Navigation timeout: ${err.message}`);
      });

      // Wait for any async API calls
      await page.waitForTimeout(3000);

      // Get page dimensions
      const viewport = page.viewportSize();
      console.log(`  ✓ Page loaded (${viewport?.width}x${viewport?.height})`);

    } catch (err) {
      console.error(`  ✗ Error loading ${route}: ${err.message}`);
    }
  }

  await browser.close();

  console.log('\n\n╔════════════════════════════════════════╗');
  console.log('║         DETAILED API TEST REPORT       ║');
  console.log('╚════════════════════════════════════════╝');

  console.log(`\n📊 API Calls Made:`);
  console.log(`  Total: ${apiResponses.length}`);
  const successful = apiResponses.filter(r => r.status < 400).length;
  const failed = apiResponses.filter(r => r.status >= 400).length;
  console.log(`  ✓ Successful (2xx-3xx): ${successful}`);
  console.log(`  ✗ Failed (4xx-5xx): ${failed}`);

  if (apiErrors.length > 0) {
    console.log(`\n🔴 FAILED API CALLS:`);
    apiErrors.forEach((err, i) => {
      console.log(`  ${i + 1}. [${err.status}] ${err.url}`);
    });
  }

  console.log(`\n📨 All API Calls:`);
  apiResponses.forEach((res, i) => {
    const icon = res.status < 400 ? '✓' : '✗';
    console.log(`  ${icon} [${res.status}] ${res.url.replace('http://localhost:3001', '')}`);
  });

  const errorMessages = consoleMessages.filter(m => m.type === 'error');
  if (errorMessages.length > 0) {
    console.log(`\n❌ CONSOLE ERRORS (${errorMessages.length}):`);
    errorMessages.forEach((msg, i) => {
      console.log(`  ${i + 1}. ${msg.text}`);
    });
  }

  const hasIssues = apiErrors.length > 0 || errorMessages.length > 0;
  console.log(`\n${hasIssues ? '⛔ ISSUES FOUND' : '✅ ALL APIS HEALTHY'}\n`);

  process.exit(apiErrors.length > 0 ? 1 : 0);
}

detailedApiTest().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
