import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();

// Track all network requests
const failedRequests = [];
page.on('response', response => {
  if (response.status() === 401) {
    failedRequests.push({
      url: response.url(),
      status: response.status(),
    });
  }
});

// Inject session and load Signals page
await page.goto('http://localhost:5174', { waitUntil: 'domcontentloaded' });
await page.evaluate(() => {
  sessionStorage.setItem('devAuth_session', JSON.stringify({
    username: 'dev-admin',
    email: 'admin@dev.local',
    firstName: 'Dev',
    lastName: 'Admin'
  }));
});
await page.reload({ waitUntil: 'networkidle' });
await page.waitForTimeout(1000);

console.log('\nNavigating to Signals page...');
await page.goto('http://localhost:5174/signals', { waitUntil: 'networkidle', timeout: 15000 });
await page.waitForTimeout(2000);

console.log('\n╔════════════════════════════════════════════╗');
console.log('║  URLs RETURNING 401 UNAUTHORIZED           ║');
console.log('╚════════════════════════════════════════════╝\n');

if (failedRequests.length === 0) {
  console.log('✅ No 401 errors found!');
} else {
  failedRequests.forEach((req, i) => {
    console.log(`${i + 1}. ${req.url}`);
  });
}

await browser.close();
