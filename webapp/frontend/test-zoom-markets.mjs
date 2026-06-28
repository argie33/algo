import { chromium } from 'playwright';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
await page.setViewportSize({ width: 1920, height: 1080 });

const apiData = {};
page.on('response', async (response) => {
  if (response.url().includes('/api/algo/')) {
    const ep = new URL(response.url()).pathname;
    try {
      const body = await response.text();
      apiData[ep] = { status: response.status(), body };
    } catch(e) {}
  }
});

await page.goto('http://localhost:5178/app/markets', { timeout: 30000, waitUntil: 'networkidle' });
await page.waitForTimeout(3000);

// Get ALL text from the page that contains error keywords
const errorTexts = await page.evaluate(() => {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const results = [];
  let node;
  while (node = walker.nextNode()) {
    const text = node.textContent.trim();
    if (text && (text.includes('503') || text.includes('500') || text.includes('Error') ||
        text.includes('error') || text.includes('unavailable') || text.includes('failed') ||
        text.includes('No data') || text.includes('loading'))) {
      const parent = node.parentElement;
      results.push({
        text: text.substring(0, 200),
        tag: parent ? parent.tagName : 'unknown',
        className: parent ? (String(parent.className || '')).substring(0, 60) : ''
      });
    }
  }
  return results;
});

console.log('\n=== ERROR/EMPTY TEXT FOUND IN PAGE ===');
errorTexts.forEach(t => {
  console.log(`\n  TEXT: "${t.text}"`);
  console.log(`  IN: <${t.tag} class="${t.className}">`);
});

// Take screenshots of specific regions
await page.screenshot({ path: 'markets-top.png', clip: { x: 0, y: 0, width: 1920, height: 600 } });
await page.screenshot({ path: 'markets-mid.png', clip: { x: 0, y: 600, width: 1920, height: 800 } });
await page.screenshot({ path: 'markets-bottom.png', clip: { x: 0, y: 1400, width: 1920, height: 1000 } });

// Check specific API responses for any "no_data" errors
console.log('\n=== API RESPONSES ===');
for (const [ep, data] of Object.entries(apiData)) {
  try {
    const parsed = JSON.parse(data.body);
    const hasError = parsed.errorType || parsed._error || (parsed.statusCode && parsed.statusCode >= 400);
    if (hasError) {
      console.log(`\n❌ ${ep}: ${JSON.stringify(parsed).substring(0, 300)}`);
    } else {
      console.log(`✅ ${ep}: status=${parsed.statusCode || data.status}`);
    }
  } catch(e) {
    console.log(`  ${ep}: (not JSON)`);
  }
}

await browser.close();
