import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

await page.goto('http://localhost:5174', { waitUntil: 'domcontentloaded', timeout: 10000 });

const config = await page.evaluate(() => ({
  hostname: window.location.hostname,
  api_url: window.__CONFIG__?.API_URL,
  config_object: window.__CONFIG__
}));

console.log('\n🔍 ACTUAL CONFIG AT RUNTIME:');
console.log('Hostname:', config.hostname);
console.log('API_URL value:', JSON.stringify(config.api_url));
console.log('Full config:', JSON.stringify(config.config_object, null, 2));

await browser.close();
