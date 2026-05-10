const { chromium } = require('playwright');

async function checkAPIcalls() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const apiCalls = [];
  const failedRequests = [];

  // Track all network requests
  page.on('request', request => {
    if (request.url().includes('/api/')) {
      apiCalls.push({
        method: request.method(),
        url: request.url(),
        status: 'pending'
      });
    }
  });

  page.on('response', response => {
    const url = response.url();
    if (url.includes('/api/')) {
      const status = response.status();
      const isError = status >= 400;

      const call = apiCalls.find(c => c.url === url);
      if (call) {
        call.status = `${status}`;
      }

      const statusEmoji = isError ? '❌' : '✅';
      console.log(`${statusEmoji} ${response.status()} ${request.method} ${url}`);

      if (isError) {
        failedRequests.push({ url, status });
      }
    }
  });

  page.on('requestfailed', request => {
    console.log(`💥 FAILED: ${request.url()} - ${request.failure().errorText}`);
    failedRequests.push({
      url: request.url(),
      error: request.failure().errorText
    });
  });

  try {
    console.log('\n🚀 Loading http://localhost:5173...\n');
    await page.goto('http://localhost:5173', { waitUntil: 'networkidle', timeout: 30000 });
    console.log('\n✅ Page loaded\n');

    // Wait for any additional async API calls
    await page.waitForTimeout(3000);

    // Check if there's any data on the page
    const dataElements = await page.evaluate(() => {
      const elements = document.querySelectorAll('[data-testid], [data-component], .data-table, table');
      return Array.from(elements).slice(0, 10).map(el => ({
        tag: el.tagName,
        testId: el.getAttribute('data-testid'),
        class: el.className,
        text: el.textContent?.substring(0, 100)
      }));
    });

    console.log('\n📊 Data Elements Found:');
    if (dataElements.length === 0) {
      console.log('  ⚠️  No data elements found - page may not be loaded');
    } else {
      dataElements.forEach((el, i) => {
        console.log(`  ${i + 1}. <${el.tag}> ${el.testId ? `[${el.testId}]` : ''}`);
      });
    }

  } catch (error) {
    console.log(`\n❌ Error: ${error.message}`);
  }

  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('📊 API CALL SUMMARY');
  console.log('='.repeat(60));

  const successful = apiCalls.filter(c => c.status && !c.status.startsWith('4') && !c.status.startsWith('5'));
  const failed = apiCalls.filter(c => c.status && (c.status.startsWith('4') || c.status.startsWith('5')));
  const pending = apiCalls.filter(c => c.status === 'pending');

  console.log(`✅ Successful: ${successful.length}`);
  console.log(`❌ Failed: ${failed.length}`);
  console.log(`⏳ Pending: ${pending.length}`);
  console.log(`💥 Network Errors: ${failedRequests.length}`);

  if (failed.length > 0) {
    console.log('\n❌ FAILED API CALLS:');
    failed.forEach(call => {
      console.log(`  ${call.status} ${call.url}`);
    });
  }

  if (failedRequests.length > 0) {
    console.log('\n💥 NETWORK FAILURES:');
    failedRequests.forEach(req => {
      console.log(`  ${req.url}`);
      if (req.error) console.log(`     Error: ${req.error}`);
    });
  }

  // List all API endpoints being called
  console.log('\n📍 API ENDPOINTS CALLED:');
  const uniqueEndpoints = [...new Set(apiCalls.map(c => c.url.split('?')[0]))];
  uniqueEndpoints.forEach(url => {
    const calls = apiCalls.filter(c => c.url.startsWith(url));
    const statuses = calls.map(c => c.status).join(', ');
    console.log(`  ${url} [${statuses}]`);
  });

  await browser.close();
}

checkAPIcalls().catch(err => {
  console.error('Script error:', err);
  process.exit(1);
});
