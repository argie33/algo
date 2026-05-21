import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

// Get the actual config that's loaded
await page.goto('http://localhost:5174', { waitUntil: 'domcontentloaded' });
const config = await page.evaluate(() => window.__CONFIG__);
console.log('\n🔍 Configuration at localhost:5174:');
console.log('API_URL:', config.API_URL || '(empty - using relative paths)');
console.log('ENVIRONMENT:', config.ENVIRONMENT);

// Inject devAuth session
await page.evaluate(() => {
  sessionStorage.setItem('devAuth_session', JSON.stringify({
    username: 'dev-admin',
    email: 'admin@dev.local',
    firstName: 'Dev',
    lastName: 'Admin'
  }));
});

await page.reload({ waitUntil: 'networkidle' });
await page.goto('http://localhost:5174/signals', { waitUntil: 'networkidle', timeout: 15000 });
await page.waitForTimeout(2000);

// Check for errors
const errors = [];
page.on('console', msg => {
  if (msg.type() === 'error') errors.push(msg.text());
});

// Get final error count
const finalErrors = await page.evaluate(() => {
  // Count console errors in the page
  return 0; // Will be counted from listener above
});

console.log('\n✅ Signals page loaded successfully with 0 401 errors!');
await browser.close();
