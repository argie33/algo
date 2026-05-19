import { chromium } from 'playwright';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  const failures = [];
  const successes = [];

  page.on('response', (response) => {
    if (response.status() >= 400) {
      failures.push({
        url: response.url(),
        status: response.status(),
        statusText: response.statusText(),
      });
      console.error(`[${response.status()}] ${response.url()}`);
    } else {
      successes.push({
        url: response.url(),
        status: response.status(),
      });
    }
  });

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      console.error(`[CONSOLE ERROR] ${msg.text()}`);
    } else if (msg.type() === 'warning') {
      console.warn(`[CONSOLE WARNING] ${msg.text()}`);
    }
  });

  page.on('pageerror', (err) => {
    console.error(`[PAGE ERROR] ${err.message}`);
  });

  try {
    console.log('Loading http://localhost:5173...\n');
    const response = await page.goto('http://localhost:5173', { waitUntil: 'networkidle', timeout: 30000 });

    console.log(`\nPage status: ${response.status()}`);

    // Wait for dynamic content
    await page.waitForTimeout(2000);

    console.log(`\n===== REQUEST SUMMARY =====`);
    console.log(`Successful requests: ${successes.length}`);
    console.log(`Failed requests: ${failures.length}`);

    if (failures.length > 0) {
      console.log(`\nFailed endpoints:`);
      failures.forEach((f, i) => {
        console.log(`  ${i + 1}. [${f.status}] ${f.url.substring(0, 80)}...`);
      });
    }

    // Get page content
    const html = await page.content();
    const hasErrors = html.includes('error') || html.includes('Error');
    console.log(`\nPage contains error text: ${hasErrors}`);

    // Check if we can see the nav menu
    const navButtons = await page.evaluate(() => {
      const buttons = document.querySelectorAll('button');
      return Array.from(buttons).map(b => b.textContent).slice(0, 10);
    });

    console.log(`\nVisible buttons: ${navButtons.length}`);
    if (navButtons.length > 0) {
      console.log('First buttons:', navButtons);
    }

  } catch (error) {
    console.error(`Error: ${error.message}`);
  } finally {
    await browser.close();
  }
})();
