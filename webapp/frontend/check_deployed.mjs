import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ ignoreHTTPSErrors: true });
const page = await context.newPage();

const messages = [];
const errors = [];

page.on('console', msg => {
  const text = msg.text();
  messages.push({
    type: msg.type(),
    text: text,
  });
  if (msg.type() === 'error' || msg.type() === 'warning') {
    console.log(`[${msg.type().toUpperCase()}] ${text}`);
  }
});

page.on('pageerror', err => {
  errors.push(err.toString());
  console.log(`[PAGE_ERROR] ${err.toString()}`);
});

page.on('response', res => {
  if (res.status() >= 500) {
    console.log(`[5XX] ${res.url()} -> ${res.status()}`);
  }
});

console.log('Navigating to deployed site...');
await page.goto('https://d2u93283nn45h2.cloudfront.net', { 
  waitUntil: 'domcontentloaded',
  timeout: 30000 
}).catch(e => console.log('Nav error:', e.message));

await page.waitForTimeout(3000);

console.log('\n=== window.__CONFIG__ ===');
const config = await page.evaluate(() => {
  if (!window.__CONFIG__) return { error: 'NOT SET' };
  return window.__CONFIG__;
});
console.log(JSON.stringify(config, null, 2));

console.log('\n=== ROOT ELEMENT STATUS ===');
const rootStatus = await page.evaluate(() => {
  const root = document.getElementById('root');
  if (!root) return { error: 'No root element found' };
  const content = root.innerHTML;
  return {
    rootExists: true,
    hasContent: content.length > 0,
    contentLength: content.length,
    firstChars: content.substring(0, 150),
    errorIndicators: {
      hasErrorText: content.includes('Error'),
      has5xxText: content.includes('5xx') || content.includes('500') || content.includes('503'),
      hasLoadingText: content.includes('Loading'),
    }
  };
});
console.log(JSON.stringify(rootStatus, null, 2));

console.log('\n=== SCREENSHOT ===');
await page.screenshot({ path: '/tmp/deployed_screenshot.png', fullPage: true });
console.log('Screenshot saved');

await browser.close();
