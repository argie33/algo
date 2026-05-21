import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

const consoleErrors = [];
page.on('console', msg => {
  if (msg.type() === 'error') {
    consoleErrors.push(msg.text());
  }
});

console.log('\n🔍 Testing AWS F12 Console Errors...\n');

try {
  await page.goto('https://d5j1h4wzrkvw7.cloudfront.net', { waitUntil: 'networkidle', timeout: 15000 });
  
  console.log('✅ Landing page loaded');
  console.log(`F12 Console errors: ${consoleErrors.length}`);
  
  consoleErrors.slice(0,3).forEach(e => console.log(`  ERROR: ${e.substring(0, 80)}`));
} catch (e) {
  console.log('❌ Navigation failed:', e.message);
}

await browser.close();
