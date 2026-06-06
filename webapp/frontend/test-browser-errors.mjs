import { chromium } from 'playwright';
import fs from 'fs';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();

// Capture console messages
const messages = [];
page.on('console', async (msg) => {
  messages.push({
    type: msg.type(),
    text: msg.text(),
    location: msg.location(),
  });
  console.log(`[${msg.type().toUpperCase()}] ${msg.text()}`);
});

// Capture page errors
page.on('pageerror', (error) => {
  console.log(`[PAGE ERROR] ${error.message}`);
  console.log(error.stack);
});

// Capture request/response errors
page.on('response', (response) => {
  if (response.status() >= 400) {
    console.log(`[HTTP ${response.status()}] ${response.url()}`);
  }
});

console.log('Navigating to http://localhost:5173...');
await page.goto('http://localhost:5173', { waitUntil: 'networkidle' });

// Wait for React to render
await page.waitForTimeout(2000);

console.log('\n=== Page loaded ===');
const title = await page.title();
console.log(`Page title: ${title}`);

// Take screenshot
await page.screenshot({ path: 'error-screenshot.png', fullPage: false });
console.log('Screenshot saved: error-screenshot.png');

// Check console messages for errors
const errors = messages.filter(m => m.type === 'error');
if (errors.length > 0) {
  console.log(`\nFound ${errors.length} console errors:`);
  errors.forEach(e => console.log(`  - ${e.text}`));
}

await browser.close();
