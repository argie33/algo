import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  const networkErrors = [];
  const apiCalls = [];

  page.on('response', async response => {
    const url = response.url();
    if (url.includes('/api/')) {
      const status = response.status();
      apiCalls.push({
        url: url.replace(/^.*\/api\//, '/api/'),
        status,
        ok: response.ok(),
      });

      if (!response.ok()) {
        const body = await response.text().catch(() => '(no body)');
        networkErrors.push({
          url,
          status,
          body: body.substring(0, 200),
        });
      }
    }
  });

  page.on('requestfailed', request => {
    if (request.url().includes('/api/')) {
      networkErrors.push({
        url: request.url(),
        error: request.failure().errorText,
      });
    }
  });

  try {
    console.log('🔍 CHECKING API ERRORS...\n');

    await page.goto('http://localhost:5173/app/dashboard', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(5000);

    // Try to trigger API calls manually
    console.log('Attempting to refresh data...');
    const refreshBtn = await page.locator('button:has-text("Refresh")').first();
    if (await refreshBtn.isVisible()) {
      await refreshBtn.click();
      await page.waitForTimeout(3000);
    }

    console.log('\n📊 API CALL SUMMARY:');
    console.log(`Total calls: ${apiCalls.length}`);
    console.log(`Failed: ${networkErrors.length}`);

    if (apiCalls.length > 0) {
      console.log('\nAPI Calls:');
      const grouped = {};
      apiCalls.forEach(call => {
        const key = call.url;
        if (!grouped[key]) grouped[key] = { success: 0, failed: 0 };
        if (call.ok) grouped[key].success++;
        else grouped[key].failed++;
      });

      Object.entries(grouped).forEach(([url, counts]) => {
        const status = counts.failed > 0 ? '❌' : '✅';
        console.log(`  ${status} ${url}: ${counts.success} OK, ${counts.failed} failed`);
      });
    }

    if (networkErrors.length > 0) {
      console.log('\n❌ API ERRORS:');
      networkErrors.forEach(err => {
        console.log(`\nURL: ${err.url}`);
        console.log(`Status: ${err.status || err.error}`);
        if (err.body) console.log(`Body: ${err.body}`);
      });
    }

    // Check what the page shows
    const errorMsg = await page.evaluate(() => {
      return document.body.innerText.match(/API Connection Issue|persistent|error/gi);
    });

    if (errorMsg) {
      console.log('\n⚠️ Page shows error message');
    }

    // Check backend status
    console.log('\n\n🔧 Checking backend availability...');
    try {
      const backendResponse = await page.evaluate(async () => {
        try {
          const res = await fetch('http://localhost:3000/health', { mode: 'no-cors' });
          return { status: res.status, text: 'backend responding' };
        } catch (e) {
          return { error: e.message };
        }
      });
      console.log('Backend check:', backendResponse);
    } catch (e) {
      console.log('Backend not accessible:', e.message);
    }

  } catch (error) {
    console.error('Test error:', error.message);
  } finally {
    await browser.close();
  }
})();
