import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

const errors = [];
page.on('pageerror', (e) => errors.push(e.message));

console.log('Testing http://localhost:5173...');
await page.goto('http://localhost:5173', { waitUntil: 'networkidle' });
await page.waitForTimeout(2000);

if (errors.length === 0) {
  console.log('✅ NO ERRORS - Page loaded successfully!');
  const root = await page.evaluate(() => !!document.querySelector('#root > div'));
  console.log(`React app rendered: ${root}`);
} else {
  console.log('❌ ERRORS FOUND:');
  errors.forEach((e, i) => console.log(`${i+1}. ${e}`));
}

await page.screenshot({ path: 'fixed-screenshot.png' });
await browser.close();
